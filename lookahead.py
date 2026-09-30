# -*- coding: utf-8 -*-
"""
lookahead.py —— 前瞻展开（从「树壳」往「树状AI」迈的那一步）

树壳的问题（结构性，不是调参能解决）：
    树在生成的【后面】。等候选出现在树上，漂移已经发生了 —— 只能观察，不能阻止。

前瞻展开做的是：在把某一条交给用户之前，**先主动往前生成**，看几条不同的路各走
2~3 轮之后分别到了哪儿，再挑端点最正的那条。用户只看到胜出那条的第一轮。

为什么这能行，而"事后判据"不行 —— 实测得到的：
    在分叉点处，正在漂的那条和合法安静的那条【数据完全一样】（都是 0.000）。
    第 1 轮、第 2 轮都分不开。
    但第 3 轮之后差距就出来了（0.222 vs 0.000）。
    区别不在于判据更聪明，在于【你看了多远】。
    树壳只能等时间流逝；前瞻可以自己往前生成。

诚实的边界（别把它当成万能）：
  ① 前瞻买到的是【信息】，不是【必然】。合法那条如果也一直安静，多深都分不开。
  ② 价值函数还是启发式（关键词覆盖 + 编造检测）。**搜得越深，坏判据的代价越大。**
     实测量过（_tree_data.py）：把语义腐蚀加到 decoy=0.30 时，判据的 AUC 从
     0.896 掉到 0.793，捕获率从 77.8% 掉到 63.6% —— 而且输的方式很集中：
     81% 的误报来自"念叨本场的东西但没推进"（关键词满格，语义空转）。
     关键词判据的真实天花板就在这里，加深度救不了它。
  ③ 即使做满前瞻，也只能「不建立在漂移之上」，做不到「不在一条里漂」。
     后者要生成时控制（logits），chat API 不给 —— 那是架构的墙。

成本：K 条分支 × D 轮深度 = K×D 次调用（每轮）。硬上限见 COST_CAP。
"""

import os
import sys
from typing import Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tree_weight as tw

# 默认参数：先用最省的配置，<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌让用户看到效果再决定加不加
DEF_BRANCHES = 2        # 分几条路
DEF_DEPTH = 2           # 每条路往前探几轮
COST_CAP = 12           # 硬上限：一次前瞻最多这么多次调用（防止配置写错把额度烧光）
# 推进用的合成用户消息。展开分支时模型需要"继续"，但没有真实用户输入，
# 所以用一句中性的推进语 —— 它只出现在【被丢弃的】分支上，不会进用户的树。
CONTINUE_PROMPT = "（继续）"


def score_branch(turns: List[str], keys, case_text: str = "",
                 rubric: Optional[float] = None) -> Dict:
    """给一条分支的端点打分。

    两个分量，都来自已验证的判据：
      · 目标覆盖：这条路上有几轮还碰着本场目标（越高越好）
      · 编造：有没有说出案卷里没有的具体人/物（有就是硬故障，重罚）
    再加上"末轮"单独看一次 —— 端点才是前瞻真正要比的东西。
    """
    turns = [t for t in (turns or []) if str(t or "").strip()]
    if not turns:
        return {"score": 0.0, "coverage": 0.0, "confab": 0, "end_cov": 0.0,
                "end_confab": 0, "rubric": None, "n_turns": 0}
    covs = [tw.anchor_coverage(t, keys) for t in turns]
    confs = [len(tw.indict(t, case_text)) for t in turns]
    mid = sum(covs) / len(covs)
    end_cov = covs[-1]
    confab = sum(1 for c in confs if c)
    # 端点权重更高：前瞻的目的就是看终点，不是看平均。
    # rubric 是唯一"知道这一轮写得好不好"的信号，启发式只能抓硬故障。
    #
    # 关键系数 kr/ka（rubric 相对启发式的比重）—— 原来取 1.25，是拍脑袋的。
    # 实测定过（_tree_data6.py，K=2/D=2，每格 3000 次，合成世界带语义腐蚀）：
    #   kr/ka = 1.25 → 模型判定质量 q 要 0.82(干净)/0.70(腐蚀) 才不亏本
    #   kr/ka = 0.30 → 只要 0.66 / 0.54，且 q=1.0 时的上限一模一样
    # 全曲线上 0.30 在每一个 q 点都 ≥ 1.25，是严格占优。
    # 病根不是"该不该用 rubric"，是【让它有能力翻掉一个有意义的分差】。
    # 一个 q=0.5 的瞎判 + 高权重 = 主动把好分支扔掉（实测捕获率 62% → 35%）。
    if isinstance(rubric, (int, float)):
        score = 1.00 * (0.4 * mid + 0.6 * end_cov) + 0.30 * float(rubric)
    else:
        score = 0.4 * mid + 0.6 * end_cov
    score -= 0.5 * confab
    return {
        "score": round(score, 4),
        "coverage": round(mid, 4),
        "end_cov": round(end_cov, 4),
        "confab": confab,
        "end_confab": 1 if confs[-1] else 0,
        "rubric": round(float(rubric), 4) if isinstance(rubric, (int, float)) else None,
        # 注意键名别叫 "turns" —— 外层 entry 里 turns 是【内容列表】，
        # 同名会被这里的整数覆盖掉（踩过一次，前瞻直接崩）。
        "n_turns": len(turns),
    }


def expand(complete_fn: Callable[[List[Dict]], str],
           base_messages: List[Dict],
           branches: int = DEF_BRANCHES,
           depth: int = DEF_DEPTH,
           keys=None,
           case_text: str = "",
           cap: int = COST_CAP,
           continue_prompt: str = CONTINUE_PROMPT,
           judge_fn: Optional[Callable[[str], Optional[float]]] = None,
           on_step: Optional[Callable[[int, int], None]] = None) -> Dict:
    """从 base_messages 出发做前瞻展开。

    complete_fn(messages) -> str ：一次模型调用（调用方注入，便于测试和复用主程序的调用路径）
    judge_fn(text) -> float|None：价值判定（rubric）。只判端点，不判每一轮。
    base_messages              ：这一轮的完整载荷（system + 历史 + 当前用户消息）
    返回 {"first": 胜出分支的第一轮, "branches": [...], "calls": n, "capped": bool}
    """
    if not base_messages:
        return {"ok": False, "err": "没有可用的载荷"}
    if not keys:
        # 没给目标就无从比较 —— 前瞻会退化成"随便挑一条"，那还不如不做
        return {"ok": False, "err": "没有本场关键词，前瞻无从比较（先设关键词）"}

    branches = max(1, int(branches or 1))
    depth = max(1, int(depth or 1))
    cap = max(1, int(cap or 1))

    out = []
    calls = 0
    capped = False
    for b in range(branches):
        if calls >= cap:
            capped = True
            break
        turns: List[str] = []
        msgs = list(base_messages)
        err = None
        for _d in range(depth):
            if calls >= cap:
                capped = True
                break
            try:
                txt = complete_fn(msgs)
            except Exception as e:
                err = str(e)[:120]
                break
            calls += 1
            if on_step:
                try:
                    on_step(calls, cap)
                except Exception:
                    pass
            txt = (txt or "").strip()
            if not txt:
                err = "空回复"
                break
            turns.append(txt)
            msgs = msgs + [{"role": "assistant", "content": txt},
                           {"role": "user", "content": continue_prompt}]
        # 不管是走完还是中途断了，这条分支都要入账 —— 半条分支也是信息，
        # 而且"探到一半就失败"本身说明这条路易断，不该当成没发生过。
        # 打分：只对【端点】做 rubric 判定（K 次），不判每一轮（K×D 次）。
        # 这是成本上的关键选择：判定是模型调用，判每一轮会让前瞻贵一倍以上，
        # 而前瞻真正要比的就是端点。
        rb = None
        if judge_fn is not None and turns:
            try:
                rb = judge_fn(turns[-1])
            except Exception:
                rb = None
        entry = {"i": b, "turns": turns,
                 **score_branch(turns, keys, case_text, rubric=rb)}
        if err:
            entry["error"] = err
        out.append(entry)

    usable = [x for x in out if x.get("turns")]
    if not usable:
        return {"ok": False, "err": "前瞻没有产出任何可用分支", "calls": calls,
                "capped": capped, "branches": out}

    best = max(usable, key=lambda x: (x["score"], -x["i"]))
    return {
        "ok": True,
        "first": best["turns"][0],
        "best_i": best["i"],
        "best": {k: v for k, v in best.items() if k != "turns"},
        "branches": [{k: v for k, v in x.items() if k != "turns"} for x in out],
        "calls": calls,
        "capped": capped,
        "budget": {"branches": branches, "depth": depth, "cap": cap},
    }


def describe(res: Dict) -> str:
    """把前瞻结果变成一句给用户/日志看的话。"""
    if not res or not res.get("ok"):
        return "前瞻未执行：%s" % ((res or {}).get("err") or "未知")
    b = res.get("budget") or {}
    lines = ["前瞻展开：%d 条 × %d 轮，实际调用 %d 次%s"
             % (b.get("branches", 0), b.get("depth", 0), res.get("calls", 0),
                "（触及上限被截断）" if res.get("capped") else "")]
    for x in res.get("branches") or []:
        lines.append("  分支%d：端点覆盖 %.2f / 编造 %d / 得分 %.2f%s"
                     % (x.get("i", 0), x.get("end_cov", 0), x.get("confab", 0),
                        x.get("score", 0),
                        "  ← 胜出" if x.get("i") == res.get("best_i") else ""))
    return "\n".join(lines)
