"""Phase 8 测试: ExperienceRetriever 四因子检索 + 不污染使用统计。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_empty_bank():
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever
    bank = ExperienceBank(':memory:')
    ret = ExperienceRetriever(bank)
    results = ret.retrieve({'keywords': ['test']})
    assert results == [], f'空库应返回空列表, 实际{len(results)}'
    bank.close()
    print('空库验证通过')

def test_keyword_similarity():
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever
    bank = ExperienceBank(':memory:')
    ret = ExperienceRetriever(bank)

    # 完全相同
    sim1 = ret._keyword_similarity(['grass', 'tree', 'river'], ['grass', 'tree', 'river'])
    assert sim1 == 1.0, f'完全相同应=1.0, 实际{sim1}'

    # 部分重叠
    sim2 = ret._keyword_similarity(['grass', 'tree'], ['tree', 'river'])
    assert 0 < sim2 < 1.0, f'部分重叠应在0~1, 实际{sim2}'

    # 完全不同
    sim3 = ret._keyword_similarity(['mountain'], ['city'])
    assert sim3 == 0.0, f'完全不同应=0, 实际{sim3}'

    bank.close()
    print(f'关键词相似度验证通过: sim1={sim1}, sim2={sim2:.2f}, sim3={sim3}')

def test_retrieve_ranked():
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever
    bank = ExperienceBank(':memory:')
    bank.save('山谷草地河流场景', {'keywords': ['grass', 'river']}, {}, rating=5)
    bank.save('城市街道场景', {'keywords': ['city', 'road']}, {}, rating=3)
    bank.save('山谷松树河流', {'keywords': ['tree', 'river']}, {}, rating=4)
    ret = ExperienceRetriever(bank)
    results = ret.retrieve({'keywords': ['grass', 'river']}, top_k=2)
    assert len(results) <= 2, f'应最多返回2条, 实际{len(results)}'
    assert len(results) > 0, '应返回至少1条'
    assert '山谷' in results[0]['user_desc'], f'最相似应含山谷, 实际: {results[0]["user_desc"]}'
    bank.close()
    print('检索排序验证通过')

def test_no_usage_pollution():
    """retrieve 不应调用 update_usage（使用统计由管线末尾处理）"""
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever
    bank = ExperienceBank(':memory:')
    exp_id = bank.save('山谷草地', {'keywords': ['grass', 'tree']}, {}, rating=5)
    ret = ExperienceRetriever(bank)
    results = ret.retrieve({'keywords': ['grass', 'tree']}, top_k=3)
    assert len(results) > 0
    # 验证 used_count / fail_count 未被 retrieve 修改
    exp = bank.get_by_id(exp_id)
    assert exp['used_count'] == 0, f'retrieve不应修改used_count, 实际{exp["used_count"]}'
    assert exp['fail_count'] == 0, f'retrieve不应修改fail_count, 实际{exp["fail_count"]}'
    bank.close()
    print('不污染使用统计验证通过')

if __name__ == '__main__':
    test_empty_bank()
    test_keyword_similarity()
    test_retrieve_ranked()
    test_no_usage_pollution()
    print('=== Phase 8 全部测试通过 ===')
