# -*- coding: utf-8 -*-
"""本地全套测试跑批：逐个跑 tests/test_*.py，汇总"多少脚本 / 多少断言 / 多少失败"。

为什么放进仓库（而不是放 %TEMP%）：
    以前这个脚本一直躺在 TEMP 里，结果某个 agent 清临时目录时把它一起删了，
    跑到一半才报 "can't open file ...dick_local_suite.py"。跑批脚本属于**工具**，
    不是临时文件，就该跟着仓库走、受水印与测试保护。

用法：
    utau_env\\Scripts\\python.exe tools\\run_local_suite.py
    utau_env\\Scripts\\python.exe tools\\run_local_suite.py --only workshop,i18n   # 只跑名字含这些词的
    utau_env\\Scripts\\python.exe tools\\run_local_suite.py --fail-fast

注意：
    · 子进程的 TEMP 被指到 %TEMP%\\loc_tmp，避免测试产物散到仓库里（本机 tempfile.gettempdir()
      在某些环境下会退化成当前目录，这个重定向是必要的）。
    · venv 启动器偶发 "No Python at ...WindowsApps..."，这里会重试几次（已知环境抖动）。
"""
import argparse
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, "utau_env", "Scripts", "python.exe")
if not os.path.isfile(PY):
    PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔的关键词，只跑文件名含这些词的测试")
    ap.add_argument("--fail-fast", action="store_true")
    a = ap.parse_args()

    tmp = os.path.join(os.environ.get("TEMP", ROOT), "loc_tmp")
    os.makedirs(tmp, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=ROOT,
               TEMP=tmp, TMP=tmp, TMPDIR=tmp)

    tests = sorted(f for f in os.listdir(os.path.join(ROOT, "tests"))
                   if f.startswith("test_") and f.endswith(".py"))
    if a.only:
        keys = [k.strip().lower() for k in a.only.split(",") if k.strip()]
        tests = [t for t in tests if any(k in t.lower() for k in keys)]

    total, bad, lines = 0, [], []
    t0 = time.time()
    for t in tests:
        p = os.path.join(ROOT, "tests", t)
        out, rc = "", 0
        for _ in range(4):          # venv 启动器抖动重试
            proc = subprocess.run([PY, p], capture_output=True, env=env, cwd=ROOT, timeout=900)
            out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
            rc = proc.returncode
            if rc == 0:
                break
            if "Unable to create process" in out or "No Python at" in out:
                time.sleep(1.2)
                continue
            break
        if rc != 0:
            bad.append(t)
            tail = " | ".join([l for l in out.strip().splitlines() if l.strip()][-2:])
            lines.append("FAIL %-38s %s" % (t, tail[:160]))
            if a.fail_fast:
                break
            continue
        n = 0
        for m in re.finditer(r"通过\s+(\d+)\s*/\s*失败\s+(\d+)", out):
            n += int(m.group(1))
        for m in re.finditer(r"结果：(\d+)\s*通过", out):
            n += int(m.group(1))
        total += n

    print("本地全套：%d 个脚本，%d 条断言，%d 个失败（%.1f 秒）"
          % (len(tests), total, len(bad), time.time() - t0))
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌