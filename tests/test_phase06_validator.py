"""Phase 6 测试: 无错误直通 + 有错误修复 + 修复失败容错 + 知识注入。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GOOD_SCENE = {
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/M', 'section_size_quads': 63,
        'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8,
        'layers': [{'info': '/Game/L', 'weight': 1.0}],
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
}

FIXED_SCENE = json.dumps({
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/M', 'section_size_quads': 63,
        'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8,
        'layers': [{'info': '/Game/L', 'weight': 1.0}],
        'grass': {
            'grass_type': '/Game/RuralHouse/Landscape/LandscapeFoliage/LGT_Grass',
            'grass_mesh': '/Game/Foliage_Sets/VOL22_WildGrass/Meshes/SM_Grass_Tall_Wild_01a',
            'layer_name': 'Grass', 'density': 120.0
        },
        'height_pattern': {'type': 'flat'}
    },
    'lighting': {
        'directional_light': {'location': [0, 0, 3000]},
        'sky_light': {'location': [0, 0, 3000]},
        'sky_atmosphere': {'location': [0, 0, 0]}
    },
    'weather': {'volumetric_clouds': {'location': [0, 0, 2000]}}
})

# 坏场景：landscape 非空但缺少 section_size_quads 等 4 个必填字段
# 注意：不能用 {'scene': {}} —— validate_scene_json 中 if s: 对空字典 falsy 跳过校验
# landscape 有 material 字段 → truthy → 触发 validate_required → 报 4 个缺少必填字段错误
BAD_SCENE = {'landscape': {'material': '/Game/M'}}

def test_good_scene_passes():
    from ai.client import MockLLMClient
    from ai.validator import ValidationRepairLoop

    mock = MockLLMClient([])
    loop = ValidationRepairLoop(mock)
    final, history = loop.validate_and_repair(GOOD_SCENE, '测试场景')
    assert len(history) == 1, f'无错误应1轮通过, 实际{len(history)}'
    assert len(history[0]['errors']) == 0, '第1轮应无错误'
    print('无错误直通验证通过')

def test_bad_scene_repaired():
    from ai.client import MockLLMClient
    from ai.validator import ValidationRepairLoop

    mock = MockLLMClient([FIXED_SCENE])
    loop = ValidationRepairLoop(mock)
    final, history = loop.validate_and_repair(BAD_SCENE, '测试场景')
    assert len(history) == 2, f'应有2轮(1错误+1通过), 实际{len(history)}'
    assert len(history[0]['errors']) > 0, '第1轮应有错误'
    assert len(history[1]['errors']) == 0, '第2轮应无错误'
    print('错误修复验证通过')

def test_repair_failure_tolerant():
    from ai.client import MockLLMClient
    from ai.validator import ValidationRepairLoop

    mock = MockLLMClient(['不是JSON'])
    loop = ValidationRepairLoop(mock, max_rounds=2)
    final, history = loop.validate_and_repair(BAD_SCENE, '测试')
    assert isinstance(final, dict), '最终结果应仍为dict'
    assert len(history) <= 2, f'不应超过2轮, 实际{len(history)}'
    print('修复失败容错验证通过')

def test_knowledge_injection():
    """验证 knowledge 参数传入后修复时注入知识包 system_prompt"""
    from ai.client import MockLLMClient
    from ai.knowledge import KnowledgePack
    from ai.validator import ValidationRepairLoop

    mock = MockLLMClient([FIXED_SCENE])
    kp = KnowledgePack('data/knowledge')
    intent = {'terrain_type': 'features', 'has_grass': True, 'keywords': ['grass'], 'placements': []}
    loop = ValidationRepairLoop(mock, knowledge=kp)
    final, history = loop.validate_and_repair(BAD_SCENE, '测试', intent=intent)
    # 验证传入了 knowledge + intent 不崩溃
    assert isinstance(final, dict)
    print('知识注入验证通过')

if __name__ == '__main__':
    test_good_scene_passes()
    test_bad_scene_repaired()
    test_repair_failure_tolerant()
    test_knowledge_injection()
    print('=== Phase 6 全部测试通过 ===')
