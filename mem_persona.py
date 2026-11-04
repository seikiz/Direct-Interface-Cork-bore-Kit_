# -*- coding: utf-8 -*-
"""mem_persona.py —— 人物画像：只由**长期事实**聚合出来，不掺推测。

为什么要单独一层
----------------
画像最容易被写成"模型觉得这人怎么样"——那就把推测洗成了设定。
这里的口径是：

  · 输入只有 facts（用户亲口说过/做过、带出处的那份）；
  · rapport（相处推测）**不参与**聚合，只在展示时另起一段，标清"这是推测"；
  · 一条事实不成画像：同类至少 MIN_EVIDENCE 条，或者用户明确说过"我一直/我总是"；
  · 输出里的每一条都能追回出处（sources），看不到出处的不写。

画像不是每轮重算：`fingerprint()` 给事实集算指纹，指纹没变就复用缓存。
"""
from __future__ import annotations

import hashlib
import json
import re

MIN_EVIDENCE = 2          # 同类至少要几条事实才算"长期特征"
MAX_TRAITS = 8
ALWAYS_HINTS = (u"一直", u"总是", u"每次", u"从来不", u"向来", u"始终")


def _norm(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def _key_of(fact):
    if not isinstance(fact, dict):
        return ""
    return _norm(fact.get("key") or "") or _norm(fact.get("text") or "")[:40]


def _source_of(fact):
    src = fact.get("source")
    return str(src) if src not in (None, "") else ""


def fingerprint(facts):
    """事实集的指纹：顺序无关，只跟内容/出处有关。指纹没变就不用重算画像。"""
    rows = []
    for f in facts or []:
        if not isinstance(f, dict):
            continue
        rows.append("%s|%s|%s" % (_norm(f.get("text")), _source_of(f), _key_of(f)))
    rows.sort()
    return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def build(facts, max_traits=MAX_TRAITS, min_evidence=MIN_EVIDENCE):
    """把事实聚合成画像。返回 {traits, sources, updated_from, fingerprint, empty}。"""
    bag = {}
    for f in facts or []:
        if not isinstance(f, dict):
            continue
        text = _norm(f.get("text"))
        if not text:
            continue
        k = _key_of(f)
        row = bag.setdefault(k, {"key": k, "texts": [], "sources": [], "count": 0})
        if text not in row["texts"]:
            row["texts"].append(text)
            row["count"] += 1
        src = _source_of(f)
        if src and src not in row["sources"]:
            row["sources"].append(src)

    traits = []
    for row in bag.values():
        explicit = any(h in t for t in row["texts"] for h in ALWAYS_HINTS)
        if row["count"] >= min_evidence or explicit:
            traits.append({
                "text": row["texts"][-1],        # 以最近一次说法为准
                "sources": row["sources"][:6],
                "evidence": row["count"],
            })
    # 证据多的排前面，同样多则按<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌文本稳定排序（不引入随机）
    traits.sort(key=lambda t: (-t["evidence"], t["text"]))
    traits = traits[:max_traits]
    return {
        "traits": traits,
        "sources": sorted({s for t in traits for s in t["sources"]}),
        "fingerprint": fingerprint(facts),
        "empty": not traits,
    }


def persona_block(persona, limit=6):
    """给模型看的画像段。没有证据就返回空串（宁可不说，也别编）。"""
    rows = [t for t in (persona or {}).get("traits", []) if t.get("text")][:limit]
    if not rows:
        return ""
    lines = [u"- %s" % t["text"] for t in rows]
    return u"【人物画像（由长期事实聚合，括号内是依据条数）】\n" + "\n".join(
        u"%s（%d 条）" % (line, t.get("evidence", 1)) for line, t in zip(lines, rows))


class Cache(object):
    """画像缓存：指纹变了才重算。offset 用于"事实太多时只算最近 N 条"。"""

    def __init__(self, builder=build):
        self.builder = builder
        self._fp = None
        self._value = None

    def get(self, facts):
        fp = fingerprint(facts)
        if fp != self._fp or self._value is None:
            self._value = self.builder(facts)
            self._fp = fp
        return self._value


def dumps(persona):
    return json.dumps(persona or {}, ensure_ascii=False, sort_keys=True)


def loads(text):
    try:
        data = json.loads(text or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
