# ============================================================================
# show_umap.py - 加载已生成的 umap 关卡并截图展示
# ============================================================================
# 功能: 加载 /Game/MapForgeTest/GB_FarmingVillage 关卡 → 定位编辑器视口相机
#       → 等待渲染 → 截图保存到 Saved/Screenshots → 退出
# 用法(无头/有头均支持, 但截图需要有 RHI 渲染, 不能用 -nullrhi):
#   UnrealEditor.exe project.uproject -nosplash -stdout \
#     -ExecCmds="py show_umap.py | quit"
# ============================================================================

import unreal
import os
import time
import glob

# ---- 日志输出 (同时写 stdout 和文件) ----
LOG_PATH = "c:/Users/25868/Desktop/UE5/show_umap.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()


# 目标关卡路径 (与 farming_village.json 中的 target_level 一致)
TARGET_LEVEL = "/Game/MapForgeTest/GB_FarmingVillage"

# 项目 Saved 目录 (用于查找截图输出)
PROJECT_SAVED = "D:/code/UEEnvironment/MyUETest5_8_2/MyUETest5_8_2/Saved"
SCREENSHOT_DIR = os.path.join(PROJECT_SAVED, "Screenshots", "Windows")


def load_target_level():
    """加载目标关卡, 返回是否成功"""
    try:
        # 检查关卡资产是否存在
        if not unreal.EditorAssetLibrary.does_asset_exist(TARGET_LEVEL):
            log("ERROR: 关卡不存在: " + TARGET_LEVEL)
            return False
        # 加载关卡
        unreal.EditorLevelLibrary.load_level(TARGET_LEVEL)
        log("LEVEL_LOADED: " + TARGET_LEVEL)
        # 统计 actor 数量, 验证关卡内容
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        log("actors in level: " + str(len(actors)))
        return True
    except Exception as e:
        log("load_level fail: " + str(e))
        return False


def position_camera():
    """
    定位编辑器视口相机到东南方向俯瞰角度
    使用 UnrealEditorSubsystem.set_level_viewport_camera_info (UE5.8, 2 参数版本)
    注意: LevelEditorSubsystem 版本需要第 3 个参数 viewport_config_key, 会报错, 不可用
    相机位置: 从东南方向俯视整个农林场景 (场景范围约 30m x 30m)
    """
    try:
        # 使用 UnrealEditorSubsystem (2 参数版本, 无需 viewport_config_key)
        ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        if not ues:
            log("ERROR: UnrealEditorSubsystem 不可用")
            return False

        # 相机位置: 东南方向高空, 距场景中心约 4.5km
        new_loc = unreal.Vector(2800, -2800, 2200)
        # 旋转: pitch 俯角 15 度 (较小俯角让天空占据画面上半部分)
        # 之前 -38 度太陡只能看到地面, 改为 -15 度让天空入镜
        new_rot = unreal.Rotator(-15, 45, 0)

        # 设置视口相机: UnrealEditorSubsystem 版本只需 (location, rotation) 2 个参数
        ues.set_level_viewport_camera_info(new_loc, new_rot)
        log("camera positioned: loc=(2800,-2800,2200) rot=(-15,45,0)")

        # 设置广角 FOV (UnrealEditorSubsystem 可能无此方法, hasattr 保护避免报错)
        if hasattr(ues, "set_level_viewport_fov"):
            ues.set_level_viewport_fov(90.0)
            log("FOV set to 90")
        else:
            log("FOV: UnrealEditorSubsystem 无 set_level_viewport_fov, 用默认 FOV")

        # 验证相机设置
        after = ues.get_level_viewport_camera_info()
        log("camera info after set: " + str(after))
        return True
    except Exception as e:
        log("position_camera fail: " + str(e))
        return False


def take_screenshot():
    """
    截图: 双重捕获法 (解决无头/后台模式下视口不重绘 → 截图全黑的问题)

    原理: 在 -unattended 或后台模式下, 编辑器视口不会自动 tick/重绘.
    相机移动后, 渲染缓冲区仍为空, highresshot 会捕获到纯黑画面.
    解决: 第一次 highresshot 触发视口强制渲染一帧, 等待渲染线程完成后,
    第二次 highresshot 捕获已经填充了实际场景画面的缓冲区.
    (参考 ue-mcp issue #662: 双重捕获 + 刷新渲染线程)

    截图保存到 Saved/Screenshots/Windows/
    """
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        log("ERROR: 无法获取 editor world")
        return False

    # 第一次 highresshot: 触发视口强制渲染 (即使缓冲区为空, 命令本身会驱动一帧渲染)
    try:
        unreal.SystemLibrary.execute_console_command(world, "highresshot 1920x1080")
        log("1st highresshot sent (trigger viewport render)")
    except Exception as e:
        log("1st highresshot fail: " + str(e))

    # 等待渲染线程完成第一帧绘制 (天空/云层/光照需要时间合成)
    time.sleep(6)

    # 第二次 highresshot: 此时缓冲区已填充实际场景, 捕获真实画面
    try:
        unreal.SystemLibrary.execute_console_command(world, "highresshot 1920x1080")
        log("2nd highresshot sent (capture rendered frame)")
    except Exception as e:
        log("2nd highresshot fail: " + str(e))

    # 额外等待确保截图文件写入磁盘
    time.sleep(2)

    return True


def find_screenshot(before_files):
    """
    在 Saved/Screenshots 目录中查找新生成的截图文件
    before_files: 截图前已存在的文件列表 (用于对比找出新文件)
    """
    # 等待截图文件写入完成
    time.sleep(3)

    # 搜索所有可能的截图目录
    search_dirs = [
        SCREENSHOT_DIR,
        os.path.join(PROJECT_SAVED, "Screenshots"),
        PROJECT_SAVED,
    ]

    found = []
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        # 查找 png/jpg 文件
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
            files = glob.glob(os.path.join(d, "**", ext), recursive=True)
            for f in files:
                if f not in before_files:
                    found.append(f)

    if found:
        for f in found:
            log("SCREENSHOT_FOUND: " + f)
        return found[0]  # 返回第一个找到的截图
    else:
        log("WARNING: 未找到新截图文件, 检查 Saved/Screenshots 目录")
        return None


def main():
    log("SHOW_UMAP_START")

    # 记录截图前已存在的文件 (用于后续对比)
    # 注意: 必须包含 Saved 根目录, 否则旧的 AutoScreenshot.png 会被误判为新截图
    before_files = set()
    for d in [SCREENSHOT_DIR, os.path.join(PROJECT_SAVED, "Screenshots"), PROJECT_SAVED]:
        if os.path.exists(d):
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
                for f in glob.glob(os.path.join(d, "**", ext), recursive=True):
                    before_files.add(f)
    log("existing screenshots before: " + str(len(before_files)))

    # 1. 加载关卡
    if not load_target_level():
        log("SHOW_UMAP_FAIL: 关卡加载失败")
        _f.close()
        return

    # 等待关卡完全加载
    time.sleep(2)

    # 2. 定位相机
    # 跳过相机移动: cmd 模式下 set_level_viewport_camera_info 会清空渲染缓冲区且不重绘 → 黑屏
    # 改用默认编辑器相机 (之前 00000/00001 默认相机可正常出图), 验证天空是否随 mobility 修复而渲染
    # position_camera()
    log("camera move SKIPPED (cmd mode buffer issue), using default viewport camera")

    # 3. 相机移动后强制触发视口重绘 (-unattended/无头模式下视口不会自动重绘)
    #    否则 highresshot 会捕获到空渲染缓冲区 → 全黑截图
    world = unreal.EditorLevelLibrary.get_editor_world()
    if world:
        # 切换视图模式强制视口重新渲染当前相机画面
        unreal.SystemLibrary.execute_console_command(world, "viewmode lit")
        # 关键修复: cmd 模式下视口 ShowFlag 可能禁用大气/天空/雾 → 背景纯黑
        # 强制启用这些渲染标志, 确保天空/大气/雾/云在截图时渲染
        # 同时提高曝光补偿, 解决 cmd 模式下自动曝光不收敛导致画面偏暗
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
        log("viewport redraw + ShowFlags + ExposureCompensation x3 enabled")
    # 等待足够时间让 357 个 actor 的网格/纹理加载并完成渲染
    log("waiting for viewport render...")
    time.sleep(8)

    # 4. 截图
    take_screenshot()

    # 5. 查找截图文件
    screenshot_path = find_screenshot(before_files)

    if screenshot_path:
        log("SHOW_UMAP_SUCCESS: " + screenshot_path)
    else:
        log("SHOW_UMAP_DONE (screenshot may still be saving)")

    # 6. 保存关卡 (确保无未保存修改)
    try:
        unreal.EditorLevelLibrary.save_all_dirty_levels()
        log("levels saved")
    except Exception as e:
        log("save fail: " + str(e))

    log("SHOW_UMAP_DONE")
    _f.close()


main()
