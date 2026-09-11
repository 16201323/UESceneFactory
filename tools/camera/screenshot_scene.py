import unreal
import os
import time

# Python open 直接写日志
LOG_PATH = "c:/Users/25868/Desktop/UE5/screenshot.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    _f.write(str(msg) + "\n")
    _f.flush()

try:
    eal = unreal.EditorLevelLibrary
    world = eal.get_editor_world()
    actors = eal.get_all_level_actors()
    log("actors: " + str(len(actors)))

    # 选中所有 actor (便于框选视口)
    try:
        eal.set_selected_level_actors(actors)
        log("selected all actors")
    except Exception as e:
        log("select fail: " + str(e))

    # 尝试获取活动视口并设置相机到一个俯瞰角度
    viewport_set = False
    try:
        viewport = eal.get_active_level_viewport()
        log("viewport obj: " + str(type(viewport)))
        if viewport:
            # 相机位置: 从东南方向俯视整个农林场景
            cam_loc = unreal.Vector(2800, -2800, 2000)
            cam_rot = unreal.Rotator(-38, 45, 0)  # pitch 俯角, yaw 东南方向
            try:
                viewport.set_view_location(cam_loc)
                viewport.set_view_rotation(cam_rot)
                log("camera positioned via set_view_location/rotation")
                viewport_set = True
            except Exception as e2:
                log("set_view fail: " + str(e2))
                try:
                    viewport.set_view_location_and_rotation(cam_loc, cam_rot)
                    log("camera positioned via combined")
                    viewport_set = True
                except Exception as e3:
                    log("combined fail: " + str(e3))
    except Exception as e:
        log("viewport fail: " + str(e))

    # 等待视口渲染
    time.sleep(1.5)

    # 截图: 用 console 命令保存到 Saved/Screenshots
    try:
        unreal.SystemLibrary.execute_console_command(world, "screenshot")
        log("screenshot command sent")
    except Exception as e:
        log("screenshot fail: " + str(e))

    # 额外: 尝试用 AutomationLibrary 截图 (API 方式)
    try:
        unreal.AutomationLibrary.write_config("ScreenshotResolutionX", 1920)
        unreal.AutomationLibrary.write_config("ScreenshotResolutionY", 1080)
        log("automation screenshot config set")
    except Exception as e:
        log("automation config fail: " + str(e))

    time.sleep(2)
    log("SHOT_DONE")

except Exception as e:
    log("ERROR: " + str(e))
    import traceback
    log(traceback.format_exc())

_f.close()
