# -*- coding: utf-8 -*-
"""分支图布局闸门：dp 与 px 不许混着用（"节点叠在一起、字压字"的回归位）。

背景（2026-12 用户截图：回档的二维分支图里四行字叠在一起）
------------------------------------------------------------
`BranchesScreen.kt` 的树图原来混了两把尺子：

    坐标：px = n.x * xSpacing * scale + panX      （px，且**乘了** scale）
    卡片：.size(chipW.dp, chipH.dp)               （dp，**没乘** scale）
    间距：xSpacing = 150f, ySpacing = 96f, scale 初始 0.8f

密度 2.75 的手机上：卡片高 42dp = 115.5px，而层与层只差 96 × 0.8 = 76.8px
→ 上下两张卡重叠 38.7px，下一张的顶部文字从上一张里透出来。
横向更糟：卡片宽 138dp = 379.5px，列距 150 × 0.8 = 120px，整排全叠。

修法（不是打补丁，是换结构）：
  · dp → px **只算一次**（LocalDensity），之后坐标/卡片/间距全在同一个"未缩放 px"坐标系里；
  · 缩放由**一层** `graphicsLayer(transformOrigin = 左上角)` 统一施加，卡片与连线一起缩；
  · 间距与卡片都是 dp，于是"叠不叠"与屏幕密度无关 —— 这才是能被测试钉住的不变量。

这道闸门守四件事：
  ① 间距不等式：横向 ≥ 卡片宽 + 16dp，纵向 ≥ 卡片高 + 20dp（另加一条：还要盖住卡片下方的选项小签）；
  ② 单位混用：源码里不许再出现"坐标乘 scale"（`scale * zoom` 那条手势语句是唯一白名单，附理由）；
  ③ 尺寸来源：`.size(...)` 的宽高必须来自同一组常量，不许字面量 138/42 散落；
  ④ 反向验证：把 ySpacing 改成 80、把 xSpacing 改成 150、把 `* scale` 塞回坐标 —— 都必须红。

跑法：python tests\\test_branch_graph_layout.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app",
                   "ui", "screens", "backup", "BranchesScreen.kt")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS = 0
FAIL = 0

# 间距余量（dp）。改小就是"又要叠<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌"的前奏，所以写进断言而不是注释。
GAP_X_MIN = 16.0
GAP_Y_MIN = 20.0
GAP_OPTION_MIN = 12.0     # 卡片下方还挂着最多 OPTIONS_MAX 个选项小签
DENSITIES = (1.0, 1.5, 2.0, 2.75, 3.5)

# 白名单（**只有 1 条**）：唯一允许出现 `* scale` 的地方。理由写清楚，否则下一个人会照抄。
SCALE_WHITELIST = [
    (r"scale\s*\*\s*zoom",
     u"手势缩放：这里是给 scale 状态本身乘 zoom（scale = scale * zoom），不是拿坐标乘缩放；"
     u"坐标乘 scale 的写法（px = n.x * xSpacing * scale + panX）已彻底删除。"),
]


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


def blank_comments(text):
    """把注释抹成等长空白（保留换行，行号不漂）。

    为什么必须抹：文件头要把**旧 bug 的写法**原样引用出来（`px = n.x * xSpacing * scale + panX`、
    `take(16)`），不抹注释的话"反例说明"会被自己的扫描器当成违规 —— 那就只能把教训删掉，
    下一轮又会有人照旧写。字符串里的内容原样保留（只认引号外的注释）。
    """
    out, i, n, quote = [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == quote and text[i - 1] != "\\":
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
            out.append(c)
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(u" " * (j - i))
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(u"".join(u"\n" if ch == "\n" else u" " for ch in text[i:j]))
            i = j
            continue
        out.append(c)
        i += 1
    return u"".join(out)


# ============================================================
#  纯函数：常量复算（不受源码写法影响，能直接喂合成数据做反向验证）
# ============================================================
NEEDED = ("CHIP_W_DP", "CHIP_H_DP", "X_SPACING_DP", "Y_SPACING_DP",
          "OPTION_H_DP", "OPTION_GAP_DP", "OPTIONS_MAX")


def parse_consts(text):
    """从 Kotlin 源里取布局常量（`private const val NAME = 150f` / `= 3`）。"""
    out = {}
    for name in NEEDED:
        m = re.search(r"const\s+val\s+%s\s*=\s*(-?[\d.]+)f?" % re.escape(name), text)
        if m:
            out[name] = float(m.group(1))
    return out


def spacing_problems(v):
    """间距与卡片尺寸的不等式。返回问题清单（空 = 过）。"""
    probs = []
    miss = [k for k in NEEDED if k not in v]
    if miss:
        return [u"常量缺失：%s" % miss]
    if v["X_SPACING_DP"] < v["CHIP_W_DP"] + GAP_X_MIN:
        probs.append(u"横向间距 %.0f < 卡片宽 %.0f + %.0f（相邻两列会叠）"
                     % (v["X_SPACING_DP"], v["CHIP_W_DP"], GAP_X_MIN))
    if v["Y_SPACING_DP"] < v["CHIP_H_DP"] + GAP_Y_MIN:
        probs.append(u"纵向间距 %.0f < 卡片高 %.0f + %.0f（上下两层会叠）"
                     % (v["Y_SPACING_DP"], v["CHIP_H_DP"], GAP_Y_MIN))
    need_option = (v["CHIP_H_DP"] + v["OPTION_GAP_DP"]
                   + v["OPTIONS_MAX"] * v["OPTION_H_DP"] + GAP_OPTION_MIN)
    if v["Y_SPACING_DP"] < need_option:
        probs.append(u"纵向间距 %.0f < 卡片高 + 选项小签（%d × %.0f）+ %.0f = %.0f"
                     % (v["Y_SPACING_DP"], int(v["OPTIONS_MAX"]), v["OPTION_H_DP"],
                        GAP_OPTION_MIN, need_option))
    return probs


def vertical_gap_px(v, density, scale, mix_units):
    """相邻两层卡片之间的净空（px）。正 = 有缝，负 = 重叠。

    mix_units=True 复刻**旧 bug**的算法：层距是 px（乘 scale），卡片高是 dp（乘 density，不乘 scale）；
    mix_units=False 是**新**算法：间距与卡片都先乘 density，缩放整层一起乘 —— 两者相减时 scale 约掉。
    """
    if mix_units:
        pitch = v["Y_SPACING_DP"] * scale          # 旧：间距当 px 用
        card = v["CHIP_H_DP"] * density            # 旧：卡片当 dp 用（只在尺寸上乘密度）
    else:
        pitch = v["Y_SPACING_DP"] * density * scale
        card = v["CHIP_H_DP"] * density * scale
    return pitch - card


def horizontal_gap_px(v, density, scale, mix_units):
    if mix_units:
        pitch = v["X_SPACING_DP"] * scale
        card = v["CHIP_W_DP"] * density
    else:
        pitch = v["X_SPACING_DP"] * density * scale
        card = v["CHIP_W_DP"] * density * scale
    return pitch - card


# ============================================================
#  源码级检查
# ============================================================
def scale_mixing(text):
    """找"坐标乘 scale"的地方。返回 (违规行, 白名单命中行)。graphicsLayer 内不算（那就是修法）。"""
    bad, allowed = [], []
    for i, ln in enumerate(text.split("\n"), 1):
        code = ln.split("//")[0]
        if not re.search(r"\*\s*scale\b|\bscale\s*\*", code):
            continue
        if "graphicsLayer" in code or re.search(r"scale[XY]\s*=\s*scale", code):
            continue
        if any(re.search(pat, code) for pat, _why in SCALE_WHITELIST):
            allowed.append((i, code.strip()))
            continue
        bad.append((i, code.strip()))
    return bad, allowed


def fn_body(text, name):
    """取 `fun <name>(` 的 { } 函数体（够用的括号匹配，字符串里的括号也跳过）。"""
    m = re.search(r"fun\s+%s\(" % re.escape(name), text)
    if not m:
        return u""
    i, depth, quote = m.end(), 1, None
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
    k = text.find("{", i)
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


def literal_size_args(text):
    """`.size(<数字>.dp, …)` —— 尺寸写字面量就是"卡片尺寸与间距常量脱钩"的开始。"""
    return re.findall(r"\.size\(\s*\d+(?:\.\d+)?f?\.dp\s*,", text)


# ============================================================
#  main
# ============================================================
def main():
    print("=" * 66)
    print(u"分支图布局闸门（dp/px 单位混用 · 间距不等式 · 反向验证）")
    print("=" * 66)

    text = read(SRC)
    code = blank_comments(text)          # 扫描只看代码：注释里引用旧 bug 的写法不算违规
    graph = fn_body(code, "TreeGraph")
    v = parse_consts(code)

    # ------------------------------------------------------------------
    # ① 常量
    # ------------------------------------------------------------------
    print(u"\n== ① 布局常量（dp） ==")
    for k in NEEDED:
        print(u"       %-14s %s" % (k, v.get(k, u"缺失")))
    check(u"7 个布局常量全部解析到", all(k in v for k in NEEDED),
          u"缺 %s" % [k for k in NEEDED if k not in v])

    # ------------------------------------------------------------------
    # ② 间距不等式
    # ------------------------------------------------------------------
    print(u"\n== ② 间距 vs 卡片尺寸 ==")
    probs = spacing_problems(v)
    check(u"横向：X_SPACING_DP %.0f ≥ 卡片宽 %.0f + %g"
          % (v.get("X_SPACING_DP", 0), v.get("CHIP_W_DP", 0), GAP_X_MIN),
          v.get("X_SPACING_DP", 0) >= v.get("CHIP_W_DP", 0) + GAP_X_MIN)
    check(u"纵向：Y_SPACING_DP %.0f ≥ 卡片高 %.0f + %g"
          % (v.get("Y_SPACING_DP", 0), v.get("CHIP_H_DP", 0), GAP_Y_MIN),
          v.get("Y_SPACING_DP", 0) >= v.get("CHIP_H_DP", 0) + GAP_Y_MIN)
    check(u"纵向还要盖住卡片下方的 %d 个选项小签（+ %g 余量）"
          % (int(v.get("OPTIONS_MAX", 0)), GAP_OPTION_MIN),
          v.get("Y_SPACING_DP", 0) >= (v.get("CHIP_H_DP", 0) + v.get("OPTION_GAP_DP", 0)
                                      + v.get("OPTIONS_MAX", 0) * v.get("OPTION_H_DP", 0)
                                      + GAP_OPTION_MIN))
    check(u"三个不等式一起过（spacing_problems 为空）", not probs, u"；".join(probs))

    # ---- 升级后"树被压扁"：fit 缩放必须有下限，否则宽树会被宽度压成一条扁带 ----
    check(u"有 FIT_MIN_SCALE 常量（自动铺满的最小缩放）",
          "FIT_MIN_SCALE" in code, "缺常量")
    check(u"fit 缩放夹到 FIT_MIN_SCALE（不是 MIN_SCALE）",
          "coerceIn(FIT_MIN_SCALE, FIT_MAX_SCALE)" in code, "夹取区间不对")
    check(u"合上之后卡片高度仍 >= 30dp（52dp × 0.7 = 36dp，别缩到看不见字）",
          v.get("CHIP_H_DP", 0) * 0.7 >= 30, str(v.get("CHIP_H_DP")))
    check(u"手动缩放仍可到 MIN_SCALE（用户主动缩放不受限）",
          "coerceIn(MIN_SCALE, MAX_SCALE)" in code, "手动缩放区间被改坏")
    check(u"内容比视口高时贴顶（不再按居中算出框外）",
          "if (contentH > viewH) 0f else" in code, "缺贴顶分支")

    # ---- 宽树别变成"一条单线"：装不下时初始视野要对准当前节点 ----
    check(u"宽树：panX 对准当前节点（isCurrent）而不是树左边缘",
          "it.isCurrent" in code and "viewW / 2f - leafCxPx * fitScale" in code,
          "缺对准当前节点的分支")
    check(u"对准后仍夹在可视范围内（不露空白边）",
          "coerceIn(viewW - contentW, 0f)" in code, "缺夹取")
    check(u"装得下时仍然居中（不退化）",
          "if (contentW <= viewW)" in code, "缺居中分支")

    # ------------------------------------------------------------------
    # ③ 纯函数复算：旧算法在真机上必然重叠，新算法与密度无关
    # ------------------------------------------------------------------
    print(u"\n== ③ 纯函数复算（scale 按初始 0.8） ==")
    old_275 = vertical_gap_px({"Y_SPACING_DP": 96.0, "CHIP_H_DP": 42.0}, 2.75, 0.8, True)
    old_h_275 = horizontal_gap_px({"X_SPACING_DP": 150.0, "CHIP_W_DP": 138.0}, 2.75, 0.8, True)
    print(u"       旧算法 @2.75 密度：纵向净空 %+.1fpx（卡片高 %.1fpx / 层距 %.1fpx）"
          % (old_275, 42.0 * 2.75, 96.0 * 0.8))
    print(u"       旧算法 @2.75 密度：横向净空 %+.1fpx（卡片宽 %.1fpx / 列距 %.1fpx）"
          % (old_h_275, 138.0 * 2.75, 150.0 * 0.8))
    check(u"复算确认旧 bug：2.75 密度下纵向重叠（净空 < 0）", old_275 < 0, u"%+.1f" % old_275)
    check(u"复算确认旧 bug：2.75 密度下横向重叠（净空 < 0）", old_h_275 < 0, u"%+.1f" % old_h_275)
    worst = None
    for d in DENSITIES:
        gap = vertical_gap_px(v, d, 0.8, False)
        need = GAP_Y_MIN * d * 0.8
        print(u"       新算法 @%.2f 密度：纵向净空 %+.1fpx（要求 ≥ %.1fpx）" % (d, gap, need))
        if worst is None or gap - need < worst[1]:
            worst = (d, gap - need)
    ok = all(vertical_gap_px(v, d, 0.8, False) >= GAP_Y_MIN * d * 0.8 for d in DENSITIES)
    check(u"新算法在 %s 密度下纵向净空都 ≥ %gdp（与密度无关）"
          % (u"/".join(u"%g" % d for d in DENSITIES), GAP_Y_MIN), ok,
          u"最差余量 %.1fpx @ %g" % (worst[1], worst[0]))
    okx = all(horizontal_gap_px(v, d, 0.8, False) >= GAP_X_MIN * d * 0.8 for d in DENSITIES)
    check(u"新算法在同样密度下横向净空都 ≥ %gdp" % GAP_X_MIN, okx)

    # ------------------------------------------------------------------
    # ④ 单位混用：坐标不许再乘 scale
    # ------------------------------------------------------------------
    print(u"\n== ④ 单位混用（坐标乘 scale = 老 bug） ==")
    bad, allowed = scale_mixing(code)
    print(u"       白名单命中 %d 处：%s" % (len(allowed), [a[1] for a in allowed]))
    check(u"源码里没有'坐标乘 scale'（只允许 graphicsLayer 内）", not bad,
          u"、".join(u"%d:%s" % (i, s) for i, s in bad[:4]))
    check(u"白名单只有 1 条且都写了理由",
          len(SCALE_WHITELIST) == 1 and all(len(w.strip()) >= 10 for _p, w in SCALE_WHITELIST))
    check(u"白名单命中 ≤ 1 处（现在 %d 处）" % len(allowed), len(allowed) <= 1)
    check(u"唯一那处就是手势缩放 scale * zoom",
          all(u"zoom" in s for _i, s in allowed),
          u"%s" % [s for _i, s in allowed])

    # ------------------------------------------------------------------
    # ⑤ 结构：一层 graphicsLayer + 左上角原点 + clipToBounds
    # ------------------------------------------------------------------
    print(u"\n== ⑤ 变换结构 ==")
    check(u"存在一层 graphicsLayer 统一缩放", "graphicsLayer" in graph)
    check(u"graphicsLayer 里 scaleX/scaleY 都来自同一个 scale",
          re.search(r"scaleX\s*=\s*scale\b", graph) is not None and
          re.search(r"scaleY\s*=\s*scale\b", graph) is not None)
    check(u"transformOrigin = (0,0)（以左上角为原点，缩放才与平移一致）",
          re.search(r"transformOrigin\s*=\s*TransformOrigin\(\s*0f\s*,\s*0f\s*\)", graph) is not None)
    check(u"画布 clipToBounds()（节点/连线不许画到框外）", "clipToBounds()" in graph)
    check(u"dp→px 各只算一次（X_SPACING_DP / Y_SPACING_DP）",
          graph.count("X_SPACING_DP.dp.toPx()") == 1 and graph.count("Y_SPACING_DP.dp.toPx()") == 1,
          u"x=%d y=%d" % (graph.count("X_SPACING_DP.dp.toPx()"),
                          graph.count("Y_SPACING_DP.dp.toPx()")))
    check(u"节点坐标用 px 常量算（n.x * xSpacingPx / n.y * ySpacingPx）",
          re.search(r"x\s*\*\s*xSpacingPx", graph) is not None and
          re.search(r"y\s*\*\s*ySpacingPx", graph) is not None)

    # ------------------------------------------------------------------
    # ⑥ 尺寸来源 + 文字排布
    # ------------------------------------------------------------------
    print(u"\n== ⑥ 尺寸与文字 ==")
    check(u"卡片尺寸来自常量：.size(CHIP_W_DP.dp, CHIP_H_DP.dp)",
          re.search(r"\.size\(\s*CHIP_W_DP\.dp\s*,\s*CHIP_H_DP\.dp\s*\)", graph) is not None)
    lit = literal_size_args(graph)
    check(u"没有把尺寸写成字面量（.size(138.dp, …) 这类）", not lit, u"%s" % lit[:3])
    check(u"文案不再 take(16) 硬截", "take(16)" not in code)
    check(u"卡片文字 maxLines = 2 + 省略号",
          re.search(r"maxLines\s*=\s*2", graph) is not None and "TextOverflow.Ellipsis" in graph)
    check(u"文字列拿到剩余宽度（weight(1f)），不被图标框挤掉",
          re.search(r"Column\(Modifier\.weight\(1f\)\)", graph) is not None)
    check(u"首帧：横向居中 + 纵向放不下就贴顶（contentW/contentH 同一次算出）",
          re.search(r"\(viewW - contentW\)\s*/\s*2f", graph) is not None and
          re.search(r"if \(contentH > viewH\) 0f else \(viewH - contentH\) / 2f", graph) is not None and
          "mutableStateOf(0.8f)" in graph)

    # ------------------------------------------------------------------
    # ⑦ 反向验证：把参数改坏，闸门必须红
    # ------------------------------------------------------------------
    print(u"\n== ⑦ 反向验证（改坏参数，闸门必须红） ==")
    broken = dict(v)
    broken["Y_SPACING_DP"] = 80.0
    check(u"把 ySpacing 改成 80 → spacing_problems 报红", bool(spacing_problems(broken)),
          u"%s" % spacing_problems(broken)[:1])
    check(u"…而且报的是纵向那条（不是靠别的不等式兜住）",
          any(u"纵向间距" in p for p in spacing_problems(broken)),
          u"%s" % spacing_problems(broken))
    broken2 = dict(v)
    broken2["X_SPACING_DP"] = 150.0
    check(u"把 xSpacing 改成 150（< 150+16）→ 报红", bool(spacing_problems(broken2)),
          u"%s" % spacing_problems(broken2)[:1])
    broken3 = dict(v)
    broken3["CHIP_H_DP"] = 120.0
    check(u"把卡片高改成 120（间距没跟着变）→ 报红", bool(spacing_problems(broken3)))
    mixed = code.replace(
        "val cx = cxOf(n.x)",
        "val cx = n.x * xSpacingPx * scale + panX")
    check(u"把'坐标乘 scale'塞回源码 → 单位混用检查报红",
          bool(scale_mixing(mixed)[0]) and mixed != code,
          u"%s" % scale_mixing(mixed)[0][:1])
    check(u"反过来：当前源码是干净的（同一函数判绿）", not scale_mixing(code)[0])

    print("\n" + "=" * 66)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("BRANCH_GRAPH_LAYOUT_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
