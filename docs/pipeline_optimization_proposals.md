&lt;!-- 多智能体管线 — 劣势优化方案 --&gt;

# 多智能体管线 — 劣势优化方案

&gt; 本文档针对《多智能体场景 JSON 生成管线 — 底层逻辑与优劣分析》中识别的 9 项劣势，
&gt; 逐一分析根因并结合当前代码实现提出可落地的优化方案。
&gt; 每个方案标注实施难度（★=低 ★★=中 ★★★=高）和预估收益（$=低 $$=中 $$$=高）。

---

## 劣 1：串行瓶颈 — 无法并行加速

### 根因

```
Stage1 (30s) → Stage2 (60s) → Stage3 (20s) = 总耗时 ~110s
```

三个阶段存在严格的数据依赖链（Stage1 输出→Stage2 输入→Stage3 输入），直接并行化不可行。关键瓶颈在 Stage2（大 JSON 生成需 60s+）。

### 优化方案

**方案 A：分级模型策略** ★ / $$$

| 阶段 | 当前模型 | 建议模型 | 推理 |
|------|----------|----------|------|
| Stage1（意图解析） | glm-5.2（大模型） | glm-4-flash / qwen-turbo | 意图解析是分类+关键词提取，小模型足够 |
| Stage2（JSON 生成） | glm-5.2（大模型） | glm-5.2（保持） | JSON 生成是核心质量关卡，需强模型 |
| Stage3（校验修复） | glm-5.2（大模型） | glm-4-flash | 校验修复是结构化纠错，小模型可胜任 |

实现方式：在 `run_agent_pipeline.py` 的配置中增加 `stage_models` 字典，允许每个阶段使用不同模型。

```
# 在 ~/.uescenefactory_config.json 中新增可选字段
{
  "llm_model": "glm-5.2",            // 全局默认（向后兼容）
  "stage_models": {                   // 可选：阶段级覆盖
    "stage1": "glm-4-flash",
    "stage2": "glm-5.2",
    "stage3": "glm-4-flash"
  }
}
```

预期效果：Stage1 30s→10s，Stage3 20s→8s，总耗时 110s→78s（节省约 30%）。

---

**方案 B：合并 Stage1+2 为单次 LLM 调用** ★★ / $$

将 ScenePlannerAgent 的意图解析能力合并到 JSONBuilderAgent 的 system prompt 中，由一次 LLM 调用同时完成意图解析和 JSON 生成。

当前分离的初衷是关注点分离便于调试，但代价是额外一次完整的 LLM 往返（网络延迟 + 推理时间）。合并后：

- 省掉 Stage1 的独立 LLM 调用（~30s）
- 总耗时 110s→80s
- 但 system prompt 会变长（意图解析指令 + JSON 生成指令混在一起）
- 调试变困难（无法分阶段检查中间产物）

权衡：短期不推荐。关注点分离的价值大于省 30 秒，Stage1 的 SceneBlueprint 对于断点续跑和人工审查都很有用。

---

**方案 C：知识注入预计算缓存** ★ / $$

当前 `KnowledgePack.build_system_prompt()` 每次执行管线都从头拼接知识文档。对于相同 `(terrain_type, has_water, has_river, has_grass, has_wheat, placements)` 组合，注入结果完全一致。

`KnowledgePack` 已有 `_cache` 机制缓存模式文档，可进一步缓存完整的 `build_system_prompt` 结果：

```python
# knowledge.py — 增加 prompt 级缓存
def build_system_prompt(self, intent, asset_paths, few_shots):
    cache_key = self._make_cache_key(intent, asset_paths, few_shots)
    if cache_key in self._prompt_cache:
        return self._prompt_cache[cache_key]
    result = self._do_build(intent, asset_paths, few_shots)
    self._prompt_cache[cache_key] = result
    return result
```

对 LLM 而言无变化（仍然收到相同的 system prompt），但节省了 Python 层的字符串拼接和文件 IO 时间。效果有限（拼接本身 <1s），但对频繁重复的意图组合有意义。

---

**方案 D：Stage3 纯 Python 替代** ★★ / $$

当前 QualityGuardAgent 用 LLM 做校验修复循环，但大部分修复是确定性的（字段名拼错→改正确、资产路径不存在→尝试 search_assets 替换）。可以考虑：

```
QualityGuardAgent(LLM 驱动) → 保留，作为"智能修复"层
    +
ValidationRepairLoop(Python 驱动) → 新增，作为"快速修复"先行层
```

先跑 Python 的确定性修复（拼写纠错、路径替换、类型转换），如果全修完跳过 LLM；只把修不完的错误交给 LLM。

预期效果：大多数简单错误（占 70%+）被 Python 秒级修复，Stage3 耗时 20s→6s。

---

## 劣 2：阶段间信息损失

### 根因

`SceneBlueprint` 模型只传递结构化字段（`terrain_type` / `placements` / `keywords` / `assets` 等），不包含 Stage1 LLM 的推理过程。

例如：LLM 在 Stage1 的推理过程中可能"想到"——"这个场景需要山坡上的村庄 + 山谷中的河流，村庄应该放在 terrain 的西北角高地"——但这些布局思路不会写入 SceneBlueprint。

### 优化方案

**方案 A：Blueprint 增加 reasoning 和 layout_hints 字段** ★ / $$

在 `SceneBlueprint` 模型中新增两个可选字段，让 LLM 有机会传递推理过程：

```python
# blueprint.py
class SceneBlueprint(BaseModel):
    # ... 现有字段 ...
    reasoning: str = ""          # LLM 的完整推理链条
    layout_hints: dict = Field(default_factory=dict)
    # 例如: {"village_location": "northwest_hill", "river_flow": "east_to_west"}
```

Stage2 的 system prompt 中注入 `reasoning` 和 `layout_hints`：

```
Stage 1 的推理过程：
{blueprint.reasoning}

空间布局提示：
{blueprint.layout_hints}
```

Stage1 LLM 是否填充这些字段取决于其自主判断（不能强制——强行要求反而可能产生幻觉）。但对于复杂场景，LLM 通常会自然产生布局思路，这些信息对 Stage2 的 JSON 生成（尤其是 placement 的 location 取值）有直接指导作用。

---

**方案 B：Stage2 同时接收原始用户描述** ★ / $

`run_agent_pipeline.py` 中，Stage2 的 user_prompt 目前只传入 `blueprint_json`。可以让 Stage2 也看到用户的原始描述：

```python
# 当前:
result2 = await builder.run(blueprint_json)

# 优化: 拼接原始描述 + 蓝图
result2 = await builder.run(
    "用户原始描述：{user_desc}\n\n解析蓝图：{blueprint_json}"
)
```

这样 Stage2 的 LLM 可以交叉校验——蓝图解析结果和原始意图是否一致，不一致时可以自行修正。

---

## 劣 3：错误传播 — 语义错误穿透三层防线

### 根因

```
Stage1 判错 terrain_type → Stage2 依错生成 → Stage3 校验字段合法（但业务错误）→ 无报错通过
```

QualityGuardAgent 的校验是**形式校验**（字段存在、类型正确、路径存在），不是**语义校验**（这个场景描述用 hills 地形是否合理）。

### 优化方案

**方案 A：Stage3 增加语义一致性校验规则** ★ / $$

在 `validate_scene_json.py` 中增加语义规则层（仅 warning，不阻断通过）：

| 规则 | 检测逻辑 | 级别 |
|------|----------|------|
| 地形-放置不匹配 | terrain=flat 但 placements 含"山坡上的村庄"关键词 | warning |
| 水系缺失 | has_river=true 但 landscape.height_pattern 无 rivers 字段 | warning |
| 图层缺失 | weight_pattern 中引用的 layer_name 不在 layers[] 中 | error（已有） |
| 植被-地形冲突 | flat 地形 + wheat_varieties > 0 | warning |

这些规则不阻塞流水线（语义判断本身不精确），而是作为 warning 提示用户审查。如果用户确认 DSL 与意图相符，这些 warning 可忽略。

---

**方案 B：Stage2 逆向提问能力** ★★★ / $$

让 Stage2 的 LLM 有能力"质疑"Stage1 的输出。在 JSONBuilderAgent 的 system prompt 中增加：

```
如果蓝图的 terrain_type 与 placements 存在明显矛盾（如 terrain_type="flat"
但 placements=["village"] 而用户描述提到"山坡"），请在生成的 JSON 描述字段中
标注疑点，并主动修正 terrain_type。
```

但这依赖 LLM 的判断力，且可能引入新的不稳定性（LLM 过度修正正确的蓝图）。投入产出比不高。

---

**方案 C：多轮确认关键决策** ★★ / $$

对于置信度低的意图字段（如 terrain_type 的判断有歧义），Stage1 可以设置置信度标记：

```python
class SceneBlueprint(BaseModel):
    terrain_type: str
    terrain_confidence: float = 1.0    # 0.0~1.0, 表示 LLM 对地形判断的置信度
```

Stage2 看到 `terrain_confidence < 0.7` 时，在 system prompt 中提示 LLM 谨慎参考、必要时自己推断。

---

## 劣 4：修复轮次有限

### 根因

QualityGuardAgent 的修复轮次由 LLM 自主控制（≤3 轮），且没有注册 search_assets 工具。当资产路径不存在时，LLM 无法自行找到替代路径。

### 优化方案

**方案 A：QualityGuardAgent 注册 search_assets 工具** ★ / $$

当前 QualityGuardAgent 只注册了 `validate_scene` 和 `validate_assets` 两个工具。缺少资产搜索能力是"修不好"的主要原因——LLM 知道路径错了，但不知道正确路径是什么。

在 `quality_guard.py` 增加 `search_assets` 工具注册：

```python
# quality_guard.py — _register_tools()
@agent.tool
async def search_assets(ctx: RunContext[AgentDeps], keywords: list[str]) -> list[dict]:
    """在资产库中搜索可用的替代资产路径。"""
    from ai.tools.asset_tools import search_assets_core
    entries = search_assets_core(ctx.deps.asset_index, keywords)
    return [e.model_dump() for e in entries]
```

修复流程变为：
1. validate_assets → 发现 `/Game/Foliage/Tree_Oak` 不存在
2. LLM 调用 search_assets(["oak", "tree", "树木"]) → 找到 `/Game/Foliage/SM_Oak_Tree`
3. 替换路径 → 再校验 → 通过

这样资产路径错误的修复率可从当前的 ~40% 提升到 ~85%。

---

**方案 B：增加资产别名映射表** ★ / $$

在 `config/asset_catalog.json` 中增加 `aliases` 字段，将 LLM 常写错但实际存在的路径建立映射：

```json
{
  "aliases": {
    "/Game/Foliage/Tree_Oak": "/Game/Foliage/SM_Oak_Tree",
    "/Game/Props/House_Small": "/Game/Building/SM_House_Small_01",
    "/Game/Nature/Rock_Large": "/Game/Environment/SM_Rock_Large"
  }
}
```

在 `validate_assets_core` 中，发现缺失路径时先查别名表，如有映射则直接替换并返回 warning 而非 error：

```python
# validation_tools.py
if not mod.ue_path_to_disk(path, content_dir):
    alias = self._alias_map.get(path)
    if alias and mod.ue_path_to_disk(alias, content_dir):
        warnings.append(f"路径已自动修正: {path} → {alias}")
        continue  # 不是真的缺失
    missing.append(...)
```

---

**方案 C：扩大修复轮次上限** ★ / $

当前 3 轮限制通过 system prompt 文本指导。对于复杂场景（同时有字段错误+资产错误+类型错误），可增加到 5 轮。但增加轮次也增加 token 消耗和幻觉风险——应结合方案 A/B，让每轮修复效率更高，而非单纯增加轮次。

---

## 劣 5：知识文档维护成本

### 根因

`data/knowledge/core.md`、`height_pattern.md`、`weight_pattern.md`、`placements.md` 等 markdown 文件与 `build_scene.py` 源码**无自动化同步**。每次在 build_scene.py 新增字段、修改默认值时，需要手动更新这些文档。

### 优化方案

**方案 A：从源码自动生成字段速查表** ★★ / $$$

核心思路：解析 `build_scene.py` 中的字段读取逻辑和 `validate_scene_json.py` 中的字段校验定义，自动生成 `core.md` 中的字段速查表部分。

```
build_scene.py (源码) + validate_scene_json.py (字段注册表)
        ↓  Python 脚本解析
    field_specs.yaml (中间格式)
        ↓  Jinja2 模板渲染
    core.md (自动生成，覆盖手动维护部分)
```

实现步骤：
1. 定义字段元数据格式（字段名、类型、默认值、所属分区、说明）
2. 在 `validate_scene_json.py` 的字段注册表中增加元数据注释（如 `# @meta: "目标关卡路径"`）
3. 编写 `scripts/generate_knowledge_docs.py`，解析注册表生成 markdown
4. 在 CI/构建流程中运行，生成后 diff 检查是否有意外变更

**不覆盖整个 core.md**，只覆盖字段速查表部分（约 40% 内容）。警告规则、常见错误、使用说明等仍需手动维护。

---

**方案 B：一致性检测脚本** ★ / $

编写一个检测脚本，对比知识文档中的字段列表与 `validate_scene_json.py` 注册表中的字段列表，报告不一致项：

```python
# scripts/check_knowledge_sync.py
# 解析 core.md/height_pattern.md 中的字段列表
# 对比 validate_scene_json.py 的 SCENE_FIELDS/LANDSCAPE_FIELDS/HP_FIELDS 等
# 输出: "core.md 缺少字段 snap_to_ground" / "height_pattern.md 含已废弃字段 old_mode"
```

将此脚本加入 CI/测试流程，在每次修改 build_scene.py 后运行，及时发现知识文档的过时内容。低成本、高收益的方案。

---

## 劣 6：单模板匹配局限性

### 根因

`KnowledgePack._select_template()` 按优先级顺序遍历 `_TEMPLATE_RULES` 列表，先命中先返回。一次只能匹配一个模板，混合场景（"带河流的森林"）只能匹配到森林模板或水系模板之一，不会同时得到两者的组合。

### 优化方案

**方案 A：多模板拼接注入** ★★ / $$

将 `_select_template` 改为 `_select_templates(intent, top_k=2)`，返回最多 2 个相关模板。修改 `build_system_prompt()` 在多模板场景下注入两个模板并附带说明：

```python
# knowledge.py
def _select_templates(self, intent, top_k=2):
    templates = []
    keywords = set(str(k).lower() for k in intent.get("keywords", []))
    terrain = intent.get("terrain_type", "features")

    for filename, match_kw, match_terrain in self._TEMPLATE_RULES:
        # ... 匹配逻辑同上 ...
        if matched:
            json_str = self._try_load_template(filename)
            if json_str:
                templates.append((filename, json_str))
                if len(templates) >= top_k:
                    break
    return templates
```

注入时区分"主模板"（最佳匹配）和"参考模板"（辅助匹配）：

```
=== 主模板（地形结构以此为准）: template_p10_forest.json ===
{forest_template_json}

=== 参考模板（水系部分参考此处）: template_p15_water_river.json ===
请参考本模板中的 rivers[] 和 water 配置来添加河流元素。
{water_template_json}
```

LLM 以主模板为骨架，从参考模板中提取特定部分组合。对于 P2 围栏（45KB 超限被排除）这类场景，也可以降级注入部分信息而非完全排除。

---

**方案 B：模板组件化** ★★★ / $$

进一步解耦模板为独立组件：

```
templates/
├── components/
│   ├── terrain_flat.json       # 平地地形片段
│   ├── terrain_hills.json      # 山丘地形片段
│   ├── terrain_river.json      # 河流水系片段
│   ├── placement_forest.json   # 森林放置片段
│   ├── placement_village.json  # 村落放置片段
│   └── lighting_sunset.json    # 日落光照片段
└── full/                        # 当前的全量模板（向后兼容）
```

`_select_components(intent)` 按 intent 的每个维度（地形/水系/植被/放置/光照）分别选组件，然后注入 LLM：

```
=== 地形组件: terrain_hills.json ===
{hills_json}

=== 水系组件: terrain_river.json ===
{river_json}

=== 放置组件: placement_forest.json ===
{forest_json}
```

LLM 自行合并这些片段。挑战在于组件之间的协调（如河流的 height_pattern 和山丘的 height_pattern 如何融合），但这正是 LLM 擅长的事——在给定多个参考片段后进行创造性组合。

实施难度大（需重构模板体系），但能根本性解决混合场景匹配问题。

---

## 劣 7：经验检索精度

### 根因

1. `ExperienceBank.search_by_keywords()` 只用关键词匹配（无地形类型过滤）
2. `ExperienceRetriever.retrieve()` 权重固定（关键词 65% / 时效 15% / 可靠性 20%），不随场景调整
3. Jaccard 相似度对近义词/同义词无效（"村庄"≠"村落"）

### 优化方案

**方案 A：search_by_keywords 增加 terrain_type 过滤** ★ / $$

当前 `search_by_keywords` 只接受 keywords，不接收 terrain_type。修改检索接口，让相同关键词但不同地形类型的经验能被区分：

```python
# experience_bank.py
def search_by_intent(self, keywords, terrain_type):
    """同时按关键词和地形类型检索，提高召回精度"""
    # 先按关键词检索，再按 terrain_type 过滤（或加分）
    candidates = self.search_by_keywords(keywords)
    scored = []
    for exp in candidates:
        score = self._keyword_match_score(keywords, exp)
        # 地形类型加分
        if exp["intent"].get("terrain_type") == terrain_type:
            score *= 1.3   # 相同地形+30%
        scored.append((score, exp))
    scored.sort(key=lambda x: -x[0])
    return [exp for _, exp in scored]
```

---

**方案 B：动态权重调整** ★★ / $

在 `ExperienceRetriever` 中根据场景特征动态调整权重：

| 场景特征 | 权重调整 |
|----------|----------|
| 意图是常见场景（forest/village） | 关键词权重↑（经验库中有大量相似案例） |
| 意图是罕见场景（karst/gully） | 关键词权重↓，地形权重↑（关键词匹配可能不准） |
| 经验库 size < 50 | 降 MMR 阈值（候选少时不需多样性重排） |

```python
# retriever.py
def retrieve(self, intent, top_k=3):
    exp_count = self._bank.count()
    terrain = intent.get("terrain_type", "flat")

    # 动态权重
    if terrain in ("karst", "gully", "terraced"):
        kw_weight, diver_weight = 0.45, 0.05  # 稀有地形: 降低关键词权重
    elif exp_count < 50:
        kw_weight, diver_weight = 0.70, 0.05  # 候选少: 降多样性权重
    else:
        kw_weight, diver_weight = WEIGHT_KEYWORD_SIM, WEIGHT_DIVERSITY
    # ...
```

---

**方案 C：同义词扩展** ★ / $

在检索前对 keywords 做同义词扩展：

```python
# 同义词映射（可配置）
_SYNONYMS = {
    "村庄": ["村落", "乡村", "农村", "village"],
    "森林": ["树林", "林地", "forest", "wood"],
    "河流": ["河", "溪流", "river", "stream"],
    "山丘": ["山坡", "高地", "hill", "mountain"],
    "草地": ["草原", "草坪", "grass", "meadow"],
}
```

```python
def search_by_keywords(self, keywords):
    expanded = list(keywords)
    for kw in keywords:
        expanded.extend(self._synonyms.get(kw, []))
    # ... 用 expanded 列表检索 ...
```

---

**方案 D：使用质量评分做检索后过滤** ★ / $

当前检索忽略经验的 success_count / fail_count。可以在返回结果后过滤低质量经验：

```python
# 检索后过滤: 排除 fail_count > success_count 的经验
filtered = [e for e in results
            if e.get("fail_count", 0) <= e.get("success_count", 0)]
```

---

## 劣 8：上下文窗口与 JSON 大小限制

### 根因

1. 模板注入大小上限硬编码 25KB（`_MAX_TEMPLATE_BYTES`），超过则完全排除
2. 大规模场景（1km 全地形 + 多种 placement）的系统 prompt 可能超过 LLM context window
3. 当前无 JSON 压缩或分治机制

### 优化方案

**方案 A：模板智能裁剪** ★★ / $$$

将 25KB 硬上限改为智能裁剪——超过阈值的模板不排除，而是裁剪到合适大小：

```python
# knowledge.py
_MAX_TEMPLATE_BYTES = 25000
_MIN_TEMPLATE_BYTES = 5000    # 保留最小骨架

def _try_load_template(self, filename):
    # ... 文件读取 ...
    if len(content) > self._MAX_TEMPLATE_BYTES:
        # 尝试裁剪: 保留 landscape + 1个 placement + lighting/weather 结构
        # 移除过长的重复实例列表(instances[] 数组)
        content = self._trim_template(content)
        if len(content) < self._MIN_TEMPLATE_BYTES:
            return None  # 裁完太小, 放弃
    return content

def _trim_template(self, json_str):
    """裁剪模板: 保留结构骨架, 截断过长的重复数组"""
    import json
    data = json.loads(json_str)
    # 对 placements 中 over-实例化的条目做截断(保留前5个实例)
    for p in data.get("placements", []):
        if p.get("instances") and len(p["instances"]) > 5:
            p["instances"] = p["instances"][:5]
            p["_note"] = f"...(原始{orig_count}个实例, 此处截断为5个作为参考)"
    # 对 height_pattern 中 over-detailed 的数组做截断
    # ...
    return json.dumps(data, ensure_ascii=False)
```

这样 P2 围栏（45KB，150 个实例）可以被裁剪为 ~8KB（5 个实例的参考骨架），LLM 仍然可以学习围栏的 placement 结构和网格参数，意义远大于完全排除。

---

**方案 B：分治生成（Chunked Generation）** ★★★ / $$

将 Stage2 拆分为子阶段，每次生成场景 JSON 的一部分：

```
Stage 2a: 生成 scene + landscape + height_pattern（地形骨架）
    ↓ JSON 骨架
Stage 2b: 在骨架上生成 placements[]（放置填充）
    ↓ 完整 JSON
Stage 2c: 生成 lighting + weather（环境收尾）
```

每次只注入与该子阶段相关的知识文档（Stage 2a 只注入 height_pattern.md，Stage 2b 只注入 placements.md 和资产路径），从而大幅缩减单次 system prompt 大小。

挑战：
- 需要 LLM 理解"骨架"概念并在其上增量构建（需要精心设计 system prompt）
- 增加了 2 次额外的 LLM 调用（延迟换 token）
- placement 的 location 需要基于 landscape 的尺寸计算（跨阶段协调）

---

**方案 C：JSON 注释剥离注入** ★ / $

在注入模板和知识文档前，剥离注释（`_note` 字段、`//...` 注释）：

```python
def _strip_comments(json_str):
    """剥离 JSON 中的 _note 字段和注释，减少注入体积"""
    import json
    data = json.loads(json_str)

    def _strip(obj):
        if isinstance(obj, dict):
            obj.pop("_note", None)
            for v in obj.values():
                _strip(v)
        elif isinstance(obj, list):
            for v in obj:
                _strip(v)

    _strip(data)
    return json.dumps(data, ensure_ascii=False)
```

注释在 JSON 中占 5-15% 体积，剥离后可以多注入部分信息。

---

## 劣 9：平台耦合

### 根因

1. 默认 LLM 配置硬编码阿里云百炼 API（`glm-5.2`）
2. `AgentBase` 直接使用 `OpenAIChatModel` + `OpenAIProvider`（强绑定 OpenAI 兼容协议）
3. function calling + structured output 功能强依赖模型能力

### 优化方案

**方案 A：模型能力探测与降级** ★★ / $$

在 `AgentBase.__init__` 中增加模型能力探测，根据探测结果自动调整行为：

```python
# base.py
class AgentBase:
    def __init__(self, ...):
        # 探测模型能力
        self._capabilities = self._probe_model_capabilities()

    def _probe_model_capabilities(self):
        """探测模型是否支持 function calling 和 structured output"""
        # 1. 尝试注册一个测试 tool 并调用
        # 2. 检查 output_type 是否能正常解析
        # 3. 返回能力标志位
        return {
            "supports_function_calling": True,
            "supports_structured_output": True,
            "max_context_tokens": 128000,
        }
```

不支持 function calling 的模型降级为"纯文本生成 + Python 后解析"模式。不支持 structured output 的模型降级为"文本输出 + extract_json() 提取"模式。

---

**方案 B：模型配置模板** ★ / $

提供预置的模型配置模板，降低用户配置门槛：

```json
// config/model_presets.json
{
  "aliyun_bailian_glm52": {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "models": {
      "default": "glm-5.2",
      "fast": "qwen-turbo"
    }
  },
  "openai": {
    "base_url": "https://api.openai.com/v1",
    "models": {
      "default": "gpt-4o",
      "fast": "gpt-4o-mini"
    }
  },
  "deepseek": {
    "base_url": "https://api.deepseek.com/v1",
    "models": {
      "default": "deepseek-chat"
    }
  },
  "ollama_local": {
    "base_url": "http://localhost:11434/v1",
    "models": {
      "default": "qwen2.5:14b",
      "fast": "qwen2.5:7b"
    }
  }
}
```

用户只需在配置中选择预设名，无需手动填写 base_url 和 model 字段。GUI 设置对话框提供下拉选择。

---

**方案 C：PydanticAI Provider 适配层** ★ / $

当前的 `AgentBase._create_model()` 直接创建 `OpenAIProvider`。包装一个工厂函数，根据配置中的 `provider` 字段选择：

```python
# base.py
def _create_model(self):
    provider_type = self._config.get("llm_provider", "openai_compatible")
    if provider_type == "openai_compatible":
        provider = OpenAIProvider(api_key=self._api_key, base_url=self._base_url)
    elif provider_type == "azure":
        provider = AzureOpenAIProvider(...)
    # 等等
    return OpenAIChatModel(self._model_name, provider=provider)
```

---

## 优化优先级排序

按 **收益/成本比** 从高到低：

| 优先级 | 方案 | 收益 | 难度 | 说明 | 状态 |
|--------|------|------|------|------|------|
| P0 🔴 | 劣 4-A：QualityGuard 注册 search_assets | $$$ | ★ | 立即提升修复成功率 ~45%→~85% | ✅ 已实现 v2.8.0 |
| P0 🔴 | 劣 8-A：模板智能裁剪 | $$$ | ★★ | P2 围栏等大模板不再被排除 | ✅ 已实现 v2.8.0 |
| P1 🟡 | 劣 1-A：分级模型策略 | $$$ | ★ | Stage1/3 换小模型，总耗时省 30% | ✅ 已实现 v2.8.0 |
| P1 🟡 | 劣 3-A：语义一致性校验规则 | $$ | ★ | warning 不阻塞，帮助发现问题 | ✅ 已实现 v2.8.0 |
| P1 🟡 | 劣 5-B：一致性检测脚本 | $$ | ★ | 低成本防知识文档过时 | ✅ 已实现 v2.8.0 |
| P2 🟢 | 劣 7-A：search_by_intent 地形过滤 | $$ | ★★ | 提高经验检索精度 | ⬜ 待实施 |
| P2 🟢 | 劣 2-A：Blueprint 增加 reasoning 字段 | $$ | ★ | 减少阶段间信息损失 | ⬜ 待实施 |
| P2 🟢 | 劣 6-A：多模板拼接注入 | $$ | ★★ | 支撑混合场景生成 | ⬜ 待实施 |
| P2 🟢 | 劣 4-B：资产别名映射表 | $$ | ★ | 自动修正常见路径错误 | ⬜ 待实施 |
| P3 ⚪ | 劣 7-B：动态权重调整 | $ | ★★ | 需要积累足够经验数据后才有意义 | ⬜ 待实施 |
| P3 ⚪ | 劣 9-A：模型能力探测与降级 | $ | ★★ | 用户群扩大后才需要 | ⬜ 待实施 |
| P3 ⚪ | 劣 8-B：分治生成 | $$ | ★★★ | 架构改动大，优先尝试其他方案 | ⬜ 待实施 |
| 远期 | 劣 6-B：模板组件化 | $$$ | ★★★ | 理想方案，需模板体系统一重构 | ⬜ 待实施 |
| 远期 | 劣 5-A：从源码自动生成知识文档 | $$$ | ★★ | 投入大，先用手工维护+检测脚本 | ⬜ 待实施 |

---

## 建议实施路线

**第一期（立即可做，1-2 天）**：P0 两项 + P1 三项
- QualityGuard 加 search_assets 工具
- 模板智能裁剪
- 分级模型策略
- 语义一致性 warning
- 知识文档一致性检测脚本

**第二期（1 周）**：P2 四项
- 经验检索增加地形过滤
- Blueprint 增加 reasoning 字段
- 多模板拼接注入
- 资产别名映射

**第三期（按需）**：P3 及远期
- 动态权重、模型探测、分治生成、模板组件化等

---

*文档版本: 1.0 | 日期: 2026-09-13 | 关联: multi_agent_pipeline_analysis.md*