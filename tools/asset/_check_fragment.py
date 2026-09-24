import json

with open("c:/Users/25868/Desktop/UE5/UESceneFactory/tools/asset/new_tree_assets.json", "r", encoding="utf-8") as f:
    d = json.load(f)

assets = d["assets"]
total = len(assets)
sm = [a for a in assets if a.get("class") == "StaticMesh"]
sm_bounds = [a for a in sm if "dimensions_xyz" in a]
texs = [a for a in assets if a.get("class") == "Texture2D"]
mats = [a for a in assets if "Material" in a.get("class", "")]
bps = [a for a in assets if a.get("class") == "Blueprint"]
failed = [a for a in assets if a.get("status") == "load_failed"]

print(f"已扫描: {total} 条")
print(f"  StaticMesh: {len(sm)} (含bounds: {len(sm_bounds)})")
print(f"  Blueprint: {len(bps)}")
print(f"  Texture: {len(texs)}")
print(f"  Material: {len(mats)}")
print(f"  加载失败: {len(failed)}")
print()
print(f"最后一条: {assets[-1]['path'] if assets else '无'}")

# 按路径根统计
roots = {}
for a in assets:
    parts = a["path"].split("/")
    root = "/".join(parts[:3]) if len(parts) >= 3 else a["path"]
    roots[root] = roots.get(root, 0) + 1
    
print("\n按路径根:")
for r, c in sorted(roots.items()):
    print(f"  {r}: {c} 条")