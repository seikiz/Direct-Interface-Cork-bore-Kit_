# -*- coding: utf-8 -*-
"""安卓硬编码颜色闸门：屏/组件里的颜色只许从令牌来（棘轮 + 字段集合 + 反向验证）。

为什么需要
----------
网页端审计（`tools/audit_contrast.py` 的漂移扫描）把"硬编码颜色"变成了看得见的数字；
安卓侧重跑一遍，落在 `ui/**` 里的字面色是 8 处（不含生成物与身份色）：

    ChatScreen.kt      引导框幕布 Color(0xCC0A0C10)
    AvatarCropScreen   裁剪台底 Color(0xFF111111)、四周遮罩 4 × Color(0x99000000)、框线 Color.White
    Ui.kt              头像首字颜色 Color.White  ← 这条是**真 bug**：白字压在身份色 #fbbf24 上
                       只有 1.67:1、压 #60a5fa 只有 2.54:1，用户说的"颜色费劲"就是它

而 2026-10 那次事故（`DickTheme` 少映射 `surfaceContainer*`，弹窗落回 M3 默认淡紫，深色主题下
白得像硬编码）是同一件事的另一张脸：**颜色不是从令牌来的**。当时是手改 `Tokens.kt` 补的，
于是生成器与产物漂了 —— `python tools/gen_tokens.py --check` 直接判过期，唯一真相形同虚设。

所以这道闸门守四件事（缺一条，下一轮就会退回去）：
  ① **棘轮**：`ui/**` 里的 `Color(0x…)` / `Color.White` / `Color.Black`（非白名单）≤ 基线（0，只许降）；
  ② **成色**：`DickPalette` 声明与 dark/light/oled 三套的字段集合必须一致，且与 `design/tokens.json`
     的角色表逐一对齐 —— 少一个角色就红（`surfaceContainer*` 那次就是这样漏的）；
  ③ **唯一真相**：`python tools/gen_tokens.py --check` 必须过（产物与 json 不许漂）；
  ④ **反向验证**：往临时树里塞一条硬编码 / 从字段表里删一个角色 / 白名单缺 reason，
     上面三条必须真的红 —— 否则这套断言只是装饰。

口径（很窄，故意的）
-------------------
  算硬编码：`Color(0xFF123456)`、`Color(0xCC0A0C10)`、`Color.White`、`Color.Black`、`Color.Red` …
  不算：`Color.Unspecified` / `Color.Transparent`（"没有颜色"的哨兵，不是颜色值）、
        注释里提到的（先剥注释再数，与对比度审计同一套去注释，行号不漂）、
        `ui/theme/Tokens.kt`（它**就是**令牌表，是生成物；它的字面色数单独钉死 = 角色 × 3 + 强调色 × 2）。
  白名单只有一条：`Theme.kt` 的 `AVATAR_PALETTE` —— 身份色（同一个人永远同一种颜色），
  不属于主题令牌；命中上限 8（就是那 8 枚），多一枚就红。

跑法：python tests/test_android_colors.py
"""
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
TOOLS = os.path.join(ROOT, "tools")

for _p in (TOOLS, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_contrast as AC          # noqa: E402  对比度公式 / 去注释，与审计同一口径
import gen_tokens as GT              # noqa: E402  角色表（唯一真相的另一半：生成器）

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

APP_DIR = os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app")
UI_DIR = os.path.join(APP_DIR, "ui")
THEME = os.path.join(UI_DIR, "theme", "Theme.kt")
TOKENS = os.path.join(UI_DIR, "theme", "Tokens.kt")
SRC = os.path.join(ROOT, "design", "tokens.json")

# ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 判定器
# 为什么 8 位也认：Compose 的 Color 是 AARRGGBB，幕布写 0xCC0A0C10 才是常态；
# 只认 8 位会漏掉 `Color(0xFF112233)` 这种 6 位简写（alpha 默认 0，反而是更糟的 bug）。
RE_HEX_LITERAL = re.compile(r"Color\(\s*0x([0-9a-fA-F]{8}|[0-9a-fA-F]{6})\s*\)")
# Compose 的命名色常量（CSS 那一套）。Unspecified / Transparent 是哨兵，故意不在表里。
RE_NAMED = re.compile(r"\bColor\.(White|Black|Gray|LightGray|DarkGray|Red|Green|Blue|"
                      r"Yellow|Cyan|Magenta)\b")

# 棘轮基线：语义硬编码只许 0（从 7 降到 0）。这个数字**只许往下调**，往上调就是开倒车。
BASELINE_SEMANTIC = 0
# 文字兜底棘轮：`Text(...)` 没显式给 color 的处数（2026-12 实测 123）。
# 为什么不要求 0：`OutlinedTextField(label = { Text("名字") })` 这类**应该**跟随控件自己的
# M3 语义色（浮动 label 会随焦点变淡），硬塞令牌反而丢状态。要守的是"别再涨"。
BASELINE_TEXT_NO_COLOR = 123
# 白名单：条目上限 8 条、命中次数上限 8 次（就是 8 枚身份色），两把锁一起上。
WHITELIST_MAX_ENTRIES = 8
WHITELIST_MAX_HITS = 8
WHITELIST = [
    dict(
        file="ui/theme/Theme.kt",
        block=("val AVATAR_PALETTE = listOf(", ")"),
        reason=("身份色：头像按名字散列取色，要保证「同一个人永远同一种颜色」，"
                "不属于主题令牌（见 Theme.kt 文件头）；压在它上面的文字色已走 on_identity 令牌，"
                "所以这里只剩 8 枚头像底色。"),
    )
]

# 恒定角色：三套主题同值（幕布/裁剪台/身份色墨）。它们**故意**不跟主题变，见 tokens.json 的 _why_fixed。
FIXED_ROLES = ("scrim", "scrim_soft", "stage", "stage_line", "on_identity")

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
    with io.open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


# ============================================================
#  扫描
# ============================================================
def scan_literals(text):
    """一行一行找字面色，返回 [(行号, 种类, 值)]。注释里的不算。"""
    body = AC.strip_comments(text, js=True)      # 与 tools/audit_contrast.py 同一套（行号不漂）
    out = []
    for i, line in enumerate(body.split("\n"), 1):
        for m in RE_HEX_LITERAL.finditer(line):
            out.append((i, "Color(0x)", u"0x" + m.group(1)))
        for m in RE_NAMED.finditer(line):
            out.append((i, "Color." + m.group(1), m.group(0)))
    return out


def _segment(rel):
    """文件属于哪一段：屏 / 组件 / 主题 / 壳层（报告按这个分段）。"""
    r = rel.replace("\\", "/")
    tag = r.split("/com/dick/app/", 1)[-1] if "/com/dick/app/" in r else r
    if tag.startswith("ui/screens/"):
        return u"屏"
    if tag.startswith("ui/components/"):
        return u"组件"
    if tag.startswith("ui/theme/"):
        return u"主题"
    return u"壳层"


def _block_range(lines, begin, end):
    """在 lines 里找 begin 起始的块，返回 (起始行号, 结束行号)（1 基，闭区间）；找不到返回 None。"""
    for i, ln in enumerate(lines):
        if begin in ln:
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == end:
                    return (i + 1, j + 1)
            return (i + 1, len(lines))
    return None


def audit(root):
    """扫一个仓库根下的 app 树，分类成 generated / whitelisted / semantic。

    返回 dict(generated, whitelisted, semantic, per_file)：
      generated   —— Tokens.kt（生成物，令牌表本身）
      whitelisted —— 命中白名单的（带 rule 与 reason）
      semantic    —— 剩下的全部：这些就是"必须为 0"的语义硬编码
    """
    app = os.path.join(root, APP_DIR)
    out = dict(generated=[], whitelisted=[], semantic=[], per_file={})
    if not os.path.isdir(app):
        return out
    for base, _dirs, files in os.walk(app):
        for fn in sorted(files):
            if not fn.endswith(".kt"):
                continue
            path = os.path.join(base, fn)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            text = read(path)
            hits = scan_literals(text)
            if not hits:
                continue
            out["per_file"][rel] = len(hits)
            if rel.endswith("ui/theme/Tokens.kt"):
                out["generated"].extend(hits)
                continue
            ranges = {}
            for rule in WHITELIST:
                if rel.endswith(rule["file"]):
                    rng = _block_range(text.split("\n"), rule["block"][0], rule["block"][1])
                    if rng:
                        ranges[rule["file"]] = rng
            for line_no, kind, val in hits:
                hit_rule = None
                for rule in WHITELIST:
                    rng = ranges.get(rule["file"])
                    if rng and rng[0] <= line_no <= rng[1]:
                        hit_rule = rule
                        break
                if hit_rule:
                    out["whitelisted"].append((rel, line_no, val, hit_rule))
                else:
                    out["semantic"].append((rel, line_no, val))
    return out


def gate(found):
    """闸门判定（反向验证直接喂合成结果给这里）。返回问题清单，空 = 绿。"""
    probs = []
    if len(found["semantic"]) > BASELINE_SEMANTIC:
        probs.append(u"语义硬编码 %d 处 > 基线 %d：%s"
                     % (len(found["semantic"]), BASELINE_SEMANTIC,
                        u"、".join(u"%s:%d %s" % (r, l, v) for r, l, v in found["semantic"][:5])))
    if len(found["whitelisted"]) > WHITELIST_MAX_HITS:
        probs.append(u"白名单命中 %d 次 > 上限 %d" % (len(found["whitelisted"]), WHITELIST_MAX_HITS))
    probs.extend(whitelist_problems(WHITELIST))
    return probs


# ============================================================
#  字段集合 / 唯一真相
# ============================================================
def palette_field_problems(tok_text):
    """Tokens.kt：DickPalette 声明 与 dark/light/oled 三套的字段集合必须完全一致。"""
    probs = []
    m = re.search(r"data class DickPalette\((.*?)\n\)", tok_text, re.S)
    if not m:
        return [u"找不到 DickPalette 声明"]
    declared = re.findall(r"val (\w+): Color", m.group(1))
    if sorted(declared) != sorted(GT.ROLES_KT):
        probs.append(u"DickPalette 字段与生成器角色表不一致：缺 %s，多 %s"
                     % ([f for f in GT.ROLES_KT if f not in declared],
                        [f for f in declared if f not in GT.ROLES_KT]))
    for name in ("dark", "light", "oled"):
        bm = re.search(r"val %s = DickPalette\((.*?)\n    \)" % name, tok_text, re.S)
        if not bm:
            probs.append(u"找不到 DickTokens.%s" % name)
            continue
        got = re.findall(r"^\s+(\w+) = Color\(", bm.group(1), re.M)
        if sorted(got) != sorted(declared):
            probs.append(u"DickTokens.%s 字段不齐：缺 %s，多 %s"
                         % (name, [f for f in declared if f not in got],
                            [f for f in got if f not in declared]))
    return probs


def tokens_json_problems(data):
    """design/tokens.json：暗/浅键集合一致、与生成器 ROLES 同序、恒定角色三套同值。"""
    probs = []
    colors = data.get("colors") or {}
    dark = [k for k in (colors.get("dark") or {}) if not k.startswith("_")]
    light = [k for k in (colors.get("light") or {}) if not k.startswith("_")]
    if dark != light:
        probs.append(u"暗/浅角色集合不同：只在一边的 %s" % sorted(set(dark) ^ set(light)))
    if dark != list(GT.ROLES):
        probs.append(u"与生成器 ROLES 不一致（角色表与选项都要对）：缺 %s，多 %s"
                     % ([r for r in GT.ROLES if r not in dark], [r for r in dark if r not in GT.ROLES]))
    oled = dict(colors.get("dark") or {})
    oled.update({k: v for k, v in (data.get("oled") or {}).items() if not k.startswith("_")})
    bad = [k for k in (data.get("oled") or {}) if not k.startswith("_") and k not in GT.ROLES]
    if bad:
        probs.append(u"oled 覆写了不存在的角色：%s" % bad)
    for role in FIXED_ROLES:
        for name, pal in (("dark", colors.get("dark") or {}), ("light", colors.get("light") or {}),
                          ("oled", oled)):
            if pal.get(role) is None:
                probs.append(u"恒定角色 %s 在 %s 里缺失" % (role, name))
            elif pal.get(role) != (colors.get("dark") or {}).get(role):
                probs.append(u"恒定角色 %s 在 %s 里变成了 %s（必须三套同值）"
                             % (role, name, pal.get(role)))
    return probs


def whitelist_problems(rules):
    """白名单自身：条数上限 + 每条必须带像样的 reason。"""
    probs = []
    if len(rules) > WHITELIST_MAX_ENTRIES:
        probs.append(u"白名单 %d 条 > 上限 %d" % (len(rules), WHITELIST_MAX_ENTRIES))
    for r in rules:
        if len((r.get("reason") or "").strip()) < 10:
            probs.append(u"白名单条目缺 reason：%s" % (r.get("file") or r))
        if not r.get("file") or not r.get("block"):
            probs.append(u"白名单条目缺 file/block：%s" % (r.get("file") or r))
    return probs


# ============================================================
#  身份色 / 幕布
# ============================================================
def avatar_palette(theme_text):
    """从 Theme.kt 读出 AVATAR_PALETTE 的实际取值（身份色是代码里的常量，不在令牌里）。"""
    rng = None
    lines = theme_text.split("\n")
    for i, ln in enumerate(lines):
        if "val AVATAR_PALETTE = listOf(" in ln:
            for j in range(i, len(lines)):
                if lines[j].strip() == ")":
                    rng = (i + 1, j + 1)
                    break
            break
    if not rng:
        return []
    seg = "\n".join(lines[rng[0] - 1:rng[1]])
    return [u"#" + v[2:].lower() for v in re.findall(r"Color\(0x([0-9A-Fa-f]{8})\)", seg)]


def _alpha(hexv):
    """'#0a0c10cc' → 0.8；6 位 → 1.0。"""
    h = (hexv or "").lstrip("#")
    return int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0


# ============================================================
#  文字兜底 / 弹窗 / 卡片：源码级契约（2026-12 两个真 bug 的回归位）
# ============================================================
def _paren_span(text, open_idx):
    """open_idx 指向 '('；返回 (括号内的参数串, 右括号下标)。跳过字符串里的括号。"""
    i, depth, quote = open_idx + 1, 1, None
    while i < len(text) and depth > 0:
        c = text[i]
        if quote:
            if c == quote and text[i - 1] != "\\":
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return text[open_idx + 1:i - 1], i - 1


def _call_body(text, m):
    """从 'Foo(' 的匹配处取出参数文本。"""
    return _paren_span(text, m.end() - 1)[0]


def _fn_body(text, name):
    """取 `fun name(...) { ... }` 的函数体（大括号内），找不到返回空串。"""
    m = re.search(r"fun\s+%s\(" % name, text)
    if not m:
        return u""
    _params, close = _paren_span(text, m.end() - 1)
    k = text.find("{", close)
    if k < 0:
        return u""
    depth, p = 1, k + 1
    while p < len(text) and depth > 0:
        if text[p] == "{":
            depth += 1
        elif text[p] == "}":
            depth -= 1
        p += 1
    return text[k + 1:p - 1]


def text_calls(text):
    """返回 (Text( 总数, 未显式给 color 的处数, 未给色的行号)。注释里的不算。"""
    body = AC.strip_comments(text, js=True)
    total, uncolored, lines = 0, 0, []
    for m in re.finditer(r"(?<![A-Za-z_])Text\(", body):
        total += 1
        if not re.search(r"\bcolor\s*=", _call_body(body, m)):
            uncolored += 1
            lines.append(body.count("\n", 0, m.start()) + 1)
    return total, uncolored, lines


def dialog_shell_problems(text):
    """DickDialog 必须把四个颜色槽位显式指到 LocalDickPalette（不许吃 M3 默认）。"""
    probs = []
    if "LocalDickPalette.current" not in text:
        probs.append(u"DialogShell 没读 LocalDickPalette")
    for slot, expr in (("containerColor", r"p\.surface2"),
                       ("titleContentColor", r"p\.text\b"),
                       ("textContentColor", r"p\.text\b"),
                       ("iconContentColor", r"p\.textSub")):
        if not re.search(r"%s\s*=\s*%s" % (slot, expr), text):
            probs.append(u"DickDialog 少了 %s = %s" % (slot, expr.replace(u"\\b", u"")))
    if RE_HEX_LITERAL.search(text) or RE_NAMED.search(text):
        probs.append(u"DickDialog 里出现颜色字面量")
    return probs


def card_problems(text):
    """DickCard 的 Surface 必须显式 contentColor（M3 的 contentColorFor 认不出令牌色）。"""
    body = _fn_body(text, "DickCard")
    if not body:
        return [u"找不到 DickCard"]
    if not re.search(r"contentColor\s*=\s*LocalDickPalette\.current\.text", body):
        return [u"DickCard 没显式 contentColor = LocalDickPalette.current.text"]
    return []


def icontext_problems(text):
    """IconText 的默认 color 必须是令牌色（哨兵 Unspecified 会退回 LocalContentColor）。"""
    m = re.search(r"fun IconText\(", text)
    if not m:
        return [u"找不到 IconText"]
    if not re.search(r"color\s*:\s*Color\s*=\s*LocalDickPalette\.current\.text",
                     _call_body(text, m)):
        return [u"IconText 的 color 默认值不是 LocalDickPalette.current.text"]
    return []


def theme_root_problems(tok_text, app_text):
    """DickTheme 必须提供 LocalContentColor；App() 必须把整棵树包进 DickTheme。"""
    probs = []
    if not re.search(r"LocalContentColor\s+provides\s+pal\.text", tok_text):
        probs.append(u"DickTheme 没提供 LocalContentColor = pal.text")
    if "LocalDickPalette provides pal" not in tok_text:
        probs.append(u"DickTheme 没提供 LocalDickPalette")
    if not re.search(r"DickTheme\(", app_text):
        probs.append(u"App() 没包 DickTheme（弹窗会落回 M3 默认色）")
    return probs


# ============================================================
#  main
# ============================================================
def main():
    data = json.loads(read(SRC))
    pals = AC.palettes_of(data)

    print("=" * 66)
    print(u"安卓硬编码颜色闸门（棘轮 / 字段集合 / 唯一真相 / 反向验证）")
    print("=" * 66)

    # ------------------------------------------------------------------
    # ① 判定器自检：先证明"该数的会数到、不该数的会放过"
    # ------------------------------------------------------------------
    print(u"\n== ① 判定器自检（判定器不许被改成永远数不到） ==")
    check(u"认 Color(0xFF123456)", len(scan_literals("val c = Color(0xFF123456)")) == 1)
    check(u"认带 alpha 的 Color(0xCC0A0C10)",
          len(scan_literals("Modifier.background(Color(0xCC0A0C10))")) == 1)
    check(u"认 Color.White / Color.Black",
          len(scan_literals("color = Color.White\nbg = Color.Black")) == 2)
    check(u"认 Color.Red 这类命名色", len(scan_literals("color = Color.Red")) == 1)
    check(u"不数 Color.Unspecified / Color.Transparent（哨兵，不是颜色）",
          not scan_literals("color = Color.Unspecified\ntint = Color.Transparent"))
    check(u"不数注释里的字面量",
          not scan_literals(u"// 旧写法 Color(0xFF111111) 已搬进令牌\n/* Color.White */\nval x = 1"))
    check(u"行号不漂（注释后的字面量报在第 3 行）",
          [ln for ln, _k, _v in scan_literals(u"// a\n// b\nval c = Color(0xFF123456)")] == [3])

    # ------------------------------------------------------------------
    # ② 现场扫描 + 分段
    # ------------------------------------------------------------------
    found = audit(ROOT)
    seg = {}
    for rel, _ln, _v in found["semantic"]:
        seg[_segment(rel)] = seg.get(_segment(rel), 0) + 1
    print(u"\n== ② 现场：ui/** + 壳层的语义字面色（不含生成物与白名单） ==")
    print(u"   分段：%s" % (u" ／ ".join(u"%s %d" % (k, seg.get(k, 0))
                                     for k in (u"屏", u"组件", u"主题", u"壳层"))))
    print(u"   逐文件：%s" % (u"、".join(u"%s=%d" % (r.split("/")[-1], n)
                                     for r, n in sorted(found["per_file"].items())) or u"无"))
    check(u"语义硬编码 %d 处 ≤ 基线 %d（棘轮：只许降）"
          % (len(found["semantic"]), BASELINE_SEMANTIC),
          len(found["semantic"]) <= BASELINE_SEMANTIC,
          u"、".join(u"%s:%d %s" % (r, l, v) for r, l, v in found["semantic"][:6]))
    check(u"屏（ui/screens/**）0 处", seg.get(u"屏", 0) == 0, u"实际 %d 处" % seg.get(u"屏", 0))
    check(u"组件（ui/components/**：DickCard/DickTag/按钮/DialogShell/Fields/States）0 处",
          seg.get(u"组件", 0) == 0, u"实际 %d 处" % seg.get(u"组件", 0))
    check(u"壳层（App.kt/Ui.kt/Dialogs.kt 等 app 根目录）0 处",
          seg.get(u"壳层", 0) == 0, u"实际 %d 处" % seg.get(u"壳层", 0))
    check(u"生成物之外的整棵树 ≤ 白名单上限 %d（现在 %d）"
          % (WHITELIST_MAX_HITS, len(found["whitelisted"]) + len(found["semantic"])),
          len(found["whitelisted"]) + len(found["semantic"]) <= WHITELIST_MAX_HITS)

    # ------------------------------------------------------------------
    # ③ 白名单：只许身份色，且必须有理由
    # ------------------------------------------------------------------
    print(u"\n== ③ 白名单（只有身份色一条，命中上限 8） ==")
    wl = found["whitelisted"]
    wl_probs = whitelist_problems(WHITELIST)
    check(u"白名单条目 %d 条 ≤ 上限 %d" % (len(WHITELIST), WHITELIST_MAX_ENTRIES),
          len(WHITELIST) <= WHITELIST_MAX_ENTRIES)
    check(u"每条白名单都带 reason（≥10 字）", not wl_probs, u"；".join(wl_probs[:3]))
    check(u"白名单命中 %d 次 ≤ 上限 %d" % (len(wl), WHITELIST_MAX_HITS),
          len(wl) <= WHITELIST_MAX_HITS)
    check(u"命中只落在 Theme.kt 的 AVATAR_PALETTE 块内",
          all(r.endswith(WHITELIST[0]["file"]) for r, _l, _v, _rule in wl),
          u"、".join(sorted({r for r, _l, _v, _rule in wl})))
    check(u"命中的是 8 枚互不相同的身份色",
          len({v for _r, _l, v, _rule in wl}) == 8,
          u"实际 %d 枚：%s" % (len({v for _r, _l, v, _rule in wl}),
                              sorted({v for _r, _l, v, _rule in wl})))
    for rel, line_no, val, rule in wl:
        print(u"       · %s:%d  %s  → %s" % (rel, line_no, val, rule["reason"][:28] + u"…"))

    # ------------------------------------------------------------------
    # ④ 生成物：Tokens.kt 就是令牌表本身
    # ------------------------------------------------------------------
    print(u"\n== ④ 生成物 Tokens.kt（它里面的字面色数是被钉死的） ==")
    tok_text = read(os.path.join(ROOT, TOKENS))
    expect = len(GT.ROLES) * 3 + 2 * len(data["accents"])
    check(u"字面色数 = 角色 %d × 3 套 + 强调色 %d × 2 = %d（现在 %d）"
          % (len(GT.ROLES), len(data["accents"]), expect, len(found["generated"])),
          len(found["generated"]) == expect)
    check(u"不再有 Color.Black / Color.White（scrim 槽位已走令牌）",
          "Color.Black" not in tok_text and "Color.White" not in tok_text)
    check(u"Material3 的 scrim 槽位 = pal.scrim（原来是写死的 Color.Black）",
          re.search(r"\bscrim\s*=\s*pal\.scrim", tok_text) is not None)
    check(u"容器类槽位各映射 2 次（浅色 + 深色，2026-10 那次事故的回归位）",
          all(len(re.findall(r"\b%s\s*=" % r, tok_text)) == 2
              for r in ("surfaceContainerLowest", "surfaceContainerLow", "surfaceContainer",
                        "surfaceContainerHigh", "surfaceContainerHighest", "surfaceBright",
                        "surfaceDim")))

    # ------------------------------------------------------------------
    # ⑤ 三套 palette 字段集合一致 + 与唯一真相对齐
    # ------------------------------------------------------------------
    print(u"\n== ⑤ 字段集合：DickPalette = dark = light = oled，且与 tokens.json 对齐 ==")
    field_probs = palette_field_problems(tok_text)
    check(u"DickPalette 与三套调色板字段齐全（%d 个角色）" % len(GT.ROLES),
          not field_probs, u"；".join(field_probs[:3]))
    declared = re.findall(r"val (\w+): Color", re.search(r"data class DickPalette\((.*?)\n\)",
                                                       tok_text, re.S).group(1))
    check(u"字段名与生成器的 ROLES_KT 逐一相同（顺序也相同）", declared == list(GT.ROLES_KT),
          u"差集 %s" % (set(declared) ^ set(GT.ROLES_KT)))
    json_probs = tokens_json_problems(data)
    check(u"tokens.json：暗/浅键集合一致、与 ROLES 同序、OLED 只覆写合法角色",
          not json_probs, u"；".join(json_probs[:3]))
    check(u"恒定角色（%s）三套同值（不是漏改）" % u"/".join(FIXED_ROLES),
          not [p for p in json_probs if u"恒定角色" in p])
    alpha_roles = {k for k, v in (data["colors"]["dark"] or {}).items()
                   if isinstance(v, str) and len(v) == 9}
    check(u"只有幕布类角色允许带 alpha（#rrggbbaa）：%s" % sorted(alpha_roles),
          alpha_roles == {"scrim", "scrim_soft"}, u"实际 %s" % sorted(alpha_roles))

    # ------------------------------------------------------------------
    # ⑥ 唯一真相：生成器 --check
    # ------------------------------------------------------------------
    print(u"\n== ⑥ 唯一真相：python tools/gen_tokens.py --check ==")
    proc = subprocess.run([sys.executable, "-X", "utf8",
                           os.path.join(TOOLS, "gen_tokens.py"), "--check"],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = u"\n".join((proc.stdout or "").strip().split("\n")[-3:])
    check(u"gen_tokens.py --check 退出码 0", proc.returncode == 0,
          u"退出码 %s\n%s\n%s" % (proc.returncode, tail, (proc.stderr or "")[-300:]))

    # ------------------------------------------------------------------
    # ⑦ 对比度：身份色上的墨 + 裁剪框线 + 幕布力度
    # ------------------------------------------------------------------
    print(u"\n== ⑦ 新角色的对比度（用 audit_contrast 的公式，不另算一套） ==")
    theme_text = read(os.path.join(ROOT, THEME))
    av = avatar_palette(theme_text)
    check(u"从 Theme.kt 解析出 8 枚身份色（白名单上限与它对齐）", len(av) == 8, u"%s" % av)
    ink = pals["dark"]["on_identity"]
    worst = min([(AC.contrast(ink, c), c) for c in av]) if av else (0, u"-")
    check(u"on_identity 压 8 枚身份色都 ≥4.5（最差 %.2f @ %s）" % (worst[0], worst[1]),
          worst[0] >= 4.5)
    white_worst = min([(AC.contrast("#ffffff", c), c) for c in av]) if av else (99, u"-")
    check(u"（对照）白字压最亮那枚只有 %.2f —— 所以原来那句 Color.White 必须换掉"
          % white_worst[0], white_worst[0] < 4.5)
    check(u"stage_line 压 stage ≥3.0（裁剪框线是控件边界）",
          AC.contrast(pals["dark"]["stage_line"], pals["dark"]["stage"]) >= 3.0)
    check(u"幕布 alpha 落在 0.5~0.95（半透明才叫幕布）",
          all(0.5 <= _alpha(pals["dark"][r]) <= 0.95 for r in ("scrim", "scrim_soft")),
          u"scrim=%.2f scrim_soft=%.2f" % (_alpha(pals["dark"]["scrim"]),
                                           _alpha(pals["dark"]["scrim_soft"])))

    # ------------------------------------------------------------------
    # ⑧ 弹窗 / 卡片 / 文字兜底：2026-12 两个真 bug 的回归位
    # ------------------------------------------------------------------
    print(u"\n== ⑧ 弹窗与选中态（深色主题下白底 / 标题发暗 的回归位） ==")
    shell_text = read(os.path.join(ROOT, UI_DIR, "components", "DialogShell.kt"))
    cards_text = read(os.path.join(ROOT, UI_DIR, "components", "Cards.kt"))
    ui_text = read(os.path.join(ROOT, APP_DIR, "Ui.kt"))
    app_text = read(os.path.join(ROOT, APP_DIR, "App.kt"))
    d_probs = dialog_shell_problems(shell_text)
    check(u"DickDialog 四个颜色槽位全部显式取令牌", not d_probs, u"；".join(d_probs))
    c_probs = card_problems(cards_text)
    check(u"DickCard 显式 contentColor = 令牌 text", not c_probs, u"；".join(c_probs))
    i_probs = icontext_problems(ui_text)
    check(u"IconText 默认 color = 令牌 text", not i_probs, u"；".join(i_probs))
    t_probs = theme_root_problems(tok_text, app_text)
    check(u"App() 包 DickTheme，且 DickTheme 提供 LocalContentColor = pal.text",
          not t_probs, u"；".join(t_probs))
    raw_dlg = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, UI_DIR, "screens")):
        for fn in files:
            if not fn.endswith(".kt"):
                continue
            p = os.path.join(base, fn)
            t = AC.strip_comments(read(p), js=True)
            for m in re.finditer(r"\bAlertDialog\s*\(", t):
                raw_dlg.append("%s:%d" % (os.path.basename(p), t.count("\n", 0, m.start()) + 1))
    check(u"屏里没有裸 AlertDialog(（弹窗只有一个出口）", not raw_dlg,
          u"、".join(raw_dlg[:5]))

    total_text, no_color, no_color_lines = 0, 0, []
    for base, _dirs, files in os.walk(os.path.join(ROOT, APP_DIR)):
        for fn in sorted(files):
            if not fn.endswith(".kt"):
                continue
            t, u_, ls = text_calls(read(os.path.join(base, fn)))
            total_text += t
            no_color += u_
            no_color_lines.extend("%s:%d" % (fn, x) for x in ls)
    check(u"Text(...) 未显式给色 %d 处 ≤ 基线 %d（棘轮：只许降）"
          % (no_color, BASELINE_TEXT_NO_COLOR), no_color <= BASELINE_TEXT_NO_COLOR,
          u"、".join(no_color_lines[:8]))
    print(u"       Text( 共 %d 处，其中未给色 %d 处（基线 %d）"
          % (total_text, no_color, BASELINE_TEXT_NO_COLOR))

    print(u"   选中态（surface_2 底）上的文字对比度：")
    oled_pal = dict(pals["dark"])
    oled_pal.update({k: v for k, v in (data.get("oled") or {}).items() if not k.startswith("_")})
    for name, pal in ((u"暗色", pals["dark"]), (u"浅色", pals["light"]), (u"OLED", oled_pal)):
        r_txt = AC.contrast(pal["text"], pal["surface_2"])
        r_sub = AC.contrast(pal["text_sub"], pal["surface_2"])
        r_acc = AC.contrast(pal["accent"], pal["surface_2"])
        print(u"       %-4s text/text_sub/accent 压 surface_2 = %.2f / %.2f / %.2f"
              % (name, r_txt, r_sub, r_acc))
        check(u"%s：选中卡片标题（text 压 surface_2）≥4.5（%.2f）" % (name, r_txt), r_txt >= 4.5)
        check(u"%s：选中卡片次要字（text_sub）≥4.5（%.2f）" % (name, r_sub), r_sub >= 4.5)

    # ------------------------------------------------------------------
    # ⑨ 反向验证：闸门必须真的会红
    # ------------------------------------------------------------------
    print(u"\n== ⑨ 反向验证（塞坏数据，闸门必须红） ==")
    tmp = tempfile.mkdtemp(prefix="dick_colors_", dir=os.environ.get("TEMP") or None)
    try:
        fake_ui = os.path.join(tmp, UI_DIR)
        os.makedirs(os.path.join(fake_ui, "theme"))
        os.makedirs(os.path.join(fake_ui, "screens"))
        shutil.copyfile(os.path.join(ROOT, TOKENS), os.path.join(fake_ui, "theme", "Tokens.kt"))
        bad_kt = os.path.join(fake_ui, "screens", "SeededBad.kt")
        with io.open(bad_kt, "w", encoding="utf-8", newline="\n") as f:
            f.write(u"package com.dick.app\n\nval seeded = Color(0xFF123456)\n")
        seeded = audit(tmp)
        check(u"塞一条 Color(0xFF123456) → 语义硬编码从 0 变 1",
              len(seeded["semantic"]) == 1, u"%s" % seeded["semantic"])
        check(u"…并被 gate() 判红", bool(gate(seeded)), u"%s" % gate(seeded)[:2])
        check(u"…而且报的是那条塞进去的文件",
              bool(seeded["semantic"]) and seeded["semantic"][0][0].endswith("SeededBad.kt"))
        broken = tok_text.replace("    val stage: Color,\n", "")
        check(u"从 DickPalette 删掉一个角色（stage）→ 字段校验报红",
              broken != tok_text and bool(palette_field_problems(broken)))
        badj = json.loads(json.dumps(data))
        badj["colors"]["light"].pop("stage", None)
        check(u"tokens.json 浅色少一个角色 → 校验报红", bool(tokens_json_problems(badj)))
        badj2 = json.loads(json.dumps(data))
        badj2["colors"]["light"]["stage"] = "#222222"
        check(u"恒定角色在浅色里被改成别的值 → 校验报红", bool(tokens_json_problems(badj2)))
        check(u"白名单缺 reason → 报红",
              bool(whitelist_problems([dict(file="x", block=("a", "b"), reason=u"")])))
        check(u"弹窗壳退回 M3 默认（删掉 containerColor）→ 报红",
              bool(dialog_shell_problems(shell_text.replace("containerColor = p.surface2,", ""))))
        check(u"DickCard 删掉 contentColor → 报红",
              bool(card_problems(cards_text.replace(
                  "contentColor = LocalDickPalette.current.text,", ""))))
        check(u"IconText 默认色改回哨兵 → 报红",
              bool(icontext_problems(ui_text.replace(
                  "color: Color = LocalDickPalette.current.text", "color: Color = Color.Unspecified"))))
        check(u"App() 不包 DickTheme → 报红",
              bool(theme_root_problems(tok_text, u"fun App() { ChatScreen() }")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 66)
    print(u"通过 %d ／ 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ANDROID_COLORS_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
