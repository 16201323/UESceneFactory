# -*- coding: utf-8 -*-
"""validate_scene_quality 语义质量校验单元测试。

覆盖第一梯队(数值范围/条件必填/草麦必填/条件互斥)和
第二梯队(几何边界/河道路径/建筑重叠)全部检查项,
以及水系 flow_speed 一致性补充检查。

测试用最小场景 dict 直接验证, 不依赖磁盘文件。
"""
import pytest

from scripts.validate_scene_quality import validate_scene_quality


# ===========================================================================
# 测试基座: 最小合法场景构造器
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
# 1) 数值范围检查
# ===========================================================================

class TestRangeChecks:
    """第一梯队 1): 数值范围"""

    def test_bank_ratio_in_range(self):
        """bank_ratio 在 [0,1] 内 -> 无错误"""
        scene = _base_scene("terraced", bank_ratio=0.25)
        errors, _ = validate_scene_quality(scene)
        assert not any("bank_ratio" in e for e in errors)

    def test_bank_ratio_out_of_range(self):
        """bank_ratio > 1 -> 报错"""
        scene = _base_scene("terraced", bank_ratio=1.5)
        errors, _ = validate_scene_quality(scene)
        assert any("bank_ratio" in e and "超出范围" in e for e in errors)

    def test_bank_ratio_negative(self):
        """bank_ratio < 0 -> 报错"""
        scene = _base_scene("terraced", bank_ratio=-0.1)
        errors, _ = validate_scene_quality(scene)
        assert any("bank_ratio" in e for e in errors)

    def test_perturbation_strength_in_range(self):
        """perturbation_strength 在 [0,1] 内 -> 无错误"""
        scene = _base_scene("flat", perturbation_strength=0.5)
        errors, _ = validate_scene_quality(scene)
        assert not any("perturbation_strength" in e for e in errors)

    def test_perturbation_strength_out_of_range(self):
        """perturbation_strength > 1 -> 报错"""
        scene = _base_scene("flat", perturbation_strength=2.0)
        errors, _ = validate_scene_quality(scene)
        assert any("perturbation_strength" in e for e in errors)

    def test_peak_min_le_max_ok(self):
        """karst: peak_height_min_m <= peak_height_max_m -> 无错误"""
        scene = _base_scene("karst", peak_count=10,
                            peak_height_min_m=10, peak_height_max_m=40,
                            peak_radius_m=20)
        errors, _ = validate_scene_quality(scene)
        assert not any("peak_height" in e for e in errors)

    def test_peak_min_gt_max_error(self):
        """karst: peak_height_min_m > peak_height_max_m -> 报错"""
        scene = _base_scene("karst", peak_count=10,
                            peak_height_min_m=50, peak_height_max_m=20,
                            peak_radius_m=20)
        errors, _ = validate_scene_quality(scene)
        assert any("peak_height_min_m" in e and "peak_height_max_m" in e
                   for e in errors)

    def test_variety_cull_dist_in_range(self):
        """start_cull_dist/end_cull_dist 在 [1,100000] 内 -> 无错误"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 3000, "end_cull_dist": 30000,
                            }])
        errors, _ = validate_scene_quality(scene)
        assert not any("cull_dist" in e for e in errors)

    def test_variety_cull_dist_out_of_range(self):
        """end_cull_dist > 100000 -> 报错"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 3000, "end_cull_dist": 200000,
                            }])
        errors, _ = validate_scene_quality(scene)
        assert any("end_cull_dist" in e and "超出范围" in e for e in errors)

    def test_variety_end_le_start_error(self):
        """end_cull_dist <= start_cull_dist -> 报错"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 5000, "end_cull_dist": 3000,
                            }])
        errors, _ = validate_scene_quality(scene)
        assert any("end_cull_dist" in e and "start_cull_dist" in e
                   for e in errors)


# ===========================================================================
# 2) 条件必填检查
# ===========================================================================

class TestConditionalRequired:
    """第一梯队 2): height_pattern.type 决定必填字段"""

    def test_terraced_missing_step_height(self):
        """terraced 缺 step_height_m -> 报错"""
        scene = _base_scene("terraced", step_width_m=12.0,
                            bank_ratio=0.25, base_height_m=0.0)
        errors, _ = validate_scene_quality(scene)
        assert any("step_height_m" in e for e in errors)

    def test_terraced_all_present(self):
        """terraced 全部必填字段都在 -> 无错误"""
        scene = _base_scene("terraced", step_height_m=3.0, step_width_m=12.0,
                            bank_ratio=0.25, base_height_m=0.0)
        errors, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors)

    def test_karst_missing_peak_count(self):
        """karst 缺 peak_count -> 报错"""
        scene = _base_scene("karst", peak_height_min_m=10,
                            peak_height_max_m=40, peak_radius_m=20)
        errors, _ = validate_scene_quality(scene)
        assert any("peak_count" in e for e in errors)

    def test_karst_all_present(self):
        """karst 全部必填字段都在 -> 无错误"""
        scene = _base_scene("karst", peak_count=30, peak_height_min_m=10,
                            peak_height_max_m=40, peak_radius_m=20)
        errors, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors)

    def test_gully_missing_profile(self):
        """gully 缺 profile -> 报错"""
        scene = _base_scene("gully", main_direction_deg=0,
                            main_length_m=1000, gully_depth_m=6,
                            gully_width_m=12)
        errors, _ = validate_scene_quality(scene)
        assert any("profile" in e for e in errors)

    def test_gully_all_present(self):
        """gully 全部必填字段都在 -> 无错误"""
        scene = _base_scene("gully", main_direction_deg=0,
                            main_length_m=1000, gully_depth_m=6,
                            gully_width_m=12, profile="V")
        errors, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors)

    def test_flat_no_conditional_required(self):
        """flat 无条件必填字段 -> 无错误"""
        scene = _base_scene("flat")
        errors, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors)


# ===========================================================================
# 3) 草麦必填字段检查
# ===========================================================================

class TestVarietyRequired:
    """第一梯队 3): grass_varieties/wheat_varieties 必填 start_cull_dist/end_cull_dist"""

    def test_grass_missing_start_cull(self):
        """grass_varieties 缺 start_cull_dist -> 报错"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "end_cull_dist": 30000,
                            }])
        errors, _ = validate_scene_quality(scene)
        assert any("start_cull_dist" in e and "缺少必填" in e for e in errors)

    def test_grass_missing_end_cull(self):
        """grass_varieties 缺 end_cull_dist -> 报错"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 3000,
                            }])
        errors, _ = validate_scene_quality(scene)
        assert any("end_cull_dist" in e and "缺少必填" in e for e in errors)

    def test_wheat_missing_both_cull(self):
        """wheat_varieties 缺 start_cull_dist 和 end_cull_dist -> 2个错误"""
        scene = _base_scene("features",
                            wheat_varieties=[{
                                "mesh_path": "/Game/W", "density": 10,
                            }])
        errors, _ = validate_scene_quality(scene)
        cull_errors = [e for e in errors if "缺少必填" in e and "cull_dist" in e]
        assert len(cull_errors) >= 2

    def test_grass_all_present(self):
        """grass_varieties 含 start_cull_dist + end_cull_dist -> 无错误"""
        scene = _base_scene("features",
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 10,
                                "start_cull_dist": 3000, "end_cull_dist": 30000,
                            }])
        errors, _ = validate_scene_quality(scene)
        assert not any("缺少必填" in e for e in errors)

    def test_grass_under_landscape_grass(self):
        """landscape.grass.grass_varieties 路径也检查必填"""
        scene = _base_scene("flat")
        scene["landscape"]["grass"] = {
            "grass_varieties": [{
                "mesh_path": "/Game/G", "density": 10,
            }],
        }
        errors, _ = validate_scene_quality(scene)
        assert any("start_cull_dist" in e and "缺少必填" in e for e in errors)


# ===========================================================================
# 4) 条件互斥检查
# ===========================================================================

class TestTypeExclusive:
    """第一梯队 4): type 与专属字段不匹配 -> 警告"""

    def test_flat_with_terraced_field_warns(self):
        """type=flat 但含 step_height_m -> 警告"""
        scene = _base_scene("flat", step_height_m=3.0)
        _, warnings = validate_scene_quality(scene)
        assert any("step_height_m" in w and "terraced" in w for w in warnings)

    def test_terraced_with_karst_field_warns(self):
        """type=terraced 但含 peak_count -> 警告"""
        scene = _base_scene("terraced", step_height_m=3.0, step_width_m=12.0,
                            bank_ratio=0.25, base_height_m=0.0,
                            peak_count=30)
        _, warnings = validate_scene_quality(scene)
        assert any("peak_count" in w and "karst" in w for w in warnings)

    def test_karst_no_cross_fields(self):
        """type=karst 不含其他模式字段 -> 无互斥警告"""
        scene = _base_scene("karst", peak_count=30, peak_height_min_m=10,
                            peak_height_max_m=40, peak_radius_m=20)
        _, warnings = validate_scene_quality(scene)
        assert not any("专属字段" in w for w in warnings)


# ===========================================================================
# 5) 几何边界检查
# ===========================================================================

class TestGeometricBounds:
    """第二梯队 5): 坐标不超出地形物理范围"""

    def test_hill_in_bounds(self):
        """hills 坐标在地形范围内 -> 无错误"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 100, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}])
        errors, _ = validate_scene_quality(scene)
        assert not any("超出地形范围" in e for e in errors)

    def test_hill_out_of_bounds(self):
        """hills X坐标超出地形范围 -> 报错"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 9999, "center_y_m": 200,
                                    "radius_m": 50, "height_m": 30}])
        errors, _ = validate_scene_quality(scene)
        assert any("X坐标" in e and "超出地形范围" in e for e in errors)

    def test_river_points_in_bounds(self):
        """河流折点在地形范围内 -> 无错误"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0}])
        errors, _ = validate_scene_quality(scene)
        assert not any("超出地形范围" in e for e in errors)

    def test_river_points_out_of_bounds(self):
        """河流折点超出地形范围 -> 报错"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [9999, 200]],
                                     "width_m": 3.0}])
        errors, _ = validate_scene_quality(scene)
        assert any("X坐标" in e and "超出地形范围" in e for e in errors)

    def test_building_out_of_bounds(self):
        """建筑中心超出地形范围 -> 报错"""
        scene = _base_scene("features",
                            buildings=[{"center": [9999, 100],
                                        "size_m": [10, 10], "height_m": 5}])
        errors, _ = validate_scene_quality(scene)
        assert any("X坐标" in e and "超出地形范围" in e for e in errors)

    def test_ridge_in_bounds(self):
        """山脊区域在地形范围内 -> 无错误"""
        scene = _base_scene("features",
                            ridges=[{"region_min_x_m": 0, "region_min_y_m": 0,
                                     "region_max_x_m": 200, "region_max_y_m": 200,
                                     "amplitude_m": 30, "frequency": 0.01}])
        errors, _ = validate_scene_quality(scene)
        assert not any("超出地形范围" in e for e in errors)

    def test_ridge_out_of_bounds(self):
        """山脊区域超出地形范围 -> 报错"""
        scene = _base_scene("features",
                            ridges=[{"region_min_x_m": 0, "region_min_y_m": 0,
                                     "region_max_x_m": 9999, "region_max_y_m": 200,
                                     "amplitude_m": 30, "frequency": 0.01}])
        errors, _ = validate_scene_quality(scene)
        assert any("X坐标" in e and "超出地形范围" in e for e in errors)


# ===========================================================================
# 6) 河道路径有效性
# ===========================================================================

class TestRiverRoadPaths:
    """第二梯队 6): 河流/道路路径有效性"""

    def test_river_too_few_points(self):
        """河流 points < 2 -> 报错"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10]], "width_m": 3.0}])
        errors, _ = validate_scene_quality(scene)
        assert any("至少需要2个点" in e for e in errors)

    def test_river_two_points_ok(self):
        """河流 points=2 -> 无错误"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "bed_depth_m": 1.0}])
        errors, _ = validate_scene_quality(scene)
        assert not any("至少需要2个点" in e for e in errors)

    def test_river_width_too_small(self):
        """河流 width_m < 1m -> 警告"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 0.3}])
        _, warnings = validate_scene_quality(scene)
        assert any("width_m" in w and "< 1m" in w for w in warnings)

    def test_river_bed_depth_too_shallow(self):
        """河流 bed_depth_m < 0.5m -> 警告"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "bed_depth_m": 0.2}])
        _, warnings = validate_scene_quality(scene)
        assert any("bed_depth_m" in w and "< 0.5m" in w for w in warnings)

    def test_road_too_few_points(self):
        """道路 points < 2 -> 报错"""
        scene = _base_scene("features",
                            roads=[{"points": [[10, 10]]}])
        errors, _ = validate_scene_quality(scene)
        assert any("至少需要2个点" in e for e in errors)

    def test_waterfall_t_out_of_range(self):
        """瀑布 t 值超出 [0,1] -> 报错"""
        scene = _base_scene("features",
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0,
                                     "waterfalls": [{"t": 1.5, "drop_m": 5}]}])
        errors, _ = validate_scene_quality(scene)
        assert any("t" in e and "超出范围" in e for e in errors)


# ===========================================================================
# 7) 建筑重叠检查
# ===========================================================================

class TestBuildingOverlap:
    """第二梯队 7): 建筑两两 AABB 不重叠"""

    def test_buildings_far_apart(self):
        """两栋建筑距离足够远 -> 无重叠警告"""
        scene = _base_scene("features",
                            buildings=[{"center": [100, 100], "size_m": [10, 10],
                                        "height_m": 5},
                                       {"center": [300, 300], "size_m": [10, 10],
                                        "height_m": 5}])
        _, warnings = validate_scene_quality(scene)
        assert not any("重叠" in w for w in warnings)

    def test_buildings_overlapping(self):
        """两栋建筑中心距离 < 半宽之和 -> 重叠警告"""
        scene = _base_scene("features",
                            buildings=[{"center": [100, 100], "size_m": [20, 20],
                                        "height_m": 5},
                                       {"center": [105, 105], "size_m": [20, 20],
                                        "height_m": 5}])
        _, warnings = validate_scene_quality(scene)
        assert any("重叠" in w for w in warnings)

    def test_single_building_no_overlap(self):
        """只有一栋建筑 -> 无重叠检查"""
        scene = _base_scene("features",
                            buildings=[{"center": [100, 100], "size_m": [10, 10],
                                        "height_m": 5}])
        _, warnings = validate_scene_quality(scene)
        assert not any("重叠" in w for w in warnings)


# ===========================================================================
# 补充: 水系 flow_speed 一致性
# ===========================================================================

class TestWaterFlowSpeed:
    """补充检查: 河流 flow_speed > 湖面 flow_speed"""

    def test_river_slower_than_water_warns(self):
        """河流流速 <= 湖面流速 -> 警告"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 2.0},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 1.0}])
        _, warnings = validate_scene_quality(scene)
        assert any("flow_speed" in w and "河流流速应快于湖泊" in w
                   for w in warnings)

    def test_river_faster_than_water_ok(self):
        """河流流速 > 湖面流速 -> 无警告"""
        scene = _base_scene("features",
                            water={"level_m": 10, "flow_speed": 0.3},
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "flow_speed": 1.0}])
        _, warnings = validate_scene_quality(scene)
        assert not any("flow_speed" in w for w in warnings)


# ===========================================================================
# 边界场景测试
# ===========================================================================

class TestEdgeCases:
    """边界场景: 空场景/无 height_pattern/无 landscape"""

    def test_empty_scene(self):
        """空场景 -> 报 landscape 缺失错误 (根因修复: landscape 必填)"""
        errors, warnings = validate_scene_quality({})
        assert any("landscape" in e for e in errors), "空场景应报 landscape 缺失错误"
        assert warnings == []

    def test_no_landscape(self):
        """无 landscape -> 报 landscape 缺失错误 (根因修复: landscape 必填)"""
        errors, _ = validate_scene_quality({"scene": {}})
        assert any("landscape" in e for e in errors), "无 landscape 应报缺失错误"

    def test_landscape_null(self):
        """landscape=null -> 报 landscape 缺失错误 (根因修复: 防止下游 NoneType 崩溃)"""
        errors, _ = validate_scene_quality({"scene": {}, "landscape": None})
        assert any("landscape" in e for e in errors), "landscape=null 应报缺失错误"

    def test_no_height_pattern(self):
        """landscape 无 height_pattern -> 无错误 (有警告)"""
        scene = {
            "landscape": {
                "material": "/Game/M",
                "layers": [
                    {"info": "/Game/L_Grass", "weight": 0.7},
                    {"info": "/Game/L_Dirt", "weight": 0.3},
                ],
            },
            "placements": [
                {"type": "instances", "asset": "/Game/A",
                 "instances": [{"location": [0, 0, 0]}]},
            ],
        }
        errors, warnings = validate_scene_quality(scene)
        assert errors == []
        # height_pattern 缺失应产生警告 (L5 兜底应已注入)
        assert any("height_pattern" in w for w in warnings)

    def test_height_pattern_none(self):
        """height_pattern=null -> 无错误不崩溃 (有警告)"""
        scene = {
            "landscape": {
                "material": "/Game/M",
                "height_pattern": None,
                "layers": [
                    {"info": "/Game/L_Grass", "weight": 0.7},
                    {"info": "/Game/L_Dirt", "weight": 0.3},
                ],
            },
            "placements": [
                {"type": "instances", "asset": "/Game/A",
                 "instances": [{"location": [0, 0, 0]}]},
            ],
        }
        errors, warnings = validate_scene_quality(scene)
        assert errors == []
        assert any("height_pattern" in w for w in warnings)

    def test_grass_none(self):
        """landscape.grass=null -> 无错误不崩溃"""
        scene = _base_scene("flat")
        scene["landscape"]["grass"] = None
        errors, _ = validate_scene_quality(scene)
        assert errors == []

    def test_grass_varieties_not_list(self):
        """grass_varieties 不是 list -> 不崩溃"""
        scene = _base_scene("features", grass_varieties="not_a_list")
        errors, _ = validate_scene_quality(scene)
        assert errors == []

    def test_valid_full_scene(self):
        """完整合法场景 -> 无错误"""
        scene = _base_scene("features",
                            hills=[{"center_x_m": 100, "center_y_m": 100,
                                    "radius_m": 50, "height_m": 80}],
                            grass_varieties=[{
                                "mesh_path": "/Game/G", "density": 15,
                                "scale_min": 0.8, "scale_max": 1.2,
                                "start_cull_dist": 3000, "end_cull_dist": 30000,
                            }],
                            rivers=[{"points": [[10, 10], [200, 200]],
                                     "width_m": 3.0, "bed_depth_m": 1.0,
                                     "profile": "V"}],
                            buildings=[{"center": [100, 300], "size_m": [10, 10],
                                        "height_m": 5}])
        errors, _ = validate_scene_quality(scene)
        assert errors == []
