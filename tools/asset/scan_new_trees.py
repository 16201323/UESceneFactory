# ============================================================================
# scan_new_trees.py - 新导入树资产增量扫描脚本
# ============================================================================
# 功能: 仅扫描用户手动导入的4个树资产路径, 提取包围盒/材质/朝向等参数
# 输出: new_tree_assets.json (增量JSON片段, 供 merge_new_assets.py 合并)
# 用法: 在UE5编辑器中 Python 控制台执行
#         py "c:/Users/25868/Desktop/UE5/UESceneFactory/tools/asset/scan_new_trees.py"
# ============================================================================

import unreal
import json
import time

# 输出路径 (增量片段)
OUTPUT_PATH = "c:/Users/25868/Desktop/UE5/UESceneFactory/tools/asset/new_tree_assets.json"

# 待扫描的4个内容路径
SCAN_PATHS = [
    "/Game/Stylized_Tree_Pack",
    "/Game/HighPoly_Tree_Model",
    "/Game/Fab/Maple_Tree_Scan_Trunk_4_LOD",
    "/Game/PN_interactiveSpruceForest",
]

# ============================================================================
# 从 asset_audit.py 复用的工具函数
# ============================================================================

def guess_category(folder, subfolder, name):
    """根据路径和名称推测资产类别 (与 asset_audit.py 一致)"""
    s = (folder + "/" + subfolder + "/" + name).lower()
    if "tree" in s or "pine" in s or "foliage" in s or "oak" in s or "birch" in s or "maple" in s or "spruce" in s:
        return "vegetation_tree"
    if "wheat" in s or "crop" in s or "grass" in s or "bush" in s or "plant" in s:
        return "vegetation_crop"
    if "house" in s or "cabin" in s or "hourse" in s or "rural" in s:
        return "building"
    if "fence" in s or "wire" in s:
        return "fence"
    if "material" in s:
        return "material"
    if "texture" in s:
        return "texture"
    if "blueprint" in s or s.startswith("bp_"):
        return "blueprint"
    return "other"


def handle_static_mesh(mesh, entry):
    """获取 StaticMesh 的包围盒/材质/朝向/原点信息 (与 asset_audit.py 一致)"""
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
        entry["bounds_error"] = str(e)

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
            entry["bounds_error2"] = str(e2)

    if got_bounds:
        dims = entry["dimensions_xyz"]
        max_d = entry["max_dimension"]

        # 尺寸单位推测
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

        # 朝向分析
        dx, dy, dz = dims
        if dz > dx * 2 and dz > dy * 2:
            entry["orientation"] = "standing_tall (竖立)"
        elif dx > dz * 3 and dy > dz * 3:
            entry["orientation"] = "flat_horizontal (平躺)"
        elif abs(dx - dz) < max(dx, dz) * 0.2 and abs(dy - dz) < max(dy, dz) * 0.2:
            entry["orientation"] = "cube_like (立方体)"
        else:
            entry["orientation"] = "mixed (混合)"

        # 原点偏移分析
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
    """获取蓝图组件和网格引用信息"""
    try:
        gen_class = bp.generated_class()
        if gen_class:
            entry["generated_class"] = str(gen_class.get_name())
    except Exception as e:
        entry["bp_class_error"] = str(e)

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
        entry["bp_component_error"] = str(e)


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
    print("SCAN_NEW_TREES_START")
    print("扫描路径: %s" % SCAN_PATHS)

    # 构建 AssetRegistry 类名映射 (避免加载 World/Landscape 导致崩溃)
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    path_class_map = {}
    try:
        all_asset_data = registry.get_assets_by_path("/Game/", True)
        for ad in all_asset_data:
            try:
                pkg_name = str(ad.get_editor_property('package_name'))
                asset_name_str = str(ad.get_editor_property('asset_name'))
                obj_path = pkg_name + "." + asset_name_str
                cls = ""
                try:
                    cp = ad.get_editor_property('asset_class_path')
                    cls = str(cp.asset_name)
                except:
                    try:
                        cls = str(ad.asset_class)
                    except:
                        cls = ""
                path_class_map[obj_path] = cls
            except:
                pass
        print("AssetRegistry class map: %d 条目" % len(path_class_map))
    except Exception as e:
        print("WARN: get_assets_by_path 失败: %s" % str(e)[:100])

    # 逐路径扫描
    catalog = []
    stats = {"total": 0, "loaded": 0, "failed": 0, "by_class": {}, "by_category": {}, "by_path_root": {}}

    for scan_path in SCAN_PATHS:
        print("\n--- 扫描: %s ---" % scan_path)
        try:
            path_assets = unreal.EditorAssetLibrary.list_assets(scan_path, recursive=True)
            print("  发现资产数: %d" % len(path_assets))
        except Exception as e:
            print("  ERROR: 列出资产失败: %s" % str(e)[:200])
            continue

        for i, asset_path in enumerate(path_assets):
            if i % 50 == 0:
                print("  处理 %d/%d..." % (i, len(path_assets)))

            stats["total"] += 1
            entry = {"path": asset_path}

            # 路径解析
            parts = asset_path.split("/")
            entry["folder"] = parts[1] if len(parts) > 1 else "root"
            entry["subfolder"] = parts[2] if len(parts) > 2 else ""
            entry["name"] = parts[-1] if parts else ""

            # 类别推测
            entry["category"] = guess_category(entry["folder"], entry["subfolder"], entry["name"])

            # 路径根统计
            root = "/".join(parts[:3]) if len(parts) >= 3 else scan_path
            stats["by_path_root"][root] = stats["by_path_root"].get(root, 0) + 1

            try:
                # 跳过崩溃风险资产
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

    # 打印摘要
    print("\n" + "=" * 60)
    print("扫描完成, 耗时 %.1f 秒" % elapsed)
    print("总数: %d, 成功: %d, 失败: %d" % (stats["total"], stats["loaded"], stats["failed"]))
    print("\n按类型:")
    for cls, cnt in sorted(stats["by_class"].items(), key=lambda x: -x[1]):
        print("  %s: %d" % (cls, cnt))
    print("\n按类别:")
    for cat, cnt in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
        print("  %s: %d" % (cat, cnt))
    print("\n按路径根:")
    for root, cnt in sorted(stats["by_path_root"].items(), key=lambda x: -x[1]):
        print("  %s: %d" % (root, cnt))

    # 输出 JSON 片段
    output = {"assets": catalog, "stats": stats, "scan_paths": SCAN_PATHS, "scan_time": elapsed}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("\n增量片段已写入: %s" % OUTPUT_PATH)
    print("SCAN_NEW_TREES_DONE")


main()