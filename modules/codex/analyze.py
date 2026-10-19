# -*- coding: utf-8 -*-
"""modules/codex/analyze.py —— 剧本静态分析（可达性 / 资源引用 / 死分支）

搬家来源：`codex_core.py` 的 `_PLAYER_HANDLED` / `_UNHANDLED_KINDS` / `_MAX_NODES` /
`_refs_of` / `analyze_codex`，**统计口径与 issues 文案一字未改**。

给"发布前检查"用：哪些场景没人能到、哪些资源引用了包里没有的文件、
哪些行类型播放器其实不处理。它只读不写，不需要任何宿主能力。
"""

import os

from .constants import SUBDIRS


_PLAYER_HANDLED = ("say", "note", "choice", "jump", "end", "action")
_UNHANDLED_KINDS = ("show", "hide", "bg", "bgm", "sfx", "effect", "wait", "setflag", "roll")
_MAX_NODES = 200000


def _refs_of(sc):
    """一个场景引用到的素材文件：{相对路径: 出处说明}"""
    out = {}

    def add(rel, where):
        r = str(rel or "").strip()
        if r:
            out.setdefault(r, where)

    add(sc.get("bg"), "scene.bg")
    add(sc.get("bgm"), "scene.bgm")
    for s in (sc.get("sprites") or []):
        if isinstance(s, dict):
            add(s.get("file"), "scene.sprites")
    for j, ln in enumerate(sc.get("lines") or []):
        if not isinstance(ln, dict):
            continue
        for f in ("bg", "bgm", "voice", "sfx", "sprite"):
            add(ln.get(f), "lines[%d].%s" % (j, f))
        for s in (ln.get("sprites") or []):
            if isinstance(s, dict):
                add(s.get("file"), "lines[%d].sprites" % j)
        for im in (ln.get("images") or []):
            add(im if isinstance(im, str) else (im or {}).get("file") if isinstance(im, dict) else None,
                "lines[%d].images" % j)
    return out


def analyze_codex(data, pkg_dir=None):
    """剧本体检。返回 {"ok", "issues", "warnings", "stats", "dead_lines"}。

    issues   = 真问题（结构坏了：走不到、死行、死循环、素材缺失）
    warnings = 会咬人的提示（预览/导出行为不一致、孤儿素材、隐性结局）
    """
    issues, warnings = [], []
    stats = {"scenes": 0, "lines": 0, "choices": 0, "endings": 0, "words": 0,
             "branch_points": 0, "unreachable": 0, "dead_lines": 0}
    dead_lines = []
    if not isinstance(data, dict):
        return {"ok": False, "issues": ["剧本必须是 JSON 对象"], "warnings": [], "stats": stats,
                "dead_lines": dead_lines}
    scenes = [s for s in (data.get("scenes") or []) if isinstance(s, dict)]
    by_id = {}
    for s in scenes:
        sid = str(s.get("id") or "").strip()
        if sid and sid not in by_id:
            by_id[sid] = s
    stats["scenes"] = len(scenes)
    if not scenes:
        return {"ok": False, "issues": ["缺少 scenes（至少一个场景）"], "warnings": [],
                "stats": stats, "dead_lines": dead_lines}

    # ---- 行级模拟：把播放器实际会走到<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的 (场景, 行) 全走一遍 ----
    first = str(scenes[0].get("id") or "").strip()
    seen = set()
    reached_scenes = set()
    reached_ends = []
    stack = [(first, 0)]
    guard = 0
    while stack:
        sid, idx = stack.pop()
        guard += 1
        if guard > _MAX_NODES:
            warnings.append("剧本过大，可达性分析在 %d 个节点处截断" % _MAX_NODES)
            break
        sc = by_id.get(sid)
        if sc is None:
            continue
        reached_scenes.add(sid)
        lines = sc.get("lines") or []
        if idx >= len(lines):                      # 场景播完：jump → next → 完结
            nxt = str(sc.get("jump") or sc.get("next") or "").strip()
            if nxt:
                if nxt in by_id:
                    stack.append((nxt, 0))
                else:
                    issues.append("场景 %s 的 jump/next 指向不存在的场景: %s" % (sid, nxt))
            else:
                reached_ends.append("场景 %s 播完即完结（无 jump/next）" % sid)
            continue
        key = (sid, idx)
        if key in seen:
            continue
        seen.add(key)
        ln = lines[idx]
        if not isinstance(ln, dict):
            stack.append((sid, idx + 1))
            continue
        moved = False
        if isinstance(ln.get("choice"), list):     # 选项：各自 goto；goto 为空的选项 = 就地继续
            for o in ln["choice"]:
                if not isinstance(o, dict):
                    continue
                g = str(o.get("goto") or "").strip()
                if not g:
                    stack.append((sid, idx + 1))
                elif g in by_id:
                    stack.append((g, 0))
                else:
                    issues.append("场景 %s lines[%d] 的选项 goto 指向不存在的场景: %s" % (sid, idx, g))
            moved = True
        elif str(ln.get("jump") or "").strip():
            g = str(ln["jump"]).strip()
            if g in by_id:
                stack.append((g, 0))
            else:
                issues.append("场景 %s lines[%d] jump 指向不存在的场景: %s" % (sid, idx, g))
            moved = True
        elif "end" in ln:
            reached_ends.append("场景 %s lines[%d]：%s" % (sid, idx, str(ln.get("end") or "完结")))
            moved = True
        if not moved:
            stack.append((sid, idx + 1))

    # ---- 死行：可达场景里从未被走到的行 ----
    for s in scenes:
        sid = str(s.get("id") or "").strip()
        if sid not in reached_scenes:
            continue
        for j in range(len(s.get("lines") or [])):
            if (sid, j) not in seen:
                dead_lines.append((sid, j))
    stats["dead_lines"] = len(dead_lines)
    for sid, j in dead_lines[:20]:
        ln = (by_id[sid].get("lines") or [])[j]
        why = "永远执行不到"
        # 最常见的成因：前面有选项或跳转把流程接走了
        prev = (by_id[sid].get("lines") or [])[:j]
        if any(isinstance(p, dict) and isinstance(p.get("choice"), list) for p in prev[-1:]):
            why = "紧跟在选项之后，永远执行不到（选项已经把流程接走）"
        elif any(isinstance(p, dict) and str(p.get("jump") or "").strip() for p in prev[-1:]):
            why = "紧跟跳转之后，永远执行不到"
        issues.append("场景 %s lines[%d] %s：%s" % (sid, j, why, str(ln)[:60]))

    # ---- 不可达场景 / 死循环 ----
    unreachable = [str(s.get("id") or "") for s in scenes
                   if str(s.get("id") or "").strip() not in reached_scenes]
    stats["unreachable"] = len(unreachable)
    for sid in unreachable:
        issues.append("场景 %s 不可达（从第一个场景出发永远走不到）" % sid)
    if not reached_ends:
        issues.append("没有任何可达结局：所有路径都会绕回自己（检查 jump/goto 是否成环）")
    stats["endings"] = len(reached_ends)

    # ---- 双播放器一致性 ----
    # 2026-10 已把内嵌预览补齐：kind 分发（setflag/roll/wait/effect/hide/show/bg/bgm/sfx）
    # 与条件过滤都跟导出播放器同语义，所以这里不再报"预览不执行"。
    # 仍然真实存在的差异只有一个：action 需要后端。
    if any(isinstance(ln, dict) and "action" in ln
           for s in scenes for ln in (s.get("lines") or [])):
        warnings.append("用了「action」行动钩子：只在 DICK 主程序内生效，导出独立 HTML 后会被跳过")
    # 条件分支：静态体检按"所有条件都可能通过"来看（与播放器的作者模式一致），
    # 但至少要让作者知道哪些选项是门住的 —— 预览里被隐藏时会有提示。
    gated = 0
    for s in scenes:
        sid = str(s.get("id") or "").strip()
        if sid not in reached_scenes:
            continue
        for j, ln in enumerate(s.get("lines") or []):
            if not isinstance(ln, dict) or (sid, j) not in seen:
                continue
            for o in (ln.get("choice") or []):
                if isinstance(o, dict) and o.get("if") not in (None, {}):
                    gated += 1
    if gated:
        warnings.append("有 %d 个带条件的选项：预览会按当前好感/标志/状态实时隐藏，"
                        "被门住时选项区会显示「🔒 n/m 个选项因条件不满足被隐藏」" % gated)

    # ---- 素材引用 ----
    refs = {}
    for s in scenes:
        for rel, where in _refs_of(s).items():
            refs.setdefault(rel, where)
    if pkg_dir:
        have = {}
        for kind in SUBDIRS:
            d = os.path.join(pkg_dir, kind)
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if os.path.isfile(os.path.join(d, fn)):
                        have[kind + "/" + fn] = True
        for rel, where in sorted(refs.items()):
            if rel not in have:
                issues.append("素材缺失：%s（被 %s 引用）" % (rel, where))
        for rel in sorted(have):
            if rel not in refs:
                warnings.append("孤儿素材：%s 存在但从未被剧本引用" % rel)

    # ---- 统计 ----
    for s in scenes:
        lines = [ln for ln in (s.get("lines") or []) if isinstance(ln, dict)]
        stats["lines"] += len(lines)
        for ln in lines:
            if isinstance(ln.get("choice"), list):
                stats["choices"] += len(ln["choice"])
                stats["branch_points"] += 1
            stats["words"] += len(str(ln.get("text") or ""))
    # 估算阅读时长：中文按每秒 5 字读白 + 每个选项点 3 秒 + 每次点击 0.8 秒
    secs = stats["words"] / 5.0 + stats["choices"] * 3 + stats["lines"] * 0.8
    stats["est_seconds"] = int(secs)
    stats["est_minutes"] = round(secs / 60.0, 1)

    return {"ok": not issues, "issues": issues, "warnings": warnings,
            "stats": stats, "dead_lines": dead_lines}
