"""完整场景 JSON 模型 — JSONBuilderAgent 的输出，映射 build_scene.py 的顶层结构。

顶层 6 个分区：scene（必填）、landscape、ground、placements、lighting、weather（均可选）。
复杂嵌套结构（height_pattern、weight_pattern、grid 等）使用 dict 保持灵活，
因为它们由 C++ 层解析或结构随场景类型变化，过度约束反而会导致 LLM 输出校验失败。

默认值对齐 build_scene.py 源码中的默认值（如 section_size_quads=63、scale=[100,100,100]）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SceneInfo(BaseModel):
    """场景元数据 — build_scene.py 的 scene 分区（必填）。"""
    name: str                                              # 场景名称（仅日志）
    target_level: str                                      # 目标关卡包路径，如 /Game/Maps/Generated/MyScene
    description: str = ""                                  # 场景描述（仅日志，可选）


class LandscapeConfig(BaseModel):
    """地形配置 — build_scene.py 的 landscape 分区。

    基础参数由 Python 直接读取；height_pattern 和 weight_pattern 由 C++ 插件解析（第二层）。
    """
    material: str = ""                                     # 材质实例路径
    section_size_quads: int = 63                           # 每 Section 四边形数（63/127/255）
    num_subsections: int = 1                               # 每 Component 的 Subsection 数（1/2）
    component_count_x: int = 8                             # X 方向 Component 数量
    component_count_y: int = 8                             # Y 方向 Component 数量
    location: list[float] = Field(default_factory=lambda: [0, 0, 0])    # 世界位置 [x,y,z]（厘米）
    rotation: list[float] = Field(default_factory=lambda: [0, 0, 0])    # 旋转 [pitch,yaw,roll]
    scale: list[float] = Field(default_factory=lambda: [100, 100, 100]) # 缩放 [x,y,z]，100=1m/quad
    layers: list[dict] = Field(default_factory=list)       # 图层数组，每项含 info/weight/weight_pattern
    grass: dict | None = None                              # 草地配置 {grass_type, grass_mesh, layer_name, density}
    wheat: dict | None = None                             # 麦田配置 {type_path, layer_name}
    height_pattern: dict | None = None                    # 高度模式（C++解析，结构随 type 变化，用 dict 保持灵活）


class PlacementConfig(BaseModel):
    """放置配置 — build_scene.py 的 placements[] 数组中的一项。

    通过 type 字段分发放置方式：static / instanced_grid / static_grid / blueprint / group / crop_field / village。
    """
    type: str = "static"                                   # static/instanced_grid/static_grid/blueprint/group/crop_field/village
    asset: str = ""                                        # 资产路径（group 用 asset_prefix 代替）
    location: list[float] = Field(default_factory=lambda: [0, 0, 0])
    rotation: list[float] = Field(default_factory=lambda: [0, 0, 0])
    scale: list[float] = Field(default_factory=lambda: [1, 1, 1])
    material_override: str | None = None                  # 材质覆盖路径
    grid: dict | None = None                               # 网格配置（instanced_grid→HISM批量 / static_grid→逐个StaticMeshActor）
    instances: list[dict] | None = None                   # 显式实例数组（instanced_grid 二选一）
    asset_prefix: str | None = None                       # 资产路径前缀（group 专用）
    count: int | None = None                              # 部件数（group 专用）

    @model_validator(mode='after')
    def validate_asset_nonempty(self) -> "PlacementConfig":
        """校验 asset 字段非空 — 防止 LLM 生成空 asset 占位条目导致 UE 卡死。

        static/instanced_grid/static_grid/blueprint/crop_field 等类型依赖 asset 字段，
        空字符串会导致 build_scene.py 的 load_asset("") 卡死 UE 编辑器主线程；
        group 类型依赖 asset_prefix，不检查 asset 本身；
        village 类型使用 village dict 结构，不在此校验范围。
        校验失败时 Pydantic 抛出 ValueError，pydantic_ai 自动重试（retries=3），
        将错误消息反馈给 LLM 要求修正输出。
        """
        if self.type == "group":
            # group 类型用 asset_prefix 而非 asset
            if not self.asset_prefix or not self.asset_prefix.strip():
                raise ValueError(
                    f"group 类型放置条目必须填写非空 asset_prefix"
                    f"（当前为 '{self.asset_prefix}'）"
                )
        elif self.type != "village":
            # static / instanced_grid / static_grid / blueprint / crop_field 等类型
            if not self.asset or not self.asset.strip():
                raise ValueError(
                    f"{self.type} 类型放置条目必须填写非空 asset 路径"
                    f"（当前为 '{self.asset}'）— 空 asset 会导致 UE 编辑器卡死"
                )
        # grid 类型 (instanced_grid / static_grid) 必须提供 grid 或 instances 二者之一
        # 缺失时 build_scene.py 回退为 [0,0,0] 单实例, 导致电塔/树木挤在原点(地形外)
        if self.type in ("instanced_grid", "static_grid"):
            has_grid = isinstance(self.grid, dict) and bool(self.grid)
            has_instances = isinstance(self.instances, list) and bool(self.instances)
            if not has_grid and not has_instances:
                raise ValueError(
                    f"{self.type} 类型放置条目必须提供 grid 或 instances 二者之一"
                    f"（当前 grid={self.grid}, instances={self.instances}）"
                    f"— 缺失会导致实例退化为 [0,0,0] 单点"
                )
        return self


class LightingConfig(BaseModel):
    """光照配置 — build_scene.py 的 lighting 分区。"""
    directional_light: dict | None = None                 # 太阳光 {location, rotation, intensity, color, cast_shadows}
    sky_light: dict | None = None                          # 天空光 {location, intensity, color}
    sky_atmosphere: dict | None = None                    # 大气层 {location, sky_luminance_factor, multi_scattering_factor}
    height_fog: dict | None = None                        # 指数高度雾 {location, density, color}


class WeatherConfig(BaseModel):
    """天气配置 — build_scene.py 的 weather 分区。"""
    volumetric_clouds: dict | None = None                  # 体积云 {location}
    post_process: dict | None = None                     # 后期处理 {auto_exposure_min, auto_exposure_max}


class SceneJSON(BaseModel):
    """完整场景 JSON — JSONBuilderAgent 的输出模型。

    映射 build_scene.py 的顶层结构。model_dump() 生成的 dict 可直接传给 build_scene.py 消费。
    """
    scene: SceneInfo                                       # 场景元数据（必填）
    landscape: LandscapeConfig | None = None              # UE5 正式地形（必填，见下方 model_validator）
    ground: dict | None = None                             # 静态网格地面（可选，结构简单用 dict）
    placements: list[PlacementConfig] = Field(default_factory=list)  # 放置列表（可选，默认空）
    lighting: LightingConfig | None = None                # 光照（可选）
    weather: WeatherConfig | None = None                  # 天气（可选）

    @model_validator(mode='after')
    def validate_landscape_nonnull(self) -> "SceneJSON":
        """校验 landscape 非空 — 防止 LLM 生成 "landscape": null 导致下游崩溃。

        根因: 蓝图 SceneBlueprint.terrain_type 是必填字段, 枚举值
        (flat/ridge/hill/noise/hill_ridge/features/terraced/karst/gully)
        始终暗示需要 UE5 Landscape 地形, 不存在"无地形"的场景类型。
        若 LLM 输出 landscape=null, 下游 auto_repair/validate_scene_quality
        会将 null 视为"合法可选状态"而静默放行, 最终 build_scene.py 消费时
        抛出 AttributeError: 'NoneType' object has no attribute 'get'。

        校验失败时 Pydantic 抛出 ValueError, pydantic_ai 自动重试 (retries=3),
        将错误消息反馈给 LLM 要求重新生成完整的 landscape 分区。
        """
        if self.landscape is None:
            raise ValueError(
                "landscape 分区是必填字段（蓝图 terrain_type 始终暗示需要地形），"
                "禁止输出 null 或省略 landscape 分区。"
                "请根据蓝图的 terrain_type 生成完整的 landscape 配置，"
                "至少包含 material / component_count_x / component_count_y / "
                "scale / height_pattern 等字段。"
            )
        # grass 必填 — 缺失会导致 build_scene.py 无草地材质, 产出灰色方块地形
        if self.landscape.grass is None:
            raise ValueError(
                "landscape.grass 是必填字段, 禁止输出 null 或省略。"
                "请生成 grass 配置, 至少包含 grass_type/grass_mesh/layer_name/density。"
                "缺失会导致地形无草地材质, 产出灰色方块。"
            )
        # height_pattern 必填 — 缺失会导致 build_scene.py 传空字符串给 C++, 产出完全平坦地形
        if self.landscape.height_pattern is None:
            raise ValueError(
                "landscape.height_pattern 是必填字段, 禁止输出 null 或省略。"
                "请根据蓝图 terrain_type 生成完整的高度模式配置。"
                "缺失会导致 C++ 插件收到空字符串, 产出完全平坦地形。"
            )
        return self

    @model_validator(mode='after')
    def validate_lighting_weather_nonnull(self) -> "SceneJSON":
        """校验 lighting/weather 非空 — 防止 LLM 生成 null 导致场景全黑无云。

        根因: lighting 和 weather 被声明为可选 (dict | None = None),
        LLM 可能把它们设为 null。build_scene.py 用 if lighting:/if weather: 守卫,
        None 时静默跳过, 导致场景全黑无光照、无体积云。

        校验失败时 Pydantic 抛出 ValueError, pydantic_ai 自动重试 (retries=3),
        强制 LLM 生成完整的 lighting/weather 分区。
        """
        if self.lighting is None:
            raise ValueError(
                "lighting 分区是必填字段, 禁止输出 null 或省略。"
                "请生成 lighting 配置, 至少包含 directional_light/sky_light/sky_atmosphere。"
                "缺失会导致场景全黑无光照。"
            )
        if self.weather is None:
            raise ValueError(
                "weather 分区是必填字段, 禁止输出 null 或省略。"
                "请生成 weather 配置, 至少包含 volumetric_clouds。"
                "缺失会导致场景无体积云。"
            )
        return self


def normalize_height_pattern(hp: dict | None) -> None:
    """后处理: 补全道路推平参数 + 散布道路排除字段(就地修改 height_pattern dict)。

    在 JSONBuilderAgent 生成场景 JSON 后、QualityGuardAgent 校验前调用,
    也在 QualityGuardAgent 输出后作为安全网再调用一次(防止 LLM 修复时丢弃字段)。

    补全的字段:
    - roads[].level_depth_m (默认 0.1): 道路下切深度, 缺失时 C++ 跳过地形推平导致路面悬空
    - roads[].shoulder_width_m (默认 2.0): 路肩过渡宽度, 缺失时 C++ 跳过地形推平导致路面悬空
    - scatter[].road_exclude_distance_m (默认 3.0): 道路边缘外扩排除距离, 缺失时 C++ 散布无法避开道路
    """
    if not isinstance(hp, dict):
        return
    # 补全道路推平参数: level_depth_m + shoulder_width_m
    for road in hp.get("roads", []):
        road.setdefault("level_depth_m", 0.1)
        road.setdefault("shoulder_width_m", 2.0)
    # 补全散布道路排除距离
    for sc in hp.get("scatter", []):
        sc.setdefault("road_exclude_distance_m", 3.0)
