# -*- coding: utf-8 -*-
"""
将LandscapeHelper.cpp中的PMC连续网格河水代码替换回SMC分段平面方案。
保留PMC版的细分逻辑(每~5米采样), 但输出SMC平面而非ProceduralMeshComponent。
关键改进: 重叠从100cm降到10cm, 深色带宽度缩小10倍。
"""
import re

CPP_PATH = r"D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Plugins\LandscapeHelper\Source\LandscapeHelperEditor\Private\LandscapeHelper.cpp"

with open(CPP_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 定位PMC块: 从"=== 修复: 单连续网格水面"到"=== 瀑布创建"之前
start_marker = '                    // === 修复: 单连续网格水面(消除重叠双重混合导致的颜色变深) ==='
end_marker = '                    // === 瀑布创建(保留原逻辑: 按段遍历) ==='

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1:
    print("ERROR: 未找到PMC块起始标记")
    exit(1)
if end_idx == -1:
    print("ERROR: 未找到瀑布块起始标记")
    exit(1)

if end_idx < start_idx:
    print("ERROR: 瀑布标记在PMC标记之前, 顺序异常")
    exit(1)

old_block = content[start_idx:end_idx]
print(f"找到PMC块: {len(old_block)} 字符, {old_block.count(chr(10))} 行")

# 新SMC分段平面代码块
new_block = '''                    // === 河流水面: 分段SMC平面(细分+边缘对接+10cm微小重叠) ===
                    // 方案: 沿中心线每~5米采样, 每子段创建独立SMC平面
                    //   1) SMC平面=引擎Plane网格, 与湖泊同模式, 确保渲染+序列化
                    //   2) 10cm微小重叠: 覆盖接缝微缝, 远小于旧100cm→深色带极窄(几乎不可见)
                    //   3) 细分(~5m): 转弯处缝隙小, 平面更贴地形
                    //   4) 宽度渐变+沉入河谷(bed_depth), 与PMC版逻辑一致
                    int32 SegmentCount = 0;
                    int32 NumSegs = FMath::Max(River.Points.Num() - 1, 1);
                    float EndW = (River.WidthEndM < 0.0f) ? River.WidthM : River.WidthEndM;
                    // 水面沉入河谷: offset=bed_depth*100-30 → 水面在原地表下30cm(填满河谷)
                    float WaterSinkOffset = (River.BedDepthM > 0.3f)
                        ? (River.BedDepthM * 100.0f - 30.0f)
                        : 2.0f;

                    // 1) 收集中心线采样点(每~5米一个) + 对应宽度(米)
                    TArray<FVector> CenterPts;
                    TArray<float> WidthsM;
                    for (int32 p = 0; p < River.Points.Num() - 1; p++)
                    {
                        FVector2D W1(Location.X + River.Points[p].X * 100.0f, Location.Y + River.Points[p].Y * 100.0f);
                        FVector2D W2(Location.X + River.Points[p + 1].X * 100.0f, Location.Y + River.Points[p + 1].Y * 100.0f);
                        float SegLen = FVector2D::Distance(W1, W2);
                        float SegT0 = (float)p / (float)NumSegs;
                        float SegT1 = (float)(p + 1) / (float)NumSegs;
                        int32 NumSub = FMath::Max(1, FMath::CeilToInt(SegLen / 500.0f));
                        for (int32 s = 0; s < NumSub; s++)
                        {
                            float SubT0 = (float)s / (float)NumSub;
                            float SubMidT = FMath::Lerp(SegT0, SegT1, (SubT0 + (float)(s + 1) / (float)NumSub) * 0.5f);
                            float SubWidth = FMath::Lerp(River.WidthM, EndW, SubMidT);
                            FVector2D SubW1(FMath::Lerp(W1.X, W2.X, SubT0), FMath::Lerp(W1.Y, W2.Y, SubT0));
                            float SubZ = GetTerrainZ(SubW1.X, SubW1.Y) + WaterSinkOffset;
                            CenterPts.Add(FVector(SubW1.X, SubW1.Y, SubZ));
                            WidthsM.Add(SubWidth);
                        }
                    }
                    // 加入河流终点(闭合中心线采样)
                    {
                        FVector2D EndPt(Location.X + River.Points.Last().X * 100.0f, Location.Y + River.Points.Last().Y * 100.0f);
                        float EndZ = GetTerrainZ(EndPt.X, EndPt.Y) + WaterSinkOffset;
                        CenterPts.Add(FVector(EndPt.X, EndPt.Y, EndZ));
                        WidthsM.Add(EndW);
                    }

                    // 2) 每相邻采样点创建一个SMC平面段(边缘对接+10cm微小重叠)
                    const float OverlapCm = 10.0f;
                    for (int32 i = 0; i < CenterPts.Num() - 1; i++)
                    {
                        FVector2D P1(CenterPts[i].X, CenterPts[i].Y);
                        FVector2D P2(CenterPts[i + 1].X, CenterPts[i + 1].Y);
                        float SegLen = FVector2D::Distance(P1, P2);
                        if (SegLen < 1.0f) continue;
                        FVector2D Center((P1.X + P2.X) * 0.5f, (P1.Y + P2.Y) * 0.5f);
                        float CenterZ = (CenterPts[i].Z + CenterPts[i + 1].Z) * 0.5f;
                        float AvgWidth = (WidthsM[i] + WidthsM[i + 1]) * 0.5f;
                        float AngleDeg = FMath::RadiansToDegrees(FMath::Atan2(P2.Y - P1.Y, P2.X - P1.X));
                        // 平面缩放: X=(段长+重叠)/100, Y=宽度(引擎平面基础=1米)
                        FVector SegScale((SegLen + OverlapCm) / 100.0f, AvgWidth, 1.0f);
                        FVector SegPos(Center.X, Center.Y, CenterZ);
                        FRotator SegRot(0.0f, AngleDeg, 0.0f);
                        // 创建SMC平面段(与湖泊相同模式, 确保渲染+序列化)
                        AActor* SegActor = WaterWorld->SpawnActor<AActor>(AActor::StaticClass(), SegPos, SegRot);
                        if (SegActor)
                        {
                            UStaticMeshComponent* SegMeshComp = NewObject<UStaticMeshComponent>(SegActor);
                            SegMeshComp->CreationMethod = EComponentCreationMethod::Instance;
                            SegActor->SetRootComponent(SegMeshComp);
                            SegActor->AddInstanceComponent(SegMeshComp);
                            SegMeshComp->SetStaticMesh(PlaneMesh);
                            if (RiverMaterial) SegMeshComp->SetMaterial(0, RiverMaterial);
                            SegMeshComp->SetRelativeScale3D(SegScale);
                            SegMeshComp->RegisterComponent();
                            SegMeshComp->SetWorldLocationAndRotation(SegPos, SegRot);
                            SegActor->Modify();
                            SegActor->MarkPackageDirty();
                            SegmentCount++;
                        }
                    }

'''

new_content = content[:start_idx] + new_block + content[end_idx:]

# 验证替换结果
if 'UProceduralMeshComponent' in new_content:
    # 检查是否还有PMC引用(Include行可能还在, 那是允许的)
    pmc_in_code = False
    for line in new_content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('//'):
            continue
        if 'UProceduralMeshComponent' in stripped or 'CreateMeshSection' in stripped or 'RiverPMC' in stripped:
            pmc_in_code = True
            print(f"WARNING: 代码中仍有PMC引用: {stripped[:80]}")
    if not pmc_in_code:
        print("OK: 代码块中已无PMC引用(Include行除外)")

# 验证关键变量
for var in ['SegmentCount', 'CenterPts', 'WidthsM', 'OverlapCm', 'PlaneMesh', 'RiverMaterial']:
    if var in new_block:
        print(f"OK: 变量 {var} 存在")
    else:
        print(f"WARNING: 变量 {var} 不在新块中")

with open(CPP_PATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"\n替换完成: 旧块{len(old_block)}字符 → 新块{len(new_block)}字符")
print(f"文件已写回: {CPP_PATH}")
