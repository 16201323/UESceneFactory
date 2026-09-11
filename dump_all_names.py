# -*- coding: utf-8 -*-
# 打印 MM_Water.uasset 名字表全部条目 + 复查 SpeedX/SpeedY 磁盘值
# 目的: 1) 确认用户修改是否落盘  2) 找出 TextureSample 引用的贴图资产名(判断是否有真实水法线贴图)
import struct
PATH = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content\Modular_Rural_Cabin\Materials\Masters\MM_Water.uasset'
data = open(PATH, 'rb').read()
entries = {}
for off in range(0, len(data) - 8):
    slen = struct.unpack_from('<i', data, off)[0]
    if slen < 2 or slen > 256 or off + 4 + slen + 4 > len(data):
        continue
    raw = data[off + 4: off + 4 + slen]
    if raw[-1] != 0:
        continue
    try:
        s = raw[:-1].decode('ascii')
    except UnicodeDecodeError:
        continue
    if s and all(32 <= ord(c) < 127 for c in s):
        entries[off] = s
best = []
for off in sorted(entries):
    chain, q = [], off
    while q in entries:
        chain.append(entries[q])
        q = q + 4 + (len(entries[q]) + 1) + 4
    if len(chain) > len(best):
        best = chain
names = best
print('=== name table (' + str(len(names)) + ') ===')
for i, n in enumerate(names):
    print(str(i).rjust(4) + '  ' + n)
