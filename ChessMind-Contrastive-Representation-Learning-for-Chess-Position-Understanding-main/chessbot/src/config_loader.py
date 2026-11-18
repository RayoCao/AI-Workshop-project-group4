"""读 config.yaml。

为什么不直接 `import yaml`：队友机器上的 Python 不一定装了 PyYAML（课程的
requirements.txt 里只有 chess）。所以这里先试 PyYAML，装不上就用下面这个
"够用就行"的小解析器——它只认我们 config.yaml 用到的那几种写法：
缩进嵌套、`key: 值`、行内 `{a: 1, b: false}`、真/假/数字/字符串、# 注释。

两条路径解析同一份文件必须得到同样的结果，tests/test_search.py 里有对照测试。
"""

from __future__ import annotations

import os

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"
)

_TRUE = {"true", "yes", "on", "是"}
_FALSE = {"false", "no", "off", "否"}


def _strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _scalar(text):
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    low = t.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if low in ("null", "none", "~"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t


def _split_flow(body):
    """把 `a: 1, b: {x: 2}` 按顶层逗号切开（大括号里的逗号不算）。"""
    parts, depth, buf, quote = [], 0, [], None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "{[":
            depth += 1
            buf.append(ch)
        elif ch in "}]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in (s.strip() for s in parts) if p]


def _value(text):
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        inner = t[1:-1].strip()
        out = {}
        if not inner:
            return out
        for item in _split_flow(inner):
            k, _, v = item.partition(":")
            out[k.strip()] = _value(v)
        return out
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        return [] if not inner else [_value(x) for x in _split_flow(inner)]
    return _scalar(t)


def mini_yaml_load(text):
    """只认本项目 config.yaml 写法的极简 YAML 解析器。"""
    root = {}
    stack = [(-1, root)]
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        key, sep, val = body.partition(":")
        if not sep:
            raise ValueError("config.yaml 这一行看不懂：%r" % raw)
        key = key.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if val.strip() == "":
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _value(val)
    return root


def load_config(path=None):
    """读配置；PyYAML 在就用它，不在就退回 mini_yaml_load。"""
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # type: ignore
    except Exception:
        return mini_yaml_load(text)
    loaded = yaml.safe_load(text)
    return loaded or {}


def level_config(cfg, name, fallback=None):
    """取某一档的参数，缺项用默认值补齐，保证 search.py 拿到的是一份完整配置。"""
    from .search import DEFAULT_LEVELS

    name = (name or "").upper()
    merged = dict(DEFAULT_LEVELS.get(name, {}))
    merged.update((fallback or {}))
    merged.update((cfg.get("levels") or {}).get(name) or {})
    merged["name"] = name
    return merged
