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
    # --- 规划字段 ---
    assets: list[AssetEntry] = Field(default_factory=list)
    design_rules: list[str] = Field(default_factory=list)
    experience_refs: list[ExperienceRef] = Field(default_factory=list)
    template_ref: str | None = None
    lighting_style: str = ""
    weather_style: str = ""
