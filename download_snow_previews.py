"""
下载 ambientCG 雪地纹理预览图并制作缩略图
用于向用户展示候选雪地纹理的视觉效果
"""
import urllib.request
import zipfile
import io
import os
import base64
from PIL import Image

# 候选雪地纹理列表
# (id, 显示名称, 描述, 1K-JPG ZIP 下载URL)
SNOW_TEXTURES = [
    {
        "id": "Snow001",
        "name": "Snow 001",
        "desc": "干净浅白雪 · 程序化生成 · 下载量24,894",
        "url": "https://ambientcg.com/get?file=Snow001_1K-JPG.zip",
        "local_color": r"c:\Users\25868\Desktop\UE5\MapForgeTest\Snow001\Snow001_1K-JPG_Color.jpg",
    },
    {
        "id": "Snow002",
        "name": "Snow 002",
        "desc": "干净浅白雪(不同图案) · 程序化生成 · 下载量29,414",
        "url": "https://ambientcg.com/get?file=Snow002_1K-JPG.zip",
        "local_color": None,
    },
    {
        "id": "Snow010C",
        "name": "Snow 010 C",
        "desc": "带脚印/轨迹的雪地 · 程序化生成",
        "url": "https://ambientcg.com/get?file=Snow010C_1K-JPG.zip",
        "local_color": None,
    },
    {
        "id": "Snow015",
        "name": "Snow 015",
        "desc": "脏污融化雪(含草地) · 摄影测量 · 下载量10,005",
        "url": "https://ambientcg.com/get?file=Snow015_1K-JPG.zip",
        "local_color": None,
    },
]

# 缩略图大小
THUMB_SIZE = (256, 256)
# 输出目录
OUT_DIR = r"c:\Users\25868\Desktop\UE5\MapForgeTest\SnowPreviews"
os.makedirs(OUT_DIR, exist_ok=True)


def download_and_extract_color(url, asset_id):
    """下载ZIP并提取Color.jpg，返回图片字节流"""
    print(f"  下载 {asset_id} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        zip_bytes = resp.read()
    print(f"    ZIP大小: {len(zip_bytes)//1024} KB")
    # 从ZIP中提取Color.jpg
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        color_name = None
        for name in zf.namelist():
            if "Color" in name and name.lower().endswith((".jpg", ".jpeg")):
                color_name = name
                break
        if color_name:
            return zf.read(color_name)
    return None


def make_thumbnail(image_bytes, size=THUMB_SIZE):
    """将图片字节流制作成缩略图，返回base64编码"""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    img.thumbnail(size, Image.LANCZOS)
    # 保存为JPEG字节流
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    thumb_bytes = buf.getvalue()
    # base64编码
    b64 = base64.b64encode(thumb_bytes).decode("ascii")
    return b64, len(thumb_bytes)


def main():
    print("=== 雪地纹理预览图下载与缩略图制作 ===")
    results = []
    for tex in SNOW_TEXTURES:
        asset_id = tex["id"]
        print(f"\n处理 {tex['name']}:")
        image_bytes = None
        # 如果已有本地文件，直接读取
        if tex["local_color"] and os.path.exists(tex["local_color"]):
            print(f"  使用本地已有文件: {tex['local_color']}")
            with open(tex["local_color"], "rb") as f:
                image_bytes = f.read()
        else:
            # 下载ZIP并提取Color
            image_bytes = download_and_extract_color(tex["url"], asset_id)
            # 保存提取的Color到本地以备后用
            if image_bytes:
                save_path = os.path.join(OUT_DIR, f"{asset_id}_Color.jpg")
                with open(save_path, "wb") as f:
                    f.write(image_bytes)
                print(f"  已保存原图: {save_path}")
        if image_bytes:
            b64, thumb_size = make_thumbnail(image_bytes)
            results.append({
                "id": asset_id,
                "name": tex["name"],
                "desc": tex["desc"],
                "thumb_b64": b64,
                "thumb_size": thumb_size,
            })
            print(f"  缩略图大小: {thumb_size} bytes, base64长度: {len(b64)}")
        else:
            print(f"  错误: 无法获取 {asset_id} 的色彩图")
    # 输出base64到文件，供后续构建HTML使用
    out_file = os.path.join(OUT_DIR, "thumbnails_b64.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"=== {r['id']} ===\n")
            f.write(r["thumb_b64"] + "\n")
    print(f"\n完成! base64数据已保存到: {out_file}")
    print(f"共制作 {len(results)} 个缩略图")
    for r in results:
        print(f"  {r['name']}: {r['thumb_size']} bytes")


if __name__ == "__main__":
    main()
