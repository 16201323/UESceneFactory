"""v0.3 SceneJSON 模型单元测试。

SceneJSON 是 JSONBuilderAgent 的输出模型，映射 build_scene.py 的顶层 JSON 结构。
"""
import pytest

from ai.models.scene_json import (
    SceneInfo,
    LandscapeConfig,
    PlacementConfig,
    LightingConfig,
    WeatherConfig,
    SceneJSON,
)


# ─── SceneInfo 测试 ───

def test_scene_info_minimal():
    """SceneInfo 仅传必填字段（name, target_level），description 默认空。"""
    info = SceneInfo(name="测试场景", target_level="/Game/Maps/Generated/TestScene")
    assert info.name == "测试场景"
    assert info.target_level == "/Game/Maps/Generated/TestScene"
    assert info.description == ""


def test_scene_info_full():
    """SceneInfo 传入所有字段。"""
    info = SceneInfo(
        name="森林场景",
        target_level="/Game/Maps/Generated/Forest",
        description="一片茂密的森林",
    )
    assert info.description == "一片茂密的森林"


# ─── LandscapeConfig 测试 ───

def test_landscape_defaults():
    """LandscapeConfig 使用默认值（对齐 build_scene.py 默认值）。"""
    lc = LandscapeConfig()
    assert lc.material == ""
    assert lc.section_size_quads == 63
    assert lc.num_subsections == 1
    assert lc.component_count_x == 8
    assert lc.component_count_y == 8
    assert lc.location == [0, 0, 0]
    assert lc.rotation == [0, 0, 0]
    assert lc.scale == [100, 100, 100]
    assert lc.layers == []
    assert lc.grass is None
    assert lc.wheat is None
    assert lc.height_pattern is None


def test_landscape_with_height_pattern():
    """LandscapeConfig 接受 height_pattern 为 dict（C++ 层解析，结构复杂）。"""
    lc = LandscapeConfig(
        height_pattern={
            "type": "features",
            "hills": [{"center_x_m": 100, "center_y_m": 200, "radius_m": 50, "height_m": 30}],
        }
    )
    assert lc.height_pattern["type"] == "features"
    assert len(lc.height_pattern["hills"]) == 1


def test_landscape_with_layers():
    """LandscapeConfig 接受 layers 数组，每项为 dict（含 info/weight/weight_pattern）。"""
    lc = LandscapeConfig(
        layers=[
            {"info": "/Game/LayerInfo/Grass_LayerInfo", "weight": 0.5},
            {"info": "/Game/LayerInfo/Dirt_LayerInfo", "weight": 0.3,
             "weight_pattern": {"pattern": "height_based", "height_min_m": 0}},
        ]
    )
    assert len(lc.layers) == 2
    assert lc.layers[0]["weight"] == 0.5
    assert lc.layers[1]["weight_pattern"]["pattern"] == "height_based"


# ─── PlacementConfig 测试 ───

def test_placement_defaults():
    """PlacementConfig 使用默认值（type 默认 static）。"""
    p = PlacementConfig(asset="/Game/Props/Tree")
    assert p.type == "static"
    assert p.asset == "/Game/Props/Tree"
    assert p.location == [0, 0, 0]
    assert p.rotation == [0, 0, 0]
    assert p.scale == [1, 1, 1]
    assert p.material_override is None
    assert p.grid is None
    assert p.instances is None
    assert p.asset_prefix is None
    assert p.count is None


def test_placement_instanced_grid():
    """PlacementConfig 支持 instanced_grid 类型（含 grid 配置）。"""
    p = PlacementConfig(
        type="instanced_grid",
        asset="/Game/Props/Tree_Fir",
        grid={"pattern": "circle", "rows": 10, "cols": 10, "spacing": [500, 500, 0]},
    )
    assert p.type == "instanced_grid"
    assert p.grid["pattern"] == "circle"


def test_placement_group():
    """PlacementConfig 支持 group 类型（含 asset_prefix 和 count）。"""
    p = PlacementConfig(
        type="group",
        asset_prefix="/Game/Heliport/Object_",
        count=10,
    )
    assert p.type == "group"
    assert p.asset_prefix == "/Game/Heliport/Object_"
    assert p.count == 10


# ─── LightingConfig 测试 ───

def test_lighting_defaults():
    """LightingConfig 所有子项默认 None。"""
    lc = LightingConfig()
    assert lc.directional_light is None
    assert lc.sky_light is None
    assert lc.sky_atmosphere is None
    assert lc.height_fog is None


def test_lighting_with_directional():
    """LightingConfig 接受 directional_light 为 dict。"""
    lc = LightingConfig(
        directional_light={
            "location": [0, 0, 3000],
            "rotation": [-45, 35, 0],
            "intensity": 50000,
            "color": [1.0, 0.9, 0.7],
        }
    )
    assert lc.directional_light["intensity"] == 50000


# ─── WeatherConfig 测试 ───

def test_weather_defaults():
    """WeatherConfig 所有子项默认 None。"""
    wc = WeatherConfig()
    assert wc.volumetric_clouds is None
    assert wc.post_process is None


def test_weather_with_clouds():
    """WeatherConfig 接受 volumetric_clouds 为 dict。"""
    wc = WeatherConfig(volumetric_clouds={"location": [0, 0, 2000]})
    assert wc.volumetric_clouds["location"] == [0, 0, 2000]


# ─── SceneJSON 整体测试 ───

def test_scene_json_minimal():
    """SceneJSON 仅传必填的 scene/landscape/grass/height_pattern/lighting/weather 分区。

    L1 根因修复后 grass/height_pattern/lighting/weather 均为必填,
    缺失会分别导致灰色地形/平坦地形/场景全黑/无云。
    """
    sj = SceneJSON(
        scene=SceneInfo(name="最小场景", target_level="/Game/Maps/Generated/Min"),
        landscape=LandscapeConfig(
            grass={"grass_type": "/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass",
                   "grass_mesh": "/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a",
                   "layer_name": "Grass", "density": 120.0},
            height_pattern={"type": "flat"},
        ),
        lighting=LightingConfig(),
        weather=WeatherConfig(),
    )
    assert sj.scene.name == "最小场景"
    assert sj.landscape is not None
    assert sj.landscape.grass is not None
    assert sj.landscape.height_pattern is not None
    assert sj.ground is None
    assert sj.placements == []
    assert sj.lighting is not None
    assert sj.weather is not None


def test_scene_json_rejects_null_landscape():
    """SceneJSON 拒绝 landscape=null — 根因修复: 蓝图 terrain_type 始终暗示需要地形。"""
    with pytest.raises(ValueError, match="landscape.*必填"):
        SceneJSON(
            scene=SceneInfo(name="错误场景", target_level="/Game/Maps/Generated/Bad"),
            landscape=None,
        )


def test_scene_json_rejects_missing_landscape():
    """SceneJSON 拒绝省略 landscape 分区 — 等价于 landscape=None。"""
    with pytest.raises(ValueError, match="landscape.*必填"):
        SceneJSON(
            scene=SceneInfo(name="错误场景", target_level="/Game/Maps/Generated/Bad"),
        )


def test_scene_json_full():
    """SceneJSON 传入所有分区。"""
    sj = SceneJSON(
        scene=SceneInfo(name="完整场景", target_level="/Game/Maps/Generated/Full"),
        landscape=LandscapeConfig(
            grass={"grass_type": "/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass",
                   "grass_mesh": "/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a",
                   "layer_name": "Grass", "density": 120.0},
            height_pattern={"type": "hill"},
        ),
        ground={"asset": "/Game/Ground/Plane"},
        placements=[
            PlacementConfig(asset="/Game/Props/Tree"),
            PlacementConfig(type="group", asset_prefix="/Game/Heliport/Object_", count=10),
        ],
        lighting=LightingConfig(directional_light={"intensity": 50000}),
        weather=WeatherConfig(volumetric_clouds={"location": [0, 0, 2000]}),
    )
    assert sj.landscape.height_pattern["type"] == "hill"
    assert sj.ground["asset"] == "/Game/Ground/Plane"
    assert len(sj.placements) == 2
    assert sj.placements[1].type == "group"
    assert sj.lighting.directional_light["intensity"] == 50000
    assert sj.weather.volumetric_clouds is not None


def test_scene_json_model_dump():
    """SceneJSON.model_dump() 生成 build_scene.py 可消费的 dict 结构。"""
    sj = SceneJSON(
        scene=SceneInfo(name="测试", target_level="/Game/Maps/Generated/Test"),
        landscape=LandscapeConfig(
            grass={"grass_type": "/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass",
                   "grass_mesh": "/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a",
                   "layer_name": "Grass", "density": 120.0},
            height_pattern={"type": "flat"},
        ),
        placements=[PlacementConfig(asset="/Game/Props/Rock")],
        lighting=LightingConfig(),
        weather=WeatherConfig(),
    )
    d = sj.model_dump()
    assert d["scene"]["name"] == "测试"
    assert d["landscape"]["height_pattern"]["type"] == "flat"
    assert d["placements"][0]["asset"] == "/Game/Props/Rock"
    assert d["ground"] is None
    assert d["lighting"] is not None
    assert d["weather"] is not None
