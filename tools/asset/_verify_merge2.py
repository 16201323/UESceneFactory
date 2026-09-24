import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

assets = catalog.get("assets", [])
tree_assets = [a for a in assets if a.get("category") == "vegetation_tree"]

print(f"树木资产总数: {len(tree_assets)}")

# 查看前3条树木资产的所有字段
print(f"\n=== 前3条树木资产字段结构 ===")
for i, t in enumerate(tree_assets[:3]):
    print(f"\n--- 第{i+1}条 ---")
    for k, v in sorted(t.items()):
        if isinstance(v, list) and len(str(v)) > 100:
            print(f"  {k}: [list, len={len(v)}]")
        elif isinstance(v, dict):
            print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            print(f"  {k}: {v}")

# 查看后3条树木资产（新增的）
print(f"\n=== 最后3条树木资产字段结构 ===")
for i, t in enumerate(tree_assets[-3:]):
    print(f"\n--- 倒数第{i+1}条 ---")
    for k, v in sorted(t.items()):
        if isinstance(v, list) and len(str(v)) > 100:
            print(f"  {k}: [list, len={len(v)}]")
        elif isinstance(v, dict):
            print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            print(f"  {k}: {v}")

# 统计各类型
types = {}
for t in tree_assets:
    tp = t.get("asset_type", "unknown")
    types[tp] = types.get(tp, 0) + 1

print(f"\n=== asset_type 统计 ===")
for tp, cnt in sorted(types.items(), key=lambda x: -x[1]):
    print(f"  {tp}: {cnt}")

# 统计有物理尺寸的
with_bounds = [t for t in tree_assets if "bounds_origin" in t or "dimensions_xyz" in t]
print(f"\n有 bounds/dimensions 的树: {len(with_bounds)}")

# 按来源路径分组（看path字段最后一段）
from collections import Counter
paths = Counter()
for t in tree_assets:
    p = t.get("path", "")
    parts = p.split("/")
    if len(parts) >= 3:
        paths[parts[2]] += 1
    elif len(parts) >= 2:
        paths[parts[1]] += 1

print(f"\n=== 按第3级路径分组 (Top 20) ===")
for p, cnt in paths.most_common(20):
    print(f"  /Game/{p}: {cnt}")