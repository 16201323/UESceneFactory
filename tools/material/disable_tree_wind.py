# -*- coding: utf-8 -*-
# disable_tree_wind.py - 禁用松树枝干风动
# 方案: 修改MI_Pine_Tree_Branches材质实例, 覆写Wind相关标量参数为0
#
# 原理:
#   父材质MM_Tree_Branches的WPO链:
#   WindActor函数(无连接, 返回默认值(0,1,0,1))
#   -> WorldPosition
#   -> DotProduct(=顶点Y坐标)
#   -> Sine(时间振荡)
#   -> Multiply x WindIntensity(标量参数)
#   -> Wind函数
#   -> RotateAboutAxis(整树旋转)
#
#   将WindIntensity和WindWeight覆写为0, 使WPO=0, 消除风动
#   此修改影响所有引用MI_Pine_Tree_Branches的场景, 一次修改永久生效
#   不修改任何umap文件, 以前的关卡加载时自动应用新参数
#
# 属性访问(经diag_struct_props.py诊断确认):
#   ScalarParameterValue.parameter_info  -> MaterialParameterInfo子结构体
#   MaterialParameterInfo.name           -> 参数名(字符串)
#   ScalarParameterValue.parameter_value -> 参数值(浮点)
#   注意: 不存在parameter_name属性, 参数名嵌套在parameter_info中

import unreal
import sys

LOG_PATH = "c:/Users/25868/Desktop/UE5/disable_tree_wind.log"
_f = open(LOG_PATH, "w", encoding="utf-8")

def log(msg):
    print(msg)
    sys.stdout.flush()
    _f.write(str(msg) + "\n")
    _f.flush()

eal = unreal.EditorAssetLibrary

PARENT_PATH = "/Game/Modular_Rural_Cabin/Materials/Masters/MM_Tree_Branches"
MIC_PATH = "/Game/Modular_Rural_Cabin/Materials/Instances/MI_Pine_Tree_Branches"

# 风相关参数名(经诊断确认, "Wind Intesity"是材质中的实际拼写, 缺少字母n)
WIND_PARAMS = ["Wind Intesity", "Wind Weight"]

# ============================================================
# 辅助函数: 从ScalarParameterValue读取参数名
# ============================================================
def get_param_name(sv):
    """从ScalarParameterValue读取参数名, 通过parameter_info.name"""
    try:
        pi = sv.parameter_info
        return str(pi.get_editor_property("name"))
    except Exception:
        return None

def get_param_value(sv):
    """读取参数值"""
    try:
        return float(sv.parameter_value)
    except Exception:
        return None

# ============================================================
# 第1步: 加载MIC, 读取当前覆写
# ============================================================
log("=== 禁用树木风动: 覆写Wind参数为0 ===")
log("MIC: " + MIC_PATH)

mic = eal.load_asset(MIC_PATH)
if not mic:
    log("FATAL: 无法加载MIC")
    _f.close()
    raise RuntimeError("MIC not found")

log("已加载MIC: " + mic.get_path_name())
log("类型: " + mic.__class__.__name__)

try:
    mic_parent = mic.get_editor_property("parent")
    if mic_parent:
        log("MIC父材质: " + mic_parent.get_path_name())
except Exception as e:
    log("获取父材质失败: " + str(e))

current_values = mic.get_editor_property("scalar_parameter_values")
log("\n--- 当前MIC标量参数覆写 ---")
log("覆写数量: " + str(len(current_values)))

# 读取所有当前覆写, 构建名称->索引映射
param_map = {}  # name -> index
for i in range(len(current_values)):
    sv = current_values[i]
    pname = get_param_name(sv)
    pval = get_param_value(sv)
    if pname is not None:
        param_map[pname] = i
        log("  [%d] '%s' = %s" % (i, pname, str(pval)))
    else:
        log("  [%d] (读取失败)" % i)

# ============================================================
# 第2步: 构建新覆写数组
# ============================================================
log("\n--- 构建新覆写数组 ---")

new_values = []
overridden = set()

# 处理现有覆写: 保留非风参数, 风参数改为0.0
for i in range(len(current_values)):
    sv_old = current_values[i]
    pname = get_param_name(sv_old)
    pval = get_param_value(sv_old)

    if pname is None:
        log("  [%d] 跳过(无法读取名称)" % i)
        continue

    # 创建新结构体
    new_sv = unreal.ScalarParameterValue()

    # 复制parameter_info(子结构体)
    try:
        pi_old = sv_old.parameter_info
        new_pi = unreal.MaterialParameterInfo()
        new_pi.set_editor_property("name", pi_old.get_editor_property("name"))
        new_pi.set_editor_property("association", pi_old.get_editor_property("association"))
        new_pi.set_editor_property("index", pi_old.get_editor_property("index"))
        new_sv.set_editor_property("parameter_info", new_pi)
    except Exception as e:
        log("  [%d] 复制parameter_info失败: %s" % (i, str(e)[:80]))

    # 设置值
    if pname in WIND_PARAMS:
        # 风参数: 覆写为0.0
        new_sv.set_editor_property("parameter_value", 0.0)
        overridden.add(pname)
        log("  修改: '%s' %s -> 0.0" % (pname, str(pval)))
    else:
        # 非风参数: 保留原值
        new_sv.set_editor_property("parameter_value", pval if pval is not None else 0.0)

    new_values.append(new_sv)

# 添加不存在的风参数覆写
for wp in WIND_PARAMS:
    if wp not in overridden:
        log("  新增: '%s' = 0.0" % wp)
        new_sv = unreal.ScalarParameterValue()
        new_pi = unreal.MaterialParameterInfo()
        new_pi.set_editor_property("name", wp)
        try:
            new_pi.set_editor_property("association", unreal.MaterialParameterAssociation.GLOBAL_PARAMETER)
        except Exception:
            pass  # 枚举可能不存在, 跳过
        new_pi.set_editor_property("index", -1)
        new_sv.set_editor_property("parameter_info", new_pi)
        new_sv.set_editor_property("parameter_value", 0.0)
        new_values.append(new_sv)

log("新数组大小: " + str(len(new_values)))

# ============================================================
# 第3步: 写回并保存
# ============================================================
log("\n--- 写回并保存 ---")

try:
    mic.set_editor_property("scalar_parameter_values", new_values)
    log("set_editor_property 成功")
except Exception as e:
    log("set_editor_property 失败: " + str(e))

try:
    mic.mark_package_dirty()
    log("mark_package_dirty 成功")
except Exception as e:
    log("mark_package_dirty 失败: " + str(e))

try:
    eal.save_asset(MIC_PATH)
    log("save_asset 成功")
except Exception as e:
    log("save_asset 失败: " + str(e))

# ============================================================
# 第4步: 验证
# ============================================================
log("\n--- 验证: 读取保存后覆写 ---")

# 重新加载确保读取磁盘上的最新状态
mic2 = eal.load_asset(MIC_PATH)
verify_values = mic2.get_editor_property("scalar_parameter_values")
log("保存后覆写数量: " + str(len(verify_values)))

all_ok = True
for i in range(len(verify_values)):
    sv = verify_values[i]
    pname = get_param_name(sv)
    pval = get_param_value(sv)
    if pname is not None:
        marker = " <== WIND" if pname in WIND_PARAMS else ""
        log("  [%d] '%s' = %s%s" % (i, pname, str(pval), marker))
        if pname in WIND_PARAMS and pval != 0.0:
            all_ok = False
            log("  !! 验证失败: '%s' = %s (期望0.0)" % (pname, str(pval)))
    else:
        log("  [%d] (读取失败)" % i)

# 检查所有风参数都有覆写
for wp in WIND_PARAMS:
    found = False
    for i in range(len(verify_values)):
        sv = verify_values[i]
        pname = get_param_name(sv)
        if pname == wp:
            found = True
            break
    if not found:
        all_ok = False
        log("  !! 验证失败: '%s' 未找到覆写" % wp)

if all_ok:
    log("\n=== 验证通过: 所有风参数已设为0.0 ===")
else:
    log("\n=== 验证失败: 部分参数未正确设置 ===")

log("\nDISABLE_WIND_DONE")
_f.close()
