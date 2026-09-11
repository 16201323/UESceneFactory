# ============================================================================
# gen_shots_standalone.py - 独立截图脚本 (不依赖 runpy/build_scene)
# ============================================================================
# 功能:
#   1. 直接用 EditorLevelLibrary.load_level 加载已构建的 umap
#   2. 为每个场景设置关卡视口相机位置和角度
#   3. 用 AutomationLibrary.take_high_res_screenshot 截图
#   4. 搜索 Saved 目录找到截图文件并移动到 screenshots 目录
# 关键: 不使用 runpy/build_scene, 避免 automation 系统冲突
# 运行方式: UE5 GUI 编辑器启动时通过 -ExecCmds="py gen_shots_standalone.py" 执行
# ============================================================================

import unreal
import os
import sys
import time
import traceback
import shutil

# ---- 日志输出 (同时写 stdout 和文件) ----
LOG_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_standalone.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

SHOT_DIR = "c:/Users/25868/Desktop/UE5/screenshots"

# ---- 10个测试场景配置 ----
# 格式: (umap路径, 截图标签, 相机位置xyz, 相机旋转pitch/yaw/roll)
SCENES = [
    ("/Game/MapForgeTest/GB_Test_01_Heliport",  "01_heliport",   (2500, -2500, 1800),  (-35, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_02_Wirefence", "02_wirefence",  (3500, -3500, 2500),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_03_Hangar",    "03_hangar",     (3500, -3500, 2000),  (-30, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_04_Charging",  "04_charging",   (2000, -2000, 1200),  (-25, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_05_Solar",     "05_solar",      (2500, -2500, 1800),  (-35, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_06_Trees",     "06_trees",      (4500, -4500, 3000),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_07_CommTower", "07_comm_tower", (3500, -3500, 2500),  (-25, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_08_HVTower",   "08_hv_tower",   (8000, -8000, 9000),  (-30, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_09_Village",   "09_village",    (6000, -6000, 3500),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_10_Forest",    "10_forest",     (8000, -8000, 5000),  (-40, 45, 0)),
]

def set_camera(loc_tuple, rot_tuple):
    """设置关卡视口相机位置和旋转角度"""
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    new_loc = unreal.Vector(loc_tuple[0], loc_tuple[1], loc_tuple[2])
    # Rotator 位置参数顺序是 (roll, pitch, yaw), 用关键字参数避免混淆
    new_rot = unreal.Rotator(pitch=rot_tuple[0], yaw=rot_tuple[1], roll=rot_tuple[2])
    # UE5.8 的 set_level_viewport_camera_info 需要三个参数 (位置, 旋转, viewport_config_key)
    viewport_key = les.get_active_viewport_config_key()
    les.set_level_viewport_camera_info(new_loc, new_rot, viewport_key)
    # 强制视口实时渲染并刷新, 确保相机变更立即生效
    # UE5.8 的 editor_set_viewport_realtime 只接受一个 bool 参数
    try:
        les.editor_set_viewport_realtime(True)
    except Exception:
        pass
    try:
        les.editor_invalidate_viewports()
    except Exception:
        pass
    # 设置广角 FOV 以捕捉更大范围
    # UE5.8 的 set_level_viewport_fov 需要两个参数 (fov, viewport_config_key)
    try:
        les.set_level_viewport_fov(90.0, viewport_key)
    except Exception:
        pass

def find_screenshot(base_name, timeout=180):
    """在 Saved 目录递归搜索截图文件, 超时返回 None"""
    # 获取项目目录的绝对路径
    project_dir = unreal.Paths.project_dir()
    # 转换为绝对路径
    project_abs = unreal.Paths.convert_relative_path_to_full(project_dir)
    # 可能的截图保存路径
    search_roots = [
        project_abs + "Saved/",
        "D:/Program Files/Epic Games/UE_5.8/Engine/Saved/",
    ]
    start = time.time()
    while time.time() - start < timeout:
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            # 递归搜索 .png 文件
            for dirpath, dirnames, filenames in os.walk(root):
                for fname in filenames:
                    if fname.endswith(".png") and base_name in fname:
                        full_path = os.path.join(dirpath, fname)
                        # 检查文件是否写入完成 (大小 > 0 且稳定)
                        try:
                            size1 = os.path.getsize(full_path)
                            time.sleep(1)
                            size2 = os.path.getsize(full_path)
                            if size1 == size2 and size1 > 0:
                                return full_path
                        except Exception:
                            pass
        time.sleep(5)
    return None

try:
    log("=" * 60)
    log("GEN_SHOTS_STANDALONE START")
    log("等待编辑器初始化 8秒...")
    time.sleep(8)

    # 确保截图输出目录存在
    os.makedirs(SHOT_DIR, exist_ok=True)

    success_count = 0
    for i, (level_path, label, cam_loc, cam_rot) in enumerate(SCENES):
        log("=" * 60)
        log("SCENE %d/10: %s (label=%s)" % (i + 1, level_path, label))

        # ---- 步骤1: 加载已构建的 umap ----
        try:
            unreal.EditorLevelLibrary.load_level(level_path)
            log("LEVEL_LOADED: " + level_path)
        except Exception as e:
            log("LOAD_FAIL: " + str(e))
            log(traceback.format_exc())
            continue

        # 等待关卡加载和渲染稳定
        time.sleep(5)

        # ---- 步骤2: 设置相机位置 ----
        try:
            set_camera(cam_loc, cam_rot)
            log("CAMERA_SET: loc=%s rot=%s" % (str(cam_loc), str(cam_rot)))
        except Exception as e:
            log("CAMERA_FAIL: " + str(e))
            log(traceback.format_exc())

        # 等待视口渲染更新
        time.sleep(5)

        # ---- 步骤3: 调用 take_high_res_screenshot 截图 ----
        shot_name = "shot_" + label
        try:
            unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, shot_name)
            log("SHOT_SENT: " + shot_name)
        except Exception as e:
            log("SHOT_SEND_FAIL: " + str(e))
            log(traceback.format_exc())
            continue

        # ---- 步骤4: 搜索截图文件并移动到目标目录 ----
        log("等待截图文件生成 (最长180秒)...")
        shot_file = find_screenshot(shot_name, timeout=180)
        if shot_file:
            target_path = SHOT_DIR + "/" + shot_name + ".png"
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                shutil.move(shot_file, target_path)
                size_kb = os.path.getsize(target_path) / 1024.0
                log("SHOT_SAVED: %s (%.1f KB)" % (target_path, size_kb))
                success_count += 1
            except Exception as e:
                log("MOVE_FAIL: " + str(e))
        else:
            log("SHOT_TIMEOUT: " + shot_name + " (180秒内未找到截图文件)")

    # 汇总结果
    log("=" * 60)
    log("ALL_DONE: 成功 %d/10" % success_count)
    log("GEN_SHOTS_STANDALONE_COMPLETE")

except Exception as e:
    log("FATAL_ERROR: " + str(e))
    log(traceback.format_exc())

_f.close()
