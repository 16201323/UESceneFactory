"""Phase 5 测试: SceneGenerator Mock 生成 + validate_scene 校验。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MOCK_SCENE = json.dumps({
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/Materials/M_Landscape',
        'section_size_quads': 63,
        'num_subsections': 2,
        'component_count_x': 8,
        'component_count_y': 8,
        'layers': [{'info': '/Game/Layers/Default', 'weight': 1.0}],
        # L1/L2 根因修复后 grass/height_pattern 为必填字段
        'grass': {
            'grass_type': '/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass',
            'grass_mesh': '/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a',
            'layer_name': 'Grass', 'density': 120.0
        },
        'height_pattern': {'type': 'flat'}
    },
    # L1/L2 根因修复后 lighting/weather 为必填字段
    'lighting': {
        'directional_light': {'location': [0, 0, 3000]},
        'sky_light': {'location': [0, 0, 3000]},
        'sky_atmosphere': {'location': [0, 0, 0]}
    },
    'weather': {'volumetric_clouds': {'location': [0, 0, 2000]}}
})

def test_mock_generate():
    from ai.client import MockLLMClient
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.generator import SceneGenerator

    mock = MockLLMClient([MOCK_SCENE])
    kp = KnowledgePack('data/knowledge')
    # asset_catalog.json 已移入 config/ 目录
    ai = AssetIndex('config/asset_catalog.json')
    gen = SceneGenerator(mock, kp, ai)

    intent = {'terrain_type': 'features', 'has_grass': True, 'keywords': ['grass'], 'placements': []}
    scene = gen.generate('生成一个草地场景', intent)

    assert 'scene' in scene
    assert 'landscape' in scene
    assert scene['scene']['target_level'] == '/Game/Maps/Test'
    print('Mock JSON 生成验证通过')

def test_validate_generated():
    from ai.client import MockLLMClient
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.generator import SceneGenerator
    # validate_scene_json 已移入 scripts/
    from scripts.validate_scene_json import validate_scene

    mock = MockLLMClient([MOCK_SCENE])
    kp = KnowledgePack('data/knowledge')
    # asset_catalog.json 已移入 config/ 目录
    ai = AssetIndex('config/asset_catalog.json')
    gen = SceneGenerator(mock, kp, ai)

    intent = {'terrain_type': 'features', 'has_grass': True, 'keywords': ['grass'], 'placements': []}
    scene = gen.generate('生成一个草地场景', intent)

    errors, warnings = validate_scene(scene)
    assert len(errors) == 0, f'生成的 JSON 有校验错误: {errors[:3]}'
    print(f'字段校验验证通过 ({len(warnings)} warnings)')

if __name__ == '__main__':
    test_mock_generate()
    test_validate_generated()
    print('=== Phase 5 全部测试通过 ===')
