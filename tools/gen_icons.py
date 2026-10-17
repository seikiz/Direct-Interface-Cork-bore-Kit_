# -*- coding: utf-8 -*-
"""gen_icons.py —— 图标唯一真相 `icons/icons.json` → 两端产物。

为什么要有它
------------
原来图标是 `web/index.html` 里一张 `ICONS = {emoji → 内联 SVG}` 字典（约 120 条、6600 字符），
安卓那份由 `tools/gen_android_icons.py` 从同一张字典生成 108 个 VectorDrawable。手写路径的
问题：想换一个图标就得自己画/抄路径，风格也全凭手感。

现在换成**谷歌 Material Symbols**：唯一真相是 `icons/icons.json`（emoji → 图标名），
两边都用同一份字体渲染 —— 网页靠 CSS 的连字（ligature），安卓靠 Compose 的自定义 FontFamily。
用户定的风格口径：**少边拓扑**（细线、几何），即 Material Symbols Outlined，
`FILL 0 / wght 350 / GRAD 0 / opsz 24`。

产物（都别手改）：
  · `web/icons.js`                                     emoji → 名字（网页端 iconify* 用）
  · `DICK-Android/.../com/dick/app/IconNames.kt`        emoji/具名 → 名字（安卓端用）

作用域（json 顶层 `scoped` 段）：
  有些 emoji **只**想在某个页面的某块区域里换成图标（例如 gothic_frame.html 那五个预览按钮）。
  放进全局 `icons` 表就会连卡片/世界卡正文里同样的 emoji 一起换掉，所以单开一段：
  只输出到 `web/icons.js` 的 `window.DICK_ICONS_SCOPED`（消费方 web/icon_scope.js），
  **不进** IconNames.kt —— 安卓端没有「作用域」的需求，不该被这份表污染。

用法：
    python tools/gen_icons.py            # 重新生成两份产物
    python tools/gen_icons.py --check    # 校验 json + 产物是否最新（CI / 测试用）
    python tools/gen_icons.py --report   # 条数、体积、字体覆盖率
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 让 `import seiki_mark` 找得到（水印工具在仓库根；脚本从 tools/ 里跑，sys.path[0] 是 tools/
# —— 不插这一行，_mark() 里的 import 会静默失败、产物就没水印；tools/gen_i18n.py 踩过同一个坑）。
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SRC = os.path.join(ROOT, "icons", "icons.json")
WEB_OUT = os.path.join(ROOT, "web", "icons.js")
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "IconNames.kt")
WEB_FONT = os.path.join(ROOT, "web", "fonts", "MaterialSymbolsOutlined.woff2")
AND_FONT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "font",
                        "material_symbols_outlined.ttf")
LICENSE = os.path.join(ROOT, "web", "fonts", "LICENSE")
INDEX = os.path.join(ROOT, "web", "index.html")

HEADER_JS = (u"// ⚠ 生成物：由 tools/gen_icons.py 从 icons/icons.json 生成，别手改。\n"
             u"//   换图标：改 icons/icons.json（emoji → Material Symbols 名字），再跑一次生成器。\n")
HEADER_KT = (u"// ⚠ 生成物：由 tools/gen_icons.py 从 icons/icons.json 生成，别手改。\n"
             u"//   换图标：改 icons/icons.json（emoji → Material Symbols 名字），再跑一次生成器。\n"
             u"//   字体：res/font/material_symbols_outlined.ttf（Material Symbols Outlined，Apache-2.0）\n")

ZW = re.compile(u"[\u200b-\u200f\u2060\ufeff\u00ad]+")


# ---------------- 生成物里的水印（与 tools/ge<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌n_parity.py 同一套做法） ----------------
def _clean(text):
    """剥掉水印（可见的 `<seiki>` 前缀 + 零宽负载）后再比内容。"""
    return ZW.sub(u"", text.replace(u"<seiki>", u""))


def _mark(path, text):
    try:
        import seiki_mark as SM
        styles = SM.COMMENT.get(os.path.splitext(path)[1].lower())
        if styles:
            text, _st, _why = SM.embed(text, None, styles, fmt="native")
    except Exception:
        pass
    return text


def _read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


# ---------------- 校验 ----------------
def ligature_names(path):
    """从字体里抽出所有连字名（键=首字形；underscore 还原成 _）。"""
    from fontTools.ttLib import TTFont
    f = TTFont(path, lazy=True)
    try:
        gsub = f["GSUB"].table
        out = set()
        for fr in gsub.FeatureList.FeatureRecord:
            if fr.FeatureTag not in ("rlig", "liga"):
                continue
            for i in fr.Feature.LookupListIndex:
                for st in gsub.LookupList.Lookup[i].SubTable:
                    real = getattr(st, "ExtSubTable", st)
                    for first, arr in (getattr(real, "ligatures", None) or {}).items():
                        for l in arr:
                            out.add((first + "".join(l.Component)).replace("underscore", "_"))
        return out
    finally:
        f.close()


def scoped_tables(data):
    """只留真作用域：`scoped` 段里以 _ 开头的是注释（_note 之类），不是作用域名。

    返回 {作用域名: {emoji: 图标名}}，顺序跟 json 一致。
    """
    out = {}
    for scope, table in (data.get("scoped") or {}).items():
        if str(scope).startswith("_") or not isinstance(table, dict):
            continue
        pairs = {}
        for k, v in table.items():
            if str(k).startswith("_"):        # 作用域内部也可以写 _note
                continue
            pairs[k] = v
        out[scope] = pairs
    return out


def load(strict=True):
    """读唯一真相；返回 (data, problems)。"""
    problems = []
    if not os.path.isfile(SRC):
        return None, [u"icons/icons.json 不存在"]
    try:
        data = json.loads(_read(SRC))
    except Exception as e:
        return None, [u"icons/icons.json 不是合法 JSON：%s" % e]
    icons = data.get("icons") or {}
    named = data.get("named") or {}
    if not icons:
        problems.append(u"icons 段是空的")
    for label, table in ((u"icons", icons), (u"named", named)):
        for k, v in table.items():
            if not isinstance(v, dict) or not str(v.get("name") or "").strip():
                problems.append(u"%s[%s] 没有 name" % (label, k))
    # 作用域段：值就是图标名（纯字符串），不是 {"name": ...} 对象 —— 它没有 png 覆盖槽位
    for scope, pairs in scoped_tables(data).items():
        if not pairs:
            problems.append(u"scoped[%s] 是空的" % scope)
        for k, v in pairs.items():
            if isinstance(v, dict) or not str(v or "").strip():
                problems.append(u"scoped[%s][%s] 应该是纯图标名字符串" % (scope, k))
    return data, problems


def check_fonts(data, problems):
    """每个名字都要在**两份字体**里真的有连字（这是整套东西的地基）。

    作用域段（scoped）的图标名同样算在内：预览按钮上那几个 emoji 要是命中不了，
    就是空白/豆腐块，而且只有点进那个页面才发现。

    例外：读 **woff2** 需要 fontTools + brotli。brotli 是可选依赖（CI 与开发机都装了，
    见 requirements-test.txt），缺它时**只跳过 woff2 那份**并把话说出来 ——
    安卓 ttf 那份是同一套字形，仍然照查；不许静默放过。
    """
    names = sorted(set([v["name"] for v in data["icons"].values()] +
                       [v["name"] for v in data["named"].values()] +
                       [n for pairs in scoped_tables(data).values() for n in pairs.values()]))
    for label, path in ((u"网页 woff2", WEB_FONT), (u"安卓 ttf", AND_FONT)):
        if not os.path.isfile(path):
            problems.append(u"字体不在：%s" % os.path.relpath(path, ROOT))
            continue
        try:
            have = ligature_names(path)
        except Exception as e:
            if "brotli" in str(e).lower() or "brotli" in repr(e).lower():
                print(u"   [warn] 读不了 %s（缺 brotli）—— 只查了安卓 ttf 那份；"
                      u"CI 装了 brotli 会全查：pip install -r requirements-test.txt" % label)
                continue
            problems.append(u"%s 读不出连字表：%s" % (label, e))
            continue
        miss = [n for n in names if n not in have]
        if miss:
            problems.append(u"%s 里缺这些图标的连字：%s" % (label, u"、".join(miss)))
    return names


def _web_ui_text():
    """页面 + 已拆出去的样式（阶段1：`<style>` 搬到了 web/styles/）。

    "前端有没有 @font-face / 有没有引用随包字体"这类检查，2026-11 之后
    得看两边 —— 字体规则住进了 web/styles/components.css。
    """
    parts = []
    if os.path.isfile(INDEX):
        parts.append(_read(INDEX))
    sdir = os.path.join(ROOT, "web", "styles")
    if os.path.isdir(sdir):
        for fn in sorted(os.listdir(sdir)):
            if fn.endswith(".css"):
                parts.append(_read(os.path.join(sdir, fn)))
    return u"\n".join(parts)


def structural(data, problems):
    """前端那半边：不许再有内联 SVG 字典；字体与许可要在仓库里。"""
    if not os.path.isfile(LICENSE):
        problems.append(u"缺 web/fonts/LICENSE（Apache-2.0）")
    if os.path.isfile(INDEX):
        page = _read(INDEX)
        front = _web_ui_text()
        if "var ICONS = {" in page:
            problems.append(u"web/index.html 里还留着内联 SVG 字典（var ICONS = {）")
        if "icons.js" not in page:
            problems.append(u"web/index.html 没有引用 icons.js")
        if "@font-face" not in front:
            problems.append(u"前端没有 @font-face（字体没法加载；现在该在 web/styles/components.css）")


# ---------------- 产物 ----------------
def gen_web(data):
    o = [HEADER_JS, u"window.DICK_ICONS = {"]
    for e, v in data["icons"].items():
        o.append(u"  %s: { n: %s, p: %s }," % (json.dumps(e, ensure_ascii=False),
                                               json.dumps(v["name"]),
                                               json.dumps(v.get("png") or "")))
    o.append(u"};")
    o.append(u"window.DICK_ICON_NAMES = {")
    for k, v in data["named"].items():
        o.append(u"  %s: { n: %s, p: %s }," % (json.dumps(k), json.dumps(v["name"]),
                                               json.dumps(v.get("png") or "")))
    o.append(u"};")
    # 作用域图标：只在标了 data-icon-scope="<作用域名>" 的根内替换（消费者是 web/icon_scope.js）。
    # 刻意与上面的全局表分开：全局表里出现 💀/⛪ 会把卡片/世界卡正文里同样的 emoji 一起换掉。
    o.append(u"// 作用域图标：只在 [data-icon-scope=\"名字\"] 的根内替换，不进全局表（见 web/icon_scope.js）。")
    o.append(u"window.DICK_ICONS_SCOPED = {")
    for scope, pairs in scoped_tables(data).items():
        o.append(u"  %s: {" % json.dumps(scope))
        for e, name in pairs.items():
            o.append(u"    %s: { n: %s, p: \"\" }," % (json.dumps(e, ensure_ascii=False),
                                                      json.dumps(name)))
        o.append(u"  },")
    o.append(u"};")
    return u"\n".join(o) + u"\n"


def gen_kotlin(data):
    o = [HEADER_KT, u"package com.dick.app", u""]
    o.append(u"/** emoji（界面与正文里的键）→ Material Symbols 名字。 */")
    o.append(u"val ICON_NAME_BY_EMOJI: Map<String, String> = mapOf(")
    for e, v in data["icons"].items():
        o.append(u"    %s to %s," % (json.dumps(e, ensure_ascii=False), json.dumps(v["name"])))
    o.append(u")")
    o.append(u"")
    o.append(u"/** 具名图标（正文里写 [ic:名字]）→ Material Symbols 名字。 */")
    o.append(u"val ICON_NAME_BY_KEY: Map<String, String> = mapOf(")
    for k, v in data["named"].items():
        o.append(u"    %s to %s," % (json.dumps(k), json.dumps(v["name"])))
    o.append(u")")
    return u"\n".join(o) + u"\n"


def write_or_check(path, text, check):
    old = None
    if os.path.isfile(path):
        old = _read(path)
    if old is not None and _clean(old) == _clean(text):
        print(u"[ok] %s 已是最新" % os.path.relpath(path, ROOT))
        return True
    if check:
        print(u"[过期] %s 与 icons/icons.json 不一致 —— 跑 python tools/gen_icons.py 重新生成"
              % os.path.relpath(path, ROOT))
        return False
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_mark(path, text))
    print(u"[写] %s（%d 字符）" % (os.path.relpath(path, ROOT), len(text)))
    return True


def cmd_report(data, names):
    icons, named = data["icons"], data["named"]
    print(u"== icons/icons.json ==")
    print(u"  emoji %d ／ 具名 %d ／ 去重后图标名 %d" % (len(icons), len(named), len(names)))
    for scope, pairs in scoped_tables(data).items():
        print(u"  作用域 %s：%d 条（%s）"
              % (scope, len(pairs), u"、".join(u"%s→%s" % (k, v) for k, v in pairs.items())))
    shared = {}
    for e, v in icons.items():
        shared.setdefault(v["name"], []).append(e)
    multi = dict((k, v) for k, v in shared.items() if len(v) > 1)
    print(u"  多个 emoji 共用一个图标名：%d 组（例如 %s）"
          % (len(multi), u"、".join(u"%s←%s" % (k, u"".join(v)) for k, v in list(multi.items())[:3])))
    withp = sum(1 for v in list(icons.values()) + list(named.values()) if v.get("png"))
    print(u"  带旧 png 覆盖槽位：%d" % withp)
    for label, p in ((u"web/icons.js", WEB_OUT), (u"IconNames.kt", KT_OUT),
                     (u"web 字体", WEB_FONT), (u"安卓字体", AND_FONT), (u"LICENSE", LICENSE)):
        if os.path.isfile(p):
            print(u"  %-14s %7.1f KB" % (label, os.path.getsize(p) / 1024.0))
        else:
            print(u"  %-14s 缺失" % label)
    notes = [(k, v["name"], v["note"]) for k, v in list(icons.items()) + list(named.items())
             if v.get("note")]
    if notes:
        print(u"  有注解的条目（拿不准/改过名的）：")
        for k, n, note in notes:
            print(u"    %s → %s：%s" % (k, n, note))


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    check = "--check" in argv
    data, problems = load()
    if data is None:
        for p in problems:
            print(u"[问题] " + p)
        return 1
    names = check_fonts(data, problems)
    if problems:
        # 字体与 json 的问题**必须先解决**：名字在字体里不存在，生成出来的产物就是错的
        for p in problems:
            print(u"[问题] " + p)
        return 1
    # 前端那半边（内联字典有没有删干净、字体/许可在不在）只在 --check 时算问题：
    # 迁移期间要能先把产物生成出来，再去改 index.html。
    structural(data, problems)

    ok1 = write_or_check(WEB_OUT, gen_web(data), check)
    ok2 = write_or_check(KT_OUT, gen_kotlin(data), check)
    if "--report" in argv:
        cmd_report(data, names)
    if check:
        if problems:
            for p in problems:
                print(u"[问题] " + p)
        if ok1 and ok2 and not problems:
            scoped_n = sum(len(p) for p in scoped_tables(data).values())
            print(u"[ok] 图标一致：emoji %d ／ 具名 %d ／ 作用域 %d ／ 字体里全部命中"
                  % (len(data["icons"]), len(data["named"]), scoped_n))
        elif not (ok1 and ok2):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
