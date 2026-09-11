# UE5 场景 JSON 核心知识

## 顶层结构
```
scene / landscape / ground / placements[] / lighting / weather
```

## 两层解析（关键）
- **Python 层**: scene/ground/placements/lighting/weather + landscape 基础参数 + layers[].info/weight + grass/wheat
- **C++ 层**: landscape.height_pattern + layers[].weight_pattern（json.dumps 序列化传 C++ 插件）

## 字段速查表
| 分区 | 关键字段 | 备注 |
|------|---------|------|
| scene | name, target_level, description | target_level = /Game/路径 |
| landscape | material, section_size_quads, num_subsections, component_count_x/y, location, rotation, scale | location/rotation/scale = [x,y,z] |
| landscape.layers[] | info, weight, weight_pattern | info=LayerInfo路径, weight=0~1 |
| landscape.grass | grass_type, grass_mesh, layer_name, density | density 单位 /10㎡ |
| landscape.wheat | type_path, layer_name | 需预生成 LGT_Wheat |
| landscape.height_pattern | type, blend_mode, hills[], valleys[], ridges[], water, rivers[], roads[], scatter[], grass_varieties[], wheat_varieties[], noise_overlay, perturbation_strength/scale/seed | C++ 解析 |
| ground | asset, material_override | 可为空 {} |
| placements[] | type, asset, location, grid, asset_prefix, material_override, instances | type=group/instanced_grid/instances |
| lighting | directional_light, sky_light, sky_atmosphere, height_fog | 各含 location/rotation/intensity/color |
| weather | volumetric_clouds | location |

## _note 注释规范（必须遵守）

生成的 JSON 中，**每个结构块和子块**都必须包含 `_note` 字段，写明该块的用途和**每个参数的意义**。
`_note` 是纯注释字段，build_scene.py 和校验器会自动忽略，不影响功能。

### 格式
```
"_note": "块用途简述。参数1: 含义; 参数2: 含义; ..."
```

### 必须添加 _note 的块清单
- **顶层块**: scene, landscape, ground, placements, lighting, weather, rivers
- **landscape 子块**: layers, grass, wheat, height_pattern
- **landscape.height_pattern 子块**: hills[], valleys[], ridges[], water, rivers[], roads[], scatter[], grass_varieties[], wheat_varieties[], noise_overlay
- **lighting 子块**: directional_light, sky_light, sky_atmosphere, height_fog
- **weather 子块**: volumetric_clouds, post_process
- **placements[] 每个条目**: 说明该放置组用途及 type/asset/location/grid 参数意义

### 示例
```json
"scene": {
    "_note": "场景元信息。name: 场景名称; target_level: UE5关卡路径,格式/Game/Maps/路径; description: 场景用途描述",
    "name": "雪山基地",
    "target_level": "/Game/Maps/SnowBase"
},
"lighting": {
    "_note": "灯光配置块。directional_light: 主光源(太阳); sky_light: 环境光; sky_atmosphere: 大气散射; height_fog: 高度雾",
    "directional_light": {
        "_note": "主平行光(太阳)。rotation: [pitch,yaw,roll]旋转角度; intensity: 亮度(lux); color: RGB[0~1]; cast_shadows: 是否投射阴影",
        "rotation": [-45, 35, 0],
        "intensity": 10.0,
        "color": [1.0, 0.94, 0.78],
        "cast_shadows": true
    }
}
```

### 注意
- `_note` 必须详细列出该块所有参数的意义，不能只写块名
- placements[] 数组中可插入纯注释条目 `{"_note": "=== 灯光区 ==="}` 作为分节标注
- 数组元素(如 layers[], hills[])的每个元素也应有 `_note`

## 关键约束
1. weight 范围: layers[].weight 应为 0~1 浮点数
2. 路径格式: UE 资产路径 /Game/类别/Name，不含 .uasset 后缀
3. 单位混淆: location/spacing 单位=厘米(cm)，height_pattern 内 center_x_m/radius_m 等单位=米(m)
4. placements type: group 用 asset_prefix；instanced_grid 用 grid{}；instances 用 instances[]
5. height_pattern/weight_pattern 字段名不可拼错（C++ 层不报错但功能失效）
6. **每个结构块和子块必须包含 `_note` 注释字段，写明块用途和每个参数的意义**
7. **植被类 placement 必须贴地**: 凡是 asset 路径包含 Tree/Pine/Grass/Plant/Flower/Bush/Foliage/Crop/Wheat 等植被关键词的 placement（instanced_grid/crop_field/instances/grid/static 均适用），**必须**在 grid/field 中添加 `"snap_to_ground": true`。否则树木会埋入山体内部而非贴着地表生长。示例:
   ```json
   {"type": "instanced_grid", "asset": "/Game/.../SM_Pine_Tree_04",
    "grid": {"rows": 5, "cols": 10, "origin": [0, 0, 0], "spacing": [600, 600, 0],
             "snap_to_ground": true, "cull_start": 20000, "cull_end": 50000}}
   ```