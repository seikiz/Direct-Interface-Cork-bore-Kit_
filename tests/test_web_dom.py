# -*- coding: utf-8 -*-
"""Web 前端静态审计：JS 引用的元素/函数必须真的存在。

为什么需要这个
--------------
"JS 里引用了不存在的元素" 这类 bug 点下去就报错，但静态看不出问题、
跑测试也发现不了 —— 只有用户点到那个按钮才知道。

本项目已经因为这一类错误翻车三次：
  · 事件进度面板的关闭按钮调了不存在的 closeModal()
  · 记忆调试面板的 JS 写好了，但 HTML 元素从来没加进去
  · 战斗冒险模板写了 nrBattleMech，实际元素叫 nrBattleMechAttrs

所以把审计固化成测试。这类"琐碎但要一条条对"的活正是不该靠人记的。

跑法：utau_env\\Scripts\\python.exe tests\\test_web_dom.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HTML = os.path.join(ROOT, "web", "index.html")

# 运行时才创建的元素（setAttribute('i<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌d', ...) / innerHTML 里生成），
# 静态看不到，但确实存在。每加一个都要写明理由。
DYNAMIC_IDS = {
    "galConn": "GAL 连线用的 SVG 是运行时 setAttribute('id','galConn') 建的",
}

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [OK] %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s  %s" % (name, detail))


def main():
    print("=" * 62)
    print("Web 前端静态审计")
    print("=" * 62)
    with io.open(HTML, encoding="utf-8") as f:
        html = f.read()

    print("\n== ① JS 引用的元素 id 必须存在 ==")
    used = sorted(set(re.findall(r"""getElementById\(['"]([A-Za-z_][A-Za-z0-9_]*)['"]\)""", html)))
    missing = [u for u in used
               if ('id="%s"' % u) not in html
               and ("id='%s'" % u) not in html
               and u not in DYNAMIC_IDS]
    for m in missing:
        check("元素 #%s 存在" % m, False, "JS 引用了但 HTML 里没有 → 点到就报错")
    if not missing:
        check("全部 %d 个被引用的 id 都有对应元素" % len(used), True)
    print("        被引用 %d 个；运行时动态创建的（已登记）：%s"
          % (len(used), "、".join(DYNAMIC_IDS.keys()) or "无"))

    print("\n== ② 内联 onclick 调用的函数必须已定义 ==")
    handlers = set()
    for m in re.finditer(r"""on(?:click|change|input|mousedown|mouseup)\s*=\s*["']([^"']+)["']""", html):
        code = m.group(1)
        # 只认【裸函数名】调用：前面不能是 '.'。否则会把
        # document.getElementById(...) / this.classList.remove(...) 这类
        # 方法调用也当成裸函数，报一堆假阳性（第一版就这么错的）。
        for fn in re.findall(r"(?<![.\w$])([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", code):
            if fn in ("this", "event", "return", "if", "for", "while", "typeof"):
                continue
            handlers.add(fn)
    BUILTIN = {"alert", "confirm", "prompt", "parseInt", "parseFloat", "String",
               "Number", "Boolean", "Array", "Object", "JSON", "Math",
               "setTimeout", "encodeURIComponent", "decodeURIComponent"}
    undef = []
    for fn in sorted(handlers - BUILTIN):
        pat = (r"function\s+" + re.escape(fn) + r"\s*\("
               r"|(?:var|let|const)\s+" + re.escape(fn) + r"\s*="
               r"|" + re.escape(fn) + r"\s*=\s*function")
        if not re.search(pat, html):
            undef.append(fn)
    for fn in undef:
        check("函数 %s 已定义" % fn, False, "内联事件调用了但找不到定义")
    if not undef:
        print("        检查了 %d 个被内联调用的裸函数名" % len(handlers - BUILTIN))
        check("内联事件调用的函数都有定义", True)

    print("\n== ③ 不该再有原生弹窗（深色主题下会闪白框）==")
    # 只审计本次新增的三个面板，老代码不在此列（避免大面积假阳性）
    for name, seg_marker in (
        ("事件进度面板", "function evOpenProgress"),
        ("记忆调试面板", "function memDebugDraw"),
        ("时间流速表盘", "function dialRender"),
    ):
        i = html.find(seg_marker)
        if i < 0:
            check("%s 找得到" % name, False, seg_marker)
            continue
        seg = html[i:i + 4000]
        # 只看到下一个顶层 function 为止，避免切到别人的代码
        nxt = seg.find("\nfunction ", 10)
        if nxt > 0:
            seg = seg[:nxt]
        hits = [w for w in ("alert(", "confirm(") if w in seg]
        check("%s 不用原生弹窗" % name, not hits, "发现 " + "、".join(hits))

    print("\n== ④ 本次新增的面板必须齐全（HTML + JS + 后端三件套）==")
    PANELS = (
        ("事件进度", "evProgressModal", "evOpenProgress", "api_event_progress"),
        ("记忆调试", "memDebugModal", "memDebugDraw", "api_memory_debug"),
        ("时间表盘", "timeDialModal", "dialRender", "api_get_time_scale"),
    )
    for label, modal_id, js_fn, py_api in PANELS:
        check("%s：有 #%s" % (label, modal_id), ('id="%s"' % modal_id) in html)
        check("%s：有 %s()" % (label, js_fn), ("function " + js_fn) in html)
        check("%s：JS 调了 %s" % (label, py_api.replace("api_", "")),
              ("pywebview.api." + py_api.replace("api_", "")) in html)
        # 后端方法（pywebview 约定：前端去掉前缀，后端带前缀）
        py = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
        with io.open(py, encoding="utf-8") as f:
            kit = f.read()
        check("%s：后端有 %s" % (label, py_api), ("def %s(" % py_api) in kit)

    print("\n== ⑤ 时间表盘：对数换算必须和 Python 侧一致 ==")
    sys.path.insert(0, ROOT)
    import time_scale as TS
    m = re.search(r"TIME_DIAL\.min\s*=\s*r\.min\s*\|\|\s*(\d+)", html)
    check("前端默认下限和 Python 一致（%d）" % TS.MIN_SCALE,
          m is not None and int(m.group(1)) == int(TS.MIN_SCALE),
          m.group(1) if m else "没找到")
    check("前端 clamp 区间读的是后端给的 min/max（不写死）",
          "TIME_DIAL.min = r.min" in html and "TIME_DIAL.max = r.max" in html)
    # 一轮折算口径必须一致，否则表盘显示和后端描述会打架
    check("前端一轮折算用 30 秒（和 Python 一致）",
          "s * 30" in html and TS.ROUND_SECONDS == 30.0,
          "python ROUND_SECONDS=%s" % TS.ROUND_SECONDS)
    # 对数刻度：往返换算要能对上
    for s in (10, 60, 720, 3600, 86400, 604800):
        back = TS.pos_to_scale(TS.scale_to_pos(s))
        check("对数往返 %d 误差 < 1e-6" % s, abs(back - s) < 1e-6,
              "%.6f" % back)

    print("\n== ⑥ 顶层同名声明不得互相覆盖 ==")
    # 两个顶层 function 同名时，后声明的会静默覆盖前一个：调用点看着都在，功能却没了，
    # 而且不报错。真踩过 —— Galgame 选项面板的 renderChoices 被记忆树「选项骨架」的同名函数
    # 覆盖，选项面板从此再也不刷新（且 treeList 非空时抛 TypeError）。
    m = re.search(r"<script>([\s\S]*?)</script>", html)
    src = m.group(1) if m else ""
    base = html[:m.start(1)].count("\n") if m else 0
    decl = {}
    for i, line in enumerate(src.split("\n"), 1):
        d = re.match(r"function\s+([A-Za-z_$][\w$]*)\s*\(", line)
        if not d:
            d2 = re.match(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*function", line)
            if d2:
                decl.setdefault(d2.group(1), []).append(("var", base + i))
            continue
        decl.setdefault(d.group(1), []).append(("function", base + i))
    dup = dict((k, v) for k, v in decl.items() if len(v) > 1)
    for name in sorted(dup):
        where = "、".join("%s@第%d行" % (kind, ln) for kind, ln in dup[name])
        check("顶层声明 %s 唯一" % name, False, "重复：%s（后者覆盖前者）" % where)
    if not dup:
        check("全部 %d 个顶层函数声明互不重名" % len(decl), True)

    print("\n" + "=" * 62)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
