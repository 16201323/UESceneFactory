"""v0.4 QualityGuardAgent 单元测试。

QualityGuardAgent 是流水线第三阶段 Agent，接收 JSONBuilderAgent 输出的场景 JSON，
调用 validate_scene / validate_assets 工具校验字段和资产路径，有错误时 LLM 修复最多 3 轮，
输出 ValidationReport。测试模式沿用 v0.3 JSONBuilderAgent：子类化覆盖 _create_model 返回 TestModel。
"""
import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from ai.agents.base import AgentDeps
from ai.agents.quality_guard import QualityGuardAgent
from ai.models.validation_report import ValidationReport


def test_init():
    """QualityGuardAgent 初始化正确。"""
    agent = QualityGuardAgent("test-model", "fake-key")
    assert agent._model_name == "test-model"
    assert agent._api_key == "fake-key"
    assert isinstance(agent._deps, AgentDeps)


def test_output_type():
    """_output_type() 返回 ValidationReport 类。"""
    agent = QualityGuardAgent("test-model", "fake-key")
    assert agent._output_type() is ValidationReport


def test_system_prompt():
    """_system_prompt() 返回非空字符串，包含校验/修复关键词。"""
    agent = QualityGuardAgent("test-model", "fake-key")
    prompt = agent._system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "校验" in prompt
    assert "修复" in prompt


def test_build_with_test_model():
    """使用 TestModel 构建 Agent 实例。"""

    class TestQualityGuard(QualityGuardAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestQualityGuard("test-model", "fake-key")
    agent = agent_base.build()
    assert isinstance(agent, Agent)


def test_deps_injection():
    """自定义 deps 正确注入到 agent，validator 字段用于 content_dir。"""
    deps = AgentDeps(validator="/fake/Content")
    agent_base = QualityGuardAgent("test-model", "fake-key", deps=deps)
    assert agent_base._deps is deps
    assert agent_base._deps.validator == "/fake/Content"


def test_run_with_test_model():
    """使用 TestModel 运行 Agent，输出 ValidationReport。"""

    class TestQualityGuard(QualityGuardAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestQualityGuard("test-model", "fake-key", deps=AgentDeps())
    scene_json = '{"scene": {"name": "test", "target_level": "/Game/Maps/Test"}}'
    result = asyncio.run(agent_base.run(scene_json))
    assert isinstance(result.output, ValidationReport)
