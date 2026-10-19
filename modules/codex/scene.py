# -*- coding: utf-8 -*-
"""modules/codex/scene.py —— 剧本语法：文本 → codex.json 数据结构

搬家来源：`codex_core.py` 的九条剧本正则 + `_norm_goto` + `parse_script_text` +
`_align_resources` + `normalize_script`，**解析规则与容错一字未改**。

输入是一段人写的剧本文本（`【场景】`/`角色：台词`/`- 选项 → s2` 这类），
输出是 codex.json 的 dict 结构。资源引用对齐（`_align_resources`）把
`sprites/xxx.png` 这种相对路径补全成包内真实文件名。

依赖方向：scene → rules（`step_kind` 判行类型）。rules 不许反过来 import scene。
"""

import os
import re

from .constants import CODEX_VERSION
from .rules import step_kind


_SCENE_RE = re.compile(r"^\s*[【\[]\s*(?:场景|scene)\s*[】\]]\s*[:：]?\s*(.*)$", re.I)
_BG_RE = re.compile(r"^\s*(?:【背景】|背景\s*[:：]|bg\s*[:：])\s*(.+)$", re.I)
_BGM_RE = re.compile(r"^\s*(?:【音乐】|【bgm】|音乐\s*[:：]|bgm\s*[:：])\s*(.+)$", re.I)
_NOTE_RE = re.compile(r"^\s*>\s*(.+)$")
_CHOICE_HEAD_RE = re.compile(r"^\s*[【\[]\s*(?:选项|choice)\s*[】\]]\s*(.*)$", re.I)
_CHOICE_ITEM_RE = re.compile(r"^\s*(?:[-*·•]|\d+[.、）)])\s*(.+?)\s*(?:→|->)\s*([A-Za-z]?\d+)\s*$")
_JUMP_RE = re.compile(r"^\s*(?:【跳转】|跳转\s*[:：]|jump\s*[:：])\s*([A-Za-z]?\d+)\s*$", re.I)
_END_RE = re.compile(r"^\s*(?:【结局】|结局\s*[:：]|end\s*[:：])\s*(.+)$", re.I)
_SPEAKER_RE = re.compile(r"^\s*([^:：]{1,20}?)\s*[:：]\s*(.+)$")


def _norm_goto(g):
    """把 goto 目标规整成场景 id：'2' → 's2'，'s2' → 's2'，'S2' → 's2'"""
    g = (g or "").strip()
    if re.match(r"^[A-Za-z]", g):
        return g
    return "s" + g.lstrip("sS")


def parse_script_text(text, name="我的故事"):
    """把纯文本剧本解析成 codex.json 对象（傻瓜化：粘贴文本 → 可播剧本）。

    约定格式（中英文标点均可）：
      【场景】章节标题                 → 新建场景（id 依次 s1, s2, ...）
      【背景】xxx.png / 背景: xxx.png   → 当前场景背景
      【音乐】xxx.mp3 / bgm: xxx.mp3    → 当前场景音乐
      > 旁白文字                       → 舞台说明（note）
      角色名：台词                      → 台词
      【选项】                          → 其后用 “- 文字 → s2” 的选项行
         - 打招呼 → s2
      【跳转】s2 / 跳转: s2             → 跳转
      【结局】标题 / 结局: 标题          → 结局
    空行跳过；未识别的行当作旁白（note）。
    解析失败返回 None。"""
    if not isinstance(text, str) or not text.strip():
        return None
    scenes = []
    cur = None
    choice_items = []

    def new_scene(title):
        nonlocal cur, choice_items
        sid = "s" + str(len(scenes) + 1)
        sc = {"id": sid, "title": (title or "").strip() or ("场景 " + str(len(scenes) + 1)),
              "lines": []}
        scenes.append(sc)
        cur = sc
        choice_items = []
        return sc

    def flush_choice():
        nonlocal choice_items
        if choice_items and cur is not None:
            cur["lines"].append({"choice": choice_items})
        choice_items = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        fold = line[0:2]
        if fold in ("//", "#!"):
            continue
        m = _SCENE_RE.match(line)
        if m:
            flush_choice()
            new_scene(m.group(1))
            continue
        mb = _BG_RE.match(line)
        if mb:
            if cur is None:
                new_scene("")
            flush_choice()
            cur["bg"] = mb.group(1).strip()
            continue
        mm = _BGM_RE.match(line)
        if mm:
            if cur is None:
                new_scene("")
            flush_choice()
            cur["bgm"] = mm.group(1).strip()
            continue
        mn = _NOTE_RE.match(line)
        if mn:
            if cur is None:
                new_scene("")
            flush_choice()
            cur["lines"].append({"note": mn.group(1).strip()})
            continue
        mc = _CHOICE_HEAD_RE.match(line)
        if mc:
            if cur is None:
                new_scene("")
            inline = mc.group(1).strip()
            ci = _CHOICE_ITEM_RE.match(inline)
            if inline and ci:
                choice_items.append({"text": ci.group(1).strip(),
                                     "goto": _norm_goto(ci.group(2))})
            continue
        mi = _CHOICE_ITEM_RE.match(line)
        if mi:
            if cur is None:
                new_scene("")
            choice_items.append({"text": mi.group(1).strip(),
                                 "goto": _norm_goto(mi.group(2))})
            continue
        mj = _JUMP_RE.match(line)
        if mj:
            if cur is None:
                new_scene("")
            flush_choice()
            cur["lines"].append({"jump": _norm_goto(mj.group(1))})
            continue
        me = _END_RE.match(line)
        if me:
            if cur is None:
                new_scene("")
            flush_choice()
            cur["lines"].append({"end": me.group(1).strip()})
            continue
        ms = _SPEAKER_RE.match(line)
        if ms:
            sp = ms.group(1).strip()
            t = ms.group(2).strip()
            if t:
                if cur is None:
                    new_scene("")
                flush_choice()
                cur["lines"].append({"speaker": sp, "text": t})
                continue
        # 兜底：未识<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌别行当作旁白
        if cur is None:
            new_scene("")
        flush_choice()
        cur["lines"].append({"note": line})
    flush_choice()
    if not scenes:
        return None
    return {"codex": CODEX_VERSION, "name": name, "author": "", "intro": "",
            "scenes": scenes}


def _align_resources(data, pkg_dir):
    """把剧本资源引用与包内实有文件对齐：缺省且包内唯一 → 自动回填；
    已有引用但路径不匹配 → 按文件名修复。就地修改 data。"""
    avail = {}
    for kind in SUBDIRS:
        kd = os.path.join(pkg_dir, kind)
        files = []
        if os.path.isdir(kd):
            try:
                files = sorted(f for f in os.listdir(kd) if os.path.isfile(os.path.join(kd, f)))
            except Exception:
                files = []
        avail[kind] = files

    def repair(kind, ref):
        ref = (ref or "").strip().replace("\\", "/")
        if not kind or not ref:
            return None
        base = os.path.basename(ref)
        if base in avail.get(kind, []):
            return f"{kind}/{base}"
        return None

    def only(kind):
        fs = avail.get(kind, [])
        return f"{kind}/{fs[0]}" if len(fs) == 1 else None

    for sc in data.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        for field, kind in (("bg", "bg"), ("bgm", "bgm")):
            if field in sc and sc.get(field):
                r = repair(kind, sc[field])
                if r:
                    sc[field] = r
            elif field not in sc:
                r = only(kind)
                if r:
                    sc[field] = r
        for ln in sc.get("lines") or []:
            if not isinstance(ln, dict):
                continue
            for field, kind in (("sprite", "sprites"), ("voice", "voice"),
                                ("bg", "bg"), ("bgm", "bgm")):
                if ln.get(field):
                    r = repair(kind, ln[field])
                    if r:
                        ln[field] = r
            if isinstance(ln.get("sprites"), list):
                for s in ln["sprites"]:
                    if isinstance(s, dict) and s.get("file"):
                        r = repair("sprites", s["file"])
                        if r:
                            s["file"] = r
    return data


def normalize_script(data, pkg_dir=None):
    """把（粘贴/解析的）剧本规整成可播 codex.json：补默认字段、保证场景 id 连续、
    若有包目录则对位资源。返回规整后的 data（不校验）。"""
    if not isinstance(data, dict):
        return data
    if not data.get("codex"):
        data["codex"] = CODEX_VERSION
    data.setdefault("author", "")
    data.setdefault("intro", "")
    scenes = data.get("scenes")
    if isinstance(scenes, list):
        n = 1
        for sc in scenes:
            if not isinstance(sc, dict):
                continue
            if not str(sc.get("id") or "").strip():
                sc["id"] = "s" + str(n)
            n += 1
            if not isinstance(sc.get("lines"), list):
                sc["lines"] = []
            for ln in sc["lines"]:
                if not isinstance(ln, dict):
                    continue
                _k = step_kind(ln)
                if _k:
                    ln.setdefault("kind", _k)  # 仅在未显式给 kind 时补（不覆盖作者意图）
                if "choice" in ln and isinstance(ln["choice"], list):
                    for o in ln["choice"]:
                        if isinstance(o, dict) and o.get("if") is True:
                            o["if"] = None
        if pkg_dir:
            _align_resources(data, pkg_dir)
    return data
