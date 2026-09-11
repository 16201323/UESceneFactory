# 示例 JSON 片段

> 本文件是 UE5_JSON 技能的按需参考文档（由 SKILL.md "示例 JSON 片段"拆分）。需要可复制的完整示例时读取。
> **注意**: 每个结构块和子块都包含 `_note` 注释字段，说明块用途和每个参数的意义。生成 JSON 时必须遵守此注释规范。

最小可用场景（1km 草地+两山丘雪顶+两麦田）：

```json
{
  "scene": {
    "_note": "场景元信息。name: 场景名称(字符串); target_level: UE5关卡路径,格式/Game/Maps/路径; description: 场景用途描述",
    "name": "TwoHillsWheat_1km",
    "target_level": "/Game/Maps/Generated/TwoHillsWheat_1km"
  },
  "landscape": {
    "_note": "地形配置块。material: 地形材质路径; section_size_quads: 每section四边形数(127=标准); num_subsections: 子section数; component_count_x/y: 组件网格数(决定地形大小); location: 世界坐标[xyz]厘米; rotation: 旋转[pitch,yaw,roll]; scale: 缩放[xyz]; layers: 图层列表; grass: 草地配置; wheat: 麦田配置; height_pattern: 高度模式(C++解析)",
    "material": "/Game/Materials/MI_Landscape",
    "section_size_quads": 127,
    "num_subsections": 1,
    "component_count_x": 8,
    "component_count_y": 8,
    "scale": [100, 100, 100],
    "layers": [
      {
        "_note": "雪层。info: LayerInfo资产路径,控制材质混合; weight: 基础权重0~1(0=不显示); weight_pattern: 权重分布模式(C++解析)",
        "info": "/Game/Layers/LI_Snow",
        "weight": 0.0,
        "weight_pattern": {
          "_note": "雪线模式。pattern: 模式名; snow_line_m: 雪线高度(米); transition_m: 过渡带宽(米); max_slope: 最大坡度阈值0~1",
          "pattern": "snow_line",
          "snow_line_m": 55,
          "transition_m": 5,
          "max_slope": 0.9
        }
      },
      {
        "_note": "岩石层。info: LayerInfo路径; weight: 基础权重0~1; weight_pattern: 坡度分布模式",
        "info": "/Game/Layers/LI_Rock",
        "weight": 0.0,
        "weight_pattern": {
          "_note": "坡度模式。pattern: 模式名; slope_min: 最小坡度0~1; slope_max: 最大坡度0~1; invert: 是否反转(反转=缓坡显示)",
          "pattern": "slope_based",
          "slope_min": 0.2,
          "slope_max": 0.5,
          "invert": false
        }
      },
      {
        "_note": "草地层。info: LayerInfo路径; weight: 基础权重0.5; weight_pattern: 噪声分布模式",
        "info": "/Game/Layers/LI_Grass",
        "weight": 0.5,
        "weight_pattern": {
          "_note": "噪声模式。pattern: 模式名; noise_frequency: 噪声频率; noise_seed: 随机种子; noise_octaves: 八度数; invert: 是否反转",
          "pattern": "noise_based",
          "noise_frequency": 0.01,
          "noise_seed": 1,
          "noise_octaves": 3,
          "invert": false
        }
      },
      {
        "_note": "麦田层。info: LayerInfo路径; weight: 基础权重0; weight_pattern: 多区域分布模式",
        "info": "/Game/Layers/LI_Wheat",
        "weight": 0.0,
        "weight_pattern": {
          "_note": "多区域模式。pattern: 模式名; regions: 区域列表,每个区域含min_x/min_y/max_x/max_y坐标(米)",
          "pattern": "multi_region",
          "regions": [
            {"_note": "麦田区域1,坐标范围450~500,150~200(米)", "min_x": 450, "min_y": 150, "max_x": 500, "max_y": 200},
            {"_note": "麦田区域2,坐标范围150~200,450~500(米)", "min_x": 150, "min_y": 450, "max_x": 200, "max_y": 500}
          ]
        }
      }
    ],
    "grass": {
      "_note": "草地配置。grass_type: 草类型资产路径(LGT_); grass_mesh: 草网格路径; layer_name: 关联图层名; density: 密度(单位/10㎡)",
      "grass_type": "/Game/Grass/LGT_Grass",
      "grass_mesh": "/Game/Meshes/SM_GrassPlane",
      "layer_name": "Grass",
      "density": 200.0
    },
    "wheat": {
      "_note": "麦田配置。type_path: 麦田类型资产路径(需预生成LGT_Wheat); layer_name: 关联图层名",
      "type_path": "/Game/Grass/LGT_Wheat",
      "layer_name": "Wheat"
    },
    "height_pattern": {
      "_note": "高度模式(C++解析)。type: 模式类型(features=特征地形); hills: 山丘列表; noise_overlay: 全局噪声叠加; grass_varieties: 草网格变体; wheat_varieties: 麦网格变体",
      "type": "features",
      "hills": [
        {"_note": "山丘1。center_x_m/center_y_m: 中心坐标(米); radius_m: 半径(米); height_m: 高度(米)", "center_x_m": 250, "center_y_m": 250, "radius_m": 150, "height_m": 80},
        {"_note": "山丘2。center_x_m/center_y_m: 中心坐标(米); radius_m: 半径(米); height_m: 高度(米)", "center_x_m": 750, "center_y_m": 750, "radius_m": 150, "height_m": 80}
      ],
      "noise_overlay": {
        "_note": "全局噪声叠加。amplitude_m: 振幅(米); frequency: 频率; octaves: 八度数; seed: 随机种子",
        "amplitude_m": 2,
        "frequency": 0.01,
        "octaves": 3,
        "seed": 1
      },
      "grass_varieties": [
        {
          "_note": "草网格变体。mesh_path: 网格路径; density: 密度; scale_min/scale_max: 缩放范围; jitter: 位置抖动; random_rotation: 随机旋转; start_cull_dist/end_cull_dist: LOD剔除距离(厘米)",
          "mesh_path": "/Game/Meshes/SM_GrassPlane",
          "density": 200,
          "scale_min": 1.0,
          "scale_max": 2.0,
          "jitter": 0.5,
          "random_rotation": true,
          "start_cull_dist": 3000,
          "end_cull_dist": 30000
        }
      ],
      "wheat_varieties": [
        {
          "_note": "麦网格变体。mesh_path: 网格路径; density: 密度; scale_min/scale_max: 缩放范围; jitter: 位置抖动; random_rotation: 随机旋转; start_cull_dist/end_cull_dist: LOD剔除距离(厘米)",
          "mesh_path": "/Game/Meshes/SM_WheatPlane",
          "density": 150,
          "scale_min": 1.0,
          "scale_max": 2.0,
          "jitter": 0.3,
          "random_rotation": true,
          "start_cull_dist": 3000,
          "end_cull_dist": 50000
        }
      ]
    }
  },
  "lighting": {
    "_note": "灯光配置块。directional_light: 主平行光(太阳); sky_light: 天空环境光; sky_atmosphere: 大气散射; height_fog: 高度雾效果",
    "directional_light": {
      "_note": "主平行光(太阳)。rotation: [pitch,yaw,roll]旋转角度; intensity: 亮度(lux); color: 光色RGB[0~1]; cast_shadows: 是否投射阴影",
      "rotation": [-45, 35, 0],
      "intensity": 10.0,
      "color": [1.0, 0.94, 0.78],
      "cast_shadows": true
    },
    "sky_light": {
      "_note": "天空环境光。intensity: 亮度倍数; color: 光色RGB[0~1]",
      "intensity": 1.0,
      "color": [0.78, 0.86, 1.0]
    },
    "sky_atmosphere": {
      "_note": "大气散射效果。render_in_main_pass: 是否主通道渲染; sky_luminance_factor: 天空亮度因子RGB; multi_scattering_factor: 多次散射强度",
      "render_in_main_pass": true,
      "sky_luminance_factor": [1.0, 1.0, 1.0],
      "multi_scattering_factor": 2.0
    },
    "height_fog": {
      "_note": "高度雾效果。density: 雾密度; color: 雾色RGB[0~1]",
      "density": 0.02,
      "color": [0.78, 0.82, 0.9]
    }
  },
  "weather": {
    "_note": "天气效果块。volumetric_clouds: 体积云配置; post_process: 后期处理配置",
    "volumetric_clouds": {
      "_note": "体积云。location: 云层位置[xyz](厘米,通常z=2000=高度20米)",
      "location": [0, 0, 2000]
    },
    "post_process": {
      "_note": "后期处理。auto_exposure_min: 自动曝光最小值; auto_exposure_max: 自动曝光最大值",
      "auto_exposure_min": 1.0,
      "auto_exposure_max": 10.0
    }
  }
}
```

碎石散布（placements 圆环）示例：

```json
{
  "_note": "碎石散布组。type: 放置类型(instanced_grid=网格化实例); asset: 网格资产路径; grid: 网格配置",
  "type": "instanced_grid",
  "asset": "/Game/Meshes/SM_Rock",
  "grid": {
    "_note": "圆形网格配置。pattern: 分布模式(circle=圆形); count: 实例数量; radius: 半径(厘米); center: 中心坐标[xyz](厘米); face_center: 是否朝向中心; scale_min/scale_max: 缩放范围[xyz]",
    "pattern": "circle",
    "count": 30,
    "radius": 500,
    "center": [250, 250, 50],
    "face_center": true,
    "scale_min": [0.5, 0.5, 0.5],
    "scale_max": [2, 2, 2]
  }
}
```