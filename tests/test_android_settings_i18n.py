# -*- coding: utf-8 -*-
"""设置屏的文案一致性检查：**不允许裸中文字面量**（注释不算）。

为什么需要
----------
用户截了一张设置屏：`テーマ：浅色` `アクセント：緑` `言語` 是日文，
而同一屏里的"时间流速""壁纸""开发者模式"还是中文 —— 因为只有一部分文案走了
`I18n.t()`，其余硬编码在代码里。这种漏法**编译不报错、跑起来也"能用"**，
只有切到英文/日文才会露馅，所以必须由测试盯着。

口径（很窄，故意的）
--------------------
  · 只查 `ui/screens/settings/SettingsScreen.kt`（这一屏是用户报障的那一屏）；
  · "裸中文" = 双引号字符串里含 CJK，且**不在** `I18n.t("key", "中文原串")` 的第二个参数位置；
  · 注释（`//` 与 `/* … */`）里可以随便写中文；
  · 白名单 `ALLOW` 只放"不打算翻译"的：分隔符、纯符号、示例串。

以后每搬一屏，把它加进 `FILES` 就行（这条检查的意义是"加一屏就多一个被盯住的"）。

跑法：python tests/test_android_settings_i18n.py
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")
STRINGS = os.path.join(ROOT, "lang", "strings.json")

# 被盯住的屏（搬进<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌来一屏就加一行）
FILES = [
    os.path.join(APP, "ui", "screens", "settings", "SettingsScreen.kt"),
    # 2026-11 新增：API 教程面板 + 首启向导（同一批 guide_*/apiWiz* 键，三语齐全）
    os.path.join(APP, "ui", "screens", "api", "ApiGuideScreen.kt"),
]

# 不翻译的串：分隔/符号/示例（都是"不是给用户读的句子"）
ALLOW = {
    u"　",          # 全角空格（时间流速那行的分隔）
    u"−", u"＋",    # 计数按钮
    u"● ", u"○ ",  # 选中/未选中前缀
}

CJK = re.compile(u"[\u4e00-\u9fff]")
STR = re.compile(r'"((?:[^"\\\n]|\\.)*)"')

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


def strip_comments(src):
    """去掉 // 与 /* */ 注释（保留换行，别把行号弄乱）。字符串里的 // 不处理 —— 这些屏没有。"""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            if j < 0:
                break
            out.append(" " * (j - i))
            i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join("\n" if ch == "\n" else " " for ch in src[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def main():
    print("=" * 62)
    print(u"设置屏文案一致性（裸中文字面量 = 漏译）")
    print("=" * 62)

    doc = json.loads(read(STRINGS))
    keys = doc.get("keys") or {}
    langs = list(doc.get("langs") or [])
    check(u"langs 是 zh/en/ja", langs == ["zh", "en", "ja"], str(langs))

    for path in FILES:
        rel = os.path.relpath(path, ROOT)
        print(u"\n== %s ==" % rel)
        check(u"文件在", os.path.isfile(path), rel)
        if not os.path.isfile(path):
            continue
        raw = read(path)
        src = strip_comments(raw)

        # ① 所有 I18n.t 的 key 必须在表里，且三语齐全
        used = re.findall(r'I18n\.t\(\s*"([^"]+)"', src)
        check(u"用了 I18n.t（%d 处）" % len(used), len(used) >= 30, str(len(used)))
        missing = [k for k in used if k not in keys]
        check(u"用到的 key 都在 lang/strings.json 里", not missing, u"缺：%s" % missing[:8])
        empty = [k for k in used if k in keys and any(not (keys[k].get(lg) or "").strip() for lg in ("zh", "en", "ja"))]
        check(u"用到的 key 三语齐全", not empty, u"不全：%s" % empty[:8])
        wrong_side = [k for k in used if k in keys and "android" not in (keys[k].get("used_by") or [])]
        check(u"用到的 key 都声明了 used_by=android", not wrong_side, u"%s" % wrong_side[:8])

        # ② 裸中文字面量：先挖掉 I18n.t 的第二个参数，再看剩下的字符串
        spans = [m.span(1) for m in re.finditer(r'I18n\.t\(\s*"[^"]+"\s*,\s*("(?:[^"\\\n]|\\.)*")', src)]
        # 运行线任务名（Lanes.on(Lanes.xxx, "…")）不是给用户看的文案，是状态页上的诊断标签 ——
        # 它归 tests/test_android_lanes.py 管，这里不算"漏译"。
        spans += [m.span(1) for m in re.finditer(r'Lanes\.on\(\s*Lanes\.\w+\s*,\s*("(?:[^"\\\n]|\\.)*")', src)]
        bare = []
        for m in STR.finditer(src):
            if any(a <= m.start(1) < b for a, b in spans):
                continue
            s = m.group(1)
            if s in ALLOW:
                continue
            if CJK.search(s):
                line = src[:m.start()].count("\n") + 1
                bare.append((line, s[:40]))
        check(u"没有裸中文字面量（注释除外）", not bare,
              u"漏走的：%s" % (u"、".join(u"L%d:%s" % (ln, s) for ln, s in bare[:10])))

        # ③ 输入框里不许再塞说明（用户报障的原话："影响观感"）
        #    规则：DickField / DickLabeledField 的 label 只许是短名字，不许出现"留空""例如""如 "这类说明。
        hint_words = [u"留空", u"例如", u"如 ", u"示例", u"（可选）"]
        bad_label = []
        for m in re.finditer(r'label\s*=\s*(I18n\.t\(\s*"[^"]+"\s*,\s*"(?:[^"\\\n]|\\.)*"\)|"(?:[^"\\\n]|\\.)*")', src):
            for w in hint_words:
                if w in m.group(1):
                    bad_label.append((src[:m.start()].count("\n") + 1, m.group(1)[:40]))
                    break
        check(u"输入框 label 里没有说明性文字（说明走 hint）", not bad_label,
              u"%s" % (u"、".join(u"L%d:%s" % (ln, s) for ln, s in bad_label[:6])))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ANDROID_SETTINGS_I18N_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
