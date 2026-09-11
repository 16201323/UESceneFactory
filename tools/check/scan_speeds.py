# -*- coding: utf-8 -*-
# 扫描MM_Water.uasset中Panner的SpeedX/SpeedY序列化字节序, 判断磁盘当前值
import struct
import re

PATH = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content\Modular_Rural_Cabin\Materials\Masters\MM_Water.uasset'

data = open(PATH, 'rb').read()
print(f'文件大小: {len(data)}')

patterns = [
    ('speed=(0.1, 0.0)', struct.pack('<ff', 0.1, 0.0)),
    ('speed=(0.0, 0.1)', struct.pack('<ff', 0.0, 0.1)),
    ('speed=(0.1, 0.1)', struct.pack('<ff', 0.1, 0.1)),
    ('speed=(0.0, 0.0)', struct.pack('<ff', 0.0, 0.0)),
]
for name, pat in patterns:
    offs = [m.start() for m in re.finditer(re.escape(pat), data)]
    print(f'{name}: 出现{len(offs)}次, 偏移={offs}')
