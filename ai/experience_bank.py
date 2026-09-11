"""经验记忆库：SQLite 存储，支持保存/检索/去重历史成功场景。"""
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta


class ExperienceBank:
    def __init__(self, db_path=None):
        # 默认存到用户主目录 ~/.uescenefactory/，避免打包后 exe 目录只读
        if db_path is None:
            new_path = str(Path.home() / ".uescenefactory" / "experience.db")
            # 一次性迁移: 旧库(~/.mapforge/experience.db)存在则重命名, 保留 AI 学习数据
            legacy_path = str(Path.home() / ".mapforge" / "experience.db")
            if not os.path.exists(new_path) and os.path.exists(legacy_path):
                try:
                    os.rename(legacy_path, new_path)
                except OSError:
                    pass
            db_path = new_path
        self._db_path = db_path
        dir_path = os.path.dirname(db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_desc       TEXT NOT NULL,
                intent_json     TEXT NOT NULL,
                scene_json      TEXT NOT NULL,
                rating          INTEGER DEFAULT 3,
                tags            TEXT DEFAULT '',
                keywords_text   TEXT DEFAULT '',
                embedding       TEXT DEFAULT '',
                created_at      TEXT NOT NULL,
                used_count      INTEGER DEFAULT 0,
                last_used_at    TEXT,
                success_count   INTEGER DEFAULT 0,
                fail_count      INTEGER DEFAULT 0
            )
        """)
        # 旧库迁移: 若 keywords_text 列不存在则补加并回填
        try:
            self._conn.execute("SELECT keywords_text FROM experiences LIMIT 0")
        except Exception:
            self._conn.execute(
                "ALTER TABLE experiences ADD COLUMN keywords_text TEXT DEFAULT ''")
            for row in self._conn.execute(
                "SELECT id, intent_json FROM experiences"
            ).fetchall():
                kw = json.loads(row["intent_json"]).get("keywords", [])
                self._conn.execute(
                    "UPDATE experiences SET keywords_text=? WHERE id=?",
                    (" ".join(kw), row["id"]))
        # FTS5 全文索引: 独立虚拟表 (非外部内容表), 手动在 save() 中同步
        # 用 MATCH 快速筛选关键词有重叠的候选, 替代全表 Jaccard 扫描
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts USING fts5(
                keywords_text
            )
        """)
        # 旧库回填: 已有记录但 FTS5 索引为空时, 从 keywords_text 回填
        fts_count = self._conn.execute(
            "SELECT COUNT(*) FROM experiences_fts"
        ).fetchone()[0]
        if fts_count == 0:
            for row in self._conn.execute(
                "SELECT id, keywords_text FROM experiences WHERE keywords_text != ''"
            ).fetchall():
                self._conn.execute(
                    "INSERT INTO experiences_fts(rowid, keywords_text) VALUES (?, ?)",
                    (row["id"], row["keywords_text"]))
        self._conn.commit()

    def _find_similar(self, intent, threshold=0.6):
        """查找与当前 intent 关键词 Jaccard 相似度 >= threshold 的已有经验

        优化: 先用 FTS5 MATCH 快速筛选关键词有重叠的候选 (O(k)),
        再对候选集精确计算 Jaccard (避免全表扫描 O(n))。
        """
        my_keywords = set(intent.get("keywords", []))
        if not my_keywords:
            return None
        # FTS5 MATCH 查询: 关键词用双引号包裹以安全转义空格/特殊字符, 显式 OR 连接
        safe_tokens = ['"' + kw.replace('"', '""') + '"' for kw in my_keywords]
        query = " OR ".join(safe_tokens)
        try:
            candidate_rows = self._conn.execute(
                "SELECT e.id, e.intent_json FROM experiences e "
                "JOIN experiences_fts f ON e.id = f.rowid "
                "WHERE experiences_fts MATCH ? ORDER BY rank",
                (query,)
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 不可用时回退全表扫描 (兼容旧数据库)
            candidate_rows = self._conn.execute(
                "SELECT id, intent_json FROM experiences"
            ).fetchall()
        for row in candidate_rows:
            exp_intent = json.loads(row["intent_json"])
            exp_kw = set(exp_intent.get("keywords", []))
            if not exp_kw:
                continue
            jaccard = len(my_keywords & exp_kw) / len(my_keywords | exp_kw)
            if jaccard >= threshold:
                return {"id": row["id"]}  # 仅返回 id, 避免额外 get_by_id 查询
        return None

    def search_by_keywords(self, keywords):
        """FTS5 关键词搜索: 返回匹配的经验 dict 列表。

        封装 FTS5 查询逻辑, 避免外部直接访问 _conn 私有属性。
        关键词含特殊字符时自动转义; FTS5 不可用时回退全表查询。
        """
        if not keywords:
            return self.get_all()
        safe_tokens = ['"' + kw.replace('"', '""') + '"' for kw in keywords]
        query = " OR ".join(safe_tokens)
        try:
            rows = self._conn.execute(
                "SELECT e.* FROM experiences e "
                "JOIN experiences_fts f ON e.id = f.rowid "
                "WHERE experiences_fts MATCH ? ORDER BY rank",
                (query,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except sqlite3.OperationalError:
            return self.get_all()

    def save(self, user_desc, intent, scene, rating=3, tags=""):
        # 去重: 查找相似经验, 存在则更新而非新增
        similar = self._find_similar(intent)
        # 将 keywords 列表转为空格分隔文本 (FTS5 索引和 MATCH 查询用)
        keywords_text = " ".join(intent.get("keywords", []))
        if similar:
            now = datetime.now().isoformat()
            self._conn.execute(
                "UPDATE experiences SET user_desc=?, intent_json=?, scene_json=?, "
                "rating=?, tags=?, keywords_text=?, created_at=? WHERE id=?",
                (user_desc, json.dumps(intent, ensure_ascii=False),
                 json.dumps(scene, ensure_ascii=False), rating, tags,
                 keywords_text, now, similar["id"])
            )
            # 同步 FTS5: 先删旧索引再插新索引 (standalone 表用 DELETE)
            self._conn.execute(
                "DELETE FROM experiences_fts WHERE rowid = ?", (similar["id"],))
            self._conn.execute(
                "INSERT INTO experiences_fts(rowid, keywords_text) VALUES (?, ?)",
                (similar["id"], keywords_text))
            self._conn.commit()
            return similar["id"]
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO experiences (user_desc, intent_json, scene_json, rating, tags, "
            "keywords_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_desc, json.dumps(intent, ensure_ascii=False),
             json.dumps(scene, ensure_ascii=False), rating, tags,
             keywords_text, now)
        )
        exp_id = cursor.lastrowid
        # 同步 FTS5: 插入新索引
        self._conn.execute(
            "INSERT INTO experiences_fts(rowid, keywords_text) VALUES (?, ?)",
            (exp_id, keywords_text))
        self._conn.commit()
        return exp_id

    def get_all(self):
        rows = self._conn.execute("SELECT * FROM experiences ORDER BY created_at DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, exp_id):
        row = self._conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def update_rating(self, exp_id, rating):
        self._conn.execute("UPDATE experiences SET rating = ? WHERE id = ?", (rating, exp_id))
        self._conn.commit()

    def update_usage(self, exp_id, success):
        now = datetime.now().isoformat()
        if success:
            self._conn.execute(
                "UPDATE experiences SET used_count = used_count + 1, "
                "success_count = success_count + 1, last_used_at = ? WHERE id = ?",
                (now, exp_id))
        else:
            self._conn.execute(
                "UPDATE experiences SET used_count = used_count + 1, "
                "fail_count = fail_count + 1, last_used_at = ? WHERE id = ?",
                (now, exp_id))
        self._conn.commit()

    def get_stats(self):
        row = self._conn.execute(
            "SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM experiences"
        ).fetchone()
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        recent = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM experiences WHERE created_at > ?", (week_ago,)
        ).fetchone()
        return {
            "total": row["total"],
            "avg_rating": round(row["avg_rating"] or 0, 2),
            "recent_7d": recent["cnt"],
        }

    def _row_to_dict(self, row):
        return {
            "id": row["id"],
            "user_desc": row["user_desc"],
            "intent": json.loads(row["intent_json"]),
            "scene_json": row["scene_json"],
            "rating": row["rating"],
            "tags": row["tags"],
            "created_at": row["created_at"],
            "used_count": row["used_count"],
            "last_used_at": row["last_used_at"],
            "success_count": row["success_count"],
            "fail_count": row["fail_count"],
        }

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
