"""验证-修复循环 (Stage 3)：调用 validate_scene，有错误时用 LLM 修复，最多 3 轮。"""
import json
from ai.client import LLMClient
from ai.knowledge import KnowledgePack
from ai.utils import extract_json
from validate_scene_json import validate_scene

REPAIR_PROMPT_TEMPLATE = """你是 UE5 场景 JSON 修复器。以下 JSON 有校验错误，请修复。

校验规则摘要:
- 顶层键: scene, landscape, ground, placements, lighting, weather, rivers
- scene 必填: target_level
- landscape 必填: material, section_size_quads, num_subsections, component_count_x/y
- height_pattern.type 枚举: flat, ridge, hill, noise, hill_ridge, features, terraced, karst, gully
- weight_pattern.pattern 枚举: uniform, height_based, slope_based, region, multi_region, noise_based, aspect_based, snow_line
- placement.type 枚举: group, instanced_grid, instances, static, blueprint, crop_field, village
- weight 值范围: 0~1
- 资产路径格式: /Game/类别/Name (不含 .uasset)

原始用户需求: {user_desc}
当前 JSON:
{scene_json}

校验错误:
{errors_list}

请修复所有错误，输出完整的修复后 JSON。只输出 JSON，不要 markdown 代码块标记。
重要: 每个结构块和子块都必须包含 "_note" 字段，写明该块用途和每个参数的意义。"""


class ValidationRepairLoop:
    def __init__(self, client, knowledge=None, model=None, max_rounds=3):
        self._client = client
        self._knowledge = knowledge
        self._model = model
        self._max_rounds = max_rounds

    def validate_and_repair(self, scene, user_description="", intent=None):
        history = []
        current = scene

        system_prompt = ""
        if self._knowledge and intent:
            system_prompt = self._knowledge.build_system_prompt(intent, [], [])

        for round_num in range(self._max_rounds):
            errors, warnings = validate_scene(current)

            history.append({
                "round": round_num + 1,
                "errors": errors,
                "warnings": warnings,
            })

            if not errors:
                return current, history

            errors_text = "\n".join("- " + e for e in errors)
            prompt = REPAIR_PROMPT_TEMPLATE.format(
                user_desc=user_description,
                scene_json=json.dumps(current, ensure_ascii=False, indent=2),
                errors_list=errors_text,
            )

            kwargs = {
                "response_format": {"type": "json_object"},
                "max_tokens": 65536,
            }
            if self._model:
                kwargs["model"] = self._model

            try:
                resp = self._client.complete(system_prompt, prompt, **kwargs)
                current = extract_json(resp)
            except Exception:
                history[-1]["repair_failed"] = True
                return current, history

        return current, history
