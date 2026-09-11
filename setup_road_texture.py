"""
乡间土路纹理导入 + 材质创建脚本
功能:
  1. 将 DirtTextures/TX_Dirt_*.jpg 导入到 UE5 /Game/MapForgeTest/Textures/
  2. 创建 M_Road_Dirt 材质, 使用 WorldAligned UV 链实现世界坐标对齐的纹理平铺
  3. 连接 ALB.RGB→BaseColor, NRM.RGB→Normal, RMA.R→Roughness, RMA.G→Metallic, RMA.B→AO
  4. 编译并保存材质

材质节点链 (所有引脚名已由 probe_results.json 确认):
  WorldPosition(XY) ───────────────────────→ Divide.A
  Constant3Vector(256,256,256) → ComponentMask(RG) → Divide.B
  Divide("") → 3× TextureSampleParameter2D.UVs (扇出, UE 允许一个输出连多个输入)
  ALB.RGB → MP_BASE_COLOR
  NRM.RGB → MP_NORMAL
  RMA.R  → MP_ROUGHNESS
  RMA.G  → MP_METALLIC
  RMA.B  → MP_AMBIENT_OCCLUSION

平铺原理:
  WorldPosition 输出世界坐标(单位 cm), 除以平铺尺寸(256cm)后得到世界对齐 UV,
  纹理每 2.56m 重复一次, 与道路网格的缩放/旋转无关 → 不会拉伸
"""
import unreal
import os
import traceback

# 文件级日志 (避免 print 缓冲导致日志丢失, 参考 colorize.py 模式)
LOG_PATH = "c:/Users/25868/Desktop/UE5/MapForgeTest/setup_road_texture.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    """同时输出到 stdout 和文件, 每行 flush"""
    line = str(msg)
    print(line)
    _f.write(line + "\n")
    _f.flush()

log("SETUP_ROAD_TEXTURE_START")

# ==================== 配置 ====================
DIRT_DIR = r"c:\Users\25868\Desktop\UE5\MapForgeTest\DirtTextures"
TEX_DEST = "/Game/MapForgeTest/Textures"
MAT_PACKAGE = "/Game/MapForgeTest"
MAT_NAME = "M_Road_Dirt"
TILE_SIZE_CM = 256.0  # 纹理平铺周期 = 256cm = 2.56m

# 三张泥土贴图配置 (PBR 三件套)
TEXTURES = {
    "ALB": {"file": "TX_Dirt_ALB.jpg", "srgb": True,  "compression": "default"},
    "NRM": {"file": "TX_Dirt_NRM.jpg", "srgb": False, "compression": "normalmap"},
    "RMA": {"file": "TX_Dirt_RMA.jpg", "srgb": False, "compression": "masks"},
}


# ==================== 工具函数 ====================
def import_texture(jpg_path, dest_path, dest_name, srgb, compression):
    """导入单个纹理到 UE5 项目 (参考 setup_snow_texture.py)"""
    task = unreal.AssetImportTask()
    task.set_editor_property("automated", True)
    task.set_editor_property("filename", jpg_path)
    task.set_editor_property("destination_path", dest_path)
    task.set_editor_property("destination_name", dest_name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    asset_path = dest_path + "/" + dest_name + "." + dest_name
    texture = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not texture:
        log(f"  导入失败: {dest_name}")
        return None

    # 设置压缩格式和 sRGB (参考 setup_snow_texture.py 的枚举获取逻辑)
    tcs = unreal.TextureCompressionSettings
    def get_enum(name_tc, name_short):
        try:
            return getattr(tcs, name_tc)
        except AttributeError:
            return getattr(tcs, name_short)

    if compression == "normalmap":
        comp_enum = get_enum("TC_NORMALMAP", "NORMALMAP")
    elif compression == "masks":
        comp_enum = get_enum("TC_MASKS", "MASKS")
    else:
        comp_enum = get_enum("TC_DEFAULT", "DEFAULT")

    texture.set_editor_property("compression_settings", comp_enum)
    texture.set_editor_property("srgb", srgb)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    log(f"  导入成功: {dest_name} (sRGB={srgb}, compression={compression})")
    return texture


def try_connect(editing, src, out_name, dst, in_name, label=""):
    """安全连接两个材质节点, 记录成功/失败"""
    try:
        ok = editing.connect_material_expressions(src, out_name, dst, in_name)
        log(f"  连接 {label}: {'OK' if ok else 'FAIL'}")
        return bool(ok)
    except Exception as e:
        log(f"  连接 {label} 异常: {e}")
        return False


def try_connect_prop(editing, src, out_name, prop, label=""):
    """安全连接节点输出到材质属性, 记录成功/失败"""
    try:
        ok = editing.connect_material_property(src, out_name, prop)
        log(f"  属性连接 {label}: {'OK' if ok else 'FAIL'}")
        return bool(ok)
    except Exception as e:
        log(f"  属性连接 {label} 异常: {e}")
        return False


# ==================== 第1步: 导入贴图 ====================
def step1_import_textures():
    """导入 3 张泥土贴图 (ALB/NRM/RMA)"""
    log("=== 第1步: 导入泥土贴图 ===")
    textures = {}
    for suffix, cfg in TEXTURES.items():
        jpg_path = os.path.join(DIRT_DIR, cfg["file"])
        if not os.path.exists(jpg_path):
            log(f"  文件不存在: {jpg_path}")
            return None
        dest_name = "TX_Dirt_" + suffix
        tex = import_texture(jpg_path, TEX_DEST, dest_name, cfg["srgb"], cfg["compression"])
        if tex:
            textures[suffix] = tex
    if len(textures) < 3:
        log("贴图导入不完整, 中止")
        return None
    log("第1步完成: 3 张泥土贴图已导入")
    return textures


# ==================== 第2步: 创建材质 ====================
def step2_create_material(textures):
    """创建 M_Road_Dirt 材质并构建 WorldAligned UV 链"""
    log("=== 第2步: 创建材质 M_Road_Dirt ===")

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    editing = unreal.MaterialEditingLibrary
    eal = unreal.EditorAssetLibrary

    mat_path = MAT_PACKAGE + "/" + MAT_NAME

    # 删除旧材质 (若存在) → 干净重建
    if eal.does_asset_exist(mat_path):
        eal.delete_asset(mat_path)
        log(f"  已删除旧材质: {mat_path}")

    material = asset_tools.create_asset(MAT_NAME, MAT_PACKAGE, unreal.Material, None)
    if not material:
        log("  材质创建失败!")
        return None
    log(f"  材质已创建: {mat_path}")

    # ---- 构建 WorldAligned UV 链 ----
    # WorldPosition: 输出世界坐标 (引脚 "XY" = 仅 XY 平面坐标, 单位 cm)
    wp = editing.create_material_expression(material, unreal.MaterialExpressionWorldPosition, -900, 0)
    log("  节点: WorldPosition")

    # Constant3Vector: 平铺尺寸 (256cm → 纹理每 2.56m 重复一次)
    c3v = editing.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -900, 250)
    lc = unreal.LinearColor()
    lc.r = TILE_SIZE_CM
    lc.g = TILE_SIZE_CM
    lc.b = TILE_SIZE_CM
    lc.a = 1.0
    c3v.set_editor_property('constant', lc)
    log(f"  节点: Constant3Vector (tile={TILE_SIZE_CM}cm)")

    # ComponentMask: 从 Constant3Vector 提取 RG 通道 → float2(256, 256)
    mask = editing.create_material_expression(material, unreal.MaterialExpressionComponentMask, -550, 250)
    mask.set_editor_property('r', True)
    mask.set_editor_property('g', True)
    mask.set_editor_property('b', False)
    mask.set_editor_property('a', False)
    log("  节点: ComponentMask (RG only)")

    # Divide: WorldPosition.XY ÷ tile_size → 世界坐标 UV
    divide = editing.create_material_expression(material, unreal.MaterialExpressionDivide, -200, 100)
    log("  节点: Divide")

    # 连接 UV 链 (引脚名由 probe_results.json 确认):
    #   WorldPosition 输出 "XY" → Divide 输入 "A"
    #   Constant3Vector 输出 "" → ComponentMask 输入 "None" (无名引脚)
    #   ComponentMask 输出 "" → Divide 输入 "B"
    try_connect(editing, wp, "XY", divide, "A", "WorldPosition(XY)->Divide.A")
    try_connect(editing, c3v, "", mask, "None", "Constant3Vector->ComponentMask")
    try_connect(editing, mask, "", divide, "B", "ComponentMask->Divide.B")

    # ---- 3 个纹理采样节点 (扇出: Divide 输出连 3 个 UVs) ----
    # 引脚: 输入 "UVs", 输出 "RGB"/"R"/"G"/"B"
    # 属性: parameter_name (需传字符串, Python 自动转 Name), texture (可写, probe 确认)
    tex_nodes = {}
    x_pos = 200
    for suffix, tex in textures.items():
        ts = editing.create_material_expression(
            material, unreal.MaterialExpressionTextureSampleParameter2D, x_pos, 0
        )
        ts.set_editor_property('parameter_name', "Dirt_" + suffix)
        ts.set_editor_property('texture', tex)
        tex_nodes[suffix] = ts
        log(f"  节点: TexSample_{suffix} (param=Dirt_{suffix}, tex={tex.get_name()})")
        x_pos += 300
        # Divide → TexSample.UVs (扇出: 一个输出连多个输入, UE 允许)
        try_connect(editing, divide, "", ts, "UVs", f"Divide->TexSample_{suffix}.UVs")

    # ---- 连接材质属性 ----
    # ALB.RGB → BaseColor (反照率)
    try_connect_prop(editing, tex_nodes["ALB"], "RGB", unreal.MaterialProperty.MP_BASE_COLOR, "ALB.RGB->BaseColor")
    # NRM.RGB → Normal (法线, DirectX 格式)
    try_connect_prop(editing, tex_nodes["NRM"], "RGB", unreal.MaterialProperty.MP_NORMAL, "NRM.RGB->Normal")
    # RMA.R → Roughness (粗糙度, R 通道)
    try_connect_prop(editing, tex_nodes["RMA"], "R", unreal.MaterialProperty.MP_ROUGHNESS, "RMA.R->Roughness")
    # RMA.G → Metallic (金属度, G 通道, 泥土=0)
    try_connect_prop(editing, tex_nodes["RMA"], "G", unreal.MaterialProperty.MP_METALLIC, "RMA.G->Metallic")
    # RMA.B → AmbientOcclusion (环境光遮蔽, B 通道, 来自真实 AO)
    try_connect_prop(editing, tex_nodes["RMA"], "B", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION, "RMA.B->AO")

    # ---- 编译并保存 ----
    editing.recompile_material(material)
    log("  材质已编译")
    eal.save_loaded_asset(material)
    log("  材质已保存")

    return material


# ==================== 主流程 ====================
try:
    textures = step1_import_textures()
    if textures:
        material = step2_create_material(textures)
        if material:
            log("=== 乡间土路材质创建完成 ===")
            log(f"材质路径: {MAT_PACKAGE}/{MAT_NAME}")
        else:
            log("材质创建失败!")
    else:
        log("贴图导入失败, 无法继续!")
except Exception as e:
    log("FATAL: " + str(e))
    log(traceback.format_exc())

log("SETUP_ROAD_TEXTURE_DONE")
_f.flush()
_f.close()
