"""v0.4 校验工具核心函数单元测试。

validate_scene_core 包装 scripts/validate_scene_json.validate_scene，
validate_assets_core 包装 tools/check/validate_scene_assets 的资产校验逻辑。
核心函数与 Agent 工具装饰分离，便于直接传入 dict 测试。
"""
import pytest
from ai.tools.validation_tools import validate_scene_core, validate_assets_core


# 复用 test_phase06_validator 的场景模式
GOOD_SCENE = {
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/M', 'section_size_quads': 63,
        'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8,
        'layers': [{'info': '/Game/L', 'weight': 1.0}]
    }
}

# 坏场景：landscape 非空但缺少 section_size_quads 等 4 个必填字段
BAD_SCENE = {'landscape': {'material': '/Game/M'}}


# ---- validate_scene_core ----

def test_validate_scene_core_valid():
    """有效场景 → errors 为空。"""
    result = validate_scene_core(GOOD_SCENE)
    assert result["errors"] == []
    assert isinstance(result["warnings"], list)


def test_validate_scene_core_invalid():
    """无效场景 → errors 非空，含缺少必填字段错误。"""
    result = validate_scene_core(BAD_SCENE)
    assert len(result["errors"]) > 0
    assert any("section_size_quads" in e for e in result["errors"])


def test_validate_scene_core_returns_dict():
    """返回 dict 含 errors 和 warnings 两个键。"""
    result = validate_scene_core({})
    assert "errors" in result
    assert "warnings" in result


# ---- validate_assets_core ----

def test_validate_assets_core_no_content_dir():
    """content_dir=None → 返回空列表（无法校验磁盘存在性）。"""
    assert validate_assets_core(GOOD_SCENE, content_dir=None) == []


def test_validate_assets_core_empty_content_dir():
    """content_dir='' → 返回空列表。"""
    assert validate_assets_core(GOOD_SCENE, content_dir="") == []


def test_validate_assets_core_empty_scene(tmp_path):
    """空场景 → 无资产引用 → 返回空列表。"""
    assert validate_assets_core({}, content_dir=str(tmp_path)) == []


def test_validate_assets_core_missing_asset(tmp_path):
    """资产缺失 → 返回包含缺失描述的列表。"""
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {'material': '/Game/MissingMat'}
    }
    result = validate_assets_core(scene, content_dir=str(tmp_path))
    assert len(result) == 1
    assert "MissingMat" in result[0]


def test_validate_assets_core_valid_asset(tmp_path):
    """资产存在 → 返回空列表。"""
    # 创建 /Game/Mat → content_dir/Mat.uasset
    (tmp_path / "Mat.uasset").touch()
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {'material': '/Game/Mat'}
    }
    assert validate_assets_core(scene, content_dir=str(tmp_path)) == []
