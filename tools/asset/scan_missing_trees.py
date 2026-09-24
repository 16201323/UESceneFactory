# ============================================================================
# scan_missing_trees.py - 全量扫描 /Game/ 发现清单中缺失的树资产
# ============================================================================
# 功能:
#   1. 读取现有 asset_catalog.json, 构建已知路径集合
#   2. 用 AssetRegistry 枚举 /Game/ 下所有资产路径 (仅元数据, 不加载)
#   3. 按路径关键词过滤出树相关资产
#   4. 跳过已存在于清单中的路径
#   5. 仅加载缺失的树资产, 提取包围盒/材质/朝向/原点信息
#   6. 输出 new_tree_assets.json 增量片段
#
# 用法(UE5 Python 控制台):
#   py "c:/Users/25868/Desktop/UE5/UESceneFactory/tools/asset/scan_missing_trees.py"
# ============================================================================

import unreal
import json
import time

# 输入: 现有资产清单
CATALOG_PATH = "c:/Users/25868/Desktop/UE5/UESceneFactory/config/asset_catalog.json"
# 输出: 缺失树资产增量片段
OUTPUT_PATH = "c:/Users/25868/Desktop/UE5/UESceneFactory/tools/asset/new_tree_assets.json"

# 树类资产路径关键词 (与 asset_audit.py 的 guess_category 保持一致)
TREE_KEYWORDS = ["tree", "pine", "foliage", "oak", "birch", "maple", "spruce"]

# 跳过前缀: 这些路径已经在清单中扫描过, 且不包含新资产
SKIP_PREFIXES = [
    "/Game/Foliage_Sets/",
    "/Game/PolyHaven/",
    "/Game/RuralHouse/",
    "/Game/Modular_Rural_Cabin/",
    "/Game/hourse/",
    "/Game/MapForgeTest/",
    "/Game/Fab/Materials/",
    "/Game/Fab/MaterialParameterCollection/",
    "/Game/Foliage_Showcase2",
]


def is_tree_asset(asset_path):
    """根据路径判断是否为树资产"""
    lower = asset_path.lower()
    return any(kw in lower for kw in TREE_KEYWORDS)


def is_skipped_prefix(asset_path):
    """检查路径是否属于已知已扫描的旧路径"""
    return any(asset_path.startswith(p) for p in SKIP_PREFIXES)


def guess_category(asset_path):
    """根据路径推测类别 (对树资产直接返回 vegetation_tree)"""
    return "vegetation_tree"


def handle_static_mesh(mesh, entry):
    """获取 StaticMesh 的包围盒/尺寸/朝向/原点/材质信息"""
    got_bounds = False

    # 方法1: get_bounds()
    try:
        bounds = mesh.get_bounds()
        origin = bounds.origin
        extent = bounds.box_extent
        entry["bounds_origin"] = [round(origin.x, 2), round(origin.y, 2), round(origin.z, 2)]
        entry["bounds_extent"] = [round(extent.x, 2), round(extent.y, 2), round(extent.z, 2)]
        entry["bounds_min"] = [round(origin.x - extent.x, 2), round(origin.y - extent.y, 2), round(origin.z - extent.z, 2)]
        entry["bounds_max"] = [round(origin.x + extent.x, 2), round(origin.y + extent.y, 2), round(origin.z + extent.z, 2)]
        dim_x = round(extent.x * 2, 2)
        dim_y = round(extent.y * 2, 2)
        dim_z = round(extent.z * 2, 2)
        entry["dimensions_xyz"] = [dim_x, dim_y, dim_z]
        entry["max_dimension"] = max(dim_x, dim_y, dim_z)
        got_bounds = True
    except Exception as e:
        entry["bounds_error"] = str(e)[:200]

    # 方法2: SystemLibrary.get_object_bounds 兜底
    if not got_bounds:
        try:
            bb = unreal.SystemLibrary.get_object_bounds(mesh)
            entry["bounds_min"] = [round(bb.min.x, 2), round(bb.min.y, 2), round(bb.min.z, 2)]
            entry["bounds_max"] = [round(bb.max.x, 2), round(bb.max.y, 2), round(bb.max.z, 2)]
            dim_x = round(bb.max.x - bb.min.x, 2)
            dim_y = round(bb.max.y - bb.min.y, 2)
            dim_z = round(bb.max.z - bb.min.z, 2)
            entry["dimensions_xyz"] = [dim_x, dim_y, dim_z]
            entry["max_dimension"] = max(dim_x, dim_y, dim_z)
            got_bounds = True
        except Exception as e2:
            entry["bounds_error2"] = str(e2)[:200]

    if got_bounds:
        dims = entry["dimensions_xyz"]
        max_d = entry["max_dimension"]

        # 尺寸单位推测: UE 默认 1unit=1cm
        if max_d < 5:
            entry["likely_unit"] = "meters (需x100缩放)"
            entry["scale_to_cm"] = 100.0
        elif max_d < 50:
            entry["likely_unit"] = "meters_or_small_cm (需x100缩放)"
            entry["scale_to_cm"] = 100.0
        elif max_d < 500:
            entry["likely_unit"] = "centimeters (可能正确)"
            entry["scale_to_cm"] = 1.0
        else:
            entry["likely_unit"] = "centimeters (大物体, 可能正确)"
            entry["scale_to_cm"] = 1.0

        # 朝向分析: 判断物体是平躺还是竖立
        dx, dy, dz = dims
        if dz > dx * 2 and dz > dy * 2:
            entry["orientation"] = "standing_tall (竖立)"
        elif dx > dz * 3 and dy > dz * 3:
            entry["orientation"] = "flat_horizontal (平躺)"
        elif abs(dx - dz) < max(dx, dz) * 0.2 and abs(dy - dz) < max(dy, dz) * 0.2:
            entry["orientation"] = "cube_like (立方体)"
        else:
            entry["orientation"] = "mixed (混合)"

        # 原点偏移: 判断原点是否在底部
        if "bounds_min" in entry and "bounds_max" in entry:
            z_min = entry["bounds_min"][2]
            z_max = entry["bounds_max"][2]
            if z_min >= 0:
                entry["origin_z"] = "bottom (原点在底部, 可直接放地面)"
            elif z_max <= 0:
                entry["origin_z"] = "top (原点在顶部, 需下移)"
            elif abs(z_min) < 1.0 and abs(z_max) > 1.0:
                entry["origin_z"] = "near_bottom (原点近底部)"
            else:
                entry["origin_z"] = "center (原点在中心, 需上移半个高度)"
                entry["z_offset_needed"] = round(z_max, 2)

    # 材质列表
    try:
        mats = mesh.get_editor_property("static_materials")
        mat_names = []
        if mats:
            for m in mats:
                if m.material_interface:
                    mat_names.append(str(m.material_interface.get_path_name()))
        entry["materials"] = mat_names
        entry["material_count"] = len(mat_names)
    except Exception:
        entry["materials"] = []
        entry["material_count"] = 0


def handle_blueprint(bp, entry):
    """获取蓝图组件信息"""
    try:
        gen_class = bp.generated_class()
        if gen_class:
            entry["generated_class"] = str(gen_class.get_name())
    except Exception as e:
        entry["bp_class_error"] = str(e)[:200]

    try:
        gen_class = bp.generated_class()
        cdo = gen_class.get_default_object(True)
        if cdo and isinstance(cdo, unreal.Actor):
            components = cdo.get_components_by_class(unreal.SceneComponent)
            comp_list = []
            has_mesh = False
            for comp in components:
                comp_info = {"class": comp.__class__.__name__, "name": comp.get_name()}
                if isinstance(comp, unreal.MeshComponent):
                    has_mesh = True
                    try:
                        if isinstance(comp, unreal.StaticMeshComponent):
                            mesh_asset = comp.get_static_mesh()
                            if mesh_asset:
                                comp_info["mesh_path"] = str(mesh_asset.get_path_name())
                                try:
                                    bb = mesh_asset.get_bounds()
                                    comp_info["mesh_extents"] = [
                                        round(bb.box_extent.x * 2, 2),
                                        round(bb.box_extent.y * 2, 2),
                                        round(bb.box_extent.z * 2, 2),
                                    ]
                                except:
                                    pass
                                try:
                                    rt = comp.get_relative_location()
                                    comp_info["relative_location"] = [round(rt.x, 2), round(rt.y, 2), round(rt.z, 2)]
                                except:
                                    pass
                    except:
                        pass
                comp_list.append(comp_info)
            entry["components"] = comp_list
            entry["has_mesh_component"] = has_mesh
    except Exception as e:
        entry["bp_component_error"] = str(e)[:200]


def handle_material(mat, entry):
    """获取材质信息"""
    try:
        entry["shading_model"] = str(mat.get_editor_property("shading_model"))
    except:
        pass


def handle_texture(tex, entry):
    """获取纹理信息"""
    try:
        entry["texture_size"] = [
            tex.get_editor_property("size_x"),
            tex.get_editor_property("size_y"),
        ]
    except:
        pass


# ============================================================================
# 主函数
# ============================================================================

def main():
    start_time = time.time()
    print("=" * 60)
    print("SCAN_MISSING_TREES_START")
    print("=" * 60)

    # ====================================================================
    # 第1步: 读取现有资产清单, 构建已知路径集合
    # ====================================================================
    print("\n[1/5] 读取现有资产清单...")
    known_paths = set()
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for entry in existing.get("assets", []):
            p = entry.get("path", "")
            if p:
                known_paths.add(p)
        print("  已知资产路径: %d 条" % len(known_paths))
    except Exception as e:
        print("  WARN: 读取现有清单失败: %s, 将全部重新扫描" % str(e)[:100])
        known_paths = set()

    # ====================================================================
    # 第2步: 用 AssetRegistry 枚举 /Game/ 下所有资产
    #   AssetRegistry 只读元数据, 不触发资产加载, 速度快且安全
    # ====================================================================
    print("\n[2/5] AssetRegistry 枚举全量资产...")
    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # 构建 路径→类名 映射 + 所有路径列表
    all_paths = []
    path_class_map = {}
    try:
        all_asset_data = registry.get_assets_by_path("/Game/", True)
        for ad in all_asset_data:
            try:
                pkg_name = str(ad.get_editor_property("package_name"))
                asset_name_str = str(ad.get_editor_property("asset_name"))
                obj_path = pkg_name + "." + asset_name_str
                all_paths.append(obj_path)

                # 获取类名
                cls = ""
                try:
                    cp = ad.get_editor_property("asset_class_path")
                    cls = str(cp.asset_name)
                except:
                    try:
                        cls = str(ad.asset_class)
                    except:
                        cls = ""
                path_class_map[obj_path] = cls
            except:
                pass
        print("  全量资产: %d 条" % len(all_paths))
    except Exception as e:
        print("  ERROR: AssetRegistry 枚举失败: %s" % str(e)[:200])
        return

    # ====================================================================
    # 第3步: 筛选缺失的树资产路径
    #   条件: 路径含树关键词 + 不在已知清单中 + 不在跳过前缀中
    # ====================================================================
    print("\n[3/5] 筛选缺失的树资产...")
    missing_tree_paths = []
    for p in all_paths:
        if p in known_paths:
            continue
        if not is_tree_asset(p):
            continue
        if is_skipped_prefix(p):
            continue
        missing_tree_paths.append(p)

    print("  全量资产总数: %d" % len(all_paths))
    print("  已知清单已有: %d" % len(known_paths))
    print("  树关键词过滤后: 先计算中...")

    # 统计树资产总数
    all_tree = [p for p in all_paths if is_tree_asset(p)]
    already_known_tree = [p for p in all_tree if p in known_paths]
    print("  /Game/ 下树资产总数: %d" % len(all_tree))
    print("  已在清单中: %d" % len(already_known_tree))
    print("  缺失待扫描: %d" % len(missing_tree_paths))

    if not missing_tree_paths:
        print("\n  没有发现缺失的树资产, 无需扫描!")
        # 输出空结果 (让合并脚本知道扫描已完成)
        output = {"assets": [], "stats": {"total": 0, "loaded": 0, "failed": 0},
                  "message": "no_missing_trees_found", "scan_time": time.time() - start_time}
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print("SCAN_MISSING_TREES_DONE (no missing)")
        return

    # ====================================================================
    # 第4步: 加载并扫描缺失的树资产
    # ====================================================================
    print("\n[4/5] 加载并提取缺失树资产参数...")
    catalog = []
    stats = {"total": len(missing_tree_paths), "loaded": 0, "failed": 0,
             "by_class": {}, "by_category": {}, "by_path_root": {}}

    for i, asset_path in enumerate(missing_tree_paths):
        if i % 20 == 0:
            print("  处理 %d/%d..." % (i, len(missing_tree_paths)))

        entry = {"path": asset_path}

        # 路径解析
        parts = asset_path.split("/")
        entry["folder"] = parts[1] if len(parts) > 1 else "root"
        entry["subfolder"] = parts[2] if len(parts) > 2 else ""
        entry["name"] = parts[-1] if parts else ""
        entry["category"] = guess_category(asset_path)

        # 路径根统计
        if len(parts) >= 3:
            root = "/".join(parts[:3])
        elif len(parts) >= 2:
            root = "/".join(parts[:2])
        else:
            root = asset_path
        stats["by_path_root"][root] = stats["by_path_root"].get(root, 0) + 1

        stats["total"] += 1

        try:
            # 跳过崩溃风险资产 (World/Landscape)
            asset_class_name = path_class_map.get(asset_path, "")
            skip_keywords = ["world", "level", "landscape"]
            if asset_class_name and any(k in asset_class_name.lower() for k in skip_keywords):
                entry["class"] = asset_class_name
                entry["status"] = "skipped_crash_risk"
                catalog.append(entry)
                continue

            obj = unreal.EditorAssetLibrary.load_asset(asset_path)
            if not obj:
                entry["status"] = "load_failed"
                stats["failed"] += 1
                catalog.append(entry)
                continue

            stats["loaded"] += 1
            obj_class = obj.__class__.__name__
            entry["class"] = obj_class
            stats["by_class"][obj_class] = stats["by_class"].get(obj_class, 0) + 1
            stats["by_category"][entry["category"]] = stats["by_category"].get(entry["category"], 0) + 1

            # 按类型分发处理
            if isinstance(obj, unreal.StaticMesh):
                handle_static_mesh(obj, entry)
            elif isinstance(obj, unreal.Blueprint):
                handle_blueprint(obj, entry)
            elif isinstance(obj, unreal.MaterialInterface):
                handle_material(obj, entry)
            elif isinstance(obj, unreal.Texture):
                handle_texture(obj, entry)

        except Exception as e:
            entry["error"] = str(e)[:200]
            stats["failed"] += 1

        catalog.append(entry)

    elapsed = time.time() - start_time

    # ====================================================================
    # 第5步: 输出增量片段
    # ====================================================================
    print("\n" + "=" * 60)
    print("[5/5] 扫描完成, 耗时 %.1f 秒" % elapsed)
    print("  缺失树资产总数: %d" % len(missing_tree_paths))
    print("  成功加载: %d, 失败: %d" % (stats["loaded"], stats["failed"]))

    print("\n按类型:")
    for cls, cnt in sorted(stats["by_class"].items(), key=lambda x: -x[1]):
        print("  %s: %d" % (cls, cnt))

    print("\n按路径根:")
    for root, cnt in sorted(stats["by_path_root"].items(), key=lambda x: -x[1]):
        print("  %s: %d" % (root, cnt))

    # 重点: 列出有物理尺寸的 StaticMesh 树
    sm_trees = [a for a in catalog if a.get("class") == "StaticMesh" and "dimensions_xyz" in a]
    if sm_trees:
        print("\n有物理尺寸的静态网格树 (%d 个):" % len(sm_trees))
        for a in sorted(sm_trees, key=lambda x: x.get("max_dimension", 0), reverse=True):
            print("  %s" % a["path"])
            print("    尺寸: %s, 最大: %.1f" % (a.get("dimensions_xyz", []), a.get("max_dimension", 0)))
            print("    单位: %s, 朝向: %s" % (a.get("likely_unit", "-"), a.get("orientation", "-")))
            print("    原点: %s, 材质数: %d" % (a.get("origin_z", "-"), a.get("material_count", 0)))

    output = {
        "assets": catalog,
        "stats": stats,
        "known_paths_count": len(known_paths),
        "all_tree_count": len(all_tree),
        "missing_tree_count": len(missing_tree_paths),
        "scan_time": elapsed,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("\n增量片段已写入: %s" % OUTPUT_PATH)
    print("SCAN_MISSING_TREES_DONE")


main()