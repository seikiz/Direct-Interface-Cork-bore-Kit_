# -*- coding: utf-8 -*-
"""界面文案大一统：`lang/strings.json` 是唯一真相，三端从它派生。

守的是这件事：文案原来**三份各写一遍** ——
  · `web/index.html` 的 JS 表（界面主力）
  · `i18n.py` 的 `_EN` / `_JA`（遗留键居多）
  · 安卓 `I18n.kt` 的 `EN` / `JA`
于是漂迟早出现，而且都真的出现过：英文欢迎语里写死 `v2.0`（英文模式显示旧版号）、
按键名各写一套导致"改了中文忘了英文"。

现在：`lang/strings.json` → `web/i18n.js`（生成）、`i18n.py`（运行时读）、
`I18nStrings.kt`（生成）。"谁在用哪个键"的判定**只有一份实现**（`tools/gen_i18n.py`），
本测试直接调它 —— 生成器、--check、测试三处各写一套正是要消灭的东西。

跑法：python tests\\test_i18n_langs.py
"""
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import gen_i18n as G   # noqa: E402  （唯一那份"谁在用哪个键"的实现）

PASS = 0
FAIL = 0
NOTE = []
# 用一个**故意不是版号格式**的串当"调用方给的版号"：
# tools/bump_version.py --check 会扫全仓代码里写死的 `X v数字.数字`，测试里写死一个真版号
# 会被判成"版号漂"（踩过）—— 这里只要证明"措辞来自 json、号来自调用方"就够了。
VER = u"DICK vTEST"


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


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    print("=" * 60)
    print(u"界面文案大一统（lang/strings.json 唯一真相）")
    print("=" * 60)

    doc = G.load()
    check(u"lang/strings.json 在且能解析", isinstance(doc, dict))
    if not isinstance(doc, dict):
        return 1
    keys = doc.get("keys") or {}
    legacy = doc.get("_legacy") or {}

    # ---------------- ① <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌结构 ----------------
    print(u"\n-- ① lang/strings.json 结构 --")
    check(u"keys 非空（%d 个）" % len(keys), len(keys) > 0)
    check(u"_legacy 记录在案（%d 个，不参与硬校验）" % len(legacy), isinstance(legacy, dict))
    problems = G.validate(doc)
    check(u"结构校验通过（三语非空 / used_by 合法 / 无漏译）", not problems,
          u"；".join(problems[:4]))
    empty = [k for k, v in keys.items()
             if not all(str(v.get(lg) or "").strip() for lg in G.LANGS)]
    check(u"每个键三种语言都有非空值", not empty, u"%s" % empty[:5])
    badside = [k for k, v in keys.items()
               if not v.get("used_by") or
               any(s not in G.SIDES for s in (v.get("used_by") or []))]
    check(u"每个键的 used_by 都非空且合法", not badside, u"%s" % badside[:5])
    check(u"keys 与 _legacy 不重叠", not [k for k in keys if k in legacy])
    check(u"legacy 条目都写明来自哪份表（from）",
          all(str(v.get("from") or "").strip() for v in legacy.values()))
    counts = {s: sum(1 for v in keys.values() if s in (v.get("used_by") or []))
              for s in G.SIDES}
    shared = [k for k, v in keys.items() if len(v.get("used_by") or []) > 1]
    print(u"   桌面 web %d ／ 桌面 python %d ／ 安卓 %d ／ 多端共享 %d"
          % (counts["desktop_web"], counts["desktop_py"], counts["android"], len(shared)))

    # ---------------- ② i18n.py 运行时读取 ----------------
    print(u"\n-- ② i18n.py 从 json 读，三语逐字对得上 --")
    i18n = load_module(os.path.join(ROOT, "i18n.py"), "i18n_under_test")
    check(u"三张表都读到了", i18n.table_ok(), i18n._LOADED_FROM)
    check(u"LANGS 是三种", tuple(i18n.LANGS) == ("zh", "en", "ja"), str(i18n.LANGS))
    check(u"三种语言都有自称", set(i18n.LANG_NAMES) == set(i18n.LANGS))
    probe = ["welcome2", "status_roles_prefix", "tokens_label", "accent", "send",
             "btn_add_entry", "unknown_cmd"]
    for k in probe:
        if k not in keys:
            check(u"抽样键 %s 在 json 里" % k, False, u"不在 keys 里")
            continue
        for lg in G.LANGS:
            i18n.set_lang(lg)
            got = i18n.t(k, u"<兜底>")
            check(u"t(%s) @%s 逐字等于 json" % (k, lg), got == keys[k][lg],
                  u"得到 %r，期望 %r" % (got, keys[k][lg]))
    i18n.set_lang("ja")
    i18n.set_lang("kr")
    check(u"未知语言值退回中文", i18n.lang() == "zh", i18n.lang())
    i18n.set_lang("ja")
    check(u"表里没有的键 → 回退调用点中文（不显示 key 名）",
          i18n.t("no_such_key_zzz", u"中文兜底") == u"中文兜底",
          i18n.t("no_such_key_zzz", u"中文兜底"))
    check(u"welcome() 用 json 的措辞 + 调用方给的版号",
          i18n.welcome(VER) == (keys["welcome"]["ja"] % VER),
          i18n.welcome(VER))
    check(u"tokens_label() 用 json 的措辞", i18n.tokens_label(5) == (keys["tokens_label"]["ja"] % 5),
          i18n.tokens_label(5))
    i18n.set_lang("zh")

    # ---------------- ③ 调用点默认值 == json zh ----------------
    print(u"\n-- ③ 桌面调用点的中文默认值 == json 里的 zh --")
    scan = G.scan_sources(set(keys))
    py_defaults = scan["defaults"]["py"]
    kt_defaults = scan["defaults"]["kt"]
    compared = mismatch = skipped = 0
    for k, vals in sorted(py_defaults.items()):
        if k not in keys:
            NOTE.append(u"调用点用了 json 里没有的键：%s" % k)
            continue
        for v in vals:
            if v is None:
                skipped += 1
                continue
            compared += 1
            if v != keys[k]["zh"]:
                mismatch += 1
                check(u"调用点 %s 的默认值与 json zh 一致" % k, False,
                      u"调用点 %r vs json %r" % (v, keys[k]["zh"]))
    check(u"桌面调用点默认值全部与 json zh 一致（比对 %d 条）" % compared, mismatch == 0)
    print(u"   比对 %d 条／跳过 %d 条（默认值不是字面量：变量、条件、运行期拼接）"
          % (compared, skipped))
    if skipped:
        print(u"   跳过的键：%s"
              % sorted(k for k, vals in py_defaults.items() if any(v is None for v in vals)))
    kt_diff = [(k, v, keys[k]["zh"]) for k, vals in kt_defaults.items() if k in keys
               for v in vals if v is not None and v != keys[k]["zh"]]
    if kt_diff:
        NOTE.append(u"安卓调用点 zh 与 json 不同 %d 处（安卓 zh 优先用调用点原串，老行为不变）：%s"
                    % (len(kt_diff), [x[0] for x in kt_diff[:6]]))
    check(u"安卓调用点给的中文都非空",
          all(v for vals in kt_defaults.values() for v in vals if v is not None))

    # ---------------- ④ 生成物 ----------------
    print(u"\n-- ④ 生成物（web/i18n.js、I18nStrings.kt） --")
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_i18n.py"),
                           "--check"], cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    check(u"gen_i18n.py --check 退出 0（产物与 json 一致）", proc.returncode == 0,
          out.strip().replace(u"\n", u" | ")[:300])
    js = read(G.JS_OUT)
    check(u"web/i18n.js 是生成物（带「别手改」抬头）", u"生成物" in js and u"别手改" in js)
    check(u"web/i18n.js 暴露 window.DICK_I18N", "window.DICK_I18N" in js)
    kt = read(G.KT_OUT)
    check(u"I18nStrings.kt 是生成物（带「别手改」抬头）", u"生成物" in kt and u"别手改" in kt)
    for k in ("btn_send", "send", "lbl_model", "welcome"):
        if k not in keys:
            continue
        for lg in G.LANGS:
            needle = json.dumps(keys[k][lg], ensure_ascii=False)
            check(u"生成的 Kotlin 里 %s@%s 与 json 逐字一致" % (k, lg), needle in kt, needle)
    missing_in_js = [k for k in keys if ('"%s"' % k) not in js]
    check(u"生成物覆盖全部 keys（缺 %d 个）" % len(missing_in_js), not missing_in_js,
          u"%s" % missing_in_js[:5])

    # ---------------- ⑤ used_by 说真话 ----------------
    print(u"\n-- ⑤ used_by 声明的端，源码里真的在用 --")
    miss, extra = G.usage_mismatch(doc, scan)
    # 运行期拼出来的键扫不到是正常的：主题/强调色/预设的显示名是 "accent_" + 名字 拼的，
    # 语言标题是 data-i18n 之外的动态注入。按前缀认下来，别误判成死键。
    DYNAMIC_PREFIXES = ("accent_", "preset_", "lang_", "theme_")
    miss = {k for k in miss if not k.startswith(DYNAMIC_PREFIXES)}
    check(u"没有「声明了却扫不到」的键（死键嫌疑）", not miss, u"%s" % sorted(miss)[:8])
    check(u"没有「扫到了却没声明」的键", not extra, u"%s" % sorted(extra)[:8])
    # 拼接用的前缀（"accent_" + x）会被扫成一个以 _ 结尾的"键"，它不是键
    stray = sorted(k for k in (scan["used"]["android"] - set(keys)) if not k.endswith("_"))
    check(u"安卓用到的键都在 json 里", not stray, u"%s" % stray[:8])
    check(u"I18n.kt 不再内联 EN/JA/ZH 表（改用生成的 I18nStrings）",
          not re.search(r"private val (EN|JA|ZH)\s*=\s*mapOf\(",
                        read(os.path.join(ROOT, "DICK-Android", "app", "src", "main",
                                          "java", "com", "dick", "app", "I18n.kt"))))
    check(u"i18n.py 不再内联 _EN/_JA 表",
          not re.search(r"^_(?:EN|JA|ZH) = \{", read(os.path.join(ROOT, "i18n.py")), re.M))
    html = read(os.path.join(ROOT, "web", "index.html"))
    check(u"index.html 不再内联三段 T = {...}", "window.DICK_I18N" in html)
    check(u"index.html 引了生成的 i18n.js", 'src="i18n.js"' in html)
    # 阶段4 起设置屏的 DOM 搬到了 web/screens/settings.html，语言选择器跟着走了 ——
    # 所以"界面里有没有这三种语言"要查整棵前端，不是只看 index.html。
    web_all = html
    for base, _dirs, files in os.walk(os.path.join(ROOT, "web", "screens")):
        for fn in sorted(files):
            if fn.endswith(".html"):
                web_all += "\n" + read(os.path.join(base, fn))

    # ---------------- ⑥ 三端入口都是三选一 ----------------
    print(u"\n-- ⑥ 语言入口：三端都是三种 --")
    for v in ("zh", "en", "ja"):
        check(u"网页前端的语言选项有 %s" % v, ('value="%s"' % v) in web_all)
    check(u"i18n.py 的 LANGS 三种", 'LANGS = ("zh", "en", "ja")' in read(
        os.path.join(ROOT, "i18n.py")))
    ktp = read(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java",
                            "com", "dick", "app", "I18n.kt"))
    check(u"I18n.kt 的 LANGS 三种", 'listOf("zh", "en", "ja")' in ktp)
    check(u"设置里那个选择器的标题写着三种语言名", u"中文 / English / 日本語" in web_all)
    # 安卓 UI 已按 feature 拆包（App.kt / Dialogs.kt 只剩壳与门面）：
    # 这两个结构断言改成扫整棵安卓源码，别再钉死某个文件（否则每次拆包都要改测试）。
    def _all_kt():
        root = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick")
        buf = []
        for base, _dirs, files in os.walk(root):
            for fn in files:
                if fn.endswith(".kt"):
                    buf.append(read(os.path.join(base, fn)))
        return "\n".join(buf)

    _kt_all = _all_kt()
    check(u"安卓设置里按 I18n.LANGS 渲染三选一（整棵源码）", "for (code in I18n.LANGS)" in _kt_all)
    check(u"安卓启动时归一化语言（整棵源码）", "I18n.normalize(" in _kt_all)
    check(u"发言者标签三语（你 / You / あなた）",
          keys.get("you", {}).get("zh") == u"你" and keys.get("you", {}).get("en") == "You"
          and keys.get("you", {}).get("ja") == u"あなた",
          json.dumps(keys.get("you"), ensure_ascii=False))

    # ---------------- ⑦ 版号不再写进 i18n ----------------
    print(u"\n-- ⑦ 文案文件里不许写死版号（踩过一次） --")
    i18np = read(os.path.join(ROOT, "i18n.py"))
    check(u"i18n.py 里没有 v2.0 这类产品代", "v2.0" not in i18np)
    check(u"i18n.py 里没有写死的四段版号", not re.search(r"v?\d+\.\d+\.\d+\.\d+", i18np))
    check(u"欢迎语走 welcome(ver)（措辞归 json、号由调用方给）", "def welcome(ver)" in i18np)
    desk = read(os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"))
    check(u"主程序用 i18n.welcome(app_version.full())",
          "i18n.welcome(app_version.full())" in desk)
    check(u"主程序不再用写死的 welcome1", "welcome1" not in desk)
    check(u"首启判定用 detect_system_lang()", "i18n.detect_system_lang()" in desk)
    check(u"老的 detect_english_system 保留为兼容包装",
          "def detect_english_system(" in i18np and "detect_system_lang()" in i18np)

    # ---------------- ⑧ 读不到 json 时优雅降级 ----------------
    print(u"\n-- ⑧ 读不到 lang/strings.json 时不许炸 --")
    tmp = tempfile.mkdtemp(prefix="dick_i18n_")
    try:
        shutil.copy(os.path.join(ROOT, "i18n.py"), os.path.join(tmp, "i18n.py"))
        bare = load_module(os.path.join(tmp, "i18n.py"), "i18n_bare")
        check(u"缺 json 时仍然 import 得动", bare is not None)
        check(u"缺 json 时 table_ok() 为假", not bare.table_ok())
        bare.set_lang("ja")
        check(u"缺 json 时 t() 回退调用点中文", bare.t("btn_send", u"发送") == u"发送",
              bare.t("btn_send", u"发送"))
        check(u"缺 json 时 welcome() 不炸", bare.welcome("X") == u"欢迎使用 X！",
              bare.welcome("X"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------- ⑨ config.json 里 language 三值真实往返 ----------------
    print(u"\n-- ⑨ config.json 的 language 三值都能存能读回 --")
    import app_paths
    import i18n as live_i18n      # 用**真正被 app import 的那份**（本文件上面是另加载的副本）
    real_base = app_paths.get_base_dir()
    tmp = tempfile.mkdtemp(prefix="dick_i18n_rt_")
    try:
        import html_app
        app_paths.get_base_dir = lambda: tmp
        app_paths.get_plugin_dirs = lambda: [os.path.join(real_base, "plugins")]
        html_app.BASE_DIR = tmp
        app = html_app.HtmlApp()
        for code in ("ja", "en", "zh", "ja"):
            r = app.api_set_language(code)
            check(u"%s：api_set_language 返回 ok" % code,
                  bool(r.get("ok")) and r.get("lang") == code, str(r))
            on_disk = {}
            try:
                with io.open(os.path.join(tmp, "config.json"), encoding="utf-8") as f:
                    on_disk = json.load(f)
            except Exception as e:
                check(u"%s：config.json 读得回来" % code, False, str(e))
            check(u"%s：已落盘到 config.json" % code, on_disk.get("language") == code,
                  str(on_disk.get("language")))
            check(u"%s：i18n 全局也跟着切了" % code, live_i18n.lang() == code,
                  live_i18n.lang())
        app2 = html_app.HtmlApp()
        check(u"重启后读回上次选的语言",
              app2.language == "ja" and live_i18n.lang() == "ja",
              u"%s / %s" % (app2.language, live_i18n.lang()))
        r = app2.api_set_language("fr")
        check(u"非法语言值 → 退回 zh 且落盘", r.get("lang") == "zh", str(r))
    finally:
        app_paths.get_base_dir = real_base
        live_i18n.set_lang("zh")
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------- ⑨ data-i18n 标注的键必须都在 json 里 ----------------
    # 阶段4 起文案改成"标注在元素上"（data-i18n="<key>"），setT() 不再逐个 id 点名。
    # 好处是换文案只动标注；代价是**打错一个键名不会报错**，只是那一处永远显示初始中文。
    # 所以这里把标注的键全抓出来跟 json 对一遍：拼错的键、删掉的键，当场红。
    print(u"\n-- ⑨ 元素上的 data-i18n 标注，键必须都在 lang/strings.json --")
    web_dir = os.path.join(ROOT, "web")
    pages = [os.path.join(web_dir, "index.html")]
    for base, _dirs, files in os.walk(os.path.join(web_dir, "screens")):
        for fn in sorted(files):
            if fn.endswith(".html"):
                pages.append(os.path.join(base, fn))
    RE_ATTR = re.compile(r"""\bdata-i18n(?:-placeholder)?\s*=\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")
    RE_PREFIX = re.compile(r"""\bdata-i18n-prefix\s*=\s*["']""")
    marks = {}          # key -> ["文件:行", …]
    for p in pages:
        for i, ln in enumerate(read(p).split("\n"), 1):
            for m in RE_ATTR.finditer(ln):
                marks.setdefault(m.group(1), []).append(
                    u"%s:%d" % (os.path.relpath(p, ROOT).replace("\\", "/"), i))
    check(u"页面上有 data-i18n 标注（阶段4 的入口）", bool(marks),
          u"一个都没找到：文案套用还停在逐 id 改名")
    stray_keys = sorted(k for k in marks if k not in keys)
    check(u"标注的 %d 个键都在 json 里（拼错/删掉的键 %d 个）" % (len(marks), len(stray_keys)),
          not stray_keys,
          u"、".join(u"%s（%s）" % (k, marks[k][0]) for k in stray_keys[:8]))
    # 标注了的键，三语必须都翻过（不然切到 en/ja 会留着中文）
    untranslated = []
    for k in sorted(marks):
        row = keys.get(k) or {}
        for lg in G.LANGS:
            if not row.get(lg):
                untranslated.append(u"%s@%s" % (k, lg))
    check(u"标注的键三语都有文案（缺 %d 处）" % len(untranslated), not untranslated,
          u"%s" % untranslated[:8])
    check(u"data-i18n-prefix 只跟 data-i18n 一起出现（图标前缀不进文案表）",
          not [p for p in pages
               if RE_PREFIX.search(read(p)) and not RE_ATTR.search(read(p))])
    # 反向：setT() 不该偷偷回到逐 id 改名（阶段4 之前它是 68 处）
    idx = read(os.path.join(web_dir, "index.html"))
    i_set = idx.find("function setT(l)")
    setT_body = idx[i_set:i_set + 4000] if i_set >= 0 else u""
    id_sets = len(re.findall(r"getElementById\('[^']+'\)\s*\.textContent", setT_body))
    check(u"setT() 里不再逐 id 改文案（现在 %d 处，阶段4 之前 68 处）" % id_sets,
          i_set >= 0 and id_sets <= 1, u"%d 处" % id_sets)

    # ---------------- ⑩ 文案表里一个 emoji 字符都没有 ----------------
    # 2026-12 用户要求：界面文案里**一个 emoji 字符都不许有**，图标走内置 Material Symbols。
    # 文案表是三端唯一真相，所以这里是总闸：表里带了 emoji，web/安卓/i18n.py 三端一起回潮。
    # 图标进界面靠两处（都不进文案表）：
    #   · 网页：`data-i18n-prefix="[ic:名字] "` + index.html 的 iconifyText；
    #   · 安卓：调用点 `IconText(文案, icon = "名字")`。
    print(u"\n-- ⑩ 文案表（三语 + _legacy）里 emoji 出现次数 = 0 --")
    EMOJI_RE = re.compile(u"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF"
                          u"\u2300-\u23FF\u2190-\u21FF\U0001F1E6-\U0001F1FF]")
    # 排版符号交给字体直接画（和 Ui.kt 的 TYPO_GLYPHS、web 的 _ICON_SKIP 同一口径）
    TYPO_RE = set(u"→←↑↓↔↻◀▶▸▾★☆·")

    def emojis(s):
        return [c for c in EMOJI_RE.findall(s or u"") if c not in TYPO_RE]

    bad = []
    for section in ("keys", "_legacy"):
        for k, row in (doc.get(section) or {}).items():
            if not isinstance(row, dict):
                continue
            for lg in G.LANGS:
                hit = emojis(row.get(lg))
                if hit:
                    bad.append(u"%s.%s@%s=%s" % (section, k, lg, u"".join(hit)))
    check(u"文案表里 emoji 出现次数 = 0（%d 处残留）" % len(bad), not bad,
          u"%s" % u"、".join(bad[:8]))
    # 判定器自检：拿已知样本喂进去，该红必须红（防止把判定改成"什么都能过"）
    for sample, want in ((u"🔑 Key", True), (u"📂 存档列表", True), (u"✅ 已连接", True),
                         (u"强调色：", False), (u"→ 下一步", False), (u"A · B", False)):
        got = bool(emojis(sample))
        check(u"判定器自检：%r → %s" % (sample, u"判红" if want else u"放行"), got == want)
    # 两个生成物也跟着查一遍（它们就是发到 web / 安卓的那些字符串）
    for label, path in ((u"web/i18n.js", G.JS_OUT), (u"I18nStrings.kt", G.KT_OUT)):
        hit = [c for c in EMOJI_RE.findall(read(path)) if c not in TYPO_RE]
        check(u"生成物 %s 里 emoji = 0（实际 %d）" % (label, len(hit)), not hit,
              u"%s" % u"".join(hit[:10]))

    print(u"\n" + "=" * 60)
    for n in NOTE:
        print(u"备注：%s" % n)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("I18N_LANGS_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
