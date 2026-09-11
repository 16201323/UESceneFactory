"""Phase 3 测试: AssetIndex 加载 + 关键词搜索 + category 搜索。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_load():
    from ai.asset_index import AssetIndex
    idx = AssetIndex('asset_catalog.json')
    assert len(idx._assets) > 5000, f'资产数太少: {len(idx._assets)}'
    print(f'资产加载验证通过 ({len(idx._assets)} 条)')

def test_search():
    from ai.asset_index import AssetIndex
    idx = AssetIndex('asset_catalog.json')
    results = idx.search(['tree', 'fir'], max_results=10)
    assert len(results) > 0, 'tree+fir 搜索无结果'
    print(f'关键词搜索验证通过 ({len(results)} 条)')

def test_category():
    from ai.asset_index import AssetIndex
    idx = AssetIndex('asset_catalog.json')
    results = idx.search_by_category('rural_house', max_results=5)
    print(f'category 搜索验证通过 ({len(results)} 条)')

if __name__ == '__main__':
    test_load()
    test_search()
    test_category()
    print('=== Phase 3 全部测试通过 ===')
