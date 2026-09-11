# -*- coding: utf-8 -*-
# ============================================================================
# sync_collision_to_catalog.py - 将碰撞检测结果同步到 asset_catalog.json
# ============================================================================
# 读取 probe_collision4_result.json (65 StaticMesh) 和
#       probe_collision6_result.json (2 Blueprint),
# 为 asset_catalog.json 中匹配的条目添加 collision 字段。
#
# 用法: python sync_collision_to_catalog.py (纯 Python, 不依赖 UE)
# ============================================================================

import json

PROBE4_JSON = "c:/Users/25868/Desktop/UE5/probe_collision4_result.json"
PROBE6_JSON = "c:/Users/25868/Desktop/UE5/probe_collision6_result.json"
CATALOG_JSON = "c:/Users/25868/Desktop/UE5/MapForgeTest/asset_catalog.json"


def build_collision_field(info):
    """从探测结果提取碰撞信息, 构建统一的 collision 字段。"""
    col = {}
    col["has_collision"] = info.get("has_collision", False)
    col["collision_type"] = info.get("collision_type", "")

    # StaticMesh 字段
    if "simple_collision_count" in info:
        col["simple_collision_count"] = info["simple_collision_count"]
        col["element_detail"] = info.get("element_detail", {})
        col["uses_complex_collision"] = info.get("uses_complex_collision", False)
        col["player_blocked"] = info["simple_collision_count"] > 0
        col["bullet_hits"] = info.get("has_collision", False)

    # Blueprint 字段
    if "smc_count" in info:
        col["smc_count"] = info["smc_count"]
        col["mesh_with_asset_count"] = info.get("mesh_with_asset_count", 0)
        col["has_simple_collision"] = info.get("has_simple_collision", False)
        col["has_complex_collision"] = info.get("has_complex_collision", False)
        col["player_blocked"] = info.get("has_simple_collision", False)
        col["bullet_hits"] = info.get("has_collision", False)

    return col


def main():
    # 读取探测结果
    with open(PROBE4_JSON, "r", encoding="utf-8") as f:
        probe4 = json.load(f)
    with open(PROBE6_JSON, "r", encoding="utf-8") as f:
        probe6 = json.load(f)

    # 合并探测结果: path -> collision field
    collision_map = {}
    for path, info in probe4.items():
        collision_map[path] = build_collision_field(info)
    for path, info in probe6.items():
        collision_map[path] = build_collision_field(info)

    print("探测结果总数: %d (StaticMesh=%d, Blueprint=%d)" % (
        len(collision_map), len(probe4), len(probe6)))

    # 读取资产清单
    with open(CATALOG_JSON, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    assets = catalog.get("assets", [])
    print("资产清单总数: %d" % len(assets))

    # 同步: 为匹配的条目添加 collision 字段
    matched = 0
    unmatched_paths = list(collision_map.keys())
    for entry in assets:
        path = entry.get("path", "")
        if path in collision_map:
            entry["collision"] = collision_map[path]
            matched += 1
            if path in unmatched_paths:
                unmatched_paths.remove(path)

    print("匹配并同步: %d" % matched)
    print("未匹配的探测路径: %d" % len(unmatched_paths))
    if unmatched_paths:
        print("未匹配列表:")
        for p in unmatched_paths:
            print("  %s" % p)

    # 统计碰撞结果
    n_blocked = 0
    n_complex_only = 0
    n_none = 0
    for col in collision_map.values():
        ct = col.get("collision_type", "")
        if col.get("player_blocked"):
            n_blocked += 1
        elif col.get("has_collision"):
            n_complex_only += 1
        else:
            n_none += 1
    print("\n碰撞结果汇总:")
    print("  玩家阻挡 (含简化碰撞): %d" % n_blocked)
    print("  仅复杂碰撞 (玩家穿透): %d" % n_complex_only)
    print("  无碰撞: %d" % n_none)

    # 写回资产清单
    with open(CATALOG_JSON, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print("\n已写回: %s" % CATALOG_JSON)


if __name__ == "__main__":
    main()
