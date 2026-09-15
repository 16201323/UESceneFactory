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

    # 阶段一系统提示词 — 语义理解是整个流水线质量的基础
    # 核心能力:概念展开(把简短词展开成符合中国环境常识的要素组合)
    # 修复要点:
    #   1. terrain_type 必须用合法枚举(flat/ridge/hill/noise/hill_ridge/
    #      features/terraced/karst/gully),与 validate_scene_json.py 对齐
    #   2. 增加概念展开规则,避免"农村"只输出单一地形(无树无房)
    #   3. 增加 few-shot 示例教 LLM 做意图展开
    def _system_prompt(self) -> str:
        return (
            "你是一个 UE5 场景规划专家。你的核心任务是:把用户简短的自然语言描述\n"
            "展开成符合中国环境常识的、要素丰富的场景蓝图(SceneBlueprint)。\n\n"
            "==== 第0步:概念展开(最关键)====\n"
            "用户描述往往很简短(如\"农村\"\"山区\"\"海岸\"),你需要根据中国环境常识\n"
            "把它展开成完整的要素组合。绝不能只输出单一地形而缺少植被/建筑/水系。\n"
            "概念展开规则(按用户描述的关键词选择):\n"
            "- 农村/乡村/村庄 → 山脉背景+溪流+成片森林+村落房屋(必含 village 和 forest)\n"
            "  例: terrain_type=features 或 hill_ridge, has_water=true, has_river=true,\n"
            "      has_grass=true, placements=[\"village\",\"forest\"],\n"
            "      keywords=[\"山\",\"树\",\"房屋\",\"河流\",\"草地\"]\n"
            "- 干旱农村/西北村庄 → 沟壑+村落+枯树/稀疏树\n"
            "  例: terrain_type=gully, has_water=false, has_grass=false,\n"
            "      placements=[\"village\",\"forest\"], keywords=[\"沟壑\",\"枯树\",\"房屋\"]\n"
            "- 山区/山里/山野 → 连绵山脉+森林+可选村落\n"
            "  例: terrain_type=hill_ridge, has_grass=true, placements=[\"forest\"],\n"
            "      keywords=[\"山\",\"树\",\"草地\"], 可选 village\n"
            "- 平原/田野/农田 → 平地+草地或麦田+可选村落\n"
            "  例: terrain_type=flat, has_grass=true, has_wheat=true,\n"
            "      placements=[\"village\"], keywords=[\"草地\",\"麦田\",\"房屋\"]\n"
            "- 海岸/海边/湖边 → 平地+大片水域+可选森林\n"
            "  例: terrain_type=flat, has_water=true, placements=[\"forest\"],\n"
            "      keywords=[\"水\",\"树\",\"沙滩\"]\n"
            "- 喀斯特/峰林 → 喀斯特地貌+可选植被\n"
            "  例: terrain_type=karst, keywords=[\"峰林\",\"石\",\"树\"]\n"
            "- 梯田/台阶 → 梯田地形+可选村落\n"
            "  例: terrain_type=terraced, has_grass=true, keywords=[\"梯田\",\"田\",\"房屋\"]\n"
            "- 城市/城镇/市区 → 高楼电塔+平地+可选光伏\n"
            "  例: terrain_type=flat, has_grass=false, placements=[\"tower\",\"pv_solar\"],\n"
            "      keywords=[\"高楼\",\"电塔\",\"路\",\"光伏\"]\n"
            "- 沙漠/戈壁/荒漠 → 沙丘起伏+无草地+稀疏枯树\n"
            "  例: terrain_type=noise, has_water=false, has_grass=false,\n"
            "      placements=[\"forest\"], keywords=[\"沙丘\",\"枯树\",\"沙\"]\n"
            "- 雪山/雪原/高原雪山 → 连绵山脉+雪覆盖+无草地\n"
            "  例: terrain_type=hill_ridge, has_grass=false,\n"
            "      keywords=[\"雪山\",\"雪\",\"岩石\"], 可选少量 forest\n"
            "- 森林/密林/树林 → 以大片森林为主+平地或缓丘\n"
            "  例: terrain_type=hill, has_grass=true, placements=[\"forest\"],\n"
            "      keywords=[\"树\",\"密林\",\"草地\"]\n"
            "- 草原/草甸/牧场 → 平地+大片草地+可选牧民点\n"
            "  例: terrain_type=flat, has_grass=true, placements=[\"village\"],\n"
            "      keywords=[\"草地\",\"草\",\"牧\"]\n"
            "- 峡谷/河谷/山谷 → 陡峭山脊+河流穿行\n"
            "  例: terrain_type=ridge, has_river=true, placements=[\"forest\"],\n"
            "      keywords=[\"峡谷\",\"崖\",\"河\",\"树\"]\n"
            "- 机场/停机坪/跑道 → 平地+停机设施\n"
            "  例: terrain_type=flat, placements=[\"heliport\"],\n"
            "      keywords=[\"停机坪\",\"跑道\",\"塔\"]\n"
            "- 光伏电站/太阳能场 → 平地+大片光伏板\n"
            "  例: terrain_type=flat, placements=[\"pv_solar\"],\n"
            "      keywords=[\"光伏\",\"板\",\"支架\"]\n"
            "- 湿地/沼泽 → 平地+水域+草甸\n"
            "  例: terrain_type=flat, has_water=true, has_grass=true,\n"
            "      keywords=[\"水\",\"草\",\"芦苇\"]\n"
            "- 海岛/孤岛 → 平地+四面水域+少量森林\n"
            "  例: terrain_type=flat, has_water=true, placements=[\"forest\"],\n"
            "      keywords=[\"岛\",\"海\",\"树\",\"沙滩\"]\n"
            "- 工业区/工厂区 → 平地+电塔+光伏+少量树\n"
            "  例: terrain_type=flat, placements=[\"tower\",\"pv_solar\"],\n"
            "      keywords=[\"厂房\",\"电塔\",\"路\",\"光伏\"]\n"
            "未匹配以上时,默认按\"综合自然场景\"展开:山脉+河流+森林+草地。\n\n"
            "==== 第1步:字段取值规则 ====\n"
            "terrain_type 合法枚举(必须严格使用以下值,禁止自创):\n"
            "  flat(平地) / ridge(山脊) / hill(单丘) / noise(噪声起伏) /\n"
            "  hill_ridge(连绵山脉) / features(综合地形,最常用,默认值) /\n"
            "  terraced(梯田) / karst(喀斯特) / gully(黄土沟壑)\n"
            "  映射提示: \"山\"→hill_ridge/ridge, \"坡\"→hill, \"沟\"→gully,\n"
            "            \"喀斯特/峰林\"→karst, \"梯田\"→terraced, \"平\"→flat,\n"
            "            \"综合/自然/丰富\"→features\n"
            "has_water: 描述提及湖/潭/水域 → true, 否则按概念展开判断\n"
            "has_river: 描述提及河/溪/流 → true, 否则按概念展开判断\n"
            "has_grass: 有草地/植被 → true, 干旱枯黄场景 → false\n"
            "has_wheat: 提及麦田/农田 → true, 否则 false\n"
            "placements(可多选,必填充足): village/tower/forest/heliport/pv_solar\n"
            "  农村/山区/海岸等场景至少组合 2 类(village+forest 是农村标配)\n"
            "  禁止只输出单一空地形而不放任何 placements\n"
            "keywords: 提取供 Stage2 搜索资产的中文关键词(山/树/房屋/河流/草地/麦田等),\n"
            "  要覆盖概念展开后的所有要素,数量 4~8 个\n"
            "scene_type: 填 \"general\"(当前未细分类别,固定值即可)\n"
            "size_m: 从描述提取场景物理尺寸 [长,宽] 米,空列表表示用默认尺寸\n"
            "  提取规则: \"Nkm*Nkm\"→[N*1000,N*1000], \"Nm*Nm\"→[N,N],\n"
            "            \"Nkm×Nkm\"/\"N公里\"同理。例: \"2km*2km\"→[2000,2000],\n"
            "            \"1km×2km\"→[1000,2000]。未提及尺寸→[]\n"
            "region: 从描述提取地域名(省/地区),用于体现地域植被与水系特征\n"
            "  例: \"江西\"→\"江西\", \"西北\"→\"西北\", \"南方\"→\"南方\"。未提及→空串\n"
            "user_desc: 原样复制用户输入的完整描述,保留氛围修饰词供 Stage2 参考\n"
            "lighting_style: warm_morning/cool_noon/golden_sunset\n"
            "  用户提及时间按描述选;未提及默认 warm_morning(暖晨,适合自然场景)\n"
            "weather_style: clear/cloudy/foggy/light_rain\n"
            "  用户提及天气按描述选;未提及默认 clear\n\n"
            "==== 第2~5步:工具调用 ====\n"
            "2. 调用 search_assets(keywords) 搜索可用资产,确认关键词有对应资产\n"
            "3. 调用 search_experience(keywords, terrain_type) 检索相似历史案例\n"
            "4. 调用 get_design_principles(scene_type) 获取设计原则\n"
            "5. 调用 get_template(keywords, terrain_type) 匹配模板标杆\n\n"
            "==== 输出 ====\n"
            "输出 SceneBlueprint。要素要充足:农村必含 village+forest,\n"
            "山区必含 forest,确保后续阶段能生成有树有房的丰富场景,而非空旷单调地形。\n"
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
