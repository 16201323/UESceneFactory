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

    通过 type 字段分发四种放置方式：static / instanced_grid / blueprint / group。
    """
    type: str = "static"                                   # static/instanced_grid/blueprint/group
    asset: str = ""                                        # 资产路径（group 用 asset_prefix 代替）
    location: list[float] = Field(default_factory=lambda: [0, 0, 0])
    rotation: list[float] = Field(default_factory=lambda: [0, 0, 0])
    scale: list[float] = Field(default_factory=lambda: [1, 1, 1])
    material_override: str | None = None                  # 材质覆盖路径
    grid: dict | None = None                               # HISM 网格配置（instanced_grid 专用）
    instances: list[dict] | None = None                   # 显式实例数组（instanced_grid 二选一）
    asset_prefix: str | None = None                       # 资产路径前缀（group 专用）
    count: int | None = None                              # 部件数（group 专用）

    @model_validator(mode='after')
    def validate_asset_nonempty(self) -> "PlacementConfig":
        """校验 asset 字段非空 — 防止 LLM 生成空 asset 占位条目导致 UE 卡死。

        static/instanced_grid/blueprint/crop_field 等类型依赖 asset 字段，
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
            # static / instanced_grid / blueprint / crop_field 等类型
            if not self.asset or not self.asset.strip():
                raise ValueError(
                    f"{self.type} 类型放置条目必须填写非空 asset 路径"
                    f"（当前为 '{self.asset}'）— 空 asset 会导致 UE 编辑器卡死"
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
    landscape: LandscapeConfig | None = None              # UE5 正式地形（可选）
    ground: dict | None = None                             # 静态网格地面（可选，结构简单用 dict）
    placements: list[PlacementConfig] = Field(default_factory=list)  # 放置列表（可选，默认空）
    lighting: LightingConfig | None = None                # 光照（可选）
    weather: WeatherConfig | None = None                  # 天气（可选）
