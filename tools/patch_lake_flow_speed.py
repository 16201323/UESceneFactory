"""补丁脚本: 为真实C++源码(LandscapeHelper.cpp)添加湖面flow_speed支持

修改三处:
1. 添加 WaterFlowSpeed 成员变量(默认0.3=缓流)
2. 添加 flow_speed JSON解析(water对象)
3. 湖面材质从SetMaterial改为CreateDynamicMaterialInstance+SetScalarParameterValue
"""
import os
import sys

CPP_PATH = r"D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Plugins\LandscapeHelper\Source\LandscapeHelperEditor\Private\LandscapeHelper.cpp"


def apply_patch(content):
    """对源码内容应用三处补丁, 返回修补后的内容和是否修改"""
    modified = False

    # === 补丁1: 添加 WaterFlowSpeed 成员变量 ===
    old1 = (
        '    // 水面配置: 湖泊水位+材质(可选)\n'
        '    float WaterLevelM = 0.0f;           // 湖泊水位高度(米, 相对于0海拔基准)\n'
        '    FString WaterMaterialPath = TEXT(""); // 湖面材质路径(空=使用引擎默认材质)\n'
        '    bool bHasWater = false;             // 是否创建湖面(level_m>0时为true)\n'
    )
    new1 = old1 + (
        '    // === 模块5新增: 湖面流速倍率(JSON可配置) ===\n'
        '    float WaterFlowSpeed = 0.3f;       // 湖面流速倍率(0.3=缓流, 传入材质FlowSpeed参数控制Panner动画速度)\n'
    )
    if old1 in content:
        content = content.replace(old1, new1, 1)
        modified = True
        print("[OK] 补丁1: WaterFlowSpeed 成员变量已添加")
    else:
        # 检查是否已经修补过
        if "WaterFlowSpeed" in content:
            print("[SKIP] 补丁1: WaterFlowSpeed 已存在, 跳过")
        else:
            print("[FAIL] 补丁1: 未找到目标代码段")
            return None, False

    # === 补丁2: 添加 flow_speed JSON解析 ===
    old2 = (
        '                    const TSharedPtr<FJsonValue>* WMV = WaterObj->Values.Find(TEXT("material_path"));\n'
        '                    if (WMV && WMV->IsValid()) WaterMaterialPath = (*WMV)->AsString();\n'
        '                    if (WaterLevelM > 0.0f)\n'
    )
    new2 = (
        '                    const TSharedPtr<FJsonValue>* WMV = WaterObj->Values.Find(TEXT("material_path"));\n'
        '                    if (WMV && WMV->IsValid()) WaterMaterialPath = (*WMV)->AsString();\n'
        '                    // 湖面流速倍率(可选, 默认0.3=缓流)\n'
        '                    const TSharedPtr<FJsonValue>* WFS = WaterObj->Values.Find(TEXT("flow_speed"));\n'
        '                    if (WFS && WFS->IsValid()) WaterFlowSpeed = (float)(*WFS)->AsNumber();\n'
        '                    if (WaterLevelM > 0.0f)\n'
    )
    if old2 in content:
        content = content.replace(old2, new2, 1)
        modified = True
        print("[OK] 补丁2: flow_speed JSON解析已添加")
    else:
        if 'WaterObj->Values.Find(TEXT("flow_speed"))' in content:
            print("[SKIP] 补丁2: flow_speed 解析已存在, 跳过")
        else:
            print("[FAIL] 补丁2: 未找到目标代码段")
            return None, False

    # === 补丁3: 湖面材质从SetMaterial改为CreateDynamicMaterialInstance ===
    old3 = (
        '                        if (WaterMaterial) LakeMeshComp->SetMaterial(0, WaterMaterial);\n'
        '                        LakeMeshComp->SetRelativeScale3D(WaterScale);\n'
    )
    new3 = (
        '                        // 湖面使用动态材质实例: 传入FlowSpeed参数控制Panner动画速度(缓流)\n'
        '                        if (WaterMaterial)\n'
        '                        {\n'
        '                            UMaterialInstanceDynamic* DynLakeMat = LakeMeshComp->CreateDynamicMaterialInstance(0, WaterMaterial);\n'
        '                            if (DynLakeMat)\n'
        '                            {\n'
        '                                DynLakeMat->SetScalarParameterValue(FName(TEXT("FlowSpeed")), WaterFlowSpeed);\n'
        '                            }\n'
        '                            else\n'
        '                            {\n'
        '                                LakeMeshComp->SetMaterial(0, WaterMaterial); // 回退: 动态创建失败时用静态材质\n'
        '                            }\n'
        '                        }\n'
        '                        LakeMeshComp->SetRelativeScale3D(WaterScale);\n'
    )
    if old3 in content:
        content = content.replace(old3, new3, 1)
        modified = True
        print("[OK] 补丁3: 湖面动态材质已替换")
    else:
        if 'DynLakeMat' in content:
            print("[SKIP] 补丁3: 湖面动态材质已存在, 跳过")
        else:
            print("[FAIL] 补丁3: 未找到目标代码段")
            return None, False

    return content, modified


def main():
    if not os.path.exists(CPP_PATH):
        print(f"[ERROR] 源码文件不存在: {CPP_PATH}")
        sys.exit(1)

    with open(CPP_PATH, "r", encoding="utf-8") as f:
        original = f.read()

    patched, modified = apply_patch(original)
    if patched is None:
        print("[ABORT] 补丁失败, 未修改文件")
        sys.exit(1)

    if not modified:
        print("[DONE] 所有补丁均已存在, 无需修改")
        sys.exit(0)

    # 写回文件
    with open(CPP_PATH, "w", encoding="utf-8") as f:
        f.write(patched)
    print("[DONE] 补丁已成功应用到真实源码")
    print(f"  文件: {CPP_PATH}")


if __name__ == "__main__":
    main()
