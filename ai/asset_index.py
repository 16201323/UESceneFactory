"""资产关键词索引：从 asset_catalog.json 构建，支持关键词搜索。"""
import json


class AssetIndex:
    # 中文关键词 → 英文搜索词映射表
    # 解决问题: ScenePlanner 提取的中文关键词(树/房屋/麦田)无法匹配
    #          asset_catalog 中英文命名的资产(name=Tree_SM 等), 导致搜索返回 0
    # 映射策略: 每个中文关键词展开为对应的英文同义词列表, 拼接后参与匹配
    _KEYWORD_ALIASES = {
        # 植被类
        "树": ["tree", "forest", "pine", "oak", "foliage", "branch"],
        "树木": ["tree", "forest", "pine", "oak"],
        "森林": ["forest", "tree", "pine", "woods"],
        "密林": ["forest", "tree", "dense"],
        "树林": ["forest", "tree", "woods"],
        "枯树": ["dead", "tree", "stump", "branch"],
        "草": ["grass", "foliage", "plant"],
        "草地": ["grass", "foliage", "meadow"],
        "草原": ["grass", "meadow", "plain"],
        "草甸": ["grass", "meadow"],
        "牧场": ["grass", "meadow", "pasture"],
        "芦苇": ["reed", "grass", "wetland"],
        "麦田": ["wheat", "crop", "grain", "field"],
        "麦子": ["wheat", "crop", "grain"],
        "农田": ["crop", "wheat", "field", "farm"],
        "梯田": ["terraced", "crop", "field"],
        # 地形/地貌类
        "山": ["mountain", "hill", "ridge", "rock"],
        "山脉": ["mountain", "ridge", "peak"],
        "远山": ["mountain", "ridge", "hill"],
        "山丘": ["hill", "mound"],
        "丘": ["hill", "mound"],
        "岩石": ["rock", "stone", "boulder"],
        "石头": ["rock", "stone", "boulder"],
        "沙丘": ["sand", "dune", "desert"],
        "沙漠": ["desert", "sand", "dune"],
        "沙": ["sand", "desert"],
        "雪": ["snow", "ice", "frost"],
        "雪山": ["snow", "mountain", "ice"],
        # 水系类
        "河": ["river", "water", "stream"],
        "河流": ["river", "water", "stream"],
        "溪": ["stream", "creek", "water"],
        "水": ["water", "lake", "pond", "river"],
        "湖": ["lake", "water", "pond"],
        "潭": ["pond", "water", "lake"],
        "湿地": ["wetland", "water", "marsh"],
        "沼泽": ["marsh", "swamp", "water"],
        "海": ["sea", "ocean", "water"],
        "海滩": ["beach", "sand", "coast"],
        "沙滩": ["beach", "sand", "coast"],
        "岛": ["island", "water"],
        # 建筑/设施类
        "房屋": ["house", "building", "cottage", "cabin", "hut"],
        "房子": ["house", "building", "cottage"],
        "村舍": ["house", "cottage", "village"],
        "村落": ["village", "house", "cottage"],
        "村庄": ["village", "house", "cottage"],
        "农村": ["village", "house", "farm"],
        "乡村": ["village", "house", "rural"],
        "建筑": ["building", "house", "structure"],
        "厂房": ["factory", "industrial", "building"],
        # 基础设施类
        "电塔": ["tower", "power", "hv", "transmission"],
        "高压": ["tower", "power", "hv", "transmission"],
        "通信塔": ["communication", "telecom", "tower"],
        "基站": ["telecom", "communication", "tower"],
        "停机坪": ["heliport", "helicopter", "pad"],
        "直升机": ["helicopter", "heliport"],
        "光伏": ["solar", "pv", "panel"],
        "太阳能": ["solar", "pv", "panel"],
        # 道路类
        "道路": ["road", "path", "street"],
        "路": ["road", "path", "street"],
        "跑道": ["runway", "road", "strip"],
    }

    def __init__(self, catalog_path="asset_catalog.json"):
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._assets = data.get("assets", [])

    def _expand_keywords(self, keywords: list[str]) -> list[str]:
        """展开关键词: 中文关键词追加英文同义词, 提升匹配率。

        ScenePlanner 提取的 keywords 多为中文(树/房屋/麦田),
        而 asset_catalog 的 name/category/subfolder 均为英文,
        直接子串匹配必然返回 0。此方法将每个中文关键词映射为
        [中文原词] + [英文同义词列表], 拼成扩展关键词集参与评分。
        """
        expanded = []
        for kw in keywords:
            expanded.append(kw)
            kw_lower = kw.lower()
            if kw_lower in self._KEYWORD_ALIASES:
                expanded.extend(self._KEYWORD_ALIASES[kw_lower])
        return expanded

    def search(self, keywords: list[str], max_results: int = 20) -> list[str]:
        expanded = self._expand_keywords(keywords)
        scored = []
        for asset in self._assets:
            score = self._match_score(asset, expanded)
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

    def get_asset_by_path(self, path: str) -> dict:
        """公共接口：按路径获取资产详情字典。

        供外部工具调用，避免直接访问 _assets 私有属性。
        找不到时返回空字典。
        """
        for asset in self._assets:
            if asset.get("path") == path:
                return asset
        return {}
