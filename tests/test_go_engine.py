# -*- coding: utf-8 -*-
"""围棋规则引擎单测（不依赖界面、不依赖网络）
运行：python tests/test_go_engine.py

覆盖：坐标换算 / 提子 / 打劫 / 自杀 / 合法手 / 停一手终局 / 数目 / 悔棋 / 候选点
"""
import sys, os

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import go_engine as ge

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


def B(x, y):
    return ge.BLACK, x, y


print("== ① 坐标换算（列跳过 I，行号自下往上）==")
b = ge.new_game(19)
check(b.to_display(0, 18) == "A1", "左下角 = A1")
check(b.to_display(0, 0) == "A19", "左上角 = A19")
check(b.to_display(18, 18) == "T1", "右下角 = T1")
check(b.from_display("D4") == (3, 15), "D4 → (3,15)")
check(b.from_display("d4") == (3, 15), "小写 d4 也认")
check(b.from_display("I5") is None, "I5 非法（列跳过 I）")
check(b.from_display("U5") is None, "U5 越界")
check(b.from_display("A0") is None, "行号 0 非法")
check(b.from_display("乱写") is None, "乱写返回 None")
# 往返<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一致
same = all(b.from_display(b.to_display(x, y)) == (x, y)
           for x in range(19) for y in range(19))
check(same, "19×19 全部坐标往返一致")

print("== ② 提子 ==")
b = ge.new_game(19)
b.play(3, 3, ge.BLACK)
b.play(3, 4, ge.WHITE)          # 白子被围
b.play(2, 4, ge.BLACK)
b.play(4, 4, ge.BLACK)
check(b.grid[4][3] == ge.WHITE, "三面被围还没提（还剩一气）")
r = b.play(3, 5, ge.BLACK)      # 第四面 → 提掉
check(r["ok"] and r["captured"] == ["D15"], "第四面落下 → 提掉 D15，实际 %s" % r["captured"])
check(b.grid[4][3] == ge.EMPTY, "被提的点已清空")
check(b.captured[ge.BLACK] == 1, "黑方提子数 = 1")

print("== ③ 打劫（ko）==")
# 标准劫形（3x3 区域）：
#      x=0  x=1  x=2  x=3
# y=0   .    B    W    .
# y=1   B    W    .    W      ← 白(1,1) 只剩 (2,1) 一口气
# y=2   .    B    W    .
b3 = ge.new_game(19)
for (x, y, c) in [(1, 0, ge.BLACK), (2, 0, ge.WHITE),
                  (0, 1, ge.BLACK), (1, 1, ge.WHITE), (3, 1, ge.WHITE),
                  (1, 2, ge.BLACK), (2, 2, ge.WHITE)]:
    b3.grid[y][x] = c
b3.to_move = ge.BLACK
_st, _lib = b3.group(1, 1)
check(len(_lib) == 1 and (2, 1) in _lib,
      "摆出的劫形正确：白(1,1) 只剩 (2,1) 一口气，实际 %s" % sorted(_lib))

r = b3.play(2, 1, ge.BLACK)          # 黑提白(1,1)
check(r["ok"] and r["captured"] == ["B18"], "黑在 C18 提掉 B18，实际 %s" % r["captured"])
check(b3.ko_point == (1, 1), "打劫禁着点被记为 (1,1)=B18，实际 %s" % (b3.ko_point,))
ok_ko, why = b3.is_legal(1, 1, ge.WHITE)
check(not ok_ko, "白不能立刻提回（打劫禁着）")
check("打劫" in why, "拒绝理由里说明了是打劫：%s" % why)
# 别处下一手后，劫可以再提
b3.play(10, 10, ge.WHITE)
ok_now, _ = b3.is_legal(1, 1, ge.WHITE)
check(ok_now, "隔了一手之后，打劫解除，可以提回")

print("== ④ 自杀手 ==")
b = ge.new_game(19)
for (x, y, c) in [(1, 0, ge.BLACK), (0, 1, ge.BLACK)]:
    b.play(x, y, c)
illegal, why = b.is_legal(0, 0, ge.WHITE)
check(not illegal, "白下 A19 是自杀（角上被黑围死）")
check("自杀" in why, "拒绝理由说明了是自杀：%s" % why)
r = b.play(0, 0, ge.WHITE)
check(not r["ok"], "自杀手被拒绝")

print("== ⑤ 占位点不能重复下 ==")
b = ge.new_game(19)
b.play(3, 3, ge.BLACK)
r = b.play(3, 3, ge.WHITE)
check(not r["ok"] and "已经有子" in r["reason"], "重复落子被拒：%s" % r["reason"])

print("== ⑥ 合法手数量（开局 361，占一点少一点）==")
b = ge.new_game(19)
check(len(b.legal_moves()) == 361, "空盘 361 个合法点，实际 %d" % len(b.legal_moves()))
b.play(3, 3, ge.BLACK)
check(len(b.legal_moves()) == 360, "下一子后 360，实际 %d" % len(b.legal_moves()))

print("== ⑦ 停一手 / 终局 ==")
b = ge.new_game(19)
r1 = b.pass_turn(ge.BLACK)
check(r1["ok"] and not r1["ended"], "单方停一手，未终局")
r2 = b.pass_turn(ge.WHITE)
check(r2["ok"] and r2["ended"], "双方连续停一手 → 终局")
check(b.finished and "终局" in b.result, "状态标记为终局：%s" % b.result)

print("== ⑧ 数目（中国规则：子+空，白贴 7.5）==")
b = ge.new_game(9, komi=0.0)
# 左三列黑、右三列白，中间空着
for y in range(9):
    for x in range(3):
        b.grid[y][x] = ge.BLACK
    for x in range(6, 9):
        b.grid[y][x] = ge.WHITE
s = b.score()
check(s["black"] == 27, "黑 27 子，实际 %d" % s["black"])
check(s["white"] == 27, "白 27 子，实际 %d" % s["white"])
check("黑胜" in s["winner"] or "白胜" in s["winner"], "能算出胜负：%s" % s["winner"])
b2 = ge.new_game(19, komi=7.5)
s2 = b2.score()
check(s2["komi"] == 7.5 and "白胜" in s2["winner"], "空盘时白靠贴目胜：%s" % s2["winner"])

print("== ⑨ 悔棋 ==")
b = ge.new_game(19)
b.play(3, 3, ge.BLACK)
b.play(15, 15, ge.WHITE)
before = b.to_display(*b.last_move)
b.undo()
check(b.last_move and b.to_display(*b.last_move) == "D16", "悔一手回到黑 D16，实际 %s" % (b.to_display(*b.last_move) if b.last_move else None))
check(b.grid[15][15] == ge.EMPTY, "被悔掉的白子已清除")
check(b.to_move == ge.WHITE, "轮次回到白")
b.undo(); b.undo()
check(all(b.grid[y][x] == ge.EMPTY for y in range(19) for x in range(19)), "连续悔棋回到空盘")
r = b.undo()
check(not r["ok"], "空盘再悔 → 返回失败而不是抛异常")

print("== ⑩ 候选点启发式 ==")
b = ge.new_game(19)
cands = b.candidates(ge.BLACK, limit=5)
check(len(cands) == 5, "给出 5 个候选，实际 %d" % len(cands))
check(all(b.is_legal(c["x"], c["y"], ge.BLACK)[0] for c in cands), "候选点全部合法")
check(len(set(c["display"] for c in cands)) == 5, "候选点互不重复")
check(all(c["display"] and c["why"] for c in cands), "每个候选都带坐标和理由")
# 有子可吃时必须优先吃
b2 = ge.new_game(19)
b2.play(3, 3, ge.BLACK); b2.play(3, 4, ge.WHITE)
b2.play(2, 4, ge.BLACK); b2.play(4, 4, ge.BLACK)
b2.to_move = ge.BLACK
c2 = b2.candidates(ge.BLACK, limit=3)
check("提1子" in c2[0]["why"], "能吃子时优先吃：%s（%s）" % (c2[0]["display"], c2[0]["why"]))

print("== ⑪ 给模型看的文本 ==")
b = ge.new_game(19)
b.play(3, 3, ge.BLACK)
txt = b.to_ascii()
lines = txt.split("\n")
check(len(lines) == 22, "19 行棋盘 + 表头 + 表尾 + 最后一手 = 22 行，实际 %d" % len(lines))
check("A" in lines[0] and "T" in lines[0], "表头含 A..T 列标")
check("X" in txt and "." in txt, "文本里有黑子和空点")
check("最后一手：D16" in txt, "文本标出了最后一手")

print("== ⑫ 状态导出（给网页渲染）==")
b = ge.new_game(19)
b.play(3, 3, ge.BLACK)
st = b.state()
check(st["size"] == 19 and len(st["grid"]) == 19 and len(st["grid"][0]) == 19, "导出 19×19 网格")
check(st["grid"][3][3] == 1 and st["to_move"] == "white", "落子与轮次正确")
check(st["last_move"] == [3, 3], "最后一手坐标正确")

print("== ⑬ 让子局 ==")
b = ge.new_game(19)
check(b.setup_handicap(4) == 4, "摆 4 子")
check(sum(1 for y in range(19) for x in range(19)
          if b.grid[y][x] == ge.BLACK) == 4, "盘上正好 4 颗黑子")
check(b.to_move == ge.WHITE, "让子局由白先走（不是黑）")
check(b.grid[3][15] == ge.BLACK and b.grid[15][3] == ge.BLACK, "摆在星位上")
check(b.handicap == 4, "记下了让子数")
b0 = ge.new_game(19)
check(b0.setup_handicap(0) == 0 and b0.to_move == ge.BLACK, "0 子 = 分先，黑先走")

print("== ⑭ 放水（好感度高时故意不走最强手）==")
b = ge.new_game(19)
for c in ['D4', 'Q16', 'D16', 'Q4', 'K10']:
    b.play(*b.from_display(c), b.to_move)
same = diff = 0
for _ in range(40):
    c0 = b.candidates(b.to_move, limit=4, mercy=0.0)[0]["display"]
    c1 = b.candidates(b.to_move, limit=4, mercy=1.0)[0]["display"]
    if c0 == c1:
        same += 1
    else:
        diff += 1
check(diff > 0, "放水=1.0 时首选会变（%d/40 次不同）" % diff)
ms = b.candidates(b.to_move, limit=4, mercy=1.0)
check(any("让着你" in c["why"] for c in ms), "放水的那手会标出「让着你一点」")
check(len(b.candidates(b.to_move, limit=4, mercy=0.0)) == 4, "放水不改候选数量")

print("")
print("通过 %d 项，失败 %d 项" % (ok, bad))
sys.exit(1 if bad else 0)
