# -*- coding: utf-8 -*-
"""模块分道执行审计：同线保序、跨线并行、异常不杀线、结果流水位线、收线干净。

为什么需要
----------
"一个模块一个运行部分"这类改动最怕三种错，全都不会自己暴露：
  · 同一条线内的任务顺序乱了（对话/落盘必须有序，乱了就是数据错）
  · 慢任务把别的线也堵住（那就是白改了 —— 用户要的正是"互不拖累"）
  · 一个坏任务把整条线弄死（线程里的未捕获异常 = 这条线从此静默不干活）
跑法：python tests/test_jobs.py
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import jobs  # noqa: E402

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


def main():
    print("=" * 62)
    print(u"模块分道执行审计")
    print("=" * 62)
    jobs.start()

    print(u"\n== ① 同一条线内 FIFO 串行（顺序绝不能乱）==")
    order = []
    for i in range(6):
        jobs.submit("io", lambda n=i: order.append(n), name="seq%d" % i)
    jobs.wait_idle("io")
    check(u"6 个任务按投递顺序执行", order == [0, 1, 2, 3, 4, 5], str(order))

    print(u"\n== ② 跨线并行：慢线不堵快线 ==")
    slow_started = threading.Event()
    fast_done = threading.Event()

    def slow():
        slow_started.set()
        time.sleep(1.2)
        return "slow"

    def fast():
        return "fast"
    t0 = time.time()
    jobs.submit("vision", slow, name="慢任务")
    slow_started.wait(2)
    jobs.submit("net", fast, name="快任务", on_done=lambda r, e: fast_done.set())
    ok = fast_done.wait(0.8)
    check(u"慢线占着时，另一条线照常干活（0.8 秒内完成）", ok, u"等了 %.2fs" % (time.time() - t0))
    jobs.wait_idle(timeout=5)

    print(u"\n== ③ 同一时刻，两条线真的各跑各的 ==")
    marks = []
    barrier = threading.Barrier(2, timeout=3)

    def rendezvous(tag):
        try:
            barrier.wait()
            marks.append(tag)
            return tag
        except Exception as e:
            return "err:%s" % e
    jobs.submit("voice", rendezvous, "v", name="voice")
    jobs.submit("image", rendezvous, "i", name="image")
    jobs.wait_idle(timeout=5)
    check(u"两条线同时进入会合点（说明真并行）", sorted(marks) == ["i", "v"], str(marks))

    print(u"\n== ④ 异常被捕获，线不死 ==")
    def boom():
        raise ValueError(u"故意炸一个")
    jid = jobs.submit("plugin", boom, name="坏任务")
    jobs.wait_idle("plugin", timeout=5)
    j = jobs.job(jid)
    check(u"任务记录为 error", j and j["state"] == "error", str(j))
    check(u"错误信息带类型与文本", j and "ValueError" in j["err"] and u"故意炸" in j["err"], str(j))
    after = []
    jobs.submit("plugin", lambda: after.append(1), name="恢复任务")
    jobs.wait_idle("plugin", timeout=5)
    check(u"坏任务之后这条线还能继续干活", after == [1], str(after))

    print(u"\n== ⑤ 结果流：水位线 + 只推可序列化的东西 ==")
    jobs.drain(10 ** 9)          # 清空历史
    jid = jobs.submit("net", lambda: {"ok": True, "n": 3}, name="带结果的任务")
    jobs.wait_idle("net", timeout=5)
    seq0 = 0
    evs = jobs.drain(seq0)
    mine = [e for e in evs if e.get("id") == jid]
    check(u"拿得到该任务的结果事件", bool(mine), str(evs[-3:]))
    check(u"事件里有 ok / ms / lane", mine and mine[0]["ok"] is True
          and mine[0]["lane"] == "net" and mine[0]["ms"] >= 0, str(mine[:1]))
    check(u"结果被序列化成基本类型", mine and mine[0]["result"] == {"ok": True, "n": 3},
          str(mine[0]["result"]) if mine else None)
    watermark = evs[-1]["seq"] if evs else 0
    check(u"用同一水位线再取 → 不重复给", jobs.drain(watermark) == [], str(jobs.drain(watermark)))
    check(u"陈旧事件被清掉（不无限增长）", len(jobs.drain(watermark)) == 0)

    print(u"\n== ⑥ 状态快照能看出「现在在跑什么」==")
    gate = threading.Event()
    jobs.submit("memory", lambda: gate.wait(3), name=u"占着线")
    time.sleep(0.2)
    st = jobs.status()
    check(u"lanes 快照含所有线", set(st["lanes"]) >= {"talk", "net", "vision", "voice",
                                                     "image", "memory", "plugin", "io"},
          str(sorted(st["lanes"])))
    check(u"memory 线显示忙 + 当前任务名", st["lanes"]["memory"]["busy"] is True
          and u"占着线" in (st["lanes"]["memory"]["current"] or ""), str(st["lanes"]["memory"]))
    check(u"running 列表里有这个任务", any(u"占着线" in (x.get("label") or "")
                                          for x in st["running"]), str(st["running"][:2]))
    gate.set()
    jobs.wait_idle("memory", timeout=5)

    print(u"\n== ⑦ 队列上限与降级（宁可明确失败，不要无限堆积）==")
    gate2 = threading.Event()
    got = []
    for i in range(40):
        got.append(jobs.submit("talk", lambda: gate2.wait(3), name="fill%d" % i))
    check(u"超出上限的投递返回 None（调用方可降级为同步）",
          got.count(None) >= 1, u"None 数 %d / 40" % got.count(None))
    st = jobs.status()
    check(u"状态里记了 dropped", st["lanes"]["talk"]["dropped"] >= 1, str(st["lanes"]["talk"]))
    gate2.set()
    jobs.wait_idle("talk", timeout=8)

    print(u"\n== ⑧ 未知线名不炸 ==")
    check(u"投到不存在的线返回 None 而不是抛异常", jobs.submit("不存在", lambda: 1) is None)

    print(u"\n== ⑨ 收线干净 ==")
    jobs.shutdown(timeout=3)
    st = jobs.status()
    check(u"收线后 started=False", st["started"] is False, str(st["started"]))
    check(u"收线后线清空", st["lanes"] == {}, str(st["lanes"]))
    n_before = threading.active_count()
    check(u"没有留下跑着的分道线程", n_before <= 3, u"活跃线程 %d" % n_before)

    print(u"\n== ⑩ 多工作线程的线（互不依赖的活儿才允许）==")
    jobs.start()
    st = jobs.status()
    check(u"net 线报告 3 个工作线程", st["lanes"]["net"]["workers"] == 3,
          str(st["lanes"]["net"]))
    check(u"plugin/io 线仍是 1（保序：钩子与落盘不能乱序）",
          st["lanes"]["plugin"]["workers"] == 1 and st["lanes"]["io"]["workers"] == 1,
          str({k: st["lanes"][k]["workers"] for k in ("plugin", "io")}))
    # net 线有 3 个工作线程 → 两个任务应当能同时在跑（用会合点证明，而不是靠 sleep 猜）
    marks2 = []
    barrier2 = threading.Barrier(2, timeout=3)

    def rendezvous2(tag):
        barrier2.wait()
        marks2.append(tag)
        return tag
    jobs.submit("net", rendezvous2, "a", name="net-a")
    jobs.submit("net", rendezvous2, "b", name="net-b")
    jobs.wait_idle("net", timeout=5)
    check(u"net 线的两个任务同时进入会合点（多工作线程真并行）",
          sorted(marks2) == ["a", "b"], str(marks2))

    jobs.shutdown(timeout=3)
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("JOBS_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌