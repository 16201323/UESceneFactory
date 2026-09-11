"""v0.2 资产搜索工具核心函数单元测试。"""
import pytest

from ai.models.blueprint import AssetEntry
from ai.tools.asset_tools import search_assets_core


class StubAssetIndex:
    """模拟 AssetIndex 的最小实现。"""

    def __init__(self, assets=None):
        self._assets = assets or []

    def search(self, keywords, max_results=20):
        """简单匹配：返回所有 path 中包含任一关键词的资产路径。"""
        results = []
        for asset in self._assets:
            path = asset.get("path", "").lower()
            if any(kw.lower() in path for kw in keywords):
                results.append(asset["path"])
                if len(results) >= max_results:
                    break
        return results

    def get_asset_by_path(self, path):
        """公共接口：按路径获取资产详情字典。"""
        for asset in self._assets:
            if asset.get("path") == path:
                return asset
        return {}


def test_search_assets_core_none():
    """asset_index 为 None 时返回空列表。"""
    assert search_assets_core(None, ["tree"]) == []


def test_search_assets_core_empty_keywords():
    """空关键词列表返回空列表。"""
    idx = StubAssetIndex(assets=[{"path": "/Game/Tree", "name": "Tree"}])
    assert search_assets_core(idx, []) == []


def test_search_assets_core_results():
    """正常搜索返回 AssetEntry 列表，字段正确映射。"""
    idx = StubAssetIndex(
        assets=[
            {
                "path": "/Game/Props/Tree",
                "name": "SM_Tree",
                "category": "vegetation",
                "subfolder": "Trees",
            },
            {
                "path": "/Game/Props/Rock",
                "name": "SM_Rock",
                "category": "geology",
                "subfolder": "Rocks",
            },
        ]
    )
    results = search_assets_core(idx, ["tree"])
    assert len(results) == 1
    assert isinstance(results[0], AssetEntry)
    assert results[0].path == "/Game/Props/Tree"
    assert results[0].name == "SM_Tree"
    assert results[0].category == "vegetation"


def test_search_assets_core_no_match():
    """无匹配资产时返回空列表。"""
    idx = StubAssetIndex(assets=[{"path": "/Game/Rock"}])
    assert search_assets_core(idx, ["tree"]) == []


def test_search_assets_core_max_results():
    """max_results 限制返回数量。"""
    idx = StubAssetIndex(
        assets=[
            {"path": "/Game/Tree1"},
            {"path": "/Game/Tree2"},
            {"path": "/Game/Tree3"},
        ]
    )
    results = search_assets_core(idx, ["tree"], max_results=2)
    assert len(results) == 2
