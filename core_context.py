# -*- coding: utf-8 -*-
"""core_context —— 上下文注入策略（从 DICK_core.py 拆出）。

`ContextInjector` 只做一件事：决定"这一次请求往提示里塞什么"（世界卡、记忆、
时间、角色状态…），不负责发请求。把它单独放，是因为它是最常被改的一张策略表。
"""
from __future__ import annotations

from datetime import datetime

class ContextInjector:
    """动态上下文注入器 - 从索引文件中按关键词检索"""
    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self.indices = {}  # {index_filename: index_data}
        self._load_all_indices()

    def _load_all_indices(self):
        """加载所有 .index.json 文件"""
        if not os.path.exists(self.index_dir):
            return
        for fname in os.listdir(self.index_dir):
            if fname.endswith('.index.json'):
                try:
                    with open(os.path.join(self.index_dir, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.indices[fname] = data
                except Exception as e:
                    print(f"[ContextInjector] 加载索引失败: {fname} - {e}")

    def get_context(self, user_input: str, max_entries: int = 3, priority_threshold: int = 200) -> str:
        """
        根据用户输入检索相关条目，返回拼接后的上下文
        :param user_input: 用户消息
        :param max_entries: 最多返回几条
        :param priority_threshold: 只返回 priority <= 此值的条目（越小越优先）
        """
        if not user_input or not self.indices:
            return ""

        # 提取关键词<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（简单分词）
        words = set()
        for w in re.split(r'[，,、。.！!？?；;：:\s\n]+', user_input):
            w = w.strip()
            if len(w) >= 2:
                words.add(w.lower())

        if not words:
            return ""

        # 匹配所有索引
        matched = []
        for idx_name, idx_data in self.indices.items():
            for entry in idx_data.get('entries', []):
                entry_priority = entry.get('priority', 100)
                if entry_priority > priority_threshold:
                    continue
                entry_keys = [k.lower() for k in entry.get('keywords', [])]
                # 检查是否有关键词匹配
                for word in words:
                    for key in entry_keys:
                        if word in key or key in word:
                            matched.append(entry)
                            break
                    else:
                        continue
                    break

        # 去重（按 content 去重）
        seen = set()
        unique = []
        for entry in matched:
            content = entry.get('content', '')
            if content not in seen:
                seen.add(content)
                unique.append(entry)

        # 按优先级排序
        unique.sort(key=lambda x: x.get('priority', 100))

        # 取前 max_entries 条
        selected = unique[:max_entries]
        if not selected:
            return ""

        # 拼接成上下文
        parts = []
        for entry in selected:
            comment = entry.get('comment', '')
            content = entry.get('content', '')
            if comment:
                parts.append(f"【{comment}】\n{content}")
            else:
                parts.append(content)

        return "\n\n".join(parts)


# ============================================================
#   ChatCore - 对话核心（整合 TreeManager + API + 动态注入）
# ============================================================
GAP_NOTICE_SECONDS = 30 * 60      # 小于这个间隔不吭声（"刚说的话"不值得标注）
GAP_MAX_MARKS = 3                 # 最多标几段间隔，防止长历史把提示撑大
DAY_NOTICE_HOURS = 20             # 超过这么久，报"天"而不是"小时"


def time_context_for(chain, scale=None) -> str:
    """把历史链的【时间间隔】压成一段给模型看的话。没有值得说的间隔就返回 ""。

    为什么要做这件事：MessageNode.timestamp 一直在存，但从来没有任何地方读它，
    模型看到的对话是"没有时间的一袋字"—— 不知道那些事是昨天还是上个月发生的。
    打点计时器能读出东西不是因为它记了字，是因为纸带匀速走、点距=时间。
    所以这里把【间隔】读出来，粘到内容上。

    scale = 软件时间流速。报给模型的必须是【那边】过了多久，不是现实过了多久：
    现实隔了 1 分钟、倍率 86400 时，她那边已经过了一天，就该按一天来演。

    只报显著的间隔（现实 >30 分钟），最多 3 段，避免长历史把提示撑爆。
    纯粹是给模型的上下文，不写盘、不入树。
    """
    if not chain:
        return ""
    try:
        sc = float(scale) if scale else 1.0
    except (TypeError, ValueError):
        sc = 1.0
    if sc <= 0:
        sc = 1.0
    stamps = []
    for m in chain:
        if not isinstance(m, dict) or m.get("role") == "system":
            continue
        ts = m.get("timestamp")
        if not ts:
            continue
        try:
            stamps.append(datetime.fromisoformat(str(ts)))
        except (ValueError, TypeError):
            continue
    if not stamps:
        return ""

    def human(sec):
        if sec < 60:
            return "%d 秒" % sec
        if sec < 3600:
            return "%d 分钟" % (sec // 60)
        if sec < DAY_NOTICE_HOURS * 3600:
            return "%.1f 小时" % (sec / 3600.0)
        days = sec / 86400.0
        return ("%.1f 天" % days) if days < 30 else ("%.1f 个月" % (days / 30.0))

    marks = []
    for i in range(1, len(stamps)):
        gap = (stamps[i] - stamps[i - 1]).total_seconds()
        # 阈值按【现实】判：现实里隔不到半小时就别啰嗦，
        # 但报出来的数字要乘倍率 —— 那才是她那边过的时长。
        if gap >= GAP_NOTICE_SECONDS:
            marks.append(gap * sc)
    if not marks:
        return ""
    marks = sorted(marks, reverse=True)[:GAP_MAX_MARKS]

    since_last = (datetime.now() - stamps[-1]).total_seconds()
    seg = "、".join(human(g) for g in marks)
    out = "【时间】这段对话不是一口气说完的，中途有过 " + seg + " 的间隔。"
    if since_last * sc < GAP_NOTICE_SECONDS:
        out += "上一句是刚才说的。"
    else:
        out += "距离上一次说话已经过了 " + human(since_last * sc) + "。"
    out += "按这个时间感来演：隔了很久就该有变化（她做过别的、心情会不同、会提起你不在的时候）；"
    out += "刚刚才说完的事就别当成很久以前。"
    if sc >= 60:
        out += ("（这个世界的时间流逝比现实快 %d 倍：现实里的一小会儿，"
                "在她那边已经过了很久。）" % int(sc))
    return out


# ============================================================
#  ChatCore
# ============================================================
