# -*- coding: utf-8 -*-
"""audit_contrast.py —— 配色量化审计（本阶段的验收工具）。

两件事：
  1) **对比度矩阵**：读 `design/tokens.json`，对必需组合算 WCAG 2.1 对比度并判定。
     正文类 <4.5 判 FAIL；图标/大字/控件边界 <3.0 判 FAIL；装饰性（text_dim）只 WARN。
  2) **漂移扫描**：扫 `web/*.html`／`web/*.css`／`DICK-Android/.../app/*.kt` 里的硬编码颜色
     （`#rrggbb`、`rgba(`、`Color(0xFF…)`），列出"不在令牌文件里"的出现位置（文件:行号 + 颜色）。
     本轮不要求清零 —— 它是后续逐屏收敛的清单；但数量与位置要能看得到，不然"收敛"永远停在口头。

判定口径（Why 4.5 / 3.0）
------------------------
WCAG 2.1：正文（<18.66px 且非粗体）要 4.5:1；大字（≥18.66px 或 ≥14pt 粗体）与非文本的
控件/图形边界要 3:1。所以令牌里 `text_sub` 这种"次要但仍是正文"的角色按 4.5 卡，
`border` 按 3.0 卡，`text_dim` 明确定位成装饰性，只 WARN —— 但**不允许**拿它排正文。

用法：
    python tools/audit_contrast.py            # 矩阵 + 漂移清单
    python tools/audit_contrast.py --quiet    # 只打印结论与漂移数量
    python tools/audit_contrast.py --top 20   # 漂移清单显示前 N 条（默认 15）
退出码：必需组合缺失、或任一判定为 FAIL → 1；否则 0（WARN 不影响退出码）。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "design", "tokens.json")

# 硬编码颜色扫描范围（相对仓库根<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌）：(目录, 后缀, 是否递归)
SCAN_GLOBS = [
    ("web", ".html", False),
    # .css 要递归：2026-11 阶段1 把 index.html 的 <style> 拆到了 web/styles/*.css，
    # 不递归的话那 400 多处硬编码颜色就从扫描范围里消失了（等于自己给自己放水）。
    ("web", ".css", True),
    (os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick"), ".kt", True),
]
# 生成物：它们本来就该满是令牌色，扫它们等于自己跟自己比
SKIP_BASENAMES = {"theme.css", "Tokens.kt", "IconNames.kt", "icons.js", "i18n.js"}

HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")


# ============================================================
#  WCAG 2.1 相对亮度与对比度
# ============================================================
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_rgb(h):
    h = h.strip().lstrip(u"#")
    if len(h) == 3:
        h = u"".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(h):
    r, g, b = hex_to_rgb(h)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg, bg):
    """WCAG 对比度（1..21）。两边顺序无关。"""
    a, b = luminance(fg), luminance(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


# ============================================================
#  矩阵
# ============================================================
KIND_LABEL = {"body": u"正文", "ui": u"图标/边界", "decor": u"仅装饰"}


def print_matrix(pal, theme_name, data):
    """打印一套配色的对比度矩阵。返回 (fail, warn, missing) 三份清单。"""
    conf = data.get("contrast") or {}
    pairs = conf.get("pairs") or []
    mins = conf.get("min") or {}
    fail, warn, missing, rows = [], [], [], []
    for p in pairs:
        fg, bg = p.get("fg"), p.get("bg")
        kind = p.get("kind", "body")
        need = float(mins.get(kind, 4.5))
        if pal.get(fg) is None or pal.get(bg) is None:
            missing.append(u"%s/%s" % (fg, bg))
            rows.append((u"%s/%s" % (fg, bg), u"-", u"-", None, need, kind, u"MISSING"))
            continue
        r = contrast(pal[fg], pal[bg])
        required = bool(p.get("required", True))
        if not required:
            # 参考组合：只打印比值，不参与判定（例如 text 压在 accent 上 —— 本项目不允许这么用，
            # 压 accent 的文字一律走 accent_text）
            verdict = u"参考"
        elif kind == "decor":
            verdict = u"OK" if r >= need else u"WARN"
            if verdict == u"WARN":
                warn.append((u"%s/%s" % (fg, bg), r, need))
        else:
            verdict = u"OK" if r >= need else u"FAIL"
            if verdict == u"FAIL":
                fail.append((u"%s/%s" % (fg, bg), r, need))
        rows.append((u"%s/%s" % (fg, bg), pal[fg], pal[bg], r, need, kind, verdict))
    print(u"  %-22s %-9s %-9s %6s %6s %s" % (u"组合", u"前景", u"背景", u"比值", u"要求", u"判定"))
    for name, fg, bg, r, need, kind, verdict in rows:
        ratio = u"-" if r is None else u"%.2f" % r
        print(u"  %-22s %-9s %-9s %6s %6s %s %s" % (
            name, fg or u"-", bg or u"-", ratio, u"≥%g" % need,
            u"·" + KIND_LABEL.get(kind, kind), verdict))
    return fail, warn, missing


def load_tokens():
    with io.open(SRC, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
#  漂移扫描
# ============================================================
RE_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RE_RGBA = re.compile(r"rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+")
RE_COMPOSE = re.compile(r"Color\(\s*0x([0-9a-fA-F]{6,8})\s*\)")


def _norm_hex(h):
    h = h.lstrip(u"#").lower()
    if len(h) == 3:
        h = u"".join(ch * 2 for ch in h)
    if len(h) == 8:          # #rrggbbaa → 丢掉 alpha（漂移清单只关心色相/明度）
        h = h[:6]
    return u"#" + h


def token_color_set(data):
    """令牌文件里出现过的全部颜色（暗/浅/OLED + 强调色的暗/浅版）。"""
    out = set()
    for pal in (data.get("colors") or {}).values():
        if isinstance(pal, dict):
            for v in pal.values():
                if isinstance(v, str) and HEX6.match(v):
                    out.add(_norm_hex(v))
    for acc in data.get("accents") or []:
        for k in ("dark", "light"):
            if isinstance(acc.get(k), str):
                out.add(_norm_hex(acc[k]))
    for v in (data.get("oled") or {}).values():
        if isinstance(v, str) and HEX6.match(v):
            out.add(_norm_hex(v))
    return out


def scan_files():
    out = []
    for sub, ext, recursive in SCAN_GLOBS:
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        if recursive:
            names = []
            for base, _dirs, files in os.walk(d):
                for fn in files:
                    names.append(os.path.join(base, fn))
        else:
            names = [os.path.join(d, fn) for fn in os.listdir(d)]
        for path in sorted(names):
            fn = os.path.basename(path)
            if not fn.endswith(ext) or fn in SKIP_BASENAMES:
                continue
            out.append(path)
    return out


def scan_drift(data):
    """返回 (total, 不在令牌里的命中列表[(相对路径, 行号, 颜色)])。"""
    known = token_color_set(data)
    total = 0
    hits = []
    for path in scan_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, u"/")
        try:
            with io.open(path, encoding="utf-8") as f:
                lines = f.read().split(u"\n")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, 1):
            found = []
            for m in RE_HEX.finditer(line):
                found.append(_norm_hex(m.group(0)))
            for m in RE_RGBA.finditer(line):
                found.append(m.group(0).replace(u" ", u""))
            for m in RE_COMPOSE.finditer(line):
                found.append(_norm_hex(u"#" + m.group(1)))
            if not found:
                continue
            total += len(found)
            for col in found:
                if col not in known:
                    hits.append((rel, i, col))
    return total, hits


# ============================================================
#  main
# ============================================================
def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    quiet = "--quiet" in argv
    top = 15
    if "--top" in argv:
        try:
            top = int(argv[argv.index("--top") + 1])
        except (IndexError, ValueError):
            pass
    data = load_tokens()
    pals = {"dark": data["colors"]["dark"], "light": data["colors"]["light"]}

    n_fail = n_warn = n_missing = 0
    for name in ("dark", "light"):
        if not quiet:
            print(u"== 对比度矩阵 · %s ==" % name)
        fail, warn, missing = print_matrix(pals[name], name, data)
        n_fail += len(fail)
        n_warn += len(warn)
        n_missing += len(missing)
        if fail and quiet:
            for pair, r, need in fail:
                print(u"  [FAIL] %s %s = %.2f < %g" % (name, pair, r, need))
        if missing:
            for pair in missing:
                print(u"  [缺失] %s %s 组合引用了不存在的角色" % (name, pair))

    print(u"")
    print(u"== 汇总 ==")
    print(u"  判定：FAIL %d ／ WARN %d ／ 必需组合缺失 %d" % (n_fail, n_warn, n_missing))

    total, hits = scan_drift(data)
    by_file = {}
    for rel, line, col in hits:
        by_file.setdefault(rel, []).append((line, col))
    print(u"  漂移：硬编码颜色出现 %d 处，其中 **不在令牌里 %d 处**（分布在 %d 个文件）"
          % (total, len(hits), len(by_file)))
    if not quiet and hits:
        print(u"  -- 不在令牌里的出现位置（前 %d 条，后续逐屏收敛用）--" % top)
        shown = 0
        for rel in sorted(by_file, key=lambda k: -len(by_file[k])):
            for line, col in by_file[rel]:
                if shown >= top:
                    break
                print(u"    %s:%d  %s" % (rel, line, col))
                shown += 1
            if shown >= top:
                break
        print(u"  -- 按文件统计 --")
        for rel in sorted(by_file, key=lambda k: -len(by_file[k])):
            print(u"    %-58s %d" % (rel, len(by_file[rel])))

    bad = n_fail + n_missing
    if bad:
        print(u"[FAIL] 配置不达标（%d 项）—— 调 design/tokens.json 后重跑，别改阈值。" % bad)
        return 1
    print(u"[ok] 必需组合全部达标（%d 项 FAIL ／ %d 项 WARN 仅装饰）" % (n_fail, n_warn))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
