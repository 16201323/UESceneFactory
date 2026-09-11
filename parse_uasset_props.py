# -*- coding: utf-8 -*-
# 读取 MM_Water 材质图表中决定流向的真实数值:
#   Panner.SpeedX (x2) / Constant.R / Multiply.ConstB / ScalarParameter.DefaultValue
# 名字表用"最长连续链"算法定位(UE5.8 包头布局变化, 无法直接解析 Summary)
import struct

PATH = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content\Modular_Rural_Cabin\Materials\Masters\MM_Water.uasset'
data = open(PATH, 'rb').read()

# ---------- 名字表 ----------
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
print('names =', len(names))


def ix(n):
    return names.index(n) if n in names else -1


# ---------- 打印 SpeedX 标签附近的原始字节, 确认 FPropertyTag 布局 ----------
sx = ix('SpeedX')
print('\n=== raw bytes around SpeedX tag occurrences ===')
for off in range(0, len(data) - 32):
    ci = struct.unpack_from('<i', data, off)[0]
    if ci != sx:
        continue
    num = struct.unpack_from('<i', data, off + 4)[0]
    if num != 0:
        continue
    lo = off - 4
    chunk = data[lo: lo + 48]
    print('tag@' + str(off))
    print('   hex  :', chunk.hex(' '))
    print('   i32  :', list(struct.unpack_from('<12i', chunk)))
    print('   f32  :', [round(f, 5) for f in struct.unpack_from('<12f', chunk)])

# ---------- 通用: 按标签名扫描浮点属性 ----------
fp = ix('FloatProperty')


def scan_float(tagname, value_off_delta):
    ti = ix(tagname)
    out = []
    if ti < 0:
        return out
    for off in range(0, len(data) - 32):
        if struct.unpack_from('<i', data, off)[0] != ti:
            continue
        if struct.unpack_from('<i', data, off + 4)[0] != 0:
            continue
        if struct.unpack_from('<i', data, off + 8)[0] != fp:
            continue
        out.append((off, struct.unpack_from('<f', data, off + value_off_delta)[0]))
    return out


print('\n=== float property scan (delta 16 = Size+ArrayIndex then value) ===')
for n in ('SpeedX', 'R', 'ConstB', 'ConstA', 'DefaultValue', 'BaseReflectFractionIn',
          'Fresnel Exponent', 'FadeDistance', 'Basecolor Power', 'ExponentIn'):
    r16 = scan_float(n, 16)
    r12 = scan_float(n, 12)
    print('  ' + n.ljust(24) + ' delta16=' + str([(o, round(v, 5)) for o, v in r16])
          + '  delta12=' + str([(o, round(v, 5)) for o, v in r12]))
