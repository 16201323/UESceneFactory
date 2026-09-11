import unreal, os, sys

log_path = os.environ.get("MAPFORGE_LOG", os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "mapforge_diagnose_landscape.log"))

def log(msg):
    line = "[DIAG] " + str(msg)
    print(line, flush=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

log("=" * 60)
log("Landscape 诊断+修复脚本启动")
log("=" * 60)

# 清空日志
with open(log_path, "w", encoding="utf-8") as f:
    f.write("")

log("DIAGNOSE_START")

# 目标关卡路径
target_level = "/Game/MapForgeTest/GB_SmartAgriField2km"

# 加载关卡
try:
    unreal.EditorAssetLibrary.load_asset(target_level)
    unreal.EditorLevelLibrary.load_level(target_level)
    log("关卡已加载: " + target_level)
except Exception as e:
    log("加载关卡失败: " + str(e))
    sys.exit(1)

# 查找 Landscape Actor
landscape_actors = unreal.GameplayStatics.get_all_actors_of_class(
    unreal.EditorLevelLibrary.get_editor_world(),
    unreal.Landscape
)

log("找到 Landscape Actor 数量: " + str(len(landscape_actors)))

if len(landscape_actors) == 0:
    log("错误: 未找到 Landscape Actor!")
    sys.exit(1)

landscape = landscape_actors[0]
log("Landscape 名称: " + landscape.get_name())

# 检查材质
mat = landscape.get_editor_property("landscape_material")
if mat:
    log("当前材质: " + mat.get_path_name())
    # 检查父材质
    if hasattr(mat, 'get_editor_property'):
        try:
            parent = mat.get_editor_property("parent")
            if parent:
                log("父材质: " + parent.get_path_name())
                # 检查父材质是否已编译
                try:
                    # 重新编译材质
                    material_interface = parent
                    # 尝试获取材质表达式集合
                    log("尝试重新编译父材质...")
                    # 使用 ContentBundleUtils 或 AssetEditorManager 重新编译
                    unreal.EditorAssetLibrary.save_asset(parent.get_path_name())
                    log("父材质已保存 (触发重编译)")
                except Exception as e:
                    log("父材质操作失败: " + str(e))
        except Exception as e:
            log("获取父材质失败: " + str(e))
else:
    log("警告: Landscape 没有材质! 尝试设置...")
    try:
        mat_path = "/Game/RuralHouse/Landscape/MI_Landscape"
        new_mat = unreal.EditorAssetLibrary.load_asset(mat_path)
        if new_mat:
            landscape.set_editor_property("landscape_material", new_mat)
            log("材质已重新设置: " + mat_path)
        else:
            log("无法加载材质: " + mat_path)
    except Exception as e:
        log("设置材质失败: " + str(e))

# 检查 bGrassEnabled
try:
    grass_enabled = landscape.get_editor_property("grass_enabled")
    log("bGrassEnabled: " + str(grass_enabled))
    if not grass_enabled:
        landscape.set_editor_property("grass_enabled", True)
        log("已设置 bGrassEnabled = True")
except Exception as e:
    log("获取 grass_enabled 失败: " + str(e))
    try:
        # 尝试通过路径设置
        landscape.set_editor_property("grass_enabled", True)
        log("已设置 bGrassEnabled = True (通过 set_editor_property)")
    except Exception as e2:
        log("设置 grass_enabled 也失败: " + str(e2))

# 获取 LandscapeInfo
try:
    landscape_info = landscape.get_landscape_info()
    if landscape_info:
        log("LandscapeInfo: " + landscape_info.get_name())
        # 检查图层
        try:
            layers = landscape_info.get_editor_property("layers")
            log("LandscapeInfo 图层数: " + str(len(layers)) if layers else "0")
        except:
            log("无法获取 layers 属性")
    else:
        log("LandscapeInfo 为空!")
except Exception as e:
    log("获取 LandscapeInfo 失败: " + str(e))

# 尝试通过 ULandscapeSubsystem 重新生成草地
try:
    world = unreal.EditorLevelLibrary.get_editor_world()
    # 获取 Landscape Subsystem
    subsystem = unreal.get_engine_subsystem(unreal.LandscapeSubsystem) if hasattr(unreal, 'LandscapeSubsystem') else None
    if subsystem:
        log("找到 ULandscapeSubsystem")
        # 尝试调用 RegenerateGrass
        try:
            subsystem.execute_console_command("grass.RegenerateGrass true") if hasattr(subsystem, 'execute_console_command') else None
        except:
            pass
    else:
        log("未找到 ULandscapeSubsystem (Python API 可能不支持)")
except Exception as e:
    log("Subsystem 操作失败: " + str(e))

# 通过控制台命令强制重建草地
try:
    # 使用控制台命令刷新草地
    unreal.SystemLibrary.execute_console_command(
        unreal.EditorLevelLibrary.get_editor_world(),
        "grass.RefreshGrass"
    )
    log("已执行 grass.RefreshGrass 控制台命令")
except Exception as e:
    log("grass.RefreshGrass 失败: " + str(e))

try:
    unreal.SystemLibrary.execute_console_command(
        unreal.EditorLevelLibrary.get_editor_world(),
        "grass.Enable 1"
    )
    log("已执行 grass.Enable 1 控制台命令")
except Exception as e:
    log("grass.Enable 1 失败: " + str(e))

# 强制更新所有 Landscape 组件
try:
    components = landscape.get_editor_property("landscape_components")
    if components:
        log("Landscape 组件数: " + str(len(components)))
    else:
        log("无法获取 landscape_components")
except Exception as e:
    log("获取组件失败: " + str(e))

# 保存关卡
try:
    unreal.EditorAssetLibrary.save_asset(target_level)
    log("关卡已保存: " + target_level)
except Exception as e:
    log("保存关卡失败: " + str(e))

try:
    unreal.EditorLevelLibrary.save_all_dirty_levels()
    log("所有脏关卡已保存")
except Exception as e:
    log("保存脏关卡失败: " + str(e))

# 保存被修改的材质
try:
    mat_path = "/Game/RuralHouse/Landscape/MI_Landscape"
    mat_obj = unreal.EditorAssetLibrary.load_asset(mat_path)
    if mat_obj:
        try:
            parent = mat_obj.get_editor_property("parent")
            if parent:
                unreal.EditorAssetLibrary.save_asset(parent.get_path_name())
                log("父材质已保存: " + parent.get_path_name())
        except:
            pass
        unreal.EditorAssetLibrary.save_asset(mat_path)
        log("材质实例已保存: " + mat_path)
except Exception as e:
    log("保存材质失败: " + str(e))

log("DIAGNOSE_DONE")
