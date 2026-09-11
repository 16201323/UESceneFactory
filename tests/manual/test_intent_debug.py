import sys, os, time

sys.stdout.reconfigure(encoding='utf-8')
# tests/manual/ 向上三级到项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ai.client import OpenAILLMClient


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

api_key = os.environ["ALIYUN_APIKEY"]
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

t0 = time.time()

client = OpenAILLMClient(api_key=api_key, model="glm-5.2", base_url=base_url)

t1 = time.time()
log(f"OpenAILLMClient 创建耗时 {t1-t0:.1f}s")

user_desc = "生成一个2km*2km的中国农村场景，要有村落、草地、河流、道路、山脉、树林、麦田等元素，地形要有起伏"

try:
    resp = client.complete(
        '你是一个 UE5 场景意图解析器。从用户描述中提取结构化信息。输出 JSON，只输出 JSON，不要其他文字。',
        user_desc,
        response_format={"type": "json_object"},
        max_tokens=2048,
    )
    elapsed = time.time() - t1
    log(f"complete() 完成, 耗时 {elapsed:.1f}s")
    log(f"响应: {resp[:500]}")
except Exception as e:
    elapsed = time.time() - t1
    log(f"complete() 失败, 耗时 {elapsed:.1f}s")
    log(f"错误: {e}")
    import traceback
    traceback.print_exc()