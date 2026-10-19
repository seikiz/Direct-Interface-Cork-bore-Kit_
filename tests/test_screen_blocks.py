# -*- coding: utf-8 -*-
"""屏幕块守卫：把 `web/UI_ARCHITECTURE.md` 的「网页屏幕块清单」当契约，和磁盘上的实际文件对账。

为什么要有它
------------
`ARCHITECTURE.md` 第十节把"块"定义成四样东西：位置 / 文件清单 / 行数预算 / 验收标准。
前两样以前只写在文档里 —— 没人核对，于是"临时加个文件"永远合规。这个测试把清单变成断言：
**文档说有哪些文件，磁盘上就必须正好有那些文件，而且每个都还在行数预算里。**

四条硬断言（对应清单里的两张表）
  ① 清单里每个文件都存在（少一个 = 文档骗人）；
  ② 屏模块文件 ≤ 400 行（> 800 直接红 —— 那是"这个块该拆了"，不是"提醒一下"）；
  ③ `web/screens/*.html` 里不许出现嵌套的 `<!--@screen:`（HTML 注释不能嵌套，router 也不认）；
  ④ 屏模块不许 `getElementById` 另一屏前缀的 id（跨屏只走 DICK.state / DICK.bus）；
     例外必须写在清单表 2，且**最多 5 条**、每条带理由。

另外两条防倒退的：
  ⑤ 新加的 `web/js/screens/<块前缀>-*.js` 必须在清单表 1 里登记（"新文件必须先加名字"）；
  ⑥ 清单里的文件必须真的被 index.html 引到（script/link），片段要有对应挂载点；
     并且 index.html 里不许再出现 `function codexXxx / galXxx` 这种**实现**（门面在模块里）。

跑法：python -X utf8 tests/test_screen_blocks.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
DOC = os.path.join(WEB, "UI_ARCHITECTURE.md")
INDEX = os.path.join(WEB, "index.html")

SECTION = "## 网页屏幕块清单"
LINE_BUDGET = 400          # 目标
LINE_HARD = 800            # 硬上限
MAX_EXCEPTIONS = 5

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [OK] %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s  %s" % (name, detail))
    return cond


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _lines(path):
    return len(_read(path).split("\n")) - 1


# ================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌============================ 解析清单
def _rows(md):
    """把一段 markdown 里的表格行拆成单元格列表（跳过表头/分隔线）。"""
    out = []
    for line in md.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue                                   # |---|---|
        if cells[0] in ("块", "文件"):
            continue                                   # 表头
        out.append(cells)
    return out


def parse_manifest():
    """→ (files, exceptions)；files = [{block, prefixes, path, role, budget}]"""
    md = _read(DOC)
    i = md.find(SECTION)
    if i < 0:
        raise SystemExit("UI_ARCHITECTURE.md 里找不到「%s」" % SECTION)
    seg = md[i:]
    nxt = seg.find("\n## ", 1)
    if nxt > 0:
        seg = seg[:nxt]
    # 表 2 之前 / 之后
    k = seg.find("### 表 2")
    t1, t2 = (seg[:k], seg[k:]) if k > 0 else (seg, "")

    files = []
    for cells in _rows(t1):
        if len(cells) < 5:
            raise SystemExit("表 1 的行只有 %d 列（要 5 列）：%r" % (len(cells), cells))
        block, prefixes, path, role, budget = cells[0], cells[1], cells[2], cells[3], cells[4]
        path = path.strip("`").strip()
        b = re.search(r"\d+", budget)
        files.append({"block": block,
                      "prefixes": [p.strip() for p in prefixes.split(",") if p.strip()],
                      "path": path, "role": role,
                      "budget": int(b.group(0)) if b else None})
    exc = []
    for cells in _rows(t2):
        if len(cells) < 3:
            raise SystemExit("表 2 的行只有 %d 列（要 3 列）：%r" % (len(cells), cells))
        exc.append({"file": cells[0].strip("`").strip(), "scope": cells[1].strip(),
                    "reason": cells[2].strip()})
    return files, exc


def _abs(rel):
    return os.path.join(ROOT, rel.replace("/", os.sep))


# ============================================================ 主流程
def main():
    print("=" * 66)
    print("屏幕块守卫（UI_ARCHITECTURE.md 的「网页屏幕块清单」 vs 实际文件）")
    print("=" * 66)
    files, exc = parse_manifest()
    blocks = []
    for f in files:
        if f["block"] not in blocks:
            blocks.append(f["block"])
    print("        清单：%d 个块、%d 个文件、%d 条例外"
          % (len(blocks), len(files), len(exc)))

    # ---- ① 文件都存在 ----
    print("\n== ① 清单里每个文件都存在 ==")
    missing = [f["path"] for f in files if not os.path.isfile(_abs(f["path"]))]
    for m in missing:
        check("存在 %s" % m, False, "清单里写了，磁盘上没有")
    if not missing:
        check("全部 %d 个文件都在磁盘上" % len(files), True)

    # ---- ② 行数预算 ----
    print("\n== ② 屏模块 ≤ %d 行（硬上限 %d）==" % (LINE_BUDGET, LINE_HARD))
    over = []
    for f in files:
        if not f["path"].endswith(".js"):
            continue
        if not os.path.isfile(_abs(f["path"])):
            continue
        n = _lines(_abs(f["path"]))
        budget = f["budget"] or LINE_BUDGET
        hard = n > LINE_HARD
        soft = n > budget or n > LINE_BUDGET
        if hard or soft:
            over.append((f["path"], n, "硬上限" if hard else "超预算"))
        print("        %-40s %4d 行（预算 %d）%s"
              % (f["path"], n, budget, "  ← 超了" if (hard or soft) else ""))
    for path, n, why in over:
        check("%s 行数合规" % path, False, "%d 行（%s）" % (n, why))
    if not over:
        check("清单里的屏模块都在预算内", True)
    # 硬上限对**所有**屏模块生效（不只看清单：防"不登记就免检"）
    screens_dir = os.path.join(WEB, "js", "screens")
    huge = []
    if os.path.isdir(screens_dir):
        for fn in sorted(os.listdir(screens_dir)):
            if not fn.endswith(".js"):
                continue
            n = _lines(os.path.join(screens_dir, fn))
            if n > LINE_HARD:
                huge.append((fn, n))
    for fn, n in huge:
        check("屏模块 %s 不超过硬上限" % fn, False, "%d 行 > %d" % (n, LINE_HARD))
    if not huge:
        check("所有 web/js/screens/*.js 都 ≤ %d 行" % LINE_HARD, True)

    # ---- ③ 片段不许嵌套挂载点 ----
    print("\n== ③ 片段里不许嵌套 <!--@screen: … --> ==")
    nested = []
    frags = []
    sdir = os.path.join(WEB, "screens")
    if os.path.isdir(sdir):
        for fn in sorted(os.listdir(sdir)):
            if not fn.endswith(".html"):
                continue
            frags.append(fn)
            text = _read(os.path.join(sdir, fn))
            if re.search(r"<!--\s*@screen:", text):
                nested.append(fn)
    for fn in nested:
        check("%s 无嵌套挂载点" % fn, False, "片段里又写了 <!--@screen:…-->")
    if not nested:
        check("%d 个片段都没有嵌套挂载点" % len(frags), True)

    # ---- ④ 跨屏 id 引用 ----
    print("\n== ④ 屏模块不许摸别的屏前缀的 id（例外 ≤ %d 条）==" % MAX_EXCEPTIONS)
    known = set()
    for f in files:
        known |= set(f["prefixes"])
    allowed = set()
    for e in exc:
        fn = e["file"].replace("\\", "/")
        if fn.startswith("web/"):
            fn = fn[4:]
        allowed.add((fn, e["scope"]))
    for e in exc:
        check("例外 %s 写了理由" % e["file"], bool(e["reason"]) and len(e["reason"]) >= 10,
              "理由太短/为空")
    check("例外条数 ≤ %d" % MAX_EXCEPTIONS, len(exc) <= MAX_EXCEPTIONS,
          "现在 %d 条（白名单只许缩短，不许变长）" % len(exc))

    GETID = re.compile(r"""getElementById\(\s*['"]([A-Za-z_][\w-]*)['"]"""
                       r"""|querySelector(?:All)?\(\s*['"]#([A-Za-z_][\w-]*)""")

    def strip_comments(js):
        js = re.sub(r"/\*[\s\S]*?\*/", "", js)
        return "\n".join(("" if ln.lstrip().startswith("//") else ln)
                         for ln in js.split("\n"))

    hits = []
    for f in files:
        if not f["path"].endswith(".js") or not os.path.isfile(_abs(f["path"])):
            continue
        rel = f["path"][4:] if f["path"].startswith("web/") else f["path"]
        own = set(f["prefixes"])
        text = strip_comments(_read(_abs(f["path"])))
        for m in GETID.finditer(text):
            ident = m.group(1) or m.group(2)
            pre = re.match(r"[a-z]+", ident)
            pre = pre.group(0) if pre else ""
            if pre not in known or pre in own:
                continue
            if (rel, pre) in allowed:
                hits.append((f["path"], ident, pre, True))
            else:
                hits.append((f["path"], ident, pre, False))
    bad = [h for h in hits if not h[3]]
    for path, ident, other, ok in bad:
        check("%s 不摸 %s 前缀的 id" % (path, other), False, "发现 #%s" % ident)
    if not bad:
        check("零处未登记的跨屏 id 引用（已登记例外 %d 处）"
              % len([h for h in hits if h[3]]), True)

    # ---- ⑤ 新文件必须先登记 ----
    print("\n== ⑤ 块目录里的新文件必须先写进清单 ==")
    declared = set(f["path"] for f in files)
    undeclared = []
    if os.path.isdir(screens_dir):
        for fn in sorted(os.listdir(screens_dir)):
            if not fn.endswith(".js"):
                continue
            for p in sorted(known, key=len, reverse=True):
                if fn.startswith(p + "-"):
                    rel = "web/js/screens/" + fn
                    if rel not in declared:
                        undeclared.append(rel)
                    break
    for rel in undeclared:
        check("%s 已登记" % rel, False, "块目录里的新文件没写进「网页屏幕块清单」表 1")
    if not undeclared:
        check("块目录里没有未登记的文件", True)

    # ---- ⑥ index.html 只留挂载点 + script/link ----
    print("\n== ⑥ index.html 只留挂载点 / script / link ==")
    html = _read(INDEX)
    for f in files:
        rel = f["path"]
        if rel.endswith(".js") and "/js/screens/" in rel:
            src = rel.split("/js/screens/")[1]
            check("index.html 引了 %s" % src,
                  ('src="js/screens/%s"' % src) in html or ("src='js/screens/%s'" % src) in html,
                  "缺 <script>")
        elif rel.endswith(".css"):
            href = rel.split("/styles/")[1]
            check("index.html 引了 styles/%s" % href, ('href="styles/%s"' % href) in html, "缺 <link>")
        elif rel.endswith(".html") and rel.startswith("web/screens/"):
            name = os.path.splitext(os.path.basename(rel))[0]
            check("index.html 有 <!--@screen:%s--> 挂载点" % name,
                  ("<!--@screen:%s-->" % name) in html, "缺挂载点")

    # index.html 里不许再有这几屏的**实现**（门面必须住在模块里）
    leaked = re.findall(r"(?m)^function\s+((?:codex|cx|gal)[A-Z][\w$]*)\s*\(", html)
    check("index.html 里没有 codex/gal 函数的实现体（只该有挂载点）", not leaked,
          "还留着 " + "、".join(leaked[:6]))

    print("\n" + "=" * 66)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
