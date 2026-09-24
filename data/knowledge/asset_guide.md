# 资产清单查阅（编写 JSON 前必读）

> 本文件是 UE5_JSON 技能的按需参考文档（由 SKILL.md 第 7 节拆分）。仅在填写 mesh_path/material_path/asset/info 等资产路径字段时读取。

编写 JSON 时，所有 `mesh_path`、`material_path`、`asset`、`info`、`grass_type`、`grass_mesh` 等字段都需要填写 UE5 资产路径。在填写前，应先查阅资产清单确认路径有效、单位正确。

## 资产清单位置

资产清单文件：`MapForgeTest/asset_catalog.md`（由 `asset_audit.py` 自动生成，约 1.3MB，含 7612 个资产）。

## 资产清单内容

清单按类别分组：

| 类别 | 数量 | 说明 |
|------|------|------|
| vegetation_tree | 207 | 树木网格（松树、杨树等） |
| building | 1121 | 建筑网格（住宅、工厂等） |
| material | 1904 | 材质实例常量 |
| solar_panel | 225 | 太阳能板 |
| communication_tower | 129 | 通信塔 |
| vegetation_crop | 86 | 作物网格（麦田等） |
| heliport | 45 | 直升机停机坪 |
| high_voltage_tower | 26 | 高压电塔 |
| fence | 13 | 围栏 |
| ground | 12 | 地面贴图/材质（非网格，含 Ground003 纹理系列） |
| blueprint | 1 | 蓝图 |

每个资产条目包含：
- **资产路径**：相对路径格式 `类别路径/AssetName.AssetName`（需转换为 JSON 路径，见下文"路径转换规则"）
- **尺寸**：网格 Bounding Box 尺寸，标注单位（米/厘米）
- **朝向**：网格默认朝向
- **原点**：网格 pivot 位置
- **Z 偏移建议**：放置时推荐的 Z 轴偏移（避免浮空或埋地）
- **材质**：网格引用的材质列表

## 在 JSON 中的使用场景

| JSON 字段 | 所属区域 | 需要的资产类型 |
|-----------|----------|----------------|
| mesh_path | height_pattern.scatter[] | 静态网格（碎石、岩石） |
| mesh_path | height_pattern.grass_varieties[] | 草地网格 |
| mesh_path | height_pattern.wheat_varieties[] | 作物网格 |
| material_path | height_pattern.roads[] | 道路材质 |
| material_path | height_pattern.rivers[] | 水面材质 |
| material_path | height_pattern.buildings[] | 建筑材质 |
| material_path | height_pattern.water | 水面材质 |
| info | landscape.layers[] | LayerInfo 资产 |
| grass_type | landscape.grass | GrassType 资产 |
| grass_mesh | landscape.grass | 草地网格 |
| asset | placements[] | 任意静态网格/蓝图 |
| material_override | ground / placements[] | 材质实例 |

## 资产缩放

资产搜索结果中的 `recommended_scale` 字段（默认 1.0）是人工标注的建议缩放值：
- **1.0**：资产尺寸正常，无需缩放
- **其他值**（如 0.001）：资产原始尺寸异常，需在 JSON 的 `scale` 字段使用此值

注意 `scale_min`/`scale_max` 的两种不同格式：
- **scatter / grass_varieties / wheat_varieties**：标量 `float`（如 `1.0`）
- **placements（instanced_grid / static grid）**：数组 `[x,y,z]`（如 `[1,1,1]`）

## 查阅流程

1. 确定 JSON 中需要填写的资产路径字段
2. 打开 `asset_catalog.md`，按类别检索合适的资产
3. 复制资产路径填入 JSON
4. 参考搜索结果中的 recommended_scale（若≠1.0），填入 JSON 的 scale 字段
5. 参考 Z 偏移建议，设置 placement 的 location 或 z_offset
6. 按下方"路径转换规则"，将清单路径转换为 JSON 路径格式

## 路径转换规则（清单路径→JSON 路径）

资产清单中的路径格式与 JSON 中填写的路径格式不同，需转换：

| | 格式 | 示例 |
|--|------|------|
| 清单路径 | `相对路径/AssetName.AssetName` | `Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a.SM_Grass_Tall_Wild_01a` |
| JSON 路径 | `/Game/相对路径/AssetName` | `/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a` |

**转换步骤**：
1. 取清单路径中 `.` 之前的部分（去掉 `.AssetName` 后缀）
2. 在前面加上 `/Game/`

**build_scene.py 容错**：build_scene.py 先用 JSON 中的短路径加载，失败时自动补 `.AssetName` 后缀重试（见 build_scene.py 第 847-853 行）。因此两种写法均可用，但推荐写短路径（无后缀）。

## 放置条目 asset 字段规则（重要）

- static/instanced_grid/blueprint/crop_field 类型：asset 必须是非空的 /Game/ 路径
- group 类型：用 asset_prefix 代替 asset，asset_prefix 也必须非空
- 如果 search_assets 未找到匹配资产，不要生成该放置条目（宁可省略也不要留空）
- 严禁输出 asset 为空字符串的占位条目，空 asset 会导致 UE 编辑器卡死

## 村落房屋数量规则（重要）

- placements 含 village 时，必须配置 5~15 栋房屋，绝不能只放 1-2 栋
- 房屋组合资产(asset_prefix 类型 group)配置 count≥5 或使用 instanced_grid rows×cols≥6
- 房屋必须配置 snap_to_ground=true 和 skip_z_fix=true(多部件组合)

## 验证可用路径速查（已在项目中验证可用）

以下路径在 `all_terrain_1km.json` 中已实际验证可用，可直接复制使用：

**材质**：

| JSON 字段 | 路径 | 用途 |
|-----------|------|------|
| landscape.material | `/Game/RuralHouse/Landscape/MI_Landscape` | 地形主材质 |
| water.material_path | `/Game/Modular_Rural_Cabin/Materials/Instances/Water_Lake` | 水面材质 |
| roads[].material_path | `/Game/MapForgeTest/M_Road_Dirt` | 道路材质 |

**LayerInfo（5 层）**：

| 路径 | 对应图层 |
|------|----------|
| `/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo` | TrailSoil 基底 |
| `/Game/RuralHouse/Landscape/LandscapeLayers/Layer2_LayerInfo` | Mud 泥地 |
| `/Game/RuralHouse/Landscape/LandscapeLayers/Layer3_LayerInfo` | ForestGround 雪线 |
| `/Game/RuralHouse/Landscape/LandscapeLayers/Layer4_LayerInfo` | Grass 草地 |
| `/Game/RuralHouse/Landscape/LandscapeLayers/Layer5_LayerInfo` | Gravel 碎石 |

**草地系统**：

| JSON 字段 | 路径 | 说明 |
|-----------|------|------|
| grass.grass_type | `/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass` | GrassType 资产 |
| grass.grass_mesh | `/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a` | 主草地网格 |
| grass_varieties[].mesh_path | `/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a` 等 5 种 | 高草（01a~01e） |
| grass_varieties[].mesh_path | `/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Beach_01a` 等 5 种 | 矮草（01a~01e） |

**散布岩石（scatter）**：

| JSON 字段 | 路径 | 说明 |
|-----------|------|------|
| scatter[].mesh_path | `/Game/RuralHouse/Environment/Ground/SM_Rock_A_01` | 岩石 A-01 |
| scatter[].mesh_path | `/Game/RuralHouse/Environment/Ground/SM_Rock_A_04` | 岩石 A-04 |
| scatter[].mesh_path | `/Game/RuralHouse/Environment/Ground/SM_Rock_A_05` | 岩石 A-05 |
| scatter[].mesh_path | `/Game/RuralHouse/Environment/Ground/SM_Rock_A_07` | 岩石 A-07 |
| scatter[].mesh_path | `/Game/RuralHouse/Environment/Ground/SM_MossyRock_01` | 苔藓岩石 |

**建筑/房屋**：

| JSON 字段 | 路径 | 说明 |
|-----------|------|------|
| placements[].asset_prefix | `/Game/hourse/Imported/rural_brick_house_with_barn_and_chicken_coop/rural_brick_house_with_barn_and_chicken_coop/StaticMeshes/Object_` | 砖房+谷仓+鸡舍组合（73 部件，Object_4~148 偶数，count=149） |
| placements[].asset (type=instanced_grid) | `/Game/Modular_Rural_Cabin/Meshes/Props/Outhouse_House` | 单体农舍（木屋，已验证，template_p16 使用） |
| placements[].asset (type=blueprint) | `/Game/hourse/Blueprints/BP_House_RuralBrickFarm` | 蓝图砖房农舍（已验证，template_p16 使用） |
| placements[].asset (type=blueprint) | `/Game/hourse/Blueprints/BP_House_Traditional` | 蓝图传统屋（已验证，template_p16 使用） |
| placements[].asset (type=instanced_grid) | `/Game/RuralHouse/House/Meshes/ModularParts/SM_House_Base_300CM` | 模块化建筑基础件 300cm（已验证） |

> ⚠️ **房屋放置规则（必读）**：房屋资产无需手动Z偏移，直接用 `snap_to_ground: true` 贴地即可。若房屋为多部件组合（`type: group`），需配置 `skip_z_fix: true` 防止Z-fix压平组装。完整示例：`{"type":"group","asset_prefix":"...Object_","count":149,"location":[x,y,0],"rotation":[0,0,0],"scale":[1,1,1],"skip_z_fix":true,"snap_to_ground":true}`

> ⚠️ **路径格式注意（v2.9.8更新）**：`search_assets` 工具返回的路径含 `.ObjectName` 后缀（UE 长路径格式，如 `SM_House_Base_300CM.SM_House_Base_300CM`）。填入 JSON 时可保留后缀（校验器已兼容），也可去掉后缀只保留包路径。蓝图路径必须配 `type: "blueprint"`。单体农舍示例：`{"type":"instanced_grid","asset":"/Game/Modular_Rural_Cabin/Meshes/Props/Outhouse_House","location":[0,0,0],"grid":{"rows":2,"cols":2,"origin":[0,0,0],"spacing":[6000,6000,0],"random_yaw":true,"scale_min":[1.5,1.5,1.5],"scale_max":[2.2,2.2,2.2]}}`

**树木/植被**：

| JSON 字段 | 路径 | 说明 |
|-----------|------|------|
| placements[].asset (instanced_grid) | `/Game/RuralHouse/Environment/Trees/SM_FirTree_01` | 杉树 01（高~31m） |
| placements[].asset (instanced_grid) | `/Game/RuralHouse/Environment/Trees/SM_FirTree_02` | 杉树 02（高~36m） |
| placements[].asset (instanced_grid) | `/Game/RuralHouse/Environment/Trees/SM_FirTree_03` | 杉树 03（高~34m） |
| placements[].asset (instanced_grid) | `/Game/RuralHouse/Environment/Trees/SM_FirTreeDead_01` | 枯杉树 01（高~38m） |

> ⚠️ **树木材质规则（必读·v2.9.7更新）**：树木 placement **不要**配置 `material_override` 字段，让树木使用原生材质即可。
> 
> **历史问题**：此前推荐使用 `M_Tree_Static` 静态材质禁用风动（WPO），但该方案存在两个缺陷：
> 1. **白色枝干**：`M_Tree_Static` 复制自树枝材质但不保留 Alpha 通道，覆盖后叶面透明度丢失 → 枝干变白
> 2. **连根移动**：旧版 `set_material(0, mat)` 只覆盖 slot 0（树枝），slot 1（树皮）保留原生 WPO → 树干根部摇摆
> 
> **v2.9.7 修复**：`build_scene.py` 已改为遍历所有材质槽（`get_num_materials`），`material_override` 会覆盖全部槽位。但 `M_Tree_Static` 仍会破坏 Alpha 导致白色枝干，因此已弃用。
> 
> **当前方案**：不使用 `material_override`，树木使用原生材质。原生材质的 WPO 风动通过顶点色遮罩控制——树根处权重为 0（不动）、树梢处权重为 1（摆动），呈现自然风动效果，不会出现连根移动。
> 
> 完整示例：`{"type":"instanced_grid","asset":"/Game/RuralHouse/Environment/Trees/SM_FirTree_01","location":[0,0,0],"grid":{"rows":5,"cols":5,"origin":[0,0,0],"spacing":[1800,1800,0],"jitter":400,"random_yaw":true,"scale_min":[0.8,0.8,0.8],"scale_max":[1.3,1.3,1.3]}}`

> 以上路径来自 `all_terrain_1km.json`（已成功生成 `GB_AllTerrain_1km.umap`）。如需其他资产，查阅完整清单并按上文"路径转换规则"转换路径。