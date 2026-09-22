# -*- coding: utf-8 -*-
"""
validate_scene_quality.py - 场景 JSON 语义质量校验

在 validate_scene_json.py (字段名/类型/必填/枚举结构校验) 通过后,
进一步检查数值范围、条件必填、几何边界等语义质量问题,
避免 build_scene.py / C++ 插件静默使用默认值导致运行时视觉缺陷。

与 validate_scene_json.py 互补:
  - validate_scene_json.py: 校验字段名/类型/必填/枚举 (结构正确性)
  - validate_scene_quality.py: 校验数值范围/条件必填/几何边界 (语义质量)

检查项分两个梯队:
  第一梯队 (字典驱动, 纯数值/存在性检查):
    1) 数值范围: bank_ratio[0,1], perturbation_strength[0,1],
       start_cull_dist/end_cull_dist[1,100000], peak_min<=peak_max,
       end_cull_dist>start_cull_dist
    2) 条件必填: height_pattern.type 决定哪些字段必填
       (terraced->step_height_m 等, karst->peak_count 等, gully->gully_depth_m 等)
    3) 草麦必填: grass_varieties/wheat_varieties 每项必须有 start_cull_dist/end_cull_dist
    4) 条件互斥: type!=terraced 时不应出现 step_height_m 等专属字段
  第二梯队 (需计算地形尺寸):
    5) 几何边界: hills/valleys/rivers/roads/buildings 坐标不超出地形物理范围
    6) 河道路径: rivers/roads points 至少2个点, width_m>=1m, bed_depth_m>=0.5m
    7) 建筑重叠: height_pattern.buildings[] 两两 AABB 不重叠

用法:
    python validate_scene_quality.py <场景.json>

退出码: 0=无错误(可有警告)  1=有错误
"""

import json
import math
import os
import sys

# ===========================================================================
# 第一梯队 1): 数值范围检查注册表
# 格式: { "field_name": (min_val, max_val) }
# 数据来源: height_pattern.md 字段表
# ===========================================================================

# height_pattern 顶层字段范围
HP_RANGE_FIELDS = {
    "bank_ratio": (0.0, 1.0),            # terraced 田埂占比 [0,1]
    "perturbation_strength": (0.0, 1.0), # 扰动强度 [0,1]
}

# grass_varieties / wheat_varieties 字段范围
VARIETY_RANGE_FIELDS = {
    "start_cull_dist": (1, 100000),      # 起始剔除距离 Clamp [1,100000]
    "end_cull_dist": (1, 100000),        # 结束剔除距离 Clamp [1,100000]
}

# ===========================================================================
# 第一梯队 2): 条件必填字段注册表
# height_pattern.type -> 该模式下必填的字段列表
# 数据来源: height_pattern.md 各模式专属字段表
# ===========================================================================

HP_CONDITIONAL_REQUIRED = {
    "terraced": ["step_height_m", "step_width_m", "bank_ratio", "base_height_m"],
    "karst": ["peak_count", "peak_height_min_m", "peak_height_max_m", "peak_radius_m"],
    "gully": ["main_direction_deg", "main_length_m", "gully_depth_m",
              "gully_width_m", "profile"],
}

# ===========================================================================
# 第一梯队 4): 条件互斥字段注册表
# 每种 type 的专属字段, 其他 type 下出现则警告 (可能复制模板后忘改 type)
# ===========================================================================

HP_TYPE_EXCLUSIVE = {
    "terraced": ["step_height_m", "step_width_m", "bank_ratio", "base_height_m"],
    "karst": ["peak_count", "min_distance_m", "peak_height_min_m", "peak_height_max_m",
              "peak_radius_m", "doline_count", "doline_depth_m", "doline_radius_m"],
    "gully": ["main_direction_deg", "main_length_m", "meander_amplitude_m",
              "meander_frequency", "branch_count", "branch_angle_deg",
              "branch_length_ratio", "branch_depth", "gully_depth_m",
              "gully_width_m", "profile"],
}

# ===========================================================================
# 第一梯队 3): 草麦必填字段
# 不写则 C++ 用默认 1000/3000 (10m/30m), 高空俯瞰植被全部被剔除露出黑色地形
# ===========================================================================

VARIETY_REQUIRED = ["start_cull_dist", "end_cull_dist"]


# ===========================================================================
# 工具函数: 计算地形物理尺寸 (米)
# 公式来自 build_scene.py L122-123:
#   phys_x = (ccx * ssq * nsub) * scl[0] / 100.0
#   phys_y = (ccy * ssq * nsub) * scl[1] / 100.0
# 缺少字段时使用 build_scene.py 默认值
# ===========================================================================

def calc_terrain_size(ls):
    """计算地形物理尺寸 (米), 返回 (phys_x, phys_y)。

    ls: landscape 配置 dict
    """
    ssq = ls.get("section_size_quads", 63)
    nsub = ls.get("num_subsections", 1)
    ccx = ls.get("component_count_x", 8)
    ccy = ls.get("component_count_y", 8)
    scl = ls.get("scale", [100, 100, 100])
    phys_x = (ccx * ssq * nsub) * scl[0] / 100.0
    phys_y = (ccy * ssq * nsub) * scl[1] / 100.0
    return phys_x, phys_y


# ===========================================================================
# 第一梯队 1): 数值范围检查
# ===========================================================================

def _check_range(val, lo, hi, path, field, errors):
    """检查 val 是否在 [lo, hi] 范围内, 超出则报 error"""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if not (lo <= val <= hi):
            errors.append("%s.%s: 值 %s 超出范围 [%s, %s]" % (path, field, val, lo, hi))


def validate_ranges(hp, path, errors):
    """校验 height_pattern 顶层字段数值范围"""
    for field, (lo, hi) in HP_RANGE_FIELDS.items():
        if field in hp:
            _check_range(hp[field], lo, hi, path, field, errors)
    # karst 模式: peak_height_min_m <= peak_height_max_m
    pmin = hp.get("peak_height_min_m")
    pmax = hp.get("peak_height_max_m")
    if (isinstance(pmin, (int, float)) and isinstance(pmax, (int, float))
            and not isinstance(pmin, bool) and not isinstance(pmax, bool)
            and pmin > pmax):
        errors.append("%s: peak_height_min_m(%s) > peak_height_max_m(%s)"
                       % (path, pmin, pmax))


def validate_variety_ranges(varieties, path_prefix, errors):
    """校验 grass_varieties/wheat_varieties 每项的数值范围"""
    for i, v in enumerate(varieties):
        p = "%s[%d]" % (path_prefix, i)
        for field, (lo, hi) in VARIETY_RANGE_FIELDS.items():
            if field in v:
                _check_range(v[field], lo, hi, p, field, errors)
        # end_cull_dist 应大于 start_cull_dist
        scd = v.get("start_cull_dist")
        ecd = v.get("end_cull_dist")
        if (isinstance(scd, (int, float)) and isinstance(ecd, (int, float))
                and not isinstance(scd, bool) and not isinstance(ecd, bool)
                and ecd <= scd):
            errors.append("%s: end_cull_dist(%s) 应大于 start_cull_dist(%s)"
                           % (p, ecd, scd))


# ===========================================================================
# 第一梯队 2): 条件必填检查
# ===========================================================================

def validate_conditional_required(hp, path, errors):
    """根据 height_pattern.type 检查该模式下的必填字段"""
    hp_type = hp.get("type", "")
    required = HP_CONDITIONAL_REQUIRED.get(hp_type)
    if not required:
        return
    for field in required:
        if field not in hp:
            errors.append("%s: type=%s 缺少必填字段 '%s'" % (path, hp_type, field))


# ===========================================================================
# 第一梯队 3): 草麦必填字段检查
# ===========================================================================

def validate_variety_required(varieties, path_prefix, errors):
    """检查 grass_varieties/wheat_varieties 每项是否含必填字段"""
    for i, v in enumerate(varieties):
        p = "%s[%d]" % (path_prefix, i)
        for field in VARIETY_REQUIRED:
            if field not in v:
                errors.append(
                    "%s: 缺少必填字段 '%s' (不写则C++用默认1000/3000, 高空植被被剔除)"
                    % (p, field)
                )


# ===========================================================================
# 第一梯队 4): 条件互斥检查
# ===========================================================================

def validate_type_exclusive(hp, path, warnings):
    """检查 height_pattern 中是否出现了与当前 type 不匹配的专属字段"""
    hp_type = hp.get("type", "")
    for other_type, fields in HP_TYPE_EXCLUSIVE.items():
        if other_type == hp_type:
            continue
        for field in fields:
            if field in hp:
                warnings.append(
                    "%s: type=%s 但存在 %s 专属字段 '%s' (可能复制模板后忘改 type)"
                    % (path, hp_type, other_type, field)
                )


# ===========================================================================
# 第二梯队 5): 几何边界检查
# ===========================================================================

def _check_point_in_bounds(x, y, phys_x, phys_y, path, errors, tolerance=0.05):
    """检查坐标 (x, y) 是否在地形物理范围 [0, phys_x] x [0, phys_y] 内。

    tolerance: 容差比例(5%), 允许略微超出边界 (山丘可放在边缘)
    """
    margin_x = phys_x * tolerance
    margin_y = phys_y * tolerance
    if x < -margin_x or x > phys_x + margin_x:
        errors.append("%s: X坐标 %s 超出地形范围 [0, %.1f]m" % (path, x, phys_x))
    if y < -margin_y or y > phys_y + margin_y:
        errors.append("%s: Y坐标 %s 超出地形范围 [0, %.1f]m" % (path, y, phys_y))


def validate_geometric_bounds(hp, phys_x, phys_y, path, errors, warnings):
    """校验 height_pattern 子元素的坐标是否在地形物理范围内"""
    # hills[]
    for i, h in enumerate(hp.get("hills", [])):
        p = "%s.hills[%d]" % (path, i)
        cx = h.get("center_x_m")
        cy = h.get("center_y_m")
        if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
            _check_point_in_bounds(cx, cy, phys_x, phys_y, p, errors)

    # valleys[]
    for i, v in enumerate(hp.get("valleys", [])):
        p = "%s.valleys[%d]" % (path, i)
        cx = v.get("center_x_m")
        cy = v.get("center_y_m")
        if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
            _check_point_in_bounds(cx, cy, phys_x, phys_y, p, errors)

    # ridges[]: 检查区域边界
    for i, r in enumerate(hp.get("ridges", [])):
        p = "%s.ridges[%d]" % (path, i)
        rmin_x = r.get("region_min_x_m")
        rmin_y = r.get("region_min_y_m")
        rmax_x = r.get("region_max_x_m")
        rmax_y = r.get("region_max_y_m")
        if isinstance(rmin_x, (int, float)):
            _check_point_in_bounds(rmin_x, 0, phys_x, phys_y, p + ".region_min_x_m", errors)
        if isinstance(rmax_x, (int, float)):
            _check_point_in_bounds(rmax_x, 0, phys_x, phys_y, p + ".region_max_x_m", errors)
        if isinstance(rmin_y, (int, float)):
            _check_point_in_bounds(0, rmin_y, phys_x, phys_y, p + ".region_min_y_m", errors)
        if isinstance(rmax_y, (int, float)):
            _check_point_in_bounds(0, rmax_y, phys_x, phys_y, p + ".region_max_y_m", errors)

    # rivers[].points
    for i, rv in enumerate(hp.get("rivers", [])):
        p = "%s.rivers[%d]" % (path, i)
        for j, pt in enumerate(rv.get("points", [])):
            pp = "%s.points[%d]" % (p, j)
            if isinstance(pt, list) and len(pt) >= 2:
                _check_point_in_bounds(pt[0], pt[1], phys_x, phys_y, pp, errors)

    # roads[].points
    for i, rd in enumerate(hp.get("roads", [])):
        p = "%s.roads[%d]" % (path, i)
        for j, pt in enumerate(rd.get("points", [])):
            pp = "%s.points[%d]" % (p, j)
            if isinstance(pt, list) and len(pt) >= 2:
                _check_point_in_bounds(pt[0], pt[1], phys_x, phys_y, pp, errors)

    # buildings[].center
    for i, bd in enumerate(hp.get("buildings", [])):
        p = "%s.buildings[%d]" % (path, i)
        center = bd.get("center")
        if isinstance(center, list) and len(center) >= 2:
            _check_point_in_bounds(center[0], center[1], phys_x, phys_y, p, errors)


# ===========================================================================
# 第二梯队 6): 河道路径有效性检查
# ===========================================================================

def validate_river_road_paths(hp, path, errors, warnings):
    """校验河流和道路路径的有效性"""
    # rivers[]
    for i, rv in enumerate(hp.get("rivers", [])):
        p = "%s.rivers[%d]" % (path, i)
        points = rv.get("points", [])
        if len(points) < 2:
            errors.append("%s: points 至少需要2个点, 实际 %d 个" % (p, len(points)))
        # width_m 建议 >= 1m
        w = rv.get("width_m")
        if isinstance(w, (int, float)) and not isinstance(w, bool) and w < 1.0:
            warnings.append("%s.width_m: %s < 1m, 边缘采样可能失效出缝隙" % (p, w))
        # bed_depth_m 建议 >= 0.5m
        bd = rv.get("bed_depth_m")
        if (isinstance(bd, (int, float)) and not isinstance(bd, bool)
                and 0 < bd < 0.5):
            warnings.append("%s.bed_depth_m: %s < 0.5m, 水面沉入深度不足" % (p, bd))
        # waterfalls[].t 应在 [0, 1] 范围
        for j, wf in enumerate(rv.get("waterfalls", [])):
            wp = "%s.waterfalls[%d]" % (p, j)
            t = wf.get("t")
            if (isinstance(t, (int, float)) and not isinstance(t, bool)
                    and not (0 <= t <= 1)):
                errors.append("%s.t: 值 %s 超出范围 [0, 1]" % (wp, t))

    # roads[]
    for i, rd in enumerate(hp.get("roads", [])):
        p = "%s.roads[%d]" % (path, i)
        points = rd.get("points", [])
        if len(points) < 2:
            errors.append("%s: points 至少需要2个点, 实际 %d 个" % (p, len(points)))


# ===========================================================================
# 第二梯队 7): 建筑重叠检查
# ===========================================================================

def validate_building_overlap(hp, path, warnings):
    """检查 height_pattern.buildings[] 两两是否重叠 (AABB 检测, 忽略旋转)"""
    buildings = hp.get("buildings", [])
    if len(buildings) < 2:
        return

    # 收集每栋建筑的 AABB (index, center_x, center_y, half_w, half_d)
    aabbs = []
    for i, bd in enumerate(buildings):
        center = bd.get("center")
        size_m = bd.get("size_m")
        if not (isinstance(center, list) and len(center) >= 2):
            continue
        if not (isinstance(size_m, list) and len(size_m) >= 2):
            continue
        cx, cy = center[0], center[1]
        hw = size_m[0] / 2.0
        hd = size_m[1] / 2.0
        aabbs.append((i, cx, cy, hw, hd))

    # 两两检查 AABB 重叠
    for a in range(len(aabbs)):
        for b in range(a + 1, len(aabbs)):
            i1, cx1, cy1, hw1, hd1 = aabbs[a]
            i2, cx2, cy2, hw2, hd2 = aabbs[b]
            # AABB 重叠判定: 两轴投影距离 < 半宽之和
            if (abs(cx1 - cx2) < hw1 + hw2 and
                    abs(cy1 - cy2) < hd1 + hd2):
                dist = math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)
                warnings.append(
                    "%s.buildings[%d] 与 buildings[%d] 可能重叠 (中心距离=%.1fm)"
                    % (path, i1, i2, dist)
                )


# ===========================================================================
# 水系 flow_speed 一致性检查 (补充检查项)
# 铁律: 河流 flow_speed > 湖面 flow_speed (河流流速应快于湖泊)
# ===========================================================================

def validate_water_flow_speed(hp, path, warnings):
    """检查水系 flow_speed 一致性: 河流流速应大于湖面流速"""
    water = hp.get("water")
    rivers = hp.get("rivers", [])
    if not water or not rivers:
        return

    water_speed = water.get("flow_speed")
    if not isinstance(water_speed, (int, float)) or isinstance(water_speed, bool):
        return

    for i, rv in enumerate(rivers):
        rv_speed = rv.get("flow_speed")
        if (isinstance(rv_speed, (int, float)) and not isinstance(rv_speed, bool)
                and rv_speed <= water_speed):
            warnings.append(
                "%s.rivers[%d].flow_speed(%s) <= water.flow_speed(%s), "
                "河流流速应快于湖泊" % (path, i, rv_speed, water_speed)
            )


# ===========================================================================
# 主校验入口
# ===========================================================================

def validate_scene_quality(scene):
    """校验场景 JSON 的语义质量, 返回 (errors, warnings)。

    与 validate_scene_json.validate_scene 互补:
      - validate_scene: 字段名/类型/必填/枚举 (结构正确性)
      - validate_scene_quality: 数值范围/条件必填/几何边界 (语义质量)

    Args:
        scene: 场景 JSON 字典

    Returns:
        (errors, warnings) 两个列表, errors 为空表示无阻塞错误
    """
    errors = []
    warnings = []

    ls = scene.get("landscape", {})
    if not ls:
        return errors, warnings

    # ---- landscape.grass 下的 grass_varieties ----
    g = ls.get("grass")
    if g and isinstance(g, dict):
        gvs = g.get("grass_varieties", [])
        if isinstance(gvs, list):
            gv_path = "landscape.grass.grass_varieties"
            validate_variety_required(gvs, gv_path, errors)
            validate_variety_ranges(gvs, gv_path, errors)

    # ---- height_pattern 下的全部检查 ----
    hp = ls.get("height_pattern")
    if not hp or not isinstance(hp, dict):
        return errors, warnings

    hp_path = "landscape.height_pattern"

    # === 第一梯队 ===
    # 1) 数值范围
    validate_ranges(hp, hp_path, errors)

    # 2) 条件必填
    validate_conditional_required(hp, hp_path, errors)

    # 3) 草麦必填字段 (height_pattern 下的 grass_varieties / wheat_varieties)
    gvs = hp.get("grass_varieties", [])
    if isinstance(gvs, list):
        gv_path = hp_path + ".grass_varieties"
        validate_variety_required(gvs, gv_path, errors)
        validate_variety_ranges(gvs, gv_path, errors)

    wvs = hp.get("wheat_varieties", [])
    if isinstance(wvs, list):
        wv_path = hp_path + ".wheat_varieties"
        validate_variety_required(wvs, wv_path, errors)
        validate_variety_ranges(wvs, wv_path, errors)

    # 4) 条件互斥
    validate_type_exclusive(hp, hp_path, warnings)

    # === 第二梯队 ===
    # 计算地形物理尺寸
    phys_x, phys_y = calc_terrain_size(ls)

    # 5) 几何边界
    validate_geometric_bounds(hp, phys_x, phys_y, hp_path, errors, warnings)

    # 6) 河道路径有效性
    validate_river_road_paths(hp, hp_path, errors, warnings)

    # 7) 建筑重叠
    validate_building_overlap(hp, hp_path, warnings)

    # 补充: 水系 flow_speed 一致性
    validate_water_flow_speed(hp, hp_path, warnings)

    return errors, warnings


# ===========================================================================
# CLI 入口
# ===========================================================================

def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python validate_scene_quality.py <场景.json>")
        sys.exit(1)

    scene_path = args[0]
    if not os.path.isfile(scene_path):
        print("文件不存在: " + scene_path)
        sys.exit(1)

    try:
        with open(scene_path, "r", encoding="utf-8") as f:
            scene = json.load(f)
    except json.JSONDecodeError as e:
        print("JSON 解析失败: %s (行 %d 列 %d)" % (e.msg, e.lineno, e.colno))
        sys.exit(1)

    errors, warnings = validate_scene_quality(scene)

    if warnings:
        print("--- 警告 (%d) ---" % len(warnings))
        for w in warnings:
            print("  [WARN] " + w)

    if errors:
        print("--- 错误 (%d) ---" % len(errors))
        for e in errors:
            print("  [ERROR] " + e)
        print("\n质量校验失败: %d 个错误" % len(errors))
        sys.exit(1)
    else:
        print("质量校验通过: 数值范围/条件必填/几何边界均合法")
        if warnings:
            print("(有 %d 个警告)" % len(warnings))
        sys.exit(0)


if __name__ == "__main__":
    main()
