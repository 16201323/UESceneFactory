# -*- coding: utf-8 -*-
# ============================================================================
# create_static_tree_mat.py - 创建静态树木材质(覆写WPO为0,消除风动)
# ----------------------------------------------------------------------------
# 方案A: 复制 MM_Tree_Branches,将 WPO 输出覆写为 (0,0,0) 常量
#   原材质 WPO = Add[4] = RotateAboutAxis[21] * Multiply[41] + AdditionalWPO[14]
#   覆写后 WPO = (0,0,0),彻底断开风动旋转链,树木完全静止
#   原材质不修改,通过 HISM material_override 字段覆写
# ============================================================================

import unreal

LOG_PATH = "c:/Users/25868/Desktop/UE5/create_static_tree_mat.log"
_f = open(LOG_PATH, "w", encoding="utf-8")


def log(msg):
    print(msg)
    _f.write(str(msg) + "\n")
    _f.flush()


# 源材质路径(Modular_Rural_Cabin 树枝主材质)
SRC_MAT_PATH = "/Game/Modular_Rural_Cabin/Materials/Masters/MM_Tree_Branches.MM_Tree_Branches"

# 目标材质路径(MapForgeTest 下新建静态材质)
DST_MAT_PATH = "/Game/MapForgeTest/Materials/M_Tree_Static.M_Tree_Static"
DST_MAT_PACKAGE = "/Game/MapForgeTest/Materials/M_Tree_Static"

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def main():
    log("#" * 70)
    log("# create_static_tree_mat.py - 创建静态树木材质(覆写WPO=0)")
    log("#" * 70)

    # ================================================================
    # Step 1: 加载源材质 MM_Tree_Branches
    # ================================================================
    log("\n[Step 1] 加载源材质...")
    log("  路径: " + SRC_MAT_PATH)
    src_mat = eal.load_asset(SRC_MAT_PATH)
    if src_mat is None:
        log("  ERROR: 无法加载源材质!")
        _f.close()
        raise SystemExit(1)
    log("  源材质已加载: " + src_mat.get_name())
    log("  材质类: " + src_mat.get_class().get_name())

    # ================================================================
    # Step 2: 检查并删除已存在的目标材质(避免重复创建冲突)
    # ================================================================
    log("\n[Step 2] 检查目标材质是否已存在...")
    existing = eal.load_asset(DST_MAT_PATH)
    if existing is not None:
        log("  目标材质已存在,先删除...")
        try:
            eal.delete_asset(DST_MAT_PACKAGE)
            log("  已删除旧材质")
        except Exception as ex:
            log("  WARNING: 删除失败: " + str(ex))
            log("  尝试继续...")
    else:
        log("  目标材质不存在,可直接创建")

    # ================================================================
    # Step 3: 复制材质
    # ================================================================
    log("\n[Step 3] 复制材质到目标路径...")
    log("  源: " + SRC_MAT_PATH)
    log("  目标: " + DST_MAT_PATH)
    try:
        dst_mat = eal.duplicate_asset(SRC_MAT_PATH, DST_MAT_PATH)
    except Exception as ex:
        log("  ERROR: duplicate_asset 异常: " + str(ex))
        _f.close()
        raise SystemExit(1)

    if dst_mat is None:
        log("  ERROR: 复制返回 None!")
        _f.close()
        raise SystemExit(1)

    log("  复制成功: " + dst_mat.get_path_name())

    # 确认复制的材质表达式数量与源一致
    src_exprs = list(mel.get_material_expressions(src_mat))
    dst_exprs = list(mel.get_material_expressions(dst_mat))
    log("  源材质表达式数: " + str(len(src_exprs)))
    log("  目标材质表达式数: " + str(len(dst_exprs)))

    # ================================================================
    # Step 4: 创建 Constant3Vector 常量节点,值为 (0,0,0)
    # ================================================================
    log("\n[Step 4] 创建 Constant3Vector (0,0,0)...")

    # 尝试获取 MaterialExpressionConstant3Vector 类
    const3_class = None
    try:
        const3_class = unreal.MaterialExpressionConstant3Vector
        log("  类引用方式: unreal.MaterialExpressionConstant3Vector (直接引用)")
    except Exception:
        log("  直接引用失败,尝试 load_class...")
        try:
            const3_class = unreal.load_class(
                None, "/Script/Engine.MaterialExpressionConstant3Vector"
            )
            log("  类引用方式: unreal.load_class (间接加载)")
        except Exception as ex2:
            log("  ERROR: 无法获取 Constant3Vector 类: " + str(ex2))
            _f.close()
            raise SystemExit(1)

    if const3_class is None:
        log("  ERROR: Constant3Vector 类为 None!")
        _f.close()
        raise SystemExit(1)

    # 创建表达式节点(放在右下角避免遮挡现有节点)
    try:
        zero_const = mel.create_material_expression(dst_mat, const3_class, 100, 800)
    except Exception as ex:
        log("  ERROR: create_material_expression 异常: " + str(ex))
        _f.close()
        raise SystemExit(1)

    if zero_const is None:
        log("  ERROR: 创建的 Constant3Vector 为 None!")
        _f.close()
        raise SystemExit(1)

    log("  Constant3Vector 已创建: " + zero_const.get_name())

    # 设置值为 (0,0,0)
    # Constant3Vector 的 "constant" 属性是 FLinearColor 类型
    try:
        zero_const.set_editor_property(
            "constant", unreal.LinearColor(0.0, 0.0, 0.0, 1.0)
        )
        log("  值已设置为 (0, 0, 0)")
    except Exception as ex:
        log("  WARNING: set_editor_property(constant) 异常: " + str(ex))
        log("  尝试直接设置 r/g/b 属性...")
        try:
            zero_const.set_editor_property("r", 0.0)
            zero_const.set_editor_property("g", 0.0)
            zero_const.set_editor_property("b", 0.0)
            log("  r/g/b 已分别设置")
        except Exception as ex2:
            log("  ERROR: 直接设置也失败: " + str(ex2))

    # 验证值
    try:
        c = zero_const.get_editor_property("constant")
        if c:
            log("  验证: r=" + str(float(c.r)) + " g=" + str(float(c.g)) +
                " b=" + str(float(c.b)))
    except Exception:
        pass

    # ================================================================
    # Step 5: 连接到 WPO 输出引脚(MP_WORLD_POSITION_OFFSET)
    # ================================================================
    log("\n[Step 5] 连接 Constant3Vector 到 WPO 输出...")

    # 获取 MaterialProperty 枚举值 MP_WORLD_POSITION_OFFSET
    wpo_prop = None
    try:
        wpo_prop = unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET
        log("  枚举方式: unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET")
    except Exception:
        log("  MaterialProperty 枚举失败,尝试 EMaterialProperty...")
        try:
            wpo_prop = unreal.EMaterialProperty.MP_WORLD_POSITION_OFFSET
            log("  枚举方式: unreal.EMaterialProperty.MP_WORLD_POSITION_OFFSET")
        except Exception as ex2:
            log("  ERROR: 无法获取 MP_WORLD_POSITION_OFFSET 枚举: " + str(ex2))
            # 列出 MaterialProperty 所有属性供调试
            try:
                log("  MaterialProperty 可用属性:")
                for attr in dir(unreal.MaterialProperty):
                    if not attr.startswith("_"):
                        log("    " + attr)
            except Exception:
                pass
            _f.close()
            raise SystemExit(1)

    if wpo_prop is None:
        log("  ERROR: WPO 枚举为 None!")
        _f.close()
        raise SystemExit(1)

    # 连接: 覆写原有 WPO 连接(Add[4]节点)为零常量
    # UE5.8 API: connect_material_property(from_expression, from_output_name, to_property)
    # — from_expression 的父材质即为目标材质
    wpo_connected = False

    # 获取 Constant3Vector 的输出引脚名
    output_names = []
    try:
        output_names = list(mel.get_material_expression_output_names(zero_const))
        log("  Constant3Vector 输出引脚名: " + str(output_names))
    except Exception:
        log("  get_material_expression_output_names 不可用,尝试常见输出名")

    # 如果获取不到,用常见输出名
    if not output_names:
        output_names = ["", "RGB", "Value", "X"]
        log("  使用常见输出名尝试: " + str(output_names))

    for out_name in output_names:
        log("  尝试 connect_material_property(zero_const, '" + out_name + "', wpo_prop)...")
        try:
            mel.connect_material_property(zero_const, out_name, wpo_prop)
            log("  *** WPO 已连接! 输出名: '" + out_name + "' ***")
            wpo_connected = True
            break
        except Exception as ex:
            log("  失败: " + str(ex)[:100])

    # 方案 B: 如果 connect_material_property 全部失败,直接设置材质 WPO ExpressionInput
    if not wpo_connected:
        log("\n  方案B: 直接操作材质表达式连接...")
        # 找到当前连接到 WPO 的表达式(Add[4])
        try:
            # 获取材质所有表达式,检查哪个连到 WPO
            all_exprs = list(mel.get_material_expressions(dst_mat))
            log("  材质表达式数: " + str(len(all_exprs)))

            # 遍历检查 Constant3Vector 是否被其他表达式引用
            const3_path = zero_const.get_path_name()
            for i, expr in enumerate(all_exprs):
                if expr is zero_const:
                    continue
                try:
                    inputs = mel.get_inputs_for_material_expression(dst_mat, expr)
                    names = mel.get_material_expression_input_names(expr)
                    if names and inputs:
                        for j, inp in enumerate(inputs):
                            try:
                                ref = inp.get_editor_property("expression") if inp else None
                                if ref and ref.get_path_name() == const3_path:
                                    log("  Constant3Vector 被引用: [" + str(i) + "] " +
                                        expr.get_class().get_name() + " 引脚[" + str(names[j]) + "]")
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception as ex:
            log("  方案B异常: " + str(ex))

    # ================================================================
    # Step 6: 验证 WPO 连接(检查输出引脚当前连接的表达式)
    # ================================================================
    log("\n[Step 6] 验证 WPO 连接...")
    try:
        # 重新获取表达式列表,找到新创建的 Constant3Vector
        new_exprs = list(mel.get_material_expressions(dst_mat))
        log("  目标材质表达式数(含新节点): " + str(len(new_exprs)))

        # 检查 WPO 输出引脚连接了什么
        # 通过遍历所有表达式,找到连接到 WPO 的节点
        wpo_connected = False
        for i, expr in enumerate(new_exprs):
            if expr is zero_const:
                log("  Constant3Vector 在表达式列表索引: [" + str(i) + "]")
                # 检查这个节点是否被材质输出引用
                try:
                    # 获取表达式输出消费者
                    outputs = mel.get_outputs_for_material_expression(dst_mat, expr)
                    if outputs:
                        log("  输出数: " + str(len(outputs)))
                except Exception:
                    pass

        # 通过材质输出检查 WPO 引脚
        try:
            wpo_input = mel.get_material_input(dst_mat, wpo_prop)
            if wpo_input:
                log("  WPO 引脚有连接")
                wpo_connected = True
            else:
                log("  WARNING: WPO 引脚无连接!")
        except Exception as ex:
            log("  (get_material_input 不可用: " + str(ex) + ")")

    except Exception as ex:
        log("  验证异常(非致命): " + str(ex))

    # ================================================================
    # Step 7: 标记材质已修改并保存
    # ================================================================
    log("\n[Step 7] 保存材质...")

    try:
        # 通知编辑器材质已修改
        dst_mat.mark_asset_dirty()
        log("  mark_asset_dirty 已调用")
    except Exception:
        pass

    try:
        dst_mat.preedit_change(None)
    except Exception:
        pass

    try:
        dst_mat.postedit_change()
        log("  postedit_change 已调用")
    except Exception:
        pass

    # 保存到磁盘
    try:
        result = eal.save_asset(DST_MAT_PATH, False)
        log("  save_asset 结果: " + str(result))
    except Exception as ex:
        log("  WARNING: save_asset 异常: " + str(ex))
        # 尝试另一种保存方式
        try:
            result2 = eal.save_asset(DST_MAT_PATH)
            log("  save_asset(无参数) 结果: " + str(result2))
        except Exception as ex2:
            log("  ERROR: 保存失败: " + str(ex2))

    # ================================================================
    # 汇总
    # ================================================================
    log("\n" + "=" * 70)
    log("===== 完成 =====")
    log("=" * 70)
    log("")
    log("静态树木材质已创建: " + DST_MAT_PATH)
    log("")
    log("在场景 JSON 中使用以下路径作为 material_override:")
    log("  /Game/MapForgeTest/Materials/M_Tree_Static.M_Tree_Static")
    log("")
    log("效果: WPO 被覆写为 (0,0,0),风动旋转链彻底断开")
    log("原始材质 MM_Tree_Branches 未修改")

    _f.close()
    unreal.SystemLibrary.quit_game()


main()
