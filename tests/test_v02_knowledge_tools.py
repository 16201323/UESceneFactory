"""v0.2 知识查询工具核心函数单元测试。"""
import pytest

from ai.tools.knowledge_tools import (
    get_design_principles_core,
    get_pattern_docs_core,
    get_template_core,
)


class StubKnowledge:
    """模拟 KnowledgePack 的最小实现。"""

    def __init__(self, patterns=None, template_result=None):
        self._patterns = patterns or {}
        self._template_result = template_result

    def get_pattern(self, name):
        """公共接口：获取模式文档。"""
        if name in self._patterns:
            return self._patterns[name]
        raise FileNotFoundError(name)

    def select_template(self, intent):
        """公共接口：返回预设的模板匹配结果。"""
        return self._template_result


def test_get_pattern_docs_core_none():
    """knowledge 为 None 时返回空字符串。"""
    assert get_pattern_docs_core(None, "pattern.md") == ""


def test_get_pattern_docs_core_success():
    """正常获取模式文档内容。"""
    k = StubKnowledge(patterns={"pattern.md": "content here"})
    assert get_pattern_docs_core(k, "pattern.md") == "content here"


def test_get_pattern_docs_core_not_found():
    """模式不存在时返回空字符串（不抛异常）。"""
    k = StubKnowledge(patterns={})
    assert get_pattern_docs_core(k, "nonexistent.md") == ""


def test_get_template_core_none():
    """knowledge 为 None 时返回 None。"""
    assert get_template_core(None, ["kw"], "hills") is None


def test_get_template_core_success():
    """正常匹配模板返回文件名。"""
    k = StubKnowledge(template_result=("hills.json", "{}"))
    result = get_template_core(k, ["hill", "terrain"], "hills")
    assert result == "hills.json"


def test_get_template_core_no_match():
    """无匹配模板时返回 None。"""
    k = StubKnowledge(template_result=None)
    assert get_template_core(k, ["unknown"], "flat") is None


def test_get_design_principles_core_none():
    """knowledge 为 None 时返回空列表。"""
    assert get_design_principles_core(None, "flat") == []


def test_get_design_principles_core_success():
    """正常获取设计原则列表。"""
    k = StubKnowledge(patterns={"design_principles.md": "rule1\nrule2\nrule3"})
    result = get_design_principles_core(k, "flat")
    assert result == ["rule1", "rule2", "rule3"]
