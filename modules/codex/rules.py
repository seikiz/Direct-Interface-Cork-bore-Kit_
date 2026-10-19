# -*- coding: utf-8 -*-
"""modules/codex/rules.py —— 行类型 / 条件求值 / 选项过滤 / HTML 消毒 / 剧本校验

搬家来源：`codex_core.py` 的 `_STEP_KINDS` / `step_kind` / `_cond_cmp` / `_CMP_RE` /
`_read_aff` / `_to_num` / `evaluate_condition` / `filter_choices` / 三条 HTML 正则 /
`sanitize_html` / `validate_codex`，**判定规则与报错文案一字未改**。

这一层是"剧本能不能跑"的唯一真相：条件语法（`{"aff": ">=85"}` / `all` / `any` /
`flags` / `status`）、选项裁剪、以及校验器给出的 issues 列表都在这里。
它只依赖 stdlib，不碰文件系统 —— 所以能被自检直接喂坏输入。
"""

import re


_STEP_KINDS = ("say", "note", "show", "hide", "bg", "bgm", "sfx", "effect",
               "action", "wait", "setflag", "roll", "choice", "jump", "end")


def step_kind(ln):
    """推断一条线的表现类型（用于编辑器/规整；播放器按字段分发，兼容旧剧本）"""
    if not isinstance(ln, dict):
        return "note"
    if str(ln.get("kind") or "").strip() in _STEP_KINDS:
        return str(ln["kind"]).strip()
    # 兼容旧格式：<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌按字段唯一定类
    present = [k for k in ("text", "note", "choice", "jump", "end", "action")]
    hits = [k for k in present if k in ln]
    if "choice" in ln:
        return "choice"
    if "jump" in ln:
        return "jump"
    if "end" in ln:
        return "end"
    if "action" in ln:
        return "action"
    # 文本/note 优先；纯表现步骤按字段定类（bg/bgm/effect/wait 等）；否则 action
    if "text" in ln:
        return "say"
    if "note" in ln:
        return "note"
    for k in ("show", "hide", "bg", "bgm", "sfx", "effect", "wait", "setflag", "roll"):
        if k in ln:
            return k
    return "action"


def _cond_cmp(op, a, b):
    try:
        if op == ">=":
            return a >= b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        if op == "<":
            return a < b
        if op == "!=":
            return a != b
        return a == b  # == / =
    except (TypeError, ValueError):
        return False


_CMP_RE = re.compile(r"^\s*(>=|<=|>|<|!=|==|=)\s*(-?\d+(?:\.\d+)?)\s*$")


def _read_aff(st):
    """从机制状态里取好感度的值；找不到返回 None"""
    if not isinstance(st, dict):
        return None
    # 直接字段 / 嵌套 mechanism_state
    v = st.get("affection", st.get("aff"))
    if v is None and isinstance(st.get("mechanism_state"), dict):
        v = st["mechanism_state"].get("affection", st["mechanism_state"].get("aff"))
    return _to_num(v) if v is not None else None


def _to_num(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except (TypeError, ValueError):
            return None
    return None


def evaluate_condition(state, cond):
    """数值条件求值（广播「GAL 分支靠数值」）。

    cond 支持：
      {"aff": ">=85"} / {"aff": 85}       好感度（字符串可带比较符）
      {"status": {"心情": "开心"}}        状态字段精确匹配
      {"flags": ["x", "!y"]}              存在 / 缺失 flag（! 前缀=必须缺失）
      {"all": [c1,c2]} / {"any": [c1,c2]}  组合
    返回 True/False。
    · cond 为空/None → 恒真。
    · state 为 None（作者/预览未注入运行时状态）→ 恒真（不误隐藏选项）。
    · state 有值但缺字段 → 相应条件不命中（False）。"""
    if cond is None or cond is True or cond == {}:
        return True
    if not isinstance(cond, dict):
        return True
    if state is None:
        return True  # 预览/作者模式：不隐藏
    if "all" in cond and isinstance(cond["all"], list):
        return all(evaluate_condition(state, c) for c in cond["all"])
    if "any" in cond and isinstance(cond["any"], list):
        return any(evaluate_condition(state, c) for c in cond["any"])
    if "aff" in cond:
        t = cond["aff"]
        if isinstance(t, str):
            m = _CMP_RE.match(t)
            if m:
                return _cond_cmp(m.group(1), _read_aff(state), float(m.group(2)))
            num = _to_num(t)
            return _cond_cmp("==", _read_aff(state), num) if num is not None else True
        num = _to_num(t)
        return _cond_cmp("==", _read_aff(state), num) if num is not None else True
    if "status" in cond and isinstance(cond["status"], dict):
        st = state.get("status") if isinstance(state, dict) else None
        if not isinstance(st, dict):
            return False
        return all((_to_num(st.get(k)) if isinstance(st.get(k), (int, float)) else st.get(k)) == v
                   for k, v in cond["status"].items())
    if "flags" in cond and isinstance(cond["flags"], list):
        flags = state.get("flags") if isinstance(state, dict) else {}
        if isinstance(flags, dict):
            def has(k):
                return bool(flags.get(k))
        elif isinstance(flags, (list, set, tuple)):
            def has(k):
                return k in flags
        else:
            def has(k):
                return False
        for f in cond["flags"]:
            fs = str(f)
            must_be_false = fs.startswith("!")
            key = fs[1:] if must_be_false else fs
            if has(key) == must_be_false:
                return False
        return True
    return True


def filter_choices(items, state):
    """过滤选项：丢弃 if 条件不满足的项（作者预览：无运行时状态时不丢弃）"""
    if not isinstance(items, list):
        return items
    out = []
    for it in items:
        if isinstance(it, dict) and "if" in it and not evaluate_condition(state, it.get("if")):
            continue
        out.append(it)
    return out


_SCRIPT_RE = re.compile(r"<\s*script\b[^>]*>[\s\S]*?<\s*/\s*script\s*>", re.I)
_EMBED_TAG_RE = re.compile(r"<\s*/?\s*(iframe|object|embed|form|base|meta|link|style)\b[^>]*>", re.I)
_HANDLER_RE = re.compile(r"\son[a-zA-Z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)


def sanitize_html(html):
    """基础 HTML 注入防护：移除 <script> 块、可嵌入危险标签（iframe/object/embed/form/base），
    移除所有事件处理属性（onclick/onload 等），并把 javascript:/vbscript: 协议中立化为 blocked:。
    返回清洗后的字符串。"""
    if not isinstance(html, str):
        return ""
    s = _SCRIPT_RE.sub("", html)
    s = _EMBED_TAG_RE.sub("", s)
    s = re.sub(r"(?i)(javascript|vbscript)\s*:", "blocked:", s)
    s = _HANDLER_RE.sub("", s)
    return s


def validate_codex(data):
    """校验剧本 dict。返回 (ok, issues)"""
    issues = []
    if not isinstance(data, dict):
        return False, ["剧本必须是 JSON 对象"]
    name = str(data.get("name") or "").strip()
    if not name:
        issues.append("缺少 name（剧本名）")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        issues.append("缺少 scenes（至少一个场景）")
        return bool(not issues), issues
    ids = set()
    seen_dup = set()
    for i, sc in enumerate(scenes):
        if isinstance(sc, dict) and str(sc.get("id") or "").strip():
            sid = str(sc["id"]).strip()
            if sid in ids:
                seen_dup.add(sid)
            ids.add(sid)
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            issues.append(f"scenes[{i}] 不是对象")
            continue
        sid = str(sc.get("id") or "").strip()
        if not sid:
            issues.append(f"scenes[{i}] 缺少 id")
        elif sid in seen_dup:
            issues.append(f"场景 id 重复: {sid}")
        lines = sc.get("lines")
        if not isinstance(lines, list) or not lines:
            issues.append(f"场景 {sid or i} 缺少 lines")
            continue
        for j, ln in enumerate(lines):
            if not isinstance(ln, dict):
                issues.append(f"场景 {sid or i} lines[{j}] 不是对象")
                continue
            # 立绘多位置：sprites 数组 [{file, pos}]（pos: left/center/right）
            if "sprites" in ln:
                sl = ln["sprites"]
                if not isinstance(sl, list) or not sl:
                    issues.append(f"场景 {sid or i} lines[{j}] sprites 必须是非空数组")
                else:
                    for k, s in enumerate(sl):
                        if not isinstance(s, dict) or not str(s.get("file") or "").strip():
                            issues.append(f"场景 {sid or i} lines[{j}] sprites[{k}] 缺 file")
                        p = str(s.get("pos") or "center")
                        if p not in ("left", "center", "right"):
                            issues.append(f"场景 {sid or i} lines[{j}] sprites[{k}] pos 必须是 left/center/right: {p}")
            if "choice" in ln:
                opts = ln["choice"]
                if not isinstance(opts, list) or not opts:
                    issues.append(f"场景 {sid or i} lines[{j}] choice 为空")
                else:
                    for k, o in enumerate(opts):
                        if not isinstance(o, dict) or not str(o.get("text") or "").strip():
                            issues.append(f"场景 {sid or i} lines[{j}] choice[{k}] 缺 text")
                        g = str(o.get("goto") or "").strip()
                        if g and g not in ids:
                            issues.append(f"场景 {sid or i} lines[{j}] choice[{k}] goto 指向不存在的场景: {g}")
                        if "if" in o and o.get("if") is not None and not isinstance(o.get("if"), dict):
                            issues.append(f"场景 {sid or i} lines[{j}] choice[{k}] if 必须是对象或省略")
            if "jump" in ln:
                g = str(ln["jump"] or "").strip()
                if g and g not in ids:
                    issues.append(f"场景 {sid or i} lines[{j}] jump 指向不存在的场景: {g}")
            if not any(k in ln for k in ("text", "choice", "jump", "action", "end", "note")) \
                    and not (str(ln.get("kind") or "") in _STEP_KINDS
                             or any(k in ln for k in ("show", "hide", "bg", "bgm", "sfx", "effect", "wait", "setflag", "roll"))):
                issues.append(f"场景 {sid or i} lines[{j}] 缺少有效行类型")
    return bool(not issues), issues
