# -*- coding: utf-8 -*-
"""auto_repair_scene 自动修复单元测试。

覆盖绿色层(数值范围/条件必填/草麦必填/河流参数)和
黄色层(几何越界/水流速度)全部修复项,
以及"修复→复验通过"的集成测试和边界场景测试。

测试策略:
  1) 构造含缺陷的场景 -> 调 auto_repair_scene -> 断言值被修正 + 日志记录
  2) 修复后再调 validate_scene_quality -> 断言对应错误消失
  3) aggressive=False 时黄色层不执行
"""
import copy
import pytest

from scripts.auto_repair_scene import auto_repair_scene
from scripts.validate_scene_quality import validate_scene_quality


# ===========================================================================
# 测试基座: 最小合法场景构造器 (与 test_v04_validate_scene_quality 对齐)
# ===========================================================================

def _base_scene(hp_type="flat", **hp_extra):
    """构造最小合法场景, hp_extra 追加 height_pattern 字段"""
    hp = {"type": hp_type}
    # 非 flat 类型默认添加 1 个丘陵, 满足内容丰富度检查 (hills 不可全空)
    if hp_type != "flat" and "hills" not in hp_extra:
        hp["hills"] = [{"center_x_m": 100, "center_y_m": 100,
                        "radius_m": 50, "height_m": 80}]
    hp.update(hp_extra)
    return {
        "scene": {"name": "T", "target_level": "/Game/Maps/T"},
        "landscape": {
            "material": "/Game/M",
            "section_size_quads": 63,
            "num_subsections": 1,
            "component_count_x": 8,
            "component_count_y": 8,
            "scale": [100, 100, 100],
            "height_pattern": hp,
            # 内容丰富度检查: layers 不可为空, 至少 2 个图层
            "layers": [
                {"info": "/Game/L_Grass", "weight": 0.7},
                {"info": "/Game/L_Dirt", "weight": 0.3},
            ],
        },
        # 内容丰富度检查: placements 不可为空
        "placements": [
            {"type": "instances", "asset": "/Game/A",
             "instances": [{"location": [0, 0, 0]}]},
        ],
    }


# 默认地形尺寸: 8*63*1*100/100 = 504m x 504m
TERRAIN_X = 504.0
TERRAIN_Y = 504.0


# ===========================================================================
# 1) 绿色层: 数值范围修复
# ===========================================================================

class TestRepairRanges:
    """绿色层 1): 数值范围 clamp + peak_min/max 交换"""

    def test_bank_ratio_clamp_high(self):
        """bank_ratio=1.5 -> clamp 到 1.0"""
        scene = _base_scene("terraced", bank_ratio=1.5)
        repairs = auto_repair_scene(scene)
        assert scene["landscape"]["height_pattern"]["bank_ratio"] == 1.0
        assert any("bank_ratio" in r for r in repairs)

    def test_bank_ratio_clamp_low(self):
        """bank_ratio=-0.1 -> clamp 到 0.0"""
        scene = _base_scene("terraced", bank_ratio=-0.1)
        repairs = auto_repair_scene(scene)
        assert scene["landscape"]["height_pattern"]["bank_ratio"] == 0.0
        assert any("bank_ratio" in r for r in repairs)

    def test_bank_ratio_in_range_no_repair(self):
        """bank_ratio=0.25 在范围内 -> 不修复"""
        scene = _base_scene("terraced", bank_ratio=0.25)
        repairs = auto_repair_scene(scene)
        assert not any("bank_ratio" in r for r in repairs)

    def test_perturbation_strength_clamp(self):
        """perturbation_strength=2.0 -> clamp 到 1.0"""
        scene = _base_scene("flat", perturbation_strength=2.0)
        repairs = auto_repair_scene(scene)
        assert scene["landscape"]["height_pattern"]["perturbation_strength"] == 1.0
        assert any("perturbation_strength" in r for r in repairs)

    def test_peak_min_gt_max_swap(self):
        """karst: peak_min=50 > peak_max=20 -> 交换"""
        scene = _base_scene("karst", peak_count=10,
                            peak_height_min_m=50, peak_height_max_m=20,
                            peak_radius_m=20)
        repairs = auto_repair_scene(scene)
        hp = scene["landscape"]["height_pattern"]
        assert hp["peak_height_min_m"] == 20
        assert hp["peak_height_max_m"] == 50
        assert any("peak_height_min_m" in r for r in repairs)
        assert any("peak_height_max_m" in r for r in repairs)

    def test_peak_min_le_max_no_swap(self):
        """karst: peak_min=10 <= peak_max=40 -> 不交换"""
        scene = _base_scene("karst", peak_count=10,
                            peak_height_min_m=10, peak_height_max_m=40,
                            peak_radius_m=20)
        repairs = auto_repair_scene(scene)
        assert not any("peak_height_min_m" in r and "->" in r for r in repairs)

    def test_bank_ratio_bool_not_touched(self):
        """bank_ratio=True 不被当数值修复 (isinstance(True,int)==True 守卫)"""
        scene = _base_scene("terraced", bank_ratio=True)
        repairs = auto_repair_scene(scene)
        assert scene["landscape"]["height_pattern"]["bank_ratio"] is True
        assert not any("bank_ratio" in r for r in repairs)

    def test_range_repair_then_validate_passes(self):
        """修复后复验: bank_ratio 越界错误消失"""
        scene = _base_scene("terraced", bank_ratio=1.5,
                            step_height_m=3.0, step_width_m=12.0,
                            base_height_m=0.0)
        errors_before, _ = validate_scene_quality(scene)
        assert any("bank_ratio" in e for e in errors_before)
        auto_repair_scene(scene)
        errors_after, _ = validate_scene_quality(scene)
        assert not any("bank_ratio" in e for e in errors_after)


# ===========================================================================
# 2) 绿色层: 草麦数值范围修复
# ===========================================================================

class TestRepairVarietyRanges:
    """绿色层: cull_dist clamp + end>start 修复"""

    def test_cull_dist_clamp_high(self):
        """end_cull_dist=200000 -> clamp 到 100000"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 3000, "end_cull_dist": 200000,
                            }])
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["height_pattern"]["grass_varieties"][0]
        assert v["end_cull_dist"] == 100000
        assert any("end_cull_dist" in r for r in repairs)

    def test_cull_dist_clamp_low(self):
        """start_cull_dist=0 -> clamp 到 1"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 0, "end_cull_dist": 30000,
                            }])
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["height_pattern"]["grass_varieties"][0]
        assert v["start_cull_dist"] == 1
        assert any("start_cull_dist" in r for r in repairs)

    def test_end_le_start_fix(self):
        """end_cull_dist(3000) <= start_cull_dist(5000) -> end=start+1000"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 5000, "end_cull_dist": 3000,
                            }])
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["height_pattern"]["grass_varieties"][0]
        assert v["end_cull_dist"] == 6000
        assert v["start_cull_dist"] == 5000
        assert any("end_cull_dist" in r for r in repairs)

    def test_cull_dist_in_range_no_repair(self):
        """cull_dist 在范围内 -> 不修复"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 3000, "end_cull_dist": 30000,
                            }])
        repairs = auto_repair_scene(scene)
        assert not any("cull_dist" in r for r in repairs)


# ===========================================================================
# 3) 绿色层: 条件必填字段修复
# ===========================================================================

class TestRepairConditionalRequired:
    """绿色层 2): type 必填字段缺失 -> 用默认值填充"""

    def test_terraced_fill_all(self):
        """terraced 缺全部4个必填字段 -> 填充默认值"""
        scene = _base_scene("terraced")
        repairs = auto_repair_scene(scene)
        hp = scene["landscape"]["height_pattern"]
        assert hp["step_height_m"] == 3.0
        assert hp["step_width_m"] == 12.0
        assert hp["bank_ratio"] == 0.25
        assert hp["base_height_m"] == 0.0
        assert sum("step_height_m" in r for r in repairs) == 1
        assert sum("step_width_m" in r for r in repairs) == 1
        assert sum("bank_ratio" in r for r in repairs) == 1
        assert sum("base_height_m" in r for r in repairs) == 1

    def test_terraced_partial_fill(self):
        """terraced 只缺 step_height_m -> 仅填充该字段"""
        scene = _base_scene("terraced", step_width_m=12.0,
                            bank_ratio=0.25, base_height_m=0.0)
        repairs = auto_repair_scene(scene)
        hp = scene["landscape"]["height_pattern"]
        assert hp["step_height_m"] == 3.0
        assert sum("step_height_m" in r for r in repairs) == 1
        assert not any("step_width_m" in r for r in repairs)

    def test_karst_fill_all(self):
        """karst 缺全部4个必填字段 -> 填充默认值"""
        scene = _base_scene("karst")
        repairs = auto_repair_scene(scene)
        hp = scene["landscape"]["height_pattern"]
        assert hp["peak_count"] == 30
        assert hp["peak_height_min_m"] == 10.0
        assert hp["peak_height_max_m"] == 40.0
        assert hp["peak_radius_m"] == 20.0

    def test_gully_fill_all(self):
        """gully 缺全部5个必填字段 -> 填充默认值"""
        scene = _base_scene("gully")
        repairs = auto_repair_scene(scene)
        hp = scene["landscape"]["height_pattern"]
        assert hp["main_direction_deg"] == 0.0
        assert hp["main_length_m"] == 1000.0
        assert hp["gully_depth_m"] == 6.0
        assert hp["gully_width_m"] == 12.0
        assert hp["profile"] == "V"

    def test_flat_no_conditional_fill(self):
        """flat 无条件必填 -> 不填充"""
        scene = _base_scene("flat")
        repairs = auto_repair_scene(scene)
        assert not any("step_height_m" in r for r in repairs)
        assert not any("peak_count" in r for r in repairs)

    def test_conditional_fill_then_validate_passes(self):
        """条件必填修复后复验: "缺少必填"错误消失"""
        scene = _base_scene("terraced")
        errors_before, _ = validate_scene_quality(scene)
        assert any("缺少必填" in e for e in errors_before)
        auto_repair_scene(scene)
        errors_after, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors_after)


# ===========================================================================
# 4) 绿色层: 草麦必填字段修复
# ===========================================================================

class TestRepairVarietyRequired:
    """绿色层 3): start_cull_dist/end_cull_dist 缺失 -> 填充"""

    def test_grass_missing_both_filled(self):
        """grass_varieties 缺 start+end -> 填充草默认值 3000/30000"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                            }])
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["height_pattern"]["grass_varieties"][0]
        assert v["start_cull_dist"] == 3000
        assert v["end_cull_dist"] == 30000
        assert any("start_cull_dist" in r for r in repairs)
        assert any("end_cull_dist" in r for r in repairs)

    def test_wheat_missing_both_filled(self):
        """wheat_varieties 缺 start+end -> 填充麦默认值 3000/50000"""
        scene = _base_scene("features",
                            wheat_varieties=[{
                                "mesh_path": "/Game/W", "density": 10,
                            }])
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["height_pattern"]["wheat_varieties"][0]
        assert v["start_cull_dist"] == 3000
        assert v["end_cull_dist"] == 50000

    def test_grass_missing_only_start(self):
        """grass_varieties 只缺 start -> 仅填充 start"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "end_cull_dist": 30000,
                            }])
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["height_pattern"]["grass_varieties"][0]
        assert v["start_cull_dist"] == 3000
        assert v["end_cull_dist"] == 30000
        assert any("start_cull_dist" in r for r in repairs)
        assert not any("end_cull_dist" in r for r in repairs)

    def test_landscape_grass_path_filled(self):
        """landscape.grass.grass_varieties 路径也修复"""
        scene = _base_scene("flat")
        scene["landscape"]["grass"] = {
            "grass_varieties": [{"mesh_path": "/Game/G", "density": 10}],
        }
        repairs = auto_repair_scene(scene)
        v = scene["landscape"]["grass"]["grass_varieties"][0]
        assert v["start_cull_dist"] == 3000
        assert v["end_cull_dist"] == 30000
        assert any("landscape.grass" in r for r in repairs)

    def test_variety_fill_then_validate_passes(self):
        """草麦必填修复后复验: "缺少必填"错误消失"""
        scene = _base_scene("features",
                            grass_varieties=[{"mesh_path": "/Game/G", "density": 10}])
        errors_before, _ = validate_scene_quality(scene)
        assert any("缺少必填" in e for e in errors_before)
        auto_repair_scene(scene)
        errors_after, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors_after)


# ===========================================================================
# 5) 绿色层: 河流参数修复
# ===========================================================================

class TestRepairRiverParams:
    """绿色层 4): width_m/bed_depth_m 最小值 + waterfall.t clamp"""

    def test_width_too_small(self):
        """width_m=0.3 -> 1.0"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 0.3}])
        repairs = auto_repair_scene(scene)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["width_m"] == 1.0
        assert any("width_m" in r for r in repairs)

    def test_bed_depth_too_shallow(self):
        """bed_depth_m=0.2 -> 0.5"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "bed_depth_m": 0.2}])
        repairs = auto_repair_scene(scene)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["bed_depth_m"] == 0.5
        assert any("bed_depth_m" in r for r in repairs)

    def test_bed_depth_zero_not_repaired(self):
        """bed_depth_m=0 (不冲刷) -> 不修复 (0 是合法值表示不冲刷)"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "bed_depth_m": 0}])
        repairs = auto_repair_scene(scene)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["bed_depth_m"] == 0
        assert not any("bed_depth_m" in r for r in repairs)

    def test_waterfall_t_clamp_high(self):
        """waterfall.t=1.5 -> clamp 到 1.0"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0,
                                     "waterfalls": [{"t": 1.5, "drop_m": 5}]}])
        repairs = auto_repair_scene(scene)
        wf = scene["landscape"]["height_pattern"]["rivers"][0]["waterfalls"][0]
        assert wf["t"] == 1.0
        assert any("t" in r for r in repairs)

    def test_waterfall_t_clamp_low(self):
        """waterfall.t=-0.5 -> clamp 到 0.0"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0,
                                     "waterfalls": [{"t": -0.5, "drop_m": 5}]}])
        repairs = auto_repair_scene(scene)
        wf = scene["landscape"]["height_pattern"]["rivers"][0]["waterfalls"][0]
        assert wf["t"] == 0.0

    def test_waterfall_t_in_range_no_repair(self):
        """waterfall.t=0.5 在范围内 -> 不修复"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0,
                                     "waterfalls": [{"t": 0.5, "drop_m": 5}]}])
        repairs = auto_repair_scene(scene)
        assert not any(".t" in r for r in repairs)

    def test_river_params_repair_then_validate_clean(self):
        """河流参数修复后复验: width/bed_depth 警告消失"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 0.3, "bed_depth_m": 0.2,
                                     "waterfalls": [{"t": 1.5, "drop_m": 5}]}])
        _, warnings_before = validate_scene_quality(scene)
        errors_before, _ = validate_scene_quality(scene)
        assert any("width_m" in w for w in warnings_before)
        auto_repair_scene(scene)
        errors_after, warnings_after = validate_scene_quality(scene)
        assert not any("width_m" in w and "< 1m" in w for w in warnings_after)
        assert not any("t" in e and "超出范围" in e for e in errors_after)


# ===========================================================================
# 6) 黄色层: 几何越界坐标修复 (aggressive=True)
# ===========================================================================

class TestRepairGeometricBounds:
    """黄色层 5): 坐标 clamp 到地形范围 (需 aggressive=True)"""

    def test_hill_clamp(self):
        """hills X=9999 -> clamp 到 504"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 9999, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}])
        repairs = auto_repair_scene(scene, aggressive=True)
        h = scene["landscape"]["height_pattern"]["hills"][0]
        assert h["center_x_m"] == TERRAIN_X
        assert h["center_y_m"] == 200
        assert any("center_x_m" in r for r in repairs)

    def test_hill_clamp_negative(self):
        """hills X=-100 -> clamp 到 0"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": -100, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}])
        repairs = auto_repair_scene(scene, aggressive=True)
        h = scene["landscape"]["height_pattern"]["hills"][0]
        assert h["center_x_m"] == 0
        assert any("center_x_m" in r for r in repairs)

    def test_valley_clamp(self):
        """valleys Y=9999 -> clamp 到 504"""
        scene = _base_scene("features",
                            valleys=[{"center_x_m": 100, "center_y_m": 9999,
                                      "radius_m": 50, "depth_m": 10}])
        repairs = auto_repair_scene(scene, aggressive=True)
        v = scene["landscape"]["height_pattern"]["valleys"][0]
        assert v["center_y_m"] == TERRAIN_Y

    def test_river_points_clamp(self):
        """河流折点 [9999,200] -> clamp X 到 504"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [9999, 200]],
                                     "width_m": 3.0}])
        repairs = auto_repair_scene(scene, aggressive=True)
        pts = scene["landscape"]["height_pattern"]["rivers"][0]["points"]
        assert pts[1][0] == TERRAIN_X
        assert pts[1][1] == 200

    def test_road_points_clamp(self):
        """道路折点 [-50,200] -> clamp X 到 0"""
        scene = _base_scene("features",
                            roads=[{"points": [[-50, 10], [200, 200]]}])
        repairs = auto_repair_scene(scene, aggressive=True)
        pts = scene["landscape"]["height_pattern"]["roads"][0]["points"]
        assert pts[0][0] == 0

    def test_building_center_clamp(self):
        """建筑 center=[9999,100] -> clamp X 到 504"""
        scene = _base_scene("features",
                            buildings=[{"center": [9999, 100],
                                        "size_m": [10, 10], "height_m": 5}])
        repairs = auto_repair_scene(scene, aggressive=True)
        bd = scene["landscape"]["height_pattern"]["buildings"][0]
        assert bd["center"][0] == TERRAIN_X
        assert bd["center"][1] == 100

    def test_ridge_region_clamp(self):
        """山脊 region_max_x_m=9999 -> clamp 到 504"""
        scene = _base_scene("features",
                            ridges=[{"region_min_x_m": 0, "region_min_y_m": 0,
                                     "region_max_x_m": 9999, "region_max_y_m": 200,
                                     "amplitude_m": 30, "frequency": 0.01}])
        repairs = auto_repair_scene(scene, aggressive=True)
        r = scene["landscape"]["height_pattern"]["ridges"][0]
        assert r["region_max_x_m"] == TERRAIN_X

    def test_geometric_not_repaired_without_aggressive(self):
        """aggressive=False 时几何越界不修复"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 9999, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}])
        repairs = auto_repair_scene(scene, aggressive=False)
        h = scene["landscape"]["height_pattern"]["hills"][0]
        assert h["center_x_m"] == 9999
        assert not any("center_x_m" in r for r in repairs)

    def test_geometric_repair_then_validate_passes(self):
        """几何修复后复验: 越界错误消失"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 9999, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}])
        errors_before, _ = validate_scene_quality(scene)
        assert any("超出地形范围" in e for e in errors_before)
        auto_repair_scene(scene, aggressive=True)
        errors_after, _ = validate_scene_quality(scene)
        assert not any("超出地形范围" in e for e in errors_after)


# ===========================================================================
# 7) 黄色层: 水流速度修复 (aggressive=True)
# ===========================================================================

class TestRepairWaterFlowSpeed:
    """黄色层 6): river.flow_speed <= water.flow_speed -> 提升 river"""

    def test_river_slower_repaired(self):
        """river=1.0 <= water=2.0 -> river=3.0"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 1.0}])
        repairs = auto_repair_scene(scene, aggressive=True)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["flow_speed"] == 3.0
        assert any("flow_speed" in r for r in repairs)

    def test_river_equal_repaired(self):
        """river=2.0 == water=2.0 -> river=3.0 (<= 触发)"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 2.0}])
        repairs = auto_repair_scene(scene, aggressive=True)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["flow_speed"] == 3.0

    def test_river_faster_not_repaired(self):
        """river=5.0 > water=2.0 -> 不修复"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 5.0}])
        repairs = auto_repair_scene(scene, aggressive=True)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["flow_speed"] == 5.0
        assert not any("flow_speed" in r for r in repairs)

    def test_water_speed_not_repaired_without_aggressive(self):
        """aggressive=False 时水流速度不修复"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 1.0}])
        repairs = auto_repair_scene(scene, aggressive=False)
        rv = scene["landscape"]["height_pattern"]["rivers"][0]
        assert rv["flow_speed"] == 1.0
        assert not any("flow_speed" in r for r in repairs)

    def test_water_speed_repair_then_validate_clean(self):
        """水流速度修复后复验: 警告消失"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 1.0}])
        _, warnings_before = validate_scene_quality(scene)
        assert any("河流流速应快于湖泊" in w for w in warnings_before)
        auto_repair_scene(scene, aggressive=True)
        _, warnings_after = validate_scene_quality(scene)
        assert not any("河流流速应快于湖泊" in w for w in warnings_after)


# ===========================================================================
# 8) 集成测试: 修复→复验通过
# ===========================================================================

class TestIntegrationRepairValidate:
    """集成测试: 修复后 validate_scene_quality 应无错误"""

    def test_full_repair_cycle_green(self):
        """绿色层全修复: 含多种缺陷的场景修复后复验通过"""
        scene = _base_scene("terraced", bank_ratio=1.5)
        scene["landscape"]["height_pattern"]["grass_varieties"] = [
            {"mesh_path": "/Game/G", "density": 10, "end_cull_dist": 200000}
        ]
        errors_before, _ = validate_scene_quality(scene)
        assert len(errors_before) >= 3
        auto_repair_scene(scene)
        errors_after, _ = validate_scene_quality(scene)
        assert errors_after == []

    def test_full_repair_cycle_aggressive(self):
        """aggressive 全修复: 含几何越界+水流速度的场景修复后复验通过"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 9999, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}],
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 0.3, "flow_speed": 1.0}])
        errors_before, warnings_before = validate_scene_quality(scene)
        assert any("超出地形范围" in e for e in errors_before)
        auto_repair_scene(scene, aggressive=True)
        errors_after, warnings_after = validate_scene_quality(scene)
        assert not any("超出地形范围" in e for e in errors_after)
        assert not any("河流流速应快于湖泊" in w for w in warnings_after)
        assert not any("width_m" in w and "< 1m" in w for w in warnings_after)

    def test_valid_scene_no_repairs(self):
        """完全合法的场景 -> 0 修复"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 100, "center_y_m": 100,
                                    "radius_m": 50, "height_m": 80}],
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 15,
                                "start_cull_dist": 3000, "end_cull_dist": 30000,
                            }],
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "bed_depth_m": 1.0,
                                     "profile": "V"}])
        repairs = auto_repair_scene(scene, aggressive=True)
        assert repairs == []

    def test_repair_idempotent(self):
        """修复幂等性: 修复后再修复不产生新日志"""
        scene = _base_scene("terraced", bank_ratio=1.5)
        repairs1 = auto_repair_scene(scene)
        repairs2 = auto_repair_scene(scene)
        assert len(repairs1) > 0
        assert repairs2 == []


# ===========================================================================
# 9) 边界场景测试
# ===========================================================================

class TestEdgeCases:
    """边界场景: 空场景/无 height_pattern/非 dict 类型守卫"""

    def test_empty_scene(self):
        """空场景 -> 0 修复"""
        repairs = auto_repair_scene({})
        assert repairs == []

    def test_no_landscape(self):
        """无 landscape -> 0 修复"""
        repairs = auto_repair_scene({"scene": {}})
        assert repairs == []

    def test_landscape_not_dict(self):
        """landscape 不是 dict -> 0 修复不崩溃"""
        repairs = auto_repair_scene({"landscape": "not_dict"})
        assert repairs == []

    def test_no_height_pattern(self):
        """无 height_pattern -> 0 修复"""
        scene = {"landscape": {"material": "/Game/M"}}
        repairs = auto_repair_scene(scene)
        assert repairs == []

    def test_height_pattern_none(self):
        """height_pattern=null -> 0 修复不崩溃"""
        scene = {"landscape": {"material": "/Game/M", "height_pattern": None}}
        repairs = auto_repair_scene(scene)
        assert repairs == []

    def test_grass_none(self):
        """landscape.grass=null -> 0 修复不崩溃"""
        scene = _base_scene("flat")
        scene["landscape"]["grass"] = None
        repairs = auto_repair_scene(scene)
        assert repairs == []

    def test_grass_varieties_not_list(self):
        """grass_varieties 不是 list -> 不崩溃"""
        scene = _base_scene("features", grass_varieties="not_a_list")
        repairs = auto_repair_scene(scene)
        assert repairs == []

    def test_rivers_empty(self):
        """rivers=[] -> 0 修复"""
        scene = _base_scene("features", rivers=[])
        repairs = auto_repair_scene(scene)
        assert repairs == []

    def test_river_not_dict(self):
        """river 项不是 dict -> 不崩溃"""
        scene = _base_scene("features", rivers=["not_a_dict"])
        repairs = auto_repair_scene(scene)
        assert repairs == []

    def test_multiple_varieties_all_repaired(self):
        """多个草变体都缺字段 -> 全部修复"""
        scene = _base_scene("features",
                            grass_varieties=[
                                {"mesh_path": "/Game/G1", "density": 10},
                                {"mesh_path": "/Game/G2", "density": 20},
                            ])
        repairs = auto_repair_scene(scene)
        vs = scene["landscape"]["height_pattern"]["grass_varieties"]
        assert vs[0]["start_cull_dist"] == 3000
        assert vs[0]["end_cull_dist"] == 30000
        assert vs[1]["start_cull_dist"] == 3000
        assert vs[1]["end_cull_dist"] == 30000
