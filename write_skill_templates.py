#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将3个地形模板JSON写入UE5_JSON技能目录(工作目录外)"""

import json
import os

SKILL_DIR = r"c:\Users\25868\.trae-cn\skills\ue5_json"
TPL_DIR = os.path.join(SKILL_DIR, "templates")

templates = {}

# ========== 模板 P12: 梯田 ==========
templates["template_p12_terraced.json"] = {
  "scene": {
    "_note": "梯田场景模板 — 沿Y轴(北向)递进多级台阶, 模拟农业梯田地貌。direction_deg=90使台阶沿+Y方向逐级升高, 每级step_height_m=3m高差、step_width_m=12m宽, bank_ratio=0.2表示每级20%为田埂过渡区(smoothstep光滑斜面)、80%为平坦田面; 63m×63m小地形, 改component_count可放大",
    "name": "TerracedField",
    "target_level": "/Game/MapForgeTest/GB_TerracedTemplate",
    "description": "梯田地形模板: direction_deg=90沿Y轴递进, 每级3m高12m宽, bank_ratio=0.2田埂占20%, 63m×63m"
  },
  "landscape": {
    "_note": "【梯田算法】C++将每个顶点投影到direction_deg方向轴, 投影距离÷step_width_m=层级号level; 层内位置t∈[0,1): t<(1-bank_ratio)→平坦田面(高度=base+level×step_height_m), t≥(1-bank_ratio)→smoothstep过渡到下一级高度; perturbation扭曲等高线消除几何痕迹, noise_overlay叠加自然微起伏; blend_mode=additive叠加到基础地形(此处基础=0)",
    "material": "/Game/RuralHouse/Landscape/MI_Landscape",
    "section_size_quads": 63,
    "num_subsections": 1,
    "component_count_x": 1,
    "component_count_y": 1,
    "location": [0, 0, 0],
    "rotation": [0, 0, 0],
    "scale": [100, 100, 100],
    "layers": [
      {"_note": "Layer1基底土: uniform权重0.7, 梯田平坦田面主材质(泥土/耕地)",
       "info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo", "weight": 0.7},
      {"_note": "Layer2泥地: uniform权重0.3, 田埂斜面/低洼处泥地材质",
       "info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer2_LayerInfo", "weight": 0.3}
    ],
    "height_pattern": {
      "_note": "terraced核心参数: direction_deg=90(沿+Y北向递进, 0=+X东向); step_height_m=3.0(每级高度差3米, 值越大台阶越陡); step_width_m=12.0(每12米升一级, 值越大台阶越宽); bank_ratio=0.2(田埂占比[0,1], 0=无田埂全平坦, 1=全田埂无平面, 0.2=每级20%为光滑过渡田埂+80%为平坦田面); base_height_m=0.0(方向轴投影距离=0处起始基准高度); blend_mode=additive(梯田高度叠加到基础地形); 增强字段: perturbation_strength=0.3扭曲等高线, perturbation_scale=0.05扰动频率, noise_overlay(amp0.3m)叠加微起伏消除人工平整感",
      "type": "terraced",
      "direction_deg": 90,
      "step_height_m": 3.0,
      "step_width_m": 12.0,
      "bank_ratio": 0.2,
      "base_height_m": 0.0,
      "blend_mode": "additive",
      "perturbation_strength": 0.3,
      "perturbation_scale": 0.05,
      "perturbation_seed": 7,
      "noise_overlay": {
        "_note": "自然起伏: amp0.3m freq0.02 oct3 seed5, 在梯田几何上叠加低频Perlin微起伏",
        "amplitude_m": 0.3,
        "frequency": 0.02,
        "octaves": 3,
        "seed": 5
      }
    }
  },
  "ground": {},
  "placements": [],
  "lighting": {
    "_note": "基础光照: 太阳斜射(俯角45°)正白光 + 天空光冷色补光 + 大气层 + 轻雾营造空气透视",
    "directional_light": {
      "location": [0, 0, 5000],
      "rotation": [-45, 0, 0],
      "intensity": 3.0,
      "color": [1, 1, 1]
    },
    "sky_light": {
      "intensity": 1.0,
      "color": [0.8, 0.9, 1.0]
    },
    "sky_atmosphere": {
      "location": [0, 0, 0]
    },
    "height_fog": {
      "location": [0, 0, 0],
      "density": 0.0001,
      "color": [0.8, 0.85, 0.9]
    }
  },
  "weather": {
    "_note": "体积云: UE5原生VolumetricCloud组件",
    "volumetric_clouds": {
      "location": [0, 0, 2000]
    }
  }
}

# ========== 模板 P13: 喀斯特峰林 ==========
templates["template_p13_karst.json"] = {
  "scene": {
    "_note": "喀斯特峰林场景模板 — 泊松盘采样40座山峰+8个溶斗(漏斗), 模拟云南/桂林喀斯特峰林地貌。每座峰为高斯锥凸起(delta=h×exp(-d²/(2r²))), 溶斗为负高斯锥下凹; 63m×63m小地形, 改component_count可放大",
    "name": "KarstPeakForest",
    "target_level": "/Game/MapForgeTest/GB_KarstTemplate",
    "description": "喀斯特峰林模板: 泊松盘40峰(15~45m, 半径25m) + 8溶斗(深6m, 半径18m), 63m×63m"
  },
  "landscape": {
    "_note": "【喀斯特算法】C++用泊松盘采样(Poisson disk)在min_distance_m约束下生成peak_count个峰点, 每峰随机高度[h_min,h_max]; 每峰以高斯锥凸起: delta=h×exp(-d²/(2σ²)), σ=peak_radius_m/2; 溶斗同理但高度为负(下凹); 所有峰/溶斗高度累加(blend_mode=additive); perturbation扭曲等高线, noise_overlay叠加自然起伏",
    "material": "/Game/RuralHouse/Landscape/MI_Landscape",
    "section_size_quads": 63,
    "num_subsections": 1,
    "component_count_x": 1,
    "component_count_y": 1,
    "location": [0, 0, 0],
    "rotation": [0, 0, 0],
    "scale": [100, 100, 100],
    "layers": [
      {"_note": "Layer1基底土: uniform权重0.6, 峰体主体岩石材质",
       "info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo", "weight": 0.6},
      {"_note": "Layer2泥地: uniform权重0.4, 溶斗底部/低洼积水泥地",
       "info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer2_LayerInfo", "weight": 0.4}
    ],
    "height_pattern": {
      "_note": "karst核心参数: peak_count=40(峰数量, 越多峰林越密); min_distance_m=60(峰间最小距离, 泊松盘参数, 值越大峰越稀疏); peak_height_min_m=15/peak_height_max_m=45(每峰随机取此区间高度); peak_radius_m=25(峰底半径, σ=radius/2, 控制山体坡度陡缓); doline_count=8(溶斗/漏斗数量, 地表塌陷坑); doline_depth_m=6(溶斗下凹深度); doline_radius_m=18(溶斗半径); seed=42(随机种子, 控制峰/溶斗位置分布); blend_mode=additive(所有峰凸起+溶斗下凹累加); 增强字段: perturbation_strength=0.4扭曲等高线, noise_overlay(amp0.5m)叠加起伏",
      "type": "karst",
      "peak_count": 40,
      "min_distance_m": 60,
      "peak_height_min_m": 15,
      "peak_height_max_m": 45,
      "peak_radius_m": 25,
      "doline_count": 8,
      "doline_depth_m": 6,
      "doline_radius_m": 18,
      "seed": 42,
      "blend_mode": "additive",
      "perturbation_strength": 0.4,
      "perturbation_scale": 0.04,
      "perturbation_seed": 13,
      "noise_overlay": {
        "_note": "自然起伏: amp0.5m freq0.03 oct3 seed11, 在峰林几何上叠加中频起伏增强岩石不规则感",
        "amplitude_m": 0.5,
        "frequency": 0.03,
        "octaves": 3,
        "seed": 11
      }
    }
  },
  "ground": {},
  "placements": [],
  "lighting": {
    "_note": "基础光照: 太阳斜射(俯角45°)正白光 + 天空光冷色补光 + 大气层 + 轻雾营造空气透视",
    "directional_light": {
      "location": [0, 0, 5000],
      "rotation": [-45, 0, 0],
      "intensity": 3.0,
      "color": [1, 1, 1]
    },
    "sky_light": {
      "intensity": 1.0,
      "color": [0.8, 0.9, 1.0]
    },
    "sky_atmosphere": {
      "location": [0, 0, 0]
    },
    "height_fog": {
      "location": [0, 0, 0],
      "density": 0.0001,
      "color": [0.8, 0.85, 0.9]
    }
  },
  "weather": {
    "_note": "体积云: UE5原生VolumetricCloud组件",
    "volumetric_clouds": {
      "location": [0, 0, 2000]
    }
  }
}

# ========== 模板 P14: 黄土沟壑 ==========
templates["template_p14_gully.json"] = {
  "scene": {
    "_note": "黄土沟壑场景模板 — 分形树状沟壑网络: 主沟45°蜿蜒800m + 6条一级支沟分叉, 模拟黄土高原沟壑地貌。主沟中心线=方向向量+垂直正弦蜿蜒, 支沟从主沟随机点以±branch_angle_deg分叉, V型余弦横截面切削; 63m×63m小地形, 改component_count可放大",
    "name": "GullyLoess",
    "target_level": "/Game/MapForgeTest/GB_GullyTemplate",
    "description": "黄土沟壑模板: 主沟45°蜿蜒800m + 6支沟分叉, V型沟深8m宽15m, 63m×63m"
  },
  "landscape": {
    "_note": "【沟壑算法】C++生成主沟路径: 沿main_direction_deg方向行进main_length_m, 中心线叠加垂直方向正弦蜿蜒(meander_amplitude_m×sin(meander_frequency×距离)); 从主沟随机branch_count个点分叉支沟, 支沟方向=主沟方向±branch_angle_deg, 支沟长度=main_length×branch_length_ratio; branch_depth≥2时支沟再分叉二级支沟(递归); 每条沟沿路径用V/U型余弦横截面切削(gully_depth_m×cos), 宽度=gully_width_m; AABB裁剪提升性能",
    "material": "/Game/RuralHouse/Landscape/MI_Landscape",
    "section_size_quads": 63,
    "num_subsections": 1,
    "component_count_x": 1,
    "component_count_y": 1,
    "location": [0, 0, 0],
    "rotation": [0, 0, 0],
    "scale": [100, 100, 100],
    "layers": [
      {"_note": "Layer1基底土: uniform权重0.5, 黄土塬面/沟壑主体材质",
       "info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo", "weight": 0.5},
      {"_note": "Layer2泥地: uniform权重0.5, 沟底低洼积水泥地",
       "info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer2_LayerInfo", "weight": 0.5}
    ],
    "height_pattern": {
      "_note": "gully核心参数: main_direction_deg=45(主沟流向, 0=+X东向, 90=+Y北向, 45=东北向); main_length_m=800(主沟长度米); meander_amplitude_m=40(蜿蜒幅度, 主沟中心线垂直偏移); meander_frequency=0.008(蜿蜒频率, 值越大弯道越多); branch_count=6(一级支沟数量); branch_angle_deg=50(支沟与主沟夹角度); branch_length_ratio=0.5(支沟长度=主沟长度×此比例); branch_depth=1(分叉深度, 1=仅一级支沟, 2=支沟再分叉二级); gully_depth_m=8(沟壑切削深度米); gully_width_m=15(沟壑宽度米); profile=V(横截面形状, V=V型余弦切/U=U型平底); seed=42(随机种子控制分叉点/蜿蜒相位); blend_mode=additive; 增强字段: perturbation_strength=0.3扭曲沟壑边缘, noise_overlay(amp0.4m)叠加起伏",
      "type": "gully",
      "main_direction_deg": 45,
      "main_length_m": 800,
      "meander_amplitude_m": 40,
      "meander_frequency": 0.008,
      "branch_count": 6,
      "branch_angle_deg": 50,
      "branch_length_ratio": 0.5,
      "branch_depth": 1,
      "gully_depth_m": 8,
      "gully_width_m": 15,
      "profile": "V",
      "seed": 42,
      "blend_mode": "additive",
      "perturbation_strength": 0.3,
      "perturbation_scale": 0.05,
      "perturbation_seed": 19,
      "noise_overlay": {
        "_note": "自然起伏: amp0.4m freq0.025 oct3 seed17, 在沟壑几何上叠加起伏增强黄土塬面不规则感",
        "amplitude_m": 0.4,
        "frequency": 0.025,
        "octaves": 3,
        "seed": 17
      }
    }
  },
  "ground": {},
  "placements": [],
  "lighting": {
    "_note": "基础光照: 太阳斜射(俯角45°)正白光 + 天空光冷色补光 + 大气层 + 轻雾营造空气透视",
    "directional_light": {
      "location": [0, 0, 5000],
      "rotation": [-45, 0, 0],
      "intensity": 3.0,
      "color": [1, 1, 1]
    },
    "sky_light": {
      "intensity": 1.0,
      "color": [0.8, 0.9, 1.0]
    },
    "sky_atmosphere": {
      "location": [0, 0, 0]
    },
    "height_fog": {
      "location": [0, 0, 0],
      "density": 0.0001,
      "color": [0.8, 0.85, 0.9]
    }
  },
  "weather": {
    "_note": "体积云: UE5原生VolumetricCloud组件",
    "volumetric_clouds": {
      "location": [0, 0, 2000]
    }
  }
}

# ========== 写入文件 ==========
for fname, data in templates.items():
    fpath = os.path.join(TPL_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] {fname} -> {fpath} ({os.path.getsize(fpath)} bytes)")

print(f"\n共写入 {len(templates)} 个模板文件到 {TPL_DIR}")
