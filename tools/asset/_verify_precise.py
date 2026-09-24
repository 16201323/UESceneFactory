import json, os, sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG_PATH = os.path.join(PROJECT_ROOT, "config", "asset_catalog.json")

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    catalog = json.load(f)

assets = catalog.get("assets", [])
tree_assets = [a for a in assets if a.get("category") == "vegetation_tree"]
sm_with_bounds = [t for t in tree_assets if t.get("class") == "StaticMesh" and "bounds_origin" in t]

# 先列出所有 unique 值
units = set()
origins = set()
for t in sm_with_bounds:
    units.add(t.get("likely_unit", "N/A"))
    origins.add(t.get("origin_z", "N/A"))

print("=== unique likely_unit ===")
for u in sorted(units):
    count = sum(1 for t in sm_with_bounds if t.get("likely_unit") == u)
    print(f"  [{count}] {u}")

print("\n=== unique origin_z ===")
for o in sorted(origins):
    count = sum(1 for t in sm_with_bounds if t.get("origin_z") == o)
    print(f"  [{count}] {o}")

# 精确分析
# 单位分类
cm_trees = [t for t in sm_with_bounds if "centimeters" in t.get("likely_unit", "")]
m_ambiguous = [t for t in sm_with_bounds if "meters_or_small_cm" in t.get("likely_unit", "")]
m_pure = [t for t in sm_with_bounds if t.get("likely_unit","") == "meters"]

print(f"\n=== 精确统计 ===")
print(f"厘米: {len(cm_trees)}")
print(f"meters_or_small_cm (需缩放): {len(m_ambiguous)}")
print(f"纯米单位: {len(m_pure)}")
print(f"合计: {len(cm_trees) + len(m_ambiguous) + len(m_pure)}")

# 原点精确分类
bottom_bottom = [t for t in sm_with_bounds if "bottom (原点在底部" in t.get("origin_z", "")]
bottom_near = [t for t in sm_with_bounds if "near_bottom" in t.get("origin_z", "")]
center = [t for t in sm_with_bounds if "center (原点在中心" in t.get("origin_z", "")]
top = [t for t in sm_with_bounds if "top (原点在顶部" in t.get("origin_z", "")]

print(f"\n原点分类:")
print(f"  bottom (可直接放地面): {len(bottom_bottom)}")
print(f"  near_bottom: {len(bottom_near)}")
print(f"  center (需Z偏移): {len(center)}")
print(f"  top: {len(top)}")
print(f"  合计: {len(bottom_bottom) + len(bottom_near) + len(center) + len(top)}")

# 交叉分析
print(f"\n=== 可用性分析 ===")
ready = len([t for t in sm_with_bounds 
    if "centimeters" in t.get("likely_unit","") 
    and ("bottom" in t.get("origin_z","") or "near_bottom" in t.get("origin_z",""))])
need_z = len([t for t in sm_with_bounds 
    if "centimeters" in t.get("likely_unit","") 
    and "center" in t.get("origin_z","")])
need_z_top = len([t for t in sm_with_bounds 
    if "centimeters" in t.get("likely_unit","") 
    and "top" in t.get("origin_z","")])
need_scale = len([t for t in sm_with_bounds 
    if "meters_or_small_cm" in t.get("likely_unit","")])

print(f"✅ 可直接使用 (cm + bottom/near_bottom): {ready}")
print(f"⚠️ 需Z偏移 (cm + center): {need_z}")
print(f"⚠️ 需Z偏移 (cm + top): {need_z_top}")
print(f"⚠️ 需×100缩放 (meters_or_small_cm): {need_scale}")
total_classified = ready + need_z + need_z_top + need_scale
print(f"分类合计: {total_classified} (总数 {len(sm_with_bounds)})")

# 按来源分组
print(f"\n=== 按来源分组 ===")
from collections import defaultdict
sources = defaultdict(lambda: {"total":0,"ready":0,"need_z":0,"need_scale":0})
for t in sm_with_bounds:
    p = t.get("path","")
    parts = p.split("/")
    src = parts[2] if len(parts)>2 else parts[1]
    sources[src]["total"] += 1
    lu = t.get("likely_unit","")
    oz = t.get("origin_z","")
    if "centimeters" in lu and ("bottom" in oz or "near_bottom" in oz):
        sources[src]["ready"] += 1
    elif "centimeters" in lu and ("center" in oz or "top" in oz):
        sources[src]["need_z"] += 1
    elif "meters_or_small_cm" in lu:
        sources[src]["need_scale"] += 1

for src in sorted(sources.keys()):
    s = sources[src]
    flags = []
    if s["ready"]: flags.append(f"✅{s['ready']}")
    if s["need_z"]: flags.append(f"⬆️{s['need_z']}")
    if s["need_scale"]: flags.append(f"🔍{s['need_scale']}")
    print(f"  /Game/{src}/: {s['total']}棵 ({' '.join(flags)})")