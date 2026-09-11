# ============================================================================
# asset_audit.py - 资产清查脚本
# ============================================================================
# 功能: 枚举 /Game/ 下所有资产, 获取每种资产的详细信息:
#   - StaticMesh: 包围盒/尺寸/尺寸单位推测/朝向/材质/类别
#   - Blueprint: 生成类/CDO组件/网格引用/尺寸
#   - Material: 材质类型/着色模型
#   - Texture: 纹理尺寸
# 输出: asset_catalog.json (完整资产目录) + asset_audit.log (日志)
# 用法: UnrealEditor-Cmd.exe proj -unattended -nop4 -nosplash -nullrhi -stdout -log
#         -ExecCmds="py asset_audit.py | quit"
# ============================================================================

import unreal
import json
import os
import time
import math

LOG_PATH = "c:/Users/25868/Desktop/UE5/asset_audit.log"
OUTPUT_PATH = "c:/Users/25868/Desktop/UE5/MapForgeTest/asset_catalog.json"

_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()


# ---- 分类推测: 根据路径名和资产名推测资产类别 ----
def guess_category(folder, subfolder, name):
    """根据路径和名称推测资产类别"""
    s = (folder + "/" + subfolder + "/" + name).lower()
    if "tree" in s or "pine" in s or "foliage" in s or "oak" in s or "birch" in s or "maple" in s:
        return "vegetation_tree"
    if "wheat" in s or "crop" in s or "grass" in s or "bush" in s or "plant" in s:
        return "vegetation_crop"
    if "house" in s or "cabin" in s or "hourse" in s or "rural" in s:
        return "building"
    if "fence" in s or "wire" in s:
        return "fence"
    if "heliport" in s or "helipad" in s or "helicopter" in s:
        return "heliport"
    if "tower" in s and "comm" in s:
        return "communication_tower"
    if "tower" in s and "voltage" in s or "high_voltage" in s:
        return "high_voltage_tower"
    if "panel" in s or "photo" in s or "solar" in s:
        return "solar_panel"
    if "floor" in s or "ground" in s or "terrain" in s or "land" in s:
        return "ground"
    if "prop" in s or "generator" in s or "electric" in s or "air" in s:
        return "props_equipment"
    if "material" in s:
        return "material"
    if "texture" in s:
        return "texture"
    if "blueprint" in s or s.startswith("bp_"):
        return "blueprint"
    return "other"


# ---- StaticMesh 处理: 获取包围盒/材质/朝向 ----
def handle_static_mesh(mesh, entry):
    """获取 StaticMesh 的详细信息"""
    got_bounds = False

    # 方法1: 尝试 get_bounds() — 返回 BoxSphereBounds
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

    # 方法2: 如果 get_bounds 失败, 尝试 SystemLibrary.get_object_bounds
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

        # 尺寸单位推测 (UE 默认 1unit=1cm)
        # 真实世界参考: 人高180cm, 树高500-1500cm, 房高300-1000cm
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


# ---- Blueprint 处理: 获取组件和网格引用 ----
def handle_blueprint(bp, entry):
    """获取蓝图信息: 组件/网格引用/尺寸"""
    try:
        gen_class = bp.generated_class()
        if gen_class:
            entry["generated_class"] = str(gen_class.get_name())
    except Exception as e:
        entry["bp_class_error"] = str(e)

    # 尝试获取 CDO 的组件信息
    try:
        gen_class = bp.generated_class()
        cdo = gen_class.get_default_object(True)
        if cdo and isinstance(cdo, unreal.Actor):
            components = cdo.get_components_by_class(unreal.SceneComponent)
            comp_list = []
            has_mesh = False
            for comp in components:
                comp_info = {
                    "class": comp.__class__.__name__,
                    "name": comp.get_name(),
                }
                # 获取网格组件的信息
                if isinstance(comp, unreal.MeshComponent):
                    has_mesh = True
                    try:
                        if isinstance(comp, unreal.StaticMeshComponent):
                            mesh_asset = comp.get_static_mesh()
                            if mesh_asset:
                                comp_info["mesh_path"] = str(mesh_asset.get_path_name())
                                # 获取网格尺寸
                                try:
                                    bb = mesh_asset.get_bounds()
                                    comp_info["mesh_extents"] = [
                                        round(bb.box_extent.x * 2, 2),
                                        round(bb.box_extent.y * 2, 2),
                                        round(bb.box_extent.z * 2, 2),
                                    ]
                                except:
                                    pass
                                # 获取组件相对位置
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


# ---- 材质处理 ----
def handle_material(mat, entry):
    """获取材质信息"""
    try:
        entry["shading_model"] = str(mat.get_editor_property("shading_model"))
    except:
        pass
    # 检查是否是 Landscape 材质
    try:
        if mat.is_landscape_material():
            entry["is_landscape"] = True
    except:
        pass


# ---- 纹理处理 ----
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
    log("ASSET_AUDIT_START")
    start_time = time.time()

    # 获取资产注册表实例并批量构建 路径→类名 映射 (仅读取元数据, 不触发资产加载)
    # 已知问题: 加载含 LayerInfo 不匹配的 Landscape/World 资产会触发
    # Landscape.cpp:7845 断言, 导致整个进程崩溃 (Python try-except 无法捕获)
    # 解决方案: 使用 AssetRegistry 批量获取所有资产的类信息, 在加载前跳过崩溃风险资产
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    path_class_map = {}
    try:
        # 方式1: 尝试 get_assets_by_path (recursive 作为位置参数, 不带 include_only_package_assets)
        try:
            all_asset_data = registry.get_assets_by_path("/Game/", True)
        except Exception:
            all_asset_data = registry.get_assets_by_path("/Game/")

        for ad in all_asset_data:
            try:
                # 获取 object_path 作为字典键 (使用 package_name + asset_name 组合)
                pkg_name = str(ad.get_editor_property('package_name'))
                asset_name_str = str(ad.get_editor_property('asset_name'))
                obj_path = pkg_name + "." + asset_name_str
                cls = ""
                # UE5.8 中 asset_class 已弃用, 优先尝试 asset_class_path
                try:
                    cp = ad.get_editor_property('asset_class_path')
                    cls = str(cp.asset_name)
                except Exception:
                    try:
                        cls = str(ad.asset_class)
                    except Exception:
                        try:
                            cls = str(ad.get_editor_property('asset_class'))
                        except Exception:
                            cls = ""
                path_class_map[obj_path] = cls
            except Exception:
                pass
        log("AssetRegistry class map built: %d entries (get_assets_by_path)" % len(path_class_map))
    except Exception as e:
        log("WARN: get_assets_by_path failed: %s, trying ARFilter fallback..." % str(e)[:100])
        # 方式2: 使用 get_assets() + ARFilter 回退方案
        try:
            ar_filter = unreal.ARFilter()
            ar_filter.package_paths = ["/Game/"]
            ar_filter.recursive_paths = True
            all_asset_data = registry.get_assets(ar_filter)
            for ad in all_asset_data:
                try:
                    pkg_name = str(ad.get_editor_property('package_name'))
                    asset_name_str = str(ad.get_editor_property('asset_name'))
                    obj_path = pkg_name + "." + asset_name_str
                    cls = ""
                    try:
                        cp = ad.get_editor_property('asset_class_path')
                        cls = str(cp.asset_name)
                    except Exception:
                        try:
                            cls = str(ad.asset_class)
                        except Exception:
                            cls = ""
                    path_class_map[obj_path] = cls
                except Exception:
                    pass
            log("AssetRegistry class map built: %d entries (ARFilter fallback)" % len(path_class_map))
        except Exception as e2:
            log("WARN: ARFilter fallback also failed: %s" % str(e2)[:100])

    # 1. 列出 /Game/ 下所有资产
    all_assets = unreal.EditorAssetLibrary.list_assets("/Game/", recursive=True)
    log("Total asset paths: " + str(len(all_assets)))

    catalog = []
    stats = {"total": 0, "loaded": 0, "failed": 0, "by_class": {}, "by_category": {}, "by_folder": {}}

    for i, asset_path in enumerate(all_assets):
        if i % 200 == 0:
            log("Processing %d/%d..." % (i, len(all_assets)))

        stats["total"] += 1
        entry = {"path": asset_path}

        # 从路径提取信息
        parts = asset_path.split("/")
        entry["folder"] = parts[1] if len(parts) > 1 else "root"
        entry["subfolder"] = parts[2] if len(parts) > 2 else ""
        entry["name"] = parts[-1] if parts else ""

        # 类别推测
        entry["category"] = guess_category(entry["folder"], entry["subfolder"], entry["name"])

        try:
            # 从预建的 路径→类名 映射中查找类名 (不触发加载, 避免引擎断言崩溃)
            asset_class_name = path_class_map.get(asset_path, "")

            # 跳过 World/Level/Landscape 崩溃风险资产的直接加载
            # 已知问题: 加载含 LayerInfo 不匹配的 Landscape/World 资产会触发
            # Landscape.cpp:7845 断言, 导致整个进程崩溃 (Python try-except 无法捕获)
            skip_keywords = ["world", "level", "landscape"]
            if asset_class_name and any(k in asset_class_name.lower() for k in skip_keywords):
                entry["class"] = asset_class_name
                entry["category"] = "landscape" if "landscape" in asset_class_name.lower() else entry["category"]
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

            # 更新统计
            stats["by_class"][obj_class] = stats["by_class"].get(obj_class, 0) + 1
            stats["by_category"][entry["category"]] = stats["by_category"].get(entry["category"], 0) + 1
            stats["by_folder"][entry["folder"]] = stats["by_folder"].get(entry["folder"], 0) + 1

            # 根据资产类型获取不同信息
            if isinstance(obj, unreal.StaticMesh):
                handle_static_mesh(obj, entry)
            elif isinstance(obj, unreal.Blueprint):
                handle_blueprint(obj, entry)
            elif isinstance(obj, unreal.MaterialInterface):
                handle_material(obj, entry)
            elif isinstance(obj, unreal.Texture):
                handle_texture(obj, entry)
            elif isinstance(obj, unreal.Landscape):
                entry["category"] = "landscape"

        except Exception as e:
            entry["error"] = str(e)[:200]
            stats["failed"] += 1

        catalog.append(entry)

    elapsed = time.time() - start_time
    log("Audit completed in %.1f seconds" % elapsed)
    log("Total: %d, Loaded: %d, Failed: %d" % (stats["total"], stats["loaded"], stats["failed"]))

    # 2. 写入 JSON 目录
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"assets": catalog, "stats": stats}, f, indent=2, ensure_ascii=False)
    log("Catalog written to: " + OUTPUT_PATH)

    # 3. 打印摘要
    log("\n=== BY CLASS ===")
    for cls, count in sorted(stats["by_class"].items(), key=lambda x: -x[1]):
        log("  %s: %d" % (cls, count))

    log("\n=== BY CATEGORY ===")
    for cat, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
        log("  %s: %d" % (cat, count))

    log("\n=== BY FOLDER ===")
    for folder, count in sorted(stats["by_folder"].items(), key=lambda x: -x[1]):
        log("  %s: %d" % (folder, count))

    # 4. 打印关键发现: 尺寸异常的资产
    log("\n=== ASSETS WITH LIKELY METER UNITS (need x100 scale) ===")
    for entry in catalog:
        if entry.get("likely_unit", "").startswith("meters"):
            log("  %s: dims=%s max=%.2f" % (
                entry["path"],
                entry.get("dimensions_xyz", []),
                entry.get("max_dimension", 0)))

    # 5. 打印关键发现: 竖立朝向的资产 (可能需要旋转)
    log("\n=== ASSETS WITH STANDING/TALL ORIENTATION ===")
    for entry in catalog:
        if "standing_tall" in entry.get("orientation", ""):
            log("  %s: dims=%s" % (entry["path"], entry.get("dimensions_xyz", [])))

    # 6. 打印关键发现: 原点在中心的资产 (需要 Z 偏移)
    log("\n=== ASSETS WITH CENTER ORIGIN (need Z offset) ===")
    for entry in catalog:
        if "center" in entry.get("origin_z", ""):
            log("  %s: z_offset_needed=%s" % (entry["path"], entry.get("z_offset_needed", 0)))

    # 7. 打印关键发现: 地面/地板类资产
    log("\n=== GROUND/FLOOR ASSETS ===")
    for entry in catalog:
        if entry.get("category") == "ground":
            log("  %s: dims=%s mats=%s" % (
                entry["path"],
                entry.get("dimensions_xyz", []),
                entry.get("materials", [])))

    # 8. 打印关键发现: 树木/植被资产
    log("\n=== TREE/VEGETATION ASSETS ===")
    for entry in catalog:
        if entry.get("category", "").startswith("vegetation"):
            log("  %s: dims=%s unit=%s" % (
                entry["path"],
                entry.get("dimensions_xyz", []),
                entry.get("likely_unit", "")))

    log("\nASSET_AUDIT_DONE")
    _f.close()


main()
