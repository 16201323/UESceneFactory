"""模式库 — 基于 SQLite 的可复用模式存储。

PatternLibrary 提供 Pattern 的增删查改功能，支持内存数据库和文件数据库。
通过上下文管理器自动管理数据库连接。
"""
import json
import sqlite3

from ai.models.pattern import Pattern


class PatternLibrary:
    """基于 SQLite 的模式存储库。

    使用 INSERT OR REPLACE 实现幂等写入，支持按名称、标签、内容搜索。
    支持上下文管理器（with 语句）自动关闭连接。
    """

    def __init__(self, db_path: str = ":memory:"):
        """初始化模式库。

        Args:
            db_path: SQLite 数据库路径，默认 ":memory:" 为内存数据库
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self):
        """创建模式表（如果不存在）。"""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patterns (
                name       TEXT PRIMARY KEY,
                content    TEXT DEFAULT '',
                category   TEXT DEFAULT '',
                tags       TEXT DEFAULT '[]',
                use_count  INTEGER DEFAULT 0,
                rating     INTEGER DEFAULT 3
            )
            """
        )
        self._conn.commit()

    def add(self, pattern: Pattern):
        """添加或替换一条模式（同名覆盖）。

        Args:
            pattern: 要存储的 Pattern 对象
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO patterns (name, content, category, tags, use_count, rating) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                pattern.name,
                pattern.content,
                pattern.category,
                json.dumps(pattern.tags),
                pattern.use_count,
                pattern.rating,
            ),
        )
        self._conn.commit()

    def get(self, name: str) -> Pattern | None:
        """按名称获取模式。

        Args:
            name: 模式名称

        Returns:
            Pattern 对象或 None（不存在时）
        """
        row = self._conn.execute(
            "SELECT * FROM patterns WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_pattern(row)

    def search(self, keywords: list[str], max_results: int = 10) -> list[Pattern]:
        """按关键词搜索模式（匹配名称、标签、内容、分类）。

        Args:
            keywords: 搜索关键词列表
            max_results: 最大返回数量

        Returns:
            匹配的 Pattern 列表
        """
        if not keywords:
            return []
        rows = self._conn.execute("SELECT * FROM patterns").fetchall()
        patterns: list[Pattern] = []
        for row in rows:
            pattern = self._row_to_pattern(row)
            if self._match_keywords(pattern, keywords):
                patterns.append(pattern)
                if len(patterns) >= max_results:
                    break
        return patterns

    @staticmethod
    def _match_keywords(pattern: Pattern, keywords: list[str]) -> bool:
        """检查模式是否匹配任一关键词（不区分大小写）。"""
        searchable = " ".join(
            [pattern.name, pattern.content, pattern.category] + pattern.tags
        ).lower()
        return any(kw.lower() in searchable for kw in keywords)

    @staticmethod
    def _row_to_pattern(row: sqlite3.Row) -> Pattern:
        """将数据库行转换为 Pattern 对象。"""
        tags_str = row["tags"] or "[]"
        tags = json.loads(tags_str) if tags_str else []
        return Pattern(
            name=row["name"],
            content=row["content"],
            category=row["category"],
            tags=tags,
            use_count=row["use_count"],
            rating=row["rating"],
        )

    def count(self) -> int:
        """返回模式总数。"""
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM patterns"
        ).fetchone()
        return row["cnt"]

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
