#!/usr/bin/env python3
# ============================================================================
# build_umap.py - JSON 场景 → UE5 umap 一键构建工具
# ============================================================================
# 用法:
#   python build_umap.py --scene-json <场景.json>
#   或通过 build_umap.bat <场景.json> [forcekill] [open] 调用
#   --force-kill 开关: 跳过编辑器关闭询问, 直接终止 (用于无人值守场景)
#   --open-editor 开关: 构建成功后自动打开 UE 编辑器并加载生成的 umap
#
# 日志策略 (每次构建一个带时间戳的日志文件):
#   每次转换生成 build_umap_<yyyyMMdd_HHmmss>.log, 自动保留最近 20 份 (--keep-logs 可调),
#   旧日志自动清理; 文件头部打印场景 JSON 全路径, 正文用前置标签区分类型:
#   [DUMP]  场景参数转储 (地形坐标/图层/河流道路折点/资产坐标高度值)
#   [BUILD] 构建流程进度 (Python 端)
#   [CARVE] C++ 地形雕刻日志 (河床冲刷/道路平整, 构建后从引擎日志提取)
#   [ERROR] 错误行 (构建后从引擎日志提取)
#   [SUMMARY] 构建结果摘要
#   注: UE 引擎自身的日志 (Saved/Logs/MyUETest5_8_2.log) 由引擎固定写入,
#       本脚本只从中提取关键行追加到主日志, 不作为独立产物维护。
#
# UE 进程策略:
#   - GUI 编辑器 (UnrealEditor.exe): 锁定插件 DLL 且占用资产, 必须关闭;
#     默认交互询问 (防止丢失未保存修改), --force-kill 跳过询问
#   - 无头残留 (UnrealEditor-Cmd.exe): 上次构建挂起的残留, 直接终止
# ============================================================================

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# ---- 路径配置: 从 ~/.uescenefactory_config.json 读取 (与 GUI 共用), 不再硬编码 ----
def _resolve_paths():
    """从配置文件或环境变量解析 UE5 路径。

    优先级: 环境变量 > ~/.uescenefactory_config.json > 空串(调用方报错)。
    与 GUI (mapforge_app.py) 共用同一份配置, 用户在 GUI 设置一次即可。
    """
    ue5_cmd = ""
    project = ""
    # 1. 尝试从配置文件读取
    _config_path = os.path.join(os.path.expanduser("~"), ".uescenefactory_config.json")
    # 一次性迁移: 旧配置存在则重命名, 保留用户已设置的 UE5/项目路径
    _legacy = os.path.join(os.path.expanduser("~"), ".mapforge_config.json")
    if not os.path.exists(_config_path) and os.path.exists(_legacy):
        try:
            os.rename(_legacy, _config_path)
        except OSError:
            pass
    try:
        with open(_config_path, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
        ue5_cmd = _cfg.get("ue5_path", "")
        project = _cfg.get("project_path", "")
    except Exception:
        pass
    # 2. 环境变量覆盖 (支持无人值守/CI 场景)
    ue5_cmd = os.environ.get("MAPFORGE_UE5_EXE", ue5_cmd)
    project = os.environ.get("MAPFORGE_PROJECT", project)
    return ue5_cmd, project

EXE, PROJ = _resolve_paths()
# 从 PROJ 推导: .uproject 同级目录下的 Content
CONTENT_DIR = os.path.join(os.path.dirname(PROJ), "Content") if PROJ else ""
# 从 PROJ 推导: Saved/Logs/<项目名>.log
_proj_name = os.path.splitext(os.path.basename(PROJ))[0] if PROJ else ""
ENGINE_LOG_PATH = os.path.join(os.path.dirname(PROJ), "Saved", "Logs", _proj_name + ".log") if PROJ else ""
# 从 EXE 推导: 同目录下的 UnrealEditor.exe (GUI 编辑器, 非无头)
EDITOR_EXE = os.path.join(os.path.dirname(EXE), "UnrealEditor.exe") if EXE else ""

# 启用 Windows 10+ 控制台 ANSI 转义码支持 (颜色输出)
if sys.platform == "win32":
    os.system("")

# 脚本自身所在目录
SCRIPT_DIR = Path(__file__).resolve().parent

# 全局变量
main_log_path = None

# ---- ANSI 颜色 ----
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_MAGENTA = "\033[95m"
C_RESET = "\033[0m"


def write_step(msg):
    print(f"{C_CYAN}[步骤] {msg}{C_RESET}")


def write_ok(msg):
    print(f"{C_GREEN}[OK]   {msg}{C_RESET}")


def write_warn(msg):
    print(f"{C_YELLOW}[警告] {msg}{C_RESET}")


def write_fail(msg):
    print(f"{C_RED}[失败] {msg}{C_RESET}", file=sys.stderr)


def add_main_log(line):
    """写一行到主日志 (构建完成后脚本侧追加内容用; 构建期间由 build_scene.py 直写)"""
    with open(main_log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def kill_process(name):
    """终止指定名称的进程, 返回是否找到了进程"""
    try:
        result = subprocess.run(
            ["taskkill", "/f", "/im", name],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def get_process_pids(name):
    """获取指定进程名的 PID 列表"""
    try:
        result = subprocess.run(
            ["tasklist", "/fi", f"IMAGENAME eq {name}", "/fo", "csv", "/nh"],
            capture_output=True, text=True
        )
        pids = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.replace('"', "").split(",")
            if len(parts) >= 2:
                try:
                    pids.append(int(parts[1].strip()))
                except ValueError:
                    pass
        return pids
    except Exception:
        return []


def message_box(title, msg, icon=0x30):
    """弹出 Windows 消息框 (0x30=Warning图标, 返回值: 6=Yes, 7=No)"""
    return ctypes.windll.user32.MessageBoxW(0, msg, title, 0x04 | icon)


def strip_engine_ts(line):
    """去掉引擎日志的时间戳前缀 [2026.xx.xx-xx.xx.xx:xxx][  0]"""
    return re.sub(r'^\[[^\]]+\]\[\s*\d+\]\s*', '', line).strip()


def parse_args():
    """解析命令行参数, 兼容 build_umap.bat 的位置参数风格"""
    parser = argparse.ArgumentParser(description="JSON 场景 → UE5 umap 一键构建工具")
    parser.add_argument("--scene-json", "-SceneJson", type=str, default=None,
                        help="场景 JSON 文件路径 (必填)")
    parser.add_argument("--timeout-sec", type=int, default=1800,
                        help="构建超时秒数 (默认 30 分钟)")
    parser.add_argument("--grace-sec", type=int, default=90,
                        help="完成标记出现后等待引擎自然退出的宽限秒数")
    parser.add_argument("--force-kill", "-ForceKill", action="store_true",
                        help="跳过编辑器关闭询问, 直接终止 (无人值守模式)")
    parser.add_argument("--open-editor", "-OpenEditor", action="store_true",
                        help="构建成功后自动打开 UE 编辑器并加载生成的 umap")
    parser.add_argument("--keep-logs", type=int, default=20,
                        help="时间戳日志保留份数 (旧的自动清理, 默认 20)")

    # 兼容位置参数: build_umap.py <scene.json> [forcekill] [open]
    args, unknown = parser.parse_known_args()

    # 如果 --scene-json 未指定, 尝试从位置参数中获取
    if args.scene_json is None:
        for u in unknown:
            if not u.startswith("-") and u.lower() not in ("forcekill", "open"):
                args.scene_json = u
                break

    # 力挺 kill 和 open 也可以通过位置参数传入 (兼容 .bat 调用)
    for u in unknown:
        if u.lower() == "forcekill":
            args.force_kill = True
        elif u.lower() == "open":
            args.open_editor = True

    return args


def main():
    global main_log_path

    args = parse_args()

    if not args.scene_json:
        write_fail("用法: python build_umap.py --scene-json <场景.json> [--force-kill] [--open-editor]")
        sys.exit(1)

    # 时间戳
    time_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    main_log_path = str(SCRIPT_DIR / f"build_umap_{time_stamp}.log")

    # ========== 步骤1: 校验场景 JSON ==========
    write_step(f"校验场景文件: {args.scene_json}")
    scene_json_path = os.path.abspath(args.scene_json)
    if not os.path.exists(scene_json_path):
        write_fail(f"场景文件不存在: {scene_json_path}")
        sys.exit(1)

    # 直接解析 JSON 获取元数据 (无需子进程调用 python -c)
    try:
        with open(scene_json_path, "r", encoding="utf-8") as f:
            scene_data = json.load(f)
        scene_meta = scene_data.get("scene", {})
        scene_name = scene_meta.get("name", "")
        target_level = scene_meta.get("target_level", "")
    except json.JSONDecodeError as e:
        write_fail(f"JSON 语法错误: {e}")
        sys.exit(1)

    write_ok(f"JSON 语法合法  场景名={scene_name}  目标关卡={target_level}")

    # ========== 步骤1.5: 资产路径预校验 ==========
    write_step("资产路径预校验...")
    validator = str(SCRIPT_DIR / "validate_scene_assets.py")
    try:
        check_result = subprocess.run(
            [sys.executable, validator, scene_json_path],
            capture_output=True, text=True
        )
        check_out = (check_result.stdout + check_result.stderr).strip()
        if check_result.returncode != 0:
            # asset_prefix 模式匹配可能导致预校验误报, 改为警告而非中止
            write_warn("资产路径预校验有缺失项 (可能为 asset_prefix 误报), 继续构建...")
            for line in check_out.splitlines():
                print(f"    {C_YELLOW}{line}{C_RESET}")
        # 查找 ASSET_CHECK_OK 行
        for line in check_out.splitlines():
            if "ASSET_CHECK_OK" in line:
                write_ok(line.strip())
                break
    except Exception as e:
        write_warn(f"资产路径预校验异常: {e}, 继续构建...")

    # ========== 步骤1.6: 目标 umap 存在性检查 ==========
    umap_path = ""
    if target_level:
        rel = target_level.replace("/Game/", "", 1)
        umap_path = os.path.join(CONTENT_DIR, rel + ".umap")
    if umap_path and os.path.exists(umap_path):
        st = os.stat(umap_path)
        size_mb = round(st.st_size / (1024 * 1024), 2)
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        if args.force_kill:
            # --force-kill 模式下自动确认，不弹消息框阻塞无人值守构建
            write_ok(f"保留已有 umap ({size_mb} MB)，build_scene.py 将加载并覆盖 (--force-kill 自动确认)")
        else:
            msg = (f"目标 umap 文件已存在: {umap_path}\n\n"
                   f"大小: {size_mb} MB\n"
                   f"最后修改: {mtime}\n\n"
                   f"继续将加载已有 umap 并在其上覆盖构建。是否继续?")
            result = message_box("umap 文件已存在", msg)
            if result == 6:  # Yes
                write_ok(f"保留已有 umap ({size_mb} MB)，build_scene.py 将加载并覆盖")
            else:
                write_fail("用户取消构建 (umap 文件已存在)")
                sys.exit(1)

    # ========== 步骤2: 清理 UE 进程 ==========
    # 2.1 无头残留进程 (UnrealEditor-Cmd): 上次构建挂起的残留, 直接终止无风险
    headless_pids = get_process_pids("UnrealEditor-Cmd.exe")
    if headless_pids:
        for pid in headless_pids:
            write_warn(f"终止无头残留进程 UnrealEditor-Cmd (PID {pid})")
        kill_process("UnrealEditor-Cmd.exe")
        time.sleep(2)
        write_ok("无头残留进程已清理")

    # 2.2 GUI 编辑器 (UnrealEditor): 锁定插件 DLL + 占用资产句柄, 必须关闭才能构建
    editor_pids = get_process_pids("UnrealEditor.exe")
    if editor_pids:
        for pid in editor_pids:
            write_warn(f"检测到 UE 编辑器正在运行 (PID {pid})")
        if args.force_kill:
            write_warn("--force-kill 已指定, 直接终止编辑器 (未保存的修改将丢失)")
            answer = "y"
        else:
            answer = input("构建需要关闭 UE 编辑器 (否则插件 DLL 被锁定/资产写入冲突)。关闭? [Y/n] ").strip()
            if not answer:
                answer = "y"
        if answer.lower().startswith("y"):
            for pid in editor_pids:
                try:
                    subprocess.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True)
                except Exception:
                    pass
            time.sleep(3)
            write_ok("编辑器已关闭")
        else:
            write_fail("用户选择不关闭编辑器, 构建中止 (插件 DLL 被锁定, 无法安全构建)")
            sys.exit(1)
    else:
        write_ok("无 UE 编辑器进程运行")

    # ========== 步骤3: 无头模式构建 ==========
    write_step("启动 UE5 无头模式构建 (可能需要 10~20 分钟)...")
    add_main_log("[HEADER] ==================== 构建日志 ====================")
    add_main_log(f"[HEADER] 构建开始时间 : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add_main_log(f"[HEADER] 场景 JSON 全路径 : {scene_json_path}")
    add_main_log(f"[HEADER] 目标关卡 : {target_level}")
    add_main_log("[HEADER] ====================================================")

    # stdout/stderr 重定向到临时文件 (引擎输出大量噪音, 不作产物保留, 构建后删除)
    tmp_out = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", ".")),
                           f"build_umap_stdout_{uuid.uuid4().hex[:8]}.tmp")
    tmp_err = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", ".")),
                           f"build_umap_stderr_{uuid.uuid4().hex[:8]}.tmp")

    # 场景路径与主日志路径都经环境变量传递
    os.environ["MAPFORGE_SCENE"] = scene_json_path
    os.environ["MAPFORGE_LOG"] = main_log_path

    exec_cmds = f'py {str(SCRIPT_DIR).replace(chr(92), "/")}/build_scene.py | quit'

    t0 = time.monotonic()
    with open(tmp_out, "w") as fout, open(tmp_err, "w") as ferr:
        # 使用 shell=False 直接传命令行字符串给 CreateProcess,
        # 不走 cmd.exe, 避免 shell 注入风险 (&/|/$ 等特殊字符被 cmd.exe 解析)
        # CreateProcess 会正确处理引号, -ExecCmds="..." 中的 | 作为 UE5 命令分隔符原样传递
        cmd = f'"{EXE}" "{PROJ}" -unattended -nop4 -nosplash -nullrhi -stdout -NoConnect -NoHTTPRequests -ExecCmds="{exec_cmds}"'
        proc = subprocess.Popen(
            cmd,
            stdout=fout, stderr=ferr, shell=False
        )

    # ========== 步骤4: 监控构建进度 ==========
    write_step(f"监控构建进程 (PID {proc.pid}), 超时 {args.timeout_sec} 秒...")
    done_marker = False
    timed_out = False
    grace_t0 = None

    log_pos = 0  # 日志文件读取偏移量, 用于增量扫描, 避免每次完整读取
    while True:
        # 引擎已自然退出 → 结束监控
        if proc.poll() is not None:
            break

        # 检测完成标记 (增量读取: 只扫描新增内容, 避免日志增长后每次完整读取的性能开销)
        if not done_marker and os.path.exists(main_log_path):
            try:
                with open(main_log_path, "r", encoding="utf-8") as f:
                    f.seek(log_pos)
                    chunk = f.read()
                    log_pos = f.tell()
                    if "BUILD_SCENE_DONE" in chunk:
                        done_marker = True
                        elapsed = int(time.monotonic() - t0)
                        write_ok(f"检测到 BUILD_SCENE_DONE (耗时 {elapsed} 秒), 等待引擎退出 (宽限 {args.grace_sec} 秒)...")
                        grace_t0 = time.monotonic()
            except Exception:
                pass

        # 完成标记已出现但引擎迟迟不退出 → 宽限期满强杀
        if done_marker and grace_t0 and (time.monotonic() - grace_t0 > args.grace_sec):
            write_warn("引擎保存完成后挂起未退出, 强制结束进程 (UMAP 已落盘, 不受影响)")
            try:
                proc.kill()
            except Exception:
                pass
            break

        # 总超时
        if time.monotonic() - t0 > args.timeout_sec:
            write_fail(f"构建超时 ({args.timeout_sec} 秒), 强制结束进程")
            try:
                proc.kill()
            except Exception:
                pass
            timed_out = True
            break

        time.sleep(5)

    elapsed_total = int(time.monotonic() - t0)

    # 删除临时 stdout/stderr 文件
    for tmp in (tmp_out, tmp_err):
        try:
            os.remove(tmp)
        except OSError:
            pass

    # ========== 步骤4.5: 从引擎日志提取 C++ 雕刻日志与错误行 ==========
    carve_lines = []
    err_lines = []
    carve_pattern = re.compile(
        r"河床冲刷|道路推平|LandscapeHelper\[(Scatter|Water|Road|Building|Grass|Layers)\].*"
        r"(已放置|已创建|解析到|完成|草地)"
    )
    err_pattern = re.compile(r"Error:|Fatal error")
    noise_pattern = re.compile(r"google\.com|LogHttp|LogAutomationTest")

    # 单次遍历引擎日志, 同时提取雕刻日志和错误行, 避免两次打开文件
    if os.path.exists(ENGINE_LOG_PATH):
        try:
            with open(ENGINE_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    stripped = strip_engine_ts(line)
                    if len(carve_lines) < 50 and carve_pattern.search(stripped):
                        carve_lines.append(stripped)
                    if len(err_lines) < 10 and err_pattern.search(stripped) and not noise_pattern.search(stripped):
                        err_lines.append(stripped)
                    if len(carve_lines) >= 50 and len(err_lines) >= 10:
                        break
        except Exception:
            pass

        if carve_lines or err_lines:
            add_main_log("")
            add_main_log("[CARVE] ---------- C++ 地形雕刻日志 (提取自引擎日志) ----------")
            for l in carve_lines:
                add_main_log(f"[CARVE] {l}")
            if err_lines:
                add_main_log("")
                add_main_log("[ERROR] ---------- 引擎日志错误行 (前10条, 已滤噪音) ----------")
                for e in err_lines:
                    add_main_log(f"[ERROR] {e}")

    # ========== 步骤5: 构建结果摘要 ==========
    # 5.1 转储统计
    dump_count = 0
    if os.path.exists(main_log_path):
        try:
            with open(main_log_path, "r", encoding="utf-8") as f:
                dump_count = f.read().count("[DUMP]")
        except Exception:
            pass

    summary = []
    summary.append("==================== 构建结果摘要 ====================")
    summary.append(f"场景文件    : {scene_json_path}")
    summary.append(f"场景名称    : {scene_name}")
    summary.append(f"目标关卡    : {target_level}")
    summary.append(f"构建耗时    : {elapsed_total} 秒")
    if timed_out:
        summary.append(f"完成标记    : 构建超时 ({args.timeout_sec} 秒)")
    else:
        summary.append(f"完成标记    : {'BUILD_SCENE_DONE 已出现' if done_marker else '未出现'}")
    summary.append(f"场景转储    : {dump_count} 行 [DUMP] (地形坐标/图层/河流道路折点/资产坐标高度)")
    if carve_lines:
        summary.append(f"地形雕刻    : 河流冲刷 + 道路平整共 {len(carve_lines)} 条, 见主日志 [CARVE] 段")
    if umap_path and os.path.exists(umap_path):
        st = os.stat(umap_path)
        size_mb = round(st.st_size / (1024 * 1024), 2)
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        summary.append(f"UMAP 产物   : {umap_path}")
        summary.append(f"            大小 {size_mb} MB  保存时间 {mtime}")
    else:
        summary.append(f"UMAP 产物   : 未找到 {umap_path}")
    summary.append(f"主日志文件  : {main_log_path}")
    summary.append("            标签速查: [HEADER]构建头 [DUMP]参数转储 [CARVE]雕刻 [ERROR]错误 [SUMMARY]本摘要")
    summary.append("======================================================")

    print()
    for l in summary:
        print(f"{C_MAGENTA}{l}{C_RESET}")

    # 摘要写入主日志
    add_main_log("")
    for l in summary:
        add_main_log(f"[SUMMARY] {l}")

    # 成败判定
    build_ok = done_marker and umap_path and os.path.exists(umap_path)
    if build_ok:
        write_ok("构建成功")
    else:
        write_fail("构建失败, 请检查主日志中的 [ERROR] 段")

    # ========== 步骤6: 历史日志自动清理 ==========
    log_files = sorted(
        SCRIPT_DIR.glob("build_umap_*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    old_logs = log_files[args.keep_logs:]
    if old_logs:
        for ol in old_logs:
            try:
                ol.unlink()
            except OSError:
                pass
        print(f"[清理] 已删除 {len(old_logs)} 份过期构建日志 (保留最近 {args.keep_logs} 份)")

    # ========== 步骤7: 构建成功后自动打开编辑器 (可选) ==========
    if build_ok and args.open_editor:
        write_step(f"打开 UE 编辑器并加载关卡: {target_level}")
        subprocess.Popen(
            [EDITOR_EXE, PROJ, target_level],
            creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
        )
        write_ok("编辑器已启动")

    sys.exit(0 if build_ok else 1)


if __name__ == "__main__":
    main()