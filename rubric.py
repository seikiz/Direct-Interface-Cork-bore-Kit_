# -*- coding: utf-8 -*-
"""
rubric.py —— 价值声明 + 模型判定（便宜版的 PRM）

为什么需要它：
    树状架构的收益 = (价值函数准确度 − 随机) × 搜索规模。
    启发式判据只抓得住"拒答/复读/编造"这类硬故障，抓不住"这一轮写得好不好"。
    训练一个 PRM 很贵（而且现在没有数据），但**把人评价创造性工作的现成办法搬过来很便宜**：
    作者声明一张评分标准（rubric），让模型按标准判一次。

    这不是我们发明的 —— 作文比赛、代码评审、同行评议，人类规模化评价创造性工作一直靠 rubric。

分三步走，这一模块是第 2、3 步：
    ① 目标声明（关键词）  → 已有（tree_weight.anchor_coverage）
    ② 价值声明（rubric）  → 本模块 build_prompt / 存储
    ③ 模型判定            → 本模块 parse_verdict / judge

诚实的代价（必须写在代码里，否则会被忘掉）：
    · **rubric 写不好比不写更糟** —— 声明错了，搜索会忠实地放大它
    · 每一次判定是一次模型调用。所以只判【端点】，不判每一轮：
      前瞻 K 条分支 → 判 K 次，而不是 K×D 次
    · rubric 是【你的】价值，不是普遍价值。给朋友用就要重新想
"""

import json
import re
from typing import Dict, List, Optional

MAX_CRITERIA = 8          # 标准条数上限：写太多模型会平均化，判不出差别
SCORE_MAX = 5             # 每项满分


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  声明
# ============================================================
def normalize(criteria) -> List[str]:
    """把用户输入的标准洗干净：去空、去重、限量。"""
    if isinstance(criteria, str):
        parts = re.split(r"[\n；;]+", criteria)
    else:
        parts = list(criteria or [])
    out = []
    for c in parts:
        c = re.sub(r"^\s*[\d]+[.、)）]\s*", "", str(c or "")).strip()
        if c and c not in out:
            out.append(c)
    return out[:MAX_CRITERIA]


def build_prompt(criteria: List[str], context: List[Dict], candidate: str) -> List[Dict]:
    """组装判定用的 messages。判定是独立调用，不带主对话的人设。"""
    crit = normalize(criteria)
    lines = ["%d. %s" % (i + 1, c) for i, c in enumerate(crit)]
    sys = (
        "你是一个严格的评审。按给定的标准给「待评回复」逐项打分，"
        "每项 0~%d 的整数（0=完全不符合，%d=完全符合）。\n"
        "评分标准：\n%s\n\n"
        "只输出一个 JSON 对象，不要任何解释文字：\n"
        '{"scores": [%s], "note": "一句话说明最扣分的那项"}\n'
        "要求：不要因为文笔好就给高分——按标准判，不按感觉判。"
        % (SCORE_MAX, SCORE_MAX, "\n".join(lines),
           ", ".join(["0"] * len(crit)))
    )
    ctx = []
    for m in (context or [])[-6:]:
        r = m.get("role")
        if r in ("user", "assistant"):
            ctx.append("%s：%s" % ("用户" if r == "user" else "角色",
                                   str(m.get("content") or "")[:400]))
    body = ""
    if ctx:
        body += "【前文】\n" + "\n".join(ctx) + "\n\n"
    body += "【待评回复】\n" + str(candidate or "")
    return [{"role": "system", "content": sys},
            {"role": "user", "content": body}]


# ============================================================
#  解析（模型不听话是常态，必须容错）
# ============================================================
def parse_verdict(text: str, n: int) -> Optional[Dict]:
    """从模型回复里抠出评分。抠不出来返回 None（宁可退回启发式，也不瞎猜）。"""
    if not text or n <= 0:
        return None
    raw = str(text)

    # 1) 先试正经 JSON
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            o = json.loads(m.group(0))
            sc = o.get("scores")
            if isinstance(sc, list) and len(sc) >= n:
                vals = []
                for x in sc[:n]:
                    try:
                        vals.append(int(float(x)))
                    except Exception:
                        return None
                return {"scores": [max(0, min(SCORE_MAX, v)) for v in vals],
                        "note": str(o.get("note") or "")[:200]}
        except Exception:
            pass

    # 2) 退一步：从 "scores": [...] 里抠数字
    m = re.search(r"scores?\s*[：:]\s*\[([^\]]*)\]", raw, re.I)
    if m:
        nums = re.findall(r"-?\d+", m.group(1))
        if len(nums) >= n:
            try:
                vals = [max(0, min(SCORE_MAX, int(x))) for x in nums[:n]]
                return {"scores": vals, "note": ""}
            except Exception:
                pass

    # 3) 再退：全文找 n 个 0~5 的独立数字，但要求它们出现在同一行
    for line in raw.split("\n"):
        nums = re.findall(r"(?<![\d.])[0-5](?![\d.])", line)
        if len(nums) >= n:
            return {"scores": [int(x) for x in nums[:n]], "note": ""}
    return None


def aggregate(verdict: Optional[Dict], n: int) -> Optional[float]:
    """评分 → 0~1 的单一价值。判不出来返回 None。"""
    if not verdict or not verdict.get("scores"):
        return None
    sc = verdict["scores"][:n] if n else verdict["scores"]
    if not sc:
        return None
    return round(sum(sc) / (len(sc) * SCORE_MAX), 4)


def judge(complete_fn, criteria: List[str], context: List[Dict], candidate: str) -> Dict:
    """判一条。任何异常都退回 None，绝不抛（判定失败不该打断生成）。

    返回 {"score": 0~1|None, "scores": [...], "note": str, "error": str|None}
    """
    crit = normalize(criteria)
    if not crit or not str(candidate or "").strip():
        return {"score": None, "scores": [], "note": "", "error": "没有标准或没有内容"}
    try:
        msgs = build_prompt(crit, context, candidate)
        out = complete_fn(msgs)
    except Exception as e:
        return {"score": None, "scores": [], "note": "", "error": str(e)[:160]}
    v = parse_verdict(out, len(crit))
    if v is None:
        return {"score": None, "scores": [], "note": "",
                "error": "模型没有按格式给分（已退回启发式）"}
    return {"score": aggregate(v, len(crit)), "scores": v["scores"],
            "note": v.get("note") or "", "error": None}


def judge_candidates(complete_fn, criteria, context, candidates: List[str],
                     cap: int = 8, on_step=None) -> List[Dict]:
    """批量判。硬上限保护：判定的调用次数必须可控，否则前瞻会变成烧钱机器。"""
    out = []
    for i, c in enumerate(candidates or []):
        if i >= cap:
            out.append({"score": None, "scores": [], "note": "",
                        "error": "超过判定上限，未判"})
            continue
        r = judge(complete_fn, criteria, context, c)
        if on_step:
            try:
                on_step(i + 1, min(len(candidates), cap))
            except Exception:
                pass
        out.append(r)
    return out
