# ============================================================================
# gen_all_shots.py - 一体化脚本: 生成10个测试场景umap + 设置相机 + 截图
# ============================================================================
# 功能:
#   1. 逐个读取 test_01~test_10 的 JSON 场景文件
#   2. 通过 runpy 调用 build_scene.py 将 JSON 转为 umap 并加载到编辑器
#   3. 为每个场景设置关卡视口相机位置和角度
#   4. 通过 AutomationLibrary.take_high_res_screenshot 截图
# 运行方式: UE5 GUI 编辑器启动时通过 -ExecCmds="py gen_all_shots.py" 执行
# ============================================================================

import unreal
import runpy
import os
import sys
import time
import glob
import traceback

# ---- 日志输出 (同时写 stdout 和文件) ----
LOG_PATH = "c:/Users/25868/Desktop/UE5/gen_all_shots.log"
_f = open(LOG_PATH, "w", encoding="utf-8")
def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

BUILD_SCENE = "c:/Users/25868/Desktop/UE5/MapForgeTest/build_scene.py"
SCENE_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest"

# 截图保存目录 (UE5 项目路径下)
# 注意: UE5 编辑器通过 take_high_res_screenshot 截图时, 保存到 WindowsEditor 子目录
PROJECT_DIR = "D:/code/UEEnvironment/MyUETest5_8_2/MyUETest5_8_2"
SCREENSHOT_DIR = PROJECT_DIR + "/Saved/Screenshots/WindowsEditor"

# ---- 10个测试场景配置 ----
# 格式: (json文件名, 场景标签, 相机位置xyz, 相机旋转pitch/yaw/roll)
# 相机位置根据各场景地面尺寸和资产布局计算:
#   scale[10,20,1] → ~97m×100m, 用距离2500~4500相机
#   scale[20,40,1] → ~194m×200m, 用距离7000~8000相机
#   高压塔高77.5m, 相机需升至90m才能俯瞰塔顶
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
    # viewport_config_key 标识要设置的视口, 通过 get_active_viewport_config_key() 获取当前活动视口
    viewport_key = les.get_active_viewport_config_key()
    les.set_level_viewport_camera_info(new_loc, new_rot, viewport_key)
    # 强制视口实时渲染并刷新, 确保相机变更立即生效
    # UE5.8 的 editor_set_viewport_realtime 只接受一个 bool 参数, 不能传 viewport_key
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

def take_screenshot(name):
    """通过 AutomationLibrary.take_high_res_screenshot 截图, 轮询等待任务完成"""
    # UE5.8 编辑器中 SHOT/HighResShot 等控制台命令无法截图, 必须用 AutomationLibrary API
    # take_high_res_screenshot 是异步任务, 返回 AutomationEditorTask 对象
    # force_game_view 保持默认 True (False 不会生成文件)
    task = unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, name)
    log("  截图任务已提交: %s" % str(task))
    # 轮询 is_task_done() 等待任务完成, 超时 180 秒 (实测延迟 16~118 秒)
    timeout = 180
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(3)
        try:
            if task.is_task_done():
                elapsed = time.time() - start
                log("  截图任务完成! 耗时 %.1f 秒" % elapsed)
                return True
        except Exception:
            pass
    log("  截图任务超时(%d秒)" % timeout)
    return False

def count_existing_screenshots():
    """统计当前已有的截图文件数量"""
    # take_high_res_screenshot 按 filename 参数命名, 所以用 *.png 通配
    files = glob.glob(SCREENSHOT_DIR + "/*.png")
    return len(files)

def list_new_screenshots(start_count):
    """列出脚本运行期间新增的截图文件"""
    files = sorted(glob.glob(SCREENSHOT_DIR + "/*.png"))
    new_files = files[start_count:]
    return new_files

def process_scene(index, json_name, label, cam_loc, cam_rot):
    """处理单个场景: 生成umap -> 设置相机 -> 截图"""
    log("=" * 60)
    log("SCENE %d/10: %s (label=%s)" % (index + 1, json_name, label))

    json_path = SCENE_DIR + "/" + json_name
    if not os.path.isfile(json_path):
        log("ERROR: 场景文件不存在: " + json_path)
        return False

    # ---- 步骤1: 设置环境变量, 让 build_scene.py 读取正确的场景文件 ----
    os.environ["MAPFORGE_SCENE"] = json_path
    os.environ["MAPFORGE_LOG"] = SCENE_DIR + "/" + json_name.replace(".json", "_build.log")
    # 重置 sys.argv, 避免残留参数干扰 build_scene.py
    sys.argv = [BUILD_SCENE]
    log("env MAPFORGE_SCENE = " + json_path)

    # ---- 步骤2: 通过 runpy 执行 build_scene.py (等效于独立运行) ----
    # build_scene.py 读取 MAPFORGE_SCENE 环境变量, 生成umap并加载到编辑器
    try:
        runpy.run_path(BUILD_SCENE, run_name="__main__")
        log("BUILD_SCENE_OK: " + json_name)
    except Exception as e:
        log("BUILD_SCENE_FAIL " + json_name + ": " + str(e))
        log(traceback.format_exc())
        return False

    # 等待关卡加载和渲染稳定
    time.sleep(3)

    # ---- 步骤3: 设置相机位置 ----
    try:
        set_camera(cam_loc, cam_rot)
        log("CAMERA_SET: loc=%s rot=%s" % (str(cam_loc), str(cam_rot)))
    except Exception as e:
        log("CAMERA_FAIL: " + str(e))
        log(traceback.format_exc())

    # 等待视口渲染更新
    time.sleep(3)

    # ---- 步骤4: 截图 ----
    try:
        ok = take_screenshot(label)
        if ok:
            log("SHOT_DONE: " + label)
        else:
            log("SHOT_TIMEOUT: " + label)
    except Exception as e:
        log("SHOT_FAIL: " + str(e))
        log(traceback.format_exc())

    # 等待截图文件写入完成
    time.sleep(2)
    log("SCENE_DONE: " + json_name)
    return True

# ============================================================================
# 主流程
# ============================================================================
try:
    log("=" * 60)
    log("GEN_ALL_SHOTS START")
    log("截图目录: " + SCREENSHOT_DIR)

    # 创建截图保存目录 (确保 take_high_res_screenshot 有写入目标)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    log("截图目录已确认存在: " + SCREENSHOT_DIR)

    # 记录脚本开始前已有的截图数量
    existing = count_existing_screenshots()
    log("已有截图数量: %d" % existing)

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

    # 列出新增的截图文件
    new_shots = list_new_screenshots(existing)
    log("新增截图 %d 张:" % len(new_shots))
    for i, f in enumerate(new_shots):
        # 按顺序映射到场景标签
        if i < len(SCENES):
            label = SCENES[i][1]
        else:
            label = "unknown"
        log("  [%d] %s -> %s" % (i + 1, os.path.basename(f), label))

    log("GEN_ALL_SHOTS_COMPLETE")

except Exception as e:
    log("FATAL_ERROR: " + str(e))
    log(traceback.format_exc())

_f.close()
