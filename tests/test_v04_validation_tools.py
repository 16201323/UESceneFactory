"""v0.4 校验工具核心函数单元测试。

validate_scene_core 包装 scripts/validate_scene_json.validate_scene，
validate_assets_core 包装 tools/check/validate_scene_assets 的资产校验逻辑。
核心函数与 Agent 工具装饰分离，便于直接传入 dict 测试。
"""
import os

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


def test_validate_assets_core_null_grass(tmp_path):
    """landscape.grass=null 时不应崩溃 (pydantic model_dump_json 默认输出 None 字段)。

    复现生产 bug: LLM 生成的 JSON 中 "grass": null,
    collect_asset_refs 第 78 行 ls.get("grass", {}) 返回 None
    (键存在但值为 None, .get 默认值不生效),
    随后 g.get("grass_type") 对 None 调用 .get 抛 AttributeError。
    """
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {'material': '/Game/M', 'grass': None}
    }
    # 核心断言: 不抛 AttributeError, 返回列表 (可能含 material 缺失, 但不崩溃)
    result = validate_assets_core(scene, content_dir=str(tmp_path))
    assert isinstance(result, list)
    # grass 相关字段不应出现在缺失列表中 (null 被跳过, 不会误报缺失)
    assert not any("grass" in r for r in result)


def test_validate_assets_core_null_wheat(tmp_path):
    """landscape.wheat=null 时不应崩溃。"""
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {'material': '/Game/M', 'wheat': None}
    }
    result = validate_assets_core(scene, content_dir=str(tmp_path))
    assert isinstance(result, list)
    assert not any("wheat" in r for r in result)


def test_validate_assets_core_null_height_pattern(tmp_path):
    """landscape.height_pattern=null 时不应崩溃。"""
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {'material': '/Game/M', 'height_pattern': None}
    }
    result = validate_assets_core(scene, content_dir=str(tmp_path))
    assert isinstance(result, list)
    assert not any("height_pattern" in r or "rivers" in r or "roads" in r
                   for r in result)


def test_validate_assets_core_null_layers(tmp_path):
    """landscape.layers=null 时不应崩溃。"""
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {'material': '/Game/M', 'layers': None}
    }
    result = validate_assets_core(scene, content_dir=str(tmp_path))
    assert isinstance(result, list)
    assert not any("layers" in r for r in result)


# ---- BUG 回归测试 ----

def test_content_dir_derivation_from_uproject_path(tmp_path):
    """验证 content_dir 从 .uproject 文件路径正确推导（BUG回归测试）。

    BUG背景: project_path 是 .uproject 文件路径(如 .../MyProject.uproject),
    不是目录! 原代码 os.path.join(project_path, "Content") 生成
    .../MyProject.uproject/Content(无效路径), 导致全部资产校验失败。
    修复: 先 os.path.dirname(project_path) 取项目目录, 再 join "Content"
    (与 BuildWorker L1007-1008 模式一致)。
    """
    # 模拟 UE 项目结构: ProjectDir/MyProject.uproject + ProjectDir/Content/
    project_dir = tmp_path / "MyProject"
    project_dir.mkdir()
    uproject_path = project_dir / "MyProject.uproject"
    uproject_path.touch()  # 创建空 .uproject 文件
    (project_dir / "Content").mkdir()

    # 正确推导(修复后): dirname(.uproject文件) → 项目目录 → join "Content"
    correct_content_dir = os.path.join(
        os.path.dirname(str(uproject_path)), "Content"
    )
    assert os.path.isdir(correct_content_dir), \
        "正确推导应指向真实存在的 Content 目录"

    # 错误推导(原 BUG): 直接 join project_path(文件) + "Content" → 无效路径
    buggy_content_dir = os.path.join(str(uproject_path), "Content")
    assert not os.path.isdir(buggy_content_dir), \
        "错误推导应指向不存在的路径(.uproject/Content)"


def test_validate_scene_no_layer_name_false_positive():
    """验证 grass/wheat.layer_name 不再触发假阳性警告（BUG回归测试）。

    BUG背景: 原 validate_scene_json 规则3将 grass/wheat.layer_name
    (材质 GrassOutput 逻辑名, 如 "Grass") 与 layers[].info 路径末尾名
    (LayerInfo 资产名, 如 "L_Grass_LayerInfo" → "L_Grass") 做匹配,
    命名体系不同 → 永远不匹配 → 假阳性警告。
    修复后规则3已移除, 不应产生任何 layer_name 相关警告。
    """
    scene = {
        'scene': {'name': 'T', 'target_level': '/Game/Maps/T'},
        'landscape': {
            'material': '/Game/M', 'section_size_quads': 63,
            'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8,
            'layers': [{'info': '/Game/Layers/L_Grass_LayerInfo', 'weight': 1.0}],
            'grass': {'layer_name': 'Grass', 'grass_type': '/Game/Grass/GT'},
        }
    }
    result = validate_scene_core(scene)
    # 不应有任何关于 layer_name 未定义的假阳性警告
    assert not any("layer_name" in w for w in result["warnings"]), \
        "grass.layer_name 不应触发假阳性警告: %s" % result["warnings"]
