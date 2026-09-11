# -*- coding: utf-8 -*-
"""
合并修改LandscapeHelper.cpp:
1. 添加 MaterialInstanceDynamic.h 头文件
2. 河流SMC分段加Pitch俯仰角(修复水面断层/泥土条)
3. 用CreateDynamicMaterialInstance替代SetMaterial, 设置FlowSpeed=1.0
"""
import sys

CPP_PATH = r"D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Plugins\LandscapeHelper\Source\LandscapeHelperEditor\Private\LandscapeHelper.cpp"

with open(CPP_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

errors = []

# === 修改1: 添加 MaterialInstanceDynamic.h 头文件 ===
INCLUDE_OLD = '#include "Materials/MaterialInstance.h"'
INCLUDE_NEW = '#include "Materials/MaterialInstance.h"\n#include "Materials/MaterialInstanceDynamic.h"'

if INCLUDE_OLD in content and INCLUDE_NEW not in content:
    content = content.replace(INCLUDE_OLD, INCLUDE_NEW, 1)
    print("OK: 已添加 #include Materials/MaterialInstanceDynamic.h")
elif INCLUDE_NEW in content:
    print("SKIP: MaterialInstanceDynamic.h 已存在")
else:
    errors.append("ERROR: 找不到 #include Materials/MaterialInstance.h")
    print("ERROR: 找不到 #include Materials/MaterialInstance.h")

# === 修改2: 河流SMC分段加Pitch俯仰角 ===
PITCH_OLD = '''                        float CenterZ = (CenterPts[i].Z + CenterPts[i + 1].Z) * 0.5f;
                        float AvgWidth = (WidthsM[i] + WidthsM[i + 1]) * 0.5f;
                        float AngleDeg = FMath::RadiansToDegrees(FMath::Atan2(P2.Y - P1.Y, P2.X - P1.X));
                        // 平面缩放: X=(段长+重叠)/100, Y=宽度(引擎平面基础=1米)
                        FVector SegScale((SegLen + OverlapCm) / 100.0f, AvgWidth, 1.0f);
                        FVector SegPos(Center.X, Center.Y, CenterZ);
                        FRotator SegRot(0.0f, AngleDeg, 0.0f);'''

PITCH_NEW = '''                        float CenterZ = (CenterPts[i].Z + CenterPts[i + 1].Z) * 0.5f;
                        float AvgWidth = (WidthsM[i] + WidthsM[i + 1]) * 0.5f;
                        float AngleDeg = FMath::RadiansToDegrees(FMath::Atan2(P2.Y - P1.Y, P2.X - P1.X));
                        // 俯仰角: 河床是连续倾斜坡面, 水平平面盖在坡上会"上坡半埋入土/下坡半露出",
                        //         形成水补丁+泥土条交替条纹。加Pitch让平面沿坡度倾斜,
                        //         两端精确贴合相邻采样点Z, 相邻分段首尾相接成连续贴地水带。
                        float dZ = CenterPts[i + 1].Z - CenterPts[i].Z;
                        float PitchRad = FMath::Atan2(dZ, SegLen);
                        float PitchDeg = FMath::RadiansToDegrees(PitchRad);
                        // 平面缩放: X=斜边长(段长/cosPitch)+重叠 再/100(厘米→米), 补偿倾斜后水平投影缩短;
                        //           Y=宽度(引擎平面基础=1米)
                        FVector SegScale((SegLen / FMath::Max(FMath::Cos(PitchRad), 0.1f) + OverlapCm) / 100.0f, AvgWidth, 1.0f);
                        FVector SegPos(Center.X, Center.Y, CenterZ);
                        FRotator SegRot(PitchDeg, AngleDeg, 0.0f);'''

count_pitch = content.count(PITCH_OLD)
if count_pitch == 1:
    content = content.replace(PITCH_OLD, PITCH_NEW, 1)
    print("OK: 已为河流SMC分段加入Pitch俯仰角")
elif count_pitch == 0 and "PitchRad" in content:
    print("SKIP: Pitch修复已存在")
else:
    errors.append("ERROR: Pitch目标代码块出现 {} 次 (期望1次)".format(count_pitch))
    print("ERROR: Pitch目标代码块出现 {} 次 (期望1次)".format(count_pitch))

# === 修改3: SetMaterial → CreateDynamicMaterialInstance + FlowSpeed ===
MAT_OLD = '                            if (RiverMaterial) SegMeshComp->SetMaterial(0, RiverMaterial);'
MAT_NEW = '''                            // 创建动态材质实例: 允许每段独立设置FlowSpeed参数控制流速
                            // FlowSpeed连接到Panner的Speed输入, speed_x=0.1*FlowSpeed
                            if (RiverMaterial)
                            {
                                UMaterialInstanceDynamic* DynMat = SegMeshComp->CreateDynamicMaterialInstance(0, RiverMaterial);
                                if (DynMat)
                                {
                                    DynMat->SetScalarParameterValue(FName("FlowSpeed"), 1.0f);
                                }
                            }'''

count_mat = content.count(MAT_OLD)
if count_mat == 1:
    content = content.replace(MAT_OLD, MAT_NEW, 1)
    print("OK: 已将SetMaterial替换为CreateDynamicMaterialInstance+FlowSpeed")
elif count_mat == 0 and "CreateDynamicMaterialInstance" in content and "DynMat" in content:
    print("SKIP: CreateDynamicMaterialInstance修改已存在")
else:
    errors.append("ERROR: SetMaterial目标代码出现 {} 次 (期望1次)".format(count_mat))
    print("ERROR: SetMaterial目标代码出现 {} 次 (期望1次)".format(count_mat))

# === 写入文件 ===
if errors:
    print("\n有错误, 放弃写入:")
    for e in errors:
        print("  " + e)
    sys.exit(1)

with open(CPP_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n所有修改已写入: " + CPP_PATH)
