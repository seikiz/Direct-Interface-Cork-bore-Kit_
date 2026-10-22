# -*- coding: utf-8 -*-
"""括号保护：玩家的「（动作）」不许被任何用户域规则吃掉。

用户报的 bug：
    打 `(摸摸头)没事啦`，发出去变成 `摸摸头没事啦`（括号没了，字还在）。
翻遍全仓也没找到确定的元凶，所以改成**两端都加保护**：
  · 桌面 `_apply_regex_pipeline(scope="user")`：规则若让括号变少，跳过并打印规则 id
  · 安卓 `RegexEngine.apply(scope="user")`：同一策略
  · 两端在发送前做一次括号诊断（输入输出对不上就打印原文）

本测试钉住：
  ① lost_brackets 能准确认出"少了括号"（而不会把正常文本误判）
  ② keeps_user_text 会拦下吃括号的规则、放行不碰括号的规则
  ③ shield/unshield 是原样往返
  ④ 两端代码里确实接了这个保护（源码闸门，防回归删掉）
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import text_shield as TS   # noqa: E402

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


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read()


def main():
    print("=" * 62)
    print(u"括号保护（玩家的动作描写不是噪声）")
    print("=" * 62)

    print(u"\n== ① lost_brackets 判据 ==")
    check(u"吃掉全角括号 → 认出来",
          TS.lost_brackets(u"（摸摸头）没事啦", u"摸摸头没事啦") == (2, ["（", "）"]))
    check(u"吃掉半角括号 → 认出来",
          TS.lost_brackets(u"(摸摸头)没事啦", u"摸摸头没事啦") == (2, ["(", ")"]))
    check(u"原样不变 → 不算丢", TS.lost_brackets(u"（摸摸头）没事啦", u"（摸摸头）没事啦") == (0, []))
    check(u"只是多了括号 → 不算丢", TS.lost_brackets(u"没事啦", u"（摸摸头）没事啦") == (0, []))
    check(u"正常文本（没有括号）→ 不算丢", TS.lost_brackets(u"今天下雨了", u"今天下雨。") == (0, []))

    print(u"\n== ② keeps_user_text：该拦的拦、该放的放 ==")
    import re
    out, blocked = TS.keeps_user_text(
        lambda: re.sub(r"[（(][^）)]*[）)]", "", u"（摸摸头）没事啦"), u"（摸摸头）没事啦", "rm_action")
    check(u"吃括号的规则被拦下", blocked and out == u"（摸摸头）没事啦", out)
    out2, blocked2 = TS.keeps_user_text(
        lambda: re.sub(r"[（(]", "", u"（摸摸头）没事啦"), u"（摸摸头）没事啦", "rm_open")
    check(u"只删左括号也会被拦", blocked2 and out2 == u"（摸摸头）没事啦", out2)
    out3, blocked3 = TS.keeps_user_text(
        lambda: re.sub(r"\n{3,}", "\n\n", u"a\n\n\n\nb"), u"a\n\n\n\nb", "strip_blank")
    check(u"不碰括号的规则照常生效", (not blocked3) and out3 == u"a\n\nb", repr(out3))
    out4, _ = TS.keeps_user_text(lambda: 1 / 0, u"（x）", "boom")
    check(u"规则抛异常 → 保留原文", out4 == u"（x）")

    print(u"\n== ③ shield / unshield ==")
    src = u"（摸摸头）(笑)没事啦"
    check(u"shield 后括号全藏起来", all(c not in TS.shield(src) for c in u"（）()"), TS.shield(src))
    check(u"unshield 原样还原", TS.unshield(TS.shield(src)) == src)
    check(u"空串安全", TS.shield("") == "" and TS.unshield("") == "")

    print(u"\n== ④ 两端真的接了保护（源码闸门） ==")
    kit = read("Direct-Interface Cork-bore Kit.py")
    check(u"桌面正则在用户作用域用 keeps_user_text", "text_shield.keeps_user_text" in kit)
    check(u"桌面发送前有括号诊断", u"[括号诊断]" in kit)
    kt = read(os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "core", "RegexEngine.kt"))
    check(u"安卓有 lostBrackets", "fun lostBrackets(" in kt)
    check(u"安卓用户作用域会跳过吃括号的规则", 'scope == "user" && lostBrackets(t, out)' in kt)

    print(u"\n== ⑤ 反向：AI 侧不受影响 ==")
    check(u"AI 作用域仍走原逻辑（没有被 guard 拦）",
          'if (scope == "user" && lostBrackets' in kt and 'if (scope == "ai"' not in kt)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("TEXT_SHIELD_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌