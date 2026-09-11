"""UE场景工厂 UESceneFactory AI 场景生成器包。

提供 run_pipeline() 供非 GUI 测试使用；
GUI 场景用 AIWorker.run() 内联版本（发 Qt 信号）。
"""
import sys
import os


def get_resource_path(relative_path):
    """获取资源路径（兼容开发模式和 PyInstaller 打包模式）"""
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        return os.path.join(base, relative_path)
    return relative_path


def run_pipeline(client, config, user_desc, feedback=None):
    """完整三阶段管线（供非 GUI 测试使用；GUI 用 AIWorker.run 内联版本发信号）

    参数:
        client: LLMClient 实例
        config: dict — 含 llm_intent_model / llm_strong_model 等
        user_desc: str — 用户自然语言描述
        feedback: str | None — 反馈信息（重新生成时传入）

    返回: (final_scene, intent, history, success)
    """
    from ai.intent_parser import IntentParser
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.generator import SceneGenerator
    from ai.validator import ValidationRepairLoop
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever

    intent_parser = IntentParser(client, model=config.get("llm_intent_model"))
    intent = intent_parser.parse(user_desc)

    knowledge = KnowledgePack(
        get_resource_path("data/knowledge"),
        templates_dir=get_resource_path("data/templates"),
    )
    asset_index = AssetIndex(get_resource_path("asset_catalog.json"))
    bank = ExperienceBank()
    retriever = ExperienceRetriever(bank)

    few_shots = retriever.retrieve(intent, top_k=3)

    generator = SceneGenerator(client, knowledge, asset_index, model=config.get("llm_strong_model"))
    scene = generator.generate(user_desc, intent, few_shots)

    loop = ValidationRepairLoop(client, knowledge=knowledge, model=config.get("llm_strong_model"))
    final_scene, history = loop.validate_and_repair(scene, user_desc, intent=intent)

    success = not history[-1]["errors"] if history else False

    if few_shots:
        for exp in few_shots:
            bank.update_usage(exp["id"], success=success)

    bank.close()
    return final_scene, intent, history, success
