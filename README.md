# UESceneFactory - UE5 场景工厂

**JSON/YAML 场景描述 → UE5 UMAP 关卡转换工具**，支持 AI 自然语言生成场景、PyQt6 可视化界面、地形/Landscape 自动构建。

## 功能概览

| 功能模块 | 说明 |
|---|---|
| **场景构建** | JSON/YAML 描述文件 → UE5 UMAP 关卡，支持 Landscape 地形、静态网格地面、HISM 批量实例化放置 |
| **AI 生成** | 自然语言描述 → 场景 JSON，内置验证-修复循环 + 经验银行 + 模板标杆库 |
| **PyQt6 GUI** | 拖拽上传场景文件 → UE5 构建 → 下载 UMAP，实时日志、JSON 编辑器、AI 聊天面板 |
| **地形科学规则** | 内置河流、梯田、喀斯特、冲沟等 14 种地形模式，多层融合 |
| **资产验证** | 自动校验 JSON 中的 UE5 资产路径是否存在 |

## 快速开始

### 环境要求

- **Unreal Engine 5.8**（含 Python 插件）
- **Python 3.11+**（用于 GUI 和 AI 模块）
- 推荐使用 venv 虚拟环境

### 安装

```bash
# 克隆仓库
git clone https://github.com/16201323/UESceneFactory.git
cd UESceneFactory

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 使用方式

#### 1. PyQt6 GUI（推荐）

```bash
# 双击运行
a_UESceneFactory_run.bat

# 或命令行启动
python mapforge_app.py
```

#### 2. UE5 编辑器内命令行

```python
# UE5 编辑器 Python 控制台
py c:/path/to/UESceneFactory/build_scene.py c:/path/to/scene.json
```

#### 3. UE5 无头模式（CI/CD）

```bash
UnrealEditor-Cmd.exe MyProject.uproject -unattended -nop4 -nosplash \
  -nullrhi -stdout -ExecCmds="py build_scene.py scene.json | quit"
```

## 场景 JSON 格式

```json
{
  "scene": {
    "name": "MyScene",
    "target_level": "/Game/Maps/MyScene",
    "description": "一个示例场景"
  },
  "landscape": {
    "material": "/Game/Materials/M_Landscape",
    "section_size_quads": 63,
    "num_subsections": 2,
    "component_count_x": 8,
    "component_count_y": 8,
    "location": [0, 0, 0],
    "scale": [1, 1, 1],
    "height_pattern": { "type": "hills", "hills": [...] },
    "layers": [
      { "info": "/Game/Layers/Grass_LayerInfo", "weight": 0.8, "weight_pattern": {...} }
    ]
  },
  "placements": [
    {
      "type": "instanced_grid",
      "asset": "/Game/Foliage/SM_Tree_01",
      "grid": { "rows": 10, "cols": 10, "origin": [0, 0, 0], "spacing": [500, 500, 0] }
    }
  ],
  "lighting": {
    "directional_light": { "rotation": [-45, 35, 0], "intensity": 10.0, "color": [1.0, 0.93, 0.76] },
    "sky_light": { "intensity": 3.0 },
    "sky_atmosphere": { "location": [0, 0, 0] },
    "height_fog": { "density": 0.02 }
  },
  "weather": {
    "volumetric_clouds": { "location": [0, 0, 2000] }
  }
}
```

## 项目结构

```
UESceneFactory/
├── build_scene.py          # 核心：JSON/YAML → UMAP 转换引擎
├── build_umap.py           # UMAP 构建包装脚本
├── mapforge_app.py         # PyQt6 主界面应用
├── mapforge_gui.py         # GUI 组件库（主题/动画/控件）
├── validate_scene_json.py  # 场景 JSON 字段校验
├── validate_scene_assets.py # 场景资产路径校验
├── ai/                     # AI 场景生成模块
│   ├── __init__.py         # 三阶段管线：意图解析 → 生成 → 验证修复
│   ├── generator.py       # LLM 生成器
│   ├── knowledge.py       # 知识包组装（分层提示词）
│   ├── validator.py       # 验证-修复循环
│   ├── experience_bank.py # 经验银行（SQLite）
│   └── ...
├── data/
│   ├── knowledge/          # AI 知识库（场景约束、地形规则、资产指南）
│   └── templates/          # 12 个验证场景模板标杆库
├── asset_catalog.json      # 资产目录（AI 检索用）
└── docs/                   # 设计文档
```

## AI 场景生成

通过自然语言描述生成场景 JSON：

```python
from ai import run_pipeline
from ai.client import LLMClient

client = LLMClient(api_key="your-key", base_url="...")
scene, intent, history, success = run_pipeline(
    client,
    config={"llm_intent_model": "gpt-4o-mini", "llm_strong_model": "gpt-4o"},
    user_desc="生成一个山谷场景，有湖泊、松树林和一条河流"
)
```

### 三阶段管线

1. **意图解析**：解析用户描述 → 结构化意图（地形类型、植被、建筑等）
2. **知识注入 + 生成**：叠加知识包 + 模板标杆 + 经验检索 → LLM 生成 JSON
3. **验证-修复循环**：JSON 字段校验 + 资产路径校验 → 自动修复

## 地形模式

支持 14 种地形模式，多层融合：

| 模式 | 说明 |
|---|---|
| `hills` | 山丘 / 山峰（2D 高斯、圆锥、藤田噪声、轹缘） |
| `valleys` | 山谷 / 盆地 |
| `ridges` | 山脊 / 刀脊 |
| `water` | 水体（湖泊、海岸线、水面） |
| `rivers` | 河流网络（支流合流、蛇曲、宽度渐变） |
| `roads` | 道路网络（主路/支路、弯曲、路基平整） |
| `scatter` | 植被散布（树木、草、石头） |
| `noise_overlay` | 噪声叠加层 |
| 更多... | 梯田、喀斯特、冲沟、沙丘等 |

详细见 [data/knowledge/terrain_rules.md](data/knowledge/terrain_rules.md)

## 打包为 exe

```bash
pyinstaller UESceneFactory.spec
```

## License

MIT License
