# -*- coding: utf-8 -*-
"""ci_dep_check.py —— CI 装完依赖后的自检：九个测试依赖在不在，顺便把它们报到注解里。

为什么要单独一个脚本（而不是 CI 里那行 `python -c "..."`）
----------------------------------------------------------
2026-10 windows 作业在"安装测试依赖"这步红了两次，而 job 日志要仓库 admin 权限（API 403），
只能靠**注解**读错因；那行内联的 `python -c` 一旦自己抛异常（不是干净地 exit 1），
就既没有 ::notice:: 也没有 ::error::，注解区只剩 GitHub 那句"Process completed with exit code 1" ——
等于白红。所以：自检逻辑放进文件，**每条探测路径都自己报**（探测异常也报出来），
本地也能直接跑。

为什么用 `find_spec` 而不是 `import`
------------------------------------
`import webview` 在无显示器的 Linux 上会去碰 GTK/QT，可能直接抛。我们要确认的只是"装上了"。
但 find_spec 遇到父包导入失败也会抛 —— 所以这里逐个 try，把异常原文一起报出去，不吞。

用法：
    python tools/ci_dep_check.py            # 人读
    python tools/ci_dep_check.py --github   # 输出 ::notice:: / ::error:: 注解（CI 用）
"""
import argparse
import importlib.metadata as md
import importlib.util
import os
import sys

# 模块名 → PyPI 名（跟 requi<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌rements-test.txt 对齐）
NEED = [
    ("flask", "flask"), ("requests", "requests"), ("openai", "openai"),
    ("PIL", "Pillow"), ("webview", "pywebview"), ("numpy", "numpy"),
    ("cryptography", "cryptography"), ("docx", "python-docx"),
    ("werkzeug", "werkzeug"),
]


def probe():
    ok, bad = [], []
    for mod, pypi in NEED:
        try:
            spec = importlib.util.find_spec(mod)
        except Exception as e:
            bad.append("%s(探测异常: %s: %s)" % (mod, type(e).__name__, e))
            continue
        if spec is None:
            bad.append("%s(%s)" % (mod, pypi))
            continue
        try:
            ver = md.version(pypi)
        except Exception:
            ver = "?"
        ok.append("%s=%s" % (mod, ver))
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--github", action="store_true", help="输出 GitHub 注解格式")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    where = "%s / %s" % (sys.version.split()[0], sys.platform)
    ok, bad = probe()
    if args.github:
        print("::notice::依赖自检（%s）：%s" % (where, ", ".join(ok) if ok else "（无）"))
        if bad:
            print("::error::缺少依赖（%s）：%s" % (where, ", ".join(bad)))
        else:
            print("::notice::测试依赖就绪")
    else:
        print("依赖自检（%s）" % where)
        print("  就绪：%s" % (", ".join(ok) if ok else "（无）"))
        print("  缺失：%s" % (", ".join(bad) if bad else "（无）"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
