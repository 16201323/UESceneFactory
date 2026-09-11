"""v0.2 SceneBlueprint 模型单元测试。"""
import pytest

from ai.models.blueprint import AssetEntry, ExperienceRef, SceneBlueprint


def test_asset_entry_path_only():
    """AssetEntry 仅传 path 时，其余字段为空字符串。"""
    entry = AssetEntry(path="/Game/Props/Tree")
    assert entry.path == "/Game/Props/Tree"
    assert entry.name == ""
    assert entry.category == ""
    assert entry.subfolder == ""


def test_asset_entry_full():
    """AssetEntry 传入所有字段时正确存储。"""
    entry = AssetEntry(
        path="/Game/Props/Tree",
        name="SM_Tree",
        category="vegetation",
        subfolder="Trees",
    )
    assert entry.path == "/Game/Props/Tree"
    assert entry.name == "SM_Tree"
    assert entry.category == "vegetation"
    assert entry.subfolder == "Trees"


def test_experience_ref_minimal():
    """ExperienceRef 仅传必填字段，keywords 默认空列表。"""
    ref = ExperienceRef(id=1, user_desc="a scene", scene_type="flat", rating=4)
    assert ref.id == 1
    assert ref.user_desc == "a scene"
    assert ref.scene_type == "flat"
    assert ref.rating == 4
    assert ref.keywords == []


def test_scene_blueprint_minimal():
    """SceneBlueprint 仅传必填的意图字段，规划字段使用默认值。"""
    bp = SceneBlueprint(
        terrain_type="hills",
        has_water=False,
        has_river=False,
        has_grass=True,
        has_wheat=False,
        scene_type="features",
    )
    assert bp.terrain_type == "hills"
    assert bp.has_water is False
    assert bp.has_grass is True
    assert bp.placements == []
    assert bp.keywords == []
    assert bp.assets == []
    assert bp.template_ref is None


def test_scene_blueprint_full():
    """SceneBlueprint 传入所有字段时正确存储。"""
    bp = SceneBlueprint(
        terrain_type="mountains",
        has_water=True,
        has_river=True,
        has_grass=True,
        has_wheat=False,
        placements=["village", "tower"],
        keywords=["peak", "valley"],
        scene_type="features",
        assets=[AssetEntry(path="/Game/Props/Rock")],
        design_rules=["rule1", "rule2"],
        experience_refs=[
            ExperienceRef(id=1, user_desc="test", scene_type="mountains", rating=5)
        ],
        template_ref="mountains.json",
        lighting_style="golden_sunset",
        weather_style="cloudy",
    )
    assert bp.terrain_type == "mountains"
    assert bp.has_water is True
    assert bp.placements == ["village", "tower"]
    assert len(bp.assets) == 1
    assert len(bp.design_rules) == 2
    assert len(bp.experience_refs) == 1
    assert bp.template_ref == "mountains.json"
    assert bp.lighting_style == "golden_sunset"
    assert bp.weather_style == "cloudy"
