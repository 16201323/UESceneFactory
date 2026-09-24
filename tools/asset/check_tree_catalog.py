# -*- coding: utf-8 -*-
"""检查现有资产清单中树类资产的概况"""
import json

with open("c:/Users/25868/Desktop/UE5/UESceneFactory/config/asset_catalog.json", "r", encoding="utf-8") as f:
    d = json.load(f)

trees = [a for a in d["assets"] if a.get("category") == "vegetation_tree"]
sm = [a for a in trees if a.get("class") == "StaticMesh"]
print(f"树木类总资产: {len(trees)}")
print(f"其中StaticMesh: {len(sm)}")
print(f"其中含bounds: {sum(1 for a in sm if 'dimensions_xyz' in a)}")
print()

# 已有的树资产路径前缀 (前4级)
prefixes = set()
for a in trees:
    p = a["path"]
    parts = p.split("/")
    prefix = "/".join(parts[:4]) if len(parts) >= 4 else "/".join(parts)
    prefixes.add(prefix)

print("已有树资产路径前缀:")
for p in sorted(prefixes):
    count = sum(1 for a in trees if a["path"].startswith(p))
    print(f"  {p}  ({count} 个)")

# 列出所有已有的 tree 路径 (用于去重)
known = set()
for a in trees:
    known.add(a["path"])
print(f"\n已知树路径总数: {len(known)}")