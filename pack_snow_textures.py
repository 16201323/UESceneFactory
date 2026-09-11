"""
将 ambientCG Snow001 纹理转换为项目所需的格式
- TX_Snow_ALB.jpg ← Color.jpg (反照率)
- TX_Snow_NRM.jpg ← NormalDX.jpg (DirectX 法线，UE5 默认)
- TX_Snow_RMA.jpg ← 打包 R=粗糙度 G=金属度(0) B=环境光遮蔽(255)
"""
from PIL import Image
import shutil
import os

src_dir = r"c:\Users\25868\Desktop\UE5\MapForgeTest\Snow001"
dst_dir = r"c:\Users\25868\Desktop\UE5\MapForgeTest\SnowTextures"
os.makedirs(dst_dir, exist_ok=True)

# 1. 反照率: 直接复制 Color
color_src = os.path.join(src_dir, "Snow001_1K-JPG_Color.jpg")
alb_dst = os.path.join(dst_dir, "TX_Snow_ALB.jpg")
shutil.copy2(color_src, alb_dst)
print(f"[OK] TX_Snow_ALB.jpg <- Color.jpg")

# 2. 法线: 使用 DirectX 格式 (UE5 默认)
normal_src = os.path.join(src_dir, "Snow001_1K-JPG_NormalDX.jpg")
nrm_dst = os.path.join(dst_dir, "TX_Snow_NRM.jpg")
shutil.copy2(normal_src, nrm_dst)
print(f"[OK] TX_Snow_NRM.jpg <- NormalDX.jpg")

# 3. RMA 打包: R=粗糙度, G=金属度(0=黑), B=AO(255=白)
roughness_src = os.path.join(src_dir, "Snow001_1K-JPG_Roughness.jpg")
roughness = Image.open(roughness_src).convert("L")
w, h = roughness.size
print(f"  粗糙度图尺寸: {w}x{h}")

rma = Image.new("RGB", (w, h))
pixels_r = roughness.load()
pixels_rma = rma.load()
for y in range(h):
    for x in range(w):
        r_val = pixels_r[x, y]       # R = 粗糙度
        g_val = 0                    # G = 金属度 (雪非金属, =0)
        b_val = 255                  # B = 环境光遮蔽 (纯净雪无遮蔽, =255)
        pixels_rma[x, y] = (r_val, g_val, b_val)

rma_dst = os.path.join(dst_dir, "TX_Snow_RMA.jpg")
rma.save(rma_dst, "JPEG", quality=95)
print(f"[OK] TX_Snow_RMA.jpg <- R:粗糙度 G:0 B:255 (打包完成)")

# 打印结果
print("\n=== 输出文件 ===")
for f in os.listdir(dst_dir):
    path = os.path.join(dst_dir, f)
    print(f"  {f}: {os.path.getsize(path) // 1024} KB")
