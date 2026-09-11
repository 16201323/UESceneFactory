"""经验检索器：四因子评分 + MMR 多样性选择，将 top-K 经验作为 few-shot 注入。

四因子: 0.65×关键词相似度 + 0.15×时效性 + 0.20×可靠性 + 0.10×多样性(MMR)
注意: retrieve 不调用 update_usage — 使用统计由管线末尾(AIWorker/run_pipeline)处理
"""
from datetime import datetime
from ai.experience_bank import ExperienceBank

WEIGHT_KEYWORD_SIM = 0.65
WEIGHT_RECENCY = 0.15
WEIGHT_RELIABILITY = 0.20
WEIGHT_DIVERSITY = 0.10
MMR_THRESHOLD = 0.15


class ExperienceRetriever:
    def __init__(self, bank: ExperienceBank):
        self._bank = bank

    def retrieve(self, intent, top_k=3):
        my_keywords = intent.get("keywords", [])
        all_exps = self._bank.search_by_keywords(my_keywords)

        if not all_exps:
            return []

        scored = []
        for exp in all_exps:
            sim = self._keyword_similarity(my_keywords, exp["intent"].get("keywords", []))
            rec = self._recency(exp.get("last_used_at") or exp.get("created_at", ""))
            rel = self._reliability(exp.get("success_count", 0), exp.get("fail_count", 0))
            score = WEIGHT_KEYWORD_SIM * sim + WEIGHT_RECENCY * rec + WEIGHT_RELIABILITY * rel
            scored.append((score, sim, exp))

        scored.sort(key=lambda x: -x[0])

        selected = []
        for score, sim, exp in scored:
            if len(selected) >= top_k:
                break

            if not selected:
                selected.append(exp)
                continue

            max_sim = max(
                self._keyword_similarity(
                    exp["intent"].get("keywords", []),
                    s["intent"].get("keywords", [])
                )
                for s in selected
            )
            mmr = min(score + WEIGHT_DIVERSITY * (1 - max_sim), 1.0)

            if mmr > MMR_THRESHOLD:
                selected.append(exp)

        return selected

    def _keyword_similarity(self, keywords1, keywords2):
        set1 = set(kw.lower() for kw in keywords1) if isinstance(keywords1, list) else set()
        set2 = set(kw.lower() for kw in keywords2) if isinstance(keywords2, list) else set()
        if not set1 or not set2:
            return 0.0
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union)

    def _recency(self, timestamp_str):
        try:
            ts = datetime.fromisoformat(timestamp_str)
            days = (datetime.now() - ts).days
            return 1.0 / (1.0 + days)
        except Exception:
            return 0.0

    def _reliability(self, success_count, fail_count):
        total = success_count + fail_count
        if total == 0:
            return 0.5
        return success_count / (total + 1)
