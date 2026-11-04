# -*- coding: utf-8 -*-
"""mem_policy 的测试：窗口夹取、条数阈值、2 小时空闲、失败消息不计入。

纯逻辑，时间由测试自己给，不碰网络与磁盘。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mem_policy as P   # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def msgs(n, **kw):
    out = []
    for i in range(n):
        m = {"role": "user" if i % 2 == 0 else "assistant", "content": u"第%d条" % i}
        m.update(kw)
        out.append(m)
    return out


def main():
    print(u"\n== ① 场景默认判定 ==")
    check(u"单选 → 私聊", P.scene_for(["咲"]) == "private")
    check(u"多选 → 群聊", P.scene_for(["咲", "老约翰"]) == "group")
    check(u"空选 → 私聊", P.scene_for([]) == "private")

    print(u"\n== ② 窗口夹在 24~36 ==")
    check(u"私聊默认 30", P.window_size("private") == 30)
    check(u"群聊默认大一点（32）", P.window_size("group") == 32)
    check(u"要 5 条被抬到 24", P.window_size("private", 5) == 24)
    check(u"要 999 条被压到 36", P.window_size("private", 999) == 36)
    check(u"乱传也能兜住", P.window_size("private", "abc") == 30)

    print(u"\n== ③ 阈值：私聊 32 / 群聊 48 ==")
    check(u"私聊 32 条不压", not P.needs_compress(32, "private"))
    check(u"私聊 33 条要压", P.needs_compress(33, "private"))
    check(u"群聊 48 条不压", not P.needs_compress(48, "group"))
    check(u"群聊 49 条要压", P.needs_compress(49, "group"))

    print(u"\n== ④ 切窗：最后 N 条留下，更早的进 dropped ==")
    win, dropped = P.split(msgs(50), "private")
    check(u"留下 30 条", len(win) == 30)
    check(u"丢掉 20 条", len(dropped) == 20)
    check(u"留下的是最近 30 条", win[0]["content"] == u"第20条")
    check(u"丢掉的是最早的", dropped[0]["content"] == u"第0条")
    check(u"不足窗口时全留", P.split(msgs(10), "private")[1] == [])

    print(u"\n== ⑤ 失败消息不进上下文、也不计数 ==")
    bad = msgs(40)
    bad[39]["failed"] = True
    bad[0]["status"] = "error"
    win, dropped = P.split(bad, "private")
    check(u"失败的那条不在 window 里", all(not m.get("failed") for m in win))
    check(u"失败的那条也不在 dropped 里", all(m.get("status") != "error" for m in dropped))
    check(u"有效条数 = 38", len(P.effective(bad)) == 38)
    check(u"带 error 且没正文算失败", P.is_failed({"role": "assistant", "error": "timeout"}))
    check(u"带 error 但有正文不算失败",
          not P.is_failed({"role": "assistant", "error": "warn", "content": u"照常"}))
    check(u"should_send 对失败消息说否", not P.should_send({"content": "", "failed": True}))

    print(u"\n== ⑥ 2 小时空闲压缩 ==")
    now = 100000.0
    check(u"从没压过 → 要压", P.needs_idle_compress(None, now))
    check(u"刚压过 → 不压", not P.needs_idle_compress(now - 60, now))
    check(u"差 1 秒到 2 小时 → 不压", not P.needs_idle_compress(now - P.IDLE_SECONDS + 1, now))
    check(u"满 2 小时 → 压", P.needs_idle_compress(now - P.IDLE_SECONDS, now))
    check(u"没有新内容就不压", not P.needs_idle_compress(None, now, has_new=False))

    print(u"\n== ⑦ plan()：一次给出这一轮的决定 ==")
    p1 = P.plan(msgs(20), "private")
    check(u"20 条：窗口全留、不压", p1["kept"] == 20 and not p1["compress"])
    p2 = P.plan(msgs(50), "private")
    check(u"50 条：留 30 丢 20", p2["kept"] == 30 and p2["dropped_count"] == 20)
    check(u"50 条：触发压缩", p2["compress"])
    check(u"理由说清楚了（含条数）", u"阈值" in p2["reason"] or u"窗口" in p2["reason"])
    p3 = P.plan(msgs(10), "private", last_compress_ts=1.0, now=1.0 + P.IDLE_SECONDS + 5)
    check(u"只有空闲触发时也算要压", p3["compress"] and u"2 小时" in p3["reason"])
    p4 = P.plan(msgs(10), "group", last_compress_ts=None, now=None)
    check(u"不传 now 就不按时间判", not p4["compress"])

    print(u"\n== ⑧ 不改原对象 ==")
    src = msgs(5)
    before = [dict(m) for m in src]
    P.split(src, "private")
    check(u"入参没被就地修改", src == before)

    print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌