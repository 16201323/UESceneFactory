"""资产关键词索引：从 asset_catalog.json 构建，支持关键词搜索。"""
import json


class AssetIndex:
    def __init__(self, catalog_path="asset_catalog.json"):
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._assets = data.get("assets", [])

    def search(self, keywords: list[str], max_results: int = 20) -> list[str]:
        scored = []
        for asset in self._assets:
            score = self._match_score(asset, keywords)
            if score > 0:
                scored.append((score, asset["path"]))
        scored.sort(key=lambda x: -x[0])
        seen = set()
        result = []
        for _, path in scored:
            if path not in seen:
                seen.add(path)
                result.append(path)
            if len(result) >= max_results:
                break
        return result

    def _match_score(self, asset: dict, keywords: list[str]) -> int:
        name = asset.get("name", "").lower()
        cat = asset.get("category", "").lower()
        sub = asset.get("subfolder", "").lower()
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in name:
                score += 3  # name 匹配权重最高
            if kw_lower in cat:
                score += 2
            if kw_lower in sub:
                score += 1
        return score

    def search_by_category(self, category: str, max_results: int = 50) -> list[str]:
        result = []
        for asset in self._assets:
            if asset.get("category", "").lower() == category.lower():
                result.append(asset["path"])
            if len(result) >= max_results:
                break
        return result
