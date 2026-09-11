import sys
import os
import json
import time

# tests/manual/ 向上两级到项目根目录
script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, script_dir)

from ai.client import OpenAILLMClient
from ai.intent_parser import IntentParser
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.generator import SceneGenerator
from ai.validator import ValidationRepairLoop
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        return os.path.join(base, relative_path)
    return os.path.join(script_dir, relative_path)


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


log("=" * 60)
log("AI 场景生成 — 完整三阶段管线测试")
log("=" * 60)

user_desc = "生成一个2km*2km的中国农村场景，要有村落、草地、河流、道路、山脉、树林、麦田等元素，地形要有起伏"
log(f"用户描述: {user_desc}")

config = {"llm_intent_model": None, "llm_strong_model": None}
api_key = os.environ["ALIYUN_APIKEY"]
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

client = OpenAILLMClient(api_key=api_key, model="glm-5.2", base_url=base_url)

t_overall = time.time()

# ====== Stage 1: 意图解析 ======
log("--- Stage 1: 意图解析 ---")
t1 = time.time()
intent_parser = IntentParser(client, model=None)
intent = intent_parser.parse(user_desc)
log(f"Stage 1 完成: {time.time()-t1:.1f}s")
log(f"意图: {json.dumps(intent, ensure_ascii=False)}")

# ====== Stage 2: 知识注入 + 场景生成 ======
log("--- Stage 2: 知识注入 + 场景生成 ---")
t2 = time.time()

knowledge = KnowledgePack(
    get_resource_path("data/knowledge"),
    templates_dir=get_resource_path("data/templates"),
)
# asset_catalog.json 已移入 config/ 目录
asset_index = AssetIndex(get_resource_path("config/asset_catalog.json"))
bank = ExperienceBank()
retriever = ExperienceRetriever(bank)
few_shots = retriever.retrieve(intent, top_k=3)
log(f"知识包已构建, few_shots={len(few_shots)}条, 匹配后将注入模板")

generator = SceneGenerator(client, knowledge, asset_index, model=None)
log("开始调用 LLM 生成场景 JSON (system prompt 约50KB, max_tokens=32768)...")
scene = generator.generate(user_desc, intent, few_shots)
log(f"Stage 2 完成: {time.time()-t2:.1f}s")
log(f"场景 JSON 长度: {len(json.dumps(scene, ensure_ascii=False))} 字符")

# ====== Stage 3: 验证-修复 ======
log("--- Stage 3: 验证-修复 ---")
t3 = time.time()
loop = ValidationRepairLoop(client, knowledge=knowledge, model=None)
final_scene, history = loop.validate_and_repair(scene, user_desc, intent=intent)
log(f"Stage 3 完成: {time.time()-t3:.1f}s")

success = not history[-1]["errors"] if history else False
total_elapsed = time.time() - t_overall

log("=" * 60)
log(f"管线完成! 总耗时 {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")
log(f"成功={success}, 验证轮次={len(history)}")
if history:
    for i, h in enumerate(history):
        errors = h.get('errors', [])
        log(f"  轮{i+1}: {'❌' if errors else '✅'} {len(errors)}个错误")

out_path = os.path.join(script_dir, "test_output_rural.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(final_scene, f, ensure_ascii=False, indent=2)
log(f"场景 JSON 已保存: {out_path} ({os.path.getsize(out_path)} bytes)")

if few_shots:
    for exp in few_shots:
        bank.update_usage(exp["id"], success=success)
bank.close()