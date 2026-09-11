import unreal
import time

LOG_PATH = "c:/Users/25868/Desktop/UE5/camera_set.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    _f.write(str(msg) + "\n")
    _f.flush()

try:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    
    # 先获取当前相机信息, 了解返回格式
    current = les.get_level_viewport_camera_info()
    log("current camera info: " + str(current))
    log("type: " + str(type(current)))

    # 设置相机: 从东南方向俯瞰整个农林场景
    # 场景范围约 30m x 30m, 中心在原点
    new_loc = unreal.Vector(2800, -2800, 2200)
    new_rot = unreal.Rotator(-38, 45, 0)  # pitch 俯角 38 度, yaw 东南方向

    # 尝试多种参数格式设置相机
    camera_set = False
    for attempt, param in [
        ("tuple_vec_rot", (new_loc, new_rot)),
        ("list_vec_rot", [new_loc, new_rot]),
    ]:
        try:
            les.set_level_viewport_camera_info(param)
            log("set camera via " + attempt)
            camera_set = True
            break
        except Exception as e:
            log(attempt + " fail: " + str(e))

    # 设置 FOV (广角, 捕捉更大范围)
    try:
        les.set_level_viewport_fov(90.0)
        log("FOV set to 90")
    except Exception as e:
        log("FOV fail: " + str(e))

    # 验证相机是否设置成功
    after = les.get_level_viewport_camera_info()
    log("after camera info: " + str(after))

    # 等待视口渲染更新
    time.sleep(2)
    log("CAMERA_SET_DONE")

except Exception as e:
    log("ERROR: " + str(e))
    import traceback
    log(traceback.format_exc())

_f.close()
