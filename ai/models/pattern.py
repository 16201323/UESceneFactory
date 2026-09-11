"""场景模式模型 — 可复用的场景生成知识单元。

Pattern 是 PatternLibrary 的存储单元，表示一条经过验证的可复用模式。
每条模式包含名称、内容、分类、标签、使用次数和评分。
"""
from pydantic import BaseModel, Field


class Pattern(BaseModel):
    """可复用的场景模式。

    Attributes:
        name: 模式唯一名称（如 "mountain_ridge_dense"）
        content: 模式内容（JSON 字符串或 Markdown 文本）
        category: 模式分类（如 "terrain", "lighting", "placement"）
        tags: 可搜索的标签列表
        use_count: 被使用次数（默认 0）
        rating: 质量评分 1-5（默认 3）
    """
    name: str
    content: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    use_count: int = 0
    rating: int = 3
