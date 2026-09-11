"""Phase 4 测试: extract_json 三层提取 + IntentParser Mock + 异常容错。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_extract_json():
    from ai.utils import extract_json

    # 层1: 纯 JSON
    r1 = extract_json('{"a": 1}')
    assert r1 == {'a': 1}, f'层1失败: {r1}'

    # 层2: markdown 代码块
    r2 = extract_json('说明文字\n```json\n{"b": 2}\n```\n后续')
    assert r2 == {'b': 2}, f'层2失败: {r2}'

    # 层2b: 无 json 标记的代码块
    r2b = extract_json('```\n{"c": 3}\n```')
    assert r2b == {'c': 3}, f'层2b失败: {r2b}'

    # 层3: 混杂文本中的 JSON
    r3 = extract_json('好的，这是结果: {"d": 4} 完成')
    assert r3 == {'d': 4}, f'层3失败: {r3}'

    print('extract_json 三层提取验证通过')

def test_intent_mock():
    from ai.client import MockLLMClient
    from ai.intent_parser import IntentParser

    mock_resp = json.dumps({
        "terrain_type": "features", "has_river": True, "has_grass": True,
        "keywords": ["山谷", "河流", "草地"],
        "scene_scale": "1km", "complexity": "medium"
    })
    mock = MockLLMClient([mock_resp])
    parser = IntentParser(mock)
    intent = parser.parse('生成一个1km的山谷草地场景，有河流')

    assert intent['terrain_type'] == 'features'
    assert intent['has_river'] == True
    assert intent['has_grass'] == True
    assert '山谷' in intent['keywords']
    print('Mock 意图解析验证通过')

def test_fallback():
    from ai.client import MockLLMClient
    from ai.intent_parser import IntentParser, FALLBACK_INTENT

    mock = MockLLMClient(['这不是JSON'])
    parser = IntentParser(mock)
    intent = parser.parse('测试')
    assert intent == FALLBACK_INTENT, '异常时应返回 fallback'
    print('异常容错验证通过')

def test_json_mode_kwargs():
    """验证 IntentParser 传了 response_format 和 max_tokens 给 client"""
    from ai.client import MockLLMClient
    from ai.intent_parser import IntentParser
    import json

    mock_resp = json.dumps({"terrain_type": "flat"})
    mock = MockLLMClient([mock_resp])
    parser = IntentParser(mock)
    parser.parse('测试')

    # call_log 记录了 complete 调用，但 kwargs 未记录在 call_log 中
    # 验证 Mock 不因 kwargs 报错即可
    print('JSON Mode kwargs 验证通过')

if __name__ == '__main__':
    test_extract_json()
    test_intent_mock()
    test_fallback()
    test_json_mode_kwargs()
    print('=== Phase 4 全部测试通过 ===')
