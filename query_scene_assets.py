# -*- coding: utf-8 -*-
# ============================================================================
# query_scene_assets.py - 从资产清单查询场景各功能区所需资产及正确参数
# ============================================================================
# 读取 asset_catalog.json, 按功能区查询资产, 输出每个资产的:
#   路径/尺寸/单位/缩放系数/朝向/原点/Z偏移/材质列表
# 用于指导生成正确的大场景 JSON
# ============================================================================

import json

CATALOG = "c:/Users/25868/Desktop/UE5/MapForgeTest/asset_catalog.json"
OUT = "c:/Users/25868/Desktop/UE5/MapForgeTest/scene_asset_ref.txt"


def load():
    with open(CATALOG, "r", encoding="utf-8") as f:
        return json.load(f)["assets"]


def info(a):
    """格式化资产关键参数为一行"""
    if "dimensions_xyz" not in a:
        return "  (非网格) %s [%s]" % (a.get("path", ""), a.get("class", ""))
    dim = a["dimensions_xyz"]
    sc = a.get("scale_to_cm", 1.0)
    oz = a.get("origin_z", "-")
    zo = a.get("z_offset_needed", "-")
    ori = a.get("orientation", "-")
    mat = a.get("materials", [])
    unit = a.get("likely_unit", "-")
    # 建议缩放: 米制需x100, 厘米x1
    sug_sc = 100.0 if (str(unit).startswith("meters")) else 1.0
    # 建议Z偏移: 直接用清单值
    sug_z = zo if isinstance(zo, (int, float)) else 0
    return "  path=%s\n    dim=[%.1f, %.1f, %.1f] unit=%s scale_to_cm=%s sug_scale=%s\n    orient=%s origin_z=%s zoff=%s sug_z=%s\n    mats=%s" % (
        a.get("path", ""), dim[0], dim[1], dim[2], unit[:20], sc, sug_sc,
        ori[:20], oz[:30], zo, sug_z, mat[:3])


def query(assets, predicate, title, limit=None):
    lines = ["\n=== %s ===" % title]
    cnt = 0
    for a in assets:
        if predicate(a):
            lines.append(info(a))
            cnt += 1
            if limit and cnt >= limit:
                break
    lines.append("  (共 %d 条)" % cnt)
    return lines


def main():
    assets = load()
    out = []

    # --- 1. 树木(林带用) ---
    out += query(assets,
        lambda a: a.get("class") == "StaticMesh" and (
            "Pine_Tree" in a.get("path", "") or
            "SM_FirTree" in a.get("path", "") or
            "SM_SmallFir" in a.get("path", "") or
            "Foliage" in a.get("folder", "")),
        "1. 树木/灌木(林带)", limit=30)

    # --- 2. 地面材质(草地/泥土, 非木地板) ---
    out += query(assets,
        lambda a: a.get("class") in ("Material", "MaterialInstanceConstant") and (
            "grass" in a.get("path", "").lower() or
            "dirt" in a.get("path", "").lower() or
            "ground" in a.get("path", "").lower() or
            "terrain" in a.get("path", "").lower()) and
            "floor" not in a.get("path", "").lower(),
        "2. 地面材质(草地/泥土)", limit=20)

    # --- 3. 小麦/作物 ---
    out += query(assets,
        lambda a: a.get("class") == "StaticMesh" and "wheat" in a.get("path", "").lower(),
        "3. 小麦/作物", limit=10)

    # --- 4. 住宅蓝图(村落用) ---
    out += query(assets,
        lambda a: a.get("class") == "Blueprint" and "House" in a.get("path", ""),
        "4. 住宅蓝图", limit=20)

    # --- 5. 停机坪 ---
    out += query(assets,
        lambda a: "heliport" in a.get("path", "").lower() and a.get("class") == "StaticMesh",
        "5. 停机坪", limit=12)

    # --- 6. 通信塔(排除空网格) ---
    out += query(assets,
        lambda a: "CommunicationTower" in a.get("path", "") and a.get("class") == "StaticMesh" and not a.get("empty_mesh"),
        "6. 通信塔(非空网格)", limit=30)

    # --- 7. 高压塔 ---
    out += query(assets,
        lambda a: "HighVoltageTower" in a.get("path", "") and a.get("class") == "StaticMesh" and not a.get("empty_mesh"),
        "7. 高压塔(非空网格)", limit=25)

    # --- 8. 光伏板 ---
    out += query(assets,
        lambda a: "Photovoltaic" in a.get("path", "") and a.get("class") == "StaticMesh" and not a.get("empty_mesh"),
        "8. 光伏板(非空网格)", limit=15)

    # --- 9. 围栏 ---
    out += query(assets,
        lambda a: "WireFence" in a.get("path", "") and a.get("class") == "StaticMesh" and not a.get("empty_mesh"),
        "9. 围栏", limit=10)

    # --- 10. 房屋道具 ---
    out += query(assets,
        lambda a: a.get("class") == "StaticMesh" and "Props" in a.get("path", "") and not a.get("empty_mesh")
        and any(k in a.get("path","") for k in ["Generator","AirConditioner","ElectricBox","Power_Pole","Metal_Sheet"]),
        "10. 机库道具", limit=15)

    # --- 11. 地面平面网格(铺地面用) ---
    out += query(assets,
        lambda a: a.get("class") == "StaticMesh" and ("FloorPlane" in a.get("path", "") or "ground" in a.get("path", "").lower()) and not a.get("empty_mesh"),
        "11. 地面平面网格", limit=10)

    text = "\n".join(out)
    print(text[:8000])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("\n... 完整输出: " + OUT)


if __name__ == "__main__":
    main()
