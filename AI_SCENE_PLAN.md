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

### 3.2 知识包构建器 (`ai/knowledge.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 从 UE5_JSON 技能文档中提取知识，分层组装 system_prompt |
| 输入 | intent_json (决定加载哪些模式文档) |
| 输出 | system_prompt 字符串 |
| 数据源 | `data/knowledge/` 目录（从技能目录复制） |

### 3.3 资产关键词索引 (`ai/asset_index.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 从 asset_catalog.json 中按关键词搜索资产路径 |
| 输入 | keywords: list[str] (来自 intent 解析) |
| 输出 | asset_paths: list[str] (匹配的 UE 资产路径) |
| 数据源 | `asset_catalog.json` (7691条) |

### 3.4 意图解析器 (`ai/intent_parser.py`)

| 项目 | 说明 |
|------|------|
| 职责 | Stage 1：从自然语言提取结构化意图 |
| 输入 | user_description: str |
| 输出 | intent: dict (固定 schema) |
| 模型 | 轻量模型 (gpt-4o-mini / deepseek-chat) |

### 3.5 JSON 生成器 (`ai/generator.py`)

| 项目 | 说明 |
|------|------|
| 职责 | Stage 2：组装知识 + 调用 LLM 生成场景 JSON |
| 输入 | user_description: str, intent: dict, few_shots: list[dict] |
| 输出 | scene_json: dict |
| 模型 | 强模型 (gpt-4o / deepseek-v3) |

### 3.6 验证-修复循环 (`ai/validator.py`)

| 项目 | 说明 |
|------|------|
| 职责 | Stage 3：调用现有校验脚本 + LLM 修复 |
| 输入 | scene_json: dict |
| 输出 | (validated_scene: dict, errors_history: list) |
| 最大轮数 | 3 |

### 3.7 经验记忆库 (`ai/experience_bank.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 存储/检索历史成功场景 |
| 存储 | SQLite (`data/experience.db`) |
| 接口 | save / search / update_rating / get_stats |

### 3.8 四因子检索器 (`ai/retriever.py`)

| 项目 | 说明 |
|------|------|
| 职责 | 四因子评分 + 检索 top-K 经验 |
| 评分公式 | `score = 0.65×sim + 0.15×recency + 0.20×reliability + 0.10×diversity` |

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
