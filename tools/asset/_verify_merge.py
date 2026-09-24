import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

total = catalog.get("total_count", 0)
assets = catalog.get("assets", [])
stats = catalog.get("stats", {})

print(f"=== catalog 统计 ===")
print(f"total_count: {total}")
print(f"assets 实际数量: {len(assets)}")
print(f"stats: {json.dumps(stats, ensure_ascii=False, indent=2)}")

tree_assets = [a for a in assets if a.get("category") == "vegetation_tree"]
print(f"\n=== 树木资产统计 ===")
print(f"总数: {len(tree_assets)}")

# 按来源分组
sources = {}
for a in tree_assets:
    path = a.get("path", "")
    root = path.split("/")[1] if len(path.split("/")) > 1 else "unknown"
    if root not in sources:
        sources[root] = 0
    sources[root] += 1

print(f"\n按来源路径分组:")
for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
    print(f"  /Game/{src}: {cnt}")

# 树类型统计
subtypes = {}
for a in tree_assets:
    sub = a.get("sub_type", "unknown")
    subtypes[sub] = subtypes.get(sub, 0) + 1

print(f"\n按子类型分组:")
for sub, cnt in sorted(subtypes.items(), key=lambda x: -x[1]):
    print(f"  {sub}: {cnt}")

# 有物理尺寸的 SM 树
sm_trees = [a for a in tree_assets if a.get("type") == "StaticMesh"]
print(f"\n=== StaticMesh 树（有物理尺寸）===")
print(f"总数: {len(sm_trees)}")

ready = [t for t in sm_trees if t.get("cm_ready") == True]
need_offset = [t for t in sm_trees if t.get("origin_z_analysis") == "top or need offset"]
need_scale = [t for t in sm_trees if t.get("origin_z_analysis") == "center"]

print(f"可直接使用 (cm_ready=True): {len(ready)}")
print(f"需要Z偏移: {len(need_offset)}")
print(f"原点在中心: {len(need_scale)}")
print(f"其他: {len(sm_trees) - len(ready) - len(need_offset) - len(need_scale)}")

print(f"\n=== 最近新增的10棵树 ===")
# 按资产路径排序，显示最后10个
sorted_trees = sorted(sm_trees, key=lambda x: x.get("path", ""))
for t in sorted_trees[-10:]:
    dims = t.get("dimensions_xyz", [0,0,0])
    dim_str = f"{dims[0]:.0f}x{dims[1]:.0f}x{dims[2]:.0f}" if isinstance(dims, list) and len(dims) >= 3 else "N/A"
    print(f"  {t.get('path', '?')}")
    print(f"    尺寸: {dim_str} cm_ready={t.get('cm_ready')}")
    if t.get("origin_z_analysis"):
        print(f"    原点: {t.get('origin_z_analysis')}")