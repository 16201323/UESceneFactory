import unreal
import sys
import traceback

LOG_PATH = "c:/Users/25868/Desktop/UE5/colorize_stdout.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    line = str(msg)
    print(line)
    _f.write(line + "\n")
    _f.flush()

log("COLORIZE_START_V4")

COLORS = {
    'Red': (1.0, 0.0, 0.0),
    'Green': (0.0, 1.0, 0.0),
    'Blue': (0.0, 0.4, 1.0),
    'Yellow': (1.0, 1.0, 0.0)
}
PACKAGE = '/Game/MapForgeTest'
LEVEL_PATH = '/Game/MapForgeTest/GB_SimpleScene'

all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
log("ACTOR_COUNT: " + str(len(all_actors)))
actor_map = {}
for a in all_actors:
    nm = a.get_name()
    lbl = ""
    try:
        lbl = a.get_actor_label()
    except Exception:
        pass
    actor_map[nm] = a
    if lbl:
        actor_map[lbl] = a

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
editing = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
log("got tools")

for color_name, rgb in COLORS.items():
    try:
        mat_name = 'M_' + color_name
        mat_path = PACKAGE + '/' + mat_name
        log("=== PROCESSING " + color_name + " ===")

        # 创建或加载材质
        if eal.does_asset_exist(mat_path):
            material = eal.load_asset(mat_path)
            log("MATERIAL_EXISTS: " + mat_name)
        else:
            material = asset_tools.create_asset(mat_name, PACKAGE, unreal.Material, None)
            log("MATERIAL_CREATED: " + mat_name)

        # 创建颜色表达式 + 设色 + 连接 + 编译
        color_expr = editing.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -200, 0)
        lc = unreal.LinearColor()
        lc.r = rgb[0]; lc.g = rgb[1]; lc.b = rgb[2]; lc.a = 1.0
        color_expr.set_editor_property('constant', lc)
        editing.connect_material_property(color_expr, '', unreal.MaterialProperty.MP_BASE_COLOR)
        editing.recompile_material(material)
        log("  material built")

        # 保存材质资产到磁盘
        try:
            eal.save_loaded_asset(material)
            log("  material saved to disk")
        except Exception as e1:
            log("  save material failed: " + str(e1))

        # 赋给 actor
        actor_name = 'GB_Cube_' + color_name
        actor = actor_map.get(actor_name)
        if not actor:
            for a in all_actors:
                try:
                    if actor_name in a.get_actor_label():
                        actor = a
                        break
                except Exception:
                    pass
        if actor:
            mesh = actor.static_mesh_component
            if mesh:
                # 设 override material
                mesh.set_material(0, material)
                # 验证是否生效
                applied = mesh.get_material(0)
                applied_name = applied.get_name() if applied else "None"
                log("  applied material on " + actor_name + ": " + applied_name)
                # 显式标记 actor / component dirty, 确保 save 序列化 override
                try:
                    actor.modify()
                except Exception as e2:
                    log("  actor.modify failed: " + str(e2))
                try:
                    mesh.modify()
                except Exception as e3:
                    log("  mesh.modify failed: " + str(e3))
                log("ACTOR_COLORED: " + actor_name)
            else:
                log("NO_MESH_COMPONENT: " + actor_name)
        else:
            log("ACTOR_NOT_FOUND: " + actor_name)
    except Exception as e:
        log("ERROR_" + color_name + ": " + str(e))
        log(traceback.format_exc())

# 保存关卡: save_all_dirty_levels + 强制 save_asset 关卡包
try:
    unreal.EditorLevelLibrary.save_all_dirty_levels()
    log("save_all_dirty_levels done")
except Exception as e:
    log("save_all_dirty_levels failed: " + str(e))

try:
    eal.save_asset(LEVEL_PATH)
    log("save_asset(LEVEL) done")
except Exception as e:
    log("save_asset(LEVEL) failed: " + str(e))
    # 备选: save_asset_by_package_name
    try:
        eal.save_asset_by_package_name(LEVEL_PATH)
        log("save_asset_by_package_name done")
    except Exception as e4:
        log("save_asset_by_package_name failed: " + str(e4))

log("COLORIZE_DONE")
_f.flush()
_f.close()
