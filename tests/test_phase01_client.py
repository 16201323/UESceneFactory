"""Phase 1 测试: LLM 客户端 Mock 初始化 + kwargs 透传。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_mock_basic():
    from ai.client import MockLLMClient
    c = MockLLMClient(['{"test": true}'])
    r = c.complete('sys', 'user')
    assert r == '{"test": true}'
    print('Mock 客户端测试通过')

def test_openai_init():
    from ai.client import OpenAILLMClient
    c = OpenAILLMClient(api_key='test-key', model='gpt-4o', base_url='https://api.deepseek.com/v1')
    print('OpenAI 客户端初始化通过')

def test_kwargs_passthrough():
    from ai.client import MockLLMClient
    c = MockLLMClient(['{"test": true}'])
    r = c.complete('sys', 'user', response_format={'type': 'json_object'}, max_tokens=4096)
    assert r == '{"test": true}'
    print('kwargs 透传验证通过')

def test_call_log():
    from ai.client import MockLLMClient
    c = MockLLMClient(['resp1', 'resp2'])
    c.complete('sys1', 'user1')
    c.complete('sys2', 'user2')
    assert len(c.call_log) == 2
    assert c.call_log[0] == ('sys1', 'user1')
    print('call_log 验证通过')

if __name__ == '__main__':
    test_mock_basic()
    test_openai_init()
    test_kwargs_passthrough()
    test_call_log()
    print('=== Phase 1 全部测试通过 ===')
