# -*- coding: utf-8 -*-
"""
check_catalog_vs_content.py - 资产清单 vs UE5.8 项目 Content 目录 缺失比对

功能:
    将 asset_catalog.json 中的每个 /Game/... 资产路径映射到 Content 目录对应的
    磁盘文件(.uasset/.umap), 找出在 Content 目录中不存在的资产(即"缺失清单")。

为什么做 (背景):
    资产清单一度从多个旧工程扫描而来(含 /Game/sences/... 等已废弃资产包),
    切换 UE5.8 项目(MyUETest5_8_2)后, 清单中大量路径在真实 Content 目录
    找不到对应 .uasset, 导致 LLM 智能体搜索返回一堆"死路径", 构建时资产缺失。

用法:
    python tools/asset/check_catalog_vs_content.py         # 用默认路径
    python tools/asset/check_catalog_vs_content.py --catalog <json> --content <Content目录>

退出码: 0=无缺失  2=有缺失(缺失清单打印到 stdout)
"""
import argparse
import json
import os
import sys


def ue_path_to_disk(path: str, content_dir: str):
    """UE 资产路径(/Game/...) → Content 下磁盘文件路径, 存在返回路径, 不存在返回 None。

    容错规则与 validate_scene_assets.py::ue_path_to_disk 一致:
      1. /Game/X/Y → Content/X/Y.uasset / .umap (蓝图 _C 后缀去掉)
      2. 补对象名 /Game/A/B → /Game/A/B.B.uasset
      3. 长路径剥离 /Game/A/B.C → /Game/A/B (catalog 中 Name.Name 格式)
    """
    rel = path[len("/Game/"):] if path.startswith("/Game/") else path.lstrip("/")
    base = os.path.join(content_dir, rel.replace("/", os.sep))
    if base.endswith("_C"):
        base = base[:-2]
    # 1. 原路径 .uasset / .umap
    for ext in (".uasset", ".umap"):
        if os.path.isfile(base + ext):
            return (base + ext).replace(content_dir, "<Content>")
    # 2. 补对象名
    obj = os.path.basename(base)
    if os.path.isfile(os.path.join(base + "." + obj + ".uasset")):
        return (base + "." + obj + ".uasset").replace(content_dir, "<Content>")
    # 3. 长路径剥离(最后一段含 '.' 时取 '.' 前为包名)
    last_seg = os.path.basename(base)
    if "." in last_seg:
        short_base = os.path.join(os.path.dirname(base), last_seg.split(".")[0])
        for ext in (".uasset", ".umap"):
            if os.path.isfile(short_base + ext):
                return (short_base + ext).replace(content_dir, "<Content>")
    return None


def build_disk_index(content_dir: str) -> set:
    """预扫描 Content 目录下所有 .uasset/.umap 的相对路径集合, 加速比对。"""
    disk = set()
    for root, _, files in os.walk(content_dir):
        for fn in files:
            if fn.endswith(".uasset") or fn.endswith(".umap"):
                rel = os.path.relpath(os.path.join(root, fn), content_dir)
                disk.add(rel.replace(os.sep, "/"))
    return disk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=os.path.join(os.path.dirname(__file__), "..", "..", "config", "asset_catalog.json"))
    ap.add_argument("--content", default=r"D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content")
    ap.add_argument("--min-uasset-count", type=int, default=0,
                    help="Content 目录 .uasset 数量下限, 低于此值判定为空壳(防扫错目录)")
    args = ap.parse_args()

    catalog_path = os.path.abspath(args.catalog)
    content_dir = os.path.abspath(args.content)
    print(f"[catalog]  {catalog_path}")
    print(f"[content]  {content_dir}")

    if not os.path.isfile(catalog_path):
        print(f"错误: catalog 不存在: {catalog_path}"); sys.exit(2)
    if not os.path.isdir(content_dir):
        print(f"错误: content 目录不存在: {content_dir}"); sys.exit(2)

    with open(catalog_path, "r", encoding="utf-8") as f:
        assets = json.load(f).get("assets", [])

    # --- 空壳防护: 若 Content 资产过少, 多半路径扫错了目录, 直接中止 ---
    disk_index = build_disk_index(content_dir)
    print(f"[disk]     扫描到 .uasset/.umap 文件数: {len(disk_index)}")
    if len(disk_index) < args.min_uasset_count:
        print(f"警告: Content 资产数({len(disk_index)}) < 下限({args.min_uasset_count}), 疑似扫错目录, 已中止。")
        sys.exit(2)

    # --- 逐一映射清单路径 ---
    missing = []      # (path, category, class)
    present_disk = set()
    for a in assets:
        p = a.get("path", "")
        if not p:
            continue
        mapped = ue_path_to_disk(p, content_dir)
        if mapped is None:
            # 记录缺失
            missing.append((p, a.get("category", ""), a.get("class", "")))
        else:
            present_disk.add(mapped)

    # --- 输出缺失清单 ---
    total = len(assets)
    present_count = total - len(missing)
    print(f"\n========== 缺失清单 ==========")
    print(f"目录约束: <Content> = {content_dir}")
    print(f"清单资产总数: {total}   存在: {present_count}   缺失: {len(missing)}")
    print(f"缺失率: {len(missing)/total*100:.1f}%")

    if missing:
        # 按缺失类别聚合
        from collections import Counter
        cat_counter = Counter(c for _, c, _ in missing)
        print(f"\n缺失资产按类别统计:")
        for cat, cnt in cat_counter.most_common():
            print(f"  {cat}: {cnt}")
        print(f"\n缺失资产明细(路径 / 类别 / 类型):")
        for p, c, cl in sorted(missing, key=lambda x: (x[1], x[0])):
            print(f"  MISSING | {p} | {c} | {cl}")
    else:
        print("\n√ 清单中所有路径在 Content 目录均能找到对应资产, 无缺失。")

    # --- 可选: 反向缺失(Content 有但清单没收录) 不必全打印, 只报数量 ---
    print(f"\n(反向) Content 中存在但清单未收录的资产文件数: {len(disk_index - present_disk)}")

    sys.exit(2 if missing else 0)


if __name__ == "__main__":
    main()