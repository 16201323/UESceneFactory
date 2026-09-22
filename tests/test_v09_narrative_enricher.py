"""v2.9.0 NarrativeEnricherAgent + AgentWorker Stage0 单元测试。"""
import sys
import os
import threading

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.agents.base import AgentDeps
from ai.agents.narrative_enricher import NarrativeEnricherAgent


# ============================================================================
# NarrativeEnricherAgent 单元测试
# ============================================================================

def test_init():
    """NarrativeEnricherAgent 初始化正确。"""
    agent = NarrativeEnricherAgent("test-model", "fake-key")
    assert agent._model_name == "test-model"
    assert agent._api_key == "fake-key"
    assert isinstance(agent._deps, AgentDeps)


def test_output_type_is_str():
    """_output_type() 返回 str（纯文本输出，非结构化 JSON）。"""
    agent = NarrativeEnricherAgent("test-model", "fake-key")
    assert agent._output_type() is str


def test_system_prompt_nonempty():
    """_system_prompt() 返回非空字符串，包含关键词。"""
    agent = NarrativeEnricherAgent("test-model", "fake-key")
    prompt = agent._system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "扩写规则" in prompt
    assert "定性空间关系" in prompt
    assert "参数" in prompt


def test_system_prompt_parameter_preservation():
    """系统提示词包含参数保留强制规则。"""
    agent = NarrativeEnricherAgent("test-model", "fake-key")
    prompt = agent._system_prompt()
    assert "强制" in prompt
    assert "2km*2km" in prompt
    assert "意译" in prompt


def test_system_prompt_no_quantitative():
    """系统提示词禁止定量空间参数。"""
    agent = NarrativeEnricherAgent("test-model", "fake-key")
    prompt = agent._system_prompt()
    assert "严禁" in prompt
    assert "绝对坐标" in prompt
    assert "网格参数" in prompt


def test_register_tools_no_op():
    """_register_tools() 空实现，不注册任何工具，不报错。"""
    agent = NarrativeEnricherAgent("test-model", "fake-key")
    agent._register_tools(None)


def test_build_with_test_model():
    """使用 TestModel 构建 Agent 实例。"""

    class TestEnricher(NarrativeEnricherAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestEnricher("test-model", "fake-key")
    agent = agent_base.build()
    assert isinstance(agent, Agent)


def test_build_caches_agent():
    """build() 第二次调用返回缓存的同一 Agent 实例。"""

    class TestEnricher(NarrativeEnricherAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestEnricher("test-model", "fake-key")
    agent1 = agent_base.build()
    agent2 = agent_base.build()
    assert agent1 is agent2


def test_run_with_test_model():
    """使用 TestModel 运行 Agent，输出 str 类型。"""

    class TestEnricher(NarrativeEnricherAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestEnricher("test-model", "fake-key", deps=AgentDeps())
    import asyncio
    result = asyncio.run(agent_base.run("江西农村"))
    assert isinstance(result.output, str)


def test_deps_injection():
    """自定义 deps 正确注入到 agent。"""
    deps = AgentDeps(knowledge="fake_knowledge", asset_index="fake_index")
    agent_base = NarrativeEnricherAgent("test-model", "fake-key", deps=deps)
    assert agent_base._deps is deps
    assert agent_base._deps.knowledge == "fake_knowledge"
    assert agent_base._deps.asset_index == "fake_index"


# ============================================================================
# AgentWorker Stage0 跨线程同步测试
# ============================================================================

def test_agent_worker_init_default():
    """AgentWorker 默认不启用扩写 (enable_enrichment=False)。"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from scripts.mapforge_app import AgentWorker
    worker = AgentWorker({}, "test scene")
    assert worker._enable_enrichment is False
    assert worker._enriched_text == ""
    assert isinstance(worker._enrich_event, threading.Event)


def test_agent_worker_init_enrich_enabled():
    """AgentWorker 启用扩写时 enable_enrichment=True。"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from scripts.mapforge_app import AgentWorker
    worker = AgentWorker({}, "test scene", enable_enrichment=True)
    assert worker._enable_enrichment is True


def test_confirm_enrichment_sets_text():
    """confirm_enrichment 设置编辑后的文本。"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from scripts.mapforge_app import AgentWorker
    worker = AgentWorker({}, "test scene", enable_enrichment=True)
    worker.confirm_enrichment("编辑后的叙事文本")
    assert worker._enriched_text == "编辑后的叙事文本"


def test_confirm_enrichment_releases_event():
    """confirm_enrichment 释放 Event: confirm 前 is_set=False, confirm 后 is_set=True。"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from scripts.mapforge_app import AgentWorker
    worker = AgentWorker({}, "test scene", enable_enrichment=True)
    assert worker._enrich_event.is_set() is False
    worker.confirm_enrichment("用户编辑后的文本")
    assert worker._enrich_event.is_set() is True


def test_stage0_done_signal_exists():
    """AgentWorker 拥有 stage0_done 信号。"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from scripts.mapforge_app import AgentWorker
    worker = AgentWorker({}, "test scene", enable_enrichment=True)
    assert hasattr(worker, 'stage0_done')
