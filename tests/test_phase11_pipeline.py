"""Phase 11 测试: Mock 端到端管线 run_pipeline。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_mock_pipeline():
    from ai.client import MockLLMClient
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.intent_parser import IntentParser
    from ai.generator import SceneGenerator
    from ai.validator import ValidationRepairLoop
    from validate_scene_json import validate_scene

    intent_resp = json.dumps({
        'terrain_type': 'features', 'has_river': True, 'has_grass': True,
        'keywords': ['grass', 'tree'], 'scene_scale': '1km', 'complexity': 'medium'
    })
    scene_resp = json.dumps({
        'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
        'landscape': {
            'material': '/Game/M', 'section_size_quads': 63, 'num_subsections': 2,
            'component_count_x': 8, 'component_count_y': 8,
            'layers': [{'info': '/Game/L', 'weight': 1.0}]
        }
    })

    mock = MockLLMClient([intent_resp, scene_resp])
    kp = KnowledgePack('data/knowledge')
    ai = AssetIndex('asset_catalog.json')

    # Stage 1
    parser = IntentParser(mock)
    intent = parser.parse('山谷草地')
    assert intent['terrain_type'] == 'features'

    # Stage 2
    gen = SceneGenerator(mock, kp, ai)
    scene = gen.generate('山谷草地', intent)
    assert 'scene' in scene

    # Stage 3
    loop = ValidationRepairLoop(mock)
    final, history = loop.validate_and_repair(scene, '山谷草地')
    errors, _ = validate_scene(final)
    assert len(errors) == 0, f'应有0错误, 实际{len(errors)}'
    print(f'端到端验证: {len(history)}轮, 最终{len(errors)}错误')
    print('Mock 端到端管线验证通过')


if __name__ == '__main__':
    test_mock_pipeline()
    print('=== Phase 11 全部测试通过 ===')
