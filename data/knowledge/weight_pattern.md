# weight_pattern — 权重空间分布（C++ 解析，第二层）

> 本文件是 UE5_JSON 技能的按需参考文档（由 SKILL.md 2.6 节拆分）。仅在编写/排错 layers[].weight_pattern 时读取。

写在 layers[].weight_pattern 内。`pattern` 字段决定算法：

| pattern 值 | 特有字段 | 说明 |
|------------|----------|------|
| uniform | （无） | 全图均匀 |
| height_based | height_min_m, height_max_m, invert, fade_max_m, fade_width_m, exclude_regions[{min_x,min_y,max_x,max_y}], corridor_exclude | 按高度过渡; fade_max_m/fade_width_m 在 height_max_m 之后继续衰减(如 40~60m 越高越稀, ≥fade_max_m 权重0); exclude_regions 矩形区域内权重清零(如麦田内无草); corridor_exclude=true 时河流/道路走廊(宽×1.25)内权重清零(岸边路侧无草) |
| slope_based | slope_min, slope_max, invert | 按坡度过渡 |
| region | region_min_x, region_min_y, region_max_x, region_max_y | 单矩形区域（平铺，非数组） |
| multi_region | regions[]，每项 {min_x, min_y, max_x, max_y} | 多矩形区域 |
| noise_based | noise_frequency, noise_seed, noise_octaves, invert | 按 Perlin 噪声 |
| aspect_based | aspect_deg, aspect_range_deg, invert | 按坡向 |
| snow_line | snow_line_m, transition_m, max_slope | 海拔雪线 |

易错点（历史踩坑）：
- height_based 用 height_min_m / height_max_m，带 _m 后缀，不是 height_min
- aspect_based 用 aspect_deg / aspect_range_deg，不是 target_angle_deg
- region 模式用平铺四字段 region_min_x 等；只有 multi_region 才用 regions[] 数组
