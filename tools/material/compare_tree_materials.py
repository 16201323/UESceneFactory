# -*- coding: utf-8 -*-
# compare_tree_materials.py - 对比松树 vs 杉树材质的 WPO 风动链
# 目的: 搞清为什么杉树在HISM(植被模式)下风动正常, 松树却连根晃动
#
# 运行方式: 在 UE5 编辑器 Python 控制台执行
#   py "c:/Users/25868/Desktop/UE5/UESceneFactory/tools/material/compare_tree_materials.py"
#
# 输出: 日志写入 c:/Users/25868/Desktop/UE5/compare_tree_materials.log
import unreal

LOG_PATH = "c:/Users/25868/Desktop/UE5/compare_tree_materials.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

def expr_type(expr):
    """提取表达式类型简称(去掉 MaterialExpression 前缀)"""
    if expr is None:
        return "None"
    cls = expr.__class__.__name__
    if cls.startswith("MaterialExpression"):
        return cls[len("MaterialExpression"):]
    return cls

def dump_expressions(mat, label):
    """打印材质的所有表达式节点, 重点标注 WPO 风动相关节点"""
    log("")
    log("=" * 70)
    log("MATERIAL: " + label)
    log("  path: " + mat.get_path_name())
    log("  class: " + mat.__class__.__name__)
    log("=" * 70)

    mel = unreal.MaterialEditingLibrary

    # 如果是材质实例(MaterialInstanceConstant), 先获取父材质
    parent = None
    if mat.__class__.__name__ == "MaterialInstanceConstant":
        try:
            parent = mat.get_editor_property("parent")
            if parent:
                log("  [MaterialInstance] parent = " + parent.get_path_name())
        except:
            log("  [MaterialInstance] WARN: 无法获取 parent")
    elif mat.__class__.__name__ == "Material":
        log("  [Material] (主材质, 直接检查表达式)")

    # 收集材质实例的标量参数覆写(关键: 风动强度/权重等参数)
    if mat.__class__.__name__ == "MaterialInstanceConstant":
        try:
            scalar_params = mat.get_editor_property("scalar_parameter_values")
            if scalar_params:
                log("")
                log("  --- 标量参数覆写 (Scalar Parameter Overrides) ---")
                for sp in scalar_params:
                    try:
                        pinfo = sp.get_editor_property("parameter_info")
                        pname = pinfo.get_editor_property("name") if pinfo else "?"
                    except:
                        pname = "?"
                    try:
                        pval = sp.get_editor_property("parameter_value")
                    except:
                        pval = "?"
                    log("    " + str(pname) + " = " + str(pval))
        except:
            log("  WARN: 无法读取 scalar_parameter_values")

    # 如果是材质实例, 切换到父材质检查表达式
    target_mat = parent if parent else mat
    if parent:
        log("")
        log("  >> 切换到父材质检查表达式: " + target_mat.get_path_name())

    expressions = mel.get_material_expressions(target_mat)
    log("")
    log("  表达式总数: " + str(len(expressions)))
    log("")

    # 分类统计
    wind_keywords = [
        "Wind", "RotateAboutAxis", "WorldPosition", "AdditionalWPO",
        "WPO", "SimpleGrassWind", "Time", "Sine", "DotProduct",
        "VertexColor", "ObjectPosition", "ObjectRadius"
    ]

    wind_nodes = []
    all_nodes = []

    for i, expr in enumerate(expressions):
        etype = expr_type(expr)
        info = "  [" + str(i) + "] " + etype
        detail = ""

        # 尝试获取节点的描述/名称
        try:
            desc = expr.get_editor_property("desc")
            if desc:
                detail += " desc='" + str(desc) + "'"
        except:
            pass

        # 尝试获取节点变量名(参数名)
        try:
            vname = expr.get_editor_property("parameter_name")
            if vname:
                detail += " param='" + str(vname) + "'"
        except:
            pass

        # 常量值
        if etype == "Constant":
            try:
                detail += " value=" + str(expr.constant)
            except:
                pass
        elif etype in ("Constant2Vector", "Constant3Vector", "Constant4Vector"):
            try:
                v = expr.constant
                detail += " value=(" + str(v.x) + "," + str(v.y) + "," + str(v.z) + ")"
            except:
                pass
        elif etype == "Time":
            try:
                detail += " period=" + str(expr.get_editor_property("period"))
            except:
                pass

        # 材质函数调用: 打印函数名
        if "FunctionCall" in etype:
            try:
                fn = expr.get_editor_property("material_function")
                if fn:
                    detail += " function=" + fn.get_name() + " path=" + fn.get_path_name()
            except:
                pass

        # 检查是否是风动相关节点
        etype_lower = etype.lower()
        detail_lower = detail.lower()
        is_wind = any(kw.lower() in etype_lower or kw.lower() in detail_lower for kw in wind_keywords)

        if is_wind:
            info = "  >>> [WIND] " + info + detail
            wind_nodes.append(info)
        else:
            info = info + detail

        all_nodes.append(info)

    # 打印风动相关节点(高亮)
    log("  --- 风动相关节点 (WPO/Wind/WorldPosition/RotateAboutAxis/...) ---")
    if wind_nodes:
        for wn in wind_nodes:
            log(wn)
    else:
        log("  (未发现风动相关节点)")

    # 打印所有节点(供完整分析)
    log("")
    log("  --- 全部表达式节点 ---")
    for an in all_nodes:
        log(an)

    return wind_nodes

# ===========================================================================
# 主流程: 对比松树和杉树的材质
# ===========================================================================

log("#" * 70)
log("# 松树 vs 杉树 材质 WPO 风动链对比诊断")
log("# 目的: 找出为什么杉树在HISM下风动正常, 松树却连根晃动")
log("#" * 70)

# --- 松树材质 ---
PINE_BRANCHES_MI = "/Game/Modular_Rural_Cabin/Materials/Instances/MI_Pine_Tree_Branches.MI_Pine_Tree_Branches"
PINE_BARK_MI = "/Game/Modular_Rural_Cabin/Materials/Instances/MI_Pine_Tree_Bark.MI_Pine_Tree_Bark"

log("")
log(">>> 加载松树树枝材质实例: " + PINE_BRANCHES_MI)
pine_branches = unreal.EditorAssetLibrary.load_asset(PINE_BRANCHES_MI)
if pine_branches:
    pine_wind = dump_expressions(pine_branches, "松树-树枝 (MI_Pine_Tree_Branches)")
else:
    log("ERROR: 无法加载松树树枝材质!")
    pine_wind = []

log("")
log(">>> 加载松树树皮材质实例: " + PINE_BARK_MI)
pine_bark = unreal.EditorAssetLibrary.load_asset(PINE_BARK_MI)
if pine_bark:
    dump_expressions(pine_bark, "松树-树皮 (MI_Pine_Tree_Bark)")
else:
    log("WARN: 无法加载松树树皮材质(可能无WPO, 跳过)")

# --- 杉树材质 ---
FIR_NEEDLES_MI = "/Game/RuralHouse/Environment/Trees/Materials/MI_FirNeedles.MI_FirNeedles"
FIR_BARK_MI = "/Game/RuralHouse/Environment/Trees/Materials/MI_Bark.MI_Bark"

log("")
log(">>> 加载杉树针叶材质实例: " + FIR_NEEDLES_MI)
fir_needles = unreal.EditorAssetLibrary.load_asset(FIR_NEEDLES_MI)
if fir_needles:
    fir_wind = dump_expressions(fir_needles, "杉树-针叶 (MI_FirNeedles)")
else:
    log("ERROR: 无法加载杉树针叶材质!")
    fir_wind = []

log("")
log(">>> 加载杉树树皮材质实例: " + FIR_BARK_MI)
fir_bark = unreal.EditorAssetLibrary.load_asset(FIR_BARK_MI)
if fir_bark:
    dump_expressions(fir_bark, "杉树-树皮 (MI_Bark)")
else:
    log("WARN: 无法加载杉树树皮材质(可能无WPO, 跳过)")

# --- 对比总结 ---
log("")
log("#" * 70)
log("# 对比总结")
log("#" * 70)
log("")
log("松树树枝风动节点数: " + str(len(pine_wind)))
for wn in pine_wind:
    log("  " + wn)
log("")
log("杉树针叶风动节点数: " + str(len(fir_wind)))
for wn in fir_wind:
    log("  " + wn)
log("")
log("关键差异分析:")
log("  松树: 如果含 RotateAboutAxis + WorldPosition → HISM下WorldPosition=组件原点 → 支点错误 → 整树旋转")
log("  杉树: 如果用 AdditionalWPO / SimpleGrassWind → 顶点级偏移 → HISM下也正常")
log("")
log("Done. 日志: " + LOG_PATH)

unreal.SystemLibrary.quit_game()
_f.close()
