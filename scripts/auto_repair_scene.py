# -*- coding: utf-8 -*-
"""
auto_repair_scene.py - 场景 JSON 自动修复

与 validate_scene_quality.py 配对: 校验器检测语义质量缺陷, 修复器就地修复确定性缺陷。

修复分两层:
  绿色层 (安全修复, 总是执行): 值有明确正确答案, 修复无副作用
    1) 数值范围: bank_ratio/perturbation_strength clamp [0,1],
       peak_min<=peak_max 交换, cull_dist clamp [1,100000], end>start
    2) 条件必填: height_pattern.type 决定的必填字段缺失时用 height_pattern.md 默认值填充
    3) 草麦必填: start_cull_dist/end_cull_dist 缺失时用经验默认值填充
    4) 河流参数: width_m<1→1.0, bed_depth_m<0.5→0.5, waterfalls[].t clamp [0,1]
    5) placement 一致性: grid rows=0/cols=0 + instances 非空时清除 grid
  黄色层 (风险修复, aggressive=True 时执行): 修复可能改变场景特征
    6) 几何越界: hills/valleys/rivers/roads/buildings 坐标 clamp 到地形范围内
    7) 水流速度: river.flow_speed <= water.flow_speed 时提升 river 速度

不修复的红色层 (需语义决策, 留给 LLM):
    - 条件互斥字段 (删字段还是改 type 是语义决策)
    - river/road points<2 (需生成额外路径点, 创造性决策)
    - 建筑重叠 (移动哪个/多少/方向是空间规划决策)

用法:
    python auto_repair_scene.py <场景.json> [--aggressive]
    python auto_repair_scene.py <场景.json> --inplace  (就地写回文件)

退出码: 0=修复完成(可能有修复)  1=JSON 解析失败
"""

import json
import logging
import math
import os
import sys

# 模块级日志器 — 复用项目统一的 "uescenefactory" 日志体系
# 修复流程的每一步（绿色层/黄色层/校验）都会记录到日志, 方便排查修复失败的原因
_logger = logging.getLogger("uescenefactory.auto_repair")

# ===========================================================================
# 修复注册表 (与 validate_scene_quality.py 的检测注册表对齐)
# 数据来源: height_pattern.md 字段表
# ===========================================================================

# height_pattern 顶层字段范围 (与 HP_RANGE_FIELDS 对齐)
HP_REPAIR_RANGES = {
    "bank_ratio": (0.0, 1.0),
    "perturbation_strength": (0.0, 1.0),
}

# grass_varieties / wheat_varieties 字段范围 (与 VARIETY_RANGE_FIELDS 对齐)
VARIETY_REPAIR_RANGES = {
    "start_cull_dist": (1, 100000),
    "end_cull_dist": (1, 100000),
}

# 条件必填字段默认值 (来自 height_pattern.md 各模式字段表)
# type -> {field: default_value}
HP_CONDITIONAL_DEFAULTS = {
    "terraced": {
        "step_height_m": 3.0,
        "step_width_m": 12.0,
        "bank_ratio": 0.25,
        "base_height_m": 0.0,
    },
    "karst": {
        "peak_count": 30,
        "peak_height_min_m": 10.0,
        "peak_height_max_m": 40.0,
        "peak_radius_m": 20.0,
    },
    "gully": {
        "main_direction_deg": 0.0,
        "main_length_m": 1000.0,
        "gully_depth_m": 6.0,
        "gully_width_m": 12.0,
        "profile": "V",
    },
}

# 草麦必填字段默认值 (来自 height_pattern.md 草麦变体表)
# 草推荐 start=3000/end=30000, 麦推荐 start=3000/end=50000
VARIETY_DEFAULTS = {
    "grass_varieties": {"start_cull_dist": 3000, "end_cull_dist": 30000},
    "wheat_varieties": {"start_cull_dist": 3000, "end_cull_dist": 50000},
}

# 河流参数最小值 (来自 height_pattern.md rivers 子表)
RIVER_MIN_WIDTH = 1.0
RIVER_MIN_BED_DEPTH = 0.5


# ===========================================================================
# 工具函数
# ===========================================================================

def _is_number(val):
    """判断 val 是否为数值 (排除 bool, 因为 isinstance(True, int)==True)"""
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _clamp(val, lo, hi):
    """将 val 钳制到 [lo, hi] 范围"""
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def _log(repairs, path, field, old, new):
    """记录一条修复日志 — 同时追加到 repairs 列表和日志系统"""
    msg = "%s.%s: %s -> %s" % (path, field, old, new)
    repairs.append(msg)
    _logger.info("[REPAIR] %s", msg)


# ===========================================================================
# 绿色层 1): 数值范围修复
# ===========================================================================

def repair_ranges(hp, path, repairs):
    """修复 height_pattern 顶层字段数值范围 (clamp 到合法区间)"""
    for field, (lo, hi) in HP_REPAIR_RANGES.items():
        if field in hp and _is_number(hp[field]):
            old = hp[field]
            new = _clamp(old, lo, hi)
            if new != old:
                hp[field] = new
                _log(repairs, path, field, old, new)

    # karst 模式: peak_height_min_m > peak_height_max_m 时交换
    pmin = hp.get("peak_height_min_m")
    pmax = hp.get("peak_height_max_m")
    if _is_number(pmin) and _is_number(pmax) and pmin > pmax:
        hp["peak_height_min_m"] = pmax
        hp["peak_height_max_m"] = pmin
        _log(repairs, path, "peak_height_min_m", pmin, pmax)
        _log(repairs, path, "peak_height_max_m", pmax, pmin)


def repair_variety_ranges(varieties, path_prefix, repairs):
    """修复 grass_varieties/wheat_varieties 每项的数值范围"""
    for i, v in enumerate(varieties):
        if not isinstance(v, dict):
            continue
        p = "%s[%d]" % (path_prefix, i)
        # clamp cull_dist 范围
        for field, (lo, hi) in VARIETY_REPAIR_RANGES.items():
            if field in v and _is_number(v[field]):
                old = v[field]
                new = _clamp(old, lo, hi)
                if new != old:
                    v[field] = new
                    _log(repairs, p, field, old, new)
        # end_cull_dist <= start_cull_dist 时提升 end
        scd = v.get("start_cull_dist")
        ecd = v.get("end_cull_dist")
        if _is_number(scd) and _is_number(ecd) and ecd <= scd:
            # 提升 end 到 start + 合理差值 (至少 1000cm=10m)
            new_ecd = scd + 1000
            old_ecd = ecd
            v["end_cull_dist"] = new_ecd
            _log(repairs, p, "end_cull_dist", old_ecd, new_ecd)


# ===========================================================================
# 绿色层 2): 条件必填字段修复 (用 height_pattern.md 默认值填充)
# ===========================================================================

def repair_conditional_required(hp, path, repairs):
    """修复 height_pattern.type 必填字段缺失 (用文档默认值填充)"""
    hp_type = hp.get("type", "")
    defaults = HP_CONDITIONAL_DEFAULTS.get(hp_type)
    if not defaults:
        return
    for field, default_val in defaults.items():
        if field not in hp:
            hp[field] = default_val
            _log(repairs, path, field, "(缺失)", default_val)


# ===========================================================================
# 绿色层 3): 草麦必填字段修复
# ===========================================================================

def repair_variety_required(varieties, path_prefix, variety_type, repairs):
    """修复 grass_varieties/wheat_varieties 必填字段缺失

    variety_type: "grass_varieties" 或 "wheat_varieties", 决定 end_cull_dist 默认值
    """
    defaults = VARIETY_DEFAULTS.get(variety_type, VARIETY_DEFAULTS["grass_varieties"])
    for i, v in enumerate(varieties):
        if not isinstance(v, dict):
            continue
        p = "%s[%d]" % (path_prefix, i)
        for field, default_val in defaults.items():
            if field not in v:
                v[field] = default_val
                _log(repairs, p, field, "(缺失)", default_val)


# ===========================================================================
# 绿色层 4): 河流参数修复
# ===========================================================================

def repair_river_params(hp, path, repairs):
    """修复河流参数: width_m/bed_depth_m 最小值, waterfalls[].t 范围"""
    for i, rv in enumerate(hp.get("rivers", [])):
        if not isinstance(rv, dict):
            continue
        p = "%s.rivers[%d]" % (path, i)
        # width_m < 1.0 → 1.0
        w = rv.get("width_m")
        if _is_number(w) and w < RIVER_MIN_WIDTH:
            old = w
            rv["width_m"] = RIVER_MIN_WIDTH
            _log(repairs, p, "width_m", old, RIVER_MIN_WIDTH)
        # bed_depth_m: 0 < val < 0.5 → 0.5 (0=不冲刷, 不修复)
        bd = rv.get("bed_depth_m")
        if _is_number(bd) and 0 < bd < RIVER_MIN_BED_DEPTH:
            old = bd
            rv["bed_depth_m"] = RIVER_MIN_BED_DEPTH
            _log(repairs, p, "bed_depth_m", old, RIVER_MIN_BED_DEPTH)
        # waterfalls[].t clamp [0,1]
        for j, wf in enumerate(rv.get("waterfalls", [])):
            if not isinstance(wf, dict):
                continue
            wp = "%s.waterfalls[%d]" % (p, j)
            t = wf.get("t")
            if _is_number(t) and not (0 <= t <= 1):
                old = t
                new = _clamp(t, 0, 1)
                wf["t"] = new
                _log(repairs, wp, "t", old, new)


# ===========================================================================
# 绿色层 5): placement grid/instances 一致性修复
# ===========================================================================

def repair_placements_grid_instances(scene, repairs):
    """修复 placements 中 grid rows=0/cols=0 与 instances 非空并存的矛盾状态

    当 placement.type=instanced_grid 且 grid 存在(矩形模式)但 rows=0/cols=0,
    同时 instances 数组非空时, 将 grid 置为 None, 让生成代码走 instances 路径。
    (对应 build_scene.py _gen_instances_from_grid 的 instances fallback 分支)

    此修复是安全绿色层: 有确定正确答案(grid 吞掉 instances 是 bug), 修复无副作用。
    """
    placements = scene.get("placements")
    if not isinstance(placements, list):
        return
    for i, p in enumerate(placements):
        if not isinstance(p, dict):
            continue
        # 仅处理 instanced_grid 类型 (group/instances 类型不走 grid 逻辑)
        if p.get("type") != "instanced_grid":
            continue
        gr = p.get("grid")
        if not isinstance(gr, dict):
            continue
        # 圆环模式用 count, 不需要 rows/cols, 跳过
        if gr.get("pattern") == "circle":
            continue
        # 矩形模式 rows=0 且 cols=0 → grid 会生成 0 个实例
        if gr.get("rows", 0) == 0 and gr.get("cols", 0) == 0:
            # 仅当 instances 非空时才清除 grid (否则无 fallback, 留给 LLM)
            instances = p.get("instances")
            if isinstance(instances, list) and len(instances) > 0:
                path = "placements[%d]" % i
                _log(repairs, path, "grid", gr, None)
                p["grid"] = None


# ===========================================================================
# 黄色层 6): 几何越界坐标修复 (aggressive=True 时执行)
# ===========================================================================

def _clamp_coord(val, lo, hi):
    """将坐标值 clamp 到 [lo, hi]"""
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def repair_geometric_bounds(hp, phys_x, phys_y, path, repairs):
    """修复几何越界坐标 (clamp 到地形物理范围 [0, phys_x] x [0, phys_y])

    注意: 此修复会改变地形特征位置, 可能不是用户意图, 故仅在 aggressive=True 时执行
    """
    # hills[]
    for i, h in enumerate(hp.get("hills", [])):
        if not isinstance(h, dict):
            continue
        p = "%s.hills[%d]" % (path, i)
        cx = h.get("center_x_m")
        cy = h.get("center_y_m")
        if _is_number(cx):
            new = _clamp_coord(cx, 0, phys_x)
            if new != cx:
                h["center_x_m"] = new
                _log(repairs, p, "center_x_m", cx, new)
        if _is_number(cy):
            new = _clamp_coord(cy, 0, phys_y)
            if new != cy:
                h["center_y_m"] = new
                _log(repairs, p, "center_y_m", cy, new)

    # valleys[]
    for i, v in enumerate(hp.get("valleys", [])):
        if not isinstance(v, dict):
            continue
        p = "%s.valleys[%d]" % (path, i)
        cx = v.get("center_x_m")
        cy = v.get("center_y_m")
        if _is_number(cx):
            new = _clamp_coord(cx, 0, phys_x)
            if new != cx:
                v["center_x_m"] = new
                _log(repairs, p, "center_x_m", cx, new)
        if _is_number(cy):
            new = _clamp_coord(cy, 0, phys_y)
            if new != cy:
                v["center_y_m"] = new
                _log(repairs, p, "center_y_m", cy, new)

    # ridges[]: clamp region 边界
    for i, r in enumerate(hp.get("ridges", [])):
        if not isinstance(r, dict):
            continue
        p = "%s.ridges[%d]" % (path, i)
        for fx in ("region_min_x_m", "region_max_x_m"):
            val = r.get(fx)
            if _is_number(val):
                new = _clamp_coord(val, 0, phys_x)
                if new != val:
                    r[fx] = new
                    _log(repairs, p, fx, val, new)
        for fy in ("region_min_y_m", "region_max_y_m"):
            val = r.get(fy)
            if _is_number(val):
                new = _clamp_coord(val, 0, phys_y)
                if new != val:
                    r[fy] = new
                    _log(repairs, p, fy, val, new)

    # rivers[].points
    for i, rv in enumerate(hp.get("rivers", [])):
        if not isinstance(rv, dict):
            continue
        p = "%s.rivers[%d]" % (path, i)
        for j, pt in enumerate(rv.get("points", [])):
            if not (isinstance(pt, list) and len(pt) >= 2):
                continue
            pp = "%s.points[%d]" % (p, j)
            px, py = pt[0], pt[1]
            new_x = _clamp_coord(px, 0, phys_x) if _is_number(px) else px
            new_y = _clamp_coord(py, 0, phys_y) if _is_number(py) else py
            if new_x != px or new_y != py:
                pt[0] = new_x
                pt[1] = new_y
                _log(repairs, pp, "[x,y]", [px, py], [new_x, new_y])

    # roads[].points
    for i, rd in enumerate(hp.get("roads", [])):
        if not isinstance(rd, dict):
            continue
        p = "%s.roads[%d]" % (path, i)
        for j, pt in enumerate(rd.get("points", [])):
            if not (isinstance(pt, list) and len(pt) >= 2):
                continue
            pp = "%s.points[%d]" % (p, j)
            px, py = pt[0], pt[1]
            new_x = _clamp_coord(px, 0, phys_x) if _is_number(px) else px
            new_y = _clamp_coord(py, 0, phys_y) if _is_number(py) else py
            if new_x != px or new_y != py:
                pt[0] = new_x
                pt[1] = new_y
                _log(repairs, pp, "[x,y]", [px, py], [new_x, new_y])

    # buildings[].center
    for i, bd in enumerate(hp.get("buildings", [])):
        if not isinstance(bd, dict):
            continue
        p = "%s.buildings[%d]" % (path, i)
        center = bd.get("center")
        if not (isinstance(center, list) and len(center) >= 2):
            continue
        cx, cy = center[0], center[1]
        new_x = _clamp_coord(cx, 0, phys_x) if _is_number(cx) else cx
        new_y = _clamp_coord(cy, 0, phys_y) if _is_number(cy) else cy
        if new_x != cx or new_y != cy:
            center[0] = new_x
            center[1] = new_y
            _log(repairs, p, "center[x,y]", [cx, cy], [new_x, new_y])


# ===========================================================================
# 黄色层 6): 水流速度修复 (aggressive=True 时执行)
# ===========================================================================

def repair_water_flow_speed(hp, path, repairs):
    """修复水系 flow_speed: 河流流速应大于湖面流速

    river.flow_speed <= water.flow_speed 时, 提升 river 速度 = water + 增量
    增量取经验值 1.0 (河流流速通常 1.0~10.0)
    """
    water = hp.get("water")
    rivers = hp.get("rivers", [])
    if not (isinstance(water, dict) and rivers):
        return

    water_speed = water.get("flow_speed")
    if not _is_number(water_speed):
        return

    for i, rv in enumerate(rivers):
        if not isinstance(rv, dict):
            continue
        rv_speed = rv.get("flow_speed")
        if _is_number(rv_speed) and rv_speed <= water_speed:
            new_speed = water_speed + 1.0
            old = rv_speed
            rv["flow_speed"] = new_speed
            _log(repairs, "%s.rivers[%d]" % (path, i), "flow_speed", old, new_speed)


# ===========================================================================
# 工具: 计算地形物理尺寸 (复用 validate_scene_quality.py 公式)
# ===========================================================================

def calc_terrain_size(ls):
    """计算地形物理尺寸 (米), 返回 (phys_x, phys_y)。

    公式来自 build_scene.py:
      phys_x = (ccx * ssq * nsub) * scl[0] / 100.0
      phys_y = (ccy * ssq * nsub) * scl[1] / 100.0
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
# 主修复入口
# ===========================================================================

def auto_repair_scene(scene, aggressive=False):
    """自动修复场景 JSON 的语义质量缺陷 (就地修改 scene)。

    与 validate_scene_quality.validate_scene_quality 配对:
      - 绿色层: 安全修复 (数值 clamp, 默认值填充, 最小值约束, placement 一致性), 总是执行
      - 黄色层: 风险修复 (几何坐标 clamp, 水流速度调整), 仅 aggressive=True 时执行
      - 红色层: 不修复 (条件互斥/points不足/建筑重叠), 留给 LLM

    Args:
        scene: 场景 JSON 字典 (将被就地修改)
        aggressive: True 时启用黄色层风险修复 (几何越界/水流速度)

    Returns:
        repairs: 修复日志列表, 每项格式 "路径.字段: 旧值 -> 新值"
    """
    repairs = []

    # 注意: landscape 为 null/缺失时不做修复 (无法凭空生成地形配置),
    # 但 validate_scene_quality 会将 null landscape 报为 error, 交由 Stage 3 LLM 修复。
    # 这里用 isinstance 而非 "if not ls" 是为了区分 null/缺失 vs 空字典 {} 的情况。
    ls = scene.get("landscape")
    if not isinstance(ls, dict):
        return repairs

    # ---- landscape.grass 下的 grass_varieties ----
    g = ls.get("grass")
    if isinstance(g, dict):
        gvs = g.get("grass_varieties")
        if isinstance(gvs, list):
            gv_path = "landscape.grass.grass_varieties"
            repair_variety_required(gvs, gv_path, "grass_varieties", repairs)
            repair_variety_ranges(gvs, gv_path, repairs)

    # ---- height_pattern 下的全部修复 ----
    hp = ls.get("height_pattern")
    if not isinstance(hp, dict):
        return repairs

    hp_path = "landscape.height_pattern"

    # === 绿色层 ===
    # 1) 数值范围
    repair_ranges(hp, hp_path, repairs)

    # 2) 条件必填
    repair_conditional_required(hp, hp_path, repairs)

    # 3) 草麦必填 + 范围 (height_pattern 下的 grass_varieties / wheat_varieties)
    gvs = hp.get("grass_varieties")
    if isinstance(gvs, list):
        gv_path = hp_path + ".grass_varieties"
        repair_variety_required(gvs, gv_path, "grass_varieties", repairs)
        repair_variety_ranges(gvs, gv_path, repairs)

    wvs = hp.get("wheat_varieties")
    if isinstance(wvs, list):
        wv_path = hp_path + ".wheat_varieties"
        repair_variety_required(wvs, wv_path, "wheat_varieties", repairs)
        repair_variety_ranges(wvs, wv_path, repairs)

    # 4) 河流参数
    repair_river_params(hp, hp_path, repairs)

    # 5) placement grid/instances 一致性 (绿色层, 作用于 scene.placements)
    repair_placements_grid_instances(scene, repairs)

    # === 黄色层 (aggressive=True 时执行) ===
    if aggressive:
        # 6) 几何越界
        phys_x, phys_y = calc_terrain_size(ls)
        repair_geometric_bounds(hp, phys_x, phys_y, hp_path, repairs)

        # 7) 水流速度
        repair_water_flow_speed(hp, hp_path, repairs)

    return repairs


# ===========================================================================
# L5 兜底层: 关键分区缺失时注入默认值 (防止 LLM 删除字段导致黑屏/无草/平坦)
# ===========================================================================

def ensure_critical_sections(scene):
    """L5 安全网: 确保 lighting/weather/grass/height_pattern 关键分区存在。

    在 repair_and_validate 的最开头调用 (早于绿色层 auto_repair_scene),
    确保 LLM 即便在 Stage 3 误删了必填分区, 也至少注入一套经模板验证的默认值,
    避免 build_scene.py 因 if X: 守卫静默跳过功能而产出黑屏/无草/平坦的废场景。

    仅在字段为 null/缺失/非 dict/空字典 时注入, 已有内容则原样保留 (不覆盖)。

    Args:
        scene: 场景 JSON 字典 (就地修改)

    Returns:
        repairs: 注入日志列表, 每项描述注入了哪个分区及原因
    """
    repairs = []

    # ---- lighting: 缺失/null/空 → 注入默认光照 (防场景全黑) ----
    # 默认值来源: template_p11_all_terrain_realistic.json (已验证可正常渲染)
    lt = scene.get("lighting")
    if lt is None or not isinstance(lt, dict) or not lt:
        scene["lighting"] = {
            "directional_light": {
                "location": [0, 0, 3000],
                "rotation": [-15, 60, 0],
                "intensity": 10.0,
                "color": [1.0, 0.85, 0.7],
                "cast_shadows": True,
            },
            "sky_light": {
                "location": [0, 0, 3000],
                "intensity": 1.0,
                "color": [0.75, 0.85, 1.0],
            },
            "sky_atmosphere": {
                "location": [0, 0, 0],
            },
            "height_fog": {
                "location": [0, 0, 0],
                "density": 0.0001,
                "color": [0.7, 0.8, 0.9],
            },
        }
        # 记录注入原因: 区分缺失/null/类型错误/空字典, 方便排查 LLM 为何删除了该字段
        if lt is None:
            _reason = "缺失或 null"
        elif not isinstance(lt, dict):
            _reason = "类型错误(%s)" % type(lt).__name__
        else:
            _reason = "空字典"
        msg = "lighting: %s → 注入默认光照 (方向光+天光+大气+高度雾, 防场景全黑)" % _reason
        repairs.append(msg)
        _logger.warning("[L5-SAFETY] %s", msg)

    # ---- weather: 缺失/null/空 → 注入默认天气 (防无云) ----
    we = scene.get("weather")
    if we is None or not isinstance(we, dict) or not we:
        scene["weather"] = {
            "volumetric_clouds": {
                "location": [0, 0, 2000],
            },
        }
        if we is None:
            _reason = "缺失或 null"
        elif not isinstance(we, dict):
            _reason = "类型错误(%s)" % type(we).__name__
        else:
            _reason = "空字典"
        msg = "weather: %s → 注入默认天气 (体积云, 防无云)" % _reason
        repairs.append(msg)
        _logger.warning("[L5-SAFETY] %s", msg)

    # ---- landscape 下的 grass / height_pattern (仅当 landscape 是 dict 时) ----
    # 若 landscape 整体缺失, L1 Pydantic 验证器应已拦截, 此处不凭空创建完整 landscape
    ls = scene.get("landscape")
    if isinstance(ls, dict):
        # grass: 缺失/null/空 → 注入默认草地 (防灰色地形)
        g = ls.get("grass")
        if g is None or not isinstance(g, dict) or not g:
            ls["grass"] = {
                "grass_type": "/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass",
                "grass_mesh": "/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a",
                "layer_name": "Grass",
                "density": 120.0,
            }
            if g is None:
                _reason = "缺失或 null"
            elif not isinstance(g, dict):
                _reason = "类型错误(%s)" % type(g).__name__
            else:
                _reason = "空字典"
            msg = "landscape.grass: %s → 注入默认草地 (LGT_Grass+野草网格, 防灰色地形)" % _reason
            repairs.append(msg)
            _logger.warning("[L5-SAFETY] %s", msg)

        # height_pattern: 缺失/null/空 → 注入最小可行高度模式 (防完全平坦)
        hp = ls.get("height_pattern")
        if hp is None or not isinstance(hp, dict) or not hp:
            ls["height_pattern"] = {
                "type": "features",
                "blend_mode": "additive",
                "hills": [],
                "valleys": [],
                "ridges": [],
            }
            if hp is None:
                _reason = "缺失或 null"
            elif not isinstance(hp, dict):
                _reason = "类型错误(%s)" % type(hp).__name__
            else:
                _reason = "空字典"
            msg = "landscape.height_pattern: %s → 注入最小可行高度模式 (features, 防完全平坦)" % _reason
            repairs.append(msg)
            _logger.warning("[L5-SAFETY] %s", msg)
    else:
        # landscape 整体缺失/null — L1 Pydantic 验证器应已拦截, 到此说明严重异常
        _logger.error("[L5-SAFETY] landscape 整体缺失或非 dict (%s), 无法注入 grass/height_pattern — "
                      "L1 验证器应已拦截此情况, 请检查 Stage 2 是否跳过了 Pydantic 校验",
                      type(ls).__name__ if ls is not None else "None")

    return repairs


# ===========================================================================
# 修复-校验闭环 (流水线后处理调用)
# ===========================================================================

def repair_and_validate(scene):
    """确定性修复-校验闭环：绿色层修复 → 质量校验 → 有错则黄色层修复 → 再校验。

    流水线在 normalize_height_pattern 之后调用此函数，可在毫秒级内
    自动修复绝大多数语义缺陷，仅将红色层（条件互斥/points不足/建筑重叠）
    等需要语义决策的问题留给 LLM 处理。

    就地修改 scene dict，返回 (repairs, quality_errors, quality_warnings)：
    - repairs: 修复日志列表（可能为空）
    - quality_errors: 拋留质量错误（可能为空，空=全部修复成功）
    - quality_warnings: 质量警告列表
    """
    # 延迟导入避免循环依赖
    from scripts.validate_scene_quality import validate_scene_quality

    _scene_name = scene.get("scene", {}).get("name", "(未命名)")
    _logger.info("[REPAIR-LOOP] ===== 修复-校验闭环开始 (场景=%s) =====", _scene_name)

    # 第零轮: L5 兜底层 — 在绿色层修复之前, 确保关键分区 (lighting/weather/grass/height_pattern) 存在。
    # 若 LLM 在 Stage 3 误删了这些必填分区, auto_repair_scene 会因 isinstance 早期 return 跳过修复,
    # 此处注入经模板验证的默认值, 防止 build_scene.py 静默跳过功能而产出黑屏/无草/平坦场景。
    _logger.info("[REPAIR-LOOP] 第零轮: L5 关键分区兜底检查")
    l5_repairs = ensure_critical_sections(scene)
    if l5_repairs:
        _logger.warning("[REPAIR-LOOP] L5 兜底注入: %d 项 (LLM 误删了必填分区, 已注入默认值)", len(l5_repairs))
        for i, r in enumerate(l5_repairs, 1):
            _logger.warning("[REPAIR-LOOP]   L5 注入 %d/%d: %s", i, len(l5_repairs), r)
    else:
        _logger.info("[REPAIR-LOOP] L5 兜底检查通过: 关键分区均已存在 (无需注入)")

    # 第一轮：绿色层修复（安全，始终执行）
    # 绿色层: 数值clamp + 条件必填填充 + 草麦默认值 + 河流参数下限 + placement一致性 — 无副作用
    _logger.info("[REPAIR-LOOP] 第一轮: 绿色层修复 (aggressive=False, 安全修复)")
    repairs = auto_repair_scene(scene, aggressive=False)
    # 将 L5 兜底注入日志合并到总修复列表 (L5 在前, 绿色层在后, 保持时序)
    repairs = l5_repairs + repairs
    if repairs:
        _logger.info("[REPAIR-LOOP] 绿色层修复完成: %d 项 (含 L5 兜底 %d 项)", len(repairs), len(l5_repairs))
    else:
        _logger.info("[REPAIR-LOOP] 绿色层修复完成: 0 项 (无需安全修复)")

    # 第一轮校验：检查绿色层修复后的残留问题
    _logger.info("[REPAIR-LOOP] 第一轮校验: 质量校验开始")
    errors, warnings = validate_scene_quality(scene)
    if errors:
        _logger.warning("[REPAIR-LOOP] 第一轮校验: 残留 %d 项错误 (需黄色层修复)", len(errors))
        for i, e in enumerate(errors, 1):
            _logger.warning("[REPAIR-LOOP]   残留错误 %d/%d: %s", i, len(errors), e)
    else:
        _logger.info("[REPAIR-LOOP] 第一轮校验: 错误 0 项 (绿色层已修复全部问题)")
    if warnings:
        _logger.info("[REPAIR-LOOP] 第一轮校验: 警告 %d 项", len(warnings))
        for i, w in enumerate(warnings, 1):
            _logger.info("[REPAIR-LOOP]   警告 %d/%d: %s", i, len(warnings), w)

    # 第二轮：如果绿色层修复后仍有错误，尝试黄色层修复（几何越界/水流速度）
    # 黄色层: 几何坐标clamp + 水流速度调整 — 可能改变场景特征, 仅在有残留错误时执行
    if errors:
        _logger.info("[REPAIR-LOOP] 第二轮: 黄色层修复 (aggressive=True, 几何/水流修复)")
        repairs2 = auto_repair_scene(scene, aggressive=True)
        if repairs2:
            _logger.info("[REPAIR-LOOP] 黄色层修复完成: %d 项", len(repairs2))
        else:
            _logger.info("[REPAIR-LOOP] 黄色层修复完成: 0 项 (无需几何/水流修复)")
        repairs.extend(repairs2)

        # 第二轮校验：检查黄色层修复后的残留问题
        _logger.info("[REPAIR-LOOP] 第二轮校验: 质量校验开始")
        errors, warnings = validate_scene_quality(scene)
        if errors:
            _logger.warning("[REPAIR-LOOP] 第二轮校验: 仍有 %d 项错误 (红色层问题, 留给 LLM)", len(errors))
            for i, e in enumerate(errors, 1):
                _logger.warning("[REPAIR-LOOP]   红色层错误 %d/%d: %s", i, len(errors), e)
        else:
            _logger.info("[REPAIR-LOOP] 第二轮校验: 错误 0 项 (全部修复成功!)")
        if warnings:
            _logger.info("[REPAIR-LOOP] 第二轮校验: 警告 %d 项", len(warnings))
            for i, w in enumerate(warnings, 1):
                _logger.info("[REPAIR-LOOP]   警告 %d/%d: %s", i, len(warnings), w)
    else:
        _logger.info("[REPAIR-LOOP] 跳过黄色层 (第一轮已无错误)")

    # 汇总日志 — 一目了然地展示闭环结果
    _logger.info("[REPAIR-LOOP] ===== 修复-校验闭环结束 =====")
    _logger.info("[REPAIR-LOOP] 总修复: %d 项 | 残留错误: %d 项 | 警告: %d 项",
                 len(repairs), len(errors), len(warnings))
    if errors:
        _logger.warning("[REPAIR-LOOP] 残留错误需 LLM 处理 (条件互斥/路径点不足/建筑重叠等)")

    return repairs, errors, warnings


# ===========================================================================
# CLI 入口
# ===========================================================================

def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python auto_repair_scene.py <场景.json> [--aggressive] [--inplace]")
        sys.exit(1)

    scene_path = args[0]
    aggressive = "--aggressive" in args
    inplace = "--inplace" in args

    if not os.path.isfile(scene_path):
        print("文件不存在: " + scene_path)
        sys.exit(1)

    try:
        with open(scene_path, "r", encoding="utf-8") as f:
            scene = json.load(f)
    except json.JSONDecodeError as e:
        print("JSON 解析失败: %s (行 %d 列 %d)" % (e.msg, e.lineno, e.colno))
        sys.exit(1)

    repairs = auto_repair_scene(scene, aggressive=aggressive)

    if not repairs:
        print("无需修复: 所有字段均在合法范围内")
    else:
        print("--- 修复完成 (%d 项) ---" % len(repairs))
        for r in repairs:
            print("  [REPAIR] " + r)

        if inplace:
            with open(scene_path, "w", encoding="utf-8") as f:
                json.dump(scene, f, ensure_ascii=False, indent=2)
            print("已写回: " + scene_path)
        else:
            print("(未写回文件, 加 --inplace 写回)")

    sys.exit(0)


if __name__ == "__main__":
    main()
