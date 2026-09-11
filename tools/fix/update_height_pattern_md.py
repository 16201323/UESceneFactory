#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新 height_pattern.md: 在hill_ridge节后插入terraced/karst/gully三节"""

import os

SKILL_DIR = r"c:\Users\25868\.trae-cn\skills\ue5_json"
HP_PATH = os.path.join(SKILL_DIR, "references", "height_pattern.md")

# 读取原文件
with open(HP_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# 三节新内容
new_sections = """## terraced 模式专属字段（梯田）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| direction_deg | float | 0.0 | 梯田递进方向角（0=+X东向, 90=+Y北向），顶点投影到此方向轴计算层级 |
| step_height_m | float | 3.0 | 每级梯田高度差（米），值越大台阶越陡 |
| step_width_m | float | 12.0 | 每级梯田宽度（米），即方向上每N米升一级 |
| bank_ratio | float | 0.25 | 田埂占比[0,1]，0=无田埂全平坦，1=全田埂；0.2=每级20%为smoothstep过渡区+80%为平坦田面 |
| base_height_m | float | 0.0 | 起始基准高度（米），direction_deg方向投影距离=0处 |

**算法**：将顶点投影到 direction_deg 方向轴，投影距离 ÷ step_width_m 取整 = 层级号 level；层内位置 t∈[0,1)：t < (1-bank_ratio) → 平坦田面（高度 = base + level × step_height_m），t ≥ (1-bank_ratio) → smoothstep 过渡到下一级。bank_ratio 被 C++ 钳制到 [0,1]。

**调参建议**：
- 密台阶：减小 step_width_m，增大 step_height_m
- 缓坡梯田：减小 step_height_m，增大 step_width_m
- 陡峭田埂：增大 bank_ratio（0.3~0.5）
- direction_deg=0 沿X轴，90 沿Y轴，45 沿对角线

## karst 模式专属字段（喀斯特峰林）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| peak_count | int | 30 | 峰点数量，决定峰林密度 |
| min_distance_m | float | 50.0 | 峰间最小距离（米），泊松盘采样参数，值越大峰越稀疏 |
| peak_height_min_m | float | 10.0 | 峰最低高度（米） |
| peak_height_max_m | float | 40.0 | 峰最高高度（米），每峰随机取[min,max]区间 |
| peak_radius_m | float | 20.0 | 峰底半径（米），高斯锥 σ=radius/2，控制山体坡度 |
| doline_count | int | 0 | 溶斗（漏斗）数量，地表塌陷坑，0=无溶斗 |
| doline_depth_m | float | 5.0 | 溶斗下凹深度（米） |
| doline_radius_m | float | 15.0 | 溶斗半径（米） |
| seed | int | 42 | 随机种子，控制峰/溶斗位置分布 |

**算法**：泊松盘采样（Poisson disk）在 min_distance_m 约束下生成 peak_count 个峰点，每峰随机高度 ∈ [peak_height_min_m, peak_height_max_m]；每峰以高斯锥凸起：delta = height × exp(-d² / (2σ²))，σ = peak_radius_m / 2；溶斗同理但高度为负（下凹）；所有峰/溶斗高度累加（blend_mode=additive）。

**调参建议**：
- 密峰林：增大 peak_count，减小 min_distance_m
- 孤立峰：减小 peak_count（5~15），增大 min_distance_m
- 尖锐峰：减小 peak_radius_m（坡度更陡）
- 平缓丘陵：增大 peak_radius_m，减小 peak_height_max_m
- doline_count=0 可关闭溶斗（纯峰林）

## gully 模式专属字段（黄土沟壑）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| main_direction_deg | float | 0.0 | 主沟流向角（0=+X东向, 90=+Y北向） |
| main_length_m | float | 1000.0 | 主沟长度（米） |
| meander_amplitude_m | float | 30.0 | 蜿蜒幅度（米），主沟中心线垂直偏移 |
| meander_frequency | float | 0.01 | 蜿蜒频率，值越大弯道越多 |
| branch_count | int | 5 | 一级支沟数量 |
| branch_angle_deg | float | 45.0 | 支沟与主沟夹角（度），支沟随机取 ± 此角度 |
| branch_length_ratio | float | 0.5 | 支沟长度 = 主沟长度 × 此比例 |
| branch_depth | int | 1 | 分叉深度，1=仅一级支沟，2=支沟再分叉二级支沟（递归） |
| gully_depth_m | float | 6.0 | 沟壑切削深度（米） |
| gully_width_m | float | 12.0 | 沟壑宽度（米） |
| profile | string | "V" | 横截面形状，V=V型余弦切 / U=U型平底 |
| seed | int | 42 | 随机种子，控制分叉点位置 / 蜿蜒相位 |

**算法**：主沟路径 = 沿 main_direction_deg 方向行进 main_length_m，中心线叠加垂直方向正弦蜿蜒（meander_amplitude_m × sin(meander_frequency × 距离)）；从主沟随机 branch_count 个点分叉支沟，支沟方向 = 主沟方向 ± branch_angle_deg，支沟长度 = main_length × branch_length_ratio；branch_depth ≥ 2 时支沟递归再分叉二级支沟；每条沟沿路径用 V/U 型余弦横截面切削地形（delta = -gully_depth_m × cos(πd / width)，d 为到沟中心线距离）；AABB 裁剪提升性能。

**调参建议**：
- 密沟网：增大 branch_count，branch_depth=2
- 单一主沟：branch_count=0
- 深切峡谷：增大 gully_depth_m，减小 gully_width_m
- 宽缓沟谷：增大 gully_width_m，减小 gully_depth_m，profile="U"
- main_direction_deg=45 使沟壑沿东北-西南对角线

"""

# 插入点: 在 "## 其他顶层字段" 之前
marker = "## 其他顶层字段"
idx = content.find(marker)
if idx == -1:
    print("[ERROR] 未找到插入标记 '## 其他顶层字段'")
    exit(1)

new_content = content[:idx] + new_sections + content[idx:]

# 写回
with open(HP_PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

old_lines = len(content.splitlines())
new_lines = len(new_content.splitlines())
print(f"[OK] height_pattern.md 已更新: {old_lines} -> {new_lines} 行 (+{new_lines - old_lines})")
print(f"     文件: {HP_PATH}")
print(f"     大小: {os.path.getsize(HP_PATH)} bytes")
