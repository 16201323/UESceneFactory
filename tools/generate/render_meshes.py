# -*- coding: utf-8 -*-
"""
UE5 Python: 渲染静态网格缩略图到 PNG
使用 SceneCapture2D + TextureRenderTarget2D + RenderingLibrary.export_render_target
注意: 必须在无 -nullrhi 的模式下运行 (需要 GPU 渲染)

v2: 修复版
- 使用文件日志代替 stdout (避免 -stdout 重定向时 print 输出丢失)
- 使用固定相机距离代替 mesh.get_bounds() (避免结构体属性访问失败导致 NaN)
- 添加渲染线程刷新等待
- 先测试少量网格验证可行性
"""
import unreal
import os
import math
import time
import traceback

# ====== 常量 ======
OUTPUT_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest/mesh_thumbnails"
LOG_FILE = "c:/Users/25868/Desktop/UE5/MapForgeTest/render_meshes.log"
RT_SIZE = 512
FOV = 30.0  # 视场角 (度)
CAMERA_DIST = 300.0  # 固定相机距离 (UE单位/厘米)
WAIT_TIME = 1.5  # 捕获后等待时间 (秒), 让渲染线程处理

# ====== 文件日志 ======
_log_fh = None

def flog(msg):
    """写入文件日志并 flush"""
    global _log_fh
    if _log_fh is None:
        _log_fh = open(LOG_FILE, "w", encoding="utf-8")
    line = "[" + time.strftime("%H:%M:%S") + "] " + str(msg)
    _log_fh.write(line + "\n")
    _log_fh.flush()


# ====== 网格资产清单: (资产路径, 分类前缀, 显示名, 相机距离) ======
# 相机距离根据网格大小手动设置 (单位: 厘米)
MESHES = [
    # --- 引擎自带 BasicShapes (约100cm) ---
    ("/Engine/BasicShapes/Cube", "01_BasicShapes", "Cube", 300),
    ("/Engine/BasicShapes/Plane", "01_BasicShapes", "Plane", 300),
    ("/Engine/BasicShapes/Sphere", "01_BasicShapes", "Sphere", 300),
    ("/Engine/BasicShapes/Cone", "01_BasicShapes", "Cone", 300),
    ("/Engine/BasicShapes/Cylinder", "01_BasicShapes", "Cylinder", 300),
    # --- 房屋模块化部件 (约100-300cm) ---
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_Base_100CM", "02_House_Modular", "Base_100CM", 400),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_ExtWall_100CM", "02_House_Modular", "ExtWall_100CM", 400),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_ExtWall_Corner_A", "02_House_Modular", "ExtWall_Corner_A", 400),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_ExtWall_Window_A", "02_House_Modular", "ExtWall_Window_A", 400),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_ExtWall_Door_A", "02_House_Modular", "ExtWall_Door_A", 400),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_Roof_A_Mid", "02_House_Modular", "Roof_A_Mid", 500),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_FrontStairs_A", "02_House_Modular", "FrontStairs_A", 500),
    ("/Game/RuralHouse/House/Meshes/ModularParts/SM_House_FloorPlane_01", "02_House_Modular", "FloorPlane_01", 500),
    # --- 门窗 ---
    ("/Game/RuralHouse/House/Meshes/DoorsWindows/SM_FrontDoor_A_Door", "03_DoorsWindows", "FrontDoor_A_Door", 400),
    ("/Game/RuralHouse/House/Meshes/DoorsWindows/SM_House_Window_A", "03_DoorsWindows", "Window_A", 400),
    # --- 围栏 ---
    ("/Game/RuralHouse/House/Meshes/Fence/SM_Fence_A", "04_Fence", "Fence_A", 400),
    # --- 道具 (Props) ---
    ("/Game/RuralHouse/Props/SM_Barrel", "05_Props", "Barrel", 300),
    ("/Game/RuralHouse/Props/SM_Lamp", "05_Props", "Lamp", 400),
    ("/Game/RuralHouse/Props/SM_Tire", "05_Props", "Tire", 300),
    ("/Game/RuralHouse/Props/SM_LawnChair", "05_Props", "LawnChair", 300),
    ("/Game/RuralHouse/Props/SM_DieselGenerator", "05_Props", "DieselGenerator", 500),
    ("/Game/RuralHouse/Props/SM_Fridge", "05_Props", "Fridge", 500),
    ("/Game/RuralHouse/Props/SM_WaterTank", "05_Props", "WaterTank", 600),
    # --- 树木 ---
    ("/Game/RuralHouse/Environment/Trees/SM_FirTree_01", "06_Trees", "FirTree_01", 800),
    ("/Game/RuralHouse/Environment/Trees/SM_SmallFir_01", "06_Trees", "SmallFir_01", 500),
    # --- 岩石 ---
    ("/Game/RuralHouse/Environment/Ground/SM_Rock_A_01", "07_Rocks", "Rock_A_01", 400),
    # --- 道路 ---
    ("/Game/RuralHouse/Environment/Road/SM_Road_A", "08_Road", "Road_A", 500),
    # --- 植被 ---
    ("/Game/RuralHouse/Environment/Foliage/SM_Grass_01", "09_Foliage", "Grass_01", 300),
    ("/Game/Generated/SM_GrassCluster", "09_Foliage", "GrassCluster_Generated", 500),
]


def get_enum(enum_class, *names):
    """尝试多个枚举名称, 返回第一个找到的值"""
    for name in names:
        try:
            val = getattr(enum_class, name)
            return val
        except Exception:
            continue
    flog("  WARNING: 枚举值未找到: " + str(names))
    return None


def render_single_mesh(world, cap_comp, rt, mesh_path, category, display_name, output_dir, cam_dist):
    """渲染单个网格到 PNG"""
    safe_name = display_name.replace(" ", "_")
    file_name = category + "_" + safe_name + ".png"

    # 1. 加载网格资产
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if not mesh:
        flog("  SKIP: 无法加载 " + mesh_path)
        return False

    # 2. 生成 StaticMeshActor 并设置网格
    sm_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(0, 0, 0),
        unreal.Rotator(0, 0, 0),
    )
    if not sm_actor:
        flog("  SKIP: 无法生成 actor " + mesh_path)
        return False

    sm_comp = sm_actor.get_components_by_class(unreal.StaticMeshComponent)
    if not sm_comp or len(sm_comp) == 0:
        flog("  SKIP: 无 StaticMeshComponent " + mesh_path)
        unreal.EditorLevelLibrary.destroy_actor(sm_actor)
        return False

    sm_comp[0].set_static_mesh(mesh)

    # 3. 使用固定相机位置 (不依赖 mesh.get_bounds())
    # 3/4 透视视角: 方位角 -35度, 仰角 25度
    yaw_rad = math.radians(-35)
    pitch_rad = math.radians(25)
    cam_x = cam_dist * math.cos(pitch_rad) * math.cos(yaw_rad)
    cam_y = cam_dist * math.cos(pitch_rad) * math.sin(yaw_rad)
    cam_z = cam_dist * math.sin(pitch_rad)

    # 目标点: 网格中心 (假设在原点附近, z=50cm)
    target = unreal.Vector(0, 0, 50)
    cam_pos = unreal.Vector(cam_x, cam_y, cam_z)

    flog("  渲染: " + display_name + " cam=(" +
         str(round(cam_x, 1)) + "," + str(round(cam_y, 1)) + "," + str(round(cam_z, 1)) + ")")

    # 4. 设置相机位置和朝向
    # UE5 Python 的 set_world_location_and_rotation 需要4个参数:
    #   location(Vector), rotation(Rotator), sweep(bool), teleport(bool)
    # 相机不需要碰撞检测和传送, 两个布尔参数都传 False
    rot = unreal.MathLibrary.find_look_at_rotation(cam_pos, target)
    cap_comp.set_world_location_and_rotation(cam_pos, rot, False, False)

    # 5. 捕获场景
    cap_comp.capture_scene()

    # 等待渲染线程处理 (关键: 命令行模式没有自动tick, 需要给渲染线程时间)
    time.sleep(WAIT_TIME)

    # 6. 导出渲染目标到 PNG
    try:
        unreal.RenderingLibrary.export_render_target(world, rt, output_dir, file_name)
    except Exception as e:
        flog("  export_render_target 失败: " + str(e))

    # 7. 验证文件
    full_path = os.path.join(output_dir, file_name)
    if os.path.exists(full_path):
        size = os.path.getsize(full_path)
        flog("  OK: " + file_name + " (" + str(size) + " bytes)")
    else:
        flog("  WARN: 文件未生成 " + full_path)

    # 8. 销毁网格 actor
    unreal.EditorLevelLibrary.destroy_actor(sm_actor)
    return True


def main():
    flog("=== 网格缩略图渲染器 v2 ===")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 获取编辑器世界
    world = unreal.EditorLevelLibrary.get_editor_world()
    flog("World: " + str(world))
    if not world:
        flog("ERROR: 未找到编辑器世界!")
        return

    # 创建灯光 (方向光 + 天空光)
    dir_light = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.DirectionalLight,
        unreal.Vector(0, 0, 1000),
        unreal.Rotator(-45, 0, 0),
    )
    if dir_light:
        comps = dir_light.get_components_by_class(unreal.DirectionalLightComponent)
        if comps:
            comps[0].set_editor_property("intensity", 3.14)

    sky_light = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SkyLight,
        unreal.Vector(0, 0, 1000),
        unreal.Rotator(0, 0, 0),
    )
    if sky_light:
        comps = sky_light.get_components_by_class(unreal.SkyLightComponent)
        if comps:
            comps[0].set_editor_property("intensity", 1.0)

    flog("灯光设置完成")

    # 创建渲染目标 (RTF_RGBA8 用于 PNG 输出)
    rtf = get_enum(unreal.TextureRenderTargetFormat, "RTF_RGBA8", "RTF_RGBA_8")
    rt = unreal.RenderingLibrary.create_render_target2d(
        world,
        RT_SIZE,
        RT_SIZE,
        rtf if rtf is not None else 1,
        unreal.LinearColor(0.1, 0.1, 0.1, 1.0),
        False,
        False,
    )
    flog("渲染目标: " + str(rt))

    # 创建场景捕获 actor
    cap_actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SceneCapture2D,
        unreal.Vector(200, -200, 200),
        unreal.Rotator(0, 0, 0),
    )
    cap_comp = cap_actor.get_components_by_class(unreal.SceneCaptureComponent2D)
    if not cap_comp or len(cap_comp) == 0:
        flog("ERROR: 无 SceneCaptureComponent2D!")
        return
    cap_comp = cap_comp[0]

    # 设置捕获属性
    cap_comp.set_editor_property("texture_target", rt)

    # SCS_FinalColorLDR: 捕获最终颜色 (含光照和后处理, LDR sRGB)
    scs = get_enum(
        unreal.SceneCaptureSource,
        "SCS_FINAL_COLOR_LDR",
        "SCS_FinalColorLDR",
    )
    if scs is not None:
        cap_comp.set_editor_property("capture_source", scs)

    cap_comp.set_editor_property("capture_every_frame", False)
    cap_comp.set_editor_property("capture_on_movement", False)
    cap_comp.set_editor_property("always_persist_rendering_state", True)
    cap_comp.set_editor_property("fov_angle", FOV)
    flog("场景捕获设置完成")

    # 渲染每个网格
    success = 0
    fail = 0
    for mesh_path, category, display_name, cam_dist in MESHES:
        flog("---")
        flog("处理: " + display_name + " (" + mesh_path + ")")
        try:
            if render_single_mesh(world, cap_comp, rt, mesh_path, category, display_name, OUTPUT_DIR, cam_dist):
                success += 1
            else:
                fail += 1
        except Exception as e:
            flog("  ERROR: " + str(e))
            flog("  " + traceback.format_exc().replace("\n", " | "))
            fail += 1

    flog("=== 完成: " + str(success) + " 成功, " + str(fail) + " 失败 ===")
    flog("输出目录: " + OUTPUT_DIR)

    # 清理
    for actor in [dir_light, sky_light, cap_actor]:
        try:
            if actor:
                unreal.EditorLevelLibrary.destroy_actor(actor)
        except Exception:
            pass

    flog("清理完成, 脚本结束")


main()
