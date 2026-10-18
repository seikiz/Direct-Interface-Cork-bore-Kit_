# -*- coding: utf-8 -*-
"""界面文案"技术说明"清零 —— 网页 + 安卓两端守护。

为什么需要
----------
2026-12 用户原话：**「去掉应用内所有技术说明部分，用户不需要看到这些」**，并确认口径：
「只清散落各处的技术说明，API 教程页保留」。

清理之前界面上真的能看到这些：
  · 地址/端点 —— 工坊状态行打 `自动连接：http://154.94.226.240:8080`、代理框写
    `http://127.0.0.1:7890`、设置里挂 `https://…workers.dev`；
  · 协议/状态码 —— `已连接（认证:key · ↓12 ❤3）`、`HTTP 401：服务器要求 Key`、
    `（HTTP 404）——线上可能还是旧版`、`链路限流，稍后再试（服务器一直回 429）`；
  · 实现细节 —— `本地文件不存在：x.json（saves 下共 3 个 .json）`、
    `写 life_config.json / space_config.json`、`服务器为旧版，无世界卡包`；
  · 参数说明 —— `温度（留空=默认）`、`停止序列（指令模板，逗号分隔…）`。

这些都不报错、也不影响功能，只是"穿帮"——用户看得见却不该看见。清理完成之后**必须
有东西拦住它回来**，否则下一次加功能又会顺手把地址拼进状态行。

口径（很窄，故意的）
--------------------
扫的是**用户真的会读到的文本**：
  · `.html`：注释剥掉；只取文本位 + 可见属性（placeholder / title / alt / aria-label）；
    `<script>` / `<style>` 正文不算 HTML 文本（里面有内联 JS，另按 JS 规则扫）；
  · `.js` / `.kt`：注释剥掉；只取**含中日文的字符串字面量**——纯 ASCII 字面量是代码
    常量（`"http://127.0.0.1:11434/v1/models"` 这种探测地址、`"st_base_url"` 这种键名），
    不是界面文案，扫它们只会制造噪声；
  · `console.*` / `println` / `Log.*` 整行跳过 —— 那是开发者日志，本来就该带状态码；
  · 单独一个文件名（`"咲.json"`、`"wo.json"`）不算"说明"，跳过；出现在句子里才算。

白名单（每条都必须写理由，上限 10 条）
--------------------------------------
  ① API 教程页三个文件 —— 用户口径明确保留，那里**就是**给新手看技术信息的地方；
  ② mem / trpg 两个调试面板 —— 用户口径明确保留（开发者面板）。

跑法：utau_env\\Scripts\\python.exe -X utf8 tests\\test_no_dev_copy.py
"""
import io
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from html.parser import HTMLParser
except ImportError:                                     # pragma: no cover
    HTMLParser = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
APP = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")

PASS = 0
FAIL = 0

# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  白名单：文件级，每条都得说清为什么（上限 10，见断言）
# ============================================================
EXCLUDE = {
    "web/screens/api_guide.html":
        u"API 教程面板的壳：用户口径「API 教程页保留」，那一页就是给新手看技术信息的地方",
    "web/js/screens/api_guide.js":
        u"API 教程 + 首启向导的正文：同上（base_url / 401 / 429 / 限流 全是有意保留的教学内容）",
    "DICK-Android/app/src/main/java/com/dick/app/ui/screens/api/ApiGuideScreen.kt":
        u"安卓端的同一页 API 教程：与网页端逐条对齐，按用户口径一字不改",
    "web/screens/mem.html":
        u"记忆调试面板（开发者模式里的 mem 面板）：用户口径明确保留的调试面板",
    "web/js/screens/mem.js":
        u"记忆调试面板的行为：同上",
    "web/screens/trpg.html":
        u"跑团调试面板：用户口径明确保留的调试面板",
    "web/js/screens/trpg.js":
        u"跑团调试面板的行为：同上",
}
MAX_EXCLUDE = 10

# ============================================================
#  判定规则：每条 = (人话名字, 正则)
#  顺序有意义：靠前的更具体，先命中先报
# ============================================================
RULES = [
    (u"网址 / 端点", re.compile(r"https?://")),
    (u"本机或内网地址", re.compile(
        r"127\.0\.0\.1|154\.94\.226\.240|localhost:\d|workers\.dev|socks5://")),
    (u"HTTP 状态码", re.compile(
        r"HTTP\s*\d{3}|\b(?:400|401|403|404|405|413|415|429|500|501|502|503)\b")),
    (u"接口路径 / 协议头", re.compile(
        r"/api/|X-API-Key|\bbase_url\b|\bbaseUrl\b|Content-Encoding|Retry-After|sha256")),
    (u"传输与限流参数", re.compile(
        r"gzip|MB/s|字节|吞吐|压缩率|min_interval|限流|并发")),
    (u"本地文件 / 实现细节", re.compile(
        r"saves/|worlds/|world_packs/|history_tree|index\.json|capabilities|已剔掉|stripped")),
    (u"旧版 / 认证 / 降级", re.compile(r"旧版|认证[:：]|server_old|降级|分片|中转")),
    (u"配置文件 / 脚本名", re.compile(r"\.json\b|\.py\b")),
]

CJK = re.compile(u"[\u4e00-\u9fff\u3040-\u30ff]")
# 单独一个文件名（不是句子）→ 代码常量，不是"说明"
BARE_FILE = re.compile(r"^[\w.\-]+\.(?:json|py)$")
VISIBLE_ATTRS = ("placeholder", "title", "alt", "aria-label")


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()                                  # noqa: F821 (io 在 py2 分支才有意义)


def judge(text):
    """返回 [(规则名, 命中片段)]；空列表 = 这段文案干净。"""
    hits = []
    for name, rx in RULES:
        m = rx.search(text)
        if not m:
            continue
        if name == u"配置文件 / 脚本名" and BARE_FILE.match(text.strip()):
            continue                                     # 单独的 "咲.json" 是文件名常量
        hits.append((name, m.group(0)))
    return hits


# ============================================================
#  取"用户看得到的文本"：三种文件三套取法
# ============================================================
class _TextGrabber(HTMLParser):
    """只收文本位 + 可见属性；<script>/<style> 正文整段跳过（那部分交给 JS 取法）。"""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.items = []          # (行号, 文本, 位置)
        self.scripts = []        # (起始行号, <script> 正文) —— 正文另按 JS 规则扫
        self._skip = 0
        self._buf = []
        self._start = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            self._buf = []
            self._start = self.getpos()[0]
            return
        for k, v in attrs:
            if k.lower() in VISIBLE_ATTRS and v:
                self.items.append((self.getpos()[0], v, "attr:" + k.lower()))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
            if tag == "script":
                # 带上起始行号：内联 <script> 里的命中要报回文件里的真实行号，
                # 否则报出来的行号是"第几个 <script> 里的第几行"，排查时会白跑一趟。
                self.scripts.append((self._start, "\n".join(self._buf)))
            self._buf = []
            return

    def handle_data(self, data):
        if self._skip:
            self._buf.append(data)
            return
        t = data.strip()
        if t:
            self.items.append((self.getpos()[0], t, "text"))


def strip_html_comments(text):
    """把注释换成等长空白（保留行号）。"""
    def blank(m):
        return "".join("\n" if c == "\n" else " " for c in m.group(0))
    return re.sub(r"<!--.*?-->", blank, text, flags=re.S)


def html_texts(path):
    if HTMLParser is None:                               # pragma: no cover
        return [], []
    raw = strip_html_comments(read(path))
    g = _TextGrabber()
    g.feed(raw)
    g.close()
    return g.items, g.scripts


def code_literals(text, is_kt, base=0):
    """逐行取字符串字面量；跳过注释与日志行；只留含中日文的（= 界面文案）。"""
    out = []
    lines = text.split("\n")
    in_block = False
    for ln, line in enumerate(lines, 1):
        s = line.strip()
        if in_block:
            if "*/" in s:
                in_block = False
            continue
        if s.startswith("/*"):
            if "*/" not in s:
                in_block = True
            continue
        if s.startswith("//") or s.startswith("*"):
            continue
        if "console." in line or "println" in line or "Log." in line:
            continue                                     # 开发者日志，允许带状态码
        if is_kt:
            lits = re.findall(r'"""((?:[^"]|"(?!""))*)"""', line)
            lits += re.findall(r'"((?:[^"\\\n]|\\.)*)"', line)
        else:
            lits = []
            for m in re.finditer(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"", line):
                lits.append(m.group(1) if m.group(1) is not None else m.group(2))
        for lit in lits:
            if lit.strip() and CJK.search(lit):
                out.append((ln + base, lit, "str"))
    return out


def targets():
    """(相对路径, 取法) —— 两端 UI 源码。"""
    out = []
    for d, pat in ((os.path.join(WEB, "screens"), ".html"),
                   (os.path.join(WEB, "js", "screens"), ".js")):
        for f in sorted(os.listdir(d)):
            if f.endswith(pat):
                out.append((os.path.relpath(os.path.join(d, f), ROOT).replace("\\", "/"),
                            "html" if pat == ".html" else "js"))
    out.append(("web/index.html", "html"))               # 外壳（角色卡/世界书这些表单住在这儿）
    for dp, dns, fns in os.walk(os.path.join(APP, "ui")):
        dns[:] = sorted(dns)
        for f in sorted(fns):
            if f.endswith(".kt"):
                p = os.path.join(dp, f)
                out.append((os.path.relpath(p, ROOT).replace("\\", "/"), "kt"))
    return [t for t in out if t[0] not in EXCLUDE]


def collect(rel, kind):
    p = os.path.join(ROOT, rel.replace("/", os.sep))
    if kind == "html":
        items, scripts = html_texts(p)
        # 内联 <script> 里的 JS 文案也要扫（index.html 的设置行文案就在里面）
        for start, s in scripts:
            items += code_literals(s, False, base=max(0, start - 1))
        return items
    return code_literals(read(p), kind == "kt")


# ============================================================
#  main
# ============================================================
def main():
    print("=" * 66)
    print(u"界面文案「技术说明」清零（网页 + 安卓；API 教程页与调试面板除外）")
    print("=" * 66)

    files = targets()
    print(u"\n== ① 扫描范围先兜住（防止扫描被改空，全绿变成假绿） ==")
    check(u"扫到 ≥20 个 UI 文件（现在 %d 个）" % len(files), len(files) >= 20,
          u"%s" % [f for f, _ in files][:6])
    rels = [f for f, _ in files]
    check(u"覆盖网页屏片段 web/screens/*.html",
          any(r.startswith("web/screens/") for r in rels))
    check(u"覆盖网页屏脚本 web/js/screens/*.js",
          any(r.startswith("web/js/screens/") for r in rels))
    check(u"覆盖网页外壳 web/index.html", "web/index.html" in rels)
    check(u"覆盖安卓 ui/**/*.kt", any(r.endswith(".kt") for r in rels))
    check(u"API 教程页真的被排除了",
          all(k in EXCLUDE for k in (
              "web/screens/api_guide.html", "web/js/screens/api_guide.js",
              "DICK-Android/app/src/main/java/com/dick/app/ui/screens/api/ApiGuideScreen.kt")))
    check(u"排除了之后，教程页确实不在扫描表里",
          not any("api_guide" in r or r.endswith("api/ApiGuideScreen.kt") for r in rels))

    units, offenders = 0, []
    for rel, kind in files:
        for ln, txt, pos in collect(rel, kind):
            units += 1
            for name, word in judge(txt):
                offenders.append((rel, ln, name, word, txt))
    print(u"\n== ② 覆盖到的文本条数（%d 条）==" % units)
    check(u"取到 ≥600 条用户可见文本（现在 %d 条）" % units, units >= 600)

    print(u"\n== ③ 逐条规则：命中数必须是 0 ==")
    for name, _rx in RULES:
        hit = [o for o in offenders if o[2] == name]
        check(u"%s 命中 0 处（实际 %d 处）" % (name, len(hit)), not hit,
              u"；".join(u"%s:%d %s「%s」" % (r, l, w, t[:34]) for r, l, _n, w, t in hit[:4]))
    check(u"合计 0 处技术说明", not offenders,
          u"；".join(u"%s:%d「%s」" % (o[0], o[1], o[4][:34]) for o in offenders[:6]))

    print(u"\n== ④ 判定器自检（该红的必须红，该放的必须放） ==")
    samples = [
        (u"https://api.deepseek.com", True, u"裸网址"),
        (u"自动连接：http://154.94.226.240:8080", True, u"正文明细里的地址"),
        (u"已连接（认证:key · ↓12 赞3）", True, u"认证模式"),
        (u"服务器没有这个接口（HTTP 404）——线上可能还是旧版", True, u"状态码 + 旧版"),
        (u"现在有点挤，稍后再试（服务器一直回 429）", True, u"429"),
        (u"gzip 243→183 字节（75%），耗时 0.03s", True, u"压缩统计"),
        (u"本地文件不存在：x.json（saves 下共 3 个）", True, u"路径 + 文件名"),
        (u"写 life_config.json / space_config.json", True, u"配置文件"),
        (u"直连失败自动走中转", True, u"中转"),
        (u"min_interval_ms 决定上传间隔", True, u"限流参数"),
        (u"已连接（下载 12 · 点赞 3）", False, u"人话状态行"),
        (u"找不到这个文件，试试重新选一次", False, u"人话报错"),
        (u"现在有点挤，稍等一会儿再试", False, u"人话限流"),
        (u"别的设备输入 192.168.1.5:5080 加入", False, u"局域网地址（要照抄，保留）"),
        (u"温度", False, u"字段名本身"),
        (u"每行：名称|正则|替换|作用域", False, u"高级折叠区里的格式说明"),
        (u"咲.json", False, u"单独一个文件名 = 代码常量"),
    ]
    for txt, should_hit, why in samples:
        got = bool(judge(txt))
        check(u"自检：%s → %s" % (why, u"判红" if should_hit else u"放行"), got == should_hit,
              u"「%s」" % txt)

    print(u"\n== ⑤ 白名单（每条都要有理由，且不许变长） ==")
    check(u"白名单不超过 %d 条（现在 %d 条）" % (MAX_EXCLUDE, len(EXCLUDE)),
          len(EXCLUDE) <= MAX_EXCLUDE, u"、".join(sorted(EXCLUDE)))
    check(u"白名单每条都写了理由", all(str(v).strip() for v in EXCLUDE.values()))
    missing = [k for k in EXCLUDE if not os.path.isfile(os.path.join(ROOT, k))]
    check(u"白名单里的每个文件都真的存在", not missing, u"、".join(missing))

    print("\n" + "=" * 66)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("NO_DEV_COPY_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
