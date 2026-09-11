#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方形铁丝网围栏 JSON 生成器
=========================
参数:
  - center: 围栏中心点坐标 (cm)
  - length: 围栏长度, 沿 X 轴 (cm)
  - width:  围栏宽度, 沿 Y 轴 (cm)

铁丝网面板资产: Plane_004_chainlink_fence_textures_0
  边界尺寸: 203.7(X) x 22.6(Y) x 236.4(Z) cm, 原点在中心
  长轴沿 X (203.7cm), 厚度沿 Y (22.6cm), 高度沿 Z (236.4cm)

布局策略:
  - 间距 spacing=200cm, 略小于面板长轴 203.7cm (1.8% 重叠), 保证严丝合缝
  - 长边 (Y=±width/2): 面板长轴沿 X, 南边yaw=180/北边yaw=0 (弯折朝外)
  - 短边 (X=±length/2): 面板长轴旋转 90° 沿 Y, 西边yaw=90/东边yaw=270 (弯折朝外)
  - 弯折方向: 默认yaw=0弯折朝+Y; yaw=90朝-X; yaw=180朝-Y; yaw=270朝+X
  - 四角处长边末端面板与短边面板互相垂直交叠 (~13cm 重叠区), 封死角落
  - Z=111: 面板原点在中心, 236.4/2≈118, 取 111 使底部略微入土接地
"""

import json
import math

# ==================== 参数配置 ====================
# 围栏中心点 (cm) — 用户指定原点
CENTER = [0, 0, 0]
# 围栏长度 100m, 沿 X 轴 (cm)
LENGTH = 10000
# 围栏宽度 50m, 沿 Y 轴 (cm)
WIDTH = 5000

# 铁丝网面板尺寸 (cm) — 来自资产探测结果
PANEL_LENGTH = 203.7       # 面板长轴 (X 方向, 默认朝向)
PANEL_Z_OFFSET = 111       # Z 偏移: 原点在中心, 半高≈118, 取111贴地

# 面板间距 (cm) — 略小于面板长度, 形成小幅重叠保证无缝
SPACING = 200.0

# 输出路径
OUTPUT_PATH = r"c:\Users\25868\Desktop\UE5\MapForgeTest\square_fence.json"

# ==================== 几何计算 ====================
half_len = LENGTH / 2       # X 方向半长 = 5000
half_wid = WIDTH / 2        # Y 方向半宽 = 2500

instances = []

# --- 长边 (Y = ±half_wid), 面板长轴沿 X, rotation=[0,0,0] (yaw=0) ---
# 数量 = 长度 / 间距, 向上取整保证覆盖
n_long = int(math.ceil(LENGTH / SPACING))   # 10000/200 = 50
# 居中排列: 第一个面板中心 X = -half_len + spacing/2
start_x = -half_len + SPACING / 2            # -4900
for side in (-1, 1):                         # 两条长边: Y=-2500(南) 和 Y=+2500(北)
    y = side * half_wid
    # 弯折朝外原则: 默认yaw=0弯折朝+Y, 故北边(side=+1)用yaw=0弯折朝外(+Y)
    #   南边(side=-1)需翻转180°, yaw=180使弯折朝-Y(外)
    yaw_long = 180 if side == -1 else 0
    for k in range(n_long):
        x = start_x + k * SPACING            # -4900, -4700, ..., 4900
        instances.append({
            "location": [round(x, 1), y, PANEL_Z_OFFSET],
            "rotation": [0, yaw_long, 0],    # 南yaw=180/北yaw=0, 弯折朝外
            "scale": [1, 1, 1]
        })

# --- 短边 (X = ±half_len), 面板长轴旋转 90° 沿 Y, rotation=[0,90,0] (yaw=90) ---
n_short = int(math.ceil(WIDTH / SPACING))    # 5000/200 = 25
start_y = -half_wid + SPACING / 2            # -2400
for side in (-1, 1):                         # 两条短边: X=-5000(西) 和 X=+5000(东)
    x = side * half_len
    # 弯折朝外原则: yaw=90弯折朝-X, 故西边(side=-1)用yaw=90弯折朝外(-X)
    #   东边(side=+1)需翻转180°, yaw=270使弯折朝+X(外)
    yaw_short = 90 if side == -1 else 270
    for k in range(n_short):
        y = start_y + k * SPACING            # -2400, -2200, ..., 2400
        instances.append({
            "location": [x, round(y, 1), PANEL_Z_OFFSET],
            "rotation": [0, yaw_short, 0],   # 西yaw=90/东yaw=270, 弯折朝外
            "scale": [1, 1, 1]
        })

# ==================== 验证数据 ====================
long_span = (n_long - 1) * SPACING + PANEL_LENGTH   # 长边实际覆盖
short_span = (n_short - 1) * SPACING + PANEL_LENGTH  # 短边实际覆盖
overlap_pct = (PANEL_LENGTH - SPACING) / PANEL_LENGTH * 100  # 重叠百分比

# ==================== 组装 JSON ====================
scene = {
    "scene": {
        "name": "Square_Wirefence",
        "target_level": "/Game/MapForgeTest/GB_Square_Wirefence",
        "description": (
            f"方形铁丝网围栏 — 中心{CENTER}, "
            f"长{LENGTH/100}m(X) x 宽{WIDTH/100}m(Y). "
            f"面板间距{SPACING}cm(面板长{PANEL_LENGTH}cm, 重叠{overlap_pct:.1f}%). "
            f"长边{n_long}块x2={n_long*2}, 短边{n_short}块x2={n_short*2}, "
            f"共{len(instances)}块. 南yaw=180/北yaw=0, 西yaw=90/东yaw=270 (弯折朝外)"
        )
    },
    "ground": {
        "asset": "/Game/RuralHouse/House/Meshes/ModularParts/SM_House_FloorPlane_03",
        "location": CENTER,
        "scale": [11, 11, 1],
        "material_override": "/Game/Foliage_Sets/ground_materials/materials/M_grass_simple_a"
    },
    "placements": [
        {
            "type": "instanced_grid",
            "asset": "/Game/WireFence/chainlink_fence_tileable/StaticMeshes/Plane_004_chainlink_fence_textures_0",
            "location": CENTER,
            "rotation": [0, 0, 0],
            "scale": [1, 1, 1],
            "instances": instances
        }
    ],
    "lighting": {
        "directional_light": {
            "location": [0, 0, 3000],
            "rotation": [-45, 35, 0],
            "intensity": 10.0,
            "color": [1.0, 0.94, 0.78],
            "cast_shadows": True
        },
        "sky_light": {
            "location": [0, 0, 3000],
            "intensity": 1.0,
            "color": [0.78, 0.86, 1.0]
        },
        "sky_atmosphere": {"location": [0, 0, 0]}
    }
}

# ==================== 写出文件 ====================
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(scene, f, ensure_ascii=False, indent=2)

# ==================== 输出摘要 ====================
print("=" * 60)
print(f"JSON 已生成: {OUTPUT_PATH}")
print("=" * 60)
print(f"中心点:     {CENTER}")
print(f"长度(X):    {LENGTH}cm = {LENGTH/100}m")
print(f"宽度(Y):    {WIDTH}cm = {WIDTH/100}m")
print(f"面板间距:   {SPACING}cm (面板长轴 {PANEL_LENGTH}cm)")
print(f"重叠率:     {overlap_pct:.1f}% (严丝合缝)")
print(f"长边面板:   {n_long} 块 x 2 边 = {n_long*2}")
print(f"  X 范围:   {start_x} ~ {start_x + (n_long-1)*SPACING}")
print(f"  覆盖:     {long_span:.1f}cm (目标 {LENGTH}cm, 误差 +{long_span-LENGTH:.1f}cm)")
print(f"短边面板:   {n_short} 块 x 2 边 = {n_short*2}")
print(f"  Y 范围:   {start_y} ~ {start_y + (n_short-1)*SPACING}")
print(f"  覆盖:     {short_span:.1f}cm (目标 {WIDTH}cm, 误差 +{short_span-WIDTH:.1f}cm)")
print(f"总面板数:   {len(instances)}")
print(f"长边朝向:   南yaw=180/北yaw=0 (弯折朝外)")
print(f"短边朝向:   西yaw=90/东yaw=270 (弯折朝外)")
print("=" * 60)
