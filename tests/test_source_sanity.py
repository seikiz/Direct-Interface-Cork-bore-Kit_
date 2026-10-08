# -*- coding: utf-8 -*-
"""源码卫生审计：全仓库扫"损坏的转义标记" + 保证每个 .py 都能编译。

为什么需要
----------
2026-10 在读记忆路径时偶然发现两处**反斜杠被替换成了 `${BS}` / `{BS}`**：

    DICK_core.py:889   "\\n\\n"          →  "${BS}n${BS}n"     （文档上下文拼接，追读第二份文档时插入字面垃圾）
    web_fetch.py:146   r"index[_-]\\d+"  →  r"index[_-]{BS}d+" （正则不合法量词 → 静默失效，永远匹配不到）

两处都**不报错、只是行为变差**：第一处让模型读到垃圾文本，第二处让"下一页"识别少一条判据。
这种"静默降级"正是最难发现的一类问题 —— 所以这里加一道全仓库扫描，让它不能再悄悄回来。
另外顺带保证每个 .py 都能编译：CI 只跑 tests/ 下的脚本，别的文件语法坏了没人知道。

跑法：python tests/test_source_sanity.py
"""
import io
import os
import py_compile
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SKIP_DIRS = ("utau_env", "__pycache__", "node_modules", ".git", "dsh-",
             "tavern-installer", os.path.join("dist", "DICK-HTML"), "_phone",
             "server_build", "build")
TEXT_EXT = (".py", ".js", ".ps1", ".bat", ".spec", ".json", ".html", ".kt", ".md", ".txt")

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


def walk(exts=None):
    for dirpath, dirs, files in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        dirs[:] = [d for d in dirs if not any(s in os.path.join(rel, d) for s in SKIP_DIRS)]
        for f in files:
            if exts and not f.endswith(exts):
                continue
            p = os.path.join(dirpath, f)
            if any(s in p for s in SKIP_DIRS):
                continue
            yield p


def main():
    print("=" * 62)
    print(u"源码卫生审计（损坏转义 + 可编译性）")
    print("=" * 62)

    print(u"\n== ① 不许出现损坏的转义标记 ${BS} / {BS} ==")
    # 说明：这两处历史损坏的前缀还不一样（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一处带 $、一处不带），所以两种都扫。
    # 跳过本文件自己 —— 它的说明文字里就写着这两种标记（否则自己扫自己）。
    pat = re.compile(r"\$\{BS\}|\{BS\}")
    hits = []
    for p in walk(TEXT_EXT):
        if os.path.basename(p) == "test_source_sanity.py":
            continue
        try:
            for i, ln in enumerate(io.open(p, encoding="utf-8", errors="ignore").read().splitlines(), 1):
                if pat.search(ln):
                    hits.append("%s:%d  %s" % (os.path.relpath(p, ROOT), i, ln.strip()[:90]))
        except Exception:
            continue
    check(u"全仓库没有 ${BS}/{BS} 这类损坏标记", not hits, u"命中：\n      " + u"\n      ".join(hits))

    print(u"\n== ② 每个 .py 都必须能编译，而且不许有 SyntaxWarning ==")
    # SyntaxWarning 专门盯"无效转义序列"这类问题：tree_weight.py 曾把正则写成
    # 相邻字符串拼接，后半段不是 raw string，\[ 就一直告警（未来 Python 会变错误）。
    import warnings
    bad = []
    n = 0
    for p in walk(".py"):
        n += 1
        try:
            src = io.open(p, encoding="utf-8", errors="ignore").read()
        except Exception as e:
            bad.append("%s: 读不了 %s" % (os.path.relpath(p, ROOT), e))
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            try:
                compile(src, p, "exec")
            except SyntaxWarning as e:
                bad.append("%s: SyntaxWarning %s" % (os.path.relpath(p, ROOT), str(e)[:80]))
            except SyntaxError as e:
                bad.append("%s: SyntaxError %s" % (os.path.relpath(p, ROOT), str(e)[:80]))
    check(u"全部 %d 个 .py 编译通过且无 SyntaxWarning" % n, not bad,
          u"\n      ".join(bad[:8]))

    print(u"\n== ③ 关键文件必须存在（防止有人误删又没人发现）==")
    for rel in ("Direct-Interface Cork-bore Kit.py", "DICK_core.py", "codex_core.py",
                "image_gen.py", "novel_export.py", "offline_advance.py",
                "salience.py", "tree_weight.py", "lookahead.py", "ranker.py", "rubric.py",
                "web/index.html", "requirements.txt", "LICENSE"):
        check(u"存在 %s" % rel, os.path.exists(os.path.join(ROOT, rel)))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("SOURCE_SANITY_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
