# 叙事扩写 Agent 设计规格 — Stage 0: NarrativeEnricherAgent

> 版本: v2.9.0 规划 | 日期: 2026-09-15 | 状态: 已确认设计，待实施

## 一、背景与动机

### 1.1 问题

当前流水线 `user_desc`（用户原始输入）原封不动地传入 Stage1 ScenePlannerAgent。当用户输入很简短时（如"江西农村"仅 4 字），LLM 需要在一次调用中同时完成**语义想象**和**结构化提取**两个任务，导致：

- 概念展开不充分（Stage1 的概念展开表是静态映射，无法动态想象）
- 场景要素覆盖不全（"江西农村"的江西地域特色无法体现）
- 结构化字段提取精度不足（输入信息量太少）

### 1.2 目标

在 Stage1 之前插入一个**叙事扩写层（Stage 0）**：用 LLM 把简短输入"想象"成几段富有画面感的场景描写，用户可在 GUI 中查看并编辑后，再喂给 Stage1 做结构化提取。扩写后的丰富叙事能显著提升 Stage1 的提取精度。

### 1.3 用户决策（brainstorming 确认）

| 决策点 | 选择 |
|--------|------|
| 可见性 | 展示 + 可编辑（用户可修改 AI 扩写的叙事后再继续） |
| 架构定位 | 独立 Stage 0 调用（新增扩写 Agent，单独 LLM 调用） |
| 叙事风格 | 两者兼顾（文学画面感开篇 + 务实要素清单） |
| 实现方案 | 方案 A（新建 NarrativeEnricherAgent + 两阶段流水线 + GUI 可编辑面板） |
| 跳过逻辑 | 用户手动开关（GUI 复选框控制是否扩写） |

## 二、整体架构

### 2.1 改造后的流水线

```
用户输入 "江西农村"
  │
  ├─ [启用叙事扩写 = True]
  │   ▼
  │  Stage 0: NarrativeEnricherAgent.run("江西农村")
  │  │  LLM 扩写出:
  │  │  "远山如黛，连绵起伏于天际线……（文学开篇）
  │  │   要素清单：山脉背景/小溪/梯田/杉竹林/村落……（务实清单）"
  │  ▼
  │  GUI 弹出可编辑文本框 → 用户阅读/修改 → 点击"确认并继续"
  │  │  (threading.Event 跨线程同步：AgentWorker 阻塞等待)
  │  ▼
  │  Stage 1: ScenePlannerAgent.run(编辑后的叙事)  ← 输入信息量大幅提升
  │
  ├─ [启用叙事扩写 = False]
  │   ▼
  │  Stage 1: ScenePlannerAgent.run(user_desc)     ← 原样传入，行为不变
  │
  ▼
Stage 2 / Stage 3 不变
```

### 2.2 跨线程同步机制

```
AgentWorker (QThread)              GUI 主线程
─────────────────────              ──────────────
Stage0 完成
emit stage0_done(narrative)  →    _on_stage0(): 填充面板+启用按钮
                                  用户编辑文本
_enrich_event.wait()  ← 阻塞     用户点击"确认"
                                  _on_confirm_stage0():
                                    worker.confirm_enrichment(text)
_enrich_event.set()        ←     _enrich_event.set()
(线程恢复)
user_desc = _enriched_text
继续 Stage1/2/3
```

- `threading.Event` 是 Python 标准库线程同步原语，线程安全
- QThread 在 `wait()` 阻塞期间 GUI 主线程完全不受影响（不依赖 Qt 事件循环）
- `wait()` 无超时——用户必须确认才能继续；若关闭窗口，Qt 会终止线程

## 三、模块详细设计

### 3.1 NarrativeEnricherAgent（新文件）

**文件**: `ai/agents/narrative_enricher.py`（约 60 行）

```python
"""NarrativeEnricherAgent — 叙事扩写智能体。

把用户简短的自然语言描述扩写为富有画面感的场景叙事，
供 Stage1 ScenePlannerAgent 做更精准的结构化提取。
"""
from typing import Any

from pydantic_ai import Agent

from ai.agents.base import AgentBase


class NarrativeEnricherAgent(AgentBase):
    """叙事扩写 Agent — 固定流水线的第 0 个 Agent（可选）。

    职责：把简短输入 → 文学画面描写 + 务实要素清单
    输出：纯文本字符串（output_type=str，非结构化 JSON）
    工具：无（纯 LLM 生成，不调用搜索/经验等工具）
    """

    def _output_type(self) -> Any:
        return str

    def _system_prompt(self) -> str:
        return (
            "你是一个 UE5 场景叙事扩写专家。你的任务是把用户简短的自然语言描述，\n"
            "扩写成富有画面感的场景叙事，供后续结构化提取使用。\n\n"
            "==== 扩写规则 ====\n"
            "1. 先用 2-3 句文学化语言描绘场景画面（意境、氛围、色彩、光影）\n"
            "   例：\"远山如黛，连绵起伏于天际线。小溪从山间蜿蜒而出……\"\n"
            "2. 再用 1-2 段务实地列出场景要素清单：\n"
            "   - 地形特征（山脉/平地/丘陵/沟壑/梯田/喀斯特等）\n"
            "   - 水系（河流/湖泊/溪流/无水）\n"
            "   - 植被（森林/草地/麦田/枯树等，注明树种更好）\n"
            "   - 建筑/设施（村落/电塔/光伏/停机坪等）\n"
            "   - 氛围/时间/天气（如适用）\n"
            "3. 扩写要符合中国环境常识，体现地域特色\n"
            "4. 【强制】保留用户原始描述中的关键参数，原样不可意译：\n"
            "   尺寸格式必须保留（如\"2km*2km\"不可改写为\"两公里见方\"）\n"
            "   地域名必须保留（如\"江西\"不可改写为\"南方某地\"）\n"
            "   在要素清单末尾单独列出: \"参数: 尺寸=2km*2km, 地域=江西\"\n"
            "   未提及尺寸/地域时省略该行，不要编造\n"
            "5. 描述要素之间的定性空间关系，让人脑海出现画面：\n"
            "   - 用方位词描述相对位置（北侧远景/东南近景/村后/山前/沿河岸）\n"
            "   - 用流向词描述水系走向（从东北流向西南/蜿蜒穿村而过）\n"
            "   - 用分布词描述植被疏密（成片/稀疏/环绕/点缀/依山势而下）\n"
            "   ⚠️ 只描述定性关系，严禁写绝对坐标/精确尺寸/网格参数/资产路径\n"
            "   ✅ 正确: \"山脉在北侧远景，东西走向\" \"溪流从东北流向西南\"\n"
            "   ❌ 错误: \"山脉中心(1500,800)半径300m\" \"grid rows=10 cols=5\"\n"
            "   定量参数由 Stage2 根据资产/地形尺寸/模板规则生成，Stage0 无此信息\n"
            "6. 输出纯文本，不要 JSON，不要 markdown 标记\n\n"
            "==== 示例 ====\n"
            "输入：\"2km*2km江西农村\"\n"
            "输出：\n"
            "远山如黛，连绵起伏于北侧天际线（背景山脉，东西走向），山腰云雾缭绕。\n"
            "一条小溪从东北方山间蜿蜒而出，流经村前汇入一方水塘（水系 NE→SW）。\n"
            "村后（北侧）密林成片，以杉木和毛竹为主。村前（南侧）是层层叠叠的\n"
            "梯田，依山势而下，田埂间杂草丛生。村落房屋散布在山脚缓坡上，\n"
            "粉墙黛瓦，错落有致。\n\n"
            "场景要素清单：\n"
            "- 地形：北侧连绵山脉背景（远景）+ 山脚缓坡 + 南侧梯田\n"
            "- 水系：东北→西南流向的山间小溪 + 村前水塘\n"
            "- 植被：村后（北侧）成片杉木毛竹林 + 梯田农作物 + 田埂杂草\n"
            "- 建筑：村落房屋（粉墙黛瓦，散布山脚缓坡）\n"
            "- 氛围：清晨雾气，暖色调\n"
            "- 参数: 尺寸=2km*2km, 地域=江西\n"
        )

    def _register_tools(self, agent: Agent) -> None:
        """叙事扩写不需要工具调用，纯 LLM 生成。"""
        pass
```

**设计要点**:
- `output_type=str`: pydantic_ai 直接返回 LLM 原始文本，不做 JSON 解析
- `_register_tools` 空实现: 扩写是纯生成任务，无需搜索资产/经验/模板
- 继承 AgentBase: 复用 `build()` 缓存 + `run(user_prompt)` 封装，与其他 Agent 一致

### 3.2 AgentWorker 改造

**文件**: `scripts/mapforge_app.py` L1205-1347

**新增信号** (L1218 区域):
```python
stage0_done = pyqtSignal(str)   # 叙事扩写文本（供 GUI 展示/编辑）
```

**`__init__` 改造** (L1227):
```python
def __init__(self, config, user_desc, enable_enrichment=False):
    super().__init__()
    self._config = config
    self._user_desc = user_desc
    self._enable_enrichment = enable_enrichment
    self._enrich_event = threading.Event()  # 跨线程同步:等待用户确认
    self._enriched_text = ""                 # 用户编辑后的文本(由GUI线程设置)
```

**`run()` 改造** (在 L1288 Stage1 之前插入):
```python
# ---- Stage 0: 叙事扩写 (可选) ----
if self._enable_enrichment:
    self.log_line.emit("Stage 0: 叙事扩写 (NarrativeEnricherAgent)...")
    # 懒加载扩写 Agent (与 Stage1/2/3 一起在此处导入)
    from ai.agents.narrative_enricher import NarrativeEnricherAgent
    # 扩写专用模型: config.stage_models["stage0"]，未配置则用主模型
    model_stage0 = stage_models.get("stage0", model_name)
    enricher = NarrativeEnricherAgent(
        model_stage0, api_key, base_url=base_url, deps=deps)
    result0 = loop.run_until_complete(enricher.run(user_desc))
    narrative = result0.output
    self.stage0_done.emit(narrative)
    # 提取 Stage 0 token 消耗并上报
    u0 = result0.usage
    token_tracker.add(u0.input_tokens, u0.output_tokens)
    # 阻塞等待用户编辑确认
    self.log_line.emit("等待用户确认扩写叙事...")
    self._enrich_event.clear()
    self._enrich_event.wait()
    # 用编辑后的文本替换原始输入
    user_desc = self._enriched_text
    self.log_line.emit("用户确认扩写叙事，继续 Stage 1")
```

**新增方法** (供 GUI 线程调用):
```python
def confirm_enrichment(self, edited_text: str):
    """GUI 线程调用: 设置编辑后的文本并释放等待。"""
    self._enriched_text = edited_text
    self._enrich_event.set()
```

**import 补充**: 文件顶部需新增 `import threading`（若尚未导入）

### 3.3 AgentPipelinePanel GUI 改造

**文件**: `scripts/mapforge_app.py` L2248+

#### 3.3.1 UI 新增 (`_init_ui` 方法)

在输入框 `input_row` 下方、进度条之前插入:

```python
# 叙事扩写开关 (Stage 0)
enrich_row = QHBoxLayout()
self._enrich_checkbox = QCheckBox("启用叙事扩写 (Stage 0: AI 先把简短描述扩写成画面感叙事)")
self._enrich_checkbox.setChecked(True)  # 默认启用
self._enrich_checkbox.setToolTip(
    "勾选后，流水线先调用 LLM 把输入扩写为丰富叙事，用户可编辑后再进入 Stage 1\n"
    "取消勾选则直接把原始输入传给 Stage 1（行为同 v2.8.x）")
enrich_row.addWidget(self._enrich_checkbox)
left.addLayout(enrich_row)

# Stage 0 折叠面板: 可编辑文本 + 确认按钮
self._stage0_btn, self._stage0_content = self._make_collapsible("Stage 0: 叙事扩写")
# Stage 0 内容区设为可编辑 (其他阶段面板是只读的)
self._stage0_content.setReadOnly(False)
self._stage0_content.setMaximumHeight(200)
self._stage0_confirm_btn = QPushButton("确认并继续 Stage 1")
self._stage0_confirm_btn.setObjectName("reviewBtn")
self._stage0_confirm_btn.setEnabled(False)
self._stage0_confirm_btn.clicked.connect(self._on_confirm_stage0)
left.addWidget(self._stage0_btn)
left.addWidget(self._stage0_content)
left.addWidget(self._stage0_confirm_btn)
```

注意: `_make_collapsible` 返回的 QTextEdit 默认 `setReadOnly(True)`，
Stage 0 面板需要在创建后改为 `setReadOnly(False)` 以允许用户编辑。

#### 3.3.2 `_start_pipeline` 改造

```python
def _start_pipeline(self, user_desc):
    # ... 现有代码不变 ...
    enable_enrich = self._enrich_checkbox.isChecked()
    self._worker = AgentWorker(self._config, user_desc, enable_enrichment=enable_enrich)
    # ... 现有信号连接不变 ...
    self._worker.stage0_done.connect(self._on_stage0)   # 新增
    # ... 其余不变 ...
```

进度条重置也需包含 Stage0 面板:
```python
self._stage0_content.clear()
self._stage0_confirm_btn.setEnabled(False)
```

#### 3.3.3 新增回调方法

```python
def _on_stage0(self, narrative):
    """Stage 0 完成: 填充可编辑面板 + 自动展开 + 启用确认按钮"""
    self._stage0_content.setPlainText(narrative)
    self._stage0_btn.setChecked(True)
    self._stage0_confirm_btn.setEnabled(True)
    self._progress.setValue(20)
    self._append_chat("[Stage 0] 叙事扩写完成，请查看并编辑后确认")

def _on_confirm_stage0(self):
    """用户确认扩写叙事: 取编辑后文本 → 通知 Worker 继续 → 禁用按钮"""
    edited = self._stage0_content.toPlainText().strip()
    if not edited:
        self._append_chat("[Stage 0] 扩写内容为空，请编辑后重试")
        return
    self._worker.confirm_enrichment(edited)
    self._stage0_confirm_btn.setEnabled(False)
    self._append_chat("[Stage 0] 用户已确认，继续 Stage 1")
```

#### 3.3.4 进度条数值调整

| 阶段 | 扩写启用 | 扩写关闭 |
|------|---------|---------|
| Stage 0 | 20% | — |
| Stage 1 | 40% | 33% |
| Stage 2 | 70% | 66% |
| Stage 3 | 100% | 100% |

实现: `_on_stage0` 设 20%；`_on_stage1` 根据 `enable_enrich` 设 40% 或 33%；
`_on_stage2` 设 70% 或 66%。需要传递 `enable_enrich` 状态或用实例变量记录。

## 四、配置支持

`config["stage_models"]` 新增可选 `"stage0"` 键:

```json
{
  "llm_model": "glm-5.2",
  "stage_models": {
    "stage0": "glm-5.2",
    "stage1": "glm-5.2",
    "stage2": "glm-5.2",
    "stage3": "glm-5.2"
  }
}
```

- 未配置 `stage0` 时: 默认用 `model_name`（主模型），**完全向后兼容**
- 用户可为 `stage0` 配置更强的创意模型，为 `stage1-3` 配置结构化能力强的模型

## 五、改动文件清单

| 文件 | 操作 | 改动内容 | 预估行数 |
|------|------|---------|---------|
| `ai/agents/narrative_enricher.py` | **新增** | NarrativeEnricherAgent 类 | ~60 行 |
| `scripts/mapforge_app.py` | 修改 | AgentWorker: 信号+init+run+confirm方法 | ~30 行 |
| `scripts/mapforge_app.py` | 修改 | AgentPipelinePanel: UI+回调+进度调整 | ~40 行 |

**不改动**: `base.py`、`scene_planner.py`、`json_builder.py`、`quality_guard.py`、`run_agent_pipeline.py`、`blueprint.py` 等已有文件全部不动。

## 六、测试计划

### 6.1 单元测试

| 测试项 | 方法 |
|--------|------|
| NarrativeEnricherAgent 可构建 | 实例化 + 调用 `build()` 不报错 |
| `_system_prompt()` 返回非空字符串 | 断言 len > 0 且包含"扩写规则" |
| `_output_type()` 返回 `str` | 断言 `is str` |
| `confirm_enrichment` 设置文本+释放Event | 创建Event → confirm → assert is_set |

### 6.2 集成测试

| 测试项 | 方法 |
|--------|------|
| 扩写关闭时行为不变 | `enable_enrichment=False` → Stage1 收到原始 user_desc |
| 扩写启用时流程完整 | mock LLM → Stage0 emit → confirm → Stage1 收到编辑文本 |
| threading.Event 同步正确 | Worker wait 期间 GUI confirm → Worker 恢复 |

### 6.3 现有测试回归

运行 `python -m pytest tests/` 确保 144 项测试全部通过（现有测试不受影响，因 AgentWorker 新参数有默认值 False）。

## 七、版本计划

- **版本号**: v2.8.3 → v2.9.0（中等改动: 新增 Agent + UI 面板 + 流水线改造 → middle+1）
- **VERSION_HISTORY 条目**:
  ```
  v2.9.0 - [新增] Stage 0 叙事扩写 Agent (NarrativeEnricherAgent): 在 Stage1 之前
    用 LLM 把简短输入扩写为文学画面+要素清单的丰富叙事，GUI 可编辑后确认再继续，
    支持 stage_models["stage0"] 配置扩写专用模型，默认启用可手动关闭
  ```

## 八、风险与约束

1. **跨线程阻塞**: QThread 在 `Event.wait()` 阻塞期间若用户关闭窗口，Qt 会终止线程。可接受（不影响数据，只是放弃本次生成）。
2. **额外 LLM 调用**: 扩写增加一次 LLM 调用（~3-5 秒 + tokens 消耗）。用户可通过复选框关闭。
3. **扩写质量依赖模型**: 扩写效果取决于 LLM 创意能力，建议 `stage0` 配置较强模型。
4. **`output_type=str` 兼容性**: 需确认 pydantic_ai 支持 `output_type=str`（纯文本返回而非结构化）。若不支持，需用 `output_type=None` + 从 `result.output` 取原始文本。
5. **结构化参数意译风险（已缓解）**: LLM 天然倾向意译，可能把 "2km*2km" 改写为 "两公里见方"，
   导致 Stage 1 的正则提取规则（`"Nkm*Nkm"→[N*1000,N*1000]`）匹配失败 → size_m=[] → Stage 2 用默认 504m 而非 2000m。
   缓解措施：系统提示词规则 4 已标注【强制】，要求原样保留格式并在要素清单末尾单独列出参数行，
   供 Stage 1 精确匹配。用户也可在 GUI 编辑面板中手动修正。
6. **定量空间规划禁区（已规避）**: Stage 0 缺少场景尺寸/资产列表/地形坐标系/模板规则等信息，
   若试图描述绝对坐标/精确尺寸/网格参数，必然产生与 Stage 2 实际生成结果矛盾的参数。
   规避措施：系统提示词规则 5 明确"严禁写绝对坐标/精确尺寸/网格参数/资产路径"，
   只允许定性空间关系（方位/流向/疏密），详见第十章边界分析。

## 九、自审记录

实现时需补充的导入项（规格文档中已提及，此处汇总）:

1. **`import threading`** — mapforge_app.py 顶部未导入 threading，需新增
   （用于 AgentWorker 的 `threading.Event` 跨线程同步）

2. **`QCheckBox`** — mapforge_app.py L20-26 的 `from PyQt6.QtWidgets import (...)`
   未包含 QCheckBox，需添加到导入列表
   （用于 AgentPipelinePanel 的"启用叙事扩写"复选框）

3. **`output_type` 验证**: base.py L75-77 逻辑为 `if output_type is not None: agent_kwargs["output_type"] = output_type`。
   - 返回 `str` → 显式设 `output_type=str`，pydantic_ai 返回纯文本
   - 返回 `None` → 不设 output_type，pydantic_ai 默认也返回文本
   - 两者均可，`str` 更自文档化，推荐用 `str`

4. **`_make_collapsible` readOnly 修改**: 该方法 L2390 默认 `setReadOnly(True)`，
   Stage 0 面板需在创建后调用 `setReadOnly(False)` 使其可编辑，
   不影响 toggle 逻辑（`_on_stage_toggle` 只管 `setVisible`）。

5. **进度条状态传递**: AgentPipelinePanel 需用实例变量 `self._enable_enrich`
   记录复选框状态，供 `_on_stage1`/`_on_stage2` 判断设 40%/70% 还是 33%/66%。

## 十、定性空间关系 vs 定量空间参数——Stage 0 与 Stage 2 的边界

### 10.1 背景

用户提出升级设想：Stage 0 除了叙事扩写，还应描述每种地形的**位置、大小、方向、资产放置详细参数**，
让人脑海中出现一幅初始画面。经分析，该设想意图好但范围过宽——精确空间参数是 Stage 2 的核心职责，
Stage 0 缺少做定量决策所需的信息。最终确认：Stage 0 升级到"**定性空间关系**"为止。

### 10.2 信息不对称——Stage 0 为何不能做定量空间规划

| 做定量空间决策需要的信息 | 拥有者 | Stage 0 有吗 |
|------------------------|--------|-------------|
| 场景物理尺寸（2km 还是 500m） | Stage 1 从 size_m 提取，Stage 2 计算 component_count | ❌ |
| 可用资产列表（有没有村庄 mesh？杉树 mesh？） | Stage 1 的 search_assets 工具 | ❌ |
| 地形坐标系（section_size_quads=63, scale=100） | Stage 2 的 LandscapeConfig | ❌ |
| 模板网格规则（围栏几行几列？间距多少？） | Stage 1 的 get_template 工具 | ❌ |
| 密度/间距约束（草地 density、森林覆盖率） | Stage 2 的知识文档注入 | ❌ |

Stage 0 在"信息真空"中做空间决策，必然产生与实际资产/地形不匹配的参数：
- 坐标越界（不知道场景只有 500m 却写 x=1500）
- 资产不匹配（不知道有没有村庄 mesh 就写 50 栋房屋）
- 网格参数被模板覆盖（Stage 2 从模板注入的 grid 配置会覆盖 Stage 0 的描述）

### 10.3 边界定义

| 层次 | 归属 | 示例 |
|------|------|------|
| ✅ 定性空间关系（Stage 0） | 叙事扩写 Agent | "山脉在北侧远景，东西走向" "溪流从东北流向西南" "村后密林成片" |
| ❌ 定量空间参数（Stage 2） | JSON 构建 Agent | `hills[].center_x_m=1500, radius_m=300` `grid.rows=10, cols=5` |

**原则**：Stage 0 描述"画面"（要素之间的相对方位/前后/疏密关系），
Stage 2 根据"画面" + 资产/地形/模板信息生成"工程参数"（精确坐标/网格/实例数）。

### 10.4 与下游智能体的重叠/冲突评估

| 下游 | 重叠度 | 说明 |
|------|--------|------|
| Stage 1 (ScenePlanner) | 低 | Stage 1 概念展开表只描述要素**组合**，不涉及空间方位；Stage 0 加定性方位不重复 |
| Stage 2 (JSONBuilder) | 低（升级后） | 定性空间关系作为 Stage 2 的"参考画面"，引导其生成更连贯的坐标布局；Stage 2 仍负责所有定量参数 |

### 10.5 替代架构备忘（不在本次实施范围）

若未来认为 Stage 2 从零规划空间布局质量不足，可考虑在 Stage 1 和 Stage 2 之间
插入 **Stage 1.5 SpatialPlannerAgent**——此时已有 Stage 1 搜索到的资产列表和 size_m，
可做有依据的定量空间规划。此方案增加一次 LLM 调用，需单独评估收益。
