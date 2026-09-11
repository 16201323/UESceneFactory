# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['scripts/mapforge_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # scripts/ 下的运行脚本和工具
        ('scripts/build_umap.py', 'scripts'),
        ('scripts/build_scene.py', 'scripts'),
        ('scripts/validate_scene_json.py', 'scripts'),
        ('scripts/__init__.py', 'scripts'),
        # config/ 下的资源配置文件(资产目录/图标)
        ('config/asset_catalog.json', 'config'),
        ('config/mapforge.ico', 'config'),
        # data/ 下的知识库和模板标杆
        ('data/knowledge', 'data/knowledge'),
        # 模板标杆库: 12个已验证场景JSON, KnowledgePack按意图匹配注入system prompt
        ('data/templates', 'data/templates'),
    ],
    hiddenimports=[
        'tkinterdnd2',
        'ai',
        'ai.utils',
        'ai.client',
        'ai.knowledge',
        'ai.asset_index',
        'ai.intent_parser',
        'ai.generator',
        'ai.validator',
        'ai.experience_bank',
        'ai.retriever',
        'scripts.validate_scene_json',
        'openai',
        # QScintilla: 专业 JSON 编辑器依赖, PyInstaller 默认无法自动发现
        'PyQt6.Qsci',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UESceneFactory',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
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
    runtime_tmpdir=None,
    console=False,
    # exe 文件图标 (资源管理器/任务栏显示), 与运行时窗口图标共用同一 ico
    # mapforge.ico 已移入 config/ 目录
    icon='config/mapforge.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
