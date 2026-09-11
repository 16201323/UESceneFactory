# ============================================================================
# show_smart_agri.py - 加载智慧农林无人机起降场 umap 并多视角定位相机
# ============================================================================
# 功能: 加载 GB_SmartAgriDroneField 关卡 → 启用天空/大气/雾 ShowFlag
#       → 依次定位编辑器视口相机到 4 个视角, 每个视角暂停 30 秒供外部截图
#       → 不退出编辑器 (由外部 MCP 截图后手动关闭)
#
# 重要发现: highresshot 从命令行启动的编辑器中生成全黑截图(43KB),
#           只能通过 MCP Computer Use 的 get_app_state 捕获窗口截图。
#           因此本脚本仅负责定位相机, 截图由外部 MCP 完成。
#
# 用法 (完整编辑器, 有 RHI 渲染):
#   UnrealEditor.exe project.uproject -nosplash -stdout -log
#     -ExecCmds="py show_smart_agri.py"
# 注意: 不加 | quit (py 在完整编辑器中是异步的, | quit 会提前终止脚本)
# ============================================================================

import unreal
import os
import time

# ---- 日志输出 (同时写 stdout 和文件, 供外部轮询) ----
LOG_PATH = "c:/Users/25868/Desktop/UE5/show_smart_agri.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()


# 目标关卡路径 (与 smart_agri_drone_field.json 中的 target_level 一致)
TARGET_LEVEL = "/Game/MapForgeTest/GB_SmartAgriDroneField"


def load_target_level():
    """加载目标关卡, 返回是否成功"""
    try:
        if not unreal.EditorAssetLibrary.does_asset_exist(TARGET_LEVEL):
            log("ERROR: 关卡不存在: " + TARGET_LEVEL)
            return False
        unreal.EditorLevelLibrary.load_level(TARGET_LEVEL)
        log("LEVEL_LOADED: " + TARGET_LEVEL)
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        log("actors in level: " + str(len(actors)))
        return True
    except Exception as e:
        log("load_level fail: " + str(e))
        return False


def position_camera(loc_tuple, rot_tuple, label):
    """
    定位编辑器视口相机
    使用 UnrealEditorSubsystem.set_level_viewport_camera_info (UE5.8, 2参数版本)
    loc_tuple: (x, y, z) 位置, 单位 cm
    rot_tuple: (pitch, yaw, roll) 旋转, 单位度
    """
    try:
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if not ues:
            log("ERROR: UnrealEditorSubsystem 不可用")
            return False

        new_loc = unreal.Vector(loc_tuple[0], loc_tuple[1], loc_tuple[2])
        # Rotator 位置参数顺序是 (roll, pitch, yaw), 用关键字避免混淆
        new_rot = unreal.Rotator(pitch=rot_tuple[0], yaw=rot_tuple[1], roll=rot_tuple[2])

        ues.set_level_viewport_camera_info(new_loc, new_rot)
        log("camera positioned [%s]: loc=%s rot=%s" % (label, str(loc_tuple), str(rot_tuple)))

        # 设置广角 FOV (如果有此方法)
        if hasattr(ues, "set_level_viewport_fov"):
            ues.set_level_viewport_fov(90.0)

        return True
    except Exception as e:
        log("position_camera fail: " + str(e))
        return False


def enable_showflags():
    """启用天空/大气/雾等渲染标志, 确保视口有完整的天空和光照"""
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        log("ERROR: 无法获取 editor world")
        return

    unreal.SystemLibrary.execute_console_command(world, "viewmode lit")
    for cmd in [
        "ShowFlag.SkyAtmosphere true",
        "ShowFlag.Atmosphere true",
        "ShowFlag.VolumetricCloud true",
        "ShowFlag.SkyLighting true",
        "ShowFlag.Fog true",
        "ShowFlag.AtmosphericFog true",
        "r.EyeAdaptation.ExposureCompensation 3.0",
    ]:
        try:
            unreal.SystemLibrary.execute_console_command(world, cmd)
        except Exception:
            pass
    log("ShowFlags + ExposureCompensation x3 enabled")


def main():
    log("SHOW_SMART_AGRI_START")

    # 1. 加载关卡
    if not load_target_level():
        log("SHOW_SMART_AGRI_FAIL: 关卡加载失败")
        _f.close()
        return

    # 等待关卡完全加载 (14082 个 actor 需要时间)
    log("waiting for level load (14082 actors)...")
    time.sleep(8)

    # 2. 启用渲染标志
    enable_showflags()
    time.sleep(2)

    # 3. 多视角相机定位 (5km×5km 场景, 坐标单位 cm)
    #    视角1 - helipad_close: 直升机坪近景, 80m外50m高, 看停机坪/围栏/机库
    #    视角2 - sector_view:   区域俯瞰, 500m外300m高, 看中央+周边农田
    #    视角3 - high_overview: 高空全景, 1.5km外800m高, 看大部分场景
    #    视角4 - top_down:      正上方俯视, 2km上方, 看整体5km×5km布局
    viewpoints = [
        ("helipad_close",  (8000, -8000, 5000),    (-25, 45, 0)),
        ("sector_view",    (50000, -50000, 30000),  (-30, 45, 0)),
        ("high_overview",  (150000, -150000, 80000), (-40, 45, 0)),
        ("top_down",       (0, 0, 200000),          (-90, 0, 0)),
    ]

    for label, loc, rot in viewpoints:
        log("--- positioning: %s ---" % label)
        position_camera(loc, rot, label)
        # 写入就绪标记, 供外部 MCP 轮询日志后截图
        log("VIEWPOINT_READY: %s" % label)
        # 暂停 30 秒, 给外部 MCP 充足时间截图
        time.sleep(30)

    log("ALL_VIEWPOINTS_DONE")
    # 不退出编辑器, 由外部 MCP 截完图后手动关闭
    log("SHOW_SMART_AGRI_DONE")
    _f.close()


main()
