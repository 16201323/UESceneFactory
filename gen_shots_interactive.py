# ============================================================================
# gen_shots_interactive.py - 交互式截图脚本
# ============================================================================
# 功能:
#   1. 逐个读取 test_01~test_10 的 JSON 场景文件
#   2. 通过 runpy 调用 build_scene.py 将 JSON 转为 umap 并加载到编辑器
#   3. 为每个场景设置关卡视口相机位置和角度
#   4. 写 READY 信号文件通知外部截图, 等待 GO 信号后继续下一个场景
# 运行方式: UE5 GUI 编辑器启动时通过 -ExecCmds="py gen_shots_interactive.py" 执行
# ============================================================================

import unreal
import runpy
import os
import sys
import time
import traceback

# ---- 日志输出 (同时写 stdout 和文件) ----
LOG_PATH = "c:/Users/25868/Desktop/UE5/gen_shots_interactive.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

BUILD_SCENE = "c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py"
SCENE_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest"
SIGNAL_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest/signals"

# ---- 10个测试场景配置 ----
# 格式: (json文件名, 场景标签, 相机位置xyz, 相机旋转pitch/yaw/roll)
SCENES = [
    ("test_01_heliport.json",    "test_01_heliport",    (2500, -2500, 1800),  (-35, 45, 0)),
    ("test_02_wirefence.json",   "test_02_wirefence",   (3500, -3500, 2500),  (-40, 45, 0)),
    ("test_03_hangar.json",      "test_03_hangar",      (3500, -3500, 2000),  (-30, 45, 0)),
    ("test_04_charging.json",    "test_04_charging",    (2000, -2000, 1200),  (-25, 45, 0)),
    ("test_05_solar.json",       "test_05_solar",       (2500, -2500, 1800),  (-35, 45, 0)),
    ("test_06_trees.json",       "test_06_trees",       (4500, -4500, 3000),  (-40, 45, 0)),
    ("test_07_comm_tower.json",  "test_07_comm_tower",  (3500, -3500, 2500),  (-25, 45, 0)),
    ("test_08_hv_tower.json",    "test_08_hv_tower",    (8000, -8000, 9000),  (-30, 45, 0)),
    ("test_09_village.json",     "test_09_village",     (6000, -6000, 3500),  (-40, 45, 0)),
    ("test_10_forest.json",      "test_10_forest",      (8000, -8000, 5000),  (-40, 45, 0)),
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

def wait_for_signal(signal_file, timeout=300):
    """等待指定信号文件出现, 超时返回 False"""
    start = time.time()
    while time.time() - start < timeout:
        if os.path.isfile(signal_file):
            return True
        time.sleep(2)
    return False

def process_scene(index, json_name, label, cam_loc, cam_rot):
    """处理单个场景: 生成umap -> 设置相机 -> 等待外部截图信号"""
    log("=" * 60)
    log("SCENE %d/10: %s (label=%s)" % (index + 1, json_name, label))

    json_path = SCENE_DIR + "/" + json_name
    if not os.path.isfile(json_path):
        log("ERROR: 场景文件不存在: " + json_path)
        return False

    # ---- 步骤1: 设置环境变量, 让 build_scene.py 读取正确的场景文件 ----
    os.environ["MAPFORGE_SCENE"] = json_path
    os.environ["MAPFORGE_LOG"] = SCENE_DIR + "/" + json_name.replace(".json", "_build.log")
    sys.argv = [BUILD_SCENE]
    log("env MAPFORGE_SCENE = " + json_path)

    # ---- 步骤2: 通过 runpy 执行 build_scene.py (等效于独立运行) ----
    try:
        runpy.run_path(BUILD_SCENE, run_name="__main__")
        log("BUILD_SCENE_OK: " + json_name)
    except Exception as e:
        log("BUILD_SCENE_FAIL " + json_name + ": " + str(e))
        log(traceback.format_exc())
        return False

    # 等待关卡加载和渲染稳定
    time.sleep(5)

    # ---- 步骤3: 设置相机位置 ----
    try:
        set_camera(cam_loc, cam_rot)
        log("CAMERA_SET: loc=%s rot=%s" % (str(cam_loc), str(cam_rot)))
    except Exception as e:
        log("CAMERA_FAIL: " + str(e))
        log(traceback.format_exc())

    # 等待视口渲染更新
    time.sleep(3)

    # ---- 步骤4: 写 READY 信号, 等待外部截图完成后的 GO 信号 ----
    ready_file = SIGNAL_DIR + "/READY_%d.txt" % (index + 1)
    go_file = SIGNAL_DIR + "/GO_%d.txt" % (index + 1)

    # 写 READY 信号文件 (包含场景信息)
    with open(ready_file, "w") as f:
        f.write("scene=%s\nlabel=%s\ncam_loc=%s\ncam_rot=%s" % (json_name, label, str(cam_loc), str(cam_rot)))
    log("READY信号已写入: " + ready_file)
    log("等待外部截图, GO信号: " + go_file)

    # 等待 GO 信号 (超时 600 秒 = 10 分钟)
    if wait_for_signal(go_file, timeout=600):
        log("收到GO信号, 继续下一个场景")
        # 删除 GO 信号文件
        try:
            os.remove(go_file)
        except Exception:
            pass
    else:
        log("GO信号超时(600秒), 强制继续")

    log("SCENE_DONE: " + json_name)
    return True

# ============================================================================
# 主流程
# ============================================================================
try:
    log("=" * 60)
    log("GEN_SHOTS_INTERACTIVE START")

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
    for i, (json_name, label, cam_loc, cam_rot) in enumerate(SCENES):
        try:
            if process_scene(i, json_name, label, cam_loc, cam_rot):
                success_count += 1
        except Exception as e:
            log("FATAL %s: %s" % (json_name, str(e)))
            log(traceback.format_exc())

    # 汇总结果
    log("=" * 60)
    log("ALL_DONE: 成功 %d/10" % success_count)
    log("GEN_SHOTS_INTERACTIVE_COMPLETE")

    # 写完成信号
    done_file = SIGNAL_DIR + "/ALL_DONE.txt"
    with open(done_file, "w") as f:
        f.write("done")

except Exception as e:
    log("FATAL_ERROR: " + str(e))
    log(traceback.format_exc())

_f.close()
