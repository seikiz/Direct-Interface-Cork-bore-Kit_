# -*- coding: utf-8 -*-
"""env_report.py —— 一条命令看清"跑测试的这套环境是什么"。

为什么要它
----------
2026-10 那次 CI 全红，最贵的不是"红"，是**看不到错因**：本机有 cryptography/numpy/python-docx，
CI 没有 → 五个脚本 ModuleNotFoundError，而 CI 只报一句 exit 1。
后来追 Linux 独有的一堆问题（临时文件被后台清理删掉、写死的 Windows 路径）同样花了四轮 CI。
所以：**先让环境可读**，再谈排查。

用法：
    python tools/env_report.py            # 人话报告
    python tools/env_report.py --json     # 机器可读（贴给谁看都行）

它会说清楚：解释器在哪、什么版本、什么系统、哪些测试依赖**装了/没装**、
以及这套环境下测试会不会跑得跟 CI 一样。
"""
import argparse
import importlib.util
import io
import json
import os
import platform
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 跑测试需要的第三方模块（与 requirements<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌-test.txt 对齐；模块名 → PyPI 名）
NEED = [
    ("flask", "flask"), ("requests", "requests"), ("openai", "openai"),
    ("PIL", "Pillow"), ("webview", "pywebview"), ("numpy", "numpy"),
    ("cryptography", "cryptography"), ("docx", "python-docx"),
    ("werkzeug", "werkzeug"),
]


def collect():
    mods = []
    for mod, pypi in NEED:
        try:
            spec = importlib.util.find_spec(mod)
        except (ImportError, ValueError):
            spec = None
        ver = ""
        if spec is not None:
            try:
                m = __import__(mod)
                ver = str(getattr(m, "__version__", "") or "")
            except Exception:
                ver = "(导入失败)"
        mods.append({"module": mod, "pypi": pypi,
                     "ok": spec is not None, "version": ver})
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cwd": os.getcwd(),
        "root": ROOT,
        "temp_dir": __import__("tempfile").gettempdir(),
        "deps": mods,
        "missing": [m["pypi"] for m in mods if not m["ok"]],
    }


def human(info):
    out = []
    out.append("=" * 64)
    out.append("DICK 测试环境报告")
    out.append("=" * 64)
    out.append("Python      : %s" % info["python"])
    out.append("解释器      : %s" % info["executable"])
    out.append("系统        : %s (%s)" % (info["platform"], info["machine"]))
    out.append("工作目录    : %s" % info["cwd"])
    out.append("临时目录    : %s" % info["temp_dir"])
    out.append("")
    out.append("测试依赖：")
    for m in info["deps"]:
        mark = "OK  " if m["ok"] else "缺失"
        ver = (" " + m["version"]) if m["version"] else ""
        out.append("  %s %-12s (PyPI: %s)%s" % (mark, m["module"], m["pypi"], ver))
    out.append("")
    if info["missing"]:
        out.append("❌ 缺：%s" % "、".join(info["missing"]))
        out.append("   装法：pip install -r requirements-test.txt")
    else:
        out.append("✅ 依赖齐了，可以跑 tests/ 全套")
    # 平台提醒：这两句是踩过坑的地方
    if sys.platform == "win32":
        out.append("")
        out.append("⚠ 你在 Windows 上：CI 跑的是 Linux(Ubuntu)。")
        out.append("  · 只在这里绿 ≠ CI 绿（Linux 独有的问题：路径/权限/临时文件/大小写敏感）")
        out.append("  · 想先跑一遍 Linux：装了 Docker 就 docker build -t dick-tests . && docker run --rm dick-tests")
        out.append("  · 反过来，Windows 独有的坑（GBK、DPAPI）CI 看不见，CI 里另有一个 windows 作业在盯")
    elif sys.platform.startswith("linux"):
        out.append("")
        out.append("⚠ 你在 Linux 上：这是 CI 的系统。")
        out.append("  · 只在这里绿 ≠ Windows 绿（本机开发机的 GBK/DPAPI/路径大小写问题这里看不见）")
    else:
        out.append("")
        out.append("⚠ 这个系统既不是 Windows 也不是 Linux：CI 是 Linux，别拿它当准。")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()
    info = collect()
    text = json.dumps(info, ensure_ascii=False, indent=1) if args.json else human(info)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(text)
    return 1 if info["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
