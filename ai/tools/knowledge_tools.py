"""知识查询工具核心函数 — 包装 KnowledgePack 的私有方法。

核心函数与 Agent 工具装饰分离，便于单元测试时直接传入 Stub 对象。
"""


def get_pattern_docs_core(knowledge, pattern_name: str) -> str:
    """获取模式文档内容。

    Args:
        knowledge: KnowledgePack 实例（或 None）
        pattern_name: 模式文件名

    Returns:
        模式文档内容字符串；knowledge 为 None 或文件不存在时返回空字符串
    """
    if knowledge is None:
        return ""
    try:
        return knowledge.get_pattern(pattern_name)
    except Exception:
        return ""


def get_template_core(knowledge, keywords: list[str], terrain_type: str) -> str | None:
    """匹配模板文件名。

    Args:
        knowledge: KnowledgePack 实例（或 None）
        keywords: 用户关键词列表
        terrain_type: 地形类型

    Returns:
        模板文件名或 None；knowledge 为 None 或无匹配时返回 None
    """
    if knowledge is None:
        return None
    intent = {
        "keywords": keywords if keywords else [],
        "terrain_type": terrain_type or "features",
    }
    result = knowledge.select_template(intent)
    if result is None:
        return None
    filename, _ = result
    return filename


def get_design_principles_core(knowledge, scene_type: str) -> list[str]:
    """获取设计原则列表。

    Args:
        knowledge: KnowledgePack 实例（或 None）
        scene_type: 场景类型（当前未直接使用，预留扩展）

    Returns:
        设计原则字符串列表；knowledge 为 None 或无内容时返回空列表
    """
    if knowledge is None:
        return []
    try:
        content = knowledge.get_pattern("design_principles.md")
    except Exception:
        return []
    if not content:
        return []
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    return lines
