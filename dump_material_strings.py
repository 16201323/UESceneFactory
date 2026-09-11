# -*- coding: utf-8 -*-
# 从 MM_Water.uasset 提取可读字符串, 用于识别材质图表中的节点类型与参数名
# 目的: 确认连到 Panner 的 Speed 引脚的上游节点到底是什么(VectorParameter? Append? Constant2?)
import re
import struct

PATH = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content\Modular_Rural_Cabin\Materials\Masters\MM_Water.uasset'

data = open(PATH, 'rb').read()
print('file size =', len(data))

# 1) 提取 ASCII 字符串(长度>=4)
ascii_strs = re.findall(rb'[\x20-\x7e]{4,}', data)
seen = set()
ordered = []
for s in ascii_strs:
    t = s.decode('ascii')
    if t not in seen:
        seen.add(t)
        ordered.append(t)

# 2) 只关注与材质表达式/参数相关的条目
keys = ('Expression', 'Parameter', 'Panner', 'Speed', 'Vector', 'Append', 'Constant',
        'Flow', 'Water', 'Texture', 'Mask', 'Blend', 'Shading', 'Time', 'Noise', 'Wav')
print('\n=== expression / parameter related strings ===')
for t in ordered:
    if any(k.lower() in t.lower() for k in keys):
        print('  ', t)

print('\n=== all strings count =', len(ordered))
print('\n=== first 120 strings (name table region) ===')
for t in ordered[:120]:
    print('  ', t)

# 3) 扫描 Constant2Vector / VectorParameter 的默认值(两相邻float), 找 (0,0.1)/(0.1,0)
print('\n=== adjacent float pairs matching speed-like values ===')
targets = {
    '(0.1, 0.0)': struct.pack('<ff', 0.1, 0.0),
    '(0.0, 0.1)': struct.pack('<ff', 0.0, 0.1),
    '(1.0, 0.0)': struct.pack('<ff', 1.0, 0.0),
    '(0.0, 1.0)': struct.pack('<ff', 0.0, 1.0),
    '(0.1, 0.1)': struct.pack('<ff', 0.1, 0.1),
}
for name, pat in targets.items():
    offs = [m.start() for m in re.finditer(re.escape(pat), data)]
    if offs:
        print(f'  {name}: {len(offs)} hits at {offs}')
