# -*- coding: utf-8 -*-
# 把水系场景归入 UE5_JSON 技能: 创建模板 JSON + 更新 3 处文档
import io, os, sys

SKILL_DIR = r"c:\Users\25868\.trae-cn\skills\ue5_json"

# ============================================================
# 1) 创建模板 JSON: templates/template_p15_water_river.json
# ============================================================
TEMPLATE_JSON = r'''{
    "scene": {
        "name": "water_river_template",
        "target_level": "/Game/Maps/TestWaterRiver",
        "description": "水系模板: 河宽渐变+瀑布+支流汇入 (P15)"
    },
    "landscape": {
        "material": "/Game/RuralHouse/Landscape/MI_Landscape",
        "section_size_quads": 63,
        "num_subsections": 2,
        "component_count_x": 4,
        "component_count_y": 4,
        "location": [0, 0, 0],
        "rotation": [0, 0, 0],
        "scale": [100, 100, 100],
        "height_pattern": {
            "type": "features",
            "hills": [
                {"center_x_m": 250, "center_y_m": 250, "radius_m": 200, "height_m": 30}
            ],
            "rivers": [
                {
                    "points": [[50, 450], [150, 350], [250, 250], [350, 200], [450, 200]],
                    "width_m": 2,
                    "width_end_m": 8,
                    "bed_depth_m": 2.0,
                    "profile": "V",
                    "material_path": "/Game/Modular_Rural_Cabin/Materials/Instances/Water_Lake",
                    "waterfalls": [
                        {"t": 0.25, "drop_m": 3},
                        {"t": 0.6, "drop_m": 5}
                    ],
                    "flow_speed": 10.0
                },
                {
                    "points": [[250, 480], [250, 380], [250, 250]],
                    "width_m": 1,
                    "width_end_m": 2,
                    "bed_depth_m": 1.5,
                    "profile": "V",
                    "material_path": "/Game/Modular_Rural_Cabin/Materials/Instances/Water_Lake",
                    "flow_speed": 10.0
                }
            ]
        },
        "layers": [
            {"info": "/Game/RuralHouse/Landscape/LandscapeLayers/Layer1_LayerInfo", "weight": 1.0}
        ]
    },
    "ground": {},
    "lighting": {
        "directional_light": {"location": [0, 0, 5000], "rotation": [-45, 0, 0], "intensity": 3.0, "color": [1, 1, 1]},
        "sky_light": {"location": [0, 0, 1000], "intensity": 1.0, "color": [0.5, 0.6, 0.8]},
        "sky_atmosphere": {"location": [0, 0, 10000]},
        "height_fog": {"location": [0, 0, 500], "density": 0.01, "color": [0.6, 0.7, 0.9]}
    },
    "weather": {
        "volumetric_clouds": {"location": [0, 0, 5000]}
    }
}
'''

# ============================================================
# 2) 更新 references/height_pattern.md: rivers[] 展开为完整参数表
# ============================================================
HP_PATH = os.path.join(SKILL_DIR, "references", "height_pattern.md")

HP_OLD = u"""| rivers[] | array | points[[x,y],...], width_m, material_path(可选) | 河流; C++ 自动河床冲刷: Import 前沿路径在高度图下切 U 型谷(深 150cm, 余弦横截面+河岸余弦衰减), 水面 ribbon 逐顶点采样地形并沉入河谷 -30cm; 折点须沿自然下坡、不穿越山丘, 否则水面可能断节 |"""

HP_NEW = u"""| rivers[] | array | 见下方 rivers 子表 | 河流; C++ 两阶段处理: (1) Import 前沿路径在高度图下切 V/U 型谷(深=bed_depth_m, 余弦横截面); (2) Import 后沿中心线每~5m 分段创建 SMC 水面平面, 水面Z=min(河床底+沉入量, 较低边缘地形-15cm), 平面宽=河宽×1.2; 折点须沿自然下坡、不穿越山丘/悬崖, 否则水面可能断节或悬空. 详见下方 rivers 子表 |"""

HP_RIVER_SECTION = u"""

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
"""

# ============================================================
# 3) 更新 references/templates_index.md: 追加 P15
# ============================================================
TI_PATH = os.path.join(SKILL_DIR, "references", "templates_index.md")

TI_NEW_SECTION = u"""
## 模板 P15 — 水系场景（河流+瀑布+支流，features 模式）

- 文件：`templates/template_p15_water_river.json`
- 模式：`height_pattern.type = "features"`
- 地形规格：`component_count 4×4, section_size_quads 63, num_subsections 2, scale 100` → 504m×504m
- 场景：1 个山丘(中心 250,250 半径 200m 高 30m) + 2 条河流(主河+支流汇入) + 2 个瀑布

**河流参数详解:**

| 参数 | 主河值 | 支流值 | 说明 |
|------|--------|--------|------|
| points | 5 折点(50,450→450,200) | 3 折点(250,480→250,250) | 河流折点(米), 至少 2 个点, 坐标在地形范围内 |
| width_m | 2 | 1 | 起点河宽(米), 建议≥1m |
| width_end_m | 8 | 2 | 终点河宽(米), 支流汇入主干时变宽 |
| bed_depth_m | 2.0 | 1.5 | 河床冲刷深度(米), ≥0.5m 保证水深 |
| profile | "V" | "V" | V 型余弦横截面(中心深两岸浅) |
| material_path | Water_Lake | Water_Lake | 水面材质, 需支持 FlowSpeed 参数 |
| waterfalls | 2 个(t=0.25 drop=3m, t=0.6 drop=5m) | 无 | t=段内位置(0~1), drop_m=落差 |
| flow_speed | 10.0 | 10.0 | 流速倍数, 10=快流 |

**水面生成算法(C++ 自动, 不可配置):**

1. 沿中心线每~5m 采样一个点, 记录该点处河宽
2. 每点采样: 中心线地形Z(河床底) + 左右边缘地形Z(边缘=河宽×0.6)
3. 水面Z = min(河床底+沉入量, 较低边缘-15cm) → 平地保持水深, 坡地压低封缝
4. 每相邻采样点创建一个 SMC 平面段, 宽=河宽×1.2, 沿坡度加 Pitch 倾斜
5. 相邻段重叠 20cm 封闭弯道接缝

**边界条件与可能问题:**

| 条件 | 后果 | 规避 |
|------|------|------|
| bed_depth_m = 0 | 不冲刷, 水面贴地, 深度不足 | 保持≥0.5m |
| bed_depth_m ≤ 0.3 | 沉入量退化为 2cm | ≥0.5m |
| width_m < 0.5m | 边缘采样失效, 坡地可能缝隙 | ≥1m |
| 折点穿悬崖 | 水面 Z 异常(悬空/深埋) | 不穿悬崖, 或拆段+waterfall |
| 折点不沿下坡 | 水面可能逆流断节 | 折点 Z 递减(沿自然下坡) |

**派生方法:** 复制模板后改 `target_level`, 增删 rivers 条目, 调 width/bed_depth/points。加新河只需在 rivers[] 追加一个 object。瀑布在 waterfalls[] 追加 {t, drop_m}。改 flow_speed 控制流速。无需重新编译 DLL(纯 JSON 参数)。
"""

# ============================================================
# 4) 更新 SKILL.md: 第 8 节模板表追加 P15 行
# ============================================================
SKILL_PATH = os.path.join(SKILL_DIR, "SKILL.md")

SKILL_OLD = u"| templates/template_p14_gully.json | 黄土沟壑 | gully模式：主沟蜿蜒+支沟分叉+V型切削 |"
SKILL_NEW = u"""| templates/template_p14_gully.json | 黄土沟壑 | gully模式：主沟蜿蜒+支沟分叉+V型切削 |
| templates/template_p15_water_river.json | 水系（河流+瀑布+支流） | features模式：河宽渐变+bed_depth冲刷+水面Z自适应封缝+flow_speed流速 |"""

# ============================================================
# 执行
# ============================================================
errors = 0

# 1) 模板 JSON
tpl_path = os.path.join(SKILL_DIR, "templates", "template_p15_water_river.json")
with io.open(tpl_path, "w", encoding="utf-8") as f:
    f.write(TEMPLATE_JSON)
print("OK: created %s" % tpl_path)

# 2) height_pattern.md
with io.open(HP_PATH, "r", encoding="utf-8") as f:
    hp = f.read()
if HP_OLD not in hp:
    print("FAIL: height_pattern.md old text not found")
    errors += 1
else:
    hp = hp.replace(HP_OLD, HP_NEW, 1)
    # 在 scatter 单项格式之后追加 rivers 子表
    scatter_end = u"| random_rotation | bool | false | 随机旋转 |"
    if scatter_end not in hp:
        print("FAIL: height_pattern.md scatter_end anchor not found")
        errors += 1
    else:
        hp = hp.replace(scatter_end, scatter_end + "\n" + HP_RIVER_SECTION, 1)
        with io.open(HP_PATH, "w", encoding="utf-8") as f:
            f.write(hp)
        print("OK: updated %s" % HP_PATH)

# 3) templates_index.md
with io.open(TI_PATH, "r", encoding="utf-8") as f:
    ti = f.read()
ti_anchor = u"## 派生要点"
if ti_anchor not in ti:
    print("FAIL: templates_index.md anchor not found")
    errors += 1
else:
    ti = ti.replace(ti_anchor, TI_NEW_SECTION + "\n" + ti_anchor, 1)
    with io.open(TI_PATH, "w", encoding="utf-8") as f:
        f.write(ti)
    print("OK: updated %s" % TI_PATH)

# 4) SKILL.md
with io.open(SKILL_PATH, "r", encoding="utf-8") as f:
    sk = f.read()
if SKILL_OLD not in sk:
    print("FAIL: SKILL.md old text not found")
    errors += 1
else:
    sk = sk.replace(SKILL_OLD, SKILL_NEW, 1)
    with io.open(SKILL_PATH, "w", encoding="utf-8") as f:
        f.write(sk)
    print("OK: updated %s" % SKILL_PATH)

print("\nDone: %d errors" % errors)
