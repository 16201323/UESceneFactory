"""Phase 7 测试: ExperienceBank CRUD + 去重 + 默认路径。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_create_db():
    if os.path.exists('data/test_exp.db'):
        os.remove('data/test_exp.db')
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank('data/test_exp.db')
    assert os.path.exists('data/test_exp.db'), '数据库文件未创建'
    bank.close()
    print('数据库创建验证通过')

def test_save_query():
    if os.path.exists('data/test_exp.db'):
        os.remove('data/test_exp.db')
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank('data/test_exp.db')
    exp_id = bank.save(
        '生成山谷草地场景',
        {'terrain_type': 'features', 'has_river': True},
        {'scene': {'target_level': '/Game/Test'}},
        rating=4, tags='山谷,草地'
    )
    assert exp_id > 0, f'保存失败: {exp_id}'
    exp = bank.get_by_id(exp_id)
    assert exp['user_desc'] == '生成山谷草地场景'
    assert exp['rating'] == 4
    assert exp['intent']['has_river'] == True
    bank.close()
    print('保存查询验证通过')

def test_update_stats():
    if os.path.exists('data/test_exp.db'):
        os.remove('data/test_exp.db')
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank('data/test_exp.db')
    exp_id = bank.save('test', {}, {}, rating=3)
    bank.update_rating(exp_id, 5)
    bank.update_usage(exp_id, success=True)
    bank.update_usage(exp_id, success=True)
    bank.update_usage(exp_id, success=False)
    exp = bank.get_by_id(exp_id)
    assert exp['rating'] == 5
    assert exp['used_count'] == 3
    assert exp['success_count'] == 2
    assert exp['fail_count'] == 1
    bank.close()
    print('更新统计验证通过')

def test_stats():
    if os.path.exists('data/test_exp.db'):
        os.remove('data/test_exp.db')
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank('data/test_exp.db')
    for i in range(5):
        bank.save(f'test{i}', {}, {}, rating=i+1)
    stats = bank.get_stats()
    assert stats['total'] == 5, f'总数应为5, 实际{stats["total"]}'
    assert stats['avg_rating'] == 3.0, f'平均评分应为3.0, 实际{stats["avg_rating"]}'
    bank.close()
    print('统计信息验证通过')

def test_dedup():
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank(':memory:')
    id1 = bank.save(
        '生成山谷草地场景',
        {'terrain_type': 'features', 'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/Test1'}},
        rating=4
    )
    id2 = bank.save(
        '另一个山谷草地描述',
        {'terrain_type': 'features', 'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/Test2'}},
        rating=5
    )
    assert id1 == id2, f'相似经验应去重更新(同id), id1={id1}, id2={id2}'
    all_exps = bank.get_all()
    assert len(all_exps) == 1, f'去重后应只有1条, 实际{len(all_exps)}'
    assert all_exps[0]['rating'] == 5, f'rating应被更新为5, 实际{all_exps[0]["rating"]}'
    bank.close()
    print('去重逻辑验证通过')

def test_default_path():
    from pathlib import Path
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank()
    assert str(Path.home() / '.uescenefactory' / 'experience.db') == bank._db_path
    assert Path(bank._db_path).exists(), f'默认路径数据库未创建: {bank._db_path}'
    bank.close()
    print(f'默认路径验证通过: {bank._db_path}')

def test_fts5_candidate_filter():
    """验证 FTS5 索引: 大量经验时 _find_similar 不全表扫描, 仅返回关键词重叠候选。"""
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank(':memory:')
    # 插入 100 条无关键词重叠的经验
    for i in range(100):
        bank.save(
            f'desc_{i}',
            {'keywords': [f'kw_{i}']},
            {'scene': {'target_level': f'/Game/T{i}'}},
            rating=3,
        )
    # 插入 1 条与查询高度重叠的经验
    bank.save(
        '目标经验',
        {'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/Target'}},
        rating=5,
    )
    # 查询: 关键词完全重叠
    similar = bank._find_similar({'keywords': ['grass', 'tree', 'river']})
    assert similar is not None, '应找到相似经验'
    # _find_similar 仅返回 {"id": ...}, 通过 id 验证匹配的是目标经验
    matched = bank.get_by_id(similar["id"])
    assert matched["user_desc"] == '目标经验', f"应匹配目标经验, 实际: {matched['user_desc']}"
    # 查询: 关键词无重叠 (不应匹配任何经验)
    none_result = bank._find_similar({'keywords': ['nonexistent']})
    assert none_result is None, '无关键词重叠时应返回 None'
    bank.close()
    print('FTS5 候选过滤验证通过')

def test_fts5_backward_compat():
    """验证 FTS5 改造后原有去重逻辑仍正常工作。"""
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank(':memory:')
    id1 = bank.save(
        '山谷草地',
        {'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/T1'}},
        rating=4,
    )
    id2 = bank.save(
        '另一个山谷草地',
        {'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/T2'}},
        rating=5,
    )
    assert id1 == id2, '相似经验应去重(同id)'
    assert len(bank.get_all()) == 1, '去重后应只有1条'
    assert bank.get_by_id(id1)['rating'] == 5, 'rating应被更新'
    bank.close()
    print('FTS5 向后兼容验证通过')

if __name__ == '__main__':
    test_create_db()
    test_save_query()
    test_update_stats()
    test_stats()
    test_dedup()
    test_default_path()
    test_fts5_candidate_filter()
    test_fts5_backward_compat()
    print('=== Phase 7 全部测试通过 ===')
