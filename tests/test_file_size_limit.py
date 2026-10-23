# -*- coding: utf-8 -*-
"""一个文件不许超过 1000 行（棘轮：豁免名单只许缩短，不许新增）。

为什么要有这条闸门：
    "又臭又长的文件"是维护成本的主要来源 —— 改一处要滚十屏、找一行要全文搜索，
    对注意力不友好，也最容易在拆的时候把邻居整块吃掉。
    1000 行是这条线：一个文件一件事，超出就拆。

两种放行：
    · 第三方/构建产物（tavern-installer、node_modules、dist、live2d 素材…）不参与统计；
    · 生成文件（I18nStrings.kt 由 tools/gen_i18n.py 生成）单独列出。
    其余**豁免名单**里的文件是历史遗留，允许暂时超线，但：
        ① 不许超过登记值（只能缩，不能涨）
        ② 新文件一律不许超线
    等它们缩到 1000 以下，就把对应条目从豁免名单里删掉。

验：本文件自身
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LIMIT = 1000

# 不参与统计的路径片段（第三方 / <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌构建产物 / 素材 / 测试临时）
SKIP_PARTS = (
    "utau_env", "node_modules", ".git", "dist", "build", "tavern-installer",
    "archive", "web/live2d", "web/vendor", "web/fonts", "__pycache__",
    "dick_rr_", "exports", "dsh-vision-router", "dsh-companion", "_phone",
    ".tmp_test", "pip-", "_rel_out",
)

# 生成文件：不算手写债，但它也有上限（别让生成器把 UI 撑爆）
GENERATED = {
    os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "I18nStrings.kt"): 1100,
}

# 豁免名单（历史遗留，只许降不许涨）。缩到 1000 以下就删条目。
EXEMPT = {
    os.path.join("web", "index.html"): 3895,
    os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app",
                 "ui", "screens", "chat", "ChatScreen.kt"): 2770,
}

# 统一成 / 分隔（扫描结果用 / 作键；Windows 下 os.path.join 给的是反斜杠）
GENERATED = {k.replace("\\", "/"): v for k, v in GENERATED.items()}
EXEMPT = {k.replace("\\", "/"): v for k, v in EXEMPT.items()}

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


def lines_of(path):
    try:
        return len(io.open(path, encoding="utf-8", errors="replace").read().splitlines())
    except Exception:
        return 0


def scan():
    out = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        if any(s in rel_dir for s in SKIP_PARTS):
            dirnames[:] = []
            continue
        for f in filenames:
            if not f.endswith((".py", ".js", ".kt", ".html")):
                continue
            rel = os.path.join(rel_dir, f) if rel_dir else f
            if any(s in rel.replace("\\", "/") for s in SKIP_PARTS):
                continue
            n = lines_of(os.path.join(ROOT, rel))
            if n:
                out[rel.replace("\\", "/")] = n
    return out


def main():
    print("=" * 62)
    print(u"单文件行数上限（棘轮：豁免只许降）")
    print("=" * 62)

    sizes = scan()
    print(u"\n扫描 %d 个源文件，上限 %d 行" % (len(sizes), LIMIT))

    over = {p: n for p, n in sizes.items() if n > LIMIT}
    unknown = {p: n for p, n in over.items() if p not in EXEMPT and p not in GENERATED}
    print(u"\n== ① 不许出现新的超线文件 ==")
    for p, n in sorted(unknown.items(), key=lambda x: -x[1]):
        print(u"    超线: %5d  %s" % (n, p))
    check(u"没有新增超线文件（要么拆，要么登记进豁免）", not unknown,
          u"未登记：%s" % ", ".join(sorted(unknown)))

    print(u"\n== ② 豁免名单只许缩短（棘轮）==")
    for p, cap in sorted(EXEMPT.items()):
        n = sizes.get(p, 0)
        check(u"%s 不超登记值 %d（现有 %d）" % (os.path.basename(p), cap, n), n <= cap,
              u"涨了 %d 行 —— 先拆，别让它继续长" % (n - cap))

    print(u"\n== ③ 生成文件也有上限 ==")
    for p, cap in sorted(GENERATED.items()):
        n = sizes.get(p, 0)
        check(u"%s 不超 %d（现有 %d）" % (os.path.basename(p), cap, n), n <= cap)

    print(u"\n== ④ 已经合规的文件不回头 ==")
    clean = [p for p, n in sizes.items() if n <= LIMIT and p not in EXEMPT and p not in GENERATED]
    check(u"合规文件数 > 100（真在拆，不只是登记）", len(clean) > 100, str(len(clean)))

    print(u"\n-- 当前最接近上限的文件 --")
    near = sorted(((n, p) for p, n in sizes.items() if p not in EXEMPT and p not in GENERATED),
                  reverse=True)[:5]
    for n, p in near:
        print(u"  %5d  %s" % (n, p))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("FILE_SIZE_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
