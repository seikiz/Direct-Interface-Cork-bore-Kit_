# -*- coding: utf-8 -*-
"""交互 smoke（把 node 的替身 DOM 跑一遍，接进本地全套）。

为什么要包一层 Python：`tools/run_local_suite.py` 只跑 `tests/test_*.py`。
真正的 harness 是 `tests/screen_harness.js`（node + 手写的最小 DOM，仓库里没有也不该有 jsdom），
这里只负责：找 node → 跑 harness → 把它打印的「通过 N / 失败 M」透传出来（suite 靠这行数断言）。

harness 验的是这条链（本轮搬家的"行为守恒"）：
  编辑器开包 → 加线 → 拖节点(坐标) → 连线(分支) → 保存 → 播放器读到 → 逐行走 → 选项 → 回溯
  → 跳转 → 结局 → 存档/读档 → 退出；再反向验"编辑器/侧栏 → 打开 GAL"只发事件。

跑法：python -X utf8 tests/test_screen_smoke.py
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HARNESS = os.path.join(HERE, "screen_harness.js")


def main():
    if not os.path.isfile(HARNESS):
        print("  [FAIL] 找不到 tests/screen_harness.js")
        print("通过 0 / 失败 1")
        return 1
    node = shutil.which("node")
    if not node:
        # 没装 node 不等于代码坏了，但<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌也不许静默通过 —— 说清楚该怎么补
        print("  [FAIL] 没找到 node：交互 smoke 需要 node（tests/screen_harness.js）")
        print("通过 0 / 失败 1")
        return 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([node, HARNESS], cwd=ROOT, env=env,
                          capture_output=True, timeout=120)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    sys.stdout.write(out)
    if err.strip():
        sys.stdout.write(err)
    if proc.returncode != 0 and "失败" not in out:
        print("  [FAIL] harness 非 0 退出（%d）但没打印断言结果" % proc.returncode)
        print("通过 0 / 失败 1")
        return 1
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
