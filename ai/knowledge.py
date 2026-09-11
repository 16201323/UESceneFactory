"""知识包构建器：分层组装 system prompt。
L1 核心知识(~3KB, 始终注入) + L2 模式文档(按意图选择) + L2.5 模板标杆(按意图匹配)
+ L3 资产路径 + L4 经验 few-shot
"""
import os


class KnowledgePack:
    # 模板注入大小上限(字节): 超过此值的模板不注入 system prompt, 避免撑爆 token 预算
    # P2围栏(45KB)由脚本生成含150个实例, 过大且不适合 LLM 模仿, 排除
    _MAX_TEMPLATE_BYTES = 25000

    # 模板匹配规则: (模板文件名, 匹配关键词列表, 匹配地形类型列表)
    # 按优先级排序: 特定地形模式 > 特定资产关键词 > 水系 > 默认全地形
    _TEMPLATE_RULES = [
        # 特定地形模式优先匹配
        ("template_p12_terraced.json", ["梯田", "terraced", "台阶"], ["terraced"]),
        ("template_p13_karst.json", ["喀斯特", "karst", "峰林"], ["karst"]),
        ("template_p14_gully.json", ["沟壑", "gully", "黄土"], ["gully"]),
        # 特定资产/场景关键词
        ("template_p1_heliport.json", ["停机坪", "直升机", "heliport"], []),
        ("template_p5_pv_solar.json", ["光伏", "太阳能", "solar", "pv"], []),
        ("template_p7_comm_tower.json", ["通信塔", "基站", "telecom", "comm"], []),
        ("template_p8_hv_tower.json", ["高压", "电塔", "hv_tower", "power_tower"], []),
        ("template_p10_forest.json", ["森林", "树林", "forest", "tree"], []),
        ("template_p16_village.json", ["村落", "村庄", "房屋", "village", "house"], []),
        # 水系场景
        ("template_p15_water_river.json", ["河流", "水系", "river", "water"], []),
        # 默认: 全地形综合场景(推荐起点, 含山丘/河流/道路/森林/麦田/岩石)
        ("template_p11_all_terrain_realistic.json", [], ["features", "hill", "ridge", "noise", "hill_ridge", "flat"]),
    ]

    def __init__(self, knowledge_dir="data/knowledge", templates_dir=None):
        self._dir = knowledge_dir
        self._core = self._read("core.md")
        self._cache = {}  # 模式文档缓存
        # 模板库: 注入高质量标杆 JSON 作为 few-shot 示例, 大幅提升初次生成质量
        self._templates_dir = templates_dir
        self._template_cache = {}  # 文件名 -> json_str 或 None(懒加载, 含负缓存)

    def _read(self, name):
        path = os.path.join(self._dir, name)
        # 检查文件是否存在，给出友好的错误提示
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"知识文件不存在: {path}\n"
                f"请确保 data/knowledge/ 目录包含所需 .md 文件"
            )
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _get_pattern(self, name):
        if name not in self._cache:
            self._cache[name] = self._read(name)
        return self._cache[name]

    def get_pattern(self, name):
        """公共接口：获取模式文档内容（带缓存）。

        供外部工具调用，避免直接访问 _get_pattern 私有方法。
        """
        return self._get_pattern(name)

    def select_template(self, intent):
        """公共接口：按意图匹配模板，返回 (文件名, json_str) 或 None。

        供外部工具调用，避免直接访问 _select_template 私有方法。
        """
        return self._select_template(intent)

    def _try_load_template(self, filename):
        """懒加载模板 JSON 文件, 超大小上限或不存在时返回 None

        含负缓存: 首次加载失败后缓存 None, 避免重复磁盘 IO
        """
        if filename in self._template_cache:
            return self._template_cache[filename]
        if not self._templates_dir:
            return None
        path = os.path.join(self._templates_dir, filename)
        if not os.path.isfile(path):
            self._template_cache[filename] = None
            return None
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # 超过大小上限的模板不注入(如 P2 围栏 45KB), 避免撑爆 system prompt token 预算
        if len(content) > self._MAX_TEMPLATE_BYTES:
            self._template_cache[filename] = None
            return None
        self._template_cache[filename] = content
        return content

    def _select_template(self, intent):
        """按 intent 关键词和地形类型匹配最佳模板, 返回 (文件名, json_str) 或 None

        匹配优先级: 特定地形模式 > 特定资产关键词 > 水系 > 默认全地形综合场景
        """
        keywords = set(str(k).lower() for k in intent.get("keywords", []))
        terrain = intent.get("terrain_type", "features")

        for filename, match_kw, match_terrain in self._TEMPLATE_RULES:
            matched = False
            # 地形类型匹配
            if match_terrain and terrain in match_terrain:
                matched = True
            # 关键词匹配(任一关键词命中即可)
            if not matched and match_kw:
                if any(kw.lower() in keywords for kw in match_kw):
                    matched = True
            # 默认规则(空关键词+空地形列表)始终匹配, 作为兜底
            if not matched and not match_kw and not match_terrain:
                matched = True
            if matched:
                json_str = self._try_load_template(filename)
                if json_str:
                    return (filename, json_str)
        return None

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

        # 始终注入 examples.md（帮助 LLM 理解完整结构）
        parts.append(self._get_pattern("examples.md"))

        # L2.5: 按意图匹配并注入高质量模板作为 few-shot 标杆
        # 这是提升初次生成质量的关键: AI 拿到一个已验证的完整 JSON 可模仿,
        # 而非仅靠字段表盲写
        template = self._select_template(intent)
        if template:
            name, json_str = template
            parts.append(
                f"=== 参考模板: {name} ===\n"
                f"以下是一个已在 UE5 中验证通过的高质量场景 JSON, "
                f"请参考其结构组织、参数取值范围和 _note 注释风格来生成你的场景:\n"
                f"{json_str}"
            )

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
