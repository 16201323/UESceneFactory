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

## 单位检测与缩放调整

清单中标注了每个网格的尺寸单位：
- **米（m）**：网格尺寸已以米为单位
- **厘米（cm）**：UE5 内部单位为厘米，清单标注厘米时网格在引擎中已正确显示

注意 `scale_min`/`scale_max` 的两种不同格式：
- **scatter / grass_varieties / wheat_varieties**：标量 `float`（如 `1.0`）
- **placements（instanced_grid / static grid）**：数组 `[x,y,z]`（如 `[1,1,1]`）

## 查阅流程

1. 确定 JSON 中需要填写的资产路径字段
2. 打开 `asset_catalog.md`，按类别检索合适的资产
3. 复制资产路径填入 JSON
4. 检查尺寸单位，必要时调整 scale 参数
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

> ⚠️ **房屋 Z 偏移特殊（必读）**：该资产原点被特殊抬高 +180cm，放置时 **必须** 在 `location` 第三位写 `-180` 手动补偿，使房屋底部贴地。配置 `skip_z_fix: true`（部件原点混合 center/bottom/top）。**不可用 `ground_assembly: true`**——会与手动 -180 叠加导致房屋陷入地下。完整示例：`{"type":"group","asset_prefix":"...Object_","count":149,"location":[x,y,-180],"rotation":[0,0,0],"scale":[1,1,1],"skip_z_fix":true}`

> 以上路径来自 `all_terrain_1km.json`（已成功生成 `GB_AllTerrain_1km.umap`）。如需其他资产，查阅完整清单并按上文"路径转换规则"转换路径。