# -*- coding: utf-8 -*-
"""
前端 -> 后端 接口名一致性校验。

为什么值得单独测：
    JS 里写 pywebview.api.foo(...)，后端没有 api_foo，
    pywebview 不会报错，只是这个调用静默失效 ——
    用户点按钮没反应，日志里也什么都没有。这类错只能靠静态比对抓。

反过来也查：后端有 api_bar，前端从不调用 → 多半是「功能做完了但没接上 UI」
（加密备份之前就是这个状态：后端齐全、界面没入口）。

跑法：utau_env\\Scripts\\python.exe tests\\test_js_api_binding.py
"""

import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


# 这些 api_ 是给别的入口用的（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌侧车脚本/CLI），前端不调用属正常
FRONTEND_OPTIONAL = {
    "api_run", "api_main",
}


def front_end():
    """前端语料：页面 + 屏片段 + 屏模块。

    2026-11 阶段3 起，加密备份/多存档/世界书/创意工坊这几屏的 DOM 与 JS 都搬出了
    index.html（`web/screens/<名字>.html` + `web/js/screens/<名字>.js`）。
    只读 index.html 的话，"元素存在吗 / 接口接上了吗"会成片误报 —— 那是搬家的正常结果，
    不是回归。所以语料必须跟着扩到整棵前端。
    """
    parts = [io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()]
    for sub in ("screens", os.path.join("js")):
        d = os.path.join(ROOT, "web", sub)
        if not os.path.isdir(d):
            continue
        for base, _dirs, files in os.walk(d):
            for fn in sorted(files):
                if fn.endswith((".html", ".js")):
                    parts.append(io.open(os.path.join(base, fn), encoding="utf-8").read())
    return "\n".join(parts)


def load_app_class():
    path = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
    spec = importlib.util.spec_from_file_location("dick_app_api_check", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dick_app_api_check"] = mod
    spec.loader.exec_module(mod)
    return mod.HtmlApp


def main():
    print("=" * 56)
    print("前端 / 后端 接口名一致性")
    print("=" * 56)

    with io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as f:
        html = f.read()
    front = front_end()          # 页面 + 屏片段 + 屏模块（阶段3 之后"前端"是整棵）

    # 前端调用了哪些 api_xxx
    # 末尾那个 (?![\w*]) 是给文档字符串让路的：屏模块的文件头注释里会写
    # `pywebview.api.backup_*` 这种"一家子接口"的说法，通配符不是调用 —— 不算进去，
    # 否则会把 backup_ / go_ 这类半截名字当成缺失的后端方法。
    called = set(re.findall(r"pywebview\.api\.([A-Za-z_][A-Za-z0-9_]*)(?![\w*])", front))
    print(f"\n前端调用 {len(called)} 个接口")

    cls = load_app_class()
    backend = {n[len("api_"):] for n in dir(cls) if n.startswith("api_")}
    print(f"后端提供 {len(backend)} 个接口")

    print("\n== 1. 前端调用的接口后端必须存在 ==")
    missing = sorted(called - backend)
    for m in missing:
        check(f"后端有 api_{m}", False, "前后端名字对不上 → 调用会静默失效")
    if not missing:
        check(f"全部 {len(called)} 个调用都有对应后端实现", True)

    print("\n== 2. 本次新增的加密备份接口必须接上 ==")
    for name in ("backup_password_check", "export_backup_encrypted",
                 "import_backup_encrypted", "backup_make_password"):
        check(f"后端有 api_{name}", name in backend)
        check(f"前端调用了 {name}", name in called,
              "后端做完了但界面没入口")

    print("\n== 3. 前端 UI 元素必须存在 ==")
    # 备份屏的 DOM 在阶段3 搬到了 web/screens/bk.html，所以查 front（整棵前端），不是 html。
    for el in ("btnBackup", "backupModal", "bkPw", "bkPw2", "bkExport",
               "bkRestore", "bkCancel", "bkStatus", "bkPwMsg", "bkGen",
               "bkGenHint", "bkWarn"):
        check(f"存在元素 #{el}", ('id="%s"' % el) in front)

    print("\n== 4. 不得使用原生弹窗（深色主题下会闪白框）==")
    # 只看加密备份的 JS 区段。注意不能用 find("🔐 加密备份")：
    # 侧栏按钮文本也含这几个字，且在文件更前面，会切出一大段无关的老代码。
    # 阶段3 起这段在 web/js/screens/bk.js 里，所以同样查 front。
    marker = "// ================= 🔐 加密备份 ================="
    i = front.find(marker)
    check("能找到加密备份 JS 区段", i > 0)
    seg = front[i: i + 6000] if i > 0 else ""
    for bad in ("alert(", "confirm(", "prompt("):
        hit = re.search(r"(?<![A-Za-z_.])" + re.escape(bad), seg)
        check(f"加密备份区段不用 {bad}", hit is None, "应改用主题化弹窗")
    check("区段里确实有备份逻辑（防切空）", "bkExport" in seg and "bkRestore" in seg)

    print("\n== 5. 后端孤儿接口（做完了没接 UI）==")
    # 有些接口是通过字符串分发的，例如 goAct('go_undo', '悔棋')：
    # 名字以字符串形式出现在前端，正则抓不到 pywebview.api.xxx 这种直接调用。
    # 所以判据是「名字在前端完全不出现」才算真孤儿，否则会大量假阳性。
    # （阶段3 起"前端"是 index.html + 屏片段 + 屏模块：孤儿接口可能只被搬走的屏用着。）
    orphans = []
    for name in sorted(backend - called - FRONTEND_OPTIONAL):
        if re.search(r"['\"]" + re.escape(name) + r"['\"]", front):
            continue
        orphans.append(name)
    print(f"     {len(orphans)} 个后端接口前端完全没提到：")
    for o in orphans:
        print(f"       - {o}")
    if not orphans:
        print("       （无）")

    print("\n== 6. 备份相关接口接上了就不该留孤儿 ==")
    for name in ("export_backup_encrypted", "import_backup_encrypted"):
        check(f"{name} 不是孤儿", name not in orphans)

    print("\n" + "=" * 56)
    print(f"通过 {PASS} / 失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
