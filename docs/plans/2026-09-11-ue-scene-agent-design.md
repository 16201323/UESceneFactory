# UE 场景 Agent 架构设计文档

> **创建日期**: 2026-09-11
> **基于**: `docs/AI_SCENE_PLAN.md` 三阶段管线规格 + v0.1/v0.2 已实现代码
> **目标**: 将 AI 场景生成从「函数式三阶段管线」升级为「Agent 智能体流水线」，每个阶段由独立 Agent 承担，通过 PydanticAI 框架实现工具调用、结构化输出、依赖注入
> **执行方式**: TDD（写测试→验证失败→实现→验证通过），每个版本含完整单元测试

---

## 一、架构概览

### 1.1 三阶段 Agent 流水线

```
用户自然语言
    ↓
┌──────────────────────┐
│  v0.2 ScenePlanner   │  Stage 1: 意图解析 + 知识检索
│  (AgentBase 子类)     │  → SceneBlueprint 蓝图
└──────────┬───────────┘
           │ SceneBlueprint (Pydantic 模型)
           ↓
┌──────────────────────┐
│  v0.3 JSONBuilder    │  Stage 2: 知识注入 + JSON 生成
│  (AgentBase 子类)     │  → SceneJSON 完整场景
└──────────┬───────────┘
           │ SceneJSON (Pydantic 模型 / dict)
           ↓
┌──────────────────────┐
│  v0.4 QualityGuard   │  Stage 3: 验证 + 修复循环
│  (AgentBase 子类)     │  → ValidatedScene 校验后场景
└──────────┬───────────┘
           ↓
       最终场景 JSON → build_scene.py → UMAP
```

### 1.2 与旧架构的映射关系

| 旧架构（函数式） | 新架构（Agent 式） | 版本 |
|---|---|---|
| `IntentParser.parse()` | `ScenePlannerAgent.run()` | v0.2 ✅ |
| `KnowledgePack.build_system_prompt()` | ScenePlanner 工具调用注入 | v0.2 ✅ |
| `AssetIndex.search()` | `search_assets` 工具 | v0.2 ✅ |
| `ExperienceRetriever.retrieve()` | `search_experience` 工具 | v0.2 ✅ |
| `SceneGenerator.generate()` | `JSONBuilderAgent.run()` | v0.3 ✅ |
| `ValidationRepairLoop.validate_and_repair()` | `QualityGuardAgent.run()` | v0.4 ✅ |

> **关键区别**: 旧架构中知识注入是硬编码的（`build_system_prompt` 拼接），Agent 架构中知识注入是 LLM 自主调用的（通过 `@agent.tool` 注册的工具），LLM 按需检索，减少无关 token 注入。

### 1.3 技术栈

| 组件 | 技术 | 说明 |
|---|---|---|
| Agent 框架 | PydanticAI | `Agent`, `RunContext`, `TestModel`, `OpenAIChatModel` |
| 模型接入 | OpenAIProvider | 兼容 DeepSeek / OpenAI / Ollama(OpenAI 兼容) |
| 结构化输出 | Pydantic BaseModel | `SceneBlueprint`, `SceneJSON` 等 |
| 依赖注入 | `AgentDeps` dataclass | knowledge/asset_index/experience_bank/... |
| 测试 | pytest + TestModel | TestModel 替代真实 LLM 调用 |
| 存储 | SQLite (stdlib) | PatternLibrary, ExperienceBank |

---

## 二、Agent 基础设施（v0.1 已实现）

### 2.1 AgentDeps — 依赖容器

所有后端服务通过 `AgentDeps` 注入到 Agent，工具函数通过 `ctx.deps` 访问：

```python
@dataclass
class AgentDeps:
    knowledge: Any = None           # KnowledgePack — 知识包
    asset_index: Any = None        # AssetIndex — 资产索引
    experience_bank: Any = None    # ExperienceBank — 经验银行
    retriever: Any = None          # ExperienceRetriever — 经验检索器
    pattern_library: Any = None    # PatternLibrary — 模式库
    validator: Any = None          # validate_scene — 校验函数
```

### 2.2 AgentBase — 基类

```python
class AgentBase:
    def __init__(self, model_name, api_key, base_url=None, deps=None, retries=3):
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._deps = deps or AgentDeps()
        self._retries = retries
        self._agent = None  # 缓存

    def _create_model(self) -> OpenAIChatModel:
        """创建 LLM 模型实例，子类可覆盖为 TestModel"""
        provider = OpenAIProvider(api_key=self._api_key, base_url=self._base_url)
        return OpenAIChatModel(model_name=self._model_name, provider=provider)

    def build(self) -> Agent:
        """构建 PydanticAI Agent，缓存结果"""
        if self._agent is None:
            self._agent = Agent(
                self._create_model(),
                deps_type=AgentDeps,
                retries=self._retries,
                system_prompt=self._system_prompt(),
                output_type=self._output_type(),
            )
            self._register_tools(self._agent)
        return self._agent

    async def run(self, user_prompt: str) -> Any:
        """运行 Agent，自动传递 deps"""
        agent = self.build()
        return await agent.run(user_prompt, deps=self._deps)

    # —— 子类必须实现 ——
    def _output_type(self) -> Any:
        """返回输出类型（Pydantic 模型类）"""
        return None

    def _system_prompt(self) -> str:
        """返回系统提示词"""
        raise NotImplementedError

    def _register_tools(self, agent: Agent) -> None:
        """注册工具函数"""
        raise NotImplementedError
```

### 2.3 工具函数双层模式

每个工具由两部分组成，实现「可单元测试」+「Agent 可调用」：

```
ai/tools/xxx_tools.py          # _core 函数，接收后端对象，可独立测试
ai/agents/xxx_agent.py         # @agent.tool 包装器，从 ctx.deps 取后端对象
```

**示例**（`asset_tools.py` + ScenePlannerAgent 内）：

```python
# ai/tools/asset_tools.py — 核心函数，可单元测试
def search_assets_core(asset_index, keywords, max_results=20) -> list[AssetEntry]:
    entries = asset_index.search(keywords, max_results)
    return [AssetEntry(path=p, ...) for p in entries]

# ai/agents/scene_planner.py — Agent 工具包装器
@agent.tool
async def search_assets(ctx: RunContext[AgentDeps], keywords: list[str]) -> list[dict]:
    entries = search_assets_core(ctx.deps.asset_index, keywords)
    return [e.model_dump() for e in entries]
```

### 2.4 测试模式

使用 `TestModel` 替代真实 LLM，子类化覆盖 `_create_model`：

```python
class TestScenePlanner(ScenePlannerAgent):
    def _create_model(self):
        return TestModel()

agent = TestScenePlanner("test-model", "fake-key", deps=AgentDeps())
result = asyncio.run(agent.run("generate a flat terrain scene"))
assert isinstance(result.output, SceneBlueprint)
```

---

## 三、版本路线图

### 3.1 总览

| 版本 | Agent | Stage | 状态 | 交付物 |
|---|---|---|---|---|
| v0.1 | AgentBase 基础设施 | — | ✅ 已完成 | Pattern模型 + PatternLibrary + AgentBase + pattern_tools |
| v0.2 | ScenePlannerAgent | Stage 1 | ✅ 已完成 | SceneBlueprint + 5个知识工具 + ScenePlannerAgent |
| v0.3 | JSONBuilderAgent | Stage 2 | ✅ 已完成 | SceneJSON模型 + 知识注入工具 + JSONBuilderAgent |
| v0.4 | QualityGuardAgent | Stage 3 | ✅ 已完成 | ValidationReport + 校验工具 + QualityGuardAgent |

### 3.2 v0.1 交付物（已完成）

**文件结构**:
```
ai/
├── models/
│   ├── pattern.py          # Pattern 模型 (name/content/category/tags/use_count/rating)
│   └── __init__.py
├── pattern_library.py     # PatternLibrary — SQLite 存储 + 关键词搜索
├── agents/
│   ├── base.py            # AgentBase + AgentDeps
│   └── __init__.py
├── tools/
│   ├── pattern_tools.py   # search_patterns_core / count_patterns_core
│   └── __init__.py
tests/
├── test_v01_agent_base.py        # 9 个测试
├── test_v01_pattern.py           # Pattern 模型测试
├── test_v01_pattern_library.py   # PatternLibrary 测试
└── test_v01_pattern_tools.py     # 工具核心函数测试
```

**关键设计决策**:
- `AgentDeps` 使用 dataclass，所有字段默认 None，子类按需注入
- `AgentBase.build()` 缓存 Agent 实例，避免重复创建
- `AgentBase.run()` 自动传递 `self._deps`，调用者无需手动传
- PatternLibrary 使用 `INSERT OR REPLACE`，支持上下文管理器

### 3.3 v0.2 交付物（已完成）

**文件结构**:
```
ai/
├── models/
│   └── blueprint.py       # SceneBlueprint + AssetEntry + ExperienceRef
├── tools/
│   ├── asset_tools.py        # search_assets_core
│   ├── experience_tools.py   # search_experience_core
│   ├── knowledge_tools.py    # get_pattern_docs_core / get_template_core / get_design_principles_core
│   └── pattern_tools.py      # (v0.1 已有)
├── agents/
│   └── scene_planner.py  # ScenePlannerAgent
tests/
├── test_v02_scene_planner.py   # 6 个测试
├── test_v02_blueprint.py       # 5 个测试
├── test_v02_asset_tools.py
├── test_v02_experience_tools.py
└── test_v02_knowledge_tools.py
```

**SceneBlueprint 模型** — Stage 1 输出 / Stage 2 输入:

```python
class SceneBlueprint(BaseModel):
    # —— 意图字段（从用户描述解析）——
    terrain_type: str               # flat|ridge|hill|noise|hill_ridge|features|...
    has_water: bool
    has_river: bool
    has_grass: bool
    has_wheat: bool
    placements: list[str]           # ["trees", "fence", "heliport", ...]
    keywords: list[str]             # 资产搜索关键词
    scene_type: str                 # 场景类型

    # —— 规划字段（工具调用结果填充）——
    assets: list[AssetEntry]        # 检索到的资产路径
    design_rules: list[str]         # 设计原则
    experience_refs: list[ExperienceRef]  # 经验 few-shot 引用
    template_ref: str | None       # 模板标杆引用
    lighting_style: str            # 光照风格
    weather_style: str             # 天气风格
```

**ScenePlannerAgent 注册的 5 个工具**:

| 工具 | 核心函数 | 后端 | 用途 |
|---|---|---|---|
| `search_assets` | `search_assets_core` | AssetIndex | 关键词搜索资产路径 |
| `search_experience` | `search_experience_core` | ExperienceRetriever | 四因子检索经验 |
| `get_design_principles` | `get_design_principles_core` | KnowledgePack | 获取设计原则 |
| `get_template` | `get_template_core` | KnowledgePack | 获取模板标杆 |
| `get_pattern_docs` | `get_pattern_docs_core` | KnowledgePack | 获取模式文档 |

**ScenePlannerAgent 系统提示词**:

```
你是一个 UE 场景规划专家。分析用户描述，调用工具获取知识，输出场景蓝图。

关键步骤：
1. 解析用户描述的意图（地形类型、水系、植被、放置物）
2. 调用 search_assets 搜索相关资产
3. 调用 search_experience 检索相似经验
4. 调用 get_design_principles 获取设计原则
5. 调用 get_template 获取模板标杆
...
```

---

## 四、v0.3 设计 — JSONBuilderAgent（Stage 2）

### 4.1 目标

将 `SceneBlueprint`（蓝图）转化为完整的场景 JSON。LLM 接收蓝图作为上下文，调用工具注入知识文档，生成符合 `build_scene.py` 规范的完整 JSON。

### 4.2 输出模型 — SceneJSON

```python
class SceneJSON(BaseModel):
    """完整场景 JSON 的 Pydantic 模型，映射 build_scene.py 的顶层结构"""
    scene: SceneInfo                    # name, target_level, description
    landscape: LandscapeConfig          # material, sections, layers, height_pattern, grass, wheat
    ground: GroundConfig | None        # asset, material_override
    placements: list[PlacementConfig]   # type, asset, location, grid, instances
    lighting: LightingConfig            # directional_light, sky_light, sky_atmosphere, height_fog
    weather: WeatherConfig | None       # volumetric_clouds
```

> **设计决策**: SceneJSON 作为 Pydantic 模型，利用 PydanticAI 的 `output_type` 自动结构化输出。LLM 生成 JSON 后由 PydanticAI 框架自动验证并解析为模型实例，减少手动 `extract_json` 调用。

### 4.3 文件结构（v0.3 新增）

```
ai/
├── models/
│   └── scene_json.py       # 新增: SceneJSON + 子模型 (SceneInfo, LandscapeConfig, ...)
├── tools/
│   └── json_tools.py       # 新增: 知识注入工具 (inject_knowledge_core, inject_template_core)
├── agents/
│   └── json_builder.py     # 新增: JSONBuilderAgent
tests/
├── test_v03_scene_json.py     # 新增: SceneJSON 模型测试
├── test_v03_json_tools.py     # 新增: 知识注入工具测试
└── test_v03_json_builder.py   # 新增: JSONBuilderAgent 测试
```

### 4.4 JSONBuilderAgent 设计

```python
class JSONBuilderAgent(AgentBase):
    def _output_type(self) -> Any:
        return SceneJSON

    def _system_prompt(self) -> str:
        return (
            "你是一个 UE5 场景 JSON 生成专家。"
            "根据场景蓝图（SceneBlueprint），调用工具获取知识文档和模板标杆，"
            "生成符合 build_scene.py 规范的完整场景 JSON。\n\n"
            "关键规则:\n"
            "1. 顶层结构: scene / landscape / ground / placements / lighting / weather\n"
            "2. 资产路径格式: /Game/类别/Name（不含 .uasset）\n"
            "3. weight 值范围: 0~1\n"
            "4. location/spacing 单位=厘米(cm)\n"
            "5. height_pattern 内 center_x_m/radius_m 单位=米(m)\n"
            "6. 严格遵循工具返回的知识文档和模板结构\n"
            "..."
        )

    def _register_tools(self, agent: Agent) -> None:
        @agent.tool
        async def inject_knowledge(ctx: RunContext[AgentDeps],
                                   terrain_type: str,
                                   has_water: bool,
                                   has_grass: bool,
                                   placements: list[str]) -> str:
            """按意图注入分层知识文档"""
            return inject_knowledge_core(ctx.deps.knowledge, ...)

        @agent.tool
        async def inject_template(ctx: RunContext[AgentDeps],
                                  template_ref: str) -> str:
            """注入模板标杆 JSON"""
            return inject_template_core(ctx.deps.knowledge, template_ref)

        @agent.tool
        async def search_assets(ctx: RunContext[AgentDeps],
                                keywords: list[str]) -> list[dict]:
            """搜索资产路径"""
            entries = search_assets_core(ctx.deps.asset_index, keywords)
            return [e.model_dump() for e in entries]
```

### 4.5 ScenePlanner → JSONBuilder 的数据流

```
ScenePlannerAgent.run(user_desc)
    → result.output: SceneBlueprint
    → result.output.model_dump_json()  # 序列化为 JSON 字符串

JSONBuilderAgent.run(blueprint_json)
    → result.output: SceneJSON
    → result.output.model_dump()  # 转为 dict 传给 build_scene.py
```

> **关键**: ScenePlanner 的输出（SceneBlueprint）作为 JSONBuilder 的输入（user_prompt）。JSONBuilder 接收蓝图 JSON 字符串，解析后调用工具注入知识，生成完整场景 JSON。

### 4.6 知识注入工具设计

旧架构中 `KnowledgePack.build_system_prompt()` 是硬编码拼接的，v0.3 改为 LLM 按需调用：

```python
# ai/tools/json_tools.py
def inject_knowledge_core(knowledge, intent_dict) -> str:
    """按意图注入分层知识文档（L1 核心 + L2 模式 + L3 资产 + L4 经验）

    复用 KnowledgePack.build_system_prompt() 逻辑，但通过工具调用触发
    """
    asset_paths = []  # 由 LLM 通过 search_assets 工具另行获取
    few_shots = []    # 由 LLM 通过 search_experience 工具另行获取
    return knowledge.build_system_prompt(intent_dict, asset_paths, few_shots)

def inject_template_core(knowledge, template_ref: str) -> str:
    """注入模板标杆 JSON"""
    return knowledge.get_template_by_ref(template_ref)
```

### 4.7 测试策略

| 测试文件 | 测试内容 | 数量 |
|---|---|---|
| `test_v03_scene_json.py` | SceneJSON 模型字段验证、默认值、必填字段 | ~5 |
| `test_v03_json_tools.py` | inject_knowledge_core / inject_template_core 核心函数 | ~4 |
| `test_v03_json_builder.py` | JSONBuilderAgent init/output_type/system_prompt/build/run | ~6 |

测试模式沿用 v0.2：
```python
class TestJSONBuilder(JSONBuilderAgent):
    def _create_model(self):
        return TestModel()

agent = TestJSONBuilder("test-model", "fake-key", deps=AgentDeps())
result = asyncio.run(agent.run(blueprint_json))
assert isinstance(result.output, SceneJSON)
```

---

## 五、v0.4 设计 — QualityGuardAgent（Stage 3，已完成）

### 5.1 目标

对 `SceneJSON` 进行字段校验 + 资产路径校验，有错误时调用 LLM 修复，最多 3 轮。

### 5.2 输出模型 — ValidationReport

```python
class ValidationReport(BaseModel):
    scene: dict                    # 校验/修复后的场景 JSON
    is_valid: bool                 # 最终是否通过
    errors: list[str]              # 错误列表
    warnings: list[str]            # 警告列表
    repair_rounds: int            # 修复轮数
    repair_history: list[dict]     # 每轮校验记录
```

### 5.3 文件结构（v0.4 新增）

```
ai/
├── models/
│   └── validation_report.py  # ValidationReport 模型
├── tools/
│   └── validation_tools.py    # validate_scene_core / validate_assets_core
├── agents/
│   └── quality_guard.py        # QualityGuardAgent
tests/
├── test_v04_validation_report.py
├── test_v04_validation_tools.py
└── test_v04_quality_guard.py
```

### 5.4 QualityGuardAgent 设计

```python
class QualityGuardAgent(AgentBase):
    def _output_type(self) -> Any:
        return ValidationReport

    def _system_prompt(self) -> str:
        return (
            "你是 UE5 场景 JSON 质量守护专家。"
            "调用 validate_scene 工具校验场景 JSON，有错误时修复，最多 3 轮。\n"
            "..."
        )

    def _register_tools(self, agent: Agent) -> None:
        @agent.tool
        async def validate_scene(ctx: RunContext[AgentDeps], scene_json: str) -> dict:
            """校验场景 JSON 字段"""
            scene = json.loads(scene_json)
            errors, warnings = validate_scene(scene)
            return {"errors": errors, "warnings": warnings}

        @agent.tool
        async def validate_assets(ctx: RunContext[AgentDeps], scene_json: str) -> list[str]:
            """校验资产路径是否存在"""
            scene = json.loads(scene_json)
            return validate_scene_assets(scene)
```

---

## 六、文件结构总览（全部版本）

```
ai/
├── __init__.py                 # run_pipeline() 编排函数
├── agents/
│   ├── __init__.py
│   ├── base.py                 # v0.1: AgentBase + AgentDeps
│   ├── scene_planner.py        # v0.2: ScenePlannerAgent (Stage 1)
│   ├── json_builder.py         # v0.3: JSONBuilderAgent (Stage 2) ✅
│   └── quality_guard.py        # v0.4: QualityGuardAgent (Stage 3) ✅
├── models/
│   ├── __init__.py
│   ├── pattern.py              # v0.1: Pattern 模型
│   ├── blueprint.py            # v0.2: SceneBlueprint + AssetEntry + ExperienceRef
│   ├── scene_json.py           # v0.3: SceneJSON + 子模型 ✅
│   └── validation_report.py    # v0.4: ValidationReport ✅
├── tools/
│   ├── __init__.py
│   ├── pattern_tools.py        # v0.1: search_patterns_core / count_patterns_core
│   ├── asset_tools.py         # v0.2: search_assets_core
│   ├── experience_tools.py     # v0.2: search_experience_core
│   ├── knowledge_tools.py      # v0.2: get_pattern_docs / get_template / get_design_principles
│   ├── json_tools.py           # v0.3: inject_knowledge ✅
│   └── validation_tools.py     # v0.4: validate_scene / validate_assets ✅
├── pattern_library.py          # v0.1: PatternLibrary (SQLite)
│
│   —— 旧架构（仍保留，供 GUI 管线使用）——
├── client.py                   # LLMClient / OpenAILLMClient / MockLLMClient
├── knowledge.py                # KnowledgePack
├── asset_index.py              # AssetIndex
├── intent_parser.py            # IntentParser (旧 Stage 1)
├── generator.py                # SceneGenerator (旧 Stage 2)
├── validator.py                # ValidationRepairLoop (旧 Stage 3)
├── experience_bank.py          # ExperienceBank
├── retriever.py                # ExperienceRetriever
└── utils.py                    # extract_json()
```

---

## 七、新旧架构共存策略

### 7.1 当前状态

- **旧架构**（`IntentParser` → `SceneGenerator` → `ValidationRepairLoop`）仍在 `ai/__init__.py` 的 `run_pipeline()` 和 GUI 的 `AIWorker` 中使用
- **新架构**（`ScenePlannerAgent` → `JSONBuilderAgent` → `QualityGuardAgent`）逐步替代旧架构

### 7.2 迁移计划

| 阶段 | 动作 | 风险 |
|---|---|---|
| v0.3 完成 | JSONBuilderAgent 可独立运行，旧 SceneGenerator 仍保留 | 低 — 并存不冲突 |
| v0.4 完成 | QualityGuardAgent 可独立运行，旧 ValidationRepairLoop 仍保留 | 低 — 并存不冲突 |
| 集成 | `run_pipeline()` 切换为 Agent 流水线，GUI `AIWorker` 切换 | 中 — 需端到端测试 |
| 清理 | 移除旧 `IntentParser` / `SceneGenerator` / `ValidationRepairLoop` | 高 — 需确认无引用 |

### 7.3 共存原则

1. 新旧架构共享后端服务（KnowledgePack / AssetIndex / ExperienceBank / ExperienceRetriever）
2. 新架构通过 `AgentDeps` 注入后端，旧架构通过构造函数参数注入
3. 工具核心函数（`_core` 后缀）被新架构使用，旧架构直接调用后端方法
4. 迁移期间不修改旧架构代码，仅新增 Agent 代码

---

## 八、环境变量与配置

```bash
# LLM API Key（必需）
export MAPFORGE_API_KEY="sk-xxx"

# 测试用（可选）
export TEST_API_KEY="sk-xxx"

# Base URL（DeepSeek 示例）
# 在 mapforge_app.py SettingsDialog 中配置
```

**Python 环境**:
- Python 3.14+
- pydantic-ai
- pydantic
- pytest

---

## 九、校验工具

```bash
# 字段校验
python scripts/validate_scene_json.py <场景.json>

# 资产路径校验
python tools/check/validate_scene_assets.py <场景.json>

# 单元测试（全部）
cd UESceneFactory
python -m pytest tests/ -v
```

---

## 十、自我审查

### 10.1 版本覆盖检查

| 版本 | Agent | Stage | 文件 | 测试 | 状态 |
|---|---|---|---|---|---|
| v0.1 | AgentBase | — | base.py, pattern.py, pattern_library.py, pattern_tools.py | 9+ 个 | ✅ |
| v0.2 | ScenePlannerAgent | 1 | scene_planner.py, blueprint.py, 3个tools | 6+ 个 | ✅ |
| v0.3 | JSONBuilderAgent | 2 | json_builder.py, scene_json.py, json_tools.py | 25 个 | ✅ |
| v0.4 | QualityGuardAgent | 3 | quality_guard.py, validation_report.py, validation_tools.py | 19 个 | ✅ |

### 10.2 一致性检查

| 接口 | 签名 | 调用方 | 一致 |
|---|---|---|---|
| `AgentBase.run()` | `(user_prompt) → AgentRunResult` | 所有子类 | ✅ |
| `AgentBase.build()` | `() → Agent` | run() 内部 | ✅ |
| `search_assets_core()` | `(asset_index, keywords, max_results) → list[AssetEntry]` | ScenePlanner / JSONBuilder | ✅ |
| `search_experience_core()` | `(retriever, intent, top_k) → list[ExperienceRef]` | ScenePlanner | ✅ |
| `get_template_core()` | `(knowledge, keywords, terrain_type) → str\|None` | ScenePlanner | ✅ |
| `get_design_principles_core()` | `(knowledge, scene_type) → list[str]` | ScenePlanner | ✅ |
| `get_pattern_docs_core()` | `(knowledge, pattern_name) → str` | ScenePlanner | ✅ |

### 10.3 执行顺序

```
v0.1 (AgentBase) → v0.2 (ScenePlanner) → v0.3 (JSONBuilder) → v0.4 (QualityGuard)
```

严格线性依赖：v0.3 依赖 v0.2 的 SceneBlueprint 输出，v0.4 依赖 v0.3 的 SceneJSON 输出。

### 10.4 设计约束

1. **最小修改量**: v0.3/v0.4 仅新增文件，不修改 v0.1/v0.2 已有代码
2. **中文注释**: 所有代码含详细中文注释
3. **测试先行**: TDD 四步（写测试→验证失败→实现→验证通过）
4. **版本递增**: 每完成一个版本，更新 `mapforge_app.py` 的 `APP_VERSION` 和 `VERSION_HISTORY`
5. **不提交**: 未经用户明确要求，不执行 git commit
