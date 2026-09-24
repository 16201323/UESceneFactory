# -*- coding: utf-8 -*-
"""检查 asset_catalog.json 中是否已有新导入的树资产路径"""
import json

CATALOG_PATH = "c:/Users/25868/Desktop/UE5/UESceneFactory/config/asset_catalog.json"
NEW_PATHS = [
    "Stylized_Tree_Pack",
    "HighPoly_Tree_Model", 
    "Maple_Tree",
    "interactiveSpruceForest",
]

with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

assets = data.get("assets", [])
paths = [a.get("path", "") for a in assets]

print(f"目录总资产数: {len(assets)}")
print()

for kw in NEW_PATHS:
    count = sum(1 for p in paths if kw in p)
    print(f"  {kw}: {count} 条记录")

print()
print("现有文件夹列表:")
folders = sorted(set(a.get("folder", "") for a in assets))
for f in folders:
    print(f"  {f}")