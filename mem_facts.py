# -*- coding: utf-8 -*-
"""mem_facts.py —— 事实层：只记用户**明确说过/做过**的事，和模型的"相处推测"彻底分开。

三条硬规矩
----------
① 只收用户侧：只从 role == "user" 的消息里抽；assistant 的话一律不算事实。
② 每条必须有出处：source（消息 id 或序号）+ t（时间戳）。没有出处的条目直接丢——
   宁可少记，也不要一条无源可查的"事实"，那是第二个幻觉来源。
③ 同一件事以新的为准：key 相同的旧条目被替换，并留下 updated 时间与 prev 文本，
   这样"用户改主意了"能看出来，而不是两条并存互相矛盾。

相处推测（rapport）走 `make_rapport()` / `merge_rapport()`，永远是另一份数据结构，
不会出现在 `to_prompt_block()` 的事实段里。
"""
from __future__ import annotations

import re
import time

MAX_FACT_LEN = 200
KIND_SAID = "said"          # 用户说过的
KIND_DID = "did"            # 用户做过的
KINDS = (KIND_SAID, KIND_DID)


def _clean(text):
    s = re.sub(r"\s+", " ", (text or "")).strip()
    return s[:MAX_FACT_LEN]


def fact_key(text):
    """同一件事的判重键：去空白、去标点、转小写。"""
    s = _clean(text).lower()
    s = re.sub(r"[\s，。、；：！？,.;:!?\"'“”‘’（）()\[\]【】…~—-]+", "", s)
    return s[:80]


def make_fact(text, source, t=None, kind=KIND_SAID, key=None):
    """构造一条事实。text 或 source 为空 → 返回 None（不记无源条目）。"""
    body = _clean(text)
    if not body or source in (None, ""):
        return None
    return {
        "text": body,
        "source": str(source),
        "t": float(t if t is not None else time.time()),
        "kind": kind if kind in KINDS else KIND_SAID,
        # 同一件事的稳定标识（如「居住地」）：给<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌了就能识别"杭州→上海"是同一条的更新
        "key": _clean(key) if key else fact_key(body),
    }


def valid(fact):
    return (isinstance(fact, dict)
            and bool(_clean(fact.get("text", "")))
            and fact.get("source") not in (None, ""))


def from_messages(messages, extractor):
    """从消息里抽事实。

    extractor(msg) -> [str, ...]：只负责"这条消息里用户说了什么"，
    语义判断留给调用方（模型或规则）；本函数只管过滤与出处。
    """
    out = []
    for idx, msg in enumerate(messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        src = msg.get("id") or msg.get("node_id") or "msg-%d" % idx
        try:
            found = extractor(msg) or []
        except Exception:
            continue
        for text in found:
            f = make_fact(text, src, msg.get("t") or msg.get("ts"),
                          KIND_DID if msg.get("did") else KIND_SAID)
            if f:
                out.append(f)
    return out


def merge(existing, incoming, now=None):
    """合并事实：同 key 以新的为准，返回 (merged, replaced)。

    replaced 里是 {old, new} 对，供界面/日志说明"这条被更新了"。
    """
    stamp = float(now if now is not None else time.time())
    bag, order = {}, []
    for f in list(existing or []):
        if not valid(f):
            continue
        k = f.get("key") or fact_key(f["text"])
        if k not in bag:
            order.append(k)
        bag[k] = dict(f)
    replaced = []
    for f in list(incoming or []):
        if not valid(f):
            continue
        k = f.get("key") or fact_key(f["text"])
        if k in bag:
            old = bag[k]
            if old["text"] != f["text"]:
                replaced.append({"old": old["text"], "new": f["text"]})
            merged = dict(old)
            merged.update({kk: vv for kk, vv in f.items() if vv not in (None, "")})
            merged["updated"] = stamp
            bag[k] = merged
        else:
            order.append(k)
            bag[k] = dict(f)
    return [bag[k] for k in order], replaced


def forget(facts, text):
    """用户明确说"忘掉/不是这样"时用：按 key 删掉，返回新列表。"""
    k = fact_key(text)
    return [f for f in (facts or [])
            if valid(f) and (f.get("key") or fact_key(f["text"])) != k]


def to_prompt_block(facts, limit=12, max_chars=600):
    """压成给模型看的一小段；只放事实，不放任何推测。"""
    rows = [f for f in (facts or []) if valid(f)]
    rows = sorted(rows, key=lambda f: f.get("t") or 0, reverse=True)[:limit]
    if not rows:
        return ""
    out, used = [], 0
    for f in rows:
        line = u"- %s" % f["text"]
        if used + len(line) > max_chars:
            break
        out.append(line)
        used += len(line)
    return u"【已知事实（用户亲口说过/做过的）】\n" + "\n".join(out)


# ---------------- 相处推测（独立一份，永不混进事实） ----------------
def make_rapport(note, source, confidence=0.5, t=None):
    body = _clean(note)
    if not body:
        return None
    try:
        conf = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        conf = 0.5
    return {"note": body, "source": str(source), "confidence": conf,
            "t": float(t if t is not None else time.time())}


def merge_rapport(old, notes, keep=20):
    """相处推测按时间累加，最近的在前；只保留最近 keep 条。"""
    rows = [n for n in list(old or []) if isinstance(n, dict) and n.get("note")]
    rows += [n for n in list(notes or []) if isinstance(n, dict) and n.get("note")]
    rows.sort(key=lambda n: n.get("t") or 0, reverse=True)
    return rows[:keep]


def rapport_block(notes, limit=3):
    rows = [n for n in (notes or []) if isinstance(n, dict) and n.get("note")][:limit]
    if not rows:
        return ""
    return u"【相处印象（我的推测，不是事实）】\n" + "\n".join(
        u"- %s" % n["note"] for n in rows)
