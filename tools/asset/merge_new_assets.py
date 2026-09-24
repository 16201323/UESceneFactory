# -*- coding: utf-8 -*-
# ============================================================================
# merge_new_assets.py - 将 scan_missing_trees.py 的增量扫描结果合并到资产清单
# ============================================================================
# 功能:
#   1. 读取 scan_missing_trees.py 输出的 new_tree_assets.json 增量片段
#   2. 仅合并 vegetation_tree 类别的资产(其他类型跳过)
#   3. 去重: 相同 path 的条目用新的替换旧的
#   4. 更新 stats 统计
#   5. 重新生成 catalog 的 markdown 文档 + scene_asset_ref.txt
# 用法: python tools/asset/merge_new_assets.py
# ============================================================================

import json
import os
import time
from collections import OrderedDict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")
FRAGMENT_PATH = os.path.join(PROJECT_ROOT, "tools", "asset", "new_tree_assets.json")
CATALOG_MD_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.md")
ASSET_REF_PATH = os.path.join(PROJECT_ROOT, "config", "scene_asset_ref.txt")


def short_path(path):
    if path.startswith("/Game/"):
        return path[6:]
    return path


def fmt_dims(entry):
    d = entry.get("dimensions_xyz")
    if not d:
        return "-"
    return "%.1f x %.1f x %.1f" % (d[0], d[1], d[2])


def fmt_unit(entry):
    u = entry.get("likely_unit", "-")
    if u == "-":
        return "-"
    if u.startswith("meters"):
        return "米(需x100)"
    if u.startswith("centimeters"):
        return "厘米(正确)"
    return u


def fmt_adjust(entry):
    if "dimensions_xyz" not in entry:
        return "-"
    if entry.get("empty_mesh"):
        return "不可用(无几何体)"
    parts = []
    s = entry.get("scale_to_cm", 1.0)
    if s and s != 1.0:
        parts.append("缩放x%.0f" % s)
    ori = entry.get("orientation", "")
    if "standing_tall" in ori:
        parts.append("检查朝向(竖立)")
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


def main():
    print("=" * 60)
    print("merge_new_assets.py - 树资产增量合并")
    print("=" * 60)

    # ====================================================================
    # 1. 读取现有资产清单
    # ====================================================================
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    existing_assets = data.get("assets", [])
    print("\n[1/5] 现有资产清单: %d 条" % len(existing_assets))

    # 统计现有树资产
    existing_trees = [a for a in existing_assets if a.get("category") == "vegetation_tree"]
    existing_sm_trees = [a for a in existing_trees
                         if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]
    print("  其中树木类: %d (StaticMesh含尺寸: %d)" % (len(existing_trees), len(existing_sm_trees)))

    # ====================================================================
    # 2. 读取增量扫描片段
    # ====================================================================
    if not os.path.exists(FRAGMENT_PATH):
        print("\n[错误] 未找到增量片段: %s" % FRAGMENT_PATH)
        print("请先在 UE5 编辑器 Python 控制台中执行 scan_missing_trees.py")
        return

    with open(FRAGMENT_PATH, "r", encoding="utf-8") as f:
        fragment = json.load(f)

    fragment_assets = fragment.get("assets", [])
    frag_stats = fragment.get("stats", {})

    # 检查是否为空结果
    if fragment.get("message") == "no_missing_trees_found":
        print("\n[2/5] 增量片段: 0 条 (无缺失树资产)")
        print("  扫描完成, 无需合并。")
        # 清理临时文件
        os.remove(FRAGMENT_PATH)
        return

    print("\n[2/5] 增量片段: %d 条" % len(fragment_assets))
    print("  缺失树资产: %d, 成功加载: %d, 失败: %d" %
          (fragment.get("missing_tree_count", len(fragment_assets)),
           frag_stats.get("loaded", 0), frag_stats.get("failed", 0)))
    print("  /Game/ 下树资产总数: %d, 已在清单: %d" %
          (fragment.get("all_tree_count", "?"), fragment.get("known_paths_count", "?")))

    if not fragment_assets:
        print("  增量片段为空, 无需合并。")
        os.remove(FRAGMENT_PATH)
        return

    # ====================================================================
    # 3. 去重合并
    #    - 构建 path→entry 字典
    #    - 新条目覆盖旧的同 path 条目
    #    - 但只合并 vegetation_tree 类别的资产
    # ====================================================================
    merged = OrderedDict()
    for entry in existing_assets:
        p = entry.get("path", "")
        if p:
            merged[p] = entry

    overwrite_count = 0
    new_count = 0
    skipped_non_tree = 0
    for entry in fragment_assets:
        p = entry.get("path", "")
        if not p:
            continue
        if entry.get("category") != "vegetation_tree":
            skipped_non_tree += 1
            continue
        if p in merged:
            overwrite_count += 1
        else:
            new_count += 1
        merged[p] = entry

    assets_list = list(merged.values())
    print("\n[3/5] 合并结果: %d 条 (新增 %d, 覆盖 %d, 跳过非树 %d)" %
          (len(assets_list), new_count, overwrite_count, skipped_non_tree))

    # ====================================================================
    # 4. 重新统计
    # ====================================================================
    stats = {"total": len(assets_list), "loaded": 0, "failed": 0,
             "by_class": {}, "by_category": {}, "by_folder": {}}
    for a in assets_list:
        if a.get("status") == "load_failed":
            stats["failed"] += 1
        else:
            stats["loaded"] += 1
        cls = a.get("class", "Unknown")
        cat = a.get("category", "other")
        folder = a.get("folder", "root")
        stats["by_class"][cls] = stats["by_class"].get(cls, 0) + 1
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        stats["by_folder"][folder] = stats["by_folder"].get(folder, 0) + 1

    output_data = {"assets": assets_list, "stats": stats}
    for key in data:
        if key not in ("assets", "stats"):
            output_data[key] = data[key]

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print("[4/5] 主清单已更新: %s (%d 条)" % (CATALOG_PATH, len(assets_list)))

    # ====================================================================
    # 5. 重新生成 Markdown + 源引用文件
    # ====================================================================
    gen_tree_catalog_md(assets_list, fragment_assets, new_count)
    gen_asset_ref_txt(assets_list)
    print("[5/5] 文档已更新")

    # 清理临时增量片段
    os.remove(FRAGMENT_PATH)

    # 打印新增树资产摘要
    print_added_summary(fragment_assets, new_count)


def gen_tree_catalog_md(all_assets, new_tree_assets, new_count):
    """生成新增树资产的简明清单 (覆盖原有 catalog md)"""
    lines = []
    w = lines.append

    # 统计
    all_trees = [a for a in all_assets if a.get("category") == "vegetation_tree"]
    sm_trees = [a for a in all_trees
                if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]

    w("# 树资产增量清单")
    w("")
    w("> 由 `scan_missing_trees.py` 扫描 + `merge_new_assets.py` 合并生成")
    w("> 更新时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))
    w("")
    w("## 本次新增: %d 个树资产" % new_count)
    w("")
    w("**总树木类资产**: %d (StaticMesh含尺寸: %d)" % (len(all_trees), len(sm_trees)))
    w("")

    # 本次新增的 StaticMesh 树 (有物理尺寸)
    new_sm = [a for a in new_tree_assets
              if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]
    if new_sm:
        w("### 新增静态网格树 (有物理尺寸)")
        w("")
        w("| 资产路径 | 尺寸(长x宽x高 cm) | 最大尺寸 | 单位 | 朝向 | 原点位置 | 材质数 | 调整建议 |")
        w("|----------|---------------------|----------|------|------|----------|--------|----------|")
        for a in sorted(new_sm, key=lambda x: x.get("max_dimension", 0), reverse=True):
            w("| %s | %s | %.1f | %s | %s | %s | %d | %s |" % (
                short_path(a.get("path", "")),
                fmt_dims(a),
                a.get("max_dimension", 0),
                fmt_unit(a),
                a.get("orientation", "-").split(" (")[0] if a.get("orientation") else "-",
                a.get("origin_z", "-").split(" (")[0] if a.get("origin_z") else "-",
                a.get("material_count", 0),
                fmt_adjust(a),
            ))
        w("")

    # 本次新增的其他资产 (材质/纹理/蓝图)
    new_other = [a for a in new_tree_assets
                 if a.get("class") != "StaticMesh" or "dimensions_xyz" not in a]
    if new_other:
        w("### 新增其他树资产 (材质/纹理/蓝图)")
        w("")
        w("| 资产路径 | 类型 | 额外信息 |")
        w("|----------|------|----------|")
        for a in sorted(new_other, key=lambda x: x.get("path", "")):
            extra = ""
            if a.get("shading_model"):
                extra = "着色:%s" % a.get("shading_model", "")
            elif a.get("texture_size"):
                ts = a.get("texture_size")
                extra = "尺寸:%dx%d" % (ts[0], ts[1])
            elif a.get("generated_class"):
                extra = "生成类:%s" % a.get("generated_class", "")
            w("| %s | %s | %s |" % (
                short_path(a.get("path", "")),
                a.get("class", "-"),
                extra,
            ))
        w("")

    # 写入 catalog md (树资产清单)
    with open(CATALOG_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("  Markdown 清单: %s" % CATALOG_MD_PATH)


def gen_asset_ref_txt(all_assets):
    """重新生成 scene_asset_ref.txt (按类别聚合)"""
    CATEGORY_ORDER = [
        ("ground", "地面/地形"),
        ("vegetation_tree", "树木植被"),
        ("vegetation_crop", "农作物"),
        ("building", "建筑房屋"),
        ("heliport", "停机坪"),
        ("communication_tower", "通信塔"),
        ("high_voltage_tower", "高压电塔"),
        ("solar_panel", "太阳能板"),
        ("fence", "围栏"),
        ("blueprint", "蓝图"),
        ("material", "材质"),
        ("texture", "贴图"),
        ("other", "其他"),
    ]

    lines = []
    w = lines.append
    w("# scene_asset_ref.txt - 场景资产源引用清单")
    w("# 由 merge_new_assets.py 自动生成, 更新时间: " + time.strftime("%Y-%m-%d %H:%M:%S"))
    w("# 格式: 资产路径 | 类别 | 尺寸 | 调整建议")
    w("")

    for idx, (cat_key, cat_cn) in enumerate(CATEGORY_ORDER, 1):
        items = [a for a in all_assets if a.get("category") == cat_key]
        if not items:
            continue
        w("# %d. %s (%s) - 共 %d 个" % (idx, cat_cn, cat_key, len(items)))
        w("")

        meshes = [a for a in items
                  if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]
        for a in sorted(meshes, key=lambda x: x.get("path", "")):
            w("%s | %s | %s | %s" % (
                a.get("path", ""), cat_cn, fmt_dims(a), fmt_adjust(a)))

        bps = [a for a in items if a.get("class") == "Blueprint"]
        for a in sorted(bps, key=lambda x: x.get("path", "")):
            w("%s | %s | 蓝图 | %s" % (
                a.get("path", ""), cat_cn, a.get("generated_class", "-")))

        others = [a for a in items if a not in meshes and a not in bps]
        for a in sorted(others, key=lambda x: x.get("path", "")):
            w("%s | %s | %s | -" % (
                a.get("path", ""), cat_cn, a.get("class", "-")))
        w("")

    with open(ASSET_REF_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("  源引用文件: %s" % ASSET_REF_PATH)


def print_added_summary(new_tree_assets, new_count):
    """打印本次新增树资产的摘要"""
    print("\n" + "=" * 60)
    print("本次新增树资产摘要")
    print("=" * 60)

    sm_trees = [a for a in new_tree_assets
                if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]
    bps = [a for a in new_tree_assets if a.get("class") == "Blueprint"]
    mats = [a for a in new_tree_assets if a.get("class", "").endswith("Material")]
    texs = [a for a in new_tree_assets if a.get("class") == "Texture2D"]
    other = [a for a in new_tree_assets
             if a not in sm_trees and a not in bps and a not in mats and a not in texs]

    print("新增总数: %d" % new_count)
    print("  StaticMesh(含物理尺寸): %d" % len(sm_trees))
    print("  Blueprint: %d" % len(bps))
    print("  Material: %d" % len(mats))
    print("  Texture: %d" % len(texs))
    if other:
        print("  其他: %d" % len(other))

    # 米制/厘米制/原点居中统计
    mer_s = [a for a in sm_trees if a.get("likely_unit", "").startswith("meters")]
    cm_s = [a for a in sm_trees if a.get("likely_unit", "").startswith("centimeters")]
    centered = [a for a in sm_trees if "center" in a.get("origin_z", "")]
    bottomed = [a for a in sm_trees if "bottom" in a.get("origin_z", "")]

    print("\n使用建议:")
    if mer_s:
        print("  [需x100缩放] %d 个树(米制单位):" % len(mer_s))
        for a in mer_s:
            print("    %s | %s" % (short_path(a["path"]), fmt_dims(a)))
    if centered:
        print("  [需Z偏移] %d 个树(原点居中):" % len(centered))
        for a in centered:
            print("    %s | Z+%.0f" % (short_path(a["path"]), a.get("z_offset_needed", 0)))
    if cm_s and bottomed:
        print("  [可直接使用] %d 个树(厘米制+原点在底)" % len([a for a in cm_s if "bottom" in a.get("origin_z", "")]))

    # 按路径根分组列出
    roots = {}
    for a in sm_trees:
        path = a["path"]
        parts = path.split("/")
        root = "/".join(parts[:3]) if len(parts) >= 3 else path
        roots.setdefault(root, []).append(a)

    print("\n按来源路径根:")
    for root, items in sorted(roots.items()):
        size_range = [it.get("max_dimension", 0) for it in items]
        print("  %s: %d 棵 (尺寸范围 %.1f ~ %.1f)" %
              (root, len(items), min(size_range), max(size_range)))

    print("\n新增树资产数: %d, 路径根数: %d" % (len(sm_trees), len(roots)))


if __name__ == "__main__":
    main()