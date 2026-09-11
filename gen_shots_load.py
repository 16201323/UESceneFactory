# ============================================================================
# gen_shots_load.py - 加载已有umap截图脚本
# ============================================================================
# 功能:
#   1. 逐个加载已构建好的10个umap关卡(不再从JSON重新生成)
#   2. 为每个场景设置关卡视口相机位置和角度
#   3. 写 READY 信号文件通知外部截图, 等待 GO 信号后继续下一个场景
# 运行方式: UE5 GUI 编辑器启动时通过 -ExecCmds="py gen_shots_load.py" 执行
# 说明: 相比 gen_shots_interactive.py 省去 runpy 重建步骤, 直接加载umap更快
# ============================================================================

import unreal
import os
import time
import traceback

# ---- 日志输出 (同时写 stdout 和文件) ----
LOG_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_load.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

SIGNAL_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest/signals"

# ---- 10个测试场景配置 ----
# 格式: (umap资产路径, 场景标签, 相机位置xyz, 相机旋转pitch/yaw/roll)
# umap路径使用 /Game/ 前缀, 不带文件扩展名
SCENES = [
    ("/Game/MapForgeTest/GB_Test_01_Heliport",  "01_heliport",   (2500, -2500, 1800),  (-35, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_02_Wirefence",  "02_wirefence",   (3500, -3500, 2500),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_03_Hangar",    "03_hangar",      (3500, -3500, 2000),  (-30, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_04_Charging",  "04_charging",    (2000, -2000, 1200),  (-25, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_05_Solar",     "05_solar",       (2500, -2500, 1800),  (-35, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_06_Trees",     "06_trees",       (4500, -4500, 3000),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_07_CommTower", "07_comm_tower",  (3500, -3500, 2500),  (-25, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_08_HVTower",   "08_hv_tower",    (8000, -8000, 9000),  (-30, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_09_Village",   "09_village",     (6000, -6000, 3500),  (-40, 45, 0)),
    ("/Game/MapForgeTest/GB_Test_10_Forest",    "10_forest",      (8000, -8000, 5000),  (-40, 45, 0)),
]

def set_camera(loc_tuple, rot_tuple):
    """设置关卡视口相机位置和旋转角度"""
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    new_loc = unreal.Vector(loc_tuple[0], loc_tuple[1], loc_tuple[2])
    # Rotator 用关键字参数避免顺序混淆 (pitch俯仰, yaw偏航, roll翻滚)
    new_rot = unreal.Rotator(pitch=rot_tuple[0], yaw=rot_tuple[1], roll=rot_tuple[2])
    # UE5.8 的 set_level_viewport_camera_info 需要三个参数 (位置, 旋转, viewport_config_key)
    viewport_key = les.get_active_viewport_config_key()
    les.set_level_viewport_camera_info(new_loc, new_rot, viewport_key)
    # 强制视口实时渲染并刷新, 确保相机变更立即生效
    try:
        les.editor_set_viewport_realtime(True)
    except Exception:
        pass
    try:
        les.editor_invalidate_viewports()
    except Exception:
        pass
    # 设置广角 FOV 以捕捉更大范围
    try:
        les.set_level_viewport_fov(90.0, viewport_key)
    except Exception:
        pass

def wait_for_signal(signal_file, timeout=600):
    """等待指定信号文件出现, 超时返回 False"""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.isfile(signal_file):
            return True
        time.sleep(2)
    return False

def process_scene(index, umap_path, label, cam_loc, cam_rot):
    """处理单个场景: 加载umap -> 设置相机 -> 等待外部截图信号"""
    log("=" * 60)
    log("SCENE %d/10: %s (label=%s)" % (index + 1, umap_path, label))

    # ---- 步骤1: 加载已有umap关卡 ----
    try:
        # EditorLevelLibrary.load_level 接受 /Game/xxx 格式的资产路径
        unreal.EditorLevelLibrary.load_level(umap_path)
        log("LEVEL_LOADED: " + umap_path)
    except Exception as e:
        log("LEVEL_LOAD_FAIL " + umap_path + ": " + str(e))
        log(traceback.format_exc())
        return False

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
    time.sleep(3)

    # ---- 步骤3: 写 READY 信号, 等待外部截图完成后的 GO 信号 ----
    ready_file = SIGNAL_DIR + "/READY_%d.txt" % (index + 1)
    go_file = SIGNAL_DIR + "/GO_%d.txt" % (index + 1)

    # 写 READY 信号文件 (包含场景信息)
    with open(ready_file, "w") as f:
        f.write("scene=%s\nlabel=%s\ncam_loc=%s\ncam_rot=%s" % (umap_path, label, str(cam_loc), str(cam_rot)))
    log("READY信号已写入: " + ready_file)
    log("等待外部截图, GO信号: " + go_file)

    # 等待 GO 信号 (超时 600 秒 = 10 分钟, 给用户关闭弹框/操作时间)
    if wait_for_signal(go_file, timeout=600):
        log("收到GO信号, 继续下一个场景")
        try:
            os.remove(go_file)
        except Exception:
            pass
    else:
        log("GO信号超时(600秒), 强制继续")

    log("SCENE_DONE: " + umap_path)
    return True

# ============================================================================
# 主流程
# ============================================================================
try:
    log("=" * 60)
    log("GEN_SHOTS_LOAD START")

    # 创建信号目录
    os.makedirs(SIGNAL_DIR, exist_ok=True)
    # 清理旧的信号文件
    for old in os.listdir(SIGNAL_DIR):
        try:
            os.remove(os.path.join(SIGNAL_DIR, old))
        except Exception:
            pass
    log("信号目录已清理: " + SIGNAL_DIR)

    # 等待 UE5 编辑器完成初始加载
    log("等待编辑器初始化 5秒...")
    time.sleep(5)

    # 逐个处理10个场景
    success_count = 0
    for i, (umap_path, label, cam_loc, cam_rot) in enumerate(SCENES):
        try:
            if process_scene(i, umap_path, label, cam_loc, cam_rot):
                success_count += 1
        except Exception as e:
            log("FATAL %s: %s" % (umap_path, str(e)))
            log(traceback.format_exc())

    # 汇总结果
    log("=" * 60)
    log("ALL_DONE: 成功 %d/10" % success_count)
    log("GEN_SHOTS_LOAD_COMPLETE")

    # 写完成信号
    done_file = SIGNAL_DIR + "/ALL_DONE.txt"
    with open(done_file, "w") as f:
        f.write("done")

except Exception as e:
    log("FATAL_ERROR: " + str(e))
    log(traceback.format_exc())

_f.close()
