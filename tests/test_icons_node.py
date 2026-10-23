# -*- coding: utf-8 -*-
"""把 node 的图标回归（tests/test_icons.js）接进 Python 全套。

为什么现在才接：CI 有独立一步跑它，但**本地全套没有** —— 于是"本地全绿、CI 三平台全红"
（2026-10 就发生了一次：index.html 拆脚本后 test_icons.js 抓不到图标引擎，
node 直接 TypeError，而本地 111 个脚本一个都没跑到它）。

约定与 test_screen_smoke.py 一致：找不到 node 就明说，不静默通过。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(HERE, "test_icons.js")


def main():
    if not os.path.isfile(SCRIPT):
        print("  [FAIL] 找不到 tests/test_icons.js")
        print("通过 0 / 失败 1")
        return 1
    node = shutil.which("node")
    if not node:
        print("  [FAIL] 没找到 node：图标回归需要 node（tests/test_icons.js）")
        print("通过 0 / 失败 1")
        return 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([node, SCRIPT], cwd=ROOT, env=env, capture_output=True, timeout=180)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    sys.stdout.write(out)
    if err.strip():
        sys.stdout.write(err)
    ok = proc.returncode == 0 and "ICON_TEST_OK" in out
    if not ok and "失败" not in out:
        print("  [FAIL] node 非 0 退出（%d）但没打印断言结果" % proc.returncode)
    print("通过 %d / 失败 %d" % (0 if not ok else 1, 0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌