# -*- coding: utf-8 -*-
"""
validate_scene_assets.py - 场景 JSON 资产路径预校验

在启动 UE 构建 (一次约 2 分钟) 之前, 秒级校验 JSON 里引用的全部资产路径
是否真实存在于项目 Content 目录, 路径写错立即报出, 避免构建后才发现资产缺失。

用法 (被 build_umap.ps1 调用):
    python validate_scene_assets.py <场景.json> [--content <Content目录>]

退出码: 0=全部存在  2=有缺失 (缺失清单打印到 stdout, 供包装脚本收集展示)

资产引用提取范围 (对照 build_scene.py 实际读取的全部字段):
    scene.target_level          → .umap (关卡本身, 可不存在=新建)
    landscape.material          → .uasset
    landscape.layers[].info     → LayerInfo 资产
    landscape.grass.grass_type  → GrassType 资产
    landscape.grass.grass_mesh  → 网格
    landscape.wheat.type_path    → GrassType 资产
    height_pattern.rivers[].material_path
    height_pattern.roads[].material_path
    height_pattern.buildings[].material_path
    height_pattern.water.material_path
    height_pattern.scatter[].mesh_path
    height_pattern.grass_varieties[].mesh_path
    height_pattern.wheat_varieties[].mesh_path
    ground.asset
    placements[].asset / asset_prefix / material_override
    placements[].grid.instances 不含资产引用, 无需检查

路径容错 (与 build_scene.py 第 847-853 行行为一致):
    1. 先按原路径找      /Game/Xxx/Yyy → Content/Xxx/Yyy.uasset
    2. 找不到再补对象名  /Game/Xxx/Yyy → Content/Xxx/Yyy.Yyy.uasset
    两者都不存在才算缺失。/Game 前缀映射到 Content 目录。
"""
import json
import os
import sys


def ue_path_to_disk(path, content_dir):
    """UE 资产路径 → Content 下的磁盘文件, 返回存在的文件路径或 None

    依次尝试: 原路径.uasset / 原路径.umap / 补对象名 X.Y.uasset
    """
    rel = path[len("/Game/"):] if path.startswith("/Game/") else path.lstrip("/")
    base = os.path.join(content_dir, rel.replace("/", os.sep))
    # 1. 原路径 (关卡=.umap, 资产=.uasset; 蓝图 _C 后缀去掉)
    if base.endswith("_C"):
        base = base[:-2]
    for ext in (".uasset", ".umap"):
        if os.path.isfile(base + ext):
            return base + ext
    # 2. 补对象名: /Game/A/B → /Game/A/B.B (build_scene.py 的短路径容错重试)
    obj = os.path.basename(base)
    if os.path.isfile(os.path.join(base + "." + obj + ".uasset")):
        return base + "." + obj + ".uasset"
    return None


def collect_asset_refs(scene):
    """从场景 JSON 中提取全部资产引用, 返回 [(字段位置, UE路径), ...]"""
    refs = []  # (位置描述, ue_path)

    def add(desc, p):
        # 空路径/非 /Game 开头的跳过 (相对路径等异常交给构建端处理)
        if p and isinstance(p, str) and p.strip():
            refs.append((desc, p.strip()))

    # scene: target_level (关卡本身, 允许不存在=新建)
    s = scene.get("scene", {})
    add("scene.target_level", s.get("target_level"))

    # landscape
    ls = scene.get("landscape", {})
    add("landscape.material", ls.get("material"))
    for i, l in enumerate(ls.get("layers", [])):
        add("landscape.layers[%d].info" % i, l.get("info"))
    g = ls.get("grass", {})
    add("landscape.grass.grass_type", g.get("grass_type"))
    add("landscape.grass.grass_mesh", g.get("grass_mesh"))
    w = ls.get("wheat", {})
    add("landscape.wheat.type_path", w.get("type_path"))

    # height_pattern (C++ 端特征配置里的资产引用)
    hp = ls.get("height_pattern", {})
    for i, rv in enumerate(hp.get("rivers", [])):
        add("rivers[%d].material_path" % i, rv.get("material_path"))
    for i, rd in enumerate(hp.get("roads", [])):
        add("roads[%d].material_path" % i, rd.get("material_path"))
        add("roads[%d].mesh_path" % i, rd.get("mesh_path"))
    for i, b in enumerate(hp.get("buildings", [])):
        add("buildings[%d].material_path" % i, b.get("material_path"))
    wat = hp.get("water")
    if wat:
        add("water.material_path", wat.get("material_path"))
    for i, sc in enumerate(hp.get("scatter", [])):
        add("scatter[%d].mesh_path" % i, sc.get("mesh_path"))
    for i, gv in enumerate(hp.get("grass_varieties", [])):
        add("grass_varieties[%d].mesh_path" % i, gv.get("mesh_path"))
    for i, wv in enumerate(hp.get("wheat_varieties", [])):
        add("wheat_varieties[%d].mesh_path" % i, wv.get("mesh_path"))

    # ground
    gnd = scene.get("ground")
    if gnd:
        add("ground.asset", gnd.get("asset"))
        add("ground.material_override", gnd.get("material_override"))

    # placements
    for i, p in enumerate(scene.get("placements", [])):
        if p.get("type") == "group":
            # group: asset_prefix 需存在至少一个编号资产 (前缀_0 起存在即算有效)
            prefix = p.get("asset_prefix", "")
            if prefix:
                # 检查 prefix+"0" 是否存在 (group 从编号 0 开始)
                found = ue_path_to_disk(prefix + "0", CONTENT_DIR[0])
                if not found:
                    # 退化: 检查前缀目录是否存在 (非序列命名容错, 构建时 GROUP_SKIP 逐个跳过)
                    refs.append(("placements[%d].asset_prefix" % i, prefix))
                else:
                    # 已找到编号0资产, group 校验通过; 裸前缀不是资产路径,
                    # 不能再加入 refs (否则后续存在性检查必误报缺失)
                    pass
        add("placements[%d].asset" % i, p.get("asset"))
        add("placements[%d].material_override" % i, p.get("material_override"))

    return refs


# Content 目录 (validate 入口统一初始化, 避免全局依赖)
CONTENT_DIR = []


def main():
    args = sys.argv[1:]
    if not args:
        print("用法: validate_scene_assets.py <场景.json> [--content <Content目录>]")
        sys.exit(1)
    scene_path = args[0]
    # 从配置文件推导 Content 目录 (与 build_umap.py _resolve_paths 一致),
    # --content 参数优先级最高, 其次环境变量 MAPFORGE_CONTENT_DIR
    content = ""
    _config_path = os.path.join(os.path.expanduser("~"), ".mapforge_config.json")
    try:
        with open(_config_path, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
        _proj = _cfg.get("project_path", "")
        if _proj:
            content = os.path.join(os.path.dirname(_proj), "Content")
    except Exception:
        pass
    content = os.environ.get("MAPFORGE_CONTENT_DIR", content)
    if "--content" in args:
        content = args[args.index("--content") + 1]
    if not content or not os.path.isdir(content):
        print("错误: 未指定有效的 Content 目录。")
        print("请通过 --content <路径> 参数, 或在 ~/.mapforge_config.json 中配置 project_path。")
        sys.exit(1)
    CONTENT_DIR.append(content)

    if not os.path.isfile(scene_path):
        print("场景文件不存在: " + scene_path)
        sys.exit(1)

    with open(scene_path, "r", encoding="utf-8") as f:
        scene = json.load(f)

    refs = collect_asset_refs(scene)
    missing = []  # (位置, 路径)
    for desc, p in refs:
        if not p.startswith("/Game/"):
            continue  # 非 /Game 绝对路径不校验
        if desc == "scene.target_level":
            # target_level 是待生成的输出关卡 (允许不存在=新建, 见 collect_asset_refs 注释),
            # 只校验 /Game/ 路径格式, 不做磁盘存在性检查
            continue
        if not ue_path_to_disk(p, content):
            missing.append((desc, p))

    print("资产引用共 %d 项" % len(refs))
    if not missing:
        print("ASSET_CHECK_OK 全部资产路径有效")
        sys.exit(0)
    else:
        print("ASSET_CHECK_FAIL 缺失 %d 项:" % len(missing))
        for desc, p in missing:
            print("  缺失 [%s]: %s" % (desc, p))
        sys.exit(2)


if __name__ == "__main__":
    main()
