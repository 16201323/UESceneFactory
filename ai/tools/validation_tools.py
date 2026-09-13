"""v0.4 校验工具核心函数 — QualityGuardAgent 调用。

validate_scene_core 复用 scripts/validate_scene_json.validate_scene 的字段校验逻辑。
validate_assets_core 复用 tools/check/validate_scene_assets 的资产路径校验逻辑。

核心函数与 Agent 工具装饰分离：
- 核心函数接收 dict（便于单元测试直接传入场景对象）
- Agent 工具接收 JSON 字符串（LLM 接口），内部 json.loads 后调核心函数
"""
from __future__ import annotations

import importlib.util
import os


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
    errors, warnings = validate_scene(scene)
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
        return []

    mod = _get_asset_mod()
    # 设置全局 CONTENT_DIR 供 collect_asset_refs 内部 group 放置检查使用
    # （collect_asset_refs 在处理 group 类型时用 CONTENT_DIR[0] 检查 asset_prefix+"0"）
    mod.CONTENT_DIR = [content_dir]

    refs = mod.collect_asset_refs(scene)
    missing = []
    for desc, path in refs:
        # 非 /Game/ 开头的路径跳过（相对路径等异常交给构建端处理）
        if not path.startswith("/Game/"):
            continue
        # target_level 是待生成的输出关卡，允许不存在
        if desc == "scene.target_level":
            continue
        # 检查磁盘存在性
        if not mod.ue_path_to_disk(path, content_dir):
            missing.append("缺失 [%s]: %s" % (desc, path))
    return missing
