# -*- coding: utf-8 -*-
"""角色卡详情弹窗守护（安卓）：点工坊里的一张卡 → 打开**独立详情**，而不是嵌在列表里的小预览。

为什么需要
----------
用户原话：「给创意工坊加一个详细功能吧，点角色卡会有详细的东西。」
旧做法是工坊弹窗里塞一块紧凑预览（空间小、正文还要点「展开」）。升级成独立详情弹窗之后，
最容易悄悄退回去的四件事，正好都是"编译不报错、界面也能看"的那种：

  ① **字段表长出第二份**：详情页图省事自己抄一张 `键 → 中文标签` 表 —— 两端（网页/安卓）
     再加上这一份，以后改字段就是三处改两处漏；
  ② **分区漏了**：`CardFields.SECTIONS` 有 6 个分区，渲染器改成只画其中几个（或换了 mode
     却没写分支），界面上只是"少了一块"，没人会报错；
  ③ **详情页又开始折叠**：把原来那套"超过 8 行点展开"抄回来，等于白做这个弹窗；
  ④ **补的三块数据没接上**：世界书 `world_entries` / 机制 `advanced.mechanics` / 文件信息
     任何一块掉了，用户看到的就是"详细功能"少一块。

所以这条测试守：
  · 文件在、**≤400 行**（ARCHITECTURE 九.1 的预算）；
  · 字段 / 分区 / 标签**全部来自 `CardFields`**，且本文件**没有**任何分区 id 字面量（不可能是第二张表）；
  · `design/card_fields.json` 里每个分区的 mode 都有排版分支（漏一个就红）；
  · 三块补充数据都在，且按**数据结构**通用渲染（对象→键值行、数组→逐条行）；
  · 弹窗只走 `DickDialog`、颜色只走令牌、界面上不出现 JSON 原文；
  · 状态只有 `ChatViewModel.wsDetail` 一处（老的 `wsPreview` 彻底退场）；
  · **反向验证**：把上面每一条弄坏一次，判定器必须真的红（否则这套断言只是装饰）。

口径（窄，故意的）：只扫 `CardDetail.kt` 这一个渲染文件 + 工坊屏/VM 的接线；注释先剥掉再扫
（文档里写着「不许 Color(0x…)」不算违规）；`CardFields.kt` 是生成物，它由 `test_card_view.py`
的 `gen_card_fields.py --check` 守着，这里只断言"有没有在读它"。

跑法：python -X utf8 tests/test_card_detail_android.py
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")
WS_DIR = os.path.join(APP, "ui", "screens", "workshop")
DETAIL = os.path.join(WS_DIR, "CardDetail.kt")
PARSER = os.path.join(WS_DIR, "CardPreview.kt")
SCREEN = os.path.join(WS_DIR, "WorkshopScreen.kt")
VM = os.path.join(APP, "ChatViewModel.kt")
FIELDS = os.path.join(ROOT, "design", "card_fields.json")

LINE_BUDGET = 400
# 每种 mode 必须有自己的一条排版分支（body 走 else 兜底，所以看的是函数名）。
MODE_BRANCH = {"body": "CdBody(", "kv": "CdKeyValues(", "list": "CdList("}

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
    return cond


def read(p):
    with io.open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def lines(text):
    """行数（与 tools/run_local_suite 的数法一致：末行后有换行就算到底）。"""
    return len(text.split("\n")) - 1


def strip_comments(text):
    """去掉 // 与 /* */（替换成等量空白，行号不漂）—— 注释里写着「不许 Color(0x…)」不算违规。"""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    t = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    out = []
    for line in t.split("\n"):
        m = re.search(r"(?<![:\"'`])//", line)
        out.append(line[:m.start()] if m else line)
    return "\n".join(out)


# ============================================================
#  判定器（反向验证直接喂合成文本给它们，所以不许写死"读磁盘"）
# ============================================================
def budget_problems(code, budget=LINE_BUDGET):
    n = lines(code)
    return [] if n <= budget else [u"%d 行 > 预算 %d" % (n, budget)]


def source_problems(code):
    """字段来源：分区/标签/阈值必须读 [CardFields]（唯一真相的生成物）；不许自带字段表。"""
    probs = []
    for need in ("CardFields.sectionLabel(", "CardFields.fieldLabel(", "CardFields.OTHER",
                 "CardFields.MAX_TEXT_CHARS", "CardFields.KV_VALUE_CHARS"):
        if need not in code:
            probs.append(u"没读 %s" % need)
    if "CardSection(" in code:
        probs.append(u"自己造了 CardSection（= 第二张字段表）")
    return probs


def mode_block(code):
    """取 `when (sec.mode) { … }` 的块体（大括号配平）；找不到返回空串。

    为什么要先切出这一块再看分支：`CdList(` 这种名字在**函数定义**里也出现，
    直接全文找会把"分支被删了"判成绿（反向验证就是这么抓出这个洞的）。
    """
    m = re.search(r"when\s*\(\s*sec\.mode\s*\)\s*\{", code)
    if not m:
        return u""
    i, depth, p = m.end() - 1, 1, m.end()
    while p < len(code) and depth > 0:
        if code[p] == "{":
            depth += 1
        elif code[p] == "}":
            depth -= 1
        p += 1
    return code[i:p]


def section_problems(code, fields):
    """覆盖：`CardFields.SECTIONS` 造出来的每个分区都要被画出来，且不许写死分区 id。"""
    probs = []
    secs = fields.get("sections") or []
    if "model.sections" not in code:
        probs.append(u"没有遍历模型里的分区（model.sections）")
    body = mode_block(code)
    if not body:
        probs.append(u"没有 when (sec.mode) 分派块")
    for mode in sorted({s.get("mode") for s in secs}):
        branch = MODE_BRANCH.get(mode)
        if branch is None:
            probs.append(u"未知 mode %r（card_fields.json 只该有 body/kv/list）" % mode)
        elif branch not in body:
            probs.append(u"mode=%s 没有排版分支（when 块里缺 %s）" % (mode, branch))
    if not re.search(r"CardFields\.sectionLabel\(\s*sec\.id\s*\)", code):
        probs.append(u"分区标题没走 CardFields.sectionLabel(sec.id)")
    ids = [s.get("id") for s in secs] + [(fields.get("other") or {}).get("id")]
    for sid in [i for i in ids if i]:
        if (u'"%s"' % sid) in code:
            probs.append(u"写死了分区 id 字面量 %r（说明抄了一份表）" % sid)
    return probs


def extras_problems(code):
    """三块补充数据：世界书（默认收起 + 200 上限）/ 机制 / 文件信息，且按数据结构通用渲染。

    同样认**调用点**（`CdWorldBook(world)`）而不是函数名：定义还在、却没地方调，
    对用户来说那块就是没了。
    """
    probs = []
    for need in ("world_entries", "CdWorldBook(world)", "CD_WORLD_CAP = 200", u"还有 "):
        if need not in code:
            probs.append(u"世界书块缺 %s" % need)
    for need in ("advanced", "mechanics", "CdMechanics(mech)"):
        if need not in code:
            probs.append(u"机制块缺 %s" % need)
    for need in ("CdFileInfo(d)", u"文件", "lastModified", "length()"):
        if need not in code:
            probs.append(u"文件块缺 %s" % need)
    if not re.search(r"var open by remember\(entries\)\s*\{\s*mutableStateOf\(false\)\s*\}", code):
        probs.append(u"世界书不是默认收起（open 初值不是 false）")
    if "is J.Obj" not in code or "is J.Arr" not in code:
        probs.append(u"没有按数据结构通用渲染（缺 is J.Obj / is J.Arr）")
    if "v.fields.forEach" not in code:
        probs.append(u"对象没有逐键渲染（键名应来自数据）")
    if re.search(r"\bcf(Field|Label)Of\b", code):
        probs.append(u"又造了一张字段标签表")
    return probs


def color_problems(code):
    probs = []
    m = re.search(r"Color\(\s*0x", code)
    if m:
        probs.append(u"硬编码 %s" % m.group(0))
    m = re.search(r"\bColor\.(White|Black|Red|Green|Blue|Gray|LightGray|DarkGray)\b", code)
    if m:
        probs.append(u"命名色 %s" % m.group(0))
    if "LocalDickPalette.current" not in code:
        probs.append(u"没读 LocalDickPalette（颜色只能从令牌来）")
    return probs


def dialog_problems(code):
    probs = []
    if "DickDialog(" not in code:
        probs.append(u"没走 DickDialog（弹窗唯一出口）")
    if re.search(r"(?<![A-Za-z_])AlertDialog\s*\(", code):
        probs.append(u"出现裸 AlertDialog(")
    if "containerColor" in code:
        probs.append(u"自己写了 containerColor（绕开弹窗壳）")
    if "wsDetail.value = null" not in code:
        probs.append(u"关闭时没有置空 wsDetail")
    return probs


def json_leak_problems(code):
    probs = []
    for pat, why in ((r"JsonS\s*\.\s*stringify", u"把对象序列化回 JSON 文本"),
                     (r"JsonS\s*\.\s*parse", u"渲染层自己解析（解析归 CardPreview）"),
                     (r"Text\s*\(\s*(d\.)?raw\b", u"把原文直接丢给 Text"),
                     (r"text\s*=\s*d\.raw", u"把原文直接丢给控件")):
        m = re.search(pat, code)
        if m:
            probs.append(u"%s：%s" % (why, m.group(0)))
    return probs


def avatar_problems(code):
    probs = []
    if 'fields?.get("avatar")' not in code:
        probs.append(u"没读卡里的 avatar")
    if "speakerColor(" not in code:
        probs.append(u"没有「身份色首字」回退")
    if "onIdentity" not in code:
        probs.append(u"首字墨色没走 on_identity 令牌")
    return probs


def wiring_problems(screen, vm, tree):
    """屏间只经 ChatViewModel：单击打开 → wsDetail；选中高亮保留；列表里不再嵌预览。"""
    probs = []
    if "wsDetail" not in vm or "WsCardDetail?" not in vm:
        probs.append(u"ChatViewModel 里没有 wsDetail: WsCardDetail?")
    if re.search(r"vm\.wsPreview|var wsPreview|wsPreview\s*=", tree):
        probs.append(u"安卓树里还有活的 wsPreview（状态没换干净）")
    if len(re.findall(r"wsDetail = WsCardDetail\(", screen)) != 2:
        probs.append(u"点列表项没打开详情（角色卡 / 世界卡两列各一处）")
    if "CardDetailDialog(" not in screen:
        probs.append(u"工坊屏没有挂详情弹窗")
    if "WsCardPreview(" in screen:
        probs.append(u"工坊列表里还嵌着旧预览")
    if "outline = if (sel) theme.palette.accent else theme.line" not in screen:
        probs.append(u"选中高亮没了")
    if "outlineWidth = if (sel) 2.dp else 1.dp" not in screen:
        probs.append(u"选中描边粗细没了")
    return probs


# ============================================================
#  main
# ============================================================
def main():
    print("=" * 68)
    print(u"角色卡详情弹窗（独立弹窗 / 字段只认 CardFields / 三块补充数据 / 反向验证）")
    print("=" * 68)

    fields = json.loads(read(FIELDS))
    secs = fields.get("sections") or []
    ids = [s.get("id") for s in secs]

    # ------------------------------------------------------------------
    print(u"\n== ① 文件与行数预算 ==")
    check(u"CardDetail.kt 在", os.path.isfile(DETAIL), rel(DETAIL))
    if not os.path.isfile(DETAIL):
        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1
    raw = read(DETAIL)
    code = strip_comments(raw)
    n = lines(raw)
    check(u"单文件 %d 行 ≤ %d（ARCHITECTURE 九.1）" % (n, LINE_BUDGET), not budget_problems(raw),
          u"%d 行" % n)
    print(u"       CardDetail.kt = %d 行 / CardPreview.kt = %d 行（解析层）"
          % (n, lines(read(PARSER))))

    # ------------------------------------------------------------------
    print(u"\n== ② 字段来源：只认 CardFields（生成物），没有第二张表 ==")
    src = source_problems(code)
    check(u"分区 / 标签 / 阈值全部从 CardFields 读", not src, u"；".join(src[:4]))
    parser = read(PARSER)
    check(u"模型由 CardFields.SECTIONS 逐条攒出来（解析层）",
          "CardFields.SECTIONS" in parser and "CardFields.TITLE_KEYS" in parser)
    check(u"详情页不含任何分区 id 字面量（%d 个都不许写死）" % len(ids),
          not [i for i in ids if (u'"%s"' % i) in code],
          u"、".join(i for i in ids if (u'"%s"' % i) in code))
    check(u"详情页没有自己的 CardSection 构造（第二张字段表）", "CardSection(" not in code)

    # ------------------------------------------------------------------
    print(u"\n== ③ 每个分区都要被画出来（mode 齐全 = 6 个分区一个不漏） ==")
    sec = section_problems(code, fields)
    check(u"CardFields 的 %d 个分区全覆盖（body/kv/list 三种排版都在）" % len(secs),
          not sec, u"；".join(sec[:4]))
    for s in secs:
        branch = MODE_BRANCH.get(s.get("mode"))
        ok = bool(branch) and branch in code
        print(u"       %-10s mode=%-5s → %-14s %s" % (s.get("id"), s.get("mode"), branch,
                                                     u"OK" if ok else u"缺"))
    check(u"「其它信息」兜底分区也在（未认领的键不许丢；三块已单独渲染的键除外）",
          "CardFields.OTHER" in code and "model.other" in code and "CdKeyValues(other)" in code)
    check(u"详情页不折叠：没有「展开 / 收起」按钮，也没有折叠阈值分支",
          "card_expand" not in code and "card_collapse" not in code and
          "COLLAPSE_LINES" not in code)

    # ------------------------------------------------------------------
    print(u"\n== ④ 三块补充数据（世界书 / 机制 / 文件） ==")
    ext = extras_problems(code)
    check(u"三块都在，且按数据结构通用渲染", not ext, u"；".join(ext[:4]))
    check(u"世界书：默认收起 + 点标题展开（FoldHead + open=false）",
          "FoldHead(" in code and bool(re.search(
              r"var open by remember\(entries\)\s*\{\s*mutableStateOf\(false\)\s*\}", code)))
    check(u"世界书：超过 %d 条只渲染前 %d + 「还有 N 条」" % (200, 200),
          "CD_WORLD_CAP = 200" in code and "entries.take(CD_WORLD_CAP)" in code and
          u"还有 " in code)
    check(u"世界书：每条可点开逐条看（openIdx 状态 + CdTree）",
          "openIdx" in code and "CdTree(e, 0)" in code)
    check(u"机制：从 advanced.mechanics 取（不是另存一份配置）",
          'fields?.get("advanced")' in code and 'fields?.get("mechanics")' in code)
    check(u"文件：文件名 + 大小 + 修改时间（读不到就按原文长度兜底）",
          "cdFileNote(" in code and "cdSize(" in code and "lastModified()" in code)

    # ------------------------------------------------------------------
    print(u"\n== ⑤ 弹窗 / 颜色 / 不出现 JSON 原文 / 头像 ==")
    d = dialog_problems(code)
    check(u"弹窗只走 DickDialog，关掉只置空 wsDetail", not d, u"；".join(d[:4]))
    c = color_problems(code)
    check(u"颜色只走令牌（无 Color(0x…)、无命名色）", not c, u"；".join(c[:4]))
    j = json_leak_problems(code)
    check(u"界面上不出现 JSON 原文（大括号 / 引号 / stringify）", not j, u"；".join(j[:3]))
    a = avatar_problems(code)
    check(u"头像：卡里有 avatar 就用，没有退回身份色首字", not a, u"；".join(a[:3]))
    check(u"头像联网只读、不挡详情（超时 + 失败回退 null）",
          "connectTimeout" in code and "readTimeout" in code and "catch (e: Exception)" in code)

    # ------------------------------------------------------------------
    print(u"\n== ⑥ 接线：屏间只经 ChatViewModel（wsPreview → wsDetail） ==")
    screen = read(SCREEN)
    vm = read(VM)
    tree = ""
    for base, _dirs, files in os.walk(APP):
        for fn in sorted(files):
            if fn.endswith(".kt"):
                tree += strip_comments(read(os.path.join(base, fn))) + "\n"
    w = wiring_problems(strip_comments(screen), strip_comments(vm), tree)
    check(u"单击选中并打开详情 / 关闭 / 高亮保留 / 旧预览退场", not w, u"；".join(w[:4]))
    check(u"两列（角色卡 / 世界卡）都能打开详情",
          len(re.findall(r"wsDetail = WsCardDetail\(", screen)) == 2)
    check(u"关闭详情不清选中（选中只由 wsLocalType / wsLocalIdx 决定）",
          "wsDetail = null" in screen and "wsLocalIdx = -1" in screen)
    check(u"底部四个动作复用工坊现有回调（不新增后端接口）",
          "acts.importCardLauncher.launch(" in code and "acts.wsExportLauncher.launch(" in code and
          "acts.uploadLocal()" in code and "Workshop.deleteLocal(" in code and
          "acts.refreshLocal()" in code)

    # ------------------------------------------------------------------
    print(u"\n== ⑦ 反向验证（把每条弄坏一次，判定器必须红） ==")
    cases = [
        (u"塞一条 Color(0xFF123456)", code + u"\nval seeded = Color(0xFF123456)\n",
         color_problems, code),
        (u"删掉 list 分区的排版（mode=list 漏掉）",
         code.replace("MODE_LIST -> sec.blocks.forEach { blk -> if (blk is CardListBlock) CdList(blk) }", ""),
         lambda t: section_problems(t, fields), code),
        (u"分区标题改回硬编码（不读 CardFields.sectionLabel）",
         code.replace("CardFields.sectionLabel(sec.id)", u'"固定标题"'), section_problems_json(fields), code),
        (u"写死一个分区 id 字面量", code + u'\nval seededSec = "greeting"\n',
         section_problems_json(fields), code),
        (u"删掉世界书那一块", code.replace("if (world.isNotEmpty()) CdWorldBook(world)", ""),
         extras_problems, code),
        (u"世界书改成默认展开", code.replace(
            "var open by remember(entries) { mutableStateOf(false) }",
            "var open by remember(entries) { mutableStateOf(true) }"), extras_problems, code),
        (u"删掉文件块", code.replace("CdFileInfo(d)", ""), extras_problems, code),
        (u"删掉头像的读法与回退", code.replace('fields?.get("avatar")', u'"x"'),
         avatar_problems, code),
        (u"改成裸 AlertDialog", code + u"\nAlertDialog(onDismissRequest = {}, text = {})\n",
         dialog_problems, code),
        (u"塞一句 JsonS.stringify（JSON 原文直出）",
         code + u"\nval seededJson = JsonS.stringify(v)\n", json_leak_problems, code),
        (u"把文件撑到 401 行", code + u"\n// pad\n" * (LINE_BUDGET + 1),
         budget_problems, code),
    ]
    for name, bad, judge, before in cases:
        if not check(u"…%s：样本确实变了" % name, bad != before, u"替换没生效（字符串对不上）"):
            continue
        probs = judge(bad)
        check(u"…%s → 红" % name, bool(probs), u"%s" % (probs[:2] or u"居然还是绿的"))

    print("\n" + "=" * 68)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CARD_DETAIL_ANDROID_OK")
    return 1 if FAIL else 0


def section_problems_json(fields):
    """把 section_problems 的第二参绑死（反向验证那几个 lambda 要用）。"""
    return lambda t: section_problems(t, fields)


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌
