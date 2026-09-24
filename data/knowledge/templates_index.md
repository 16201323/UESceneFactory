# 完整场景模板（文件存档）

本节关联若干已验证的完整场景 JSON 模板文件，存放于本技能目录下 `templates/` 子文件夹。需要时直接读取对应文件作为起点，修改 `target_level`/`location`/`scale` 等字段即可派生新场景，避免在文档中内联完整 JSON 以减少 token 消耗。

## 模板 P1 — 直升机停机坪

- 文件：`templates/template_p1_heliport.json`
- 资产前缀：`/Game/heliport/heliport_helipad_air_base_helicopter/StaticMeshes/Object_`（group 10 个 Object）
- 关键开关：`rotation [0,0,-90]` + `scale [0.01,0.01,0.01]` + `skip_z_fix: true` + `scale_before_rotation: true`
- 地面：`SM_House_FloorPlane_03` scale `[10,20,1]`
- 详细规则见 references/placements.md 同类配置说明

## 模板 P8 — 高压电塔（双塔电线相向）

- 文件：`templates/template_p8_hv_tower.json`
- 资产前缀：`/Game/HighVoltageTower/high_voltage_tower_wired/StaticMeshes/Object_`（每塔 20 个 Object）
- Tower A：`location [0,1420,0]` `rotation [0,0,-90]`
- Tower B：`location [0,1500,0]` `rotation [0,180,-90]`（yaw+180°使电线相向）
- 公共开关：`scale [0.01,0.01,0.01]` + `skip_z_fix: true` + `ground_assembly: true`
- 两塔 Y 间距 80cm（scale 0.01 下经验值），电线相向连接规则详见 references/placements.md

## 模板 P2 — 方形铁丝网围栏

- 文件：`templates/template_p2_square_fence.json`
- 生成脚本：`MapForgeTest/gen_square_fence.py`（改参数后重新生成 JSON）
- 资产：`/Game/WireFence/chainlink_fence_tileable/StaticMeshes/Plane_004_chainlink_fence_textures_0`
- 面板尺寸：203.7(X) × 22.6(Y) × 236.4(Z) cm，原点在中心，Z=111 贴地

**布局参数（gen_square_fence.py 顶部常量）：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| CENTER | [0,0,0] | 围栏中心点 |
| LENGTH | 10000 | X 方向长度（cm） |
| WIDTH | 5000 | Y 方向宽度（cm） |
| SPACING | 200.0 | 面板间距（cm，面板长 203.7cm，重叠 1.8% 保证无缝） |
| PANEL_Z_OFFSET | 111 | Z 偏移（面板原点中心，111cm 贴地） |

**弯折方向规则（实测验证，最关键用法）：**

铁丝网面板顶部有弯折，弯折必须朝围栏外侧。yaw 与弯折方向对应关系：

| yaw | 弯折方向 |
|-----|----------|
| 0 | +Y |
| 90 | -X |
| 180 | -Y |
| 270 | +X |

四边 yaw 取值（弯折朝外）：

| 边 | 位置 | yaw |
|----|------|-----|
| 南 | Y = -WIDTH/2 | 180 |
| 北 | Y = +WIDTH/2 | 0 |
| 西 | X = -LENGTH/2 | 90 |
| 东 | X = +LENGTH/2 | 270 |

**实例数量公式：**
- 长边每条：n_long = ceil(LENGTH / SPACING) = 50
- 短边每条：n_short = ceil(WIDTH / SPACING) = 25
- 总数：n_long × 2 + n_short × 2 = 150

**关键实现：使用 `instances` 显式数组而非 `grid` 模式**
build_scene.py 的 grid 模式无法为每条边设置固定 yaw（只能 0 或随机），必须用 `instances` 显式数组逐个列出每个面板的 location/rotation/scale。

## 模板 P5 — 太阳能光伏板

- 文件：`templates/template_p5_pv_solar.json`
- 资产目录：`/Game/Photovoltaic/-photovoltaic_panels/StaticMeshes/Material*`
- 资产特点：非序列命名（Material2、Material3、Material21~29、Material31~32、Material210~226），共30个，其中6个空几何体

**group 加载全部（核心用法）：**

`asset_prefix` 设为 `/Game/Photovoltaic/-photovoltaic_panels/StaticMeshes/Material`，`count=227`，build_scene.py 生成 Material0~Material226 共227个候选路径，对不存在的资产自动 GROUP_SKIP 跳过（197个），实际加载30个。

| 参数 | 值 | 说明 |
|------|-----|------|
| type | group | 多部件同坐标组装 |
| asset_prefix | .../Material | 路径前缀，生成 prefix+str(k) |
| count | 227 | 覆盖最大编号 Material226 |
| scale | [0.01,0.01,0.01] | 缩到1%（如 Material3: 411m→4.1m） |
| rotation | [0,0,-90] | roll -90°（滚动-90度） |
| skip_z_fix | true | 跳过单部件Z修正（原点类型混用） |
| ground_assembly | true | 整组生成后统计最低Z平移贴地 |

**非序列命名资产处理要点：**

group 类型按 `prefix + str(k)` 顺序生成路径，k 从0到 count-1。当资产编号不连续时（如本例 Material4~20 不存在），不存在的会被 `load_asset` 返回 None 而 GROUP_SKIP 跳过，不影响存在的资产加载。`count` 需设为"最大编号+1"以覆盖全部。

**地面配置：**

`SM_House_FloorPlane_03`（基础 9.69m×5m），scale [10,10,1] = 97m×50m 草地平面，足够容纳缩到1%的光伏阵列。

**注意事项：**
- 30个资产全部堆叠在原点 [0,0,0]，尺寸差异大（Material2 缩放后仅2.7cm，Material3 达4.1m），可能互相穿插
- 6个空几何体资产（Material210/211/212/217/28/29）加载成功但不可见
- roll -90 对"mixed"朝向资产的效果需在编辑器中实测确认

## 模板 P7 — 通信塔（双塔真实标准缩放）

- 文件：`templates/template_p7_comm_tower.json`
- 资产：电信塔 `/Game/CommunicationTower/telecommunication_tower_low-poly_free/StaticMeshes/Object_`（group 6 个）+ 科幻塔 `/Game/CommunicationTower/sci-fi_communication_tower/StaticMeshes/Object_`（group 10 个）
- 真实标准缩放（核心）：按真实世界通信塔高度区间设定 scale，而非统一 1.0

| 塔 | 资产 | 基础最高 | scale | 实际高度 | 对标标准 |
|----|------|---------|-------|---------|---------|
| 左·电信塔 | telecom(6部件) | 2058cm(20.6m) | 1.2 | 24.7m | 城市宏基站15-30m |
| 右·科幻塔 | sci-fi(10部件) | 280cm(2.8m) | 3.0 | 8.4m | 小型基站4-15m |

- 公共开关：`skip_z_fix: true` + `ground_assembly: true`（组合内原点混合需跳过单件Z修正，改用整组包围盒贴地）
- 地面：`SM_House_FloorPlane_03` scale `[10,20,1]` = 97m×100m，两塔 ±2000cm(±20m)间距40m
- 碰撞：两塔均已 ✓完整碰撞；科幻塔 Object_1 单位异常（米制DCC未转换，scale 3.0 后约0.4m仍偏小，如需精确可单独再 ×100）

## 模板 P10 — 密集森林（HISM 每实例距离剔除）

- 文件：`templates/template_p10_forest.json`
- 资产：11 种杉树（4 大型 SM_FirTree_01/02/03/Dead_01 + 7 小型 SM_SmallFir_01~05/Dead_01/Dead_02），全部 `instanced_grid` HISM
- 布局：上层 4 种各 5×5=25 棵（间距 1500cm/15m，四象限）+ 下层 7 种各 3×3=9 棵（间距 600cm/6m，中心区），共 163 棵
- 地面：`SM_House_FloorPlane_03` scale `[20,40,1]` = 194m×200m 草地

**距离剔除（省资源核心）：**
所有 11 个 grid 均设 `"cull_start": 20000, "cull_end": 50000`（200m~500m，300m 渐隐带），>500m 实例不渲染（GPU 不画）。对应 HISM 的 `InstanceStartCullDistance`/`InstanceEndCullDistance`。

| cull 区间 | 行为 |
|-----------|------|
| < 200m（start） | 完全可见，满画质 |
| 200m~500m | 渐隐过渡 |
| > 500m（end） | 不渲染（GPU 不画） |

**关键点：**
1. **仅 `instanced_grid` 生效**：cull 是 HISM 独有属性，`static` grid 不支持
2. **两值同时给**：cull_start/cull_end 必须同时出现才生效，缺省则不剔除（向后兼容）
3. **值单位为世界厘米**：20000=200m
4. **HISM 合批 + 距离剔除双重省资源**：同类网格合并 1 draw call + 远处不画

## 模板 P11 — 全地形综合场景（地形+资产单 JSON 一体化，推荐起点）

- 文件：`templates/template_p11_all_terrain_realistic.json`
- 产出：`GB_RealisticAllTerrain.umap`（1km×1km 已验证），**地形与资产放置写在同一份 JSON 中一次转换成 umap**，是新场景的首选起点
- 地形规格：`component_count 16×16, section_size_quads 63, scale 100` → 1008m×1008m，`location [-50400,-50400,0]` 使坐标原点在地形中心（features 坐标以米、原点在地形左上角计，模板内注释已换算）

**场景构成（features 模式 blend_mode=additive）：**

| 元素 | 配置 | 说明 |
|------|------|------|
| 基础穹隆 | hills 中心(504,504) r950 h20m | 全图抬至约 20m，陆地露出水面 |
| 雪山主峰/副峰 | h130m / h80m + Layer3 snow_line(75m) | 海拔>75m 且坡度<0.8 处积雪 |
| 湖盆 | valleys d35m br120 + water level 5m | 440m 直径冰川湖 |
| 河流×2 | rivers 宽 12m/8m，折点从山麓入湖 | C++ 自动河床冲刷下切（U 型谷，深 150cm）+ ribbon 水面沉入河谷 -30cm |
| 道路×3 | roads 宽 4m/3m/3m | C++ 自动路基平整（余弦横截面 + 路肩过渡） |
| 麦田 | Layer6 multi_region 60×40m + wheat_varieties | 需先运行 `gen_2km_scene.py` 生成 `/Game/Generated/LGT_Wheat` 与 `LIS_Wheat`，否则 C++ 仅 Warning 跳过 |
| 草地 | Layer4 height_based(6~20m + fade 40~60m) + 10 种草 | `corridor_exclude: true` → 河/路走廊(宽×1.25)内权重清零 |
| 森林 | placements 4 个 instanced_grid 共 148 棵杉树 | cull_start 20000 / cull_end 50000，Z=2000 |
| 散布岩石 | scatter 5 种共 180 块 | scale 0.7~4.0，随机旋转 |

**关键真实性参数（本模板核心价值，勿删）：**

| 参数 | 值 | 作用 |
|------|-----|------|
| `corridor_exclude` | true（Layer4 weight_pattern 内） | 河流/道路走廊内草权重清零，消除"贴图感" |
| 河床冲刷/路基平整 | C++ 端自动（依据 rivers/roads 自动执行） | 河流 U 型下切、道路横截面平整，水面沉入河谷 |
| `noise_overlay` | amp5 freq0.006 oct5 | 多倍频 Perlin 消除人工平整感 |
| `perturbation_strength` | 0.35 | 扭曲等高线，消除几何痕迹 |
| 河流路径设计 | 折点沿自然下坡、不穿越山丘 | 保证 C++ 细分贴合后水面连续不断节 |

**派生方法：** 复制本模板后，改 `scene.name`/`target_level`，按需增删 hills/valleys/rivers/roads/layers/placements。地形与资产放置继续写在这同一份 JSON 中，一次 `build_scene.py` 全部转换成 umap。

## 模板 P12 — 梯田地形（terraced 模式）

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


## 模板 P15 — 水系场景（河流+支流汇入，features 模式）

- 文件：`templates/template_p15_water_river.json`
- 模式：`height_pattern.type = "features"`
- 地形规格：`component_count 4×4, section_size_quads 63, num_subsections 2, scale 100` → 504m×504m
- 场景：2 条河流(主河+支流汇入)，无山丘无瀑布，纯水系最小配置

**河流参数详解:**

| 参数 | 主河值 | 支流值 | 说明 |
|------|--------|--------|------|
| points | 3 折点(50,450→450,200) | 3 折点(450,450→250,350) | 河流折点(米), 至少 2 个点, 坐标在地形范围内, 须沿自然下坡 |
| width_m | 3 | 1.5 | 起点河宽(米), 建议≥1m |
| width_end_m | 8 | 3 | 终点河宽(米), 模拟下游加宽; <0 时退化为固定宽=width_m |
| bed_depth_m | 2.0 | 1.5 | 河床冲刷深度(米), ≥0.5m 保证水深; 0=不冲刷仅水面 |
| profile | "V" | "V" | 横截面: "V"=余弦V型(中心深), "U"=平底+边坡 |
| material_path | Water_Lake | Water_Lake | 水面材质, 需支持 FlowSpeed 标量参数 |
| flow_speed | 10.0 | 10.0 | 流速倍数, 10=快流 1=缓流; 传入材质 FlowSpeed 参数 |
| waterfalls | (省略) | (省略) | 可选, 瀑布列表 [{t(0~1), drop_m, mesh_path(可选)}]; 不写=无瀑布 |

**水面生成算法(C++ 自动, 不可配置):**

1. 沿中心线每~5m 采样, 记录该点河宽
2. 采样三处地形Z: 中心线(河床底) + 左右边缘(边缘=河宽×0.6)
3. 水面Z = min(河床底+沉入量, 较低边缘-15cm) → 平地保持水深, 坡地压低封缝
4. 每相邻采样点创建 SMC 水面段, 宽=河宽×1.2, 沿坡度加 Pitch
5. 相邻段重叠 20cm 封闭弯道接缝

**边界条件与可能问题:**

| 条件 | 后果 | 规避 |
|------|------|------|
| bed_depth_m = 0 | 不冲刷, 水面贴地, 深度不足 | ≥0.5m |
| bed_depth_m ≤ 0.3 | 沉入量退化为固定 2cm | ≥0.5m |
| width_m < 0.5m | 边缘采样失效, 坡地可能缝隙 | ≥1m |
| 折点穿悬崖/陡崖 | 水面 Z 异常(悬空/深埋) | 不穿悬崖, 或拆段+waterfall |
| 折点不沿下坡 | 水面可能逆流断节 | 折点 Z 递减(沿自然下坡) |
| 河流穿越山丘 | 水面可能穿山或断节 | 折点避开山丘区域 |

**派生方法:** 复制模板后改 `target_level`, 增删 rivers 条目, 调 width/bed_depth/points。加新河在 rivers[] 追加 object。加瀑布追加 waterfalls[{t, drop_m}]。改 flow_speed 控制流速。加山丘在 height_pattern 追加 hills[]。无需重新编译 DLL(纯 JSON 参数)。

## 模板 P16 — 房屋村落（多类型 village/blueprint placement 组合）

- 文件：`templates/template_p16_village.json`
- 场景：8 个区域、4 个风格象限的房屋村落，含 2 类原有房屋（village cluster/scatter + blueprint）+ 10 个 Fab 静态网格房屋按真实世界尺寸分布
- 地形：`component_count 4x4, section_size_quads 63, num_subsections 2, scale 100` -> 504m x 504m，hills 单中心隆起 20m

**核心 placement 类型：**

| type | 用途 | 关键参数 |
|------|------|----------|
| village | 房屋聚集/散布 | house_assets, house_count, layout(scatter/cluster), radius_m, min_distance_m, seed, snap_to_ground, scale_min/max |
| blueprint | 蓝图Actor房屋 | asset, location, rotation, scale, snap_to_ground |

**派生方法：** 复制模板后改 target_level，增删 village placement，替换 house_assets 路径。资产缩放值参考搜索结果中的 `recommended_scale` 字段（已在资产清单中人工标注）。

## 派生要点

复制模板后通常只需改：`target_level`、`location`、`scale`、`ground.location/scale`。三个开关 `skip_z_fix`/`scale_before_rotation`/`ground_assembly` 必须保持一致，否则会出现部件错位/塔身躺倒/悬浮。改 scale 时双塔间距需等比调整（≈ scale × 8000cm）。