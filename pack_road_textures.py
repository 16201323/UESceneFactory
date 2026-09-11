"""
将 ambientCG Ground103 泥土纹理转换为项目所需格式
- TX_Dirt_ALB.jpg <- Color.jpg (反照率, sRGB)
- TX_Dirt_NRM.jpg <- NormalDX.jpg (DirectX 法线, UE5 默认)
- TX_Dirt_RMA.jpg <- 打包 R=粗糙度 G=金属度(0) B=环境光遮蔽(来自真实AO图)

与 pack_snow_textures.py 区别:
  - 泥土用真实 AmbientOcclusion 图作为 B 通道 (雪地用纯白 255),
    使凹陷/裂缝处更暗, 视觉更自然
  - 用 PIL Image.merge 向量化打包 (C 层实现), 替代像素级双重循环
"""
from PIL import Image
import shutil
import os

src_dir = r"c:\Users\25868\Desktop\UE5\MapForgeTest\downloads\Ground103_1K-JPG"
dst_dir = r"c:\Users\25868\Desktop\UE5\MapForgeTest\DirtTextures"
os.makedirs(dst_dir, exist_ok=True)


def check(name):
    p = os.path.join(src_dir, name)
    if not os.path.exists(p):
        print(f"[ERR] 源文件缺失: {p}")
        return None
    return p


# 1. 反照率: 直接复制 Color
color_src = check("Ground103_1K-JPG_Color.jpg")
if not color_src:
    raise SystemExit(1)
alb_dst = os.path.join(dst_dir, "TX_Dirt_ALB.jpg")
shutil.copy2(color_src, alb_dst)
print("[OK] TX_Dirt_ALB.jpg <- Color.jpg")

# 2. 法线: 使用 DirectX 格式 (UE5 默认)
normal_src = check("Ground103_1K-JPG_NormalDX.jpg")
if not normal_src:
    raise SystemExit(1)
nrm_dst = os.path.join(dst_dir, "TX_Dirt_NRM.jpg")
shutil.copy2(normal_src, nrm_dst)
print("[OK] TX_Dirt_NRM.jpg <- NormalDX.jpg")

# 3. RMA 打包: R=粗糙度, G=金属度(0=黑, 泥土非金属), B=环境光遮蔽(真实AO)
roughness_src = check("Ground103_1K-JPG_Roughness.jpg")
ao_src = check("Ground103_1K-JPG_AmbientOcclusion.jpg")
if not (roughness_src and ao_src):
    raise SystemExit(1)

roughness = Image.open(roughness_src).convert("L")
ao = Image.open(ao_src).convert("L")
w, h = roughness.size
print(f"  粗糙度图尺寸: {w}x{h}")

# AO 尺寸对齐 (理论上同源应一致, 防御性处理)
if ao.size != (w, h):
    ao = ao.resize((w, h), Image.BILINEAR)
    print(f"  AO 已缩放至 {w}x{h}")

# 用 Image.merge 向量化打包 (R=roughness, G=纯黑金属度, B=真实AO)
metallic_zero = Image.new("L", (w, h), 0)
rma = Image.merge("RGB", (roughness, metallic_zero, ao))

rma_dst = os.path.join(dst_dir, "TX_Dirt_RMA.jpg")
rma.save(rma_dst, "JPEG", quality=95)
print("[OK] TX_Dirt_RMA.jpg <- R:粗糙度 G:0 B:真实AO (打包完成)")

# 打印结果
print("\n=== 输出文件 ===")
for f in sorted(os.listdir(dst_dir)):
    path = os.path.join(dst_dir, f)
    print(f"  {f}: {os.path.getsize(path) // 1024} KB")
