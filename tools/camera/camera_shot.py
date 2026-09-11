import unreal
import os
import time

LOG_PATH = "c:/Users/25868/Desktop/UE5/camera_shot.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    _f.write(str(msg) + "\n")
    _f.flush()

try:
    eal = unreal.EditorLevelLibrary
    world = eal.get_editor_world()
    actors = eal.get_all_level_actors()
    log("actors: " + str(len(actors)))
    eal.set_selected_level_actors(actors)

    # 探索 LevelEditorSubsystem 的视口相关方法
    try:
        les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        all_methods = [m for m in dir(les) if not m.startswith('_')]
        view_methods = [m for m in all_methods if any(k in m.lower() for k in ['view','camera','persp','viewport','lookat','set_loc','set_rot'])]
        log("LES view_methods: " + str(view_methods))
        # 尝试常见方法
        for m in ['set_view_location','set_view_rotation','set_view_location_and_rotation','get_active_viewport','focus_viewport_on_selection','frame_selected']:
            if hasattr(les, m):
                log("  LES has: " + m)
    except Exception as e:
        log("LES fail: " + str(e))

    # 探索 UnrealEdSubsystem
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEdSubsystem)
        if ues:
            ues_methods = [m for m in dir(ues) if not m.startswith('_')]
            ues_view = [m for m in ues_methods if any(k in m.lower() for k in ['view','camera','persp','viewport'])]
            log("UES view_methods: " + str(ues_view))
    except Exception as e:
        log("UES fail: " + str(e))

    # 尝试通过 console 命令框选视口 (某些 UE 版本支持)
    try:
        unreal.SystemLibrary.execute_console_command(world, "FRAME_SELECTED")
        log("FRAME_SELECTED sent")
    except:
        pass

    # 直接用 SHOT 命令截图 (比 screenshot 更可靠)
    try:
        unreal.SystemLibrary.execute_console_command(world, "SHOT FarmingVillage")
        log("SHOT command sent")
    except Exception as e:
        log("SHOT fail: " + str(e))

    # 也用 screenshot 命令
    try:
        unreal.SystemLibrary.execute_console_command(world, "screenshot FarmingVillage")
        log("screenshot with name sent")
    except Exception as e:
        log("screenshot_name fail: " + str(e))

    time.sleep(3)
    log("CAMERA_SHOT_DONE")

except Exception as e:
    log("ERROR: " + str(e))
    import traceback
    log(traceback.format_exc())

_f.close()
