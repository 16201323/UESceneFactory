import os, sys
sys.stdout.reconfigure(encoding='utf-8')

api_key = os.environ.get("ALIYUN_APIKEY", "")
base_url = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

from openai import OpenAI
client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)

resp = client.chat.completions.create(
    model="glm-5.2",
    messages=[
        {"role": "system", "content": "回复JSON"},
        {"role": "user", "content": "返回 {\"ok\": true}"},
    ],
    response_format={"type": "json_object"},
    max_tokens=256,
)
content = resp.choices[0].message.content
print(f"OK: {content}", flush=True)