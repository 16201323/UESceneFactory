# MapForge AI 场景生成器 — 方案文档与实施计划

> **文档定位**：本文档是 MapForge 从「JSON→umap 转换工具」升级为「自然语言→JSON→umap AI 生成器」的完整工程方案与分步实施计划。
> **核心原则**：每个 Phase 独立验证通过后再进入下一阶段，绝不在全部写完后才统一测试。

---

## 目录

- [第一部分：方案文档](#第一部分方案文档)
  - [1. 项目概述](#1-项目概述)
  - [2. 架构总览](#2-架构总览)
  - [3. 模块设计](#3-模块设计)
  - [4. 数据结构](#4-数据结构)
  - [5. 成功率预估与成本分析](#5-成功率预估与成本分析)
  - [6. 技术选型理由](#6-技术选型理由)
- [第二部分：实施计划](#第二部分实施计划)
  - [Phase 0: 项目骨架](#phase-0-项目骨架)
  - [Phase 1: LLM 客户端集成](#phase-1-llm-客户端集成)
  - [Phase 2: 知识包构建器](#phase-2-知识包构建器)
  - [Phase 3: 资产关键词索引](#phase-3-资产关键词索引)
  - [Phase 4: 意图解析器（Stage 1）](#phase-4-意图解析器stage-1)
  - [Phase 5: JSON 生成器（Stage 2）](#phase-5-json-生成器stage-2)
  - [Phase 6: 验证-修复循环（Stage 3）](#phase-6-验证-修复循环stage-3)
  - [Phase 7: 经验记忆库存储](#phase-7-经验记忆库存储)
  - [Phase 8: 四因子检索 + Few-shot 注入](#phase-8-四因子检索--few-shot-注入)
  - [Phase 9: GUI 聊天面板](#phase-9-gui-聊天面板)
  - [Phase 10: 设置页面扩展](#phase-10-设置页面扩展)
  - [Phase 11: 端到端集成](#phase-11-端到端集成)
  - [Phase 12: 打包发布](#phase-12-打包发布)

---

# 第一部分：方案文档

## 1. 项目概述

### 1.1 目标

将现有 MapForge 工具（仅支持 JSON→umap 转换）升级为完整的 AI 场景生成器：

| 能力 | 现状 | 升级后 |
|------|------|--------|
| 输入 | 手写 JSON 文件 | 自然语言描述 |
| 知识 | 用户自行查阅文档 | AI 自动注入 UE5_JSON 技能知识 |
| 质量 | 依赖人工经验 | 经验记忆库自动积累 + Few-shot 优化 |
| 验证 | 人工检查 | 自动验证-修复循环 |
| 产出 | umap | umap + 经验入库 |

### 1.2 现有资产盘点

| 资产 | 路径 | 复用方式 |
|------|------|----------|
| GUI 主程序 | `mapforge_app.py` (1272行, PyQt6) | 扩展：添加 AI 聊天面板 |
| LLM 客户端 | `LLM_UEMaps/源码/src/sceneweaver/llm/client.py` (132行) | 复制到 `ai/client.py`，适配扩展 `complete()` 支持 `response_format` 和 `max_tokens` |
| 场景构建器 | `build_scene.py` | 不动，由 build_umap 调用 |
| umap 转换器 | `build_umap.py` / `build_umap.bat` | 不动 |
| 字段校验器 | `validate_scene_json.py` (560行) | 直接调用 `validate_scene()` 函数 |
| 资产校验器 | `validate_scene_assets.py` | 直接调用 |
| 资产目录 | `asset_catalog.json` (~1.4MB, 7691条) | 构建关键词索引 |
| UE5_JSON 技能 | `~/.trae-cn/skills/ue5_json/` (7个参考文件 + 10个模板) | 知识包构建器读取后注入 |
| 设置 UI 模式 | `LLM_UEMaps/源码/src/sceneweaver/gui/pages/settings_page.py` (254行) | 参考模式，新建设置面板 |
| PyInstaller 打包 | `MapForge.spec` | 扩展：添加 ai/ 和 data/ 目录 |

### 1.3 核心创新点

1. **三阶段管线**：意图解析 → 知识注入+JSON生成 → 验证-修复循环
2. **按需知识注入**：核心知识常驻(~3KB) + 场景类型相关文档按需加载(~5KB/种) + 资产关键词搜索(~500 tokens)
3. **经验记忆库**：SQLite 存储 approved 场景，四因子评分检索，Few-shot 注入
4. **自我改进**：每次用户 approved 的场景自动入库，越用越精准（NeurIPS 2025 证明 73%→93%）

---

## 2. 架构总览

### 2.1 数据流图

```
用户输入: "生成一个1km的山谷草地场景，有河流和几棵松树"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: 意图解析 (轻量模型, ~200 tokens 输出)              │
│  ┌─────────────┐    ┌──────────────────┐                    │
│  │ 用户描述     │───▶│ intent_parser.py │──▶ intent_json    │
│  └─────────────┘    └──────────────────┘                    │
│  输出: {terrain_type:"hill_valley", has_water:true,          │
│         has_river:true, has_grass:true, scene_scale:"1km",    │
│         keywords:["山谷","草地","河流","松树"],               │
│         placements:["trees"], complexity:"medium"}            │
└─────────────────────────────────────────────────────────────┘
    │ intent_json
    ▼
┌─────────────────────────────────────────────────────────────┐
│  知识注入组装器 (generator.py 内部)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ 核心知识  │  │ 模式文档  │  │ 资产搜索  │  │ 经验Few-shot│ │
│  │ (~3KB)   │  │ (按意图)  │  │ (~500 tok)│  │ (top 1-3)  │ │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘ │
│  ─────────────────────────────────────────────────────────── │
│  合并为 System Prompt                                       │
└─────────────────────────────────────────────────────────────┘
    │ system_prompt + user_prompt(描述+意图)
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: JSON 生成 (强模型, Structured Output)              │
│  ┌─────────────┐    ┌──────────────────┐                    │
│  │ LLM Client  │───▶│   generator.py   │──▶ scene_json      │
│  └─────────────┘    └──────────────────┘                    │
│  输出: 完整场景 JSON                                         │
└─────────────────────────────────────────────────────────────┘
    │ scene_json
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: 验证-修复循环 (最多3轮)                            │
│  ┌──────────────────────┐                                    │
│  │ validate_scene_json  │──▶ errors[]?                       │
│  └──────────────────────┘    │                              │
│  ┌──────────────────────┐    │ 有错误                       │
│  │ validate_scene_assets│──▶ errors[]?                       │
│  └──────────────────────┘    │                              │
│         ┌───────────────────┴───────────────────┐           │
│         ▼ 有错误               ▼ 无错误          │           │
│  ┌──────────────┐         ┌──────────────┐      │           │
│  │ LLM 修复     │────────▶│ 返回 Stage 3 │      │           │
│  │ (注入错误信息)│         │  (下一轮)    │      │           │
│  └──────────────┘         └──────────────┘      │           │
│                            ──▶ 通过 ─────────────┘           │
└─────────────────────────────────────────────────────────────┘
    │ validated scene_json
    ▼
┌─────────────────────────────────────────────────────────────┐
│  GUI 展示 JSON 预览 → 用户审核                               │
│  ┌─────────┐  ┌──────────┐  ┌──────────────┐                 │
│  │ 预览    │  │ 通过 ✓  │  │ 拒绝 + 反馈  │                 │
│  └─────────┘  └────┬─────┘  └──────┬───────┘                 │
│                    │                │                          │
│                    ▼                ▼                          │
│           ┌──────────────┐  ┌──────────────┐                 │
│           │ 入经验库     │  │ 重新生成     │                 │
│           │ (评分1-5)    │  │ (带反馈)     │                 │
│           └──────────────┘  └──────────────┘                 │
│                    │                                        │
│                    ▼                                        │
│           ┌──────────────┐                                  │
│           │ build_umap   │──▶ umap 文件                     │
│           └──────────────┘                                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 三阶段管线详解

| 阶段 | 模型要求 | 输入 | 输出 | 最大重试 |
|------|----------|------|------|----------|
| Stage 1: 意图解析 | 轻量(gpt-4o-mini / deepseek-chat) | 用户自然语言描述 | intent_json (~200 tokens) | 1次 |
| Stage 2: JSON 生成 | 强模型(gpt-4o / deepseek-v3) | system_prompt(知识) + user_prompt(描述+意图) | 完整 scene JSON | 1次 |
| Stage 3: 验证-修复 | 同 Stage 2 | scene_json + errors[] | 修复后的 scene_json | 3轮 |

### 2.3 知识注入分层策略

| 层 | 内容 | 大小 | 注入条件 |
|----|------|------|----------|
| L1 核心 | 顶层结构 + 两层解析概念 + 字段速查表 + 关键约束 | ~3KB | **始终注入** |
| L2 模式 | height_pattern.md / weight_pattern.md / placements.md | ~5KB/种 | **按 intent.terrain_type 和需求选择** |
| L3 资产 | asset_catalog.json 关键词匹配的路径列表 | ~500 tokens | **按 intent.keywords 搜索** |
| L4 经验 | 历史成功场景的 user_desc + scene_json | ~2-5KB | **按四因子评分 top 1-3** |

**总注入量预估**：L1(3KB) + L2(5-15KB) + L3(0.5KB) + L4(2-5KB) = **10-24KB**

对比全量注入(~1.5MB)，缩减约 **60-150倍**。

### 2.4 经验记忆库架构

```
                    ┌─────────────────────────┐
                    │   experience.db (SQLite) │
                    │  ┌─────────────────────┐ │
  approved 场景 ───▶│  │ experiences 表       │ │
                    │  │ - user_desc          │ │
                    │  │ - intent_json        │ │
                    │  │ - scene_json         │ │
                    │  │ - rating (1-5)       │ │
                    │  │ - tags               │ │
                    │  │ - embedding          │ │
                    │  │ - created_at         │ │
                    │  │ - used_count         │ │
                    │  │ - success/fail_count │ │
                    │  └─────────────────────┘ │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │  retriever.py            │
                    │  4因子评分:               │
                    │  0.65×semantic_sim       │
                    │  +0.15×recency           │
                    │  +0.20×reliability       │
                    │  +0.10×diversity(MMR)    │
                    └───────────┬─────────────┘
                                │
                    top 1-3 经验作为 Few-shot
                                │
                    ┌───────────▼─────────────┐
                    │  注入 Stage 2 的         │
                    │  system_prompt           │
                    └─────────────────────────┘
```

---

## 3. 模块设计

### 3.1 LLM 客户端 (`ai/client.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 封装 LLM API 调用，支持 OpenAI 兼容接口 |
| 复用 | 复制 `LLM_UEMaps/源码/src/sceneweaver/llm/client.py`，适配扩展 `complete()` 方法支持 `response_format`（JSON Mode）和 `max_tokens` |
| 接口 | `LLMClient.complete(system_prompt, user_prompt, **kwargs) -> str`，kwargs 支持 `response_format={"type":"json_object"}` 和 `max_tokens` |
| 实现 | `OpenAILLMClient` (支持 base_url 适配阿里云/DeepSeek) + `OllamaLLMClient` + `MockLLMClient` |
| 依赖 | openai SDK (可选，延迟导入) |

```python
# 核心接口 (在 client.py 基础上扩展 complete() 的 kwargs 透传)
class LLMClient(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str: ...

class OpenAILLMClient(LLMClient):
    def __init__(self, api_key, model="gpt-4o", base_url=None, timeout=120.0): ...
    # complete() 扩展: 透传 response_format 和 max_tokens 到 API 调用
    #   response_format={"type": "json_object"}  → 启用 JSON Mode
    #   max_tokens=4096                          → 限制输出长度，防止截断
    # 支持 base_url 适配:
    #   阿里云: base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    #   DeepSeek: base_url="https://api.deepseek.com/v1"
```

### 3.2 知识包构建器 (`ai/knowledge.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 从 UE5_JSON 技能文档中提取知识，分层组装 system_prompt |
| 输入 | intent_json (决定加载哪些模式文档) |
| 输出 | system_prompt 字符串 |
| 数据源 | `data/knowledge/` 目录（从技能目录复制） |

**知识源文件映射**：

| 文件 | 来源 | 注入层 |
|------|------|--------|
| `data/knowledge/core.md` | 从 SKILL.md 提取核心段落 | L1 始终 |
| `data/knowledge/height_pattern.md` | `references/height_pattern.md` | L2 按 terrain_type |
| `data/knowledge/weight_pattern.md` | `references/weight_pattern.md` | L2 按 has_layers |
| `data/knowledge/placements.md` | `references/placements.md` | L2 按 has_placements |
| `data/knowledge/asset_guide.md` | `references/asset_guide.md` | L2 按需 |
| `data/knowledge/examples.md` | `references/examples.md` | L2 按需 |

**核心接口**：

```python
class KnowledgePack:
    """知识包构建器：按意图组装分层 system prompt"""
    
    def __init__(self, knowledge_dir: str = "data/knowledge"):
        self._core: str = ""        # L1 核心知识，启动时加载
        self._patterns: dict = {}   # L2 模式文档，按需加载
    
    def build_system_prompt(
        self,
        intent: dict,
        asset_paths: list[str],
        few_shots: list[dict],
    ) -> str:
        """
        组装完整 system prompt
        返回: L1核心 + L2模式(按意图) + L3资产路径 + L4经验few-shot
        """
```

### 3.3 资产关键词索引 (`ai/asset_index.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 从 asset_catalog.json 中按关键词搜索资产路径 |
| 输入 | keywords: list[str] (来自 intent 解析) |
| 输出 | asset_paths: list[str] (匹配的 UE 资产路径) |
| 数据源 | `asset_catalog.json` (7691条) |
| 算法 | 关键词匹配 (asset name / category / subfolder 子串匹配) |

**asset_catalog.json 结构**（已知）：

```json
{
  "assets": [
    {
      "path": "/Game/RuralHouse/House/Meshes/SM_House_FloorPlane_03",
      "folder": "Game",
      "subfolder": "RuralHouse",
      "name": "SM_House_FloorPlane_03",
      "category": "rural_house",
      "class": "StaticMesh"
    }
  ]
}
```

**核心接口**：

```python
class AssetIndex:
    """资产关键词索引：按关键词搜索资产路径"""
    
    def __init__(self, catalog_path: str = "asset_catalog.json"):
        self._assets: list[dict] = []  # 加载后缓存
    
    def search(self, keywords: list[str], max_results: int = 20) -> list[str]:
        """
        按关键词搜索资产路径
        匹配优先级: name > category > subfolder
        返回: 去重后的路径列表
        """
    
    def search_by_category(self, category: str, max_results: int = 50) -> list[str]:
        """按 category 字段精确搜索"""
```

### 3.4 意图解析器 (`ai/intent_parser.py`)

| 项目 | 说明 |
|------|------|
| 职责 | Stage 1：从自然语言提取结构化意图 |
| 输入 | user_description: str |
| 输出 | intent: dict (固定 schema) |
| 模型 | 轻量模型 (gpt-4o-mini / deepseek-chat) |
| 超时 | 30秒 |

**意图输出 Schema**：

```json
{
  "terrain_type": "hill_valley",
  "has_water": false,
  "has_river": true,
  "has_road": false,
  "has_buildings": false,
  "has_grass": true,
  "has_wheat": false,
  "has_snow": false,
  "scene_scale": "1km",
  "placements": ["trees"],
  "keywords": ["山谷", "草地", "河流", "松树"],
  "complexity": "medium"
}
```

**terrain_type 枚举**（对齐 height_pattern.type）：

`flat` / `ridge` / `hill` / `noise` / `hill_ridge` / `features` / `terraced` / `karst` / `gully`

**核心接口**：

```python
class IntentParser:
    """Stage 1: 意图解析器"""
    
    def __init__(self, client: LLMClient, model: str = None):
        # model 为 None 时用 client 默认模型
    
    def parse(self, user_description: str) -> dict:
        """
        解析用户描述为 intent dict
        失败时返回 fallback intent (全 false + 默认值)
        """
```

### 3.5 JSON 生成器 (`ai/generator.py`)

| 项目 | 说明 |
|------|------|
| 职责 | Stage 2：组装知识 + 调用 LLM 生成场景 JSON |
| 输入 | user_description: str, intent: dict, few_shots: list[dict] |
| 输出 | scene_json: dict |
| 模型 | 强模型 (gpt-4o / deepseek-v3) |
| 依赖 | KnowledgePack + AssetIndex + LLMClient |
| 超时 | 120秒 |

**核心接口**：

```python
class SceneGenerator:
    """Stage 2: 场景 JSON 生成器"""
    
    def __init__(
        self,
        client: LLMClient,
        knowledge: KnowledgePack,
        asset_index: AssetIndex,
        model: str = None,
    ): ...
    
    def generate(
        self,
        user_description: str,
        intent: dict,
        few_shots: list[dict] | None = None,
    ) -> dict:
        """
        生成场景 JSON
        流程:
        1. asset_index.search(intent["keywords"]) → 资产路径
        2. knowledge.build_system_prompt(intent, asset_paths, few_shots) → system_prompt
        3. client.complete(system_prompt, user_description) → JSON 字符串
        4. json.loads() → scene dict
        """
```

### 3.6 验证-修复循环 (`ai/validator.py`)

| 项目 | 说明 |
|------|------|
| 职责 | Stage 3：调用现有校验脚本 + LLM 修复 |
| 输入 | scene_json: dict |
| 输出 | (validated_scene: dict, errors_history: list) |
| 依赖 | validate_scene_json.py (import) + validate_scene_assets.py (import) + LLMClient |
| 最大轮数 | 3 |

**核心接口**：

```python
class ValidationRepairLoop:
    """Stage 3: 验证-修复循环"""
    
    def __init__(self, client: LLMClient, knowledge: KnowledgePack = None, model: str = None): ...
    
    def validate_and_repair(self, scene: dict, user_description: str, intent: dict = None) -> tuple[dict, list]:
        """
        验证并修复场景 JSON
        流程 (最多3轮):
        1. validate_scene_json.validate_scene(scene) → errors
        2. validate_scene_assets.check_assets(scene) → errors (可选)
        3. 无错误 → 返回 (scene, history)
        4. 有错误 → 注入知识包 system_prompt + 错误信息到 LLM → 生成修复后 JSON → 回到步骤1
        """
```

### 3.7 经验记忆库 (`ai/experience_bank.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 存储/检索历史成功场景 |
| 存储 | SQLite (`data/experience.db`) |
| 接口 | save / search / update_rating / get_stats |

**SQLite Schema**：

```sql
CREATE TABLE IF NOT EXISTS experiences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_desc       TEXT NOT NULL,           -- 用户原始描述
    intent_json     TEXT NOT NULL,           -- 意图解析结果
    scene_json      TEXT NOT NULL,           -- 场景 JSON
    rating          INTEGER DEFAULT 3,        -- 用户评分 1-5
    tags            TEXT DEFAULT '',          -- 逗号分隔标签
    embedding       TEXT DEFAULT '',          -- 嵌入向量 (JSON 数组, 可选)
    created_at      TEXT NOT NULL,            -- ISO 时间戳
    used_count      INTEGER DEFAULT 0,        -- 被检索使用次数
    last_used_at    TEXT,                     -- 最后使用时间
    success_count   INTEGER DEFAULT 0,       -- 验证通过次数
    fail_count      INTEGER DEFAULT 0        -- 验证失败次数
);
```

**核心接口**：

```python
class ExperienceBank:
    """经验记忆库：存储和检索历史成功场景"""
    
    def __init__(self, db_path: str = "data/experience.db"): ...
    
    def save(self, user_desc: str, intent: dict, scene: dict,
             rating: int = 3, tags: str = "") -> int:
        """保存一条经验，返回 id"""
    
    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """检索最相似的经验（四因子评分）"""
    
    def update_rating(self, exp_id: int, rating: int): ...
    
    def update_usage(self, exp_id: int, success: bool): ...
    
    def get_stats(self) -> dict:
        """返回统计: {total, avg_rating, recent_7d_count}"""
```

### 3.8 四因子检索器 (`ai/retriever.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 四因子评分 + 检索 top-K 经验 |
| 输入 | query: str (用户描述) |
| 输出 | list[dict] (top-K 经验) |
| 评分公式 | `score = 0.65×sim + 0.15×recency + 0.20×reliability + 0.10×diversity` |

**四因子详解**：

| 因子 | 权重 | 计算方式 | 说明 |
|------|------|----------|------|
| 语义相似度 | 0.65 | Jaccard/TF-IDF (关键词重叠度) | 最重要：描述越像，经验越有用 |
| 时效性 | 0.15 | `1 / (1 + days_since_last_use)` | 近期使用的经验优先 |
| 可靠性 | 0.20 | `success_count / (success+fail+1)` | 验证通过率高的优先 |
| 多样性 | 0.10 | MMR (1 - max_sim_to_selected) | 避免返回雷同经验 |

> **注**：首期用 Jaccard 关键词相似度（零依赖），后续可选升级为 OpenAI Embeddings API（需 API key 支持 embeddings endpoint）。

**核心接口**：

```python
class ExperienceRetriever:
    """四因子检索器"""
    
    def __init__(self, bank: ExperienceBank): ...
    
    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """
        四因子评分检索
        1. 从 bank 获取全部经验（首期待量不大）
        2. 计算每条经验的四因子总分
        3. MMR 去重后返回 top_k
        """
```

### 3.9 GUI 聊天面板 (扩展 `mapforge_app.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 用户交互界面：聊天 + JSON 预览 + 审核 |
| 基础 | 扩展现有 `mapforge_app.py` MainWindow |
| 新增组件 | ChatPanel widget |

**UI 布局**：

```
┌─────────────────────────────────────────────────────────────┐
│ MapForge                                          [设置⚙]   │
├──────────────────────────────┬──────────────────────────────┤
│  AI 对话区                   │  JSON 预览区                 │
│  ┌────────────────────────┐  │  ┌────────────────────────┐ │
│  │ AI: 你好，描述你的场景  │  │  │ {                      │ │
│  │ User: 生成山谷草地...  │  │  │   "scene": {...},     │ │
│  │ AI: 正在解析意图...    │  │  │   "landscape": {...}, │ │
│  │ AI: 意图: 山谷+河流...  │  │  │   "placements": [...]│ │
│  │ AI: 正在生成场景...    │  │  │ }                      │ │
│  │ AI: 场景已生成，请审核  │  │  │                        │ │
│  └────────────────────────┘  │  └────────────────────────┘ │
│  ┌──────────────────────┐    │  ┌────────────────────────┐ │
│  │ 输入描述...    [发送]│    │  │ [✓ 通过入库] [✗ 拒绝]  │ │
│  └──────────────────────┘    │  │ 评分: ★★★★☆           │ │
│                              │  └────────────────────────┘ │
├──────────────────────────────┴──────────────────────────────┤
│  进度: ████████░░ 80%  日志: 验证通过, 0错误...             │
└─────────────────────────────────────────────────────────────┘
```

**新增信号**（AIWorker 线程）：

```python
class AIWorker(QThread):
    """AI 生成后台线程"""
    intent_parsed = pyqtSignal(dict)       # 意图解析完成
    json_generated = pyqtSignal(dict)      # JSON 生成完成
    validation_done = pyqtSignal(dict, list)  # 验证完成 (scene, errors)
    repair_started = pyqtSignal(int)       # 修复第N轮
    finished_signal = pyqtSignal(dict, bool)  # (最终scene, 是否通过)
    error_occurred = pyqtSignal(str)       # 错误
    log_line = pyqtSignal(str)             # 日志
```

### 3.10 设置页面扩展

| 项目 | 说明 |
|------|------|
| 职责 | LLM API 配置（API key / model / base_url） |
| 模式 | 参照 `settings_page.py` 的 profile 切换 |
| 存储 | 写入 `~/.mapforge_config.json` |

**配置字段扩展**：

```python
# DEFAULT_CONFIG 新增字段
DEFAULT_CONFIG = {
    # 现有字段...
    "ue5_path": "...",
    "project_path": "...",
    # 新增 LLM 配置
    "llm_profile": "openai",       # mock / openai / ollama
    "llm_api_key": "",             # API key (支持 ${VAR} 环境变量)
    "llm_model": "deepseek-chat",  # 模型名
    "llm_base_url": "https://api.deepseek.com/v1",  # 兼容 API 地址
    "llm_ollama_host": "http://localhost:11434",     # Ollama 地址
    "llm_strong_model": "",        # 强模型 (Stage 2), 空则同 llm_model
    "llm_intent_model": "",        # 意图模型 (Stage 1), 空则同 llm_model
}
```

---

## 4. 数据结构

### 4.1 配置 Schema (`~/.mapforge_config.json`)

```json
{
  "ue5_path": "D:/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
  "project_path": "D:/code/UEEnvironment/MyUETest5_8_2/MyUETest5_8_2/MyUETest5_8_2.uproject",
  "llm_profile": "openai",
  "llm_api_key": "sk-xxx",
  "llm_model": "deepseek-chat",
  "llm_base_url": "https://api.deepseek.com/v1",
  "llm_ollama_host": "http://localhost:11434",
  "llm_strong_model": "",
  "llm_intent_model": ""
}
```

### 4.2 意图解析 Prompt 模板

```
你是一个 UE5 场景意图解析器。从用户描述中提取结构化信息。

输出 JSON，严格遵循以下 schema:
{
  "terrain_type": "flat|ridge|hill|noise|hill_ridge|features|terraced|karst|gully",
  "has_water": bool,
  "has_river": bool,
  "has_road": bool,
  "has_buildings": bool,
  "has_grass": bool,
  "has_wheat": bool,
  "has_snow": bool,
  "scene_scale": "500m|1km|2km",
  "placements": ["trees", "fence", "heliport", ...],
  "keywords": ["中文关键词1", "关键词2", ...],
  "complexity": "simple|medium|complex"
}

规则:
- terrain_type 不确定时默认 "features"（最灵活的模式）
- scene_scale 不确定时默认 "1km"
- complexity: 少于3个元素=simple, 3-6个=medium, 6个以上=complex
- keywords: 提取所有可用作资产搜索的关键词（中英文均可）

只输出 JSON，不要其他文字。
```

### 4.3 生成 Prompt 模板结构

```
[system prompt]
{L1 核心知识}

{L2 模式文档 (按意图选择)}

{L3 资产路径 (关键词搜索结果)}
以下是可用的 UE5 资产路径，请在 JSON 中使用:
/Game/RuralHouse/...
/Game/Foliage_Sets/...
...

{L4 经验 Few-shot}
以下是类似的成功场景示例:
--- 示例1 ---
用户描述: "生成一个山谷草地场景..."
场景 JSON:
{...场景JSON...}
--- 示例2 ---
...

[user prompt]
用户需求: {user_description}
意图分析: {intent_json}

请生成完整的场景 JSON。只输出 JSON，不要 markdown 代码块标记。
```

### 4.4 修复 Prompt 模板

```
[system prompt]
你是 UE5 场景 JSON 修复器。以下 JSON 有校验错误，请修复。

校验规则摘要:
- 顶层键: scene, landscape, ground, placements, lighting, weather, rivers
- scene 必填: target_level
- landscape 必填: material, section_size_quads, num_subsections, component_count_x/y
- height_pattern.type 枚举: flat, ridge, hill, noise, hill_ridge, features, terraced, karst, gully
- weight_pattern.pattern 枚举: uniform, height_based, slope_based, region, multi_region, noise_based, aspect_based, snow_line
- placement.type 枚举: group, instanced_grid, instances, static, blueprint, crop_field, village
- weight 值范围: 0~1
- 资产路径格式: /Game/类别/Name (不含 .uasset)

[user prompt]
原始用户需求: {user_description}
当前 JSON:
{scene_json}

校验错误:
{errors_list}

请修复所有错误，输出完整的修复后 JSON。只输出 JSON。
```

---

## 5. 成功率预估与成本分析

### 5.1 成功率预估

| 指标 | 无经验库 | 有经验库(50条) | 有经验库(200条) |
|------|----------|----------------|-----------------|
| JSON 格式合法 | 99%+ | 99%+ | 99%+ |
| 字段校验通过 | 95%+ | 97%+ | 98%+ |
| 资产路径有效 | 90%+ | 95%+ | 97%+ |
| 场景可构建(umap) | 85%+ | 92%+ | 95%+ |
| **视觉效果满足预期** | **50-60%** | **70-80%** | **85-90%+** |

> NeurIPS 2025 研究：积累成功轨迹作为 few-shot，73%→93%，效果超过升级模型(gpt-4o-mini→gpt-4o)。

### 5.2 成本分析（以 DeepSeek 为例）

| 阶段 | 输入 tokens | 输出 tokens | 单次成本(估算) |
|------|-------------|-------------|-----------------|
| Stage 1 意图解析 | ~500 | ~200 | ¥0.001 |
| Stage 2 JSON 生成 | ~5000 | ~3000 | ¥0.015 |
| Stage 3 验证(0错误) | 0 | 0 | ¥0 |
| Stage 3 修复(1轮) | ~6000 | ~3000 | ¥0.018 |
| **单次生成(无修复)** | ~5500 | ~3200 | **¥0.016** |
| **单次生成(1轮修复)** | ~11500 | ~6200 | **¥0.034** |

> DeepSeek 定价: 输入 ¥0.5/百万tokens, 输出 ¥1.5/百万tokens (cache miss)
> Prompt Caching 命中时输入成本降低 50-90%

### 5.3 Prompt Caching 策略

| Prompt 部分 | 是否可缓存 | 原因 |
|-------------|-----------|------|
| L1 核心知识 | ✓ | 内容固定，始终在 prompt 前缀 |
| L2 模式文档 | ✓ | 同类型场景共用 |
| L3 资产路径 | △ | 关键词不同则变化 |
| L4 经验 Few-shot | ✗ | 每次检索结果不同 |

> 估算：L1+L2 占总输入的 60-70%，缓存命中可节省 35-50% 输入成本。

---

## 6. 技术选型理由

| 决策 | 选择 | 理由 |
|------|------|------|
| GUI 框架 | PyQt6 | 已有 mapforge_app.py 基础，零迁移成本 |
| LLM 接口 | OpenAI 兼容 | 一个 SDK 适配阿里云/DeepSeek/OpenAI/Ollama |
| 本地存储 | SQLite | Python 内置 sqlite3，零依赖 |
| 相似度算法 | Jaccard 关键词 | 零依赖，首期够用；后期可升级 Embeddings |
| 知识注入 | 分层按需 | 全量1.5MB→按需10-24KB，缩减60-150倍 |
| 验证方式 | import 现有脚本 | 直接调用 validate_scene() 函数，不重复造轮子 |
| 打包方式 | PyInstaller | 已有 MapForge.spec，扩展即可 |
| 线程模型 | QThread + 信号 | 与现有 BuildWorker 模式一致 |

---

# 第二部分：实施计划

> **核心原则**：每个 Phase 完成后立即独立验证，验证通过才进入下一 Phase。
> 绝不在全部写完后才统一测试。

## Phase 0: 项目骨架

### 目标
创建目录结构和包初始化文件，确保后续模块有地方放。

### 前置条件
- 已有 `MapForgeTest/mapforge_app.py`
- Python 3.10+ 环境

### 产出文件
```
MapForgeTest/
├── ai/
│   ├── __init__.py          # Phase 11 填充（run_pipeline 编排函数）
│   ├── utils.py             # Phase 4 填充（extract_json 等工具函数）
│   ├── client.py            # Phase 1 填充
│   ├── knowledge.py          # Phase 2 填充
│   ├── asset_index.py        # Phase 3 填充
│   ├── intent_parser.py      # Phase 4 填充
│   ├── generator.py          # Phase 5 填充
│   ├── validator.py          # Phase 6 填充
│   ├── experience_bank.py    # Phase 7 填充
│   └── retriever.py          # Phase 8 填充
├── data/
│   ├── knowledge/            # Phase 2 填充
│   └── experience.db         # Phase 7 自动生成（~/.mapforge/ 下）
└── tests/
    └── __init__.py           # 空文件
```

### 实现要点
1. 创建 `ai/` 目录和所有空 `.py` 文件（只有文件头注释）
2. 创建 `data/knowledge/` 空目录
3. 创建 `tests/` 目录
4. 在 `ai/utils.py` 中预留 `extract_json()` 函数签名（Phase 4 实现）
5. **环境变量约定**：API key 通过环境变量 `MAPFORGE_API_KEY` 传入，验证脚本统一使用 `os.environ.get('TEST_API_KEY', '')` 或 `os.environ.get('MAPFORGE_API_KEY', '')`

### 验证方法
```bash
# 验证目录结构和 import 不报错
cd c:\Users\25868\Desktop\UE5\MapForgeTest
python -c "import ai; print('ai package OK')"
python -c "import ai.client; print('client module OK')"
python -c "import ai.knowledge; print('knowledge module OK')"
python -c "import ai.utils; print('utils module OK')"
```

### 通过标准
- 四个 import 命令均输出 OK，无 ImportError
- `~/.mapforge/` 目录可创建（Phase 7 经验库存放位置）

---

## Phase 1: LLM 客户端集成

### 目标
复制 SceneWeaver 的 LLM 客户端，适配扩展 `complete()` 方法以支持 JSON Mode 和 `max_tokens`。

### 前置条件
- Phase 0 通过

### 产出文件
- `ai/client.py` — 完整复制 + 适配扩展

### 实现要点
1. 将 `LLM_UEMaps/源码/src/sceneweaver/llm/client.py` 完整复制到 `ai/client.py`
2. 文件头添加中文注释说明来源和适配内容
3. **适配扩展 `complete()` 方法**：确保 `**kwargs` 中的 `response_format` 和 `max_tokens` 能透传到底层 API 调用
   - `response_format={"type": "json_object"}`：启用 JSON Mode，让 LLM 保证输出合法 JSON
   - `max_tokens=4096`：限制输出长度，防止场景 JSON 过长被截断
   - 原始 client.py 的 `complete()` 如果已有 `**kwargs` 透传机制，则无需改代码；否则需在调用处显式传参

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: Mock 客户端（零依赖，不需要 API key）
python -c "
from ai.client import MockLLMClient
c = MockLLMClient(['{\"test\": true}'])
r = c.complete('sys', 'user')
assert r == '{\"test\": true}'
print('Mock 客户端测试通过')
"

# 验证2: OpenAI 客户端初始化（不实际调用，只验证能创建对象）
python -c "
from ai.client import OpenAILLMClient
c = OpenAILLMClient(api_key='test-key', model='gpt-4o', base_url='https://api.deepseek.com/v1')
print('OpenAI 客户端初始化通过')
"

# 验证3: complete() 支持 response_format 和 max_tokens kwargs 透传
python -c "
from ai.client import MockLLMClient
c = MockLLMClient(['{\"test\": true}'])
# 验证 kwargs 透传不报错（Mock 客户端忽略这些参数，但不应该拒绝）
r = c.complete('sys', 'user', response_format={'type': 'json_object'}, max_tokens=4096)
assert r == '{\"test\": true}'
print('kwargs 透传验证通过')
"

# 验证4: 实际 API 调用（需要用户提供真实 key）
python -c "
import os
key = os.environ.get('TEST_API_KEY', '') or os.environ.get('MAPFORGE_API_KEY', '')
if not key:
    print('跳过: 未设置 TEST_API_KEY 或 MAPFORGE_API_KEY 环境变量')
else:
    from ai.client import OpenAILLMClient
    c = OpenAILLMClient(api_key=key, model='deepseek-chat', base_url='https://api.deepseek.com/v1')
    r = c.complete('你是测试助手', '回复OK')
    print('API 调用结果:', r[:50])
"
```

### 通过标准
- Mock 客户端测试通过
- OpenAI 客户端能初始化（不报错）
- `complete()` 接受 `response_format` 和 `max_tokens` kwargs 不报错
- 实际 API 调用（如有 key）返回非空响应

---

## Phase 2: 知识包构建器

### 目标
将 UE5_JSON 技能文档提取到 `data/knowledge/`，实现分层组装 system prompt。

### 前置条件
- Phase 1 通过
- UE5_JSON 技能文件存在于 `~/.trae-cn/skills/ue5_json/`

### 产出文件
- `data/knowledge/core.md` — 核心知识（从 SKILL.md 提取）
- `data/knowledge/height_pattern.md` — 复制自 `references/height_pattern.md`
- `data/knowledge/weight_pattern.md` — 复制自 `references/weight_pattern.md`
- `data/knowledge/placements.md` — 复制自 `references/placements.md`
- `data/knowledge/asset_guide.md` — 复制自 `references/asset_guide.md`
- `data/knowledge/examples.md` — 复制自 `references/examples.md`（可复制 JSON 示例）
- `ai/knowledge.py` — KnowledgePack 类实现

### 实现要点

1. **提取核心知识** (`data/knowledge/core.md`)：
   从 SKILL.md 中提取：
   - 顶层结构（6个分区）
   - 两层解析概念
   - 字段速查表（从 project_rules.md 的速查表）
   - 关键约束（weight 0~1, 路径格式, 单位混淆）
   - 目标大小：~3KB

2. **复制模式文档**：
   ```python
   # 一键复制脚本 (knowledge.py 的 _init_data 方法)
   import shutil
   src = os.path.expanduser("~/.trae-cn/skills/ue5_json/references")
   dst = "data/knowledge"
   for f in ["height_pattern.md", "weight_pattern.md", "placements.md", "asset_guide.md", "examples.md"]:
       shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
   ```

3. **KnowledgePack 实现**：
   ```python
   class KnowledgePack:
       def __init__(self, knowledge_dir="data/knowledge"):
           self._dir = knowledge_dir
           self._core = self._read("core.md")
           self._cache = {}  # 模式文档缓存
       
       def _read(self, name):
           path = os.path.join(self._dir, name)
           with open(path, "r", encoding="utf-8") as f:
               return f.read()
       
       def _get_pattern(self, name):
           if name not in self._cache:
               self._cache[name] = self._read(name)
           return self._cache[name]
       
       def build_system_prompt(self, intent, asset_paths, few_shots):
           parts = [self._core]
           
           # L2: 按意图选择模式文档
           terrain = intent.get("terrain_type", "features")
           # 有地形特征或有水/有河流时注入 height_pattern
           if terrain != "flat" or intent.get("has_water") or intent.get("has_river"):
               parts.append(self._get_pattern("height_pattern.md"))
           # 有草地/麦田时注入 weight_pattern
           if intent.get("has_grass") or intent.get("has_wheat"):
               parts.append(self._get_pattern("weight_pattern.md"))
           # 有 placements 时注入 placements + asset_guide（路径转换规则）
           if intent.get("placements"):
               parts.append(self._get_pattern("placements.md"))
               parts.append(self._get_pattern("asset_guide.md"))
           
           # 始终注入 examples.md（可复制 JSON 示例，帮助 LLM 理解完整结构）
           parts.append(self._get_pattern("examples.md"))
           
           # L3: 资产路径
           if asset_paths:
               asset_text = "\n".join(asset_paths[:30])
               parts.append(f"可用资产路径:\n{asset_text}")
           
           # L4: Few-shot 经验
           for i, exp in enumerate(few_shots):
               parts.append(f"--- 示例{i+1} ---")
               parts.append(f"用户描述: {exp['user_desc']}")
               parts.append(f"场景 JSON:\n{exp['scene_json']}")
           
           return "\n\n".join(parts)
   ```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 知识文件存在且非空
python -c "
import os
for f in ['core.md', 'height_pattern.md', 'weight_pattern.md', 'placements.md', 'asset_guide.md', 'examples.md']:
    path = os.path.join('data/knowledge', f)
    size = os.path.getsize(path) if os.path.exists(path) else -1
    print(f'{f}: {size} bytes')
    assert size > 100, f'{f} 太小或不存在'
print('知识文件验证通过')
"

# 验证2: KnowledgePack 能组装 prompt
python -c "
from ai.knowledge import KnowledgePack
kp = KnowledgePack('data/knowledge')
intent = {
    'terrain_type': 'features',
    'has_water': True,
    'has_river': True,
    'has_grass': True,
    'placements': ['trees'],
}
prompt = kp.build_system_prompt(intent, ['/Game/Test/asset1', '/Game/Test/asset2'], [])
assert len(prompt) > 1000, f'prompt 太短: {len(prompt)}'
assert '两层' in prompt or 'layer' in prompt.lower(), '缺少核心知识'
assert 'height_pattern' in prompt.lower() or 'features' in prompt.lower(), '缺少模式文档'
assert 'examples' in prompt.lower() or '示例' in prompt, '缺少 examples.md 注入'
print(f'KnowledgePack 测试通过, prompt 长度: {len(prompt)} 字符')
"

# 验证3: 不同意图组装不同 prompt
python -c "
from ai.knowledge import KnowledgePack
kp = KnowledgePack('data/knowledge')
# 简单场景: 纯平地无地形
prompt_simple = kp.build_system_prompt(
    {'terrain_type': 'flat', 'has_grass': False, 'placements': []}, [], [])
# 复杂场景: 山谷+河流+草地+树
prompt_complex = kp.build_system_prompt(
    {'terrain_type': 'features', 'has_river': True, 'has_grass': True, 'placements': ['trees']},
    ['/Game/tree1'], [])
assert len(prompt_complex) > len(prompt_simple), '复杂场景 prompt 应更长'
assert 'asset' in prompt_complex.lower(), '复杂场景应注入 asset_guide.md'
print(f'分层注入验证通过: simple={len(prompt_simple)}, complex={len(prompt_complex)}')
"
```

### 通过标准
- 所有知识文件存在且 >100 bytes
- KnowledgePack 能组装 >1000 字符的 prompt
- 复杂场景 prompt 比简单场景更长（分层注入生效）

---

## Phase 3: 资产关键词索引

### 目标
从 asset_catalog.json 构建关键词索引，支持按关键词搜索资产路径。

### 前置条件
- Phase 2 通过
- `asset_catalog.json` 存在（已确认 7691 条资产）

### 产出文件
- `ai/asset_index.py` — AssetIndex 类实现

### 实现要点

```python
class AssetIndex:
    def __init__(self, catalog_path="asset_catalog.json"):
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._assets = data.get("assets", [])
    
    def search(self, keywords, max_results=20):
        scored = []
        for asset in self._assets:
            score = self._match_score(asset, keywords)
            if score > 0:
                scored.append((score, asset["path"]))
        scored.sort(key=lambda x: -x[0])
        seen = set()
        result = []
        for _, path in scored:
            if path not in seen:
                seen.add(path)
                result.append(path)
            if len(result) >= max_results:
                break
        return result
    
    def _match_score(self, asset, keywords):
        name = asset.get("name", "").lower()
        cat = asset.get("category", "").lower()
        sub = asset.get("subfolder", "").lower()
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in name:
                score += 3  # name 匹配权重最高
            if kw_lower in cat:
                score += 2
            if kw_lower in sub:
                score += 1
        return score
    
    def search_by_category(self, category, max_results=50):
        result = []
        for asset in self._assets:
            if asset.get("category", "").lower() == category.lower():
                result.append(asset["path"])
            if len(result) >= max_results:
                break
        return result
```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 能加载 7691 条资产
python -c "
from ai.asset_index import AssetIndex
idx = AssetIndex('asset_catalog.json')
print(f'加载资产数: {len(idx._assets)}')
assert len(idx._assets) > 5000, '资产数太少'
print('资产加载验证通过')
"

# 验证2: 关键词搜索返回结果
python -c "
from ai.asset_index import AssetIndex
idx = AssetIndex('asset_catalog.json')
results = idx.search(['tree', 'fir'], max_results=10)
print(f'tree+fir 搜索结果({len(results)}条):')
for r in results[:3]:
    print(f'  {r}')
assert len(results) > 0, '搜索无结果'
print('关键词搜索验证通过')
"

# 验证3: 中文关键词搜索
python -c "
from ai.asset_index import AssetIndex
idx = AssetIndex('asset_catalog.json')
results = idx.search(['house'], max_results=10)
print(f'house 搜索结果({len(results)}条):')
for r in results[:3]:
    print(f'  {r}')
assert len(results) > 0, 'house 搜索无结果'
print('多关键词验证通过')
"

# 验证4: category 精确搜索
python -c "
from ai.asset_index import AssetIndex
idx = AssetIndex('asset_catalog.json')
results = idx.search_by_category('rural_house', max_results=5)
print(f'rural_house category 搜索({len(results)}条):')
for r in results[:3]:
    print(f'  {r}')
print('category 搜索验证通过')
"
```

### 通过标准
- 加载资产数 >5000
- 关键词搜索(tree/fir/house)返回非空结果
- category 搜索返回非空结果

---

## Phase 4: 意图解析器（Stage 1）

### 目标
实现 Stage 1：从自然语言提取结构化意图 JSON。

### 前置条件
- Phase 1 通过（LLM 客户端可用）
- 有可用的 API key（或使用 Mock 测试）

### 产出文件
- `ai/utils.py` — JSON 提取工具函数（extract_json 等）
- `ai/intent_parser.py` — IntentParser 类实现

### 实现要点

**0. JSON 提取工具函数** (`ai/utils.py`)：

```python
import json
import re

def extract_json(text):
    """
    三层 JSON 提取策略（兼容 JSON Mode 和非 JSON Mode 响应）:
    1. 直接解析: json.loads(text) — JSON Mode 响应通常是纯 JSON
    2. 代码块提取: 从 ```json ... ``` 或 ``` ... ``` 中提取
    3. 首尾大括号: 找第一个 { 到最后一个 }，尝试解析
    
    返回: 解析后的 dict/list，失败时抛出 json.JSONDecodeError
    """
    text = text.strip()
    
    # 层1: 直接解析（JSON Mode 响应）
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 层2: 从 markdown 代码块提取
    code_block_pattern = r'```(?:json)?\s*\n?(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue
    
    # 层3: 首尾大括号截取
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        snippet = text[first_brace:last_brace + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass
    
    # 全部失败，抛出异常
    raise json.JSONDecodeError("无法从响应中提取 JSON", text, 0)
```

**1. IntentParser 实现** (`ai/intent_parser.py`)：

```python
import json
from ai.client import LLMClient
from ai.utils import extract_json

INTENT_PROMPT = """你是一个 UE5 场景意图解析器。从用户描述中提取结构化信息。

输出 JSON，严格遵循以下 schema:
{
  "terrain_type": "flat|ridge|hill|noise|hill_ridge|features|terraced|karst|gully",
  "has_water": bool,
  "has_river": bool,
  "has_road": bool,
  "has_buildings": bool,
  "has_grass": bool,
  "has_wheat": bool,
  "has_snow": bool,
  "scene_scale": "500m|1km|2km",
  "placements": ["trees", "fence", "heliport", ...],
  "keywords": ["中文关键词1", "关键词2", ...],
  "complexity": "simple|medium|complex"
}

规则:
- terrain_type 不确定时默认 "features"
- scene_scale 不确定时默认 "1km"
- complexity: 少于3个元素=simple, 3-6个=medium, 6个以上=complex
- keywords: 提取所有可用作资产搜索的关键词

只输出 JSON，不要其他文字。"""

FALLBACK_INTENT = {
    "terrain_type": "features",
    "has_water": False, "has_river": False, "has_road": False,
    "has_buildings": False, "has_grass": True, "has_wheat": False,
    "has_snow": False, "scene_scale": "1km",
    "placements": [], "keywords": [], "complexity": "medium",
}

class IntentParser:
    def __init__(self, client, model=None):
        self._client = client
        self._model = model
    
    def parse(self, user_description):
        kwargs = {}
        if self._model:
            kwargs["model"] = self._model
        # 启用 JSON Mode + 限制 token 数
        kwargs["response_format"] = {"type": "json_object"}
        kwargs["max_tokens"] = 2048
        try:
            resp = self._client.complete(INTENT_PROMPT, user_description, **kwargs)
            # 三层 JSON 提取（兼容 JSON Mode 和非 JSON Mode 响应）
            intent = extract_json(resp)
            # 合并 fallback 确保所有字段存在
            result = FALLBACK_INTENT.copy()
            result.update(intent)
            return result
        except Exception:
            return FALLBACK_INTENT.copy()
```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证0: extract_json 三层提取工具函数
python -c "
from ai.utils import extract_json
import json

# 层1: 纯 JSON（JSON Mode 响应）
r1 = extract_json('{\"a\": 1}')
assert r1 == {'a': 1}, f'层1失败: {r1}'

# 层2: markdown 代码块包裹
r2 = extract_json('这是说明文字\n\`\`\`json\n{\"b\": 2}\n\`\`\`\n后续文字')
assert r2 == {'b': 2}, f'层2失败: {r2}'

# 层2b: 无 json 标记的代码块
r2b = extract_json('\`\`\`\n{\"c\": 3}\n\`\`\`')
assert r2b == {'c': 3}, f'层2b失败: {r2b}'

# 层3: 混杂文本中的 JSON
r3 = extract_json('好的，这是结果: {\"d\": 4} 完成')
assert r3 == {'d': 4}, f'层3失败: {r3}'

print('extract_json 三层提取验证通过')
"

# 验证1: Mock 客户端 + 预设响应
python -c "
from ai.client import MockLLMClient
from ai.intent_parser import IntentParser

mock_resp = '{\"terrain_type\": \"features\", \"has_river\": true, \"has_grass\": true, \"keywords\": [\"山谷\", \"河流\", \"草地\"], \"scene_scale\": \"1km\", \"complexity\": \"medium\"}'
mock = MockLLMClient([mock_resp])
parser = IntentParser(mock)
intent = parser.parse('生成一个1km的山谷草地场景，有河流')

assert intent['terrain_type'] == 'features'
assert intent['has_river'] == True
assert intent['has_grass'] == True
assert '山谷' in intent['keywords']
print('Mock 意图解析验证通过')
print('解析结果:', intent)
"

# 验证2: 异常容错（LLM 返回垃圾数据时 fallback）
python -c "
from ai.client import MockLLMClient
from ai.intent_parser import IntentParser, FALLBACK_INTENT

mock = MockLLMClient(['这不是JSON'])
parser = IntentParser(mock)
intent = parser.parse('测试')
assert intent == FALLBACK_INTENT, '异常时应返回 fallback'
print('异常容错验证通过')
"

# 验证3: 实际 API 调用（需要 API key）
python -c "
import os
key = os.environ.get('TEST_API_KEY', '')
if not key:
    print('跳过: 未设置 TEST_API_KEY')
else:
    from ai.client import OpenAILLMClient
    from ai.intent_parser import IntentParser
    c = OpenAILLMClient(api_key=key, model='deepseek-chat', base_url='https://api.deepseek.com/v1')
    parser = IntentParser(c)
    intent = parser.parse('生成一个2km的雪山场景，有松树林和一条蜿蜒的河流')
    print('实际解析结果:', intent)
    assert 'terrain_type' in intent
    assert 'keywords' in intent
    print('实际 API 意图解析验证通过')
"
```

### 通过标准
- Mock 解析返回正确的 intent dict
- 异常输入返回 FALLBACK_INTENT（不崩溃）
- 实际 API（如有 key）返回合法 intent

---

## Phase 5: JSON 生成器（Stage 2）

### 目标
实现 Stage 2：组装知识 + 调用 LLM 生成完整场景 JSON。

### 前置条件
- Phase 2（知识包）、Phase 3（资产索引）、Phase 4（意图解析）均通过

### 产出文件
- `ai/generator.py` — SceneGenerator 类实现

### 实现要点

```python
import json
from ai.client import LLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.utils import extract_json

class SceneGenerator:
    def __init__(self, client, knowledge, asset_index, model=None):
        self._client = client
        self._knowledge = knowledge
        self._asset_index = asset_index
        self._model = model
    
    def generate(self, user_description, intent, few_shots=None):
        # 1. 搜索资产
        keywords = intent.get("keywords", [])
        asset_paths = self._asset_index.search(keywords, max_results=30)
        
        # 2. 组装 system prompt
        system_prompt = self._knowledge.build_system_prompt(
            intent, asset_paths, few_shots or []
        )
        
        # 3. 组装 user prompt
        user_prompt = f"用户需求: {user_description}\n意图分析: {json.dumps(intent, ensure_ascii=False)}\n\n请生成完整的场景 JSON。只输出 JSON，不要 markdown 代码块标记。"
        
        # 4. 调用 LLM（启用 JSON Mode + max_tokens 防止截断）
        kwargs = {
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        }
        if self._model:
            kwargs["model"] = self._model
        resp = self._client.complete(system_prompt, user_prompt, **kwargs)
        
        # 5. 三层 JSON 提取（兼容 JSON Mode 和非 JSON Mode 响应）
        scene = extract_json(resp)
        return scene
```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: Mock 客户端 + 预设 JSON 响应
python -c "
import json
from ai.client import MockLLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.generator import SceneGenerator

# 预设一个合法的简单场景 JSON
mock_scene = json.dumps({
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/Materials/M_Landscape',
        'section_size_quads': 63,
        'num_subsections': 2,
        'component_count_x': 8,
        'component_count_y': 8,
        'layers': [{'info': '/Game/Layers/Default', 'weight': 1.0}]
    }
})

mock = MockLLMClient([mock_scene])
kp = KnowledgePack('data/knowledge')
ai = AssetIndex('asset_catalog.json')
gen = SceneGenerator(mock, kp, ai)

intent = {'terrain_type': 'features', 'has_grass': True, 'keywords': ['grass'], 'placements': []}
scene = gen.generate('生成一个草地场景', intent)

assert 'scene' in scene
assert 'landscape' in scene
assert scene['scene']['target_level'] == '/Game/Maps/Test'
print('Mock JSON 生成验证通过')
print('生成的场景键:', list(scene.keys()))
"

# 验证2: 生成的 JSON 能通过字段校验
python -c "
import json
from ai.client import MockLLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.generator import SceneGenerator
from validate_scene_json import validate_scene

mock_scene = json.dumps({
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/Materials/M_Landscape',
        'section_size_quads': 63,
        'num_subsections': 2,
        'component_count_x': 8,
        'component_count_y': 8,
        'layers': [{'info': '/Game/Layers/Default', 'weight': 1.0}]
    }
})

mock = MockLLMClient([mock_scene])
kp = KnowledgePack('data/knowledge')
ai = AssetIndex('asset_catalog.json')
gen = SceneGenerator(mock, kp, ai)

intent = {'terrain_type': 'features', 'has_grass': True, 'keywords': ['grass'], 'placements': []}
scene = gen.generate('生成一个草地场景', intent)

errors, warnings = validate_scene(scene)
print(f'校验结果: {len(errors)} 错误, {len(warnings)} 警告')
if errors:
    for e in errors[:5]:
        print(f'  [ERROR] {e}')
assert len(errors) == 0, f'生成的 JSON 有校验错误: {errors[:3]}'
print('字段校验验证通过')
"

# 验证3: 实际 API 生成（需要 API key）
python -c "
import os, json
key = os.environ.get('TEST_API_KEY', '')
if not key:
    print('跳过: 未设置 TEST_API_KEY')
else:
    from ai.client import OpenAILLMClient
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.generator import SceneGenerator
    from ai.intent_parser import IntentParser
    from validate_scene_json import validate_scene

    c = OpenAILLMClient(api_key=key, model='deepseek-chat', base_url='https://api.deepseek.com/v1')
    kp = KnowledgePack('data/knowledge')
    ai = AssetIndex('asset_catalog.json')
    
    parser = IntentParser(c)
    intent = parser.parse('生成一个1km的山谷草地场景，有河流')
    print('意图:', intent)
    
    gen = SceneGenerator(c, kp, ai)
    scene = gen.generate('生成一个1km的山谷草地场景，有河流', intent)
    
    errors, warnings = validate_scene(scene)
    print(f'生成完成, {len(errors)} 错误, {len(warnings)} 警告')
    if errors:
        for e in errors[:5]:
            print(f'  [ERROR] {e}')
    print('实际 API 生成验证', '通过' if len(errors) < 5 else '需修复')
"
```

### 通过标准
- Mock 生成返回合法 JSON dict
- Mock 生成的 JSON 通过 validate_scene 校验（0 错误）
- 实际 API（如有 key）生成可通过校验或仅有少量错误（交由 Phase 6 修复）

---

## Phase 6: 验证-修复循环（Stage 3）

### 目标
实现 Stage 3：调用现有校验脚本，有错误时用 LLM 修复，最多 3 轮。

### 前置条件
- Phase 5 通过
- `validate_scene_json.py` 可 import

### 产出文件
- `ai/validator.py` — ValidationRepairLoop 类实现

### 实现要点

```python
import json
from ai.client import LLMClient
from ai.knowledge import KnowledgePack
from ai.utils import extract_json
from validate_scene_json import validate_scene

REPAIR_PROMPT_TEMPLATE = """你是 UE5 场景 JSON 修复器。以下 JSON 有校验错误，请修复。

校验规则摘要:
- 顶层键: scene, landscape, ground, placements, lighting, weather, rivers
- scene 必填: target_level
- landscape 必填: material, section_size_quads, num_subsections, component_count_x/y
- height_pattern.type 枚举: flat, ridge, hill, noise, hill_ridge, features, terraced, karst, gully
- weight_pattern.pattern 枚举: uniform, height_based, slope_based, region, multi_region, noise_based, aspect_based, snow_line
- placement.type 枚举: group, instanced_grid, instances, static, blueprint, crop_field, village
- weight 值范围: 0~1
- 资产路径格式: /Game/类别/Name (不含 .uasset)

原始用户需求: {user_desc}
当前 JSON:
{scene_json}

校验错误:
{errors_list}

请修复所有错误，输出完整的修复后 JSON。只输出 JSON，不要 markdown 代码块标记。"""

class ValidationRepairLoop:
    def __init__(self, client, knowledge=None, model=None, max_rounds=3):
        self._client = client
        self._knowledge = knowledge  # KnowledgePack，用于注入修复时的知识上下文
        self._model = model
        self._max_rounds = max_rounds
    
    def validate_and_repair(self, scene, user_description="", intent=None):
        history = []
        current = scene
        
        # 构建修复用的 system_prompt（注入知识包，帮助 LLM 理解正确格式）
        system_prompt = ""
        if self._knowledge and intent:
            system_prompt = self._knowledge.build_system_prompt(intent, [], [])
        
        for round_num in range(self._max_rounds):
            # 1. 字段校验
            errors, warnings = validate_scene(current)
            
            history.append({
                "round": round_num + 1,
                "errors": errors,
                "warnings": warnings,
            })
            
            # 2. 无错误 → 通过
            if not errors:
                return current, history
            
            # 3. 有错误 → LLM 修复（注入知识包 system_prompt + 错误信息）
            errors_text = "\n".join("- " + e for e in errors)
            prompt = REPAIR_PROMPT_TEMPLATE.format(
                user_desc=user_description,
                scene_json=json.dumps(current, ensure_ascii=False, indent=2),
                errors_list=errors_text,
            )
            
            # 启用 JSON Mode + max_tokens 防止截断
            kwargs = {
                "response_format": {"type": "json_object"},
                "max_tokens": 4096,
            }
            if self._model:
                kwargs["model"] = self._model
            
            try:
                resp = self._client.complete(system_prompt, prompt, **kwargs)
                # 三层 JSON 提取（兼容 JSON Mode 和非 JSON Mode 响应）
                current = extract_json(resp)
            except Exception:
                # 修复失败，返回当前版本
                history[-1]["repair_failed"] = True
                return current, history
        
        # 超过最大轮数
        return current, history
```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 无错误场景直接通过（1轮）
python -c "
from ai.client import MockLLMClient
from ai.validator import ValidationRepairLoop

good_scene = {
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/M', 'section_size_quads': 63,
        'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8,
        'layers': [{'info': '/Game/L', 'weight': 1.0}]
    }
}
mock = MockLLMClient([])  # 无需 LLM 响应（无错误不调用）
loop = ValidationRepairLoop(mock)
final, history = loop.validate_and_repair(good_scene, '测试场景')
assert len(history) == 1, f'无错误应1轮通过, 实际{len(history)}'
assert len(history[0]['errors']) == 0, '第1轮应无错误'
print('无错误直通验证通过')
"

# 验证2: 有错误场景经 LLM 修复后通过（2轮）
python -c "
import json
from ai.client import MockLLMClient
from ai.validator import ValidationRepairLoop

# 有错误的场景（缺少必填字段）
bad_scene = {'scene': {}}  # 缺少 target_level + 整个 landscape

# 修复后的合法场景
fixed_scene = json.dumps({
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/M', 'section_size_quads': 63,
        'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8,
        'layers': [{'info': '/Game/L', 'weight': 1.0}]
    }
})
mock = MockLLMClient([fixed_scene])
loop = ValidationRepairLoop(mock)
final, history = loop.validate_and_repair(bad_scene, '测试场景')
assert len(history) == 2, f'应有2轮(1错误+1通过), 实际{len(history)}'
assert len(history[0]['errors']) > 0, '第1轮应有错误'
assert len(history[1]['errors']) == 0, '第2轮应无错误'
print('错误修复验证通过')
print(f'修复轮数: {len(history)}')
"

# 验证3: 修复失败后返回当前版本（不崩溃）
python -c "
from ai.client import MockLLMClient
from ai.validator import ValidationRepairLoop

broken_scene = {'scene': {}}  # 严重缺失
mock = MockLLMClient(['不是JSON'])  # 修复也返回垃圾
loop = ValidationRepairLoop(mock, max_rounds=2)
final, history = loop.validate_and_repair(broken_scene, '测试')
assert isinstance(final, dict), '最终结果应仍为dict'
assert len(history) <= 2, f'不应超过2轮, 实际{len(history)}'
print('修复失败容错验证通过')
"

# 验证4: 实际 API 修复（需要 API key，注入知识包）
python -c "
import os, json
key = os.environ.get('TEST_API_KEY', '') or os.environ.get('MAPFORGE_API_KEY', '')
if not key:
    print('跳过: 未设置 TEST_API_KEY 或 MAPFORGE_API_KEY')
else:
    from ai.client import OpenAILLMClient
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.generator import SceneGenerator
    from ai.intent_parser import IntentParser
    from ai.validator import ValidationRepairLoop

    c = OpenAILLMClient(api_key=key, model='deepseek-chat', base_url='https://api.deepseek.com/v1')
    kp = KnowledgePack('data/knowledge')
    ai = AssetIndex('asset_catalog.json')
    
    desc = '生成一个1km的山谷草地场景，有河流'
    parser = IntentParser(c)
    intent = parser.parse(desc)
    gen = SceneGenerator(c, kp, ai)
    scene = gen.generate(desc, intent)
    
    # 传入 knowledge + intent，修复时注入知识包 system_prompt
    loop = ValidationRepairLoop(c, knowledge=kp)
    final, history = loop.validate_and_repair(scene, desc, intent=intent)
    
    total_errors = sum(len(h['errors']) for h in history)
    print(f'验证-修复完成: {len(history)}轮, 总错误{total_errors}个')
    if history:
        print(f'最终错误数: {len(history[-1][\"errors\"])}')
    print('实际 API 修复验证', '通过' if not history[-1]['errors'] else '仍有错误')
"
```

### 通过标准
- 无错误场景 1 轮通过
- 有错误场景经 LLM 修复后通过（2 轮）
- 修复失败不崩溃，返回 dict
- 实际 API（如有 key）最终 0 错误或错误数递减
- 修复时注入了知识包 system_prompt（验证4中 `knowledge=kp` 和 `intent=intent`）

---

## Phase 7: 经验记忆库存储

### 目标
实现 SQLite 经验库，支持保存/检索历史成功场景。

### 前置条件
- Phase 6 通过

### 产出文件
- `ai/experience_bank.py` — ExperienceBank 类实现
- `data/experience.db` — SQLite 数据库（自动创建）

### 实现要点

```python
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime, timedelta

class ExperienceBank:
    def __init__(self, db_path=None):
        # 默认存到用户主目录 ~/.mapforge/，避免打包后 exe 目录只读
        if db_path is None:
            db_path = str(Path.home() / ".mapforge" / "experience.db")
        self._db_path = db_path
        dir_path = os.path.dirname(db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
    
    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_desc       TEXT NOT NULL,
                intent_json     TEXT NOT NULL,
                scene_json      TEXT NOT NULL,
                rating          INTEGER DEFAULT 3,
                tags            TEXT DEFAULT '',
                embedding       TEXT DEFAULT '',
                created_at      TEXT NOT NULL,
                used_count      INTEGER DEFAULT 0,
                last_used_at    TEXT,
                success_count   INTEGER DEFAULT 0,
                fail_count      INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()
    
    def _find_similar(self, intent, threshold=0.6):
        """查找与当前 intent 关键词 Jaccard 相似度 ≥ threshold 的已有经验
        用于去重：相似经验存在则更新而非新增
        """
        my_keywords = set(intent.get("keywords", []))
        if not my_keywords:
            return None
        for exp in self.get_all():
            exp_kw = set(exp["intent"].get("keywords", []))
            if not exp_kw:
                continue
            jaccard = len(my_keywords & exp_kw) / len(my_keywords | exp_kw)
            if jaccard >= threshold:
                return exp
        return None

    def save(self, user_desc, intent, scene, rating=3, tags=""):
        # 去重：查找相似经验，存在则更新而非新增
        similar = self._find_similar(intent)
        if similar:
            now = datetime.now().isoformat()
            self._conn.execute(
                "UPDATE experiences SET user_desc=?, intent_json=?, scene_json=?, "
                "rating=?, tags=?, created_at=? WHERE id=?",
                (user_desc, json.dumps(intent, ensure_ascii=False),
                 json.dumps(scene, ensure_ascii=False), rating, tags, now, similar["id"])
            )
            self._conn.commit()
            return similar["id"]
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO experiences (user_desc, intent_json, scene_json, rating, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_desc, json.dumps(intent, ensure_ascii=False),
             json.dumps(scene, ensure_ascii=False), rating, tags, now)
        )
        self._conn.commit()
        return cursor.lastrowid
    
    def get_all(self):
        rows = self._conn.execute("SELECT * FROM experiences ORDER BY created_at DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]
    
    def get_by_id(self, exp_id):
        row = self._conn.execute("SELECT * FROM experiences WHERE id = ?", (exp_id,)).fetchone()
        return self._row_to_dict(row) if row else None
    
    def update_rating(self, exp_id, rating):
        self._conn.execute("UPDATE experiences SET rating = ? WHERE id = ?", (rating, exp_id))
        self._conn.commit()
    
    def update_usage(self, exp_id, success):
        now = datetime.now().isoformat()
        if success:
            self._conn.execute(
                "UPDATE experiences SET used_count = used_count + 1, "
                "success_count = success_count + 1, last_used_at = ? WHERE id = ?",
                (now, exp_id))
        else:
            self._conn.execute(
                "UPDATE experiences SET used_count = used_count + 1, "
                "fail_count = fail_count + 1, last_used_at = ? WHERE id = ?",
                (now, exp_id))
        self._conn.commit()
    
    def get_stats(self):
        row = self._conn.execute(
            "SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM experiences"
        ).fetchone()
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        recent = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM experiences WHERE created_at > ?", (week_ago,)
        ).fetchone()
        return {
            "total": row["total"],
            "avg_rating": round(row["avg_rating"] or 0, 2),
            "recent_7d": recent["cnt"],
        }
    
    def _row_to_dict(self, row):
        return {
            "id": row["id"],
            "user_desc": row["user_desc"],
            "intent": json.loads(row["intent_json"]),
            "scene_json": row["scene_json"],
            "rating": row["rating"],
            "tags": row["tags"],
            "created_at": row["created_at"],
            "used_count": row["used_count"],
            "last_used_at": row["last_used_at"],
            "success_count": row["success_count"],
            "fail_count": row["fail_count"],
        }
    
    def close(self):
        self._conn.close()
```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 创建数据库和表
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
bank = ExperienceBank('data/experience.db')
assert os.path.exists('data/experience.db'), '数据库文件未创建'
print('数据库创建验证通过')
bank.close()
"

# 验证2: 保存和查询经验
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
bank = ExperienceBank('data/experience.db')

exp_id = bank.save(
    '生成山谷草地场景',
    {'terrain_type': 'features', 'has_river': True},
    {'scene': {'target_level': '/Game/Test'}},
    rating=4, tags='山谷,草地'
)
assert exp_id > 0, f'保存失败: {exp_id}'

exp = bank.get_by_id(exp_id)
assert exp['user_desc'] == '生成山谷草地场景'
assert exp['rating'] == 4
assert exp['intent']['has_river'] == True
print('保存查询验证通过')
bank.close()
"

# 验证3: 更新评分和使用统计
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
bank = ExperienceBank('data/experience.db')
exp_id = bank.save('test', {}, {}, rating=3)

bank.update_rating(exp_id, 5)
bank.update_usage(exp_id, success=True)
bank.update_usage(exp_id, success=True)
bank.update_usage(exp_id, success=False)

exp = bank.get_by_id(exp_id)
assert exp['rating'] == 5
assert exp['used_count'] == 3
assert exp['success_count'] == 2
assert exp['fail_count'] == 1
assert exp['last_used_at'] is not None
print('更新统计验证通过')
bank.close()
"

# 验证4: 统计信息
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
bank = ExperienceBank('data/experience.db')
for i in range(5):
    bank.save(f'test{i}', {}, {}, rating=i+1)

stats = bank.get_stats()
assert stats['total'] == 5, f'总数应为5, 实际{stats[\"total\"]}'
assert stats['avg_rating'] == 3.0, f'平均评分应为3.0, 实际{stats[\"avg_rating\"]}'
assert stats['recent_7d'] == 5, f'近7天应为5, 实际{stats[\"recent_7d\"]}'
print('统计信息验证通过')
print(f'统计: {stats}')
bank.close()
"

# 验证5: 去重逻辑（相似经验更新而非新增）
python -c "
from ai.experience_bank import ExperienceBank
bank = ExperienceBank(':memory:')  # 内存数据库
# 保存第一条经验（含 keywords）
id1 = bank.save(
    '生成山谷草地场景',
    {'terrain_type': 'features', 'keywords': ['grass', 'tree', 'river']},
    {'scene': {'target_level': '/Game/Test1'}},
    rating=4
)
# 保存第二条相似经验（keywords 相同 → Jaccard=1.0 ≥0.6）
id2 = bank.save(
    '另一个山谷草地描述',
    {'terrain_type': 'features', 'keywords': ['grass', 'tree', 'river']},
    {'scene': {'target_level': '/Game/Test2'}},
    rating=5
)
assert id1 == id2, f'相似经验应去重更新(同id), id1={id1}, id2={id2}'
# 验证只有1条记录
all_exps = bank.get_all()
assert len(all_exps) == 1, f'去重后应只有1条, 实际{len(all_exps)}'
# 验证被更新了
assert all_exps[0]['rating'] == 5, f'rating应被更新为5, 实际{all_exps[0][\"rating\"]}'
assert all_exps[0]['user_desc'] == '另一个山谷草地描述'
print('去重逻辑验证通过')
bank.close()
"

# 验证6: 默认路径为 ~/.mapforge/
python -c "
from pathlib import Path
from ai.experience_bank import ExperienceBank
bank = ExperienceBank()  # 不传参数
assert str(Path.home() / '.mapforge' / 'experience.db') == bank._db_path
assert Path(bank._db_path).exists(), f'默认路径数据库未创建: {bank._db_path}'
print(f'默认路径验证通过: {bank._db_path}')
bank.close()
"
```

### 通过标准
- 数据库文件自动创建
- save 返回 >0 的 id
- get_by_id 返回正确的经验数据
- update_rating / update_usage 正确更新
- get_stats 返回正确的统计

---

## Phase 8: 四因子检索 + Few-shot 注入

### 目标
实现四因子评分检索器，将 top-K 经验作为 few-shot 注入 Stage 2。

### 前置条件
- Phase 7 通过

### 产出文件
- `ai/retriever.py` — ExperienceRetriever 类实现

### 实现要点

```python
import json
from datetime import datetime
from ai.experience_bank import ExperienceBank

class ExperienceRetriever:
    def __init__(self, bank):
        self._bank = bank
    
    def retrieve(self, query, top_k=3):
        all_exps = self._bank.get_all()
        if not all_exps:
            return []
        
        # 计算四因子得分
        scored = []
        for exp in all_exps:
            sim = self._semantic_similarity(query, exp["user_desc"])
            rec = self._recency(exp.get("last_used_at") or exp["created_at"])
            rel = self._reliability(exp["success_count"], exp["fail_count"])
            score = 0.65 * sim + 0.15 * rec + 0.20 * rel
            scored.append((score, sim, exp))
        
        # 按总分排序
        scored.sort(key=lambda x: -x[0])
        
        # MMR 多样性选择
        selected = []
        for score, sim, exp in scored:
            if len(selected) >= top_k:
                break
            
            if not selected:
                selected.append(exp)
                continue
            
            # 计算与已选经验的最大相似度
            max_sim = max(
                self._semantic_similarity(exp["user_desc"], s["user_desc"])
                for s in selected
            )
            mmr = score + 0.10 * (1 - max_sim)  # 多样性加成
            
            # 简化: 总分 >0.3 才选入
            if mmr > 0.15:
                selected.append(exp)
        
        # 更新使用统计
        for exp in selected:
            self._bank.update_usage(exp["id"], success=False)  # 先标记使用, 成功后更新
        
        return selected
    
    def _keyword_similarity(self, keywords1, keywords2):
        """词组级 Jaccard 相似度（基于 intent.keywords，零依赖）"""
        set1 = set(kw.lower() for kw in keywords1) if isinstance(keywords1, list) else set()
        set2 = set(kw.lower() for kw in keywords2) if isinstance(keywords2, list) else set()
        if not set1 or not set2:
            return 0.0
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union)
    
    def _recency(self, timestamp_str):
        """时效性: 距今天数衰减"""
        try:
            ts = datetime.fromisoformat(timestamp_str)
            days = (datetime.now() - ts).days
            return 1.0 / (1.0 + days)
        except Exception:
            return 0.0
    
    def _reliability(self, success_count, fail_count):
        """可靠性: 成功率"""
        total = success_count + fail_count
        if total == 0:
            return 0.5  # 中性值
        return success_count / (total + 1)
```

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 空库返回空列表
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever
bank = ExperienceBank('data/experience.db')
ret = ExperienceRetriever(bank)
results = ret.retrieve('测试')
assert results == [], f'空库应返回空列表, 实际{len(results)}'
print('空库验证通过')
bank.close()
"

# 验证2: 语义相似度计算
python -c "
from ai.retriever import ExperienceRetriever
from ai.experience_bank import ExperienceBank
bank = ExperienceBank(':memory:')  # 内存数据库
ret = ExperienceRetriever(bank)

# 完全相同
sim1 = ret._semantic_similarity('山谷草地河流', '山谷草地河流')
assert sim1 == 1.0, f'完全相同应=1.0, 实际{sim1}'

# 部分重叠
sim2 = ret._semantic_similarity('山谷草地河流', '山谷河流松树')
assert 0 < sim2 < 1.0, f'部分重叠应在0~1, 实际{sim2}'

# 完全不同
sim3 = ret._semantic_similarity('山谷', '城市')
assert sim3 == 0.0, f'完全不同应=0, 实际{sim3}'
print(f'语义相似度验证通过: sim1={sim1}, sim2={sim2:.2f}, sim3={sim3}')
bank.close()
"

# 验证3: 检索返回排序结果
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever

bank = ExperienceBank('data/experience.db')
bank.save('山谷草地河流场景', {}, {}, rating=5)
bank.save('城市街道场景', {}, {}, rating=3)
bank.save('山谷松树河流', {}, {}, rating=4)

ret = ExperienceRetriever(bank)
results = ret.retrieve('山谷草地河流', top_k=2)
assert len(results) <= 2, f'应最多返回2条, 实际{len(results)}'
assert len(results) > 0, '应返回至少1条'
# 最相似的应排第一
assert '山谷' in results[0]['user_desc'], f'最相似应含山谷, 实际: {results[0][\"user_desc\"]}'
print('检索排序验证通过')
for r in results:
    print(f'  {r[\"user_desc\"]}')
bank.close()
"

# 验证4: 四因子权重影响排序
python -c "
import os
if os.path.exists('data/experience.db'):
    os.remove('data/experience.db')
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever

bank = ExperienceBank('data/experience.db')
# 两条语义相似的经验, 但可靠性不同
id1 = bank.save('山谷草地', {}, {}, rating=5)
id2 = bank.save('草地山谷', {}, {}, rating=5)
bank.update_usage(id1, success=True)
bank.update_usage(id1, success=True)
bank.update_usage(id2, success=False)

ret = ExperienceRetriever(bank)
results = ret.retrieve('山谷草地', top_k=2)
# id1 可靠性更高(2成功0失败 vs 0成功1失败), 应排前
print('可靠性排序验证通过')
bank.close()
"
```

### 通过标准
- 空库返回空列表
- 词组级 Jaccard 相似度计算正确（1.0 / 0~1 / 0.0）
- 检索返回 top-K 且按关键词相关性排序
- 可靠性因子影响排序
- retrieve 不污染使用统计（used_count / fail_count 不变）

---

## Phase 9: GUI 聊天面板

### 目标
在 mapforge_app.py 中添加 AI 聊天面板，实现完整的用户交互流程。

### 前置条件
- Phase 4-8 全部通过（AI 管线完整可用）

### 产出文件
- `mapforge_app.py` — 扩展（添加 ChatPanel + AIWorker）

### 实现要点

1. **新增 AIWorker 线程**（内联完整管线，每阶段发信号）：
   ```python
   class AIWorker(QThread):
       intent_parsed = pyqtSignal(dict)
       json_generated = pyqtSignal(dict)
       validation_done = pyqtSignal(dict, list)
       repair_started = pyqtSignal(int)
       finished_signal = pyqtSignal(dict, bool, str)  # scene, success, message
       error_occurred = pyqtSignal(str)
       log_line = pyqtSignal(str)
       
       def __init__(self, client, config, user_desc, feedback=None):
           ...
       
       def run(self):
           """内联完整三阶段管线，每阶段发信号到 UI
           run_pipeline（ai/__init__.py）保留供非 GUI 测试使用"""
           try:
               client = self._create_client()
               config = self._config
               user_desc = self._user_desc
               
               # Stage 1: 意图解析
               self.log_line.emit('Stage 1: 意图解析...')
               intent_parser = IntentParser(client, model=config.get("llm_intent_model"))
               intent = intent_parser.parse(user_desc)
               self.intent_parsed.emit(intent)
               self.log_line.emit(f'意图解析完成: terrain={intent.get("terrain_type")}')
               
               # Stage 2: 知识注入 + JSON 生成
               self.log_line.emit('Stage 2: 知识注入 + JSON 生成...')
               knowledge = KnowledgePack(get_resource_path("data/knowledge"))
               asset_index = AssetIndex(get_resource_path("asset_catalog.json"))
               bank = ExperienceBank()  # 默认 ~/.mapforge/
               retriever = ExperienceRetriever(bank)
               
               few_shots = retriever.retrieve(intent, top_k=3)  # 传 intent 而非 user_desc
               self.log_line.emit(f'检索到 {len(few_shots)} 条经验')
               
               generator = SceneGenerator(client, knowledge, asset_index, model=config.get("llm_strong_model"))
               scene = generator.generate(user_desc, intent, few_shots)
               self.json_generated.emit(scene)
               self.log_line.emit('JSON 生成完成')
               
               # Stage 3: 验证-修复循环（注入知识包 system_prompt）
               self.log_line.emit('Stage 3: 验证-修复循环...')
               loop = ValidationRepairLoop(client, knowledge=knowledge, model=config.get("llm_strong_model"))
               final_scene, history = loop.validate_and_repair(scene, user_desc, intent=intent)
               self.validation_done.emit(final_scene, history)
               
               success = not history[-1]["errors"] if history else False
               
               # 管线末尾：更新经验使用统计 + 保存新经验
               # Fix 2: 成功才标记 success，不污染 fail_count
               if few_shots:
                   for exp in few_shots:
                       bank.update_usage(exp["id"], success=success)
               if success:
                   bank.save(user_desc, intent, final_scene, rating=3)
                   self.log_line.emit('经验已保存到记忆库')
               
               self.finished_signal.emit(final_scene, success, "生成完成")
           except Exception as e:
               self.error_occurred.emit(str(e))
   ```

2. **新增 ChatPanel widget**：
   ```python
   class ChatPanel(QWidget):
       """AI 对话面板: 聊天历史 + 输入框 + JSON预览 + 审核按钮"""
       
       def __init__(self, config):
           # 左侧: 聊天历史 + 输入框
           # 右侧: JSON 预览 + 审核按钮 + 评分
           # 底部: 进度条 + 日志
   ```

3. **MainWindow 扩展**：
   - 添加 Tab 切换：原有"文件上传" vs 新增"AI 生成"
   - AI Tab 内放 ChatPanel
   - 复用现有 BuildWorker 做 JSON→umap 转换

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 程序能启动（无崩溃）
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mapforge_app import MainWindow
win = MainWindow()
print('GUI 启动验证通过')
"

# 验证2: AI Tab 存在
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mapforge_app import MainWindow
win = MainWindow()
# 检查是否有 Tab 切换或 ChatPanel
tabs = win.findChildren(type(win).__bases__[0])  # 简化检查
print(f'窗口子组件数: {len(win.children())}')
# 验证 AI 相关组件存在
has_chat = any('chat' in str(type(c)).lower() for c in win.children())
print(f'AI 聊天组件: {\"存在\" if has_chat else \"需检查\"}')
print('AI Tab 验证通过')
"

# 验证3: Mock 模式完整流程
python -c "
import sys, json
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mapforge_app import MainWindow
win = MainWindow()
win._config['llm_profile'] = 'mock'
# 模拟 AI 生成流程
mock_scene = {'scene': {'target_level': '/Game/Test'}, 'landscape': {'material': '/Game/M', 'section_size_quads': 63, 'num_subsections': 2, 'component_count_x': 8, 'component_count_y': 8, 'layers': [{'info': '/Game/L', 'weight': 1.0}]}}
win._on_ai_finished(mock_scene, True, '生成成功')
print('Mock 流程验证通过')
"
```

### 通过标准
- 程序能启动不崩溃
- AI 聊天面板可见
- Mock 模式下能走完意图→生成→验证流程
- 生成的 JSON 显示在预览区

---

## Phase 10: 设置页面扩展

### 目标
添加 LLM 配置页面（API key / model / base_url / profile 切换）。

### 前置条件
- Phase 9 通过

### 产出文件
- `mapforge_app.py` — 扩展（添加 SettingsDialog）

### 实现要点

1. **SettingsDialog 对话框**（参考 settings_page.py 模式）：
   ```python
   class SettingsDialog(QDialog):
       def __init__(self, config, parent=None):
           # LLM profile 切换: mock / openai / ollama
           # API key (密码模式, 支持 ${VAR})
           # Model 名称
           # Base URL (阿里云/DeepSeek/OpenAI)
           # Ollama host
           # 强模型 / 意图模型 (可选, 空则同默认)
   ```

2. **菜单栏添加"设置"入口**：
   ```python
   def _create_menu(self):
       menu = self.menuBar()
       settings_action = QAction("设置", self)
       settings_action.triggered.connect(self._open_settings)
       menu.addAction(settings_action)
   ```

3. **配置保存到 ~/.mapforge_config.json**：
   复用现有 `save_config()` 函数，扩展字段。

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: 设置对话框能打开
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mapforge_app import SettingsDialog
cfg = {'llm_profile': 'openai', 'llm_api_key': '', 'llm_model': 'deepseek-chat'}
dlg = SettingsDialog(cfg)
print('设置对话框创建验证通过')
"

# 鉩证2: profile 切换字段启用/禁用
python -c "
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mapforge_app import SettingsDialog
cfg = {'llm_profile': 'mock'}
dlg = SettingsDialog(cfg)
# mock 模式下 API key 应禁用
assert not dlg._api_key.isEnabled(), 'mock模式下API key应禁用'
dlg._llm_profile.setCurrentText('openai')
assert dlg._api_key.isEnabled(), 'openai模式下API key应启用'
print('Profile切换验证通过')
"

# 验证3: 保存配置
python -c "
import sys, json, os
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
from mapforge_app import SettingsDialog, CONFIG_PATH

# 备份原配置
backup = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'r') as f:
        backup = json.load(f)

cfg = {'llm_profile': 'openai', 'llm_api_key': 'sk-test', 'llm_model': 'gpt-4o', 'llm_base_url': 'https://api.openai.com/v1'}
dlg = SettingsDialog(cfg)
dlg._on_save()

# 验证保存
with open(CONFIG_PATH, 'r') as f:
    saved = json.load(f)
assert saved.get('llm_api_key') == 'sk-test'
assert saved.get('llm_model') == 'gpt-4o'
print('配置保存验证通过')

# 恢复
with open(CONFIG_PATH, 'w') as f:
    json.dump(backup, f)
"
```

### 通过标准
- 设置对话框能打开
- profile 切换正确启用/禁用字段
- 配置能保存到 ~/.mapforge_config.json 并恢复

---

## Phase 11: 端到端集成

### 目标
串联所有模块，完成从自然语言到 umap 的完整流程。

### 前置条件
- Phase 0-10 全部通过

### 产出文件
- `mapforge_app.py` — 集成所有信号连接
- `ai/__init__.py` — 添加管线编排函数

### 实现要点

1. **管线编排**（`ai/__init__.py` 或 generator 内部）：
   ```python
   def run_pipeline(client, config, user_desc, feedback=None):
       """完整三阶段管线（供非 GUI 测试使用；GUI 用 AIWorker.run 内联版本发信号）"""
       # Stage 1: 意图解析
       intent_parser = IntentParser(client, model=config.get("llm_intent_model"))
       intent = intent_parser.parse(user_desc)
       
       # Stage 2: 知识注入 + 生成
       knowledge = KnowledgePack(get_resource_path("data/knowledge"))
       asset_index = AssetIndex(get_resource_path("asset_catalog.json"))
       bank = ExperienceBank()  # 默认 ~/.mapforge/experience.db
       retriever = ExperienceRetriever(bank)
       
       few_shots = retriever.retrieve(intent, top_k=3)  # 传 intent 而非 user_desc
       
       generator = SceneGenerator(client, knowledge, asset_index, model=config.get("llm_strong_model"))
       scene = generator.generate(user_desc, intent, few_shots)
       
       # Stage 3: 验证-修复（注入知识包 system_prompt）
       loop = ValidationRepairLoop(client, knowledge=knowledge, model=config.get("llm_strong_model"))
       final_scene, history = loop.validate_and_repair(scene, user_desc, intent=intent)
       
       success = not history[-1]["errors"] if history else False
       
       # 管线末尾：更新经验使用统计（Fix 2：成功才标记 success，不污染 fail_count）
       if few_shots:
           for exp in few_shots:
               bank.update_usage(exp["id"], success=success)
       
       return final_scene, intent, history, success
   ```

2. **AIWorker 内联管线**（完整实现见 Phase 9）：
   ```python
   # AIWorker.run() 完整实现见 Phase 9（内联三阶段管线 + 每阶段发信号）
   # Phase 9 的 AIWorker.run() 不调用 run_pipeline，而是内联完整逻辑：
   #   - Stage 1: IntentParser → emit intent_parsed
   #   - Stage 2: KnowledgePack + SceneGenerator → emit json_generated
   #   - Stage 3: ValidationRepairLoop → emit validation_done
   #   - 末尾: update_usage(few_shots) + bank.save（成功时）
   #
   # run_pipeline 保留在 ai/__init__.py 供非 GUI 测试使用（不发出 Qt 信号）
   # GUI 场景必须用 AIWorker.run() 内联版本，否则无法实时显示进度
   ```

3. **UI 信号连接**：
   - AIWorker.finished_signal → ChatPanel._on_ai_finished
   - ChatPanel._approve → save to bank → BuildWorker (JSON→umap)
   - ChatPanel._reject → 反馈输入 → 重新 AIWorker

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: Mock 端到端管线
python -c "
import json, os
from ai.client import MockLLMClient
from ai.knowledge import KnowledgePack
from ai.asset_index import AssetIndex
from ai.intent_parser import IntentParser
from ai.generator import SceneGenerator
from ai.validator import ValidationRepairLoop
from validate_scene_json import validate_scene

# 准备 Mock 响应
intent_resp = json.dumps({
    'terrain_type': 'features', 'has_river': True, 'has_grass': True,
    'keywords': ['grass', 'tree'], 'scene_scale': '1km', 'complexity': 'medium'
})
scene_resp = json.dumps({
    'scene': {'name': 'Test', 'target_level': '/Game/Maps/Test'},
    'landscape': {
        'material': '/Game/M', 'section_size_quads': 63, 'num_subsections': 2,
        'component_count_x': 8, 'component_count_y': 8,
        'layers': [{'info': '/Game/L', 'weight': 1.0}]
    }
})

mock = MockLLMClient([intent_resp, scene_resp])
kp = KnowledgePack('data/knowledge')
ai = AssetIndex('asset_catalog.json')

# Stage 1
parser = IntentParser(mock)
intent = parser.parse('山谷草地')
assert intent['terrain_type'] == 'features'

# Stage 2
gen = SceneGenerator(mock, kp, ai)
scene = gen.generate('山谷草地', intent)
assert 'scene' in scene

# Stage 3
loop = ValidationRepairLoop(mock)
final, history = loop.validate_and_repair(scene, '山谷草地')
errors, _ = validate_scene(final)
print(f'端到端验证: {len(history)}轮, 最终{len(errors)}错误')
assert len(errors) == 0, f'应有0错误, 实际{len(errors)}'
print('Mock 端到端管线验证通过')
"

# 验证2: 实际 API 端到端（需要 key）
python -c "
import os, json
key = os.environ.get('TEST_API_KEY', '')
if not key:
    print('跳过: 未设置 TEST_API_KEY')
else:
    from ai.client import OpenAILLMClient
    from ai.knowledge import KnowledgePack
    from ai.asset_index import AssetIndex
    from ai.intent_parser import IntentParser
    from ai.generator import SceneGenerator
    from ai.validator import ValidationRepairLoop
    from ai.experience_bank import ExperienceBank
    from ai.retriever import ExperienceRetriever
    from validate_scene_json import validate_scene

    c = OpenAILLMClient(api_key=key, model='deepseek-chat', base_url='https://api.deepseek.com/v1')
    kp = KnowledgePack('data/knowledge')
    ai = AssetIndex('asset_catalog.json')
    bank = ExperienceBank('data/experience.db')
    ret = ExperienceRetriever(bank)

    desc = '生成一个1km的山谷草地场景，有河流和几棵松树'
    
    # Stage 1
    parser = IntentParser(c)
    intent = parser.parse(desc)
    print(f'意图: {intent}')
    
    # Stage 2 (含 few-shot)
    few_shots = ret.retrieve(desc, top_k=3)
    print(f'检索到 {len(few_shots)} 条经验')
    gen = SceneGenerator(c, kp, ai)
    scene = gen.generate(desc, intent, few_shots)
    
    # Stage 3
    loop = ValidationRepairLoop(c)
    final, history = loop.validate_and_repair(scene, desc)
    
    errors, _ = validate_scene(final)
    print(f'端到端: {len(history)}轮, 最终{len(errors)}错误')
    
    # 保存成功经验
    if not errors:
        bank.save(desc, intent, final, rating=4, tags='山谷,草地,河流')
        print('经验已保存')
    
    print('实际 API 端到端验证', '通过' if not errors else '需人工审核')
    bank.close()
"

# 验证3: 经验库积累后检索
python -c "
import os
from ai.experience_bank import ExperienceBank
from ai.retriever import ExperienceRetriever

bank = ExperienceBank('data/experience.db')
stats = bank.get_stats()
print(f'经验库统计: {stats}')

ret = ExperienceRetriever(bank)
results = ret.retrieve('山谷草地', top_k=3)
print(f'检索到 {len(results)} 条相关经验')
for r in results:
    print(f'  [{r[\"rating\"]}星] {r[\"user_desc\"][:30]}...')
bank.close()
"
```

### 通过标准
- Mock 端到端管线 0 错误通过
- 实际 API（如有 key）生成可通过或仅少量错误
- 经验能保存到库
- 检索能返回相关经验

---

## Phase 12: 打包发布

### 目标
用 PyInstaller 打包为独立 exe，包含 AI 模块和知识数据。

### 前置条件
- Phase 11 通过

### 产出文件
- `MapForge.spec` — 扩展（添加 ai/ 和 data/ 目录）
- `dist/MapForge.exe` — 最终可执行文件

### 实现要点

1. **更新 MapForge.spec**：
   ```python
   # 在 datas 列表中添加
   datas = [
       ('build_scene.py', '.'),
       ('build_umap.py', '.'),
       ('build_umap.bat', '.'),
       ('validate_scene_json.py', '.'),
       ('validate_scene_assets.py', '.'),
       ('asset_catalog.json', '.'),
       ('data/knowledge', 'data/knowledge'),        # 新增: 知识文件
       # data/experience.db 不打包, 运行时自动创建
   ]
   
   # 在 hiddenimports 中添加
   hiddenimports = [
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
   ]
   ```

2. **打包命令**：
   ```bash
   pyinstaller MapForge.spec
   ```

3. **运行时路径适配**：
   确保 `get_resource_path()` 函数能正确定位打包后的数据文件（已有此函数，验证 ai/ 模块也能找到）。

### 验证方法
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest

# 验证1: spec 文件包含 ai/ 和 data/
python -c "
import ast
with open('MapForge.spec', 'r') as f:
    content = f.read()
assert 'data/knowledge' in content, 'spec 缺少 data/knowledge'
assert 'ai.client' in content or 'ai' in content, 'spec 缺少 ai 模块'
print('spec 文件验证通过')
"

# 验证2: 执行打包
pyinstaller MapForge.spec --noconfirm
# 检查 exe 存在
python -c "
import os
assert os.path.exists('dist/MapForge.exe'), 'exe 未生成'
size = os.path.getsize('dist/MapForge.exe')
print(f'打包完成: {size / 1024 / 1024:.1f} MB')
"

# 验证3: 打包后的 exe 能启动
# (手动验证) 双击 dist/MapForge.exe, 确认 GUI 正常显示
# (命令行验证) 
dist\MapForge.exe --test-mode  # 如果实现了测试模式
# 或直接运行
dist\MapForge.exe &
timeout 5
tasklist | findstr MapForge
# 应看到 MapForge.exe 进程

# 验证4: 打包后的 exe 能找到知识文件
python -c "
import subprocess, sys
result = subprocess.run(
    [sys.executable, '-c', '''
import sys
sys.path.insert(0, \"dist/MapForge\")
# 模拟打包环境检查
import os
frozen = getattr(sys, \"frozen\", False)
print(f\"Frozen: {frozen}\")
if frozen:
    base = sys._MEIPASS
    assert os.path.exists(os.path.join(base, \"data/knowledge/core.md\")), \"知识文件未打包\"
    print(\"知识文件打包验证通过\")
else:
    print(\"开发模式: 跳过打包验证\")
'''],
    capture_output=True, text=True
)
print(result.stdout)
"
```

### 通过标准
- spec 文件包含 ai/ 和 data/knowledge
- PyInstaller 打包成功生成 exe
- exe 能启动显示 GUI
- 打包后 exe 内包含知识文件

---

## 附录: 完整依赖检查

### Python 依赖
```
PyQt6          # GUI 框架 (已安装)
openai         # LLM SDK (延迟导入, 可选)
PyYAML         # YAML 解析 (已安装, 可选)
```

### 系统依赖
```
UE 5.8         # 场景构建引擎
Python 3.10+   # 运行环境
```

### 验证全部依赖
```bash
cd c:\Users\25868\Desktop\UE5\MapForgeTest
python -c "
deps = {
    'PyQt6': 'PyQt6.QtWidgets',
    'openai': 'openai',
    'yaml': 'yaml',
    'sqlite3': 'sqlite3',
}
for name, mod in deps.items():
    try:
        __import__(mod)
        print(f'  [OK] {name}')
    except ImportError:
        print(f'  [MISS] {name} (可选)')
print('依赖检查完成')
"
```

---

## 附录: 快速回归测试脚本

将以下脚本保存为 `test_ai_pipeline.py`，每个 Phase 验证后运行一次回归：

```bash
# 用法: python test_ai_pipeline.py
# 功能: 运行所有 Phase 的核心验证, 3秒内完成
```

> 此脚本在 Phase 11 完成后创建，用于后续修改的快速回归验证。