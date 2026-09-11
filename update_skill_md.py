#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新 SKILL.md: ① type字段加3新模式 ② 模式速览表加3行 ③ 模板表加3行 ④ 模板计数7→10"""

import os

SKILL_DIR = r"c:\Users\25868\.trae-cn\skills\ue5_json"
SKILL_PATH = os.path.join(SKILL_DIR, "SKILL.md")

with open(SKILL_PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes = []

# ① type 字段描述: 加入 terraced/karst/gully
old1 = "| type | string | 全部 | flat/ridge/hill/noise/hill_ridge/features |"
new1 = "| type | string | 全部 | flat/ridge/hill/noise/hill_ridge/terraced/karst/gully/features |"
if old1 in content:
    content = content.replace(old1, new1)
    changes.append("[1] type字段描述已更新")
else:
    print("[WARN] 未找到 type 字段行")

# ② 模式速览表: 在 hill_ridge 行后、features 行前插入3行
old2 = "| hill_ridge | 田垄复合 | ridge_amplitude_m, ridge_frequency, ridge_direction_deg, ridge_region_* |\n| features |"
new2 = "| hill_ridge | 田垄复合 | ridge_amplitude_m, ridge_frequency, ridge_direction_deg, ridge_region_* |\n| terraced | 梯田 | direction_deg, step_height_m, step_width_m, bank_ratio, base_height_m |\n| karst | 喀斯特峰林 | peak_count, min_distance_m, peak_height_min_m/max_m, peak_radius_m, doline_count, doline_depth_m, doline_radius_m, seed |\n| gully | 黄土沟壑 | main_direction_deg, main_length_m, meander_*, branch_*, gully_depth_m, gully_width_m, profile, seed |\n| features |"
if old2 in content:
    content = content.replace(old2, new2)
    changes.append("[2] 模式速览表已新增3行")
else:
    print("[WARN] 未找到模式速览表插入点")

# ③ 模板表: 在 p11 行后插入3行
old3 = "| templates/template_p11_full_terrain.json | 全地形（1km） | 综合：山丘/雪线/草地/麦田/碎石/道路 |\n"
new3 = "| templates/template_p11_full_terrain.json | 全地形（1km） | 综合：山丘/雪线/草地/麦田/碎石/道路 |\n| templates/template_p12_terraced.json | 梯田 | terraced模式：direction_deg递进+step_height_m台阶+bank_ratio田埂 |\n| templates/template_p13_karst.json | 喀斯特峰林 | karst模式：泊松盘峰采样+高斯锥凸起+溶斗下凹 |\n| templates/template_p14_gully.json | 黄土沟壑 | gully模式：主沟蜿蜒+支沟分叉+V型切削 |\n"
if old3 in content:
    content = content.replace(old3, new3)
    changes.append("[3] 模板表已新增3行")
else:
    print("[WARN] 未找到模板表插入点")

# ④ 模板计数: 7→10 (两处)
old4a = "7 个模板完整字段说明与派生要点"
new4a = "10 个模板完整字段说明与派生要点"
count_a = content.count(old4a)
content = content.replace(old4a, new4a)
if count_a > 0:
    changes.append(f"[4] 模板计数 7→10 ({count4a}处)" if False else f"[4] 模板计数 7→10 ({count_a}处)")

old4b = "7 个模板完整说明与派生要点"
new4b = "10 个模板完整说明与派生要点"
count_b = content.count(old4b)
content = content.replace(old4b, new4b)
if count_b > 0:
    changes.append(f"[5] references索引模板计数 7→10 ({count_b}处)")

# 写回
with open(SKILL_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print(f"[OK] SKILL.md 已更新 ({len(changes)}处修改)")
for c in changes:
    print(f"  {c}")
print(f"  文件: {SKILL_PATH}")
print(f"  大小: {os.path.getsize(SKILL_PATH)} bytes")
