# -*- coding: utf-8 -*-
"""atomic_io 的测试 + "关键路径不许回退成非原子写"的闸门。

断电/被杀进程的模拟方式：让 os.replace 或 fsync 抛异常，
断言 ①原文件仍在且内容未变 ②临时文件被清理 ③异常照常抛出。
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import atomic_io as A   # noqa: E402

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
    tmp = tempfile.mkdtemp(prefix="atomic_io_")
    try:
        p = os.path.join(tmp, "cfg.json")

        print(u"\n== ① 正常写：内容对、不留临时文件 ==")
        A.write_json(p, {"a": 1, u"中文": u"值"})
        check(u"文件写出来了", os.path.isfile(p))
        check(u"读回来一致", A.read_json(p) == {"a": 1, u"中文": u"值"})
        check(u"没有残留 .atomic-*.tmp", A.leftovers(p) == [])
        raw = io.open(p, encoding="utf-8").read()
        check(u"以换行结尾", raw.endswith("\n"))

        print(u"\n== ② 覆盖写：旧内容被替换、不残留 ==")
        A.write_json(p, {"a": 2})
        check(u"内容已更新", A.read_json(p)["a"] == 2)
        check(u"依旧没有临时文件", A.leftovers(p) == [])

        print(u"\n== ③ 换名失败（模拟断电/被杀）：原文件必须完好 ==")
        A.write_json(p, {"keep": True})
        real_replace = os.replace
        try:
            os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
            threw = False
            try:
                A.write_json(p, {"keep": False})
            except OSError:
                threw = True
        finally:
            os.replace = real_replace
        check(u"异常照常抛出", threw)
        check(u"原文件仍是旧内容", A.read_json(p) == {"keep": True})
        check(u"临时文件被清理", A.leftovers(p) == [])

        print(u"\n== ④ 写内容阶段就失败：原文件也不受影响 ==")
        threw = False
        try:
            A.write_json(p, {"x": object()})      # 不可序列化 → dumps 先炸
        except TypeError:
            threw = True
        check(u"序列化失败会抛", threw)
        check(u"原文件没被动过", A.read_json(p) == {"keep": True})
        check(u"没留下半成品", A.leftovers(p) == [])

        print(u"\n== ⑤ 文本与二进制 ==")
        t = os.path.join(tmp, "note.txt")
        A.write_text(t, u"第一行\r\n第二行")
        got = io.open(t, encoding="utf-8").read()
        check(u"CRLF 统一成 LF", "\r" not in got and u"第二行" in got)
        b = os.path.join(tmp, "blob.bin")
        A.write_bytes(b, b"\x00\x01\x02")
        check(u"二进制原样", open(b, "rb").read() == b"\x00\x01\x02")

        print(u"\n== ⑥ 读侧容错 ==")
        bad = os.path.join(tmp, "broken.json")
        io.open(bad, "w", encoding="utf-8").write("{ 这不是 json")
        check(u"坏 JSON 返回默认值", A.read_json(bad, {"d": 1}) == {"d": 1})
        check(u"不存在也返回默认值", A.read_json(os.path.join(tmp, "nope.json"), []) == [])

        print(u"\n== ⑦ 闸门：关键路径不许回退成非原子写 ==")
        critical = [
            "DICK_core.py", "plugin_manager.py", "net.py",
            "plugins/import_tavern_card.py", "modules/codex/pack.py",
            "kernel/config.py", "mem_scene.py", "mem_facts.py",
            "save_guard.py", "game_store.py",
        ]
        atomic_markers = ("atomic_io.", "atomic_write_json", "os.replace", "os.rename")
        offenders = []
        for rel in critical:
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                continue
            lines = io.open(path, encoding="utf-8").read().split("\n")
            for i, line in enumerate(lines):
                if "json.dump(" not in line and not (
                        ("open(" in line and '"w"' in line or "'w'" in line)):
                    continue
                if "StringIO" in line or "sys.std" in line:
                    continue
                ctx = "\n".join(lines[max(0, i - 12):i + 12])
                if any(m in ctx for m in atomic_markers):
                    continue
                offenders.append("%s:%d" % (rel, i + 1))
        check(u"关键文件里没有裸覆盖写", not offenders, u"、".join(offenders[:6]))

        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌