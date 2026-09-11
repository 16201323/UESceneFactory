# -*- coding: utf-8 -*-
# ============================================================================
# audit_catalog.py - 资产清单完整性与正确性校验脚本
# ============================================================================
# 功能: 对 asset_catalog.json 做全面校验, 输出问题清单
#   完整性: 总数/必填字段缺失/空值/截断记录
#   正确性: 数值一致性(dimensions=extent*2等)/单位检测误报/
#           Z偏移计算错误/朝向分类合理性/材质列表
# 用法: python audit_catalog.py  (纯Python, 无需UE)
# ============================================================================

import json
import sys
from collections import Counter

CATALOG_PATH = "c:/Users/25868/Desktop/UE5/MapForgeTest/asset_catalog.json"
REPORT_PATH = "c:/Users/25868/Desktop/UE5/MapForgeTest/audit_report.txt"

# StaticMesh 必填字段(有bounds时)
MESH_FIELDS = ["path", "folder", "subfolder", "name", "category", "class",
               "bounds_origin", "bounds_extent", "bounds_min", "bounds_max",
               "dimensions_xyz", "max_dimension", "likely_unit", "scale_to_cm",
               "orientation", "origin_z", "materials", "material_count"]
BASE_FIELDS = ["path", "folder", "subfolder", "name", "category", "class"]


def approx(a, b, eps=0.05):
    """浮点近似比较, 容差eps(处理round误差)"""
    if a is None or b is None:
        return False
    return abs(a - b) <= eps


def main():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assets = data.get("assets", [])
    stats = data.get("stats", {})
    total = len(assets)

    issues = []          # 严重问题
    warnings = []        # 轻微问题/可疑项

    # ========================================================================
    # 一、完整性校验
    # ========================================================================
    missing_base = []       # 缺基础字段
    missing_mesh = []       # StaticMesh缺物理字段
    zero_extent = []         # 全零包围盒(异常)
    null_bounds = []        # bounds字段为None

    mesh_count = 0
    nonmesh_count = 0
    for a in assets:
        cls = a.get("class", "")
        # 基础字段
        for fld in BASE_FIELDS:
            v = a.get(fld)
            if v is None or v == "":
                missing_base.append((a.get("path", "?"), fld))
        if cls == "StaticMesh":
            mesh_count += 1
            has_bounds = "bounds_extent" in a
            if not has_bounds:
                missing_mesh.append((a.get("path", "?"), "bounds_extent(整个bounds块缺失)"))
                continue
            # 全零包围盒检测
            ext = a.get("bounds_extent", [0, 0, 0])
            # 跳过已标注的空网格(不再计为异常)
            if a.get("empty_mesh"):
                continue
            if all(abs(v) < 0.01 for v in ext):
                zero_extent.append(a.get("path", "?"))
            # None值检测
            for fld in MESH_FIELDS:
                if fld in a and a.get(fld) is None:
                    null_bounds.append((a.get("path", "?"), fld))
        else:
            nonmesh_count += 1

    # ========================================================================
    # 二、正确性校验
    # ========================================================================
    dim_mismatch = []       # dimensions != extent*2
    maxdim_mismatch = []    # max_dimension != max(dimensions)
    bounds_math = []        # bounds_min/max != origin ± extent
    zoffset_wrong = []     # z_offset_needed != -z_min (非对称中心原点)
    near_bottom_no_zoffset = []  # near_bottom缺z_offset_needed
    unit_suspect = []       # 单位检测可疑(小物体被判米制)
    orient_conflict = []   # 朝向与尺寸矛盾

    for a in assets:
        if a.get("class") != "StaticMesh":
            continue
        if "bounds_extent" not in a:
            continue
        path = a.get("path", "?")
        ext = a.get("bounds_extent", [0, 0, 0])
        dim = a.get("dimensions_xyz", [0, 0, 0])
        origin = a.get("bounds_origin", [0, 0, 0])
        bmin = a.get("bounds_min", [0, 0, 0])
        bmax = a.get("bounds_max", [0, 0, 0])
        maxd = a.get("max_dimension", 0)

        # 2.1 dimensions == extent * 2
        for i, axis in enumerate("xyz"):
            if not approx(dim[i], ext[i] * 2, 0.1):
                dim_mismatch.append((path, axis, dim[i], ext[i] * 2))
                break

        # 2.2 max_dimension == max(dimensions)
        if not approx(maxd, max(dim), 0.1):
            maxdim_mismatch.append((path, maxd, max(dim)))

        # 2.3 bounds_min = origin - extent, bounds_max = origin + extent
        for i, axis in enumerate("xyz"):
            if not approx(bmin[i], origin[i] - ext[i], 0.1):
                bounds_math.append((path, "min_" + axis, bmin[i], origin[i] - ext[i]))
                break
        else:
            for i, axis in enumerate("xyz"):
                if not approx(bmax[i], origin[i] + ext[i], 0.1):
                    bounds_math.append((path, "max_" + axis, bmax[i], origin[i] + ext[i]))
                    break

        # 2.4 Z偏移: center原点应为 -z_min(而非z_max), 检测非对称
        oz = a.get("origin_z", "")
        if "center" in oz:
            z_min = bmin[2]
            z_max = bmax[2]
            zoff = a.get("z_offset_needed")
            if zoff is None:
                # center但缺z_offset_needed(不该发生)
                zoffset_wrong.append((path, "center缺z_offset_needed", z_min, z_max))
            else:
                # 对称中心: |z_min|==z_max, zoff应=z_max(正确)
                # 非对称: zoff应为-z_min, 若用z_max则错
                if not approx(abs(z_min), z_max, 1.0):
                    # 非对称中心原点, 检查zoff是否=-z_min
                    if not approx(zoff, -z_min, 1.0):
                        zoffset_wrong.append((path, "非对称center: zoff=%s 应为%s" % (zoff, round(-z_min, 2)), z_min, z_max))
        elif "near_bottom" in oz:
            if "z_offset_needed" not in a:
                near_bottom_no_zoffset.append(path)

        # 2.5 单位检测可疑: max_d<50判米制, 但可能是小道具(cm)
        unit = a.get("likely_unit", "")
        # 注意: 用startswith避免"centimeters"含"meters"子串的误匹配
        if unit.startswith("meters") and maxd < 50 and maxd > 0:
            # 可能是真实小物体被误判
            # 启发: 名称含prop/lamp/switch等小物件词更可疑
            n = a.get("name", "").lower()
            small_words = ["lamp", "switch", "knob", "handle", "btn", "button",
                           "prop", "tool", "cup", "mug", "plate", "book", "pen"]
            if any(w in n for w in small_words):
                unit_suspect.append((path, maxd, "名称像小道具但被判米制"))

        # 2.6 朝向与尺寸矛盾
        orient = a.get("orientation", "")
        dx, dy, dz = dim
        if "standing_tall" in orient:
            if not (dz > dx * 2 and dz > dy * 2):
                orient_conflict.append((path, "standing_tall但尺寸不满足", dx, dy, dz))
        elif "flat_horizontal" in orient:
            if not (dx > dz * 3 and dy > dz * 3):
                orient_conflict.append((path, "flat_horizontal但尺寸不满足", dx, dy, dz))

    # ========================================================================
    # 三、输出报告
    # ========================================================================
    lines = []
    def w(s=""):
        lines.append(s)

    w("=" * 70)
    w("资产清单校验报告 (audit_catalog.py)")
    w("=" * 70)
    w()
    w("【一、完整性校验】")
    w("  资产总数: %d  (StaticMesh: %d, 非网格: %d)" % (total, mesh_count, nonmesh_count))
    w("  缺基础字段: %d 条" % len(missing_base))
    w("  StaticMesh缺物理字段: %d 条" % len(missing_mesh))
    w("  全零包围盒(异常): %d 条" % len(zero_extent))
    w("  字段值为None: %d 条" % len(null_bounds))
    w("  near_bottom缺z_offset_needed: %d 条" % len(near_bottom_no_zoffset))
    if missing_base[:10]:
        w("  --缺基础字段示例(前10):")
        for p, fld in missing_base[:10]:
            w("     %s -> 缺%s" % (p, fld))
    if missing_mesh[:10]:
        w("  --StaticMesh缺物理字段示例(前10):")
        for p, fld in missing_mesh[:10]:
            w("     %s -> 缺%s" % (p, fld))
    if zero_extent[:10]:
        w("  --全零包围盒示例(前10):")
        for p in zero_extent[:10]:
            w("     %s" % p)
    if near_bottom_no_zoffset[:10]:
        w("  --near_bottom缺z_offset示例(前10):")
        for p in near_bottom_no_zoffset[:10]:
            w("     %s" % p)
    w()
    w("【二、正确性校验】")
    w("  dimensions≠extent*2: %d 条" % len(dim_mismatch))
    w("  max_dimension≠max(dim): %d 条" % len(maxdim_mismatch))
    w("  bounds_min/max≠origin±extent: %d 条" % len(bounds_math))
    w("  Z偏移计算错误(非对称center): %d 条" % len(zoffset_wrong))
    w("  单位检测可疑(小道具误判米制): %d 条" % len(unit_suspect))
    w("  朝向与尺寸矛盾: %d 条" % len(orient_conflict))
    if dim_mismatch[:10]:
        w("  --dimensions≠extent*2示例(前10):")
        for p, ax, d, e2 in dim_mismatch[:10]:
            w("     %s [%s] dim=%s extent*2=%s" % (p, ax, d, round(e2, 2)))
    if maxdim_mismatch[:10]:
        w("  --max_dimension≠max(dim)示例(前10):")
        for p, md, mx in maxdim_mismatch[:10]:
            w("     %s maxdim=%s max(dim)=%s" % (p, md, round(mx, 2)))
    if bounds_math[:10]:
        w("  --bounds数学不一致示例(前10):")
        for p, ax, v, exp in bounds_math[:10]:
            w("     %s [%s] 实际=%s 应为=%s" % (p, ax, v, round(exp, 2)))
    if zoffset_wrong[:15]:
        w("  --Z偏移错误示例(前15):")
        for p, msg, zmin, zmax in zoffset_wrong[:15]:
            w("     %s %s (z_min=%s z_max=%s)" % (p, msg, zmin, zmax))
    if unit_suspect[:15]:
        w("  --单位检测可疑示例(前15):")
        for p, md, msg in unit_suspect[:15]:
            w("     %s max_d=%s %s" % (p, md, msg))
    if orient_conflict[:10]:
        w("  --朝向矛盾示例(前10):")
        for p, msg, dx, dy, dz in orient_conflict[:10]:
            w("     %s %s (dim=%sx%sx%s)" % (p, msg, dx, dy, dz))
    w()
    w("【三、分类统计】")
    w("  原点分布: " + str(dict(Counter(a.get("origin_z", "无")[:12] for a in assets if a.get("class") == "StaticMesh"))))
    w("  朝向分布: " + str(dict(Counter(a.get("orientation", "无")[:14] for a in assets if a.get("class") == "StaticMesh"))))
    w("  单位分布: " + str(dict(Counter(a.get("likely_unit", "无")[:16] for a in assets if a.get("class") == "StaticMesh"))))
    w()
    w("【四、结论】")
    crit = len(missing_base) + len(missing_mesh) + len(zero_extent) + len(dim_mismatch) + len(maxdim_mismatch) + len(bounds_math)
    w("  严重问题(完整性+数值一致性): %d" % crit)
    w("  轻微问题(Z偏移/单位检测/朝向/缺字段): %d" % (len(zoffset_wrong) + len(unit_suspect) + len(orient_conflict) + len(near_bottom_no_zoffset)))
    if crit == 0:
        w("  => 完整性与数值一致性: 通过")
    else:
        w("  => 存在严重问题, 需修复")
    w("=" * 70)

    report = "\n".join(lines)
    print(report)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n报告已保存: " + REPORT_PATH)


if __name__ == "__main__":
    main()
