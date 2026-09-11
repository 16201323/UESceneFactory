"""资产搜索工具核心函数 — 包装 AssetIndex。

核心函数与 Agent 工具装饰分离，便于单元测试时直接传入 Stub 对象。
"""
from ai.models.blueprint import AssetEntry


def search_assets_core(asset_index, keywords: list[str], max_results: int = 20) -> list[AssetEntry]:
    """搜索资产并返回 AssetEntry 列表。

    Args:
        asset_index: AssetIndex 实例（或 None）
        keywords: 搜索关键词列表
        max_results: 最大返回数量

    Returns:
        AssetEntry 列表；asset_index 为 None 或 keywords 为空时返回空列表
    """
    if asset_index is None:
        return []
    if not keywords:
        return []
    paths = asset_index.search(keywords, max_results=max_results)
    if not paths:
        return []
    # 通过公共接口获取资产详情，补全 AssetEntry 的 name/category/subfolder
    results = []
    for path in paths:
        asset_dict = asset_index.get_asset_by_path(path)
        results.append(
            AssetEntry(
                path=path,
                name=asset_dict.get("name", ""),
                category=asset_dict.get("category", ""),
                subfolder=asset_dict.get("subfolder", ""),
            )
        )
    return results
