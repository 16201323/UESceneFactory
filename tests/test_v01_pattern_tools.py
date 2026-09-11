"""v0.1 模式工具核心函数单元测试。"""
import pytest

from ai.models.pattern import Pattern
from ai.pattern_library import PatternLibrary
from ai.tools.pattern_tools import count_patterns_core, search_patterns_core


def test_search_patterns_core_none_library():
    """pattern_library 为 None 时返回空列表。"""
    assert search_patterns_core(None, ["keyword"]) == []


def test_search_patterns_core_empty_keywords():
    """空关键词列表返回空列表。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="test"))
    assert search_patterns_core(lib, []) == []
    lib.close()


def test_search_patterns_core_results():
    """正常搜索返回字典列表。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="mountain_ridge", content="terrain", tags=["hill"]))
    results = search_patterns_core(lib, ["mountain"])
    assert len(results) == 1
    assert isinstance(results, list)
    assert isinstance(results[0], dict)
    assert results[0]["name"] == "mountain_ridge"
    lib.close()


def test_search_patterns_core_no_match():
    """无匹配结果时返回空列表。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="mountain"))
    assert search_patterns_core(lib, ["ocean"]) == []
    lib.close()


def test_count_patterns_core_none_library():
    """pattern_library 为 None 时返回 0。"""
    assert count_patterns_core(None) == 0


def test_count_patterns_core():
    """正常统计返回正确的模式数量。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="p1"))
    lib.add(Pattern(name="p2"))
    assert count_patterns_core(lib) == 2
    lib.close()
