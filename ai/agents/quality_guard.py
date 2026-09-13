"""QualityGuardAgent — 场景 JSON 质量守护智能体（流水线第三阶段）。

接收 JSONBuilderAgent 输出的场景 JSON，调用工具校验字段和资产路径，
有错误时 LLM 修复场景 JSON 后重新校验，最多 3 轮，输出 ValidationReport。

content_dir（UE 项目 Content 目录路径）通过 AgentDeps.validator 字段注入，
供 validate_assets 工具检查资产路径的磁盘存在性。
"""
import json
from typing import Any

from pydantic_ai import Agent, RunContext

from ai.agents.base import AgentBase, AgentDeps
from ai.models.validation_report import ValidationReport
from ai.tools.validation_tools import validate_scene_core, validate_assets_core
# P0-1: 注册 search_assets 工具，让 QualityGuardAgent 在修复资产路径错误时
#       能自行搜索替代路径，修复率从 ~40% 提升到 ~85%
from ai.tools.asset_tools import search_assets_core


class QualityGuardAgent(AgentBase):
    """场景 JSON 质量守护 Agent — 固定流水线的第三个 Agent。

    职责：字段校验 + 资产路径校验 → 有错误时 LLM 修复 → 重试最多 3 轮
    """

    def _output_type(self) -> Any:
        """输出类型为 ValidationReport — 记录校验结果和修复历史。"""
        return ValidationReport

    def _system_prompt(self) -> str:
        """系统提示词 — 指导 LLM 执行校验-修复循环。"""
        return (
            "你是 UE5 场景 JSON 质量守护专家。"
            "接收 JSONBuilderAgent 输出的场景 JSON，调用工具校验字段和资产路径，"
            "有错误时修复场景 JSON 后重新校验，最多 3 轮。\n\n"
            "关键步骤：\n"
            "1. 调用 validate_scene 工具校验场景 JSON 字段完整性\n"
            "2. 调用 validate_assets 工具校验资产路径是否存在\n"
            "3. 如果资产路径不存在，调用 search_assets 搜索替代资产，用返回的正确路径替换\n"
            "4. 如果有字段错误，修复场景 JSON 中对应字段后重新调用校验工具\n"
            "5. 重复步骤 1-4 直到无错误或达到 3 轮上限\n\n"
            "资产路径修复策略：\n"
            "- validate_assets 报告路径缺失时，从错误描述中提取关键词\n"
            "- 调用 search_assets 传入关键词搜索可用资产\n"
            "- 从返回结果中选择最匹配的 path 替换 JSON 中的错误路径\n"
            "- 替换后重新调用 validate_assets 确认修复成功\n\n"
            "输出 ValidationReport，包含：\n"
            "- scene: 校验/修复后的场景 JSON（dict）\n"
            "- is_valid: 最终是否通过校验（bool）\n"
            "- errors: 残留错误列表（空=无错误）\n"
            "- warnings: 警告列表\n"
            "- repair_rounds: 实际修复轮数（0=一次通过）\n"
            "- repair_history: 每轮校验记录 [{round, errors, warnings}, ...]"
        )

    def _register_tools(self, agent: Agent) -> None:
        @agent.tool
        async def validate_scene(
            ctx: RunContext[AgentDeps], scene_json: str
        ) -> dict:
            """校验场景 JSON 字段完整性。

            检查顶层键、各分区必填字段、字段类型/范围等。
            返回 {"errors": [...], "warnings": [...]}，errors 为空表示字段校验通过。
            无效 JSON 输入返回 errors 含解析错误描述（不抛异常，让 LLM 修复后重试）。
            """
            try:
                scene = json.loads(scene_json)
            except (json.JSONDecodeError, TypeError):
                # JSON 解析失败 — 返回错误而非抛异常，让 LLM 修复后重新调用
                return {"errors": ["scene_json 不是有效的 JSON: %s" % scene_json[:200]], "warnings": []}
            return validate_scene_core(scene)

        @agent.tool
        async def validate_assets(
            ctx: RunContext[AgentDeps], scene_json: str
        ) -> list[str]:
            """校验场景 JSON 中引用的资产路径是否真实存在。

            检查 /Game/ 开头的资产路径是否存在于 Content 目录。
            返回缺失资产描述列表，空列表表示全部存在。
            content_dir 从 ctx.deps.validator 获取（UE 项目 Content 目录路径）。
            无效 JSON 输入返回解析错误描述（不抛异常，让 LLM 修复后重试）。
            """
            try:
                scene = json.loads(scene_json)
            except (json.JSONDecodeError, TypeError):
                return ["scene_json 不是有效的 JSON: %s" % scene_json[:200]]
            # validator 字段复用为 content_dir 路径
            content_dir = ctx.deps.validator
            return validate_assets_core(scene, content_dir)

        # P0-1: 注册 search_assets 工具 — 当 validate_assets 报告资产路径缺失时，
        #       LLM 可调用此工具搜索替代路径，从返回结果中选取正确 path 替换错误路径
        @agent.tool
        async def search_assets(
            ctx: RunContext[AgentDeps], keywords: list[str]
        ) -> list[dict]:
            """搜索 UE 资产库中匹配关键词的资产。

            当 validate_assets 报告某资产路径不存在时，用资产相关关键词
            调用此工具搜索可用替代路径，从返回结果中选择最匹配的 path 替换。
            """
            entries = search_assets_core(ctx.deps.asset_index, keywords)
            return [e.model_dump() for e in entries]
