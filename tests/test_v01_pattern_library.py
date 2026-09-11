"""v0.1 PatternLibrary 单元测试。"""
import pytest

from ai.models.pattern import Pattern
from ai.pattern_library import PatternLibrary


def test_init_memory_db():
    """使用内存数据库初始化不报错。"""
    lib = PatternLibrary()
    assert lib is not None
    lib.close()


def test_add_and_get():
    """添加模式后，可按名称获取。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="test", content="hello"))
    p = lib.get("test")
    assert p is not None
    assert p.name == "test"
    assert p.content == "hello"
    lib.close()


def test_get_nonexistent():
    """获取不存在的模式返回 None。"""
    lib = PatternLibrary()
    assert lib.get("nonexistent") is None
    lib.close()


def test_search_by_name():
    """按名称关键词搜索模式。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="mountain_ridge", tags=["terrain"]))
    lib.add(Pattern(name="flat_plain", tags=["terrain"]))
    results = lib.search(["mountain"])
    assert len(results) == 1
    assert results[0].name == "mountain_ridge"
    lib.close()


def test_search_by_tags():
    """按标签关键词搜索模式。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="p1", tags=["water", "river"]))
    lib.add(Pattern(name="p2", tags=["mountain"]))
    results = lib.search(["river"])
    assert len(results) == 1
    assert results[0].name == "p1"
    lib.close()


def test_search_empty_keywords():
    """空关键词列表返回空结果。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="test"))
    assert lib.search([]) == []
    lib.close()


def test_count_empty():
    """空库的 count() 返回 0。"""
    lib = PatternLibrary()
    assert lib.count() == 0
    lib.close()


def test_count_after_add():
    """添加 3 条模式后 count() 返回 3。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="p1"))
    lib.add(Pattern(name="p2"))
    lib.add(Pattern(name="p3"))
    assert lib.count() == 3
    lib.close()


def test_context_manager():
    """上下文管理器正常工作。"""
    with PatternLibrary() as lib:
        lib.add(Pattern(name="test"))
        assert lib.count() == 1


def test_add_replace():
    """同名模式添加两次，后者覆盖前者。"""
    lib = PatternLibrary()
    lib.add(Pattern(name="test", content="old", rating=3))
    lib.add(Pattern(name="test", content="new", rating=5))
    assert lib.count() == 1
    p = lib.get("test")
    assert p.content == "new"
    assert p.rating == 5
    lib.close()
