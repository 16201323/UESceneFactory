# 对比修复旋转前(00009)与修复后(00010)的截图
# 关键验证: 地面亮度变化 = 太阳从地下升到地上 = 旋转修复生效
import sys
from PIL import Image

DIR = r"D:\code\UEEnvironment\MyUETest5_8_2\MyUETest5_8_2\Saved\Screenshots\WindowsEditor"

for name in ["HighresScreenshot00009.png", "HighresScreenshot00010.png"]:
    path = DIR + "\\" + name
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:
        print(name + " ERROR: " + str(e))
        continue
    W, H = img.size
    px = img.load()
    # 整体 + 地面区域(下半部分) + 天空区域(上半部分) 的平均亮度
    all_sum = sky_sum = ground_sum = 0
    all_n = W * H
    sky_n = W * (H // 2)
    ground_n = W * (H - H // 2)
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            lum = (r + g + b) / 3
            all_sum += lum
            if y < H // 2:
                sky_sum += lum
            else:
                ground_sum += lum
    print("{} ({}x{}): all_L={:.1f} sky_L={:.1f} ground_L={:.1f}".format(
        name, W, H,
        all_sum / all_n,
        sky_sum / sky_n,
        ground_sum / ground_n))

print("DONE")
