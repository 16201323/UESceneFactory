# -*- coding: utf-8 -*-
"""
validate_scene_json.py - 场景 JSON 字段名校验

在编写或修改场景 JSON 后, 秒级校验字段名拼写、类型、必填项和枚举值,
避免 build_scene.py 静默忽略拼错字段导致功能失效。

与 validate_scene_assets.py 互补:
  - 本脚本校验字段名/类型/必填 (结构正确性)
  - validate_scene_assets.py 校验资产路径是否存在 (资源存在性)

用法:
    python validate_scene_json.py <场景.json>

退出码: 0=无错误(可有警告)  1=有错误

字段注册表对齐 build_scene.py (Python 层) 和 LandscapeHelper.cpp (C++ 层)。
"""

import json
import os
import sys

# ===========================================================================
# 字段注册表: 各分区的合法字段名及期望类型
# _note 字段是注释字段, build_scene.py 忽略, 全分区通用允许
# ===========================================================================

# 顶层分区
TOP_KEYS = {"scene", "landscape", "ground", "placements", "lighting", "weather", "rivers"}

# scene 分区
SCENE_FIELDS = {
    "name": str, "target_level": str, "description": str,
}

# landscape 基础参数 (Python 层)
LANDSCAPE_FIELDS = {
    "material": str,
    "section_size_quads": int,
    "num_subsections": int,
    "component_count_x": int,
    "component_count_y": int,
    "location": list,
    "rotation": list,
    "scale": list,
    "layers": list,
    "grass": dict,
    "wheat": dict,
    "height_pattern": dict,
}

# landscape.layers[] 每层
LAYER_FIELDS = {
    "info": str, "weight": (int, float), "weight_pattern": dict,
}

# landscape.grass
GRASS_FIELDS = {
    "grass_type": str, "grass_mesh": str, "layer_name": str, "density": (int, float),
    "grass_varieties": list,
}

# landscape.wheat
WHEAT_FIELDS = {
    "type_path": str, "layer_name": str,
}

# height_pattern 顶层字段 (C++ 层, features 模式最常用)
HP_FIELDS = {
    "type": str, "blend_mode": str,
    "amplitude_m": (int, float), "frequency": (int, float),
    "direction_deg": (int, float), "seed": (int, float),
    "hill_count": int, "hill_radius_m": (int, float),
    "hills": list, "valleys": list, "ridges": list,
    "water": dict, "rivers": list, "roads": list, "buildings": list,
    "scatter": list, "grass_varieties": list, "wheat_varieties": list,
    "noise_overlay": dict,
    "perturbation_strength": (int, float),
    "perturbation_scale": (int, float),
    "perturbation_seed": int,
    # 模块3: 中国特色地形模式新增字段
    # terraced: 梯田
    "step_height_m": (int, float),
    "step_width_m": (int, float),
    "bank_ratio": (int, float),
    "base_height_m": (int, float),
    # karst: 喀斯特峰林
    "peak_count": int,
    "min_distance_m": (int, float),
    "peak_height_min_m": (int, float),
    "peak_height_max_m": (int, float),
    "peak_radius_m": (int, float),
    "doline_count": int,
    "doline_depth_m": (int, float),
    "doline_radius_m": (int, float),
    # gully: 黄土沟壑
    "main_direction_deg": (int, float),
    "main_length_m": (int, float),
    "meander_amplitude_m": (int, float),
    "meander_frequency": (int, float),
    "branch_count": int,
    "branch_angle_deg": (int, float),
    "branch_length_ratio": (int, float),
    "branch_depth": int,
    "gully_depth_m": (int, float),
    "gully_width_m": (int, float),
    "profile": str,
}

# height_pattern.hills[] 单个山丘
HP_HILL_FIELDS = {
    "center_x_m": (int, float), "center_y_m": (int, float),
    "radius_m": (int, float), "height_m": (int, float),
}

# height_pattern.valleys[] 单个山谷
HP_VALLEY_FIELDS = {
    "center_x_m": (int, float), "center_y_m": (int, float),
    "radius_m": (int, float), "depth_m": (int, float),
    "bottom_radius_m": (int, float),
}

# height_pattern.ridges[] 单个山脊
HP_RIDGE_FIELDS = {
    "region_min_x_m": (int, float), "region_min_y_m": (int, float),
    "region_max_x_m": (int, float), "region_max_y_m": (int, float),
    "amplitude_m": (int, float), "frequency": (int, float),
    "direction_deg": (int, float),
}

# height_pattern.water (模块5新增: flow_speed 控制湖面Panner流速动画)
HP_WATER_FIELDS = {
    "level_m": (int, float), "material_path": str,
    "flow_speed": (int, float),
}

# height_pattern.rivers[] 河流 (模块1新增: bed_depth_m, profile; 模块5新增: flow_speed)
HP_RIVER_FIELDS = {
    "points": list, "width_m": (int, float), "material_path": str,
    "bed_depth_m": (int, float), "profile": str,
    "width_end_m": (int, float), "waterfalls": list,
    "flow_speed": (int, float),
}

# height_pattern.roads[] 道路 (模块1新增: level_depth_m, shoulder_width_m, level_height_m, mesh_path)
HP_ROAD_FIELDS = {
    "points": list, "width_m": (int, float), "material_path": str,
    "level_depth_m": (int, float), "shoulder_width_m": (int, float),
    "level_height_m": (int, float), "mesh_path": str,
}

# height_pattern.buildings[] 建筑 (模块1新增: shoulder_width_m)
HP_BUILDING_FIELDS = {
    "center": list, "size_m": list, "height_m": (int, float),
    "rotation_deg": (int, float), "material_path": str,
    "shoulder_width_m": (int, float),
}

# height_pattern.scatter[] 散布 (模块2新增: 智能分层过滤字段; 道路排除新增: road_exclude_distance_m)
HP_SCATTER_FIELDS = {
    "mesh_path": str, "count": int, "seed": int,
    "scale_min": (int, float, list), "scale_max": (int, float, list),
    "random_rotation": bool,
    "layer_filter": dict, "slope_filter": dict, "altitude_filter": dict,
    "max_retries": int,
    "road_exclude_distance_m": (int, float),
}

# height_pattern.grass_varieties[] / wheat_varieties[] 共用
HP_VARIETY_FIELDS = {
    "mesh_path": str, "density": (int, float),
    "scale_min": (int, float, list), "scale_max": (int, float, list),
    "jitter": (int, float), "random_rotation": bool,
    "start_cull_dist": (int, float), "end_cull_dist": (int, float),
}

# height_pattern.noise_overlay
HP_NOISE_FIELDS = {
    "amplitude_m": (int, float), "frequency": (int, float),
    "octaves": int, "seed": int,
}

# weight_pattern (layers[].weight_pattern)
WP_FIELDS = {
    "pattern": str,
    "height_min_m": (int, float), "height_max_m": (int, float),
    "invert": bool, "fade_max_m": (int, float), "fade_width_m": (int, float),
    "exclude_regions": list, "corridor_exclude": bool,
    "slope_min": (int, float), "slope_max": (int, float),
    "region_min_x": (int, float), "region_min_y": (int, float),
    "region_max_x": (int, float), "region_max_y": (int, float),
    "regions": list,
    "noise_frequency": (int, float), "noise_seed": (int, float),
    "noise_octaves": (int, float),
    "aspect_deg": (int, float), "aspect_range_deg": (int, float),
    "snow_line_m": (int, float), "transition_m": (int, float),
    "max_slope": (int, float),
}

# ground 分区
GROUND_FIELDS = {
    "asset": str, "material_override": str,
}

# placements[] 每个
# 注: count/rotation/scale/skip_z_fix/scale_before_rotation 为 build_scene.py
#     group(static/instanced_grid 共用)放置实际支持的字段(见 build_scene.py 1106~1116 行),
#     此前漏登导致已验证模板(如 template_p1_heliport.json)误报未知字段, 现补齐
# 补登: snap_to_ground 为 blueprint/group 类型贴地支持(build_scene.py 蓝图处理器与
#     组处理器中新增, 查询 get_terrain_z 覆盖 location Z 使底部贴合地形表面);
#     ground_assembly 为 group 类型地面组装(build_scene.py 组处理器将所有部件平移
#     使 min_z 对齐到 gloc[2]), 此前漏登导致村落房屋场景误报未知字段
PLACEMENT_FIELDS = {
    "type": str, "asset": str, "location": list,
    "rotation": list, "scale": list,
    "grid": dict, "asset_prefix": str, "count": int,
    "skip_z_fix": bool, "scale_before_rotation": bool,
    "snap_to_ground": bool, "ground_assembly": bool,
    "instances": list, "material_override": str,
    "field": dict, "village": dict,
}

# placements[].grid
GRID_FIELDS = {
    "rows": int, "cols": int, "origin": list, "spacing": list,
    "jitter": (int, float), "random_yaw": bool,
    "scale_min": (int, float, list), "scale_max": (int, float, list),
    "cull_start": (int, float), "cull_end": (int, float),
    "pattern": str,
    # 补登: build_scene.py 1058行实际读取 gr.get("pitch")(光伏板倾斜),
    # 此前漏登导致已验证模板(如 smart_agri 光伏阵列)误报未知字段
    "pitch": (int, float),
    # 补登: build_scene.py 1019~1031行实际支持 pattern=="circle" 圆环布局,
    # 读取 count/radius/center/face_center/yaw_offset/z_offset 六字段,
    # 此前漏登导致含圆环阵列(如北方麦田香蒲环)的场景误报未知字段
    "count": int,
    "radius": (int, float),
    "center": list,
    "face_center": bool,
    "yaw_offset": (int, float),
    "z_offset": (int, float),
    # 补登: build_scene.py 1114行实际读取 gr.get("snap_to_ground")(逐实例地形贴地),
    # 为 True 时调用 get_terrain_z() 查询地形表面Z使实例在山谷/山丘自动跟随,
    # 此前漏登导致含贴地植被(松树/香蒲)的场景误报未知字段
    "snap_to_ground": bool,
}

# lighting 子对象
LIGHT_SUB_FIELDS = {
    "location": list, "rotation": list,
    "intensity": (int, float), "color": list,
    "cast_shadows": bool, "density": (int, float),
    "fog_density": (int, float), "fog_color": list,
}

# sky_atmosphere 专有字段 (build_scene.py setup_lighting 读取, 不同于其他光源)
SKY_ATMOSPHERE_FIELDS = {
    "location": list,
    "render_in_main_pass": bool,
    "sky_luminance_factor": list,
    "multi_scattering_factor": (int, float),
}

# top-level rivers[] 河流 (模块4: 与 height_pattern.rivers 共用字段, 增加 width_end_m/waterfalls; 模块5新增: flow_speed)
TOP_RIVER_FIELDS = {
    "points": list, "width_m": (int, float), "material_path": str,
    "bed_depth_m": (int, float), "profile": str,
    "width_end_m": (int, float), "waterfalls": list,
    "flow_speed": (int, float),
}

# waterfalls[] 瀑布点
WATERFALL_FIELDS = {
    "t": (int, float), "drop_m": (int, float), "mesh_path": str,
}

# crop_field.field 子字段
CROP_FIELD_FIELDS = {
    "origin": list, "size_m": list, "row_spacing_m": (int, float),
    "plant_spacing_m": (int, float), "row_direction_deg": (int, float),
    "jitter": (int, float), "snap_to_ground": bool,
    "scale_min": (int, float, list), "scale_max": (int, float, list),
    "random_yaw": bool,
}

# village.village 子字段
VILLAGE_FIELDS = {
    "center": list, "house_count": int, "layout": str,
    "house_assets": list, "radius_m": (int, float),
    "min_distance_m": (int, float), "street_direction_deg": (int, float),
    "street_spacing_m": (int, float), "house_spacing_m": (int, float),
    "snap_to_ground": bool, "random_yaw": bool,
    "yaw_range": list, "scale_min": (int, float, list),
    "scale_max": (int, float, list), "seed": (int, float),
}

# ===========================================================================
# 必填字段: 缺少时报 error (而非 warning)
# ===========================================================================

REQUIRED = {
    "scene": ["target_level"],
    # landscape 新增 grass/height_pattern 为必填 — 缺失会导致灰色地形和完全平坦
    "landscape": ["material", "section_size_quads", "num_subsections",
                  "component_count_x", "component_count_y",
                  "grass", "height_pattern"],
    "layer": ["info", "weight"],
    "placement": ["type"],
    "height_pattern": ["type"],
    "weight_pattern": ["pattern"],
    # 新增: lighting/weather 为顶层必填 — 缺失会导致场景全黑无云
    "lighting": ["directional_light", "sky_light", "sky_atmosphere"],
    "weather": ["volumetric_clouds"],
}

# ===========================================================================
# 枚举值: 字段值必须在指定集合内
# ===========================================================================

ENUM_VALUES = {
    "height_pattern.type": {"flat", "ridge", "hill", "noise", "hill_ridge", "features",
                            "terraced", "karst", "gully"},
    "weight_pattern.pattern": {"uniform", "height_based", "slope_based", "region",
                               "multi_region", "noise_based", "aspect_based", "snow_line"},
    # 补齐 build_scene.py 实际支持的 type: "static"(缺省)与"blueprint"(spawn_blueprint, 1096行);
    # 此前漏登导致房屋蓝图类场景(如 smart_agri)误报无效值
    # static_grid: 逐个 StaticMeshActor 放置(非HISM), 解决 HISM 树木材质 WorldPosition
    #   解析为组件原点导致顶点色风动遮罩失效→整树旋转的问题, 与手动拖入编辑器效果一致
    "placement.type": {"group", "instanced_grid", "instances", "static", "static_grid", "blueprint", "crop_field", "village"},
}

# ===========================================================================
# 类型检查工具
# ===========================================================================

def check_type(value, expected):
    """检查 value 是否匹配 expected 类型描述

    expected 可以是:
      - type 对象 (str, int, float, list, dict, bool)
      - tuple of types (满足任一即可, 如 (int, float) 表示 int 或 float)
    返回 True=匹配, False=不匹配
    """
    # bool 是 int 的子类, 需特殊处理: 当期望 int 时不接受 bool
    if expected is int and isinstance(value, bool):
        return False
    if isinstance(expected, tuple):
        return any(check_type(value, t) for t in expected)
    return isinstance(value, expected)


def type_name(expected):
    """返回类型的可读名称, 用于报错信息"""
    if isinstance(expected, tuple):
        return " | ".join(t.__name__ for t in expected)
    return expected.__name__


# ===========================================================================
# P1-2: 语义一致性校验 — 检测地形/水系/图层引用的逻辑矛盾
# 语义规则只产生 warning（不阻塞流水线），提示用户审查潜在的不一致
# ===========================================================================

# 语义规则1: flat 地形但描述含山丘关键词 → 可能 terrain_type 判断有误
_HILL_KEYWORDS = ["山", "hill", "坡", "mountain", "峰", "peak", "ridge", "脊", "高原"]


def validate_semantic(scene):
    """语义一致性校验 — 检测地形/水系/图层引用的逻辑矛盾。

    语义规则只产生 warning（不阻塞流水线），提示用户审查潜在的不一致。
    用户确认意图与 JSON 相符时可忽略这些 warning。

    规则:
    1. 地形-描述不匹配: height_pattern.type=flat 但 scene.description 含山丘关键词
    2. 水系不完整: height_pattern 含 water 但无 rivers（静水池可忽略）
    3. 植被图层引用未定义: grass/wheat 的 layer_name 不在 layers[].info 中定义

    Args:
        scene: 场景 JSON 字典

    Returns:
        语义 warning 列表（空=无语义矛盾）
    """
    warnings = []
    # 注意: JSON 中 landscape / height_pattern 可能为 null (而非缺失),
    # .get(key, default) 只在 key 缺失时返回 default, 值为 None 时仍返回 None
    # → 后续 .get() 会抛 'NoneType' 无属性 'get' (LLM 生成 "landscape": null 即触发)。
    # 用 or {} 让 null/缺失 统一回退为空字典, 后续所有 .get(...) 安全。
    ls = scene.get("landscape") or {}
    hp = ls.get("height_pattern") or {}
    hp_type = hp.get("type", "")
    # 同理: scene.scene / description 可能为 null, 一并判空避免 'NoneType' 无属性
    desc = ((scene.get("scene") or {}).get("description") or "").lower()

    # 规则1: 地形-描述不匹配 — flat 地形但场景描述含山丘关键词
    if hp_type == "flat":
        for kw in _HILL_KEYWORDS:
            if kw in desc:
                warnings.append(
                    "语义: height_pattern.type=flat 但描述含 '%s'，考虑改为 hills/mountains" % kw
                )
                break

    # 规则2: 水系不完整 — 有 water 配置但无 rivers（静水池可忽略此警告）
    if hp.get("water") and not hp.get("rivers"):
        warnings.append("语义: height_pattern 含 water 但无 rivers，若为静水池可忽略")

    # 规则3: 植被图层引用校验 — 已移除(假阳性)
    # 原逻辑: 将 grass/wheat.layer_name 与 layers[].info 路径末尾名做匹配,
    # 但 layer_name 是材质 GrassOutput 逻辑名(如 "Grass", 见 LandscapeHelper.cpp:3439),
    # 而 layers[].info 路径末尾名是 LayerInfo 资产名(如 "L_Grass_LayerInfo" → "L_Grass"),
    # 两者命名体系不同, 永远不匹配 → 产生假阳性警告。
    # 真正的图层-植被绑定关系由 C++ 材质 GrassOutput 节点运行时解析, JSON 层无法校验。

    return warnings


# ===========================================================================
# 校验核心: 遍历 JSON 结构, 检查字段名/类型/必填/枚举
# ===========================================================================

def validate_section(data, fields, path, errors, warnings):
    """校验单个分区: 检查未知字段 + 类型不匹配

    data: dict 分区数据
    fields: dict 合法字段注册表
    path: str 当前路径 (如 "scene" / "landscape.layers[0]")
    errors: list 错误列表
    warnings: list 警告列表
    """
    for key, val in data.items():
        if key == "_note":
            continue
        if key not in fields:
            errors.append("%s.%s: 未知字段 '%s' (可能拼错, build_scene.py 将忽略)" % (path, key, key))
            continue
        exp = fields[key]
        if not check_type(val, exp):
            errors.append("%s.%s: 类型错误, 期望 %s 实际 %s" % (path, key, type_name(exp), type(val).__name__))


def validate_required(data, req_list, path, errors):
    """检查必填字段是否缺失"""
    for field in req_list:
        if field not in data:
            errors.append("%s: 缺少必填字段 '%s'" % (path, field))


def validate_enum(data, field, enum_key, path, errors):
    """检查枚举字段值是否合法"""
    val = data.get(field)
    if val is not None and val not in ENUM_VALUES[enum_key]:
        errors.append("%s.%s: 无效值 '%s', 应为 %s 之一" % (path, field, val, sorted(ENUM_VALUES[enum_key])))


def validate_scene(scene):
    """校验完整场景 JSON, 返回 (errors, warnings)"""
    errors = []
    warnings = []

    # 顶层键检查
    for key in scene:
        if key not in TOP_KEYS:
            errors.append("顶层: 未知键 '%s', 合法键: %s" % (key, sorted(TOP_KEYS)))

    # scene
    s = scene.get("scene", {})
    if s:
        validate_section(s, SCENE_FIELDS, "scene", errors, warnings)
        validate_required(s, REQUIRED["scene"], "scene", errors)

    # landscape
    ls = scene.get("landscape", {})
    if ls:
        validate_section(ls, LANDSCAPE_FIELDS, "landscape", errors, warnings)
        validate_required(ls, REQUIRED["landscape"], "landscape", errors)

        # layers[]
        for i, layer in enumerate(ls.get("layers", [])):
            p = "landscape.layers[%d]" % i
            validate_section(layer, LAYER_FIELDS, p, errors, warnings)
            validate_required(layer, REQUIRED["layer"], p, errors)
            # weight 范围检查 (0~1)
            w = layer.get("weight")
            if w is not None and isinstance(w, (int, float)) and not (0 <= w <= 1):
                warnings.append("%s.weight: 值 %s 超出 0~1 范围" % (p, w))
            # weight_pattern
            wp = layer.get("weight_pattern")
            if wp:
                wp_path = p + ".weight_pattern"
                validate_section(wp, WP_FIELDS, wp_path, errors, warnings)
                validate_required(wp, REQUIRED["weight_pattern"], wp_path, errors)
                validate_enum(wp, "pattern", "weight_pattern.pattern", wp_path, errors)

        # grass — 必填字段, 缺失/null/空字典均报 error (防止 LLM 删除字段绕过校验)
        # 原先用 if g: 守卫, g 为 None/{} 时静默跳过, LLM 删除 grass 即可让错误归零
        g = ls.get("grass")
        if g is None:
            errors.append("landscape.grass: 必填字段缺失或为 null — "
                          "缺失会导致 build_scene.py 无草地材质, 产出灰色地形")
        elif not isinstance(g, dict):
            errors.append("landscape.grass: 类型错误, 期望 dict 实际 %s" % type(g).__name__)
        elif not g:
            errors.append("landscape.grass: 必填字段为空字典 {} — "
                          "请填充 grass_type/grass_mesh/layer_name/density 等内容")
        else:
            validate_section(g, GRASS_FIELDS, "landscape.grass", errors, warnings)
            for i, gv in enumerate(g.get("grass_varieties", [])):
                validate_section(gv, HP_VARIETY_FIELDS, "landscape.grass.grass_varieties[%d]" % i, errors, warnings)

        # wheat
        w = ls.get("wheat")
        if w:
            validate_section(w, WHEAT_FIELDS, "landscape.wheat", errors, warnings)

        # height_pattern — 必填字段, 缺失/null/空字典均报 error (防止 LLM 删除字段绕过校验)
        # 原先用 if hp: 守卫, hp 为 None/{} 时静默跳过, LLM 删除即让错误归零
        # 缺失会导致 build_scene.py 传空字符串给 C++ 插件, 产出完全平坦地形
        hp = ls.get("height_pattern")
        if hp is None:
            errors.append("landscape.height_pattern: 必填字段缺失或为 null — "
                          "缺失会导致 build_scene.py 传空字符串给 C++ 插件, 产出完全平坦地形")
        elif not isinstance(hp, dict):
            errors.append("landscape.height_pattern: 类型错误, 期望 dict 实际 %s" % type(hp).__name__)
        elif not hp:
            errors.append("landscape.height_pattern: 必填字段为空字典 {} — "
                          "请填充 type/hills/valleys 等内容以生成地形起伏")
        else:
            validate_section(hp, HP_FIELDS, "landscape.height_pattern", errors, warnings)
            validate_required(hp, REQUIRED["height_pattern"], "landscape.height_pattern", errors)
            validate_enum(hp, "type", "height_pattern.type", "landscape.height_pattern", errors)
            # 子列表校验
            for i, h in enumerate(hp.get("hills", [])):
                validate_section(h, HP_HILL_FIELDS, "height_pattern.hills[%d]" % i, errors, warnings)
            for i, v in enumerate(hp.get("valleys", [])):
                validate_section(v, HP_VALLEY_FIELDS, "height_pattern.valleys[%d]" % i, errors, warnings)
            for i, r in enumerate(hp.get("ridges", [])):
                validate_section(r, HP_RIDGE_FIELDS, "height_pattern.ridges[%d]" % i, errors, warnings)
            wat = hp.get("water")
            if wat:
                validate_section(wat, HP_WATER_FIELDS, "height_pattern.water", errors, warnings)
            for i, rv in enumerate(hp.get("rivers", [])):
                validate_section(rv, HP_RIVER_FIELDS, "height_pattern.rivers[%d]" % i, errors, warnings)
            for i, rd in enumerate(hp.get("roads", [])):
                validate_section(rd, HP_ROAD_FIELDS, "height_pattern.roads[%d]" % i, errors, warnings)
            for i, bd in enumerate(hp.get("buildings", [])):
                validate_section(bd, HP_BUILDING_FIELDS, "height_pattern.buildings[%d]" % i, errors, warnings)
            for i, sc in enumerate(hp.get("scatter", [])):
                validate_section(sc, HP_SCATTER_FIELDS, "height_pattern.scatter[%d]" % i, errors, warnings)
            for i, gv in enumerate(hp.get("grass_varieties", [])):
                validate_section(gv, HP_VARIETY_FIELDS, "height_pattern.grass_varieties[%d]" % i, errors, warnings)
            for i, wv in enumerate(hp.get("wheat_varieties", [])):
                validate_section(wv, HP_VARIETY_FIELDS, "height_pattern.wheat_varieties[%d]" % i, errors, warnings)
            no = hp.get("noise_overlay")
            if no:
                validate_section(no, HP_NOISE_FIELDS, "height_pattern.noise_overlay", errors, warnings)

    # ground
    gnd = scene.get("ground")
    if gnd:
        validate_section(gnd, GROUND_FIELDS, "ground", errors, warnings)

    # placements[]
    for i, p in enumerate(scene.get("placements", [])):
        # 跳过仅含 _note 的注释条目 (模板中用作分节注释, build_scene.py 忽略此类条目)
        if set(p.keys()) <= {"_note"}:
            continue
        p_path = "placements[%d]" % i
        validate_section(p, PLACEMENT_FIELDS, p_path, errors, warnings)
        validate_required(p, REQUIRED["placement"], p_path, errors)
        validate_enum(p, "type", "placement.type", p_path, errors)
        # grid 校验 (instanced_grid / static_grid 类型均使用 grid 字段生成实例)
        # grid 类型缺失 grid 时, build_scene.py 回退为 [0,0,0] 单实例, 导致电塔/树木挤在原点(地形外)
        grd = p.get("grid")
        _is_grid_type = p.get("type") in ("instanced_grid", "static_grid")
        if grd is None:
            if _is_grid_type:
                errors.append("%s.grid: 缺失或为 null — grid 类型 placement 必须提供 grid (spacing/count)" % p_path)
        elif not isinstance(grd, dict):
            errors.append("%s.grid: 类型错误, 期望 dict 实际 %s" % (p_path, type(grd).__name__))
        elif not grd:
            if _is_grid_type:
                errors.append("%s.grid: 空字典 {} — grid 类型 placement 必须含 spacing/count 等字段" % p_path)
        else:
            validate_section(grd, GRID_FIELDS, p_path + ".grid", errors, warnings)
        # crop_field 子字段校验
        fd = p.get("field")
        if fd:
            validate_section(fd, CROP_FIELD_FIELDS, p_path + ".field", errors, warnings)
        # village 子字段校验
        vd = p.get("village")
        if vd:
            validate_section(vd, VILLAGE_FIELDS, p_path + ".village", errors, warnings)

    # lighting — 顶层必填, 缺失/null/空字典均报 error (防止 LLM 删除字段绕过校验)
    # 原先用 if lt: 守卫, lt 为 None/{} 时静默跳过, 缺失会导致场景全黑无光照
    lt = scene.get("lighting")
    if lt is None:
        errors.append("lighting: 顶层必填字段缺失或为 null — 缺失会导致 build_scene.py 跳过光照, 场景全黑")
    elif not isinstance(lt, dict):
        errors.append("lighting: 类型错误, 期望 dict 实际 %s" % type(lt).__name__)
    elif not lt:
        errors.append("lighting: 顶层必填字段为空字典 {} — 请填充 directional_light/sky_light/sky_atmosphere")
    else:
        # 校验必填子项是否存在 (directional_light/sky_light/sky_atmosphere)
        validate_required(lt, REQUIRED["lighting"], "lighting", errors)
        # sky_atmosphere 有专有字段 (render_in_main_pass 等), 使用独立 schema
        _light_schemas = {
            "directional_light": LIGHT_SUB_FIELDS,
            "sky_light": LIGHT_SUB_FIELDS,
            "sky_atmosphere": SKY_ATMOSPHERE_FIELDS,
            "height_fog": LIGHT_SUB_FIELDS,
        }
        for sub, schema in _light_schemas.items():
            obj = lt.get(sub)
            # 必填子项键缺失已由 validate_required 报告; 此处检查值非 None 时的类型/空字典
            if obj is not None:
                if not isinstance(obj, dict):
                    errors.append("lighting.%s: 类型错误, 期望 dict 实际 %s" % (sub, type(obj).__name__))
                elif obj:
                    validate_section(obj, schema, "lighting." + sub, errors, warnings)
                elif sub in ("directional_light", "sky_light", "sky_atmosphere"):
                    errors.append("lighting.%s: 必填子项为空字典 {}" % sub)
            elif sub in ("directional_light", "sky_light", "sky_atmosphere") and sub in lt:
                errors.append("lighting.%s: 必填子项为 null — 场景将缺%s" % (
                    sub, {"directional_light": "方向光", "sky_light": "天光",
                          "sky_atmosphere": "大气"}.get(sub, "该光源")))

    # weather — 顶层必填, 缺失/null/空字典均报 error (防止 LLM 删除字段绕过校验)
    # 原先用 if we: 守卫, we 为 None/{} 时静默跳过, 缺失会导致场景无体积云
    we = scene.get("weather")
    if we is None:
        errors.append("weather: 顶层必填字段缺失或为 null — 缺失会导致 build_scene.py 跳过天气, 无体积云")
    elif not isinstance(we, dict):
        errors.append("weather: 类型错误, 期望 dict 实际 %s" % type(we).__name__)
    elif not we:
        errors.append("weather: 顶层必填字段为空字典 {} — 请填充 volumetric_clouds")
    else:
        validate_required(we, REQUIRED["weather"], "weather", errors)
        vc = we.get("volumetric_clouds")
        if vc is not None:
            if not isinstance(vc, dict):
                errors.append("weather.volumetric_clouds: 类型错误, 期望 dict 实际 %s" % type(vc).__name__)
            elif vc:
                validate_section(vc, LIGHT_SUB_FIELDS, "weather.volumetric_clouds", errors, warnings)
            else:
                errors.append("weather.volumetric_clouds: 必填子项为空字典 {}")
        elif "volumetric_clouds" in we:
            errors.append("weather.volumetric_clouds: 必填子项为 null")

    # top-level rivers[] (模块4: 与 height_pattern.rivers 分开, 支持 width_end_m/waterfalls)
    for i, rv in enumerate(scene.get("rivers", [])):
        rv_path = "rivers[%d]" % i
        validate_section(rv, TOP_RIVER_FIELDS, rv_path, errors, warnings)
        for j, wf in enumerate(rv.get("waterfalls", [])):
            validate_section(wf, WATERFALL_FIELDS, "%s.waterfalls[%d]" % (rv_path, j), errors, warnings)

    # P1-2: 语义一致性校验 — 检测地形/水系/图层引用的逻辑矛盾(只产生 warning)
    warnings.extend(validate_semantic(scene))

    return errors, warnings


# ===========================================================================
# 入口: 解析命令行参数, 加载 JSON, 校验, 输出结果
# ===========================================================================

def main():
    args = sys.argv[1:]
    if not args:
        print("用法: python validate_scene_json.py <场景.json>")
        sys.exit(1)

    scene_path = args[0]
    if not os.path.isfile(scene_path):
        print("文件不存在: " + scene_path)
        sys.exit(1)

    # 加载 JSON
    try:
        with open(scene_path, "r", encoding="utf-8") as f:
            scene = json.load(f)
    except json.JSONDecodeError as e:
        print("JSON 解析失败: %s (行 %d 列 %d)" % (e.msg, e.lineno, e.colno))
        sys.exit(1)

    # 执行校验
    errors, warnings = validate_scene(scene)

    # 输出结果
    if warnings:
        print("--- 警告 (%d) ---" % len(warnings))
        for w in warnings:
            print("  [WARN] " + w)

    if errors:
        print("--- 错误 (%d) ---" % len(errors))
        for e in errors:
            print("  [ERROR] " + e)
        print("\n校验失败: %d 个错误" % len(errors))
        sys.exit(1)
    else:
        print("校验通过: 字段名/类型/必填/枚举均合法")
        if warnings:
            print("(有 %d 个警告)" % len(warnings))
        sys.exit(0)


if __name__ == "__main__":
    main()
