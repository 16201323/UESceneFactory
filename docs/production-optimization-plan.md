# MapForge 生产级优化方案

> **执行方式:** 按任务顺序 (Task 1 → Task 7) 逐项实施, 每个任务完成后验证通过再进入下一个。

**目标:** 将 MapForge 从开发原型优化为可出售的生产级软件, 消除硬编码路径、补全崩溃日志、修复打包脚本、锁定依赖、优化性能瓶颈。

**架构:** 7 项独立优化, 按依赖关系排序: 配置去硬编码(基础) → 崩溃日志(调试基础) → 打包脚本 → UPX排除 → 依赖锁定 → 异步解析 → 经验库索引。

**技术栈:** Python 3.14 / PyQt6 6.11.0 / QScintilla 2.14.1 / openai 3.8.0 / PyYAML 6.0.3 / PyInstaller 6.22.2 / SQLite3 FTS5

---

## 文件结构总览

| 文件 | 涉及任务 | 职责 |
|------|---------|------|
| `mapforge_app.py` | Task 1, 2, 6 | GUI 主程序: 配置/日志/异步解析 |
| `build_umap.py` | Task 1 | 独立 CLI: 路径解析 |
| `build_scene.py` | Task 1 | UE5 内脚本: 日志路径/默认场景 |
| `diagnose_landscape.py` | Task 1 | 诊断脚本: 日志路径 |
| `build_exe.bat` | Task 3 | 打包脚本: chcp/spec 委托 |
| `MapForge.spec` | Task 4 | PyInstaller 配置: UPX 排除 |
| `requirements.txt` | Task 5 | 依赖锁定 (新建) |
| `ai/experience_bank.py` | Task 7 | 经验库: FTS5 索引 |
| `ai/retriever.py` | Task 7 | 检索器: 候选预过滤 |
| `tests/test_phase07_bank.py` | Task 7 | 经验库测试: 新增 FTS5 用例 |

---

## Task 1: Item 6 — 配置去硬编码（7 处用户专属路径）

**问题:** 代码中散布 7 处用户专属绝对路径 (`D:/Program Files/...`、`D:/code/...`、`c:/Users/25868/...`), 换台电脑即失效。

**文件:**
- Modify: `mapforge_app.py:85-93` (DEFAULT_CONFIG)
- Modify: `mapforge_app.py:184-187` (autodetect_project_paths roots)
- Modify: `build_umap.py:40-45` (5 个硬编码常量)
- Modify: `build_scene.py:31` (LOG_PATH 默认值)
- Modify: `build_scene.py:872` (DEFAULT_SCENE)
- Modify: `diagnose_landscape.py:3` (log_path 默认值)

### 步骤

- [ ] **Step 1: 修改 mapforge_app.py DEFAULT_CONFIG — 去掉用户专属路径**

将 `mapforge_app.py:85-93` 的 DEFAULT_CONFIG 改为:

```python
DEFAULT_CONFIG = {
    # 引擎/项目路径: 空串表示未配置, 首次启动时自动探测
    "ue5_path": "",
    "project_path": "",
    # 阿里云 AI API 默认配置
    "llm_profile": "openai",
    "llm_base_url": "https://token-plan.cn-beijing.maoliyun.com/compatible-mode/v1",
    "llm_api_key": "${ALIYUN_APIKEY}",
    "llm_model": "glm-5.2",
}
```

- [ ] **Step 2: 修改 mapforge_app.py autodetect_project_paths — 去掉 D:/code/UEEnvironment**

将 `mapforge_app.py:184-187` 的 roots 列表改为:

```python
    roots = [
        # 从用户主目录推导, 不硬编码特定用户路径
        os.path.join(home, "Desktop", "UE5"),
    ]
```

- [ ] **Step 3: 修改 build_umap.py — 从配置文件解析路径, 不再硬编码**

将 `build_umap.py:40-45` 替换为:

```python
# ---- 路径配置: 从 ~/.mapforge_config.json 读取 (与 GUI 共用), 不再硬编码 ----
def _resolve_paths():
    """从配置文件或环境变量解析 UE5 路径。

    优先级: 环境变量 > ~/.mapforge_config.json > 空串(调用方报错)。
    与 GUI (mapforge_app.py) 共用同一份配置, 用户在 GUI 设置一次即可。
    """
    ue5_cmd = ""
    project = ""
    # 1. 尝试从配置文件读取
    _config_path = os.path.join(os.path.expanduser("~"), ".mapforge_config.json")
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
```

- [ ] **Step 4: 修改 build_scene.py LOG_PATH — 使用临时目录, 不硬编码用户路径**

将 `build_scene.py:31` 改为:

```python
# 日志路径优先从环境变量读取 (GUI 工具会设置), 无则用系统临时目录
LOG_PATH = os.environ.get("MAPFORGE_LOG", os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "mapforge_build_scene.log"))
```

- [ ] **Step 5: 修改 build_scene.py DEFAULT_SCENE — 基于脚本目录推导**

将 `build_scene.py:872` 改为:

```python
    # 默认场景文件: 与 build_scene.py 同目录下的 farming_village.yaml, 不硬编码用户路径
    DEFAULT_SCENE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "farming_village.yaml")
```

- [ ] **Step 6: 修改 diagnose_landscape.py log_path — 使用临时目录**

将 `diagnose_landscape.py:3` 改为:

```python
log_path = os.environ.get("MAPFORGE_LOG", os.path.join(
    os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
    "mapforge_diagnose_landscape.log"))
```

- [ ] **Step 7: 验证**

```bash
# 确认无用户专属路径残留
python -c "import mapforge_app; print('DEFAULT_CONFIG:', mapforge_app.DEFAULT_CONFIG)"
# 编译检查
python -m py_compile mapforge_app.py build_umap.py build_scene.py diagnose_landscape.py
# 运行已有测试
python -m pytest tests/ -v
```

预期: DEFAULT_CONFIG 的 ue5_path/project_path 为空串; 编译通过; 31 项测试全通过。

---

## Task 2: Item 7 — 崩溃捕获 + 持久化日志

**问题:** 日志仅输出到控制台 (console=False 时全部丢失); 无 sys.excepthook, 未捕获异常静默崩溃; Qt 内部警告无记录。

**文件:**
- Modify: `mapforge_app.py:34-40` (logging 初始化区)

### 步骤

- [ ] **Step 1: 编写持久化日志 + 崩溃捕获测试**

创建 `tests/test_logging_setup.py`:

```python
"""测试: 持久化日志文件创建 + 崩溃捕获钩子安装。"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_log_dir_created():
    """验证日志目录在 APPDATA 下自动创建。"""
    # 模拟: 调用 _setup_logging 后应存在日志文件
    import mapforge_app
    # 日志目录应在 %APPDATA%/MapForge/logs/ 或 ~/.mapforge/logs/
    log_dir = getattr(mapforge_app, '_LOG_DIR', None)
    assert log_dir is not None, '日志目录未设置'
    assert os.path.isdir(log_dir), f'日志目录不存在: {log_dir}'
    # 应至少有一个日志文件
    logs = [f for f in os.listdir(log_dir) if f.endswith('.log')]
    assert len(logs) > 0, f'日志目录无 .log 文件: {log_dir}'
    print(f'日志目录验证通过: {log_dir}, 文件: {logs}')

def test_excepthook_installed():
    """验证 sys.excepthook 已被替换为自定义钩子。"""
    import mapforge_app
    assert sys.excepthook is not sys.__excepthook__, 'sys.excepthook 未被替换'
    print('崩溃捕获钩子验证通过')

if __name__ == '__main__':
    test_log_dir_created()
    test_excepthook_installed()
    print('=== 日志系统测试通过 ===')
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_logging_setup.py -v
```

预期: FAIL (_LOG_DIR 未定义 / excepthook 未替换)。

- [ ] **Step 3: 实现 _setup_logging 函数**

在 `mapforge_app.py` 的 `logging.basicConfig` 处 (约 35-40 行), 替换为:

```python
# 模块级日志器: 统一记录异常与诊断信息, 替代裸 except: pass
logger = logging.getLogger("mapforge")

def _setup_logging():
    """初始化持久化日志: RotatingFileHandler 写入用户目录 + 安装崩溃捕获钩子。

    日志路径: Windows %APPDATA%/MapForge/logs/, 其他平台 ~/.mapforge/logs/
    崩溃捕获: sys.excepthook 记录未捕获异常到日志文件 (console=False 时不可见)
    Qt 消息: qInstallMessageHandler 记录 Qt 内部警告/错误
    """
    import logging.handlers
    from logging.handlers import RotatingFileHandler

    # 1. 确定日志目录
    if sys.platform == "win32":
        _appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        log_dir = os.path.join(_appdata, "MapForge", "logs")
    else:
        log_dir = os.path.join(os.path.expanduser("~"), ".mapforge", "logs")
    os.makedirs(log_dir, exist_ok=True)
    # 暴露给测试
    globals()["_LOG_DIR"] = log_dir

    # 2. RotatingFileHandler: 单文件 5MB, 保留 3 份备份, UTF-8 编码
    _file_handler = RotatingFileHandler(
        os.path.join(log_dir, "mapforge.log"),
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _file_handler.setLevel(logging.INFO)
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

    # 3. 同时保留控制台输出 (开发调试用)
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))

    logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])

    # 4. 安装 sys.excepthook: 未捕获异常写入日志 (console=False 时尤为重要)
    def _excepthook(exc_type, exc_value, exc_tb):
        logger.critical("未捕获的异常", exc_info=(exc_type, exc_value, exc_tb))
        # 同时调用默认钩子 (打印到 stderr, 供开发调试)
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = _excepthook

    # 5. 安装 Qt 消息处理器: 捕获 Qt 内部警告/错误到日志
    try:
        from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        def _qt_msg_handler(msg_type, context, message):
            level = logging.INFO
            if msg_type == QtMsgType.QtWarningMsg:
                level = logging.WARNING
            elif msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                level = logging.ERROR
            logger.log(level, "Qt: %s", message)
        qInstallMessageHandler(_qt_msg_handler)
    except Exception as e:
        logger.warning("安装 Qt 消息处理器失败: %s", e)

_setup_logging()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python -m pytest tests/test_logging_setup.py -v
```

预期: PASS。

- [ ] **Step 5: 编译检查 + 全量测试**

```bash
python -m py_compile mapforge_app.py
python -m pytest tests/ -v
```

预期: 全部通过 (31 + 2 = 33 项)。

---

## Task 3: Item 11 — 修复 build_exe.bat

**问题:** (1) `chcp 65001` 违反 AGENTS.md 1.2 规范 (应 936); (2) `cd /d "c:\Users\25868\..."` 硬编码用户路径; (3) `del MapForge.spec` 删除了正确的配置文件; (4) 裸 `pyinstaller --onefile` CLI 缺少 datas/hiddenimports, 产出残缺 exe。

**文件:**
- Rewrite: `build_exe.bat` (必须 GBK + CRLF 编码, 按 AGENTS.md 1.5)

### 步骤

- [ ] **Step 1: 用 Python 脚本以 GBK 编码重写 build_exe.bat**

执行以下 Python 命令 (Write 工具默认 UTF-8, 必须用脚本转换):

```python
content = r'''@echo off
chcp 936 >nul 2>&1
echo ============================================================
echo  MapForge - 打包构建脚本
echo  将 mapforge_app.py + build_scene.py 打包为 MapForge.exe
echo ============================================================
echo.

REM 使用脚本自身所在目录, 不硬编码用户路径
cd /d "%~dp0"

echo [1/2] 清理旧的构建产物...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [2/2] 开始 PyInstaller 打包 (使用 MapForge.spec 配置)...
pyinstaller MapForge.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [错误] 打包失败! 错误码见上
    pause
    exit /b 1
)

echo.
echo 打包完成! 输出文件: dist\MapForge.exe
dir "dist\MapForge.exe"
echo.
echo 可以将 dist\MapForge.exe 复制到任意位置使用
echo.
pause
'''
# 统一 CRLF + GBK 编码 (按 AGENTS.md 1.5 规范)
content = content.replace('\r\n', '\n').replace('\n', '\r\n')
data = content.encode('gbk')
open('build_exe.bat', 'wb').write(data)
```

关键变更:
- `chcp 936` 替代 `chcp 65001` (AGENTS.md 1.2)
- `cd /d "%~dp0"` 替代硬编码路径 (脚本自身目录)
- 删除 `if exist "MapForge.spec" del /q "MapForge.spec"` (不再删除 spec)
- `pyinstaller MapForge.spec --noconfirm` 替代裸 CLI (使用完整配置)
- `if errorlevel 1` 替代 `if %ERRORLEVEL% NEQ 0` (AGENTS.md 2.3 块内规则)

- [ ] **Step 2: 验证编码**

```bash
python -c "data=open('build_exe.bat','rb').read(); print('BOM:', data[:3]==b'\\xef\\xbb\\xbf'); print('GBK:', data.decode('gbk')[:50])"
```

预期: BOM: False; GBK 可正常解码。

- [ ] **Step 3: 验证打包 (执行 build_exe.bat)**

```bash
.\build_exe.bat
```

预期: dist\MapForge.exe 生成成功, 大小合理 (>50MB, 包含 PyQt6 + QScintilla)。

---

## Task 4: Item 12 — UPX 排除列表

**问题:** `MapForge.spec` 中 `upx_exclude=[]`, UPX 压缩 Qt/Python DLL 会导致运行时崩溃 (Qt DLL 压缩后加载失败, Python DLL 压缩后 import 异常)。

**文件:**
- Modify: `MapForge.spec:55-56`

### 步骤

- [ ] **Step 1: 修改 MapForge.spec upx_exclude**

将 `MapForge.spec:55-56` 的:

```python
    upx=True,
    upx_exclude=[],
```

改为:

```python
    upx=True,
    # UPX 排除: Qt/Python 核心 DLL 压缩后会导致运行时崩溃, 必须排除
    upx_exclude=[
        'Qt6*.dll',          # Qt6 核心库: 压缩后信号槽/插件加载失败
        'Qt6*.pyd',          # Qt6 Python 绑定
        'PyQt6*.pyd',        # PyQt6 模块
        'sip*.pyd',          # SIP 绑定层
        'python3*.dll',      # Python 解释器: 压缩后 import 异常
        'python3*.pyd',      # Python 扩展模块
        'vcruntime*.dll',    # VC 运行时: 压缩后内存分配异常
        'msvcp*.dll',        # C++ 标准库
        'ucrtbase*.dll',     # 通用 C 运行时
    ],
```

- [ ] **Step 2: 重新打包验证**

```bash
.\build_exe.bat
```

预期: 打包成功, exe 可正常启动 (不因 UPX 压缩崩溃)。

- [ ] **Step 3: 启动 exe 冒烟测试**

```bash
dist\MapForge.exe
# 等待 3 秒后关闭
```

预期: 窗口正常显示, 无崩溃。

---

## Task 5: Item 13 — 创建 requirements.txt 依赖锁定

**问题:** 无 requirements.txt, 依赖版本未锁定, 换机安装可能引入不兼容版本。

**文件:**
- Create: `requirements.txt` (项目根目录)

### 步骤

- [ ] **Step 1: 创建 requirements.txt**

```
# MapForge 运行时依赖 (版本锁定, pip install -r requirements.txt)
PyQt6==6.11.0
PyQt6-QScintilla==2.14.1
openai==3.8.0
PyYAML==6.0.3
# 打包工具 (仅开发环境需要)
pyinstaller==6.22.2
```

- [ ] **Step 2: 验证依赖安装**

```bash
pip install -r requirements.txt
python -c "import PyQt6, PyQt6.QtCore, PyQt6.Qsci, openai, yaml; print('依赖导入成功')"
```

预期: 全部导入成功。

- [ ] **Step 3: 运行测试确认无回归**

```bash
python -m pytest tests/ -v
```

预期: 全部通过。

---

## Task 6: Item 15 — 异步 JSON 解析（QThread）

**问题:** `_on_file_selected` 在主线程同步调用 `parse_scene_file`, 大型 JSON (>1MB) 会阻塞 UI 线程导致界面卡顿。

**文件:**
- Modify: `mapforge_app.py` (新增 SceneParseWorker 类 + 修改 _on_file_selected)
- Test: `tests/test_parse_worker.py` (新建)

### 步骤

- [ ] **Step 1: 编写 SceneParseWorker 测试**

创建 `tests/test_parse_worker.py`:

```python
"""测试: SceneParseWorker 异步解析场景文件, 通过信号返回结果。"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_parse_worker_success():
    """验证 SceneParseWorker 能异步解析合法 JSON 并通过信号返回 (scene, info)。"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
    app = QApplication.instance() or QApplication(sys.argv)

    # 写一个合法场景 JSON 到临时文件
    scene_data = {
        "scene": {"name": "TestScene", "target_level": "/Game/Maps/Test"},
        "placements": [{"asset": "/Game/A", "location": [0, 0, 0]}],
    }
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(scene_data, tmp)
    tmp.close()

    from mapforge_app import SceneParseWorker
    worker = SceneParseWorker(tmp.name)
    results = {}
    def on_done(scene, info):
        results["scene"] = scene
        results["info"] = info
    worker.finished_signal.connect(on_done)
    worker.start()

    # 等待 worker 完成 (事件循环驱动)
    loop = QEventLoop()
    worker.finished_signal.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)  # 超时保护
    loop.exec()

    assert results.get("scene") is not None, "scene 未返回"
    assert results["info"]["name"] == "TestScene"
    assert results["info"]["total_actors"] == 1
    os.unlink(tmp.name)
    print("SceneParseWorker 成功解析验证通过")

def test_parse_worker_error():
    """验证非法文件路径时返回 (None, error_msg)。"""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer
    app = QApplication.instance() or QApplication(sys.argv)

    from mapforge_app import SceneParseWorker
    worker = SceneParseWorker("/nonexistent/path.json")
    results = {}
    def on_done(scene, info):
        results["scene"] = scene
        results["info"] = info
    worker.finished_signal.connect(on_done)
    worker.start()

    loop = QEventLoop()
    worker.finished_signal.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()

    assert results.get("scene") is None, "非法路径应返回 None"
    assert isinstance(results.get("info"), str), "应返回错误信息字符串"
    print("SceneParseWorker 错误处理验证通过")

if __name__ == "__main__":
    test_parse_worker_success()
    test_parse_worker_error()
    print("=== SceneParseWorker 测试通过 ===")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_parse_worker.py -v
```

预期: FAIL (SceneParseWorker 不存在)。

- [ ] **Step 3: 实现 SceneParseWorker 类**

在 `mapforge_app.py` 的 `parse_scene_file` 函数之后 (约 297 行后), 添加:

```python
class SceneParseWorker(QThread):
    """异步场景文件解析线程: 避免大型 JSON 阻塞 UI 主线程。

    信号:
        finished_signal: (scene_dict, info_dict) 或 (None, error_msg)
    """
    finished_signal = pyqtSignal(object, object)  # (scene|None, info|error_msg)

    def __init__(self, file_path):
        super().__init__()
        self._file_path = file_path

    def run(self):
        scene, info = parse_scene_file(self._file_path)
        self.finished_signal.emit(scene, info)
```

- [ ] **Step 4: 修改 _on_file_selected 改为异步解析**

将 `mapforge_app.py:1941-1996` 的 `_on_file_selected` 方法改为:

```python
    def _on_file_selected(self, file_path):
        """文件选择回调: 异步解析场景文件, 更新 UI"""
        if not file_path:
            self.scene_info_label.setText("❌ 不支持的文件格式, 请选择 .json 或 .yaml 文件")
            self.generate_btn.setEnabled(False)
            return

        self.scene_file = file_path
        self.scene_info = None
        self.umap_path = ""
        # 切换场景后旧 umap 已失效, 禁用打开目录/下载/UE编辑器按钮
        self.download_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.open_ue_btn.setEnabled(False)
        # 解析期间禁用生成按钮, 显示解析中状态
        self.generate_btn.setEnabled(False)
        self.scene_info_label.setText("⏳ 正在解析场景文件...")

        # 异步解析: 大型 JSON 在后台线程解析, 避免阻塞 UI
        self._parse_worker = SceneParseWorker(file_path)
        self._parse_worker.finished_signal.connect(self._on_parse_done)
        self._parse_worker.start()

    def _on_parse_done(self, scene, info):
        """异步解析完成回调: 根据结果更新 UI"""
        if scene is None:
            self.scene_info_label.setText("❌ " + str(info))
            self.generate_btn.setEnabled(False)
            return

        self.scene_info = info

        # 记入最近文件列表(去重置顶, 便于下次快速加载)
        self._add_recent_file(self.scene_file)

        # 显示场景信息
        info_text = (
            "✅ 场景: {name}\n"
            "    目标关卡: {target_level}\n"
            "    Actor 总数: {total_actors} (单体 {singles} + 网格 {grids})\n"
            "    光照: {lighting}  天气: {weather}"
        ).format(
            name=info["name"],
            target_level=info["target_level"],
            total_actors=info["total_actors"],
            singles=info["singles"],
            grids=info["grids"],
            lighting="✅" if info["has_lighting"] else "❌",
            weather="✅" if info["has_weather"] else "❌",
        )
        self.scene_info_label.setText(info_text)

        # 检查引擎配置是否有效
        ue5_ok = os.path.isfile(self.ue5_path_edit.text().strip())
        proj_ok = os.path.isfile(self.project_path_edit.text().strip())
        if ue5_ok and proj_ok:
            self.generate_btn.setEnabled(True)
        else:
            self.generate_btn.setEnabled(False)
            if not ue5_ok:
                self.scene_info_label.setText(info_text + "\n⚠️ UE5 引擎路径无效, 请检查设置")
            elif not proj_ok:
                self.scene_info_label.setText(info_text + "\n⚠️ 项目文件路径无效, 请检查设置")
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_parse_worker.py -v
```

预期: PASS。

- [ ] **Step 6: 编译检查 + 全量测试**

```bash
python -m py_compile mapforge_app.py
python -m pytest tests/ -v
```

预期: 全部通过。

---

## Task 7: Item 16 — 经验库 FTS5 索引优化

**问题:** `ExperienceBank._find_similar` 和 `ExperienceRetriever.retrieve` 均调用 `get_all()` 全表加载 + Python 端逐行 Jaccard 计算, O(n) 随经验数线性退化。

**方案:** 利用 SQLite 内置 FTS5 全文索引, 先用关键词 MATCH 快速筛选候选集, 再对候选集精确计算 Jaccard, 将 O(n) 降为 O(k) (k = 候选数, 通常 << n)。

**文件:**
- Modify: `ai/experience_bank.py` (_init_db + _find_similar + 新增 _sync_fts)
- Modify: `ai/retriever.py` (retrieve 候选预过滤)
- Modify: `tests/test_phase07_bank.py` (新增 FTS5 用例)

### 步骤

- [ ] **Step 1: 编写 FTS5 候选过滤测试**

在 `tests/test_phase07_bank.py` 末尾 (`if __name__` 之前) 新增:

```python
def test_fts5_candidate_filter():
    """验证 FTS5 索引: 大量经验时 _find_similar 不全表扫描, 仅返回关键词重叠候选。"""
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank(':memory:')
    # 插入 100 条无关键词重叠的经验
    for i in range(100):
        bank.save(
            f'desc_{i}',
            {'keywords': [f'kw_{i}']},
            {'scene': {'target_level': f'/Game/T{i}'}},
            rating=3,
        )
    # 插入 1 条与查询高度重叠的经验
    bank.save(
        '目标经验',
        {'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/Target'}},
        rating=5,
    )
    # 查询: 关键词完全重叠
    similar = bank._find_similar({'keywords': ['grass', 'tree', 'river']})
    assert similar is not None, '应找到相似经验'
    assert similar['user_desc'] == '目标经验', f"应匹配目标经验, 实际: {similar['user_desc']}"
    # 查询: 关键词无重叠 (不应匹配任何经验)
    none_result = bank._find_similar({'keywords': ['nonexistent']})
    assert none_result is None, '无关键词重叠时应返回 None'
    bank.close()
    print('FTS5 候选过滤验证通过')

def test_fts5_backward_compat():
    """验证 FTS5 改造后原有去重逻辑仍正常工作。"""
    from ai.experience_bank import ExperienceBank
    bank = ExperienceBank(':memory:')
    id1 = bank.save(
        '山谷草地',
        {'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/T1'}},
        rating=4,
    )
    id2 = bank.save(
        '另一个山谷草地',
        {'keywords': ['grass', 'tree', 'river']},
        {'scene': {'target_level': '/Game/T2'}},
        rating=5,
    )
    assert id1 == id2, '相似经验应去重(同id)'
    assert len(bank.get_all()) == 1, '去重后应只有1条'
    assert bank.get_by_id(id1)['rating'] == 5, 'rating应被更新'
    bank.close()
    print('FTS5 向后兼容验证通过')
```

并在 `if __name__ == '__main__':` 块中追加调用:

```python
if __name__ == '__main__':
    test_create_db()
    test_save_query()
    test_update_stats()
    test_stats()
    test_dedup()
    test_default_path()
    test_fts5_candidate_filter()
    test_fts5_backward_compat()
    print('=== Phase 7 全部测试通过 ===')
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_phase07_bank.py::test_fts5_candidate_filter tests/test_phase07_bank.py::test_fts5_backward_compat -v
```

预期: FAIL (FTS5 表未创建 / _find_similar 仍全表扫描)。

- [ ] **Step 3: 修改 experience_bank.py _init_db — 新增 keywords_text 列 + FTS5 虚拟表**

将 `ai/experience_bank.py:22-39` 的 `_init_db` 方法改为 (含旧库迁移逻辑):

```python
    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_desc       TEXT NOT NULL,
                intent_json     TEXT NOT NULL,
                scene_json      TEXT NOT NULL,
                rating          INTEGER DEFAULT 3,
                tags            TEXT DEFAULT '',
                keywords_text   TEXT DEFAULT '',
                embedding       TEXT DEFAULT '',
                created_at      TEXT NOT NULL,
                used_count      INTEGER DEFAULT 0,
                last_used_at    TEXT,
                success_count   INTEGER DEFAULT 0,
                fail_count      INTEGER DEFAULT 0
            )
        """)
        # 旧库迁移: 若 keywords_text 列不存在则补加并回填
        try:
            self._conn.execute("SELECT keywords_text FROM experiences LIMIT 0")
        except Exception:
            self._conn.execute(
                "ALTER TABLE experiences ADD COLUMN keywords_text TEXT DEFAULT ''")
            for row in self._conn.execute(
                "SELECT id, intent_json FROM experiences"
            ).fetchall():
                kw = json.loads(row["intent_json"]).get("keywords", [])
                self._conn.execute(
                    "UPDATE experiences SET keywords_text=? WHERE id=?",
                    (" ".join(kw), row["id"]))
        # FTS5 全文索引: 独立虚拟表 (非外部内容表), 手动在 save() 中同步
        # 用 MATCH 快速筛选关键词有重叠的候选, 替代全表 Jaccard 扫描
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts USING fts5(
                keywords_text
            )
        """)
        # 旧库回填: 已有记录但 FTS5 索引为空时, 从 keywords_text 回填
        fts_count = self._conn.execute(
            "SELECT COUNT(*) FROM experiences_fts"
        ).fetchone()[0]
        if fts_count == 0:
            for row in self._conn.execute(
                "SELECT id, keywords_text FROM experiences WHERE keywords_text != ''"
            ).fetchall():
                self._conn.execute(
                    "INSERT INTO experiences_fts(rowid, keywords_text) VALUES (?, ?)",
                    (row["id"], row["keywords_text"]))
        self._conn.commit()
```

设计说明:
- `keywords_text` 列存储空格分隔的关键词 (如 `"grass tree river"`), 在 `save()` 中写入
- FTS5 使用独立虚拟表 (非 `content=` 外部内容表), 避免触发器复杂度, 在 `save()` 中手动同步
- 旧库迁移: `ALTER TABLE` 补列 + 从 `intent_json` 回填 `keywords_text` + 回填 FTS5 索引

- [ ] **Step 4: 修改 experience_bank.py save — 手动同步 FTS5**

将 `ai/experience_bank.py:57-78` 的 `save` 方法改为:

```python
    def save(self, user_desc, intent, scene, rating=3, tags=""):
        # 去重: 查找相似经验, 存在则更新而非新增
        similar = self._find_similar(intent)
        # 将 keywords 列表转为空格分隔文本 (FTS5 索引和 MATCH 查询用)
        keywords_text = " ".join(intent.get("keywords", []))
        if similar:
            now = datetime.now().isoformat()
            self._conn.execute(
                "UPDATE experiences SET user_desc=?, intent_json=?, scene_json=?, "
                "rating=?, tags=?, keywords_text=?, created_at=? WHERE id=?",
                (user_desc, json.dumps(intent, ensure_ascii=False),
                 json.dumps(scene, ensure_ascii=False), rating, tags,
                 keywords_text, now, similar["id"])
            )
            # 同步 FTS5: 先删旧索引再插新索引
            self._conn.execute(
                "INSERT INTO experiences_fts(experiences_fts, rowid, keywords_text) "
                "VALUES ('delete', ?, ?)", (similar["id"], ""))
            self._conn.execute(
                "INSERT INTO experiences_fts(rowid, keywords_text) VALUES (?, ?)",
                (similar["id"], keywords_text))
            self._conn.commit()
            return similar["id"]
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO experiences (user_desc, intent_json, scene_json, rating, tags, "
            "keywords_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_desc, json.dumps(intent, ensure_ascii=False),
             json.dumps(scene, ensure_ascii=False), rating, tags,
             keywords_text, now)
        )
        exp_id = cursor.lastrowid
        # 同步 FTS5: 插入新索引
        self._conn.execute(
            "INSERT INTO experiences_fts(rowid, keywords_text) VALUES (?, ?)",
            (exp_id, keywords_text))
        self._conn.commit()
        return exp_id
```

- [ ] **Step 5: 修改 experience_bank.py _find_similar — FTS5 候选预过滤**

将 `ai/experience_bank.py:41-55` 的 `_find_similar` 方法改为:

```python
    def _find_similar(self, intent, threshold=0.6):
        """查找与当前 intent 关键词 Jaccard 相似度 >= threshold 的已有经验

        优化: 先用 FTS5 MATCH 快速筛选关键词有重叠的候选 (O(k)),
        再对候选集精确计算 Jaccard (避免全表扫描 O(n))。
        """
        my_keywords = set(intent.get("keywords", []))
        if not my_keywords:
            return None
        # FTS5 MATCH 查询: 将关键词用空格连接, MATCH 返回含任一关键词的行
        query = " ".join(my_keywords)
        try:
            candidate_rows = self._conn.execute(
                "SELECT e.id, e.intent_json FROM experiences e "
                "JOIN experiences_fts f ON e.id = f.rowid "
                "WHERE experiences_fts MATCH ? ORDER BY rank",
                (query,)
            ).fetchall()
        except Exception:
            # FTS5 不可用时回退全表扫描 (兼容旧数据库)
            candidate_rows = self._conn.execute(
                "SELECT id, intent_json FROM experiences"
            ).fetchall()
        for row in candidate_rows:
            exp_intent = json.loads(row["intent_json"])
            exp_kw = set(exp_intent.get("keywords", []))
            if not exp_kw:
                continue
            jaccard = len(my_keywords & exp_kw) / len(my_keywords | exp_kw)
            if jaccard >= threshold:
                return self.get_by_id(row["id"])
        return None
```

- [ ] **Step 6: 修改 retriever.py retrieve — FTS5 候选预过滤**

将 `ai/retriever.py:42-88` 的 `retrieve` 方法中 `all_exps = self._bank.get_all()` 改为 FTS5 候选预过滤:

```python
    def retrieve(self, intent, top_k=3):
        """检索与 intent 最相似的经验, 返回 top-K 条。

        优化: 先用 FTS5 MATCH 筛选关键词重叠候选 (O(k)),
        再对候选集计算四因子得分 (避免全表扫描 O(n))。
        无关键词时回退全表扫描。
        """
        # 当前 intent 的关键词
        my_keywords = intent.get("keywords", [])

        # FTS5 候选预过滤: 仅取关键词有重叠的经验 (大幅减少评分范围)
        if my_keywords:
            query = " ".join(my_keywords)
            try:
                candidate_rows = self._bank._conn.execute(
                    "SELECT e.* FROM experiences e "
                    "JOIN experiences_fts f ON e.id = f.rowid "
                    "WHERE experiences_fts MATCH ? ORDER BY rank",
                    (query,)
                ).fetchall()
                all_exps = [self._bank._row_to_dict(r) for r in candidate_rows]
            except Exception:
                # FTS5 不可用时回退全表
                all_exps = self._bank.get_all()
        else:
            # 无关键词: 回退全表 (语义需要, 无法用 FTS5 过滤)
            all_exps = self._bank.get_all()

        if not all_exps:
            return []

        # 计算四因子得分（关键词相似度 0.65 + 时效性 0.15 + 可靠性 0.20）
        scored = []
        for exp in all_exps:
            sim = self._keyword_similarity(my_keywords, exp["intent"].get("keywords", []))
            rec = self._recency(exp.get("last_used_at") or exp.get("created_at", ""))
            rel = self._reliability(exp.get("success_count", 0), exp.get("fail_count", 0))
            score = WEIGHT_KEYWORD_SIM * sim + WEIGHT_RECENCY * rec + WEIGHT_RELIABILITY * rel
            scored.append((score, sim, exp))

        # 按总分降序排序
        scored.sort(key=lambda x: -x[0])

        # MMR 多样性选择：避免返回关键词高度相似的多条经验
        selected = []
        for score, sim, exp in scored:
            if len(selected) >= top_k:
                break
            if not selected:
                selected.append(exp)
                continue
            max_sim = max(
                self._keyword_similarity(
                    exp["intent"].get("keywords", []),
                    s["intent"].get("keywords", [])
                )
                for s in selected
            )
            mmr = score + WEIGHT_DIVERSITY * (1 - max_sim)
            if mmr > MMR_THRESHOLD:
                selected.append(exp)

        return selected
```

- [ ] **Step 7: 运行测试确认通过**

```bash
python -m pytest tests/test_phase07_bank.py -v
```

预期: 全部通过 (6 项原有 + 2 项新增 = 8 项)。

- [ ] **Step 8: 运行检索器测试确认无回归**

```bash
python -m pytest tests/test_phase08_retriever.py -v
```

预期: 全部通过。

- [ ] **Step 9: 编译检查 + 全量测试**

```bash
python -m py_compile ai/experience_bank.py ai/retriever.py
python -m pytest tests/ -v
```

预期: 全部通过。

---

## 最终验证

- [ ] **Step F1: 全量编译检查**

```bash
python -m py_compile mapforge_app.py build_umap.py build_scene.py diagnose_landscape.py ai/experience_bank.py ai/retriever.py
```

- [ ] **Step F2: 全量测试**

```bash
python -m pytest tests/ -v
```

预期: 全部通过 (原有 31 + 新增 4 = 35 项)。

- [ ] **Step F3: 打包验证**

```bash
.\build_exe.bat
```

预期: dist\MapForge.exe 生成成功。

- [ ] **Step F4: 冒烟测试**

```bash
# 启动 exe, 确认窗口正常显示
dist\MapForge.exe
```

---

## 自审清单

**1. 规范覆盖:**
- Item 6 (配置去硬编码) → Task 1 ✓
- Item 7 (崩溃捕获 + 持久化日志) → Task 2 ✓
- Item 11 (build_exe.bat chcp/路径/spec 委托) → Task 3 ✓
- Item 12 (UPX 排除列表) → Task 4 ✓
- Item 13 (requirements.txt 依赖锁定) → Task 5 ✓
- Item 15 (异步 JSON 解析) → Task 6 ✓
- Item 16 (经验库 FTS5 索引) → Task 7 ✓

**2. 占位符扫描:** 无 TBD/TODO/"实现细节后补" 等占位符, 每步均有完整代码。

**3. 类型/方法签名一致性:**
- `SceneParseWorker.finished_signal` 在 Task 6 Step 3 定义为 `pyqtSignal(object, object)`, Step 4 的 `_on_parse_done(self, scene, info)` 签名一致 ✓
- `ExperienceBank._find_similar` 在 Task 7 Step 5 返回 `get_by_id(row["id"])` 或 `None`, 与原有调用方 `save()` 中的 `similar` 使用方式一致 ✓
- `ExperienceBank._conn` 在 retriever.py 中通过 `self._bank._conn` 访问, 与 experience_bank.py 中 `self._conn` 一致 ✓
- 新增字段 `keywords_text` 在 `_init_db`、`save`、`_find_similar` 中一致使用 ✓
