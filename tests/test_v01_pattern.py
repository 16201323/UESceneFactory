"""v0.1 Pattern 模型单元测试。"""
import pytest

from ai.models.pattern import Pattern


def test_pattern_minimal():
    """仅传 name 时，其余字段使用默认值。"""
    p = Pattern(name="test_pattern")
    assert p.name == "test_pattern"
    assert p.content == ""
    assert p.category == ""
    assert p.tags == []
    assert p.use_count == 0
    assert p.rating == 3


def test_pattern_full():
    """传入所有字段时，值正确存储。"""
    p = Pattern(
        name="mountain_ridge",
        content="some json content",
        category="terrain",
        tags=["mountain", "ridge"],
        use_count=5,
        rating=4,
    )
    assert p.name == "mountain_ridge"
    assert p.content == "some json content"
    assert p.category == "terrain"
    assert p.tags == ["mountain", "ridge"]
    assert p.use_count == 5
    assert p.rating == 4


def test_pattern_tags_default_empty():
    """不传 tags 时，默认为空列表而非 None。"""
    p = Pattern(name="test")
    assert p.tags == []
    assert isinstance(p.tags, list)


def test_pattern_model_dump():
    """model_dump() 返回包含所有字段的字典。"""
    p = Pattern(name="test", content="content", tags=["a", "b"])
    d = p.model_dump()
    assert d["name"] == "test"
    assert d["content"] == "content"
    assert d["tags"] == ["a", "b"]
    assert d["use_count"] == 0
    assert d["rating"] == 3
