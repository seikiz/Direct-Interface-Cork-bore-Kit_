# -*- coding: utf-8 -*-
"""一次性迁移：把三份手写文案表合并成 lang/strings.json（唯一真相）。

三份来源：
  ① web/index.html 的 setT() 里三段 T = {...}（ja / en / zh）—— 界面文案主力
  ② i18n.py 的 _EN / _JA（遗留，很多键只有 archive/ 那份旧副本在用）
  ③ DICK-Android .../I18n.kt 的 EN / JA

zh 的来源：
  · web 表自带 zh；
  · 安卓 / 桌面**没有** zh 表 —— 它们的 zh 在调用点：`I18n.t("k", "中文")` / `i18n.t("k", "中文")`，
    所以从调用点抠（能解析字面量与字面量拼接；其余记为"跳过"并统计）。

used_by 的判定（与 tests/test_i18n_langs.py 用同一套规则）：
  · desktop_web —— web/*.html 里出现 `T.<key>`（消费点；表本身搬走了，所以不能扫表）
  · desktop_py  —— 活跃 *.py 里出现该键字符串（排除 archive/ 等）
  · android     —— 安卓 *.kt 里出现该键字符串

只有 archive/ 里出现、三个端都扫不到的键 → 落进 `_legacy` 段（不参与硬校验，但留档）。

跑法：python tools/_import_i18n_once.py [--write]
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "web", "index.html")
I18NPY = os.path.join(ROOT, "i18n.py")
KT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "I18n.kt")
OUT = os.path.join(ROOT, "lang", "strings.json")

SKIP_DIRS = {".git", "node_modules", ".gradle", "build", ".kotlin", "utau_env",
             "tavern-installer", "site-packages", "_internal", "dist", "lang",
             "__pycache__", ".idea", "archive"}
LEGACY_DIRS = {"archive"}


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def walk(exts, roots=None, skip_dirs=None, only_dirs=None):
    """产出 (相对路径, 绝对路径)；skip_dirs/only_dirs 用来分开"活跃代码"与 archive。"""
    skip = SKIP_DIRS if skip_dirs is None else skip_dirs
    for base in (roots or [ROOT]):
        for dp, dns, fns in os.walk(base):
            rel_dirs = set(os.path.relpath(dp, ROOT).replace("\\", "/").split("/"))
            if only_dirs is not None and not (rel_dirs & only_dirs):
                continue
            if only_dirs is None and (rel_dirs & skip):
                dns[:] = []
                continue
            dns[:] = [d for d in dns if d not in skip]
            for fn in fns:
                if fn.endswith(tuple(exts)):
                    p = os.path.join(dp, fn)
                    yield os.path.relpath(p, ROOT).replace("\\", "/"), p


# ---------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------- 抠表
def js_tables():
    t = read(HTML)
    i = t.find("function setT(l)")
    seg = t[i:i + 30000]
    out = {}
    pats = {"ja": r"if \(l === 'ja'\) \{\s*T = \{(.*?)\};",
            "en": r"else if \(l === 'en'\) \{\s*T = \{(.*?)\};",
            "zh": r"else \{\s*T = \{(.*?)\};"}
    for lang, pat in pats.items():
        m = re.search(pat, seg, re.S)
        pairs = {}
        if m:
            for km in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'((?:[^'\\]|\\.)*)'", m.group(1)):
                pairs[km.group(1)] = km.group(2).replace("\\'", "'")
        out[lang] = pairs
    return out


def py_tables():
    t = read(I18NPY)
    out = {}
    for name in ("_EN", "_JA"):
        m = re.search(name + r"\s*=\s*\{(.*?)\n\}", t, re.S)
        pairs = {}
        if m:
            for km in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"((?:[^"\\]|\\.)*)"', m.group(1)):
                pairs[km.group(1)] = km.group(2)
        out[name] = pairs
    return out


def kt_tables():
    t = read(KT)
    out = {}
    for name in ("EN", "JA"):
        m = re.search(r"private val " + name + r" = mapOf\((.*?)\n    \)", t, re.S)
        pairs = {}
        if m:
            for km in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)" to "((?:[^"\\]|\\.)*)"', m.group(1)):
                pairs[km.group(1)] = km.group(2)
        out[name] = pairs
    return out


# ---------------------------------------------------------------- 调用点
def _split_args(src, start):
    """从 src[start]（左括号）开始，按配对取到实参文本列表（能处理引号内的括号）。"""
    depth = 0
    i = start
    args, cur = [], []
    in_s = None
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
    """把 `"a"` / `"a" + "b"` / 单引号变体求值；求不出来返回 None。"""
    e = expr.strip()
    if not e:
        return None
    parts = re.split(r"\s*\+\s*", e)
    vals = []
    for p in parts:
        p = p.strip()
        m = re.fullmatch(r'u?"((?:[^"\\]|\\.)*)"', p) or re.fullmatch(r"'((?:[^'\\]|\\.)*)'", p)
        if not m:
            return None
        vals.append(m.group(1).replace('\\"', '"').replace("\\'", "'"))
    return "".join(vals)


def call_sites(exts, callee):
    """产出 {key: [(rel, 默认值或 None, 原始表达式)]}；callee 形如 'i18n.t' / 'I18n.t'。"""
    out = {}
    for rel, p in walk(exts):
        src = read(p)
        for m in re.finditer(re.escape(callee) + r"\s*\(", src):
            args, _ = _split_args(src, m.end() - 1)
            if len(args) < 2:
                continue
            km = re.fullmatch(r'"([A-Za-z_][A-Za-z0-9_]*)"', args[0].strip())
            if not km:
                continue
            key = km.group(1)
            out.setdefault(key, []).append((rel, literal_of(args[1]), args[1][:50]))
    return out


def main():
    write = "--write" in sys.argv
    js, py, kt = js_tables(), py_tables(), kt_tables()
    py_live = call_sites([".py"], "i18n.t")                     # 活跃 .py（已排除 archive）
    py_arch = {}
    for rel, p in walk([".py"], only_dirs=LEGACY_DIRS):
        src = read(p)
        for m in re.finditer(r"i18n\.t\s*\(", src):
            args, _ = _split_args(src, m.end() - 1)
            if len(args) >= 2:
                km = re.fullmatch(r'"([A-Za-z_][A-Za-z0-9_]*)"', args[0].strip())
                if km:
                    py_arch.setdefault(km.group(1), []).append((rel, literal_of(args[1])))
    kt_live = call_sites([".kt"], "I18n.t")

    # 活跃源码里的键字符串（用于 used_by 判定）。
    # **必须排除"表文件"本身**：I18n.kt 里每个键都出现一次，拿它判定"安卓在用"永远是 true（循环论证）。
    # 活跃 .py 的"在用"扫描：不能整份排除 i18n.py —— 模块自己也在 t() 里用键
    # （roles_label → t("status_roles_prefix", "")）。所以只把**表声明块**抠掉再看。
    def py_without_tables(path):
        src = read(path)
        if os.path.basename(path) == "i18n.py":
            src = re.sub(r"^_[A-Z]+ = \{.*?\n\}", "", src, flags=re.S | re.M)
        return src

    live_py_blob = "\n".join(py_without_tables(p) for _, p in walk([".py"])
                             if os.path.basename(p) != "_import_i18n_once.py")
    html_blob = "\n".join(read(p) for _, p in walk([".html"], roots=[os.path.join(ROOT, "web")]))
    # kt 的"在用"扫描：不能整份排除 I18n.kt —— 那里面除了表，还有真正在用键的代码
    # （例如 budgetLabel 里 t("budget_unlimited", "不限")）。所以只把**表声明块**抠掉，
    # 再看剩下正文里有没有这个键字符串。生成的 I18nStrings.kt 整份都是表，直接排除。
    def kt_without_tables(path):
        src = read(path)
        if os.path.basename(path) == "I18nStrings.kt":
            return ""
        return re.sub(r"private val (?:ZH|EN|JA)\s*=\s*mapOf\(.*?\n    \)", "", src, flags=re.S)

    kt_blob = "\n".join(kt_without_tables(p) for _, p in walk([".kt"]))
    # I18n.kt 内部自己的 t("key", "中文") 调用（例如 budgetLabel）—— 只用来抠 zh，不算"在用"
    kt_internal = {}
    for m in re.finditer(r"(?<![A-Za-z_.])t\(\s*\"([A-Za-z_][A-Za-z0-9_]*)\"\s*,\s*(.+?)\)\s*[,)]",
                         read(KT)):
        pass
    for m in re.finditer(r"(?<![A-Za-z_.])t\(", read(KT)):
        args, _ = _split_args(read(KT), m.end() - 1)
        if len(args) >= 2:
            km = re.fullmatch(r'"([A-Za-z_][A-Za-z0-9_]*)"', args[0].strip())
            if km:
                kt_internal.setdefault(km.group(1), []).append(literal_of(args[1]))

    js_keys = set(js["zh"]) | set(js["en"]) | set(js["ja"])
    py_keys = set(py["_EN"]) | set(py["_JA"])
    kt_keys = set(kt["EN"]) | set(kt["JA"])
    all_keys = sorted(js_keys | py_keys | kt_keys)

    keys, legacy, conflicts, no_zh, no_lang = {}, {}, [], [], []
    # "谁在用"统一走 gen_i18n.scan_sources()：生成器、校验器、测试三处共用一套判定。
    # 关键：used_by 只看**源码扫到没扫到**，与"哪张表里有这个键"无关 ——
    # 例如 unknown_cmd / vision_fail 是桌面调用点用了安卓表里的键（共享键）。
    import gen_i18n as gen
    U = gen.scan_sources()["used"]
    used_anywhere = set()
    for side in gen.SIDES:
        used_anywhere |= U[side]
    for k in sorted(set(all_keys) | used_anywhere):
        entry = {"zh": "", "en": "", "ja": "", "used_by": []}
        src_note = []
        if k in js_keys:
            entry["zh"] = js["zh"].get(k, "")
            entry["en"] = js["en"].get(k, "")
            entry["ja"] = js["ja"].get(k, "")
            src_note.append("web")
        if k in py_keys:
            entry["en"] = entry["en"] or py["_EN"].get(k, "")
            entry["ja"] = entry["ja"] or py["_JA"].get(k, "")
            src_note.append("py")
        if k in kt_keys:
            entry["en"] = entry["en"] or kt["EN"].get(k, "")
            entry["ja"] = entry["ja"] or kt["JA"].get(k, "")
            src_note.append("kt")

        for side in gen.SIDES:
            if k in U[side]:
                entry["used_by"].append(side)

        zh_pool = []
        for z in (py_live.get(k) or []):
            if z[1]:
                zh_pool.append(z[1])
        for z in (py_arch.get(k) or []):
            if z[1]:
                zh_pool.append(z[1])
        for z in (kt_live.get(k) or []):
            if z[1]:
                zh_pool.append(z[1])
        for z in (kt_internal.get(k) or []):
            if z:
                zh_pool.append(z)
        for m in re.finditer(r'(?<![A-Za-z_.])t\(\s*"%s"\s*,\s*(.+?)\)' % re.escape(k),
                             py_without_tables(I18NPY)):
            v = literal_of(m.group(1))
            if v:
                zh_pool.append(v)
        if zh_pool:
            entry["zh"] = zh_pool[0]
            uniq = [x for x in zh_pool if x != zh_pool[0]]
            if uniq and "desktop_py" in entry["used_by"]:
                conflicts.append((k, "zh", zh_pool[0], uniq[0]))

        if entry["used_by"]:
            keys[k] = entry
            if not entry["zh"]:
                no_zh.append(k)
            if not (entry["en"] and entry["ja"]):
                no_lang.append(k)
        else:
            legacy[k] = {"zh": entry["zh"], "en": entry["en"], "ja": entry["ja"],
                         "from": "+".join(src_note) or "?"}

    doc = {"_note": "界面文案唯一真相（三语）。改文案只改这里："
                    "桌面 web/i18n.js、i18n.py 运行时读它、安卓 I18nStrings.kt 由 "
                    "tools/gen_i18n.py 生成。used_by 取值：desktop_web / desktop_py / android。",
           "langs": ["zh", "en", "ja"],
           "keys": {k: keys[k] for k in sorted(keys)},
           "_legacy": {k: legacy[k] for k in sorted(legacy)}}

    print("== 合并结果 ==")
    print("  keys:   %d" % len(keys))
    for side in ("desktop_web", "desktop_py", "android"):
        print("    %-12s %d" % (side, sum(1 for v in keys.values() if side in v["used_by"])))
    print("    多端共享   %d" % sum(1 for v in keys.values() if len(v["used_by"]) > 1))
    print("  _legacy: %d（三个端都扫不到的键）" % len(legacy))
    ghost = sorted(js_keys - U["desktop_web"] - set(legacy))
    print("  js 键里既不算 used 也不算 legacy 的（不该有）: %d %s" % (len(ghost), ghost[:10]))
    for side in ("desktop_py", "android"):
        names = sorted(k for k, v in keys.items() if side in v["used_by"])
        print(u"  %s 判为在用的键 %d 个: %s" % (side, len(names), names[:24]))
    print("  legacy 名单:", list(legacy)[:40])
    print("  缺 zh 的键: %d %s" % (len(no_zh), no_zh[:20]))
    print("  缺 en/ja 的键: %d %s" % (len(no_lang), no_lang[:20]))
    print("  共享键的 zh 冲突: %d" % len(conflicts))
    for c in conflicts[:10]:
        print("    %s：桌面 %r vs 安卓 %r" % (c[0], c[2], c[3]))
    shared = [k for k, v in keys.items() if "desktop_py" in v["used_by"] and "android" in v["used_by"]]
    print("  py∩kt 共享键 %d 个，en/ja 是否一致：" % len(shared))
    for k in shared:
        same_en = py["_EN"].get(k) == kt["EN"].get(k)
        same_ja = py["_JA"].get(k) == kt["JA"].get(k)
        if not (same_en and same_ja):
            print("    %-22s en: %r / %r   ja: %r / %r"
                  % (k, py["_EN"].get(k), kt["EN"].get(k), py["_JA"].get(k), kt["JA"].get(k)))

    if write:
        d = os.path.dirname(OUT)
        if not os.path.isdir(d):
            os.makedirs(d)
        with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("\n[写] %s（%d 键 + %d legacy）" % (os.path.relpath(OUT, ROOT), len(keys), len(legacy)))
    else:
        print("\n（只报告，没写盘；加 --write 才写）")


if __name__ == "__main__":
    main()
