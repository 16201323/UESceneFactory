# -*- coding: utf-8 -*-
# wind_default_v9b.py - 检查Wind函数FunctionInput默认值(通过材质间接加载)
import unreal

LOG_PATH = "c:/Users/25868/Desktop/UE5/wind_default_v9b.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()

def expr_type(expr):
    if expr is None:
        return "None"
    cls = expr.__class__.__name__
    if cls.startswith("MaterialExpression"):
        return cls[len("MaterialExpression"):]
    return cls

# v5验证过的方法:先加载材质,从材质内部找到Wind函数调用节点
MAT_PATH = "/Game/Modular_Rural_Cabin/Materials/Masters/MM_Tree_Branches.MM_Tree_Branches"
log("Loading material: " + MAT_PATH)
mat = unreal.EditorAssetLibrary.load_asset(MAT_PATH)
if mat is None:
    log("ERROR: Cannot load material!")
    _f.close()
    raise SystemExit(1)
log("Material loaded: " + mat.get_name())

# 获取材质表达式列表
mel = unreal.MaterialEditingLibrary
expressions = mel.get_material_expressions(mat)
log("Material expression count: " + str(len(expressions)))

# 查找Wind函数调用节点(在材质中索引[24])
wind_fn_asset = None
wind_call_idx = -1
for i, expr in enumerate(expressions):
    cls = expr.__class__.__name__
    if "MaterialFunctionCall" in cls:
        try:
            fn = expr.get_editor_property("material_function")
            if fn and fn.get_name() == "Wind":
                wind_fn_asset = fn
                wind_call_idx = i
                log("Found Wind function call at material expr[" + str(i) + "]")
                break
        except:
            pass

if wind_fn_asset is None:
    log("ERROR: Wind function call not found in material!")
    _f.close()
    raise SystemExit(1)

log("Wind function asset: " + wind_fn_asset.get_name())
log("Wind function path: " + str(wind_fn_asset.get_path_name()))

# 获取Wind函数内部表达式
wind_exprs = list(mel.get_material_function_expressions(wind_fn_asset))
log("Wind function internal expression count: " + str(len(wind_exprs)))
log("")

# 遍历Wind函数内部表达式,重点读取FunctionInput的默认值
for i, expr in enumerate(wind_exprs):
    etype = expr_type(expr)
    info = "[" + str(i) + "] " + etype

    if etype == "FunctionInput":
        # 读取input_name
        try:
            info += " input_name=" + str(expr.input_name)
        except:
            try:
                info += " input_name=" + str(expr.get_editor_property("input_name"))
            except:
                info += " input_name=?"

        # 读取input_type
        try:
            info += " input_type=" + str(expr.input_type)
        except:
            try:
                info += " input_type=" + str(expr.get_editor_property("input_type"))
            except:
                info += " input_type=?"

        # 直接读取已知的FunctionInput属性名(UE5 C++属性)
        info += " | KNOWN_PROPS:"
        for pn in [
            "preview_value", "function_input_default", "default_value",
            "bUsePreviewValueAsDefault", "Description", "SortOrder",
            "bCollapsed", "bShowOutputNameOnPin", "bIs3D"
        ]:
            try:
                val = expr.get_editor_property(pn)
                if val is not None:
                    sval = str(val)
                    if len(sval) > 200:
                        sval = sval[:200] + "..."
                    info += " " + str(pn) + "=" + sval + ";"
                    # 尝试读取Vector4f的分量(x,y,z,w 或 r,g,b,a)
                    if pn == "preview_value":
                        for comp in ["x","y","z","w","r","g","b","a","R","G","B","A"]:
                            try:
                                cv = getattr(val, comp, None)
                                if cv is None:
                                    cv = val.get_editor_property(comp)
                                if cv is not None:
                                    info += f" pv.{comp}={cv};"
                            except:
                                pass
                        # 尝试索引访问
                        try:
                            info += f" pv_list=[{val[0]},{val[1]},{val[2]},{val[3]}];"
                        except:
                            pass
            except:
                pass
        # 备选:用Python dir()枚举,过滤可能的默认值属性
        try:
            all_attrs = [a for a in dir(expr) if not a.startswith("_") and ("value" in a.lower() or "default" in a.lower() or "preview" in a.lower())]
            if all_attrs:
                info += " | DIR_FILTERED:" + ",".join(all_attrs)
        except:
            pass

    elif etype == "FunctionOutput":
        try:
            info += " output_name=" + str(expr.output_name)
        except:
            try:
                info += " output_name=" + str(expr.get_editor_property("output_name"))
            except:
                pass
    elif etype == "Constant":
        try:
            info += " value=" + str(expr.constant)
        except:
            try:
                info += " value=" + str(expr.get_editor_property("constant"))
            except:
                pass
    elif etype in ("Constant2Vector", "Constant3Vector", "Constant4Vector"):
        try:
            v = expr.constant
            info += " value=(" + str(v.x) + "," + str(v.y) + "," + str(v.z)
            if hasattr(v, 'w'):
                info += "," + str(v.w)
            info += ")"
        except:
            try:
                v = expr.get_editor_property("constant")
                info += " value=(" + str(v.x) + "," + str(v.y) + "," + str(v.z) + ")"
            except:
                pass
    elif etype == "Time":
        try:
            info += " period=" + str(expr.get_editor_property("period"))
        except:
            pass

    log(info)

log("")
log("=" * 60)
log("ANALYSIS:")
log("  FunctionInput[11] = WindActor input")
log("  If default = (0,0,0,0): Wind outputs zero -> no wind")
log("  If default != (0,0,0,0): constant wind -> dot(pos,wind) varies")
log("")
log("Done. Log: " + LOG_PATH)

# 显式退出
unreal.SystemLibrary.quit_game()
_f.close()
