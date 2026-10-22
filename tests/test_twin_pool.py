# -*- coding: utf-8 -*-
"""双子池（twin.py）的测试：轮流、坏就换、冷静期、好了回来、状态落盘。

这一层是纯逻辑，所以测试完全控制"时间"与"成败"，不碰网络。
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from twin import TwinPool, parse_list, norm   # noqa: E402

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


class Clock(object):
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def tick(self, n):
        self.t += n


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read()


def main():
    print("=" * 62)
    print(u"双子：两台服务器轮流跑（坏一个换另一个）")
    print("=" * 62)

    print(u"\n== ① URL 规范化 ==")
    check(u"去空白去尾斜杠", norm(" http://a:5000/ ") == "http://a:5000")
    check(u"逗号列表去重保序",
          parse_list("a:1, b:2 ,a:1") == ["a:1", "b:2"], parse_list("a:1, b:2 ,a:1"))
    check(u"空输入 → 空列表", parse_list("") == [] and parse_list(None) == [])

    print(u"\n== ② 两台都健康：轮流 ==")
    c = Clock()
    pool = TwinPool(["http://a", "http://b"], rotate_seconds=60, now=c)
    check(u"第一台先上", pool.pick() == "http://a")
    c.tick(30)
    check(u"没到 60 秒不换（刚传的卡下次刷新还看得到）", pool.pick() == "http://a")
    c.tick(31)
    check(u"到点换第二台（候鸟）", pool.pick() == "http://b")
    c.tick(60)
    check(u"再轮回来", pool.pick() == "http://a")

    print(u"\n== ③ 坏就换 + 冷静期 ==")
    c = Clock()
    pool = TwinPool(["http://a", "http://b"], rotate_seconds=600, cooldown=90, now=c)
    check(u"初始在 a", pool.pick() == "http://a")
    pool.report("http://a", False)
    check(u"a 挂了立刻换 b", pool.pick() == "http://b")
    check(u"a 进入冷静期", pool.snapshot()["nodes"][0]["cooling"] is True)
    c.tick(30)
    check(u"冷静期内不去碰 a", pool.pick() == "http://b")
    c.tick(61)
    check(u"冷静期过了允许再试 a（轮换回去）", pool.pick() == "http://a")
    pool.report("http://a", True)
    check(u"试通即恢复", pool.snapshot()["nodes"][0]["ok"] is True)

    print(u"\n== ④ 两台都挂：挑最早恢复的那台，而不是直接失败 ==")
    c = Clock()
    pool = TwinPool(["http://a", "http://b"], cooldown=90, now=c)
    pool.report("http://a", False)
    c.tick(10)
    pool.report("http://b", False)
    check(u"仍有返回（a 先恢复）", pool.pick() == "http://a", pool.pick())
    check(u"两台都在冷静", all(n["cooling"] for n in pool.snapshot()["nodes"]))

    print(u"\n== ⑤ 单台配置时行为不变 ==")
    c = Clock()
    single = TwinPool(["http://only"], now=c)
    check(u"永远用它", single.pick() == "http://only" and single.pick() == "http://only")
    single.report("http://only", False)
    check(u"单台挂了也只能返回它（调用方会抛错）", single.pick() == "http://only")
    check(u"空配置返回空串", TwinPool([]).pick() == "")

    print(u"\n== ⑥ 状态落盘：重启后记得 ==")
    tmp = tempfile.mkdtemp(prefix="dick_twin_")
    state = os.path.join(tmp, "workshop_twin.json")
    c = Clock()
    p1 = TwinPool(["http://a", "http://b"], state_file=state, rotate_seconds=60, now=c)
    p1.pick()
    c.tick(61)
    p1.pick()                     # 换到 b 并落盘
    p1.report("http://a", False)
    check(u"状态文件已写", os.path.isfile(state))
    data = json.load(io.open(state, encoding="utf-8"))
    check(u"记住了 active=b", data.get("active") == "http://b", str(data.get("active")))
    p2 = TwinPool(["http://a", "http://b"], state_file=state, rotate_seconds=60, now=c)
    check(u"重启后仍从 b 开始", p2.active == "http://b", p2.active)

    print(u"\n== ⑦ 服务端 / 客户端接线（源码闸门）==")
    net_src = read("net.py")
    check(u"net.py 注册了双子接口", "register_twin_routes(app, DATA_DIR)" in net_src)
    check(u"net.py 支持独立数据目录（本机跑两台）", "WORKSHOP_DATA_DIR" in net_src)
    http_src = read("twin_http.py")
    check(u"有 /api/node", '"/api/node"' in http_src)
    check(u"有 /api/twin", '"/api/twin"' in http_src)
    check(u"有 /api/health", '"/api/health"' in http_src)

    print(u"\n== \u2467 \u670d\u52a1\u7aef\u84dd\u56fe\uff08\u771f\u8c03\u4e00\u6b21\uff09==")
    try:
        from flask import Flask
        import twin_http
        fa = Flask("twin_test")
        twin_http.register_twin_routes(fa, data_dir="/tmp/node_a")
        cli = fa.test_client()
        r1 = cli.get("/api/node")
        body = json.loads(r1.data.decode("utf-8"))
        check(u"/api/node 返回 200", r1.status_code == 200)
        check(u"带节点标识", bool(body.get("node")))
        check(u"带数据目录", body.get("data_dir") == "/tmp/node_a", str(body.get("data_dir")))
        r2 = cli.get("/api/health")
        check(u"/api/health 返回 ok", r2.status_code == 200 and json.loads(r2.data.decode("utf-8")).get("ok") is True)
        r3 = cli.get("/api/twin")
        check(u"/api/twin 返回 200 且带 self", r3.status_code == 200 and "self" in json.loads(r3.data.decode("utf-8")))
    except Exception as e:
        check(u"Flask 可用（缺 Flask 时跳过）", False, str(e)[:100])

    print(u"\n== \u2468 \u5ba2\u6237\u7aef\u63a5\u7ebf\uff08shell_ws\uff09==")
    ws = read(os.path.join("shell_ws.py"))
    check(u"有 _ws_servers\uff08\u8bfb\u4e24\u53f0\u914d\u7f6e\uff09", "def _ws_servers(" in ws)
    check(u"\u6709 _ws_twin\uff08\u61d2\u5efa\u6c60\uff09", "def _ws_twin(" in ws)
    check(u"\u53cc\u53f0\u65f6\u8d70 pool.pick()", "self._ws_twin().pick()" in ws)
    check(u"\u72b6\u6001\u843d\u76d8 workshop_twin.json", "workshop_twin.json" in ws)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("TWIN_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌