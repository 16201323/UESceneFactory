"""QualityGuardAgent — 场景 JSON 质量守护智能体（流水线第三阶段）。

接收 JSONBuilderAgent 输出的场景 JSON，调用工具校验字段、资产路径和语义质量，
有错误时 LLM 修复场景 JSON 后重新校验，最多 3 轮（程序化强制上限），输出 ValidationReport。

性能优化:
- 合并 validate_scene + validate_assets + validate_quality 为单一 validate_all 工具，减少 LLM 往返次数
- 添加程序化轮次计数器（闭包变量），到达 3 轮后工具返回 MAX_ROUNDS_REACHED 信号，
  强制 LLM 停止重试并输出当前结果（原先"最多3轮"仅是文字约束，LLM 可无限重试）

content_dir（UE 项目 Content 目录路径）通过 AgentDeps.validator 字段注入，
供 validate_all 工具检查资产路径的磁盘存在性。
"""
import json
import logging
from typing import Any

from pydantic_ai import Agent, RunContext

from ai.agents.base import AgentBase, AgentDeps
from ai.models.validation_report import ValidationReport
from ai.tools.validation_tools import validate_scene_core, validate_assets_core, validate_quality_core
# search_assets 工具 — 当 validate_all 报告资产路径缺失时，
# LLM 可调用此工具搜索替代路径，修复率从 ~40% 提升到 ~85%
from ai.tools.asset_tools import search_assets_core

# 模块级日志器 — 复用项目统一的 "uescenefactory" 日志体系
# validate_all 工具每次调用都会记录轮次/各类错误数, 方便追踪 LLM 修复循环过程
_logger = logging.getLogger("uescenefactory.quality_guard")


class QualityGuardAgent(AgentBase):
    """场景 JSON 质量守护 Agent — 固定流水线的第三个 Agent。

    职责：字段校验 + 资产路径校验 → 有错误时 LLM 修复 → 重试最多 3 轮（程序化强制）
    """

    def _output_type(self) -> Any:
        """输出类型为 ValidationReport — 记录校验结果和修复历史。"""
        return ValidationReport

    def _system_prompt(self) -> str:
        """系统提示词 — 指导 LLM 执行校验-修复循环。

        性能优化: 合并两个校验工具为 validate_all，减少 LLM 往返次数；
        轮次计数器由工具程序化追踪，到达上限后工具返回 MAX_ROUNDS_REACHED 信号。
        """
        return (
            "你是 UE5 场景 JSON 质量守护专家。"
            "接收 JSONBuilderAgent 输出的场景 JSON，调用 validate_all 工具同时校验"
            "字段完整性、资产路径和语义质量，有错误时修复后重新校验，最多 3 轮。\n\n"
            "关键步骤：\n"
            "1. 调用 validate_all 工具校验场景 JSON（字段+资产+质量一次性完成）\n"
            "2. 如果 asset_errors 非空，调用 search_assets 搜索替代路径并替换\n"
            "3. 如果 field_errors 或 quality_errors 非空，修复对应字段后重新调用 validate_all\n"
            "   quality_errors 常见问题：数值超范围(bank_ratio>1)、条件必填缺失"
            "(terraced缺step_height_m)、几何越界(坐标超出地形)、河流流速≤湖面流速\n"
            "4. 重复步骤 1-3 直到 is_valid=true 或工具返回 MAX_ROUNDS_REACHED\n\n"
            "⚠️ 轮次上限：validate_all 工具内置轮次计数器，第 4 次调用时返回"
            " MAX_ROUNDS_REACHED 信号。收到此信号后必须停止重试，将当前 JSON 和"
            "残留错误写入 ValidationReport 输出。\n\n"
            "资产路径修复策略：\n"
            "- validate_all 的 asset_errors 报告路径缺失时，从错误描述中提取关键词\n"
            "- 调用 search_assets 传入关键词搜索可用资产\n"
            "- 从返回结果中选择最匹配的 path 替换 JSON 中的错误路径\n"
            "- 替换后重新调用 validate_all 确认修复成功\n\n"
            "输出 ValidationReport，包含：\n"
            "- scene: 校验/修复后的场景 JSON（dict）\n"
            "- is_valid: 最终是否通过校验（bool）\n"
            "- errors: 拋留错误列表（空=无错误）\n"
            "- warnings: 警告列表\n"
            "- repair_rounds: 实际修复轮数（0=一次通过，等于最后一次 validate_all 的 round 值减 1）\n"
            "- repair_history: 每轮校验记录 [{round, errors, warnings}, ...]"
        )

    def _register_tools(self, agent: Agent) -> None:
        # 程序化轮次计数器 — 闭包可变变量，每次 run 新建 Agent 实例时重置为 0
        # 到达 _MAX_ROUNDS(3) 后，validate_all 返回 MAX_ROUNDS_REACHED 信号强制停止
        # 原先"最多3轮"仅是系统提示词文字约束，LLM 可无视并无限重试（实测 13 次调用）
        _MAX_ROUNDS = 3
        _round_counter = [0]

        @agent.tool
        async def validate_all(
            ctx: RunContext[AgentDeps], scene_json: str
        ) -> dict:
            """一次性校验场景 JSON 的字段完整性、资产路径和语义质量。

            合并 validate_scene + validate_assets + validate_quality 为单一工具，减少 LLM 往返次数。
            内置轮次计数器：每次调用 +1，超过 _MAX_ROUNDS(3) 后返回 MAX_ROUNDS_REACHED。
            返回 {round, max_rounds, field_errors, field_warnings, asset_errors,
                  quality_errors, quality_warnings, total_errors, is_valid}。
            无效 JSON 输入返回解析错误（不抛异常，让 LLM 修复后重试）。
            """
            _round_counter[0] += 1
            current_round = _round_counter[0]
            _logger.info("[VALIDATE-ALL] ===== 轮次 %d/%d 开始 =====", current_round, _MAX_ROUNDS)

            # 轮次上限检查 — 超过最大轮次时强制停止，返回信号让 LLM 输出当前结果
            if current_round > _MAX_ROUNDS:
                _logger.warning("[VALIDATE-ALL] 已达轮次上限 %d, 强制停止 (返回 MAX_ROUNDS_REACHED 信号)", _MAX_ROUNDS)
                return {
                    "round": current_round,
                    "max_rounds": _MAX_ROUNDS,
                    "signal": "MAX_ROUNDS_REACHED",
                    "message": "已达到最大校验轮数(%d)，请停止重试，将当前 JSON 和残留错误写入 ValidationReport 输出" % _MAX_ROUNDS,
                }

            # JSON 解析 — 失败时返回错误而非抛异常，让 LLM 修复后重试
            try:
                scene = json.loads(scene_json)
            except (json.JSONDecodeError, TypeError) as e:
                _logger.error("[VALIDATE-ALL] JSON 解析失败: %s (输入前200字符: %s)", e, scene_json[:200])
                return {
                    "round": current_round,
                    "max_rounds": _MAX_ROUNDS,
                    "field_errors": ["scene_json 不是有效的 JSON: %s" % scene_json[:200]],
                    "field_warnings": [],
                    "asset_errors": [],
                    "total_errors": 1,
                    "is_valid": False,
                }

            _logger.info("[VALIDATE-ALL] JSON 解析成功, 开始三合一校验")

            # 字段校验 — 检查顶层键、必填字段、类型/范围（原 validate_scene 逻辑）
            _logger.info("[VALIDATE-ALL] 步骤1/3: 字段完整性校验")
            field_result = validate_scene_core(scene)
            field_errors = field_result.get("errors", [])
            field_warnings = field_result.get("warnings", [])
            _logger.info("[VALIDATE-ALL] 字段校验: 错误 %d 项, 警告 %d 项", len(field_errors), len(field_warnings))

            # 资产路径校验 — 检查 /Game/ 路径是否存在于 Content 目录（原 validate_assets 逻辑）
            # validator 字段复用为 content_dir 路径
            _logger.info("[VALIDATE-ALL] 步骤2/3: 资产路径校验 (content_dir=%s)", ctx.deps.validator)
            content_dir = ctx.deps.validator
            asset_errors = validate_assets_core(scene, content_dir)
            _logger.info("[VALIDATE-ALL] 资产校验: 缺失 %d 项", len(asset_errors))

            # 质量校验 — 检查数值范围、条件必填、几何边界等语义缺陷（validate_scene_quality 逻辑）
            _logger.info("[VALIDATE-ALL] 步骤3/3: 语义质量校验")
            quality_result = validate_quality_core(scene)
            quality_errors = quality_result.get("errors", [])
            quality_warnings = quality_result.get("warnings", [])
            _logger.info("[VALIDATE-ALL] 质量校验: 错误 %d 项, 警告 %d 项", len(quality_errors), len(quality_warnings))

            total_errors = len(field_errors) + len(asset_errors) + len(quality_errors)

            # 汇总日志 — 一行展示本轮校验全貌, 方便快速判断是否需要修复
            _logger.info("[VALIDATE-ALL] 轮次 %d 汇总: 总错误 %d (字段%d+资产%d+质量%d), is_valid=%s",
                         current_round, total_errors,
                         len(field_errors), len(asset_errors), len(quality_errors),
                         total_errors == 0)
            if total_errors == 0:
                _logger.info("[VALIDATE-ALL] ===== 轮次 %d 通过! =====", current_round)
            else:
                _logger.warning("[VALIDATE-ALL] ===== 轮次 %d 未通过, LLM 需修复后重试 =====", current_round)

            return {
                "round": current_round,
                "max_rounds": _MAX_ROUNDS,
                "field_errors": field_errors,
                "field_warnings": field_warnings,
                "asset_errors": asset_errors,
                "quality_errors": quality_errors,
                "quality_warnings": quality_warnings,
                "total_errors": total_errors,
                "is_valid": total_errors == 0,
            }

        # search_assets 工具 — 当 validate_all 的 asset_errors 报告路径缺失时，
        # LLM 可调用此工具搜索替代路径，从返回结果中选取正确 path 替换错误路径
        @agent.tool
        async def search_assets(
            ctx: RunContext[AgentDeps], keywords: list[str]
        ) -> list[dict]:
            """搜索 UE 资产库中匹配关键词的资产。

            当 validate_all 的 asset_errors 报告某资产路径不存在时，用资产相关关键词
            调用此工具搜索可用替代路径，从返回结果中选择最匹配的 path 替换。
            """
            entries = search_assets_core(ctx.deps.asset_index, keywords)
            return [e.model_dump() for e in entries]
