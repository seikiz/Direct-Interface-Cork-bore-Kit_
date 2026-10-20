# -*- coding: utf-8 -*-
"""耦合卡（卡包耦合）· 分次设定调度器

这一块只做两件事，但都是纯函数、可单测、可回滚：

  ① **卡包耦合的模型**：一个"耦合包"= 主卡 + 世界卡/世界书 + 机制 + 一批设定条目。
     它们是**不可拆的整体**：加载耦合包就等于同时加载这四样，缺一样就报错（不是警告）。

  ② **分次设定**：每轮只把"核心 + 少量次要"放进上下文。
     · 核心（tier=core）**永远常驻**——这是人设的骨架，不能轮换；
     · 次要（tier=secondary）按"话题相关 × 权重 − 最近用过的惩罚"排序，
       取到字数预算为止；
     · 结果**确定性**：同样的输入一定选出同样的集合（便于复盘与回归测试）。

为什么不做成"让模型自己挑"：那要多一次调用，而且每轮选得不一样，
客户反馈的"没有活人感"往往就是上下文抖动造成的。这里用确定性调度，抖动可控。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 模式互斥
# 耦合卡模式与其它模式**不兼容**（用户明确要求）。这里是唯一真相：
# 其它地方要判断"能不能开"，一律走 can_enable()。
COUPLED = "coupled"
# 用 tuple + frozenset：块里不许有可变全局状态（shared-state 规则会红）
EXCLUSIVE_GROUPS = (
    # 同一组里的模式互斥：开了一个，其它的都必须先关
    frozenset(("single", "group", "coupled")),
)


def can_enable(mode: str, active: Sequence[str]) -> Tuple[bool, str]:
    """能不能把 mode 打开。返回 (可以?, 原因)。"""
    for group in EXCLUSIVE_GROUPS:
        if mode in group:
            others = [m for m in active if m in group and m != mode]
            if others:
                return False, "「%s」与已开启的「%s」不兼容，请先关闭它们" % (mode, "、".join(others))
    return True, ""


def modes_after_enable(mode: str, active: Sequence[str]) -> List[str]:
    """打开 mode 之后，实际生效的模式集合（互斥的自动关掉）。"""
    out = [m for m in active if m != mode]
    for group in EXCLUSIVE_GROUPS:
        if mode in group:
            out = [m for m in out if m not in group]
    out.append(mode)
    return sorted(set(out))


# ---------------------------------------------------------------- 卡包校验
class PackError(ValueError):
    """耦合包不成立（缺件 / 版本不对 / 条目非法）。"""


_REQUIRED = ("id", "version", "main", "settings")


def validate_pack(pack: Dict[str, Any]) -> None:
    """耦合包必须四件齐全：id / version / main（主卡） / settings。

    世界卡与机制**可以没有内容**，但字段必须在（显式的空 = "我知道这里是空的"，
    缺字段 = "忘了写"，两者必须区分开——这是"不可拆"的另一半）。
    """
    if not isinstance(pack, dict):
        raise PackError("耦合包必须是对象")
    for key in _REQUIRED:
        if key not in pack:
            raise PackError("耦合包缺少必填字段：%s" % key)
    if not isinstance(pack["settings"], list) or not pack["settings"]:
        raise PackError("settings 必须是非空数组")
    if "world" not in pack or "mechanics" not in pack:
        raise PackError("耦合包必须显式声明 world 与 mechanics（可以为空对象，但不能不写）")
    ver = str(pack.get("version", ""))
    if len(ver.split(".")) != 4:
        raise PackError("version 必须是四段版号，例如 1.0.0.0")

    seen: Set[str] = set()
    for i, entry in enumerate(pack["settings"]):
        if not isinstance(entry, dict):
            raise PackError("settings[%d] 必须是对象" % i)
        for key in ("id", "text", "tier"):
            if key not in entry:
                raise PackError("settings[%d] 缺少 %s" % (i, key))
        if entry["tier"] not in ("core", "secondary"):
            raise PackError("settings[%d].tier 只能是 core / secondary" % i)
        if entry["id"] in seen:
            raise PackError("settings id 重复：%s" % entry["id"])
        seen.add(entry["id"])


# ---------------------------------------------------------------- 分次调度
def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _score(entry: Dict[str, Any], recent: str, used_recently: Set[str], turn: int) -> float:
    """次要条目的得分：话题相关 × 权重 − 最近用过的惩罚。

    相关性用"标签命中 + 正文里出现关键词"的粗匹配——够快、可解释、不需要模型。
    以后要换成向量相似度，只要替换这个函数（接口不变）。
    """
    weight = float(entry.get("weight", 1.0))
    tags = [str(t) for t in (entry.get("tags") or [])]
    hit = 0.0
    for tag in tags:
        if tag and tag in recent:
            hit += 1.0
    body = _norm(entry.get("text", ""))
    for tag in tags:
        if tag and tag in body:
            hit += 0.2
    score = weight * (1.0 + hit)
    if entry["id"] in used_recently:
        score -= 0.75                      # 刚用过 → 让位
    # 稳定的小量轮转偏移：同一分时按轮次微调，避免永远同样的顺序
    score -= ((turn + len(entry["id"])) % 7) * 0.001
    return score


def select_settings(pack: Dict[str, Any], turn: int = 0, recent_text: str = "",
                    used_recently: Optional[Set[str]] = None,
                    budget_chars: Optional[int] = None) -> Dict[str, Any]:
    """选出本轮要注入的设定条目。

    返回 {"text": 拼好的上下文, "picked": [id...], "skipped": [id...],
          "chars": N, "budget": N, "core": N}

    规则（写死在这里，避免每个调用点各有一套）：
      1. **core 全部常驻**，永不被预算裁掉（裁了就是没骨架）；
      2. secondary 按得分降序取，直到 chars + 条目字数 > budget；
      3. 预算默认读 pack.rules.budget_chars（缺省 1200），可被参数覆盖；
      4. 同样的入参 → 同样的结果（确定性）。
    """
    validate_pack(pack)
    rules = pack.get("rules") or {}
    budget = int(budget_chars if budget_chars is not None
                 else rules.get("budget_chars", 1200))
    used = set(used_recently or ())
    recent = _norm(recent_text)

    core = [e for e in pack["settings"] if e["tier"] == "core"]
    secondary = [e for e in pack["settings"] if e["tier"] == "secondary"]

    picked: List[Dict[str, Any]] = list(core)
    chars = sum(len(e["text"]) for e in picked)

    # 轮换是**硬规则**：刚用过的排到未用过的后面（同档内再按相关度排）。
    # 只靠打分惩罚不够——一条"话题命中"就能把刚用过的重新顶上来。
    ranked = sorted(secondary,
                    key=lambda e: (1 if e["id"] in used else 0,
                                   -_score(e, recent, used, turn), e["id"]))
    skipped: List[str] = []
    for entry in ranked:
        n = len(entry["text"])
        if chars + n > budget:
            skipped.append(entry["id"])
            continue
        picked.append(entry)
        chars += n

    text = "\n".join(e["text"] for e in picked)
    return {
        "text": text,
        "picked": [e["id"] for e in picked],
        "skipped": skipped,
        "chars": chars,
        "budget": budget,
        "core": len(core),
    }
