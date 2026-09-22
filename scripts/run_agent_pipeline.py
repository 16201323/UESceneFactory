"""三阶段 Agent 流水线启动脚本 — 命令行运行完整场景生成管线。

流水线:
    用户自然语言描述
    → ScenePlannerAgent  (意图解析 + 资产搜索 + 经验检索 → SceneBlueprint)
    → JSONBuilderAgent   (知识注入 + 资产搜索 → SceneJSON)
    → QualityGuardAgent  (字段校验 + 资产校验 + LLM 修复 → ValidationReport)
    → 最终场景 JSON

用法:
    python scripts/run_agent_pipeline.py --desc "山谷草地，有一条河流穿过"
    python scripts/run_agent_pipeline.py -d "山坡上的小村庄" -o output/scene.json
    python scripts/run_agent_pipeline.py   # 交互式输入描述

配置来源: ~/.uescenefactory_config.json（与 GUI 应用共享同一份配置文件）
"""
import argparse
import asyncio
import json
import logging
import os
import sys

# 确保项目根目录在 sys.path 中（本文件在 scripts/，向上一级）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 配置日志 — CLI 模式下需要显式配置, 否则底层模块(validation_tools/auto_repair/quality_guard)
# 的日志不会输出。格式: 时间 | 级别 | 模块 | 消息
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("uescenefactory.pipeline")

from ai.agents.base import AgentDeps
from ai.agents.scene_planner import ScenePlannerAgent
from ai.agents.json_builder import JSONBuilderAgent
from ai.agents.quality_guard import QualityGuardAgent
from ai.models.scene_json import normalize_height_pattern


# ============================================================================
# 配置加载 — 复用 GUI 应用的 ~/.uescenefactory_config.json 配置文件
# ============================================================================

# 默认配置（与 mapforge_app.py 的 DEFAULT_CONFIG 保持一致）
_DEFAULT_CONFIG = {
    "llm_base_url": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "llm_api_key": "${ALIYUN_APIKEY}",
    "llm_model": "glm-5.2",
    "project_path": "",
}


def load_config():
    """从用户主目录加载配置文件（与 GUI 应用共享）。

    读取 ~/.uescenefactory_config.json，合并默认值后返回。
    文件不存在时返回默认配置。
    """
    config_path = os.path.join(os.path.expanduser("~"), ".uescenefactory_config.json")
    cfg = _DEFAULT_CONFIG.copy()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass  # 文件不存在，用默认值
    except Exception as e:
        print("[警告] 配置文件加载失败，使用默认值: %s" % e)
    return cfg


def resolve_env_value(value):
    """解析 ${VAR_NAME} 格式的环境变量引用。

    用户可在配置中填写 ${ALIYUN_APIKEY} 而非明文密钥，
    运行时从系统环境变量解析实际值，避免密钥明文存储。
    非 ${...} 格式则原样返回。
    """
    if value and isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


# ============================================================================
# 依赖初始化 — 注入知识库/资产索引/经验检索器到 AgentDeps
# ============================================================================

def init_deps(config):
    """初始化 AgentDeps — 注入后端组件供 Agent 工具函数使用。

    Returns:
        (deps, bank) — AgentDeps 实例和 ExperienceBank 引用（需在流水线结束后关闭）
    """
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever

    # 知识库目录（data/knowledge, data/templates 在项目根下）
    knowledge = KnowledgePack(
        os.path.join(_ROOT, "data", "knowledge"),
        templates_dir=os.path.join(_ROOT, "data", "templates"),
    )
    # 资产目录（config/asset_catalog.json 在项目根下）
    asset_index = AssetIndex(os.path.join(_ROOT, "config", "asset_catalog.json"))
    # 经验库（默认 ~/.uescenefactory/experience.db）
    bank = ExperienceBank()
    retriever = ExperienceRetriever(bank)

    # content_dir: UE 项目 Content 目录（用于 QualityGuardAgent 的资产路径校验）
    # validator 字段复用为 content_dir 路径；project_path 未配置时为 None（跳过磁盘校验）
    # BUG修复: project_path 是 .uproject 文件路径(如 .../MyUETest5_8_2.uproject),
    # 不是目录! 直接 os.path.join(project_path, "Content") 会生成
    # .../MyUETest5_8_2.uproject/Content (无效路径), 导致全部资产校验失败。
    # 正确做法: 先 dirname 取项目目录, 再 join "Content" (与 BuildWorker L1007 一致)
    project_path = config.get("project_path", "")
    content_dir = (
        os.path.join(os.path.dirname(project_path), "Content")
        if project_path else None
    )

    deps = AgentDeps(
        knowledge=knowledge,
        asset_index=asset_index,
        experience_bank=bank,
        retriever=retriever,
        validator=content_dir,
    )
    return deps, bank


# ============================================================================
# 三阶段流水线执行
# ============================================================================

async def run_pipeline(user_desc, config, deps):
    """运行三阶段 Agent 流水线，返回 ValidationReport。

    Args:
        user_desc: 用户自然语言场景描述
        config: 配置字典（含 llm_model/llm_api_key/llm_base_url）
        deps: AgentDeps 依赖注入容器

    Returns:
        ValidationReport — 包含最终场景 JSON 和校验历史
    """
    model_name = config.get("llm_model", "glm-5.2")
    api_key = resolve_env_value(config.get("llm_api_key", ""))
    base_url = config.get("llm_base_url", "")

    if not api_key:
        print("[错误] API Key 未配置。")
        print("       请在 GUI 设置对话框中填写 API Key，或设置环境变量 %s" %
              config.get("llm_api_key", "${ALIYUN_APIKEY}"))
        sys.exit(1)

    # P1-1: 分级模型策略 — 允许每个阶段使用不同模型
    # stage_models 是可选配置, 不配置时所有阶段使用全局 llm_model(向后兼容)
    # 建议配置: Stage1/3 用小模型(glm-4-flash)省时, Stage2 保持大模型保质量
    stage_models = config.get("stage_models", {})
    model_stage1 = stage_models.get("stage1", model_name)
    model_stage2 = stage_models.get("stage2", model_name)
    model_stage3 = stage_models.get("stage3", model_name)

    # ---- Stage 1: ScenePlannerAgent — 意图解析 + 资产搜索 + 经验检索 ----
    print("=" * 60)
    print("Stage 1: 场景规划 (ScenePlannerAgent)  [模型: %s]" % model_stage1)
    print("=" * 60)
    planner = ScenePlannerAgent(model_stage1, api_key, base_url=base_url, deps=deps)
    result1 = await planner.run(user_desc)
    blueprint = result1.output
    blueprint_json = blueprint.model_dump_json()
    print("蓝图生成完成:")
    print("  terrain_type = %s" % blueprint.terrain_type)
    print("  placements   = %s" % blueprint.placements)
    print("  keywords     = %s" % blueprint.keywords)
    print("  资产数       = %d" % len(blueprint.assets))
    print("  经验引用     = %d" % len(blueprint.experience_refs))
    print("  template_ref = %s" % blueprint.template_ref)
    # 补打结构化参数, 验证尺寸/地域/原描述是否正确提取
    print("  size_m       = %s" % blueprint.size_m)
    print("  region       = %s" % blueprint.region)
    print("  user_desc    = %s" % blueprint.user_desc)

    # ---- Stage 2: JSONBuilderAgent — 知识注入 + 资产搜索 → 场景 JSON ----
    print()
    print("=" * 60)
    print("Stage 2: 场景 JSON 生成 (JSONBuilderAgent)  [模型: %s]" % model_stage2)
    print("=" * 60)
    builder = JSONBuilderAgent(model_stage2, api_key, base_url=base_url, deps=deps)
    result2 = await builder.run(blueprint_json)
    scene_json = result2.output
    # 后处理: 补全道路推平参数 + 散布道路排除字段(防止C++跳过地形推平/物体落在路上)
    if scene_json.landscape and scene_json.landscape.height_pattern:
        normalize_height_pattern(scene_json.landscape.height_pattern)
    # 确定性修复-校验闭环: 绿色层修复→质量校验→黄色层修复→再校验
    # 在 LLM 校验前先自动修复可确定性修复的语义缺陷, 减少 LLM 往返次数
    logger.info("[Stage2] ===== 确定性修复-校验闭环开始 =====")
    from scripts.auto_repair_scene import repair_and_validate
    _scene_dict = scene_json.model_dump()
    _repairs, _q_errors, _q_warnings = repair_and_validate(_scene_dict)
    if _repairs:
        print("确定性修复: %d 项" % len(_repairs))
        logger.info("[Stage2] 确定性修复: %d 项", len(_repairs))
        for _r in _repairs:
            print("  [REPAIR] %s" % _r)
            logger.info("[Stage2] [REPAIR] %s", _r)
    else:
        logger.info("[Stage2] 确定性修复: 0 项 (无需修复)")
    if _q_errors:
        print("残留质量错误: %d 项 (交由 Stage 3 LLM 修复)" % len(_q_errors))
        logger.warning("[Stage2] 残留质量错误: %d 项 (需 LLM 修复)", len(_q_errors))
        for i, _e in enumerate(_q_errors, 1):
            logger.warning("[Stage2]   残留错误 %d/%d: %s", i, len(_q_errors), _e)
    else:
        logger.info("[Stage2] 残留质量错误: 0 项")
    if _q_warnings:
        logger.info("[Stage2] 质量警告: %d 项", len(_q_warnings))
        for i, _w in enumerate(_q_warnings, 1):
            logger.info("[Stage2]   警告 %d/%d: %s", i, len(_q_warnings), _w)
    logger.info("[Stage2] ===== 确定性修复-校验闭环结束 =====")
    scene_json_str = json.dumps(_scene_dict, ensure_ascii=False)
    scene_name = scene_json.scene.name if scene_json.scene else "unnamed"
    print("场景 JSON 生成完成: scene.name = %s" % scene_name)

    # ---- Stage 3: QualityGuardAgent — 字段校验 + 资产校验 + LLM 修复 ----
    print()
    print("=" * 60)
    print("Stage 3: 质量校验 (QualityGuardAgent)  [模型: %s]" % model_stage3)
    print("=" * 60)
    guard = QualityGuardAgent(model_stage3, api_key, base_url=base_url, deps=deps)
    result3 = await guard.run(scene_json_str)
    report = result3.output
    # 安全网: 确保质量守护LLM未丢弃道路推平+散布排除字段
    _ls = report.scene.get("landscape")
    if isinstance(_ls, dict) and _ls.get("height_pattern"):
        normalize_height_pattern(_ls["height_pattern"])
    # 安全网: 确定性修复-校验闭环 (防止 LLM 修复引入新的语义缺陷)
    logger.info("[Stage3] ===== 安全网修复-校验闭环开始 =====")
    from scripts.auto_repair_scene import repair_and_validate
    _repairs, _q_errors, _q_warnings = repair_and_validate(report.scene)
    if _repairs:
        print("安全网修复: %d 项" % len(_repairs))
        logger.info("[Stage3] 安全网修复: %d 项", len(_repairs))
        for _r in _repairs:
            print("  [REPAIR] %s" % _r)
            logger.info("[Stage3] [REPAIR] %s", _r)
    else:
        logger.info("[Stage3] 安全网修复: 0 项 (LLM 未引入新缺陷)")
    if _q_errors:
        report.errors.extend(_q_errors)
        report.is_valid = False
        print("安全网残留质量错误: %d 项" % len(_q_errors))
        logger.warning("[Stage3] 安全网残留质量错误: %d 项", len(_q_errors))
        for i, _e in enumerate(_q_errors, 1):
            logger.warning("[Stage3]   残留错误 %d/%d: %s", i, len(_q_errors), _e)
    else:
        logger.info("[Stage3] 安全网残留质量错误: 0 项")
    if _q_warnings:
        logger.info("[Stage3] 安全网质量警告: %d 项", len(_q_warnings))
        for i, _w in enumerate(_q_warnings, 1):
            logger.info("[Stage3]   警告 %d/%d: %s", i, len(_q_warnings), _w)
    logger.info("[Stage3] ===== 安全网修复-校验闭环结束 =====")
    print("校验完成:")
    print("  is_valid      = %s" % report.is_valid)
    print("  errors        = %d 项" % len(report.errors))
    print("  warnings      = %d 项" % len(report.warnings))
    print("  repair_rounds = %d" % report.repair_rounds)
    if report.errors:
        for e in report.errors:
            print("  [错误] %s" % e)
    if report.warnings:
        for w in report.warnings:
            print("  [警告] %s" % w)

    return report


# ============================================================================
# 命令行入口
# ============================================================================

def main():
    """命令行入口 — 解析参数、加载配置、运行流水线、输出结果。"""
    parser = argparse.ArgumentParser(
        description="UE 场景工厂 — 三阶段 Agent 流水线 (ScenePlanner → JSONBuilder → QualityGuard)",
    )
    parser.add_argument(
        "--desc", "-d", type=str, default="",
        help="场景自然语言描述（不提供则交互式输入）",
    )
    parser.add_argument(
        "--output", "-o", type=str, default="",
        help="输出 JSON 文件路径（不提供则仅打印到终端）",
    )
    args = parser.parse_args()

    # 获取用户描述
    user_desc = args.desc
    if not user_desc:
        print("请输入场景描述（输入后按回车确认）:")
        user_desc = input().strip()
    if not user_desc:
        print("[错误] 场景描述不能为空")
        sys.exit(1)

    print("用户描述: %s" % user_desc)
    print()

    # 加载配置 + 初始化依赖
    config = load_config()
    deps, bank = init_deps(config)

    try:
        # 运行流水线
        report = asyncio.run(run_pipeline(user_desc, config, deps))

        # 输出最终场景 JSON
        output_json = json.dumps(report.scene, indent=2, ensure_ascii=False)
        print()
        print("=" * 60)
        print("最终场景 JSON (is_valid=%s):" % report.is_valid)
        print("=" * 60)
        print(output_json)

        # 保存到文件
        if args.output:
            output_dir = os.path.dirname(args.output)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_json)
            print()
            print("已保存到: %s" % args.output)

    finally:
        # 确保在任何路径下 SQLite 连接都被关闭
        try:
            bank.close()
        except Exception as e:
            print("[警告] 关闭经验库连接失败: %s" % e)


if __name__ == "__main__":
    main()
