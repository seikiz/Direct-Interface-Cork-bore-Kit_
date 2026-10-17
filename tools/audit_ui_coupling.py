# -*- coding: utf-8 -*-
"""audit_ui_coupling.py —— 把「UI 解耦程度」变成可量化的数字。

为什么要有它
------------
「解耦」听起来很对，但只要没人量，就永远是"感觉松了点"。
这个脚本把六个硬指标固定下来，跑一次给出**当前分 + 每个指标的原始数字 + Top10 重灾点**，
并用 `--baseline` 把现状钉成基线：以后谁改完跑一遍，数字变差就非 0 退出（CI 能拦）。

六个指标（每项都是"越小越好"，除了第 6 项的复用率用来展示）
  1. 大文件：单文件 >1500 行算超标。一个文件里塞下整屏逻辑，等于把界面和实现焊死。
  2. index.html 的行内样式：`<style>` 块数 + 块总行数 + 行内 `style="..."` 次数。
     样式长在页面里 → 改配色要改页面结构，换皮肤/换框架都下不去手。
  3. 硬编码颜色：`#rrggbb` / `rgba(...)` / `Color(0xFF…)`。颜色该只在令牌文件里出现一次。
  4. 网页顶层全局可变状态：`^var x = …` 且在别处被**重新赋值**（不是只读常量）。
     全局可变状态是屏与屏之间的隐形电话线 —— 谁都能改，谁都不知道谁改了。
  5. 屏与屏的耦合：一个屏的代码里引用另一个屏的 DOM id 前缀（网页）／
     一个屏文件引用另一个屏的顶层符号（安卓）。这是"能不能单独搬走一屏"的直接度量。
  6. 组件复用度：裸控件（`<button`、`Button(`/`TextButton(`）vs 自家组件。
     散装的越多，改一次按钮样式就得改 N 处。

跑法：
    python tools/audit_ui_coupling.py                       # 控制台打分表
    python tools/audit_ui_coupling.py --json                # 机器可读（stdout 只有 JSON）
    python tools/audit_ui_coupling.py --baseline tools/ui_coupling_baseline.json
                                                           # 没基线→写；有基线<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌→比，恶化则退出 1
    python tools/audit_ui_coupling.py --baseline … --force  # 覆盖基线（改完确实变好了再用）
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
INDEX = os.path.join(WEB, "index.html")
ANDROID = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")

BASELINE_DEFAULT = os.path.join(HERE, "ui_coupling_baseline.json")

# ---------------------------------------------------------------- 扫描范围
# 只扫这些后缀：UI 代码全在这三种里（安卓是 .kt）。
WEB_EXTS = (".html", ".js", ".css")
# 第三方（pixi / live2d）与字体资源目录不参与统计：那是别人的压缩代码，
# 算进"大文件"只会把真正的重灾区埋掉。
WEB_SKIP_DIRS = {"live2d", "fonts", "icons", "gothic_img", "vendor"}
# 生成物：本来就满是颜色/图标，扫它们等于自己跟自己比（与 tools/audit_contrast.py 同一口径）。
GENERATED = {"theme.css", "icons.js", "i18n.js", "IconNames.kt", "Tokens.kt",
             "I18nStrings.kt", "icon_scope.js"}

BIG_FILE_LINES = 1500          # 超标线
TOLERANCE = 1e-6               # 浮点比较容差

# ---------------------------------------------------------------- 屏前缀表
# 从代码归纳出来的「屏」：前缀 → 屏名。网页端 id 用驼峰前缀（stAccentBtn），
# 安卓端没有前缀，靠文件归属（见 AND_SCREENS）。
# 归纳方法：把 index.html 里 500 多个 id 按首段小写词聚类，取成规模的簇，
# 再按它们所在的容器（modal / 全屏 panel）确认是不是独立的一屏。
SCREENS = {
    "chat": "主聊天（外壳）", "st": "设置", "nr": "新建角色", "pp": "角色卡编辑",
    "role": "角色卡槽", "world": "世界卡槽", "save": "多存档", "ws": "世界书/世界卡库",
    "wm": "世界书条目", "codex": "编年史编辑器", "cx": "编年史播放器",
    "gal": "GAL 制作器", "go": "围棋", "gen": "生图", "ev": "事件编辑器",
    "mem": "记忆调试", "trpg": "跑团", "dial": "时间表盘", "fin": "财报折叠",
    "qc": "快捷面板", "onb": "首次引导", "crop": "图片裁剪", "em": "编辑消息",
    "offline": "离线推进", "bk": "加密备份", "sg": "箭头教程", "l2d": "Live2D",
}
# 外壳自己的 id 没有统一前缀（input / send / choices / mechbar…），
# 归到 chat 这一屏；否则它们会被当成"无主"，指标就漏掉一半。
BASE_IDS = {"app", "sidebar", "sideToggle", "main", "topbar", "chat", "input",
            "inputbar", "send", "quickpanel", "imgprev", "choices", "mechbar",
            "battlebar", "branchWrap", "branchPanel", "l2d-stage", "l2d-hint",
            "onboard", "achToast", "msgs", "wallpaper"}

# 安卓端：屏文件 → 屏名。其余文件是共享件（Ui.kt 组件 / Theme/Tokens 主题等）。
AND_SCREENS = {
    "App.kt": "主界面（会话/侧栏）",
    "Dialogs.kt": "对话框集合",
    "LifeSpaceSettings.kt": "生活·空间设置屏",
}


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _lines(text):
    return text.split("\n")


def _rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


# ============================================================
#  文件清单
# ============================================================
def web_files():
    """web/ 下的 UI 源码（不含第三方与资源目录）。"""
    out = []
    for base, dirs, files in os.walk(WEB):
        dirs[:] = [d for d in dirs if d not in WEB_SKIP_DIRS]
        for fn in sorted(files):
            if os.path.splitext(fn)[1].lower() in WEB_EXTS:
                out.append(os.path.join(base, fn))
    return sorted(out)


def android_files():
    if not os.path.isdir(ANDROID):
        return []
    return sorted(os.path.join(ANDROID, fn) for fn in os.listdir(ANDROID)
                  if fn.endswith(".kt"))


def _counted(path):
    """参与"颜色/指标"统计的文件：去掉生成物。"""
    return os.path.basename(path) not in GENERATED


# ============================================================
#  ① 大文件
# ============================================================
def metric_big_files(paths):
    rows = []
    for p in paths:
        n = len(_lines(_read(p)))
        rows.append((n, _rel(p)))
    rows.sort(reverse=True)
    over = sum(max(0, n - BIG_FILE_LINES) for n, _ in rows)
    bad = [r for r in rows if r[0] > BIG_FILE_LINES]
    tops = ["%s：%d 行（超 %d）" % (p, n, n - BIG_FILE_LINES) for n, p in bad[:10]]
    return {"key": "big_files", "label": "① 大文件（>%d 行）" % BIG_FILE_LINES,
            "value": over, "unit": "超标行数合计", "count": len(bad),
            "score": 100.0 / (1.0 + over / 1000.0), "weight": 20,
            "top": tops, "rows": [{"file": p, "lines": n} for n, p in rows[:10]]}


# ============================================================
#  ② index.html 的行内样式
# ============================================================
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.S)
INLINE_STYLE = re.compile(r"""\sstyle\s*=\s*["']""")


def metric_html_style(html):
    blocks = list(STYLE_BLOCK.finditer(html))
    block_lines = 0
    tops = []
    for m in blocks:
        seg = m.group(1)
        if seg.startswith("\n"):      # `<style>` 后面的换行不算块内容
            seg = seg[1:]
        n = len(_lines(seg))
        if seg.endswith("\n"):
            n -= 1
        block_lines += n
        start = html[:m.start()].count("\n") + 1
        tops.append("<style> 块 @第%d行：%d 行" % (start, n))
    inline = list(INLINE_STYLE.finditer(html))
    # 行内样式最密集的行（Top10）—— 以后搬家先从这里下手
    per_line = {}
    for m in inline:
        ln = html[:m.start()].count("\n") + 1
        per_line[ln] = per_line.get(ln, 0) + 1
    hot = sorted(per_line.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    lines = _lines(html)
    for ln, cnt in hot:
        snippet = lines[ln - 1].strip() if 0 <= ln - 1 < len(lines) else ""
        tops.append("第%d行：%d 处 style=… %s" % (ln, cnt, snippet[:70]))
    # 分数：块行数最重（那是整块样式），行内次之（零碎但同样卡住换皮肤）
    penalty = block_lines + len(inline) * 1.5 + len(blocks) * 3.0
    return {"key": "html_style", "label": "② index.html 行内样式",
            "value": round(penalty, 1), "unit": "惩罚分（块行数 + 行内×1.5 + 块×3）",
            "count": len(inline), "blocks": len(blocks), "block_lines": block_lines,
            "inline": len(inline),
            "score": 100.0 / (1.0 + penalty / 200.0), "weight": 15,
            "top": tops, "rows": [{"line": ln, "inline": c} for ln, c in hot]}


# ============================================================
#  ③ 硬编码颜色
# ============================================================
COLOR_RES = [
    ("#rrggbb", re.compile(r"#[0-9a-fA-F]{6}\b")),
    ("rgba(", re.compile(r"\brgba?\s*\(")),
    ("Color(0x…)", re.compile(r"\bColor\s*\(\s*0x[0-9a-fA-F]{6,8}")),
]


def metric_colors(paths):
    total = 0
    per_file = []
    for p in paths:
        if not _counted(p):
            continue
        text = _read(p)
        n = sum(len(rx.findall(text)) for _k, rx in COLOR_RES)
        if n:
            per_file.append((n, _rel(p)))
    per_file.sort(reverse=True)
    total = sum(n for n, _ in per_file)
    tops = ["%s：%d 处" % (p, n) for n, p in per_file[:10]]
    return {"key": "colors", "label": "③ 硬编码颜色",
            "value": total, "unit": "颜色字面量处数", "count": len(per_file),
            "score": 100.0 / (1.0 + total / 150.0), "weight": 15,
            "top": tops, "rows": [{"file": p, "count": n} for n, p in per_file[:10]]}


# ============================================================
#  ④ 网页顶层全局可变状态
# ============================================================
TOP_VAR = re.compile(r"^var\s+([A-Za-z_$][\w$]*)\s*=")


def metric_globals(js_texts):
    """顶层 `var x = …` 且后续被重新赋值 → 一个"全局可变状态"。

    js_texts 里既有 index.html 的内联脚本，也有 web/*.js（i18n.js/icons.js 是生成物、
    已在调用处剔掉）。统计"赋值次数"时把两边拼起来看，跨文件重新赋值也算。
    """
    decl = []
    for label, text in js_texts:
        for i, line in enumerate(_lines(text), 1):
            m = TOP_VAR.match(line)
            if m:
                decl.append((m.group(1), label, i))
    rows = []
    all_text = "\n".join(t for _l, t in js_texts)
    seen = set()
    for name, label, ln in decl:
        if name in seen:
            continue
        seen.add(name)
        # 统计"赋值"次数（含声明那一行）；>=2 才算可变
        n = len(re.findall(r"(?<![\w$.])" + re.escape(name) + r"\s*=(?!=)", all_text))
        if n >= 2:
            rows.append((n, name, label, ln))
    rows.sort(reverse=True)
    tops = ["%s ← %s:%d（被赋值 %d 次）" % (nm, lb, ln, n) for n, nm, lb, ln in rows[:10]]
    return {"key": "globals", "label": "④ 顶层全局可变状态",
            "value": len(rows), "unit": "个", "count": len(decl),
            "score": 100.0 / (1.0 + len(rows) / 8.0), "weight": 15,
            "top": tops, "rows": [{"name": nm, "file": lb, "line": ln, "assigns": n}
                                  for n, nm, lb, ln in rows[:10]]}


# ============================================================
#  ⑤ 屏与屏的耦合
# ============================================================
SCRIPT_BLOCK = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)
TOP_DECL = re.compile(r"^(?:function\s+([A-Za-z_$][\w$]*)|var\s+([A-Za-z_$][\w$]*))")
ID_REF = re.compile(r"""getElementById\(\s*['"]([\w-]+)['"]"""
                    r"""|querySelector(?:All)?\(\s*['"]#([\w-]+)"""
                    r"""|['"]#([\w-]+)['"]""")


def _prefix(name):
    m = re.match(r"[a-z]+", name)
    return m.group(0) if m else ""


def _screen_of_id(dom_id):
    if dom_id in BASE_IDS:
        return "chat"
    pre = _prefix(dom_id)
    if pre in SCREENS:
        return pre
    if pre == "msg":
        return "chat"
    return None


def _brace_delta(line):
    """这一行让花括号净深 +几（先剥掉字符串与行注释，避免把 `'{'` 数成代码）。"""
    out = 0
    i = 0
    n = len(line)
    quote = None
    while i < n:
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
        elif c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        elif c == "{":
            out += 1
        elif c == "}":
            out -= 1
        i += 1
    return out


def _chunks(text, base_line=1):
    """按"顶层声明 + 花括号配平"切块 → [(名字, 文件内起始行, 块文本)]。

    两个坑（都是这个脚本第一版真踩过的）：
      · 只看到下一个 `^function` 就断块 → 函数后面那些"顶层绑定语句"
        （`document.getElementById('codexDelBtn').onclick = …`）会被算进上一个函数，
        跨屏引用数凭空翻倍、Top10 全是指错的行号。所以这里数花括号，回到 0 就算块结束。
      · 回到 0 之后如果下一行不是新的顶层声明，必须**另起一个匿名块**
        （名字为空，按它引用的屏多数票归属）；否则整段胶水代码还是挂在上一个函数名下。
    连续的多条匿名语句合并成一块，免得一个 chunk 一行、噪声太大。
    """
    out = []
    cur = None
    depth = 0
    for i, line in enumerate(_lines(text), 1):
        if depth <= 0:
            m = TOP_DECL.match(line)
            if m:
                if cur:
                    out.append((cur[0], cur[1], "\n".join(cur[2])))
                cur = [(m.group(1) or m.group(2)), base_line + i - 1, []]
            elif cur is None or cur[0]:
                # 上一个块是命名的（刚闭合）或还没有块 → 开一个匿名块
                if cur:
                    out.append((cur[0], cur[1], "\n".join(cur[2])))
                cur = ["", base_line + i - 1, []]
            depth = 0
        cur[2].append(line)
        depth += _brace_delta(line)
    if cur:
        out.append((cur[0], cur[1], "\n".join(cur[2])))
    return out


def metric_coupling_web(html, js_texts):
    """一个屏的函数里出现另一个屏的 id 引用 → 记一笔跨屏耦合。"""
    sources = []
    for m in SCRIPT_BLOCK.finditer(html):
        base = html[:m.start(1)].count("\n") + 1
        sources.append(("web/index.html", m.group(1), base))
    sources += [(lb, t, 1) for lb, t in js_texts]
    hits = []          # (count, 函数名, 文件/行, 引用到的屏)
    total = 0
    per_screen = {}
    for label, text, base in sources:
        for name, line, body in _chunks(text, base):
            pre = _prefix(name) if name else ""
            own = pre if pre in SCREENS else None
            if own is None:
                # 函数名前缀不是屏（render* / load* / set* …）→ 按它引用的屏多数票归属
                votes = {}
                for m in ID_REF.finditer(body):
                    sid = m.group(1) or m.group(2) or m.group(3)
                    sc = _screen_of_id(sid)
                    if sc:
                        votes[sc] = votes.get(sc, 0) + 1
                own = max(votes.items(), key=lambda kv: kv[1])[0] if votes else "chat"
            foreign = {}
            for m in ID_REF.finditer(body):
                sid = m.group(1) or m.group(2) or m.group(3)
                sc = _screen_of_id(sid)
                if sc and sc != own:
                    foreign[sc] = foreign.get(sc, 0) + 1
            if foreign:
                n = sum(foreign.values())
                total += n
                top_sc = max(foreign.items(), key=lambda kv: kv[1])[0]
                pair = sc_label(own) + "→" + sc_label(top_sc)
                per_screen[pair] = per_screen.get(pair, 0) + n
                hits.append((n, name or "(顶层绑定语句)", "%s:%d" % (label, line), top_sc))
    hits.sort(reverse=True)
    tops = ["%s（%s）引用 %s 的 id：%d 处" % (nm, where, sc_label(sc), n)
            for n, nm, where, sc in hits[:10]]
    pairs = sorted(per_screen.items(), key=lambda kv: -kv[1])[:10]
    return {"value": total, "tops": tops, "pairs": pairs}


def sc_label(key):
    return SCREENS.get(key, key)


AND_DECL = re.compile(r"^(?:fun|class|object|data class|enum class|val|var)\s+"
                      r"(?:(?:<[^>]*>)\s*)?([A-Za-z_]\w*)")
AND_IMPORT = re.compile(r"^import\s+com\.dick\.app\.([A-Za-z_]\w*)")


def metric_coupling_android(paths):
    decls = {}          # 屏文件 → [顶层符号]
    for p in paths:
        fn = os.path.basename(p)
        if fn not in AND_SCREENS:
            continue
        own = []
        for line in _lines(_read(p)):
            if line.startswith("private ") or line.startswith("internal "):
                continue
            m = AND_DECL.match(line)
            if m:
                own.append(m.group(1))
        decls[fn] = own
    hits = []
    total = 0
    for p in paths:
        fn = os.path.basename(p)
        if fn not in AND_SCREENS:
            continue
        text = _read(p)
        imports = set(AND_IMPORT.findall(text))
        for other, names in decls.items():
            if other == fn:
                continue
            n = 0
            for nm in names:
                n += len(re.findall(r"(?<![\w.])" + re.escape(nm) + r"(?![\w])", text))
            n += len(imports & set(names))
            if n:
                total += n
                hits.append((n, "%s → %s" % (fn, other),
                             "、".join(names[:4])))
    hits.sort(reverse=True)
    tops = ["%s：%d 处（%s…）" % (k, n, sym) for n, k, sym in hits[:10]]
    return {"value": total, "tops": tops, "pairs": hits[:10],
            "decls": dict((k, len(v)) for k, v in decls.items())}


def metric_coupling(html, js_texts, and_paths):
    web = metric_coupling_web(html, js_texts)
    and_ = metric_coupling_android(and_paths)
    value = web["value"] + and_["value"]
    tops = ["[网页] " + t for t in web["tops"]] + ["[安卓] " + t for t in and_["tops"]]
    return {"key": "coupling", "label": "⑤ 屏与屏的耦合",
            "value": value, "unit": "跨屏引用处数（网页 %d + 安卓 %d）"
                                   % (web["value"], and_["value"]),
            "count": len(web["tops"]) + len(and_["tops"]),
            "web": web["value"], "android": and_["value"],
            "score": 100.0 / (1.0 + value / 40.0), "weight": 20,
            "top": tops[:10],
            "rows": [{"pair": k, "count": n} for k, n in web["pairs"]]}


# ============================================================
#  ⑥ 组件复用度
# ============================================================
BTN_RAW = re.compile(r"<button\b")
BTN_SHARED = re.compile(r"""<button\b[^>]*\bclass\s*=\s*["'][^"']*\b"""
                        r"""(?:btn2?|iconbtn|chip2?|battle-btn|choice-btn|tabbtn)\b""")
AND_RAW = re.compile(r"\b(?:TextButton|OutlinedButton|IconButton|Button)\s*\(")
AND_OWN = re.compile(r"\b(?:IconText|MsIcon|DickButton|TextBtns)\s*\(")
AND_OWN_DEF = re.compile(r"^fun\s+(?:IconText|MsIcon|DickButton)\s*\(", re.M)
# 网页端没有"组件定义"这回事，退一步数共享控件的**样式定义**处：
# .btn / .btn2 / .iconbtn / .chip / .chip2 / .battle-btn / .choice-btn / .tabbtn 各几条规则。
CSS_BTN_DEF = re.compile(r"(?m)^\s*\.(?:btn|btn2|iconbtn|chip2?|battle-btn|choice-btn|tabbtn)"
                         r"\b[^{,;]*\{")


def metric_reuse(files):
    """散装控件数（越小越好）；复用率与定义处数量只用来展示。"""
    raw = shared = defs = 0
    per_file = []
    for p in files:
        if not _counted(p):
            continue
        text = _read(p)
        a = len(BTN_RAW.findall(text))
        b = len(BTN_SHARED.findall(text))
        c = len(AND_RAW.findall(text))
        d = len(AND_OWN.findall(text))
        if p.endswith(".css"):
            defs += len(CSS_BTN_DEF.findall(text))
        if p.endswith(".kt"):
            defs += len(AND_OWN_DEF.findall(text))
        if a or c:
            per_file.append((a + c, _rel(p), a, c, d))
        raw += a + c
        shared += b + d
    per_file.sort(reverse=True)
    total = raw
    reuse = 100.0 * shared / raw if raw else 100.0
    tops = ["%s：裸控件 %d（网页 %d／安卓 %d），自家组件调用 %d" % (p, n, a, c, d)
            for n, p, a, c, d in per_file[:10]]
    return {"key": "reuse", "label": "⑥ 组件复用度（裸控件越少越好）",
            "value": total, "unit": "裸控件出现次数（共享件调用 %d ／ 定义处 %d）"
                                   % (shared, defs),
            "count": shared, "defs": defs,
            "reuse_pct": round(reuse, 1),
            "score": reuse, "weight": 15, "top": tops,
            "rows": [{"file": p, "raw": n} for n, p, a, c, d in per_file[:10]]}


# ============================================================
#  汇总
# ============================================================
def collect():
    wf = web_files()
    af = android_files()
    html = _read(INDEX) if os.path.isfile(INDEX) else ""
    js_texts = [("web/" + os.path.basename(p), _read(p)) for p in wf
                if p.endswith(".js") and _counted(p)]
    # 全局可变状态要把 index.html 的内联脚本算进去 —— 那是真正的主战场；
    # 只数 web/*.js 会得出 0 个全局状态的假结论。
    inline_js = [(html[:m.start(1)].count("\n") + 1, m.group(1))
                 for m in SCRIPT_BLOCK.finditer(html)]
    glob_sources = [("web/index.html", t) for _b, t in inline_js] + js_texts
    metrics = [
        metric_big_files(wf + af),
        metric_html_style(html),
        metric_colors(wf + af),
        metric_globals(glob_sources),
        metric_coupling(html, js_texts, af),
        metric_reuse(wf + af),
    ]
    wsum = sum(m["weight"] for m in metrics)
    total = sum(m["score"] * m["weight"] for m in metrics) / wsum if wsum else 0.0
    return {"version": 1,
            "tool": "tools/audit_ui_coupling.py",
            "total_score": round(total, 1),
            "metrics": metrics,
            "counts": {"web_files": len(wf), "android_files": len(af)}}


# ============================================================
#  输出
# ============================================================
def print_table(res, top=10):
    print("=" * 78)
    print("UI 耦合打分表  ——  解耦分 %s / 100（越高越松）" % res["total_score"])
    print("扫描：web/ %d 个文件 ＋ 安卓 %d 个 .kt"
          % (res["counts"]["web_files"], res["counts"]["android_files"]))
    print("=" * 78)
    print("%-26s %10s %8s %6s   %s" % ("指标", "原始值", "子分", "权重", "单位"))
    for m in res["metrics"]:
        print("%-26s %10s %8.1f %5d%%   %s"
              % (m["label"], m["value"], m["score"], m["weight"], m["unit"]))
    for m in res["metrics"]:
        print("\n-- %s  Top%d 重灾点" % (m["label"], top))
        if not m["top"]:
            print("   （无：这一项是干净的）")
        for i, t in enumerate(m["top"][:top], 1):
            print("   %2d) %s" % (i, t))
    print()


def _baseline_of(res):
    """基线里只存**原始值**（子分公式以后能改，原始值不会说谎）。"""
    out = {"version": 1, "tool": res["tool"],
           "note": ("UI 解耦阶段2（状态/路由 + 5 个低耦合小屏搬出 index.html）完成时的现状；"
                    "指标口径见本脚本顶部文档。阶段 3/4/5 只会更好，别让数字退回去。"),
           "total_score": res["total_score"],
           "metrics": {}, "counts": res["counts"]}
    for m in res["metrics"]:
        out["metrics"][m["key"]] = {"value": m["value"], "unit": m["unit"],
                                    "score": round(m["score"], 2)}
    return out


def compare_baseline(res, path, force):
    new = _baseline_of(res)
    if os.path.isfile(path) and not force:
        try:
            old = json.loads(_read(path).lstrip(u"\ufeff"))
        except Exception as e:
            # 基线坏了就是坏了：不许静默覆盖（那就等于把"变差"悄悄抹掉）。
            print("❌ 基线读不了：%s（%s）\n   它是坏的就删掉重钉，别让它悄悄失效。" % (path, e))
            return 2
        if old:
            print("== 与基线对比：%s ==" % _rel(path))
            worse = []
            for key, nm in new["metrics"].items():
                om = (old.get("metrics") or {}).get(key)
                if not om:
                    print("   ?  %-10s 基线里没有，跳过" % key)
                    continue
                ov, nv = float(om["value"]), float(nm["value"])
                d = nv - ov
                flag = "="
                if d > TOLERANCE:
                    flag, worse = "变差", worse + [key]
                elif d < -TOLERANCE:
                    flag = "变好"
                print("   %-4s %-10s %8.2f → %8.2f   (%+.2f)" % (flag, key, ov, nv, d))
            if worse:
                print("\n❌ 有 %d 项比基线更耦合：%s" % (len(worse), "、".join(worse)))
                print("   要么改回去，要么在 review 里说清为什么值得（再 --force 重钉基线）。")
                return 1
            print("   ✅ 与基线一致（没有一项变差）")
            return 0
    try:
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(new, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
    except OSError as e:
        # 本机有个坑：python 写不进 $env:TEMP（PowerShell 能写）——别抛栈，说清就行。
        print("❌ 基线写不进去：%s（%s）" % (path, e))
        return 2
    print("== 基线已写入：%s ==" % _rel(path))
    return 0


def main(argv):
    as_json = "--json" in argv
    force = "--force" in argv
    top = 10
    if "--top" in argv:
        try:
            top = int(argv[argv.index("--top") + 1])
        except (IndexError, ValueError):
            print("--top 需要一个整数")
            return 2
    base = None
    if "--baseline" in argv:
        i = argv.index("--baseline")
        base = argv[i + 1] if len(argv) > i + 1 else BASELINE_DEFAULT

    res = collect()
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print_table(res, top)

    rc = 0
    if base:
        if not os.path.isabs(base):
            base = os.path.join(ROOT, base)
        if as_json:
            # JSON 模式下人看的对比结论走 stderr，stdout 保持纯 JSON
            out = sys.stdout
            sys.stdout = sys.stderr
            rc = compare_baseline(res, base, force)
            sys.stdout = out
        else:
            rc = compare_baseline(res, base, force)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
