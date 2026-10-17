# -*- coding: utf-8 -*-
"""浅色字守护测试：把"颜色看起来费劲"这件事变成一条会红的断言。

为什么需要
----------
用户反复反馈"颜色看起来费劲"。`tools/audit_contrast.py` 早就把 `design/tokens.json`
里的令牌算成了矩阵，`text_sub` 也满足 AA —— 但**令牌绿不等于界面绿**：
网页里散着 `color:#8a93a3`、`color:rgba(255,255,255,.45)`，安卓里散着
`theme.text.copy(alpha = 0.6f)`，这些都不走令牌，令牌表一格都看不见它们。
更糟的是它们分布在 `web/js/screens/*.js` 与 `web/screens/*.html` 里 ——
`audit_contrast` 原来的漂移扫描只扫 `web/*.html`（不递归）且不扫 `.js`，等于漏掉八成。

所以这条测试守三件事：
  ① **声明层**：文字色里不许再出现"半透明浅色"（rgba alpha < 0.6）与"已知暗底次要灰"
     （`#888/#777/#999` 这一族）。安卓端不许 `copy(alpha = 0.[0-6])` 出现在 `color =`/`tint =` 语境。
  ② **效果层**：每条文字色对**它自己的背景**都要 ≥4.5（占位符 ≥3.0），暗/浅两套主题各算一遍。
  ③ **判定器本身**：拿已知违规样本喂给判定函数，它必须判 FAIL ——
     否则以后谁把阈值改成 0.05，"全绿"就成了假绿。

口径（很窄，故意的）
--------------------
  允许保留（不是正文）：
    · 禁用态      —— `:disabled` / `disable` 出现在选择器或行内；
    · 占位符      —— `::placeholder`，按 3:1 卡，不按 4.5；
    · 装饰线/边框 —— `border`/`box-shadow`/`outline` 本来就不在文字属性表里，扫不到；
    · 水印        —— 只有 `#dickMark` 那一个（`aria-hidden` + 源码里带"水印"注释），
                     它的作用是"截图可取证"，本来就该看不见；
    · 开发者控制台 —— `console.log` 的 `%c` 样式，不是界面文字。
  这几类必须**在白名单里点名**，白名单总数还钉了上限（≤3），防止它慢慢变成垃圾桶。

跑法：python tests/test_no_dim_text.py
"""
import io
import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import audit_contrast as AC          # noqa: E402  （要先把 tools 放进 sys.path）

STRINGS = os.path.join(ROOT, "design", "tokens.json")

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


def main():
    print("=" * 66)
    print(u"浅色字守护（半透明浅色 / 已知暗灰 / 文字色 vs 背景 ≥4.5）")
    print("=" * 66)

    data = json.loads(read(STRINGS))
    pals = AC.palettes_of(data)

    # ---------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌---------------------------------
    # ① 判定器自检：先证明"该红的会红"，后面才有意义
    # ------------------------------------------------------------------
    print(u"\n== ① 判定器自检（判定函数不许被改成永远 PASS） ==")
    check(u"rgba(255,255,255,0.30) 判为浅色字",
          AC.dim_reason("rgba(255,255,255,0.30)") is not None)
    check(u"rgba(255,255,255,0.59) 仍判为浅色字（阈值 0.6 是开区间）",
          AC.dim_reason("rgba(255,255,255,0.59)") is not None)
    check(u"rgba(255,255,255,0.60) 不算浅色字",
          AC.dim_reason("rgba(255,255,255,0.60)") is None)
    check(u"#888 判为已知暗灰", AC.dim_reason("#888") is not None)
    check(u"#777 / #999 / #9aa1ab 都判为已知暗灰",
          all(AC.dim_reason(v) is not None for v in ("#777", "#999", "#9aa1ab")))
    check(u"#e5e7eb / #fff 不算暗灰（它们是正文/高对比）",
          AC.dim_reason("#e5e7eb") is None and AC.dim_reason("#fff") is None)
    check(u"已存在的令牌变量不算浅色字",
          AC.dim_reason("var(--text-sub)", pals["dark"]) is None)
    check(u"未定义令牌的兜底值照样判（--nope 不存在 → 看 #777）",
          AC.dim_reason("var(--nope,#777)") is not None)
    check(u"对比度公式对已知样本正确（#fff on #000 = 21）",
          abs(AC.contrast("#ffffff", "#000000") - 21.0) < 0.01)
    check(u"对比度公式对已知样本正确（#0b1220 on #60a5fa ≈ 7.36）",
          abs(AC.contrast("#0b1220", "#60a5fa") - 7.36) < 0.02)

    # ------------------------------------------------------------------
    # ② web：覆盖范围先兜住（防止扫描范围被改空）
    # ------------------------------------------------------------------
    units = AC.web_text_units()
    files = sorted({u["rel"] for u in units})
    print(u"\n== ② 网页扫描覆盖 ==")
    check(u"扫到 ≥20 个文件（现在 %d 个）" % len(files), len(files) >= 20,
          u"%s" % files[:5])
    check(u"扫到 ≥200 条文字色声明（现在 %d 条）" % len(units), len(units) >= 200)
    check(u"覆盖 web/js/**（脚本里 cssText 的 color: 也算）",
          any(r.startswith("web/js/") for r in files))
    check(u"覆盖 web/screens/**（片段里的行内 style 也算）",
          any(r.startswith("web/screens/") for r in files))
    check(u"覆盖 web/styles/**", any(r.startswith("web/styles/") for r in files))

    # ------------------------------------------------------------------
    # ③ ④ web 声明层：半透明浅色 / 已知暗灰
    # ------------------------------------------------------------------
    viol, white = AC.check_no_dim_text(data)
    web_viol = [v for v in viol if v[0].startswith("web/")]
    kt_viol = [v for v in viol if not v[0].startswith("web/")]
    alpha_viol = [v for v in web_viol if u"rgba" in v[2]]
    hex_viol = [v for v in web_viol if u"暗灰" in v[2]]

    print(u"\n== ③ 网页：文字色里不许有 alpha<0.6 的 rgba ==")
    check(u"rgba 半透明浅色字 0 处", not alpha_viol,
          u"、".join(u"%s:%d" % (r, l) for r, l, _ in alpha_viol[:8]))
    print(u"\n== ④ 网页：文字色里不许有已知暗灰 hex ==")
    check(u"已知暗灰文字色 0 处", not hex_viol,
          u"、".join(u"%s:%d" % (r, l) for r, l, _ in hex_viol[:8]))

    # ------------------------------------------------------------------
    # ⑤ 安卓：copy(alpha = 0.[0-6]) / Color(0x…) 暗灰
    # ------------------------------------------------------------------
    print(u"\n== ⑤ 安卓：color=/tint= 不许被 copy(alpha = 0.[0-6]) 压暗 ==")
    kt_units = AC.android_text_units()
    kt_alpha = [u for u in kt_units if u["prop"] == "copy(alpha)" and u["alpha"] <= AC.DIM_ALPHA_KT + 1e-9]
    check(u"copy(alpha = 0.[0-6]) 文字色 0 处", not kt_alpha,
          u"、".join(u"%s:%d" % (u["rel"], u["line"]) for u in kt_alpha[:8]))
    check(u"copy(alpha…) 0.x 违规总数为 0", not kt_viol,
          u"、".join(u"%s:%d %s" % (r, l, w) for r, l, w in kt_viol[:6]))
    kt_lit = [u for u in kt_units if u["prop"] == "Color(0x)"]
    kt_dim_lit = []
    for u in kt_lit:
        hsl = AC.hex_to_rgb(u["literal"])
        # 明度极低且接近中性灰的字面量 = 暗底上不可读的灰
        if max(hsl) - min(hsl) <= 24 and AC.luminance(u["literal"]) < 0.22:
            kt_dim_lit.append(u)
    check(u"color=/tint= 里没有暗灰 Color(0x…) 字面量（%d 条被检查）" % len(kt_lit),
          not kt_dim_lit,
          u"、".join(u"%s:%d" % (u["rel"], u["line"]) for u in kt_dim_lit[:6]))

    # ------------------------------------------------------------------
    # ⑥ ⑦ 效果层：文字色 vs 其背景
    # ------------------------------------------------------------------
    pairs = AC.text_pairs(data)
    judged = [p for p in pairs if p["ratio"] is not None]
    bad = [p for p in judged if p["ratio"] < p["need"]]
    print(u"\n== ⑥ 所有文字色 vs 其背景 ≥4.5 ==")
    check(u"检查了 ≥380 对（现在 %d 对，暗/浅各算一遍）" % len(judged), len(judged) >= 380)
    check(u"低于门槛的 0 对", not bad,
          u"；".join(u"%s:%d [%s] %s %.2f<%g" % (p["rel"], p["line"], p["theme"], p["value"],
                                                 p["ratio"], p["need"]) for p in bad[:6]))
    worst = min(judged, key=lambda p: p["ratio"])
    print(u"       最差：%.2f  %s:%d [%s] %s" % (worst["ratio"], worst["rel"], worst["line"],
                                                worst["theme"], worst["value"]))
    check(u"最差比值 ≥4.5", worst["ratio"] >= 4.5, u"%.2f" % worst["ratio"])
    check(u"两套主题都被算过（dark 与 light 都有样本）",
          {p["theme"] for p in judged} == {"dark", "light"})

    print(u"\n== ⑦ 占位符单独按 3:1（不占正文的 4.5） ==")
    holders = [p for p in judged if p["need"] < 4.5]
    for p in holders:
        check(u"%s:%d 占位符 ≥3.0（%.2f）" % (p["rel"], p["line"], p["ratio"]),
              p["ratio"] >= 3.0)

    # ------------------------------------------------------------------
    # ⑧ 白名单：只许三类，且总数有上限
    # ------------------------------------------------------------------
    print(u"\n== ⑧ 白名单（功能态，不是正文） ==")
    allowed_reasons = {"disabled", "::placeholder", "watermark", "console"}
    alien = [w for w in white if w[3] not in allowed_reasons]
    check(u"白名单理由都在 disabled/::placeholder/watermark/console 之内",
          not alien, u"%s" % alien[:4])
    check(u"白名单总数 ≤3（现在 %d 处）" % len(white), len(white) <= 3,
          u"%s" % [(w[0], w[1], w[3]) for w in white])
    for rel, line, why, reason in white:
        print(u"       · %s:%d  %s（%s）" % (rel, line, why, reason))

    # ------------------------------------------------------------------
    # ⑨ 直接调 tools/audit_contrast.py：退出码必须 0
    # ------------------------------------------------------------------
    print(u"\n== ⑨ 调 tools/audit_contrast.py（不达标就 FAIL） ==")
    proc = subprocess.run([sys.executable, "-X", "utf8",
                           os.path.join(TOOLS, "audit_contrast.py"), "--quiet"],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = u"\n".join((proc.stdout or "").strip().split("\n")[-4:])
    check(u"audit_contrast.py 退出码 0", proc.returncode == 0,
          u"退出码 %s\n%s\n%s" % (proc.returncode, tail, (proc.stderr or "")[-400:]))
    check(u"audit_contrast.py 自己报 '无浅色字声明'",
          u"无浅色字声明" in (proc.stdout or ""), tail)

    print("\n" + "=" * 66)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("NO_DIM_TEXT_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
