"""测试: AgentPipelinePanel 全流程 GUI 交互 — 自动继续、手风琴、异常恢复

模拟用户操作场景:
  1. 勾选/取消"自动继续"复选框
  2. 点击"确认并继续 Stage 1"按钮
  3. 点击"采纳并构建 UMAP"按钮
  4. 折叠面板展开/收起 (手风琴模式)
  5. 异常发生后按钮重新启用

通过 MockAgentWorker(QObject) 发射信号模拟 AgentWorker 各阶段完成,
避免真实线程和 LLM 调用, 专注于 UI 交互逻辑的正确性验证。
"""
import sys
import os
import threading
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication


# ============================================================================
# MockAgentWorker: 纯 QObject 版, 发射与 AgentWorker 完全一致的信号
# ============================================================================

class MockAgentWorker(QObject):
    """模拟 AgentWorker, 不启动线程/不调 LLM, 通过 emit 信号驱动 UI 回调"""
    stage0_done = pyqtSignal(str)
    stage1_done = pyqtSignal(str)
    stage2_done = pyqtSignal(str)
    stage3_done = pyqtSignal(str)
    finished_signal = pyqtSignal(dict, bool, str)
    error_occurred = pyqtSignal(str)
    log_line = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._enriched_text = ""
        self._enrich_event = threading.Event()

    def confirm_enrichment(self, text):
        self._enriched_text = text
        self._enrich_event.set()


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def qapp():
    """确保 QApplication 单例在整个模块内存在"""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _process_events(times=5):
    """多次处理 Qt 事件循环, 确保 QTimer.singleShot(0) 等延迟回调已执行"""
    for _ in range(times):
        QApplication.processEvents()


# ============================================================================
# 测试: 自动继续功能
# ============================================================================

class TestAutoContinue:
    """自动继续功能测试: 勾选后 Stage 0 自动确认 + 完成后自动采纳"""

    def test_auto_confirm_stage0_on_signal(self, qapp):
        """[场景A] 勾选自动继续 → stage0_done 信号到达 → 自动调 confirm_enrichment"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True
        panel._auto_continue_checkbox.setChecked(True)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.log_line.connect(panel._on_log)
        worker.stage0_done.connect(panel._on_stage0)

        narrative = "一片辽阔的平原, 天际线延伸至远方, 有蜿蜒的河流穿过"
        worker.stage0_done.emit(narrative)
        _process_events()

        assert worker._enriched_text == narrative, "自动继续应将叙事文本传给 worker.confirm_enrichment"
        assert panel._stage0_confirm_btn.isEnabled() is False, "自动确认后按钮应禁用"
        assert panel._progress.value() == 20, "进度应为 20"

    def test_auto_approve_on_finished(self, qapp):
        """[场景B] 勾选自动继续 + 成功 → finished_signal → 自动调 _on_approve"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True
        panel._auto_continue_checkbox.setChecked(True)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.finished_signal.connect(panel._on_finished)

        scene = {"scene": {"name": "TestScene", "target_level": "/Game/Maps/Test"}}
        worker.finished_signal.emit(scene, True, "多智能体流水线完成")
        _process_events()

        assert panel._approve_btn.isEnabled() is False, "自动采纳后按钮应禁用"
        assert panel._last_scene == scene, "最终场景应已保存"
        chat = panel._chat_history.toPlainText()
        assert "已采纳" in chat, "聊天记录应显示已采纳"
        assert "保存场景 JSON 失败" not in chat, "不应有保存失败错误"

    def test_full_pipeline_with_auto_continue(self, qapp):
        """[场景C] 完整流水线全自动: Stage0→1→2→3→采纳, 全程不阻塞"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True
        panel._auto_continue_checkbox.setChecked(True)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.log_line.connect(panel._on_log)
        worker.stage0_done.connect(panel._on_stage0)
        worker.stage1_done.connect(panel._on_stage1)
        worker.stage2_done.connect(panel._on_stage2)
        worker.stage3_done.connect(panel._on_stage3)
        worker.finished_signal.connect(panel._on_finished)

        # Stage 0
        worker.stage0_done.emit("扩写后的叙事文本")
        _process_events()
        assert worker._enriched_text == "扩写后的叙事文本", "Stage0 自动确认应已执行"
        assert panel._stage0_confirm_btn.isEnabled() is False

        # Stage 1
        worker.stage1_done.emit('{"blueprint": "test"}')
        _process_events()
        assert panel._progress.value() in (40, 33), "Stage1 后进度应更新"

        # Stage 2
        worker.stage2_done.emit('{"scene": {"name": "T", "target_level": "/G/M"}}')
        _process_events()
        assert panel._progress.value() in (70, 66)

        # Stage 3
        worker.stage3_done.emit('{"report": "ok", "is_valid": true}')
        _process_events()

        # Finished (成功)
        scene = {"scene": {"name": "T", "target_level": "/G/M"}}
        worker.finished_signal.emit(scene, True, "流水线完成")
        _process_events()

        assert panel._approve_btn.isEnabled() is False, "自动采纳后按钮应禁用"
        chat = panel._chat_history.toPlainText()
        assert "已采纳" in chat, "最终应触发自动采纳"

    def test_manual_mode_stage0(self, qapp):
        """[场景D] 不勾选自动继续 → Stage 0 完成时按钮保持启用, 需手动点击确认"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True
        panel._auto_continue_checkbox.setChecked(False)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.log_line.connect(panel._on_log)
        worker.stage0_done.connect(panel._on_stage0)

        narrative = "一片辽阔的平原"
        worker.stage0_done.emit(narrative)
        _process_events()

        assert worker._enriched_text == "", "不勾选自动继续, 不应自动调用 confirm_enrichment"
        assert panel._stage0_confirm_btn.isEnabled() is True, "确认按钮应保持启用供用户操作"

        # 模拟用户手动点击确认按钮
        panel._on_confirm_stage0()
        assert worker._enriched_text == narrative, "手动确认后应通知 worker"
        assert panel._stage0_confirm_btn.isEnabled() is False, "手动确认后按钮应禁用"

    def test_manual_mode_finished(self, qapp):
        """[场景E] 不勾选自动继续 → 完成时采纳按钮保持启用, 需手动点击采纳"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True
        panel._auto_continue_checkbox.setChecked(False)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.finished_signal.connect(panel._on_finished)

        scene = {"scene": {"name": "T", "target_level": "/G/M"}}
        worker.finished_signal.emit(scene, True, "流水线完成")
        _process_events()

        assert panel._approve_btn.isEnabled() is True, "手动模式下采纳按钮应保持启用"
        assert "已采纳" not in panel._chat_history.toPlainText(), "不应自动采纳"

    def test_no_auto_approve_on_failure(self, qapp):
        """[场景F] 自动继续模式下校验失败 → 不应自动采纳, 按钮保持启用"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True
        panel._auto_continue_checkbox.setChecked(True)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.finished_signal.connect(panel._on_finished)

        scene = {"scene": {"name": "T"}}
        worker.finished_signal.emit(scene, False, "校验发现错误")
        _process_events()

        assert panel._approve_btn.isEnabled() is True, "校验失败时不应自动采纳, 供用户审核"
        assert "已采纳" not in panel._chat_history.toPlainText(), "失败不应自动采纳"


# ============================================================================
# 测试: 手风琴模式
# ============================================================================

class TestAccordion:
    """手风琴模式: 展开新面板时自动收起其他面板"""

    def test_accordion_collapses_others(self, qapp):
        """展开 Stage 1 时 Stage 0 自动收起"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel.show()  # 需显示面板才能用 isVisible() 检测可见性

        # 展开 Stage 0
        panel._stage0_btn.setChecked(True)
        _process_events()
        assert panel._stage0_content.isVisible() is True

        # 展开 Stage 1 → Stage 0 应自动收起
        panel._stage1_btn.setChecked(True)
        _process_events()
        assert panel._stage1_content.isVisible() is True
        assert panel._stage0_content.isVisible() is False
        assert panel._stage0_btn.isChecked() is False

    def test_accordion_all_collapsed_initially(self, qapp):
        """所有面板初始为折叠状态"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        assert panel._stage0_content.isVisible() is False
        assert panel._stage1_content.isVisible() is False
        assert panel._stage2_content.isVisible() is False
        assert panel._stage3_content.isVisible() is False


# ============================================================================
# 测试: 异常恢复
# ============================================================================

class TestErrorRecovery:
    """异常回调后按钮重新启用"""

    def test_error_re_enables_buttons(self, qapp):
        """_on_error 应重新启用确认/采纳按钮, 防止界面锁死"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True

        # 模拟流水线运行中按钮全部被禁用的状态
        panel._send_btn.setEnabled(False)
        panel._approve_btn.setEnabled(False)
        panel._stage0_confirm_btn.setEnabled(False)

        worker = MockAgentWorker()
        panel._worker = worker
        worker.error_occurred.connect(panel._on_error)

        worker.error_occurred.emit("API 调用失败, 请检查网络连接和 API Key")
        _process_events()

        assert panel._send_btn.isEnabled() is True, "发送按钮应重新启用"
        assert panel._approve_btn.isEnabled() is True, "采纳按钮应重新启用"
        assert panel._stage0_confirm_btn.isEnabled() is True, "Stage0 确认按钮应重新启用"
        chat = panel._chat_history.toPlainText()
        assert "API 调用失败" in chat, "错误消息应显示在聊天历史"


# ============================================================================
# 测试: 边界情况
# ============================================================================

class TestEdgeCases:
    """边界和防御性检查"""

    def test_confirm_empty_content(self, qapp):
        """_on_confirm_stage0 编辑区为空时应拒绝并提示"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._enable_enrich = True

        worker = MockAgentWorker()
        panel._worker = worker

        # 空内容确认
        panel._stage0_content.setPlainText("")
        panel._on_confirm_stage0()

        assert worker._enriched_text == "", "空内容不应传递给 worker"
        assert "扩写内容为空" in panel._chat_history.toPlainText()

    def test_approve_without_scene(self, qapp):
        """_on_approve 无 _last_scene 时应直接返回, 不报错"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._last_scene = None

        panel._on_approve()
        assert "已采纳" not in panel._chat_history.toPlainText()

    def test_reentry_guard_on_approve(self, qapp):
        """_on_approve 重入防护: 按钮已禁用时再次调用应直接返回"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel._last_scene = {"scene": {"name": "T", "target_level": "/G/M"}}
        panel._approve_btn.setEnabled(False)  # 模拟已执行过一次

        panel._on_approve()
        # 不报错, 不重复执行, 聊天无"已采纳"
        assert "已采纳" not in panel._chat_history.toPlainText()

    def test_accordion_loopback_safety(self, qapp):
        """手风琴互斥不应导致栈溢出: setChecked(False) 触发 _on_stage_toggle 不递归"""
        from scripts.mapforge_app import AgentPipelinePanel
        panel = AgentPipelinePanel({})
        panel.show()  # 需显示面板才能用 isVisible() 检测可见性

        # 展开所有面板 (手风琴应确保最终只展开最后一个)
        panel._stage0_btn.setChecked(True)
        panel._stage1_btn.setChecked(True)
        panel._stage2_btn.setChecked(True)
        panel._stage3_btn.setChecked(True)
        _process_events()

        assert panel._stage3_content.isVisible() is True, "最后展开的面板应可见"
        assert panel._stage0_content.isVisible() is False, "先前展开的面板应自动收起"
        assert panel._stage1_content.isVisible() is False
        assert panel._stage2_content.isVisible() is False