"""意图解析器 (Stage 1)：从自然语言提取结构化意图 JSON。"""
import json
from ai.client import LLMClient
from ai.utils import extract_json

INTENT_PROMPT = """你是一个 UE5 场景意图解析器。从用户描述中提取结构化信息。

输出 JSON，严格遵循以下 schema:
{
  "terrain_type": "flat|ridge|hill|noise|hill_ridge|features|terraced|karst|gully",
  "has_water": bool,
  "has_river": bool,
  "has_road": bool,
  "has_buildings": bool,
  "has_grass": bool,
  "has_wheat": bool,
  "has_snow": bool,
  "scene_scale": "500m|1km|2km",
  "placements": ["trees", "fence", "heliport", ...],
  "keywords": ["中文关键词1", "关键词2", ...],
  "complexity": "simple|medium|complex"
}

规则:
- terrain_type 不确定时默认 "features"
- scene_scale 不确定时默认 "1km"
- complexity: 少于3个元素=simple, 3-6个=medium, 6个以上=complex
- keywords: 提取所有可用作资产搜索的关键词

只输出 JSON，不要其他文字。"""

FALLBACK_INTENT = {
    "terrain_type": "features",
    "has_water": False, "has_river": False, "has_road": False,
    "has_buildings": False, "has_grass": True, "has_wheat": False,
    "has_snow": False, "scene_scale": "1km",
    "placements": [], "keywords": [], "complexity": "medium",
}


class IntentParser:
    def __init__(self, client, model=None):
        self._client = client
        self._model = model

    def parse(self, user_description):
        kwargs = {}
        if self._model:
            kwargs["model"] = self._model
        # 启用 JSON Mode + 限制 token 数
        kwargs["response_format"] = {"type": "json_object"}
        kwargs["max_tokens"] = 2048
        try:
            resp = self._client.complete(INTENT_PROMPT, user_description, **kwargs)
            # 三层 JSON 提取（兼容 JSON Mode 和非 JSON Mode 响应）
            intent = extract_json(resp)
            # 合并 fallback 确保所有字段存在
            result = FALLBACK_INTENT.copy()
            result.update(intent)
            return result
        except Exception:
            return FALLBACK_INTENT.copy()
