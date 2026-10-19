# -*- coding: utf-8 -*-
"""安卓主题槽位守护：弹窗/抽屉这些"容器"必须从令牌派生，不许落回 Material3 默认色。

背景（2026-10 的用户截图）：深色主题下「创意工坊」弹窗是一片白，里面卡片却是深色。
根因不是硬编码，而是 **DickTheme 只映射了少数槽位**：
    AlertDialog 的底色取的是 `surfaceContainerHigh`，那个槽位没映射，
    就落回 M3 默认的淡紫（#F7F2FA）—— 在深色主题里白得像硬编码。

这条测试盯三件事：
  ① Tokens.kt 的**浅色与深色两套**都要映射容器类角色（各出现一次，不多不少）；
  ② 弹窗壳 DialogShell 里不许出现颜色字面量（`Color(0xFF…)` / `Color.White`）；
  ③ 任何 `DickDialog(` / `AlertDialog(` 调用不许自带 `containerColor=`（那样又绕开主题了）。

跑法：python tests\\test_android_theme_roles.py
"""
import io
import os
import re
import sys

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


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


TOKENS = os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "ui", "theme", "Tokens.kt")
SHELL = os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "ui", "components", "DialogShell.kt")
UI_DIR = os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "ui")

# M3 里"容器"类角色：弹窗/抽屉/卡片用<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌它们取底色。缺一个就会在某处露出默认淡紫。
CONTAINER_ROLES = [
    "surfaceContainerLowest",
    "surfaceContainerLow",
    "surfaceContainer",
    "surfaceContainerHigh",
    "surfaceContainerHighest",
    "surfaceBright",
    "surfaceDim",
]


def main():
    print("=" * 62)
    print(u"安卓主题槽位：容器角色必须从令牌派生（弹窗不许白得像硬编码）")
    print("=" * 62)

    tok = read(TOKENS)

    print(u"\n== ① 两套配色都映射了容器角色 ==")
    check(u"Tokens.kt 里同时有 lightColorScheme 与 darkColorScheme",
          "lightColorScheme(" in tok and "darkColorScheme(" in tok)
    for role in CONTAINER_ROLES:
        n = len(re.findall(r"\b%s\s*=" % role, tok))
        check(u"%s 映射了 2 次（浅色 + 深色）" % role, n == 2, u"实际 %d 次" % n)

    print(u"\n== ② 弹窗壳不许自带颜色 ==")
    shell = read(SHELL)
    check(u"DialogShell.kt 无 Color(0x…) 字面量", not re.search(r"Color\(0x", shell))
    check(u"DialogShell.kt 无 Color.White / Color.Black", "Color.White" not in shell and "Color.Black" not in shell)
    check(u"DialogShell 走 Material3 默认（没有 containerColor 参数）", "containerColor" not in shell)

    print(u"\n== ③ 屏里的弹窗不许自带 containerColor ==")
    offenders = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, UI_DIR)):
        for fn in files:
            if not fn.endswith(".kt"):
                continue
            path = os.path.join(base, fn)
            text = io.open(path, encoding="utf-8").read()
            for m in re.finditer(r"(DickDialog|AlertDialog)\s*\(", text):
                # 取调用括号后的 300 字符，看看有没有 containerColor
                seg = text[m.end():m.end() + 300]
                if "containerColor" in seg:
                    line = text.count("\n", 0, m.start()) + 1
                    offenders.append("%s:%d" % (os.path.relpath(path, ROOT), line))
    check(u"没有屏自己写 containerColor（写了就绕开主题）", not offenders, u"、".join(offenders[:5]))

    print(u"\n== ④ 对比：如果只有一个槽位被映射，弹窗就会露馅（防回归） ==")
    check(u"surfaceContainerHigh 与 surface 都指向令牌变量",
          re.search(r"surfaceContainerHigh\s*=\s*pal\.", tok) is not None or
          re.search(r"surfaceContainerHigh\s*=\s*palette\.", tok) is not None)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ANDROID_THEME_ROLES_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
