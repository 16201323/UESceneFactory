"""v0.1 AgentBase 基类单元测试。"""
import pytest

from ai.agents.base import AgentBase, AgentDeps


def test_init_defaults():
    """AgentBase 初始化时使用默认 deps。"""
    agent_base = AgentBase("test-model", "fake-key")
    assert agent_base._model_name == "test-model"
    assert agent_base._api_key == "fake-key"
    assert isinstance(agent_base._deps, AgentDeps)


def test_init_with_deps():
    """传入自定义 deps 时正确存储。"""
    deps = AgentDeps(knowledge="fake_knowledge")
    agent_base = AgentBase("model", "key", deps=deps)
    assert agent_base._deps is deps
    assert agent_base._deps.knowledge == "fake_knowledge"


def test_deps_defaults_all_none():
    """AgentDeps 默认所有字段为 None。"""
    deps = AgentDeps()
    assert deps.knowledge is None
    assert deps.asset_index is None
    assert deps.experience_bank is None
    assert deps.retriever is None
    assert deps.pattern_library is None
    assert deps.validator is None


def test_output_type_default_none():
    """AgentBase._output_type() 默认返回 None。"""
    agent_base = AgentBase("model", "key")
    assert agent_base._output_type() is None


def test_system_prompt_raises():
    """AgentBase._system_prompt() 抛出 NotImplementedError。"""
    agent_base = AgentBase("model", "key")
    with pytest.raises(NotImplementedError):
        agent_base._system_prompt()


def test_register_tools_raises():
    """AgentBase._register_tools() 抛出 NotImplementedError。"""
    agent_base = AgentBase("model", "key")
    with pytest.raises(NotImplementedError):
        agent_base._register_tools(None)


def test_build_with_test_model():
    """使用 TestModel 子类化 AgentBase，build() 返回 Agent 实例。"""
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    class TestAgent(AgentBase):
        def _create_model(self):
            return TestModel()

        def _system_prompt(self):
            return "test prompt"

        def _register_tools(self, agent):
            pass

    agent_base = TestAgent("test-model", "fake-key")
    agent = agent_base.build()
    assert isinstance(agent, Agent)


def test_build_caches_agent():
    """build() 第二次调用返回缓存的同一 Agent 实例。"""
    from pydantic_ai.models.test import TestModel

    class TestAgent(AgentBase):
        def _create_model(self):
            return TestModel()

        def _system_prompt(self):
            return "test prompt"

        def _register_tools(self, agent):
            pass

    agent_base = TestAgent("test-model", "fake-key")
    agent1 = agent_base.build()
    agent2 = agent_base.build()
    assert agent1 is agent2


def test_run_auto_passes_deps():
    """run() 自动传递 deps，无需调用者手动传。"""
    import asyncio
    from pydantic_ai.models.test import TestModel

    class TestAgent(AgentBase):
        def _create_model(self):
            return TestModel()

        def _system_prompt(self):
            return "test prompt"

        def _register_tools(self, agent):
            pass

    agent_base = TestAgent("test-model", "fake-key", deps=AgentDeps())
    # run() 内部自动将 self._deps 传给 agent.run()
    result = asyncio.run(agent_base.run("hello"))
    assert result is not None
