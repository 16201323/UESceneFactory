"""v0.4 校验工具核心函数 — QualityGuardAgent 调用。

validate_scene_core 复用 scripts/validate_scene_json.validate_scene 的字段校验逻辑。
validate_assets_core 复用 tools/check/validate_scene_assets 的资产路径校验逻辑。

核心函数与 Agent 工具装饰分离：
- 核心函数接收 dict（便于单元测试直接传入场景对象）
- Agent 工具接收 JSON 字符串（LLM 接口），内部 json.loads 后调核心函数
"""
from __future__ import annotations

import importlib.util
import logging
import os

# 模块级日志器 — 复用项目统一的 "uescenefactory" 日志体系
# mapforge_app.py 中 logging.basicConfig(level=INFO) 已配置根处理器，
# 此处只需 getLogger 即可将日志输出到文件 + 控制台
_logger = logging.getLogger("uescenefactory.validation_tools")


# ---- 延迟加载 tools/check/validate_scene_assets.py（非包模块，用 importlib 按文件路径加载）----

_asset_mod = None  # 缓存加载的模块实例，避免重复加载


def _load_asset_checker():
    """用 importlib 从文件路径加载 validate_scene_assets 模块。

    tools/check/ 不是 Python 包（无 __init__.py），无法用 from...import 导入，
    改用 importlib.util.spec_from_file_location 按文件路径加载。
    """
    # 计算 tools/check/validate_scene_assets.py 的绝对路径
    # 本文件在 ai/tools/，向上两级到项目根，再进入 tools/check/
    check_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "check")
    mod_path = os.path.join(check_dir, "validate_scene_assets.py")
    spec = importlib.util.spec_from_file_location("validate_scene_assets", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_asset_mod():
    """获取（或首次加载并缓存）validate_scene_assets 模块实例。"""
    global _asset_mod
    if _asset_mod is None:
        _asset_mod = _load_asset_checker()
    return _asset_mod


# ---- 核心校验函数 ----

def validate_scene_core(scene: dict) -> dict:
    """校验场景 JSON 字段完整性。

    复用 scripts/validate_scene_json.validate_scene 的校验逻辑：
    - 顶层键检查（未知键报错）
    - 各分区必填字段检查（scene/landscape/layers/grass/wheat/placements/lighting/weather）
    - 字段类型/范围检查（weight 0~1、枚举值等）

    Args:
        scene: 场景 JSON 字典

    Returns:
        {"errors": [...], "warnings": [...]} — errors 为空表示字段校验通过
    """
    from scripts.validate_scene_json import validate_scene
    _logger.info("[FIELD] 开始字段完整性校验 (场景名=%s)", scene.get("scene", {}).get("name", "(未命名)"))
    errors, warnings = validate_scene(scene)

    # 逐条记录字段错误 — 方便定位缺字段/类型错/枚举值非法
    if errors:
        _logger.warning("[FIELD] 发现 %d 项字段错误:", len(errors))
        for i, e in enumerate(errors, 1):
            _logger.warning("[FIELD]   错误 %d/%d: %s", i, len(errors), e)
    else:
        _logger.info("[FIELD] 字段错误: 0 项 (结构校验通过)")

    # 逐条记录字段警告
    if warnings:
        _logger.info("[FIELD] 发现 %d 项字段警告:", len(warnings))
        for i, w in enumerate(warnings, 1):
            _logger.info("[FIELD]   警告 %d/%d: %s", i, len(warnings), w)
    else:
        _logger.info("[FIELD] 字段警告: 0 项")

    return {"errors": errors, "warnings": warnings}


def validate_assets_core(scene: dict, content_dir: str | None = None) -> list[str]:
    """校验场景 JSON 中引用的资产路径是否真实存在于 Content 目录。

    复用 tools/check/validate_scene_assets 的逻辑：
    1. collect_asset_refs(scene) 提取全部资产引用 [(desc, ue_path), ...]
    2. ue_path_to_disk(path, content_dir) 将 UE 路径映射到磁盘文件并检查存在性
    3. 非 /Game/ 开头的路径跳过（相对路径等交给构建端处理）
    4. scene.target_level 跳过（待生成关卡，允许不存在）

    Args:
        scene: 场景 JSON 字典
        content_dir: UE 项目 Content 目录绝对路径；为 None 或空时返回空列表

    Returns:
        缺失资产描述列表，格式 ["缺失 [字段位置]: UE路径", ...]；空列表=全部存在
    """
    # content_dir 为空 → 无法校验磁盘存在性，返回空列表
    if not content_dir:
        _logger.info("[ASSET] content_dir 为空, 跳过资产路径校验")
        return []

    _logger.info("[ASSET] 开始资产路径校验 (content_dir=%s)", content_dir)
    mod = _get_asset_mod()
    # 设置全局 CONTENT_DIR 供 collect_asset_refs 内部 group 放置检查使用
    # （collect_asset_refs 在处理 group 类型时用 CONTENT_DIR[0] 检查 asset_prefix+"0"）
    mod.CONTENT_DIR = [content_dir]

    refs = mod.collect_asset_refs(scene)
    _logger.info("[ASSET] 收集到 %d 条资产引用", len(refs))
    missing = []
    checked = 0
    for desc, path in refs:
        # 非 /Game/ 开头的路径跳过（相对路径等异常交给构建端处理）
        if not path.startswith("/Game/"):
            continue
        # target_level 是待生成的输出关卡，允许不存在
        if desc == "scene.target_level":
            continue
        # 检查磁盘存在性
        checked += 1
        if not mod.ue_path_to_disk(path, content_dir):
            missing.append("缺失 [%s]: %s" % (desc, path))
            _logger.warning("[ASSET] 资产缺失: [%s] %s", desc, path)

    if missing:
        _logger.warning("[ASSET] 资产校验完成: 检查 %d 条, 缺失 %d 条", checked, len(missing))
    else:
        _logger.info("[ASSET] 资产校验完成: 检查 %d 条, 缺失 0 条 (全部存在)", checked)
    return missing


def validate_quality_core(scene: dict) -> dict:
    """校验场景 JSON 语义质量（数值范围、条件必填、几何边界等）。

    复用 scripts/validate_scene_quality.validate_scene_quality 的校验逻辑：
    - 数值范围（bank_ratio[0,1] 等）
    - 条件必填（height_pattern.type 驱动的必填字段）
    - 草麦品种必填
    - 几何边界（坐标是否超出地形范围）
    - 河流参数下限
    - 水流速度一致性

    与 validate_scene_core 的区别：
    - validate_scene_core 检查"结构正确性"（字段名/类型/必填/枚举）
    - validate_quality_core 检查"语义合理性"（数值范围/条件组合/几何边界）

    Args:
        scene: 场景 JSON 字典

    Returns:
        {"errors": [...], "warnings": [...]} — errors 为空表示质量校验通过
    """
    _logger.info("[QUALITY] 开始语义质量校验 (场景名=%s)", scene.get("scene", {}).get("name", "(未命名)"))
    from scripts.validate_scene_quality import validate_scene_quality
    errors, warnings = validate_scene_quality(scene)

    # 逐条记录错误 — 方便从日志中定位具体哪个字段超范围/缺失/越界
    if errors:
        _logger.warning("[QUALITY] 发现 %d 项质量错误:", len(errors))
        for i, e in enumerate(errors, 1):
            _logger.warning("[QUALITY]   错误 %d/%d: %s", i, len(errors), e)
    else:
        _logger.info("[QUALITY] 质量错误: 0 项 (语义校验通过)")

    # 逐条记录警告 — 警告不阻断流程但记录在案, 方便排查潜在问题
    if warnings:
        _logger.info("[QUALITY] 发现 %d 项质量警告:", len(warnings))
        for i, w in enumerate(warnings, 1):
            _logger.info("[QUALITY]   警告 %d/%d: %s", i, len(warnings), w)
    else:
        _logger.info("[QUALITY] 质量警告: 0 项")

    return {"errors": errors, "warnings": warnings}
