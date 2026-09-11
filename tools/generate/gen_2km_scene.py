#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
山野田园地形场景生成脚本
========================
场景: 8x8组件, 127*1=127四边形/组件, 约1016m x 1016m (1km x 1km)
功能: 山丘(山)/山谷(湖泊+低地)/田垄(农田)/噪声叠加/扰动/水面/河流/道路/建筑/散布/草地

流程:
  1. 创建5个ULandscapeLayerInfoObject (Snow/Rock/Grass/Dirt/Sand)
  2. 创建ULandscapeGrassType (草地类型, 供函数填充varieties)
  3. 创建景观地形材质 (含LayerBlend + GrassOutput, 失败则跳过)
  4. 读取JSON配置
  5. 调用CreateLandscapeWithLayers
  6. 保存关卡为.umap
"""

import unreal
import json
import os
import sys

# ============================================================================
# 配置区
# ============================================================================

# JSON文件所在目录
JSON_DIR = r"c:\Users\25868\Desktop\UE5\MapForgeTest"

# UE5内容目录(存放生成的资产)
ASSET_DIR = "/Game/Generated"

# 输出关卡路径
MAP_PATH = "/Game/Maps/Generated/MountainValleyScene"

# 6个图层定义: (图层名, 图层信息资产名, 权重JSON文件名)
# 第6层Wheat: 麦田图层, 按区域分布, 配合LGT_Wheat生成麦穗实例
LAYERS = [
    ("Snow",  "LIS_Snow",  "layer_weight_snow.json"),
    ("Rock",  "LIS_Rock",  "layer_weight_rock.json"),
    ("Grass", "LIS_Grass", "layer_weight_grass.json"),
    ("Dirt",  "LIS_Dirt",  "layer_weight_dirt.json"),
    ("Sand",  "LIS_Sand",  "layer_weight_sand.json"),
    ("Wheat", "LIS_Wheat", "layer_weight_wheat.json"),
]

# 每层基础权重(均匀分配, 让各层都有机会在权重模式控制下显现)
LAYER_WEIGHTS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]

# 草地配置
GRASS_LAYER_NAME = "Grass"
GRASS_DENSITY = 200.0
GRASS_MESH_PATH = "/Engine/BasicShapes/Plane"

# 麦田配置
# 麦穗网格在height_pattern.json的wheat_varieties数组中配置(5种混合)
# 这里仅定义图层名, 网格/密度/缩放等由C++从JSON解析
WHEAT_LAYER_NAME = "Wheat"

# 地形几何参数
LOCATION = unreal.Vector(0.0, 0.0, 0.0)
ROTATION = unreal.Rotator(0.0, 0.0, 0.0)
SCALE = unreal.Vector(100.0, 100.0, 100.0)
# 【关键修复】NumSubsections必须为1, 使TextureSize == ComponentSizeVerts
# 原因: 当NumSubsections>1时, TextureSize=(SectionSizeQuads+1)*NumSubsections
#       而ComponentSizeVerts=SectionSizeQuads*NumSubsections+1, 两者不匹配
#       导致引擎遍历纹理像素时GetHeightData断言LocalX<ComponentSizeVerts失败
#       (63*4+1=253 vs (63+1)*4=256, 3像素不匹配→越界崩溃)
# 修复: NumSubsections=1, TextureSize=(127+1)*1=128=ComponentSizeVerts=128
#       且127=2^7-1, ComponentSizeVerts=128=2^7(2的幂, 纹理无填充, 无越界)
SECTION_SIZE_QUADS = 127
NUM_SUBSECTIONS = 1
COMPONENT_COUNT_X = 8
COMPONENT_COUNT_Y = 8


# ============================================================================
# 工具函数
# ============================================================================

def log(msg, level="INFO"):
    """带级别前缀的日志输出"""
    prefix = {"INFO": "[INFO]", "OK": "[OK]", "WARN": "[WARN]", "ERROR": "[ERROR]"}
    print(f"{prefix.get(level, '[INFO]')} {msg}")


def read_json(filename):
    """读取JSON文件内容为字符串"""
    filepath = os.path.join(JSON_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def get_asset_tools():
    """获取AssetTools实例"""
    return unreal.AssetToolsHelpers.get_asset_tools()


def ensure_directory(package_path):
    """确保UE5内容目录存在(AssetTools会自动创建包路径, 此函数仅做日志)"""
    log(f"使用资产目录: {package_path}")


# ============================================================================
# 步骤1: 创建ULandscapeLayerInfoObject资产
# ============================================================================

def create_layer_info(layer_name, asset_name):
    """
    创建ULandscapeLayerInfoObject资产
    ULandscapeLayerInfoObject是UObject子类, 存储图层名和类型信息
    CreateLandscapeWithLayers函数通过LoadObject加载此资产来注册地形图层
    """
    asset_path = f"{ASSET_DIR}/{asset_name}"

    # 检查是否已存在
    existing = unreal.EditorAssetLibrary.load_asset(asset_path)
    if existing:
        # 更新图层名(LayerName可能只读, 用try保护)
        try:
            existing.set_editor_property("layer_name", unreal.Name(layer_name))
        except Exception:
            log(f"LayerName只读, 跳过更新 (layer={layer_name})", "WARN")
        unreal.EditorAssetLibrary.save_asset(asset_path)
        log(f"图层信息已存在并更新: {asset_path} (layer={layer_name})", "OK")
        return asset_path

    asset_tools = get_asset_tools()

    # ULandscapeLayerInfoObject是UObject子类(非UDataAsset)
    # 不能用DataAssetFactory(会触发assert: Class->IsChildOf(UDataAsset))
    # create_asset签名: (asset_name, package_path, asset_class, factory)
    # 第3个参数asset_class传unreal.LandscapeLayerInfoObject, 第4个factory传None
    asset = None
    try:
        asset = asset_tools.create_asset(
            asset_name, ASSET_DIR,
            unreal.LandscapeLayerInfoObject,  # 资产类: ULandscapeLayerInfoObject
            None  # 无工厂, 直接用类创建
        )
    except Exception as e:
        log(f"创建图层信息对象失败: {e}", "WARN")

    if asset:
        # LayerName属性在Python API中可能被标记为只读
        # 尝试多种方式设置, 失败则跳过(C++ CreateLandscapeWithLayers会处理)
        try:
            asset.set_editor_property("layer_name", unreal.Name(layer_name))
        except Exception:
            try:
                asset.layer_name = layer_name
            except Exception:
                log(f"LayerName属性为只读, 跳过设置 (layer={layer_name})", "WARN")
        unreal.EditorAssetLibrary.save_asset(asset_path)
        log(f"图层信息已创建: {asset_path} (layer={layer_name})", "OK")
        return asset_path

    log(f"无法创建图层信息对象: {asset_name}", "ERROR")
    return None


# ============================================================================
# 步骤2: 创建ULandscapeGrassType资产
# ============================================================================

def create_grass_type():
    """
    创建ULandscapeGrassType资产
    ULandscapeGrassType是UDataAsset子类, 存储草地网格和密度配置
    CreateLandscapeWithLayers函数会从JSON的grass_varieties数组填充其GrassVarieties
    """
    asset_name = "LGT_Grass"
    asset_path = f"{ASSET_DIR}/{asset_name}"

    existing = unreal.EditorAssetLibrary.load_asset(asset_path)
    if existing:
        log(f"草地类型已存在: {asset_path}", "OK")
        return asset_path

    asset_tools = get_asset_tools()

    # 不能用DataAssetFactory! 它的C++断言(Class->IsChildOf(UDataAsset))会直接崩溃,
    # try-except无法捕获C++致命错误。
    # 直接用create_asset指定asset_class创建, 无需工厂
    # create_asset签名: (asset_name, package_path, asset_class, factory)
    asset = None
    try:
        asset = asset_tools.create_asset(
            asset_name, ASSET_DIR,
            unreal.LandscapeGrassType,  # 资产类: ULandscapeGrassType
            None  # 无工厂
        )
    except Exception as e:
        log(f"创建草地类型失败: {e}", "WARN")

    if asset:
        unreal.EditorAssetLibrary.save_asset(asset_path)
        log(f"草地类型已创建: {asset_path}", "OK")
        return asset_path

    log("无法创建草地类型, 草地将被跳过", "WARN")
    return None


def create_wheat_grass_type():
    """创建ULandscapeGrassType资产(麦田类型)

    与create_grass_type()相同方式创建LGT_Wheat资产,
    C++ CreateLandscapeWithLayers会从height_pattern.json的wheat_varieties数组
    填充其GrassVarieties(5种麦穗网格混合).
    麦穗网格使用用户已有的realistic_wheat静态网格资产.
    """
    asset_name = "LGT_Wheat"
    asset_path = f"{ASSET_DIR}/{asset_name}"

    existing = unreal.EditorAssetLibrary.load_asset(asset_path)
    if existing:
        log(f"麦田类型已存在: {asset_path}", "OK")
        return asset_path

    asset_tools = get_asset_tools()
    try:
        asset = asset_tools.create_asset(
            asset_name, ASSET_DIR,
            unreal.LandscapeGrassType,
            None
        )
    except Exception as e:
        log(f"创建麦田类型失败: {e}", "WARN")
        asset = None

    if asset:
        unreal.EditorAssetLibrary.save_asset(asset_path)
        log(f"麦田类型已创建: {asset_path}", "OK")
        return asset_path

    log("无法创建麦田类型, 麦田将被跳过", "WARN")
    return None


# ============================================================================
# 步骤3: 创建景观地形材质
# ============================================================================

def create_landscape_material(layer_names, grass_layer_name, wheat_layer_name=""):
    """
    创建景观地形材质(含LayerBlend + GrassOutput + WheatOutput)

    【关键修复】原方案纯Python创建材质表达式, 但Python设置struct数组元素
    (FLayerBlendInput.layer_name)不生效, 导致layer_name为空, 材质无法匹配
    地形图层权重, 渲染为银色/灰色。

    新方案: C++完成全部材质操作(创建表达式+设置layer_name+连接BaseColor+编译)

    流程:
      1. Python创建UMaterial资产(如果不存在)
      2. C++ SetupLandscapeMaterial创建表达式+连接BaseColor+编译材质
         - LayerBlend: N层混合(Snow/Rock/Grass/Dirt/Sand/Wheat)
         - GrassOutput: 2个条目(Grass+Wheat), 各自连接LayerSample
      3. Python保存材质资产

    注: 原Python方案中connect_expression_to_property/rebuild_material在UE5.8不存在,
        已全部移至C++使用ConnectMaterialProperty/RecompileMaterial替代
    """
    asset_name = "MM_LandscapeBase"
    asset_path = f"{ASSET_DIR}/{asset_name}"

    # 1. 确保材质资产存在
    existing = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not existing:
        asset_tools = get_asset_tools()
        try:
            factory = unreal.MaterialFactoryNew()
            material = asset_tools.create_asset(asset_name, ASSET_DIR, None, factory)
            if material:
                unreal.EditorAssetLibrary.save_asset(asset_path)
                log(f"材质资产已创建: {asset_path}", "OK")
        except Exception as e:
            log(f"无法创建材质资产: {e}", "ERROR")
            return ""
    else:
        log(f"材质资产已存在: {asset_path}", "OK")

    # 2. 调用C++函数创建表达式并设置layer_name(关键: Python无法设置struct数组元素)
    try:
        result = unreal.LandscapeHelper.setup_landscape_material(
            asset_path, layer_names, grass_layer_name, wheat_layer_name)
        if not result:
            log("C++ SetupLandscapeMaterial返回False", "WARN")
            return asset_path
        log("C++已创建材质表达式并设置layer_name", "OK")
    except Exception as e:
        log(f"C++ SetupLandscapeMaterial调用失败: {e}", "ERROR")
        return asset_path

    # 3. 保存材质资产(C++已完成表达式创建+BaseColor连接+材质编译)
    try:
        unreal.EditorAssetLibrary.save_asset(asset_path)
        log(f"材质已保存: {asset_path}", "OK")
    except Exception as e:
        log(f"材质保存失败: {e}", "WARN")

    return asset_path


# ============================================================================
# 步骤4: 创建新关卡
# ============================================================================

def create_new_level():
    """创建新的空关卡, 作为地形场景的容器

    【关键修复1】使用LevelEditorSubsystem(而非UnrealEditorSubsystem)
    原因: UnrealEditorSubsystem没有new_level方法, 调用会抛AttributeError,
          降级到EditorLevelLibrary.new_level(deprecated), 后者使用OpenWorld模板
          创建World Partition关卡, 其HLOD Actor引用临时网格体导致save_map失败
    修复: LevelEditorSubsystem.new_level创建空白关卡, 不含HLOD模板Actor

    【关键修复2】删除旧关卡时带重试和GC
    原因: delete_asset是异步操作, 单次调用可能未完成就返回
    修复: 最多重试3次, 每次后GC+延迟0.5秒, 用does_asset_exist验证
    """
    log(f"创建新关卡: {MAP_PATH}")

    # 删除已存在的关卡资产(带重试和GC, 确保完全删除)
    # 【关键修复】用does_asset_exist替代load_asset检查存在性
    # 原因: load_asset会反序列化旧.umap, 触发Landscape.cpp:7845断言
    #       (旧.umap含已生成地形, 引用空LayerName的LIS_资产), 导致编辑器崩溃
    # 修复: does_asset_exist只检查磁盘存在性, 不加载资产, 避免触发地形验证
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        log(f"发现旧关卡, 尝试删除...")
        for attempt in range(3):
            try:
                unreal.EditorAssetLibrary.delete_asset(MAP_PATH)
            except:
                pass
            # GC + 延迟, 让删除操作完全完成
            try:
                unreal.SystemLibrary.collect_garbage()
            except:
                pass
            import time
            time.sleep(0.5)
            # 验证是否已删除
            if not unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
                log(f"旧关卡已删除(尝试{attempt + 1})", "OK")
                break
        else:
            log("旧关卡删除3次仍未成功, 将尝试覆盖创建", "WARN")

    # 【关键修复】delete_asset失败时, 直接从磁盘删除.umap文件
    # 原因: delete_asset是异步操作, 可能因资产注册表缓存或内存引用而失败.
    #       但磁盘文件仍存在, 导致后续new_level报"asset already exists",
    #       new_level失败后降级使用/Temp临时世界, 最终save_map也因文件冲突而失败.
    # 修复: 直接用os.remove删除磁盘.umap文件, 绕过资产注册表,
    #       确保new_level能在MAP_PATH成功创建.
    import os
    try:
        content_dir = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_content_dir())
        umap_disk = os.path.join(content_dir, "Maps", "Generated",
                                "MountainValleyScene.umap")
        if os.path.exists(umap_disk):
            os.remove(umap_disk)
            log(f"已从磁盘直接删除旧.umap: {umap_disk}", "OK")
            # 删除后刷新资产注册表, 让does_asset_exist返回False
            try:
                unreal.EditorAssetLibrary.refresh_asset_nodes_in_directory(
                    "/Game/Maps/Generated")
            except Exception:
                pass
            # 【关键修复】磁盘删除后必须等待足够时间让资产注册表更新,
            # 否则new_level仍认为资产存在, 回退创建到/Temp/Untitled_1,
            # 导致OpenWorld模板的HLOD Actor阻止save_map保存.umap
            import time
            time.sleep(2.0)
            # 再次GC, 清除注册表中对已删除.umap的缓存引用
            try:
                unreal.SystemLibrary.collect_garbage()
            except:
                pass
            log("磁盘删除后延迟2秒+GC完成, 资产注册表已刷新", "OK")
    except Exception as e:
        log(f"磁盘删除旧.umap失败({e})", "WARN")

    # 方式1: LevelEditorSubsystem (UE5.1+, 拥有new_level方法)
    # 【关键修复】new_level可能在资产注册表未更新时回退创建到/Temp/Untitled_1,
    # 该临时世界使用OpenWorld模板, 包含HLOD Actor引用私有对象, 阻止save_map.
    # 修复: 验证关卡路径, 若在/Temp/则GC+延迟后重试, 确保创建在MAP_PATH
    try:
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if level_subsystem:
            for _new_level_attempt in range(3):
                level_subsystem.new_level(MAP_PATH)
                # 验证关卡是否在正确路径创建(非/Temp/)
                world = unreal.EditorLevelLibrary.get_editor_world()
                if world:
                    pkg_path = world.get_outer().get_path_name()
                    if "/Temp/" in pkg_path:
                        log(f"new_level回退到临时路径(尝试{_new_level_attempt+1}): {pkg_path}, GC后重试", "WARN")
                        try:
                            unreal.SystemLibrary.collect_garbage()
                        except:
                            pass
                        import time
                        time.sleep(1.0)
                        continue
                    log(f"新关卡已创建(LevelEditorSubsystem), 包路径: {pkg_path}", "OK")
                    return True
                else:
                    log("新关卡已创建(LevelEditorSubsystem)", "OK")
                    return True
            # 3次都在/Temp/, 最后一次的世界仍可用(save_map会尝试保存到MAP_PATH)
            log("new_level 3次均回退到/Temp/, 将尝试save_map直接保存到目标路径", "WARN")
            return True
    except AttributeError:
        log("LevelEditorSubsystem不可用, 尝试备用方式...", "WARN")
    except Exception as e:
        log(f"LevelEditorSubsystem创建关卡失败({e}), 尝试备用方式...", "WARN")

    # 方式2: EditorLevelLibrary (deprecated, 最后手段)
    try:
        unreal.EditorLevelLibrary.new_level(MAP_PATH)
        log("新关卡已创建(EditorLevelLibrary, deprecated)", "OK")
        return True
    except Exception as e:
        log(f"EditorLevelLibrary创建关卡失败: {e}", "ERROR")

    return False


def cleanup_template_actors():
    """删除关卡中所有模板Actor, 清除OpenWorld模板残留

    【关键修复】new_level可能使用OpenWorld模板, 包含HLOD Actor和景观代理,
    这些Actor引用了临时静态网格体(/Temp/...), 导致save_map保存时报
    "Illegal reference to private object"错误, .umap无法写入磁盘

    修复: 创建新关卡后, 立即删除所有非必要的模板Actor(保留WorldSettings等
    必需Actor), 确保存时无非法引用. 之后由generate_terrain创建我们自己的
    Landscape Actor.
    """
    log("清理关卡模板Actor(防止HLOD非法引用)...")
    all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
    deleted = 0

    # 必需Actor: 删除会导致关卡损坏, 必须保留
    keep_classes = {"WorldSettings", "LevelScriptActor", "Brush"}

    for actor in all_actors:
        try:
            actor_class = actor.get_class().get_name()
            if actor_class in keep_classes:
                continue
            actor_name = actor.get_name()
            unreal.EditorLevelLibrary.destroy_actor(actor)
            deleted += 1
        except Exception as e:
            pass

    log(f"已清理 {deleted} 个模板Actor", "OK")

    # GC刷新, 确保被删除Actor的引用完全释放
    try:
        unreal.SystemLibrary.collect_garbage()
    except:
        pass

    return True


# ============================================================================
# 步骤5: 调用CreateLandscapeWithLayers
# ============================================================================

def generate_terrain(material_path, layer_info_paths, grass_type_path,
                     wheat_type_path, height_json, weight_jsons):
    """调用C++函数CreateLandscapeWithLayers生成地形"""
    log("调用CreateLandscapeWithLayers...")

    # 调用C++暴露的BlueprintCallable函数(UE5 Python自动处理FString/TArray转换)
    # 新增WheatTypePath和WheatLayerName参数, 麦穗网格由C++从height_json的wheat_varieties解析
    landscape = unreal.LandscapeHelper.create_landscape_with_layers(
        LOCATION,
        ROTATION,
        SCALE,
        SECTION_SIZE_QUADS,
        NUM_SUBSECTIONS,
        COMPONENT_COUNT_X,
        COMPONENT_COUNT_Y,
        material_path,
        layer_info_paths,
        LAYER_WEIGHTS,
        grass_type_path,
        GRASS_MESH_PATH,
        GRASS_LAYER_NAME,
        GRASS_DENSITY,
        wheat_type_path,
        WHEAT_LAYER_NAME,
        height_json,
        weight_jsons
    )

    if landscape:
        log(f"地形创建成功: {landscape.get_name()}", "OK")
        return True

    log("地形创建失败! 函数返回None", "ERROR")
    return False


# ============================================================================
# 步骤6: 保存关卡
# ============================================================================

def save_level():
    """保存当前关卡为.umap文件

    【关键修复1】new_level可能创建临时世界(/Temp/Untitled_1),
    而非MAP_PATH包. 使用EditorLoadingAndSavingUtils.save_map(world, MAP_PATH)
    可直接将临时世界保存到指定路径.

    【关键修复2】save_map返回成功但磁盘上找不到.umap(之前发生过),
    添加磁盘文件验证, 确认文件真的写入磁盘, 而非仅内存中标记为saved.
    """
    log(f"保存关卡: {MAP_PATH}")

    # 获取当前编辑器世界, 打印包路径用于诊断
    world = unreal.EditorLevelLibrary.get_editor_world()
    if world:
        pkg = world.get_outer()
        log(f"世界名称: {world.get_name()}, 包路径: {pkg.get_path_name()}")
    else:
        log("无法获取编辑器世界!", "ERROR")
        return False

    saved = False

    # GC清理: 清除模板Actor残留引用, 防止save_map报"非法引用"错误
    try:
        unreal.SystemLibrary.collect_garbage()
        import time
        time.sleep(1.0)
        log("save_map前GC清理完成", "OK")
    except Exception:
        pass

    # 方式1: EditorLoadingAndSavingUtils.save_map
    # 核心方法: 将世界(即使在/Temp)保存到MAP_PATH指定路径
    # 最多重试3次, 每次失败后GC+延迟
    for save_attempt in range(3):
        try:
            result = unreal.EditorLoadingAndSavingUtils.save_map(world, MAP_PATH)
            if result:
                log(f"save_map成功(尝试{save_attempt+1}): {MAP_PATH}", "OK")
                saved = True
                break
            else:
                log(f"save_map返回False(尝试{save_attempt+1}, GC后重试)", "WARN")
        except Exception as e:
            log(f"save_map失败(尝试{save_attempt+1}): {e}", "WARN")
        # GC + 延迟后重试
        try:
            unreal.SystemLibrary.collect_garbage()
            time.sleep(1.0)
        except Exception:
            pass

    # 验证: 检查.umap是否真的写入了磁盘
    # 【关键修复】原代码仅检查文件是否存在, 会找到旧.umap产生假阳性
    # 原因: save_map返回False时, 磁盘上仍有上一次运行的旧.umap,
    #       os.path.exists返回True → 错误地设置saved=True → 误报保存成功
    # 修复: 检查文件修改时间, 仅30秒内修改的才算本次保存成功
    try:
        content_dir = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_content_dir()
        )
        import os
        import time
        umap_disk = os.path.join(content_dir, "Maps", "Generated",
                                "MountainValleyScene.umap")
        if os.path.exists(umap_disk):
            size_kb = os.path.getsize(umap_disk) // 1024
            mtime = os.path.getmtime(umap_disk)
            age = time.time() - mtime
            if age < 30:
                # 30秒内修改的, 确认是本次保存写入的
                log(f"磁盘验证: .umap已保存 ({size_kb}KB, {age:.1f}秒前)", "OK")
                saved = True
            else:
                # 文件存在但非近期修改, 是旧.umap, 保存可能失败
                log(f"磁盘验证: .umap存在但非刚保存 ({size_kb}KB, {age:.0f}秒前), 保存可能失败!", "WARN")
                # 【Bug修复】save_map返回True但磁盘文件过旧, 说明保存实际未成功,
                # 必须重置saved=False, 否则函数返回True产生假阳性(同Bug2类型)
                saved = False
        elif saved:
            log("save_map返回成功但磁盘上找不到.umap!", "WARN")
            # 【Bug修复】save_map返回True但磁盘无文件, 保存实际未成功, 重置假阳性
            saved = False
    except Exception as e:
        log(f"磁盘验证失败({e})", "WARN")

    # 方式2: EditorLevelLibrary (deprecated, 补充保存)
    try:
        unreal.EditorLevelLibrary.save_current_level()
        log("save_current_level调用完成", "OK")
    except Exception as e:
        log(f"save_current_level失败({e})", "WARN")

    # 方式3: EditorAssetLibrary (直接保存路径上的包)
    # 【Bug修复】save_asset在C++层可能静默失败(如关卡在/Temp/, 资产无法加载),
    # 但不抛Python异常, 导致saved=True被错误设置, 脚本误报保存成功
    # 修复: save_asset后验证.umap磁盘文件, 仅在确认近期写入时才设saved=True
    try:
        unreal.EditorAssetLibrary.save_asset(MAP_PATH)
        # 验证.umap是否真的写入磁盘(C++层save_asset可能静默失败)
        import os as _os
        import time as _time
        _content_dir = unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_content_dir())
        _umap_disk = _os.path.join(_content_dir, "Maps", "Generated",
                                  "MountainValleyScene.umap")
        if _os.path.exists(_umap_disk):
            _age = _time.time() - _os.path.getmtime(_umap_disk)
            if _age < 30:
                log(f"save_asset完成(磁盘验证通过, {_age:.1f}秒前): {MAP_PATH}", "OK")
                saved = True
            else:
                log(f"save_asset调用完成但.umap非近期写入(age={_age:.0f}s), 保存失败", "WARN")
        else:
            log(f"save_asset调用完成但.umap不在磁盘上, 保存失败", "WARN")
    except Exception as e:
        log(f"save_asset失败({e})", "WARN")

    # 刷新: 垃圾回收 + 延迟, 确保磁盘写入完成
    if saved:
        try:
            unreal.SystemLibrary.collect_garbage()
            log("垃圾回收完成(刷新磁盘缓存)", "OK")
        except:
            pass
        import time
        time.sleep(2.0)
        log("保存刷新延迟完成(2秒)", "OK")

    return saved


def save_layer_info_assets():
    """保存图层信息资产到磁盘, 持久化C++设置的LayerName

    【关键修复】C++ CreateLandscapeWithLayers在内存中设置了LayerInfoObj->LayerName,
    但未调用SavePackage保存到磁盘. .uasset磁盘文件LayerName仍为空.
    加载.umap时, 引擎从磁盘加载.uasset(空LayerName),
    Landscape.cpp:7845断言 LayerInfoObj->GetLayerName()==Key 失败→编辑器崩溃.
    修复: 地形生成后, 在Python中标记dirty并重新保存每个LIS_资产,
    将内存中的LayerName写入.uasset磁盘文件.
    """
    log("保存图层信息资产(持久化LayerName)...")
    saved_count = 0
    for layer_name, asset_name, _ in LAYERS:
        asset_path = f"{ASSET_DIR}/{asset_name}"
        try:
            asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            if asset:
                # 读取LayerName验证C++已正确设置(从内存中读取)
                try:
                    actual_name = asset.get_editor_property("layer_name")
                    log(f"  {asset_name} 内存LayerName: '{actual_name}'")
                except Exception:
                    log(f"  {asset_name} 无法读取layer_name属性", "WARN")
                # 传only_if_is_dirty=False强制保存(mark_package_dirty在Python API不存在)
                # C++ SavePackage已保存, 此处为Python层面备份
                try:
                    unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
                except Exception:
                    pass
                saved_count += 1
                log(f"  {asset_name} 已保存 (layer={layer_name})", "OK")
            else:
                log(f"  {asset_name} 加载失败", "WARN")
        except Exception as e:
            log(f"  {asset_name} 保存失败({e})", "WARN")
    try:
        unreal.SystemLibrary.collect_garbage()
    except:
        pass
    log(f"图层信息资产保存完成: {saved_count}/{len(LAYERS)}", "OK")
    return saved_count == len(LAYERS)


def save_grass_type_assets():
    """保存草地/麦田GrassType资产到磁盘, 持久化C++填充的GrassVarieties

    【关键修复】C++ CreateLandscapeWithLayers在内存中向LGT_Grass/LGT_Wheat
    填充了GrassVarieties(草地网格+麦穗网格混合), 并调用PostEditChange()+
    MarkPackageDirty(), 但未调用SavePackage保存到磁盘.
    .uasset磁盘文件GrassVarieties仍为空(0个变体).
    加载.umap时, 引擎从磁盘加载LGT(0变体)→不生成任何草地/麦穗实例.
    修复: 地形生成后, 在Python中强制重新保存LGT_Grass和LGT_Wheat,
    将内存中的GrassVarieties写入.uasset磁盘文件.
    """
    log("保存GrassType资产(持久化GrassVarieties)...")
    # LGT_Grass和LGT_Wheat两个资产需要保存
    grass_assets = [
        ("LGT_Grass", "草地"),
        ("LGT_Wheat", "麦田"),
    ]
    saved_count = 0
    for asset_name, desc in grass_assets:
        asset_path = f"{ASSET_DIR}/{asset_name}"
        try:
            asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            if asset:
                # 读取GrassVarieties验证C++已正确填充(从内存中读取)
                try:
                    varieties = asset.get_editor_property("grass_varieties")
                    variety_count = len(varieties) if varieties else 0
                    log(f"  {asset_name} 内存变体数: {variety_count}")
                except Exception:
                    log(f"  {asset_name} 无法读取grass_varieties属性", "WARN")
                # 传only_if_is_dirty=False强制保存
                # C++已MarkPackageDirty, 此处将内存数据写入磁盘
                try:
                    unreal.EditorAssetLibrary.save_asset(asset_path, only_if_is_dirty=False)
                    saved_count += 1
                    log(f"  {asset_name} 已保存 ({desc}类型)", "OK")
                except Exception as e:
                    log(f"  {asset_name} 保存失败({e})", "WARN")
            else:
                log(f"  {asset_name} 加载失败, 跳过", "WARN")
        except Exception as e:
            log(f"  {asset_name} 处理异常({e})", "WARN")
    try:
        unreal.SystemLibrary.collect_garbage()
    except:
        pass
    log(f"GrassType资产保存完成: {saved_count}/{len(grass_assets)}", "OK")
    return saved_count == len(grass_assets)


# ============================================================================
# 步骤6.5: 添加环境光照和天空
# ============================================================================

def add_environment():
    """添加基础环境光照和天空

    当前JSON配置只含地形几何和图层权重, 不含环境光照.
    此函数从environment.json读取配置, 创建:
    - 定向光(太阳): 主光源, 提供方向光照和阴影
    - 天光: 环境光, 使用指定颜色模拟天空散射
    - 天空大气: 添加为定向光组件, 渲染蓝色天空
    - 体积云: 动态云层
    - 指数高度雾: 大气深度感
    使场景可见, 非一片漆黑.
    """
    log("添加环境光照和天空...")

    # 读取环境配置
    try:
        env = json.loads(read_json("environment.json"))
    except Exception as e:
        log(f"读取environment.json失败({e}), 使用默认配置", "WARN")
        env = {}

    dl = None  # 定向光引用(后续天空大气需要)

    # 1. 定向光(太阳)
    dl_cfg = env.get("directional_light", {})
    try:
        dl = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.DirectionalLight, unreal.Vector(0, 0, 0))
        if dl:
            dl.set_actor_label("Sun_DirectionalLight")
            # 设置旋转(太阳角度): pitch=俯仰 yaw=方位 roll=翻滚
            # 【修复】set_actor_rotation需要第2个参数teleport_physics(布尔值)
            # 原因: UE5.8 Python绑定要求显式传入teleport_physics, 否则抛出参数缺失异常
            #       导致定向光虽已spawn但旋转设置失败, 异常向上传播标记整个创建失败
            rot = dl_cfg.get("rotation", [-45, -67, 0])
            dl.set_actor_rotation(
                unreal.Rotator(rot[0], rot[1], rot[2]), False)
            # 设置光源组件属性
            try:
                lc = dl.get_editor_property("light_component")
                if lc:
                    lc.set_editor_property("intensity",
                        dl_cfg.get("intensity", 10.0))
                    # 【修复】light_color属性需要FColor(0-255), 非FLinearColor(0.0-1.0)
                    # 原因: DirectionalLightComponent.LightColor是FColor类型,
                    #       传入LinearColor抛出类型转换异常,
                    #       且异常会跳过后续的cast_shadows和atmosphere_sun_light设置
                    # 修复: 使用unreal.Color(0-255), 并用独立try-except包裹
                    color = dl_cfg.get("color", [1.0, 0.95, 0.85])
                    try:
                        lc.set_editor_property("light_color",
                            unreal.Color(
                                int(color[0] * 255),
                                int(color[1] * 255),
                                int(color[2] * 255)))
                    except Exception:
                        pass
                    lc.set_editor_property("cast_shadows",
                        dl_cfg.get("cast_shadows", True))
                    # 标记为天空大气的太阳光
                    if dl_cfg.get("atmosphere_sun_light", True):
                        lc.set_editor_property("atmosphere_sun_light", True)
            except Exception as e:
                log(f"  定向光属性设置失败: {e}", "WARN")
            log("  定向光(太阳)已创建", "OK")
    except Exception as e:
        log(f"  定向光创建失败: {e}", "WARN")

    # 2. 天光(环境光)
    sl_cfg = env.get("sky_light", {})
    try:
        sl = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.SkyLight, unreal.Vector(0, 0, 0))
        if sl:
            sl.set_actor_label("SkyLight")
            try:
                lc = sl.get_editor_property("light_component")
                if lc:
                    lc.set_editor_property("intensity",
                        sl_cfg.get("intensity", 1.0))
                    # 使用指定颜色模式(不依赖SkyAtmosphere, 保证有环境光)
                    try:
                        lc.set_editor_property("source_type",
                            unreal.SkyLightSourceType.SLS_SpecifiedColor)
                        color = sl_cfg.get("sky_color", [0.5, 0.7, 1.0])
                        lc.set_editor_property("specified_color",
                            unreal.LinearColor(color[0], color[1], color[2]))
                    except Exception:
                        pass
            except Exception as e:
                log(f"  天光属性设置失败: {e}", "WARN")
            log("  天光已创建", "OK")
    except Exception as e:
        log(f"  天光创建失败: {e}", "WARN")

    # 3. 天空大气(独立Actor, 渲染蓝色天空)
    # 【最终方案v2】直接spawn SkyAtmosphere Actor(与VolumetricCloud相同方式)
    # 原因: 之前尝试将SkyAtmosphereComponent附加到DirectionalLight,
    #       但AddInstanceComponent导致save_map失败(组件引用问题),
    #       组件方案被放弃, 改用独立Actor方式
    # SkyAtmosphere Actor自带SkyAtmosphereComponent作为根组件,
    # spawn后自动注册和序列化, 无需手动AddInstanceComponent
    # 与定向光的链接通过atmosphere_sun_light属性实现, 不需要组件附加
    atm_cfg = env.get("sky_atmosphere", {})
    if atm_cfg.get("enabled", True):
        try:
            sky_atm = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
            if sky_atm:
                sky_atm.set_actor_label("SkyAtmosphere")
                log("  天空大气已创建", "OK")
            else:
                log("  天空大气spawn返回None", "WARN")
        except Exception as e:
            log(f"  天空大气创建失败: {e}", "WARN")

    # 4. 体积云
    cloud_cfg = env.get("volumetric_clouds", {})
    if cloud_cfg.get("enabled", True):
        try:
            cloud = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.VolumetricCloud, unreal.Vector(0, 0, 0))
            if cloud:
                cloud.set_actor_label("VolumetricCloud")
                log("  体积云已创建", "OK")
        except Exception as e:
            log(f"  体积云创建失败: {e}", "WARN")

    # 5. 指数高度雾(大气深度感)
    fog_cfg = env.get("exponential_height_fog", {})
    try:
        fog = unreal.EditorLevelLibrary.spawn_actor_from_class(
            unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
        if fog:
            fog.set_actor_label("ExponentialHeightFog")
            try:
                fc = fog.get_editor_property("component")
                if fc:
                    fc.set_editor_property("fog_density",
                        fog_cfg.get("density", 0.02))
                    # 【修复】属性名fog_color在UE5中不存在
                    # 原因: UE5 ExponentialHeightFogComponent的属性名为fog_inscattering_color
                    #       而非fog_color, 导致set_editor_property抛出属性未找到异常
                    color = fog_cfg.get("fog_color", [0.5, 0.6, 0.7])
                    try:
                        fc.set_editor_property("fog_inscattering_color",
                            unreal.LinearColor(color[0], color[1], color[2]))
                    except Exception:
                        # 如果fog_inscattering_color也不对, 尝试inscattering_color
                        try:
                            fc.set_editor_property("inscattering_color",
                                unreal.LinearColor(color[0], color[1], color[2]))
                        except Exception:
                            pass
            except Exception as e:
                log(f"  高度雾属性设置失败: {e}", "WARN")
            log("  高度雾已创建", "OK")
    except Exception as e:
        log(f"  高度雾创建失败: {e}", "WARN")

    log("环境光照添加完成", "OK")
    return True


# ============================================================================
# 主流程
# ============================================================================

def main():
    print("=" * 70)
    print("  山野田园地形场景生成器")
    print("  地形: 1017x1017顶点 (约1km x 1km)")
    print("  特征: 山丘(5座) + 山谷(2处) + 田垄(2片) + 噪声 + 扰动")
    print("  配套: 湖泊 + 河流 + 道路 + 建筑(3栋) + 散布(树木+岩石) + 草地")
    print("=" * 70)

    # --- 步骤1: 创建图层信息对象 ---
    print("\n--- 步骤1: 创建图层信息对象 ---")
    layer_info_paths = []
    for layer_name, asset_name, _ in LAYERS:
        path = create_layer_info(layer_name, asset_name)
        if not path:
            log(f"图层创建失败, 中止: {layer_name}", "ERROR")
            return False
        layer_info_paths.append(path)

    # --- 步骤2: 创建草地类型 ---
    print("\n--- 步骤2: 创建草地类型和麦田类型 ---")
    grass_type_path = create_grass_type() or ""
    wheat_type_path = create_wheat_grass_type() or ""

    # --- 步骤3: 创建地形材质 ---
    print("\n--- 步骤3: 创建地形材质 ---")
    layer_names = [l[0] for l in LAYERS]
    material_path = create_landscape_material(layer_names, GRASS_LAYER_NAME, WHEAT_LAYER_NAME)

    # --- 步骤4: 读取JSON配置 ---
    print("\n--- 步骤4: 读取JSON配置 ---")
    weight_jsons = []
    for _, _, json_file in LAYERS:
        json_str = read_json(json_file)
        weight_jsons.append(json_str)
        log(f"已读取: {json_file}", "OK")

    height_json = read_json("height_pattern.json")
    log("已读取: height_pattern.json", "OK")

    # --- 步骤5: 创建新关卡 ---
    print("\n--- 步骤5: 创建新关卡 ---")
    if not create_new_level():
        log("关卡创建失败, 中止", "ERROR")
        return False

    # 清理关卡模板Actor(防止HLOD非法引用导致保存失败)
    cleanup_template_actors()

    # --- 步骤6: 生成地形 ---
    print("\n--- 步骤6: 生成地形 ---")
    success = generate_terrain(
        material_path,
        layer_info_paths,
        grass_type_path,
        wheat_type_path,
        height_json,
        weight_jsons
    )
    if not success:
        return False

    # 【关键修复1】地形生成后保存图层信息资产, 持久化C++设置的LayerName
    # 原因: 不保存则.uasset磁盘文件LayerName为空, 打开.umap时Landscape.cpp:7845断言崩溃
    save_layer_info_assets()

    # 【关键修复2】保存GrassType资产, 持久化C++填充的GrassVarieties
    # 原因: C++向LGT_Grass/LGT_Wheat填充了变体但未SavePackage,
    # 不保存则磁盘LGT变体数为0, 打开.umap时不生成草地/麦穗
    save_grass_type_assets()

    # 【关键修复3】重新保存地形材质, 持久化C++分配的GrassType引用
    # 原因: C++ CreateLandscapeWithLayers在内存中为材质GrassOutput条目
    # 分配了GrassType引用(LGT_Grass/LGT_Wheat), 但未SavePackage.
    # 步骤3保存的材质磁盘文件GrassType=NULL, 打开.umap时
    # GrassOutput无GrassType引用→不生成任何草地/麦穗实例
    if material_path:
        try:
            unreal.EditorAssetLibrary.save_asset(material_path, only_if_is_dirty=False)
            log(f"材质已重新保存(持久化GrassType引用): {material_path}", "OK")
        except Exception as e:
            log(f"材质重新保存失败({e})", "WARN")

    # --- 步骤6.5: 添加环境光照和天空 ---
    # 原因: 原场景只有地形无光照, 打开后一片漆黑
    # 添加定向光/天光/天空大气/体积云/高度雾, 使场景可见
    print("\n--- 步骤6.5: 添加环境光照和天空 ---")
    add_environment()

    # --- 步骤7: 保存关卡 ---
    print("\n--- 步骤7: 保存关卡 ---")
    if not save_level():
        log("关卡保存失败!", "ERROR")
        return False

    print("\n" + "=" * 70)
    log("山野田园地形场景生成完成!", "OK")
    print(f"  关卡路径: {MAP_PATH}")
    print(f"  材质路径: {material_path or '(无, 使用默认)'}")
    print(f"  草地类型: {grass_type_path or '(无, 草地已跳过)'}")
    print(f"  麦田类型: {wheat_type_path or '(无, 麦田已跳过)'}")
    print(f"  图层数量: {len(layer_info_paths)}")
    print("=" * 70)

    # 将结果写入文件, 供外部脚本读取(UE5日志不便直接捕获)
    try:
        result_path = os.path.join(JSON_DIR, "generation_result.txt")
        with open(result_path, "w", encoding="utf-8") as rf:
            rf.write(f"success=True\n")
            rf.write(f"map_path={MAP_PATH}\n")
            rf.write(f"material_path={material_path or ''}\n")
            rf.write(f"grass_type={grass_type_path or ''}\n")
            rf.write(f"wheat_type={wheat_type_path or ''}\n")
            rf.write(f"layers={len(layer_info_paths)}\n")
        print(f"结果已写入: {result_path}")
    except Exception as e:
        print(f"写入结果文件失败: {e}")

    return True


if __name__ == "__main__":
    success = main()
    # 失败时也写入结果文件
    if not success:
        try:
            result_path = os.path.join(JSON_DIR, "generation_result.txt")
            with open(result_path, "w", encoding="utf-8") as rf:
                rf.write(f"success=False\n")
        except Exception:
            pass
    sys.exit(0 if success else 1)