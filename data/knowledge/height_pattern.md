# height_pattern — 高度模式（C++ 解析，第二层）

> 本文件是 UE5_JSON 技能的按需参考文档（由 SKILL.md 2.5 节拆分）。仅在编写/排错 height_pattern 时读取，无需常驻上下文。

控制地形起伏。`type` 字段决定模式，所有字段都是 height_pattern 对象内部字段。

## 顶层字段（flat/ridge/hill/noise/hill_ridge 用）

| 字段 | 类型 | 适用模式 | 说明 |
|------|------|----------|------|
| type | string | 全部 | flat/ridge/hill/noise/hill_ridge/terraced/karst/gully/features |
| amplitude_m | float | ridge/hill/noise | 高度幅度（米） |
| frequency | float | ridge/noise | 频率 |
| direction_deg | float | ridge | 山脊方向角 |
| seed | float | hill/noise | 噪声种子 |
| hill_count | int | hill | 山丘数量 |
| hill_radius_m | float | hill | 山丘半径（米） |

## hill_ridge 复合模式专属字段

| 字段 | 类型 | 说明 |
|------|------|------|
| ridge_amplitude_m | float | 田垄幅度（米） |
| ridge_frequency | float | 田垄频率 |
| ridge_direction_deg | float | 田垄方向 |
| ridge_region_min_x_m | float | 田垄区域 X 最小 |
| ridge_region_min_y_m | float | 田垄区域 Y 最小 |
| ridge_region_max_x_m | float | 田垄区域 X 最大 |
| ridge_region_max_y_m | float | 田垄区域 Y 最大 |

## terraced 模式专属字段（梯田）

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

## 其他顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| export_heightmap | string | 导出 8 位灰度高度图 PNG 路径 |

## 所有模式通用的增强字段

| 字段 | 类型 | 说明 |
|------|------|------|
| perturbation_strength | float | 扰动强度 [0,1]，0=完美几何形状 |
| perturbation_scale | float | 扰动噪声频率 |
| perturbation_seed | int | 扰动种子（独立于 seed） |
| noise_overlay | object | 噪声叠加层 |

noise_overlay 子字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| amplitude_m | float | 叠加噪声幅度 |
| frequency | float | 频率 |
| octaves | int | 八度数 |
| seed | float | 种子 |

## features 模式子配置（C++ 解析，第二层）

features 是最强大模式，以下字段只在 features 下生效：

| 字段 | 类型 | 子字段 | 说明 |
|------|------|--------|------|
| hills[] | array | center_x_m, center_y_m, radius_m, height_m | 山丘列表 |
| valleys[] | array | center_x_m, center_y_m, radius_m, depth_m, bottom_radius_m | 山谷列表 |
| ridges[] | array | region_min_x_m, region_min_y_m, region_max_x_m, region_max_y_m, amplitude_m, frequency, direction_deg | 山脊列表 |
| blend_mode | string | — | additive/max/min/replace，特征混合模式 |
| scatter[] | array | mesh_path, count, seed, scale_min(float), scale_max(float), random_rotation | 碎石等散布物（详见下方子表） |
| water | object | level_m, material_path | 水面 |
| rivers[] | array | 见下方 rivers 子表 | 河流; C++ 两阶段处理: (1) Import 前沿路径在高度图下切 V/U 型谷(深=bed_depth_m, 余弦横截面); (2) Import 后沿中心线每~5m 分段创建 SMC 水面平面, 水面Z=min(河床底+沉入量, 较低边缘地形-15cm), 平面宽=河宽×1.2; 折点须沿自然下坡、不穿越山丘/悬崖, 否则水面可能断节或悬空. 详见下方 rivers 子表 |
| roads[] | array | points[[x,y],...], width_m, mesh_path(可选，空=引擎Plane), material_path(可选) | 道路; C++ 自动路基平整: 沿中心线横截面推向路径高度形成平整路面(余弦加权) + 路肩余弦缓过渡, 道路 ribbon 逐顶点采样地形贴合高差 |
| buildings[] | array | center[x,y], size_m[宽,深], height_m, rotation_deg, material_path(可选) | 建筑 |
| grass_varieties[] | array | 见下 | 草地变体（C++ 可能改写 LGT_Grass） |
| wheat_varieties[] | array | 见下 | 麦田变体（C++ 可能改写 LGT_Wheat） |

grass_varieties / wheat_varieties 单项格式（8 字段）：

> ⚠️ **必填提醒**：`start_cull_dist` / `end_cull_dist` 为草/麦变体必填字段。不写则 C++ 使用原始默认值 1000/3000（10m/30m），高空俯瞰时植被全部被剔除露出黑色地形。生成草/麦 JSON 时必须包含这两个字段。

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| mesh_path | string | — | 网格资产路径 |
| density | float | — | 密度（/10㎡） |
| scale_min | float | — | 最小缩放（标量，非数组） |
| scale_max | float | — | 最大缩放（标量，非数组） |
| jitter | float | — | 位置抖动 |
| random_rotation | bool | — | 随机旋转 |
| start_cull_dist | float | **必填** | 起始剔除距离（世界cm）。草/麦推荐3000(30m)：相机<30m满画质 |
| end_cull_dist | float | **必填** | 结束剔除距离（世界cm）。草推荐30000(300m)、麦推荐50000(500m)；麦穗是航拍主体需更远剔除覆盖高空视角 |

> ⚠️ **必填字段**：`start_cull_dist`/`end_cull_dist` 是草/麦变体的必填字段，生成 JSON 时不可省略。控制 UE5 foliage 系统的距离剔除。C++ 结构体 `FGrassVarietyEntry` 原始默认值为 1000/3000（10m/30m），**JSON 不写这两个字段时使用 C++ 原始默认值（10m/30m），高空俯瞰时植被全部被剔除露出下方黑色地形材质**。推荐值：草 start=3000(30m)/end=30000(300m)、麦 start=3000(30m)/end=50000(500m)，覆盖大部分航拍高度。Clamp 范围 [1, 100000]（0.01m~1000m）。

scatter 单项格式（6 字段，C++ 结构体 FScatterEntry）：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| mesh_path | string | — | 网格资产路径 |
| count | int | 0 | 实例数量 |
| seed | int | 42 | 随机种子 |
| scale_min | float | 1.0 | 最小缩放（标量，非数组） |
| scale_max | float | 1.0 | 最大缩放（标量，非数组） |
| random_rotation | bool | false | 随机旋转 |


### rivers[] 单项格式（C++ 解析，第二层）

河流每项是一个 object，含 8 个字段：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| points | [[x,y],...] | — | 河流折点坐标(米, 相对 landscape.location)。至少 2 个点。坐标在 height_pattern 坐标系(地形左上角为原点, X=东 Y=南) |
| width_m | float | — | 起点河宽(米)。建议≥1m, <0.5m 时边缘采样失效可能缝隙 |
| width_end_m | float | -1 | 终点河宽(米)。<0 时退化为固定宽=width_m(向后兼容)。支持渐变(如 2→8m 模拟下游加宽) |
| bed_depth_m | float | 0 | 河床冲刷深度(米)。0=不冲刷(仅水面 ribbon); >0 时 C++ 沿路径下切 V/U 型谷。建议≥0.5m, ≤0.3 时 WaterSinkOffset 退化为 2cm |
| profile | string | "V" | 河床横截面: "V"=余弦V型(中心最深两岸渐浅), "U"=平底+余弦边坡(flat_ratio=0.6) |
| material_path | string | "" | 水面材质路径(可选, 空=引擎默认材质)。材质需支持 FlowSpeed 标量参数控制流速动画 |
| waterfalls[] | array | [] | 瀑布列表, 每项 {t(0~1段内位置), drop_m(落差), mesh_path(可选瀑布网格)} |
| flow_speed | float | 1.0 | 流速倍数, 传入材质 FlowSpeed 参数控制 Panner 动画速度。10.0=快流, 1.0=缓流 |

**水面 Z 计算公式（C++ 自动, 不可配置）:**

```
WaterSinkOffset = (bed_depth_m > 0.3) ? bed_depth_m * 100 - 30 : 2.0   (cm)
HalfEdgeCm      = width_m * 1.2 * 0.5 * 100                              (cm, 平面半宽)
LeftEdgeZ  = GetTerrainZ(center + LeftNormal * HalfEdgeCm)
RightEdgeZ = GetTerrainZ(center - LeftNormal * HalfEdgeCm)
水面Z = min(河床底Z + WaterSinkOffset, min(LeftEdgeZ, RightEdgeZ) - 15cm)
```

- 平地时: 河床底+沉入量 < 边缘地形-15cm → 水面保持原水深
- 坡地时: 较低边缘地形-15cm 更低 → 水面压低, 封住下坡岸缝

**边界条件与可能问题:**

| 条件 | 后果 | 规避 |
|------|------|------|
| bed_depth_m = 0 | 不冲刷, WaterSinkOffset=2cm, 水面几乎贴地, 边缘检测仍工作但深度不足 | 保持 bed_depth_m ≥ 0.5m |
| bed_depth_m ≤ 0.3 | WaterSinkOffset 退化为固定 2cm, 水面仅沉入 2cm | bed_depth_m ≥ 0.5m |
| width_m < 0.5m | 平面半宽 < 0.3m, 边缘采样离中心太近, 坡地可能采不到下坡边 → 缝隙 | width_m ≥ 1m |
| 折点穿过悬崖/陡崖 | 边缘采样落在悬崖外, GetTerrainZ 返回远处地形, 水面 Z 异常(悬空或深埋) | 折点不直接穿悬崖, 或拆段+waterfall |
| U profile + 大 flat_ratio | 深水区更窄, 边缘检测灵敏度下降 | 一般无需改; 若缝隙可加 bed_depth_m 0.5m |
| width_end_m 比 width_m 小很多 | 河流逆流变窄(支流汇入场景), 正常 | 无 |
| 两河折点重叠 | 汇入处水面重叠 20cm, Opaque 材质无暗缝 | 正常设计, 无需处理 |

