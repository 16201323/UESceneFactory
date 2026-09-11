"""ScenePlanner Agent — 场景规划智能体。

分析用户描述，调用工具搜索资产/经验/模板/设计原则，输出结构化 SceneBlueprint。
"""
from typing import Any

from pydantic_ai import Agent, RunContext

from ai.agents.base import AgentBase, AgentDeps
from ai.models.blueprint import SceneBlueprint
from ai.tools.knowledge_tools import (
    get_design_principles_core,
    get_pattern_docs_core,
    get_template_core,
)
from ai.tools.asset_tools import search_assets_core
from ai.tools.experience_tools import search_experience_core


class ScenePlannerAgent(AgentBase):
    """场景规划 Agent — 固定流水线的第一个 Agent。

    职责：解析意图 → 搜索资产 → 检索经验 → 获取设计原则 → 匹配模板 → 输出 SceneBlueprint
    """

    def _output_type(self) -> Any:
        return SceneBlueprint

    def _system_prompt(self) -> str:
        return (
            "你是一个 UE 场景规划专家。分析用户描述，调用工具获取知识，输出场景蓝图。\n\n"
            "关键步骤：\n"
            "1. 解析用户描述的意图（terrain_type/has_water/has_river/has_grass/has_wheat/"
            "placements/keywords/scene_type）\n"
            "2. 调用 search_assets 搜索可用资产\n"
            "3. 调用 search_experience 检索相似历史案例\n"
            "4. 调用 get_design_principles 获取设计原则\n"
            "5. 调用 get_template 匹配模板\n\n"
            "terrain_type: flat/hills/mountains/karst/gully/terraced\n"
            "placements: village/tower/forest/heliport/pv_solar\n"
            "lighting_style: warm_morning/cool_noon/golden_sunset\n"
            "weather_style: clear/cloudy/foggy/light_rain\n\n"
            "输出 SceneBlueprint。"
        )

    def _register_tools(self, agent: Agent) -> None:
        @agent.tool
        async def search_assets(
            ctx: RunContext[AgentDeps], keywords: list[str]
        ) -> list[dict]:
            """搜索 UE 资产库中匹配关键词的资产。"""
            entries = search_assets_core(ctx.deps.asset_index, keywords)
            return [e.model_dump() for e in entries]

        @agent.tool
        async def search_experience(
            ctx: RunContext[AgentDeps], keywords: list[str], terrain_type: str
        ) -> list[dict]:
            """检索与当前意图相似的历史经验案例。"""
            intent = {"keywords": keywords, "terrain_type": terrain_type}
            refs = search_experience_core(ctx.deps.retriever, intent)
            return [r.model_dump() for r in refs]

        @agent.tool
        async def get_design_principles(
            ctx: RunContext[AgentDeps], scene_type: str
        ) -> list[str]:
            """获取场景设计原则列表。"""
            return get_design_principles_core(ctx.deps.knowledge, scene_type)

        @agent.tool
        async def get_template(
            ctx: RunContext[AgentDeps], keywords: list[str], terrain_type: str
        ) -> str:
            """根据关键词和地形类型匹配模板文件名。"""
            result = get_template_core(ctx.deps.knowledge, keywords, terrain_type)
            return result if result else ""

        @agent.tool
        async def get_pattern_docs(
            ctx: RunContext[AgentDeps], pattern_name: str
        ) -> str:
            """获取指定模式文件的文档内容。"""
            return get_pattern_docs_core(ctx.deps.knowledge, pattern_name)
