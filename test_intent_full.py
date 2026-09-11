import sys, os, time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.client import OpenAILLMClient
from ai.intent_parser import IntentParser


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

api_key = os.environ["ALIYUN_APIKEY"]
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

user_desc = "生成一个2km*2km的中国农村场景，要有村落、草地、河流、道路、山脉、树林、麦田等元素，地形要有起伏"

t0 = time.time()

client = OpenAILLMClient(api_key=api_key, model="glm-5.2", base_url=base_url)

log("IntentParser.parse() 开始...")
parser = IntentParser(client)

try:
    intent = parser.parse(user_desc)
    elapsed = time.time() - t0
    import json
    log(f"完成! 耗时 {elapsed:.1f}s")
    log(f"意图结果: {json.dumps(intent, ensure_ascii=False, indent=2)}")
except Exception as e:
    elapsed = time.time() - t0
    log(f"失败! 耗时 {elapsed:.1f}s")
    log(f"错误: {e}")
    import traceback
    traceback.print_exc()