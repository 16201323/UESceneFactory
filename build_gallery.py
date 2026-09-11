# -*- coding: utf-8 -*-
"""
生成 base64 嵌入的 HTML 图库
把 mesh_thumbnails/ 下的 PNG 压缩为 256px JPEG 并嵌入 HTML
"""
import os
import base64
import io

THUMB_DIR = "c:/Users/25868/Desktop/UE5/MapForgeTest/mesh_thumbnails"
OUTPUT_HTML = "c:/Users/25868/Desktop/UE5/MapForgeTest/mesh_gallery.html"

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: Pillow not available, using raw base64 (larger output)")

# 分类顺序与显示名称
CATEGORIES = [
    ("01_BasicShapes", "基础形状 (Engine BasicShapes)", [
        ("01_BasicShapes_Cube.png", "Cube 立方体"),
        ("01_BasicShapes_Plane.png", "Plane 平面"),
        ("01_BasicShapes_Sphere.png", "Sphere 球体"),
        ("01_BasicShapes_Cone.png", "Cone 圆锥"),
        ("01_BasicShapes_Cylinder.png", "Cylinder 圆柱"),
    ]),
    ("02_House_Modular", "模块化建筑 (RuralHouse)", [
        ("02_House_Modular_Base_100CM.png", "Base 基座"),
        ("02_House_Modular_ExtWall_100CM.png", "ExtWall 外墙"),
        ("02_House_Modular_ExtWall_Corner_A.png", "ExtWall_Corner 外墙转角"),
        ("02_House_Modular_ExtWall_Door_A.png", "ExtWall_Door 外墙带门"),
        ("02_House_Modular_ExtWall_Window_A.png", "ExtWall_Window 外墙带窗"),
        ("02_House_Modular_FloorPlane_01.png", "FloorPlane 地板"),
        ("02_House_Modular_FrontStairs_A.png", "FrontStairs 前楼梯"),
        ("02_House_Modular_Roof_A_Mid.png", "Roof_A_Mid 屋顶中段"),
    ]),
    ("03_DoorsWindows", "门窗 (DoorsWindows)", [
        ("03_DoorsWindows_FrontDoor_A_Door.png", "FrontDoor 前门"),
        ("03_DoorsWindows_Window_A.png", "Window 窗户"),
    ]),
    ("04_Fence", "栅栏 (Fence)", [
        ("04_Fence_Fence_A.png", "Fence 栅栏"),
    ]),
    ("05_Props", "道具 (Props)", [
        ("05_Props_Barrel.png", "Barrel 桶"),
        ("05_Props_DieselGenerator.png", "DieselGenerator 柴油发电机"),
        ("05_Props_Fridge.png", "Fridge 冰箱"),
        ("05_Props_Lamp.png", "Lamp 灯"),
        ("05_Props_LawnChair.png", "LawnChair 草坪椅"),
        ("05_Props_Tire.png", "Tire 轮胎"),
        ("05_Props_WaterTank.png", "WaterTank 水箱"),
    ]),
    ("06_Trees", "树木 (Trees)", [
        ("06_Trees_FirTree_01.png", "FirTree 冷杉树"),
        ("06_Trees_SmallFir_01.png", "SmallFir 小冷杉"),
    ]),
    ("07_Rocks", "岩石 (Rocks)", [
        ("07_Rocks_Rock_A_01.png", "Rock 岩石"),
    ]),
    ("08_Road", "道路 (Road)", [
        ("08_Road_Road_A.png", "Road 道路段"),
    ]),
    ("09_Foliage", "植被 (Foliage)", [
        ("09_Foliage_GrassCluster_Generated.png", "GrassCluster 草丛(生成)"),
        ("09_Foliage_Grass_01.png", "Grass 草"),
    ]),
]


def encode_image(path):
    """读取 PNG, 压缩为 256px JPEG, 返回 base64 字符串"""
    if HAS_PIL:
        img = Image.open(path).convert("RGB")
        max_dim = 256
        w, h = img.size
        if w > h:
            new_w = max_dim
            new_h = int(h * max_dim / w)
        else:
            new_h = max_dim
            new_w = int(w * max_dim / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        data = buf.getvalue()
    else:
        with open(path, "rb") as f:
            data = f.read()
    b64 = base64.b64encode(data).decode("ascii")
    mime = "image/jpeg" if HAS_PIL else "image/png"
    return "data:" + mime + ";base64," + b64, len(data)


def main():
    total_encoded = 0
    total_count = 0

    html_parts = []
    html_parts.append('<div data-dynamic-ui-widget style="font-family:system-ui,Arial,sans-serif;color:#e8e8e8;background:#1a1a1a;padding:16px;border-radius:10px;max-width:920px;margin:0 auto;">')
    html_parts.append('<h2 style="margin:0 0 4px 0;font-size:20px;color:#4fc3f7;">UE5 引擎自带资产与项目网格缩略图</h2>')
    html_parts.append('<p style="margin:0 0 14px 0;font-size:12px;color:#999;">共 29 个网格, 按类别分组 (256px JPEG)</p>')

    for cat_key, cat_title, items in CATEGORIES:
        html_parts.append('<div style="margin-bottom:18px;">')
        html_parts.append('<h3 style="margin:0 0 8px 0;font-size:15px;color:#81c784;border-bottom:1px solid #333;padding-bottom:4px;">' + cat_title + '</h3>')
        html_parts.append('<div style="display:flex;flex-wrap:wrap;gap:8px;">')
        for fname, label in items:
            fpath = os.path.join(THUMB_DIR, fname)
            if not os.path.exists(fpath):
                html_parts.append('<div style="text-align:center;width:120px;"><div style="width:120px;height:120px;background:#2a2a2a;border:1px solid #444;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#666;">缺失</div><div style="font-size:10px;color:#aaa;margin-top:3px;">' + label + '</div></div>')
                continue
            b64, raw_len = encode_image(fpath)
            total_encoded += raw_len
            total_count += 1
            html_parts.append('<div style="text-align:center;width:120px;">')
            html_parts.append('<img src="' + b64 + '" style="width:120px;height:120px;object-fit:cover;border:1px solid #444;border-radius:6px;background:#000;display:block;" />')
            html_parts.append('<div style="font-size:10px;color:#aaa;margin-top:3px;word-break:break-word;line-height:1.2;">' + label + '</div>')
            html_parts.append('</div>')
        html_parts.append('</div></div>')

    html_parts.append('</div>')

    html = "".join(html_parts)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print("DONE: " + str(total_count) + " images encoded")
    print("Total encoded size: " + str(total_encoded) + " bytes (~" + str(round(total_encoded / 1024)) + " KB)")
    print("HTML file size: " + str(os.path.getsize(OUTPUT_HTML)) + " bytes (~" + str(round(os.path.getsize(OUTPUT_HTML) / 1024)) + " KB)")
    print("Output: " + OUTPUT_HTML)


if __name__ == "__main__":
    main()
