# -*- coding: utf-8 -*-
"""lock_requirements.py —— 把 requirements-test.txt 变成"钉死版本"的锁文件。

为什么需要
----------
2026-10 那次 CI 连续全红，根因就是**环境差**：本机有 cryptography/numpy/python-docx，
CI 没有 → 五个脚本 ModuleNotFoundError，而 CI 只报一句 exit 1。
`>=` 下限保证"装了不会太旧"，但保证不了"两台机器装的是同一套"。

两种模式
--------
  direct（默认，写 requirements-lock.txt）
      只把**直接依赖**钉到精确版本，跨平台可用。
      为什么不钉传递依赖：依赖树是**分平台**的 —— 同一个 pywebview 在 Windows 上会拖
      pythonnet/clr-loader，在 Linux 上根本不装。拿 Windows 生成的整棵树去 Linux 装会直接失败
      （这正是"环境差"的另一种形态）。

  full（写 requirements-lock-<平台>.txt）
      把当前平台解析出的**整棵依赖树**钉死，用于"我在本机复现一个字节级一致的环境"。
      带平台后缀，别跨平台用。

⚠ 两个真踩过的坑（所以仓库里**没有**提交任何现成的锁文件）：
  1. 用 3.14 解析出的版本（numpy 2.5 / pillow 12 …）在 3.11 上可能没有轮子 → 锁文件装不回去。
     所以有 `--target-python 3.11` 这种按目标版本解析的开关。
  2. 即便按 3.11 解析，在本机（Windows）上也可能直接 `ResolutionImpossible` ——
     轮子的可用性是**平台 + 版本**两个维度的事，写个文件跨不过去。
  结论：**要一致，就在"要用的那台机器/那个容器"上生成**（`--mode full`），
  或者干脆用容器（见仓库根 Dockerfile）把环境本身固定下来。
  跨平台通用的那份"直接依赖下限表"仍然是 requirements-test.txt —— CI 装的就是它。

不需要 pip-tools：pip 21.3+ 自带 `pip install --dry-run --report`。

用法（工程根）：
    python tools/lock_requirements.py                 # direct → requirements-lock.txt
    python tools/lock_requirements.py --mode full     # full → requirements-lock-win32.txt
    python tools/lock_requirements.py --target-python 3.11 --mode direct
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {"pip", "setuptools", "wheel", "pkg-resources"}


def _parse_requirements(path):
    """返回 [(名字小写, 原始行)] —— 只取真正的依赖行，注释/空行不要"""
    out = []
    with io.open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#")[0].strip()
            if not line:
                continue
            name = re.split(r"[<>=!\[; ]", line)[0].strip()
            if name:
                out.append((name.lower(), line))
    return out


def resolve_tree(req_file, python=None, target_python=None):
    """让 pip 算一遍依赖树，返回 {名字小写: 版本}

    target_python（如 "3.11"）：按**那个 Python 版本**解析，而不是跑脚本的解释器。
    为什么要这个开关：本机可能只有 3.14，而 CI 跑 3.11/3.12 —— 用 3.14 解析出来的
    numpy/cryptography 版本在 3.11 上可能没有轮子，锁文件就装不回去（踩过）。
    pip 支持跨版本解析（--python-version + --only-binary，必须配 --target）。
    """
    py = python or sys.executable
    fd, report = tempfile.mkstemp(suffix=".json", prefix="dick_lock_")
    os.close(fd)
    target = None
    try:
        cmd = [py, "-m", "pip", "install", "--dry-run", "--ignore-installed",
               "--quiet", "--report", report]
        if target_python:
            target = tempfile.mkdtemp(prefix="dick_lock_t_")
            cmd += ["--python-version", str(target_python),
                    "--only-binary=:all:", "--target", target]
        r = subprocess.run(cmd + ["-r", req_file], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print("pip 解析失败：\n%s\n%s" % (r.stdout[-2000:], r.stderr[-2000:]))
            return None
        with io.open(report, encoding="utf-8") as f:
            data = json.load(f)
    finally:
        try:
            os.remove(report)
        except OSError:
            pass
        if target:
            import shutil
            shutil.rmtree(target, ignore_errors=True)
    got = {}
    for item in data.get("install", []):
        meta = item.get("metadata") or {}
        name = str(meta.get("name") or "").strip().lower()
        ver = str(meta.get("version") or "").strip()
        if name and ver and name not in SKIP:
            got[name] = ver
    return got


def header(src_rel, py_ver, mode, extra=""):
    return [
        "# 依赖锁文件（由 tools/lock_requirements.py 生成，别手改）",
        "#   来源：%s" % src_rel,
        "#   模式：%s" % ("direct（只钉直接依赖，跨平台可用）" if mode == "direct"
                       else "full（整棵依赖树，仅限当前平台）"),
        "#   生成环境：Python %s / %s" % (py_ver, sys.platform),
        "#   生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "#",
        "# 为什么要有它：CI 那次全红就是「本机有、CI 没有」造成的（见 待办与想法.md §六）。",
        "# 换解释器（3.11 → 3.12）或改了 requirements-test.txt，都要重跑这个脚本。",    ] + ([extra] if extra else []) + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="requirements-test.txt")
    ap.add_argument("--mode", choices=("direct", "full"), default="direct")
    ap.add_argument("--out", default=None)
    ap.add_argument("--python", default=None, help="用来解析的解释器（默认当前）")
    ap.add_argument("--target-python", default=None,
                    help="按这个 Python 版本解析（如 3.11）—— CI 跑什么就写什么，"
                         "否则本机 3.14 解析出的版本在 CI 上可能没有轮子")
    args = ap.parse_args()

    src = args.input if os.path.isabs(args.input) else os.path.join(ROOT, args.input)
    if not os.path.isfile(src):
        print("找不到输入文件：%s" % src)
        return 1
    py = args.python or sys.executable
    py_ver = subprocess.run([py, "-c", "import sys;print('.'.join(map(str,sys.version_info[:3])))"],
                            capture_output=True, text=True).stdout.strip() or "?"

    print("解析 %s（用 %s）…" % (os.path.relpath(src, ROOT), py))
    tree = resolve_tree(src, py, args.target_python)
    if tree is None:
        return 1

    if args.mode == "direct":
        pins, missing = [], []
        for name_l, raw in _parse_requirements(src):
            ver = tree.get(name_l)
            if ver:
                pins.append("%s==%s" % (name_l, ver))
            else:
                missing.append(raw)
        if missing:
            print("⚠ 这些直接依赖没解析出版本：%s" % "、".join(missing))
        out = args.out or os.path.join(ROOT, "requirements-lock.txt")
        lines = header(os.path.relpath(src, ROOT), py_ver, "direct",
                       "#   传递依赖不在这里钉：依赖树分平台（Windows 的 pywebview 会拖 pythonnet，"
                       "Linux 不会），\n#   拿一份跨平台的整树去装必炸。要字节级一致就用 --mode full。")
        lines += sorted(pins, key=str.lower)
    else:
        out = args.out or os.path.join(ROOT, "requirements-lock-%s.txt" % sys.platform)
        lines = header(os.path.relpath(src, ROOT), py_ver, "full",
                       "#   ⚠ 带平台后缀：这一份只在 %s 上保证一致，别拿去别的平台装。" % sys.platform)
        lines += ["%s==%s" % (n, tree[n]) for n in sorted(tree)]

    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("写出 %s（%d 个包）" % (os.path.relpath(out, ROOT), len(pins) if args.mode == "direct" else len(tree)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌