# ============================================================================
# UE场景工厂 UESceneFactory - JSON/YAML → UMAP 可视化转换工具 (PyQt6 GUI)
# ============================================================================
# 功能: 上传 JSON/YAML 场景文件 → 调用 UE5 引擎生成 umap → 下载结果
# 依赖: PyQt6, PyYAML (可选, 无则仅支持 JSON)
# 打包: pyinstaller --onefile --add-data "build_scene.py;." mapforge_app.py
# ============================================================================

import sys
import os
import json
import shutil
import subprocess
import tempfile
import time
import logging
from collections import deque

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QProgressBar, QPlainTextEdit, QLineEdit,
    QFileDialog, QFrame, QGroupBox, QMessageBox, QSizePolicy, QSpacerItem,
    QComboBox, QTextEdit, QSplitter, QTabWidget, QScrollArea,
    QDialog, QFormLayout, QDialogButtonBox, QListWidget, QListWidgetItem,
    QMenu, QApplication
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize, QEvent, QPoint,
    pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF, QPointF, QRect
)
from PyQt6.QtGui import (
    QFont, QDragEnterEvent, QDropEvent, QIcon, QAction, QColor,
    QPainter, QFontMetrics, QKeySequence,
    QLinearGradient, QRadialGradient, QConicalGradient,
    QPainterPath, QPen, QBrush, QPalette, QShortcut
)
# QScintilla: 专业代码编辑器组件, 提供 JSON 语法高亮 + 代码折叠 + 行号
# 导入失败时降级为 QPlainTextEdit, 保证应用其他功能 (UMAP构建等) 不受影响
try:
    from PyQt6.Qsci import QsciScintilla, QsciLexerJSON
    HAS_QSCI = True
except ImportError:
    HAS_QSCI = False
    from PyQt6.QtWidgets import QPlainTextEdit
    # 降级类型别名, 使 ChatPanel 代码无需区分 HAS_QSCI 即可创建编辑器
    QsciScintilla = QPlainTextEdit
    QsciLexerJSON = None

# ============================================================================
# 版本管理: 每次修改/新增功能后, 版本号递增 + VERSION_HISTORY 追加条目
# ----------------------------------------------------------------------------
APP_VERSION = "1.0.10"

# 版本更新记录: [(版本号, 日期, [更新条目]), ...] 最新在最前
VERSION_HISTORY = [
    ("1.0.10", "2026-09-10", [
        "[新增] AI 对话面板每条信息自动加时间戳前缀 [HH:MM:SS], 统一通过 _append_chat() 方法输出, 便于追踪生成流程各阶段耗时",
        "[修复] AI 生成 Stage 2 请求超时(Request timed out): glm-5.2 推理模型处理 20KB 模板注入后的大 system prompt + 32K 输出超过原 300s 超时, _LLM_TIMEOUT 调至 600s(10分钟)",
    ]),
    ("1.0.9", "2026-09-10", [
        "[优化] AI 初次生成 JSON 质量大幅提升: KnowledgePack 新增模板标杆注入机制, 按用户意图自动匹配 1 个已验证高质量场景 JSON(P1~P16 共12个模板)注入 system prompt 作为 few-shot 标杆示例, AI 从'靠字段表盲写'变为'有高质量完整 JSON 可模仿'",
        "[优化] 模板匹配优先级: 特定地形模式(梯田/喀斯特/沟壑) > 特定资产关键词(停机坪/光伏/通信塔/高压塔/森林/村落) > 水系场景 > 默认全地形综合场景(P11推荐起点)",
        "[优化] 大模板(P2围栏45KB)自动排除注入, 避免撑爆 system prompt token 预算(上限25KB)",
        "[新增] data/templates/ 目录收录12个已验证模板, data/knowledge/templates_index.md 收录模板说明",
        "[新增] UESceneFactory.spec 打包配置同步加入 data/templates/ 目录",
    ]),
    ("1.0.8", "2026-09-10", [
        "[改进] 程序更名: MapForge → UE场景工厂 UESceneFactory (按产品命名: UE=Unreal Engine, 场景工厂=从 JSON 生产 UE5 场景)。同步更新: 窗口标题/品牌标识/关于弹窗/命令面板/应用名/日志目录(%APPDATA%/UESceneFactory)/AI 经验库目录(~/.uescenefactory); exe 产物更名为 UESceneFactory.exe",
    ]),
    ("1.0.7", "2026-09-10", [
        "[修复] 关于弹窗滚动方案修正: v1.0.6 的 QTextBrowser 在 layout 中 sizeHint=内容高度会撑开对话框, 导致内容全部平铺、滚动条始终不出现(弹窗占满屏幕高度 768px 无滚动); 改用 QScrollArea + QLabel(wordWrap), viewport 固定、内容超出即出滚动条",
        "[修复] 关于弹窗不弹出: QLabel 无 setHtml 方法(误用 QTextBrowser API 致 AttributeError, 弹窗无法打开), 改用 setText(已设 RichText 格式按富文本渲染)",
    ]),
    ("1.0.6", "2026-09-10", [
        "[修复] AI 生成页点击“采纳并生成 umap”跳转构建页时, 顶部分段控件滑块未同步(仍停在“AI 生成”): 改为通过 _segmented.setCurrentIndex 切换, 滑块动画与 tabs 内容同步",
        "[改进] 关于弹窗改用 QTextBrowser 承载版本简说, 高度上限 900px, 超出部分自动出现滚动条(原 QMessageBox.about 固定布局无滚动)",
    ]),
    ("1.0.5", "2026-09-10", [
        "[修复] 顶部状态药丸从不更新: 文件药丸在选文件/解析/失败时, 构建药丸在构建/取消/完成/失败时, 均未接状态流转(一直停留初始文本)。现已在 _on_file_selected/_on_parse_done/_on_generate/_on_finished 接线, 药丸随流程实时变化(idle/working/done/error 四态)",
    ]),
    ("1.0.4", "2026-09-10", [
        "[修复] 构建页左侧栏整块不渲染: 移除 QGraphicsDropShadowEffect(当前 Qt6 环境下该效果使子树离屏合成为空), 纵深改由 Mesh 渐变+玻璃面板呈现",
        "[修复] 768p 等矮窗口侧栏标签被裁切: 侧栏内容改按需滚动容器(QScrollArea), 常规高度无滚动条, 矮窗口自动出现纵向滚动条",
        "[修复] 最大化时进程崩溃: StatusPill.paintEvent 中 drawRoundedRect 因宽度为 float 触发 int 重载 TypeError, 改用 QRectF 重载规避",
    ]),
    ("1.0.3", "2026-09-09", [
        "[设计] 方案三·暗室 UI 框架重构: Mesh 渐变背景 + 玻璃悬浮面板",
        "[设计] 顶栏分段控件(SegmentedControl)替代原生 TabBar, 带动画滑块",
        "[设计] 状态药丸(StatusPill)实时显示文件/构建状态",
        "[设计] Ctrl+K 命令面板(CommandPalette), 模糊搜索快捷操作",
        "[设计] 玻璃面板投影(QGraphicsDropShadowEffect), 纵深空间感",
    ]),
    ("1.0.2", "2026-09-09", [
        "[功能] AI 生成的 JSON 每个结构块和子块自动包含 _note 详细注释",
        "[功能] 注释写明块用途和每个参数的意义 (core.md 注释规范 + 示例模板)",
        "[功能] 关于弹窗显示版本号和版本更新简说",
    ]),
    ("1.0.1", "2026-09-09", [
        "[修复] 资产校验 Content 路径改为从配置文件推导, 移除硬编码 (C1)",
        "[修复] MMR 多样性评分增加 min() 裁剪, 防止权重溢出 (C3)",
        "[修复] UE5 构建命令 shell=False, 消除命令注入风险 (C4)",
        "[修复] QScintilla 导入防御, 缺失时降级为 QPlainTextEdit (W2)",
        "[修复] 场景校验器清理 __import__('os'), 统一使用 import os (W7)",
    ]),
    ("1.0.0", "2026-09-08", [
        "[功能] AI 智能生成 UE5 场景 JSON (8 阶段管线)",
        "[功能] 场景 JSON 字段/类型/枚举校验器",
        "[功能] JSON 场景 → UE5 umap 一键构建",
        "[功能] 经验库存储与 MMR 检索",
        "[功能] QScintilla 语法高亮编辑器",
        "[功能] 资产路径预校验",
    ]),
]

# 模块级日志器: 统一记录异常与诊断信息, 替代裸 except: pass
logger = logging.getLogger("uescenefactory")
_LOG_DIR = None  # 日志目录路径, 由 _setup_logging() 初始化, 测试可读取

def _setup_logging():
    """初始化持久化日志: RotatingFileHandler 写入用户目录 + 安装崩溃捕获钩子。

    日志路径: Windows %APPDATA%/UESceneFactory/logs/, 其他平台 ~/.uescenefactory/logs/
    崩溃捕获: sys.excepthook 记录未捕获异常到日志文件 (console=False 时不可见)
    Qt 消息: qInstallMessageHandler 记录 Qt 内部警告/错误
    """
    from logging.handlers import RotatingFileHandler

    # 1. 确定日志目录
    if sys.platform == "win32":
        _appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        log_dir = os.path.join(_appdata, "UESceneFactory", "logs")
    else:
        log_dir = os.path.join(os.path.expanduser("~"), ".uescenefactory", "logs")
    os.makedirs(log_dir, exist_ok=True)
    # 暴露给测试
    global _LOG_DIR
    _LOG_DIR = log_dir

    # 2. RotatingFileHandler: 单文件 5MB, 保留 3 份备份, UTF-8 编码
    _file_handler = RotatingFileHandler(
        os.path.join(log_dir, "uescenefactory.log"),
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

# 尝试导入 yaml (可选依赖, 无则仅支持 JSON 场景文件)
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# AI 场景生成模块
from ai.client import MockLLMClient, OpenAILLMClient, OllamaLLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.intent_parser import IntentParser
from ai.generator import SceneGenerator
from ai.validator import ValidationRepairLoop
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever

# Mock 模式预设响应：意图 JSON + 场景 JSON（供 MockLLMClient 循环返回）
# 与 tests/test_phase11_pipeline.py 中的 mock 数据格式一致，保证管线端到端可用
_MOCK_INTENT = json.dumps({
    "terrain_type": "features", "has_river": True, "has_grass": True,
    "keywords": ["grass", "tree"], "scene_scale": "1km", "complexity": "medium"
})
_MOCK_SCENE = json.dumps({
    "scene": {"name": "MockScene", "target_level": "/Game/Maps/MockScene"},
    "landscape": {
        "material": "/Game/M", "section_size_quads": 63, "num_subsections": 2,
        "component_count_x": 8, "component_count_y": 8,
        "layers": [{"info": "/Game/L", "weight": 1.0}]
    }
})


# ============================================================================
# 配置管理: 保存/加载用户设置 (UE5 路径、项目路径)
# ============================================================================

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".uescenefactory_config.json")

# 一次性迁移: 旧配置文件(.mapforge_config.json)存在而新配置不存在时, 重命名以保留用户 API Key 等设置
_legacy_config = os.path.join(os.path.expanduser("~"), ".mapforge_config.json")
if not os.path.exists(CONFIG_PATH) and os.path.exists(_legacy_config):
    try:
        os.rename(_legacy_config, CONFIG_PATH)
    except OSError:
        pass

# 默认配置 (基于用户当前环境)
# 阿里云 AI API 可选模型列表（用户可在设置对话框下拉选择或手动输入自定义模型名）
ALIYUN_MODELS = ["glm-5.2", "deepseek-v4-pro", "deepseek-v4-flash", "qwen3.8-max"]

DEFAULT_CONFIG = {
    # 引擎/项目路径: 空串表示未配置, 首次启动时自动探测
    "ue5_path": "",
    "project_path": "",
    # 阿里云 AI API 默认配置
    "llm_profile": "openai",
    "llm_base_url": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "llm_api_key": "${ALIYUN_APIKEY}",
    "llm_model": "glm-5.2",
    # 转换成功历史记录: 每条 {ts, scene_name, scene_path, umap_path, duration_sec, size_bytes}
    "build_history": [],
}


def load_config():
    """从用户主目录加载配置文件"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # 合并默认值 (防止缺少字段)
        merged = DEFAULT_CONFIG.copy()
        merged.update(cfg)
        return merged
    except FileNotFoundError:
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logger.warning("配置文件加载失败, 回退默认值: %s", e)
        return DEFAULT_CONFIG.copy()


def save_config(cfg):
    """保存配置到用户主目录, 返回是否成功"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error("配置保存失败: %s", e)
        return False


def _fmt_size(num):
    """把字节数格式化为 B/KB/MB/GB 可读字符串(用于历史记录大小显示)"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def resolve_env_value(value):
    """解析 ${VAR_NAME} 格式的环境变量引用，运行时从 os.environ 读取

    用户可在设置对话框中填写 ${MAPFORGE_API_KEY} 而非明文密钥，
    运行时从系统环境变量解析实际值，避免密钥明文存储在配置文件中。
    若 value 不是 ${...} 格式，则原样返回。
    """
    if value and isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        var_name = value[2:-1]
        return os.environ.get(var_name, "")
    return value


# ============================================================================
# 路径自动探测: 首次使用时扫描常见位置, 免去手动配置
# ============================================================================

def autodetect_ue5_path():
    """扫描常见引擎安装位置, 返回版本号最高的 UnrealEditor-Cmd.exe 路径(正斜杠)。

    多版本并存时(如 UE_5.7 与 UE_5.8)取最高版本, 保证确定性。未找到返回空串。
    """
    found = []
    for drive in ("C:", "D:", "E:", "F:"):
        base = "{}/Program Files/Epic Games".format(drive)
        if not os.path.isdir(base):
            continue
        try:
            for name in os.listdir(base):
                if not name.upper().startswith("UE_"):
                    continue
                exe = "{}/{}/Engine/Binaries/Win64/UnrealEditor-Cmd.exe".format(base, name)
                if os.path.isfile(exe):
                    found.append((name, exe))
        except Exception as e:
            logger.debug("扫描引擎路径 %s 时出错: %s", base, e)
            continue
    if not found:
        return ""

    def ver_key(name):
        # "UE_5.8" → (5, 8); 解析失败退化为 (0,) 排在最后
        try:
            return tuple(int(x) for x in name.split("_", 1)[1].split("."))
        except Exception:
            return (0,)

    # 按版本号降序, 取最高版本
    found.sort(key=lambda t: ver_key(t[0]), reverse=True)
    return found[0][1].replace("\\", "/")


def autodetect_project_paths():
    """在常见项目根目录下扫描 *.uproject(深度受限, 避免遍历过深)。

    返回找到的全部项目文件路径列表(正斜杠)。存在多个时不臆测,
    交由调用方提示用户手动选择, 避免选错项目。
    """
    results = []
    # 从用户主目录推导, 避免硬编码特定用户路径
    home = os.path.expanduser("~")
    roots = [
        # 从用户主目录推导, 不硬编码特定用户路径
        os.path.join(home, "Desktop", "UE5"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for dirpath, dirnames, files in os.walk(root):
                # 深度超过 3 层就不再下钻, 避免进入 Intermediate/Binaries 等庞大目录
                depth = dirpath[len(root):].count(os.sep)
                if depth >= 3:
                    dirnames[:] = []
                    continue
                for f in files:
                    if f.lower().endswith(".uproject"):
                        results.append(os.path.join(dirpath, f).replace("\\", "/"))
        except Exception as e:
            logger.debug("扫描项目路径 %s 时出错: %s", root, e)
    return results


def classify_ue_processes(running):
    """将检测到的 UnrealEditor* 进程分类为 (editor, cmd) 两组。

    - editor: GUI 编辑器(UnrealEditor.exe), 用户主动打开, 不能替用户关闭 → 走硬阻断。
    - cmd: 无头实例(UnrealEditor-Cmd.exe), 多为上次崩溃/中断的残留 → 可提示清理后继续。
    返回 (editor_list, cmd_list), 每项为 (pid, name)。
    """
    editor, cmd = [], []
    for pid, name in running:
        if name.lower() == "unrealeditor.exe":
            editor.append((pid, name))
        elif name.lower() == "unrealeditor-cmd.exe":
            cmd.append((pid, name))
    return editor, cmd


# ============================================================================
# 资源路径: 获取 build_scene.py (支持 PyInstaller 打包后运行)
# ============================================================================

def get_resource_path(filename):
    """
    获取打包资源的真实路径
    PyInstaller --onefile 模式下, 资源解压到 sys._MEIPASS 临时目录
    开发环境下, 从脚本所在目录读取
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后：sys._MEIPASS 可能不存在（非 onefile 模式），用 getattr 安全回退
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        # 开发环境
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)


# ============================================================================
# 场景文件解析: 读取 JSON/YAML, 提取场景信息
# ============================================================================

def parse_scene_file(file_path):
    """
    解析场景文件 (.json 或 .yaml)
    返回: (scene_dict, scene_info_dict) 或 (None, error_message)
    scene_info 包含: name, target_level, total_actors, has_lighting, has_weather
    """
    ext = os.path.splitext(file_path)[1].lower()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if ext == ".json":
                scene = json.load(f)
            elif ext in (".yaml", ".yml"):
                if not HAS_YAML:
                    return None, "系统未安装 PyYAML, 无法解析 YAML 文件"
                scene = yaml.safe_load(f)
            else:
                return None, "不支持的文件格式: " + ext
    except Exception as e:
        return None, "解析文件失败: " + str(e)

    # 提取场景信息
    s = scene.get("scene", {})
    name = s.get("name", "未命名场景")
    target_level = s.get("target_level", "")

    # 统计 actor 数量
    total_actors = 0
    singles = 0
    grids = 0
    if scene.get("ground"):
        total_actors += 1
    for p in scene.get("placements", []):
        if "grid" in p:
            grids += 1
            gr = p["grid"]
            total_actors += gr.get("rows", 1) * gr.get("cols", 1)
        else:
            singles += 1
            total_actors += 1

    has_lighting = "lighting" in scene
    has_weather = "weather" in scene

    info = {
        "name": name,
        "target_level": target_level,
        "total_actors": total_actors,
        "singles": singles,
        "grids": grids,
        "has_lighting": has_lighting,
        "has_weather": has_weather,
    }
    return scene, info


class SceneParseWorker(QThread):
    """
    异步场景文件解析线程: 避免大型 JSON/YAML 阻塞 UI 主线程。
    解析完成后通过 finished_signal 发射 (scene|None, info|error_msg)。
    """
    # 信号: (scene_dict 或 None, info_dict 或 错误信息字符串)
    finished_signal = pyqtSignal(object, object)

    def __init__(self, file_path):
        super().__init__()
        self._file_path = file_path

    def run(self):
        """在后台线程中调用 parse_scene_file, 将结果通过信号回传主线程。"""
        try:
            scene, info = parse_scene_file(self._file_path)
            self.finished_signal.emit(scene, info)
        except Exception as e:
            # 兜底异常捕获: parse_scene_file 已有内部处理, 此处防漏
            logger.error("SceneParseWorker 解析异常: %s", e)
            self.finished_signal.emit(None, f"解析线程异常: {e}")


# ============================================================================
# 后台工作线程: 启动 UE5, 监控日志文件, 解析进度
# ============================================================================

class BuildWorker(QThread):
    """
    后台工作线程: 负责启动 UE5 引擎进程, 实时监控 build_scene.log 日志,
    解析进度关键字, 通过信号通知主线程更新 UI
    """
    # 信号定义
    progress = pyqtSignal(int)           # 进度百分比 0-100
    status_msg = pyqtSignal(str)         # 当前状态文本
    log_line = pyqtSignal(str)           # 日志行
    finished_signal = pyqtSignal(bool, str, str)  # (成功, 消息, umap路径)

    def __init__(self, ue5_path, project_path, scene_file, build_script_path, log_path, target_level=None):
        super().__init__()
        self.ue5_path = ue5_path
        self.project_path = project_path
        self.scene_file = scene_file
        self.build_script_path = build_script_path
        self.log_path = log_path
        # 缓存 target_level, 避免 _find_umap 重复解析场景文件
        self._target_level = target_level
        self._cancelled = False
        self._process = None

    def cancel(self):
        """取消构建 (外部调用)"""
        self._cancelled = True
        if self._process:
            try:
                self._process.kill()
            except Exception as e:
                logger.warning("取消构建时 kill 进程失败: %s", e)

    def run(self):
        """线程主逻辑: 启动 UE5 → 监控日志 → 解析进度 → 等待完成"""
        try:
            # 记录构建开始时间, 用于最终校验 umap 是否确为本次运行所写
            self._run_start = time.time()
            # 构建前快照 umap 文件状态(若磁盘上已存在旧文件):
            # 仅靠 mtime >= _run_start 的跨进程时间比较在 Windows 上不可靠
            # (目录元数据缓存/时间戳精度差异会导致假阴性 → 构建成功却误报
            # "仍是旧文件")。改为"构建前后快照对比 + 新鲜度兜底"双重判定,
            # 与 build_scene.py 内部的磁盘验证逻辑(time.time()-mtime<30)一致。
            self._umap_before = None
            _umap_path_pre = self._find_umap()
            if _umap_path_pre and os.path.exists(_umap_path_pre):
                self._umap_before = (
                    os.path.getsize(_umap_path_pre),
                    os.path.getmtime(_umap_path_pre),
                )
            # ---- 1. 准备 build_scene.py 副本到临时目录 (避免路径含空格) ----
            self.status_msg.emit("正在准备构建脚本...")
            self.progress.emit(1)

            temp_dir = tempfile.mkdtemp(prefix="uescenefactory_")
            temp_script = os.path.join(temp_dir, "build_scene.py").replace("\\", "/")
            shutil.copy2(self.build_script_path, temp_script)

            # ---- 2. 设置环境变量 (日志路径 + 场景文件路径) ----
            env = os.environ.copy()
            env["MAPFORGE_LOG"] = self.log_path
            # 传递场景文件路径给 build_scene.py, 避免回退到默认 farming_village.json
            # build_scene.py 优先从 MAPFORGE_SCENE 环境变量读取场景文件路径,
            # 彻底避免 ExecCmds 中 | 被当 argv 传入导致使用错误场景的问题
            env["MAPFORGE_SCENE"] = self.scene_file

            # ---- 3. 构造 ExecCmds 命令 ----
            # 格式: py <script> | quit
            # 关键: 脚本路径绝对不能加双引号! -ExecCmds="..." 外层已有一层引号,
            # UE 的 ExecCmds 解析器无法处理嵌套引号, 加引号会导致 py 命令收到空参数
            # 并进入交互模式阻塞 stdin, 引擎永久卡死(症状: 进度卡 5%)。
            # 临时目录路径保证不含空格, 因此可以安全地去掉引号。
            exec_cmds = 'py {} | quit'.format(temp_script)

            # ---- 4. 启动 UE5 无头模式 ----
            self.status_msg.emit("正在启动 UE5 引擎 (可能需要30-60秒)...")
            self.progress.emit(2)

            cmd = [
                self.ue5_path,
                self.project_path,
                "-unattended",
                "-nop4",
                "-nosplash",
                "-nullrhi",
                "-stdout",
                '-ExecCmds={}'.format(exec_cmds),
            ]
            # 关键修复: 不能直接用 PIPE 且不读取 —— UE5 启动日志量巨大,
            # PIPE 缓冲区(约4KB)写满后引擎写日志时会被永久阻塞, 导致进度卡死。
            # 改为重定向到临时文件, 既解除阻塞又保留失败诊断信息。
            self._ue_out_path = os.path.join(temp_dir, "ue_stdout.log")
            self._ue_out_file = open(
                self._ue_out_path, "w", encoding="utf-8", errors="replace")
            self._process = subprocess.Popen(
                cmd,
                # 防御性加固: stdin 接空设备。即使 py 命令因任何原因收到空参数
                # 进入交互模式, 也会立即读到 EOF 退出, 不会永久阻塞 stdin
                stdin=subprocess.DEVNULL,
                stdout=self._ue_out_file,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # ---- 5. 等待日志文件出现 (UE5 启动后才会创建) ----
            self.status_msg.emit("等待 UE5 引擎初始化...")
            MAX_WAIT = 240  # 最长等待秒数, 超时则判定启动失败, 避免无限卡死
            # 引擎日志静默阈值(秒): 引擎 stdout 持续无新输出且构建脚本未开始,
            # 即判定为"另一 UE 实例占用同一项目"导致的静默卡死, 提前快速失败
            SILENT_LIMIT = 90
            wait_count = 0
            last_out_size = -1  # 上一轮引擎 stdout 文件大小, 用于检测日志是否仍在增长
            last_activity = time.time()  # 最近一次引擎日志增长的时间戳
            while not os.path.exists(self.log_path) and not self._cancelled:
                if self._process.poll() is not None:
                    # UE5 进程已退出但日志未生成, 附带 stdout 尾部诊断信息
                    tail = self._read_ue_tail()
                    self._close_ue_out()
                    self.finished_signal.emit(
                        False, "UE5 引擎启动失败(进程已退出), 诊断信息:\n" + tail, "")
                    return
                # 检测引擎日志活跃度: stdout 文件仍在增长说明引擎正常启动中
                try:
                    cur_size = os.path.getsize(self._ue_out_path)
                except OSError:
                    cur_size = last_out_size
                if cur_size != last_out_size:
                    last_out_size = cur_size
                    last_activity = time.time()
                silent_sec = int(time.time() - last_activity)
                time.sleep(1)
                wait_count += 1
                # 静默卡死早期检测: 引擎启动中途停止输出(典型特征: 另一个 UE 编辑器
                # 或未退出的 UE 实例占用同一项目, 阻塞了后台引擎执行构建命令)
                if silent_sec >= SILENT_LIMIT:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                    tail = self._read_ue_tail()
                    self._close_ue_out()
                    self.finished_signal.emit(
                        False,
                        "UE5 引擎启动中途停止输出(已静默 {} 秒), 构建脚本未能执行。\n"
                        "典型原因: 另一个 UE 编辑器(或未退出的 UE 实例)正占用同一项目, 阻塞了后台引擎。\n"
                        "请关闭 UE 编辑器, 并在任务管理器中确认无残留 UnrealEditor 进程后重试。\n\n"
                        "诊断信息:\n".format(silent_sec) + tail, "")
                    return
                if wait_count > MAX_WAIT:
                    # 启动超时, 强制终止并给出诊断信息
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                    tail = self._read_ue_tail()
                    self._close_ue_out()
                    self.finished_signal.emit(
                        False, "UE5 引擎启动超时({}秒), 诊断信息:\n".format(MAX_WAIT) + tail, "")
                    return
                # 进度缓慢推进 (0-4% 表示正在启动)
                if wait_count <= 30:
                    self.progress.emit(2 + wait_count // 10)
                # 状态栏实时显示等待时长与引擎日志静默时长, 卡死时用户可直观看到
                self.status_msg.emit(
                    "正在启动 UE5 引擎... (已等待 {} 秒, 引擎日志静默 {} 秒)".format(
                        wait_count, silent_sec))

            if self._cancelled:
                self.finished_signal.emit(False, "已取消生成", "")
                return

            # ---- 6. 实时监控日志文件, 解析进度 ----
            self.status_msg.emit("正在构建场景...")
            with open(self.log_path, "r", encoding="utf-8") as log_f:
                done = False
                error_found = False
                last_pos = 0
                while not self._cancelled and not done:
                    # 读取新增的日志行
                    log_f.seek(last_pos)
                    new_lines = log_f.readlines()
                    last_pos = log_f.tell()

                    for line in new_lines:
                        line = line.strip()
                        if not line:
                            continue
                        self.log_line.emit(line)
                        # 解析进度
                        pct, msg = self._parse_progress(line)
                        if pct is not None:
                            self.progress.emit(pct)
                        if msg:
                            self.status_msg.emit(msg)
                        # 检查完成标志
                        if "BUILD_SCENE_DONE" in line:
                            done = True
                        # 检查致命错误
                        # 检查致命错误 (startswith 已隐含包含该子串, 无需冗余 and)
                        if line.startswith("load_level failed"):
                            error_found = True

                    if not done:
                        time.sleep(0.3)  # 避免忙等待

            # ---- 7. 等待 UE5 进程退出 (最多等 30 秒) ----
            if not self._cancelled:
                self.status_msg.emit("正在保存关卡文件...")
                self.progress.emit(95)
                for _ in range(30):
                    if self._process.poll() is not None:
                        break
                    time.sleep(1)
                # 如果 UE5 没有自动退出, 强制终止
                if self._process.poll() is None:
                    try:
                        self._process.kill()
                    except Exception:
                        pass

            # ---- 8. 查找生成的 umap 文件 ----
            if done and not self._cancelled:
                self.progress.emit(98)
                self.status_msg.emit("正在查找生成的 umap 文件...")
                umap_path = self._find_umap()
                if umap_path and os.path.exists(umap_path):
                    # 校验 umap 是否确为本次构建所写。
                    # 采用"快照对比 + 新鲜度兜底"双重判定, 替代不可靠的
                    # 跨进程 mtime>=run_start 比较(Windows 上会假阴性):
                    #  1) 快照对比: 构建后的大小/mtime 与构建前快照不同 → 已覆写
                    #  2) 新鲜度兜底: 文件 mtime 距当前 <120 秒 → 足够新(与
                    #     build_scene.py 内部 _age<30 一致, 此处放宽到 120 秒
                    #     容纳 UE 退出后文件锁释放的延迟)
                    _size_now = os.path.getsize(umap_path)
                    _mtime_now = os.path.getmtime(umap_path)
                    _age = time.time() - _mtime_now
                    _size_before = self._umap_before[0] if self._umap_before else -1
                    _mtime_before = self._umap_before[1] if self._umap_before else 0.0
                    _size_changed = (_size_now != _size_before)
                    _mtime_changed = (_mtime_now != _mtime_before)
                    _is_fresh = (_age < 120)
                    # 输出校验诊断日志, 便于排查(即便成功也记录, 用户可见)
                    self.log_line.emit(
                        "[校验] size {}KB->{}KB mtime {:.1f}->{:.1f} age {:.1f}s "
                        "size_changed={} mtime_changed={} fresh={}".format(
                            _size_before // 1024, _size_now // 1024,
                            _mtime_before, _mtime_now, _age,
                            _size_changed, _mtime_changed, _is_fresh))
                    if _size_changed or _mtime_changed or _is_fresh:
                        self.progress.emit(100)
                        self.finished_signal.emit(
                            True, "UMAP 生成成功!", umap_path)
                    else:
                        self.finished_signal.emit(
                            False,
                            "构建脚本执行完成, 但 umap 未能写入磁盘 (仍是旧文件)。\n"
                            "典型原因: UE 编辑器中正打开着目标地图, 文件被锁定, "
                            "后台引擎无法覆盖保存。\n"
                            "请在 UE 编辑器中关闭该地图 (或关闭编辑器) 后重试。",
                            "")
                else:
                    self.finished_signal.emit(
                        False, "生成完成但未找到 umap 文件 (请检查关卡路径)", "")
            elif self._cancelled:
                self.finished_signal.emit(False, "已取消生成", "")
            else:
                self.finished_signal.emit(
                    False, "生成失败 (未检测到 BUILD_SCENE_DONE)", "")

        except Exception as e:
            self.finished_signal.emit(False, "发生异常: " + str(e), "")
        finally:
            # 确保 UE5 stdout 重定向文件句柄被关闭
            self._close_ue_out()
            # 清理构建脚本临时目录, 避免长期累积垃圾文件
            temp_dir = locals().get("temp_dir")
            if temp_dir and os.path.isdir(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception as e:
                    logger.debug("清理临时目录失败: %s", e)

    def _close_ue_out(self):
        """关闭 UE5 stdout 重定向文件句柄"""
        try:
            if getattr(self, "_ue_out_file", None):
                self._ue_out_file.close()
                self._ue_out_file = None
        except Exception as e:
            logger.debug("关闭 UE5 stdout 文件句柄失败: %s", e)

    def _read_ue_tail(self, n=15):
        """读取 UE5 stdout 日志最后 n 行, 用于失败时给用户诊断信息

        性能优化: 使用 deque(maxlen=n) 流式读取, 避免将数十 MB 的日志全量载入内存
        """
        try:
            if getattr(self, "_ue_out_file", None):
                self._ue_out_file.flush()
            with open(self._ue_out_path, "r", encoding="utf-8", errors="replace") as f:
                tail = deque((l.rstrip() for l in f if l.strip()), maxlen=n)
            return "\n".join(tail) if tail else "(UE5 无输出)"
        except Exception as e:
            logger.debug("读取诊断日志失败: %s", e)
            return "(无法读取诊断日志)"

    def _parse_progress(self, line):
        """
        解析单行日志, 返回 (进度百分比, 状态消息)
        基于日志关键字映射进度:
          BUILD_SCENE_START → 5%
          ground placed → 8%
          single[N] → 8-20% (按比例)
          grid[N] → 20-55% (按比例)
          lighting setup done → 70%
          weather setup done → 80%
          SAVED_DIRTY → 85%
          SAVED_ASSET → 90%
          BUILD_SCENE_DONE → 100%
        """
        # 完成标志
        if "BUILD_SCENE_DONE" in line:
            return 100, "生成完成!"
        if "SAVED_ASSET" in line:
            return 90, "正在写入 umap 文件..."
        if "SAVED_DIRTY" in line:
            return 85, "正在保存关卡..."
        if "weather setup done" in line:
            return 80, "天气系统设置完成"
        if "lighting setup done" in line:
            return 70, "光照系统设置完成"
        if "HeightFog OK" in line:
            return 68, "高度雾设置完成"
        if "SkyAtmosphere OK" in line:
            return 66, "大气层设置完成"
        if "SkyLight OK" in line:
            return 64, "天空光设置完成"
        if "DirectionalLight OK" in line:
            return 62, "太阳光设置完成"
        if "ground placed" in line:
            return 8, "地面放置完成"
        if "NEW_LEVEL" in line:
            return 6, "关卡创建/加载完成"
        if "BUILD_SCENE_START" in line:
            return 5, "开始构建场景..."

        # 网格体放置进度 (20-55% 区间)
        if line.startswith("grid["):
            return None, "正在放置: " + line
        if line.startswith("single["):
            return None, "正在放置: " + line

        # 错误信息
        if "fail" in line.lower() and "OK" not in line:
            return None, None  # 错误不改变进度, 但会显示在日志中

        return None, None

    def _find_umap(self):
        """
        根据 target_level 路径和项目路径, 推算 umap 文件实际磁盘路径
        target_level 格式: /Game/MapForgeTest/GB_FarmingVillage
        umap 实际路径: {项目目录}/Content/MapForgeTest/GB_FarmingVillage.umap

        性能优化: 优先使用构造时缓存的 target_level, 避免重复解析场景文件
        """
        try:
            # 优先使用缓存的 target_level, 若无则回退到解析场景文件
            if self._target_level:
                target_level = self._target_level
            else:
                scene, _ = parse_scene_file(self.scene_file)
                if not scene:
                    return None
                target_level = scene.get("scene", {}).get("target_level", "")

            if not target_level:
                return None

            # /Game/xxx → Content/xxx
            if target_level.startswith("/Game/"):
                rel_path = target_level[6:]  # 去掉 /Game/ 前缀
            else:
                rel_path = target_level

            # 项目 Content 目录
            project_dir = os.path.dirname(self.project_path)
            content_dir = os.path.join(project_dir, "Content")
            umap_path = os.path.join(content_dir, rel_path.replace("/", os.sep) + ".umap")
            return umap_path
        except Exception:
            return None


# ============================================================================
# 拖拽上传区域: 自定义 QFrame 支持文件拖放
# ============================================================================

class DropArea(QFrame):
    """文件拖拽上传区域, 支持点击浏览和拖拽放入"""
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        # U1 修复: 不再用 setFixedHeight(80) (会裁切多行内容);
        # 改用 setMinimumHeight 由布局按内容 sizeHint 撑开, DPI/大字体自适应
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        # U14 修复: 用 Qt 标准文件夹图标替代 emoji, 规避远程桌面字体回退风险
        from PyQt6.QtWidgets import QStyle
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        self.icon_label.setPixmap(icon.pixmap(QSize(36, 36)))

        self.text_label = QLabel("拖拽 JSON/YAML 文件到此处，或点击浏览选择")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖拽进入时通过属性切换高亮样式 (避免内联 setStyleSheet 覆盖全局 QSS)"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("dragHover", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        """拖拽离开时恢复默认样式"""
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        """放下文件时触发信号"""
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".json", ".yaml", ".yml"):
                self.file_dropped.emit(file_path)
            else:
                self.file_dropped.emit("")  # 无效文件类型

    def mousePressEvent(self, event):
        """点击时打开文件浏览对话框"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._browse_file()

    def _browse_file(self):
        """打开文件选择对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择场景文件",
            "",
            "场景文件 (*.json *.yaml *.yml);;JSON 文件 (*.json);;YAML 文件 (*.yaml *.yml);;所有文件 (*)"
        )
        if file_path:
            self.file_dropped.emit(file_path)


# ============================================================================
# AI 生成后台线程: 内联三阶段管线，每阶段发信号到 UI
# ============================================================================

class AIWorker(QThread):
    """AI 生成后台线程：内联三阶段管线（意图解析→JSON生成→验证修复），每阶段发信号到 UI

    三阶段:
        1. IntentParser 解析自然语言 → intent dict
        2. KnowledgePack + AssetIndex + ExperienceRetriever 注入 → SceneGenerator 生成 JSON
        3. ValidationRepairLoop 验证-修复循环 → 最终场景 JSON
    管线末尾更新经验使用统计并保存新经验。
    """
    # 信号定义：每阶段完成后通知 UI 更新
    intent_parsed = pyqtSignal(dict)                # 意图解析完成
    json_generated = pyqtSignal(dict)               # JSON 生成完成
    validation_done = pyqtSignal(dict, list)       # 验证完成（场景 + 历史）
    repair_started = pyqtSignal(int)                # 修复轮次开始
    finished_signal = pyqtSignal(dict, bool, str)   # 全部完成（场景, 成功, 消息）
    error_occurred = pyqtSignal(str)                # 异常
    log_line = pyqtSignal(str)                       # 日志行
    # 经验保存完成信号: 传递 exp_id 供 ChatPanel 后续 update_rating 使用
    exp_saved = pyqtSignal(int)                     # 经验已保存到库 (exp_id)

    def __init__(self, client, config, user_desc, feedback=None):
        super().__init__()
        self._client = client
        self._config = config
        self._user_desc = user_desc
        self._feedback = feedback

    def run(self):
        """内联完整三阶段管线，每阶段发信号到 UI

        资源管理: bank (SQLite) 必须在 finally 中关闭,
        防止 Stage 2/3 任意步骤抛异常时连接泄漏
        """
        bank = None
        try:
            client = self._client
            config = self._config
            user_desc = self._user_desc

            # ---- Stage 1: 意图解析 ----
            self.log_line.emit('Stage 1: 意图解析...')
            intent_parser = IntentParser(client, model=config.get("llm_intent_model"))
            intent = intent_parser.parse(user_desc)
            self.intent_parsed.emit(intent)
            self.log_line.emit(f'意图解析完成: terrain={intent.get("terrain_type")}')

            # ---- Stage 2: 知识注入 + JSON 生成 ----
            self.log_line.emit('Stage 2: 知识注入 + JSON 生成...')
            # 传入 templates_dir 启用模板标杆注入, AI 初次生成即可参考已验证的高质量 JSON
            knowledge = KnowledgePack(
                get_resource_path("data/knowledge"),
                templates_dir=get_resource_path("data/templates"),
            )
            asset_index = AssetIndex(get_resource_path("asset_catalog.json"))
            bank = ExperienceBank()  # 默认 ~/.uescenefactory/
            retriever = ExperienceRetriever(bank)

            # 检索相似经验作为 few-shot 示例
            few_shots = retriever.retrieve(intent, top_k=3)
            self.log_line.emit(f'检索到 {len(few_shots)} 条经验')

            generator = SceneGenerator(client, knowledge, asset_index,
                                       model=config.get("llm_strong_model"))
            scene = generator.generate(user_desc, intent, few_shots)
            self.json_generated.emit(scene)
            self.log_line.emit('JSON 生成完成')

            # ---- Stage 3: 验证-修复循环（注入知识包 system_prompt）----
            self.log_line.emit('Stage 3: 验证-修复循环...')
            loop = ValidationRepairLoop(client, knowledge=knowledge,
                                        model=config.get("llm_strong_model"))
            final_scene, history = loop.validate_and_repair(scene, user_desc, intent=intent)
            self.validation_done.emit(final_scene, history)

            # 判断是否成功：最后一轮无错误
            success = not history[-1]["errors"] if history else False

            # 管线末尾：更新经验使用统计 + 保存新经验
            if few_shots:
                for exp in few_shots:
                    bank.update_usage(exp["id"], success=success)
            if success:
                # 初始保存 rating=3 (占位), 用户在 UMAP 预览后通过 update_rating 更新真实评分
                exp_id = bank.save(user_desc, intent, final_scene, rating=3)
                self.log_line.emit('经验已保存到记忆库')
                # 通知 ChatPanel: exp_id 可用于后续评分更新
                if exp_id:
                    self.exp_saved.emit(exp_id)

            self.finished_signal.emit(final_scene, success, "生成完成")
        except Exception as e:
            logger.error("AI 生成管线异常: %s", e, exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            # 确保在任何路径下 SQLite 连接都被关闭
            if bank is not None:
                try:
                    bank.close()
                except Exception as e:
                    logger.debug("关闭 ExperienceBank 连接失败: %s", e)


# ============================================================================
# 星级评分控件: 5 颗星, 悬停预览 + 点击打分
# ============================================================================

class StarRating(QWidget):
    """星级评分控件: 5 颗星, 鼠标悬停预览 + 点击确认评分

    交互流程:
        1. 初始禁用 (set_enabled(False)), UMAP 生成后由外部启用
        2. 鼠标悬停时高亮预览 (1~N 颗金色 ★)
        3. 点击星星确认评分, 发射 rating_changed 信号

    信号:
        rating_changed(int): 用户点击星星后发射, 值 1~5
    """
    rating_changed = pyqtSignal(int)

    STAR_FULL = "★"
    STAR_EMPTY = "☆"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0       # 当前评分 (0=未评分)
        self._hover = 0        # 悬停预览数 (0=无悬停)
        self._max = 5          # 最大星数
        self._enabled = False  # 初始禁用, UMAP 生成后启用
        self.setMouseTracking(True)
        self.setFixedHeight(32)
        self.setMinimumWidth(140)
        # U10 修复: 键盘可操作 + 屏幕阅读器可读
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("UMAP 效果评分")
        self.setAccessibleDescription("1 到 5 星评分控件, 左右方向键调整, 回车确认")

    def rating(self) -> int:
        """返回当前评分 (0=未评分)"""
        return self._rating

    def set_rating(self, value: int):
        """程序化设置评分 (不发射信号)"""
        value = max(0, min(self._max, value))
        self._rating = value
        self.update()

    def set_enabled(self, enabled: bool):
        """启用/禁用评分交互"""
        self._enabled = enabled
        if not enabled:
            self._hover = 0
        self.update()

    def is_enabled(self) -> bool:
        return self._enabled

    def _star_font(self) -> QFont:
        """星星字体: Segoe UI Symbol 支持彩色 Unicode 星号"""
        return QFont("Segoe UI Symbol", 16)

    def paintEvent(self, event):
        """绘制 5 颗星: 已选/悬停=金色 ★, 未选=暗灰 ☆, 禁用=最暗"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self._star_font()
        painter.setFont(font)
        fm = QFontMetrics(font)
        star_w = fm.horizontalAdvance(self.STAR_FULL)
        gap = 4
        total_w = star_w * self._max + gap * (self._max - 1)
        x = max(0, (self.width() - total_w) / 2)
        y = (self.height() - fm.height()) / 2

        # 决定显示数量: 悬停时用 hover, 否则用 rating
        active = self._hover if self._hover > 0 else self._rating

        for i in range(self._max):
            idx = i + 1
            if not self._enabled:
                # 禁用: 全部暗灰
                color = QColor("#313244")
                star_char = self.STAR_FULL if idx <= self._rating else self.STAR_EMPTY
            elif idx <= active:
                # 已选/悬停: 金色 ★
                color = QColor("#f9e2af")
                star_char = self.STAR_FULL
            else:
                # 未选: 暗灰 ☆
                color = QColor("#585b70")
                star_char = self.STAR_EMPTY

            painter.setPen(color)
            painter.drawText(int(x), int(y + fm.ascent()), star_char)
            x += star_w + gap

    def mouseMoveEvent(self, event):
        """鼠标移动: 计算悬停的星星数量并更新预览"""
        if not self._enabled:
            return
        font = self._star_font()
        fm = QFontMetrics(font)
        star_w = fm.horizontalAdvance(self.STAR_FULL)
        gap = 4
        total_w = star_w * self._max + gap * (self._max - 1)
        start_x = max(0, (self.width() - total_w) / 2)
        pos_x = event.position().x() - start_x
        if pos_x < 0:
            hover = 0
        else:
            hover = int(pos_x / (star_w + gap)) + 1
        hover = max(0, min(self._max, hover))
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event):
        """鼠标离开: 清除悬停预览"""
        if self._hover != 0:
            self._hover = 0
            self.update()

    def mousePressEvent(self, event):
        """点击星星: 确认评分并发射信号"""
        if not self._enabled:
            return
        if self._hover > 0:
            self._rating = self._hover
            self.rating_changed.emit(self._hover)
            self.update()

    def keyPressEvent(self, event):
        """U10 修复: 键盘评分 (左/下减1, 右/上加1, 回车确认)"""
        if not self._enabled:
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._rating = max(0, self._rating - 1)
            self._hover = self._rating
            self.rating_changed.emit(self._rating)
            self.update()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._rating = min(self._max, self._rating + 1)
            self._hover = self._rating
            self.rating_changed.emit(self._rating)
            self.update()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._rating > 0:
                self.rating_changed.emit(self._rating)
        else:
            super().keyPressEvent(event)

    def sizeHint(self):
        return QSize(self._max * 24 + 16, 32)


# ============================================================================
# 方案三·暗室 UI 控件: 分段选择器 / 状态药丸 / 命令面板
# ============================================================================
class SegmentedControl(QWidget):
    """药丸形分段选择器: 替代 QTabBar 可见标签, 滑块渐变高亮 + 动画过渡

    专业感来源: macOS SegmentedControl / iOS UISegmentedControl
    激活段使用 #6d4aff→#9d8aff 渐变填充, 非激活段半透明文字,
    切换时滑块通过 QPropertyAnimation 平滑滑动到新位置。
    """

    currentChanged = pyqtSignal(int)

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self._items = list(items) if items else []
        self._current = 0
        self._slider_pos = 0.0
        self.setFixedHeight(34)
        self.setMinimumWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 滑块滑动动画: OutCubic 缓出, 220ms 自然手感
        self._anim = QPropertyAnimation(self, b"sliderPos")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getSliderPos(self):
        return self._slider_pos

    def setSliderPos(self, val):
        self._slider_pos = val
        self.update()

    sliderPos = pyqtProperty(float, getSliderPos, setSliderPos)

    def setItems(self, items):
        self._items = list(items)
        self.update()

    def setCurrentIndex(self, idx):
        if 0 <= idx < len(self._items) and idx != self._current:
            self._current = idx
            # 动画: 从当前位置滑到目标位置
            self._anim.stop()
            self._anim.setStartValue(self._slider_pos)
            self._anim.setEndValue(float(idx))
            self._anim.start()
            self.currentChanged.emit(idx)

    def currentIndex(self):
        return self._current

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        r = h / 2
        # 背景药丸: 极淡白色 (3.5% 不透明度), 与玻璃面板融合
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 9))
        painter.drawRoundedRect(0, 0, w, h, r, r)

        if not self._items:
            return

        n = len(self._items)
        seg_w = w / n
        # 滑块: 渐变填充, 3px 内边距让滑块不贴边
        slider_x = self._slider_pos * seg_w
        grad = QLinearGradient(slider_x, 0, slider_x + seg_w, h)
        grad.setColorAt(0, QColor("#6d4aff"))
        grad.setColorAt(1, QColor("#9d8aff"))
        painter.setBrush(QBrush(grad))
        margin = 3
        painter.drawRoundedRect(
            int(slider_x) + margin, margin,
            int(seg_w) - margin * 2, h - margin * 2,
            r - margin, r - margin)

        # 文字: 激活=白色加粗, 非激活=半透明
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.Medium))
        for i, label in enumerate(self._items):
            if i == self._current:
                painter.setPen(QColor("#ffffff"))
            else:
                painter.setPen(QColor(255, 255, 255, 130))
            painter.drawText(
                QRectF(i * seg_w, 0, seg_w, h),
                Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event):
        if self._items and event.button() == Qt.MouseButton.LeftButton:
            n = len(self._items)
            seg_w = self.width() / n
            idx = int(event.position().x() / seg_w)
            idx = max(0, min(n - 1, idx))
            self.setCurrentIndex(idx)

    def sizeHint(self):
        return QSize(220, 34)


class StatusPill(QWidget):
    """状态药丸: 彩色圆点 + 文本, 四种状态色

    状态色映射:
        idle    → 绿色 #6bc09b (就绪/空闲)
        working → 橙色 #fab387 (生成中)
        done    → 绿色 #6bc09b (完成)
        error   → 红色 #f38ba8 (错误)
    自绘圆点 + 文本, 背景为极淡白色药丸, 与玻璃面板融合。
    """

    STATE_COLORS = {
        "idle": QColor("#6bc09b"),
        "working": QColor("#fab387"),
        "done": QColor("#6bc09b"),
        "error": QColor("#f38ba8"),
    }

    def __init__(self, text="就绪", state="idle", parent=None):
        super().__init__(parent)
        self._text = text
        self._state = state
        self._dot_color = self.STATE_COLORS.get(state, QColor("#6bc09b"))
        self.setFixedHeight(24)
        self.setMinimumWidth(70)

    def setState(self, state, text=None):
        """更新状态: 同时更新圆点颜色, 可选更新文本"""
        self._state = state
        self._dot_color = self.STATE_COLORS.get(state, self._dot_color)
        if text is not None:
            self._text = text
        self.update()

    def setText(self, text):
        self._text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(self._text)
        dot_r = 3.5
        pad_x = 10
        gap = 6
        # 计算实际宽度: 圆点 + 间隙 + 文本 + 两侧 padding
        total_w = pad_x + dot_r * 2 + gap + text_w + pad_x
        w = max(self.width(), total_w)
        h = self.height()
        r = h / 2

        # 背景药丸: 极淡白色
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 8))
        # 暗室: total_w 含 dot_r(3.5 浮点)参与运算, 使 w 在文本较长(total_w 占优)时为 float;
        # drawRoundedRect 的 (x,y,w,h) int 重载不接受 float w → TypeError(最大化重排时触发,
        # 异常被全局 excepthook 捕获后退出进程, 表现为"崩溃")。改用 QRectF 重载规避类型陷阱。
        painter.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # 状态圆点
        dot_cx = pad_x + dot_r
        dot_cy = h / 2
        painter.setBrush(self._dot_color)
        painter.drawEllipse(QPointF(dot_cx, dot_cy), dot_r, dot_r)

        # 文字
        painter.setPen(QColor("#94a3b8"))
        painter.drawText(
            QRectF(dot_cx + dot_r + gap, 0, text_w + pad_x, h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._text)

    def sizeHint(self):
        return QSize(80, 24)


class CommandPalette(QDialog):
    """⌘K 命令面板: 搜索框 + 命令列表 + 快捷键标注, 实时模糊过滤

    交互: Ctrl+K 唤出 → 输入关键词过滤 → ↑↓ 选择 → Enter 执行 → Esc 关闭
    面板无边框 Popup 样式, 定位到父窗口顶部居中。
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setObjectName("commandPalette")
        self.setFixedWidth(400)
        self._commands = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 搜索框
        self._search = QLineEdit()
        self._search.setObjectName("cmdSearch")
        self._search.setPlaceholderText("输入命令名称...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)
        self._search.returnPressed.connect(self._execute_selected)
        layout.addWidget(self._search)

        # 命令列表
        self._list = QListWidget()
        self._list.setObjectName("cmdList")
        self._list.setMaximumHeight(280)
        self._list.itemClicked.connect(self._execute_selected)
        layout.addWidget(self._list)

        # Esc 快捷键关闭
        self._esc_sc = QShortcut(QKeySequence("Escape"), self)
        self._esc_sc.activated.connect(self.hide)

    def addCommand(self, name, callback, shortcut=""):
        self._commands.append((name, callback, shortcut))

    def show_palette(self):
        """填充列表 + 清空搜索 + 定位到父窗口顶部居中 + 显示"""
        self._populate("")
        self._search.clear()
        self._search.setFocus()
        if self.parent():
            pg = self.parent().geometry()
            x = pg.center().x() - self.width() // 2
            y = pg.y() + 56
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def _populate(self, query):
        self._list.clear()
        q = query.lower().strip()
        for idx, (name, callback, shortcut) in enumerate(self._commands):
            if not q or q in name.lower():
                item = QListWidgetItem()
                text = name
                if shortcut:
                    text += f"    {shortcut}"
                item.setText(text)
                item.setData(Qt.ItemDataRole.UserRole, idx)
                self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _filter(self, text):
        self._populate(text)

    def _execute_selected(self):
        """执行当前选中的命令并关闭面板"""
        item = self._list.currentItem()
        if item:
            idx = item.data(Qt.ItemDataRole.UserRole)
            if 0 <= idx < len(self._commands):
                _name, callback, _sc = self._commands[idx]
                self.hide()
                if callback:
                    callback()

    def keyPressEvent(self, event):
        # ↑↓ 键导航命令列表
        if event.key() == Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
        elif event.key() == Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(event)


# ============================================================================
# AI 对话面板: 聊天历史 + 输入框 + JSON 预览 + 审核按钮
# ============================================================================

class ChatPanel(QWidget):
    """AI 对话面板: 聊天历史 + 输入框 + JSON 预览 + 底部动作栏

    布局 (方案B · 三区分离):
      左栏 = 纯对话区 (聊天历史 + 输入框 + 进度条)
      右栏 = JSON 预览卡片 + 可折叠运行日志
      底部 = 通栏动作栏 (采纳 / 反馈 / 复制 JSON / 评分 / 打开 UE)
    交互: 输入自然语言 → AIWorker 后台生成 → JSON 预览 → 采纳/反馈
    """

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._worker = None
        self._last_scene = None
        self._umap_path = None
        self._exp_id = None        # AIWorker 保存经验后返回的 ID, 供后续 update_rating 使用
        self._init_ui()
        # 延迟连接 MainWindow 的 umap_ready 信号 (此时 MainWindow 可能尚未完成构建)
        # 通过 showEvent 在窗口显示时建立连接
        self._umap_signal_connected = False

    def _init_ui(self):
        """构建聊天面板 UI (方案B · 三区分离: 左对话 / 右JSON+日志 / 底部动作栏)"""
        # 根布局由水平改为垂直: 上方放左右分栏 splitter, 底部放通栏动作栏
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # 左栏: 纯对话区 (聊天历史 + 输入框 + 进度条)
        left = QVBoxLayout()
        left.setSpacing(10)

        # 聊天历史
        self._chat_history = QTextEdit()
        self._chat_history.setObjectName("chatHistory")
        self._chat_history.setReadOnly(True)
        # U7 修复: 欢迎语作为 placeholder 而非 append 写入聊天流, 避免与真实对话混杂
        self._chat_history.setPlaceholderText(
            "欢迎使用 AI 场景生成器。输入自然语言描述，例如:\n  生成一个1km的山谷草地场景，有河流和松树")
        left.addWidget(self._chat_history, 1)

        # 输入框 + 发送按钮（多行输入，最小高度 80px，Ctrl+Enter 发送）
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input = QTextEdit()
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText("描述你想要的场景...（Ctrl+Enter 发送）")
        self._input.setMinimumHeight(80)
        self._input.setMaximumHeight(120)
        self._input.setAcceptRichText(False)
        input_row.addWidget(self._input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.clicked.connect(self._on_send)
        # U11 修复: 发送按钮底对齐, 与多行输入框底部齐平而非垂直居中悬浮
        input_row.addWidget(self._send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        left.addLayout(input_row)

        # 安装事件过滤器，捕获 Ctrl+Enter 发送快捷键
        self._input.installEventFilter(self)

        # 进度条 (方案B: 留在左栏对话区底部, 指示 AI 生成进度)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        left.addWidget(self._progress)
        # 注: 运行日志已按方案B移至右栏 JSON 预览下方 (见 _init_ui 右栏部分)

        # 底部通栏动作栏 (方案B): 左半=采纳/反馈/复制JSON, 右半=评分/打开UE
        # 注: 此处仅创建, 在 splitter 挂载之后再 addLayout 到根布局底部
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)
        self._approve_btn = QPushButton("采纳并生成 umap")
        self._approve_btn.setObjectName("reviewBtn")
        self._approve_btn.clicked.connect(self._on_approve)
        self._approve_btn.setEnabled(False)
        self._approve_btn.setToolTip("将 AI 生成的场景 JSON 保存为文件并触发 UMAP 构建")
        action_bar.addWidget(self._approve_btn)

        self._reject_btn = QPushButton("反馈并重新生成")
        self._reject_btn.setObjectName("reviewBtn")
        self._reject_btn.clicked.connect(self._on_reject)
        self._reject_btn.setEnabled(False)
        self._reject_btn.setToolTip("将当前结果标记为不满意，使用原始描述重新生成")
        action_bar.addWidget(self._reject_btn)

        # 复制 JSON 按钮: 方便将场景 JSON 粘贴到外部编辑器调试
        self._copy_json_btn = QPushButton("复制 JSON")
        self._copy_json_btn.setObjectName("copyJsonBtn")
        self._copy_json_btn.clicked.connect(self._on_copy_json)
        self._copy_json_btn.setEnabled(False)
        self._copy_json_btn.setToolTip("将场景 JSON 复制到系统剪贴板")
        action_bar.addWidget(self._copy_json_btn)

        # 弹性空隙: 把审核类按钮推到左侧, 评分类控件推到右侧
        action_bar.addStretch()

        # 评分区: UMAP 生成并预览后启用, 用户打分后提交到经验库
        self._rating_hint = QLabel("预览 UMAP 效果后评分:")
        # U9 修复: 对比度 #585b70≈2.4:1 不达 WCAG AA; 改用 #a6adc8≈7.6:1 + objectName 交 QSS 管
        self._rating_hint.setObjectName("ratingHint")
        action_bar.addWidget(self._rating_hint)

        # 星级评分控件: 初始禁用, umap_ready 后启用
        self._star_rating = StarRating()
        self._star_rating.set_enabled(False)
        action_bar.addWidget(self._star_rating)

        # 提交评分按钮: 将星级评分写入经验库 (update_rating)
        self._submit_rating_btn = QPushButton("提交评分")
        self._submit_rating_btn.setObjectName("reviewBtn")
        self._submit_rating_btn.clicked.connect(self._on_submit_rating)
        self._submit_rating_btn.setEnabled(False)
        self._submit_rating_btn.setToolTip("将评分提交到经验库, 优化未来检索质量")
        action_bar.addWidget(self._submit_rating_btn)

        # 打开 UE 编辑器按钮（生成 umap 后显示, 位于动作栏最右端）
        self._open_ue_btn = QPushButton("在 UE 编辑器中打开")
        self._open_ue_btn.setObjectName("openUEBtn")
        self._open_ue_btn.clicked.connect(self._on_open_ue_editor)
        self._open_ue_btn.setVisible(False)
        self._open_ue_btn.setToolTip("启动 UE5 编辑器并加载刚生成的 UMAP 关卡")
        action_bar.addWidget(self._open_ue_btn)

        # 右侧: JSON 预览 (QScintilla 专业代码编辑器: 语法高亮 + 代码折叠 + 行号)
        # U8 修复: 右侧加标题标签, 空态占半屏不自解释的问题
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        json_title = QLabel("场景 JSON 预览")
        json_title.setObjectName("sectionLabel")
        right_layout.addWidget(json_title)

        self._json_editor = QsciScintilla()
        self._json_editor.setObjectName("jsonEditor")
        self._json_editor.setReadOnly(True)
        if HAS_QSCI:
            # QScintilla 专业配置: 语法高亮 + 代码折叠 + 行号边距
            # U15 修复: 空内容时 scrollWidth 归零, 消除无意义的横向滚动条
            self._json_editor.setScrollWidth(0)
            # 配置 JSON 语法 lexer (括号变色 + 字符串/数字/键名着色)
            json_lexer = QsciLexerJSON()
            self._json_editor.setLexer(json_lexer)
            # 启用代码折叠 (树形折叠图标)
            self._json_editor.setFolding(QsciScintilla.FoldStyle.BoxedTreeFoldStyle)
            # 行号边距
            self._json_editor.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
            self._json_editor.setMarginWidth(0, "40")
            self._json_editor.setMarginsForegroundColor(QColor("#585b70"))
            self._json_editor.setMarginsBackgroundColor(QColor("#11111b"))
            # 关键: setFolding 会新建一个折叠边距(margin 2), 其默认纸张色为白色,
            # 且 setMarginsBackgroundColor 不覆盖它 → 表现为编辑器左侧刺眼的白竖条。
            # 逐个把 0~3 号边距的背景色显式设为暗色, 彻底消除白条。
            self._json_editor.setMarginWidth(1, 0)          # 符号边距(margin 1)不需要, 宽度归零
            for _m in (0, 1, 2, 3):
                self._json_editor.setMarginBackgroundColor(_m, QColor("#11111b"))
            self._json_editor.setMarginWidth(2, 14)         # 折叠图标边距, 收窄到 14px 即可
            self._json_editor.setFoldMarginColors(QColor("#11111b"), QColor("#11111b"))  # 折叠线底色
            # 暗色主题适配 (Catppuccin Mocha 配色)
            font = QFont("Consolas", 10)
            self._json_editor.setFont(font)
            json_lexer.setFont(font)
            self._json_editor.setPaper(QColor("#11111b"))
            self._json_editor.setColor(QColor("#a6adc8"))
            json_lexer.setPaper(QColor("#11111b"))
            json_lexer.setColor(QColor("#a6adc8"))
            # JSON 语法元素配色: 键名蓝/字符串绿/数字橙/括号红
            for style_name, color_hex in [
                ("Keyword", "#89b4fa"),    # JSON 关键字
                ("String", "#a6e3a1"),     # 字符串
                ("Number", "#fab387"),     # 数字
                ("Operator", "#f38ba8"),   # 括号/冒号/逗号
                ("Property", "#89b4fa"),  # 键名
                ("Comment", "#585b70"),   # 注释
            ]:
                style_val = getattr(QsciLexerJSON, style_name, None)
                if style_val is not None:
                    json_lexer.setColor(QColor(color_hex), style_val)
        else:
            # 降级模式: QPlainTextEdit 基本样式 (无语法高亮/折叠/行号)
            font = QFont("Consolas", 10)
            self._json_editor.setFont(font)
            self._json_editor.setStyleSheet(
                "background-color: #11111b; color: #a6adc8; border: none;")

        # ★ 核心修复: JSON 编辑器此前只创建未挂载, 成为游离于窗口外的孤儿控件,
        #   导致生成 JSON 后 setText 写入了一个不可见控件 → 右栏永远空白。
        #   现将其加入右栏布局并给 stretch=1, 使其占满标题以下的全部空间。
        right_layout.addWidget(self._json_editor, 1)

        # 运行日志 (方案B: 从原左栏移至右栏 JSON 预览下方)
        # U3 修复保留: checkable 标题按钮兑现"可折叠", 默认展开 (用户选定维持现状)
        self._log_toggle_btn = QPushButton("▼ 运行日志")
        self._log_toggle_btn.setObjectName("logToggleBtn")
        self._log_toggle_btn.setCheckable(True)
        self._log_toggle_btn.setChecked(True)
        self._log_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_toggle_btn.toggled.connect(self._on_log_toggle)
        right_layout.addWidget(self._log_toggle_btn)

        self._log = QTextEdit()
        self._log.setObjectName("chatLog")
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        right_layout.addWidget(self._log)

        # 用 Splitter 分割左右两栏 (右栏现在有了可扩展的 JSON 编辑器, 比例才真正生效)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_widget.setLayout(left)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 480])      # 右栏略宽, 给 JSON 预览更多展示空间
        layout.addWidget(splitter, 1)      # stretch=1: splitter 占据动作栏以外的全部高度

        # 通栏动作栏挂载到窗口底部 (方案B: 采纳/反馈/复制/评分/打开UE 一行排开)
        layout.addLayout(action_bar)

    def _on_send(self):
        """发送按钮回调：获取输入文本，启动生成"""
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._append_chat(f"[用户] {text}")
        self._input.clear()
        self._start_generation(text)

    def eventFilter(self, obj, event):
        """事件过滤器：捕获 Ctrl+Enter 发送快捷键 (QEvent/Qt 已在文件顶部统一导入)"""
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._on_send()
                return True
        return super().eventFilter(obj, event)

    def _on_log_toggle(self, checked):
        """U3 修复: 运行日志折叠/展开, 同步按钮箭头方向"""
        self._log.setVisible(checked)
        self._log_toggle_btn.setText("▼ 运行日志" if checked else "▶ 运行日志")

    def _start_generation(self, user_desc, feedback=None):
        """启动 AI 生成线程

        根据 llm_profile 配置创建对应 LLM 客户端，然后启动 AIWorker。
        """
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._send_btn.setEnabled(False)

        # 重置评分状态: 新一轮生成开始, 清除上一轮的评分和 exp_id
        self._exp_id = None
        self._star_rating.set_rating(0)
        self._star_rating.set_enabled(False)
        self._submit_rating_btn.setEnabled(False)
        self._copy_json_btn.setEnabled(False)

        # 保存原始用户描述，供反馈重试时使用（_on_send 已清空输入框）
        self._last_user_desc = user_desc

        # 根据 profile 创建 LLM 客户端
        profile = self._config.get("llm_profile", "openai")
        if profile == "mock":
            # Mock 模式：传入预设的意图+场景 JSON，保证管线端到端可用
            client = MockLLMClient([_MOCK_INTENT, _MOCK_SCENE])
        elif profile == "ollama":
            client = OllamaLLMClient(
                host=self._config.get("ollama_host", "http://localhost:11434"),
                model=self._config.get("llm_model", "glm-5.2")
            )
        else:
            # API Key 支持 ${VAR_NAME} 环境变量引用，运行时从 os.environ 解析
            raw_key = self._config.get("llm_api_key", "")
            api_key = resolve_env_value(raw_key)
            client = OpenAILLMClient(
                api_key=api_key,
                model=self._config.get("llm_model", "glm-5.2"),
                base_url=self._config.get("llm_base_url", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
            )

        # 创建并启动后台线程，连接信号
        self._worker = AIWorker(client, self._config, user_desc, feedback)
        self._worker.log_line.connect(self._on_log)
        self._worker.intent_parsed.connect(self._on_intent)
        self._worker.json_generated.connect(self._on_json)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.error_occurred.connect(self._on_error)
        # 经验保存完成信号: 接收 exp_id, 供后续评分提交时调用 update_rating
        self._worker.exp_saved.connect(self._on_exp_saved)
        self._worker.start()

    def _on_log(self, line):
        """日志行追加"""
        self._log.append(line)

    def _append_chat(self, msg):
        """统一追加聊天历史，自动加时间戳前缀 [HH:MM:SS]

        所有 [用户]/[意图]/[AI]/[错误]/[系统] 标签信息都走此方法,
        便于统一管理格式和后续扩展(如颜色/过滤)
        """
        ts = time.strftime("%H:%M:%S")
        self._chat_history.append(f"[{ts}] {msg}")

    def _on_intent(self, intent):
        """意图解析完成回调"""
        self._append_chat(f"[意图] {json.dumps(intent, ensure_ascii=False)[:200]}")
        self._progress.setValue(33)

    def _on_json(self, scene):
        """JSON 生成完成回调：显示到右侧 QScintilla 编辑器"""
        self._json_editor.setText(json.dumps(scene, ensure_ascii=False, indent=2))
        self._progress.setValue(66)

    def _on_finished(self, scene, success, message):
        """生成全部完成回调"""
        self._last_scene = scene
        self._progress.setValue(100)
        self._progress.setVisible(False)
        self._send_btn.setEnabled(True)
        self._approve_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        # JSON 生成完毕, 启用复制按钮
        self._copy_json_btn.setEnabled(True)
        status = "✅ 成功" if success else "⚠️ 有错误，请审核"
        self._append_chat(f"[AI] {message} ({status})")

    def _on_error(self, msg):
        """异常回调"""
        self._progress.setVisible(False)
        self._send_btn.setEnabled(True)
        self._append_chat(f"[错误] {msg}")

    def _on_approve(self):
        """采纳按钮回调：保存 JSON 到临时文件，切换到构建 Tab 并触发 umap 构建"""
        if not self._last_scene:
            return
        try:
            # 重置评分状态: 新一轮 umap 构建开始, 旧评分已失效
            self._star_rating.set_rating(0)
            self._star_rating.set_enabled(False)
            self._submit_rating_btn.setEnabled(False)

            # 将场景 JSON 保存到临时文件，供 build_scene.py 使用
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            )
            json.dump(self._last_scene, tmp, ensure_ascii=False, indent=2)
            tmp.close()

            # 获取主窗口引用，设置场景文件并触发 umap 构建
            mw = self.window()
            # 关键: 必须通过分段控件切换(而非直接 _tabs.setCurrentIndex), 否则
            # 分段控件滑块仍停在"AI 生成"档, 与实际显示的"构建 UMAP"内容不一致。
            # setCurrentIndex(0) 会动画滑块到"构建 UMAP" 并 emit currentChanged,
            # 由 _on_segment_changed 同步驱动 _tabs 内容切换, 滑块/内容一致。
            if hasattr(mw, "_segmented"):
                mw._segmented.setCurrentIndex(0)
            elif hasattr(mw, "_tabs"):
                mw._tabs.setCurrentIndex(0)
            # 关键修复: 切换到构建 Tab 后必须调用 _on_file_selected 刷新
            # "上传场景文件"区域(DropArea 提示文本 + scene_info_label 场景信息
            # + 启用生成按钮), 否则 UI 仍显示上一个文件或"未选择文件"。
            # _on_file_selected 内部会设置 scene_file、解析场景、更新显示。
            if hasattr(mw, "_on_file_selected"):
                mw._on_file_selected(tmp.name)

            self._append_chat("[用户] 已采纳，开始生成 umap...")
            # 隐藏 Open UE 按钮（新构建开始，旧 umap 已失效）
            self._open_ue_btn.setVisible(False)

            if hasattr(mw, "_on_generate"):
                mw._on_generate()
        except Exception as e:
            self._append_chat(f"[错误] 保存场景 JSON 失败: {e}")

    def showEvent(self, event):
        """窗口显示时延迟连接 MainWindow 的 umap_ready 信号

        构造时 MainWindow 可能尚未完成初始化, 在 showEvent 中建立信号连接更安全
        """
        if not self._umap_signal_connected:
            mw = self.window()
            if mw is not None and hasattr(mw, "umap_ready"):
                mw.umap_ready.connect(self._on_umap_ready)
                self._umap_signal_connected = True
        super().showEvent(event)

    def _on_umap_ready(self, umap_path):
        """MainWindow umap_ready 信号的槽函数: UMAP 生成完成后被调用

        替代原 QTimer 轮询方案, 遵循 Qt 信号驱动设计模式, 无 CPU 空转
        """
        if umap_path and os.path.isfile(umap_path):
            self._umap_path = umap_path
            self._open_ue_btn.setVisible(True)
            # UMAP 已生成, 启用评分控件: 用户可在 UE 预览后进行打分
            self._star_rating.set_enabled(True)
            self._submit_rating_btn.setEnabled(True)
            self._append_chat("[系统] UMAP 已生成，请在 UE 编辑器中预览效果后评分")

    def _on_open_ue_editor(self):
        """打开 UE 编辑器并加载当前生成的 UMAP"""
        mw = self.window()
        umap = self._umap_path or getattr(mw, "umap_path", "")
        if not umap or not os.path.isfile(umap):
            QMessageBox.critical(self, "错误", "UMAP 文件不存在:\n" + umap)
            return
        # 委托给 MainWindow 的统一打开逻辑
        if hasattr(mw, "_on_open_ue_editor"):
            mw._on_open_ue_editor()

    def _on_exp_saved(self, exp_id):
        """AIWorker 经验保存完成回调: 保存 exp_id 供后续评分更新使用"""
        self._exp_id = exp_id

    def _on_copy_json(self):
        """复制 JSON 按钮: 将当前场景 JSON 复制到系统剪贴板"""
        if not self._last_scene:
            return
        from PyQt6.QtWidgets import QApplication
        text = json.dumps(self._last_scene, ensure_ascii=False, indent=2)
        QApplication.clipboard().setText(text)
        self._append_chat("[系统] 场景 JSON 已复制到剪贴板")

    def _on_submit_rating(self):
        """提交评分按钮: 将用户星级评分写入经验库 (update_rating)

        流程:
            1. AIWorker 初始保存经验时 rating=3 (占位)
            2. UMAP 生成后, 用户在 UE 预览效果
            3. 用户点击星星评分, 再点「提交评分」按钮
            4. 本方法调用 bank.update_rating(exp_id, rating) 更新真实评分
        """
        rating = self._star_rating.rating()
        if rating <= 0:
            QMessageBox.information(self, "提示", "请先点击星星选择评分 (1~5 分)")
            return
        if not self._exp_id:
            QMessageBox.warning(self, "提示", "经验 ID 不存在，无法提交评分")
            return
        try:
            bank = ExperienceBank()
            bank.update_rating(self._exp_id, rating)
            self._append_chat(f"[系统] 评分 {rating} 星已提交到经验库")
            # 提交后禁用, 防止重复提交
            self._submit_rating_btn.setEnabled(False)
            self._star_rating.set_enabled(False)
        except Exception as e:
            self._append_chat(f"[错误] 提交评分失败: {e}")

    def _on_reject(self):
        """反馈按钮回调：使用保存的原始描述重新生成"""
        self._reject_btn.setEnabled(False)
        # 使用 _start_generation 中保存的原始描述，而非输入框文本（此时输入框已被 _on_send 清空）
        desc = getattr(self, "_last_user_desc", "") or self._input.text().strip() or "重新生成"
        self._start_generation(desc, feedback="不满意")


# ============================================================================
# LLM 设置对话框
# ============================================================================

class SettingsDialog(QDialog):
    """LLM 设置对话框: profile 切换 + API key/model/base_url"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("LLM 设置")
        self._init_ui()

    def _init_ui(self):
        """构建表单布局"""
        layout = QFormLayout(self)

        # Profile 切换（mock / openai / ollama）
        self._llm_profile = QComboBox()
        self._llm_profile.addItems(["mock", "openai", "ollama"])
        self._llm_profile.setCurrentText(self._config.get("llm_profile", "openai"))
        self._llm_profile.currentTextChanged.connect(self._on_profile_changed)
        layout.addRow("Profile:", self._llm_profile)

        # API key（密码模式，防止泄露）
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setText(self._config.get("llm_api_key", ""))
        self._api_key.setPlaceholderText("直接输入或 ${ALIYUN_APIKEY}")
        layout.addRow("API Key:", self._api_key)

        # Model（下拉可选阿里云模型，也可手动输入自定义模型名）
        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.addItems(ALIYUN_MODELS)
        # 设置当前模型：若配置中的模型在列表内则选中，否则填入自定义模型名
        current_model = self._config.get("llm_model", "glm-5.2")
        if current_model in ALIYUN_MODELS:
            self._model.setCurrentText(current_model)
        else:
            self._model.setEditText(current_model)
        layout.addRow("Model:", self._model)

        # Base URL
        self._base_url = QLineEdit()
        self._base_url.setText(self._config.get("llm_base_url", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"))
        layout.addRow("Base URL:", self._base_url)

        # Ollama host
        self._ollama_host = QLineEdit()
        self._ollama_host.setText(self._config.get("ollama_host", "http://localhost:11434"))
        layout.addRow("Ollama Host:", self._ollama_host)

        # 强模型 / 意图模型（可选，留空则同默认 model）
        self._strong_model = QLineEdit()
        self._strong_model.setText(self._config.get("llm_strong_model", ""))
        self._strong_model.setPlaceholderText("留空则同默认 model")
        layout.addRow("强模型(可选):", self._strong_model)

        self._intent_model = QLineEdit()
        self._intent_model.setText(self._config.get("llm_intent_model", ""))
        self._intent_model.setPlaceholderText("留空则同默认 model")
        layout.addRow("意图模型(可选):", self._intent_model)

        # 保存 / 取消按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

        # 初始化字段启用状态
        self._on_profile_changed(self._llm_profile.currentText())

    def _on_profile_changed(self, profile):
        """profile 切换时启用/禁用对应字段"""
        is_mock = (profile == "mock")
        is_ollama = (profile == "ollama")
        # mock 和 ollama 模式不需要 API key 和 base_url
        self._api_key.setEnabled(not is_mock and not is_ollama)
        self._base_url.setEnabled(not is_mock and not is_ollama)
        # mock 模式不需要 model
        self._model.setEnabled(not is_mock)
        # ollama 模式需要 host
        self._ollama_host.setEnabled(is_ollama)

    def _on_save(self):
        """保存配置到 ~/.uescenefactory_config.json"""
        cfg = self._config.copy()
        cfg["llm_profile"] = self._llm_profile.currentText()
        cfg["llm_api_key"] = self._api_key.text()
        cfg["llm_model"] = self._model.currentText()
        cfg["llm_base_url"] = self._base_url.text()
        cfg["ollama_host"] = self._ollama_host.text()
        cfg["llm_strong_model"] = self._strong_model.text()
        cfg["llm_intent_model"] = self._intent_model.text()

        # 使用统一的 save_config 函数写入，它已内置 try/except 异常处理
        save_config(cfg)

        self._config.update(cfg)
        self.accept()


# ============================================================================
# 主窗口: 组装所有 UI 组件
# ============================================================================

# QSS 暗色主题样式
DARK_THEME = """
/* ===== 基础面: 统一深蓝紫底色, 消除与面板色相冲突的割裂感 ===== */
QMainWindow { background-color: #1e1e2e; }
/* 标签页容器: 显式指定 pane 与 tab 背景, 避免回落到系统默认灰底(原配色不协调的根因) */
QTabWidget { background-color: #1e1e2e; border: none; }
QTabWidget::pane { border: none; background-color: #1e1e2e; }
QTabBar::tab {
    background-color: #181825; color: #a6adc8;
    padding: 8px 20px; border: none; font-size: 13px;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected { background-color: #313244; color: #cdd6f4; font-weight: bold; }
QTabBar::tab:hover:!selected { background-color: #262637; color: #cdd6f4; }

QLabel { color: #cdd6f4; font-size: 13px; }
QLabel#titleLabel { font-size: 20px; font-weight: bold; color: #89b4fa; }
QLabel#sectionLabel { font-size: 14px; font-weight: bold; color: #89b4fa; }
QLabel#infoLabel { color: #a6adc8; font-size: 12px; }
/* 状态标签: 用中性主文字色, 语义交由前缀 emoji(✅/❌/️) 表达, 去掉额外橙色强调以免杂乱 */
QLabel#statusLabel { font-size: 13px; color: #cdd6f4; font-weight: bold; }

/* ===== 按钮: 全局仅保留一个蓝色强调色用于主操作, 次级操作走中性面+描边 ===== */
QPushButton {
    background-color: #89b4fa; color: #11111b; border: none;
    padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: bold;
}
QPushButton:hover { background-color: #a6c4fb; }
QPushButton:pressed { background-color: #74a8fc; }
QPushButton:disabled { background-color: #262637; color: #6c7086; }
/* 主操作按钮(生成/下载): 统一为蓝色强调填充, 取代原先冲突的粉绿+粉黄双色 */
QPushButton#generateBtn { background-color: #89b4fa; font-size: 15px; padding: 12px 24px; }
QPushButton#generateBtn:hover { background-color: #a6c4fb; }
QPushButton#generateBtn:disabled { background-color: #262637; color: #6c7086; }
QPushButton#downloadBtn { background-color: #89b4fa; color: #11111b; font-size: 13px; font-weight: bold; padding: 10px 16px; border-radius: 6px; }
QPushButton#downloadBtn:hover { background-color: #a6c4fb; }
QPushButton#downloadBtn:disabled { background-color: #262637; color: #6c7086; }
QPushButton#browseBtn { padding: 6px 12px; font-size: 12px; }

/* 进度条: 深色轨道 + 蓝色强调填充, 与主按钮呼应 */
QProgressBar {
    border: 1px solid #45475a; border-radius: 6px; text-align: center;
    background-color: #181825; color: #cdd6f4; min-height: 28px;
    font-size: 13px; font-weight: bold;
}
QProgressBar::chunk { background-color: #89b4fa; border-radius: 5px; }

/* 日志区: 最深一档底色, 形成内凹的阅读区 */
QPlainTextEdit {
    background-color: #11111b; color: #a6adc8;
    border: 1px solid #313244; border-radius: 6px;
    font-family: Consolas, 'Courier New', monospace; font-size: 12px;
}
/* 拖放区: 中性内凹面, 悬停时点亮强调色描边 */
QFrame#dropArea {
    border: 2px dashed #45475a; border-radius: 10px; background-color: #262637;
}
QFrame#dropArea:hover { border-color: #89b4fa; background-color: #2e2e44; }
/* 拖拽进行中: 属性式高亮 (替代内联 setStyleSheet, 避免覆盖全局 QSS) */
QFrame#dropArea[dragHover="true"] { border-color: #89b4fa; background-color: #2e2e44; }
QLineEdit {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 4px; padding: 6px; font-size: 12px;
}
QLineEdit:focus { border-color: #89b4fa; }
QGroupBox {
    color: #89b4fa; border: 1px solid #313244; border-radius: 6px;
    margin-top: 14px; padding-top: 14px; font-weight: bold; font-size: 13px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
/* 下拉框: 与输入框风格统一, 避免默认 Windows 控件破坏暗色主题一致性 */
QComboBox {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 6px 28px 6px 10px; font-size: 12px; min-height: 22px;
}
QComboBox:hover { border-color: #89b4fa; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid #a6adc8;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 4px;
    selection-background-color: #89b4fa; selection-color: #11111b;
    outline: none; padding: 4px;
}
/* 滚动条: 暗色细条风格, 与日志区背景融合, 不抢视觉焦点 */
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 0; border: none;
}
QScrollBar::handle:vertical {
    background: #45475a; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
/* 横向滚动条: 同样暗色细条风格 (QScintilla JSON 编辑器底部会出现) */
QScrollBar:horizontal {
    background: transparent; height: 10px; margin: 0; border: none;
}
QScrollBar::handle:horizontal {
    background: #45475a; border-radius: 5px; min-width: 30px;
}
QScrollBar::handle:horizontal:hover { background: #585b70; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
/* 卡片容器: 略深于窗口底色的中性面, 形成层次但不引入新色相 */
QFrame#card {
    background-color: #181825; border: 1px solid #313244;
    border-radius: 10px;
}
/* 方案C 左侧栏: 独立面板底色, 与右主区(窗口底色)形成左右分区 */
QFrame#sidebar {
    background-color: #181825; border: 1px solid #313244;
    border-radius: 10px;
}
/* 方案C 最近文件悬浮弹窗: 卡片式浮层, 带描边与圆角, 脱离布局悬浮显示 */
QWidget#recentPopup {
    background-color: #181825; border: 1px solid #45475a;
    border-radius: 8px;
}
/* 最近文件/运行日志折叠按钮: 次级操作风格, 左对齐, 与卡片底色区分 */
QPushButton#recentToggleBtn, QPushButton#logToggleBtn {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 8px 12px; font-size: 13px; text-align: left;
}
QPushButton#recentToggleBtn:hover, QPushButton#logToggleBtn:hover { border-color: #89b4fa; background-color: #3a3a52; }
QPushButton#recentToggleBtn:checked, QPushButton#logToggleBtn:checked { border-color: #89b4fa; background-color: #3a3a52; }
/* U9 修复: 评分提示对比度 #a6adc8≈7.6:1 达 WCAG AA */
QLabel#ratingHint { color: #a6adc8; font-size: 12px; }
/* U8 修复: JSON 预览区标题 */
QLabel#sectionLabel { color: #cdd6f4; font-size: 13px; font-weight: bold; padding: 2px 0; }
/* 最近文件内联列表: 展开时显示在卡片内部, 不悬浮遮挡其他控件 */
QListWidget#recentList {
    background-color: #11111b; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    font-size: 12px; padding: 4px; outline: none;
}
QListWidget#recentList::item { padding: 5px 8px; border-radius: 4px; }
QListWidget#recentList::item:hover { background-color: #313244; }
QListWidget#recentList::item:selected { background-color: #89b4fa; color: #11111b; }
/* 转换历史列表: 侧栏底部双行条目, 选中用深底+左蓝边避免子控件文字被亮底覆盖 */
QListWidget#historyList {
    background-color: #11111b; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 6px;
    font-size: 12px; padding: 4px; outline: none;
}
QListWidget#historyList::item { padding: 2px 4px; border-radius: 4px; }
QListWidget#historyList::item:hover { background-color: #313244; }
QListWidget#historyList::item:selected { background-color: #45475a; border-left: 3px solid #89b4fa; }
/* 历史详情条: 固定在列表下方, 显示选中条目的元信息 */
QFrame#historyDetail {
    background-color: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-left: 3px solid #89b4fa;
    border-radius: 4px; padding: 6px 8px;
}
QLabel#historyDetailTitle { color: #cdd6f4; font-size: 12px; font-weight: bold; }
QLabel#historyDetailMeta { color: #a6adc8; font-size: 11px; }
QLabel#historyDetailPath { color: #94a3b8; font-size: 10px; }
QLabel#historyStatsLabel { color: #a6adc8; font-size: 11px; padding: 2px 0; }
/* 打开目录按钮: 次级操作按钮风格(中性面+描边, 不抢主按钮焦点) */
QPushButton#openFolderBtn {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 10px 16px; font-size: 13px; font-weight: bold;
}
QPushButton#openFolderBtn:hover { border-color: #89b4fa; background-color: #3a3a52; }
QPushButton#openFolderBtn:disabled { background-color: #181825; color: #45475a; border: none; }
/* 打开 UE 编辑器按钮: 绿色强调操作, 语义与构建/下载区分, 表示"外部启动" */
QPushButton#openUEBtn {
    background-color: #6bc09b; color: #11111b; border: none;
    padding: 10px 16px; border-radius: 6px; font-size: 13px; font-weight: bold;
}
QPushButton#openUEBtn:hover { background-color: #7cd4af; }
QPushButton#openUEBtn:disabled { background-color: #262637; color: #6c7086; }
/* AI 聊天区: 历史记录与输入框, 使用略深底色形成对话气泡区的视觉聚焦 */
QTextEdit#chatHistory {
    background-color: #181825; color: #cdd6f4;
    border: 1px solid #313244; border-radius: 8px;
    font-size: 13px; padding: 8px;
}
QTextEdit#chatLog {
    background-color: #11111b; color: #a6adc8;
    border: 1px solid #313244; border-radius: 6px;
    font-size: 12px; padding: 6px;
}
/* QScintilla JSON 编辑器: 最深底色, 边框与整体暗色主题统一 */
QsciScintilla#jsonEditor {
    border: 1px solid #313244; border-radius: 8px;
}
/* 复制 JSON 按钮: 独立强调色, 区分于审核操作 */
QPushButton#copyJsonBtn {
    background-color: #313244; color: #89b4fa;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 8px 16px; font-size: 13px;
}
QPushButton#copyJsonBtn:hover { border-color: #89b4fa; background-color: #3a3a52; }
QPushButton#copyJsonBtn:disabled { background-color: #181825; color: #45475a; border-color: #313244; }
QTextEdit#chatInput {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 8px 12px; font-size: 13px;
}
QTextEdit#chatInput:focus { border-color: #89b4fa; }
/* 审核按钮: 中性面+描边风格, 与主操作按钮区分层次 */
QPushButton#reviewBtn {
    background-color: #313244; color: #cdd6f4;
    border: 1px solid #45475a; border-radius: 6px;
    padding: 8px 16px; font-size: 13px; font-weight: bold;
}
QPushButton#reviewBtn:hover { border-color: #89b4fa; background-color: #3a3a52; }
QPushButton#reviewBtn:disabled { background-color: #181825; color: #45475a; border-color: #313244; }
"""


# ============================================================================
# 暗室主题 QSS (DARKROOM_THEME)
# ----------------------------------------------------------------------------
# 设计语言: 深底(#0a0b0f) + 玻璃面板(rgba 半透明) + 紫蓝渐变(#6d4aff→#9d8aff)
# 核心策略: QMainWindow/QTabWidget/页面容器全部透明, 让 paintEvent 绘制的
#           Mesh 径向渐变光斑从底层透出, 玻璃面板悬浮其上形成纵深空间感。
# ============================================================================
DARKROOM_THEME = """
/* ===== 基础层: 全透明, 让 paintEvent 的 Mesh 渐变透出 ===== */
QMainWindow { background: transparent; }
QTabWidget { background: transparent; border: none; }
QTabWidget::pane { border: none; background: transparent; }
QTabWidget::tab-bar { height: 0px; }
QTabBar { background: transparent; }
QTabBar::tab { height: 0px; padding: 0px; margin: 0px; border: none; background: transparent; }

/* ===== 全局文字: 冷调白 + 降饱色, 与深底形成专业对比 ===== */
QLabel { color: #e2e8f0; font-size: 13px; background: transparent; }
QLabel#titleLabel { font-size: 20px; font-weight: bold; color: transparent; }
QLabel#sectionLabel { font-size: 14px; font-weight: bold; color: #a78bfa; background: transparent; }
QLabel#infoLabel { color: #94a3b8; font-size: 12px; }
QLabel#statusLabel { font-size: 13px; color: #e2e8f0; font-weight: bold; }

/* ===== 玻璃面板: 半透明底色 + 细描边, 配合 QGraphicsDropShadowEffect 浮动阴影 ===== */
QFrame#card {
    background-color: rgba(20, 20, 28, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
}
QFrame#sidebar {
    background-color: rgba(20, 20, 28, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
}

/* ===== 按钮: 中性次级面 + 紫蓝渐变主操作 ===== */
QPushButton {
    background-color: rgba(255, 255, 255, 0.05); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 8px 16px; border-radius: 10px; font-size: 13px;
}
QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); border-color: rgba(255, 255, 255, 0.15); }
QPushButton:pressed { background-color: rgba(255, 255, 255, 0.03); }
QPushButton:disabled { background-color: rgba(255, 255, 255, 0.02); color: #475569; border-color: rgba(255, 255, 255, 0.03); }
/* 主操作按钮: 紫蓝渐变填充 */
QPushButton#generateBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d4aff, stop:1 #9d8aff);
    color: #ffffff; border: none; font-size: 15px; padding: 12px 24px; border-radius: 10px;
}
QPushButton#generateBtn:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c5aff, stop:1 #ad9aff); }
QPushButton#generateBtn:pressed { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5e3aff, stop:1 #8d7aff); }
QPushButton#generateBtn:disabled { background-color: rgba(255, 255, 255, 0.05); color: #475569; border: none; }
QPushButton#downloadBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d4aff, stop:1 #9d8aff);
    color: #ffffff; border: none; font-size: 13px; font-weight: bold; padding: 10px 16px; border-radius: 10px;
}
QPushButton#downloadBtn:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c5aff, stop:1 #ad9aff); }
QPushButton#downloadBtn:disabled { background-color: rgba(255, 255, 255, 0.05); color: #475569; border: none; }
QPushButton#browseBtn { padding: 6px 12px; font-size: 12px; }

/* ===== 进度条: 玻璃轨道 + 渐变填充 ===== */
QProgressBar {
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px; text-align: center;
    background-color: rgba(255, 255, 255, 0.03); color: #e2e8f0; min-height: 28px;
    font-size: 13px; font-weight: bold;
}
QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d4aff, stop:1 #9d8aff); border-radius: 9px; }

/* ===== 日志区: 深底内凹阅读区 ===== */
QPlainTextEdit {
    background-color: rgba(10, 11, 15, 0.6); color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px;
    font-family: Consolas, 'Courier New', monospace; font-size: 12px;
}

/* ===== 拖放区: 虚线描边玻璃面, 悬停点亮紫光 ===== */
QFrame#dropArea {
    border: 2px dashed rgba(255, 255, 255, 0.12); border-radius: 12px;
    background-color: rgba(255, 255, 255, 0.02);
}
QFrame#dropArea:hover { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.08); }
QFrame#dropArea[dragHover="true"] { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.12); }

/* ===== 输入框: 玻璃面 + 聚焦紫光 ===== */
QLineEdit {
    background-color: rgba(255, 255, 255, 0.03); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 6px; font-size: 12px;
}
QLineEdit:focus { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.05); }
QGroupBox {
    color: #a78bfa; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px;
    margin-top: 14px; padding-top: 14px; font-weight: bold; font-size: 13px; background: transparent;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
/* 下拉框: 玻璃面统一, 弹出层用纯色底 */
QComboBox {
    background-color: rgba(255, 255, 255, 0.05); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
    padding: 6px 28px 6px 10px; font-size: 12px; min-height: 22px;
}
QComboBox:hover { border-color: #6d4aff; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 6px solid #94a3b8;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #15161c; color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
    selection-background-color: #6d4aff; selection-color: #ffffff;
    outline: none; padding: 4px;
}
/* 滚动条: 细条暗色, 不抢焦点 */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.1); border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: rgba(255, 255, 255, 0.2); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: rgba(255, 255, 255, 0.1); border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: rgba(255, 255, 255, 0.2); }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
/* 暗室: 侧栏按需滚动容器 —— 滚动区自身/viewport/内容控件全透明, 玻璃背景由外层 #sidebar 承担 */
QScrollArea#sideScroll { background: transparent; border: none; }
QScrollArea#sideScroll > QWidget,
QScrollArea#sideScroll > QWidget > QWidget { background: transparent; }
/* 最近文件悬浮弹窗: 纯色卡片浮层 */
QWidget#recentPopup {
    background-color: #15161c; border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
}
/* 折叠按钮: 中性次级风格 */
QPushButton#recentToggleBtn, QPushButton#logToggleBtn {
    background-color: rgba(255, 255, 255, 0.03); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
    padding: 8px 12px; font-size: 13px; text-align: left;
}
QPushButton#recentToggleBtn:hover, QPushButton#logToggleBtn:hover { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.08); }
QPushButton#recentToggleBtn:checked, QPushButton#logToggleBtn:checked { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.12); }
QLabel#ratingHint { color: #94a3b8; font-size: 12px; }
/* 最近文件内联列表 */
QListWidget#recentList {
    background-color: rgba(10, 11, 15, 0.6); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
    font-size: 12px; padding: 4px; outline: none;
}
QListWidget#recentList::item { padding: 5px 8px; border-radius: 4px; }
QListWidget#recentList::item:hover { background-color: rgba(255, 255, 255, 0.05); }
QListWidget#recentList::item:selected { background-color: #6d4aff; color: #ffffff; }
/* 转换历史列表: 选中用深底+左紫边 */
QListWidget#historyList {
    background-color: rgba(10, 11, 15, 0.6); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
    font-size: 12px; padding: 4px; outline: none;
}
QListWidget#historyList::item { padding: 2px 4px; border-radius: 4px; }
QListWidget#historyList::item:hover { background-color: rgba(255, 255, 255, 0.05); }
QListWidget#historyList::item:selected { background-color: rgba(255, 255, 255, 0.08); border-left: 3px solid #6d4aff; }
/* 历史详情条 */
QFrame#historyDetail {
    background-color: rgba(10, 11, 15, 0.6); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.06); border-left: 3px solid #6d4aff;
    border-radius: 8px; padding: 6px 8px;
}
QLabel#historyDetailTitle { color: #e2e8f0; font-size: 12px; font-weight: bold; }
QLabel#historyDetailMeta { color: #94a3b8; font-size: 11px; }
QLabel#historyDetailPath { color: #64748b; font-size: 10px; }
QLabel#historyStatsLabel { color: #94a3b8; font-size: 11px; padding: 2px 0; }
/* 打开目录按钮: 中性次级 */
QPushButton#openFolderBtn {
    background-color: rgba(255, 255, 255, 0.05); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
    padding: 10px 16px; font-size: 13px; font-weight: bold;
}
QPushButton#openFolderBtn:hover { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.08); }
QPushButton#openFolderBtn:disabled { background-color: rgba(255, 255, 255, 0.02); color: #475569; border: none; }
/* 打开 UE 按钮: 绿色渐变, 语义区分"外部启动" */
QPushButton#openUEBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e);
    color: #ffffff; border: none;
    padding: 10px 16px; border-radius: 10px; font-size: 13px; font-weight: bold;
}
QPushButton#openUEBtn:hover { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #178943, stop:1 #2ad96b); }
QPushButton#openUEBtn:disabled { background-color: rgba(255, 255, 255, 0.05); color: #475569; border: none; }
/* AI 聊天区 */
QTextEdit#chatHistory {
    background-color: rgba(10, 11, 15, 0.6); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px;
    font-size: 13px; padding: 8px;
}
QTextEdit#chatLog {
    background-color: rgba(10, 11, 15, 0.8); color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 8px;
    font-size: 12px; padding: 6px;
}
QsciScintilla#jsonEditor { border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px; }
QPushButton#copyJsonBtn {
    background-color: rgba(255, 255, 255, 0.05); color: #a78bfa;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
    padding: 8px 16px; font-size: 13px;
}
QPushButton#copyJsonBtn:hover { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.08); }
QPushButton#copyJsonBtn:disabled { background-color: rgba(255, 255, 255, 0.02); color: #475569; border: none; }
QTextEdit#chatInput {
    background-color: rgba(255, 255, 255, 0.03); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
    padding: 8px 12px; font-size: 13px;
}
QTextEdit#chatInput:focus { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.05); }
QPushButton#reviewBtn {
    background-color: rgba(255, 255, 255, 0.05); color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;
    padding: 8px 16px; font-size: 13px; font-weight: bold;
}
QPushButton#reviewBtn:hover { border-color: #6d4aff; background-color: rgba(109, 74, 255, 0.08); }
QPushButton#reviewBtn:disabled { background-color: rgba(255, 255, 255, 0.02); color: #475569; border: none; }

/* ===== 顶栏: 透明, 仅底部细线分隔 ===== */
QFrame#topBar { background: transparent; border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
QLabel#brandLabel { font-size: 15px; font-weight: bold; color: #e2e8f0; background: transparent; }
/* 命令面板入口按钮 */
QPushButton#cmdBtn {
    background-color: rgba(255, 255, 255, 0.05); color: #94a3b8;
    border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px;
    font-size: 11px; font-weight: bold;
}
QPushButton#cmdBtn:hover { border-color: #6d4aff; color: #e2e8f0; }

/* ===== 命令面板弹窗: 毛玻璃纯色浮层 ===== */
QDialog#commandPalette, QWidget#commandPalette {
    background-color: #15161c; border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}
QLineEdit#cmdSearch {
    background-color: transparent; color: #e2e8f0;
    border: none; border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 0; padding: 12px 16px; font-size: 14px;
}
QLineEdit#cmdSearch:focus { border-bottom-color: #6d4aff; }
QListWidget#cmdList {
    background-color: transparent; color: #e2e8f0;
    border: none; border-radius: 0; font-size: 13px; padding: 4px; outline: none;
}
QListWidget#cmdList::item { padding: 8px 16px; border-radius: 6px; }
QListWidget#cmdList::item:hover { background-color: rgba(255, 255, 255, 0.05); }
QListWidget#cmdList::item:selected { background-color: #6d4aff; color: #ffffff; }

/* ===== 状态栏: 透明让 Mesh 渐变透出 ===== */
QStatusBar { background: transparent; color: #64748b; border-top: 1px solid rgba(255, 255, 255, 0.04); }
QStatusBar::item { border: none; }

/* ===== 菜单栏: 透明, 悬停高亮 ===== */
QMenuBar { background: transparent; color: #94a3b8; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }
QMenuBar::item { background: transparent; padding: 6px 12px; border-radius: 4px; }
QMenuBar::item:selected { background-color: rgba(255, 255, 255, 0.08); color: #e2e8f0; }
QMenu { background-color: #15161c; color: #e2e8f0; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 24px; border-radius: 4px; }
QMenu::item:selected { background-color: #6d4aff; color: #ffffff; }
QMenu::separator { height: 1px; background: rgba(255, 255, 255, 0.06); margin: 4px 8px; }

/* ===== 对话框背景 ===== */
QDialog { background-color: #15161c; }
"""


class MainWindow(QMainWindow):
    """主窗口: 文件上传 + 设置 + 生成 + 进度 + 日志 + 下载"""

    # UMAP 构建完成信号: ChatPanel 连接此信号替代 QTimer 轮询
    umap_ready = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("UE场景工厂 UESceneFactory - JSON/YAML → UMAP 转换工具")
        # 方案C(侧栏向导): 左右分栏大幅降低总高度, 最小尺寸改为宽扁比例,
        # 保证 1366×768 屏幕(可用客户区≈700px 高)下无需滚动条即可完整显示。
        self.setMinimumSize(980, 640)
        # U17 修复: QSS 提到 app 级 (见 main()), MainWindow 不再单独设
        # U6 修复: 用 QMainWindow 原生状态栏显示全局状态, 符合 GUI 工程惯例
        self.statusBar().showMessage("就绪")

        # 状态变量
        self.config = load_config()
        self._config = self.config  # ChatPanel 使用 self._config
        self.scene_file = ""
        self.scene_info = None
        self.umap_path = ""
        self.worker = None
        self._parse_worker = None  # 异步场景解析线程引用, 防止被 GC 回收

        self._build_ui()
        self._create_menu()  # 创建菜单栏（设置入口）
        self._load_config_to_ui()
        # 首次使用或路径无效时, 自动探测 UE5/项目路径并填入
        self._onboard_config()
        # 用配置中的最近文件列表填充下拉框
        self._refresh_recent_files()
        # 用配置中的历史记录填充侧栏底部列表
        self._refresh_history()

    def _build_ui(self):
        """构建完整 UI 布局

        方案C(侧栏向导): 顶层左右分栏, 打破原先"从上到下一条条"的纵向堆叠。
        - 左侧栏(~40%): 单行页头 + ① 上传场景文件(拖拽区/最近文件悬浮按钮) + ② 引擎配置
        - 右主区(~60%): 场景信息卡 + ③ 生成 UMAP(按钮/进度条/状态同一行) + 构建日志(占满剩余高度) + 输出按钮行
        配合"最近文件"改为悬浮弹窗; 侧栏改为按需滚动容器(常规窗口高度无滚动条,
        矮窗口自动出现纵向滚动条, 避免内容被压缩裁切)。
        """
        # 暗室布局: 顶层容器 = 顶栏 + 隐藏 TabBar 的 TabWidget
        # QMainWindow 透明(QSS), paintEvent 绘制 Mesh 渐变从底层透出
        # 暗室: 普通 QWidget 默认不填充背景(原生透明), 此处禁止再设 transparent 样式表。
        # 原因: 祖先容器一旦带"透明背景"样式表, 会触发 Qt6 已知问题 ——
        # 后代控件的 QGraphicsDropShadowEffect 离屏合成结果为空, 导致整棵子树不可见(侧栏消失)。
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setSpacing(0)
        cl.setContentsMargins(0, 0, 0, 0)

        # ---- 顶栏: 品牌 + 分段控件 + 状态药丸 + ⌘K ----
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(52)
        tbl = QHBoxLayout(top_bar)
        tbl.setContentsMargins(18, 0, 18, 0)
        tbl.setSpacing(12)

        brand = QLabel("◈ UE场景工厂 UESceneFactory")
        brand.setObjectName("brandLabel")
        tbl.addWidget(brand)

        # 分段控件替代原生 TabBar, 带动画滑块
        self._segmented = SegmentedControl(["构建 UMAP", "AI 生成"])
        self._segmented.currentChanged.connect(self._on_segment_changed)
        tbl.addWidget(self._segmented)
        tbl.addStretch(1)

        # 状态药丸: 文件状态 + 构建状态
        self._pill_file = StatusPill("未选择文件", "idle")
        tbl.addWidget(self._pill_file)
        self._pill_build = StatusPill("就绪", "idle")
        tbl.addWidget(self._pill_build)

        # ⌘K 命令面板入口按钮
        cmd_btn = QPushButton("⌘K")
        cmd_btn.setObjectName("cmdBtn")
        cmd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cmd_btn.setToolTip("打开命令面板 (Ctrl+K)")
        cmd_btn.clicked.connect(self._open_command_palette)
        tbl.addWidget(cmd_btn)

        cl.addWidget(top_bar)

        # ---- Tab 容器: 隐藏原生 TabBar, 由分段控件驱动切换 ----
        self._tabs = QTabWidget()
        self._tabs.tabBar().setVisible(False)
        cl.addWidget(self._tabs, 1)
        self.setCentralWidget(central)

        # Tab 1: 构建 UMAP
        # 暗室: 保持原生透明(不设样式表), 避免 styled-background 标记使后代玻璃面板投影失效
        build_tab = QWidget()
        # 顶层横向布局: 左侧栏 + 右主区
        root = QHBoxLayout(build_tab)
        root.setSpacing(14)
        root.setContentsMargins(14, 12, 14, 12)

        # ======================= 左侧栏 (向导: 上传 + 配置) =======================
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(300)          # 保证窄屏下路径输入仍可用
        # 暗室: 新增顶栏(52px)后, 768p 等矮窗口下侧栏内容总高会超出可用高度,
        # 旧版"直接平铺"会反向压缩 QGroupBox 导致标签被裁切。改为按需滚动容器:
        # 常规窗口高度下无滚动条(内容一屏放下), 仅矮窗口自动出现纵向滚动条,
        # 保证任何窗口尺寸下内容都不被裁切。
        side_scroll = QScrollArea(sidebar)
        side_scroll.setObjectName("sideScroll")
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        side_content = QWidget()              # 原生透明, 玻璃背景仍由外层 #sidebar 承担
        side = QVBoxLayout(side_content)
        side.setSpacing(10)
        side.setContentsMargins(14, 14, 14, 14)
        side_scroll.setWidget(side_content)
        sidebar_box = QVBoxLayout(sidebar)
        sidebar_box.setContentsMargins(0, 0, 0, 0)
        sidebar_box.addWidget(side_scroll)

        # 暗室: 原设计在此挂 QGraphicsDropShadowEffect 玻璃投影, 但实测当前 Qt6 环境下
        # 该效果会使整棵子树离屏合成结果为空(侧栏所有控件完全不可见), 故移除。
        # 纵深感改由 Mesh 渐变底色 + 半透明玻璃面板(rgba 背景+微光边框)自身呈现。

        # ---- ① 上传场景文件 ----
        section1 = QLabel("① 上传场景文件")
        section1.setObjectName("sectionLabel")
        side.addWidget(section1)

        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_selected)
        side.addWidget(self.drop_area)

        # 最近文件: 改为"悬浮弹窗"按钮(不再内联展开占用布局空间)。
        # 点击后在按钮正下方弹出浮层列表, 点击别处或选中后自动收起。
        self.recent_toggle_btn = QPushButton("📂 最近文件 ▾")
        self.recent_toggle_btn.setObjectName("recentToggleBtn")
        self.recent_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.recent_toggle_btn.setToolTip("显示最近转换过的场景文件, 一键重新加载")
        self.recent_toggle_btn.clicked.connect(self._toggle_recent_popup)
        side.addWidget(self.recent_toggle_btn)

        # ---- ② 引擎配置 ----
        section2 = QLabel("② 引擎配置")
        section2.setObjectName("sectionLabel")
        side.addWidget(section2)

        settings_group = QGroupBox()
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(8)
        settings_layout.setContentsMargins(10, 14, 10, 10)

        # UE5 引擎路径: 窄侧栏下采用"标签在上, 输入框+浏览按钮在下"的竖排形式
        settings_layout.addWidget(QLabel("UE5 引擎路径:"))
        self.ue5_path_edit = QLineEdit()
        self.ue5_path_edit.setPlaceholderText("UnrealEditor-Cmd.exe 路径")
        # U13 修复: 长路径被截断时, tooltip 同步显示完整路径供悬停查看
        self.ue5_path_edit.textChanged.connect(
            lambda t: self.ue5_path_edit.setToolTip(t))
        ue5_browse = QPushButton("浏览")
        ue5_browse.setObjectName("browseBtn")
        ue5_browse.clicked.connect(lambda: self._browse_path(self.ue5_path_edit, "选择 UnrealEditor-Cmd.exe", "可执行文件 (*.exe)"))
        ue5_row = QHBoxLayout()
        ue5_row.setSpacing(6)
        ue5_row.addWidget(self.ue5_path_edit, 1)   # 输入框拉伸占满
        ue5_row.addWidget(ue5_browse)              # 浏览按钮固定宽度
        settings_layout.addLayout(ue5_row)

        # 项目文件路径: 同样竖排
        settings_layout.addWidget(QLabel("项目文件路径:"))
        self.project_path_edit = QLineEdit()
        self.project_path_edit.setPlaceholderText(".uproject 文件路径")
        # U13 修复: 长路径被截断时, tooltip 同步显示完整路径供悬停查看
        self.project_path_edit.textChanged.connect(
            lambda t: self.project_path_edit.setToolTip(t))
        proj_browse = QPushButton("浏览")
        proj_browse.setObjectName("browseBtn")
        proj_browse.clicked.connect(lambda: self._browse_path(self.project_path_edit, "选择项目文件", "UE 项目文件 (*.uproject)"))
        proj_row = QHBoxLayout()
        proj_row.setSpacing(6)
        proj_row.addWidget(self.project_path_edit, 1)
        proj_row.addWidget(proj_browse)
        settings_layout.addLayout(proj_row)

        side.addWidget(settings_group)

        # ======================= ④ 转换历史 (侧栏底部) =======================
        history_header = QHBoxLayout()
        history_header.setSpacing(6)
        hist_label = QLabel("④ 转换历史")
        hist_label.setObjectName("sectionLabel")
        self.history_stats_label = QLabel("")
        self.history_stats_label.setObjectName("historyStatsLabel")
        history_header.addWidget(hist_label)
        history_header.addStretch(1)
        history_header.addWidget(self.history_stats_label)
        side.addLayout(history_header)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.setMinimumHeight(160)
        self.history_list.setMouseTracking(True)
        self.history_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_list.itemSelectionChanged.connect(self._on_history_selected)
        self.history_list.itemDoubleClicked.connect(self._on_history_activated)
        self.history_list.customContextMenuRequested.connect(self._on_history_context)
        side.addWidget(self.history_list, 1)

        # 详情条: 固定在列表下方, 显示选中条目的元信息
        detail = QFrame()
        detail.setObjectName("historyDetail")
        detail_l = QVBoxLayout(detail)
        detail_l.setContentsMargins(8, 6, 8, 6)
        detail_l.setSpacing(2)
        self.detail_title = QLabel("选中一条历史记录查看详情")
        self.detail_title.setObjectName("historyDetailTitle")
        self.detail_meta = QLabel("")
        self.detail_meta.setObjectName("historyDetailMeta")
        self.detail_umap = QLabel("")
        self.detail_umap.setObjectName("historyDetailPath")
        self.detail_src = QLabel("")
        self.detail_src.setObjectName("historyDetailPath")
        detail_l.addWidget(self.detail_title)
        detail_l.addWidget(self.detail_meta)
        detail_l.addWidget(self.detail_umap)
        detail_l.addWidget(self.detail_src)
        side.addWidget(detail)

        # ======================= 右主区 (场景信息 + 生成 + 日志 + 输出) =======================
        # 暗室: 保持原生透明(不设样式表), 避免 styled-background 标记使信息卡投影失效
        main = QWidget()
        mainl = QVBoxLayout(main)
        mainl.setSpacing(10)
        mainl.setContentsMargins(0, 0, 0, 0)

        # ---- 场景信息卡: 展示当前选中文件的解析摘要 ----
        info_card = QFrame()
        info_card.setObjectName("card")
        info_card_layout = QVBoxLayout(info_card)
        info_card_layout.setContentsMargins(12, 10, 12, 10)
        # 暗室: 信息卡投影同侧栏原因移除(QGraphicsDropShadowEffect 致子树不可见),
        # 玻璃质感由 QSS 的 rgba 背景 + 1px 微光边框 + 14px 圆角承担。
        self.scene_info_label = QLabel("未选择文件")
        self.scene_info_label.setObjectName("infoLabel")
        self.scene_info_label.setWordWrap(True)
        info_card_layout.addWidget(self.scene_info_label)
        mainl.addWidget(info_card)

        # ---- ③ 生成 UMAP: 按钮/进度条/状态标签同一行(按钮不再独占一整行) ----
        section3 = QLabel("③ 生成 UMAP")
        section3.setObjectName("sectionLabel")
        mainl.addWidget(section3)

        gen_row = QHBoxLayout()
        gen_row.setSpacing(10)
        self.generate_btn = QPushButton("🚀 生成 UMAP")
        self.generate_btn.setObjectName("generateBtn")
        self.generate_btn.setEnabled(False)
        # Tooltip: 辅助用户理解按钮双用语义和快捷操作
        self.generate_btn.setToolTip("生成 UMAP 关卡文件；构建进行中点击可取消生成")
        self.generate_btn.clicked.connect(self._on_generate)
        gen_row.addWidget(self.generate_btn)          # 按钮自然宽度

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("")  # U12: 空闲时不显示噪声文本, 生成开始时才设格式
        gen_row.addWidget(self.progress_bar, 1)       # 进度条拉伸填满中间

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        gen_row.addWidget(self.status_label)          # 状态标签靠右
        mainl.addLayout(gen_row)

        # ---- 构建日志: 占据主区剩余全部高度(stretch=1), 生成过程实时可见 ----
        log_label = QLabel("构建日志:")
        log_label.setObjectName("sectionLabel")
        mainl.addWidget(log_label)

        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumBlockCount(500)  # 限制日志行数避免内存溢出
        self.log_display.setMinimumHeight(120)      # 保底高度, 其余由 stretch 撑满
        mainl.addWidget(self.log_display, 1)

        # ---- 输出按钮行: 下载 / 打开目录 / 在 UE 编辑器中打开 (等宽分布) ----
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        self.download_btn = QPushButton("💾 下载 UMAP 文件")
        self.download_btn.setObjectName("downloadBtn")
        self.download_btn.setEnabled(False)
        self.download_btn.setToolTip("将生成的 UMAP 文件复制到指定目录")
        self.download_btn.clicked.connect(self._on_download)
        out_row.addWidget(self.download_btn)

        # 成功后打开资源管理器并定位到 umap 文件, 免去手动找文件
        self.open_folder_btn = QPushButton("📂 打开输出目录")
        self.open_folder_btn.setObjectName("openFolderBtn")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.setToolTip("在文件资源管理器中打开 UMAP 所在目录")
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        out_row.addWidget(self.open_folder_btn)

        # 直接在 UE 编辑器中打开当前生成的 umap, 省去手动加载步骤
        self.open_ue_btn = QPushButton("在 UE 编辑器中打开")
        self.open_ue_btn.setObjectName("openUEBtn")
        self.open_ue_btn.setEnabled(False)
        self.open_ue_btn.setToolTip("启动 UE5 编辑器并加载刚生成的 UMAP 关卡")
        self.open_ue_btn.clicked.connect(self._on_open_ue_editor)
        out_row.addWidget(self.open_ue_btn)
        # 三个按钮等宽分布, 视觉平衡
        out_row.setStretch(0, 1)
        out_row.setStretch(1, 1)
        out_row.setStretch(2, 1)
        mainl.addLayout(out_row)

        # 左右分栏装入顶层: 侧栏 40% / 主区 60% (随窗口缩放按比例伸缩)
        root.addWidget(sidebar, 40)
        root.addWidget(main, 60)

        # 直接作为 Tab 内容; 一屏体验由左右分栏+弹性 stretch+侧栏按需滚动共同保证
        self._tabs.addTab(build_tab, "构建 UMAP")
        # Tab 2: AI 生成
        self._chat_panel = ChatPanel(self._config)
        self._tabs.addTab(self._chat_panel, "AI 生成")

        # 最近文件悬浮弹窗: 独立顶层 Popup 窗口, 承载 recent_list, 点击别处自动关闭
        self._recent_popup = QWidget(self, Qt.WindowType.Popup)
        self._recent_popup.setObjectName("recentPopup")
        pop_layout = QVBoxLayout(self._recent_popup)
        pop_layout.setContentsMargins(6, 6, 6, 6)
        pop_layout.setSpacing(4)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("recentList")
        self.recent_list.setMaximumHeight(220)
        self.recent_list.setMinimumWidth(440)     # 悬浮层较宽, 便于显示完整路径
        self.recent_list.itemClicked.connect(self._on_recent_selected)
        pop_layout.addWidget(self.recent_list)
        self._recent_popup.hide()

        # 暗室: Ctrl+K 快捷键 → 命令面板
        self._cmd_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._cmd_shortcut.activated.connect(self._open_command_palette)
        # 命令面板延迟创建, 首次打开时填充
        self._cmd_palette = None

    def paintEvent(self, event):
        """暗室 Mesh 渐变背景: 4 个径向渐变光斑叠加在深色底上

        QMainWindow 透明(QSS), 此方法在窗口底层绘制 Mesh 渐变,
        玻璃面板悬浮其上形成纵深空间感。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        # 基底深色
        painter.fillRect(rect, QColor("#0a0b0f"))
        # 光斑 1: 左上 紫
        g1 = QRadialGradient(QPointF(rect.width() * 0.15, rect.height() * 0.1),
                             rect.width() * 0.4)
        g1.setColorAt(0, QColor(109, 74, 255, 50))
        g1.setColorAt(1, QColor(109, 74, 255, 0))
        painter.fillRect(rect, g1)
        # 光斑 2: 右下 蓝紫
        g2 = QRadialGradient(QPointF(rect.width() * 0.9, rect.height() * 0.85),
                             rect.width() * 0.45)
        g2.setColorAt(0, QColor(157, 138, 255, 35))
        g2.setColorAt(1, QColor(157, 138, 255, 0))
        painter.fillRect(rect, g2)
        # 光斑 3: 右上 青
        g3 = QRadialGradient(QPointF(rect.width() * 0.85, rect.height() * 0.15),
                             rect.width() * 0.3)
        g3.setColorAt(0, QColor(48, 52, 70, 40))
        g3.setColorAt(1, QColor(48, 52, 70, 0))
        painter.fillRect(rect, g3)
        # 光斑 4: 左下 暗蓝
        g4 = QRadialGradient(QPointF(rect.width() * 0.1, rect.height() * 0.9),
                             rect.width() * 0.35)
        g4.setColorAt(0, QColor(30, 40, 80, 30))
        g4.setColorAt(1, QColor(30, 40, 80, 0))
        painter.fillRect(rect, g4)
        painter.end()

    def _on_segment_changed(self, index):
        """分段控件切换 → 驱动隐藏的 TabWidget"""
        self._tabs.setCurrentIndex(index)

    def _setup_command_palette(self):
        """填充命令面板命令列表"""
        self._cmd_palette = CommandPalette(self)
        self._cmd_palette.addCommand("生成 UMAP", self._on_generate, "Ctrl+Return")
        self._cmd_palette.addCommand("下载 UMAP 文件", self._on_download)
        self._cmd_palette.addCommand("打开输出目录", self._on_open_folder)
        self._cmd_palette.addCommand("在 UE 编辑器中打开", self._on_open_ue_editor)
        self._cmd_palette.addCommand("选择场景文件", self._browse_scene_file)
        self._cmd_palette.addCommand("最近文件", self._toggle_recent_popup)
        self._cmd_palette.addCommand("设置", self._open_settings, "Ctrl+,")
        self._cmd_palette.addCommand("关于UE场景工厂", self._show_about)

    def _open_command_palette(self):
        """打开命令面板(首次调用时延迟初始化)"""
        if self._cmd_palette is None:
            self._setup_command_palette()
        self._cmd_palette.show_palette()

    def _load_config_to_ui(self):
        """将配置加载到输入框"""
        self.ue5_path_edit.setText(self.config.get("ue5_path", ""))
        self.project_path_edit.setText(self.config.get("project_path", ""))

    def _save_config(self):
        """从输入框读取并保存配置"""
        self.config["ue5_path"] = self.ue5_path_edit.text().strip()
        self.config["project_path"] = self.project_path_edit.text().strip()
        save_config(self.config)

    def _browse_path(self, line_edit, caption, filter_str):
        """通用文件浏览对话框"""
        file_path, _ = QFileDialog.getOpenFileName(self, caption, "", filter_str)
        if file_path:
            line_edit.setText(file_path.replace("\\", "/"))

    def _detect_running_ue(self):
        """检测所有 UnrealEditor* 进程正在运行(GUI 编辑器 + 可能残留的无头实例)

        返回 [(pid, name), ...] 列表。本检测在启动后台引擎之前执行,
        因此不会误判自身即将启动的进程; 此时若存在任何 UnrealEditor*
        进程, 均视为冲突源(同项目多实例会导致资产注册表竞争,
        且编辑器打开目标地图会锁定 umap 文件使保存失败)。
        """
        found = []
        try:
            out = subprocess.run(
                ["tasklist", "/NH"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            for line in out.stdout.splitlines():
                parts = line.split()
                # 首字段为映像名, 次字段为 PID; 名字以 unrealeditor 开头即命中
                if len(parts) >= 2 and parts[0].lower().startswith("unrealeditor"):
                    found.append((parts[1], parts[0]))
        except Exception:
            pass
        return found

    def _on_file_selected(self, file_path):
        """文件选择回调: 解析场景文件, 更新 UI"""
        if not file_path:
            self.scene_info_label.setText("❌ 不支持的文件格式, 请选择 .json 或 .yaml 文件")
            self.generate_btn.setEnabled(False)
            # 同步顶部文件状态药丸: 格式无效 → 红色 error
            self._pill_file.setState("error", "格式无效")
            return

        self.scene_file = file_path
        self.scene_info = None
        self.umap_path = ""
        # 切换场景后旧 umap 已失效, 禁用打开目录/下载/UE编辑器按钮
        self.download_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.open_ue_btn.setEnabled(False)
        # U16 修复: 同步 AI 生成 Tab 的 UE 打开按钮, 避免同名按钮状态不同步
        self._chat_panel._open_ue_btn.setVisible(False)

        # 异步解析场景文件: 大型 JSON 可能耗时数百毫秒, 避免阻塞 UI 主线程
        self.scene_info_label.setText("⏳ 正在解析场景文件...")
        # 同步顶部文件状态药丸: 解析中 → 橙色 working
        self._pill_file.setState("working", "解析中...")
        self.generate_btn.setEnabled(False)
        # 断开旧解析线程的信号连接, 避免回调重复触发 (非阻塞)
        if self._parse_worker is not None and self._parse_worker.isRunning():
            try:
                self._parse_worker.finished_signal.disconnect(self._on_parse_done)
            except TypeError:
                pass  # 未连接过, 忽略
            self._parse_worker.quit()  # 请求线程退出, 不阻塞主线程
        self._parse_worker = SceneParseWorker(file_path)
        # 使用 lambda 闭包捕获当前 file_path, 避免回调时 self.scene_file 已被覆盖
        self._parse_worker.finished_signal.connect(
            lambda scene, info, fp=file_path: self._on_parse_done(scene, info, fp))
        self._parse_worker.start()

    def _on_parse_done(self, scene, info, file_path=None):
        """异步解析完成回调: scene 为 dict 或 None, info 为 info_dict 或错误字符串"""
        if scene is None:
            # 解析失败: info 为错误信息字符串
            self.scene_info_label.setText("❌ " + str(info))
            self.generate_btn.setEnabled(False)
            # 同步顶部文件状态药丸: 解析失败 → 红色 error
            self._pill_file.setState("error", "解析失败")
            return

        self.scene_info = info
        # 记入最近文件列表(去重置顶, 便于下次快速加载)
        self._add_recent_file(file_path)

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
        # 同步顶部文件状态药丸: 解析成功 → 绿色 done, 显示文件名(用户一眼可见当前文件)
        self._pill_file.setState("done", ("已加载: " + os.path.basename(file_path)) if file_path else "已加载")

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

    def _on_generate(self):
        """生成按钮回调: 构建中再次点击则取消, 否则验证配置并启动后台构建"""
        # 一键两用: 构建进行中再次点击 = 取消生成(无需额外按钮)
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("⏹ 正在取消...")
            # 同步顶部构建状态药丸: 取消中 → 橙色 working
            self._pill_build.setState("working", "取消中...")
            return

        # 保存配置
        self._save_config()

        # 验证输入
        ue5_path = self.ue5_path_edit.text().strip()
        project_path = self.project_path_edit.text().strip()

        if not os.path.isfile(ue5_path):
            QMessageBox.critical(self, "错误", "UE5 引擎路径无效:\n" + ue5_path)
            return
        if not os.path.isfile(project_path):
            QMessageBox.critical(self, "错误", "项目文件路径无效:\n" + project_path)
            return
        if not self.scene_file or not os.path.isfile(self.scene_file):
            QMessageBox.critical(self, "错误", "请先选择有效的场景文件")
            return

        # 软件工程原则: 快速失败(fail-fast)。检测到 UE 引擎正在运行时,
        # 不让进度条启动后中途卡住或最终保存失败, 而是前置处置。
        # 改进: 不再区分编辑器/无头实例分别弹"错误框/询问框", 统一弹一个
        # 警告框(Warning 图标, 而非 Critical 错误图标), 并提供"关闭 UE 并继续"
        # 按钮直接结束所有检测到的 UE 进程, 用户无需手动去任务管理器关闭。
        running = self._detect_running_ue()
        if running:
            editor, cmd = classify_ue_processes(running)
            all_procs = editor + cmd          # 编辑器 + 无头残留, 一并处理
            lines = "\n".join("  - {} (PID: {})".format(n, p) for p, n in all_procs)
            # 构造警告对话框: Warning 图标 + 两个自定义按钮
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("检测到 UE 进程正在运行")
            msg.setText(
                "检测到以下 UE 进程正在运行, 为避免冲突与文件锁定, 建议先关闭:\n\n"
                + lines +
                "\n\n点击「关闭 UE 并继续」将自动结束上述进程并开始转换;\n"
                "点击「取消」则中止本次操作。"
            )
            close_btn = msg.addButton("关闭 UE 并继续",
                                      QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(close_btn)
            msg.exec()
            # 用户选择"关闭 UE 并继续" → 结束全部 UE 进程后继续构建
            if msg.clickedButton() is close_btn:
                for pid, _ in all_procs:
                    try:
                        # /T 树杀: 连同 UE 子进程一并结束, 避免残留
                        subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                                       capture_output=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                    except Exception:
                        pass
                # 等待进程句柄与 umap 文件锁释放(编辑器退出后文件锁不会立即解除)
                time.sleep(2)
            else:
                return

        # 获取 build_scene.py 路径
        build_script = get_resource_path("build_scene.py")
        if not os.path.isfile(build_script):
            QMessageBox.critical(self, "错误", "未找到 build_scene.py 脚本:\n" + build_script)
            return

        # 准备日志文件路径
        temp_dir = tempfile.mkdtemp(prefix="uescenefactory_log_")
        log_path = os.path.join(temp_dir, "build_scene.log").replace("\\", "/")
        self._log_temp_dir = temp_dir  # 保存引用, 构建完成后清理

        # 清空日志显示和进度
        self.log_display.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备中... %p%")
        self.download_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.open_ue_btn.setEnabled(False)
        self.umap_path = ""

        # 构建期间按钮变为"取消生成"并保持可用, 一键两用(点击即取消)
        self.generate_btn.setText("⏳ 取消生成")

        # 创建并启动后台线程 (传入 target_level 缓存, 避免工作线程重复解析场景文件)
        target_level = ""
        if self.scene_info and isinstance(self.scene_info, dict):
            target_level = self.scene_info.get("target_level", "")
        self.worker = BuildWorker(
            ue5_path, project_path, self.scene_file, build_script, log_path,
            target_level=target_level
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.status_msg.connect(self._on_status)
        self.worker.log_line.connect(self._on_log_line)
        self.worker.finished_signal.connect(self._on_finished)
        self._build_start_time = time.time()
        self.worker.start()
        # 同步顶部构建状态药丸: 构建已启动(所有校验通过后) → 橙色 working
        # 注意: 必须在 worker.start() 之后设置, 此前多个 early return(路径/文件/UE占用校验)
        # 不会触发, 避免校验失败时药丸误留 working 状态
        self._pill_build.setState("working", "构建中...")

    def _on_progress(self, value):
        """进度更新回调"""
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat("生成中... %p%")

    def _on_status(self, msg):
        """状态文本更新回调"""
        self.status_label.setText(msg)
        # U6 修复: 同步到窗口状态栏, 全局可见
        self.statusBar().showMessage(msg)

    def _on_log_line(self, line):
        """日志行追加回调"""
        self.log_display.appendPlainText(line)

    def _on_finished(self, success, message, umap_path):
        """构建完成回调"""
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.progress_bar.setFormat("完成" if success else "失败")

        if success:
            self.status_label.setText("✅ " + message)
            # 同步顶部构建状态药丸: 构建成功 → 绿色 done
            self._pill_build.setState("done", "构建完成")
            self.umap_path = umap_path
            self.download_btn.setEnabled(True)
            self.open_folder_btn.setEnabled(True)
            self.open_ue_btn.setEnabled(True)
            self.log_display.appendPlainText("")
            self.log_display.appendPlainText("=" * 50)
            self.log_display.appendPlainText("UMAP 文件已生成: " + umap_path)
            self.log_display.appendPlainText("点击下方按钮下载或打开输出目录")
            # 通知 ChatPanel (及其他监听者) UMAP 已就绪
            self.umap_ready.emit(umap_path)
            self._add_history(umap_path)
        else:
            self.status_label.setText("❌ " + message)
            # 同步顶部构建状态药丸: 构建失败 → 红色 error
            self._pill_build.setState("error", "构建失败")
            self.log_display.appendPlainText("")
            self.log_display.appendPlainText("=" * 50)
            self.log_display.appendPlainText("生成失败: " + message)

        # 释放 worker 引用, 使一键两用逻辑恢复为"生成"
        self.worker = None
        # 清理日志临时目录, 避免累积垃圾文件
        log_temp = getattr(self, "_log_temp_dir", None)
        if log_temp and os.path.isdir(log_temp):
            try:
                shutil.rmtree(log_temp, ignore_errors=True)
            except Exception as e:
                logger.debug("清理日志临时目录失败: %s", e)
            self._log_temp_dir = None
        # 恢复生成按钮
        self.generate_btn.setEnabled(True)
        self.generate_btn.setText("🚀 生成 UMAP")

    def _on_open_folder(self):
        """打开 umap 所在目录并在资源管理器中选中该文件"""
        if not self.umap_path or not os.path.isfile(self.umap_path):
            QMessageBox.critical(self, "错误", "UMAP 文件不存在:\n" + self.umap_path)
            return
        # explorer /select,<path> 打开父目录并定位到文件; 路径需为系统分隔符
        sel = "/select," + os.path.normpath(self.umap_path)
        try:
            subprocess.Popen(["explorer", sel],
                              creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            QMessageBox.critical(self, "错误", "无法打开目录:\n" + str(e))

    def _onboard_config(self):
        """首次使用或路径无效时, 自动探测 UE5/项目路径并填入; 探测失败给出提示。"""
        ue5 = self.ue5_path_edit.text().strip()
        proj = self.project_path_edit.text().strip()
        ue5_ok = os.path.isfile(ue5)
        proj_ok = os.path.isfile(proj)
        if not ue5_ok:
            det = autodetect_ue5_path()
            if det:
                self.ue5_path_edit.setText(det)
                ue5_ok = True
        if not proj_ok:
            # 仅当唯一确定时才自动填入; 多项目时交由用户选择, 避免选错
            found = autodetect_project_paths()
            if len(found) == 1:
                self.project_path_edit.setText(found[0])
                proj_ok = True
            elif len(found) > 1:
                multi_proj = True  # 见下方提示
            else:
                multi_proj = False
        else:
            multi_proj = False
        # 探测结果持久化, 下次直接复用
        self._save_config()
        hints = []
        if not ue5_ok:
            hints.append("未探测到 UE5 引擎, 请手动选择 UnrealEditor-Cmd.exe")
        if not proj_ok:
            if multi_proj:
                hints.append("发现多个 UE 项目, 请手动选择 .uproject")
            else:
                hints.append("未探测到项目文件, 请手动选择 .uproject")
        if hints:
            self.status_label.setText("⚠️ " + "；".join(hints))

    def _toggle_recent_popup(self):
        """点击"最近文件"按钮: 在按钮正下方弹出/收起悬浮列表。

        采用 Qt.Popup 顶层浮层, 不占用侧栏布局空间; 点击浮层外部会自动关闭。
        """
        if self._recent_popup.isVisible():
            self._recent_popup.hide()
            return
        # 先刷新一次, 确保显示的是最新的最近文件记录
        self._refresh_recent_files()
        # 定位到按钮左下角正下方(全局坐标)
        btn = self.recent_toggle_btn
        self._recent_popup.adjustSize()
        global_pos = btn.mapToGlobal(QPoint(0, btn.height() + 4))
        self._recent_popup.move(global_pos)
        self._recent_popup.show()
        self._recent_popup.raise_()
        self._recent_popup.activateWindow()


    def _refresh_recent_files(self):
        """用配置中的最近文件列表填充内联列表(显示完整路径)"""
        self.recent_list.clear()
        # 去重: 统一路径分隔符 + 大小写后按完整路径去重,
        # 防止历史残留或不同写法(C:\ vs c:/)导致重复
        seen = set()
        for f in self.config.get("recent_files", []):
            norm = f.replace("\\", "/")
            key = norm.lower()
            if key in seen:
                continue
            seen.add(key)
            # 显示完整路径而非仅文件名, 便于用户区分同名文件; 路径存入 item data
            item = QListWidgetItem(norm)
            item.setData(Qt.ItemDataRole.UserRole, norm)
            item.setToolTip(norm)
            self.recent_list.addItem(item)
        # 无记录时给出占位提示项(不可点击加载)
        if self.recent_list.count() == 0:
            empty = QListWidgetItem("— 暂无最近文件 —")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(empty)

    def _add_recent_file(self, path):
        """把新选择的文件加入最近列表(去重、置顶、最多 8 条)"""
        path = path.replace("\\", "/")
        path_key = path.lower()
        recent = self.config.get("recent_files", [])
        # 去重: 统一分隔符 + 大小写后比较, 避免同一文件因 C:\ 与 c:/ 写法不同而重复
        recent = [r.replace("\\", "/") for r in recent
                  if r.replace("\\", "/").lower() != path_key]
        recent.insert(0, path)
        self.config["recent_files"] = recent[:8]
        save_config(self.config)
        self._refresh_recent_files()

    def _on_recent_selected(self, item):
        """点击最近文件列表项时加载; 文件已不存在则移除该条目"""
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        # 选中即收起悬浮层(无论加载成功与否), 避免浮层遮挡主区
        self._recent_popup.hide()
        if os.path.isfile(data):
            self._on_file_selected(data)
        else:
            # 文件已不存在, 从列表移除并刷新
            recent = [r for r in self.config.get("recent_files", []) if r != data]
            self.config["recent_files"] = recent[:8]
            save_config(self.config)
            self._refresh_recent_files()

    # ======================= 转换历史记录方法 =======================

    def _add_history(self, umap_path):
        """把一次成功转换加入历史记录(按 umap 路径去重、置顶、最多 20 条)"""
        umap_path = umap_path.replace("\\", "/")
        key = umap_path.lower()
        # 计算耗时: 从 _build_start_time 取差值, 无则记 0
        duration = 0
        start = getattr(self, "_build_start_time", None)
        if start:
            duration = round(time.time() - start, 1)
            self._build_start_time = None
        # 读取文件大小
        try:
            size = os.path.getsize(umap_path)
        except Exception:
            size = 0
        # 场景文件名: 从 self.scene_file 取
        scene_path = (getattr(self, "scene_file", "") or "").replace("\\", "/")
        scene_name = os.path.basename(scene_path) if scene_path else ""
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "scene_name": scene_name,
            "scene_path": scene_path,
            "umap_path": umap_path,
            "duration_sec": duration,
            "size_bytes": size,
        }
        history = self.config.get("build_history", [])
        # 去重: 统一分隔符 + 大小写后按 umap 路径比较
        history = [r for r in history
                   if r.get("umap_path", "").replace("\\", "/").lower() != key]
        history.insert(0, rec)
        self.config["build_history"] = history[:20]
        save_config(self.config)
        self._refresh_history()
        # 自动选中最新一条(第 0 行)
        if self.history_list.count() > 0:
            self.history_list.setCurrentRow(0)

    def _refresh_history(self):
        """用配置中的历史记录填充侧栏列表(双行: 场景名 + 时间/耗时/大小)"""
        self.history_list.clear()
        for rec in self.config.get("build_history", []):
            umap = rec.get("umap_path", "")
            valid = os.path.isfile(umap) if umap else False
            title = rec.get("scene_name") or os.path.basename(umap) or "(未知)"
            if not valid:
                title += "  (已失效)"
            ts = rec.get("ts", "")
            dur = rec.get("duration_sec", 0)
            size = _fmt_size(rec.get("size_bytes", 0))
            meta = f"{ts}  ·  {dur}s  ·  {size}"
            # 构建双行 widget: 第一行标题, 第二行元信息
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(0)
            t = QLabel(title)
            t.setStyleSheet("color: %s; font-size: 12px;" % ("#a6adc8" if not valid else "#cdd6f4"))
            m = QLabel(meta)
            m.setStyleSheet("color: #6c7086; font-size: 10px;")
            wl.addWidget(t)
            wl.addWidget(m)
            # 透明鼠标事件: 点击穿透到 QListWidget, 保证选中/双击/右键均生效
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 38))
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, w)
        # 无记录时给出占位提示项(不可点击)
        if self.history_list.count() == 0:
            empty = QListWidgetItem("— 暂无转换历史 —")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_list.addItem(empty)
        self._refresh_history_stats()

    def _refresh_history_stats(self):
        """更新历史统计标签: 条数 + 累计大小"""
        history = self.config.get("build_history", [])
        n = len(history)
        total = sum(r.get("size_bytes", 0) for r in history)
        self.history_stats_label.setText("共 %d 条 · 累计 %s" % (n, _fmt_size(total)))

    def _on_history_selected(self):
        """选中历史条目时更新底部详情条; 无选中则重置为占位文本"""
        items = self.history_list.selectedItems()
        if not items:
            self.detail_title.setText("选中一条历史记录查看详情")
            self.detail_meta.setText("")
            self.detail_umap.setText("")
            self.detail_src.setText("")
            return
        rec = items[0].data(Qt.ItemDataRole.UserRole)
        if not rec:
            return
        umap = rec.get("umap_path", "")
        valid = os.path.isfile(umap) if umap else False
        title = rec.get("scene_name", "(未知)")
        if not valid:
            title += "  (已失效)"
        self.detail_title.setText(title)
        self.detail_meta.setText("%s  ·  %ss  ·  %s" % (
            rec.get("ts", ""), rec.get("duration_sec", 0), _fmt_size(rec.get("size_bytes", 0))))
        self.detail_umap.setText("UMAP: " + umap)
        self.detail_src.setText("场景: " + rec.get("scene_path", ""))

    def _on_history_activated(self, item):
        """双击历史条目: 在资源管理器中定位 UMAP 文件"""
        rec = item.data(Qt.ItemDataRole.UserRole)
        if not rec:
            return
        umap = rec.get("umap_path", "")
        if not umap or not os.path.isfile(umap):
            QMessageBox.information(self, "提示", "UMAP 文件已不存在:\n" + str(umap))
            return
        sel = "/select," + os.path.normpath(umap)
        try:
            subprocess.Popen(["explorer", sel], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            QMessageBox.critical(self, "错误", "无法打开目录:\n" + str(e))

    def _on_history_context(self, pos):
        """右键历史条目: 弹出操作菜单(P0 打开目录 / P1 UE+加载 / P2 重新转换 + 复制+删除)"""
        item = self.history_list.itemAt(pos)
        if item is None:
            return
        rec = item.data(Qt.ItemDataRole.UserRole)
        if not rec:
            return
        umap = rec.get("umap_path", "")
        scene = rec.get("scene_path", "")
        valid = os.path.isfile(umap) if umap else False
        scene_valid = os.path.isfile(scene) if scene else False
        menu = QMenu(self)
        act_folder = menu.addAction("打开输出目录")
        act_ue = menu.addAction("在 UE 编辑器中打开")
        act_reload = menu.addAction("重新加载场景文件")
        act_reconvert = menu.addAction("重新转换该场景")
        menu.addSeparator()
        act_copy_umap = menu.addAction("复制 UMAP 路径")
        act_copy_scene = menu.addAction("复制场景路径")
        menu.addSeparator()
        act_delete = menu.addAction("删除此条记录")
        act_clear = menu.addAction("清空全部历史")
        # 已失效项禁用依赖文件存在的操作
        if not valid:
            act_folder.setEnabled(False)
            act_ue.setEnabled(False)
            act_copy_umap.setEnabled(False)
        if not scene_valid:
            act_reload.setEnabled(False)
            act_reconvert.setEnabled(False)
            act_copy_scene.setEnabled(False)
        action = menu.exec(self.history_list.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action == act_folder:
            self._on_history_activated(item)
        elif action == act_ue:
            self._history_open_ue(rec)
        elif action == act_reload:
            self._history_reload_scene(rec, generate=False)
        elif action == act_reconvert:
            self._history_reconvert(rec)
        elif action == act_copy_umap:
            self._history_copy(umap)
        elif action == act_copy_scene:
            self._history_copy(scene)
        elif action == act_delete:
            self._history_delete(rec)
        elif action == act_clear:
            self._history_clear_all()

    def _history_open_ue(self, rec):
        """用 UE 编辑器打开历史记录中的 UMAP(复用 _on_open_ue_editor 逻辑)"""
        umap = rec.get("umap_path", "")
        if not umap or not os.path.isfile(umap):
            QMessageBox.critical(self, "错误", "UMAP 文件不存在:\n" + str(umap))
            return
        ue5_cmd = self.config.get("ue5_path", "")
        ue5_dir = os.path.dirname(ue5_cmd)
        ue_editor = os.path.join(ue5_dir, "UnrealEditor.exe")
        if not os.path.isfile(ue_editor):
            QMessageBox.critical(self, "错误",
                "未找到 UE 编辑器:\n" + ue_editor + "\n\n请确认 UE5 引擎路径配置正确")
            return
        project_path = self.config.get("project_path", "")
        if not os.path.isfile(project_path):
            QMessageBox.critical(self, "错误",
                "项目文件不存在:\n" + project_path + "\n\n请在设置中检查项目路径")
            return
        try:
            subprocess.Popen([ue_editor, project_path, umap],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            self.status_label.setText("UE 编辑器正在启动...")
        except Exception as e:
            QMessageBox.critical(self, "错误", "启动 UE 编辑器失败:\n" + str(e))

    def _history_reload_scene(self, rec, generate=False):
        """重新加载历史记录对应的场景文件; 若当前已加载其他场景则弹确认框

        generate=True 时加载后自动触发 _on_generate 重新转换。
        """
        scene = rec.get("scene_path", "")
        if not scene or not os.path.isfile(scene):
            QMessageBox.information(self, "提示", "场景文件已不存在:\n" + str(scene))
            return
        current = (getattr(self, "scene_file", "") or "").replace("\\", "/")
        if current.lower() != scene.lower():
            # 当前已加载其他场景, 弹确认框避免误覆盖
            reply = QMessageBox.question(
                self, "确认重新加载",
                "当前已加载其他场景文件, 是否替换为:\n" + scene,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._on_file_selected(scene)
        self.status_label.setText("已加载场景: " + os.path.basename(scene))
        if generate:
            self._on_generate()

    def _history_reconvert(self, rec):
        """重新转换历史记录对应的场景(加载场景后立即触发生成)"""
        self._history_reload_scene(rec, generate=True)

    def _history_copy(self, text):
        """复制文本到系统剪贴板"""
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("已复制到剪贴板", 3000)

    def _history_delete(self, rec):
        """删除单条历史记录(按 umap 路径匹配)"""
        key = rec.get("umap_path", "").replace("\\", "/").lower()
        history = [r for r in self.config.get("build_history", [])
                   if r.get("umap_path", "").replace("\\", "/").lower() != key]
        self.config["build_history"] = history
        save_config(self.config)
        self._refresh_history()

    def _history_clear_all(self):
        """清空全部历史记录(弹确认框)"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空全部转换历史记录吗? 此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.config["build_history"] = []
        save_config(self.config)
        self._refresh_history()

    def _on_download(self):
        """下载按钮回调: 打开保存对话框, 复制 umap 文件"""
        if not self.umap_path or not os.path.isfile(self.umap_path):
            QMessageBox.critical(self, "错误", "UMAP 文件不存在:\n" + self.umap_path)
            return

        # 建议文件名
        default_name = os.path.basename(self.umap_path)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存 UMAP 文件", default_name, "UMAP 文件 (*.umap)"
        )
        if not save_path:
            return

        try:
            shutil.copy2(self.umap_path, save_path)
            QMessageBox.information(self, "成功", "UMAP 文件已保存到:\n" + save_path)
            self.status_label.setText("✅ UMAP 已下载到: " + save_path)
        except Exception as e:
            QMessageBox.critical(self, "错误", "保存文件失败:\n" + str(e))

    def _on_open_ue_editor(self):
        """在 UE 编辑器中打开当前生成的 UMAP

        从 UnrealEditor-Cmd.exe 路径推导 UnrealEditor.exe 路径,
        然后用项目路径 + UMAP 文件路径启动编辑器并加载该地图。
        """
        if not self.umap_path or not os.path.isfile(self.umap_path):
            QMessageBox.critical(self, "错误", "UMAP 文件不存在:\n" + str(self.umap_path))
            return

        # 从配置中获取 UE5 引擎路径（UnrealEditor-Cmd.exe）并推导 UnrealEditor.exe
        ue5_cmd = self.config.get("ue5_path", "")
        ue5_dir = os.path.dirname(ue5_cmd)
        ue_editor = os.path.join(ue5_dir, "UnrealEditor.exe")
        if not os.path.isfile(ue_editor):
            QMessageBox.critical(
                self, "错误",
                "未找到 UE 编辑器:\n" + ue_editor +
                "\n\n请确认 UE5 引擎路径配置正确")
            return

        project_path = self.config.get("project_path", "")
        if not os.path.isfile(project_path):
            QMessageBox.critical(
                self, "错误",
                "项目文件不存在:\n" + project_path +
                "\n\n请在设置中检查项目路径")
            return

        # 启动 UE 编辑器打开特定地图
        # 命令行格式: UnrealEditor.exe <project.uproject> <full_path_to.umap>
        try:
            subprocess.Popen(
                [ue_editor, project_path, self.umap_path],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.status_label.setText("UE 编辑器正在启动...")
        except Exception as e:
            QMessageBox.critical(self, "错误", "启动 UE 编辑器失败:\n" + str(e))

    def _on_ai_finished(self, scene, success, message):
        """供外部调用测试 AI 生成流程"""
        self._chat_panel._on_finished(scene, success, message)

    def _create_menu(self):
        """创建菜单栏 (U18 修复: 补全文件/帮助菜单, 不再是孤立设置文字)"""
        menubar = self.menuBar()
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        open_action = QAction("打开场景文件...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._browse_scene_file)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        settings_action = QAction("设置...", self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _browse_scene_file(self):
        """U18: 菜单 文件→打开 场景文件选择 (复用 _on_file_selected)"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择场景文件", "", "场景文件 (*.json *.yaml)")
        if file_path:
            self._on_file_selected(file_path)

    def _show_about(self):
        """关于对话框: 显示版本号 + 版本更新简说

        风格与主界面暗室主题(DARKROOM_THEME)一致: 对话框深色底继承 app 级 QSS 的
        QDialog 规则(#15161c), 不再覆盖浅色背景(浅色底+主题浅色字=低对比不可读);
        标题/副标题/分隔线/"版本更新简说"节标题为固定区, 不随内容滚动。
        仅版本简说内容放入 QScrollArea: viewport 高度固定(跟随对话框), 内部
        QLabel 按真实内容展开并自动换行, 内容高度超过 viewport 时滚动条只出现在
        该简说区域内, 而非整页。
        对话框最高 900px, 避免弹窗过高超出屏幕。
        """
        from PyQt6.QtWidgets import QScrollArea  # 局部导入, 不污染顶层
        # 从 VERSION_HISTORY 动态生成更新说明 HTML, 避免手动维护两处
        changelog_html = ""
        for ver, date, items in VERSION_HISTORY:
            # 版本号冷调白加粗、日期低饱和灰, 与暗室主题文字层级一致
            changelog_html += (
                f"<font color='#e2e8f0'><b>v{ver}</b></font> "
                f"<font color='#64748b'>({date})</font><br>"
            )
            for item in items:
                changelog_html += f"&nbsp;&nbsp;• {item}<br>"
            changelog_html += "<br>"
        dlg = QDialog(self)
        dlg.setObjectName("aboutDialog")
        dlg.setWindowTitle("关于 UE场景工厂")
        dlg.setMaximumHeight(900)          # 最高 900px, 防止超出屏幕
        dlg.setMinimumWidth(560)
        # 暗室主题局部样式: 以 objectName 精确约束本弹窗内控件, 配色取自 DARKROOM_THEME
        # (标题白 #e2e8f0 / 副标题灰 #94a3b8 / 节标题紫 #a78bfa / 正文灰蓝 #a6adc8)
        dlg.setStyleSheet(
            "QLabel#aboutTitle { font-size: 20px; font-weight: bold; color: #e2e8f0; }"
            "QLabel#aboutSubtitle { font-size: 12px; color: #94a3b8; }"
            "QFrame#aboutSep { background-color: rgba(255, 255, 255, 0.08);"
            " border: none; min-height: 1px; max-height: 1px; }"
            "QLabel#aboutSectionLabel { font-size: 14px; font-weight: bold; color: #a78bfa; }"
            "QScrollArea#aboutScroll { background: transparent; border: none; }"
            "QScrollArea#aboutScroll > QWidget { background: transparent; }"
            "QLabel#aboutContent { font-size: 12px; color: #a6adc8; }"
        )
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        # ---- 固定区: 标题/副标题/分隔线/节标题, 始终可见不滚动 ----
        title = QLabel(
            f"UE场景工厂 UESceneFactory <font color='#89b4fa'>v{APP_VERSION}</font>")
        title.setObjectName("aboutTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitle = QLabel(
            "JSON/YAML → UMAP 可视化转换工具<br>基于 PyQt6 + UE5 + ProjectAirSim")
        subtitle.setObjectName("aboutSubtitle")
        subtitle.setTextFormat(Qt.TextFormat.RichText)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        sep = QFrame()                     # 1px 背景色块作分隔线, 同主题分割线配色
        sep.setObjectName("aboutSep")
        sep.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(sep)
        section = QLabel("版本更新简说")
        section.setObjectName("aboutSectionLabel")
        layout.addWidget(section)
        # ---- 滚动区: 仅版本简说内容进入 QScrollArea, 滚动条只在此区域出现 ----
        scroll = QScrollArea(dlg)
        scroll.setObjectName("aboutScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QLabel()
        content.setObjectName("aboutContent")
        content.setWordWrap(True)
        content.setTextFormat(Qt.TextFormat.RichText)
        # QLabel 用 setText 设置文本(无 setHtml); 已设 RichText 格式故按富文本解析渲染
        content.setText(changelog_html)
        content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        scroll.setWidget(content)
        # stretch=1: 滚动区占满剩余高度, viewport 固定故滚动条只出现在简说区域内
        layout.addWidget(scroll, 1)
        # 初始高度 640(紧凑), 用户可向下拉至最高 900; 内容超出 viewport 即出滚动条
        dlg.resize(560, 640)
        dlg.exec()

    def _open_settings(self):
        """打开 LLM 设置对话框，保存后同步配置到 ChatPanel"""
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            # SettingsDialog._on_save 已更新 dlg._config，此处直接同步引用即可
            self._chat_panel._config = self._config


# ============================================================================
# 程序入口
# ============================================================================

def main():
    """主函数: 创建应用和窗口"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("UESceneFactory")

    # 程序图标: 窗口标题栏/任务栏显示 (打包后从 _MEIPASS 读取, 开发环境从脚本目录读取)
    app.setWindowIcon(QIcon(get_resource_path("mapforge.ico")))

    # U17 修复: QSS 提到 app 级 (所有窗口统一继承) + 全局中文字体适配
    app.setStyleSheet(DARKROOM_THEME)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    # 高 DPI 支持
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    # 支持命令行传入场景文件路径, 启动时自动加载 (便于测试和快捷使用)
    if len(sys.argv) > 1:
        arg_path = sys.argv[1]
        if os.path.isfile(arg_path):
            window._on_file_selected(arg_path)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
