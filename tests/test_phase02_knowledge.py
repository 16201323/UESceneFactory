"""Phase 2 测试: 知识文件存在性 + KnowledgePack 分层注入 + 模板标杆注入。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_knowledge_files():
    for f in ['core.md', 'height_pattern.md', 'weight_pattern.md', 'placements.md', 'asset_guide.md', 'examples.md', 'templates_index.md']:
        path = os.path.join('data/knowledge', f)
        size = os.path.getsize(path) if os.path.exists(path) else -1
        assert size > 100, f'{f} 太小或不存在 (size={size})'
    print('知识文件验证通过')

def test_template_files():
    """验证 12 个模板 JSON 文件已复制到 data/templates/"""
    import json
    tpl_dir = os.path.join('data', 'templates')
    files = [f for f in os.listdir(tpl_dir) if f.endswith('.json')]
    assert len(files) >= 11, f'模板文件不足 11 个, 实际 {len(files)} 个'
    # 抽样验证 P11 模板可正常解析为 JSON
    with open(os.path.join(tpl_dir, 'template_p11_all_terrain_realistic.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert 'landscape' in data, 'P11 模板缺 landscape 键'
    print(f'模板文件验证通过: {len(files)} 个模板')

def test_build_prompt():
    from ai.knowledge import KnowledgePack
    kp = KnowledgePack('data/knowledge', templates_dir='data/templates')
    intent = {
        'terrain_type': 'features', 'has_water': True, 'has_river': True,
        'has_grass': True, 'placements': ['trees'],
    }
    prompt = kp.build_system_prompt(intent, ['/Game/Test/asset1', '/Game/Test/asset2'], [])
    assert len(prompt) > 1000, f'prompt 太短: {len(prompt)}'
    assert '两层' in prompt or 'layer' in prompt.lower(), '缺少核心知识'
    # 验证模板标杆已注入(水系 intent 应匹配 P15 或 P11)
    assert '参考模板' in prompt, 'system prompt 缺少模板标杆注入'
    print(f'KnowledgePack 测试通过, prompt 长度: {len(prompt)} 字符')

def test_template_matching():
    """验证不同意图匹配到不同模板"""
    from ai.knowledge import KnowledgePack
    kp = KnowledgePack('data/knowledge', templates_dir='data/templates')

    # 梯田地形应匹配 P12
    prompt = kp.build_system_prompt(
        {'terrain_type': 'terraced', 'keywords': ['梯田']}, [], [])
    assert 'template_p12' in prompt, '梯田 intent 未匹配 P12 模板'

    # 喀斯特地形应匹配 P13
    prompt = kp.build_system_prompt(
        {'terrain_type': 'karst', 'keywords': ['喀斯特']}, [], [])
    assert 'template_p13' in prompt, '喀斯特 intent 未匹配 P13 模板'

    # 沟壑地形应匹配 P14
    prompt = kp.build_system_prompt(
        {'terrain_type': 'gully', 'keywords': ['沟壑']}, [], [])
    assert 'template_p14' in prompt, '沟壑 intent 未匹配 P14 模板'

    # 森林关键词应匹配 P10
    prompt = kp.build_system_prompt(
        {'terrain_type': 'features', 'keywords': ['森林', '树']}, [], [])
    assert 'template_p10' in prompt, '森林 intent 未匹配 P10 模板'

    # 河流关键词应匹配 P15(水系场景)
    prompt = kp.build_system_prompt(
        {'terrain_type': 'features', 'keywords': ['河流']}, [], [])
    assert 'template_p15' in prompt, '河流 intent 未匹配 P15 水系模板'

    # 默认 features(无特定关键词)应匹配 P11(全地形综合场景)
    prompt = kp.build_system_prompt(
        {'terrain_type': 'features', 'keywords': ['山丘', '草地']}, [], [])
    assert 'template_p11' in prompt, '默认 features intent 未匹配 P11 模板'

    # P2 围栏(45KB)应被排除, 不出现在任何 prompt 中
    prompt = kp.build_system_prompt(
        {'terrain_type': 'flat', 'keywords': ['围栏', 'fence']}, [], [])
    assert 'template_p2' not in prompt, 'P2 围栏(45KB)应被排除, 不应注入'

    print('模板匹配验证通过: 梯田→P12, 喀斯特→P13, 沟壑→P14, 森林→P10, 默认→P11, P2排除')

def test_layered_injection():
    from ai.knowledge import KnowledgePack
    kp = KnowledgePack('data/knowledge', templates_dir='data/templates')
    prompt_simple = kp.build_system_prompt(
        {'terrain_type': 'flat', 'has_grass': False, 'placements': []}, [], [])
    prompt_complex = kp.build_system_prompt(
        {'terrain_type': 'features', 'has_river': True, 'has_grass': True, 'placements': ['trees']},
        ['/Game/tree1'], [])
    assert len(prompt_complex) > len(prompt_simple), '复杂场景 prompt 应更长'
    print(f'分层注入验证通过: simple={len(prompt_simple)}, complex={len(prompt_complex)}')

def test_scale_note_injection():
    """recommended_scale≠1.0 时注入缩放提示，=1.0 时不注入。"""
    from ai.knowledge import KnowledgePack
    from ai.models.blueprint import AssetEntry
    kp = KnowledgePack('data/knowledge', templates_dir='data/templates')
    # 含缩放建议的 AssetEntry
    entries = [
        AssetEntry(path="/Game/House", recommended_scale=0.001, recommended_scale_note="需缩小"),
        AssetEntry(path="/Game/Tree", recommended_scale=1.0),
    ]
    prompt = kp.build_system_prompt(
        {'terrain_type': 'flat', 'placements': ['house']}, entries, []
    )
    assert '⚠️' in prompt, '缺少缩放警告'
    assert '0.001' in prompt, '缺少缩放值'
    assert '/Game/House' in prompt, '缺少资产路径'
    # 全部 scale=1.0 时不应有警告
    prompt_flat = kp.build_system_prompt(
        {'terrain_type': 'flat'}, [AssetEntry(path="/Game/Tree")], []
    )
    assert '⚠️' not in prompt_flat, 'scale=1.0 不应触发警告'
    print('缩放提示注入验证通过')

if __name__ == '__main__':
    test_knowledge_files()
    test_template_files()
    test_build_prompt()
    test_template_matching()
    test_layered_injection()
    test_scale_note_injection()
    print('=== Phase 2 全部测试通过 ===')
