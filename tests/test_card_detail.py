# -*- coding: utf-8 -*-
"""卡片详情守护测试：工坊点一张卡 → 完整详情弹窗（不折叠 + 世界书 / 机制 / 文件三块）。

为什么需要
----------
用户原话（2026-12）：「给创意工坊加一个详细功能吧，点角色卡会有详细的东西。」
窄条预览（#wsPreview）只够"扫一眼"：正文超 8 行折叠、世界书 / 机制 / 文件根本不显示。
详情弹窗是新的第二份**渲染器**，所以三件事最容易悄悄坏，而且坏了界面都不报错：

  ① 字段清单被抄成第二份（今天加一个键，明天两边就不一样了）；
  ② 详情把 JSON 原文摊出来（用户说的"穿帮"就是这种）；
  ③ 详情又开始折叠（那和窄条预览就没区别了）。

守的层次
--------
  ① 文件与预算：两个新文件在、screen 模块 ≤400 行、容器在 ws.html、index.html 引了；
  ② 单一真相：字段名 / 分区 id / 标签键**一个都不许**在详情代码里出现（反向自检必须判红）；
  ③ 渲染行为：真跑一遍渲染器（node tests/card_detail_harness.js），断言**每个 section**
     都画出来了、不折叠、没有 JSON 原文、世界书 / 机制 / 文件三块入口在、>200 条会截断；
  ④ 反向验证：把模块源码里"渲染每个 section"的循环改短一个（内存里改，不落盘）→
     必须判红（证明这条断言不是摆设）；
  ⑤ 低耦与令牌：屏间只走 DICK.bus、不新增后端接口、颜色只用令牌。

跑法：utau_env\\Scripts\\python.exe -X utf8 tests\\test_card_detail.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DETAIL_JS = os.path.join(ROOT, "web", "js", "screens", "ws-detail.js")
DETAIL_CSS = os.path.join(ROOT, "web", "styles", "screens", "ws-detail.css")
WS_HTML = os.path.join(ROOT, "web", "screens", "ws.html")
WS_JS = os.path.join(ROOT, "web", "js", "screens", "ws.js")
INDEX = os.path.join(ROOT, "web", "index.html")
DOC = os.path.join(ROOT, "web", "UI_ARCHITECTURE.md")
FIELDS = os.path.join(ROOT, "design", "card_fields.json")
STRINGS = os.path.join(ROOT, "lang", "strings.json")
HARNESS = os.path.join(HERE, "card_detail_harness.js")

LINE_BUDGET = 400
# 反向验证：把「逐个 section 渲染<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌」的循环少走一趟（内存里改源码，不落盘）
MUTATE = "i < secs.length=>i < secs.length - 1"

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
    return bool(cond)


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def _blank(m):
    """注释内容换成等量空格（保留换行，行号不乱）。"""
    return re.sub(r"[^\n]", " ", m.group(0))


def strip_comments(text, ext):
    """去掉注释再扫禁用写法：注释里写「不许出现 system_prompt」不算违规。"""
    if ext == ".html":
        return re.sub(r"<!--.*?-->", _blank, text, flags=re.S)
    t = re.sub(r"/\*.*?\*/", _blank, text, flags=re.S)
    if ext in (".js", ".kt"):
        out = []
        for line in t.split("\n"):
            m = re.search(r"(?<![:\"'`])//", line)
            out.append(line[:m.start()] if m else line)
        return "\n".join(out)
    return t


def zh_labels():
    """→ ([(分区 id, 中文标签)], {字段键: 中文标签}, [标题键])，全部读**唯一真相**两份表。"""
    fields = json.loads(read(FIELDS))
    keys = (json.loads(read(STRINGS)) or {}).get("keys") or {}

    def zh(k):
        return str(((keys.get(k) or {}).get("zh")) or "")

    pairs = [(s.get("id"), zh(s.get("label_key"))) for s in (fields.get("sections") or [])]
    pairs.append(((fields.get("other") or {}).get("id"), zh((fields.get("other") or {}).get("label_key"))))
    flabels = dict((k, zh(v)) for k, v in (fields.get("field_labels") or {}).items())
    return [p for p in pairs if p[0]], flabels, list(fields.get("title_keys") or []), fields


def missing_sections(html, pairs):
    """渲染结果里缺了哪些分区（按中文标签找；标签包在 `>` … `<` 之间）。"""
    out = []
    for sid, label in pairs:
        if not label:
            out.append(sid)                    # 标签都取不到 = 这份渲染一定不对
        elif (">" + label + "<") not in html:
            out.append(sid)
    return out


def run_harness(mutate=None, node=None):
    env = dict(os.environ)
    env.pop("DETAIL_MUTATE", None)
    if mutate:
        env["DETAIL_MUTATE"] = mutate
    proc = subprocess.run([node or "node", HARNESS], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)
    return proc


def main():
    print("=" * 66)
    print(u"卡片详情守护（不折叠 / 单一字段表 / 世界书·机制·文件三块 / 反向验证）")
    print("=" * 66)

    # ------------------------------------------------------------------
    print(u"\n== ① 文件、行数预算、容器与入口 ==")
    check(u"web/js/screens/ws-detail.js 在", os.path.isfile(DETAIL_JS), rel(DETAIL_JS))
    check(u"web/styles/screens/ws-detail.css 在", os.path.isfile(DETAIL_CSS), rel(DETAIL_CSS))
    js = read(DETAIL_JS) if os.path.isfile(DETAIL_JS) else u""
    css = read(DETAIL_CSS) if os.path.isfile(DETAIL_CSS) else u""
    n_lines = len(js.split("\n")) - 1
    check(u"详情模块 ≤ %d 行（实际 %d）" % (LINE_BUDGET, n_lines), 0 < n_lines <= LINE_BUDGET,
          u"%d 行" % n_lines)
    html = read(WS_HTML)
    check(u"ws.html 里有容器 #wsDetailModal（跟着创意工坊片段一起注入）",
          'id="wsDetailModal"' in html)
    for part in ("wsDetailAvatar", "wsDetailHead", "wsDetailBody", "wsDetailClose",
                 "wsDetailImport", "wsDetailExport", "wsDetailDelete", "wsDetailUpload"):
        check(u"容器里有 #%s" % part, ('id="%s"' % part) in html)
    index = read(INDEX)
    check(u"index.html 引了 js/screens/ws-detail.js",
          'src="js/screens/ws-detail.js"' in index)
    check(u"index.html 引了 styles/screens/ws-detail.css",
          'href="styles/screens/ws-detail.css"' in index)
    doc = read(DOC)
    check(u"块清单登记了 ws-detail.js（表 1）", "web/js/screens/ws-detail.js" in doc)
    check(u"块清单登记了 ws-detail.css（表 1）", "web/styles/screens/ws-detail.css" in doc)

    # ------------------------------------------------------------------
    print(u"\n== ② 字段表只有一份真相（详情代码里不许出现字段名 / 分区 id / 标签键）==")
    code = strip_comments(js, ".js")
    check(u"详情读 window.DICK_CARD_FIELDS（分区 / 键 / 阈值都从这来）",
          "DICK_CARD_FIELDS" in code)
    check(u"分区标签走 DICK_CARD_LABEL", "DICK_CARD_LABEL" in code)
    check(u"字段标签走 DICK_CARD_FIELD_LABEL", "DICK_CARD_FIELD_LABEL" in code)
    check(u"没有第二份分区标签表（不出现 card_sec_* 键）", "card_sec_" not in code)
    check(u"详情不折叠：源里没有 collapse_lines（那个阈值只归窄条预览）",
          "collapse_lines" not in code)

    pairs, flabels, title_keys, fields = zh_labels()
    check(u"字段表里读到 %d 个分区（含「其它信息」）" % len(pairs), len(pairs) >= 5,
          u"%s" % [p[0] for p in pairs])

    def hardcoded_names(src):
        """代码里以字面量出现的字段名 / 分区 id（引号写法、obj.xxx 两种最典型的硬编码）。"""
        hits = []
        names = []
        for sec in (fields.get("sections") or []):
            for k in (sec.get("keys") or []):
                names.append(k)
                if "." in k:
                    names.extend(k.split("."))
        for sid in [s.get("id") for s in (fields.get("sections") or [])]:
            if sid:
                names.append(sid)
        for nm in sorted(set(names)):
            if not nm:
                continue
            for pat in (u"'%s'" % nm, u'"%s"' % nm, u"obj.%s" % nm, u"data.%s" % nm):
                if pat in src:
                    hits.append(u"%s（%s）" % (nm, pat))
                    break
        return hits

    hits = hardcoded_names(code)
    check(u"详情代码里 0 处硬编码字段名 / 分区 id", not hits, u"命中：%s" % hits[:6])
    # 反向自检：故意塞一个字段名进去 → 扫描必须报出来（否则这条断言就是摆设）
    planted = code + u"\nvar probe = obj['system_prompt'];\n"
    check(u"反向自检：塞进 system_prompt → 扫描判红", bool(hardcoded_names(planted)),
          u"塞进去却扫不到")
    planted2 = code + u"\nvar probe = section('profile');\n"
    check(u"反向自检：塞进分区 id profile → 扫描判红", bool(hardcoded_names(planted2)))

    # ------------------------------------------------------------------
    print(u"\n== ③ 渲染行为：每个分区都画、不折叠、没有 JSON 原文 ==")
    node = shutil.which("node")
    check(u"node 在（其余前端测试也用它）", bool(node), u"PATH 里找不到 node")
    if not node:
        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1
    proc = run_harness(node=node)
    check(u"harness 退出 0", proc.returncode == 0,
          (proc.stderr or u"")[-400:] or (proc.stdout or u"")[-300:])
    if proc.returncode != 0:
        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1
    got = json.loads(proc.stdout)
    cases = got.get("cases") or {}
    check(u"harness 跑出 6 份用例（%s）" % "、".join(sorted(cases)), len(cases) == 6)

    full = (cases.get("full") or {})
    html_full = (full.get("head") or u"") + (full.get("body") or u"")
    miss = missing_sections(html_full, pairs)
    check(u"渲染覆盖**每个** section（%d 个分区都出现）" % len(pairs), not miss,
          u"缺：%s" % miss)
    # 判定器自检：把某一个分区的标签删掉 → 必须报缺
    one = pairs[0][1]
    broken_html = html_full.replace(">" + one + "<", "><")
    check(u"判定器自检：删掉「%s」→ 判红" % one, pairs[0][0] in missing_sections(broken_html, pairs),
          u"删了还判绿")

    check(u"抬头：标题取 name", u">测试角色卡<" in html_full, (full.get("head") or u"")[:120])
    check(u"抬头：作者 · 版本 · 类型", u"seiki" in html_full and u"v1.0" in html_full
          and u"角色卡" in html_full, (full.get("head") or u"")[:160])
    check(u"抬头：#标签（#病娇 #腹黑）", u"#病娇 #腹黑" in html_full, (full.get("head") or u"")[:160])

    for label, why in ((u"世界书", u"世界书入口"), (u"机制", u"机制入口"), (u"文件", u"文件入口")):
        check(u"有%s（标题 + 一行摘要）" % why, (">" + label + "</span>") in html_full)
    check(u"世界书摘要报了条数（3 条）", u">3 条<" in html_full)
    check(u"机制摘要报了项数（3 项）", u">3 项<" in html_full)
    check(u"文件摘要报了名字 + 大小", u"咲.json" in html_full
          and re.search(u"(KB|B)\\u003c|(KB|B)</span>", html_full) is not None)
    check(u"世界书的条目逐条可见（3 条内容都在）",
          all(x in html_full for x in (u"这家咖啡馆叫「蓝猫」", u"老板娘叫玲子", u"学校在河边")))
    check(u"机制的数据看得见（affection / 51 / 是）",
          u"affection" in html_full and u">51<" in html_full)
    check(u"「其它信息」收了未知键（legacy + 列表 · 3 项）",
          u"来自旧版存档" in html_full and u"列表 · 3 项" in html_full)
    hidden = [x for x in ("card_data", "history_tree", "_meta", "chara_card_v2") if x in html_full]
    check(u"隐藏槽不进详情（card_data / history_tree / _meta）", not hidden, u"漏了：%s" % hidden)
    check(u"界面里没有大括号 / JSON 引号 / <pre>",
          not any(x in html_full for x in ("{", "}", "&quot;", "<pre")))
    check(u"没有 JSON.stringify / 等宽代码块",
          "JSON.stringify" not in code and "<pre" not in code)

    js_str = ((cases.get("jsonstr") or {}).get("head") or u"") + \
             ((cases.get("jsonstr") or {}).get("body") or u"")
    check(u"字符串里包的 JSON 只报「对象 · 1 项」",
          u"对象 · 1 项" in js_str and "{" not in js_str, js_str[:200])

    long_html = ((cases.get("long") or {}).get("body") or u"")
    n_par = len(re.findall(r"<p>", long_html))
    check(u"详情不折叠：30 段正文全画出来（实际 %d 段）" % n_par, n_par == 30, str(n_par))
    check(u"详情里没有「展开 / 收起」按钮（没有 cv-more / data-cv）",
          "cv-more" not in long_html and "data-cv" not in long_html
          and u"展开" not in long_html and u"收起" not in long_html)

    many_html = ((cases.get("many") or {}).get("body") or u"")
    n_entry = many_html.count("ws-detail-entry")
    check(u"世界书 >200 条只渲染前 200（实际 %d）" % n_entry, n_entry == 200, str(n_entry))
    check(u"截断后报「还有 50 条」", u"还有 50 条" in many_html)

    broken_html2 = ((cases.get("broken") or {}).get("body") or u"")
    check(u"坏 JSON：原文按段落显示（两段都在，且不是代码块）",
          u"这不是 JSON，只是一段原文。" in broken_html2 and u"第二段原文。" in broken_html2
          and "<pre" not in broken_html2, broken_html2[:160])
    empty_html = ((cases.get("empty") or {}).get("body") or u"")
    check(u"空文件不炸（仍给出三块入口）",
          all((u">" + x + "</span>") in empty_html for x in (u"世界书", u"机制", u"文件")),
          empty_html[:120])

    # ------------------------------------------------------------------
    print(u"\n== ④ 反向验证：删掉一个 section 的渲染 → 必须判红 ==")
    proc_m = run_harness(mutate=MUTATE, node=node)
    check(u"变异版 harness 退出 0（只在内存里改源码）", proc_m.returncode == 0,
          (proc_m.stderr or u"")[-300:])
    mut_cases = (json.loads(proc_m.stdout).get("cases") or {}) if proc_m.returncode == 0 else {}
    mut_full = (mut_cases.get("full") or {})
    mut_html = (mut_full.get("head") or u"") + (mut_full.get("body") or u"")
    mut_miss = missing_sections(mut_html, pairs)
    last_sec = pairs[-2]                    # pairs 末尾是「其它信息」，倒数第二才是最后一个分区
    check(u"变异版少了一个分区（缺 %s）" % mut_miss, len(mut_miss) == 1, u"%s" % mut_miss)
    check(u"缺的正是最后一个分区「%s」" % last_sec[1], mut_miss == [last_sec[0]],
          u"实际 %s" % mut_miss)
    check(u"也就是说：删掉一个 section 渲染，③ 的断言会红（反向验证成立）",
          bool(mut_miss))

    # ------------------------------------------------------------------
    print(u"\n== ⑤ 交互面（真的点一下：开窗 / 三种关法 / 展开收起 / 底部动作）==")
    smoke = got.get("smoke") or {}
    check(u"open() 真的把抬头 + 正文画出来了（并加上 .open）", bool(smoke.get("painted")))
    check(u"Esc 能关", bool(smoke.get("escClosed")))
    check(u"点遮罩能关", bool(smoke.get("maskClosed")))
    check(u"点「关闭」能关", bool(smoke.get("btnClosed")))
    check(u"三块 extras 默认收起", bool(smoke.get("expanded0")))
    check(u"点标题展开", bool(smoke.get("expanded")))
    check(u"再点一次收起", bool(smoke.get("collapsed")))
    want_ev = [[u"ws:detail:action", u"export"], [u"ws:detail:action", u"delete"],
               [u"ws:detail:action", u"upload"], [u"card:import", None]]
    check(u"底部四个动作按顺序发对事件（导出/删除/上传回本屏，导入归外壳）",
          smoke.get("events") == want_ev, u"%s" % (smoke.get("events"),))

    print(u"\n== ⑤2 低耦（屏间只经 DICK.bus / 不新增后端接口）==")
    check(u"Esc 能关", "Escape" in code)
    check(u"点遮罩能关（e.target === modal）", "e.target === modal" in code)
    check(u"点「关闭」能关（#wsDetailClose 绑定 close）",
          "wsDetailClose" in code and "onclick = close" in code)
    check(u"导入发 'card:import'（外壳自己的动作）", "card:import" in code)
    check(u"导出 / 删除 / 上传发 'ws:detail:action'（复用本屏已有按钮）",
          "ws:detail:action" in code and all(x in code for x in ("export", "delete", "upload")))
    check(u"详情自己不调后端（没有 pywebview.api）", "pywebview" not in code)
    others = sorted(set(re.findall(r"""getElementById\(\s*['"]([A-Za-z_][\w-]*)['"]""", code)) |
                    set(re.findall(r"""\bel\(\s*['"]([A-Za-z_][\w-]*)['"]""", code)))
    foreign = [x for x in others if not x.startswith("wsDetail")]
    acts = [x for x in ("wsDetailImport", "wsDetailExport", "wsDetailDelete", "wsDetailUpload")
            if x in code]
    check(u"只摸自己的 id（%d 个 wsDetail*，四个动作都在）" % len(others),
          not foreign and len(others) >= 4 and len(acts) == 4,
          u"越界：%s ／ 动作：%s" % (foreign, acts))

    ws = read(WS_JS)
    check(u"ws.js 仍导出 cardHtml 门面（老调用点不许断）",
          "cardHtml: wsCardHtmlFor" in ws)
    check(u"ws.js 发 'ws:detail:open'（只发事件，不摸详情 DOM）",
          "'ws:detail:open'" in ws and "wsDetailModal" not in ws
          and "getElementById('wsDetail" not in ws)
    check(u"ws.js 收 'ws:detail:action' 并复用已有按钮（不复制第二份实现）",
          "'ws:detail:action'" in ws and "wsDetailAction" in ws)
    check(u"单击入口是 #wsPreview（列表的选择 / 双击 / 长按行为未动）",
          "getElementById('wsPreview')" in ws and "onclick" in ws)
    # 预览里「展开 / 收起 N 行」是老行为：它的 click 不能冒泡到 #wsPreview 顺带把详情打开
    cv = ws[ws.find("btns[b].onclick"):] if "btns[b].onclick" in ws else ""
    check(u"预览的「展开 / 收起」按钮 stopPropagation（不会顺带开详情）",
          "stopPropagation" in cv[:400], cv[:120])
    # 导入是唯一一个不归本屏的动作：外壳必须真的接住 'card:import'，否则按钮点了没反应
    check(u"外壳接住了 'card:import'（点 #btnImportCard，不新增后端接口）",
          "'card:import'" in index and "btnImportCard" in index)

    # ------------------------------------------------------------------
    print(u"\n== ⑥ 颜色只用令牌（容器底色 / 文字色闸门同口径）==")
    css_code = strip_comments(css, ".css")
    lit = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|\bhsla?\s*\(", css_code)
    check(u"样式里没有 hex / rgba / hsl 字面量", not lit, u"命中：%s" % lit[:6])
    allowed = {"surface", "surface-2", "text", "text-sub", "border", "accent", "danger",
               "radius-sm", "radius-md", "radius-lg", "font-xs", "font-sm", "font-md",
               "font-lg", "font-xl", "lh-normal"}
    used = set(re.findall(r"var\(\s*--([\w-]+)\s*\)", css_code))
    alienc = sorted(used - allowed)
    check(u"用到的令牌都在约定清单里（%s）" % u"、".join(sorted(used)), not alienc,
          u"越界令牌：%s" % alienc)
    check(u"容器底色只来自 --surface / --surface-2",
          "background:var(--surface)" in css_code and "background:var(--surface-2)" in css_code)
    check(u"详情里不写行内 style（行内 style 归 ui_snapshot 守恒）", "style=" not in css_code)
    check(u"#wsPreview 有可点的光标提示",
          re.search(r"#wsPreview\{\s*cursor:pointer;\s*\}", css_code) is not None)

    print("\n" + "=" * 66)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CARD_DETAIL_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
