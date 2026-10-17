# -*- coding: utf-8 -*-
"""ui_snapshot.py —— 像素级回归安全网：结构 / 样式规则 / 内联样式 的"守恒"检查。

为什么要有它
------------
把一屏从 index.html 里搬走，最怕的不是"报错"，而是**悄悄地变了一点**：
少写一个 class、行内 style 少个属性、某条 CSS 声明被顺手改了 —— 页面照样能开，
只有用户看久了才觉得"哪里不对"。这种改动没有异常、没有断言，代码评审也很难一眼看出来。

所以这个工具把三样东西拍成快照，改动前后必须**逐字节一致**：
  1. DOM 结构树：`index.html` 里所有元素的 层级 + tag + id + class + 其余属性
     （按出现顺序平铺成一行一个元素，diff 时能直接看出少/多/改了哪个元素）；
  2. CSS 规则集合：`web/**/*.css` 里每条规则 → `选择器 { 声明… }`，声明按属性名排序；
  3. 行内 `style=`：每个带 style 属性的元素一条（这是最容易被"顺手"改掉的东西）。

**它能挡什么**（搬屏时最常犯的错）
  · DOM 层级/位置被挪错（模态从 #inputbar 里跑到 body 下、挂载点插错一层）；
  · class 改了名或漏了一个（`.modal-box` → `.modalbox`：页面不报错，只是样式没了）；
  · 元素 id 变了（JS 里的 getElementById 从此拿到 null）；
  · 某条 CSS 声明被改/删/重复（含 @media 上下文：同一条规则在 media 里外是两回事）；
  · 行内 style 被增删改（本轮不做美化，所以它必须一动不动）。
  结论：**结构 + 规则 + 行内 三层都没动** = 这次搬运没有碰观感。

**它不能挡什么**（别把它当浏览器）
  · 浏览器层的层叠计算：继承、同优先级规则的先后覆盖、`@supports`、伪类（:hover/:focus）、
    `:nth-child`、浮动/换行/字体度量 —— 这些要真的渲染出来才知道，本工具是静态的；
  · 运行时 DOM：`goPaint()` 画的棋盘、`dialRender()` 生成的 SVG、聊天消息、动态 style 赋值，
    静态文件里根本没有，快照也管不到（它们由各自的 JS 保证，靠 `tests/test_web_dom.py` 兜底）；
  · 文字内容：文案是易变数据（还要走 i18n），这里**整块跳过**，只认结构；
  · 真像素：颜色在主题变量里换一版，快照看不出来（那属于设计变更，本来也该是显式的）。
  换句话说：它是"搬运守恒"的栅栏，不是"渲染回归"的截图对比。

关于 `<!--@screen:名字-->`
------------------------
阶段的 2 步开始，一屏的 DOM 不再写在 index.html 里，而是搬到 `web/screens/<名字>.html`，
index.html 原地只留一个注释挂载点 `<!--@screen:名字-->`，由 `web/js/router.js` 同步注入。
本工具**认识这个语法**：遇到挂载点就把片段文件展开进来再拍快照。
所以"搬走"这件事本身不会让快照变红 —— 只有搬错（结构/样式/内联真的变了）才会红。

跑法：
    python -X utf8 tools/ui_snapshot.py --write     # 写基线 tools/ui_snapshot.json
    python -X utf8 tools/ui_snapshot.py --check     # 比对：不一致打印第一处差异并退出 1
    python -X utf8 tools/ui_snapshot.py --diff      # 比对：打印全部差异
    python -X utf8 tools/ui_snapshot.py --check --out 别的文件.json

退出码：0 = 一致；1 = 有差异；2 = 用错/基线不存在。
"""
import difflib
import io
import json
import os
import re
import sys

try:                                   # 只在老解释器上兜底，标准库就够用
    from html.parser import HTMLParser
except ImportError:                    # pragma: no cover
    HTMLParser = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
INDEX = os.path.join(WEB, "index.html")
SCREENS = os.path.join(WEB, "screens")
SNAP_DEFAULT = os.path.join(HERE, "ui_snapshot.json")

# 挂载点语法：<!--@screen:go-->；片<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌段文件 = web/screens/go.html
MARKER = re.compile(r"^@screen:([A-Za-z0-9_-]+)$")
# 空元素：没有闭合标签，别让栈跟着它往下钻
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
# 参与快照的样式来源：web/ 下所有 .css（theme.css 也进来 —— 它是生成物，但同样不该偷偷变）
CSS_SKIP_DIRS = {"live2d", "fonts", "icons", "gothic_img", "vendor"}
DIFF_LINES = 400                       # --diff 每段最多打这么多行，防刷屏


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ============================================================
#  DOM：解析 → 展开片段 → 平铺成"一行一个元素"
# ============================================================
class _Node(object):
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, attrs=None, children=None):
        self.tag = tag
        self.attrs = attrs or []
        self.children = children if children is not None else []


class _Parser(HTMLParser):
    """只关心元素与注释；文本一律丢弃（文案是易变数据，见文件头）。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = _Node("#root")
        self.stack = [self.root]
        self.fragments = []          # 展开过的片段名（按出现顺序，写进快照当证据）
        self.missing = []            # 挂载点但片段文件不存在
        self.depth = 0               # 防片段互相引用造成死循环

    # -- 元素 --
    def handle_starttag(self, tag, attrs):
        node = _Node(tag, [(k.lower(), "" if v is None else v) for k, v in attrs])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = _Node(tag, [(k.lower(), "" if v is None else v) for k, v in attrs])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        # 容错：HTML 里历史遗留的错配对别把整棵树带歪，向上找同名节点
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    # -- 挂载点 --
    def handle_comment(self, data):
        m = MARKER.match(data.strip())
        if not m:
            return
        self.expand(m.group(1))

    def expand(self, name):
        path = os.path.join(SCREENS, name + ".html")
        if not os.path.isfile(path):
            self.missing.append(name)
            return
        if self.depth > 8:
            return
        sub = _Parser()
        sub.depth = self.depth + 1
        sub.feed(_read(path))
        sub.close()
        self.stack[-1].children.extend(sub.root.children)
        self.fragments.append(name)
        self.fragments.extend(sub.fragments)
        self.missing.extend(sub.missing)


def _norm_style(value):
    """行内 style 规范化：掐空白、按属性名排序（换行/顺序差异不算改动）。"""
    out = []
    for part in (value or "").split(";"):
        part = " ".join(part.split())
        if part:
            out.append(part)
    return "; ".join(sorted(out))


def _flatten(children):
    """→ (dom 行列表, 行内 style 字典, 元素数)。一行 = 路径 TAB tag TAB id TAB class TAB 其余属性。"""
    lines = []
    inline = {}
    count = [0]

    def walk(nodes, prefix):
        seen = {}
        for node in nodes:
            tag = node.tag
            if not isinstance(tag, str) or tag.startswith("#"):
                continue
            seen[tag] = seen.get(tag, 0) + 1
            attr = {}
            for k, v in node.attrs:
                # 同名属性以最后一个为准（浏览器也是这个行为）
                attr[k] = v
            ident = attr.pop("id", "")
            klass = " ".join(sorted((attr.pop("class", "") or "").split()))
            style = attr.pop("style", None)
            rest = " ".join("%s=%s" % (k, v) for k, v in sorted(attr.items()))
            comp = "%s%s[%d]" % (tag, ("#" + ident) if ident else "", seen[tag])
            path = (prefix + "/" + comp) if prefix else comp
            lines.append("\t".join((path, tag, ident, klass, rest)))
            if style is not None:
                inline[path] = _norm_style(style)
            count[0] += 1
            walk(node.children, path)

    walk(children, "")
    return lines, inline, count[0]


# ============================================================
#  CSS：拆注释 → 逐条规则（@media 当上下文前缀）→ 声明排序
# ============================================================
def _strip_css_comments(text):
    out = []
    i, n = 0, len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _find_open(text, start):
    """下一个没被引号包住的 '{' 下标；没有就 -1。"""
    i, n = start, len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "{":
            return i
        i += 1
    return -1


def _match_brace(text, start):
    """text[start] == '{' → 配对的 '}' 下标（括号/引号里的不算）。"""
    depth = 0
    paren = 0
    quote = None
    i, n = start, len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
        elif c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif paren == 0 and c == "{":
            depth += 1
        elif paren == 0 and c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _norm_decls(body):
    """一条规则里的声明：掐空白、丢空项、按属性名排序。"""
    parts = []
    cur = []
    quote = None
    paren = 0
    for c in body:
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            continue
        if c in "\"'":
            quote = c
            cur.append(c)
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif c == ";" and paren == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(c)
    parts.append("".join(cur))
    decls = []
    for p in parts:
        p = " ".join(p.split())
        if p:
            decls.append(p)
    return "; ".join(sorted(decls))


def _css_rules(css, prefix, out):
    i = 0
    while True:
        j = _find_open(css, i)
        if j < 0:
            return
        prelude = " ".join(css[i:j].split())
        end = _match_brace(css, j)
        body = css[j + 1:end]
        if prelude.startswith("@"):
            low = prelude.lower()
            if low.startswith("@media") or low.startswith("@supports") or low.startswith("@layer"):
                # 条件块：里面每条规则都带上上下文，否则"挪进/挪出 @media"就看不出来了
                _css_rules(body, prefix + prelude + " ", out)
            else:
                # @font-face / @keyframes 之类：整块当一条规则
                out.append(prefix + prelude + " { " + _norm_decls(body) + " }")
        elif prelude:
            out.append(prefix + prelude + " { " + _norm_decls(body) + " }")
        i = end + 1


def _css_files():
    out = []
    for base, dirs, files in os.walk(WEB):
        dirs[:] = sorted(d for d in dirs if d not in CSS_SKIP_DIRS)
        for fn in sorted(files):
            if fn.lower().endswith(".css"):
                out.append(os.path.join(base, fn))
    return sorted(out)


def _collect_css():
    """所有 CSS 文件的规则，合成一个**全局排序的多重集**。

    为什么不按文件存：本轮允许把某屏专有规则从 screens.css 挪到 styles/screens/<名>.css。
    "只换存放位置"对层叠的影响由 <link> 顺序决定（那写在 index.html 里，是显式的），
    而"哪条规则还在不在"才是这里要守的东西 —— 所以比较口径是全局集合，不看它在哪个文件。
    """
    rules = []
    files = []
    for path in _css_files():
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        files.append(rel)
        _css_rules(_strip_css_comments(_read(path)), "", rules)
    return sorted(rules), files


# ============================================================
#  快照
# ============================================================
def build_snapshot():
    parser = _Parser()
    parser.feed(_read(INDEX))
    parser.close()
    dom, inline, n = _flatten(parser.root.children)
    css, css_files = _collect_css()
    return {
        "version": 1,
        "tool": "tools/ui_snapshot.py",
        "note": ("结构/样式/内联守恒快照。口径见本脚本顶部文档：能挡搬运时的无意改动，"
                 "挡不住浏览器层叠计算与运行时 DOM。合法改动请 --write 重钉。"),
        "counts": {
            "dom_elements": n,
            "css_rules": len(css),
            "inline_styles": len(inline),
            "fragments": parser.fragments,
            "missing_fragments": parser.missing,
            "css_files": css_files,
        },
        "dom": dom,
        "inline": dict(sorted(inline.items())),
        "css": css,
    }


def _dump(snap):
    return json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def _load(path):
    try:
        return json.loads(_read(path).lstrip(u"\ufeff"))
    except Exception as e:
        print(u"❌ 快照读不了：%s（%s）" % (path, e))
        print(u"   它是坏的就删掉重钉：python -X utf8 tools/ui_snapshot.py --write")
        return None


def _inline_lines(snap):
    return ["%s = %s" % (k, v) for k, v in sorted((snap.get("inline") or {}).items())]


def _diff_sections(old, new):
    """→ [(段名, 差异行列表)]，只含有差异的段。"""
    out = []
    for key, label in (("dom", "DOM 结构"), ("css", "CSS 规则"), ("inline", "行内 style")):
        if key == "inline":
            a, b = _inline_lines(old), _inline_lines(new)
        else:
            a, b = old.get(key) or [], new.get(key) or []
        if a == b:
            continue
        d = list(difflib.unified_diff(a, b,
                                      fromfile=u"旧快照/" + label, tofile=u"现在/" + label,
                                      n=2, lineterm=""))
        out.append((label, d))
    return out


def _print_diffs(diffs, full):
    total = 0
    for label, lines in diffs:
        # 统计真正的增删行（unified_diff 的头两行是 ---/+++，不算）
        changed = sum(1 for l in lines if l[:1] in ("+", "-") and not l.startswith(("+++", "---")))
        total += changed
        print(u"\n-- %s：%d 行有变化 --" % (label, changed))
        show = lines if full else lines[:24]
        for l in show:
            print("   " + l)
        if not full and len(lines) > len(show):
            print(u"   …（还有 %d 行，用 --diff 看全部）" % (len(lines) - len(show)))
        elif full and len(lines) > DIFF_LINES:
            print(u"   …（已截断到 %d 行）" % DIFF_LINES)
    return total


def main(argv):
    mode = "check"
    out = SNAP_DEFAULT
    if "--write" in argv:
        mode = "write"
    elif "--diff" in argv:
        mode = "diff"
    elif "--check" in argv:
        mode = "check"
    if "--out" in argv:
        i = argv.index("--out")
        out = argv[i + 1] if len(argv) > i + 1 else SNAP_DEFAULT
        if not os.path.isabs(out):
            out = os.path.join(ROOT, out)

    if not os.path.isfile(INDEX):
        print(u"❌ 找不到 %s" % INDEX)
        return 2

    now = build_snapshot()
    c = now["counts"]
    print(u"扫描 %s：元素 %d 个 ／ CSS 规则 %d 条（%d 个文件）／ 行内 style %d 处"
          % (os.path.relpath(INDEX, ROOT).replace("\\", "/"), c["dom_elements"],
             c["css_rules"], len(c["css_files"]), c["inline_styles"]))
    if c["fragments"]:
        print(u"     展开的片段：%s" % ("、".join(c["fragments"])))
    if c["missing_fragments"]:
        print(u"❌ 有挂载点但找不到片段文件：%s（web/screens/<名字>.html）"
              % ("、".join(c["missing_fragments"])))
        return 2

    if mode == "write":
        old = None
        if os.path.isfile(out):
            try:
                old = _load(out)
            except SystemExit:
                old = None
        try:
            with io.open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(_dump(now))
        except OSError as e:
            print(u"❌ 快照写不进去：%s（%s）" % (out, e))
            return 2
        same = old is not None and old.get("dom") == now["dom"] \
            and old.get("css") == now["css"] and old.get("inline") == now["inline"]
        print(u"== 基线已写入：%s%s ==" % (os.path.relpath(out, ROOT).replace("\\", "/"),
                                       u"（内容与上一版一致）" if same else ""))
        return 0

    if not os.path.isfile(out):
        print(u"❌ 还没有基线：%s" % os.path.relpath(out, ROOT).replace("\\", "/"))
        print(u"   先跑：python -X utf8 tools/ui_snapshot.py --write")
        return 2
    old = _load(out)
    if old is None:
        return 2

    diffs = _diff_sections(old, now)
    if not diffs:
        print(u"✅ 与基线一致：结构 / 样式规则 / 行内 style 都没动")
        return 0
    total = _print_diffs(diffs, full=(mode == "diff"))
    print(u"\n❌ 与基线不一致：%d 行差异（%s）" % (total, u"、".join(l for l, _ in diffs)))
    print(u"   搬屏时的无意改动就长这样。确实是有意改的，再 --write 重钉基线并说明原因。")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
