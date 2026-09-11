"""Agent 公共基类和依赖注入容器。

AgentBase 封装 PydanticAI Agent 的创建流程：
模型创建 → 系统提示词 → 输出类型 → 工具注册。
子类只需实现 _system_prompt()、_output_type()、_register_tools()。
"""
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


@dataclass
class AgentDeps:
    """Agent 依赖注入容器 — 在运行时传递后端组件给工具函数。

    所有字段默认 None，允许按需注入（如测试时只传 knowledge）。
    """
    knowledge: Any = None
    asset_index: Any = None
    experience_bank: Any = None
    retriever: Any = None
    pattern_library: Any = None
    validator: Any = None


class AgentBase:
    """所有 Agent 的公共基类。

    子类必须实现：
        - _system_prompt(): 返回系统提示词字符串
        - _output_type(): 返回输出类型（Pydantic 模型类或 None）
        - _register_tools(agent): 注册 @agent.tool 装饰的函数
    """

    def __init__(self, model_name: str, api_key: str, base_url: str | None = None,
                 deps: AgentDeps | None = None, retries: int = 3):
        """初始化 Agent 基类。

        Args:
            model_name: 模型名称（如 "gpt-4o"）
            api_key: API 密钥
            base_url: 自定义 API 基础 URL（可选，用于代理或兼容端点）
            deps: 依赖注入容器，默认创建空的 AgentDeps
            retries: 工具调用失败时的重试次数
        """
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._deps = deps if deps is not None else AgentDeps()
        self._retries = retries
        self._agent: Agent | None = None

    def _create_model(self) -> OpenAIChatModel:
        """创建 OpenAIChatModel 实例。"""
        provider = OpenAIProvider(api_key=self._api_key, base_url=self._base_url)
        return OpenAIChatModel(model_name=self._model_name, provider=provider)

    def build(self) -> Agent:
        """构建并返回 PydanticAI Agent 实例（带缓存）。

        首次调用时创建 Agent 并注册工具，后续调用直接返回缓存实例。
        """
        if self._agent is not None:
            return self._agent

        model = self._create_model()
        agent_kwargs = {
            "deps_type": AgentDeps,
            "retries": self._retries,
            "system_prompt": self._system_prompt(),
        }
        output_type = self._output_type()
        if output_type is not None:
            agent_kwargs["output_type"] = output_type

        self._agent = Agent(model, **agent_kwargs)
        self._register_tools(self._agent)
        return self._agent

    async def run(self, user_prompt: str) -> Any:
        """运行 Agent，自动传递存储的 deps 依赖。

        封装 agent.run() 调用，避免调用者忘记传 deps 导致 ctx.deps 为 None。
        """
        agent = self.build()
        return await agent.run(user_prompt, deps=self._deps)

    def _output_type(self) -> Any:
        """返回输出类型 — 子类覆盖以指定结构化输出。"""
        return None

    def _system_prompt(self) -> str:
        """返回系统提示词 — 子类必须实现。"""
        raise NotImplementedError("子类必须实现 _system_prompt()")

    def _register_tools(self, agent: Agent) -> None:
        """注册工具函数 — 子类必须实现。"""
        raise NotImplementedError("子类必须实现 _register_tools()")
