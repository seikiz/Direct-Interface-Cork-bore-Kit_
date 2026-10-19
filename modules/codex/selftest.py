# -*- coding: utf-8 -*-
"""modules/codex/selftest.py —— codex 块的自检入口（闭环：不惊动任何别的块）

`python -m modules.codex --selftest`  → 成功时**只有一行** JSON：
    {"block": "codex", "pass": 21, "fail": 0, "ms": 303, "deps": []}

失败时在这行之后追加：FAIL <case>: <原因>  +  一行最小复现命令。

本文件只做三件事：跑 case（来自 cases.py）、算耗时、打那行 JSON。
用例与替身在 cases.py / harness.py —— 拆开是因为合起来 548 行，超过 400 行预算（九.1）。

硬规则（改代码的人先看到）：
  · **不许连网、不许占端口**：这一块本来就不碰网络；打包 EXE（PyInstaller）只验命令构造；
  · **< 2s**：占位 PNG 是纯 Python 逐像素画的，所以示例包布局那个 case 把生成器换成了桩；
  · 每条都是"输入 → 输出/异常"的闭环，坏输入覆盖见 cases.py 的 docstring。
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
from . import pack as pack_mod
from .service import CodexService
from .cases import CASES
from .harness import BLOCK, MAX_MS


def _deps():
    """依赖声明只认 manifest（唯一真相），不在这里再写一遍"""
    try:
        with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "manifest.json"), encoding="utf-8") as f:
            return list((json.load(f).get("requires") or {}).get("modules") or [])
    except Exception:
        return []

def run(only=None):
    t0 = time.perf_counter()
    passed, failed, errors = 0, 0, []
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):      # 自检期间模块自己的日志收进缓冲区
        for cid in sorted(CASES):
            if only and cid != only:
                continue
            try:
                CASES[cid]()
                passed += 1
            except Exception as e:
                failed += 1
                errors.append((cid, "%s: %s" % (type(e).__name__, str(e)[:200])))
    ms = int((time.perf_counter() - t0) * 1000)
    if not only and ms > MAX_MS:
        failed += 1
        errors.append(("budget", "自检耗时 %dms 超过上限 %dms" % (ms, MAX_MS)))
    return ({"block": BLOCK, "pass": passed, "fail": failed, "ms": ms, "deps": _deps()},
            errors, sink.getvalue())

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" not in argv:
        print("用法：python -m modules.codex --selftest [--only <case>]")
        return 2
    only = argv[argv.index("--only") + 1] if "--only" in argv and \
        len(argv) > argv.index("--only") + 1 else None
    res, errors, log = run(only)
    print(json.dumps(res, ensure_ascii=False))          # 唯一一行 JSON
    if errors:
        for line in log.splitlines():
            print("  | " + line)
        for cid, msg in errors:
            print("FAIL %s: %s" % (cid, msg))
            print("  复现：python -m modules.codex --selftest --only %s" % cid)
    return 1 if res["fail"] else 0
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌