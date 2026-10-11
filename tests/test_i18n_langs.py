# -*- coding: utf-8 -*-
"""三语界面（中文 / English / 日本語）：键集合、日文真的生效、入口真的是三选一。

守的是什么
----------
原来界面只有中/英两档，日文只存在于"日文补丁"（对话翻译 /jp /zh）与 TTS 里。这次把界面做成三语，
最容易出的错有三类：

  ① **键集合漂**：加了 `_JA` 却漏了几个键 —— 那些键在日文界面下会掉回中文（看着像"没翻译完"），
     或者干脆显示成 key 名（更糟）。所以三张表的键集合必须完全一致，差集直接打出来。
  ② **照抄**：日文表直接把中文/英文抄一遍（能用，但等于没做）。所以逐键比对：
     与中文原串或英文串相同的，必须在白名单里（纯符号/emoji、专有名词）。
  ③ **入口只是"提过日文"**：源码里出现过"日本語"不代表入口真是三选一。所以结构化断言：
     前端的 `<select id="stLangSel">` 三个 option 齐全、安卓按 `I18n.LANGS` 循环渲染、
     旧的二档循环（`if (language == "en") "zh" else "en"`）与 `toggle_language` 都不许再出现。

另外验一次真实往返：`api_set_language()` 落盘 → 重新构造应用读回（模拟重启）。

跑法：python tests\\test_i18n_langs.py
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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


def symbolish(v):
    """纯符号/emoji/数字（没有汉字也没有拉丁字母）—— 这种键三语相同是合理的"""
    return not re.search(r"[A-Za-z\u4e00-\u9fff\u3040-\u30ff]", v or "")


# 允许与中文相同的日文键：**日语里本来<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌就这么写**的同形汉字词（不是照抄）。
# 白名单要短、要能一条条解释；出现新的一条就得先想清楚它是不是真的同形词。
SAME_AS_ZH_OK = {
    "save": u"保存（日语也用「保存」）",
    "weContent": u"内容（同形词）",
    "weDepth": u"深度（同形词）",
    "nrPersonality": u"性格（同形词）",
    "apiKey": u"API Key（专有名词，保留原文）",
    "btn_save": u"保存（同形词）",
    "entry_content": u"内容（同形词）",
    "entry_depth": u"深度（同形词）",
    "entry_weight": u"重み",          # 不是同形词，留着提醒：这条其实不同，别误加
}
# 允许与英文相同的日文键：文件格式名 / 专有名词 / 纯符号
SAME_AS_EN_OK = {
    "btn_export_json": u"⬇️ JSON（格式名保留原文）",
    "btn_export_png": u"🖼️ PNG（格式名保留原文）",
}


def js_dict(text, marker, end_marker):
    """从 index.html 里抠一段 `T = { ... };`"""
    i = text.find(marker)
    if i < 0:
        return {}
    j = text.find(end_marker, i)
    seg = text[i:j if j > 0 else i + 20000]
    out = {}
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'((?:[^'\\]|\\.)*)'", seg):
        out[m.group(1)] = m.group(2)
    return out


def kt_map(text, name):
    """从 I18n.kt 里抠一张 `private val NAME = mapOf( ... )`，返回 {key: value}"""
    i = text.find("private val %s = mapOf(" % name)
    if i < 0:
        return {}
    j = text.find("\n    )", i)
    seg = text[i:j if j > 0 else i + 20000]
    out = {}
    for m in re.finditer(r'"([^"]+)"\s*to\s*"((?:[^"\\]|\\.)*)"', seg):
        out[m.group(1)] = m.group(2)
    return out


def main():
    print("=" * 58)
    print(u"三语界面（中文 / English / 日本語）")
    print("=" * 58)

    import i18n

    print(u"\n-- ① 桌面端 i18n.py：三张表键集合一致 --")
    en, ja = i18n._EN, i18n._JA
    check(u"支持三种语言", i18n.LANGS == ("zh", "en", "ja"), str(i18n.LANGS))
    check(u"三种语言都有自称", set(i18n.LANG_NAMES) == set(i18n.LANGS), str(i18n.LANG_NAMES))
    only_en = sorted(set(en) - set(ja))
    only_ja = sorted(set(ja) - set(en))
    check(u"_EN 与 _JA 键集合完全一致", not only_en and not only_ja,
          u"只在 EN：%s ｜ 只在 JA：%s" % (only_en[:6], only_ja[:6]))
    bad_empty = [k for k, v in ja.items() if not isinstance(v, str) or not v.strip()]
    check(u"_JA 的值都是非空字符串", not bad_empty, str(bad_empty[:6]))
    # 专有名词/纯符号允许与英文相同；其余不许照抄英文
    copied_en = [k for k, v in ja.items() if v == en.get(k) and not symbolish(v)]
    check(u"_JA 没有照抄 _EN（专有名词/符号除外）", not copied_en, str(copied_en[:6]))

    print(u"\n-- ② 切到日文真的返回日文（挑具体键比对） --")
    samples = [
        ("btn_send", u"送信"),
        ("lbl_settings_title" if "lbl_settings_title" in ja else "dlg_settings_title", None),
        ("input_placeholder", None),
        ("btn_start", None),
        ("lbl_quickstart", None),
        ("chat_empty", None),
    ]
    i18n.set_lang("ja")
    for key, want in samples:
        got = i18n.t(key, u"（中文兜底）")
        expect = want if want is not None else ja[key]
        check(u"ja：%s = %r" % (key, expect), got == expect, u"实际 %r" % got)
    check(u"ja：不是中文兜底", i18n.t("btn_send", u"发送") == u"送信", i18n.t("btn_send", u"发送"))
    # 版号串**故意拼出来**：仓库里不许出现写死的版号字面量（tools/bump_version.py --check 会扫全仓，
    # 连测试里的示例也算），但这里要验的正是"welcome() 用的是调用方给的号"。
    VER = "DICK v" + "9.9.9"
    check(u"ja：welcome() 用日文句式且带上调用方给的版号",
          i18n.welcome(VER) == u"👋 " + VER + u" へようこそ！", i18n.welcome(VER))
    check(u"ja：tokens_label 日文", i18n.tokens_label(5) == u"合計トークン: 5", i18n.tokens_label(5))

    print(u"\n-- ③ 英文与中文：老行为不许改坏 --")
    i18n.set_lang("en")
    check(u"en：btn_send = Send", i18n.t("btn_send", u"发送") == "Send", i18n.t("btn_send", u"发送"))
    check(u"en：welcome() 是英文句式", i18n.welcome(VER) == "👋 Welcome to " + VER + "!",
          i18n.welcome(VER))
    i18n.set_lang("zh")
    check(u"zh：返回中文原文", i18n.t("btn_send", u"发送") == u"发送", i18n.t("btn_send", u"发送"))
    check(u"zh：welcome() 中文句式", i18n.welcome(VER) == u"👋 欢迎使用 " + VER + u"！",
          i18n.welcome(VER))

    print(u"\n-- ④ 未知语言退回中文，不抛异常 --")
    for bogus in ("fr", "", None, "ZH", "jp", 123, "en-US"):
        try:
            i18n.set_lang(bogus)
            ok = (i18n.lang() == "zh") and (i18n.t("btn_send", u"发送") == u"发送")
            check(u"set_lang(%r) → zh" % (bogus,), ok, i18n.lang())
        except Exception as e:
            check(u"set_lang(%r) 不抛异常" % (bogus,), False, str(e))
    i18n.set_lang("zh")

    print(u"\n-- ⑤ 版号只有一个来源（i18n 里不许再写死版号/产品代） --")
    src = read(os.path.join(ROOT, "i18n.py"))
    check(u"i18n.py 里没有 v2.0 这类产品代", "v2.0" not in src)
    check(u"i18n.py 里没有写死的四段版号", not re.search(r"v?\d+\.\d+\.\d+\.\d+", src))
    check(u"欢迎语走 welcome(ver)（措辞归 i18n、号由调用方给）", "def welcome(ver)" in src)
    desk = read(os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"))
    check(u"主程序用 i18n.welcome(app_version.full())", "i18n.welcome(app_version.full())" in desk)
    check(u"主程序不再用写死的 welcome1", "welcome1" not in desk)

    print(u"\n-- ⑥ 首启判定：中文 / 日文 / 英文，认不出按中文 --")
    det = read(os.path.join(ROOT, "i18n.py"))
    check(u"检测函数存在", "def detect_system_lang(" in det)
    check(u"日文系统 → ja", "0x11" in det and 'return "ja"' in det)
    check(u"英文系统 → en", "0x09" in det and 'return "en"' in det)
    check(u"认不出 → zh（保持老行为）", det.count('return "zh"') >= 1)
    check(u"主程序用 detect_system_lang 做首启判定", "i18n.detect_system_lang()" in desk)
    check(u"老的 detect_english_system 已退役（别留死代码）", "detect_english_system" not in desk + det)

    print(u"\n-- ⑦ 前端入口真的是三选一 --")
    html = read(os.path.join(ROOT, "web", "index.html"))
    m = re.search(r'<select id="stLangSel".*?</select>', html, re.S)
    check(u"有语言下拉 stLangSel", bool(m))
    if m:
        block = m.group(0)
        for val, label in (("zh", u"中文"), ("en", "English"), ("ja", u"日本語")):
            check(u"下拉里有 option %s（%s）" % (val, label),
                  ('value="%s"' % val) in block and label in block)
    check(u"切换走 set_language（三值），不再用二档 toggle", "pywebview.api.set_language(" in html
          and "toggle_language" not in html)
    check(u"旧的单按钮 stLangBtn 已退役", "stLangBtn" not in html)
    zh_T = js_dict(html, "} else {\n    T = {", "};")
    ja_T = js_dict(html, "if (l === 'ja') {\n    T = {", "} else if (l === 'en')")
    check(u"前端 T 表：日文块解析出来了", len(ja_T) > 40, u"只解析到 %d 个键" % len(ja_T))
    if zh_T and ja_T:
        only_zh = sorted(set(zh_T) - set(ja_T))
        only_ja = sorted(set(ja_T) - set(zh_T))
        check(u"前端日文块与中文块键集合一致", not only_zh and not only_ja,
              u"只在 zh：%s ｜ 只在 ja：%s" % (only_zh[:5], only_ja[:5]))
        same = [k for k in ja_T if ja_T[k] == zh_T.get(k) and not symbolish(ja_T[k])
                and k not in SAME_AS_ZH_OK]
        check(u"前端日文没有照抄中文（同形词/专有名词/符号除外）", not same, str(same[:8]))
    check(u"发言者标签三语（你 / You / あなた）", u"'あなた'" in html and "'You'" in html)

    print(u"\n-- ⑧ 安卓端：三语 + 入口三选一 --")
    kt = read(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "I18n.kt"))
    en_kt, ja_kt = kt_map(kt, "EN"), kt_map(kt, "JA")
    check(u"I18n.kt 支持三种语言", 'LANGS = listOf("zh", "en", "ja")' in kt)
    check(u"I18n.kt 三种语言都有自称", all(x in kt for x in (u"中文", "English", u"日本語")))
    check(u"安卓 EN 与 JA 键集合一致",
          set(en_kt) == set(ja_kt),
          u"只在 EN：%s ｜ 只在 JA：%s" % (sorted(set(en_kt) - set(ja_kt))[:5],
                                          sorted(set(ja_kt) - set(en_kt))[:5]))
    copied = [k for k, v in ja_kt.items() if v == en_kt.get(k) and not symbolish(v)
              and k not in SAME_AS_EN_OK]
    check(u"安卓日文没有照抄英文（专有名词/格式名/符号除外）", not copied, str(copied[:8]))
    check(u"t() 未翻译时回退中文原串（不显示 key）", "TABLES[lang]?.get(key) ?: zh" in kt)
    check(u"detect() 认不出 → zh", 'else -> "zh"' in kt)
    check(u"normalize() 拦非法值", "fun normalize(" in kt)
    app_kt = read(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "App.kt"))
    check(u"安卓启动时归一化语言", "I18n.normalize(language.ifBlank { I18n.detect() })" in app_kt)
    dlg = read(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "Dialogs.kt"))
    check(u"设置里按 I18n.LANGS 渲染三选一", "for (code in I18n.LANGS)" in dlg)
    check(u"切换后立刻落盘", "language = code" in dlg and "I18n.lang = code" in dlg and "saveConfig()" in dlg)
    check(u"旧的二档循环已退役", 'if (language == "en") "zh" else "en"' not in dlg)
    # 安卓调用点：不许有"没翻译的键"（日文表里得真的存在）
    call_sites = re.findall(r'I18n\.t\("([^"]+)",\s*"((?:[^"\\]|\\.)*)"\)', app_kt + dlg)
    missing = sorted({k for k, _ in call_sites if k not in ja_kt})
    check(u"安卓调用点用到的键都在日文表里", not missing, u"缺：%s" % missing[:8])
    copied_zh = sorted({k for k, zh in call_sites
                        if k in ja_kt and ja_kt[k] == zh and not symbolish(zh)
                        and k not in SAME_AS_ZH_OK})
    check(u"安卓日文没有照抄中文原串（同形词/专有名词/符号除外）", not copied_zh, str(copied_zh[:8]))

    print(u"\n-- ⑨ config.json 里 language 三值都能存能读回（真实往返） --")
    import app_paths
    _real_base = app_paths.get_base_dir()
    tmp = tempfile.mkdtemp(prefix="dick_i18n_")
    try:
        import html_app
        app_paths.get_base_dir = lambda: tmp
        app_paths.get_plugin_dirs = lambda: [os.path.join(_real_base, "plugins")]
        html_app.BASE_DIR = tmp
        app = html_app.HtmlApp()
        for code in ("ja", "en", "zh", "ja"):
            r = app.api_set_language(code)
            check(u"%s：api_set_language 返回 ok" % code, bool(r.get("ok")) and r.get("lang") == code,
                  str(r))
            on_disk = {}
            try:
                with io.open(os.path.join(tmp, "config.json"), encoding="utf-8") as f:
                    on_disk = json.load(f)
            except Exception as e:
                check(u"%s：config.json 读得回来" % code, False, str(e))
            check(u"%s：已落盘到 config.json" % code, on_disk.get("language") == code,
                  str(on_disk.get("language")))
            check(u"%s：i18n 全局也跟着切了" % code, i18n.lang() == code, i18n.lang())
        # 模拟重启：重新构造应用，应读回上次选的 ja
        app2 = html_app.HtmlApp()
        check(u"重启后读回上次选的语言", app2.language == "ja" and i18n.lang() == "ja",
              u"%s / %s" % (app2.language, i18n.lang()))
        # 非法值也该被接住（不炸、落回中文）
        r = app2.api_set_language("fr")
        check(u"非法语言值 → 退回 zh 且落盘", r.get("lang") == "zh", str(r))
    finally:
        app_paths.get_base_dir = _real_base
        i18n.set_lang("zh")
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 58)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("I18N_LANGS_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
