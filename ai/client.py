"""LLM 客户端抽象接口与实现。

来源: LLM_UEMaps/源码/src/sceneweaver/llm/client.py（完整复制）
适配: 无需修改 — complete() 已支持 **kwargs 透传,
      response_format 和 max_tokens 可直接传入。
"""
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

_LLM_TIMEOUT = 600.0


class LLMClient(ABC):
    """LLM 客户端抽象基类；子类实现 complete()。"""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
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
            call_kwargs = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            call_kwargs.update(kwargs)
            call_kwargs.setdefault("model", self._model)
            response = self._client.chat.completions.create(**call_kwargs)
            choice = response.choices[0]
            content = choice.message.content
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
        data_dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
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
                return str(result["message"]["content"])
        except (TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(
                f"Ollama 请求失败（可能超时/未启动/响应异常）：{e}"
            ) from e
