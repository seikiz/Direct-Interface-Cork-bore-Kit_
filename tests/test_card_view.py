# -*- coding: utf-8 -*-
"""卡片外显守护测试：工坊预览必须是**结构化卡片**，不是把 JSON 当代码显示。

为什么需要
----------
用户的原话（2026-12，安卓截图）：
  ①「角色卡 UI 应该是白的」
  ②「角色卡外显应该是结构化，而不是像现在一样像个代码，穿帮了」

这两句话背后是三个很容易"改回去"的东西：
  · 字段表（哪一栏叫什么、哪些键算同一栏）—— 两端各写一份必然漂；
  · 渲染器（把 JSON 摆成卡片）—— 一句 `Text(wsPreview)` / `textContent = r.preview`
    就退回"代码块"，而且界面不报错，只有人肉看图才发现；
  · 标签文案（三语）—— 只要有人图省事写死中文，切到 EN/JA 就露馅。

所以这条测试守四层：
  ① `design/card_fields.json` 结构合法，且**确实覆盖**用户点名的那些键；
  ② 两端产物（`web/card_fields.js` / `CardFields.kt`）与 json 一致（跑生成器 --check），
     折叠阈值/分区数逐项对得上；
  ③ 两端渲染器里**禁止**把 JSON 直接字符串化显示（模式扫描，白名单单独列清楚）；
  ④ 真的跑一遍网页渲染器（node tests/card_view_harness.js），断言渲染结果里
     有分区标题、没有大括号、超行会折叠、坏 JSON 退成正文、切语言标签跟着变。

跑法：python tests/test_card_view.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")

FIELDS = os.path.join(ROOT, "design", "card_fields.json")
STRINGS = os.path.join(ROOT, "lang", "strings.json")
WEB_JS = os.path.join(ROOT, "web", "card_fields.js")
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "CardFields.kt")
WS_HTML = os.path.join(ROOT, "web", "screens", "ws.html")
WS_JS = os.path.join(ROOT, "web", "js", "screens", "ws.js")
WS_CSS = os.path.join(ROOT, "web", "styles", "screens", "ws.css")
AND_WS = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "ui", "screens", "workshop")
CARDS_KT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                        "app", "ui", "components", "Cards.kt")
HARNESS = os.path.join(HERE, "card_view_harness.js")

# 禁止模式：(文件名, <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌正则, 为什么禁止)
#   —— 命中即 FAIL。整数看的是「渲染器里有没有把整份 JSON 直接摊在界面上」这件事。
FORBIDDEN = [
    ("web/js/screens/ws.js", r"JSON\s*\.\s*stringify\s*\(",
     "预览里不许把对象序列化回 JSON 文本（那正是「像个代码」的来源）"),
    ("web/js/screens/ws.js", r"wsPreview['\"]?\s*\)\s*\.\s*textContent",
     "预览框不许直塞原文（应该走结构化渲染器）"),
    ("web/js/screens/ws.js", r"<pre",
     "预览里不许出现等宽代码块"),
    ("web/screens/ws.html", r"<pre[^>]*id=[\"']wsPreview",
     "#wsPreview 不许再是 <pre>"),
    ("web/styles/screens/ws.css", r"font-family\s*:\s*[^;}]*(monospace|ui-monospace|Consolas)",
     "预览样式里不许出现等宽字体"),
    ("DICK-Android/app/src/main/java/com/dick/app/ui/screens/workshop/WorkshopScreen.kt",
     r"Text\s*\(\s*wsPreview", "预览不许直接把原文丢给 Text"),
    ("DICK-Android/app/src/main/java/com/dick/app/ui/screens/workshop/WorkshopScreen.kt",
     r"wsPreview\s*\.\s*toString", "预览不许把原文 toString 后显示"),
    ("DICK-Android/app/src/main/java/com/dick/app/ui/screens/workshop/CardPreview.kt",
     r"JsonS\s*\.\s*stringify\s*\(", "卡片渲染器里不许把对象序列化回 JSON 文本"),
    ("DICK-Android/app/src/main/java/com/dick/app/ui/screens/workshop/CardPreview.kt",
     r"Text\s*\([^)\n]*\bjson\b", "卡片渲染器里不许出现 Text(…json…) 这种直出"),
]

# 白名单：命中上面某条但**确实该那么写**的地方，必须在这里点名 + 写理由（总数有上限）。
# 现在一条都没有 —— 结构化的做法本来就不需要这些模式。
WHITELIST = {}
WHITELIST_MAX = 2

# 用户点名的字段覆盖（键 → 必须落在哪个分区里；None = 不限分区，只要在 sections 里）
REQUIRED_KEYS = {
    "system_prompt": "setting",
    "prompt": "setting",
    "description": "setting",
    "personality": "persona",
    "外貌": "persona",
    "性格": "persona",
    "greeting": "greeting",
    "first_mes": "greeting",
    "opening": "greeting",
    "rules": "rules",
    "params.era": "era",
    "params.space": "era",
}
REQUIRED_TITLE = ["name"]

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


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def _blank(m):
    """把注释内容换成等量空格（保留换行，行号不乱）——注释里写着「不许 <pre>」不算违规。"""
    return re.sub(r"[^\n]", " ", m.group(0))


def strip_comments(text, ext):
    """去掉注释再扫禁止模式：注释里解释「原来这里是 <pre>」不是在写违规代码。"""
    if ext == ".html":
        return re.sub(r"<!--.*?-->", _blank, text, flags=re.S)
    t = re.sub(r"/\*.*?\*/", _blank, text, flags=re.S)
    if ext in (".js", ".kt"):
        out = []
        for line in t.split("\n"):
            # 行注释：引号/协议头之外的 // 才算（`http://` 与字符串里的 // 不算）
            m = re.search(r"(?<![:\"'`])//", line)
            out.append(line[:m.start()] if m else line)
        t = "\n".join(out)
    return t


def main():
    print("=" * 66)
    print(u"卡片外显守护（结构化卡片 / 白底卡片 / 两端同一份字段表）")
    print("=" * 66)

    # ------------------------------------------------------------------
    print(u"\n== ① design/card_fields.json 的结构 ==")
    check(u"design/card_fields.json 在", os.path.isfile(FIELDS), rel(FIELDS))
    data = json.loads(read(FIELDS))
    check(u"顶层是对象", isinstance(data, dict))
    for k in ("version", "collapse_lines", "kv_value_chars", "max_text_chars"):
        check(u"%s 是整数" % k, isinstance(data.get(k), int) and not isinstance(data.get(k), bool),
              repr(data.get(k)))
    check(u"折叠阈值就是 8 行（用户口径「超过 ~8 行折叠」）", data.get("collapse_lines") == 8,
          repr(data.get("collapse_lines")))
    sections = data.get("sections") or []
    check(u"sections 非空（%d 个分区）" % len(sections), len(sections) >= 4)
    ids = [s.get("id") for s in sections]
    check(u"分区 id 唯一", len(set(ids)) == len(ids), u"%s" % ids)
    bad_mode = [s.get("id") for s in sections if s.get("mode") not in ("body", "kv", "list")]
    check(u"展示方式只有 body / kv / list（没有 json 这一档）", not bad_mode, u"%s" % bad_mode)
    bad_keys = [s.get("id") for s in sections if not (s.get("keys") or [])]
    check(u"每个分区都有 keys", not bad_keys, u"%s" % bad_keys)
    other = data.get("other") or {}
    check(u"有兜底分区「其它信息」（两列）",
          other.get("mode") == "kv" and bool(other.get("label_key")), u"%s" % other)
    check(u"隐藏槽写清楚了（原样数据不进界面）",
          isinstance(data.get("hidden_keys"), list) and data["hidden_keys"],
          u"%s" % data.get("hidden_keys"))

    where = {}
    for sec in sections:
        for k in (sec.get("keys") or []):
            where.setdefault(k, sec.get("id"))
    missing = [k for k, want in REQUIRED_KEYS.items() if where.get(k) != want]
    check(u"用户点名的 %d 个字段都落在对的分区里" % len(REQUIRED_KEYS), not missing,
          u"没落到指定分区：%s" % missing)
    check(u"标题键包含 name", all(k in (data.get("title_keys") or []) for k in REQUIRED_TITLE),
          u"%s" % data.get("title_keys"))

    strings = (json.loads(read(STRINGS)) or {}).get("keys") or {}
    labels = [s.get("label_key") for s in sections] + [other.get("label_key")]
    labels += list((data.get("field_labels") or {}).values())
    labels = sorted(set(x for x in labels if x))
    absent = [k for k in labels if k not in strings]
    check(u"%d 个标签键都在 lang/strings.json 里" % len(labels), not absent, u"%s" % absent[:8])
    untranslated = [u"%s@%s" % (k, lg) for k in labels for lg in ("zh", "en", "ja")
                    if not str((strings.get(k) or {}).get(lg) or "").strip()]
    check(u"标签键三语齐全（缺 %d 处）" % len(untranslated), not untranslated,
          u"%s" % untranslated[:6])
    sides = [k for k in labels
             if set(("desktop_web", "android")) - set((strings.get(k) or {}).get("used_by") or [])]
    check(u"标签键的 used_by 同时覆盖网页与安卓", not sides, u"%s" % sides[:6])

    ui_keys = ["card_expand", "card_collapse", "card_yes", "card_no",
               "card_count_list", "card_count_obj"]
    miss_ui = [k for k in ui_keys if k not in strings]
    check(u"展开/收起/是/否/计数这几条界面文案都有键", not miss_ui, u"%s" % miss_ui)

    # ------------------------------------------------------------------
    print(u"\n== ② 两端产物与 json 一致（唯一真相 → 两端，同一套 --check）==")
    gen = os.path.join(TOOLS, "gen_card_fields.py")
    check(u"tools/gen_card_fields.py 在", os.path.isfile(gen), rel(gen))
    proc = subprocess.run([sys.executable, "-X", "utf8", gen, "--check"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (proc.stdout or u"").strip().replace(u"\n", u" | ")[-300:]
    check(u"gen_card_fields.py --check 退出 0（产物与 json 一致）", proc.returncode == 0, tail)
    check(u"web/card_fields.js 在", os.path.isfile(WEB_JS), rel(WEB_JS))
    check(u"CardFields.kt 在", os.path.isfile(KT_OUT), rel(KT_OUT))
    js = read(WEB_JS) if os.path.isfile(WEB_JS) else u""
    kt = read(KT_OUT) if os.path.isfile(KT_OUT) else u""
    check(u"网页产物暴露 window.DICK_CARD_FIELDS", "window.DICK_CARD_FIELDS" in js)
    check(u"网页产物有标签函数（字面引用 T.<键>，i18n 扫描才看得见）",
          "window.DICK_CARD_LABEL" in js and "T.card_sec_" in js)
    check(u"安卓产物带「生成物 · 别手改」抬头", u"生成物" in kt and u"别手改" in kt)
    # 只数 SECTIONS 里的条目（val OTHER 也是一个 CardSection，别把它算进分区数）
    sec_block = kt.split("val SECTIONS", 1)[-1].split("val OTHER", 1)[0]
    check(u"安卓产物分区数 == json（%d）" % len(sections),
          sec_block.count('CardSection("') == len(sections),
          str(sec_block.count('CardSection("')))
    check(u"两端折叠阈值 == json（%d）" % data["collapse_lines"],
          (u"collapseLines: %d" % data["collapse_lines"]) in js and
          (u"const val COLLAPSE_LINES = %d" % data["collapse_lines"]) in kt)
    probe = sections[0]["keys"][0]
    check(u"抽样一致：首分区的第一个键 %s 两端口径相同" % probe,
          (u'"%s"' % probe) in js and (u'"%s"' % probe) in kt, probe)

    # ------------------------------------------------------------------
    print(u"\n== ③ 渲染器里禁止把 JSON 直接字符串化显示 ==")
    check(u"白名单没有变成垃圾桶（%d 条 ≤ %d）" % (len(WHITELIST), WHITELIST_MAX),
          len(WHITELIST) <= WHITELIST_MAX)
    hits = 0
    for path, pattern, why in FORBIDDEN:
        full = os.path.join(ROOT, *path.split("/"))
        if not os.path.isfile(full):
            check(u"%s 在（要扫描的文件）" % path, False, rel(full))
            continue
        # 扫的是**代码**：注释里解释「原来这里是 <pre>」不算违规（行号仍然对得上）
        text = strip_comments(read(full), os.path.splitext(full)[1].lower())
        found = []
        for m in re.finditer(pattern, text):
            line = text.count(u"\n", 0, m.start()) + 1
            if (path, pattern) in WHITELIST:
                continue
            found.append(u"%s:%d %s" % (path, line, m.group(0)[:40]))
        hits += len(found)
        check(u"%s 不含 %s" % (path, why), not found, u"；".join(found[:3]))
    check(u"禁止模式命中 0 处", hits == 0, str(hits))
    # 反向：渲染器必须真的在（别把功能删掉换成空白）
    wjs = read(WS_JS)
    check(u"ws.js 有结构化渲染器（ws-cardview / cv-sec）",
          "ws-cardview" in wjs and "cv-sec" in wjs)
    check(u"ws.js 的字段表来自生成物（DICK_CARD_FIELDS），不是自己写死一份",
          "window.DICK_CARD_FIELDS" in wjs and "DICK_CARD_FIELD_LABEL" in wjs)
    check(u"ws.html 的预览容器还是 #wsPreview（JS 还在找它）但换了标签",
          'id="wsPreview"' in read(WS_HTML) and "<pre" not in read(WS_HTML))
    and_ws = read(os.path.join(AND_WS, "WorkshopScreen.kt"))
    check(u"安卓预览改成调结构化组件 WsCardPreview",
          "WsCardPreview(" in and_ws and "Text(wsPreview" not in and_ws)
    check(u"安卓渲染器在用生成的 CardFields（分区/标签都不硬编码）",
          "CardFields.SECTIONS" in read(os.path.join(AND_WS, "CardPreview.kt")))
    check(u"安卓标题走 CardFields.TITLE_KEYS",
          "CardFields.TITLE_KEYS" in read(os.path.join(AND_WS, "CardPreview.kt")))

    # ------------------------------------------------------------------
    print(u"\n== ④ 白底卡片：两端都用令牌，不再是「一块灰」==")
    css = read(WS_CSS)
    card_rule = re.search(r"\.ws-card\{([^}]*)\}", css)
    body = card_rule.group(1) if card_rule else u""
    check(u".ws-card 用 --surface 打底（浅色主题下才是白的）", "background:var(--surface)" in body,
          body[:80])
    check(u".ws-card 不再用 --bubble（surface_2）打底", "background:var(--bubble)" not in body)
    check(u".ws-card 有 --line 描边", "border:1px solid var(--line)" in body)
    check(u".ws-card 用 radius 令牌", "border-radius:var(--radius-md)" in body)
    check(u"本地列表的词条底色也换成 surface（原生 select 的 option）",
          ".ws-col option{" in css and "background:var(--surface)" in
          re.search(r"\.ws-col option\{([^}]*)\}", css).group(1))
    cards_kt = read(CARDS_KT)
    check(u"DickCard 新增 outline 参数（描边），默认 null = 老调用点不变样",
          "outline: Color? = null" in cards_kt and "BorderStroke" in cards_kt)
    check(u"工坊列表项传了描边（选中 accent / 未选 line）",
          "outline = if (sel) theme.palette.accent else theme.line" in and_ws)
    check(u"选中态靠描边而不是整块灰底（outlineWidth 选中 2dp）",
          "outlineWidth = if (sel) 2.dp else 1.dp" in and_ws)
    preview_rule = re.search(r"\.ws-preview\{([^}]*)\}", css)
    check(u"预览区自己是白底卡片（surface + line + radius）",
          bool(preview_rule) and "background:var(--surface)" in preview_rule.group(1) and
          "border:1px solid var(--line)" in preview_rule.group(1))

    # ------------------------------------------------------------------
    print(u"\n== ⑤ 真跑一遍网页渲染器（node tests/card_view_harness.js）==")
    node = shutil.which("node")
    check(u"node 在（仓库其他前端测试也用它）", bool(node), u"PATH 里找不到 node")
    if not node:
        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1
    proc = subprocess.run([node, HARNESS], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    check(u"harness 退出 0", proc.returncode == 0,
          (proc.stderr or u"")[-400:] or (proc.stdout or u"")[-300:])
    if proc.returncode != 0:
        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1
    got = json.loads(proc.stdout)
    zh = got.get("zh") or {}
    ja = got.get("ja") or {}

    role = zh.get("role", u"")
    check(u"角色卡：标题取 name", u">测试角色卡<" in role, role[:120])
    check(u"角色卡：有「角色设定」分区", u">角色设定<" in role, role[:160])
    check(u"角色卡：personality + appearance 归并进「性格 / 外貌」",
          u">性格 / 外貌<" in role and u">性格<" in role and u">外貌<" in role, role[:220])
    check(u"角色卡：有「开场白」分区", u">开场白<" in role, role[:220])
    check(u"角色卡：未知键 legacy 进「其它信息」（键名当标签）",
          u">其它信息<" in role and u">legacy<" in role, role[-260:])
    check(u"角色卡：隐藏槽 card_data / history_tree 不出现",
          "card_data" not in role and "history_tree" not in role, role[-260:])
    check(u"角色卡：字面 \\n 已还原成段落（不再是一行转义）",
          u"第一段：他是谁。" in role and u"\\\\n" not in role, role[:200])
    check(u"角色卡：渲染结果里没有大括号/引号（结构化，不是 JSON）",
          "{" not in role and "}" not in role and "&quot;" not in role, role[:200])
    check(u"角色卡：对象值只报计数（unknown_list → 列表 · 3 项）",
          u"列表 · 3 项" in role, role[-200:])

    world = zh.get("world", u"")
    check(u"世界卡：年代/空间取自 params.era / params.space",
          u">年代<" in world and u">明末<" in world and u">空间<" in world and u">江南水乡<" in world,
          world[:400])
    check(u"世界卡：rules[] 变成列表（3 条 li）", world.count("<li>") == 3, world[-300:])
    check(u"世界卡：entries 只报计数（列表 · 2 项）", u"列表 · 2 项" in world, world[-260:])
    check(u"世界卡：没有大括号", "{" not in world and "}" not in world, world[:200])

    long_html = zh.get("long", u"")
    lines = len(re.findall(r"<p>", long_html))
    check(u"长正文折叠到 8 行（实际 %d 段）" % lines, lines == data["collapse_lines"], str(lines))
    check(u"折叠时有「展开」按钮且带了分区 id",
          u'class="btn2 ghost cv-more" data-cv="setting"' in long_html and u">展开<" in long_html,
          long_html[-200:])

    broken = zh.get("broken", u"")
    check(u"坏 JSON：标题退回文件名", u">坏文件<" in broken, broken[:120])
    check(u"坏 JSON：原文照旧显示（正文样式，不是代码块）",
          u"这不是 JSON，只是一段原文。" in broken, broken[:200])
    check(u"坏 JSON：没有两列键值（没有把它当卡解析）", "cv-kv" not in broken, broken[:200])

    check(u"切到日语：分区标签跟着变（不是硬编码中文）",
          u">キャラクター設定<" in ja.get("role", u""), ja.get("role", u"")[:200])
    check(u"切到日语：折叠按钮变「展開」", u">展開<" in ja.get("long", u""), ja.get("long", u"")[-120:])
    check(u"切到日语：布尔值走三语（是 / はい）", u">はい<" in ja.get("role", u""),
          ja.get("role", u"")[-200:])

    # ------------------------------------------------------------------
    print(u"\n== ⑥ 文案产物仍然一致（加了标签键之后 gen_i18n 还得过）==")
    proc = subprocess.run([sys.executable, "-X", "utf8", os.path.join(TOOLS, "gen_i18n.py"),
                           "--check"], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    check(u"gen_i18n.py --check 退出 0", proc.returncode == 0,
          (proc.stdout or u"").strip().replace(u"\n", u" | ")[-300:])

    print("\n" + "=" * 66)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CARD_VIEW_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
