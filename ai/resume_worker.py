"""从指定 Stage 续跑 AI 生成管线。

当会话中断在 Stage 2/3 中途时, 利用已保存的 intent/scene_json 从断点继续,
而非从头重跑整个管线, 节省 LLM 调用时间和费用。
"""
from PyQt6.QtCore import QThread, pyqtSignal
from ai.intent_parser import IntentParser
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.generator import SceneGenerator
from ai.validator import ValidationRepairLoop
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever
from ai.session_manager import SessionManager
from ai import get_resource_path
import logging

logger = logging.getLogger(__name__)


class ResumeWorker(QThread):
    """断点续跑管线, 从指定 Stage 开始执行

    复用已保存的中间产物:
      - resume_from="stage2": 复用 intent, 重跑 Stage 2 + Stage 3
      - resume_from="stage3": 复用 intent + scene_json, 重跑 Stage 3

    信号与 AIWorker 保持一致, ChatPanel 可用相同槽函数接收。
    """

    # 信号定义: 与 AIWorker 完全一致, ChatPanel 无需区分来源
    intent_parsed = pyqtSignal(dict)
    json_generated = pyqtSignal(dict)
    validation_done = pyqtSignal(dict, list)
    repair_started = pyqtSignal(int)
    finished_signal = pyqtSignal(dict, bool, str)
    error_occurred = pyqtSignal(str)
    log_line = pyqtSignal(str)
    exp_saved = pyqtSignal(int)

    def __init__(self, client, config, session_id, resume_from,
                 user_desc, intent=None, scene_json=None, feedback=None):
        """初始化续跑 worker

        参数:
            client: LLMClient 实例
            config: 配置 dict
            session_id: 会话 ID, 用于续跑中更新检查点
            resume_from: 续跑起点, "stage2" 或 "stage3"
            user_desc: 原始用户描述
            intent: 已保存的意图 (stage2 续跑需要)
            scene_json: 已保存的场景 JSON (stage3 续跑需要)
            feedback: 反馈信息
        """
        super().__init__()
        self._client = client
        self._config = config
        self._session_id = session_id
        self._resume_from = resume_from
        self._user_desc = user_desc
        self._intent = intent
        self._scene_json = scene_json
        self._feedback = feedback
        self._sm = SessionManager()

    def run(self):
        """执行续跑管线

        资源管理: bank (SQLite) 必须在 finally 中关闭,
        防止 Stage 2/3 任意步骤抛异常时连接泄漏
        """
        bank = None
        try:
            client = self._client
            config = self._config
            user_desc = self._user_desc

            # ---- Stage 1 跳过 (已有 intent) ----
            intent = self._intent
            if intent is None:
                # 如果 stage2 续跑但 intent 丢失, 退回到完整重跑 Stage 1
                self.log_line.emit('Stage 1: 意图解析 (恢复)...')
                intent_parser = IntentParser(client, model=config.get("llm_intent_model"))
                intent = intent_parser.parse(user_desc)
                self.intent_parsed.emit(intent)
                self.log_line.emit('意图解析完成(恢复)')
                self._sm.update_session(self._session_id,
                                        intent=intent, status="stage1_done")

            # ---- Stage 2: 如果 resume_from == "stage3", 跳过 (已有 scene_json) ----
            scene = self._scene_json
            if self._resume_from == "stage2":
                self.log_line.emit('Stage 2: 知识注入 + JSON 生成 (恢复)...')
                self._sm.update_session(self._session_id, status="stage2_running")
                knowledge = KnowledgePack(
                    get_resource_path("data/knowledge"),
                    templates_dir=get_resource_path("data/templates"),
                )
                asset_index = AssetIndex(get_resource_path("asset_catalog.json"))
                bank = ExperienceBank()
                retriever = ExperienceRetriever(bank)
                few_shots = retriever.retrieve(intent, top_k=3)
                self.log_line.emit(f'检索到 {len(few_shots)} 条经验')
                generator = SceneGenerator(client, knowledge, asset_index,
                                           model=config.get("llm_strong_model"))
                scene = generator.generate(user_desc, intent, few_shots)
                self.json_generated.emit(scene)
                self.log_line.emit('JSON 生成完成(恢复)')
                self._sm.update_session(self._session_id,
                                        scene_json=scene, status="stage2_done")
            else:
                # stage3 续跑: scene_json 已有, 但需要初始化 knowledge 和 bank 用于 Stage 3
                knowledge = KnowledgePack(
                    get_resource_path("data/knowledge"),
                    templates_dir=get_resource_path("data/templates"),
                )
                bank = ExperienceBank()
                retriever = ExperienceRetriever(bank)
                few_shots = retriever.retrieve(intent, top_k=3)

            # ---- Stage 3: 验证-修复 (总是执行, 即使 resume_from="stage3") ----
            self.log_line.emit('Stage 3: 验证-修复循环 (恢复)...')
            self._sm.update_session(self._session_id, status="stage3_running")
            loop = ValidationRepairLoop(client, knowledge=knowledge,
                                        model=config.get("llm_strong_model"))
            final_scene, history = loop.validate_and_repair(scene, user_desc, intent=intent)
            self.validation_done.emit(final_scene, history)

            # 判断是否成功: 最后一轮无错误 (用 .get 防 KeyError)
            success = not history[-1].get("errors", []) if history else False

            # 管线末尾: 更新经验使用统计 + 保存新经验
            if few_shots:
                for exp in few_shots:
                    bank.update_usage(exp["id"], success=success)
            if success:
                exp_id = bank.save(user_desc, intent, final_scene, rating=3)
                self.log_line.emit('经验已保存到记忆库')
                if exp_id:
                    self.exp_saved.emit(exp_id)
                    self._sm.update_session(self._session_id, exp_id=exp_id)

            self._sm.update_session(self._session_id,
                                    scene_json=final_scene,
                                    validation_history=history,
                                    status="stage3_done")
            self.finished_signal.emit(final_scene, success, "生成完成(恢复)")
        except Exception as e:
            logger.error("AI 续跑管线异常: %s", e, exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            # 确保在任何路径下 SQLite 连接都被关闭
            if bank is not None:
                try:
                    bank.close()
                except Exception as e:
                    logger.debug("关闭 ExperienceBank 连接失败: %s", e)