# -*- coding: utf-8 -*-
"""gen_card_fields.py —— 卡片外显字段的唯一真相 `design/card_fields.json` → 两端产物。

为什么要有它
------------
工坊「本地」页的预览原来两端都是**把整份 JSON 原样显示**：网页塞进等宽 `<pre>`、安卓塞进
`Text(wsPreview)`。用户的原话是「角色卡外显应该结构化，而不是像现在一样像个代码，穿帮了」。
要修的是一件事：卡片是**角色卡**，不是数据文件。

结构化要有一张表：哪些键是标题、哪些键是「角色设定」正文、`personality` 与「性格」是不是同一个
小节、世界卡的 `params.era` 算「年代」…… 这张表两端各写一份必然漂（网页认 `first_mes`、
安卓不认，同一张卡在两端长出不同的脸）。所以**唯一真相是 `design/card_fields.json`**，
两端产物由本脚本生成：

  · `web/card_fields.js`                    `window.DICK_CARD_FIELDS`（表）+ 两个标签函数
  · `DICK-Android/.../app/CardFields.kt`    `object CardFields`（表）+ 两个标签函数

标签为什么是「生成时展开成字面引用」
------------------------------------
中文标签不能硬编码在渲染器里，只能住 `lang/strings.json`（三语）。但 `tools/gen_i18n.py` 判定
「谁在用哪个键」靠的是源码里的**字面量**（`T.<键>` / `I18n.t("<键>")`）——`T[labelKey]` 这种
动态查表它看不见，那些键会被判成死键。所以生成器把 json 里的 `label_key` 展开成
`T.card_sec_setting` / `I18n.t("card_sec_setting", "角色设定")` 这样的字面调用：
标签的**清单**在 card_fields.json、标签的**文案**在 strings.json，两者都不在渲染器里。

（Kotlin 那个中文默认值同样是从 `lang/strings.json` 的 zh 抄的 —— 这是安卓既有约定
「t(key, 调用点中文原串)」，抄一遍才能让中文模式与表逐字一致，--check 会盯着。）

用法：
    python tools/gen_card_fields.py            # 重新生成两份产物
    python tools/gen_card_fields.py --check    # 校验 json + 标签三语齐全 + 产物是否最新
    python tools/gen_card_fields.py --report   # 分区 / 字段 / 标签一览
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 让 `import seiki_mark` 找得到（水印工具在仓库根<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌；脚本从 tools/ 里跑，sys.path[0] 是 tools/
# —— 不插这一行，_mark() 里的 import 会静默失败、产物就没水印；tools/gen_i18n.py 踩过同一个坑）。
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SRC = os.path.join(ROOT, "design", "card_fields.json")
STRINGS = os.path.join(ROOT, "lang", "strings.json")
JS_OUT = os.path.join(ROOT, "web", "card_fields.js")
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "CardFields.kt")

LANGS = ("zh", "en", "ja")
MODES = ("body", "kv", "list")          # 没有 json 模式：卡片外显不该出现大括号（故意的）
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ZW = re.compile(u"[\u200b-\u200f\u2060\ufeff\u00ad]+")

HEADER_JS = (u"// ⚠ 生成物：由 tools/gen_card_fields.py 从 design/card_fields.json 生成，别手改。\n"
             u"//   改分区/字段/折叠阈值：改 design/card_fields.json，再跑一次生成器。\n")
HEADER_KT = (u"// ⚠ 生成物：由 tools/gen_card_fields.py 从 design/card_fields.json 生成，别手改。\n"
             u"//   改分区/字段/折叠阈值：改 design/card_fields.json，再跑一次生成器。\n"
             u"//   标签文案在 lang/strings.json（本文件里的中文只是 I18n.t 的调用点默认值）。\n")


# ---------------- 水印（与 tools/gen_icons.py / gen_i18n.py 同一套做法） ----------------
def _clean(text):
    """剥掉水印（可见的 `<seiki>` 前缀 + 零宽负载）后再比内容。"""
    return ZW.sub(u"", (text or "").replace(u"<seiki>", u""))


def _mark(path, text):
    try:
        import seiki_mark as SM
        styles = SM.COMMENT.get(os.path.splitext(path)[1].lower())
        if styles:
            text, _st, _why = SM.embed(text, None, styles, fmt="native")
    except Exception:
        pass
    return text


def _supports_mark(path):
    try:
        import seiki_mark as SM
        return bool(SM.COMMENT.get(os.path.splitext(path)[1].lower()))
    except Exception:
        return False


def _read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def _s(v):
    """Kotlin 字符串字面量（转义反斜杠与引号）。"""
    return u'"%s"' % str(v).replace(u"\\", u"\\\\").replace(u'"', u'\\"')


# ---------------- 载入与校验 ----------------
def load_strings(problems):
    """读 lang/strings.json（标签文案的唯一真相）。读不到 = 生成物没法写（Kotlin 要 zh 默认值）。"""
    if not os.path.isfile(STRINGS):
        problems.append(u"lang/strings.json 不存在")
        return {}
    try:
        doc = json.loads(_read(STRINGS))
    except ValueError as e:
        problems.append(u"lang/strings.json 不是合法 JSON：%s" % e)
        return {}
    return doc.get("keys") or {}


def load_data():
    """返回 (data, strings, problems)。problems 非空时产物不能生成。

    data    = design/card_fields.json（字段表唯一真相）
    strings = lang/strings.json 的 keys 段（标签文案的唯一真相；Kotlin 的 zh 默认值从这里抄）
    """
    problems = []
    if not os.path.isfile(SRC):
        return None, {}, [u"找不到唯一真相 design/card_fields.json"]
    try:
        data = json.loads(_read(SRC))
    except ValueError as e:
        return None, {}, [u"design/card_fields.json 不是合法 JSON：%s" % e]
    strings = load_strings(problems)
    problems += structural(data)
    if problems:
        return None, strings, problems
    problems += _check_labels(data, strings)
    return (None if problems else data), strings, problems


def structural(data):
    """结构校验（不碰 strings）：分区/键/展示方式/阈值。"""
    problems = []
    if not isinstance(data, dict):
        return [u"design/card_fields.json 顶层必须是对象"]
    for k in ("version", "collapse_lines", "kv_value_chars", "max_text_chars"):
        if not isinstance(data.get(k), int) or isinstance(data.get(k), bool):
            problems.append(u"%s 必须是整数（当前 %r）" % (k, data.get(k)))
    if isinstance(data.get("collapse_lines"), int) and data["collapse_lines"] <= 0:
        problems.append(u"collapse_lines 必须 > 0")
    title = data.get("title_keys")
    if not isinstance(title, list) or not title or not all(isinstance(x, str) and x for x in title):
        problems.append(u"title_keys 必须是非空的键名数组")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        problems.append(u"sections 必须是非空数组")
        sections = []
    seen_ids = set()
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            problems.append(u"sections[%d] 必须是对象" % i)
            continue
        sid = sec.get("id")
        if not isinstance(sid, str) or not ID_RE.match(sid or ""):
            problems.append(u"sections[%d].id 必须是小写下划线名（当前 %r）" % (i, sid))
        elif sid in seen_ids:
            problems.append(u"sections[%d].id 重复：%s" % (i, sid))
        else:
            seen_ids.add(sid)
        if sec.get("mode") not in MODES:
            problems.append(u"sections[%d].mode 必须是 %s 之一（当前 %r）"
                            % (i, u"/".join(MODES), sec.get("mode")))
        keys = sec.get("keys")
        if not isinstance(keys, list) or not keys or not all(isinstance(x, str) and x for x in keys):
            problems.append(u"sections[%d].keys 必须是非空字符串数组" % i)
    other = data.get("other")
    if not isinstance(other, dict) or other.get("mode") not in MODES:
        problems.append(u"other 必须是对象且 mode 在 %s 之内" % u"/".join(MODES))
    for label, node in [(u"hidden_keys", data.get("hidden_keys")),
                        (u"hidden_prefixes", data.get("hidden_prefixes"))]:
        if not isinstance(node, list) or not all(isinstance(x, str) for x in node):
            problems.append(u"%s 必须是字符串数组" % label)
    if not isinstance(data.get("field_labels"), dict):
        problems.append(u"field_labels 必须是非空对象")
    return problems


def _check_labels(data, strings):
    """标签键必须都在 strings.json 里，且三语非空。"""
    problems = []
    label_keys = []
    for sec in data.get("sections") or []:
        if isinstance(sec, dict) and sec.get("label_key"):
            label_keys.append(sec["label_key"])
    other = data.get("other")
    if isinstance(other, dict) and other.get("label_key"):
        label_keys.append(other["label_key"])
    fields = data.get("field_labels")
    if isinstance(fields, dict):
        label_keys += [v for v in fields.values() if isinstance(v, str)]
    for k in sorted(set(label_keys)):
        row = strings.get(k)
        if not row:
            problems.append(u"标签键 %s 不在 lang/strings.json 里（标签文案只住那里）" % k)
            continue
        for lg in LANGS:
            if not str(row.get(lg) or "").strip():
                problems.append(u"标签键 %s 缺 %s 文案" % (k, lg))
    return problems


# ---------------- web/card_fields.js ----------------
def _js_str(v):
    return json.dumps(v, ensure_ascii=False)


def gen_web(data):
    o = [HEADER_JS]
    o.append(u"// 分区/字段/阈值：与安卓 CardFields.kt 同一份（tools/gen_card_fields.py --check 盯着）")
    o.append(u"window.DICK_CARD_FIELDS = {")
    o.append(u"  version: %d," % data["version"])
    o.append(u"  collapseLines: %d," % data["collapse_lines"])
    o.append(u"  kvValueChars: %d," % data["kv_value_chars"])
    o.append(u"  maxTextChars: %d," % data["max_text_chars"])
    o.append(u"  titleKeys: [%s]," % u", ".join(_js_str(k) for k in data["title_keys"]))
    o.append(u"  sections: [")
    for sec in data["sections"]:
        o.append(u"    { id: %s, mode: %s, labelKey: %s, keys: [%s] },"
                 % (_js_str(sec["id"]), _js_str(sec["mode"]), _js_str(sec["label_key"]),
                    u", ".join(_js_str(k) for k in sec["keys"])))
    o.append(u"  ],")
    other = data["other"]
    o.append(u"  other: { id: %s, mode: %s, labelKey: %s },"
             % (_js_str(other["id"]), _js_str(other["mode"]), _js_str(other["label_key"])))
    o.append(u"  fieldLabels: {")
    for k, v in data["field_labels"].items():
        o.append(u"    %s: %s," % (_js_str(k), _js_str(v)))
    o.append(u"  },")
    o.append(u"  hiddenKeys: [%s]," % u", ".join(_js_str(k) for k in data["hidden_keys"]))
    o.append(u"  hiddenPrefixes: [%s]" % u", ".join(_js_str(k) for k in data["hidden_prefixes"]))
    o.append(u"};")
    o.append(u"")
    o.append(u"// 分区标签：生成时就展开成 T.<键> 字面引用 —— 这样 tools/gen_i18n.py 的")
    o.append(u"// 「谁在用哪个键」扫描看得见它们（动态 T[labelKey] 会被判成死键）。文案仍只住 lang/strings.json。")
    o.append(u"window.DICK_CARD_LABEL = function (id) {")
    o.append(u"  switch (id) {")
    for sec in data["sections"] + [other]:
        o.append(u"    case %s: return T.%s || '';" % (_js_str(sec["id"]), sec["label_key"]))
    o.append(u"    default: return '';")
    o.append(u"  }")
    o.append(u"};")
    o.append(u"")
    o.append(u"// 字段标签（同一套：字面引用，扫描可见）。没登记的键返回空串 —— 渲染器退回显示键名本身。")
    o.append(u"window.DICK_CARD_FIELD_LABEL = function (key) {")
    # 同一个标签键挂在多个同义键上时，case 归并成一支（T.<键> 只出现一次）
    by_label = {}
    for k, v in data["field_labels"].items():
        by_label.setdefault(v, []).append(k)
    for label_key, keys in by_label.items():
        o.append(u"  if ([%s].indexOf(key) >= 0) return T.%s || '';"
                 % (u", ".join(_js_str(k) for k in keys), label_key))
    o.append(u"  return '';")
    o.append(u"};")
    return u"\n".join(o) + u"\n"


# ---------------- CardFields.kt ----------------
def gen_kotlin(data, strings):
    def zh_of(label_key):
        return str((strings.get(label_key) or {}).get("zh") or "")

    o = [HEADER_KT, u"package com.dick.app", u""]
    o.append(u"/** 一个卡片分区：id + 展示方式（body/kv/list）+ 这个分区收哪些键（顺序即渲染顺序）。 */")
    o.append(u"data class CardSection(")
    o.append(u"    val id: String,")
    o.append(u"    val mode: String,")
    o.append(u"    val keys: List<String>,")
    o.append(u")")
    o.append(u"")
    o.append(u"/**")
    o.append(u" * 卡片外显字段表（唯一真相 design/card_fields.json 的生成物）。")
    o.append(u" * 网页端是 web/card_fields.js —— 分区 / 顺序 / 折叠阈值 / 隐藏槽逐字一致（--check 盯着）。")
    o.append(u" */")
    o.append(u"object CardFields {")
    o.append(u"    const val VERSION = %d" % data["version"])
    o.append(u"")
    o.append(u"    /** 正文超过这么多行就折叠（网页端读的是同一个数） */")
    o.append(u"    const val COLLAPSE_LINES = %d" % data["collapse_lines"])
    o.append(u"")
    o.append(u"    /** 两列视图里字符串值的截断长度 */")
    o.append(u"    const val KV_VALUE_CHARS = %d" % data["kv_value_chars"])
    o.append(u"")
    o.append(u"    /** 正文分区单段最长字数 */")
    o.append(u"    const val MAX_TEXT_CHARS = %d" % data["max_text_chars"])
    o.append(u"")
    o.append(u"    /** 标题候选键（按顺序取第一个有非空标量值的） */")
    o.append(u"    val TITLE_KEYS: List<String> = listOf(%s)"
             % u", ".join(_s(k) for k in data["title_keys"]))
    o.append(u"")
    o.append(u"    /** 分区（顺序即渲染顺序） */")
    o.append(u"    val SECTIONS: List<CardSection> = listOf(")
    for sec in data["sections"]:
        o.append(u"        CardSection(%s, %s, listOf(%s)),"
                 % (_s(sec["id"]), _s(sec["mode"]), u", ".join(_s(k) for k in sec["keys"])))
    o.append(u"    )")
    o.append(u"")
    other = data["other"]
    o.append(u"    /** 兜底分区：没被上面任何分区认领的键都进这里（两列「键: 值」，**不显示 JSON**） */")
    o.append(u"    val OTHER: CardSection = CardSection(%s, %s, emptyList())"
             % (_s(other["id"]), _s(other["mode"])))
    o.append(u"")
    o.append(u"    /** 键 → 字段标签的 i18n 键（文案在 lang/strings.json） */")
    o.append(u"    val FIELD_LABEL_KEYS: Map<String, String> = mapOf(")
    for k, v in data["field_labels"].items():
        o.append(u"        %s to %s," % (_s(k), _s(v)))
    o.append(u"    )")
    o.append(u"")
    o.append(u"    /** 原样数据槽：不显示（整份原始卡 / 对话树 / 世界书元数据） */")
    o.append(u"    val HIDDEN_KEYS: Set<String> = setOf(%s)"
             % u", ".join(_s(k) for k in data["hidden_keys"]))
    o.append(u"")
    o.append(u"    /** 这些前缀开头的键一律不显示（_meta / _tree_* 等程序槽） */")
    o.append(u"    val HIDDEN_PREFIXES: List<String> = listOf(%s)"
             % u", ".join(_s(k) for k in data["hidden_prefixes"]))
    o.append(u"")
    o.append(u"    /** 分区标签（三语走 I18n；键在这里展开成字面调用，扫描器才看得见） */")
    o.append(u"    fun sectionLabel(id: String): String = when (id) {")
    for sec in data["sections"] + [other]:
        o.append(u"        %s -> I18n.t(%s, %s)"
                 % (_s(sec["id"]), _s(sec["label_key"]), _s(zh_of(sec["label_key"]))))
    o.append(u"        else -> \"\"")
    o.append(u"    }")
    o.append(u"")
    o.append(u"    /** 字段标签；没登记的键返回空串（渲染器退回显示键名本身） */")
    o.append(u"    fun fieldLabel(key: String): String = when (key) {")
    for k, v in data["field_labels"].items():
        o.append(u"        %s -> I18n.t(%s, %s)" % (_s(k), _s(v), _s(zh_of(v))))
    o.append(u"        else -> \"\"")
    o.append(u"    }")
    o.append(u"}")
    return u"\n".join(o) + u"\n"


# ---------------- 写 / 校验 ----------------
def write_or_check(path, text, check):
    old = _read(path) if os.path.isfile(path) else None
    # 内容一致**且**带水印才算最新（与 gen_i18n.py 同口径：否则「没水印但内容对」永远补不上水印）
    fresh = (old is not None and _clean(old) == _clean(text) and
             (not _supports_mark(path) or u"<seiki>" in old))
    if fresh:
        print(u"[ok] %s 已是最新" % os.path.relpath(path, ROOT))
        return True
    if check:
        print(u"[过期] %s 与 design/card_fields.json 不一致（或没水印）—— 跑 python tools/gen_card_fields.py"
              % os.path.relpath(path, ROOT))
        return False
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_mark(path, text))
    print(u"[写] %s（%d 字符）" % (os.path.relpath(path, ROOT), len(text)))
    return True


def cmd_report(data, strings):
    print(u"== design/card_fields.json ==")
    print(u"  折叠阈值 %d 行 ／ 两列截断 %d 字 ／ 正文上限 %d 字"
          % (data["collapse_lines"], data["kv_value_chars"], data["max_text_chars"]))
    print(u"  标题键：%s" % u"、".join(data["title_keys"]))
    for sec in data["sections"]:
        print(u"  [%s] %s（%s）← %s"
              % (sec["id"], (strings.get(sec["label_key"]) or {}).get("zh", "?"),
                 sec["mode"], u"、".join(sec["keys"])))
    other = data["other"]
    print(u"  [%s] %s（%s）← 剩余未知键"
          % (other["id"], (strings.get(other["label_key"]) or {}).get("zh", "?"), other["mode"]))
    print(u"  字段标签 %d 条：%s" % (len(data["field_labels"]),
                                 u"、".join(u"%s→%s" % (k, v)
                                            for k, v in list(data["field_labels"].items())[:8])))
    print(u"  隐藏槽：%s ／ 隐藏前缀：%s"
          % (u"、".join(data["hidden_keys"]), u"、".join(data["hidden_prefixes"])))


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    check = "--check" in argv
    data, strings, problems = load_data()
    if problems:
        for p in problems:
            print(u"[问题] " + p)
        return 1
    ok1 = write_or_check(JS_OUT, gen_web(data), check)
    ok2 = write_or_check(KT_OUT, gen_kotlin(data, strings), check)
    if "--report" in argv:
        cmd_report(data, strings)
    if check:
        if not (ok1 and ok2):
            return 1
        print(u"[ok] 字段表一致：%d 个分区 ／ %d 条字段标签 ／ 折叠阈值 %d 行"
              % (len(data["sections"]), len(data["field_labels"]), data["collapse_lines"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
