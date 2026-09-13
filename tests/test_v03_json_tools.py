"""v0.3 知识注入工具核心函数单元测试。

inject_knowledge_core 复用 KnowledgePack.build_system_prompt()，
asset_paths 和 few_shots 传空列表（由 LLM 通过 search_assets 工具另行获取资产）。
"""
import pytest

from ai.tools.json_tools import inject_knowledge_core


class StubKnowledge:
    """模拟 KnowledgePack 的最小实现，记录调用参数。"""

    def __init__(self, prompt_result="L1核心知识\n\nL2模式文档"):
        self._prompt_result = prompt_result
        self.last_call = None  # 记录最后一次调用参数

    def build_system_prompt(self, intent, asset_paths, few_shots):
        self.last_call = (intent, asset_paths, few_shots)
        return self._prompt_result


def test_inject_knowledge_core_none():
    """knowledge 为 None 时返回空字符串（容错处理）。"""
    assert inject_knowledge_core(None, {"terrain_type": "hills"}) == ""


def test_inject_knowledge_core_basic():
    """正常注入知识文档，返回 build_system_prompt 的结果。"""
    k = StubKnowledge(prompt_result="核心知识+模式文档")
    intent = {"terrain_type": "hills", "has_water": True, "has_grass": True}
    result = inject_knowledge_core(k, intent)
    assert result == "核心知识+模式文档"


def test_inject_knowledge_core_passes_empty_assets_and_few_shots():
    """调用 build_system_prompt 时传空 asset_paths 和 few_shots。"""
    k = StubKnowledge()
    intent = {"terrain_type": "flat"}
    inject_knowledge_core(k, intent)
    _, asset_paths, few_shots = k.last_call
    assert asset_paths == []
    assert few_shots == []


def test_inject_knowledge_core_passes_intent():
    """将 intent 原样传给 build_system_prompt。"""
    k = StubKnowledge()
    intent = {"terrain_type": "features", "has_grass": True}
    inject_knowledge_core(k, intent)
    passed_intent, _, _ = k.last_call
    assert passed_intent == intent
