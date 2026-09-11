# ============================================================================
# build_scene.py - JSON/YAML 场景描述 → UE5 umap 关卡转换工具 (可复用 CLI)
# ============================================================================
# 用法:
#   1. 编辑器内控制台:  py c:/.../build_scene.py c:/.../scene.yaml
#   2. 无头模式:
#      UnrealEditor-Cmd.exe project.uproject -unattended -nop4 -nosplash \
#        -nullrhi -stdout -ExecCmds="py build_scene.py scene.yaml | quit"
#   3. 不传参数时默认使用 farming_village.yaml
#
# 场景文件 schema (YAML/JSON 通用):
#   scene:        { name, target_level, description }
#   landscape:    { material, section_size_quads, num_subsections, component_count_x,
#                  component_count_y, location, scale }
#                  (UE5 正式 Landscape 地形, 需 LandscapeHelper C++ 插件)
#   ground:       { asset, location, rotation, scale, material_override }
#                  (静态网格地面, 与 landscape 二选一或叠加使用)
#   placements:   [ { asset, location, rotation, scale } | { asset, grid:{...} } ]
#   lighting:     { directional_light, sky_light, sky_atmosphere, height_fog }
#   weather:      { volumetric_clouds, post_process }
# ============================================================================

import unreal
import sys
import json
import os
import random

# ---- 日志输出 (同时写 stdout 和文件, 避免 -stdout 缓冲丢失) ----
# 日志路径优先从环境变量读取 (GUI 工具会设置), 无则用系统临时目录
LOG_PATH = os.environ.get("MAPFORGE_LOG", os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "mapforge_build_scene.log"))
# 追加模式: 外层包装脚本(build_umap.ps1)会先在日志头部写入 JSON 全路径等构建头信息,
# 用 "w" 会清掉它们; 日志文件名本身带时间戳 (每次构建一个新文件), 追加不会混入旧内容
_f = open(LOG_PATH, "a", encoding="utf-8")
def log(msg, level="INFO"):
    prefix = {"INFO": "[INFO]", "OK": "[OK]", "WARN": "[WARN]", "ERROR": "[ERROR]"}
    _line = f"{prefix.get(level, '[INFO]')} {msg}"
    print(_line)
    _f.write(_line + "\n")
    _f.flush()

# ---- 尝试导入 yaml 模块 (UE5.8 可能不含 PyYAML, 无则回退 json) ----
try:
    import yaml
    HAS_YAML = True
    log("yaml module available")
except ImportError:
    HAS_YAML = False
    log("yaml module NOT available, will fall back to json")

# 资产缓存, 避免重复 LoadObject
_asset_cache = {}
# SubobjectDataSubsystem 缓存 (UE5 添加持久化子组件的正道, 惰性初始化)
_sds = None
# 地形高度缓存: 按 (round(x/100), round(y/100)) 1m 精度缓存地形 Z, 避免重复查询
# 用途: snap_to_ground 时大量实例查询地形高度, 缓存命中率极高(网格间距通常>1m)
_terrain_cache = {}
_terrain_helper_available = None
# 是否优先使用内存高度图查询(GetHeightFromHeightmap): None=未检测, True/False=已检测
# 绕过纹理重建导致的悬浮问题: Import()+PostEditChange()后部分纹理区域被空编辑层覆盖,
# GetHeightAtLocation对部分位置返回0 -> 同一山谷区域有的树贴地有的悬浮。
# GetHeightFromHeightmap直接读取Import前快照的内存高度数组, 与散布代码同源, 稳定贴地。
_terrain_use_heightmap = None
# 诊断计数器: 记录前3次地形Z查询结果, 验证贴地是否生效
_terrain_z_log_count = 0
# 诊断计数器: 记录地形Z查询返回0的次数(疑似悬浮, 高度图快照未就绪或越界)
_terrain_z_zero_count = 0


def load_scene(path):
    """加载场景文件 (.yaml 或 .json); yaml 不可用时自动回退同名 .json"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    if HAS_YAML:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    json_path = os.path.splitext(path)[0] + ".json"
    if os.path.exists(json_path):
        log("yaml 不可用, 回退 json: " + json_path)
        with open(json_path, "r", encoding="utf-8") as jf:
            return json.load(jf)
    raise RuntimeError("yaml 不可用且无同名 json 兜底: " + path)


def dump_scene_detail(scene):
    """详细场景信息转储 (日志留档用)

    在构建前把整份场景 JSON 的关键参数逐项打印到日志:
    - 地形每个设置的空间坐标 (component/section/location/scale/物理尺寸)
    - 每个图层的权重模式完整 JSON
    - height_pattern 每个山丘/山谷/山脊/湖泊/河流/道路/散布物/草麦变体的坐标与高度值
    - 每个放置项 (placement) 的资产路径、坐标、旋转、缩放、网格参数
    - 光照/天气配置
    目的: 构建日志成为场景的完整档案, 出问题时无需打开 JSON 即可对照日志排错。
    所有行带 [DUMP] 前缀, 便于在长日志中快速检索。
    """

    # ---------- 1. 场景元数据 ----------
    s = scene.get("scene", {})
    log("[DUMP]========== 场景元数据 ==========")
    log("[DUMP]  name=%s  target_level=%s" % (s.get("name", ""), s.get("target_level", "")))
    if s.get("description"):
        log("[DUMP]  description: " + s["description"])

    # ---------- 2. 地形基础参数 (空间坐标) ----------
    ls = scene.get("landscape", {})
    if ls:
        log("[DUMP]========== 地形 Landscape 基础参数 ==========")
        log("[DUMP]  material=%s" % ls.get("material", ""))
        ssq = ls.get("section_size_quads", 63)
        nsub = ls.get("num_subsections", 1)
        ccx = ls.get("component_count_x", 8)
        ccy = ls.get("component_count_y", 8)
        loc = ls.get("location", [0, 0, 0])
        rot = ls.get("rotation", [0, 0, 0])
        scl = ls.get("scale", [100, 100, 100])
        # 物理尺寸 = quad 数 × 缩放 / 100 (1UU=1cm, scale=100 时每 quad=1m)
        phys_x = (ccx * ssq * nsub) * scl[0] / 100.0
        phys_y = (ccy * ssq * nsub) * scl[1] / 100.0
        log("[DUMP]  section_size_quads=%d  num_subsections=%d  components=%dx%d" % (ssq, nsub, ccx, ccy))
        log("[DUMP]  location(世界坐标cm)=[%.1f, %.1f, %.1f]" % tuple(loc))
        log("[DUMP]  rotation(pitch,yaw,roll)=[%s, %s, %s]" % tuple(rot))
        log("[DUMP]  scale=[%s, %s, %s]" % tuple(scl))
        log("[DUMP]  物理尺寸=%.1fm x %.1fm  覆盖世界范围 X:[%.1f, %.1f] Y:[%.1f, %.1f] (cm)"
            % (phys_x, phys_y, loc[0], loc[0] + phys_x * 100.0 / scl[0] * scl[0],
               loc[1], loc[1] + phys_y * 100.0 / scl[1] * scl[1]))

        # ---------- 3. 图层权重模式 (每个图层的完整配置) ----------
        layers = ls.get("layers", [])
        if layers:
            log("[DUMP]---------- 图层 (%d 层) ----------" % len(layers))
            for i, l in enumerate(layers):
                log("[DUMP]  Layer%d: info=%s  weight=%.3f" % (i + 1, l.get("info", ""), float(l.get("weight", 0.0))))
                wp = l.get("weight_pattern")
                if wp:
                    # 权重模式完整 JSON 原样输出 (含全部空间坐标参数)
                    log("[DUMP]    weight_pattern=" + json.dumps(wp, ensure_ascii=False))

        # ---------- 4. 草地/麦田配置 ----------
        g = ls.get("grass", {})
        if g:
            log("[DUMP]---------- 草地配置 ----------")
            log("[DUMP]  grass_type=%s  mesh=%s  layer=%s  density=%.1f"
                % (g.get("grass_type", ""), g.get("grass_mesh", ""),
                   g.get("layer_name", ""), float(g.get("density", 0.0))))
        w = ls.get("wheat", {})
        if w:
            log("[DUMP]---------- 麦田配置 ----------")
            log("[DUMP]  type_path=%s  layer=%s" % (w.get("type_path", ""), w.get("layer_name", "")))

        # ---------- 5. 地形起伏 height_pattern (每个特征的坐标与高度) ----------
        hp = ls.get("height_pattern", {})
        if hp:
            log("[DUMP]========== 地形起伏 height_pattern ==========")
            log("[DUMP]  type=%s  blend_mode=%s" % (hp.get("type", ""), hp.get("blend_mode", "")))
            for i, h in enumerate(hp.get("hills", [])):
                # 山丘: 中心坐标 + 半径 + 高度
                log("[DUMP]  hills[%d]: 中心(%.1f, %.1f)m 半径%.1fm 高度%.1fm"
                    % (i, h.get("center_x_m", 0), h.get("center_y_m", 0),
                       h.get("radius_m", 0), h.get("height_m", 0)))
            for i, v in enumerate(hp.get("valleys", [])):
                # 山谷/湖盆: 中心坐标 + 半径 + 深度 + 底部半径
                log("[DUMP]  valleys[%d]: 中心(%.1f, %.1f)m 半径%.1fm 深度%.1fm 底半径%.1fm"
                    % (i, v.get("center_x_m", 0), v.get("center_y_m", 0),
                       v.get("radius_m", 0), v.get("depth_m", 0), v.get("bottom_radius_m", 0)))
            for i, r in enumerate(hp.get("ridges", [])):
                # 山脊: 区域范围 + 幅度 + 频率 + 方向
                log("[DUMP]  ridges[%d]: 区域(%.1f,%.1f)~(%.1f,%.1f)m 幅度%.1fm 频率%.4f 方向%.1f°"
                    % (i, r.get("region_min_x_m", 0), r.get("region_min_y_m", 0),
                       r.get("region_max_x_m", 0), r.get("region_max_y_m", 0),
                       r.get("amplitude_m", 0), r.get("frequency", 0), r.get("direction_deg", 0)))
            wat = hp.get("water")
            if wat:
                log("[DUMP]  water: 水位%.1fm 材质=%s" % (wat.get("level_m", 0), wat.get("material_path", "")))
            for i, rv in enumerate(hp.get("rivers", [])):
                # 河流: 宽度 + 全部折点坐标 (C++ 按折点细分冲刷河床)
                pts = rv.get("points", [])
                log("[DUMP]  rivers[%d]: 宽%.1fm 折点%d个 材质=%s 流速=%.1fx"
                    % (i, rv.get("width_m", 0), len(pts), rv.get("material_path", ""),
                       rv.get("flow_speed", 1.0)))
                for j, p in enumerate(pts):
                    log("[DUMP]    折点[%d]: (%s, %s)m" % (j, p[0], p[1]))
            for i, rd in enumerate(hp.get("roads", [])):
                # 道路: 宽度 + 全部折点坐标 (C++ 按折点细分平整路基)
                pts = rd.get("points", [])
                log("[DUMP]  roads[%d]: 宽%.1fm 折点%d个 材质=%s"
                    % (i, rd.get("width_m", 0), len(pts), rd.get("material_path", "")))
                for j, p in enumerate(pts):
                    log("[DUMP]    折点[%d]: (%s, %s)m" % (j, p[0], p[1]))
            no = hp.get("noise_overlay")
            if no:
                log("[DUMP]  noise_overlay: 幅度%.1fm 频率%.4f 八度%d 种子%s"
                    % (no.get("amplitude_m", 0), no.get("frequency", 0),
                       no.get("octaves", 0), no.get("seed", 0)))
            if "perturbation_strength" in hp:
                log("[DUMP]  perturbation: 强度%.2f 尺度%.4f 种子%s"
                    % (hp.get("perturbation_strength", 0), hp.get("perturbation_scale", 0),
                       hp.get("perturbation_seed", 0)))
            for i, sc in enumerate(hp.get("scatter", [])):
                # 散布物: 网格 + 数量 + 缩放范围 (C++ 随机散布, 坐标由种子决定)
                log("[DUMP]  scatter[%d]: mesh=%s 数量%d seed=%s 缩放%.2f~%.2f 随机旋转=%s"
                    % (i, sc.get("mesh_path", ""), sc.get("count", 0), sc.get("seed", 0),
                       sc.get("scale_min", 0), sc.get("scale_max", 0),
                       sc.get("random_rotation", False)))
            for i, gv in enumerate(hp.get("grass_varieties", [])):
                log("[DUMP]  grass_varieties[%d]: mesh=%s 密度%.1f 缩放%.2f~%.2f cull %s~%s"
                    % (i, gv.get("mesh_path", ""), gv.get("density", 0),
                       gv.get("scale_min", 0), gv.get("scale_max", 0),
                       gv.get("start_cull_dist", 0), gv.get("end_cull_dist", 0)))
            for i, wv in enumerate(hp.get("wheat_varieties", [])):
                log("[DUMP]  wheat_varieties[%d]: mesh=%s 密度%.1f 缩放%.2f~%.2f cull %s~%s"
                    % (i, wv.get("mesh_path", ""), wv.get("density", 0),
                       wv.get("scale_min", 0), wv.get("scale_max", 0),
                       wv.get("start_cull_dist", 0), wv.get("end_cull_dist", 0)))

    # ---------- 6. 静态网格地面 ----------
    gnd = scene.get("ground")
    if gnd and gnd.get("asset"):
        log("[DUMP]========== 静态网格地面 ground ==========")
        log("[DUMP]  asset=%s  location(世界cm)=[%s, %s, %s]  rotation=[%s, %s, %s]  scale=[%s, %s, %s]"
            % tuple([gnd.get("asset", "")] +
                    list(gnd.get("location", [0, 0, 0])) +
                    list(gnd.get("rotation", [0, 0, 0])) +
                    list(gnd.get("scale", [1, 1, 1]))))

    # ---------- 7. 放置列表 (每个资产的坐标与高度值) ----------
    placements = scene.get("placements", [])
    if placements:
        log("[DUMP]========== 放置列表 placements (%d 条) ==========" % len(placements))
        pi = 0  # 有效放置项序号 (跳过纯 _note 注释项)
        for p in placements:
            if "asset" not in p and "asset_prefix" not in p:
                continue  # 纯注释条目, 不计入
            pi += 1
            atype = p.get("type", "static")
            if atype == "group":
                # 组合资产: 前缀 + 部件数
                log("[DUMP]  放置%d[group]: prefix=%s 部件%d个 location=[%s, %s, %s] rotation=[%s, %s, %s] scale=[%s, %s, %s]"
                    % tuple([pi, p.get("asset_prefix", ""), p.get("count", 0)] +
                            list(p.get("location", [0, 0, 0])) +
                            list(p.get("rotation", [0, 0, 0])) +
                            list(p.get("scale", [1, 1, 1]))))
            else:
                loc = p.get("location", [0, 0, 0])
                log("[DUMP]  放置%d[%s]: asset=%s location(世界cm)=[%s, %s, %s](高Z=%s) rotation=[%s, %s, %s] scale=[%s, %s, %s]"
                    % tuple([pi, atype, p.get("asset", "")] +
                            list(loc) + [loc[2]] +
                            list(p.get("rotation", [0, 0, 0])) +
                            list(p.get("scale", [1, 1, 1]))))
            grid = p.get("grid")
            if grid:
                # 网格参数: 行列数 + 起点(含高度) + 间距 + 缩放范围 + 距离剔除
                origin = grid.get("origin", [0, 0, 0])
                log("[DUMP]    grid: rows=%s cols=%s origin=[%s, %s, %s](高Z=%s) spacing=[%s, %s, %s] jitter=%s 随机yaw=%s"
                    % tuple([grid.get("rows", 0), grid.get("cols", 0)] +
                            list(origin) + [origin[2]] +
                            list(grid.get("spacing", [100, 100, 0])) +
                            [grid.get("jitter", 0), grid.get("random_yaw", False)]))
                smin = grid.get("scale_min")
                smax = grid.get("scale_max")
                if smin:
                    log("[DUMP]    grid缩放: min=%s max=%s" % (smin, smax))
                if "cull_start" in grid:
                    log("[DUMP]    grid距离剔除: cull %s~%s (世界cm)"
                        % (grid.get("cull_start"), grid.get("cull_end")))
            insts = p.get("instances")
            if insts:
                # 显式实例数组: 逐个打印坐标 (含高度值)
                log("[DUMP]    instances: %d 个显式实例" % len(insts))
                for k, ins in enumerate(insts):
                    il = ins.get("location", [0, 0, 0])
                    log("[DUMP]      实例[%d]: location=[%s, %s, %s](高Z=%s) rotation=[%s, %s, %s] scale=[%s, %s, %s]"
                        % tuple([k] + list(il) + [il[2]] +
                                list(ins.get("rotation", [0, 0, 0])) +
                                list(ins.get("scale", [1, 1, 1]))))

    # ---------- 8. 光照 / 天气 ----------
    lit = scene.get("lighting", {})
    if lit:
        log("[DUMP]========== 光照 lighting ==========")
        dl = lit.get("directional_light", {})
        if dl:
            # 太阳光: 旋转角度 + 强度 + 颜色 + 投影开关
            drot = list(dl.get("rotation", [0, 0, 0]))
            log("[DUMP]  太阳光: rotation(pitch,yaw,roll)=[%s, %s, %s] intensity=%s color=%s 投影=%s"
                % (drot[0], drot[1], drot[2],
                   dl.get("intensity"), dl.get("color"), dl.get("cast_shadows")))
        sl = lit.get("sky_light", {})
        if sl:
            log("[DUMP]  天空光: intensity=%s color=%s" % (sl.get("intensity"), sl.get("color")))
        hf = lit.get("height_fog", {})
        if hf:
            log("[DUMP]  高度雾: density=%s color=%s" % (hf.get("density"), hf.get("color")))
    wth = scene.get("weather", {})
    if wth:
        log("[DUMP]========== 天气 weather ==========")
        vc = wth.get("volumetric_clouds")
        if vc:
            log("[DUMP]  体积云: location=%s" % (vc.get("location"),))
        pp = wth.get("post_process")
        if pp:
            log("[DUMP]  后处理: auto_exposure %s~%s" % (pp.get("auto_exposure_min"), pp.get("auto_exposure_max")))
    log("[DUMP]========== 场景转储结束 ==========")


def to_vector(loc):
    return unreal.Vector(loc[0], loc[1], loc[2])


def to_rotator(rot):
    # 关键修复: UE5.8 Rotator 构造函数位置参数顺序为 (roll, pitch, yaw),
    # 而非直觉上的 (pitch, yaw, roll)。
    # 之前用位置参数 unreal.Rotator(rot[0], rot[1], rot[2]) 传入 [-45, 35, 0]
    # 实际变成: roll=-45, pitch=35, yaw=0
    # → pitch 变正(35°) → 太阳跑到地平线以下 → SkyAtmosphere 无阳光可散射 → 天空全黑
    # 改用关键字参数彻底消除位置参数歧义, 确保 pitch/yaw/roll 各归其位
    return unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2])


def to_color(c):
    """将 [r,g,b] (0.0~1.0) 转为 unreal.Color (0-255 整数), 用于灯光 light_color 属性"""
    return unreal.Color(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255), 255)


def to_linear_color(c):
    """将 [r,g,b] (0.0~1.0 线性) 转为 unreal.LinearColor, 用于雾 fog_inscattering_color 属性"""
    return unreal.LinearColor(c[0], c[1], c[2], 1.0)


def get_terrain_z(x, y):
    """查询地形表面Z高度(通用贴地核心函数)
    优先使用 GetHeightFromHeightmap(内存高度图快照, 绕过纹理重建导致的悬浮问题);
    当快照未就绪或返回0时, 回退到 GetHeightAtWorldLocation(纹理读取)。
    按 1m 精度缓存结果, 避免密集网格重复查询。
    用途: snap_to_ground=true 时, 树木/草地等HISM实例逐个查询地形Z实现贴地,
          使实例在山谷/山丘上自动跟随地形起伏而非悬浮。
    """
    global _terrain_use_heightmap, _terrain_helper_available
    # 惰性检测: 首次调用时检查两个方法是否可用
    if _terrain_use_heightmap is None:
        try:
            _terrain_use_heightmap = hasattr(unreal.LandscapeHelper, "get_height_from_heightmap")
        except Exception:
            _terrain_use_heightmap = False
        try:
            _terrain_helper_available = hasattr(unreal.LandscapeHelper, "get_height_at_world_location")
        except Exception:
            _terrain_helper_available = False
        log("TERRAIN_HELPER: heightmap=" + str(_terrain_use_heightmap) + " world_loc=" + str(_terrain_helper_available))
    if not _terrain_use_heightmap and not _terrain_helper_available:
        return None
    # 1m 精度缓存键, 避免相近点重复查询
    key = (round(x / 100.0), round(y / 100.0))
    if key in _terrain_cache:
        return _terrain_cache[key]
    z = None
    method = "none"
    try:
        # 优先: 内存高度图快照(与C++散布代码同源, 绕过纹理重建)
        if _terrain_use_heightmap:
            z = unreal.LandscapeHelper.get_height_from_heightmap(float(x), float(y))
            method = "heightmap"
        # 回退: 快照未就绪/返回0时用纹理读取(部分位置可能仍为0, 但尽力而为)
        if (z is None or z == 0.0) and _terrain_helper_available:
            z_fb = unreal.LandscapeHelper.get_height_at_world_location(float(x), float(y))
            if z_fb is not None and z_fb != 0.0:
                z = z_fb
                method = "world_loc(fb)"
    except Exception as e:
        log("TERRAIN_Z_FAIL: " + str(e))
        _terrain_helper_available = False
    if z is not None:
        _terrain_cache[key] = z
        global _terrain_z_log_count, _terrain_z_zero_count
        # 诊断: 前3次查询打印结果及所用方法, 验证地形Z值非0
        if _terrain_z_log_count < 3:
            _terrain_z_log_count += 1
            log("TERRAIN_Z_QUERY[" + str(_terrain_z_log_count) + "]: x=" + str(round(x)) + " y=" + str(round(y)) + " -> z=" + str(round(z, 1)) + " [" + method + "]")
        # 诊断: 统计返回0的次数(疑似悬浮)
        if z == 0.0:
            _terrain_z_zero_count += 1
        return z
    return None


def spawn_mesh(asset_path, location, rotation=(0, 0, 0), scale=(1, 1, 1), material_override=None, skip_z_fix=False, scale_before_rotation=False):
    """放置一个 StaticMeshActor, 设置 mesh/缩放, 返回 actor
    material_override: 可选, 指定材质路径覆盖网格原有材质(如将房屋地板材质替换为草地材质)
    skip_z_fix: 可选, 跳过Z自动修正(多部件组合资产内部已含相对高度偏移, 独立Z修正会把各部件底部都压到同一高度, 破坏组装)
    scale_before_rotation: 可选, 先设缩放再补旋转(复刻手动操作顺序: 拖入→缩小→转-90°), 用于停机坪等多部件组合
    """
    loc = to_vector(location)
    rot = to_rotator(rotation)
    # scale_before_rotation 模式: 先以零旋转生成Actor, 等设完缩放后再补目标旋转, 完全复刻手动操作顺序
    spawn_rot = to_rotator([0, 0, 0]) if scale_before_rotation else rot
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, loc, spawn_rot)
    if not actor:
        log("  SPAWN_FAIL " + str(location))
        return None
    mesh = actor.static_mesh_component
    if asset_path not in _asset_cache:
        _asset_cache[asset_path] = unreal.EditorAssetLibrary.load_asset(asset_path)
    asset = _asset_cache[asset_path]
    if not asset:
        log("  ASSET_MISSING " + asset_path)
        return actor
    mesh.set_static_mesh(asset)
    # 材质覆盖: 将网格的第0号材质槽替换为指定材质(解决地面使用房屋木地板材质的问题)
    if material_override:
        mat = unreal.EditorAssetLibrary.load_asset(material_override)
        if mat:
            mesh.set_material(0, mat)
            log("  MATERIAL_OVERRIDE: " + material_override.split("/")[-1])
        else:
            log("  MATERIAL_OVERRIDE_FAIL: " + material_override)
    if scale != (1, 1, 1):
        actor.set_actor_scale3d(unreal.Vector(scale[0], scale[1], scale[2]))
    # scale_before_rotation 模式: 缩放设置完成后, 再补上目标旋转(模拟手动: 先缩小再转-90°)
    if scale_before_rotation:
        actor.set_actor_rotation(rot, False)
    # 自动修正Z位置: 获取actor世界包围盒, 将底部对齐到location的Z坐标
    # 解决蓝图网格原点在中心/顶部导致建筑悬浮(离地)或沉地的问题
    # skip_z_fix=True 时跳过该步骤(多部件组合资产内部已含相对高度, 独立Z修正会压平组装)
    if not skip_z_fix:
        try:
            b_origin, b_extent = unreal.SystemLibrary.get_actor_bounds(actor)
            z_bottom = b_origin.z - b_extent.z
            z_correction = loc.z - z_bottom
            if abs(z_correction) > 1.0:
                # 修复: z_correction是delta偏移量, 不是绝对Z坐标
                # 原bug: set_actor_location(loc.x, loc.y, z_correction) → 移到z=50(埋地)
                # 修正: loc.z + z_correction → 正确抬升底部到loc.z
                new_z = loc.z + z_correction
                actor.set_actor_location(
                    unreal.Vector(loc.x, loc.y, new_z), False, None)
                log("  BP_Z_FIX: " + str(round(z_bottom, 1)) + " -> " + str(round(new_z, 1)))
        except Exception as e_zfix:
            log("  BP_Z_FIX_SKIP: " + str(e_zfix))
    return actor


def spawn_hism(asset_path, location, instances, base_rotation=(0, 0, 0), base_scale=(1, 1, 1), material_override=None, cull_start=None, cull_end=None):
    """
    放置一个带 HierarchicalInstancedStaticMeshComponent 的 Actor, 批量添加实例。
    用途: 树木/麦田等大量重复网格, 比逐个 spawn StaticMeshActor 高效数百倍,
    且渲染合并 draw call, 大场景(数千实例)性能可控。
    参数:
      asset_path: 静态网格资产路径
      location: HISM Actor 的基准世界坐标
      instances: [{location, rotation, scale}, ...] 实例列表 (相对 actor 的局部坐标)
      base_rotation/base_scale: Actor 整体变换
      cull_start/cull_end: 每实例距离剔除(世界厘米). 实例距相机 < start 完全可见,
                           start~end 渐隐, > end 不渲染(GPU 不画). 两值同时给才生效.
                           用途: 森林等大批量实例, 远处不画只画近处, 大幅省 GPU.
    """
    loc = to_vector(location)
    # 1. 用 StaticMeshActor 作为 HISM 容器 (它自带根 SceneComponent, 可作 subobject 父)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, loc, to_rotator(base_rotation))
    if not actor:
        log("  HISM_SPAWN_FAIL " + str(location))
        return None
    # 2. 用 SubobjectDataSubsystem.add_new_subobject 创建持久化 HISM 子组件
    #    探测结论(UE5.8 Python):
    #    - new_object(outer=actor)+attach_to_component: 组件挂到场景图但不在 InstanceComponents
    #      数组里, 保存关卡时不序列化, 重载后组件与实例全部丢失;
    #    - register_component / add_instance_component 在 Python 反射中未暴露, 无法调用;
    #    - 唯一可行正道: SubobjectDataSubsystem.add_new_subobject(AddNewSubobjectParams),
    #      创建的组件进入 actor 的 subobject 树, 保存关卡时正确序列化,
    #      实例数据(PerInstanceData)随之持久化, 重载后组件数与实例数均保留(已验证)。
    global _sds
    if _sds is None:
        try:
            _sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        except Exception as e:
            log("  HISM_SDS_FAIL: " + str(e))
            return actor
    if not _sds:
        log("  HISM_SDS_NULL")
        return actor
    try:
        # gather 返回 actor 的 subobject handle 数组, handles[0] 为根 handle
        handles = _sds.k2_gather_subobject_data_for_instance(actor)
        if not handles:
            log("  HISM_NO_HANDLES")
            return actor
        # AddNewSubobjectParams 仅两个可写字段: parent_handle, new_class
        params = unreal.AddNewSubobjectParams()
        params.set_editor_property("parent_handle", handles[0])
        params.set_editor_property("new_class", unreal.HierarchicalInstancedStaticMeshComponent)
        _sds.add_new_subobject(params)
    except Exception as e:
        log("  HISM_SDS_ADD_FAIL: " + str(e))
        return actor
    # 3. 取刚创建的 HISM 组件
    comps = actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    if not comps:
        log("  HISM_COMP_NULL_AFTER_SDS")
        return actor
    him = comps[0]
    # 4. 加载并设置静态网格
    if asset_path not in _asset_cache:
        _asset_cache[asset_path] = unreal.EditorAssetLibrary.load_asset(asset_path)
    asset = _asset_cache[asset_path]
    if not asset:
        log("  HISM_ASSET_MISSING " + asset_path)
        return actor
    him.set_static_mesh(asset)
    # 每实例距离剔除(省资源核心): 设 InstanceStartCullDistance/InstanceEndCullDistance,
    # 实例距相机 < start 完全可见, start~end 渐隐, > end 不渲染(GPU 不画).
    # 用途: 森林等大批量实例, 远处不画只画近处, 大幅省 GPU. 值为世界厘米.
    if cull_start is not None and cull_end is not None:
        try:
            him.set_editor_property("InstanceStartCullDistance", int(cull_start))
            him.set_editor_property("InstanceEndCullDistance", int(cull_end))
            log("  HISM_CULL: start=" + str(int(cull_start)) + " end=" + str(int(cull_end)))
        except Exception as e_cull:
            log("  HISM_CULL_FAIL: " + str(e_cull))
    # 材质覆盖: HISM 继承自 StaticMeshComponent, set_material 对所有实例生效
    # 用途: 地面 tile 用统一草地材质, 避免 UV 被大缩放拉伸成纯色
    # 注意: 树木风动问题改用方案B(引擎着色器修复), 不再用材质覆写
    if material_override:
        mat = unreal.EditorAssetLibrary.load_asset(material_override)
        if mat:
            him.set_material(0, mat)
            log("  HISM_MATERIAL_OVERRIDE: " + material_override.split("/")[-1])
        else:
            log("  HISM_MATERIAL_OVERRIDE_FAIL: " + material_override)
    # 5. 批量添加实例
    # 关键修复: 探测确认 unreal.Transform 位置参数顺序为 (translation, rotation, scale3d),
    # 即第一个参数是 Vector(平移), 第二个 Rotator(旋转), 第三个 Vector(缩放)。
    # 之前误写成 (rotation, translation, scale) 导致 "Cannot nativize Rotator as Location"。
    n = 0
    for inst in instances:
        i_loc = inst.get("location", [0, 0, 0])
        i_rot = inst.get("rotation", [0, 0, 0])
        i_scl = inst.get("scale", [1, 1, 1])
        try:
            t = unreal.Transform(
                to_vector(i_loc),
                to_rotator(i_rot),
                to_vector(i_scl))
            him.add_instance(t)
            n += 1
        except Exception as e_inst:
            log("  HISM_ADD_INSTANCE_FAIL[" + str(n) + "]: " + str(e_inst))
            break
    if base_scale != (1, 1, 1):
        actor.set_actor_scale3d(unreal.Vector(base_scale[0], base_scale[1], base_scale[2]))
    log("  HISM_OK: " + str(n) + " x " + asset_path.split("/")[-1])
    return actor


def spawn_blueprint(bp_path, location, rotation=(0, 0, 0), scale=(1, 1, 1)):
    """
    放置一个蓝图 Actor (用于机库/村落住宅等完整功能体)。
    蓝图资产(UBlueprint)加载后取 generated_class (UBlueprintGeneratedClass),
    用该类 spawn_actor, 才能正确实例化蓝图内的所有组件网格。
    """
    loc = to_vector(location)
    rot = to_rotator(rotation)
    # 1. 加载蓝图资产对象
    if bp_path not in _asset_cache:
        _asset_cache[bp_path] = unreal.EditorAssetLibrary.load_asset(bp_path)
    bp_asset = _asset_cache[bp_path]
    if not bp_asset:
        log("  BP_MISSING " + bp_path)
        return None
    # 2. 取蓝图的生成类 (这才是可 spawn 的 UClass)
    # 探测确认: generated_class 在 Python 中是"方法"而非属性,
    #   get_editor_property("generated_class") 会失败 ("Failed to find property"),
    #   需调用 bp.generated_class() 取得 UBlueprintGeneratedClass;
    # 另有 _C 后缀路径兜底 (蓝图编译生成的类对象)。
    bp_class = None
    gc_attr = getattr(bp_asset, "generated_class", None)
    if gc_attr is not None:
        try:
            # 若是方法则调用, 若已是类对象则直接用
            bp_class = gc_attr() if callable(gc_attr) else gc_attr
        except Exception as e_gc:
            log("  BP_GC_CALL_FAIL: " + str(e_gc))
    if not bp_class:
        # 兜底: 直接 load _C 后缀路径 (蓝图生成类的标准资产路径)
        try:
            bp_class = unreal.EditorAssetLibrary.load_asset(bp_path + "_C")
        except Exception:
            pass
    if not bp_class:
        log("  BP_CLASS_FAIL " + bp_path)
        return None
    # 3. 用蓝图类 spawn actor
    try:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(bp_class, loc, rot)
    except Exception as e:
        log("  BP_SPAWN_FAIL " + str(location) + " err=" + str(e))
        return None
    if not actor:
        log("  BP_SPAWN_NULL " + str(location))
        return None
    if scale != (1, 1, 1):
        actor.set_actor_scale3d(unreal.Vector(scale[0], scale[1], scale[2]))
    # 自动修正Z位置: 获取蓝图Actor世界包围盒, 将底部对齐到location的Z坐标
    # 修复: 蓝图原点常在中心/顶部, 若不修正会导致房屋等建筑悬浮离地或沉入地下
    # (spawn_mesh 已有此逻辑, spawn_blueprint 此前缺失, 现补齐使两者落地行为一致)
    # 关键修复1: spawn后蓝图组件可能未完全注册, get_actor_bounds返回trivial bounds
    #   (extent≈0), 导致z_correction≈0, Z_FIX不触发, 蓝图网格保持默认偏移→房屋离地
    #   解决: 调用reregister_all_components强制组件注册后再取bounds
    # 关键修复2: z_correction是delta(偏移量), 不是绝对Z坐标
    #   原bug: set_actor_location(loc.x, loc.y, z_correction) → 移到z=50(埋地)
    #   修正: set_actor_location(loc.x, loc.y, loc.z + z_correction) → 正确抬升底部到loc.z
    try:
        actor.reregister_all_components()
    except Exception as e_reg:
        log("  BP_REREG_FAIL: " + str(e_reg))
    try:
        b_origin, b_extent = unreal.SystemLibrary.get_actor_bounds(actor)
        z_bottom = b_origin.z - b_extent.z
        z_correction = loc.z - z_bottom
        log("  BP_BOUNDS: origin.z=" + str(round(b_origin.z, 1)) +
            " extent.z=" + str(round(b_extent.z, 1)) +
            " z_bottom=" + str(round(z_bottom, 1)) +
            " z_corr=" + str(round(z_correction, 1)))
        if abs(z_correction) > 1.0:
            new_z = loc.z + z_correction
            actor.set_actor_location(
                unreal.Vector(loc.x, loc.y, new_z), False, None)
            log("  BP_Z_FIX: " + str(round(z_bottom, 1)) + " -> " + str(round(new_z, 1)))
    except Exception as e_zfix:
        log("  BP_Z_FIX_SKIP: " + str(e_zfix))
    return actor


def get_component(actor, comp_class):
    """获取 actor 上指定类型的组件 (用 get_component_by_class, 最可靠)"""
    try:
        comp = actor.get_component_by_class(comp_class)
        if comp:
            return comp
    except:
        pass
    return None


def setup_lighting(lighting_cfg):
    """
    根据 lighting 配置创建完整光照系统:
    - directional_light: 太阳光 (定向光), 设 intensity/color/cast_shadows
    - sky_light: 天空光 (环境光), 设 intensity/color, source_type=SpecifiedColor
    - sky_atmosphere: 大气层 (天空渲染)
    - height_fog: 指数高度雾, 设 density/color
    关键修复: Python spawn 的光源 intensity 默认=0 (非编辑器默认值), 必须显式设置
    """
    count = 0

    # ---- 1. 太阳光 (定向光) ----
    dl = lighting_cfg.get("directional_light")
    if dl:
        loc = dl.get("location", [0, 0, 3000])
        rot = dl.get("rotation", [-45, 35, 0])
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.DirectionalLight, to_vector(loc), to_rotator(rot))
            if actor:
                comp = get_component(actor, unreal.DirectionalLightComponent)
                if comp:
                    # 设置强度 (lux) - 核心修复: 不设置则默认0导致全黑
                    if "intensity" in dl:
                        comp.set_editor_property("intensity", dl["intensity"])
                    # 设置颜色 (unreal.Color, 0-255 整数)
                    if "color" in dl:
                        comp.set_editor_property("light_color", to_color(dl["color"]))
                    # 设置是否投射阴影
                    if "cast_shadows" in dl:
                        comp.set_editor_property("cast_shadows", dl["cast_shadows"])
                    # 关键修复: Python spawn 的光源默认 mobility=Static,
                    # 不参与实时渲染(Lumen/视口/截图均收不到光照→全黑)
                    # 必须设为 Movable 才能实时点亮场景
                    comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
                    # 关键修复: 标记为大气太阳光 (atmosphere_sun_light=True, index=0)
                    # 否则 SkyAtmosphere 无法识别太阳 → 大气不散射 → 天空纯黑
                    # (官方属性: atmosphere_sun_light, atmosphere_sun_light_index)
                    try:
                        comp.set_editor_property("atmosphere_sun_light", True)
                        comp.set_editor_property("atmosphere_sun_light_index", 0)
                    except Exception as e_sun:
                        log("atmosphere_sun_light set fail: " + str(e_sun))
                    log("DirectionalLight OK: intensity=" + str(dl.get("intensity")) +
                        " color=" + str(dl.get("color")) + " mobility=MOVABLE atmosphere_sun=ON")
                else:
                    log("WARN: DirectionalLightComponent 未找到")
                count += 1
        except Exception as e:
            log("DirectionalLight fail: " + str(e))

    # ---- 2. 天空光 (环境光) ----
    sl = lighting_cfg.get("sky_light")
    if sl:
        loc = sl.get("location", [0, 0, 3000])
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.SkyLight, to_vector(loc), to_rotator([0, 0, 0]))
            if actor:
                comp = get_component(actor, unreal.SkyLightComponent)
                if comp:
                    if "intensity" in sl:
                        comp.set_editor_property("intensity", sl["intensity"])
                    if "color" in sl:
                        comp.set_editor_property("light_color", to_color(sl["color"]))
                    # 设置光源类型为指定颜色 (确保有光照, 不依赖场景捕获)
                    try:
                        comp.set_editor_property("source_type",
                            unreal.SkyLightSourceType.SLS_SpecifiedColor)
                    except Exception:
                        pass
                    # 关键修复: 天空光同样需 Movable 才能实时贡献环境光
                    comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
                    log("SkyLight OK: intensity=" + str(sl.get("intensity")) +
                        " color=" + str(sl.get("color")) + " mobility=MOVABLE")
                count += 1
        except Exception as e:
            log("SkyLight fail: " + str(e))

    # ---- 3. 大气层 (天空渲染, 必须存在否则天空全黑) ----
    sa = lighting_cfg.get("sky_atmosphere")
    if not sa:
        # 关键兜底: JSON 缺少 sky_atmosphere 时使用默认值, 否则无大气散射→天空纯黑
        sa = {"render_in_main_pass": True, "sky_luminance_factor": [1.0, 1.0, 1.0], "multi_scattering_factor": 2.0}
        log("WARN: lighting 缺少 sky_atmosphere, 使用默认值 (天空渲染必需, 否则天空全黑)")
    if sa:
        loc = sa.get("location", [0, 0, 0])
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.SkyAtmosphere, to_vector(loc), to_rotator([0, 0, 0]))
            if actor:
                # 设为 Movable, 确保大气层实时渲染 (Static 时部分视口不更新天空)
                comp = get_component(actor, unreal.SkyAtmosphereComponent)
                if comp:
                    comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
                    # 可选: 天空增强参数 (单个失败不影响主流程)
                    # 注意: 属性名必须与 SkyAtmosphereComponent 官方 API 完全一致
                    try:
                        # render_in_main_pass: 强制大气在主渲染通道渲染 (bool)
                        # 关键: 解决 -unattended/cmd 模式下视口不渲染天空背景的根因
                        if "render_in_main_pass" in sa:
                            comp.set_editor_property("render_in_main_pass", sa["render_in_main_pass"])
                        # sky_luminance_factor: 放大天空像素亮度 (LinearColor 类型)
                        # 增强天空可见度, 同时影响 SkyLight 对天空的捕获
                        if "sky_luminance_factor" in sa:
                            v = sa["sky_luminance_factor"]
                            comp.set_editor_property("sky_luminance_factor",
                                unreal.LinearColor(v[0], v[1], v[2], 1.0))
                        # multi_scattering_factor: 多次散射因子 (float, 官方推荐值 2.0)
                        # 让大气多次散射更真实, 天空整体更亮更蓝
                        if "multi_scattering_factor" in sa:
                            comp.set_editor_property("multi_scattering_factor", sa["multi_scattering_factor"])
                    except Exception as e2:
                        log("SkyAtmosphere extra param skip: " + str(e2))
                log("SkyAtmosphere OK mobility=MOVABLE")
                count += 1
        except Exception as e:
            log("SkyAtmosphere fail: " + str(e))

    # ---- 4. 指数高度雾 (大气透视感) ----
    hf = lighting_cfg.get("height_fog")
    if hf:
        loc = hf.get("location", [0, 0, 0])
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.ExponentialHeightFog, to_vector(loc), to_rotator([0, 0, 0]))
            if actor:
                comp = get_component(actor, unreal.ExponentialHeightFogComponent)
                if comp:
                    if "density" in hf:
                        comp.set_editor_property("fog_density", hf["density"])
                    # UE5 属性名: fog_inscattering_luminance (UE4 的 fog_inscattering_color 已改名)
                    # 类型: LinearColor (非 Color)
                    if "color" in hf:
                        comp.set_editor_property("fog_inscattering_luminance", to_linear_color(hf["color"]))
                    log("HeightFog OK: density=" + str(hf.get("density")) +
                        " color=" + str(hf.get("color")))
                count += 1
        except Exception as e:
            log("HeightFog fail: " + str(e))

    return count


def setup_weather(weather_cfg):
    """
    根据 weather 配置创建天气系统:
    - volumetric_clouds: 体积云 (UE5 云层渲染)
    - post_process: 后期处理体积 (锁定曝光, 防止自动曝光导致画面过暗)
    """
    count = 0

    # ---- 1. 体积云 ----
    vc = weather_cfg.get("volumetric_clouds")
    if vc:
        loc = vc.get("location", [0, 0, 2000])
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.VolumetricCloud, to_vector(loc), to_rotator([0, 0, 0]))
            if actor:
                # 设为 Movable, 确保体积云实时渲染 (Static 时云层可能不显示)
                comp = get_component(actor, unreal.VolumetricCloudComponent)
                if comp:
                    comp.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
                log("VolumetricCloud OK mobility=MOVABLE")
                count += 1
        except Exception as e:
            log("VolumetricCloud fail: " + str(e))

    # ---- 2. 后期处理 (曝光控制) ----
    pp = weather_cfg.get("post_process")
    if pp:
        try:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
                unreal.PostProcessVolume, to_vector([0, 0, 0]), to_rotator([0, 0, 0]))
            if actor:
                # 设置为无限范围, 影响整个场景
                actor.set_editor_property("unbound", True)
                # 获取 PostProcessSettings 结构体, 设置曝光参数
                settings = actor.get_editor_property("settings")
                if settings:
                    if "auto_exposure_min" in pp:
                        settings.set_editor_property(
                            "auto_exposure_min_brightness", pp["auto_exposure_min"])
                    if "auto_exposure_max" in pp:
                        settings.set_editor_property(
                            "auto_exposure_max_brightness", pp["auto_exposure_max"])
                    # 结构体可能是值拷贝, 需写回 actor
                    actor.set_editor_property("settings", settings)
                log("PostProcessVolume OK: unbound=True exposure=" +
                    str(pp.get("auto_exposure_min")) + "~" + str(pp.get("auto_exposure_max")))
                count += 1
        except Exception as e:
            log("PostProcessVolume fail: " + str(e))

    return count


def clear_level_actors():
    """清空当前关卡所有 actor (保留 WorldSettings), 用于干净重建"""
    try:
        all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
        cleared = 0
        for a in all_actors:
            try:
                # 保留 WorldSettings (关卡根 actor, 删除会导致关卡损坏)
                if not isinstance(a, unreal.WorldSettings):
                    unreal.EditorLevelLibrary.destroy_actor(a)
                    cleared += 1
            except Exception:
                pass
        log("cleared " + str(cleared) + " existing actors")
    except Exception as e:
        log("clear actors fail: " + str(e))


def main():
    log("BUILD_SCENE_START")

    # ---- CLI 参数: 接受场景文件路径 (可复用工具) ----
    # 用法: py build_scene.py <scene.yaml|scene.json>
    # 注意: ExecCmds 中 "py script.py | quit" 的 | 可能被当作参数传入,
    #       所以需校验 sys.argv[1] 是否为真实文件路径, 非法则用默认值
    # 新增: 优先从环境变量 MAPFORGE_SCENE 读取场景文件路径,
    #       彻底避免 ExecCmds 中 | 被当 argv 传入导致回退默认场景的问题
    # 默认场景文件: scenes/examples/farming_village.yaml (目录重组后从子目录读取)
    DEFAULT_SCENE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenes", "examples", "farming_village.yaml")
    env_scene = os.environ.get("MAPFORGE_SCENE", "")
    if env_scene and os.path.isfile(env_scene):
        scene_file = env_scene
        log("scene_file (from MAPFORGE_SCENE env): " + scene_file)
    elif len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        scene_file = sys.argv[1]
    else:
        scene_file = DEFAULT_SCENE
        if len(sys.argv) > 1:
            log("argv[1] 不是有效文件路径: " + repr(sys.argv[1]) + ", 使用默认")
    log("scene_file: " + scene_file)

    scene = load_scene(scene_file)
    s = scene["scene"]
    target_level = s["target_level"]
    log("scene: " + s["name"] + " -> " + target_level)

    # ---- 详细场景转储: 地形/图层/河流道路/资产放置的全部坐标与参数写入日志 ----
    # 构建前先把输入 JSON 完整落档, 日志即场景档案, 排错时无需翻 JSON
    dump_scene_detail(scene)

    # ---- 创建/加载关卡 ----
    # 【关键修复】commandlet 模式下 new_level 总是把世界创建在 /Temp/Untitled_X，
    # save_map 时因世界路径≠目标路径，触发 SaveLevelAs 对话框 → 自动关闭 → 保存失败。
    # 修复方案：优先加载已有 UMAP（即使只有 8KB），世界直接在目标路径上，
    # save_map 走 SaveCurrentLevel 路径，无对话框，保存成功。
    # 只有首次构建（.umap 不存在）才走 new_level 创建流程。
    import time as _time
    import os as _os

    # 步骤1: 从磁盘检查 .umap 是否真正存在（不依赖 does_asset_exist，commandlet 下不可靠）
    _content_dir = unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.project_content_dir())
    _rel_path = target_level.replace("/Game/", "")
    _umap_disk = _os.path.join(_content_dir, _rel_path + ".umap")
    _umap_exists_on_disk = _os.path.exists(_umap_disk)

    level_created = False
    _world_at_target_path = False  # 标记世界是否在目标路径上（决定 save_map 走哪个分支）

    if _umap_exists_on_disk:
        log("磁盘上发现旧 .umap (" + str(_os.path.getsize(_umap_disk) // 1024) + "KB)，尝试加载到目标路径")
        # 加载已有关卡 → 世界直接在目标路径上 → save_map 走 SaveCurrentLevel → 无对话框
        for _load_attempt in range(3):
            try:
                unreal.EditorLevelLibrary.load_level(target_level)
                _world = unreal.EditorLevelLibrary.get_editor_world()
                if _world:
                    _pkg_path = _world.get_outer().get_path_name()
                    _expected_path = target_level.split("/")[-1]
                    if "/Temp/" not in _pkg_path:
                        log("关卡加载成功（尝试" + str(_load_attempt + 1) + "），包路径: " + _pkg_path)
                        level_created = True
                        _world_at_target_path = True
                        break
                    else:
                        log("加载后世界仍在 /Temp/（尝试" + str(_load_attempt + 1) + "）: " + _pkg_path)
                _time.sleep(1.0)
            except Exception as _e:
                log("load_level 失败（尝试" + str(_load_attempt + 1) + "）: " + str(_e))
                _time.sleep(1.0)

    if not level_created:
        # 首次构建：磁盘上无 .umap，使用 new_level 创建
        log("首次构建或加载失败，使用 new_level 创建关卡")
        try:
            _level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            if _level_subsystem:
                for _nl_attempt in range(3):
                    _level_subsystem.new_level(target_level)
                    _world = unreal.EditorLevelLibrary.get_editor_world()
                    if _world:
                        _pkg_path = _world.get_outer().get_path_name()
                        if "/Temp/" in _pkg_path:
                            log("new_level 回退到临时路径（尝试" + str(_nl_attempt + 1) + "）: " + _pkg_path + "，稍后重试")
                            _time.sleep(1.0)
                            continue
                        log("new_level 创建成功，包路径: " + _pkg_path)
                        level_created = True
                        _world_at_target_path = True
                        break
                    else:
                        log("new_level 创建成功")
                        level_created = True
                        break
                if not level_created:
                    log("new_level 3次均回退到 /Temp/，将尝试直接加载目标路径的空壳", "WARN")
                    # 【修复】new_level回退到/Temp/时会在目标路径创建8KB空壳.umap,
                    # 加载该空壳后世界在目标路径上, save_map走SaveCurrentLevel路径即可成功保存。
                    # 注意: PackageTools.find_or_create_package在UE5 Python API中不存在,
                    # 不能用它手动创建包。改用直接load_level加载new_level已创建的空壳。
                    _stub_exists = _os.path.exists(_umap_disk)
                    if _stub_exists:
                        _stub_size_kb = _os.path.getsize(_umap_disk) // 1024
                        log("空壳 .umap 已存在 (" + str(_stub_size_kb) + "KB)，尝试加载以将世界移至目标路径")
                        try:
                            unreal.EditorLevelLibrary.load_level(target_level)
                            _world = unreal.EditorLevelLibrary.get_editor_world()
                            if _world:
                                _pkg_path = _world.get_outer().get_path_name()
                                log("加载空壳后世界包路径: " + _pkg_path)
                                if "/Temp/" not in _pkg_path:
                                    _world_at_target_path = True
                                    log("世界已正确加载到目标路径")
                        except Exception as _e:
                            log("加载空壳失败: " + str(_e))
                    else:
                        log("空壳 .umap 不存在于磁盘（new_level未创建），回退使用当前 /Temp/ 世界")
                    level_created = True
        except AttributeError:
            log("LevelEditorSubsystem 不可用，降级使用 EditorLevelLibrary...", "WARN")
        except Exception as _e:
            log("LevelEditorSubsystem 创建关卡失败: " + str(_e) + "，降级使用 EditorLevelLibrary...", "WARN")

        if not level_created:
            try:
                unreal.EditorLevelLibrary.new_level(target_level)
                log("new_level 创建成功（EditorLevelLibrary，deprecated）")
                level_created = True
            except Exception as _e:
                log("new_level 创建失败: " + str(_e))

    # 步骤3: 清理模板 Actor（删除 OpenWorld 模板残留，标记世界为 dirty）
    # gen_2km_scene.py 已验证：cleanup_template_actors 删除模板 Actor 后，
    # 世界包被标记为 dirty，save_map 的 IsDirty() 检查通过，保存成功
    if level_created:
        clear_level_actors()
        # 额外清理模板 Actor（包括 HLOD/StaticMeshActor 等模板残留）
        try:
            _all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
            _keep_classes = {"WorldSettings", "LevelScriptActor", "Brush"}
            _deleted = 0
            for _actor in _all_actors:
                try:
                    _actor_class = _actor.get_class().get_name()
                    if _actor_class in _keep_classes:
                        continue
                    unreal.EditorLevelLibrary.destroy_actor(_actor)
                    _deleted += 1
                except:
                    pass
            if _deleted > 0:
                log("清理模板 Actor: " + str(_deleted) + " 个")
        except Exception as _e:
            log("清理模板 Actor 失败: " + str(_e))

    count = 0

    # ---- Landscape 正式地形 (UE5 Landscape) ----
    # 通过 C++ 插件 LandscapeHelper 创建真正的 UE5 Landscape 地形
    # Landscape 使用高度场(Heightmap)渲染, 支持雕刻/图层绘制/LOD, 比静态网格地面更专业
    # 需要项目安装 LandscapeHelper 插件 (Plugins/LandscapeHelper/)
    lscape = scene.get("landscape")
    if lscape:
        try:
            helper = unreal.LandscapeHelper
            # 从 JSON 读取参数, 提供合理默认值
            mat_path = lscape.get("material", "")
            loc = lscape.get("location", [0, 0, 0])
            rot = lscape.get("rotation", [0, 0, 0])
            scl = lscape.get("scale", [100, 100, 100])
            ssq = lscape.get("section_size_quads", 63)       # 每个 Section 的四边形数 (63/127/255)
            nsub = lscape.get("num_subsections", 1)          # 每个 Component 的 Subsection 数 (1/2)
            ccx = lscape.get("component_count_x", 8)         # X 方向 Component 数量
            ccy = lscape.get("component_count_y", 8)         # Y 方向 Component 数量

            # 先计算地形顶点尺寸 (用于日志确认参数正确)
            size_x, size_y = helper.calculate_landscape_size(ssq, nsub, ccx, ccy)
            # 物理尺寸 = quad数 × 缩放 / 100 (UE5中1 UU=1cm, 缩放100时每个quad=100cm=1m)
            phys_x = (ccx * ssq * nsub) * scl[0] / 100.0  # 转换为米
            phys_y = (ccy * ssq * nsub) * scl[1] / 100.0
            log("landscape: section_size=%d subsections=%d components=%dx%d -> vertices=%dx%d phys=%.1fm x %.1fm" %
                (ssq, nsub, ccx, ccy, size_x, size_y, phys_x, phys_y))

            # 从 JSON 读取图层权重和草地配置 (新功能: 填充图层权重 + UE5原生草地自动生成)
            layers_cfg = lscape.get("layers", [])
            grass_cfg = lscape.get("grass", {})

            if layers_cfg:
                # 新模式: 带图层权重 + 草地自动生成
                # 提取图层信息路径数组和权重数组 (C++ 接收 TArray<FString> 和 TArray<float>)
                layer_info_paths = [l.get("info", "") for l in layers_cfg]
                layer_weights = [float(l.get("weight", 0.0)) for l in layers_cfg]
                # 草地配置: 草地类型/网格/触发图层名/密度
                gt_path = grass_cfg.get("grass_type", "")
                gm_path = grass_cfg.get("grass_mesh", "")
                g_layer = grass_cfg.get("layer_name", "")
                g_density = float(grass_cfg.get("density", 200.0))

                log("landscape[layers]: %d layers configured" % len(layer_info_paths))
                for li, lw in zip(layer_info_paths, layer_weights):
                    log("  layer info=%s weight=%.2f" % (li, lw))
                log("landscape[grass]: type=%s mesh=%s layer=%s density=%.1f" %
                    (gt_path, gm_path, g_layer, g_density))

                # 小麦配置(可选): 当前JSON无wheat字段则传空字符串(向后兼容, 不生成小麦)
                wheat_cfg = lscape.get("wheat", {})
                wt_path = wheat_cfg.get("type_path", "")
                w_layer = wheat_cfg.get("layer_name", "")

                # 高度模式(可选): 当前JSON无height_pattern则传空字符串=平地(向后兼容)
                height_pattern = lscape.get("height_pattern", {})
                height_pattern_json = json.dumps(height_pattern) if height_pattern else ""

                # 每层权重模式(可选): 当前JSON无weight_pattern则传空数组=全图均匀(向后兼容)
                layer_weight_patterns = []
                for l in layers_cfg:
                    wp = l.get("weight_pattern", {})
                    layer_weight_patterns.append(json.dumps(wp) if wp else "")

                # 调用 C++ 插件创建带图层权重的 Landscape (共18个参数)
                # (填充 LayerData 权重数据 + 配置 LandscapeGrassOutput 草地自动生成)
                landscape_actor = helper.create_landscape_with_layers(
                    unreal.Vector(loc[0], loc[1], loc[2]),
                    unreal.Rotator(rot[0], rot[1], rot[2]),
                    unreal.Vector(scl[0], scl[1], scl[2]),
                    ssq, nsub, ccx, ccy,
                    mat_path,
                    layer_info_paths, layer_weights,
                    gt_path, gm_path, g_layer, g_density,
                    wt_path, w_layer,              # 第15-16参数: 小麦配置
                    height_pattern_json,           # 第17参数: 高度模式JSON
                    layer_weight_patterns          # 第18参数: 每层权重模式JSON数组
                )
            else:
                # 旧模式: 无图层权重 (平地无草地, 向后兼容)
                landscape_actor = helper.create_landscape(
                    unreal.Vector(loc[0], loc[1], loc[2]),
                    unreal.Rotator(rot[0], rot[1], rot[2]),
                    unreal.Vector(scl[0], scl[1], scl[2]),
                    ssq, nsub, ccx, ccy,
                    mat_path, True
                )

            if landscape_actor:
                count += 1
                log("landscape placed: %s (material=%s)" %
                    (landscape_actor.get_name(), mat_path if mat_path else "default"))

                # ---- 保存被C++修改的资产 (材质父材质 + 草地类型) ----
                # C++代码可能修改了:
                #   1. 父材质 MM_LandscapeBase 的 GrassOutput.GrassTypes (添加Layer1条目)
                #   2. LGT_Grass 的 GrassVarieties (添加草地变体)
                # 这些资产不在关卡包内，save_all_dirty_levels 不会保存它们
                # 必须显式 save_asset 保存到磁盘
                if mat_path:
                    try:
                        mat_obj = unreal.EditorAssetLibrary.load_asset(mat_path)
                        if mat_obj:
                            # 材质实例的 parent 才是被修改的基础材质
                            # 使用 get_editor_property("parent") 获取父材质路径
                            try:
                                parent_mat = mat_obj.get_editor_property("parent")
                                if parent_mat:
                                    parent_path = parent_mat.get_path_name()
                                    # 显式重新编译材质, 确保清理未连接GrassOutput条目后材质编译成功
                                    # (headless模式下PostEditChange可能不触发编译,需显式调用)
                                    try:
                                        unreal.MaterialEditingLibrary.recompile_material(parent_mat)
                                        log("parent material recompiled: " + parent_path)
                                    except Exception as e_recomp:
                                        log("material recompile skip: " + str(e_recomp))
                                    unreal.EditorAssetLibrary.save_asset(parent_path)
                                    log("parent material saved: " + parent_path)
                                    # 不对MI进行recompile_material和save_asset操作
                                    # 原因1: recompile_material只接受Material不接受MaterialInstanceConstant,
                                    #         调用会抛异常被静默捕获, 实际无效
                                    # 原因2: MI的texture_parameter_values(如雪地纹理)已由setup_snow_texture.py
                                    #         用Approach B(重建数组)写入磁盘, 此处save_asset可能保存
                                    #         被父材质recompile触发的重置状态, 导致纹理覆盖丢失
                            except Exception as e_parent:
                                log("parent material save skip: " + str(e_parent))
                    except Exception as e_mat:
                        log("material save fail: " + str(e_mat))
                if gt_path:
                    try:
                        unreal.EditorAssetLibrary.save_asset(gt_path)
                        log("grass type saved: " + gt_path)
                    except Exception as e_gt:
                        log("grass type save fail: " + str(e_gt))
                # 保存麦穗类型 LGT_Wheat: C++修改了其GrassVarieties(scale/density等),
                # 必须显式save_asset写盘, 否则编辑器加载的是磁盘旧版本(scale=0.9~1.1)
                if wt_path:
                    try:
                        unreal.EditorAssetLibrary.save_asset(wt_path)
                        log("wheat type saved: " + wt_path)
                    except Exception as e_wt:
                        log("wheat type save fail: " + str(e_wt))
            else:
                log("ERROR: landscape creation returned None!")
        except Exception as e:
            log("landscape creation failed: " + str(e))

    # ---- 地面 (静态网格) ----
    # 与 Landscape 二选一: 如果已有 Landscape, 通常不需要 ground
    # 但也可以叠加使用 (如 Landscape 作为地形 + ground 作为特殊区域)
    g = scene.get("ground")
    if g:
        spawn_mesh(g["asset"], g.get("location", [0, 0, 0]),
                   g.get("rotation", [0, 0, 0]), g.get("scale", [1, 1, 1]),
                   g.get("material_override"))
        count += 1
        log("ground placed")

    # ---- 放置列表 ----
    # 支持 type 字段分发:
    #   "instanced_grid": HISM 实例化 (树木/麦田等大量重复网格)
    #   "blueprint": 蓝图 Actor (机库/村落住宅)
    #   未指定 type: 原有 single 单体 / grid 网格 (StaticMeshActor)
    for i, p in enumerate(scene.get("placements", [])):
        # 跳过纯注释条目 (JSON 里用 {"_note": "..."} 标注分区, 无 asset/asset_prefix/village)
        # 模块4新增: village 类型用 house_assets 而非 asset, 需额外放行
        if "asset" not in p and "asset_prefix" not in p and "village" not in p:
            continue
        ptype = p.get("type", "static")
        asset = p.get("asset", "")

        # ---- HISM 实例化放置 ----
        if ptype == "instanced_grid":
            if asset not in _asset_cache:
                _asset_cache[asset] = unreal.EditorAssetLibrary.load_asset(asset)
            if not _asset_cache[asset]:
                log("SKIP[" + str(i) + "] him missing: " + asset)
                continue
            base_loc = p.get("location", [0, 0, 0])
            base_rot = p.get("rotation", [0, 0, 0])
            base_scl = p.get("scale", [1, 1, 1])
            # 支持两种方式生成实例: 显式 instances 数组 / grid 自动生成
            gr = p.get("grid")
            if gr:
                # 支持 pattern: "circle" 圆环布局(围栏/环形阵列)
                # 其它 pattern 或缺省: 走 rows/cols 矩形网格
                if gr.get("pattern") == "circle":
                    import math
                    cnt = gr["count"]
                    radius = gr.get("radius", 1000)
                    center = gr.get("center", [0, 0, 0])
                    # face_center: 实例朝向圆心, yaw = 角度+yaw_offset
                    # yaw_offset 默认90度(适配面板默认朝+Y); 可在JSON覆盖以适配不同网格朝向
                    face_center = gr.get("face_center", True)
                    yaw_off = gr.get("yaw_offset", 90.0)
                    z_off = gr.get("z_offset", 0)
                    cpitch = gr.get("pitch", 0.0)
                    smin = gr.get("scale_min", [1, 1, 1])
                    smax = gr.get("scale_max", [1, 1, 1])
                    # snap_to_ground: 逐实例查询地形表面Z, 使实例贴地(山谷/山丘自动跟随)
                    snap_ground = gr.get("snap_to_ground", False)
                    random.seed(i * 7 + 13)
                    instances = []
                    for k in range(cnt):
                        ang = (float(k) / cnt) * 2.0 * math.pi
                        x = center[0] + math.cos(ang) * radius
                        y = center[1] + math.sin(ang) * radius
                        if snap_ground:
                            tz = get_terrain_z(x, y)
                            z = (tz if tz is not None else center[2]) + z_off
                        else:
                            z = center[2] + z_off
                        yaw = (math.degrees(ang) + yaw_off) if face_center else 0.0
                        sx = random.uniform(smin[0], smax[0])
                        sy = random.uniform(smin[1], smax[1])
                        sz = random.uniform(smin[2], smax[2])
                        instances.append({
                            "location": [x, y, z],
                            "rotation": [cpitch, yaw, 0],
                            "scale": [sx, sy, sz],
                        })
                    n = len(instances)
                else:
                    rows = gr["rows"]; cols = gr["cols"]
                    origin = gr.get("origin", [0, 0, 0])
                    spacing = gr.get("spacing", [100, 100, 0])
                    jitter = gr.get("jitter", 0)
                    random_yaw = gr.get("random_yaw", False)
                    # pitch: 每实例俯仰角(光伏板向南倾斜), 0=保持网格平面朝上
                    gpitch = gr.get("pitch", 0.0)
                    # scale_min/scale_max 控制每实例缩放随机范围 (文档: Scale=0.80~1.25)
                    smin = gr.get("scale_min", [1, 1, 1])
                    smax = gr.get("scale_max", [1, 1, 1])
                    # snap_to_ground: 逐实例查询地形表面Z, 使实例贴地(山谷/山丘自动跟随)
                    snap_ground = gr.get("snap_to_ground", False)
                    random.seed(i * 7 + 13)
                    instances = []
                    for r in range(rows):
                        for c in range(cols):
                            jx = (random.random() - 0.5) * jitter * 2
                            jy = (random.random() - 0.5) * jitter * 2
                            jz = (random.random() - 0.5) * max(spacing[2], 1) * 0.3
                            x = origin[0] + c * spacing[0] + jx
                            y = origin[1] + r * spacing[1] + jy
                            if snap_ground:
                                tz = get_terrain_z(x, y)
                                z = (tz if tz is not None else origin[2]) + jz
                            else:
                                z = origin[2] + jz
                            yaw = random.random() * 360.0 if random_yaw else 0.0
                            sx = random.uniform(smin[0], smax[0])
                            sy = random.uniform(smin[1], smax[1])
                            sz = random.uniform(smin[2], smax[2])
                            instances.append({
                                "location": [x, y, z],
                                "rotation": [gpitch, yaw, 0],
                                "scale": [sx, sy, sz],
                            })
                    # 诊断摘要: snap_to_ground生效时打印Z范围及零值数, 验证贴地(山谷Z为负,山丘Z为正)
                    # zero_z: Z=0的实例数(疑似悬浮), 理想为0; >0说明高度图快照未覆盖该区域
                    if snap_ground and instances:
                        zs = [inst["location"][2] for inst in instances]
                        zero_count = sum(1 for v in zs if v == 0.0)
                        log("SNAP_SUMMARY[i=" + str(i) + "]: snap=True n=" + str(len(zs)) + " z_min=" + str(round(min(zs), 1)) + " z_max=" + str(round(max(zs), 1)) + " zero_z=" + str(zero_count) + " (疑似悬浮)")
                    n = len(instances)
            else:
                instances = p.get("instances", [])
                # snap_to_ground: 显式instances也支持贴地, 覆盖每个实例的Z为地形表面Z
                snap_ground = p.get("snap_to_ground", False)
                if snap_ground:
                    for inst in instances:
                        iloc = inst.get("location", [0, 0, 0])
                        tz = get_terrain_z(iloc[0], iloc[1])
                        if tz is not None:
                            iloc[2] = tz
                            inst["location"] = iloc
                n = len(instances)
            mat_override = p.get("material_override")
            # 距离剔除: 从 grid 配置读取 cull_start/cull_end (世界厘米), 传给 HISM.
            # 仅当 grid 存在且含这两个字段时启用, 缺省则不剔除(向后兼容).
            cull_start = gr.get("cull_start") if gr else None
            cull_end = gr.get("cull_end") if gr else None
            spawn_hism(asset, base_loc, instances, base_rot, base_scl, mat_override, cull_start, cull_end)
            count += n
            log("instanced_grid[" + str(i) + "]: " + str(n) + " x " + asset.split("/")[-1])
            continue

        # ---- 模块4新增: 农田行垄作物 (type=crop_field) ----
        # 封装行垄布局生成: 行距/株距/垄向可配, jitter 控制整齐度, snap_to_ground 贴地
        # 本质是 instanced_grid rows 的作物专用封装, 复用 spawn_hism 高效渲染
        if ptype == "crop_field":
            if asset not in _asset_cache:
                _asset_cache[asset] = unreal.EditorAssetLibrary.load_asset(asset)
            if not _asset_cache[asset]:
                log("SKIP[" + str(i) + "] crop missing: " + asset)
                continue
            fd = p["field"]
            origin = fd.get("origin", [0, 0, 0])  # 米
            sx_m, sy_m = fd.get("size_m", [100, 100])
            row_sp = fd.get("row_spacing_m", 1.0)
            plant_sp = fd.get("plant_spacing_m", 0.5)
            row_dir = fd.get("row_direction_deg", 0)
            jitter = fd.get("jitter", 0)
            snap_g = fd.get("snap_to_ground", False)
            smin = fd.get("scale_min", [1, 1, 1])
            smax = fd.get("scale_max", [1, 1, 1])
            # 单位转换: JSON origin/size/spacing 均为米, UE5世界坐标为厘米(cm)
            # spawn_hism 的 location=世界厘米, instances=相对actor的局部厘米偏移
            # get_terrain_z 的 x/y 也为厘米, 故全部 ×100 转换
            ox = origin[0] * 100.0  # actor 世界X(厘米)
            oy = origin[1] * 100.0  # actor 世界Y(厘米)
            oz = origin[2] * 100.0  # actor 世界Z(厘米)
            row_sp_cm = row_sp * 100.0       # 行距(厘米)
            plant_sp_cm = plant_sp * 100.0   # 株距(厘米)
            import math
            rad = math.radians(row_dir)
            # 垄向单位向量(dx,dy) + 垂直方向(px,py)
            dx, dy = math.cos(rad), math.sin(rad)
            px, py = -math.sin(rad), math.cos(rad)
            # 沿垄向投影长度(每行株数) + 垂直方向投影长度(行数)
            along_len = abs(sx_m * dx + sy_m * dy)
            perp_len = abs(sx_m * px + sy_m * py)
            n_rows = max(1, int(perp_len / row_sp))
            n_plants = max(1, int(along_len / plant_sp))
            random.seed(i * 7 + 13)
            instances = []
            for r in range(n_rows):
                off_row = r * row_sp_cm  # 厘米
                for c in range(n_plants):
                    off_plant = c * plant_sp_cm  # 厘米
                    # jitter 是比例值(0~1), 抖动量基于厘米间距
                    jx = (random.random() - 0.5) * jitter * plant_sp_cm * 2
                    jy = (random.random() - 0.5) * jitter * row_sp_cm * 2
                    # 世界坐标(厘米)
                    wx = ox + dx * off_plant + px * off_row + jx
                    wy = oy + dy * off_plant + py * off_row + jy
                    if snap_g:
                        tz = get_terrain_z(wx, wy)  # 厘米坐标查询地形Z
                        wz = tz if tz is not None else oz
                    else:
                        wz = oz
                    yaw = random.uniform(0, 360) if fd.get("random_yaw", False) else 0.0
                    sx_ = random.uniform(smin[0], smax[0])
                    sy_ = random.uniform(smin[1], smax[1])
                    sz_ = random.uniform(smin[2], smax[2])
                    # 实例位置=相对actor的局部偏移(厘米) = 世界坐标 - actor世界坐标
                    instances.append({"location": [wx - ox, wy - oy, wz - oz], "rotation": [0, yaw, 0], "scale": [sx_, sy_, sz_]})
            n = len(instances)
            # spawn_hism: location=actor世界坐标(厘米), instances=局部偏移(厘米)
            spawn_hism(asset, [ox, oy, oz], instances,
                       p.get("rotation", [0, 0, 0]), p.get("scale", [1, 1, 1]),
                       p.get("material_override"), None, None)
            count += n
            log("crop_field[" + str(i) + "]: " + str(n) + " x " + asset.split("/")[-1] + " rows=" + str(n_rows) + " plants=" + str(n_plants))
            continue

        # ---- 模块4新增: 村落生成 (type=village) ----
        # 三种布局: cluster(聚集) / rows(沿街) / scatter(泊松盘)
        # 房屋资产池随机选mesh, 按mesh分组用 spawn_hism 高效渲染
        if ptype == "village":
            vd = p["village"]
            center = vd.get("center", [0, 0, 0])  # 米
            house_count = vd.get("house_count", 10)
            layout = vd.get("layout", "cluster")
            house_assets = vd.get("house_assets", [])
            radius_m = vd.get("radius_m", 50)
            min_dist = vd.get("min_distance_m", 10)
            street_dir = vd.get("street_direction_deg", 0)
            street_sp = vd.get("street_spacing_m", 20)
            house_sp = vd.get("house_spacing_m", 8)
            snap_g = vd.get("snap_to_ground", False)
            random_yaw = vd.get("random_yaw", False)
            yaw_range = vd.get("yaw_range", [0, 360])
            smin = vd.get("scale_min", [1, 1, 1])
            smax = vd.get("scale_max", [1, 1, 1])
            seed = vd.get("seed", 42)
            # 单位转换: JSON center/radius/spacing 均为米, UE5世界坐标为厘米(cm)
            # spawn_hism 的 location=世界厘米, instances=相对actor的局部厘米偏移
            # get_terrain_z 的 x/y 也为厘米, 故全部 ×100 转换
            cx = center[0] * 100.0  # 村落中心X(厘米)
            cy = center[1] * 100.0  # 村落中心Y(厘米)
            cz = center[2] * 100.0  # 村落中心Z(厘米)
            radius_cm = radius_m * 100.0         # 半径(厘米)
            min_dist_cm = min_dist * 100.0       # 最小间距(厘米)
            street_sp_cm = street_sp * 100.0     # 街道间距(厘米)
            house_sp_cm = house_sp * 100.0       # 房屋间距(厘米)
            if not house_assets:
                log("SKIP[" + str(i) + "] village: empty house_assets")
                continue
            import math
            random.seed(seed)
            rad = math.radians(street_dir)
            dx, dy = math.cos(rad), math.sin(rad)
            px, py = -math.sin(rad), math.cos(rad)
            positions = []  # [(x, y), ...] 房屋二维坐标

            if layout == "cluster":
                # 聚集分布: 围绕中心随机分布, 泊松拒绝保证最小间距
                for k in range(house_count):
                    placed = False
                    for attempt in range(20):
                        ang = random.uniform(0, 2 * math.pi)
                        dist = random.uniform(0, radius_cm) * math.sqrt(random.random())
                        x = cx + math.cos(ang) * dist
                        y = cy + math.sin(ang) * dist
                        ok = True
                        for ex_x, ex_y in positions:
                            if (x - ex_x) ** 2 + (y - ex_y) ** 2 < min_dist_cm ** 2:
                                ok = False
                                break
                        if ok:
                            positions.append((x, y))
                            placed = True
                            break
                    if not placed:
                        # 拒绝上限耗尽, 退化为已有最佳位置(日志告警)
                        positions.append((x, y))
                if len(positions) < house_count:
                    log("VILLAGE_WARN[" + str(i) + "]: cluster 拒绝耗尽, 实际=" + str(len(positions)) + "/" + str(house_count))

            elif layout == "rows":
                # 沿街排列: 房屋沿街道两侧排列
                n_streets = max(1, int(math.sqrt(house_count)))
                per_street = max(1, house_count // (2 * n_streets))
                placed_count = 0
                for s in range(n_streets):
                    street_off = (s - (n_streets - 1) / 2.0) * street_sp_cm
                    for side in [-1, 1]:
                        for h in range(per_street):
                            if placed_count >= house_count:
                                break
                            along = h * house_sp_cm - (per_street - 1) * house_sp_cm / 2.0
                            x = cx + dx * along + px * street_off * side
                            y = cy + dy * along + py * street_off * side
                            positions.append((x, y))
                            placed_count += 1
                        if placed_count >= house_count:
                            break
                    if placed_count >= house_count:
                        break

            elif layout == "scatter":
                # 泊松盘散布: 随机撒点 + 拒绝重叠
                attempts = house_count * 30
                while len(positions) < house_count and attempts > 0:
                    x = random.uniform(cx - radius_cm, cx + radius_cm)
                    y = random.uniform(cy - radius_cm, cy + radius_cm)
                    ok = True
                    for ex_x, ex_y in positions:
                        if (x - ex_x) ** 2 + (y - ex_y) ** 2 < min_dist_cm ** 2:
                            ok = False
                            break
                    if ok:
                        positions.append((x, y))
                    attempts -= 1
                if len(positions) < house_count:
                    log("VILLAGE_WARN[" + str(i) + "]: scatter 拒绝耗尽, 实际=" + str(len(positions)) + "/" + str(house_count))

            else:
                log("SKIP[" + str(i) + "] village: 未知 layout=" + layout)
                continue

            # 按mesh分组: 每栋房屋从资产池随机选mesh, 同mesh的合并为一个HISM
            him_groups = {}  # {asset_path: [instances]}
            for (hx, hy) in positions:
                chosen = random.choice(house_assets)
                if snap_g:
                    tz = get_terrain_z(hx, hy)  # 厘米坐标查询地形Z
                    hz = tz if tz is not None else cz
                else:
                    hz = cz
                yaw = random.uniform(yaw_range[0], yaw_range[1]) if random_yaw else 0.0
                sx_ = random.uniform(smin[0], smax[0])
                sy_ = random.uniform(smin[1], smax[1])
                sz_ = random.uniform(smin[2], smax[2])
                if chosen not in him_groups:
                    him_groups[chosen] = []
                # 实例位置=相对actor的局部偏移(厘米) = 世界坐标 - actor世界坐标
                him_groups[chosen].append({"location": [hx - cx, hy - cy, hz - cz], "rotation": [0, yaw, 0], "scale": [sx_, sy_, sz_]})

            # 逐mesh组 spawn_hism 放置
            for asset_path, insts in him_groups.items():
                if asset_path not in _asset_cache:
                    _asset_cache[asset_path] = unreal.EditorAssetLibrary.load_asset(asset_path)
                if not _asset_cache[asset_path]:
                    log("  VILLAGE_SKIP " + asset_path)
                    continue
                # spawn_hism: location=actor世界坐标(厘米), instances=局部偏移(厘米)
                spawn_hism(asset_path, [cx, cy, cz], insts, [0, 0, 0], [1, 1, 1], None, None, None)
                count += len(insts)
                log("  village_group[" + asset_path.split("/")[-1] + "]: " + str(len(insts)))
            log("village[" + str(i) + "]: layout=" + layout + " houses=" + str(len(positions)) + " groups=" + str(len(him_groups)))
            continue

        # ---- 蓝图 Actor 放置 ----
        if ptype == "blueprint":
            loc = p.get("location", [0, 0, 0])
            rot = p.get("rotation", [0, 0, 0])
            scl = p.get("scale", [1, 1, 1])
            spawn_blueprint(asset, loc, rot, scl)
            count += 1
            log("blueprint[" + str(i) + "]: " + asset.split("/")[-1])
            continue

        # ---- 多Object组合放置 (停机坪/通信塔/高压塔等由多部件组成的单体) ----
        # asset_prefix 为路径前缀(如 .../Object_), 生成 Object_0..Object_{count-1}
        # 全部放在同一世界坐标; 部件内部相对偏移由资产自带, 自动组装成完整单体。
        if ptype == "group":
            prefix = p["asset_prefix"]
            gc = p["count"]
            gloc = p.get("location", [0, 0, 0])
            grot = p.get("rotation", [0, 0, 0])
            gscl = p.get("scale", [1, 1, 1])
            # 组合专属开关: 跳过Z自动修正 + 先缩放后旋转(复刻手动组装顺序) + 整体贴地, 默认False保持兼容
            gskip_z = p.get("skip_z_fix", False)
            gsbr = p.get("scale_before_rotation", False)
            # ground_assembly: 全部部件放置完成后, 统计世界空间最低Z, 整组平移使最低点对齐 gloc.z(贴地)
            # 用途: 高压电塔等竖立资产 roll-90 后躺倒, 各部件内部相对高度被保留, 但整组可能悬空或埋地, 需统一贴地
            gground = p.get("ground_assembly", False)
            # 贴地支持: 查询地形Z覆盖 gloc.z, 使组合体底部贴合地形表面(与 village snap_to_ground 同源)
            if p.get("snap_to_ground", False):
                tz = get_terrain_z(gloc[0], gloc[1])
                if tz is not None:
                    gloc = [gloc[0], gloc[1], tz]
            gn = 0
            actors = []  # 收集已生成actor, 供整组贴地平移使用
            for k in range(gc):
                ap = prefix + str(k)
                if ap not in _asset_cache:
                    # 先用短路径(仅包名)加载; 失败则回退完整路径 包名.对象名
                    # (某些资产对象名≠包名, 或短路径无法解析, 需显式对象名)
                    a = unreal.EditorAssetLibrary.load_asset(ap)
                    if not a:
                        base_name = ap.split("/")[-1]
                        a = unreal.EditorAssetLibrary.load_asset(ap + "." + base_name)
                    _asset_cache[ap] = a
                if _asset_cache[ap]:
                    a = spawn_mesh(ap, gloc, grot, gscl, None, gskip_z, gsbr)
                    if a:
                        actors.append(a)
                    gn += 1
                else:
                    log("  GROUP_SKIP " + ap)
            count += gn
            log("group[" + str(i) + "]: " + str(gn) + "/" + str(gc) + " x " + prefix.split("/")[-1])
            # 整体贴地: 遍历所有部件世界空间包围盒, 取最低Z, 整体平移至 gloc.z
            # 在 roll/scale 已生效后取 bounds(世界空间), 故自动包含旋转后的真实最低点
            if gground and actors:
                try:
                    min_z = None
                    for a in actors:
                        b_origin, b_extent = unreal.SystemLibrary.get_actor_bounds(a)
                        z_bottom = b_origin.z - b_extent.z
                        if min_z is None or z_bottom < min_z:
                            min_z = z_bottom
                    z_shift = gloc[2] - min_z
                    if abs(z_shift) > 1.0:
                        for a in actors:
                            loc_now = a.get_actor_location()
                            a.set_actor_location(
                                unreal.Vector(loc_now.x, loc_now.y, loc_now.z + z_shift), False, None)
                        log("  ASSEMBLY_GROUND: min_z=" + str(round(min_z, 1)) + " -> " + str(round(gloc[2], 1)) + " shift=" + str(round(z_shift, 1)))
                    else:
                        log("  ASSEMBLY_GROUND: already_grounded min_z=" + str(round(min_z, 1)))
                except Exception as e_ground:
                    log("  ASSEMBLY_GROUND_FAIL: " + str(e_ground))
            continue

        # ---- 原有 StaticMeshActor 放置 (single / grid) ----
        if asset not in _asset_cache:
            _asset_cache[asset] = unreal.EditorAssetLibrary.load_asset(asset)
        if not _asset_cache[asset]:
            log("SKIP[" + str(i) + "] missing: " + asset)
            continue
        if "grid" in p:
            gr = p["grid"]
            rows = gr["rows"]; cols = gr["cols"]
            origin = gr.get("origin", [0, 0, 0])
            spacing = gr.get("spacing", [100, 100, 0])
            jitter = gr.get("jitter", 0)
            rot = p.get("rotation", [0, 0, 0])
            scl = p.get("scale", [1, 1, 1])
            # snap_to_ground: 逐实例查询地形表面Z, 使实例贴地(山谷/山丘自动跟随)
            snap_ground = gr.get("snap_to_ground", False)
            random.seed(i * 7 + 13)
            n = 0
            for r in range(rows):
                for c in range(cols):
                    jx = (random.random() - 0.5) * jitter * 2
                    jy = (random.random() - 0.5) * jitter * 2
                    jz = (random.random() - 0.5) * max(spacing[2], 1) * 0.3
                    x = origin[0] + c * spacing[0] + jx
                    y = origin[1] + r * spacing[1] + jy
                    if snap_ground:
                        tz = get_terrain_z(x, y)
                        z = (tz if tz is not None else origin[2]) + jz
                    else:
                        z = origin[2] + jz
                    spawn_mesh(asset, [x, y, z], rot, scl)
                    n += 1
            count += n
            log("grid[" + str(i) + "]: " + str(n) + " x " + asset.split("/")[-1])
        else:
            loc = p.get("location", [0, 0, 0])
            rot = p.get("rotation", [0, 0, 0])
            scl = p.get("scale", [1, 1, 1])
            # snap_to_ground: 单个实例也支持贴地, 查询地形Z覆盖location的Z
            if p.get("snap_to_ground", False):
                tz = get_terrain_z(loc[0], loc[1])
                if tz is not None:
                    loc = [loc[0], loc[1], tz]
            spawn_mesh(asset, loc, rot, scl)
            count += 1
            log("single[" + str(i) + "]: " + asset.split("/")[-1])

    # ---- 光照系统 (修复全黑: 显式设置 intensity/color) ----
    lighting = scene.get("lighting")
    if lighting:
        count += setup_lighting(lighting)
        log("lighting setup done")
    else:
        log("WARN: scene 无 lighting 配置, 场景可能全黑")

    # ---- 天气系统 (体积云 + 后期处理曝光控制) ----
    weather = scene.get("weather")
    if weather:
        count += setup_weather(weather)
        log("weather setup done")

    # ---- 保存关卡 ----
    # 【关键修复】commandlet 模式下 save_map(world, target_level) 可直接将世界（即使在
    # /Temp/）保存到 target_level 指定路径。此前代码在 _world_at_target_path=False 时
    # 跳过 save_map 直接走 save_asset，导致 /Temp/ 世界的 Actor 全部丢失、umap 全黑。
    # 现对齐 gen_2km_scene.py: 始终尝试 save_map，失败再依次降级 save_current_level /
    # save_all_dirty_levels / save_asset。
    saved_ok = False
    editor_world = unreal.EditorLevelLibrary.get_editor_world()
    if editor_world:
        # 打印世界包路径用于诊断
        try:
            _pkg_name = editor_world.get_outer().get_path_name()
            log("保存关卡: 世界包路径=" + _pkg_name + " → " + target_level)
        except Exception:
            log("保存关卡: (无法获取世界包路径) → " + target_level)

        # GC 清理: 清除模板 Actor 残留引用，防止 save_map 报"非法引用"错误
        try:
            unreal.SystemLibrary.collect_garbage()
            _time.sleep(1.0)
            log("save_map 前 GC 清理完成")
        except Exception:
            pass

        # 方式1: EditorLoadingAndSavingUtils.save_map (核心方法)
        # 无论世界在目标路径还是 /Temp/，都尝试 save_map 保存到 target_level
        # commandlet 模式无 UI，不会弹出 SaveLevelAs 对话框
        for _sv_attempt in range(3):
            try:
                _result = unreal.EditorLoadingAndSavingUtils.save_map(editor_world, target_level)
                if _result:
                    log("save_map 成功（尝试" + str(_sv_attempt + 1) + "）: " + target_level)
                    saved_ok = True
                    break
                else:
                    log("save_map 返回 False（尝试" + str(_sv_attempt + 1) + "，GC 后重试）")
            except Exception as _e:
                log("save_map 失败（尝试" + str(_sv_attempt + 1) + "）: " + str(_e))
            # GC + 延迟后重试
            try:
                unreal.SystemLibrary.collect_garbage()
            except Exception:
                pass
            _time.sleep(1.0)

        # 磁盘验证：检查 .umap 是否真的写入了磁盘（排除旧文件假阳性）
        # 【修复】new_level在回退到/Temp/时会在目标路径创建8KB空壳.umap,
        # save_map返回False但磁盘验证找到空壳(8KB)错误判定成功,跳过所有后备保存。
        # 增加最小大小阈值: 504m地形含4层权重至少>200KB, <100KB=空壳无效
        _MIN_UMAP_BYTES = 100 * 1024  # 100KB, 8KB空壳会被过滤
        try:
            _content_dir = unreal.Paths.convert_relative_path_to_full(
                unreal.Paths.project_content_dir())
            _rel_path = target_level.replace("/Game/", "")
            _umap_disk = _os.path.join(_content_dir, _rel_path + ".umap")
            if _os.path.exists(_umap_disk):
                _size_kb = _os.path.getsize(_umap_disk) // 1024
                _mtime = _os.path.getmtime(_umap_disk)
                _age = _time.time() - _mtime
                if _age < 30 and _os.path.getsize(_umap_disk) > _MIN_UMAP_BYTES:
                    log("磁盘验证: .umap 已保存 (" + str(_size_kb) + "KB, " + str(round(_age, 1)) + "秒前)")
                    saved_ok = True
                elif _os.path.getsize(_umap_disk) <= _MIN_UMAP_BYTES:
                    log("磁盘验证: .umap 文件过小 (" + str(_size_kb) + "KB), 是空壳存根, 保存失败, 尝试降级方案")
                    saved_ok = False
                else:
                    log("磁盘验证: .umap 存在但非刚保存 (" + str(_size_kb) + "KB, " + str(round(_age, 0)) + "秒前)，保存可能失败!")
                    saved_ok = False
            elif saved_ok:
                log("save_map 返回成功但磁盘上找不到 .umap!")
                saved_ok = False
        except Exception as _e:
            log("磁盘验证失败: " + str(_e))

        # 方式2: EditorLevelLibrary.save_current_level (deprecated, 补充保存)
        if not saved_ok:
            try:
                unreal.EditorLevelLibrary.save_current_level()
                log("save_current_level 调用完成")
                saved_ok = True
            except Exception as _e:
                log("save_current_level 失败: " + str(_e))

        # 方式3: save_all_dirty_levels (批量保存所有脏关卡)
        if not saved_ok:
            try:
                unreal.EditorLevelLibrary.save_all_dirty_levels()
                log("save_all_dirty_levels 调用完成")
                saved_ok = True
            except Exception as _e:
                log("save_all_dirty_levels 失败: " + str(_e))

    # 方式4: 后备方案 save_asset 强制保存 (最后手段)
    if not saved_ok:
        try:
            unreal.EditorAssetLibrary.save_asset(target_level, False)
            log("SAVED_ASSET_FORCE: " + target_level)
        except Exception as _e:
            log("save_asset fail: " + str(_e))

    log("TOTAL_PLACED: " + str(count) + " (仅Python层Actor, C++层Scatter/Water/Road/Building/Grass不在此计数)")
    log("BUILD_SCENE_DONE")
    _f.close()


main()
