"""v0.3 知识注入工具 — JSONBuilderAgent 调用的核心函数。

inject_knowledge_core 复用 KnowledgePack.build_system_prompt()，
asset_paths 和 few_shots 传空列表，因为：
- 资产路径由 LLM 通过 search_assets 工具另行获取并直接写入 JSON
- 模板标杆（L2.5）已包含在 build_system_prompt 的输出中
- 经验 few-shot 由 ScenePlanner 在 SceneBlueprint.experience_refs 中传递
"""
from __future__ import annotations

from typing import Any


def inject_knowledge_core(knowledge: Any, intent: dict) -> str:
    """按意图注入分层知识文档。

    复用 KnowledgePack.build_system_prompt() 的完整逻辑：
    L1 核心知识(~3KB) + L2 模式文档(按意图选择) + L2.5 模板标杆(按意图匹配)
    + L3 资产路径(空) + L4 经验 few-shot(空)。

    参数:
        knowledge: KnowledgePack 实例（为 None 时返回空字符串）
        intent: 意图字典，含 terrain_type/has_water/has_grass/has_wheat/placements 等字段

    返回:
        拼接好的知识文档字符串，供 LLM 生成场景 JSON 时参考
    """
    if knowledge is None:
        return ""
    return knowledge.build_system_prompt(intent, [], [])
