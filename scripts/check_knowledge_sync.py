# -*- coding: utf-8 -*-
"""
check_knowledge_sync.py - 知识文档与字段注册表一致性检测

对比 data/knowledge/*.md 文档中提及的字段名 与 validate_scene_json.py 中的
字段注册表(*_FIELDS / *_KEYS), 报告两类不一致:

  1. 注册表有但文档无 → 字段可能漏文档(新增字段忘了写文档)
  2. 文档有但注册表无 → 文档可能过期(字段已从注册表移除或改名)

用法:
    python check_knowledge_sync.py

退出码: 0=无不一致  1=存在不一致(需人工审查)
"""

import os
import re
import sys

# 确保能导入同目录的 validate_scene_json
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# 导入字段注册表(模块级 dict 常量, key 即字段名)
import validate_scene_json as vsj

# 知识文档目录(相对脚本上溯两级: scripts/ -> UESceneFactory/ -> data/knowledge/)
_KNOWLEDGE_DIR = os.path.normpath(
    os.path.join(_SCRIPT_DIR, os.pardir, "data", "knowledge")
)

# 全文 snake_case token 正则: 匹配小写字母开头、含字母/数字/下划线的标识符
# 用于检测注册表字段是否在文档任意位置被提及(表格/正文/代码块均算)
_TOKEN_RE = re.compile(r'\b([a-z][a-z0-9_]*[a-z0-9])\b')
# 反引号包裹的 token 正则: 仅匹配 `field_name` 形式, 噪声更小
# 用于检测文档中"明确标注为字段引用"但注册表无对应项的情况
_BACKTICK_RE = re.compile(r'`([a-z][a-z0-9_]*[a-z0-9])`')

# 收集所有注册表 dict 的 (注册表名, 字段集合)
def _collect_registries():
    """扫描 vsj 模块中所有以 _FIELDS 或 _KEYS 结尾的大写常量, 返回 [(name, set)]"""
    registries = []
    for attr in dir(vsj):
        if attr.startswith("_"):
            continue
        val = getattr(vsj, attr)
        # 只收集 dict 类型且 key 为 str 的常量(即字段注册表)
        if isinstance(val, dict) and all(isinstance(k, str) for k in val):
            registries.append((attr, set(val.keys())))
    return registries

# 收集某 .md 文件中出现的全部 snake_case token(用于漏文档检测)
def _scan_md_all_tokens(md_path):
    """返回该 md 文件全文中所有 snake_case token 集合"""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    return set(_TOKEN_RE.findall(text))

# 收集某 .md 文件中反引号包裹的 token(用于额外字段检测, 噪声更小)
def _scan_md_backtick_tokens(md_path):
    """返回该 md 文件中所有反引号包裹的 snake_case token 集合"""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    return set(_BACKTICK_RE.findall(text))

# 主检测流程
def main():
    registries = _collect_registries()
    # 全注册表字段并集
    all_registry_fields = set()
    for _, fields in registries:
        all_registry_fields |= fields

    # 扫描知识文档: 全文 token 用于漏文档检测, 反引号 token 用于额外字段检测
    all_doc_tokens = set()        # 全文 token 并集(检测注册表字段是否被提及)
    all_backtick_tokens = set()  # 反引号 token 并集(检测文档明确标注的字段引用)
    doc_map = {}                  # backtick_token -> [文件名]
    if not os.path.isdir(_KNOWLEDGE_DIR):
        print("错误: 知识文档目录不存在: %s" % _KNOWLEDGE_DIR)
        return 1
    for fname in sorted(os.listdir(_KNOWLEDGE_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(_KNOWLEDGE_DIR, fname)
        all_doc_tokens |= _scan_md_all_tokens(fpath)
        bt = _scan_md_backtick_tokens(fpath)
        all_backtick_tokens |= bt
        for fld in bt:
            doc_map.setdefault(fld, []).append(fname)

    # 检测1: 注册表有但文档全文无(漏文档) — 用全文 token 检测
    missing_in_docs = all_registry_fields - all_doc_tokens
    # 检测2: 文档反引号标注有但注册表无(过期/额外) — 仅用反引号 token 减少噪声
    _NOISE = {"json", "true", "false", "null", "none", "self", "cls",
              "int", "float", "str", "bool", "list", "dict",
              "game", "ue5", "md", "py", "cpp", "uasset"}
    extra_in_docs = {t for t in (all_backtick_tokens - all_registry_fields)
                     if t not in _NOISE and len(t) >= 3}

    has_issue = False

    # 报告1: 漏文档字段(按注册表分组)
    if missing_in_docs:
        has_issue = True
        print("=" * 60)
        print("【漏文档】注册表有但知识文档无(可能需补充文档):")
        for reg_name, reg_fields in registries:
            missing = reg_fields & missing_in_docs
            if missing:
                print("  %s:" % reg_name)
                for fld in sorted(missing):
                    print("    - %s" % fld)
    else:
        print("✓ 所有注册表字段均已在文档中提及")

    # 报告2: 文档额外字段(可能过期)
    if extra_in_docs:
        has_issue = True
        print("=" * 60)
        print("【文档额外】文档提及但注册表无(可能过期或子字段):")
        for fld in sorted(extra_in_docs):
            files = doc_map.get(fld, [])
            print("  - %s  (见: %s)" % (fld, ", ".join(files)))
    else:
        if not missing_in_docs:
            print("✓ 文档无额外未知字段")

    print("=" * 60)
    total_reg = len(all_registry_fields)
    print("统计: 注册表字段 %d 个, 文档全文 token %d 个, 漏文档 %d 个, 额外 %d 个" % (
        total_reg, len(all_doc_tokens), len(missing_in_docs), len(extra_in_docs)))

    return 1 if has_issue else 0


if __name__ == "__main__":
    sys.exit(main())
