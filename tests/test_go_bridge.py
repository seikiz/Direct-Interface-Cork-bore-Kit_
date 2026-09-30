# -*- coding: utf-8 -*-
"""围棋注入桥单测：坐标解析 + 注入文本（不联网、不起界面）
运行：python tests/test_go_bridge.py

模型回复里会出现各种花样的坐标写法，这里专门把"解析"这一环钉死；
解析不出来棋局就停住，所以这是整条链路最容易出事的地方。
"""
import sys, os

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import go_engine as ge
import html_app   # 只为拿 HtmlApp 的方法（不实例化，避免起 ChatCore）

ok = 0
bad = 0


def check(cond, msg):
    global ok, bad
    if cond:
        ok += 1
        print("  OK   " + msg)
    else:
        bad += 1
        print("  FAIL " + msg)


class Stub:
    """够 HtmlApp 那几个围棋方法用的最小桩"""
    def __init__(self, board, human="black", roles=None, aff=None):
        self._go = board
        self._go_human = human
        self._go_log = []
        self.core = type("Core", (), {
            "active_roles": roles or [],
            "mechanism_state": ({"affection": aff} if aff is not None else {}),
        })()

    def _go_game(self):
        return self._go

    def _go_note(self, text):
        self._go_log.append(text)


G = html_app.HtmlApp

# 把真实方法/常量绑到桩上 —— 测的仍是 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌HtmlApp 里的实现，不是复制品。
# GO_* 常量自动搬运：手工逐个列的话，以后在 HtmlApp 里加一个就会被忘掉，
# 表现为桩上 AttributeError（就像 GO_MAX_HANDICAP 刚加时那样）。
for _n in dir(G):
    if _n.startswith("GO_"):
        setattr(Stub, _n, getattr(G, _n))
Stub._go_style = G._go_style
Stub._go_settings = G._go_settings

print("== ① 常规写法 ==")
b = ge.new_game(19)
s = Stub(b)
for reply, want, label in [
    ("我下在 Q16。", "Q16", "「我下在 Q16」"),
    ("那我走 D4 吧。", "D4", "「那我走 D4」"),
    ("落子：c3", "C3", "小写 c3 也认"),
    ("Q16", "Q16", "光秃秃一个坐标"),
    ("我落在 Q16 这个星位。", "Q16", "坐标夹在句子里"),
    ("嗯……(Q16)", "Q16", "带括号"),
]:
    xy = G._go_parse_move(s, reply)
    got = b.to_display(*xy) if xy else None
    check(got == want, "%s → %s（期望 %s）" % (label, got, want))

print("== ② 干扰：提到别的坐标 ==")
b = ge.new_game(19)
b.play(*b.from_display("D4"), ge.BLACK)          # D4 已被占
s = Stub(b, human="white")                        # 轮白（AI）
xy = G._go_parse_move(s, "你下在 D4，那我下 Q16。")
check(xy and b.to_display(*xy) == "Q16",
      "同时提到两个坐标时，取能下的那个（Q16），实际 %s" % (b.to_display(*xy) if xy else None))

print("== ③ 全是被占的点 → 解析不出来（交给兜底）==")
b = ge.new_game(19)
for c in ("D4", "Q16", "C3"):
    b.play(*b.from_display(c), b.to_move)
s = Stub(b)
xy = G._go_parse_move(s, "我想下 D4，不然 Q16，再不然 C3。")
check(xy is None, "三个点都占了 → 返回 None，实际 %s" % (b.to_display(*xy) if xy else None))

print("== ④ 根本不提坐标 ==")
b = ge.new_game(19)
s = Stub(b)
for reply in ("", "我先想想。", "这局看起来你占优呢。", "我下在星位附近。",
              "行吧。", None):
    xy = G._go_parse_move(s, reply or "")
    check(xy is None, "「%s」→ None" % (str(reply)[:16] or "(空)"))

print("== ⑤ 不能下在打劫禁着点 ==")
b = ge.new_game(19)
for (x, y, c) in [(1, 0, ge.BLACK), (2, 0, ge.WHITE),
                  (0, 1, ge.BLACK), (1, 1, ge.WHITE), (3, 1, ge.WHITE),
                  (1, 2, ge.BLACK), (2, 2, ge.WHITE)]:
    b.grid[y][x] = c
b.to_move = ge.BLACK
b.play(2, 1, ge.BLACK)          # 形成劫，禁着点 B18
s = Stub(b, human="white")      # 轮白（AI）
xy = G._go_parse_move(s, "我提回 B18！")
check(xy is None, "打劫禁着点被排除，实际 %s" % (b.to_display(*xy) if xy else None))

print("== ⑥ 候选点优先 ==")
b = ge.new_game(19)
b.play(*b.from_display("D4"), ge.BLACK)
s = Stub(b, human="white")
cands = b.candidates(b.to_move, limit=6)
cset = {c["display"] for c in cands}
if cands:
    c0, c1 = cands[0]["display"], cands[1]["display"]
    xy = G._go_parse_move(s, "随便提一句 %s，其实我下 %s。" % ("A1", c1))
    check(xy and b.to_display(*xy) == c1, "提到多个时优先命中候选点 %s" % c1)

print("== ⑦ 注入文本（模型看到的东西）==")
b = ge.new_game(19)
b.play(*b.from_display("D4"), ge.BLACK)
s = Stub(b, human="white")           # 玩家执白 → AI 执黑
txt = G._go_prompt_block(s)
check("你执黑" in txt, "说明了 AI 执黑（玩家执白）")
check("对方执白" in txt, "说明了对手执什么色")
check("候选点" in txt, "包含候选点段")
check("坐标" in txt and "我下在" in txt, "要求模型给出坐标并给了写法示例")
check("空点" in txt and "打劫" in txt, "提醒了合法性（空点 / 打劫点不能下）")
check("台词" in txt, "要求带上角色台词")
head = [ln for ln in txt.split("\n") if ln.strip().startswith("A ") or "A B C" in ln]
check(bool(head), "棋盘文本含 A..T 列表头")
check("X" in txt, "棋盘里有黑子标记 X")
check("最后一手：D4" in txt, "标出了最后一手（D4）")
# 换个颜色再验一次
b9 = ge.new_game(19)
b9.play(*b9.from_display("D4"), ge.BLACK)
s9 = Stub(b9, human="black")         # 玩家执黑 → AI 执白
t9 = G._go_prompt_block(s9)
check("你执白" in t9 and "对方执黑" in t9, "玩家执黑时 AI 说明自己是白")

print("== ⑧ 注入文本随棋盘变化 ==")
b2 = ge.new_game(19)
for c in ("D4", "Q16", "D16"):
    b2.play(*b2.from_display(c), b2.to_move)
s2 = Stub(b2, human="white")
t2 = G._go_prompt_block(s2)
check(t2.count("X") + t2.count("O") >= 3, "棋盘上 3 颗子都体现在文本里")
check(len(t2) != len(txt), "不同局面生成的注入文本不同")

print("== ⑨ 棋风：从角色卡推断性格 → 影响落子 ==")
b = ge.new_game(19)
cases = [
    ([{"personality": "她性格暴躁，好战，喜欢挑衅对手"}], None, "aggressive", "暴躁好战"),
    ([{"personality": "冷静缜密，做事稳重，很有耐心"}], None, "solid", "冷静稳重"),
    ([{"personality": "高傲的天才，目中无人，自恋"}], None, "proud", "高傲天才"),
    ([{"personality": "随性又贪玩，整天漫不经心"}], None, "playful", "随性贪玩"),
    ([{"personality": "一个普通的女孩"}], None, "balanced", "没明显倾向"),
    ([{"description": "爱笑，开朗，好奇"}], None, "playful", "开朗好奇（走 description）"),
    ([], 10, "aggressive", "没性格文本 + 好感度 10 → 偏冲"),
    ([], 90, "solid", "没性格文本 + 好感度 90 → 偏稳"),
    ([], 50, "balanced", "好感度正常 → 均衡"),
]
for roles, aff, want, label in cases:
    s = Stub(b, roles=roles, aff=aff)
    got = G._go_style(s)
    check(got == want, "%s → %s（期望 %s）" % (label, got, want))

print("== ⑩ 棋风真的改变候选点 ==")
b2 = ge.new_game(19)
for c in ['D4', 'Q16', 'D16', 'Q4', 'K10', 'K11', 'L10', 'D10', 'Q10',
          'C10', 'C11']:
    b2.play(*b2.from_display(c), b2.to_move)
ag = [c["display"] for c in b2.candidates(b2.to_move, limit=3, style="aggressive")]
so = [c["display"] for c in b2.candidates(b2.to_move, limit=3, style="solid")]
ba = [c["display"] for c in b2.candidates(b2.to_move, limit=3, style="balanced")]
check(ag != ba or so != ba, "好战/稳重 与 均衡 给出的候选不同")
agg_why = " ".join(c["why"] for c in b2.candidates(b2.to_move, limit=3, style="aggressive"))
check("贴身" in agg_why, "好战棋风偏好贴身缠斗：%s" % agg_why)
sol_why = " ".join(c["why"] for c in b2.candidates(b2.to_move, limit=3, style="solid"))
check("连接" in sol_why or "稳健" in sol_why, "稳重棋风偏好连接：%s" % sol_why)
check(len(set(ag) & set(so)) < 3, "两种棋风的前三候选不完全重合")

print("== ⑪ 棋风写进注入文本 ==")
b3 = ge.new_game(19)
b3.play(*b3.from_display("D4"), ge.BLACK)
s3 = Stub(b3, human="white", roles=[{"personality": "暴躁好战"}])
t3 = G._go_prompt_block(s3)
check("棋风" in t3, "注入文本里说明了棋风")
check("好战" in t3, "写的是推断出来的具体棋风（好战）：%s" %
      [ln for ln in t3.split("\n") if "棋风" in ln][:1])

print("== ⑫ 好感度决定棋局设定（让子 + 放水）==")
# 这里刻意不写死具体档位数值 —— 档位是要被反复调的。
# 只锁「不变量」：上限、单调性、边界。作者改表时测试不会拦着他，
# 但一旦让子超过上限就会当场报出来。
b = ge.new_game(19)
check(isinstance(G.GO_MAX_HANDICAP, int) and G.GO_MAX_HANDICAP >= 0,
      "GO_MAX_HANDICAP 已定义：%r" % (G.GO_MAX_HANDICAP,))
check(G.GO_MAX_HANDICAP <= 1, "让子数上限不超过 1 子：%d" % G.GO_MAX_HANDICAP)

# 表里每个档位本身都不能越过上限
over = [(lo, h) for lo, h, _m, _l in G.GO_AFF_TIERS if h > G.GO_MAX_HANDICAP]
check(not over, "档位表里没有超过上限的让子数：%s" % over)

# 覆盖 0~100 全区间扫一遍，确保任何好感度下都不会多让子
worst = 0
for aff in range(0, 101):
    st = G._go_settings(Stub(b, human="black", aff=aff))
    worst = max(worst, st["handicap"])
    if st["mercy"] < 0 or st["mercy"] > 1:
        check(False, "好感度 %d 的放水概率越界：%r" % (aff, st["mercy"]))
        break
else:
    check(True, "0~100 好感度放水概率都在 0~1 之间")
check(worst <= G.GO_MAX_HANDICAP, "全区间最大让子数 %d ≤ 上限 %d"
      % (worst, G.GO_MAX_HANDICAP))

# 单调性：好感度越高，让子数不会变少、放水概率不会变小
prev = None
mono = True
for aff in range(0, 101):
    st = G._go_settings(Stub(b, human="black", aff=aff))
    cur = (st["handicap"], st["mercy"])
    if prev is not None and (cur[0] < prev[0] or cur[1] < prev[1] - 1e-9):
        mono = False
        check(False, "好感度 %d 处出现回退：%r -> %r" % (aff, prev, cur))
        break
    prev = cur
if mono:
    check(True, "让子数与放水概率随好感度单调不降")

# 边界：最低档必须是「不留情」，最高好感度必须真的给到上限
st_lo = G._go_settings(Stub(b, human="black", aff=0))
st_hi = G._go_settings(Stub(b, human="black", aff=100))
check(st_lo["handicap"] == 0 and st_lo["mercy"] == 0.0,
      "好感度 0 → 不让子也不放水：%r" % (st_lo,))
check(st_hi["handicap"] == G.GO_MAX_HANDICAP,
      "好感度 100 → 让满上限 %d 子：%d" % (G.GO_MAX_HANDICAP, st_hi["handicap"]))

# 玩家执白：不给让子，改成多贴目
st = G._go_settings(Stub(b, human="white", aff=100))
check(st["handicap"] == 0 and st["komi_extra"] > 0,
      "玩家执白时不给让子，改成多贴目 %.1f 目" % st["komi_extra"])
check(abs(st["komi_extra"] - G.GO_MAX_HANDICAP * G.GO_KOMI_PER_HANDICAP) < 1e-9,
      "执白贴目 = 上限子数 × %.1f" % G.GO_KOMI_PER_HANDICAP)
check("mood" in st and st["mood"], "带上了关系描述：%s" % st["mood"])

# 让 1 子必须真的能摆到盘上（引擎对 1 子的处理容易和分先混淆）
b1 = ge.new_game(19)
placed = b1.setup_handicap(1)
check(placed == 1, "setup_handicap(1) 真的摆了 1 子：%d" % placed)
check(sum(row.count(ge.BLACK) for row in b1.grid) == 1, "盘上确实只有 1 个黑子")
check(b1.to_move == ge.WHITE, "让子局由白先走")

print("== ⑬ 设定写进注入文本 ==")
b2 = ge.new_game(19)
b2.play(*b2.from_display("D4"), ge.BLACK)
t_low = G._go_prompt_block(Stub(b2, human="white", aff=10))
t_high = G._go_prompt_block(Stub(b2, human="black", aff=95))
check("分先对局" in t_low and "不必留情" in t_low, "低好感度 → 提示「分先、不必留情」")
check("让子局" in t_high, "高好感度 → 提示这是让子局")
# 不写死子数（档位要反复调），只要求注入文本里的数字和设定一致
_want = G._go_settings(Stub(b2, human="black", aff=95))["handicap"]
check("让了对方 %d 子" % _want in t_high,
      "写明了让子数 %d" % _want)

print("== ⑭ AI 出手链路（对方不出手就是这段崩了）==")


class AIStub:
    """能跑 _go_ai_turn / _go_after_reply 的桩：记下发出去的话和 pending_event"""
    def __init__(self, board, human="black", roles=None, aff=None):
        self._go = board
        self._go_human = human
        self._go_log = []
        self.sent = []
        self._go_retry = 0
        core = type("C", (), {})()
        core.active_roles = roles or []
        core.mechanism_state = ({"affection": aff} if aff is not None else {})
        core.pending_event = None
        self.core = core

    def _go_game(self):
        return self._go

    def _go_note(self, t):
        self._go_log.append(t)

    def _append_sys(self, t):
        self._go_log.append(t)

    def _send_text(self, text, hidden, image, is_choice=False):
        self.sent.append(text)


for _m in ("_go_prompt_block", "_go_style", "_go_settings", "_go_ai_turn",
           "_go_after_reply", "_go_parse_move", "_go_ai_first"):
    setattr(AIStub, _m, getattr(G, _m))
for _n in dir(G):                      # 同 Stub：GO_* 常量一并搬过去
    if _n.startswith("GO_"):
        setattr(AIStub, _n, getattr(G, _n))

# ① 人类（黑）落子后，AI 必须被叫起来出手
b = ge.new_game(19)
s = AIStub(b, human="black")
b.play(*b.from_display("D4"), ge.BLACK)          # 人类下 D4
check(b.to_move == ge.WHITE, "人类落子后轮到白")
G._go_ai_turn(s, "我下在 D4。")
check(s.core.pending_event is not None, "AI 出手时注入了 pending_event（不崩）")
check(s.core.pending_event and "围棋" in str(s.core.pending_event.get("name", "")),
      "注入的是围棋事件：%s" % (s.core.pending_event or {}).get("name"))
check(len(s.sent) == 1, "确实发出了请求（1 次），实际 %d" % len(s.sent))
check("我下在 D4" in (s.sent[0] if s.sent else ""), "把人类这一手告诉了模型")

# ② 模型回复里有合法坐标 → 落到盘上
ok_before = sum(1 for y in range(19) for x in range(19) if b.grid[y][x] == ge.WHITE)
G._go_after_reply(s, "哼，我下在 Q16，别得意。")
ok_after = sum(1 for y in range(19) for x in range(19) if b.grid[y][x] == ge.WHITE)
check(ok_after == ok_before + 1, "模型给坐标 → 白子真的落上了（%d→%d）" % (ok_before, ok_after))
check(b.grid[3][15] == ge.WHITE, "落在说的那个点上（Q16）")
check(b.to_move == ge.BLACK, "落完轮到人类")

# ③ 回复里没有坐标 → 先驳回重选，再失败就引擎兜底
b2 = ge.new_game(19)
s2 = AIStub(b2, human="black")
b2.play(*b2.from_display("D4"), ge.BLACK)
G._go_after_reply(s2, "我先想想，这局有点难。")
check(s2._go_retry == 1, "第一次没解析出坐标 → 记下要驳回重选")
check(any("重选" in x for x in s2._go_log), "日志里写了驳回：%s" % s2._go_log[-1:])
before = sum(1 for y in range(19) for x in range(19) if b2.grid[y][x] == ge.WHITE)
G._go_after_reply(s2, "还是不知道下哪。")          # 第二次仍失败 → 兜底
after = sum(1 for y in range(19) for x in range(19) if b2.grid[y][x] == ge.WHITE)
check(after == before + 1, "两次都不行 → 引擎代落，棋局不停住（%d→%d）" % (before, after))
check(any("代落" in x for x in s2._go_log), "日志标明了是裁判代落：%s" % s2._go_log[-1:])

# ④ 玩家执白时，开局要叫 AI 先走
b3 = ge.new_game(19)
s3 = AIStub(b3, human="white")
G._go_ai_first(s3)
check(s3.core.pending_event is not None, "玩家执白 → 开局 AI 先走（不崩）")
check(len(s3.sent) == 1, "并且发了请求")

# ⑤ 人类执黑时，开局不该叫 AI
b4 = ge.new_game(19)
s4 = AIStub(b4, human="black")
G._go_ai_first(s4)
check(s4.core.pending_event is None and not s4.sent, "玩家执黑 → 等人类先下，AI 不抢")

# ⑥ 不是 AI 的回合时，回复里就算有坐标也不能落子（防止误伤）
b5 = ge.new_game(19)
s5 = AIStub(b5, human="black")
G._go_after_reply(s5, "我下在 Q16。")
check(sum(1 for y in range(19) for x in range(19) if b5.grid[y][x] != ge.EMPTY) == 0,
      "轮到人类时，模型回复不会擅自落子")

print("")
print("通过 %d 项，失败 %d 项" % (ok, bad))
sys.exit(1 if bad else 0)
