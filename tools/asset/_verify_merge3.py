import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

assets = catalog.get("assets", [])
tree_assets = [a for a in assets if a.get("category") == "vegetation_tree"]

# StaticMesh 树（有物理尺寸的）
sm_trees = [t for t in tree_assets if t.get("class") == "StaticMesh"]
sm_with_bounds = [t for t in sm_trees if "bounds_origin" in t or "dimensions_xyz" in t]

print(f"StaticMesh 树总数: {len(sm_trees)}")
print(f"其中有 bounds/dimensions: {len(sm_with_bounds)}")

# 看一条完整的SM树
if sm_with_bounds:
    print(f"\n=== 示例 StaticMesh 树（全部字段）===")
    for k, v in sorted(sm_with_bounds[0].items()):
        print(f"  {k}: {v}")

# 按来源路径分组 SM树
from collections import Counter
paths = Counter()
for t in sm_with_bounds:
    p = t.get("path", "")
    parts = p.split("/")
    if len(parts) >= 3:
        paths[parts[2]] += 1

print(f"\n=== 有物理尺寸的 StaticMesh 树按来源 (Top 20) ===")
for p, cnt in paths.most_common(20):
    print(f"  /Game/{p}: {cnt}")

# 分析可用性
ready = 0
need_offset = 0
need_scale = 0
other = 0
for t in sm_with_bounds:
    dims = t.get("dimensions_xyz", [])
    origin = t.get("bounds_origin", [])
    unit = t.get("unit_inferred", "")
    origin_z = t.get("origin_z_analysis", "")
    
    if unit == "centimeters" and origin_z == "bottom":
        ready += 1
    elif origin_z == "center":
        need_scale += 1
    elif origin_z in ["top", "top_or_need_offset"]:
        need_offset += 1
    else:
        other += 1

print(f"\n=== 可用性分析 ===")
print(f"可直接使用 (cm + bottom原点): {ready}")
print(f"需Z偏移 (原点偏上): {need_offset}")
print(f"原点在中心: {need_scale}")
print(f"其他: {other}")

# 列出最新的有尺寸的树（最近新增的来源）
new_sources = ["Stylized_Tree_Pack", "HighPoly_Tree_Model", "PN_interactiveSpruceForest", "EuropeanBeech", "MSPresets"]
for src in new_sources:
    src_trees = [t for t in sm_with_bounds if f"/Game/{src}/" in t.get("path", "")]
    if src_trees:
        print(f"\n=== /Game/{src}/ ({len(src_trees)} 棵树) ===")
        for t in sorted(src_trees[:5], key=lambda x: x.get("height_m", 0) or 0, reverse=True):
            dims = t.get("dimensions_xyz", [0,0,0])
            if isinstance(dims, list) and len(dims) >= 3:
                dim_str = f"{dims[0]:.0f}x{dims[1]:.0f}x{dims[2]:.0f} cm"
            else:
                dim_str = str(dims)
            name = t.get("name", "?").split(".")[0]
            print(f"  {name} 尺寸={dim_str} 原点={t.get('origin_z_analysis','?')} 单位={t.get('unit_inferred','?')}")