"""AI 工具函数：三层 JSON 提取策略。"""
import json
import re


def _close_unbalanced(snippet):
    stack = []
    in_str = False
    esc = False
    for ch in snippet:
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in '{[':
                stack.append(ch)
            elif ch in '}]':
                if stack:
                    stack.pop()
    if in_str:
        snippet += '"'
    for opener in reversed(stack):
        snippet += '}' if opener == '{' else ']'
    return snippet


def _repair_truncated(text):
    start = text.find('{')
    if start == -1:
        return None
    body = text[start:]
    cut = len(body)
    for _ in range(16):
        candidate = _close_unbalanced(body[:cut].rstrip().rstrip(','))
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        prev = max(body.rfind(',', 0, cut),
                   body.rfind('}', 0, cut),
                   body.rfind(']', 0, cut))
        if prev <= 0 or prev >= cut:
            break
        cut = prev
    return None


def extract_json(text):
    """
    四层 JSON 提取策略（兼容 JSON Mode / 代码块 / 截断响应）:
    1. 直接解析: json.loads(text) — JSON Mode 响应通常是纯 JSON
    2. 代码块提取: 从 ```json ... ``` 或 ``` ... ``` 中提取
    3. 首尾大括号: 找第一个 { 到最后一个 }，尝试解析
    4. 截断修复: 响应被 max_tokens 截断时, 回退+补齐括号 salvaging 前半部分

    返回: 解析后的 dict/list，失败时抛出 json.JSONDecodeError
    """
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    code_block_pattern = r'```(?:json)?\s*\n?(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        snippet = text[first_brace:last_brace + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            pass

    repaired = _repair_truncated(text)
    if repaired is not None:
        return repaired

    preview = text[:200].replace("\n", " ")
    raise json.JSONDecodeError(
        "无法从响应中提取 JSON (响应前200字符: %s)" % preview, text, 0)
