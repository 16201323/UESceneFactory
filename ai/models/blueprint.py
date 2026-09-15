"""场景蓝图模型 — ScenePlanner 的输出，JSONBuilder 的输入。

SceneBlueprint 包含用户意图字段和规划字段，是连接意图解析和 JSON 生成的桥梁。
"""
from pydantic import BaseModel, Field


class AssetEntry(BaseModel):
    """资产条目 — 从 AssetIndex 搜索结果映射而来。"""
    path: str
    name: str = ""
    category: str = ""
    subfolder: str = ""


class ExperienceRef(BaseModel):
    """经验引用 — 从 ExperienceRetriever 检索结果映射而来。"""
    id: int
    user_desc: str
    scene_type: str
    rating: int
    keywords: list[str] = Field(default_factory=list)


class SceneBlueprint(BaseModel):
    """场景蓝图 — ScenePlanner 的结构化输出。

    包含两部分：
    1. 意图字段：从用户描述解析而来（terrain_type, has_water 等）
    2. 规划字段：通过工具调用获取的资产、设计规则、经验引用、模板引用等
    """
    # --- 意图字段 ---
    terrain_type: str
    has_water: bool
    has_river: bool
    has_grass: bool
    has_wheat: bool
    placements: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    scene_type: str
    # --- 结构化参数字段(从描述提取,透传给 Stage2 配置 landscape 尺寸/地域氛围)---
    # size_m: 场景物理尺寸 [长,宽] 米,如 [2000,2000] 表示 2km×2km;空列表=用默认尺寸
    size_m: list[int] = Field(default_factory=list)
    # region: 地域名(江西/西北/南方/沿海等),用于体现地域植被与水系特征
    region: str = ""
    # user_desc: 用户原始描述原样透传,保留氛围修饰词供 Stage2 参考
    user_desc: str = ""
    # --- 规划字段 ---
    assets: list[AssetEntry] = Field(default_factory=list)
    design_rules: list[str] = Field(default_factory=list)
    experience_refs: list[ExperienceRef] = Field(default_factory=list)
    template_ref: str | None = None
    lighting_style: str = ""
    weather_style: str = ""
