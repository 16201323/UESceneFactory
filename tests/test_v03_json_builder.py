"""v0.3 JSONBuilderAgent 单元测试。

JSONBuilderAgent 是流水线第二阶段 Agent，接收 SceneBlueprint 蓝图，
调用工具注入知识和搜索资产，输出 SceneJSON。
测试模式沿用 v0.2 ScenePlannerAgent：子类化覆盖 _create_model 返回 TestModel。
"""
import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from ai.agents.base import AgentDeps
from ai.agents.json_builder import JSONBuilderAgent
from ai.models.scene_json import SceneJSON


def test_init():
    """JSONBuilderAgent 初始化正确。"""
    agent = JSONBuilderAgent("test-model", "fake-key")
    assert agent._model_name == "test-model"
    assert agent._api_key == "fake-key"
    assert isinstance(agent._deps, AgentDeps)


def test_output_type():
    """_output_type() 返回 SceneJSON 类。"""
    agent = JSONBuilderAgent("test-model", "fake-key")
    assert agent._output_type() is SceneJSON


def test_system_prompt():
    """_system_prompt() 返回非空字符串，包含关键词。"""
    agent = JSONBuilderAgent("test-model", "fake-key")
    prompt = agent._system_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "JSON" in prompt


def test_build_with_test_model():
    """使用 TestModel 构建 Agent 实例。"""

    class TestJSONBuilder(JSONBuilderAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestJSONBuilder("test-model", "fake-key")
    agent = agent_base.build()
    assert isinstance(agent, Agent)


def test_deps_injection():
    """自定义 deps 正确注入到 agent。"""
    deps = AgentDeps(knowledge="fake_knowledge", asset_index="fake_index")
    agent_base = JSONBuilderAgent("test-model", "fake-key", deps=deps)
    assert agent_base._deps is deps
    assert agent_base._deps.knowledge == "fake_knowledge"
    assert agent_base._deps.asset_index == "fake_index"


def test_run_with_test_model():
    """使用 TestModel 运行 Agent，输出 SceneJSON。"""

    class TestJSONBuilder(JSONBuilderAgent):
        def _create_model(self):
            return TestModel()

    agent_base = TestJSONBuilder("test-model", "fake-key", deps=AgentDeps())
    blueprint_json = '{"terrain_type": "flat", "has_water": false, "has_river": false, "has_grass": true, "has_wheat": false, "scene_type": "flat"}'
    result = asyncio.run(agent_base.run(blueprint_json))
    assert isinstance(result.output, SceneJSON)
