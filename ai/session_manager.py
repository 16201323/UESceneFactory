"""AI 生成会话持久化管理。

负责: 创建/更新/列举/加载/删除/查找未完成会话
存储: ~/.uescenefactory/sessions/session_<时间戳>.json

会话文件记录 AI 生成管线各阶段的中间产物, 支持程序重启后恢复到中断点。
"""
import json
import os
import time
import threading
from pathlib import Path


# 会话状态枚举: 决定恢复后从哪个阶段继续
# stage1_running → 从头重跑; stage1_done → 从 Stage 2 续跑; 以此类推
SESSION_STATUS_VALUES = [
    "stage1_running",  # Stage 1 进行中(程序中断) → 重跑整个管线
    "stage1_done",     # 意图已解析 → 从 Stage 2 续跑
    "stage2_running",  # Stage 2 进行中 → 从 Stage 2 续跑
    "stage2_done",     # 场景 JSON 已生成 → 从 Stage 3 续跑
    "stage3_running",  # Stage 3 进行中 → 从 Stage 3 续跑
    "stage3_done",     # 管线完成, 未采纳 → 显示结果等待用户采纳
    "approved",       # 已采纳, 构建/评分中 → 显示结果+UMAP, 等待评分
    "rated",          # 已评分, 完整结束 → 仅查看, 不提示恢复
]


class SessionManager:
    """AI 生成会话的持久化管理器

    每次用户发起 AI 生成时创建一个会话文件, 各 Stage 完成后更新检查点。
    程序重启后通过 list_sessions() / find_unfinished() 发现未完成会话,
    通过 load_session() 加载后恢复到中断前的状态。
    """

    # 类级别文件锁: 跨实例共享, 防止 ResumeWorker 子线程与 ChatPanel 主线程
    # 并发调用 update_session/append_chat 时 read-modify-write 竞态丢数据
    _file_lock = threading.Lock()

    def __init__(self, sessions_dir=None):
        """初始化会话存储目录

        参数:
            sessions_dir: 自定义目录路径, 默认 ~/.uescenefactory/sessions/
        """
        if sessions_dir is None:
            sessions_dir = str(Path.home() / ".uescenefactory" / "sessions")
        self._sessions_dir = sessions_dir
        os.makedirs(sessions_dir, exist_ok=True)

    def create_session(self, user_desc, feedback=None):
        """创建新会话, 返回 session_id

        参数:
            user_desc: 用户自然语言场景描述
            feedback: 反馈信息(重新生成时传入), 首次生成为 None

        返回: session_id (str), 格式 "session_YYYYMMDD_HHMMSS" 或带毫秒后缀
        """
        # 生成会话 ID: 秒级时间戳; 若同秒内已存在(如反馈重试), 追加毫秒后缀避免覆盖
        session_id = "session_" + time.strftime("%Y%m%d_%H%M%S")
        if os.path.exists(self._filepath(session_id)):
            session_id = session_id + "_" + str(int(time.time() * 1000) % 10000)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "user_desc": user_desc,
            "feedback": feedback,
            "intent": None,
            "scene_json": None,
            "chat_history": [],
            "validation_history": None,
            "exp_id": None,
            "umap_path": None,
            "rating": None,
            "status": "stage1_running",
        }
        self._write(session_id, data)
        return session_id

    def update_session(self, session_id, **kwargs):
        """增量更新会话字段, 自动刷新 updated_at

        参数:
            session_id: 会话 ID
            **kwargs: 要更新的字段 (如 intent=..., status="stage1_done")
        """
        # 加锁保护 read-modify-write 原子性: 防止子线程与主线程并发写入丢数据
        with self._file_lock:
            data = self._read(session_id)
            if data is None:
                return
            data.update(kwargs)
            data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._write(session_id, data)

    def append_chat(self, session_id, msg):
        """向会话的 chat_history 追加一条聊天记录

        参数:
            session_id: 会话 ID
            msg: 已含时间戳前缀的聊天行 (如 "[15:30:00] [用户] ...")
        """
        # 加锁保护 read-modify-write 原子性
        with self._file_lock:
            data = self._read(session_id)
            if data is None:
                return
            data["chat_history"].append(msg)
            data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._write(session_id, data)

    def list_sessions(self):
        """列举所有会话的摘要信息, 按更新时间倒序

        返回: list[dict], 每项含 session_id / user_desc / status / updated_at
        """
        result = []
        if not os.path.isdir(self._sessions_dir):
            return result
        for fname in os.listdir(self._sessions_dir):
            if not fname.startswith("session_") or not fname.endswith(".json"):
                continue
            sid = fname[:-5]  # 去掉 .json 后缀
            data = self._read(sid)
            if data is None:
                continue
            # 摘要: 只取列表展示所需字段, 不含完整 scene_json
            result.append({
                "session_id": sid,
                "user_desc": data.get("user_desc", ""),
                "status": data.get("status", "unknown"),
                "updated_at": data.get("updated_at", ""),
                "rating": data.get("rating"),
            })
        # 按更新时间倒序: 最近的在前
        result.sort(key=lambda x: x["updated_at"], reverse=True)
        return result

    def find_unfinished(self):
        """查找所有未完成会话 (status != 'rated')

        返回: list[dict], 同 list_sessions() 格式但仅含未完成项
        """
        return [s for s in self.list_sessions() if s["status"] != "rated"]

    def load_session(self, session_id):
        """加载完整会话数据

        返回: dict 或 None (会话不存在时)
        """
        return self._read(session_id)

    def delete_session(self, session_id):
        """删除指定会话文件

        返回: True 成功 / False 失败
        """
        fpath = self._filepath(session_id)
        if os.path.isfile(fpath):
            os.remove(fpath)
            return True
        return False

    def _filepath(self, session_id):
        """获取会话文件的完整路径"""
        return os.path.join(self._sessions_dir, session_id + ".json")

    def _read(self, session_id):
        """读取会话 JSON 文件"""
        fpath = self._filepath(session_id)
        if not os.path.isfile(fpath):
            return None
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _write(self, session_id, data):
        """写入会话 JSON 文件"""
        fpath = self._filepath(session_id)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)