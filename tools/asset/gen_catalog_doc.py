# -*- coding: utf-8 -*-
# ============================================================================
# gen_catalog_doc.py - 资产清单文档生成器(纯Python, 不依赖UE)
# ============================================================================
# 功能: 读取 asset_catalog.json, 生成按类别组织的可读 Markdown 清单
# 字段: 资产路径/类型/尺寸/尺寸单位/朝向/原点位置/Z偏移/材质/缩放建议
# 用法: python gen_catalog_doc.py
# 输出: asset_catalog.md
# ============================================================================

import json
import os
from collections import defaultdict, OrderedDict

# 输入: 引擎清查生成的JSON目录
CATALOG_JSON = "c:/Users/25868/Desktop/UE5/MapForgeTest/asset_catalog.json"
# 输出: 可读Markdown清单
OUTPUT_MD = "c:/Users/25868/Desktop/UE5/MapForgeTest/asset_catalog.md"


def fmt_dims(entry):
    """格式化尺寸: 返回 'XxYxZ cm' 字符串"""
    d = entry.get("dimensions_xyz")
    if not d:
        return "-"
    return "%.1f x %.1f x %.1f" % (d[0], d[1], d[2])


def fmt_unit(entry):
    """格式化尺寸单位推测(注意: centimeters 包含 meters 子串, 必须用 startswith 精确匹配)"""
    u = entry.get("likely_unit", "-")
    if u == "-":
        return "-"
    # 仅当以 meters 开头才是米制(排除 centimeters)
    if u.startswith("meters"):
        return "米(需x100)"
    if u.startswith("centimeters"):
        return "厘米(正确)"
    return u


def fmt_adjust(entry):
    """根据清查数据生成'接近真实世界'的调整建议"""
    if "dimensions_xyz" not in entry:
        return "-"
    # 空网格(无几何体)优先返回不可用, 避免误报缩放建议
    if entry.get("empty_mesh"):
        return "不可用(无几何体)"
    parts = []
    # 缩放建议
    s = entry.get("scale_to_cm", 1.0)
    if s and s != 1.0:
        parts.append("缩放x%.0f" % s)
    # 朝向修复
    ori = entry.get("orientation", "")
    if "standing_tall" in ori:
        parts.append("检查朝向(竖立)")
    # 原点修复
    oz = entry.get("origin_z", "")
    if "center" in oz:
        zo = entry.get("z_offset_needed", 0)
        if zo:
            parts.append("Z+%.0f(原点居中)" % zo)
        else:
            parts.append("原点居中需上移")
    elif "top" in oz:
        parts.append("原点在顶需下移")
    if not parts:
        return "可直接使用"
    return "; ".join(parts)


def fmt_collision(entry):
    """格式化碰撞检测结果: 返回简洁的碰撞状态描述

    碰撞字段由 probe_collision4/6.py 在 UE5 引擎内探测,
    经 sync_collision_to_catalog.py 同步到 asset_catalog.json。

    StaticMesh 碰撞字段: has_collision, collision_type, simple_collision_count,
                         element_detail, uses_complex_collision, player_blocked, bullet_hits
    Blueprint 碰撞字段:  has_collision, collision_type, smc_count,
                         mesh_with_asset_count, has_simple_collision, has_complex_collision,
                         player_blocked, bullet_hits

    返回值含义:
    - ✓阻挡(N): 玩家会被阻挡, 含 N 个简化碰撞体(球/盒/凸包/胶囊)
    - △复杂:    玩家可穿透, 但子弹/射线会命中(仅复杂逐面碰撞, 无简化体)
    - ✗无碰撞:  无任何碰撞体, 玩家和子弹均穿透
    - 未检测:   该资产未被碰撞探测脚本覆盖(非起降场使用资产)
    """
    col = entry.get("collision")
    if not col:
        return "未检测"
    if not col.get("has_collision", False):
        return "✗无碰撞"
    # 蓝图: 有 smc_count 字段(静态网格组件总数)
    if "smc_count" in col:
        if col.get("player_blocked", False):
            return "✓阻挡(%d组件)" % col.get("smc_count", 0)
        if col.get("bullet_hits", False):
            return "△复杂(玩家穿透)"
        return "✗无碰撞"
    # StaticMesh: 有 simple_collision_count 字段(简化碰撞体数量)
    if "simple_collision_count" in col:
        sc = col.get("simple_collision_count", 0)
        if col.get("player_blocked", False):
            return "✓阻挡(简化%d)" % sc
        if col.get("bullet_hits", False):
            return "△复杂(玩家穿透)"
        return "✗无碰撞"
    return "未知"


def short_path(path):
    """缩短路径便于显示: 去掉 /Game/ 前缀"""
    if path.startswith("/Game/"):
        return path[6:]
    return path


# 类别中文名映射与排序(按场景搭建优先级)
CATEGORY_CN = OrderedDict([
    ("vegetation_tree", "树木植被"),
    ("vegetation_crop", "农作物"),
    ("building", "建筑房屋"),
    ("heliport", "停机坪/直升机"),
    ("communication_tower", "通信塔"),
    ("high_voltage_tower", "高压电塔"),
    ("solar_panel", "太阳能板"),
    ("fence", "围栏"),
    ("ground", "地面/地形"),
    ("blueprint", "蓝图"),
    ("material", "材质"),
    ("texture", "贴图"),
    ("other", "其他"),
])


def main():
    with open(CATALOG_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    assets = data.get("assets", [])
    stats = data.get("stats", {})

    # 按类别分组
    by_cat = defaultdict(list)
    for a in assets:
        by_cat[a.get("category", "other")].append(a)

    # 每个类别内按子文件夹再分组, 便于浏览
    lines = []
    w = lines.append  # 写行快捷函数

    w("# 资产清单 - Content 目录全量清查")
    w("")
    w("> 本清单由 `asset_audit.py` 在 UE5.8 引擎内脚本化读取生成, ")
    w("> 已捕获每个资产的包围盒尺寸、尺寸单位、朝向、原点位置、材质等详细信息。")
    w("> 字段均为引擎实测值, 可直接据此调整到接近真实世界的参数后使用。")
    w("")
    w("---")
    w("")
    w("## 一、概览统计")
    w("")
    w("- **资产总数**: %d" % stats.get("total", len(assets)))
    w("- **成功加载**: %d" % stats.get("loaded", 0))
    w("- **加载失败**: %d" % stats.get("failed", 0))
    w("")

    w("### 按资产类型(按数量降序)")
    w("")
    w("| 类型 | 数量 |")
    w("|------|------|")
    for cls, cnt in sorted(stats.get("by_class", {}).items(), key=lambda x: -x[1]):
        w("| %s | %d |" % (cls, cnt))
    w("")

    w("### 按用途类别(按数量降序)")
    w("")
    w("| 类别 | 数量 |")
    w("|------|------|")
    for cat, cnt in sorted(stats.get("by_category", {}).items(), key=lambda x: -x[1]):
        cn = CATEGORY_CN.get(cat, cat)
        w("| %s (%s) | %d |" % (cat, cn, cnt))
    w("")

    # 碰撞检测汇总(仅统计已检测的资产)
    w("### 碰撞检测状态(已探测资产)")
    w("")
    w("> 仅覆盖智慧农林无人机起降场使用的 67 个资产(65 静态网格 + 2 蓝图)。")
    w("> 探测脚本: `probe_collision4.py`(StaticMesh) + `probe_collision6.py`(Blueprint)")
    w("")
    checked = [a for a in assets if a.get("collision")]
    blocked = [a for a in checked if a["collision"].get("player_blocked", False)]
    complex_only = [a for a in checked if not a["collision"].get("player_blocked", False)
                    and a["collision"].get("bullet_hits", False)]
    no_col = [a for a in checked if not a["collision"].get("has_collision", False)]
    w("| 碰撞状态 | 数量 | 含义 |")
    w("|----------|------|------|")
    w("| ✓玩家阻挡 | %d | 含简化碰撞体, 玩家无法穿透 |" % len(blocked))
    w("| △仅复杂碰撞 | %d | 无简化体, 玩家穿透但子弹命中 |" % len(complex_only))
    w("| ✗无碰撞 | %d | 无任何碰撞体, 玩家和子弹均穿透 |" % len(no_col))
    w("| 合计已检测 | %d | 占总资产 %.2f%% |" % (len(checked), 100.0 * len(checked) / max(len(assets), 1)))
    w("")

    w("---")
    w("")
    w("## 二、字段说明(使用指南)")
    w("")
    w("- **尺寸单位**: UE 默认 `1 单位 = 1 厘米`。若资产最大尺寸 <50, 多为米制, 需 x100 缩放。")
    w("- **dimensions_xyz**: 包围盒 长x宽x高(单位:厘米)。")
    w("- **朝向**: `standing_tall`=竖立(可能需旋转放平); `flat_horizontal`=平躺; `cube_like`=立方; `mixed`=混合。")
    w("- **原点位置**: `bottom`=原点在底(可直接放地面); `center`=原点居中(需上移半个高度); `top`=原点在顶。")
    w("- **Z偏移**: 原点居中时需要上移的高度(厘米)。")
    w("- **调整建议**: 综合上述数据, 给出接近真实世界参数的缩放/旋转/Z偏移操作。")
    w("")
    w("---")
    w("")

    # 每个类别的详细清单
    w("## 三、分类详细清单")
    w("")

    for cat_key, cat_cn in CATEGORY_CN.items():
        items = by_cat.get(cat_key, [])
        if not items:
            continue
        w("### %s — %s (%d 个)" % (cat_cn, cat_key, len(items)))
        w("")

        # 区分: 有物理属性的StaticMesh用完整表格; 材质/贴图用紧凑列表; 蓝图用组件表
        meshes = [a for a in items if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]
        bps = [a for a in items if a.get("class") == "Blueprint"]
        others = [a for a in items if a not in meshes and a not in bps]

        # StaticMesh 完整属性表
        if meshes:
            w("#### 静态网格 (有物理尺寸)")
            w("")
            w("| 资产路径 | 尺寸(长x宽x高 cm) | 最大尺寸 | 单位 | 朝向 | 原点位置 | Z偏移 | 材质数 | 碰撞 | 调整建议 |")
            w("|----------|---------------------|----------|------|------|----------|-------|--------|------|----------|")
            for a in sorted(meshes, key=lambda x: x.get("path", "")):
                zo = a.get("z_offset_needed", "")
                w("| %s | %s | %.1f | %s | %s | %s | %s | %d | %s | %s |" % (
                    short_path(a.get("path", "")),
                    fmt_dims(a),
                    a.get("max_dimension", 0),
                    fmt_unit(a),
                    a.get("orientation", "-").split(" (")[0],
                    a.get("origin_z", "-").split(" (")[0],
                    ("%.0f" % zo) if zo else "-",
                    a.get("material_count", 0),
                    fmt_collision(a),
                    fmt_adjust(a),
                ))
            w("")

        # 蓝图表
        if bps:
            w("#### 蓝图")
            w("")
            w("| 资产路径 | 生成类 | 含网格组件 | 组件数 | 碰撞 | 备注 |")
            w("|----------|--------|------------|--------|------|------|")
            for a in sorted(bps, key=lambda x: x.get("path", "")):
                comp = a.get("components", [])
                w("| %s | %s | %s | %d | %s | %s |" % (
                    short_path(a.get("path", "")),
                    a.get("generated_class", "-"),
                    "是" if a.get("has_mesh_component") else "否",
                    len(comp),
                    fmt_collision(a),
                    a.get("bp_component_error", "-"),
                ))
            w("")

        # 材质/贴图等紧凑列表
        if others:
            w("#### 其他(材质/贴图等)")
            w("")
            w("| 资产路径 | 类型 | 额外信息 |")
            w("|----------|------|----------|")
            for a in sorted(others, key=lambda x: x.get("path", "")):
                extra = ""
                if a.get("shading_model"):
                    extra = "着色:%s" % a.get("shading_model", "").split(" (")[0]
                elif a.get("texture_size"):
                    ts = a.get("texture_size")
                    extra = "尺寸:%dx%d" % (ts[0], ts[1])
                w("| %s | %s | %s |" % (
                    short_path(a.get("path", "")),
                    a.get("class", "-"),
                    extra,
                ))
            w("")

        w("")
        w("---")
        w("")

    # 需要修复的资产汇总
    w("## 四、需要修复的资产汇总")
    w("")
    w("### 1. 米制单位(需 x100 缩放)")
    w("> 这些资产最大尺寸 <50, 推测为米制, 放置时需 Scale x100 才接近真实大小。")
    w("")
    w("| 资产路径 | 当前尺寸 | 最大尺寸 |")
    w("|----------|----------|----------|")
    meter_assets = [a for a in assets if a.get("likely_unit", "").startswith("meters")]
    for a in sorted(meter_assets, key=lambda x: x.get("path", "")):
        w("| %s | %s | %.2f |" % (
            short_path(a.get("path", "")),
            fmt_dims(a),
            a.get("max_dimension", 0),
        ))
    w("")

    w("### 2. 原点居中(需上移 Z 偏移)")
    w("> 原点在中心, 直接放地面会半埋地下, 需上移半个高度。")
    w("")
    w("| 资产路径 | 尺寸(cm) | Z偏移建议 |")
    w("|----------|----------|-----------|")
    center_assets = [a for a in assets if "center" in a.get("origin_z", "")]
    for a in sorted(center_assets, key=lambda x: x.get("path", "")):
        w("| %s | %s | %.0f |" % (
            short_path(a.get("path", "")),
            fmt_dims(a),
            a.get("z_offset_needed", 0),
        ))
    w("")

    w("### 3. 竖立朝向(可能需旋转放平)")
    w("> 高度远大于长宽, 可能本应平躺却竖着, 需检查并旋转(如停机坪)。")
    w("")
    w("| 资产路径 | 尺寸(长x宽x高 cm) |")
    w("|----------|---------------------|")
    tall_assets = [a for a in assets if "standing_tall" in a.get("orientation", "")]
    for a in sorted(tall_assets, key=lambda x: x.get("path", "")):
        w("| %s | %s |" % (
            short_path(a.get("path", "")),
            fmt_dims(a),
        ))
    w("")

    w("### 4. 碰撞检测详情(智慧农林无人机起降场资产)")
    w("> 已探测 67 个资产(65 静态网格 + 2 蓝图), 碰撞字段已同步回 asset_catalog.json。")
    w("> ✓=玩家阻挡 | △=仅复杂碰撞(玩家穿透,子弹命中) | ✗=无碰撞")
    w("")
    w("| 资产路径 | 类型 | 碰撞状态 | 简化体数 | 玩家阻挡 | 子弹命中 |")
    w("|----------|------|----------|----------|----------|----------|")
    col_assets = [a for a in assets if a.get("collision")]
    for a in sorted(col_assets, key=lambda x: x.get("path", "")):
        col = a["collision"]
        # 判断碰撞状态符号
        if not col.get("has_collision", False):
            status = "✗无碰撞"
        elif col.get("player_blocked", False):
            status = "✓阻挡"
        elif col.get("bullet_hits", False):
            status = "△仅复杂"
        else:
            status = "✗无碰撞"
        # 简化体数: StaticMesh 用 simple_collision_count, 蓝图用组件数
        sc = col.get("simple_collision_count", col.get("smc_count", "-"))
        w("| %s | %s | %s | %s | %s | %s |" % (
            short_path(a.get("path", "")),
            a.get("class", "-"),
            status,
            sc,
            "是" if col.get("player_blocked", False) else "否",
            "是" if col.get("bullet_hits", False) else "否",
        ))
    w("")

    w("---")
    w("")
    w("## 五、场景已用资产清单(智慧农林无人机起降场)")
    w("")
    w("以下资产已在 `smart_agri_drone_field.json` 中使用, 并已按真实世界参数调整:")
    w("")
    used = [
        ("SM_FirTree_01", "vegetation_tree", "919x929x3095 cm", "可直接使用(树高约31m)"),
        ("SM_SmallFir_01", "vegetation_tree", "222x246x644 cm", "小树约6.4m, 可直接使用"),
        ("停机坪 Object_*", "heliport", "原为竖立(X-Z平面,Y=0)", "旋转[0,0,-90](roll=-90正向平躺)+缩放0.01(3728m→37m)"),
        ("小麦 wheat", "vegetation_crop", "原米制(米)", "缩放0.04~0.06 (x100后)"),
        ("地面 SM_wood", "ground", "木地板材质", "材质覆盖为 M_ground_dirt_grass_master"),
        ("建筑蓝图", "building", "原点居中", "Z自动修正(get_actor_bounds)"),
    ]
    w("| 资产 | 类别 | 原始尺寸/问题 | 调整方案 |")
    w("|------|------|----------------|----------|")
    for name, cat, prob, fix in used:
        w("| %s | %s | %s | %s |" % (name, cat, prob, fix))
    w("")

    w("---")
    w("")
    w("> 清单生成完毕。共收录 %d 个资产。" % len(assets))
    w("> 数据来源: UE5.8 引擎内 `EditorAssetLibrary.load_asset()` + `get_bounds()` 实测。")

    # 写入文件
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("文档已生成: %s" % OUTPUT_MD)
    print("总行数: %d" % len(lines))
    print("资产数: %d" % len(assets))
    print("米制单位需修复: %d" % len(meter_assets))
    print("原点居中需修复: %d" % len(center_assets))
    print("竖立朝向需检查: %d" % len(tall_assets))
    print("碰撞检测已探测: %d (玩家阻挡=%d, 仅复杂=%d, 无碰撞=%d)" % (
        len(col_assets), len(blocked), len(complex_only), len(no_col)))


if __name__ == "__main__":
    main()
