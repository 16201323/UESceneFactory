"""场景 JSON 生成器 (Stage 2)：组装知识 + 调用 LLM 生成完整场景 JSON。"""
import json
from ai.client import LLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.utils import extract_json


class SceneGenerator:
    def __init__(self, client, knowledge, asset_index, model=None):
        self._client = client
        self._knowledge = knowledge
        self._asset_index = asset_index
        self._model = model

    def generate(self, user_description, intent, few_shots=None):
        keywords = intent.get("keywords", [])
        asset_paths = self._asset_index.search(keywords, max_results=30)

        system_prompt = self._knowledge.build_system_prompt(
            intent, asset_paths, few_shots or []
        )

        user_prompt = (
            f"用户需求: {user_description}\n"
            f"意图分析: {json.dumps(intent, ensure_ascii=False)}\n\n"
            f"请生成完整的场景 JSON。只输出 JSON，不要 markdown 代码块标记。\n"
            f"重要: 每个结构块和子块都必须包含 \"_note\" 字段，"
            f"写明该块的用途和每个参数的意义（格式见核心知识中的 _note 注释规范）。"
        )

        kwargs = {
            "response_format": {"type": "json_object"},
            "max_tokens": 65536,
        }
        if self._model:
            kwargs["model"] = self._model
        resp = self._client.complete(system_prompt, user_prompt, **kwargs)

        scene = extract_json(resp)
        return scene
