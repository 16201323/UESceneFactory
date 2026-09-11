"""经验检索工具核心函数 — 包装 ExperienceRetriever。

核心函数与 Agent 工具装饰分离，便于单元测试时直接传入 Stub 对象。
"""
from ai.models.blueprint import ExperienceRef

_MAX_USER_DESC_LEN = 200


def search_experience_core(retriever, intent: dict, top_k: int = 3) -> list[ExperienceRef]:
    """检索相似经验并返回 ExperienceRef 列表。

    Args:
        retriever: ExperienceRetriever 实例（或 None）
        intent: 用户意图字典（含 keywords, terrain_type 等）
        top_k: 返回的最大经验数量

    Returns:
        ExperienceRef 列表；retriever 为 None 时返回空列表
    """
    if retriever is None:
        return []
    if intent is None:
        intent = {}
    experiences = retriever.retrieve(intent, top_k=top_k)
    if not experiences:
        return []
    results = []
    for exp in experiences:
        exp_id = exp.get("id", 0)
        user_desc = exp.get("user_desc", "")
        if len(user_desc) > _MAX_USER_DESC_LEN:
            user_desc = user_desc[:_MAX_USER_DESC_LEN]
        # scene_type 从输入 intent 映射（而非经验自身的 intent）
        scene_type = intent.get("terrain_type", "")
        rating = exp.get("rating", 3)
        # keywords 从经验自身的 intent 提取
        # 后端 experience_bank._row_to_dict() 已将 intent_json 反序列化为 dict
        exp_intent = exp.get("intent", {})
        keywords = exp_intent.get("keywords", [])
        results.append(
            ExperienceRef(
                id=exp_id,
                user_desc=user_desc,
                scene_type=scene_type,
                rating=rating,
                keywords=keywords if isinstance(keywords, list) else [],
            )
        )
    return results
