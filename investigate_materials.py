# ============================================================================
# investigate_materials.py - 调查 Landscape 材质和草类型资产的属性
# 目的: 确认 MI_Landscape/MM_LandscapeBase 是否已有 LandscapeGrassOutput 节点,
#       以及5个图层信息对象的名称和GUID, 为C++填充权重数据做准备
# ============================================================================
import unreal
import os

LOG_PATH = "c:/Users/25868/Desktop/UE5/MapForgeTest/investigate_materials.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

# 1. 检查 MI_Landscape 材质和其父材质 MM_LandscapeBase
log("=" * 60)
log("1. 检查 MI_Landscape 和 MM_LandscapeBase")
log("=" * 60)

mi = unreal.EditorAssetLibrary.load_asset("/Game/RuralHouse/Landscape/MI_Landscape")
if mi:
    log("MI_Landscape loaded: " + mi.get_path_name())
    # 获取父材质
    try:
        parent = mi.get_editor_property("parent")
        if parent:
            log("  Parent material: " + parent.get_path_name())
            # 遍历所有表达式, 查找 LandscapeGrassOutput 和 TextureSampleParameter2D
            try:
                exprs = parent.get_editor_property("expressions")
                log("  Total expressions: " + str(len(exprs)))
                grass_count = 0
                texture_params = []
                for expr in exprs:
                    try:
                        class_name = expr.get_class().get_name()
                        if "LandscapeGrass" in class_name:
                            grass_count += 1
                            log("  >>> FOUND LandscapeGrassOutput!")
                            # 尝试读取 grass output 的属性
                            for prop in ["layer_name", "grass_types"]:
                                try:
                                    val = expr.get_editor_property(prop)
                                    log("      " + prop + ": " + str(val))
                                except Exception as ep:
                                    log("      " + prop + " (err): " + str(ep))
                        elif "TextureSampleParameter2D" in class_name:
                            try:
                                pname = expr.get_editor_property("parameter_name")
                                texture_params.append(str(pname))
                            except:
                                pass
                    except:
                        pass
                log("  LandscapeGrassOutput count: " + str(grass_count))
                log("  TextureSampleParameter2D layers: " + ", ".join(texture_params))
            except Exception as e:
                log("  expressions error: " + str(e))
        else:
            log("  No parent material!")
    except Exception as e:
        log("  parent error: " + str(e))
else:
    log("MI_Landscape NOT FOUND!")

# 2. 检查 LGT_Grass (LandscapeGrassType) 的属性
log("")
log("=" * 60)
log("2. 检查 LGT_Grass")
log("=" * 60)

lgt = unreal.EditorAssetLibrary.load_asset(
    "/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass")
if lgt:
    log("LGT_Grass loaded: " + lgt.get_path_name())
    # 尝试读取所有可能的属性
    props_to_check = [
        "grass_mesh", "density", "scale_x", "scale_y", "scale_z",
        "random_rotation", "placement_jitter", "start_guid",
        "use_grid", "render_layer_change", "influence_over_landscape",
        "landscape_layers"
    ]
    for prop_name in props_to_check:
        try:
            val = lgt.get_editor_property(prop_name)
            log("  " + prop_name + ": " + str(val))
        except:
            pass
else:
    log("LGT_Grass NOT FOUND!")

# 3. 检查5个图层信息对象 (ULandscapeLayerInfoObject)
# 这些对象定义了图层的名称和GUID, 在Import时需要匹配
log("")
log("=" * 60)
log("3. 检查 Layer Info 对象 (名称+GUID)")
log("=" * 60)

layer_paths = [
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer2_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer3_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer4_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer5_LayerInfo",
]

layer_infos = []
for i, lp in enumerate(layer_paths):
    try:
        li = unreal.EditorAssetLibrary.load_asset(lp)
        if li:
            log("Layer" + str(i+1) + " loaded: " + li.get_path_name())
            for prop in ["layer_name", "layer_guid", "channel", "physical_material"]:
                try:
                    val = li.get_editor_property(prop)
                    log("  " + prop + ": " + str(val))
                    if prop == "layer_name":
                        layer_infos.append((i+1, str(val)))
                except:
                    pass
        else:
            log("Layer" + str(i+1) + " NOT FOUND: " + lp)
    except Exception as e:
        log("Layer" + str(i+1) + " error: " + str(e))

log("")
log("Layer summary: " + str(layer_infos))

# 4. 检查 MI_Landscape 的纹理参数值 (确认纹理路径正确)
log("")
log("=" * 60)
log("4. 检查 MI_Landscape 纹理参数值")
log("=" * 60)

if mi:
    try:
        params = mi.get_editor_property("texture_parameter_values")
        log("texture_parameter_values count: " + str(len(params)))
        for p in params:
            try:
                name = p.get_editor_property("parameter_name")
                val = p.get_editor_property("parameter_value")
                log("  " + str(name) + " = " + str(val))
            except:
                pass
    except Exception as e:
        log("texture_parameter_values error: " + str(e))

    try:
        params = mi.get_editor_property("scalar_parameter_values")
        log("scalar_parameter_values count: " + str(len(params)))
        for p in params:
            try:
                name = p.get_editor_property("parameter_name")
                val = p.get_editor_property("parameter_value")
                log("  " + str(name) + " = " + str(val))
            except:
                pass
    except Exception as e:
        log("scalar_parameter_values error: " + str(e))

# 5. 检查可用的草网格 (用于LGT)
log("")
log("=" * 60)
log("5. 检查可用草网格")
log("=" * 60)

grass_meshes = [
    "/Game/RuralHouse/Environment/Foliage/SM_Grass_01",
    "/Game/RuralHouse/Environment/Foliage/SM_Grass_02",
    "/Game/RuralHouse/Environment/Foliage/SM_Grass_03",
    "/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a",
    "/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Beach_01a",
]
for gm in grass_meshes:
    exists = unreal.EditorAssetLibrary.does_asset_exist(gm)
    log(gm + ": " + ("EXISTS" if exists else "NOT FOUND"))

# 6. 检查 Landscape_Grass_Showcase.umap 是否有已有的草地配置参考
log("")
log("=" * 60)
log("6. 检查 Landscape_Grass_Showcase.umap")
log("=" * 60)

showcase_exists = unreal.EditorAssetLibrary.does_asset_exist(
    "/Game/Landscape_Grass_Showcase")
log("Landscape_Grass_Showcase.umap: " + ("EXISTS" if showcase_exists else "NOT FOUND"))

log("")
log("INVESTIGATION_DONE")
_f.close()
