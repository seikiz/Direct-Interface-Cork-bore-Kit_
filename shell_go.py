# -*- coding: utf-8 -*-
"""shell_go —— 从 Kit.py 拆出的 mixin（^_go_|^_choices_|^_gal）。

包含方法：_choices_plugin、_choices_state、_go_game、_go_settings、_go_style、_go_note、_go_ai_first、_go_maybe_ai_first、_go_prompt_block、_go_ai_turn、_go_parse_move、_go_after_reply

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

import plugin_manager

class GoMixin:
    """shell_go"""

    def _choices_plugin(self):
        try:
            if self.plugin_manager:
                return self.plugin_manager.get_plugin("Galgame 选项")
        except Exception:
            pass
        return None


    def _choices_state(self):
        p = self._choices_plugin()
        if not p or not p.enabled:
            return {"items": [], "loading": False, "error": ""}
        try:
            return {"items": list(getattr(p, "choices", None) or []),
                    "loading": bool(getattr(p, "choices_loading", False)),
                    "error": str(getattr(p, "choices_error", "") or "")}
        except Exception:
            return {"items": [], "loading": False, "error": ""}


    def _go_game(self):
        return getattr(self, "_go", None)

    # 棋风关键词：从角色卡的性格描述里推断<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌，让「性格」真的影响落子而不只是台词
    GO_STYLE_WORDS = {
        "aggressive": ["好战", "激进", "暴躁", "强势", "攻击", "争强", "不服输", "凶", "狠",
                       "狂妄", "挑衅", "火爆", "嗜血", "暴虐", "战斗", "危险", "咄咄"],
        "solid": ["谨慎", "稳重", "冷静", "沉着", "细腻", "保守", "理性", "严谨", "稳健",
                  "小心", "缜密", "沉稳", "克制", "耐心", "踏实"],
        "proud": ["骄傲", "自负", "自信", "高傲", "目中无人", "天才", "自恋", "优越",
                  "高贵", "不屑", "傲慢", "大小姐", "冷淡"],
        "playful": ["随性", "懒", "散漫", "调皮", "顽皮", "跳脱", "漫不经心", "任性",
                    "胡闹", "活泼", "开朗", "天真", "好奇", "贪玩"],
    }
    GO_STYLE_LABEL = {
        "aggressive": "好战 —— 喜欢贴身纠缠、追杀、叫吃",
        "solid": "稳重 —— 喜欢连接、围地、稳扎稳打",
        "proud": "高傲 —— 喜欢占大场星位做模样，不屑贴身缠斗",
        "playful": "随性 —— 下得跳脱，偶尔神来一笔或随手一着",
        "balanced": "均衡 —— 该怎么下怎么下",
    }

    # ── 好感度 → 棋局设定（想调难度就改这里）────────────────────
    # 格式：(好感下限, 让子数, 放水概率, 关系描述)
    #
    # 让子数上限是 1 —— 再多就不像在下棋了，而是像在哄人。
    # 所以【放水概率】才是真正决定难度的那一列，想让棋更轻松就调它。
    # 真要让更多子：改下面的 GO_MAX_HANDICAP（引擎支持到 9 子），
    # 同时记得把这张表里对应档位的让子数一起改大。
    GO_MAX_HANDICAP = 1
    GO_KOMI_PER_HANDICAP = 5.0     # 玩家执白时，1 子折成多少目贴还给他

    GO_AFF_TIERS = [
        (85, 1, 0.30, "很亲近，愿意让着你一子"),
        (70, 1, 0.20, "关系不错，会不自觉地放水"),
        (50, 1, 0.05, "还算熟，让一子客气一下"),
        (0, 0, 0.00, "还没什么交情，不留情"),
    ]


    def _go_settings(self):
        """按好感度算出这盘的让子数 / 放水概率 / 额外贴目"""
        aff = 50
        try:
            v = (self.core.mechanism_state or {}).get("affection")
            if isinstance(v, (int, float)):
                aff = v
        except Exception:
            pass
        handicap, mercy, mood = 0, 0.0, self.GO_AFF_TIERS[-1][3]
        for lo, h, m, label in self.GO_AFF_TIERS:
            if aff >= lo:
                handicap, mercy, mood = h, m, label
                break
        # 上限在这里再夹一次：以后有人把表里的数字改大了，也不会真的多让子
        handicap = max(0, min(int(handicap), self.GO_MAX_HANDICAP))
        human = getattr(self, "_go_human", "black")
        komi_extra = 0.0
        if human == "white":
            # 玩家执白时没法给他让子，改成多贴目（她吃亏）
            komi_extra = handicap * self.GO_KOMI_PER_HANDICAP
            handicap = 0
        return {"aff": aff, "handicap": handicap, "mercy": mercy,
                "komi_extra": komi_extra, "mood": mood}


    def _go_style(self):
        """从当前角色卡推断棋风；好感度也会影响（低→更冲，高→更稳）"""
        try:
            roles = getattr(self.core, "active_roles", None) or []
            text = ""
            for r in roles[:1]:
                if not isinstance(r, dict):
                    continue
                for k in ("personality", "description", "scenario", "name", "system_prompt"):
                    v = r.get(k)
                    if isinstance(v, str):
                        text += v + "\n"
            scores = {}
            for st, words in self.GO_STYLE_WORDS.items():
                scores[st] = sum(text.count(w) for w in words)
            best = "balanced"
            if scores:
                cand = max(scores, key=lambda k: scores[k])
                if scores[cand] > 0:
                    best = cand
            # 机制卡联动：好感度低时更冲，高时更稳（只在没明显性格倾向时生效）
            if best == "balanced":
                aff = None
                try:
                    aff = (self.core.mechanism_state or {}).get("affection")
                except Exception:
                    aff = None
                if isinstance(aff, (int, float)):
                    if aff < 30:
                        best = "aggressive"
                    elif aff >= 80:
                        best = "solid"
            return best
        except Exception:
            return "balanced"


    def _go_note(self, text):
        log = getattr(self, "_go_log", None)
        if log is None:
            log = self._go_log = []
        log.append(text)
        if len(log) > 200:
            del log[:-200]


    def _go_ai_first(self):
        """玩家执白时，开局让 AI 先走"""
        b = self._go_game()
        human = getattr(self, "_go_human", "black")
        if b is None or b.finished:
            return
        ai_black = (human == "white")
        if ai_black and b.to_move == b.BLACK and len(b.moves) == 0:
            self._go_ai_turn("（对局开始，你执黑先行。）")


    def _go_maybe_ai_first(self):
        try:
            self._go_ai_first()
        except Exception:
            pass


    def _go_prompt_block(self):
        """构造注入给模型的棋盘说明 + 候选点"""
        import go_engine as ge
        b = self._go_game()
        human = getattr(self, "_go_human", "black")
        ai_color = "白" if human == "black" else "黑"
        my_mark = "O" if ai_color == "白" else "X"
        cands = []
        style = self._go_style()
        gs = self._go_settings()
        try:
            cands = b.candidates(b.to_move, limit=6, style=style, mercy=gs["mercy"])
        except Exception:
            pass
        lines = []
        lines.append("你执%s（棋盘上 %s 是你的子），对方执%s。" % (ai_color, my_mark,
                                                            "黑" if ai_color == "白" else "白"))
        lines.append("你的棋风：%s。选点请贴合你的性格。" %
                     self.GO_STYLE_LABEL.get(style, self.GO_STYLE_LABEL["balanced"]))
        # 好感度 → 这盘棋的设定（让子/放水），让她的态度和棋局一致
        if gs["handicap"]:
            lines.append("这是让子局：你让了对方 %d 子。你们的关系——%s。"
                         "可以偶尔手软，但别放得太明显，输了也别恼。" % (gs["handicap"], gs["mood"]))
        elif gs["komi_extra"]:
            lines.append("你多贴了 %.1f 目给对方，是让着她的。你们的关系——%s。"
                         % (gs["komi_extra"], gs["mood"]))
        else:
            lines.append("分先对局，关系——%s。不必留情，全力下。" % gs["mood"])
        lines.append("")
        lines.append("当前棋盘（X=黑子 O=白子 .=空；列 A-T 跳过 I，行 1-19 自下往上）：")
        lines.append(b.to_ascii())
        lines.append("")
        st = b.score()
        ai_stone = ge.BLACK if ai_color == "黑" else ge.WHITE
        opp_stone = ge.WHITE if ai_color == "黑" else ge.BLACK
        lines.append("已提子：你 %d 子，对方 %d 子。已下 %d 手。" %
                     (b.captured[ai_stone], b.captured[opp_stone], len(b.moves)))
        if cands:
            lines.append("")
            lines.append("【引擎给你的候选点】这几个点都不错，**优先从里面挑一个**：")
            for i, c in enumerate(cands, 1):
                lines.append("   %d. %s —— %s" % (i, c["display"], c["why"]))
        lines.append("")
        lines.append("要求：")
        lines.append("1. 落子必须是**空点**、且不能让你的子自杀；不要下在刚被提掉的打劫点上。")
        lines.append("2. 回复里**必须**用一个坐标明确说出你下在哪里，例如「我下在 Q16」。")
        lines.append("3. 再用你自己的口吻说一两句台词，体现性格（可以吐槽棋局、可以挑衅、可以紧张）。")
        lines.append("4. 不要解释规则，不要输出棋盘。")
        return "\n".join(lines)


    def _go_ai_turn(self, user_line=""):
        """轮到 AI：把棋盘注入 pending_event，然后发一句话触发请求"""
        b = self._go_game()
        if b is None or b.finished:
            return
        human = getattr(self, "_go_human", "black")
        if (b.to_move == b.BLACK) == (human == "black"):
            return                                    # 还没轮到 AI
        try:
            blocks = [self._go_prompt_block()]
            fix = getattr(self, "_go_fix", None)
            if fix:
                blocks.append("")
                blocks.append("【上一手被驳回】%s 请重新选一个合法的点。" % fix)
                self._go_fix = None
            self.core.pending_event = {
                "id": "_go_turn", "name": "围棋·轮到你",
                "prompt": "\n".join(blocks),
            }
        except Exception as e:
            self._append_sys("围棋：注入失败 %s" % str(e)[:120])
            return
        self._send_text(user_line or "（轮到你落子）", None, None)


    def _go_parse_move(self, reply):
        """从回复里解析落子坐标。返回 (x,y) 或 None。
        优先命中引擎给的候选点；否则取最后一个合法坐标。"""
        import re as _re
        b = self._go_game()
        if b is None or not reply:
            return None
        pat = _re.compile(r"(?<![A-Za-z0-9])([A-HJ-Ta-hj-t])\s?(\d{1,2})(?![0-9])")
        found = []
        for m in pat.finditer(str(reply)):
            xy = b.from_display(m.group(1) + m.group(2))
            if xy and xy not in found:
                found.append(xy)
        if not found:
            return None
        try:
            cand = [(c["x"], c["y"]) for c in b.candidates(b.to_move, limit=8, style=self._go_style())]
        except Exception:
            cand = []
        for xy in found:                      # 先看是不是候选点
            if xy in cand and b.is_legal(xy[0], xy[1])[0]:
                return xy
        for xy in reversed(found):            # 再退而求其次：最后一个能下的
            if b.is_legal(xy[0], xy[1])[0]:
                return xy
        return None


    def _go_after_reply(self, reply):
        """模型回复落地后的钩子：解析并落子。解析不到就引擎兜底，保证棋局永远能推进。"""
        import threading as _th
        b = self._go_game()
        if b is None or b.finished:
            return
        human = getattr(self, "_go_human", "black")
        if (b.to_move == b.BLACK) == (human == "black"):
            return                                    # 现在不是 AI 的回合
        xy = self._go_parse_move(reply)
        if xy is not None:
            r = b.play(xy[0], xy[1])
            if r["ok"]:
                self._go_note("对手落子 %s%s" % (r["display"],
                                             ("，提 %d 子" % len(r["captured"])) if r["captured"] else ""))
                if b.finished:
                    self._go_note("终局：" + b.result)
                return
            reason = r.get("reason") or "非法手"
        else:
            reason = "回复里没找到可用的坐标"

        # 驳回重选：最多重试 1 次；延迟一下让本轮 _on_response 先跑完（busy 复位）
        tries = getattr(self, "_go_retry", 0)
        if tries < 1:
            self._go_retry = tries + 1
            self._go_fix = reason
            self._go_note("⚠ 对手这一手有问题（%s），让它重选一次" % reason)
            try:
                _th.Timer(0.8, lambda: self._go_ai_turn("（刚才那手不行，重选一个点）")).start()
                return
            except Exception:
                pass

        # 兜底：引擎替它落一手，棋局绝不停住
        self._go_retry = 0
        try:
            cands = b.candidates(b.to_move, limit=1)
        except Exception:
            cands = []
        if cands:
            c = cands[0]
            r = b.play(c["x"], c["y"])
            if r["ok"]:
                self._go_note("⚠ 对手没给出合法坐标，裁判代落 %s（%s）" % (r["display"], c["why"]))
                if b.finished:
                    self._go_note("终局：" + b.result)

