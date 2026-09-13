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
        """系统提示词 — 指导 LLM 生成符合 build_scene.py 规范的场景 JSON。"""
        return (
            "你是一个 UE5 场景 JSON 生成专家。根据输入的场景蓝图（SceneBlueprint JSON），"
            "调用工具注入知识文档和搜索资产，生成完整的场景 JSON。\n\n"
            "关键步骤：\n"
            "1. 解析蓝图中的意图字段（terrain_type/has_water/has_river/has_grass/"
            "has_wheat/placements/keywords）\n"
            "2. 调用 inject_knowledge 注入分层知识文档（核心知识+模式文档+模板标杆）\n"
            "3. 调用 search_assets 搜索蓝图 keywords 对应的 UE 资产路径\n"
            "4. 根据知识文档和资产路径，生成符合 build_scene.py 规范的场景 JSON\n\n"
            "JSON 顶层结构：scene(必填) / landscape / ground / placements / lighting / weather\n"
            "资产路径格式：/Game/类别/Name（不含 .uasset 后缀）\n"
            "单位：location/spacing=厘米(cm)，height_pattern 内=米(m)\n"
            "weight 范围：0~1 浮点数\n\n"
            "⚠️ 放置条目 asset 字段规则（重要）：\n"
            "- static/instanced_grid/blueprint/crop_field 类型：asset 必须是非空的 /Game/ 路径\n"
            "- group 类型：用 asset_prefix 代替 asset，asset_prefix 也必须非空\n"
            "- 如果 search_assets 未找到匹配资产，不要生成该放置条目（宁可省略也不要留空）\n"
            "- 严禁输出 asset 为空字符串的占位条目，空 asset 会导致 UE 编辑器卡死\n\n"
            "⚠️ 贴地规则（重要）：\n"
            "- 所有放置条目默认贴地(snap_to_ground=true)：树木/房屋/栅栏/灯柱等自动跟随地形起伏\n"
            "- 放置条目的 grid/field/顶层均可写 snap_to_ground 字段，默认 true 无需显式写出\n"
            "- 仅当资产需要悬空（如桥梁、高架、飞行物）时才写 \"snap_to_ground\": false 并指定 location Z\n"
            "- 植被类(Tree/Pine/Grass/Plant/Flower/Bush/Crop/Wheat)必须保持贴地，不可设为 false\n\n"
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
