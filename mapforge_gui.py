#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# mapforge_gui.py - MapForge 场景构建 GUI 工具
# ============================================================================
# 双击运行，选择 JSON 场景文件，勾选构建选项，一键构建 UE5 umap 关卡。
# 不修改 build_umap.py / build_scene.py 任何逻辑，仅作为图形外壳通过
# subprocess 调用 build_umap.py。
# ============================================================================

import os
import re
import sys
import shutil
import json
import queue
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ---- 确定脚本所在目录，用于定位 build_umap.py ----
# PyInstaller 打包后 sys.executable 指向 exe 自身，__file__ 不可靠
# exe 在 dist/ 子目录下，build_umap.py 在上级目录
if getattr(sys, 'frozen', False):
    _EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    SCRIPT_DIR = _EXE_DIR
    BUILD_UMAP = os.path.join(os.path.dirname(_EXE_DIR), "build_umap.py")
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    BUILD_UMAP = os.path.join(SCRIPT_DIR, "build_umap.py")

# ---- 尝试导入 tkinterdnd2 (拖拽文件支持) ----
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False


# ============================================================================
# 日志标签颜色映射
# ============================================================================
TAG_COLORS = {
    "[OK]":      "#34d399",
    "[INFO]":    "#60a5fa",
    "[WARN]":    "#fbbf24",
    "[ERROR]":   "#f87171",
    "[DUMP]":    "#a78bfa",
    "[BUILD]":   "#60a5fa",
    "[CARVE]":   "#fbbf24",
    "[SUMMARY]": "#f472b6",
    "[HEADER]":  "#9ca3af",
    # 中文字段标签（build_umap.py 使用）
    "[步骤]":    "#60a5fa",
    "[警告]":    "#fbbf24",
    "[失败]":    "#f87171",
}
# 匹配 [ASCII] 或 [中文] 标签，支持中文字符
TAG_PATTERN = re.compile(r'^(\[[A-Z\u4e00-\u9fff]+\])\s*(.*)$')
# 剥离 ANSI 终端转义码（颜色、光标控制等），避免 tkinter Text 控件显示乱码
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')


def _parse_log_line(line):
    """解析日志行，提取标签和内容，返回 (tag, msg) 或 (None, line)。
    会先剥离 ANSI 转义码，避免 tkinter Text 控件显示乱码。"""
    clean = ANSI_ESCAPE.sub('', line).strip()
    m = TAG_PATTERN.match(clean)
    if m:
        return m.group(1), m.group(2)
    return None, clean


def _find_python_exe():
    """查找可用的 Python 解释器路径。
    PyInstaller 打包后 sys.executable 指向 exe 自身，
    sys._base_executable 也指向 exe（PyInstaller 行为），
    因此必须通过系统 PATH 或 sys.exec_prefix 查找真正的 Python。
    """
    if getattr(sys, 'frozen', False):
        # 方案1: 系统 PATH 中的 python / python3 / py
        for name in ('python', 'python3', 'py'):
            path = shutil.which(name)
            if path and os.path.exists(path):
                return path
        # 方案2: 从 sys.exec_prefix 推测（Conda 环境）
        prefix = sys.exec_prefix
        if prefix:
            candidates = [
                os.path.join(prefix, 'python.exe'),
                os.path.join(os.path.dirname(prefix), 'python.exe'),
            ]
            for p in candidates:
                if os.path.exists(p):
                    return p
    return sys.executable


# ============================================================================
# 主窗口类
# ============================================================================
class MapForgeGUI:
    """MapForge 场景构建 GUI 主窗口"""

    # ---- 窗口配置 ----
    WINDOW_TITLE = "MapForge — 场景构建工具"
    WINDOW_WIDTH = 600
    WINDOW_HEIGHT = 520  # 折叠日志时的高度
    WINDOW_HEIGHT_EXPANDED = 720  # 展开日志时的高度

    # ---- 颜色配置（深色主题） ----
    COLOR_BG = "#12121a"
    COLOR_BG_MUTED = "#1a1a2e"
    COLOR_TEXT = "#e0e0e8"
    COLOR_TEXT_MUTED = "#8888a0"
    COLOR_BORDER = "#2a2a3e"
    COLOR_BRAND = "#a78bfa"
    COLOR_BRAND_SURFACE = "#1e1a2e"
    COLOR_BRAND_TEXT = "#ffffff"
    COLOR_SUCCESS = "#34d399"
    COLOR_SUCCESS_SURFACE = "#0a2e1a"
    COLOR_SUCCESS_BORDER = "#1a4d33"
    COLOR_ERROR = "#f87171"
    COLOR_ERROR_SURFACE = "#1a0a0a"
    COLOR_ERROR_BORDER = "#4d1a1a"
    COLOR_LOG_BG = "#080812"
    COLOR_LOG_TEXT = "#c0c0d0"

    def __init__(self):
        self._build_process = None
        self._log_queue = queue.Queue()
        self._build_running = False
        self._log_expanded = True
        self._result_frame = None
        self._json_path = None

        self._build_window()
        self._build_ui()
        self._poll_log_queue()

    # ========================================================================
    # 窗口创建
    # ========================================================================
    def _build_window(self):
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
        self.root.title(self.WINDOW_TITLE)
        self.root.configure(bg=self.COLOR_BG)
        self.root.minsize(500, 400)
        self.root.resizable(True, True)

        # 居中显示
        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws - self.WINDOW_WIDTH) // 2
        y = (hs - self.WINDOW_HEIGHT) // 2
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")

        # Windows 10/11 下将系统标题栏切换为深色模式
        if sys.platform == "win32":
            try:
                import ctypes
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                value = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ========================================================================
    # UI 构建
    # ========================================================================
    def _build_ui(self):
        self._main_frame = tk.Frame(self.root, bg=self.COLOR_BG, padx=16, pady=12)
        self._main_frame.pack(fill=tk.BOTH, expand=True)

        # ttk 深色样式（滚动条 / 进度条）
        # clam 主题在 Windows 下对滚动条颜色配置不生效，改用 alt 主题
        style = ttk.Style()
        style.theme_use("alt")
        style.configure("Vertical.TScrollbar",
                        background=self.COLOR_BG_MUTED,
                        troughcolor=self.COLOR_LOG_BG,
                        bordercolor=self.COLOR_LOG_BG,
                        arrowcolor=self.COLOR_TEXT_MUTED)
        style.map("Vertical.TScrollbar",
                  background=[("active", self.COLOR_BG_MUTED),
                              ("!active", self.COLOR_BG_MUTED)])
        style.configure("TProgressbar",
                        background=self.COLOR_BRAND,
                        troughcolor=self.COLOR_BG_MUTED,
                        bordercolor=self.COLOR_BG_MUTED)

        # ---- 标题栏 ----
        title_frame = tk.Frame(self._main_frame, bg=self.COLOR_BG_MUTED, padx=12, pady=8)
        title_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(title_frame, text="M", bg=self.COLOR_BRAND, fg=self.COLOR_BRAND_TEXT,
                 font=("Segoe UI", 10, "bold"), width=3, height=1).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(title_frame, text="MapForge — 场景构建工具",
                 bg=self.COLOR_BG_MUTED, fg=self.COLOR_TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)

        # ---- 文件选择 ----
        self._build_file_section()

        # ---- 构建选项 ----
        self._build_options_section()

        # ---- 按钮 ----
        self._build_button_section()

        # ---- 进度条 ----
        self._build_progress_section()

        # ---- 日志区 ----
        self._build_log_section()

    # ========================================================================
    # 文件选择区域
    # ========================================================================
    def _build_file_section(self):
        tk.Label(self._main_frame, text="JSON 场景文件",
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 4))

        file_frame = tk.Frame(self._main_frame, bg=self.COLOR_BG)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        drop_hint = "拖拽 JSON 文件到此处" if HAS_DND else "点击浏览选择 JSON 文件"

        self._drop_frame = tk.Frame(file_frame, bg=self.COLOR_BG,
                                     highlightbackground=self.COLOR_BORDER,
                                     highlightthickness=2, relief="ridge", bd=0)
        self._drop_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)

        self._file_label = tk.Label(self._drop_frame, text=drop_hint,
                                     bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                                     font=("Segoe UI", 10))
        self._file_label.pack(expand=True, fill=tk.BOTH, padx=10)

        # 拖拽支持
        if HAS_DND:
            self._drop_frame.drop_target_register(DND_FILES)
            self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            self._file_label.drop_target_register(DND_FILES)
            self._file_label.dnd_bind("<<Drop>>", self._on_drop)

        # 浏览按钮：外层 Frame 用描边色填充，内层按钮 padx/pady=1 留出描边
        # （Windows 下 tk.Button 的 highlightthickness 环不渲染，故用 Frame 模拟描边）
        browse_border = tk.Frame(file_frame, bg=self.COLOR_BORDER)
        browse_border.pack(side=tk.RIGHT, padx=(8, 0))
        browse_btn = tk.Button(browse_border, text="浏览...", bg=self.COLOR_BG,
                                fg=self.COLOR_TEXT, font=("Segoe UI", 10),
                                relief="flat", bd=0, padx=12,
                                activebackground=self.COLOR_BG_MUTED,
                                activeforeground=self.COLOR_TEXT,
                                command=self._on_browse)
        browse_btn.pack(padx=1, pady=1)

    # ========================================================================
    # 构建选项区域
    # ========================================================================
    def _build_options_section(self):
        tk.Label(self._main_frame, text="构建选项",
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 4))

        opts_frame = tk.Frame(self._main_frame, bg=self.COLOR_BG)
        opts_frame.pack(fill=tk.X, pady=(0, 10))

        self._force_kill_var = tk.BooleanVar(value=True)
        ck1 = tk.Checkbutton(opts_frame, text="自动关闭 UE 编辑器进程 (--force-kill)",
                              variable=self._force_kill_var,
                              bg=self.COLOR_BG, fg=self.COLOR_TEXT,
                              font=("Segoe UI", 10), activebackground=self.COLOR_BG,
                              selectcolor=self.COLOR_BRAND, anchor=tk.W)
        ck1.pack(anchor=tk.W, pady=(0, 4))

        self._open_editor_var = tk.BooleanVar(value=False)
        ck2 = tk.Checkbutton(opts_frame, text="构建完成后自动打开 UE 编辑器加载关卡",
                              variable=self._open_editor_var,
                              bg=self.COLOR_BG, fg=self.COLOR_TEXT,
                              font=("Segoe UI", 10), activebackground=self.COLOR_BG,
                              selectcolor=self.COLOR_BRAND, anchor=tk.W)
        ck2.pack(anchor=tk.W)

    # ========================================================================
    # 按钮区域
    # ========================================================================
    def _build_button_section(self):
        btn_frame = tk.Frame(self._main_frame, bg=self.COLOR_BG)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        # 开始构建按钮：品牌色描边（外层 Frame 2px），透明背景 + 品牌色文字
        build_border = tk.Frame(btn_frame, bg=self.COLOR_BRAND)
        build_border.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._build_btn = tk.Button(build_border, text="开始构建",
                                     bg=self.COLOR_BG, fg=self.COLOR_BRAND,
                                     font=("Segoe UI", 11, "bold"),
                                     relief="flat", bd=0, padx=20, pady=6,
                                     activebackground=self.COLOR_BRAND_SURFACE,
                                     activeforeground=self.COLOR_BRAND,
                                     command=self._on_build)
        self._build_btn.pack(fill=tk.X, padx=2, pady=2)

        # 取消按钮：普通描边（外层 Frame 1px）
        cancel_border = tk.Frame(btn_frame, bg=self.COLOR_BORDER)
        cancel_border.pack(side=tk.RIGHT, padx=(8, 0))
        self._cancel_btn = tk.Button(cancel_border, text="取消",
                                      bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                                      font=("Segoe UI", 10),
                                      relief="flat", bd=0, padx=16, pady=6,
                                      activebackground=self.COLOR_BG_MUTED,
                                      activeforeground=self.COLOR_TEXT_MUTED,
                                      command=self._on_cancel,
                                      state=tk.DISABLED)
        self._cancel_btn.pack(padx=1, pady=1)

    # ========================================================================
    # 进度条区域
    # ========================================================================
    def _build_progress_section(self):
        self._progress_frame = tk.Frame(self._main_frame, bg=self.COLOR_BG)
        # 初始隐藏进度条
        self._progress_bar = ttk.Progressbar(self._progress_frame, mode="indeterminate",
                                              length=100, style="TProgressbar")
        self._progress_bar.pack(fill=tk.X, pady=(0, 2))

        self._status_var = tk.StringVar(value="就绪")
        tk.Label(self._progress_frame, textvariable=self._status_var,
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 font=("Segoe UI", 9), anchor=tk.W).pack(fill=tk.X)

    # ========================================================================
    # 日志区域（可折叠）
    # ========================================================================
    def _build_log_section(self):
        # 日志折叠头部
        log_header = tk.Frame(self._main_frame, bg=self.COLOR_BG, cursor="hand2")
        log_header.pack(fill=tk.X, pady=(8, 0))
        log_header.bind("<Button-1>", self._toggle_log)

        self._log_arrow_var = tk.StringVar(value="▶")
        tk.Label(log_header, textvariable=self._log_arrow_var,
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 font=("Segoe UI", 9), width=2, anchor=tk.W).pack(side=tk.LEFT)
        # 绑定折叠事件到箭头标签
        for child in log_header.winfo_children():
            child.bind("<Button-1>", self._toggle_log)

        self._log_count_var = tk.StringVar(value="")
        tk.Label(log_header, text="显示详细日志",
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Label(log_header, textvariable=self._log_count_var,
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)

        # 日志文本区
        self._log_body = tk.Frame(self._main_frame, bg=self.COLOR_LOG_BG)
        self._log_body.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self._log_text = tk.Text(self._log_body, bg=self.COLOR_LOG_BG, fg=self.COLOR_LOG_TEXT,
                                  font=("Consolas", 9), wrap=tk.WORD, bd=0,
                                  padx=8, pady=6, state=tk.DISABLED,
                                  relief=tk.FLAT, highlightthickness=0, cursor="arrow")

        # 配置颜色标签
        for tag_name, color in TAG_COLORS.items():
            self._log_text.tag_configure(tag_name, foreground=color, font=("Consolas", 9, "bold"))
        self._log_text.tag_configure("normal", foreground=self.COLOR_LOG_TEXT)

        # 滚动条（ttk + clam 基础样式 Vertical.TScrollbar）
        # 实测：滚动条 master 为 Text 控件时 clam 深色样式不生效，
        # 必须与 Text 同级挂在 _log_body 下，并先 pack 占住右侧空间
        self._log_scrollbar = ttk.Scrollbar(self._log_body, orient=tk.VERTICAL,
                                             command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=self._log_scrollbar.set)
        self._log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._log_text.bind("<MouseWheel>", self._on_log_mousewheel)

        self._log_line_count = 0

    # ========================================================================
    # 文件选择回调
    # ========================================================================
    def _on_browse(self):
        path = filedialog.askopenfilename(
            title="选择场景 JSON 文件",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialdir=SCRIPT_DIR
        )
        if path:
            self._set_json_path(path)

    def _on_drop(self, event):
        """拖拽文件回调，解析 Windows 拖拽格式"""
        raw = event.data
        if raw:
            # Windows 拖拽格式: {path1} {path2} ... 或 {path}
            path = raw.strip("{}").strip()
            # 处理可能的多个文件，取第一个
            path = path.split("} {")[0].strip()
            if path.lower().endswith(".json"):
                self._set_json_path(path)
            else:
                messagebox.showwarning("文件类型错误", "请拖拽 .json 文件")

    def _set_json_path(self, path):
        """设置选中的 JSON 文件路径"""
        path = os.path.abspath(path)
        self._json_path = path
        fname = os.path.basename(path)
        self._file_label.configure(text=fname, fg=self.COLOR_BRAND,
                                    font=("Segoe UI", 10, "bold"))

    # ========================================================================
    # 构建控制
    # ========================================================================
    def _on_build(self):
        """开始构建"""
        if self._build_running:
            return

        if not self._json_path:
            messagebox.showwarning("未选择文件", "请先选择或拖拽一个 JSON 场景文件")
            return

        if not os.path.exists(self._json_path):
            messagebox.showerror("文件不存在", f"文件不存在:\n{self._json_path}")
            return

        # 快速校验 JSON 语法
        try:
            with open(self._json_path, "r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            messagebox.showerror("JSON 语法错误", f"文件不是合法的 JSON:\n{e}")
            return

        if not os.path.exists(BUILD_UMAP):
            messagebox.showerror("缺少依赖", f"未找到 build_umap.py:\n{BUILD_UMAP}")
            return

        self._build_running = True
        self._build_btn.configure(state=tk.DISABLED, text="构建中...",
                                   fg=self.COLOR_TEXT_MUTED)
        self._cancel_btn.configure(state=tk.NORMAL)

        # 显示进度条
        self._progress_frame.pack(fill=tk.X, pady=(0, 8), before=self._log_body)
        self._progress_bar.start(10)
        self._status_var.set("正在启动...")

        # 清空日志
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)
        self._log_line_count = 0
        self._log_count_var.set("")
        self._log_expanded = True
        self._log_arrow_var.set("▶")

        # 清除旧结果
        if self._result_frame:
            self._result_frame.destroy()
            self._result_frame = None

        # 构建命令行参数
        # 注意：不能用 sys.executable，PyInstaller 打包后它指向 exe 自身
        # 必须用 _find_python_exe() 找到真正的 Python 解释器
        python_exe = _find_python_exe()
        cmd = [python_exe, BUILD_UMAP, "--scene-json", self._json_path]
        if self._force_kill_var.get():
            cmd.append("--force-kill")
        if self._open_editor_var.get():
            cmd.append("--open-editor")

        self._append_log_tag("[INFO]", f"执行命令: {' '.join(cmd)}")

        # 后台线程启动构建
        thread = threading.Thread(target=self._run_build, args=(cmd,), daemon=True)
        thread.start()

    def _on_cancel(self):
        """取消构建"""
        # 先取到局部变量，避免后台线程异步设置 self._build_process 产生竞态
        proc = self._build_process
        if proc and proc.poll() is None:
            proc.terminate()
            self._status_var.set("已取消")
            self._append_log_tag("[WARN]", "构建已取消")
        self._reset_build_ui()

    # ========================================================================
    # 构建子进程
    # ========================================================================
    def _run_build(self, cmd):
        """在后台线程中运行 build_umap.py"""
        try:
            # 必须设置 PYTHONIOENCODING=utf-8，否则 Windows 中文系统下
            # 子进程 stdout 默认用 GBK 编码输出，GUI 以 UTF-8 解码会产生乱码
            build_env = os.environ.copy()
            build_env["PYTHONIOENCODING"] = "utf-8"

            self._build_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=SCRIPT_DIR,
                env=build_env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            for line in iter(self._build_process.stdout.readline, ""):
                self._log_queue.put(line.rstrip())

            self._build_process.stdout.close()
            returncode = self._build_process.wait()
            self._log_queue.put(("__EXIT__", returncode))

        except Exception as e:
            self._log_queue.put(("__ERROR__", str(e)))

    def _poll_log_queue(self):
        """定时轮询日志队列，更新 UI"""
        try:
            while True:
                item = self._log_queue.get_nowait()

                if isinstance(item, tuple):
                    if item[0] == "__EXIT__":
                        returncode = item[1]
                        self._on_build_finished(returncode)
                    elif item[0] == "__ERROR__":
                        self._append_log_tag("[ERROR]", f"构建异常: {item[1]}")
                        self._on_build_finished(-1)
                else:
                    self._process_log_line(item)

        except queue.Empty:
            pass

        # 每 100ms 轮询一次
        self.root.after(100, self._poll_log_queue)

    def _process_log_line(self, line):
        """处理单行日志输出"""
        tag, msg = _parse_log_line(line)
        if tag:
            self._append_log_tag(tag, msg)
        else:
            self._append_log_line(msg)

        # 更新进度状态（使用剥离 ANSI 后的纯文本匹配）
        if "BUILD_SCENE_DONE" in msg:
            self._status_var.set("检测到 BUILD_SCENE_DONE，等待引擎退出...")
        elif "启动 UE5 无头模式" in msg:
            self._status_var.set("UE 引擎启动中...")
        elif "JSON 语法合法" in msg:
            self._status_var.set("JSON 校验通过...")
        elif "资产路径预校验" in msg:
            self._status_var.set("校验资产路径...")
        elif "监控构建进程" in msg:
            self._status_var.set("构建中...")

    def _on_build_finished(self, returncode):
        """构建完成回调"""
        self._progress_bar.stop()
        self._progress_bar.pack_forget()

        self._build_running = False
        self._build_btn.configure(state=tk.NORMAL, text="开始构建",
                                   fg=self.COLOR_BRAND)
        self._cancel_btn.configure(state=tk.DISABLED)

        if returncode == 0:
            self._status_var.set("构建成功")
            self._show_result_success()
        else:
            self._status_var.set(f"构建失败 (退出码: {returncode})")
            self._show_result_failure()

        self._build_process = None

    def _reset_build_ui(self):
        """重置构建 UI 状态"""
        self._build_running = False
        self._progress_bar.stop()
        self._progress_bar.pack_forget()
        self._progress_frame.pack_forget()
        self._build_btn.configure(state=tk.NORMAL, text="开始构建",
                                   fg=self.COLOR_BRAND)
        self._cancel_btn.configure(state=tk.DISABLED)
        self._build_process = None

    # ========================================================================
    # 结果展示
    # ========================================================================
    def _show_result_success(self):
        """显示构建成功结果"""
        log_content = self._log_text.get("1.0", tk.END)
        # 保险起见再次剥离 ANSI 转义码，确保关键词匹配不受干扰
        clean_content = ANSI_ESCAPE.sub('', log_content)

        # 从日志中提取 UMAP 路径、大小和构建耗时
        # build_umap.py 的 SUMMARY 输出格式：
        #   [SUMMARY] UMAP 产物   : /path/to/file.umap
        #   [SUMMARY]             大小 123.45 MB  保存时间 ...
        #   [SUMMARY] 构建耗时    : 12.34 秒
        umap_path = ""
        umap_size = ""
        build_time = ""
        for line in clean_content.split("\n"):
            if "UMAP 产物" in line:
                # 提取冒号后的路径（去除可能的尾部空格）
                if ":" in line:
                    umap_path = line.split(":", 1)[-1].strip()
                else:
                    umap_path = line.split("UMAP 产物")[-1].strip()
            if "大小" in line and "MB" in line:
                # 提取 "大小 xxx MB" 中的数字和单位
                m = re.search(r'大小\s+([\d.]+)\s*MB', line)
                if m:
                    umap_size = f"{m.group(1)} MB"
            if "构建耗时" in line:
                # 提取冒号后的耗时信息
                if ":" in line:
                    build_time = line.split(":", 1)[-1].strip()
                else:
                    build_time = line.split("构建耗时")[-1].strip()

        self._build_result_frame(True, umap_path, umap_size, build_time)
        messagebox.showinfo("构建完成", f"构建成功!\n\nUMAP: {umap_path}\n大小: {umap_size}\n耗时: {build_time}")

    def _show_result_failure(self):
        """显示构建失败结果"""
        self._build_result_frame(False)
        messagebox.showerror("构建失败", "构建失败，请查看日志中的 [ERROR] 段了解详情")

    def _build_result_frame(self, success, umap_path="", umap_size="", build_time=""):
        """构建结果展示面板"""
        if self._result_frame:
            self._result_frame.destroy()

        bg_color = self.COLOR_SUCCESS_SURFACE if success else self.COLOR_ERROR_SURFACE
        border_color = self.COLOR_SUCCESS_BORDER if success else self.COLOR_ERROR_BORDER
        text_color = self.COLOR_SUCCESS if success else self.COLOR_ERROR
        icon = "✅" if success else "❌"
        title = "构建成功" if success else "构建失败"

        self._result_frame = tk.Frame(self._main_frame, bg=bg_color,
                                       highlightbackground=border_color,
                                       highlightthickness=1, bd=0, padx=10, pady=8)
        self._result_frame.pack(fill=tk.X, pady=(8, 0), before=self._log_body)

        tk.Label(self._result_frame, text=f"{icon} {title}",
                 bg=bg_color, fg=text_color,
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

        if success:
            rows = [
                ("UMAP 产物", umap_path),
                ("文件大小", umap_size),
                ("构建耗时", build_time),
            ]
            for label, value in rows:
                if not value:
                    continue
                row = tk.Frame(self._result_frame, bg=bg_color)
                row.pack(fill=tk.X, pady=1)
                tk.Label(row, text=label, bg=bg_color, fg=self.COLOR_TEXT_MUTED,
                         font=("Segoe UI", 9), width=10, anchor=tk.W).pack(side=tk.LEFT)
                tk.Label(row, text=value, bg=bg_color, fg=self.COLOR_TEXT,
                         font=("Segoe UI", 9, "bold"), anchor=tk.W).pack(side=tk.LEFT)

    # ========================================================================
    # 日志操作
    # ========================================================================
    def _append_log_line(self, line):
        """追加普通日志行"""
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, line + "\n", "normal")
        self._log_text.configure(state=tk.DISABLED)
        self._log_text.see(tk.END)
        self._log_line_count += 1
        self._update_log_count()

    def _append_log_tag(self, tag, msg):
        """追加带标签的日志行"""
        self._log_text.configure(state=tk.NORMAL)
        if tag in TAG_COLORS:
            self._log_text.insert(tk.END, tag + " ", tag)
        else:
            self._log_text.insert(tk.END, tag + " ")
        self._log_text.insert(tk.END, msg + "\n")
        self._log_text.configure(state=tk.DISABLED)
        self._log_text.see(tk.END)
        self._log_line_count += 1
        self._update_log_count()

    def _update_log_count(self):
        """更新日志条数显示"""
        self._log_count_var.set(f"({self._log_line_count} 条)")

    def _toggle_log(self, event=None):
        """折叠/展开日志区"""
        if self._log_expanded:
            self._log_text.pack_forget()
            self._log_scrollbar.pack_forget()
            self._log_arrow_var.set("▸")
            self._log_expanded = False
        else:
            # 展开顺序须与构建时一致：先滚动条占右侧，再文本区填充剩余
            self._log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self._log_arrow_var.set("▶")
            self._log_expanded = True

    def _on_log_mousewheel(self, event):
        """鼠标滚轮滚动日志"""
        self._log_text.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ========================================================================
    # 窗口关闭
    # ========================================================================
    def _on_close(self):
        if self._build_running:
            if messagebox.askyesno("确认退出", "构建正在进行中，退出将中止构建。确定退出吗？"):
                # 先取到局部变量，避免后台线程异步设置 self._build_process 产生竞态
                proc = self._build_process
                if proc and proc.poll() is None:
                    proc.terminate()
                self.root.destroy()
        else:
            self.root.destroy()

    # ========================================================================
    # 启动
    # ========================================================================
    def run(self):
        self.root.mainloop()


# ============================================================================
# 入口
# ============================================================================
if __name__ == "__main__":
    app = MapForgeGUI()
    app.run()