# 多智能体场景 JSON 生成管线 — 底层逻辑与优劣分析

> 本文档分析 UESceneFactory 的三阶段 Agent 流水线架构，梳理底层设计逻辑，评估优势与劣势。

---

## 一、架构总览

```
用户自然语言描述
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: ScenePlannerAgent  (意图解析 + 资产搜索 + 经验检索)     │
│  输入: 用户自然语言                                               │
│  输出: SceneBlueprint (Pydantic 模型)                            │
├─────────────────────────────────────────────────────────────────┤
│  Stage 2: JSONBuilderAgent   (知识注入 + 资产搜索)                │
│  输入: SceneBlueprint.model_dump_json()                          │
│  输出: SceneJSON (Pydantic 模型)                                 │
├─────────────────────────────────────────────────────────────────┤
│  Stage 3: QualityGuardAgent  (字段校验 + 资产校验 + LLM 自主修复) │
│  输入: SceneJSON.model_dump_json()                               │
│  输出: ValidationReport (含修复后的最终场景 JSON)                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
  最终场景 JSON
```

Agent 之间**不直接通信**，而是通过 Pydantic 模型序列化/反序列化传递中间产物。每个 Agent 独立创建、独立销毁，前后阶段仅通过 JSON 字符串交接数据。

**依赖注入容器**：所有 Agent 共享同一个 `AgentDeps` 实例（知识库 / 资产索引 / 经验银行 / 检索器 / content_dir），由编排器在管线启动时初始化，注入各 Agent 的工具函数中。

---

## 二、底层逻辑详解

### 2.1 Stage 1 — ScenePlannerAgent：从自然语言到结构化蓝图

**核心任务**：将用户自由文本描述解析为结构化的 `SceneBlueprint`。

**输入**：`"山谷草地，有一条河流穿过，山坡上有小村庄"`

**输出**：
```
SceneBlueprint {
    terrain_type: "features",         // 地形类型
    has_water: true, has_river: true, // 特征布尔值
    has_grass: true, has_wheat: false,
    placements: ["village", "forest"], // 放置需求
    keywords: ["村庄", "森林", "河流", "山谷"],
    assets: [...],                     // 搜索到的资产路径
    experience_refs: [...],            // 检索到的历史案例
    template_ref: "template_p15_water_river.json", // 匹配的模板
    design_principles: [...]           // 设计原则
}
```

**内部机制**：

1. LLM 被赋予系统提示词，要求按固定步骤执行：解析意图 → 调工具搜索资源 → 输出结构体。
2. **5 个注册工具**均由 Agent 自主决定调用时机和参数：
   - `search_assets(keywords)` — 搜索 UE 资产库，找到可用的 StaticMesh/Blueprint 路径
   - `search_experience(keywords, terrain_type)` — 四因子评分 + MMR 检索相似历史案例
   - `get_design_principles(scene_type)` — 从知识库获取场景类型对应的设计原则（如"森林场景应使用 cull_start/cull_end 距离剔除"）
   - `get_template(keywords, terrain_type)` — 关键词 + 地形类型匹配已验证的模板 JSON
   - `get_pattern_docs(pattern_name)` — 获取特定模式的技术文档（如 height_pattern.md）
3. LLM 在工具返回结果的指导下，组装 `SceneBlueprint`。
4. PydanticAI 对输出做类型校验（`terrain_type` 必须是枚举值、`placements` 必须是合法列表等），失败则自动重试（最多 3 次）。

### 2.2 Stage 2 — JSONBuilderAgent：分层知识注入 + 生成完整 JSON

**核心任务**：将 ScenePlannerAgent 输出的蓝图转为完整的 `build_scene.py` 兼容 JSON。

**分层知识注入机制**（`KnowledgePack.build_system_prompt()`）：

```
┌──────────────────────────────────────────────────┐
│ L1 核心知识 (core.md, ~3KB, 始终注入)              │  基础规范、字段速查、常见错误
├──────────────────────────────────────────────────┤
│ L2 模式文档 (按意图选择注入)                        │
│  - height_pattern.md  (当 terrain != flat)        │  高度模式完整字段表
│  - weight_pattern.md  (当 has_grass 或 has_wheat) │  权重分布 8 种模式
│  - placements.md      (当有 placements)           │  放置进阶字段
│  - asset_guide.md     (当有 placements)           │  资产路径转换规则
│  - examples.md        (始终注入)                   │  最小可用示例
├──────────────────────────────────────────────────┤
│ L2.5 模板标杆 (按意图匹配 1 个高质量 JSON)          │  关键词+地形→匹配最佳模板
│  模板大小限制 ≤ 25KB，超过则跳过                     │  LLM "临摹"而非"盲写"
├──────────────────────────────────────────────────┤
│ L3 资产路径 (最多 30 条，按需注入)                   │  搜索到的 /Game/ 资产路径
├──────────────────────────────────────────────────┤
│ L4 经验 few-shot (历史相似案例)                     │  完整的 用户描述→JSON 对
└──────────────────────────────────────────────────┘
```

**设计意图**：
- **L1 始终注入**：核心规范必须每次都有，避免 LLM 犯基础错误（如路径格式、单位混淆）
- **L2 按需注入**：避免浪费 token——无河流场景不注入水系模式文档；无草地不注入 weight_pattern
- **L2.5 模板标杆**：最关键的提升手段。LLM 拿到一个已验证的完整 JSON 可以直接模仿结构组织、参数取值、注释风格
- **L3/L4 补充**：资产路径解决"路径从哪来"；历史案例解决"这个场景别人怎么写的"

**LLM 的工具调用**：
- `inject_knowledge(terrain_type, ...)` — 触发上述分层注入，返回拼接好的知识文本
- `search_assets(keywords)` — 搜索资产路径

**输出校验**：`PlacementConfig.validate_asset_nonempty` (model_validator) 阻止 `asset=""` 的无效条目，防止 UE 编辑器卡死。校验失败时 PydanticAI 自动重试，将错误反馈给 LLM。

### 2.3 Stage 3 — QualityGuardAgent：LLM 自主驱动的校验修复循环

**核心任务**：接收 Stage 2 的场景 JSON，调用校验工具检测错误，有错则修复后重新校验。

**与旧版 `ValidationRepairLoop` 的区别**：

| | 旧版 (Python for-loop) | 新版 (QualityGuardAgent) |
|---|---|---|
| 修复决策 | Python 代码固定流程 | **LLM 自主决定**何时修复、修什么 |
| 工具调用 | Python 代码直接调函数 | LLM 通过 function calling 调工具 |
| 灵活性 | 固定字段替换 | LLM 可跨字段联动修复（如改 material 后同步调 layer info） |
| 修复上限 | 代码硬编码 | 系统提示词指导 ≤ 3 轮 |

**自驱动循环流程**：

```
LLM 收到场景 JSON
  → 调用 validate_scene(scene_json) 获取字段错误列表
  → 调用 validate_assets(scene_json) 获取缺失资产列表
  → 如果没有错误 → 输出 ValidationReport(is_valid=true)
  → 如果有错误 → 在"脑中"修复 JSON → 重新调用两个校验工具
  → 重复 ≤ 3 轮 → 输出 ValidationReport(is_valid=false/true, repair_rounds=N)
```

**关键设计点**：修复循环的迭代次数由**LLM 自主决策**，不是 Python `for i in range(3)`。LLM 可以：
- 第 1 轮发现 5 个错误 → 修复全部 → 再校验
- 第 2 轮发现 1 个残余错误（资产路径写错） → 用 search_assets 找正确路径替换 → 再校验
- 第 3 轮 0 错误 → 停止，输出 is_valid=true

### 2.4 经验银行 — 越用越好的记忆系统

```
┌──────────────────────────────────────────────────────┐
│  ExperienceBank (SQLite)                              │
│  ~/.uescenefactory/experience.db                     │
├──────────────────────────────────────────────────────┤
│  存储: 每次成功生成的场景 JSON + 用户描述 + 元数据      │
│  检索: 四因子评分(30%关键词Jaccard + 25%地形匹配       │
│        + 25%放置匹配 + 20%新鲜度) + MMR多样性重排       │
│  去重: Jaccard >= 0.6 时更新而非新增                   │
└──────────────────────────────────────────────────────┘
```

**LLM 使用经验的方式**：经验作为 L4 few-shot 注入 Stage 2 的 system prompt，LLM 看到"用户说了 X → 最终生成了 Y"的完整对，可以模仿其 JSON 结构和参数。

### 2.5 会话持久化与断点续跑

```
~/.uescenefactory/sessions/
├── session_20260912_143022/
│   ├── intent.json        ← Stage 1 输出 (SceneBlueprint)
│   ├── scene_json.json    ← Stage 2 输出 (SceneJSON)
│   └── validation.json    ← Stage 3 输出 (ValidationReport)
```

**断点续跑**：
- `resume_from="stage2"`：加载 intent.json，跳过 Stage 1，重跑 Stage 2+3
- `resume_from="stage3"`：加载 intent.json + scene_json.json，跳过 Stage 1+2，重跑 Stage 3
- 用途：Stage 2 崩了不需要重跑 Stage 1（省 token）；只改校验规则时重跑 Stage 3

### 2.6 模板匹配规则

`KnowledgePack._select_template(intent)` 按以下优先级匹配模板：

| 优先级 | 匹配条件 | 示例模板 |
|--------|----------|----------|
| 最高 | 特定地形模式（terraced/karst/gully） | P12 梯田 / P13 喀斯特 / P14 沟壑 |
| 高 | 特定资产关键词（停机坪/光伏/通信塔/高压电塔/森林/村落） | P1 / P5 / P7 / P8 / P10 / P16 |
| 中 | 水系（河流/river/water） | P15 水系 |
| 兜底 | 全地形综合场景 | P11 全地形综合 |

LLM 拿到匹配的模板 JSON 后，在这个"范本"上修改 `target_level`、调整地形参数、增删 placements，而非从零写 JSON。

---

## 三、优势分析

### 3.1 分层知识注入：token 效率与信息完整性的平衡

| 传统的"一次性全部注入" | 本系统的"分层按需注入" |
|---|---|
| L1~L4 全部塞入，大场景 system prompt 轻松 >30KB | 仅注入与当前意图相关的文档，典型 8~20KB |
| LLM 在海量信息中找重点 | LLM 只看到当前场景需要的知识 |
| 简单的平地场景也被灌入水系/river 模式文档 | 平地无河流 → 不注 height_pattern 中 river 相关 |
| token 浪费 → 成本高、输出质量下降 | 精准注入 → token 用在刀刃上 |

### 3.2 模板标杆机制：从"盲写"到"临摹"

这是**提升生成质量最有效**的手段。LLM 仅靠字段表描述很难写出符合项目约定的 JSON（即使字段名都对，参数取值、结构组织方式可能偏离项目风格）。注入一个已验证的真实 JSON 后，LLM 可以直接：

- 模仿其结构组织（landsape 参数放前面、placements 的 type 分组方式）
- 参考其参数取值范围（component_count 用多少、scale 用多少）
- 学习其注释风格（`_note` 注释、中文说明）

### 3.3 双重校验 + LLM 自主修复

```
Pydantic model_validator (Stage 2 输出时)
    ↓ 阻止 asset="" 等致命错误
外部校验脚本 (Stage 3)
    ↓ 字段拼写/类型/必填/枚举 + 资产路径磁盘存在性
LLM 自主修复 (Stage 3, ≤ 3 轮)
    ↓ 跨字段联动修复
```

三层防线，各自覆盖不同类型的错误：
- **Pydantic** 挡住最底层的格式错误（类型不匹配、空值）
- **外部脚本** 挡住语义/领域错误（字段名拼错、路径不存在）
- **LLM 修复** 处理需要上下文理解的修复（改 terrain_type → 需同步改 height_pattern；改 material → 需同步改 layer info）

### 3.4 关注点分离与单一职责

| Agent | 职责 | 只关心 |
|-------|------|--------|
| ScenePlannerAgent | 意图解析 | "用户想要什么场景？有什么资源可用？" |
| JSONBuilderAgent | JSON 生成 | "这个场景的 JSON 应该怎么写？字段如何取值？" |
| QualityGuardAgent | 质量校验 | "生成的 JSON 有错吗？怎么修？" |

每个 Agent 的 system prompt 只需覆盖自己的领域，不会被其他阶段的信息污染。分开调试：Stage 2 出问题只改 JSONBuilderAgent 的 prompt，不影响其他阶段。

### 3.5 经验累积与复用

- SQLite 持久化，跨会话保留
- 四因子评分确保检索相关性（不仅靠关键词，还考虑地形类型和放置需求的结构匹配）
- MMR 多样性重排避免"全是森林场景"的同质化检索结果
- 越用越好：每多生成一个场景，经验库就多一个可参考的案例

### 3.6 断点续跑降低重试成本

- Stage 2 的 LLM 调用失败不需要重跑 Stage 1（省 token + 时间）
- 只改校验规则时只重跑 Stage 3（秒级 vs 完整管线的分钟级）
- 中间产物 JSON 可人工查阅修改后再喂入下一阶段

### 3.7 PydanticAI 框架的自动重试

`AgentBase` 设置 `retries=3`：当 LLM 输出的 JSON 无法通过 `output_type` 的 Pydantic 校验时，框架自动将校验错误反馈给 LLM 重试。这意味着 LLM 不需要"一次写对"——写错了也能从错误消息中学习修正。

---

## 四、劣势与局限性

### 4.1 串行瓶颈 — 无法并行加速

```
Stage 1 (30s) → Stage 2 (60s) → Stage 3 (20s) = 总耗时 ~110s
```

三个阶段严格串行，总时间等于各阶段之和。理想情况下：
- Stage 1 和 Stage 2 依赖关系紧密（Blueprint → JSON），无法并行
- Stage 2 的大 JSON 生成是主要瓶颈（60s+），且是整个管线的关键路径
- 如果有多个 placement 分组需要不同模板，无法并行生成后合并

### 4.2 阶段间信息损失

Stage 1 输出的是 `SceneBlueprint`（结构化的意图 + 搜索到的资产列表），但 LLM 在 Stage 1 的**推理过程**（为什么选这个模板、为什么排除某些资产、对场景布局的构思）不会传递给 Stage 2。

Stage 2 只能看到冷冰冰的 `terrain_type: "features"` 和 `placements: ["village"]`，缺少 Stage 1 的"这张图大概长什么样"的上下文。这可能导致 Stage 2 生成的地形与 Stage 1 预期的布局不一致。

### 4.3 错误传播 — 上游的错下游难纠

```
Stage 1 将 terrain_type 错判为 "flat" (应为 "hills")
    ↓
Stage 2 按 flat 模式生成（无 hills 参数、无 height_pattern 起伏）
    ↓
Stage 3 校验通过（flat 模式确实不需要 hills 字段，字段合法性没问题）
    ↓
最终 JSON 合法但语义错误 — 平地上建了"山谷村庄"
```

QualityGuardAgent 只能校验字段合法性和资产路径存在性，**无法校验业务语义**。如果 Stage 1 的意图解析出错，这个错误会穿透 Stage 2 和 Stage 3，最终产出一个"语法正确但语义错误"的 JSON。

### 4.4 修复轮次有限

QualityGuardAgent 的修复上限是 3 轮（系统提示词指导），复杂错误可能修不完：
- 第 1 轮：修复 5 个字段拼写错误 + 3 个资产路径错误
- 第 2 轮：修复了拼写但引入新的类型错误（把 string 写成了 number）
- 第 3 轮：还剩 1 个资产路径错误（正确的路径在资产库中不存在，LLM 无法"创造"一个存在的路径）
- → 最终 is_valid=false，需要人工介入

对于资产路径不存在的情况，LLM 无法自行找到替代路径（除非重新调 search_assets 工具），而 QualityGuardAgent 目前没有注册 search_assets 工具。

### 4.5 知识文档维护成本

分层知识注入依赖 `data/knowledge/` 下的 markdown 文件与 `build_scene.py` 源代码保持同步。每次在 `build_scene.py` 中新增字段、修改默认值、调整枚举值时，都需要同步更新：
- `core.md`（字段速查表）
- `height_pattern.md`（C++ 解析层字段表）
- `weight_pattern.md`（8 种 pattern 字段表）
- `placements.md`（进阶放置字段）
- `asset_guide.md`（资产路径速查）

目前这些文件**没有自动化同步机制**，完全依赖手动维护。如果知识文档过时，LLM 将基于错误信息生成 JSON，而校验脚本基于源码验证——这会造成"AI 认为合法但实际不合法"的困惑。

### 4.6 单模板匹配的局限性

`_select_template()` 一次只返回一个最佳匹配模板。混合场景难以精准匹配：

| 用户描述 | 匹配结果 | 问题 |
|----------|----------|------|
| "带河流的森林" | P10 森林（关键词"森林"命中在前）或 P15 水系（"河流"命中） | 取决于规则顺序，但两者都不完美 |
| "山坡上的光伏阵列" | P5 光伏（关键词命中） | 模板是平地上的光伏，无山丘地形参数 |
| "梯田上的村庄" | P12 梯田（地形优先） | 模板无 village placement，LLM 需要自己添加 |

当前规则表按优先级顺序匹配，先命中先返回。没有"同时匹配两个模板"或"模板组合"机制。

### 4.7 经验检索的精度风险

四因子评分 + MMR 检索依赖关键词匹配的准确性：
- 用户说"田园风光" → 关键词解析为 ["田园", "风光"] → 可能匹配到"麦田+栅栏"、"草地+农舍"、"梯田+村落"等不同风格的案例
- MMR 多样性重排可能把真正相似的案例排到后面
- 历史案例质量参差不齐——早期生成的 JSON 可能存在瑕疵，但也被存入经验库

### 4.8 上下文窗口与 JSON 大小限制

- 模板注入大小上限 `_MAX_TEMPLATE_BYTES = 25000`（约 25KB）
- 超限模板（如 P2 围栏 45KB）被排除，LLM 失去参考该场景的机会
- 大规模场景 JSON（1km 全地形 + 多种 placement）可能超过 LLM 的 context window
- 当 system prompt（L1~L4 知识注入）+ 用户消息 + 输出 JSON 合计超过 context window 时，LLM 会截断或生成不完整的 JSON

### 4.9 平台耦合

- 默认 LLM 配置硬编码了阿里云百炼 API（`glm-5.2`）
- 虽然配置文件可覆盖，但 PydanticAI 的 tool use 和 output_type 机制对模型能力有要求（需要支持 function calling + structured output）
- 切换到不支持 function calling 的模型（如部分开源模型）会导致工具调用失效

---

## 五、总结

| 维度 | 评价 |
|------|------|
| **架构清晰度** | ★★★★★ 三段式流水线，关注点分离，易于理解和调试 |
| **生成质量** | ★★★★☆ 模板标杆 + 分层知识 + 经验 few-shot 三重保障，首次生成质量较高 |
| **鲁棒性** | ★★★☆☆ 双重校验 + LLM 修复，但语义错误无法纠错；经验检索偶有噪声 |
| **可维护性** | ★★★☆☆ 知识文档与源码手动同步，新增字段需更新多处；Agent prompt 较分散 |
| **成本效率** | ★★★★☆ 分层注入节省 token，经验复用降低重复推理，但串行三阶段无法并行 |
| **扩展性** | ★★★☆☆ 单模板匹配限制混合场景；缺少多模板组合机制；context window 限制大规模场景 |

**最适合的场景**：单一主题的中等复杂度场景（森林 / 村庄 / 梯田 / 水系等），匹配的模板覆盖度高，生成质量稳定。

**需要小心的场景**：跨主题混合场景（"山上的森林村庄 + 山下的河流 + 远处的光伏阵列"）、模板不匹配的场景（全新主题无对应模板）、超大规模场景（JSON > 50KB）。