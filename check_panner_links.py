# -*- coding: utf-8 -*-
# 检查 MM_Water 材质的引脚连接情况(哪些 MaterialInput 被序列化 = 有连线)
# 以及确认 Panner 的 Speed 输入是否已连线(连线会覆盖 SpeedX/SpeedY 字面值)
import re
import struct

PATH = r'D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Content\Modular_Rural_Cabin\Materials\Masters\MM_Water.uasset'
data = open(PATH, 'rb').read()

def has_name(name):
    b = name.encode('ascii')
    pat = struct.pack('<i', len(b) + 1) + b + b'\x00'
    hits = [m.start() for m in re.finditer(re.escape(pat), data)]
    return hits

checks = [
    'Speed', 'SpeedX', 'SpeedY', 'Time', 'Coordinate', 'CoordinateIndex',
    'OpacityMaskMaterialInput', 'OpacityMaterialInput', 'BaseColorMaterialInput',
    'NormalMaterialInput', 'RoughnessMaterialInput', 'MetallicMaterialInput',
    'SpecularMaterialInput', 'EmissiveColorMaterialInput',
    'MaterialExpressionPanner', 'MaterialExpressionAppendVector',
    'MaterialExpressionScalarParameter', 'MaterialExpressionConstant',
    'MaterialExpressionMultiply', 'MaterialExpressionTextureCoordinate',
    'R', 'A', 'B', 'ConstA', 'ConstB', 'UTiling', 'VTiling',
    'UnTileU', 'UnTileV', 'bUseFractionalTime', 'ShadingModel',
]
print('=== name table presence ===')
for n in checks:
    print(f'  {n:42s} -> {has_name(n)}')

# 统计 Panner 出现次数(导出表里的类引用无法直接数, 用 EditorComments/实例数间接判断)
print()
print('=== count of "MaterialExpressionPanner" raw substring ===')
print('  ', len(re.findall(rb'MaterialExpressionPanner', data)))
print('=== count of "MaterialExpressionAppendVector" raw substring ===')
print('  ', len(re.findall(rb'MaterialExpressionAppendVector', data)))
print('=== count of "FlowSpeed" raw substring ===')
print('  ', len(re.findall(rb'FlowSpeed', data)))
