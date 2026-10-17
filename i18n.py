# -*- coding: utf-8 -*-
"""i18n.py —— 三语界面（中文 / English / 日本語）的运行时读取口。

**唯一真相是 `lang/strings.json`**（原来这个文件里手写两张 dict：`_EN` / `_JA`，
和 `web/index.html` 的 JS 表、安卓 `I18n.kt` 的 map 各写一份 —— 三份迟早对不上）。
现在：

    lang/strings.json
      ├── web/i18n.js        ← tools/gen_i18n.py 生成（页面 setT() 用）
      ├── 这里               ← 运行时读 json（本文件不再内联任何文案）
      └── I18nStrings.kt     ← tools/gen_i18n.py 生成（安卓用）

约定：
  · `set_lang()` 只认 zh / en / ja，**认不出退回中文**（老行为：不炸、不乱切）；
  · `t(key, zh)`：当前语言里有这个键就用表里的，没有就返回调用点给的中文原串
    （**绝不显示 key 名**）；`zh` 也走表，调用点默认值应当与表里一致
    （tests/test_i18n_langs.py 会逐条比对）；
  · 读不到 json 时**优雅降级**：所有 `t()` 直接返回调用点给的中文，不影响启动；
  · 版号不在这里写死：措辞归 i18n（`welcome(ver)`），版号串由调用方给
    （`i18n.welcome(app_version.full())`）。
"""

import io
import json
import os
import sys

LANGS = ("zh", "en", "ja")
LANG_NAMES = {"zh": "中文", "en": "English", "ja": "日本語"}

JSON_REL = os.path.join("lang", "strings.json")
_LANG = "zh"
_TABLE = {}          # {lang: {key: 文案}}
_LOADED_FROM = ""    # 读到了哪份 json（调试/面板用；读不到就是空串）


def _roots():
    """找 lang/strings.json：PyInstaller 解包目录优先，其次源码目录。"""
    out = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        out.append(mei)
    out.append(os.path.dirname(os.path.abspath(__file__)))
    return out


def load():
    """把 json 读成 {lang: {key: 文案}}。读不到就留空表（t() 全部退回中文）。"""
    global _TABLE, _LOADED_FROM
    table = {}
    for d in _roots():
        p = os.path.join(d, JSON_REL)
        try:
            with io.open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            continue
        keys = doc.get("keys") if isinstance(doc, dict) else None
        if not isinstance(keys, dict) or not keys:
            continue
        for lg in LANGS:
            table[lg] = dict((k, str(v.get(lg) or "")) for k, v in keys.items()
                             if isinstance(v, dict))
        _LOADED_FROM = p
        break
    _TABLE = table
    return table


def reload():
    """测试/命令面板用：重新读盘（json 改了不必重启进程）。"""
    return load()


def table_ok():
    """三语表都读到了？没有的话 t() 会全部退回中文原串（优雅降级）。"""
    return all(_TABLE.get(lg) for lg in LANGS)


def set_lang(lang):
    """只认 zh / en / ja；认不出退回中文（老行为：不炸、不乱切）"""
    global _LANG
    _LANG = lang if lang in LANGS else "zh"


def lang():
    return _LANG


def t(key, zh):
    """当前语言的文案；表里没有就返回调用点给的中文原串（绝不显示 key 名）。"""
    row = _TABLE.get(_LANG) or {}
    val = row.get(key)
    return val if val else zh


def welcome(ver):
    """欢迎语：**措辞来自 json，版号由调用方给**（版号只有 version.json 一个来源）。

    2026-12：界面文案里不再允许 emoji 字符，兜底串也跟 json 一样去掉行首的 👋
    （图标位由前端按文案表渲染，见 web 的 [ic:名字] 与安卓的 IconText(icon = …)）。
    """
    return t("welcome", u"欢迎使用 %s！") % str(ver)


def tokens_label(n):
    return t("tokens_label", u"总消耗: %s tokens") % str(n)


def roles_label(zh_text, count):
    """count=0 时显示无角色；否则前缀 + 中文角色名列表（角色名是数据，不翻译）

    这里给的中文默认值就是**读不到 json 时的降级文案**，所以必须是真中文，
    不能传空串（踩过：传空串会让"缺 json"时的界面变成空白）。
    """
    if count == 0:
        return t("status_roles_prefix", u"当前角色：") + t("roles_none", u"无")
    return t("status_roles_prefix", u"当前角色：") + zh_text.replace(u"当前角色：", "")


def detect_system_lang():
    """首启判定：中文系统 → zh；日文系统 → ja；英文系统 → en；**认不出 → zh**（保持老行为）"""
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        if lid == 0x11:
            return "ja"
        if lid == 0x09:
            return "en"
        return "zh"
    except Exception:
        pass
    try:
        import locale
        name = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        name = ""
    if name.startswith("ja"):
        return "ja"
    if name.startswith("en"):
        return "en"
    return "zh"


def detect_english_system():
    """老接口（保留兼容）：英文系统返回 True。新代码请用 detect_system_lang()。"""
    return detect_system_lang() == "en"


load()
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌