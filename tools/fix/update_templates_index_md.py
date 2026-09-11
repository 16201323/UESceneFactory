#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""更新 templates_index.md: 在P11节后、派生要点前插入P12/P13/P14三节"""

import os

TI_PATH = r"c:\Users\25868\.trae-cn\skills\ue5_json\references\templates_index.md"

with open(TI_PATH, "r", encoding="utf-8") as f:
    content = f.read()

new_sections = """## 模板 P12 — 梯田地形（terraced 模式）

- 文件：`templates/template_p12_terraced.json`
- 模式：`height_pattern.type = "terraced"`
- 地形规格：`component_count 1×1, section_size_quads 63, scale 100` → 63m×63m

**核心参数：**

| 参数 | 值 | 说明 |
|------|-----|------|
| direction_deg | 90 | 梯田沿+Y(北)方向递进，0=+X东向 |
| step_height_m | 3.0 | 每级台阶高差3米 |
| step_width_m | 12.0 | 每12米升一级 |
| bank_ratio | 0.2 | 田埂占20%，80%为平坦田面 |
| base_height_m | 0.0 | 起始基准高度 |

**算法**：顶点投影到 direction_deg 方向轴，投影距离 ÷ step_width_m = 层级号；层内位置 < (1-bank_ratio) 为平坦田面，≥ (1-bank_ratio) 为 smoothstep 过渡到下一级。bank_ratio 被 C++ 钳制到 [0,1]。

**派生方法**：复制模板后改 `target_level`/`direction_deg`/`step_height_m`/`step_width_m`/`bank_ratio`。放大地形改 `component_count_x/y`（如 8×8 → 1km）。密台阶减小 step_width_m 增大 step_height_m；缓坡反之；陡峭田埂增大 bank_ratio（0.3~0.5）。

## 模板 P13 — 喀斯特峰林（karst 模式）

- 文件：`templates/template_p13_karst.json`
- 模式：`height_pattern.type = "karst"`
- 地形规格：`component_count 1×1, section_size_quads 63, scale 100` → 63m×63m

**核心参数：**

| 参数 | 值 | 说明 |
|------|-----|------|
| peak_count | 40 | 40座山峰 |
| min_distance_m | 60 | 峰间最小距离60m（泊松盘） |
| peak_height_min_m | 15 | 最低峰高15m |
| peak_height_max_m | 45 | 最高峰高45m |
| peak_radius_m | 25 | 峰底半径25m（σ=12.5） |
| doline_count | 8 | 8个溶斗 |
| doline_depth_m | 6 | 溶斗下凹6m |
| doline_radius_m | 18 | 溶斗半径18m |
| seed | 42 | 随机种子 |

**算法**：泊松盘采样在 min_distance_m 约束下生成 peak_count 个峰点；每峰高斯锥凸起 delta = h × exp(-d²/(2σ²))，σ = peak_radius_m/2；溶斗同理但为负（下凹）；所有高度累加（additive）。

**派生方法**：复制模板后改 `peak_count`/`min_distance_m`/`peak_height_min/max_m`/`peak_radius_m`/`doline_*`/`seed`。想要孤立峰林减小 peak_count 增大 min_distance_m；想要密峰林反之；想要尖锐峰减小 peak_radius_m；doline_count=0 可关闭溶斗。

## 模板 P14 — 黄土沟壑（gully 模式）

- 文件：`templates/template_p14_gully.json`
- 模式：`height_pattern.type = "gully"`
- 地形规格：`component_count 1×1, section_size_quads 63, scale 100` → 63m×63m

**核心参数：**

| 参数 | 值 | 说明 |
|------|-----|------|
| main_direction_deg | 45 | 主沟东北-西南对角线流向 |
| main_length_m | 800 | 主沟长800m |
| meander_amplitude_m | 40 | 蜿蜒幅度40m |
| meander_frequency | 0.008 | 蜿蜒频率 |
| branch_count | 6 | 6条一级支沟 |
| branch_angle_deg | 50 | 支沟与主沟夹角50° |
| branch_length_ratio | 0.5 | 支沟长度=主沟×0.5 |
| branch_depth | 1 | 仅一级支沟（2=二级分叉） |
| gully_depth_m | 8 | 沟深8m |
| gully_width_m | 15 | 沟宽15m |
| profile | "V" | V型余弦横截面 |
| seed | 42 | 随机种子 |

**算法**：主沟沿 main_direction_deg 方向行进 main_length_m，中心线叠加正弦蜿蜒（meander_amplitude_m × sin(meander_frequency × 距离)）；从主沟随机 branch_count 个点分叉支沟（±branch_angle_deg，长度=main_length×branch_length_ratio）；branch_depth≥2 递归分叉二级支沟；每条沟用 V/U 型余弦横截面切削地形。

**派生方法**：复制模板后改 `main_direction_deg`/`main_length_m`/`branch_count`/`branch_depth`/`gully_depth_m`/`gully_width_m`/`profile`/`seed`。想要密沟网设 branch_depth=2；想要单一主沟设 branch_count=0；想要宽缓沟谷增大 gully_width_m 减小 gully_depth_m 改 profile="U"。

"""

# 插入点: 在 "## 派生要点" 之前
marker = "## 派生要点"
idx = content.find(marker)
if idx == -1:
    print("[ERROR] 未找到插入标记 '## 派生要点'")
    exit(1)

new_content = content[:idx] + new_sections + content[idx:]

with open(TI_PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

old_lines = len(content.splitlines())
new_lines = len(new_content.splitlines())
print(f"[OK] templates_index.md 已更新: {old_lines} -> {new_lines} 行 (+{new_lines - old_lines})")
print(f"     文件: {TI_PATH}")
print(f"     大小: {os.path.getsize(TI_PATH)} bytes")
