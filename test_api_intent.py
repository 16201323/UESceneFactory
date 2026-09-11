import os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
api_key = os.environ["ALIYUN_APIKEY"]
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
from openai import OpenAI

client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)

t0 = time.time()
print(f"[{time.strftime('%H:%M:%S')}] 发送意图解析请求...", flush=True)
try:
    resp = client.chat.completions.create(
        model="glm-5.2",
        messages=[
            {"role": "system", "content": "你是一个UE5场景意图解析器。输出JSON。只输出JSON。"},
            {"role": "user", "content": "生成一个中国农村场景"},
        ],
        response_format={"type": "json_object"},
        max_tokens=2048,
    )
    content = resp.choices[0].message.content
    print(f"[{time.strftime('%H:%M:%S')}] 完成! 耗时 {time.time()-t0:.1f}s", flush=True)
    print(f"Content: {content}", flush=True)
except Exception as e:
    print(f"错误: {e}", flush=True)