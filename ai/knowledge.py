"""知识包构建器：分层组装 system prompt。
L1 核心知识(~3KB, 始终注入) + L2 模式文档(按意图选择) + L2.5 模板标杆(按意图匹配)
+ L3 资产路径 + L4 经验 few-shot
"""
import os


class KnowledgePack:
    _MAX_TEMPLATE_BYTES = 25000

    _TEMPLATE_RULES = [
        ("template_p12_terraced.json", ["梯田", "terraced", "台阶"], ["terraced"]),
        ("template_p13_karst.json", ["喀斯特", "karst", "峰林"], ["karst"]),
        ("template_p14_gully.json", ["沟壑", "gully", "黄土"], ["gully"]),
        ("template_p1_heliport.json", ["停机坪", "直升机", "heliport"], []),
        ("template_p5_pv_solar.json", ["光伏", "太阳能", "solar", "pv"], []),
        ("template_p7_comm_tower.json", ["通信塔", "基站", "telecom", "comm"], []),
        ("template_p8_hv_tower.json", ["高压", "电塔", "hv_tower", "power_tower"], []),
        ("template_p10_forest.json", ["森林", "树林", "forest", "tree"], []),
        ("template_p16_village.json", ["村落", "村庄", "房屋", "village", "house"], []),
        ("template_p15_water_river.json", ["河流", "水系", "river", "water"], []),
        ("template_p11_all_terrain_realistic.json", [], ["features", "hill", "ridge", "noise", "hill_ridge", "flat"]),
    ]

    def __init__(self, knowledge_dir="data/knowledge", templates_dir=None):
        self._dir = knowledge_dir
        self._core = self._read("core.md")
        self._cache = {}
        self._templates_dir = templates_dir
        self._template_cache = {}

    def _read(self, name):
        path = os.path.join(self._dir, name)
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

    def _try_load_template(self, filename):
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
        if len(content) > self._MAX_TEMPLATE_BYTES:
            self._template_cache[filename] = None
            return None
        self._template_cache[filename] = content
        return content

    def _select_template(self, intent):
        keywords = set(str(k).lower() for k in intent.get("keywords", []))
        terrain = intent.get("terrain_type", "features")

        for filename, match_kw, match_terrain in self._TEMPLATE_RULES:
            matched = False
            if match_terrain and terrain in match_terrain:
                matched = True
            if not matched and match_kw:
                if any(kw.lower() in keywords for kw in match_kw):
                    matched = True
            if not matched and not match_kw and not match_terrain:
                matched = True
            if matched:
                json_str = self._try_load_template(filename)
                if json_str:
                    return (filename, json_str)
        return None

    def build_system_prompt(self, intent, asset_paths, few_shots):
        parts = [self._core]

        terrain = intent.get("terrain_type", "features")
        if terrain != "flat" or intent.get("has_water") or intent.get("has_river"):
            parts.append(self._get_pattern("height_pattern.md"))
        if intent.get("has_grass") or intent.get("has_wheat"):
            parts.append(self._get_pattern("weight_pattern.md"))
        if intent.get("placements"):
            parts.append(self._get_pattern("placements.md"))
            parts.append(self._get_pattern("asset_guide.md"))

        parts.append(self._get_pattern("examples.md"))

        template = self._select_template(intent)
        if template:
            name, json_str = template
            parts.append(
                f"=== 参考模板: {name} ===\n"
                f"以下是一个已在 UE5 中验证通过的高质量场景 JSON, "
                f"请参考其结构组织、参数取值范围和 _note 注释风格来生成你的场景:\n"
                f"{json_str}"
            )

        if asset_paths:
            asset_text = "\n".join(asset_paths[:30])
            parts.append(f"可用资产路径:\n{asset_text}")

        for i, exp in enumerate(few_shots):
            parts.append(f"--- 示例{i+1} ---")
            parts.append(f"用户描述: {exp['user_desc']}")
            parts.append(f"场景 JSON:\n{exp['scene_json']}")

        return "\n\n".join(parts)
