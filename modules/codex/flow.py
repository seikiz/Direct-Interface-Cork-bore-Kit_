# -*- coding: utf-8 -*-
"""modules/codex/flow.py —— 条件推进与走查（试玩 / 全路径模拟）

搬家来源：`codex_core.py` 的 `cond_pass` / `_state_with` / `_flags_of` / `simulate` /
`run_path`，**状态推进与"全路径"遍历规则一字未改**。

两个用法：
    · `run_path(剧本, 选择序列)` —— 按玩家的一次选择走一遍，返回逐步轨迹（试玩/回放）；
    · `simulate(剧本)` —— 穷举所有可达状态（带上限），报"有多少结局、有没有死路"。
状态是纯 dict（flags/aff/status 都在里面），不落盘、不需要宿主。
"""

import re

from .rules import step_kind


def cond_pass(cond, state):
    """条件求值：与 JS 侧 cxCond/codexCond 同语义。

    state=None → 作者模式，条件一律视为通过（与播放器"没有机制状态时不隐藏"一致）。
    支持：{"all":[...]} {"any":[...]} {"aff":">=85"} {"status":{"k":v}} {"flags":["a","!b"]}
    """
    if cond is None or cond is True or not isinstance(cond, dict) or not cond:
        return True
    if state is None:
        return True
    st = state.get("mechanism_state") or state if isinstance(state, dict) else {}
    if cond.get("all") and isinstance(cond["all"], list):
        return all(cond_pass(c, state) for c in cond["all"])
    if cond.get("any") and isinstance(cond["any"], list):
        return any(cond_pass(c, state) for c in cond["any"])
    if "aff" in cond:
        target, op = cond["aff"], "=="
        if isinstance(target, str):
            m = re.match(r"^\s*(>=|<=|>|<|!=|==|=)?\s*(-?\d+(?:\.\d+)?)\s*$", target)
            target = m.group(2) if m else target
            op = (m.group(1) or "==") if m else "=="
        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        n, aff = num(target), num(st.get("affection"))
        if n is None or aff is None:
            return False
        return {">=": aff >= n, ">": aff > n, "<=": aff <= n, "<": aff < n,
                "!=": aff != n}.get(op, aff == n)
    if isinstance(cond.get("status"), dict):
        cur = st.get("status") or {}
        for k, q in cond["status"].items():
            v = cur.get(k)
            try:
                if float(v) == float(q):
                    continue
            except (TypeError, ValueError):
                pass
            if str(v) != str(q):
                return False
        return True
    if isinstance(cond.get("flags"), list):
        fl = st.get("flags") or {}
        for f in cond["flags"]:
            f = str(f)
            neg = f.startswith("!")
            k = f[1:] if neg else f
            present = (k in fl) if isinstance(fl, list) else bool(fl.get(k))
            if present == neg:
                return False
        return True
    return True


def _state_with(state, flags):
    """复制 state 并替换 flags（模拟里每步的 flag 变动都产生新状态，避免互相污染）"""
    base = dict(state or {})
    inner = dict(base.get("mechanism_state") or base)
    inner["flags"] = dict(flags)
    if base.get("mechanism_state"):
        base["mechanism_state"] = inner
    else:
        base = inner
    return base


def _flags_of(state):
    if not isinstance(state, dict):
        return {}
    inner = state.get("mechanism_state") or state
    return dict(inner.get("flags") or {})


def simulate(data, state=None, max_states=20000, roll_values=None):
    """无头枚举：把剧本所有可达状态走一遍（含 setflag/roll 造成的分支）。

    返回 {"ok", "endings": [文本], "states": n, "gated": [...], "cycles": bool,
          "truncated": bool, "visited_scenes": set}
    state=None 表示作者模式（条件全通过）—— 与静态体检的口径一致。
    roll_values：可选，按出现顺序给 roll 步骤指定结果（测试用；不给就随机）。
    """
    scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict)]
    by_id = {}
    for s in scenes:
        sid = str(s.get("id") or "").strip()
        if sid and sid not in by_id:
            by_id[sid] = s
    if not by_id:
        return {"ok": False, "msg": "没有场景", "endings": [], "states": 0,
                "gated": [], "cycles": False, "truncated": False, "visited_scenes": set()}
    first = str(scenes[0].get("id") or "").strip()
    rolls = list(roll_values or [])
    roll_i = 0
    # 作者模式（state=None）：条件一律视为通<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌过，也不记 gated —— 与静态体检口径一致。
    # 注意不能靠 _state_with(None, ...) 造出来的字典来判：那会让"无状态"变成"有状态"，
    # 于是 aff 条件因为拿不到 affection 而全部失败（这个坑真踩过）。
    author_mode = state is None
    endings, gated, visited = [], [], set()
    seen = set()
    cycles = False
    truncated = False
    init = _state_with(state, _flags_of(state))
    # 队列元素：(场景, 行号, flags, 路径摘要)
    queue = [(first, 0, _flags_of(init), [])]
    while queue:
        sid, idx, flags, path = queue.pop()
        if len(seen) >= max_states:
            truncated = True
            break
        sc = by_id.get(sid)
        if sc is None:
            continue
        visited.add(sid)
        st_now = _state_with(state, flags)
        lines = sc.get("lines") or []
        if idx >= len(lines):
            nxt = str(sc.get("jump") or sc.get("next") or "").strip()
            if nxt and nxt in by_id:
                key = ("->", nxt, tuple(sorted(flags.items())))
                if key in seen:
                    cycles = True
                    continue
                seen.add(key)
                queue.append((nxt, 0, flags, path))
            else:
                endings.append("场景 %s 播完完结" % sid)
            continue
        key = (sid, idx, tuple(sorted(flags.items())))
        if key in seen:
            cycles = True
            continue
        seen.add(key)
        ln = lines[idx]
        if not isinstance(ln, dict):
            queue.append((sid, idx + 1, flags, path))
            continue
        nxt_flags = dict(flags)
        # 先执行会改状态的步骤
        if ln.get("kind") == "setflag":
            k = (ln.get("flag") or {}).get("k")
            if k:
                v = (ln.get("flag") or {}).get("v", True)
                nxt_flags[str(k)] = v
        elif ln.get("kind") == "roll":
            k = (ln.get("roll") or {}).get("k")
            if k:
                try:
                    d = int((ln.get("roll") or {}).get("d") or 100)
                except (TypeError, ValueError):
                    d = 100
                if roll_i < len(rolls):
                    nxt_flags[str(k)] = rolls[roll_i]
                else:
                    nxt_flags[str(k)] = 1 + (hash((sid, idx)) % max(1, d))
                roll_i += 1
        opts = ln.get("choice")
        moved = False
        if isinstance(opts, list):
            for o in opts:
                if not isinstance(o, dict):
                    continue
                cond = o.get("if")
                if cond not in (None, {}) and not author_mode and not cond_pass(cond, st_now):
                    gated.append("%s:lines[%d] 选项「%s」被条件门住" %
                                 (sid, idx, str(o.get("text") or "")[:16]))
                    continue
                g = str(o.get("goto") or "").strip()
                if not g:
                    queue.append((sid, idx + 1, nxt_flags, path))
                elif g in by_id:
                    queue.append((g, 0, nxt_flags, path))
            moved = True
        elif str(ln.get("jump") or "").strip():
            g = str(ln["jump"]).strip()
            if g in by_id:
                queue.append((g, 0, nxt_flags, path))
            moved = True
        elif "end" in ln:
            endings.append(str(ln.get("end") or "完结"))
            moved = True
        if not moved:
            queue.append((sid, idx + 1, nxt_flags, path))
    return {"ok": True, "endings": sorted(set(endings)), "states": len(seen),
            "gated": gated, "cycles": cycles, "truncated": truncated,
            "visited_scenes": visited}


def run_path(data, picks, state=None, max_steps=1000, roll_values=None):
    """按给定选择序列跑**一条**路径（picks 里每个数字 = 当次显示出来的第几个选项）。

    与真播放器的差别：这里不渲染，只走流程；因此可以用来在 CI 里断言
    "好感到 85 时第 2 个选项才出现""设了 flag 之后那条路才通"这类事情。
    返回 {"ok","steps":[...],"ending","flags","stopped"}
    """
    scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict)]
    by_id = {}
    for s in scenes:
        sid = str(s.get("id") or "").strip()
        if sid and sid not in by_id:
            by_id[sid] = s
    if not by_id:
        return {"ok": False, "stopped": "没有场景", "steps": [], "ending": None, "flags": {}}
    sid = str(scenes[0].get("id") or "").strip()
    idx = 0
    flags = _flags_of(_state_with(state, _flags_of(state)))
    rolls = list(roll_values or [])
    roll_i = 0
    picks = list(picks or [])
    pick_i = 0
    steps = []
    for _ in range(max_steps):
        sc = by_id.get(sid)
        if sc is None:
            return {"ok": False, "stopped": "跳到了不存在的场景 " + sid, "steps": steps,
                    "ending": None, "flags": flags}
        lines = sc.get("lines") or []
        if idx >= len(lines):
            nxt = str(sc.get("jump") or sc.get("next") or "").strip()
            if nxt and nxt in by_id:
                steps.append("→ 跳转 %s" % nxt)
                sid, idx = nxt, 0
                continue
            return {"ok": True, "stopped": "完结", "steps": steps,
                    "ending": "场景 %s 播完完结" % sid, "flags": flags}
        ln = lines[idx]
        if not isinstance(ln, dict):
            idx += 1
            continue
        st_now = _state_with(state, flags)
        kind = step_kind(ln)
        if kind == "setflag":
            k = (ln.get("flag") or {}).get("k")
            if k:
                flags[str(k)] = (ln.get("flag") or {}).get("v", True)
                steps.append("setflag %s" % k)
            idx += 1
            continue
        if kind == "roll":
            k = (ln.get("roll") or {}).get("k")
            if k:
                if roll_i < len(rolls):
                    flags[str(k)] = rolls[roll_i]
                else:
                    try:
                        d = int((ln.get("roll") or {}).get("d") or 100)
                    except (TypeError, ValueError):
                        d = 100
                    flags[str(k)] = 1 + (hash((sid, idx)) % max(1, d))
                roll_i += 1
                steps.append("roll %s=%s" % (k, flags[str(k)]))
            idx += 1
            continue
        opts = ln.get("choice")
        if isinstance(opts, list):
            shown = [o for o in opts if isinstance(o, dict)
                     and (o.get("if") in (None, {}) or cond_pass(o.get("if"), st_now))]
            if not shown:
                return {"ok": False, "stopped": "选项全被条件挡住（无法继续）", "steps": steps,
                        "ending": None, "flags": flags}
            pick = picks[pick_i] if pick_i < len(picks) else 0
            pick_i += 1
            if not isinstance(pick, int) or pick < 0 or pick >= len(shown):
                pick = 0
            o = shown[pick]
            steps.append("选择「%s」" % str(o.get("text") or "")[:20])
            g = str(o.get("goto") or "").strip()
            if g and g in by_id:
                sid, idx = g, 0
            else:
                idx += 1
            continue
        if "jump" in ln:
            g = str(ln.get("jump") or "").strip()
            if g in by_id:
                steps.append("→ 跳转 %s" % g)
                sid, idx = g, 0
                continue
            idx += 1
            continue
        if "end" in ln:
            return {"ok": True, "stopped": "到达结局", "steps": steps,
                    "ending": str(ln.get("end") or "完结"), "flags": flags}
        # 台词/表现类：记录一句然后前进
        txt = str(ln.get("text") or ln.get("note") or "")
        if txt:
            steps.append("%s：%s" % (ln.get("speaker") or "·", txt[:30]))
        idx += 1
    return {"ok": False, "stopped": "步数超限（可能是死循环）", "steps": steps,
            "ending": None, "flags": flags}
