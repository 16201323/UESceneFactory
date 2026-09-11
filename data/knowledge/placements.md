# placements 进阶字段

> 本文件是 UE5_JSON 技能的按需参考文档（由 SKILL.md 第 4 节拆分）。公共字段（4.1）、blueprint（4.3）、group 基本字段、static（4.5）见 SKILL.md 主文件；本文件只放 instanced_grid 的 grid 子字段表与高压电塔电线连接规则。

## instanced_grid 的 grid 子字段

二选一：grid 自动生成 或 instances 显式数组。

grid 子字段（pattern="circle" 走圆环，缺省走矩形）：

| 子字段 | 类型 | 模式 | 默认 | 说明 |
|--------|------|------|------|------|
| pattern | string | 两者 | "" | "circle" 圆环 / 缺省矩形 |
| count | int | circle | — | 实例数 |
| radius | float | circle | 1000 | 半径 |
| center | [x,y,z] | circle | [0,0,0] | 圆心 |
| face_center | bool | circle | true | 朝向圆心 |
| yaw_offset | float | circle | 90 | 偏航补偿 |
| z_offset | float | circle | 0 | Z 偏移 |
| pitch | float | 两者 | 0 | 俯仰角 |
| scale_min | [x,y,z] | 两者 | [1,1,1] | 最小缩放 |
| scale_max | [x,y,z] | 两者 | [1,1,1] | 最大缩放 |
| rows | int | 矩形 | — | 行数 |
| cols | int | 矩形 | — | 列数 |
| origin | [x,y,z] | 矩形 | [0,0,0] | 起点 |
| spacing | [x,y,z] | 矩形 | [100,100,0] | 间距 |
| jitter | float | 矩形 | 0 | 抖动量 |
| random_yaw | bool | 矩形 | false | 随机偏航 |
| cull_start | float | 两者 | **必填**(植物) | 每实例距离剔除起始(世界cm). 实例距相机<start完全可见. 树木推荐20000(200m) |
| cull_end | float | 两者 | **必填**(植物) | 每实例距离剔除结束(世界cm). start~end渐隐, >end不渲染GPU. 须与cull_start同时给, 仅instanced_grid(HISM)生效. 树木推荐50000(500m) |

> ⚠️ **植物必填**：`cull_start`/`cull_end` 设 HISM 的 `InstanceStartCullDistance`/`InstanceEndCullDistance`。森林等大批量实例, 远处不画只画近处, 大幅省 GPU。**缺省不剔除(向后兼容)**——不写则无任何距离剔除，远处实例全部渲染消耗GPU。树木推荐 start=20000(200m)/end=50000(500m)，300m 渐隐带，覆盖大部分航拍高度。草/灌木等小型植物可设 start=15000(150m)/end=30000(300m)。生成树/草/灌木等植物的 instanced_grid 时**必须包含 cull_start/cull_end**，不可省略。仅 `instanced_grid` 生效, `static` grid 不支持(HISM 独有属性)。

instances 子字段：数组，每项 {location, rotation, scale}。

## 高压电塔电线连接规则（实测验证）

高压电塔组合资产（`asset_prefix=/Game/HighVoltageTower/high_voltage_tower_wired/StaticMeshes/Object_`、`count=20`）的电线默认沿塔身方向延伸。两座电塔若同朝向放置，电线同向平行、永不相交；要让一座塔引出的电线落在另一座塔上，须按以下规则布置。

**核心参数（经编辑器手动调试确认）：**

| 参数 | Tower A | Tower B | 说明 |
|------|---------|---------|------|
| location | [0, 1420, 0] | [0, 1500, 0] | 两塔沿 Y 轴分开，X、Z 相同 |
| rotation | [0, 0, -90] | [0, 180, -90] | B 塔 yaw+180° 镜像，电线相向 |
| scale | [0.01, 0.01, 0.01] | [0.01, 0.01, 0.01] | 缩到 1%，塔身 77.5m→77.5cm |
| skip_z_fix | true | true | P8 修复：跳过独立 Z 修正 |
| ground_assembly | true | true | P8 修复：整组贴地 |

**两塔间距 = |1500 − 1420| = 80 cm = 0.8 m**

**规则要点：**
1. **方向沿 Y 轴**：两塔仅 Y 坐标不同（X=0、Z 贴地相同），电线沿 Y 轴相向延伸并落在对方塔上
2. **B 塔 yaw 镜像 180°**：rotation 第二位（yaw）B=A+180，使 B 塔电线朝 A 塔延伸；A 塔作方向基准保持 yaw=0
3. **roll 保持 -90 + P8 三连**：两塔 roll（第三位）均为 -90，配合 skip_z_fix + ground_assembly（P8 修复值，勿改）
4. **scale 必须 0.01**：塔身原 77.5m，缩到 77.5cm 后 80cm 间距让电线端恰好相接；满尺度（scale [1,1,1]）下 80cm 间距会让塔身重叠 76m，不可用
5. **真实档距等效**：0.01 缩放下 80cm 场景距离 ≈ 80m 真实档距，落在高压输电 50–500m 合理区间

**JSON 示例（两座电塔电线相向连接）：**

```json
{"type": "group", "asset_prefix": "/Game/HighVoltageTower/high_voltage_tower_wired/StaticMeshes/Object_", "count": 20, "location": [0, 1420, 0], "rotation": [0, 0, -90], "scale": [0.01, 0.01, 0.01], "skip_z_fix": true, "ground_assembly": true},
{"type": "group", "asset_prefix": "/Game/HighVoltageTower/high_voltage_tower_wired/StaticMeshes/Object_", "count": 20, "location": [0, 1500, 0], "rotation": [0, 180, -90], "scale": [0.01, 0.01, 0.01], "skip_z_fix": true, "ground_assembly": true}
```

**反模式（避免）：**
- ❌ 两塔同 rotation（无 yaw 镜像）→ 电线同向平行，永不相交
- ❌ 两塔沿 X 轴分开 + roll-90 → 电线沿 Y 延伸、与连线方向垂直，无法相接
- ❌ 满尺度 scale [1,1,1] + 80cm 间距 → 塔身重叠 76m