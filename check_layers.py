import unreal, os

log_path = "c:/Users/25868/Desktop/UE5/check_layers.log"

def log(msg):
    line = "[CHECK] " + str(msg)
    print(line, flush=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

with open(log_path, "w", encoding="utf-8") as f:
    f.write("")

log("CHECK_LAYERS_START")

# 检查所有 LayerInfoObject 的 LayerName
layer_info_paths = [
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer2_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer3_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer4_LayerInfo",
    "/Game/RuralHouse/Landscape/LandscapeLayers/Layer5_LayerInfo",
]

log("--- LayerInfoObject 属性检查 ---")
for path in layer_info_paths:
    try:
        obj = unreal.EditorAssetLibrary.load_asset(path)
        if obj:
            layer_name = obj.get_editor_property("layer_name")
            log(f"{path} -> LayerName='{layer_name}'")
        else:
            log(f"{path} -> 加载失败!")
    except Exception as e:
        log(f"{path} -> 错误: {e}")

# 检查 GrassType 资产
log("")
log("--- GrassType 资产检查 ---")
gt_path = "/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass"
try:
    gt = unreal.EditorAssetLibrary.load_asset(gt_path)
    if gt:
        log(f"LGT_Grass 已加载: {gt_path}")
        # 检查 GrassVarieties
        try:
            varieties = gt.get_editor_property("grass_varieties")
            if varieties:
                log(f"GrassVarieties 数量: {len(varieties)}")
                for i, v in enumerate(varieties):
                    try:
                        mesh = v.get_editor_property("grass_mesh")
                        density = v.get_editor_property("grass_density")
                        log(f"  Variety[{i}]: mesh={mesh}, density={density}")
                    except:
                        log(f"  Variety[{i}]: 无法读取属性")
            else:
                log("GrassVarieties 为空!")
        except Exception as e:
            log(f"获取 GrassVarieties 失败: {e}")
    else:
        log(f"LGT_Grass 加载失败: {gt_path}")
except Exception as e:
    log(f"LGT_Grass 错误: {e}")

# 检查 Grass Mesh
log("")
log("--- Grass Mesh 检查 ---")
mesh_path = "/Game/RuralHouse/Environment/Foliage/SM_Grass_01"
try:
    mesh = unreal.EditorAssetLibrary.load_asset(mesh_path)
    if mesh:
        log(f"Grass Mesh 已加载: {mesh_path}")
    else:
        log(f"Grass Mesh 加载失败: {mesh_path} - 尝试其他路径")
        # 尝试其他可能的路径
        alt_paths = [
            "/Game/RuralHouse/Environment/Foliage/SM_Grass",
            "/Game/RuralHouse/Environment/Foliage/SM_Grass_1",
            "/Game/RuralHouse/Environment/Foliage/Grass/SM_Grass_01",
        ]
        for ap in alt_paths:
            m = unreal.EditorAssetLibrary.load_asset(ap)
            if m:
                log(f"  找到 Grass Mesh: {ap}")
                break
except Exception as e:
    log(f"Grass Mesh 错误: {e}")

# 检查材质参数
log("")
log("--- 材质实例参数检查 ---")
mat_path = "/Game/RuralHouse/Landscape/MI_Landscape"
try:
    mat = unreal.EditorAssetLibrary.load_asset(mat_path)
    if mat:
        log(f"MI_Landscape 已加载")
        # 检查材质参数
        try:
            params = mat.get_editor_property("scalar_parameter_values")
            log(f"Scalar 参数数: {len(params) if params else 0}")
            for p in (params or [])[:5]:
                try:
                    name = p.get_editor_property("parameter_info").get_editor_property("name")
                    val = p.get_editor_property("parameter_value")
                    log(f"  Scalar: {name} = {val}")
                except:
                    pass
        except:
            log("无法获取 scalar_parameter_values")
        
        try:
            tex_params = mat.get_editor_property("texture_parameter_values")
            log(f"Texture 参数数: {len(tex_params) if tex_params else 0}")
            for p in (tex_params or [])[:5]:
                try:
                    name = p.get_editor_property("parameter_info").get_editor_property("name")
                    val = p.get_editor_property("parameter_value")
                    log(f"  Texture: {name} = {val}")
                except:
                    pass
        except:
            log("无法获取 texture_parameter_values")
except Exception as e:
    log(f"材质检查错误: {e}")

log("CHECK_LAYERS_DONE")
