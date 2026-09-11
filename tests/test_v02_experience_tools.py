"""v0.2 经验检索工具核心函数单元测试。"""
import pytest

from ai.models.blueprint import ExperienceRef
from ai.tools.experience_tools import search_experience_core


class StubRetriever:
    """模拟 ExperienceRetriever 的最小实现。"""

    def __init__(self, experiences=None):
        self._experiences = experiences or []

    def retrieve(self, intent, top_k=3):
        """返回前 top_k 条经验（忽略 intent 匹配逻辑）。"""
        return self._experiences[:top_k]


def test_search_experience_core_none():
    """retriever 为 None 时返回空列表。"""
    assert search_experience_core(None, {"terrain_type": "flat"}) == []


def test_search_experience_core_none_intent():
    """intent 为 None 时不崩溃，内部转为空字典。"""
    retriever = StubRetriever(experiences=[])
    assert search_experience_core(retriever, None) == []


def test_search_experience_core_results():
    """正常检索返回 ExperienceRef 列表。"""
    retriever = StubRetriever(
        experiences=[
            {"id": 1, "user_desc": "a mountain scene", "rating": 4, "intent": {"keywords": ["peak"]}},
            {"id": 2, "user_desc": "a valley scene", "rating": 3, "intent": {"keywords": ["river"]}},
        ]
    )
    results = search_experience_core(retriever, {"terrain_type": "hills"})
    assert len(results) == 2
    assert isinstance(results[0], ExperienceRef)
    assert results[0].id == 1


def test_search_experience_core_scene_type_mapping():
    """scene_type 从输入 intent 映射，而非经验自身的 intent。"""
    retriever = StubRetriever(
        experiences=[
            {
                "id": 1,
                "user_desc": "scene",
                "rating": 4,
                "intent": {"terrain_type": "hills", "keywords": ["hill"]},
            },
        ]
    )
    # 输入 intent 的 terrain_type = "flat"，经验自身的 terrain_type = "hills"
    results = search_experience_core(retriever, {"terrain_type": "flat"})
    assert len(results) == 1
    assert results[0].scene_type == "flat"  # 来自输入 intent
    assert results[0].keywords == ["hill"]  # 来自经验自身的 intent


def test_search_experience_core_user_desc_truncation():
    """user_desc 超过 200 字符时被截断。"""
    long_desc = "x" * 250
    retriever = StubRetriever(
        experiences=[
            {"id": 1, "user_desc": long_desc, "rating": 3, "intent": {}},
        ]
    )
    results = search_experience_core(retriever, {"terrain_type": "flat"})
    assert len(results[0].user_desc) == 200


def test_search_experience_core_keywords_extraction():
    """keywords 从经验自身的 intent 提取。"""
    retriever = StubRetriever(
        experiences=[
            {"id": 1, "user_desc": "scene", "rating": 3, "intent": {"keywords": ["a", "b", "c"]}},
        ]
    )
    results = search_experience_core(retriever, {"terrain_type": "flat"})
    assert results[0].keywords == ["a", "b", "c"]
