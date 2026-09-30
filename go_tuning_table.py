# -*- coding: utf-8 -*-
"""打印好感度→棋局设定的实际生效表（调档位时照着看）"""
import importlib.util, os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import go_engine as ge

spec = importlib.util.spec_from_file_location(
    "app_for_table", os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["app_for_table"] = mod
spec.loader.exec_module(mod)
G = mod.HtmlApp


class Stub:
    def __init__(self, human, aff):
        self._go_human = human
        self.core = type("C", (), {"mechanism_state": {"affection": aff}})()

    def _go_settings(self):
        return G._go_settings(self)


for _n in dir(G):                      # GO_* 常量搬到桩上
    if _n.startswith("GO_"):
        setattr(Stub, _n, getattr(G, _n))


print("让子上限 GO_MAX_HANDICAP =", G.GO_MAX_HANDICAP)
print("1 子折合贴目 GO_KOMI_PER_HANDICAP =", G.GO_KOMI_PER_HANDICAP)
print()
print("档位表 GO_AFF_TIERS（好感下限, 让子, 放水, 描述）:")
for row in G.GO_AFF_TIERS:
    print("   ", row)
print()
print("实际采样（玩家执黑）：")
print("   %-6s %-8s %-10s %s" % ("好感", "让子", "放水", "关系描述"))
for aff in (0, 30, 49, 50, 60, 69, 70, 84, 85, 100):
    st = G._go_settings(Stub("black", aff))
    print("   %-6d %-8d %-10s %s" % (aff, st["handicap"],
                                     "%.0f%%" % (st["mercy"] * 100), st["mood"]))
print()
print("实际采样（玩家执白 → 改成多贴目）：")
for aff in (0, 50, 85, 100):
    st = G._go_settings(Stub("white", aff))
    print("   好感 %-4d 让子 %d  多贴目 %.1f" % (aff, st["handicap"], st["komi_extra"]))
print()
mx = max(G._go_settings(Stub("black", a))["handicap"] for a in range(101))
print("0~100 全区间最大让子数:", mx, "（上限 %d）" % G.GO_MAX_HANDICAP)
print("结论:", "符合「最多 1 子」" if mx <= G.GO_MAX_HANDICAP <= 1 else "!! 超出上限")
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌