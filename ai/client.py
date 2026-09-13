"""LLM 客户端抽象接口与实现。

来源: LLM_UEMaps/源码/src/sceneweaver/llm/client.py（完整复制）
适配: 无需修改 — complete() 已支持 **kwargs 透传,
      response_format 和 max_tokens 可直接传入。
"""
import json
import threading
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

# 推理模型(如 glm-5.2)需要先完成 reasoning 再输出 content;
# Stage 2 注入20KB模板后 system prompt 暴增, 300s 实测不够(大场景推理+32K输出超时), 调到600s
_LLM_TIMEOUT = 600.0


class TokenTracker:
    """全局 LLM Token 累计器(线程安全单例)

    统一统计程序启动后所有用到 LLM 的 token 消耗量, 覆盖两条调用路径:
      1. AIWorker(旧管线): IntentParser/SceneGenerator/ValidationRepairLoop → LLMClient.complete()
         → 在 complete() 成功返回后调用 add() 上报(OpenAI: usage.prompt_tokens/completion_tokens;
         Ollama: prompt_eval_count/eval_count)
      2. AgentWorker(新管线): pydantic_ai Agent.run() → AgentRunResult.usage
         → 在 run() 每阶段完成后调用 add() 上报(input_tokens/output_tokens)
    UI 层通过 QTimer 定时轮询 totals 属性刷新顶栏显示, 实现"所有用到 LLM 的 tokens
    量都计算进去"的跨模块统一统计。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._input_tokens = 0   # 累计输入(prompt) tokens
        self._output_tokens = 0  # 累计输出(completion) tokens

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """上报一次 LLM 调用的 token 消耗(线程安全, 允许 None/负值自动归零)"""
        with self._lock:
            self._input_tokens += int(input_tokens or 0)
            self._output_tokens += int(output_tokens or 0)

    @property
    def totals(self) -> tuple[int, int, int]:
        """返回 (累计输入, 累计输出, 累计合计) 的快照"""
        with self._lock:
            return self._input_tokens, self._output_tokens, self._input_tokens + self._output_tokens

    def reset(self) -> None:
        """重置累计(用于新会话/测试隔离)"""
        with self._lock:
            self._input_tokens = 0
            self._output_tokens = 0


# 全局单例: 程序生命周期内所有 LLM 调用统一上报到此实例
token_tracker = TokenTracker()


class LLMClient(ABC):
    """LLM 客户端抽象基类；子类实现 complete()。"""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """发送 system+user prompt，返回文本响应。"""
        ...


class MockLLMClient(LLMClient):
    """测试用 Mock：按预设响应列表循环返回。"""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.call_log: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        self.call_log.append((system_prompt, user_prompt))
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return self._responses[-1] if self._responses else ""

    def reset(self) -> None:
        self._idx = 0
        self.call_log.clear()


class OpenAILLMClient(LLMClient):
    """OpenAI API 客户端（延迟导入 openai 包）。"""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
        timeout: float = _LLM_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._client: Any = None

    def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai 包未安装。请运行: pip install openai"
            ) from exc

        if self._client is None:
            client_kwargs: dict[str, Any] = {
                "api_key": self._api_key,
                "timeout": self._timeout,
            }
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            self._client = OpenAI(**client_kwargs)

        try:
            # kwargs 中的 model 优先(允许调用方覆盖默认模型), 避免重复传参冲突
            call_kwargs = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            call_kwargs.update(kwargs)
            call_kwargs.setdefault("model", self._model)
            response = self._client.chat.completions.create(**call_kwargs)
            # 上报本次调用的 token 消耗到全局累计器
            # (OpenAI 响应 usage 含 prompt_tokens=输入, completion_tokens=输出;
            #  放在内容提取之前, 即使推理模型耗尽预算导致 content 为空, 已消耗的 tokens 仍被统计)
            _usage = getattr(response, "usage", None)
            if _usage is not None:
                token_tracker.add(
                    getattr(_usage, "prompt_tokens", 0),
                    getattr(_usage, "completion_tokens", 0),
                )
            choice = response.choices[0]
            content = choice.message.content
            # 推理模型(如 glm-5.2): reasoning_content 和 content 共享 max_tokens 预算
            # 推理耗尽预算时 content 为空, finish_reason="length"
            # 此时返回空字符串会导致下游 extract_json 报晦涩错误, 需给出明确原因
            if not content:
                finish_reason = getattr(choice, "finish_reason", "unknown")
                rc = getattr(choice.message, "reasoning_content", None)
                rc_len = len(rc) if rc else 0
                raise RuntimeError(
                    f"LLM 响应内容为空: 推理模型可能耗尽 max_tokens 预算 "
                    f"(finish_reason={finish_reason}, reasoning_content 长度={rc_len})。"
                    f"请增大 max_tokens 或精简提示词"
                )
            return str(content)
        except RuntimeError:
            # 空内容诊断错误直接向上抛, 不被下面的通用异常包装
            raise
        except Exception as e:
            raise RuntimeError(
                f"OpenAI 请求失败（可能超时/网络/鉴权/配额）：{e}"
            ) from e


class OllamaLLMClient(LLMClient):
    """Ollama 本地 LLM 客户端（纯 stdlib urllib，无需额外依赖）。"""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: float = _LLM_TIMEOUT,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        # 构建 Ollama API 请求体，传递 max_tokens 限制（Ollama 用 options.num_predict）
        data_dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
        # 将 kwargs 中的 max_tokens 映射到 Ollama 的 options.num_predict
        max_tokens = kwargs.get("max_tokens")
        if max_tokens:
            data_dict["options"] = {"num_predict": max_tokens}
        data = json.dumps(data_dict).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                # 上报本次调用的 token 消耗到全局累计器
                # (Ollama 响应含 prompt_eval_count=输入tokens, eval_count=输出tokens;
                #  某些模型/版本可能不返回这两个字段, 用 .get 兜底为 0)
                token_tracker.add(
                    result.get("prompt_eval_count", 0),
                    result.get("eval_count", 0),
                )
                return str(result["message"]["content"])
        except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(
                f"Ollama 请求失败（可能超时/未启动/响应异常）：{e}"
            ) from e
