"""场景 JSON 生成器 (Stage 2)：组装知识 + 调用 LLM 生成完整场景 JSON。"""
import json
from ai.client import LLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.utils import extract_json
from ai.tools.asset_tools import search_assets_core


class SceneGenerator:
    def __init__(self, client, knowledge, asset_index, model=None):
        self._client = client
        self._knowledge = knowledge
        self._asset_index = asset_index
        self._model = model

    def generate(self, user_description, intent, few_shots=None):
        # 1. 搜索资产（用 search_assets_core 获取含 recommended_scale 的 AssetEntry）
        keywords = intent.get("keywords", [])
        asset_entries = search_assets_core(self._asset_index, keywords, max_results=30)

        # 2. 组装 system prompt（AssetEntry 含缩放建议，由 build_system_prompt 注入）
        system_prompt = self._knowledge.build_system_prompt(
            intent, asset_entries, few_shots or []
        )

        # 3. 组装 user prompt
        user_prompt = (
            f"用户需求: {user_description}\n"
            f"意图分析: {json.dumps(intent, ensure_ascii=False)}\n\n"
            f"请生成完整的场景 JSON。只输出 JSON，不要 markdown 代码块标记。\n"
            f"重要: 每个结构块和子块都必须包含 \"_note\" 字段，"
            f"写明该块的用途和每个参数的意义（格式见核心知识中的 _note 注释规范）。"
        )

        # 4. 调用 LLM（启用 JSON Mode + max_tokens 防止截断）
        # 推理模型(如 glm-5.2)的 reasoning_content 和 content 共享 max_tokens 预算
        # 实测: 复杂场景推理约耗 10K~30K tokens(波动大), 32768 有时不够会导致 content 为空
        # 65536 实测可覆盖推理(~28K) + 内容(~10K), finish_reason=stop
        kwargs = {
            "response_format": {"type": "json_object"},
            "max_tokens": 65536,
        }
        if self._model:
            kwargs["model"] = self._model
        resp = self._client.complete(system_prompt, user_prompt, **kwargs)

        # 5. 三层 JSON 提取
        scene = extract_json(resp)
        return scene
