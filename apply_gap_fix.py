# -*- coding: utf-8 -*-
# 补丁脚本: 修改LandscapeHelper.cpp水面段生成逻辑, 修复水面与河岸缺口
# 修改点1: OverlapCm 0->20 (封闭弯道段接缝楔形缺口)
# 修改点2: 新增EdgeMarginM=0.8, 水面宽度加宽埋入岸土 (消除水-土缺口)
import io

PATH = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Plugins\LandscapeHelper\Source\LandscapeHelperEditor\Private\LandscapeHelper.cpp'

with io.open(PATH, 'r', encoding='utf-8', newline='') as f:
    lines = f.readlines()

nl = '\r\n' if lines[0].endswith('\r\n') else '\n'

# --- 修改点1: OverlapCm 与新增 EdgeMarginM ---
idx1 = None
for i, l in enumerate(lines):
    if 'const float OverlapCm = 0.0f;' in l:
        idx1 = i
        break
if idx1 is None:
    raise SystemExit('[ERROR] 未找到 OverlapCm 定义行')

new_block = [
    '                    // 2) 每相邻采样点创建一个SMC平面段' + nl,
    '                    // 重叠=20cm: 封闭河道弯道处相邻段接缝露出的楔形缺口;' + nl,
    '                    //            水面材质改为写深度模式(Opaque/Masked/SingleLayerWater)后,' + nl,
    '                    //            重叠区不再发生半透明alpha叠加, 不会重现暗缝。' + nl,
    '                    const float OverlapCm = 20.0f;' + nl,
    '                    // 水面两侧加宽总量(米): 让水面边缘越过渠壁埋入岸土,' + nl,
    '                    // 可见水线变为水面与岸坡的交线, 消除水面与泥土之间的缺口。' + nl,
    '                    const float EdgeMarginM = 0.8f;' + nl,
]
# 旧注释3行 + 旧定义行 共4行, 整体替换
lines[idx1 - 3: idx1 + 1] = new_block
print('[OK] 修改点1完成: OverlapCm=20, 新增EdgeMarginM=0.8')

# --- 修改点2: SegScale 的 Y 分量加宽 ---
idx2 = None
for i, l in enumerate(lines):
    if 'SegScale' in l and 'AvgWidth, 1.0f);' in l:
        idx2 = i
        break
if idx2 is None:
    raise SystemExit('[ERROR] 未找到 SegScale 行')

lines[idx2] = lines[idx2].replace('AvgWidth, 1.0f);', 'AvgWidth + EdgeMarginM, 1.0f);')
# 同步更新上一行Y注释
if 'Y=宽度(引擎平面基础=1米)' in lines[idx2 - 1]:
    lines[idx2 - 1] = lines[idx2 - 1].replace('Y=宽度(引擎平面基础=1米)', 'Y=宽度+两侧埋入余量(引擎平面基础=1米)')
print('[OK] 修改点2完成: SegScale.Y = AvgWidth + EdgeMarginM')

with io.open(PATH, 'w', encoding='utf-8', newline='') as f:
    f.writelines(lines)
print('[OK] 文件已写回:', PATH)
