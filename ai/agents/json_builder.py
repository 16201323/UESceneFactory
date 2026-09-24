"""JSONBuilderAgent — 场景 JSON 生成智能体（流水线第二阶段）。

接收 ScenePlannerAgent 输出的蓝图 JSON，调用工具注入分层知识文档和搜索资产，
生成符合 build_scene.py 规范的完整场景 JSON（SceneJSON 模型）。
"""
from typing import Any

from pydantic_ai import Agent, RunContext

from ai.agents.base import AgentBase, AgentDeps
from ai.models.scene_json import SceneJSON
from ai.tools.json_tools import inject_knowledge_core
from ai.tools.asset_tools import search_assets_core


class JSONBuilderAgent(AgentBase):
    """场景 JSON 生成 Agent — 固定流水线的第二个 Agent。

    职责：解析蓝图意图 → 注入知识文档 → 搜索资产路径 → 生成场景 JSON
    """

    def _output_type(self) -> Any:
        """输出类型为 SceneJSON — 映射 build_scene.py 顶层 JSON 结构。"""
        return SceneJSON

    def _system_prompt(self) -> str:
        """系统提示词 — 指导 LLM 生成符合 build_scene.py 规范的场景 JSON。

        性能优化: 详细规则（landscape尺寸/asset字段/贴地/村落/山脉/水系）
        已移入对应知识文档（core/asset_guide/placements/height_pattern），
        通过 inject_knowledge 工具按需注入，避免每次调用都携带冗长指令。
        系统提示词从~4KB精简到~1KB，减少推理模型(glm-5.2)的上下文处理开销。
        """
        return (
            "你是一个 UE5 场景 JSON 生成专家。根据输入的场景蓝图（SceneBlueprint JSON），"
            "调用工具注入知识文档和搜索资产，生成完整的场景 JSON。\n\n"
            "关键步骤：\n"
            "1. 解析蓝图意图字段（terrain_type/has_water/has_river/has_grass/"
            "has_wheat/placements/keywords）及结构化参数（size_m/region/user_desc）\n"
            "2. 调用 inject_knowledge 注入分层知识文档（含尺寸换算/资产规则/贴地规则/"
            "村落规则/山脉规则/水系规则等详细约束）\n"
            "3. 调用 search_assets 搜索蓝图 keywords 对应的 UE 资产路径\n"
            "4. 严格遵守知识文档中的约束，生成符合 build_scene.py 规范的场景 JSON\n\n"
            "JSON 顶层结构：scene(必填) / landscape(必填) / ground / placements / lighting(必填) / weather(必填)\n"
            "⚠️ 必填字段（禁止输出 null 或省略，缺失会导致严重渲染缺陷）：\n"
            "   - landscape: 蓝图 terrain_type(flat/ridge/hill/noise/hill_ridge/features/terraced/karst/gully)\n"
            "     始终暗示需要 UE5 Landscape 地形\n"
            "   - landscape.grass: 草地配置(缺→灰色地形)\n"
            "   - landscape.height_pattern: 高度模式(缺→完全平坦)\n"
            "   - lighting: 光照(缺→场景全黑)，至少含 directional_light/sky_light/sky_atmosphere\n"
            "   - weather: 天气(缺→无云)，至少含 volumetric_clouds\n"
            "   - grid 类型 placement 的 grid 或 instances(缺→实例退化为[0,0,0])\n"
            "资产路径格式：/Game/类别/Name（不含 .uasset 后缀）\n"
            "单位：location/spacing=厘米(cm)，height_pattern 内=米(m)\n"
            "weight 范围：0~1 浮点数\n\n"
            "⚠️ 所有详细规则（landscape尺寸换算、asset字段规则、贴地规则、"
            "村落房屋数量、远景山脉、水系flow_speed等）均在 inject_knowledge 返回的"
            "知识文档中，生成 JSON 前务必仔细阅读并严格遵守。\n\n"
            "输出 SceneJSON。"
        )

    def _register_tools(self, agent: Agent) -> None:
        @agent.tool
        async def inject_knowledge(
            ctx: RunContext[AgentDeps],
            terrain_type: str,
            has_water: bool,
            has_river: bool,
            has_grass: bool,
            has_wheat: bool,
            placements: list[str],
        ) -> str:
            """注入分层知识文档（L1核心+L2模式+L2.5模板标杆）。

            根据意图字段构建 intent 字典，调用 KnowledgePack.build_system_prompt()
            获取完整的知识文档，供 LLM 生成场景 JSON 时参考。
            """
            intent = {
                "terrain_type": terrain_type,
                "has_water": has_water,
                "has_river": has_river,
                "has_grass": has_grass,
                "has_wheat": has_wheat,
                "placements": placements,
            }
            return inject_knowledge_core(ctx.deps.knowledge, intent)

        @agent.tool
        async def search_assets(
            ctx: RunContext[AgentDeps], keywords: list[str]
        ) -> list[dict]:
            """搜索 UE 资产库中匹配关键词的资产，返回资产详情列表。"""
            entries = search_assets_core(ctx.deps.asset_index, keywords)
            return [e.model_dump() for e in entries]
