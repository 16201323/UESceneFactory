"""模式查询工具核心函数 — 包装 PatternLibrary 的查询方法。

核心函数与 Agent 工具装饰分离，便于单元测试时直接传入 Mock 对象。
"""
from ai.models.pattern import Pattern


def search_patterns_core(pattern_library, keywords: list[str], max_results: int = 10) -> list[dict]:
    """搜索模式并返回字典列表。

    Args:
        pattern_library: PatternLibrary 实例（或 None）
        keywords: 搜索关键词列表
        max_results: 最大返回数量

    Returns:
        模式字典列表；pattern_library 为 None 或 keywords 为空时返回空列表
    """
    if pattern_library is None:
        return []
    if not keywords:
        return []
    patterns = pattern_library.search(keywords, max_results=max_results)
    if not patterns:
        return []
    return [p.model_dump() for p in patterns]


def count_patterns_core(pattern_library) -> int:
    """统计模式总数。

    Args:
        pattern_library: PatternLibrary 实例（或 None）

    Returns:
        模式总数；pattern_library 为 None 时返回 0
    """
    if pattern_library is None:
        return 0
    return pattern_library.count()
