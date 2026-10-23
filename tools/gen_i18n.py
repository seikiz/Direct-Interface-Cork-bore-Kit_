# -*- coding: utf-8 -*-
"""gen_i18n.py —— 界面文案的生成器 + 校验器（唯一真相 = `lang/strings.json`）。

三端同一份 json
---------------
    lang/strings.json
      ├── web/i18n.js            由本脚本生成（window.DICK_I18N = {zh,en,ja}）
      │      index.html 的 setT() 从这里取表（原来三段 T = {...} 写在页面里）
      ├── i18n.py                运行时读 json（本脚本不生成它，但断言它没有内联表）
      └── DICK-Android/.../I18nStrings.kt   由本脚本生成（三张 map）

`used_by` 三种取值：`desktop_web` / `desktop_py` / `android`。

"谁在用"的判定（--check 与 tests/test_i18n_langs.py 共用这套，别各写一份）
------------------------------------------------------------------------
   · desktop_web  —— `web/*.html` 里出现 `T.<key>` / `T['<key>']` /
                     `data-i18n="<key>"` / `data-i18n-placeholder="<key>"`，
                     或命中动态前缀（`T['param_' + k]` → 所有 `param_*`）
   · desktop_py   —— 活跃 `*.py` 里出现 `i18n.t("<key>"` 或模块内 `t("<key>"`
                     （**排除 `tests/` 与 `tools/`**：那里是测试与工具，不是界面在用它；
                      也排除 `i18n.py` 的**表声明块**，否则拿表证明表在用 = 循环论证）
   · android      —— 安卓 `*.kt` 里出现 `I18n.t("<key>"` 或 `t("<key>"`
                     （同理排除生成的 `I18nStrings.kt`，并抠掉 `I18n.kt` 的表声明块）

跑法：
    python tools/gen_i18n.py            # 重新生成 web/i18n.js 与 I18nStrings.kt
    python tools/gen_i18n.py --check    # 只校验（CI 用；不写盘，有问题退出 1）
    python tools/gen_i18n.py --report   # 打印键数 / 死键 / used_by 与源码不一致的键
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 让 `import seiki_mark` 找得到（水印工具在仓库根；脚本从 tools/ 里跑，
# sys.path[0] 是 tools/ —— 不插这一行，_mark() 里的 import 会静默失败、产物就没水印）
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

JSON_PATH = os.path.join(ROOT, "lang", "strings.json")
JS_OUT = os.path.join(ROOT, "web", "i18n.js")
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "I18nStrings.kt")
I18NPY = os.path.join(ROOT, "i18n.py")
KT_DIR = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java")
WEB_DIR = os.path.join(ROOT, "web")

LANGS = ("zh", "en", "ja")
SIDES = ("desktop_web", "desktop_py", "android")

SKIP_DIRS = {".git", "node_modules", ".gradle", "build", ".kotlin", "utau_env",
             "tavern-installer", "site-packages", "_internal", "dist", "lang",
             "__pycache__", ".idea", "archive"}
# 这两个目录里的 .py 不算<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌"界面在用"（测试 / 工具）
PY_SKIP_DIRS = SKIP_DIRS | {"tests", "tools"}
# web/ 下的 .js 里，这几个不是"界面调用点"：i18n.js 是生成物（表本身），
# icons.js / icon_scope.js 是图标表与图标替换器。扫它们只会引入噪声。
WEB_JS_SKIP = {"i18n.js", "icons.js", "icon_scope.js"}

HEADER_JS = ("// 生成物：由 tools/gen_i18n.py 从 lang/strings.json 生成，别手改。\n"
             "//   改文案改 json；改完跑 python tools/gen_i18n.py\n")
HEADER_KT = ("// 生成物：由 tools/gen_i18n.py 从 lang/strings.json 生成，别手改。\n"
             "//   改文案改 json；改完跑 python tools/gen_i18n.py\n")

ZW = re.compile(u"[\u200b-\u200f\u2060\ufeff\u00ad]+")
CJK = re.compile(u"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")


# ============================================================
#  读 / 写（带水印：写时嵌、比对时先剥）
# ============================================================
def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _mark(path, text):
    try:
        import seiki_mark as SM
        styles = SM.COMMENT.get(os.path.splitext(path)[1].lower())
        if styles:
            text, _st, _why = SM.embed(text, None, styles, fmt="native")
    except Exception:
        pass
    return text


def _clean(text):
    """剥掉水印（可见的 `<seiki>` 前缀 + 零宽负载）后再比内容。"""
    return ZW.sub(u"", (text or "").replace(u"<seiki>", u""))


def _supports_mark(path):
    try:
        import seiki_mark as SM
        return bool(SM.COMMENT.get(os.path.splitext(path)[1].lower()))
    except Exception:
        return False


def write_or_check(path, text, check):
    old = read(path) if os.path.isfile(path) else None
    # 内容一致**且**带水印才算最新：只比内容的话，一个"没有水印但内容对"的文件
    # 会被判为最新 → 永远不会补上水印（tests/test_seiki_mark.py 会红，踩过）
    fresh = (old is not None and _clean(old) == _clean(text) and
             (not _supports_mark(path) or u"<seiki>" in old))
    if fresh:
        print(u"[ok] %s 已是最新" % os.path.relpath(path, ROOT))
        return True
    if check:
        print(u"[过期] %s 与 lang/strings.json 不一致（或没水印）—— 跑 python tools/gen_i18n.py"
              % os.path.relpath(path, ROOT))
        return False
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_mark(path, text))
    print(u"[写] %s" % os.path.relpath(path, ROOT))
    return True


# ============================================================
#  源码扫描：谁在用哪个键
# ============================================================
def _walk(exts, roots, skip):
    for base in roots:
        for dp, dns, fns in os.walk(base):
            rel = os.path.relpath(dp, ROOT).replace("\\", "/").split("/")
            if set(rel) & skip:
                dns[:] = []
                continue
            dns[:] = [d for d in dns if d not in skip]
            for fn in fns:
                if fn.endswith(tuple(exts)):
                    yield os.path.join(dp, fn)


def _strip_tables(src, names, kind="py"):
    """抠掉表声明块：py 的 `_EN = {...}` / kt 的 `private val EN = mapOf(...)`。"""
    for n in names:
        if kind == "py":
            src = re.sub(r"^%s = \{.*?\n\}" % re.escape(n), "", src, flags=re.S | re.M)
        else:
            src = re.sub(r"(?:private )?val %s\s*=\s*mapOf\(.*?\n\s*\)" % re.escape(n),
                         "", src, flags=re.S)
    return src


def _split_args(src, start):
    """从 src[start]（左括号）开始按配对取实参文本；返回 (args, 结束位置)。"""
    depth, i, args, cur, in_s = 0, start, [], [], None
    while i < len(src):
        c = src[i]
        if in_s:
            cur.append(c)
            if c == "\\":
                i += 1
                if i < len(src):
                    cur.append(src[i])
            elif c == in_s:
                in_s = None
        else:
            if c in "\"'":
                in_s = c
                cur.append(c)
            elif c in "([{":
                depth += 1
                if depth == 1:
                    i += 1
                    continue
                cur.append(c)
            elif c in ")]}":
                depth -= 1
                if depth == 0:
                    args.append("".join(cur).strip())
                    return args, i
                cur.append(c)
            elif c == "," and depth == 1:
                args.append("".join(cur).strip())
                cur = []
            else:
                cur.append(c)
        i += 1
    return args, i


def literal_of(expr):
    """`"a"` / `"a" + "b"` / 单引号变体 → 求值；求不出来（变量、模板串）返回 None。"""
    e = (expr or "").strip()
    if not e:
        return None
    vals = []
    for p in re.split(r"\s*\+\s*", e):
        p = p.strip()
        m = (re.fullmatch(r'u?"((?:[^"\\]|\\.)*)"', p) or
             re.fullmatch(r"'((?:[^'\\]|\\.)*)'", p))
        if not m:
            return None
        vals.append(m.group(1).replace('\\"', '"').replace("\\'", "'"))
    return "".join(vals)


def _find_calls(src, callees):
    """找出 callee("key", <默认值>) 形式 → {key: [默认值或 None]}"""
    out = {}
    for callee in callees:
        for m in re.finditer(re.escape(callee) + r"\s*\(", src):
            args, _ = _split_args(src, m.end() - 1)
            if len(args) < 2:
                continue
            km = re.fullmatch(r'"([A-Za-z_][A-Za-z0-9_]*)"', args[0].strip())
            if km:
                out.setdefault(km.group(1), []).append(literal_of(args[1]))
    return out


def scan_sources(json_keys=None):
    """扫三端源码，返回 dict：
       used   = {"desktop_web": set(), "desktop_py": set(), "android": set()}
       defaults = {"py": {key: [默认值…]}, "kt": {key: [默认值…]}}

    json_keys：传进来时，`T['param_' + k]` 这种**动态前缀**会把 json 里所有
    `param_*` 键都算成"有人在用"（表本身已经从 index.html 搬走了，页面里只剩动态查找，
    所以必须按 json 里的键族展开，否则那 8 个键会误判成死键、生成的表里也没有它们）。
    """
    used = {s: set() for s in SIDES}
    defaults = {"py": {}, "kt": {}}

    # ---- desktop_web：页面 + 屏模块里的 T.<key> / T['<key>'] / 动态前缀 ----
    # 2026-11 阶段2：一屏的 JS 搬到了 web/js/screens/*.js（DOM 在 web/screens/*.html），
    # 只扫 .html 会把那些屏用到的键误判成死键 —— 所以 .js 也要扫。
    # 例外见 WEB_JS_SKIP：i18n.js 是生成物（表本身），icons.js/icon_scope.js 是图标表，
    # 它们里面出现的 T.xxx 不是"界面调用点"。
    web_src = [read(p) for p in _walk([".html"], [WEB_DIR], SKIP_DIRS)]
    web_src += [read(p) for p in _walk([".js"], [WEB_DIR], SKIP_DIRS)
                if os.path.basename(p) not in WEB_JS_SKIP]
    html = "\n".join(web_src)
    for m in re.finditer(r"\bT\.([A-Za-z_][A-Za-z0-9_]*)\b", html):
        used["desktop_web"].add(m.group(1))
    for m in re.finditer(r"\bT\[['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\]", html):
        used["desktop_web"].add(m.group(1))
    for m in re.finditer(r"\bT\[['\"]([A-Za-z_][A-Za-z0-9_]*_)['\"]\s*\+", html):
        pfx = m.group(1)
        if json_keys:
            used["desktop_web"].update(k for k in json_keys if k.startswith(pfx))
        else:
            for k in re.findall(r"['\"](%s[A-Za-z0-9_]+)['\"]" % re.escape(pfx), html):
                used["desktop_web"].add(k)
    # 2026-11 阶段4：文案改成**标注在元素上**（data-i18n="<key>"），setT() 不再逐个
    # getElementById 点名。所以这两种属性也必须算"界面在用"，否则整页的键会被判成死键。
    #   data-i18n="key"              → textContent
    #   data-i18n-placeholder="key"  → placeholder
    for m in re.finditer(r"""\bdata-i18n(?:-placeholder)?\s*=\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""",
                         html):
        used["desktop_web"].add(m.group(1))

    # ---- desktop_py：活跃 .py 里的 i18n.t("k" / 模块内 t("k" ----
    # 注意别用 `(?:i18n\.)?(?<![A-Za-z_.])t\(`：`i18n.` 之后的 `t` 前面正好是 `.`，
    # 会被负向后顾直接否掉（踩过）—— 两种写法分开扫。
    RE_PY_NS = re.compile(r'i18n\.t\(\s*"([A-Za-z_][A-Za-z0-9_]*)"')
    RE_PY_BARE = re.compile(r'(?<![A-Za-z_.])t\(\s*"([A-Za-z_][A-Za-z0-9_]*)"')
    for p in _walk([".py"], [ROOT], PY_SKIP_DIRS):
        src = read(p)
        if os.path.basename(p) == "i18n.py":
            src = _strip_tables(src, ["_EN", "_JA", "_ZH"], "py")
        for rgx in (RE_PY_NS, RE_PY_BARE):
            for m in rgx.finditer(src):
                used["desktop_py"].add(m.group(1))
        if os.path.basename(p) == "i18n.py":
            for k, vals in _find_calls(src, ["t"]).items():
                defaults["py"].setdefault(k, []).extend(vals)
        for k, vals in _find_calls(src, ["i18n.t"]).items():
            defaults["py"].setdefault(k, []).extend(vals)

    # ---- android：I18n.t("k" / 对象内 t("k" ----
    RE_KT_NS = re.compile(r'I18n\.t\(\s*"([A-Za-z_][A-Za-z0-9_]*)"')
    RE_KT_BARE = re.compile(r'(?<![A-Za-z_.])t\(\s*"([A-Za-z_][A-Za-z0-9_]*)"')
    for p in _walk([".kt"], [KT_DIR], SKIP_DIRS):
        if os.path.basename(p) == "I18nStrings.kt":
            continue
        src = read(p)
        if os.path.basename(p) == "I18n.kt":
            src = _strip_tables(src, ["ZH", "EN", "JA"], "kt")
        for rgx in (RE_KT_NS, RE_KT_BARE):
            for m in rgx.finditer(src):
                used["android"].add(m.group(1))
        for k, vals in _find_calls(src, ["t", "I18n.t"]).items():
            defaults["kt"].setdefault(k, []).extend(vals)
    return {"used": used, "defaults": defaults}


# ============================================================
#  校验
# ============================================================
def load():
    if not os.path.isfile(JSON_PATH):
        return None
    try:
        return json.loads(read(JSON_PATH))
    except Exception as e:
        print("[错] lang/strings.json 不是合法 JSON：%s" % e)
        return None


def validate(doc):
    """结构校验（不读源码）。返回问题列表。"""
    p = []
    if not isinstance(doc, dict):
        return ["lang/strings.json 顶层必须是对象"]
    keys = doc.get("keys")
    if not isinstance(keys, dict) or not keys:
        return ["keys 段缺失或为空"]
    if list(doc.get("langs") or []) != list(LANGS):
        p.append("langs 必须是 %s" % (list(LANGS),))
    for k, v in keys.items():
        if not isinstance(v, dict):
            p.append("%s：值必须是对象" % k)
            continue
        for lg in LANGS:
            s = v.get(lg)
            if not isinstance(s, str) or not s.strip():
                p.append("%s：%s 缺失或为空" % (k, lg))
        ub = v.get("used_by")
        if not isinstance(ub, list) or not ub:
            p.append("%s：used_by 缺失或为空" % k)
        else:
            bad = [x for x in ub if x not in SIDES]
            if bad:
                p.append("%s：used_by 有非法端 %s" % (k, bad))
            if len(set(ub)) != len(ub):
                p.append("%s：used_by 有重复" % k)
        # 三语相同：只在"没有假名/汉字"的值上允许（纯符号/专有名词），
        # 或者键被列在 `_same_as_zh_ok` 里 —— 日语有大量**同形汉字**
        # （保存 / 内容 / 深度 / 性格…），那些本来就该与中文一模一样，不是漏译。
        zh = v.get("zh") or ""
        same_ok = set(doc.get("_same_as_zh_ok") or [])
        for lg in ("en", "ja"):
            if v.get(lg) == zh and CJK.search(zh or "") and k not in same_ok:
                p.append(u"%s：%s 与 zh 完全相同（%r）—— 像是漏译（确实是同形汉字就加进 "
                         u"_same_as_zh_ok）" % (k, lg, zh[:18]))
    legacy = doc.get("_legacy") or {}
    if not isinstance(legacy, dict):
        p.append("_legacy 段必须是对象")
    else:
        for k, v in legacy.items():
            if k in keys:
                p.append("%s：同时出现在 keys 与 _legacy" % k)
            if not isinstance(v, dict) or not str(v.get("from") or "").strip():
                p.append("%s：_legacy 条目缺 from（写明来自哪份表）" % k)
            elif not any(str(v.get(lg) or "").strip() for lg in LANGS):
                p.append("%s：_legacy 条目三语全空" % k)
    return p


def check(quiet=False):
    """完整校验：json 结构 + 产物新鲜度 + i18n.py 没有内联表。返回问题列表。"""
    problems = []
    doc = load()
    if doc is None:
        return ["lang/strings.json 读不到"]
    problems += validate(doc)

    ok = write_or_check(JS_OUT, gen_js(doc), True) if quiet else True
    if not ok:
        problems.append("web/i18n.js 过期")
    _kt_main, _kt_extra = gen_kotlin(doc)
    ok2 = write_or_check(KT_OUT, _kt_main, True) if quiet else True
    _kt_extra_out = os.path.join(os.path.dirname(KT_OUT), "I18nStringsExtra.kt")
    ok3 = write_or_check(_kt_extra_out, _kt_extra, True) if quiet else True
    ok2 = ok2 and ok3
    if not ok2:
        problems.append("DICK-Android/.../I18nStrings.kt 过期")

    if os.path.isfile(I18NPY):
        src = read(I18NPY)
        for name in ("_EN", "_JA", "_ZH"):
            if re.search(r"^%s = \{" % re.escape(name), src, re.M):
                problems.append("i18n.py 里还有内联表 %s（应该只从 json 读）" % name)
    else:
        problems.append("i18n.py 不见了")

    if not quiet and problems:
        for x in problems:
            print("[问题] " + x)
    return problems


def usage_mismatch(doc, scan):
    """used_by 声明的端，源码里是不是真的扫得到（返回 (声明了没扫到, 扫到了没声明)）。"""
    used = scan["used"]
    declared = {k: set(v.get("used_by") or []) for k, v in (doc.get("keys") or {}).items()}
    missing = {k: sorted(s for s in sides if k not in used[s])
               for k, sides in declared.items() if any(k not in used[s] for s in sides)}
    extra = {}
    for side in SIDES:
        for k in sorted(used[side]):
            if k in declared and side not in declared[k]:
                extra.setdefault(k, []).append(side)
    return missing, extra


# ============================================================
#  产物
# ============================================================
def _tables(doc):
    """{lang: {key: value}} —— 只取 keys 段（_legacy 不参与产物）。"""
    keys = doc.get("keys") or {}
    return {lg: {k: v[lg] for k, v in sorted(keys.items())} for lg in LANGS}


def gen_js(doc):
    t = _tables(doc)
    out = [HEADER_JS]
    out.append("window.DICK_I18N = {")
    for i, lg in enumerate(LANGS):
        out.append(u"  %s: %s%s" % (json.dumps(lg), json.dumps(t[lg], ensure_ascii=False, indent=2)
                                    .replace(u"\n", u"\n  "), u"," if i < len(LANGS) - 1 else u""))
    out.append("};")
    out.append("")
    return u"\n".join(out)


def _kstr(s):
    return json.dumps(s, ensure_ascii=False).replace(u"$", u"\\$")


def gen_kotlin(doc):
    """生成两个 Kotlin 文件的内容：主表（ZH）+ 附表（EN/JA）。

    为什么拆：三张 map 放一个文件会 ~1000 行，顶到"单文件 1000 行"闸门；
    数据本身没变，只是 EN/JA 搬到 I18nStringsExtra（对外仍是 I18nStrings.EN/.JA）。
    """
    t = _tables(doc)
    main = [HEADER_KT, u"package com.dick.app", u"",
            u"/** 三语界面文案（来自 lang/strings.json；EN/JA 与 ZH 键集合完全一致）。",
            u" *  EN/JA 的数据在 I18nStringsExtra.kt（拆文件只为单文件长度闸门）。 */",
            u"internal object I18nStrings {"]
    main.append(u"    val ZH: Map<String, String> = mapOf(")
    for k, v in t["zh"].items():
        main.append(u"        %s to %s," % (_kstr(k), _kstr(v)))
    main.append(u"    )")
    for lg in LANGS[1:]:
        main.append(u"    val %s: Map<String, String> get() = I18nStringsExtra.%s" % (lg.upper(), lg.upper()))
    main.append(u"}")
    main.append(u"")

    extra = [HEADER_KT, u"package com.dick.app", u"",
             u"/** EN/JA 文案（从 I18nStrings 拆出；生成物，勿手改）。 */",
             u"internal object I18nStringsExtra {"]
    for lg in LANGS[1:]:
        extra.append(u"    val %s: Map<String, String> = mapOf(" % lg.upper())
        for k, v in t[lg].items():
            extra.append(u"        %s to %s," % (_kstr(k), _kstr(v)))
        extra.append(u"    )")
    extra.append(u"}")
    extra.append(u"")
    return u"\n".join(main), u"\n".join(extra)


# ============================================================
#  main
# ============================================================
def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    doc = load()
    if doc is None:
        print("lang/strings.json 读不到，先跑 tools/_import_i18n_once.py（一次性迁移）")
        return 1

    if "--report" in argv:
        scan = scan_sources(set(doc.get("keys") or {}))
        keys = doc.get("keys") or {}
        print(u"== lang/strings.json ==")
        print(u"  keys %d ／ _legacy %d" % (len(keys), len(doc.get("_legacy") or {})))
        for side in SIDES:
            print(u"  %-12s 声明 %d ／ 源码扫到 %d"
                  % (side, sum(1 for v in keys.values() if side in (v.get("used_by") or [])),
                     len(scan["used"][side])))
        miss, extra = usage_mismatch(doc, scan)
        print(u"  声明了但扫不到（死键嫌疑）%d：%s" % (len(miss), sorted(miss)[:20]))
        print(u"  扫到了但没声明 %d：%s" % (len(extra), sorted(extra)[:20]))
        print(u"  _legacy：%s" % sorted(doc.get("_legacy") or {})[:24])
        return 0

    if "--check" in argv:
        problems = check(quiet=True)
        if problems:
            for x in problems:
                print(u"[问题] " + x)
            return 1
        print(u"[ok] 文案一致：keys %d，_legacy %d"
              % (len(doc.get("keys") or {}), len(doc.get("_legacy") or {})))
        return 0

    ok = write_or_check(JS_OUT, gen_js(doc), False)
    _km, _ke = gen_kotlin(doc)
    ok2 = write_or_check(KT_OUT, _km, False)
    ok2 = write_or_check(os.path.join(os.path.dirname(KT_OUT), "I18nStringsExtra.kt"), _ke, False) and ok2
    return 0 if (ok and ok2) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
