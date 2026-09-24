import json, os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

assets = catalog.get("assets", [])
tree_assets = [a for a in assets if a.get("category") == "vegetation_tree"]
sm_trees = [t for t in tree_assets if t.get("class") == "StaticMesh" and "bounds_origin" in t]

# --- 需缩放的 (meters_or_small_cm) ---
need_scale = [t for t in sm_trees if "meters_or_small_cm" in t.get("likely_unit", "")]
print(f"=== 需缩放的树 ({len(need_scale)} 棵) ===")
print(f"参数检查:")
for t in need_scale[:5]:
    name = t.get("name","?").split(".")[0]
    scale = t.get("scale_to_cm", "缺失")
    z_offset = t.get("z_offset_needed", "缺失")
    dims = t.get("dimensions_xyz", [])
    print(f"  {name}")
    print(f"    likely_unit: {t.get('likely_unit','?')}")
    print(f"    dimensions: {dims}")
    print(f"    scale_to_cm: {scale}")
    print(f"    z_offset_needed: {z_offset}")

# 统计 scale_to_cm 缺失的
scale_missing = [t for t in need_scale if "scale_to_cm" not in t]
print(f"\n需缩放但 scale_to_cm 缺失: {len(scale_missing)} 棵")

# --- 需偏移的 (center origin + cm) ---
need_offset = [t for t in sm_trees 
    if "centimeters" in t.get("likely_unit","") 
    and "center" in t.get("origin_z","")]
print(f"\n=== 需Z偏移的树 ({len(need_offset)} 棵) ===")
for t in need_offset[:5]:
    name = t.get("name","?").split(".")[0]
    z_offset = t.get("z_offset_needed", "缺失")
    dims = t.get("dimensions_xyz", [])
    print(f"  {name}")
    print(f"    origin_z: {t.get('origin_z','?')}")
    print(f"    dimensions: {dims}")
    print(f"    z_offset_needed: {z_offset}")

# 统计 z_offset_needed 缺失的
offset_missing = [t for t in need_offset if "z_offset_needed" not in t]
print(f"\n需偏移但 z_offset_needed 缺失: {len(offset_missing)} 棵")

# --- 可直接用的 ---
ready = [t for t in sm_trees
    if "centimeters" in t.get("likely_unit","")
    and ("bottom" in t.get("origin_z","") or "near_bottom" in t.get("origin_z",""))]
print(f"\n=== 可直接用的树 ({len(ready)} 棵) - 抽检 ===")
for t in ready[:3]:
    name = t.get("name","?").split(".")[0]
    scale = t.get("scale_to_cm", "缺失")
    z_offset = t.get("z_offset_needed", "缺失")
    print(f"  {name}: scale_to_cm={scale}, z_offset_needed={z_offset}")

# 检查所有字段名列表
all_keys = set()
for t in sm_trees:
    all_keys.update(t.keys())
print(f"\n=== StaticMesh 树所有字段名 ===")
for k in sorted(all_keys):
    has = sum(1 for t in sm_trees if k in t)
    print(f"  {k}: {has}/198")