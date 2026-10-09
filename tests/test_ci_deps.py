# -*- coding: utf-8 -*-
"""CI 依赖守卫：测试用到的第三方包必须在 requirements-test.txt 里声明。

为什么要有这个
--------------
2026-10：CI 连续 6 次全红。看着像"全是测试失败"，翻注释才看到唯一一条 Node 相关提示是
**警告**（actions/checkout@v4 跑在 Node 24 上，Node 20 已弃用）—— 真正的失败是 Python
那一步：`requirements-test.txt` 少了 cryptography / numpy / python-docx，
于是 test_ranker、test_novel_export、test_backup_*、test_release_backup_e2e 五个脚本
直接 ModuleNotFoundError。本机开发环境里这些包都在 → **本地全绿、CI 全红**。

这种红最贵的地方不是"红"，是**错因看不出来**：CI 只报"运行全量测试 exit 1"。
所以这里做两件事：

  ① 扫 tests/*.py 里所有第三方 import，逐个要求 requirements-test.txt 有声明；
  ② 维护一张"传递依赖"表（测试直接 import 的模块 → 它背后的 PyPI 包），
     确保 crypto_core→cryptography 这种**间接**需求也被钉住 ——
     第 ① 条抓不到它（测试里没写 import cryptography，是 crypto_core 里写的）。

跑法：python tests\\test_ci_deps.py
"""
import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PASS = 0
FAIL = 0

# 模块名 → PyPI 包名（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌只有名字不一样的才要写在这里）
PYPI_NAME = {
    "PIL": "Pillow",
    "docx": "python-docx",
    "webview": "pywebview",
    "yaml": "PyYAML",
}

# 第 ② 条：被测模块间接需要、但测试文件里不会直接 import 的包 → 为什么需要
TRANSITIVE = {
    "cryptography": "crypto_core.encrypt/decrypt 里才 import（AES-GCM），测试只调 API",
    "werkzeug": "flask 的依赖，但测试直接 from werkzeug.serving import make_server → 必须自己钉住",
}
# lxml 不在这里：仓库里没有任何地方直接 import 它，它只是 python-docx 的依赖，
# 所以 requirements-test.txt 里以注释交代，不单独钉版本（钉了反而容易和 docx 打架）。


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def read(path):
    with io.open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def declared_packages():
    """requirements-test.txt 里声明的包名（小写，去版本号）"""
    out = set()
    p = os.path.join(ROOT, "requirements-test.txt")
    if not os.path.isfile(p):
        return out
    for line in read(p).splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        out.add(re.split(r"[<>=!\[; ]", line)[0].strip().lower())
    return out


def third_party_imports(files):
    """扫描这些文件里的第三方顶层 import（排除标准库与本工程模块）"""
    stdlib = set(getattr(sys, "stdlib_module_names", ()) or ())
    local = set()
    for fn in os.listdir(ROOT):
        if fn.endswith(".py"):
            local.add(fn[:-3])
        d = os.path.join(ROOT, fn)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "__init__.py")):
            local.add(fn)
    # plugins/ 不是包（没有 __init__.py），测试是按"目录在 sys.path 上"直接 import 里面的
    # 模块名（from galgame_choices_plugin import …）—— 这些是**本工程**的模块，不是第三方。
    pdir = os.path.join(ROOT, "plugins")
    local.add("plugins")
    if os.path.isdir(pdir):
        for fn in os.listdir(pdir):
            if fn.endswith(".py"):
                local.add(fn[:-3])
    # tests/ 里的辅助模块同理（测试互相 import，比如 test_time_context → probe_payload）
    tdir = os.path.join(ROOT, "tests")
    local.add("tests")
    if os.path.isdir(tdir):
        for fn in os.listdir(tdir):
            if fn.endswith(".py"):
                local.add(fn[:-3])
    found = {}
    for p in files:
        try:
            tree = ast.parse(read(p))
        except SyntaxError as e:
            found.setdefault("__syntax__", set()).add("%s: %s" % (os.path.basename(p), e))
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for n in names:
                if n in stdlib or n in local or n.startswith("_"):
                    continue
                found.setdefault(n, set()).add(os.path.basename(p))
    return found


def test_requirements_file_exists():
    print("\n== ① requirements-test.txt 存在且有内容 ==")
    p = os.path.join(ROOT, "requirements-test.txt")
    check("文件存在", os.path.isfile(p))
    pkgs = declared_packages()
    check("至少声明了 5 个包", len(pkgs) >= 5, str(sorted(pkgs)))


def test_tests_imports_declared():
    print("\n== ② tests/*.py 里的第三方 import 都已声明 ==")
    tdir = os.path.join(ROOT, "tests")
    files = [os.path.join(tdir, f) for f in sorted(os.listdir(tdir))
             if f.startswith("test_") and f.endswith(".py")]
    found = third_party_imports(files)
    check("没有解析失败的测试文件", "__syntax__" not in found,
          str(found.get("__syntax__")))
    found.pop("__syntax__", None)
    declared = declared_packages()
    missing = []
    for mod, where in sorted(found.items()):
        pypi = PYPI_NAME.get(mod, mod).lower()
        if pypi not in declared and mod.lower() not in declared:
            missing.append("%s（PyPI: %s，用于 %s）" % (mod, pypi, ", ".join(sorted(where))))
    check("测试用到的第三方包都在 requirements-test.txt 里", not missing,
          "\n      ".join(missing))
    print("        测试直接 import 的第三方：%s"
          % (", ".join(sorted(found)) if found else "（无）"))


def test_transitive_pinned():
    print("\n== ③ 间接依赖也要钉住（这次 CI 红的就是这一类）==")
    declared = declared_packages()
    for pkg, why in sorted(TRANSITIVE.items()):
        check("%s 已声明（%s）" % (pkg, why), pkg.lower() in declared)


def test_the_five_that_broke_ci():
    print("\n== ④ 2026-10 那次红的五个脚本，依赖必须还在 ==")
    declared = declared_packages()
    need = {
        "test_ranker.py": "numpy",
        "test_novel_export.py": "python-docx",
        "test_backup_encrypted.py": "cryptography",
        "test_backup_entries.py": "cryptography",
        "test_release_backup_e2e.py": "cryptography",
    }
    for t, pkg in sorted(need.items()):
        check("%s 的依赖 %s 已声明" % (t, pkg), pkg.lower() in declared
              and os.path.isfile(os.path.join(ROOT, "tests", t)))


def test_no_node_red_herring():
    print("\n== ⑤ CI 工作流：Node 那步不该被 Python 的失败连累 ==")
    p = os.path.join(ROOT, ".github", "workflows", "test.yml")
    check("工作流文件存在", os.path.isfile(p))
    if os.path.isfile(p):
        yml = read(p)
        check("图标回归（Node）那步带 if: always()（Python 失败也要跑，免得看不出 Node 有没有事）",
              "if: always()" in yml.split("图标系统回归")[-1] if "图标系统回归" in yml else False)
        check("actions 版本已升到 Node 24 世代（checkout@v5 / setup-python@v6）",
              "actions/checkout@v5" in yml and "actions/setup-python@v6" in yml)


def test_two_platform_jobs():
    print("\n== ⑥ 两个平台都跑：Windows 独有的坑 Linux 看不见，反之亦然 ==")
    p = os.path.join(ROOT, ".github", "workflows", "test.yml")
    yml = read(p) if os.path.isfile(p) else ""
    check("有 linux 作业", "runs-on: ubuntu-latest" in yml)
    check("有 windows 作业（2026-10 漏过 GBK/stdin 那种只有 Windows 才炸的问题）",
          "runs-on: windows-latest" in yml)
    check("Windows 作业用 shell: bash 跑同一段脚本（两套逻辑迟早漂移）",
          "shell: bash" in yml)
    check("跑测试前先打一份环境报告（省得以后猜 CI 上是什么环境）",
          "tools/env_report.py" in yml)


def test_container_and_env_tooling():
    print("\n== ⑦ 容器与工具：环境要能「照着文件重建」，不是靠记忆 ==")
    df = os.path.join(ROOT, "Dockerfile")
    check("Dockerfile 存在（本机没 Linux 时用它复现 CI）", os.path.isfile(df))
    if os.path.isfile(df):
        txt = read(df)
        check("容器里装的就是 requirements-test.txt（跟 CI 同一个源）",
              "requirements-test.txt" in txt)
        check("容器里显式钉 UTF-8（免得再踩 GBK）", "PYTHONIOENCODING" in txt)
    check("devcontainer 存在（Codespaces / VS Code 能直接用）",
          os.path.isfile(os.path.join(ROOT, ".devcontainer", "devcontainer.json")))
    check("env_report 工具存在", os.path.isfile(os.path.join(ROOT, "tools", "env_report.py")))
    check("锁文件生成工具存在", os.path.isfile(os.path.join(ROOT, "tools", "lock_requirements.py")))
    # 故意**不**要求仓库里有 requirements-lock.txt：见 tools/lock_requirements.py 顶部的说明
    # （轮子可用性是"平台 × 版本"两个维度，手写一份跨平台锁文件只会制造新的环境坑）


if __name__ == "__main__":
    print("=" * 62)
    print(u"CI 依赖守卫（测试要的包，requirements-test.txt 里有没有）")
    print("=" * 62)
    test_requirements_file_exists()
    test_tests_imports_declared()
    test_transitive_pinned()
    test_the_five_that_broke_ci()
    test_no_node_red_herring()
    test_two_platform_jobs()
    test_container_and_env_tooling()
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CI_DEPS_TEST_OK")
    sys.exit(1 if FAIL else 0)
