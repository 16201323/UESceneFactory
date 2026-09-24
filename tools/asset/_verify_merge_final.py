import json, os, sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

assets = catalog.get("assets", [])
tree_assets = [a for a in assets if a.get("category") == "vegetation_tree"]
sm_with_bounds = [t for t in tree_assets if t.get("class") == "StaticMesh" and "bounds_origin" in t]

print(f"=== 资产清单验证报告 ===\n")
print(f"catalog 总资产数: {len(assets)}")
print(f"树木资产总数: {len(tree_assets)}")
print(f"StaticMesh 树（有物理尺寸）: {len(sm_with_bounds)}")
print()

# 单位分析
cm_trees = [t for t in sm_with_bounds if "centimeters" in t.get("likely_unit", "")]
meter_trees = [t for t in sm_with_bounds if "meters" in t.get("likely_unit", "")]
print(f"厘米单位树: {len(cm_trees)}")
print(f"米单位树（需×100缩放）: {len(meter_trees)}")
print()

# 原点分析
bottom = [t for t in sm_with_bounds if "bottom" in t.get("origin_z", "")]
center = [t for t in sm_with_bounds if "center" in t.get("origin_z", "")]
top = [t for t in sm_with_bounds if "top" in t.get("origin_z", "")]
print(f"原点在底部（可直接使用）: {len(bottom)}")
print(f"原点在中心（需Z偏移）: {len(center)}")
print(f"原点在顶部: {len(top)}")
other_origin = len(sm_with_bounds) - len(bottom) - len(center) - len(top)
print(f"其他: {other_origin}")
print()

# 可直接使用的判断：cm + bottom-origin
ready = [t for t in sm_with_bounds if "centimeters" in t.get("likely_unit","") and "bottom" in t.get("origin_z","")]
need_offset = [t for t in sm_with_bounds if "centimeters" in t.get("likely_unit","") and "center" in t.get("origin_z","")]
need_scale = [t for t in sm_with_bounds if "meters" in t.get("likely_unit","")]
print(f"✅ 可直接使用 (cm + bottom原点): {len(ready)}")
print(f"⚠️ 需Z偏移 (cm + center原点): {len(need_offset)}")
print(f"⚠️ 需×100缩放 (meters单位): {len(need_scale)}")
print(f"⏳ 其他情况: {len(sm_with_bounds) - len(ready) - len(need_offset) - len(need_scale)}")

# 按来源分组展示
print(f"\n=== 新增来源详细 ===")
sources = {}
for t in sm_with_bounds:
    p = t.get("path", "")
    parts = p.split("/")
    key = parts[2] if len(parts) > 2 else parts[1]
    if key not in sources:
        sources[key] = {"total": 0, "ready": 0, "need_offset": 0, "need_scale": 0, "other": 0, "trees": []}
    sources[key]["total"] += 1
    if "centimeters" in t.get("likely_unit","") and "bottom" in t.get("origin_z",""):
        sources[key]["ready"] += 1
    elif "centimeters" in t.get("likely_unit","") and "center" in t.get("origin_z",""):
        sources[key]["need_offset"] += 1
    elif "meters" in t.get("likely_unit",""):
        sources[key]["need_scale"] += 1
    else:
        sources[key]["other"] += 1

for src in sorted(sources.keys()):
    s = sources[src]
    flags = []
    if s["ready"]: flags.append(f"{s['ready']}可直接用")
    if s["need_offset"]: flags.append(f"{s['need_offset']}需偏移")
    if s["need_scale"]: flags.append(f"{s['need_scale']}需缩放")
    if s["other"]: flags.append(f"{s['other']}其他")
    print(f"  /Game/{src}/: {s['total']}棵 ({', '.join(flags)})")

# 最大树的 Top 10
print(f"\n=== 最大树木 Top 10 ===")
sorted_trees = sorted(sm_with_bounds, key=lambda x: x.get("height_m", 0) or 0, reverse=True)
for t in sorted_trees[:10]:
    h = t.get("height_m", 0) or 0
    dims = t.get("dimensions_xyz", [0,0,0])
    name = t.get("name", "?").split(".")[0]
    dim_str = f"{dims[0]:.0f}x{dims[1]:.0f}x{dims[2]:.0f}cm" if isinstance(dims, list) and len(dims)>=3 else "N/A"
    unit = t.get("likely_unit", "?")
    origin = t.get("origin_z", "?")
    print(f"  {name}  {dim_str}  单位={unit}  原点={origin}")

print(f"\n=== 验证完成 ===")