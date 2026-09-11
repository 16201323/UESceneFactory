"""v0.2 ScenePlannerAgent 单元测试。"""
import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from ai.agents.base import AgentDeps
from ai.agents.scene_planner import ScenePlannerAgent
from ai.models.blueprint import SceneBlueprint


def test_init():
    """ScenePlannerAgent 初始化正确。"""
    agent = ScenePlannerAgent("test-model", "fake-key")
    assert agent._model_name == "test-model"
    assert agent._api_key == "fake-key"
    assert isinstance(agent._deps, AgentDeps)


def test_output_type():
    """_output_type() 返回 SceneBlueprint 类。"""
    agent = ScenePlannerAgent("test-model", "fake-key")
    assert agent._output_type() is SceneBlueprint


def test_system_prompt():
    """_system_prompt() 返回非空字符串，包含关键词。"""
    agent = ScenePlannerAgent("test-model", "fake-key")
    prompt = agent._system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "场景规划" in prompt


def test_build_with_test_model():
    """使用 TestModel 构建 Agent 实例。"""

    class TestScenePlanner(ScenePlannerAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestScenePlanner("test-model", "fake-key")
    agent = agent_base.build()
    assert isinstance(agent, Agent)


def test_deps_injection():
    """自定义 deps 正确注入到 agent。"""
    deps = AgentDeps(knowledge="fake_knowledge", asset_index="fake_index")
    agent_base = ScenePlannerAgent("test-model", "fake-key", deps=deps)
    assert agent_base._deps is deps
    assert agent_base._deps.knowledge == "fake_knowledge"
    assert agent_base._deps.asset_index == "fake_index"


def test_run_with_test_model():
    """使用 TestModel 运行 Agent，输出 SceneBlueprint。"""

    class TestScenePlanner(ScenePlannerAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestScenePlanner("test-model", "fake-key", deps=AgentDeps())
    # AgentBase.run() 自动传递 deps，无需手动传
    result = asyncio.run(agent_base.run("generate a flat terrain scene"))
    assert isinstance(result.output, SceneBlueprint)
