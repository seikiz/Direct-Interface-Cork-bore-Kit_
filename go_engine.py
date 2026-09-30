# -*- coding: utf-8 -*-
"""
go_engine.py —— 围棋规则引擎（纯 Python，无第三方依赖，可单测）

设计原则：**规则 100% 由引擎决定，模型只负责"选点"和"说台词"。**
模型算不清棋（19 路每步约 250+ 合法点，ASCII 坐标又不携带形状信息），
所以引擎额外提供 candidates()：挑出几个"还不错的点"给模型选，
模型下出来的棋既合法、又不至于太难看。

坐标约定：内部 (x, y) 均为 0 起算，x 向右、y 向下（左上角为 0,0）。
显示坐标：列用 A-T（跳过 I），行用 1-19 自下往上 —— 跟人类习惯一致。
"""

BLACK, WHITE, EMPTY = 1, 2, 0
STONE_CHARS = {EMPTY: ".", BLACK: "X", WHITE: "O"}
COL_LETTERS = "ABCDEFGHJKLMNOPQRST"          # 跳过 I
KOMI_DEFAULT = 7.5                            # 中国规则常用贴目


class GoBoard:
    """一块围棋盘 + 完整规则。所有会改状态的操作都进 history，支持 undo。"""

    # 把颜色常量挂到类上：外部写 b<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌oard.BLACK 也能用。
    # （之前只有模块级 ge.BLACK，调用方写 b.BLACK 会 AttributeError，
    #   而且 AI 出手那条路径是崩在 try 里，症状就是"对方永远不出手"。）
    BLACK = BLACK
    WHITE = WHITE
    EMPTY = EMPTY

    def __init__(self, size=19, komi=KOMI_DEFAULT):
        self.size = int(size)
        self.komi = float(komi)
        self.reset()

    # ---------- 基础 ----------
    def reset(self):
        n = self.size
        self.grid = [[EMPTY] * n for _ in range(n)]
        self.to_move = BLACK
        self.ko_point = None                  # 打劫禁着点 (x, y) 或 None
        self.captured = {BLACK: 0, WHITE: 0}  # 各方"提掉对方的子数"
        self.passes = 0                       # 连续 pass 次数
        self.history = []                     # 快照栈
        self.moves = []                       # [(x, y, color, captured) ...]
        self.last_move = None                 # (x, y) 或 None（pass）
        self.finished = False
        self.result = ""

    def _snapshot(self):
        return {
            "grid": [row[:] for row in self.grid],
            "to_move": self.to_move,
            "ko": self.ko_point,
            "captured": dict(self.captured),
            "passes": self.passes,
            "moves": list(self.moves),
            "last_move": self.last_move,
            "finished": self.finished,
            "result": self.result,
        }

    def _restore(self, s):
        self.grid = [row[:] for row in s["grid"]]
        self.to_move = s["to_move"]
        self.ko_point = s["ko"]
        self.captured = dict(s["captured"])
        self.passes = s["passes"]
        self.moves = list(s["moves"])
        self.last_move = s["last_move"]
        self.finished = s["finished"]
        self.result = s["result"]

    # ---------- 坐标 ----------
    def in_bounds(self, x, y):
        return 0 <= x < self.size and 0 <= y < self.size

    def neighbors(self, x, y):
        if x > 0: yield (x - 1, y)
        if x < self.size - 1: yield (x + 1, y)
        if y > 0: yield (x, y - 1)
        if y < self.size - 1: yield (x, y + 1)

    def to_display(self, x, y):
        """(x,y) → 'D4' 这样的人类坐标（行号自下往上）"""
        return "%s%d" % (COL_LETTERS[x], self.size - y)

    def from_display(self, s):
        """'D4' / 'd4' / 'Q16' → (x,y)；非法返回 None"""
        if not s:
            return None
        t = "".join(ch for ch in str(s).upper() if ch.isalnum())
        if len(t) < 2:
            return None
        col, rest = t[0], t[1:]
        if col not in COL_LETTERS[:self.size] or not rest.isdigit():
            return None
        x = COL_LETTERS.index(col)
        row = int(rest)
        if not (1 <= row <= self.size):
            return None
        return (x, self.size - row)

    # ---------- 棋块与气 ----------
    def group(self, x, y):
        """返回 (同色连通块坐标列表, 该块的气的集合)"""
        color = self.grid[y][x]
        if color == EMPTY:
            return [], set()
        seen = {(x, y)}
        stack = [(x, y)]
        libs = set()
        while stack:
            cx, cy = stack.pop()
            for nx, ny in self.neighbors(cx, cy):
                v = self.grid[ny][nx]
                if v == EMPTY:
                    libs.add((nx, ny))
                elif v == color and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return list(seen), libs

    def _apply_move(self, x, y, color):
        """落子 + 提子，返回 (提掉的坐标列表, 己方块是否无气)"""
        opp = WHITE if color == BLACK else BLACK
        self.grid[y][x] = color
        taken = []
        for nx, ny in self.neighbors(x, y):
            if self.grid[ny][nx] == opp:
                stones, libs = self.group(nx, ny)
                if not libs:
                    for sx, sy in stones:
                        self.grid[sy][sx] = EMPTY
                        taken.append((sx, sy))
        _, my_libs = self.group(x, y)
        return taken, (not my_libs)

    # ---------- 合法性 ----------
    def is_legal(self, x, y, color=None):
        """返回 (是否合法, 原因)。原因用于给模型解释为什么不行。"""
        color = color or self.to_move
        if self.finished:
            return False, "对局已结束"
        if not self.in_bounds(x, y):
            return False, "越界：坐标超出 %dx%d 棋盘" % (self.size, self.size)
        if self.grid[y][x] != EMPTY:
            return False, "%s 已经有子了" % self.to_display(x, y)
        if self.ko_point == (x, y):
            return False, "%s 是打劫禁着点（刚提过一子，不能立刻提回）" % self.to_display(x, y)
        # 试下：模拟一遍看是不是自杀
        snap = self._snapshot()
        taken, no_lib = self._apply_move(x, y, color)
        self._restore(snap)
        if no_lib and not taken:
            return False, "%s 是自杀手（自己这块会没气）" % self.to_display(x, y)
        return True, ""

    def legal_moves(self, color=None):
        color = color or self.to_move
        out = []
        for y in range(self.size):
            for x in range(self.size):
                if self.grid[y][x] != EMPTY:
                    continue
                if self.ko_point == (x, y):
                    continue
                ok, _ = self.is_legal(x, y, color)
                if ok:
                    out.append((x, y))
        return out

    # ---------- 落子 ----------
    def play(self, x, y, color=None):
        """落子。返回 {ok, reason, captured, coord, display}"""
        color = color or self.to_move
        ok, why = self.is_legal(x, y, color)
        if not ok:
            return {"ok": False, "reason": why}
        self.history.append(self._snapshot())

        captured, _ = self._apply_move(x, y, color)
        self.captured[color] += len(captured)

        # 打劫点：只提了一子，且自己刚落下的这块是单子且只有一口气 → 对方不能立刻提回
        new_ko = None
        if len(captured) == 1:
            stones, libs = self.group(x, y)
            if len(stones) == 1 and len(libs) == 1:
                new_ko = captured[0]
        self.ko_point = new_ko

        self.moves.append((x, y, color, len(captured)))
        self.last_move = (x, y)
        self.passes = 0
        self.to_move = WHITE if color == BLACK else BLACK
        return {
            "ok": True, "reason": "",
            "captured": [self.to_display(cx, cy) for cx, cy in captured],
            "coord": (x, y),
            "display": self.to_display(x, y),
        }

    def play_display(self, s, color=None):
        """按人类坐标落子，如 'D4'"""
        xy = self.from_display(s)
        if xy is None:
            return {"ok": False, "reason": "坐标看不懂：%r（应形如 D4 / Q16）" % (s,)}
        return self.play(xy[0], xy[1], color)

    def pass_turn(self, color=None):
        color = color or self.to_move
        self.history.append(self._snapshot())
        self.passes += 1
        self.ko_point = None
        self.last_move = None
        self.to_move = WHITE if color == BLACK else BLACK
        if self.passes >= 2:
            self.finish_by_scoring()
            return {"ok": True, "ended": True, "display": "停一手", "reason": ""}
        return {"ok": True, "ended": False, "display": "停一手", "reason": ""}

    def resign(self, color=None):
        color = color or self.to_move
        winner = "白" if color == BLACK else "黑"
        self.finished = True
        self.result = "%s中盘胜（对方认输）" % winner
        return {"ok": True, "result": self.result}

    def undo(self, steps=1):
        done = 0
        for _ in range(steps):
            if not self.history:
                break
            self._restore(self.history.pop())
            done += 1
        return {"ok": done > 0, "steps": done}

    # ---------- 数目（中国规则：子 + 空，双活按空算给双方） ----------
    def score(self):
        """返回 {black, white, komi, winner, detail}"""
        n = self.size
        black = white = 0
        seen = set()
        for y in range(n):
            for x in range(n):
                if self.grid[y][x] == BLACK:
                    black += 1
                elif self.grid[y][x] == WHITE:
                    white += 1
                elif (x, y) not in seen:
                    # 洪水填充这块空，看它被谁围住
                    area = []
                    stack = [(x, y)]
                    seen.add((x, y))
                    border = set()
                    while stack:
                        cx, cy = stack.pop()
                        area.append((cx, cy))
                        for nx, ny in self.neighbors(cx, cy):
                            v = self.grid[ny][nx]
                            if v == EMPTY and (nx, ny) not in seen:
                                seen.add((nx, ny))
                                stack.append((nx, ny))
                            elif v != EMPTY:
                                border.add(v)
                    if border == {BLACK}:
                        black += len(area)
                    elif border == {WHITE}:
                        white += len(area)
                    # 双方都挨着 = 双活/公气，不计
        white_with_komi = white + self.komi
        if black > white_with_komi:
            winner = "黑胜 %.1f 目" % (black - white_with_komi)
        else:
            winner = "白胜 %.1f 目" % (white_with_komi - black)
        return {
            "black": black, "white": white, "komi": self.komi,
            "white_total": white_with_komi,
            "captured": dict(self.captured),
            "winner": winner,
        }

    def finish_by_scoring(self):
        s = self.score()
        self.finished = True
        self.result = "双方停一手，终局。%s" % s["winner"]
        return self.result

    # ---------- 给模型看的文本 ----------
    def to_ascii(self, last_marker=True):
        """返回棋盘文本：列 A-T、行 1-19，X=黑 O=白 .=空"""
        n = self.size
        head = "   " + " ".join(COL_LETTERS[:n])
        rows = []
        for y in range(n):
            cells = []
            for x in range(n):
                v = self.grid[y][x]
                ch = STONE_CHARS[v]
                markers = []
                if v != EMPTY:
                    markers.append(ch)
                else:
                    markers.append(ch)
                cells.append(markers[0])
            rows.append("%2d %s" % (n - y, " ".join(cells)))
        tail = "   " + " ".join(COL_LETTERS[:n])
        out = [head] + rows + [tail]
        if last_marker and self.last_move:
            out.append("最后一手：%s" % self.to_display(*self.last_move))
        return "\n".join(out)

    def state(self):
        """给网页渲染用的 JSON（不返回引擎内部对象）"""
        n = self.size
        grid = []
        for y in range(n):
            grid.append([int(self.grid[y][x]) for x in range(n)])
        return {
            "size": n,
            "grid": grid,
            "to_move": "black" if self.to_move == BLACK else "white",
            "last_move": list(self.last_move) if self.last_move else None,
            "captured": {"black": self.captured[BLACK], "white": self.captured[WHITE]},
            "moves": len(self.moves),
            "finished": self.finished,
            "result": self.result,
            "komi": self.komi,
        }

    # ---------- 候选点启发式（让模型"选"而不是"算"） ----------
    # ---------- 让子 ----------
    # 标准让子顺序（19 路）：右上、左下、左上、右下、天元、然后两边中间
    HANDICAP_ORDER = [(15, 3), (3, 15), (3, 3), (15, 15), (9, 9),
                      (9, 3), (9, 15), (3, 9), (15, 9)]

    def setup_handicap(self, n):
        """摆让子局：黑先摆 n 个星位，之后由**白先走**（让子局规矩）。
        n=0 时就是分先。返回实际摆的子数。"""
        n = max(0, min(int(n or 0), 9))
        if n == 0:
            self.handicap = 0
            self.to_move = BLACK
            return 0
        for i in range(n):
            x, y = self.HANDICAP_ORDER[i]
            self.grid[y][x] = BLACK
        self.handicap = n
        self.to_move = WHITE
        return n

    def candidates(self, color=None, limit=5, style="balanced", mercy=0.0):
        """挑几个还不错的点给模型选。
        打分依据：能吃子 > 救自己被叫吃的块 > 叫吃对方 > 贴着已有棋子 >
        避免填自己的眼 > 三线/四线优先。
        style 让「角色的性格」真的影响下法（不只是影响台词）：
          balanced   均衡（默认）
          aggressive 好战：贴身、叫吃、追着打
          solid      稳重：连接、围地、避免贴身纠缠
          proud      高傲：爱占大场星位，不屑于贴身
          playful    随性：随机性大，偶尔下闲着
        mercy 放水概率（0~1）：关系越好，她越可能不走最强手 —— 让棋局有人情味。
        返回 [{coord, display, score, why}, ...]，按分从高到低。"""
        color = color or self.to_move
        opp = WHITE if color == BLACK else BLACK
        moves = self.legal_moves(color)
        if not moves:
            return []
        import random
        # 先找出双方处于叫吃（只剩一口气）的块，救/吃都要优先
        opp_atari_libs = set()
        my_atari_libs = set()
        checked = set()
        for y in range(self.size):
            for x in range(self.size):
                v = self.grid[y][x]
                if v == EMPTY or (x, y) in checked:
                    continue
                stones, libs = self.group(x, y)
                checked.update(stones)
                if len(libs) == 1:
                    if v == opp:
                        opp_atari_libs.update(libs)
                    else:
                        my_atari_libs.update(libs)

        stars = [(3, 3), (3, 9), (3, 15), (9, 3), (9, 9), (9, 15), (15, 3), (15, 9), (15, 15)] \
            if self.size == 19 else []
        early = len(self.moves) < self.size * 2

        scored = []
        for (x, y) in moves:
            s = 0.0
            why = []
            # 模拟这一手
            snap = self._snapshot()
            taken, _ = self._apply_move(x, y, color)
            self._restore(snap)
            if taken:
                s += 12.0 * len(taken)
                why.append("提%d子" % len(taken))
            if (x, y) in my_atari_libs:
                s += 7.0
                why.append("救自己被叫吃的块")
            if (x, y) in opp_atari_libs:
                s += 4.0
                why.append("叫吃对方")
            # 贴着已有棋子（局部性）
            near = 0
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    nx, ny = x + dx, y + dy
                    if self.in_bounds(nx, ny) and self.grid[ny][nx] != EMPTY:
                        near += 1
            if near == 0:
                s -= 6.0                     # 远离战场的孤点，别乱下
                why.append("远离战场")
            else:
                s += min(near, 6) * 0.6
            contact = sum(1 for nx, ny in self.neighbors(x, y) if self.grid[ny][nx] == opp)
            own_near = sum(1 for nx, ny in self.neighbors(x, y) if self.grid[ny][nx] == color)
            # 别填自己的眼（四面都是自己子）
            own_around = own_near
            empty_around = sum(1 for nx, ny in self.neighbors(x, y)
                               if self.grid[ny][nx] == EMPTY)
            if own_around >= 3 and empty_around == 0:
                s -= 10.0
                why.append("像自己的眼，别填")
            # 布局阶段偏好三线/四线
            edge_dist = min(x, y, self.size - 1 - x, self.size - 1 - y)
            if early:
                if edge_dist == 2:
                    s += 2.5
                elif edge_dist == 3:
                    s += 2.0
                elif edge_dist == 0:
                    s -= 3.0
            else:
                if edge_dist == 0:
                    s -= 1.5
            # 同样条件下偏向靠近最后一手（跟着打）
            if self.last_move:
                d = max(abs(x - self.last_move[0]), abs(y - self.last_move[1]))
                if d <= 3:
                    s += 1.2

            # ---- 性格偏置：这一步让"角色的下法"有区别 ----
            if style == "aggressive":
                if (x, y) in opp_atari_libs:
                    s += 3.0
                s += contact * 1.9
                if self.last_move:
                    d = max(abs(x - self.last_move[0]), abs(y - self.last_move[1]))
                    if d <= 2:
                        s += 1.6
                if contact:
                    why.append("贴身缠斗")
            elif style == "solid":
                s += own_near * 1.7
                s -= contact * 1.3
                if early and edge_dist in (2, 3):
                    s += 1.3
                if own_near:
                    why.append("稳健连接")
            elif style == "proud":
                if early and edge_dist in (3, 4):
                    s += 2.2
                if (x, y) in stars:
                    s += 2.6
                    why.append("占星位做大模样")
                s -= contact * 0.9
            elif style == "playful":
                s += random.uniform(-3.2, 3.2)
                if random.random() < 0.10:
                    why.append("随手下的一手")

            scored.append({"x": x, "y": y, "score": round(s, 2),
                           "display": self.to_display(x, y),
                           "why": "、".join(why) if why else "普通应手"})

        scored.sort(key=lambda m: -m["score"])
        # 一点随机性，免得每局一模一样
        top = scored[:max(limit * 3, limit)]
        random.shuffle(top)
        top.sort(key=lambda m: -m["score"])
        out = []
        for m in top[:limit]:
            out.append({"x": m["x"], "y": m["y"], "display": m["display"],
                        "score": m["score"], "why": m["why"]})
        # 放水：不以概率走最强手，而是从候选里挑一个次好的（显得"让着你"）
        if mercy > 0 and len(out) >= 3 and random.random() < mercy:
            k = random.randint(2, len(out) - 1)
            pick = out[k]
            pick = dict(pick, why=(pick["why"] + "、让着你一点"))
            out = [pick] + [o for i, o in enumerate(out) if i != k]
        return out


def new_game(size=19, komi=KOMI_DEFAULT):
    return GoBoard(size=size, komi=komi)
