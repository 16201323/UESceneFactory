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

    依次尝试: 原路径.uasset / 原路径.umap / 补对象名 X.Y.uasset / 长路径剥离后缀

    长路径兼容(v2.9.8新增): UE 长路径格式 /Game/A/B.B 中,
    最后一段的 '.' 前为包名(磁盘文件名), '.' 后为对象名(不对应文件)。
    asset_catalog.json 全部使用此格式(如 Name.Name), 若不剥离后缀,
    ue_path_to_disk 会尝试 B.B.uasset 而非 B.uasset, 导致误报缺失。
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
    # 3. 长路径剥离: /Game/A/B.C → /Game/A/B
    #    最后一段含 '.' 时, '.' 前为包名, 剥离后重试 .uasset/.umap 检查
    #    修复场景: LLM 从 search_assets 获取 catalog 中的 Name.Name 格式路径,
    #    直接填入 JSON 后校验端无法匹配磁盘文件
    last_seg = os.path.basename(base)
    if "." in last_seg:
        short_base = os.path.join(os.path.dirname(base), last_seg.split(".")[0])
        for ext in (".uasset", ".umap"):
            if os.path.isfile(short_base + ext):
                return short_base + ext
    return None


def _scan_group_dir(prefix, content_dir):
    """扫描 group 前缀所在目录, 检查是否存在任意匹配的 .uasset 文件。

    部分资产包(如 rural_brick_house)编号不从0开始且非连续(仅偶数),
    prefix+"0" 检查会误报缺失。此函数扫描目录, 只要存在以 prefix
    的末段(如 "Object_")开头且以 .uasset 结尾的文件, 即判定有效——
    build_scene.py 的 GROUP_SKIP 会逐个跳过缺失编号, 只加载存在的部件。

    Returns: True=目录中有匹配文件(group有效), False=无匹配(group无效)
    """
    rel = prefix[len("/Game/"):] if prefix.startswith("/Game/") else prefix.lstrip("/")
    prefix_dir = os.path.join(content_dir, os.path.dirname(rel).replace("/", os.sep))
    prefix_base = os.path.basename(rel)  # 如 "Object_"
    if not os.path.isdir(prefix_dir):
        return False
    for name in os.listdir(prefix_dir):
        if name.startswith(prefix_base) and name.endswith(".uasset"):
            return True
    return False


def collect_asset_refs(scene):
    """从场景 JSON 中提取全部资产引用, 返回 [(字段位置, UE路径), ...]"""
    refs = []  # (位置描述, ue_path)

    def add(desc, p):
        # 空路径/非 /Game 开头的跳过 (相对路径等异常交给构建端处理)
        if p and isinstance(p, str) and p.strip():
            refs.append((desc, p.strip()))

    # scene: target_level (关卡本身, 允许不存在=新建)
    # 注意: dict.get(key, {}) 的默认值仅在 key 不存在时生效;
    # 若 LLM 输出 "scene": null, .get 返回 None, 后续 .get 会崩。
    # 用 `or {}` 把 None 也归一为空 dict, 彻底防御 null 值。
    s = scene.get("scene") or {}
    add("scene.target_level", s.get("target_level"))

    # landscape (可能为 null, 用 or {} 防御)
    ls = scene.get("landscape") or {}
    add("landscape.material", ls.get("material"))
    # layers 可能为 null → or [] 归一为空列表, 避免遍历 None 崩溃
    for i, l in enumerate(ls.get("layers") or []):
        # 单个 layer 也可能为 null (LLM 生成异常), or {} 防御
        l = l or {}
        add("landscape.layers[%d].info" % i, l.get("info"))
    # grass / wheat 可能为 null → or {} 防御, 避免 None.get() 崩溃
    g = ls.get("grass") or {}
    add("landscape.grass.grass_type", g.get("grass_type"))
    add("landscape.grass.grass_mesh", g.get("grass_mesh"))
    w = ls.get("wheat") or {}
    add("landscape.wheat.type_path", w.get("type_path"))

    # height_pattern (C++ 端特征配置里的资产引用, 可能为 null)
    hp = ls.get("height_pattern") or {}
    for i, rv in enumerate(hp.get("rivers") or []):
        rv = rv or {}
        add("rivers[%d].material_path" % i, rv.get("material_path"))
    for i, rd in enumerate(hp.get("roads") or []):
        rd = rd or {}
        add("roads[%d].material_path" % i, rd.get("material_path"))
        add("roads[%d].mesh_path" % i, rd.get("mesh_path"))
    for i, b in enumerate(hp.get("buildings") or []):
        b = b or {}
        add("buildings[%d].material_path" % i, b.get("material_path"))
    wat = hp.get("water")
    if wat:
        add("water.material_path", wat.get("material_path"))
    for i, sc in enumerate(hp.get("scatter") or []):
        sc = sc or {}
        add("scatter[%d].mesh_path" % i, sc.get("mesh_path"))
    for i, gv in enumerate(hp.get("grass_varieties") or []):
        gv = gv or {}
        add("grass_varieties[%d].mesh_path" % i, gv.get("mesh_path"))
    for i, wv in enumerate(hp.get("wheat_varieties") or []):
        wv = wv or {}
        add("wheat_varieties[%d].mesh_path" % i, wv.get("mesh_path"))

    # ground
    gnd = scene.get("ground")
    if gnd:
        add("ground.asset", gnd.get("asset"))
        add("ground.material_override", gnd.get("material_override"))

    # placements (可能为 null → or [] 防御)
    for i, p in enumerate(scene.get("placements") or []):
        p = p or {}  # 单个 placement 也可能为 null
        if p.get("type") == "group":
            # group: asset_prefix 需存在至少一个编号资产
            prefix = p.get("asset_prefix", "")
            if prefix:
                # 检查 prefix+"0" 是否存在 (group 从编号 0 开始)
                found = ue_path_to_disk(prefix + "0", CONTENT_DIR[0])
                if not found:
                    # v2.9.8: prefix+"0" 不存在时, 扫描前缀所在目录是否有任意匹配的 .uasset 文件
                    # 部分资产包编号不从0开始(如 rural_brick_house 从 Object_4 起, 仅偶数),
                    # build_scene.py 的 GROUP_SKIP 会逐个跳过缺失编号, 只要目录中有匹配文件即有效
                    found = _scan_group_dir(prefix, CONTENT_DIR[0])
                if not found:
                    # 目录中也没有任何匹配文件, 前缀确实无效
                    refs.append(("placements[%d].asset_prefix" % i, prefix))
                else:
                    # 已找到编号资产或目录中有匹配文件, group 校验通过
                    # 裸前缀不是资产路径, 不能再加入 refs (否则后续存在性检查必误报缺失)
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
