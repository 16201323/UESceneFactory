# ============================================================================
# import_polyhaven.py - Poly Haven CC0 资产批量导入脚本
# ============================================================================
# 功能: 将 DownloadedAssets/PolyHaven/ 下所有 FBX 模型导入 UE5 项目
#   - 导入 FBX 网格 + 贴图 + 材质
#   - 自动修复贴图压缩设置 (Normalmap 翻转绿通道, Roughness 灰度等)
#   - 保存所有导入的资产
# 用法: UnrealEditor-Cmd.exe proj -unattended -nop4 -nosplash -nullrhi -stdout -log
#         -ExecCmds="py import_polyhaven.py | quit"
# ============================================================================

import unreal
import os
import time
import traceback

LOG_PATH = "c:/Users/25868/Desktop/UE5/import_polyhaven.log"
BASE_DIR = "c:/Users/25868/Desktop/UE5/DownloadedAssets/PolyHaven"
UE_BASE = "/Game/PolyHaven"

# 22 个已下载的 Poly Haven CC0 模型
MODELS = [
    "Dandelion", "Celandine", "FlowerGazania", "FlowerUrsinia",
    "FlowerHeliophila", "Periwinkle", "GrassBermuda", "GrassMedium",
    "Moss", "WeedPlant", "Shrub01", "Shrub02", "Shrub03",
    "Nettle", "Fern", "PineSaplingMed", "FirSapling", "TreeSmall",
    "TreeStump", "DeadTreeTrunk", "Boulder", "Rock07"
]

# 模型分类 (用于日志和资产清单)
CATEGORIES = {
    "Dandelion": "flower", "Celandine": "flower",
    "FlowerGazania": "flower", "FlowerUrsinia": "flower",
    "FlowerHeliophila": "flower", "Periwinkle": "flower",
    "GrassBermuda": "grass", "GrassMedium": "grass",
    "Moss": "grass", "WeedPlant": "grass",
    "Shrub01": "shrub", "Shrub02": "shrub", "Shrub03": "shrub",
    "Nettle": "shrub", "Fern": "shrub",
    "PineSaplingMed": "tree", "FirSapling": "tree",
    "TreeSmall": "tree", "TreeStump": "tree",
    "DeadTreeTrunk": "tree",
    "Boulder": "rock", "Rock07": "rock"
}

# ---- 日志 ----
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()


def get_texture_settings(tex_name):
    """根据贴图文件名后缀返回正确的压缩设置
    返回: (compression_settings_enum, srgb_bool, flip_green_bool)
    Poly Haven 命名规则:
      _diff_     = Diffuse/Albedo (sRGB)
      _nor_gl_   = Normal OpenGL (需翻转绿通道 Y+ -> Y-)
      _rough_    = Roughness (Linear)
      _alpha_    = Alpha/Opacity Mask (Linear)
      _mask_     = Mask (Linear)
      _disp_     = Displacement (Linear)
      _translucency_ = Translucency/SSS (Linear)
      _opacity_  = Opacity (Linear)
    """
    n = tex_name.lower()

    # 法线贴图: OpenGL 格式, 需翻转绿通道
    if "_nor_gl_" in n or "_normal" in n or "_nor_" in n:
        return (unreal.TextureCompressionSettings.TC_NORMALMAP, False, True)

    # 漫反射/基色: sRGB 颜色
    if "_diff_" in n or "_albedo" in n or "_color" in n or "_basecolor" in n:
        return (unreal.TextureCompressionSettings.TC_DEFAULT, True, False)

    # 粗糙度: 线性灰度
    if "_rough_" in n or "_roughness" in n:
        return (unreal.TextureCompressionSettings.TC_GRAYSCALE, False, False)

    # Alpha/遮罩/不透明度: 线性灰度
    if "_alpha_" in n or "_mask_" in n or "_opacity_" in n:
        return (unreal.TextureCompressionSettings.TC_GRAYSCALE, False, False)

    # 置换贴图: 线性
    if "_disp_" in n or "_displacement" in n:
        return (unreal.TextureCompressionSettings.TC_DISPLACEMENTMAP, False, False)

    # 半透明/SSS: 线性颜色
    if "_translucency_" in n or "_translucency" in n:
        return (unreal.TextureCompressionSettings.TC_DEFAULT, False, False)

    # 默认: 假设是 sRGB 颜色
    return (unreal.TextureCompressionSettings.TC_DEFAULT, True, False)


def safe_set(obj, prop, val):
    """安全设置编辑器属性，若属性不存在则跳过并记录警告
    避免因 UE 版本差异导致整个导入流程中断"""
    try:
        obj.set_editor_property(prop, val)
        return True
    except Exception as e:
        log("    [WARN] 属性设置跳过 %s.%s = %s (%s)" % (
            obj.__class__.__name__, prop, repr(val)[:50], str(e)[:80]))
        return False


def import_model(model_name, asset_tools):
    """导入单个模型的 FBX 文件"""
    model_dir = os.path.join(BASE_DIR, model_name)

    if not os.path.exists(model_dir):
        log("  [ERROR] 目录不存在: " + model_dir)
        return {"success": False, "meshes": [], "textures": [], "materials": []}

    # 查找 FBX 文件
    fbx_files = [f for f in os.listdir(model_dir) if f.lower().endswith('.fbx')]
    if not fbx_files:
        log("  [ERROR] 未找到 FBX 文件: " + model_dir)
        return {"success": False, "meshes": [], "textures": [], "materials": []}

    fbx_path = os.path.join(model_dir, fbx_files[0])
    dest_path = UE_BASE + "/" + model_name

    # 记录导入前已有的资产 (用于后续对比)
    before_assets = set(unreal.EditorAssetLibrary.list_assets(dest_path, recursive=True)) if unreal.EditorAssetLibrary.does_directory_exist(dest_path) else set()

    log("  FBX: " + fbx_files[0])
    log("  目标: " + dest_path)

    # 创建导入任务
    task = unreal.AssetImportTask()
    task.set_editor_property('filename', fbx_path)
    task.set_editor_property('destination_path', dest_path)
    task.set_editor_property('save', True)
    task.set_editor_property('replace_existing', True)
    task.set_editor_property('automated', True)
    task.set_editor_property('replace_existing_settings', True)

    # FBX 导入选项
    fbx_options = unreal.FbxImportUI()
    fbx_options.set_editor_property('import_mesh', True)
    fbx_options.set_editor_property('import_as_skeletal', False)
    fbx_options.set_editor_property('import_materials', True)
    fbx_options.set_editor_property('import_textures', True)
    fbx_options.set_editor_property('import_animations', False)
    # 是否导入顶点色 (Poly Haven 资产含顶点色用于风场, 保留)
    safe_set(fbx_options, 'import_vertex_colors', True)

    # 静态网格导入选项 - 使用 safe_set 包裹可选属性
    sm_data = unreal.FbxStaticMeshImportData()
    safe_set(sm_data, 'combine_meshes', True)
    # remove_degenerate_materials 在 UE5.8 已不存在, 不再设置
    safe_set(sm_data, 'generate_lightmap_u_vs', False)
    safe_set(sm_data, 'build_scale3d', [1.0, 1.0, 1.0])
    # 保留顶点法线和切线, 避免光照异常
    safe_set(sm_data, 'compute_weighted_normals', True)
    safe_set(sm_data, 'reorder_materials_to_fbx_order', False)
    fbx_options.set_editor_property('static_mesh_import_data', sm_data)

    # 贴图导入选项 - 使用 safe_set 包裹可选属性
    tex_data = unreal.FbxTextureImportData()
    safe_set(tex_data, 'invert_normal_maps', False)
    safe_set(tex_data, 'material_search_locally', True)
    safe_set(fbx_options, 'texture_data', tex_data)

    task.set_editor_property('options', fbx_options)

    # 执行导入
    try:
        asset_tools.import_asset_tasks([task])
    except Exception as e:
        log("  [ERROR] 导入失败: " + str(e))
        log(traceback.format_exc())
        return {"success": False, "meshes": [], "textures": [], "materials": []}

    # 检查导入错误 (用安全方式获取, 避免属性不存在导致中断)
    try:
        had_errors = task.get_editor_property('has_errors')
        if had_errors:
            log("  [WARNING] 导入过程有警告/错误, 但部分资产可能已导入")
    except Exception:
        pass

    # 修复贴图设置
    tex_info = fix_textures(dest_path, model_name)

    # 收集导入的网格和材质
    after_assets = unreal.EditorAssetLibrary.list_assets(dest_path, recursive=True)
    meshes = []
    materials = []
    textures = []

    for asset_path in after_assets:
        obj = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not obj:
            continue
        if isinstance(obj, unreal.StaticMesh):
            meshes.append(asset_path)
        elif isinstance(obj, unreal.MaterialInterface):
            materials.append(asset_path)
        elif isinstance(obj, unreal.Texture2D):
            textures.append(asset_path)

    log("  导入结果: %d 网格, %d 材质, %d 贴图" % (len(meshes), len(materials), len(textures)))

    # 保存所有资产
    for asset_path in after_assets:
        try:
            unreal.EditorAssetLibrary.save_asset(asset_path)
        except Exception:
            pass

    return {"success": True, "meshes": meshes, "textures": textures, "materials": materials}


def fix_textures(folder_path, model_name):
    """修复文件夹内所有贴图的压缩设置"""
    result = []

    if not unreal.EditorAssetLibrary.does_directory_exist(folder_path):
        return result

    textures = unreal.EditorAssetLibrary.list_assets(folder_path, recursive=True)
    for tex_path in textures:
        try:
            obj = unreal.EditorAssetLibrary.load_asset(tex_path)
            if not obj or not isinstance(obj, unreal.Texture2D):
                continue

            tex_name = obj.get_name()
            comp, srgb, flip_green = get_texture_settings(tex_name)

            changed = False

            # 设置压缩格式
            current_comp = obj.get_editor_property('compression_settings')
            if current_comp != comp:
                obj.set_editor_property('compression_settings', comp)
                changed = True

            # 设置 sRGB
            current_srgb = obj.get_editor_property('srgb')
            if current_srgb != srgb:
                obj.set_editor_property('srgb', srgb)
                changed = True

            # 翻转绿通道 (法线贴图)
            if flip_green:
                try:
                    current_flip = obj.get_editor_property('flip_green_channel')
                    if not current_flip:
                        obj.set_editor_property('flip_green_channel', True)
                        changed = True
                except Exception:
                    pass

            if changed:
                # 标记为脏并保存
                unreal.EditorAssetLibrary.save_asset(tex_path)
                comp_name = str(comp).split('.')[-1] if '.' in str(comp) else str(comp)
                log("    贴图修复: " + tex_name + " -> " + comp_name + " (srgb=" + str(srgb) + ", flip_g=" + str(flip_green) + ")")
                result.append(tex_name)

        except Exception as e:
            log("    [WARNING] 贴图设置失败: " + tex_path + " - " + str(e))

    return result


def collect_mesh_info(mesh_path):
    """获取网格的包围盒信息"""
    info = {"path": mesh_path}
    try:
        mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
        if not mesh:
            return info

        bounds = mesh.get_bounds()
        extent = bounds.box_extent
        origin = bounds.origin

        dim_x = round(extent.x * 2, 2)
        dim_y = round(extent.y * 2, 2)
        dim_z = round(extent.z * 2, 2)
        info["dimensions_xyz"] = [dim_x, dim_y, dim_z]
        info["max_dimension"] = max(dim_x, dim_y, dim_z)

        # 尺寸单位推测
        max_d = info["max_dimension"]
        if max_d < 5:
            info["likely_unit"] = "meters (需x100缩放)"
        elif max_d < 50:
            info["likely_unit"] = "meters_or_small_cm (需x100缩放)"
        elif max_d < 500:
            info["likely_unit"] = "centimeters (可能正确)"
        else:
            info["likely_unit"] = "centimeters (大物体)"

        # 原点位置
        z_min = round(origin.z - extent.z, 2)
        z_max = round(origin.z + extent.z, 2)
        if z_min >= 0:
            info["origin_z"] = "bottom"
        elif abs(z_min) < 1.0 and abs(z_max) > 1.0:
            info["origin_z"] = "near_bottom"
        elif z_max <= 0:
            info["origin_z"] = "top"
        else:
            info["origin_z"] = "center"
            info["z_offset"] = z_max

        # 材质列表
        try:
            mats = mesh.get_editor_property("static_materials")
            mat_names = []
            if mats:
                for m in mats:
                    if m.material_interface:
                        mat_names.append(str(m.material_interface.get_path_name()))
            info["materials"] = mat_names
            info["material_count"] = len(mat_names)
        except Exception:
            info["materials"] = []
            info["material_count"] = 0

    except Exception as e:
        info["error"] = str(e)[:200]

    return info


# ============================================================================
# 主函数
# ============================================================================
def main():
    log("=" * 60)
    log("Poly Haven CC0 资产批量导入")
    log("=" * 60)
    log("源目录: " + BASE_DIR)
    log("目标目录: " + UE_BASE)
    log("模型数量: " + str(len(MODELS)))
    log("")

    start_time = time.time()
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()

    results = []
    success_count = 0
    fail_count = 0

    for i, model in enumerate(MODELS):
        log("[%d/%d] %s (类别: %s)" % (i + 1, len(MODELS), model, CATEGORIES.get(model, "unknown")))
        try:
            result = import_model(model, asset_tools)
            result["model"] = model
            result["category"] = CATEGORIES.get(model, "unknown")
            results.append(result)
            if result["success"]:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            log("  [ERROR] " + str(e))
            log(traceback.format_exc())
            results.append({"model": model, "success": False, "error": str(e)})
            fail_count += 1
        log("")

    elapsed = time.time() - start_time

    # 汇总报告
    log("=" * 60)
    log("导入完成汇总")
    log("=" * 60)
    log("成功: %d / %d" % (success_count, len(MODELS)))
    log("失败: %d / %d" % (fail_count, len(MODELS)))
    log("耗时: %.1f 秒" % elapsed)
    log("")

    # 逐模型详情
    log("逐模型详情:")
    total_meshes = 0
    total_textures = 0
    total_materials = 0
    for r in results:
        if r["success"]:
            nm = len(r["meshes"])
            nt = len(r["textures"])
            nmat = len(r["materials"])
            total_meshes += nm
            total_textures += nt
            total_materials += nmat
            log("  %s: %d 网格, %d 材质, %d 贴图" % (r["model"], nm, nmat, nt))
        else:
            log("  %s: FAILED" % r["model"])

    log("")
    log("总资产: %d 网格, %d 材质, %d 贴图" % (total_meshes, total_materials, total_textures))

    # 收集网格尺寸信息 (用于资产清单)
    log("")
    log("网格尺寸信息:")
    for r in results:
        if not r["success"]:
            continue
        for mesh_path in r["meshes"]:
            info = collect_mesh_info(mesh_path)
            log("  %s | %s | %s" % (
                info.get("path", "?"),
                info.get("dimensions_xyz", "?"),
                info.get("likely_unit", "?")))

    log("")
    log("IMPORT_POLYHAVEN_DONE")
    _f.close()


main()
