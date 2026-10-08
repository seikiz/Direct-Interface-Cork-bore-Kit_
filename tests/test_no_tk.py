# -*- coding: utf-8 -*-
"""Tk 退役审计：确保 Tcl/Tk 不会再溜回项目里。

为什么需要
----------
2026-10 清掉 Tk 时代遗产（三个 Tk 插件 + ui_root/ui_fonts + 隐藏 Tk 根窗口）。
那次清理的直接收益：每次发布少 3.5 MB 的 tcl86t.dll/tk86t.dll，也少一类"隐形窗口被关掉
连带整个程序退出"的故障。但这种清理最怕的是**慢慢又长回来**：某个插件图省事
`from tkinter import filedialog`，于是打包脚本又得把 Tcl/Tk 收进去 —— 而且不报错，只是包变大、
启动变脆。所以这里把它钉死：
  ① 项目源码（archive/ 之外）不许 import tkinter / customtkinter / ui_root / ui_fonts
  ② 插件要界面必须走 host_ui（宿主通道），且宿主确实接了
  ③ 打包 spec 必须【显式排除】Tcl/Tk，构建自检不许再要求 ui_root/ui_fonts
跑法：python tests/test_no_tk.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCHIVE = os.path.join(ROOT, "archive")

BANNED_MODULES = ("tkinter", "customtkinter", "darkdetect", "ui_root", "ui_fonts")
IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(%s)\b" % "|".join(BANNED_MODULES), re.M)

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


def project_py():
    for dp, dirs, fs in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("utau_env", "__pycache__", "node_modules",
                                                ".git", "dist", "build", "_phone",
                                                "tavern-installer")]
        if os.path.abspath(dp).startswith(ARCHIVE):
            continue
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(dp, f)


def read(p):
    try:
        return io.open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def main():
    print("=" * 62)
    print(u"Tk 退役审计（不许 Tcl/Tk 溜回来）")
    print("=" * 62)

    print(u"\n== ① 项目源码（archive/ 之外）不许 import Tk 系 ==")
    hits = []
    n = 0
    for p in project_py():
        n += 1
        src = read(p)
        for m in IMPORT_RE.finditer(src):
            line = src[:m.start()].count("\n") + 1
            hits.append("%s:%d  %s" % (os.path.relpath(p, ROOT), line, m.group(0).strip()))
    check(u"扫描 %d 个 .py，没有 Tk 系 import" % n, not hits, u"命中：\n      " + u"\n      ".join(hits[:8]))

    print(u"\n== ② 插件要界面必须走 host_ui ==")
    check(u"host_ui.py 存在", os.path.isfile(os.path.join(ROOT, "host_ui.py")))
    host = read(os.path.join(ROOT, "host_ui.py"))
    for fn in ("ask_file", "ask_save", "notify", "set_ui", "capabilities"):
        check(u"host_ui 提供 %s" % fn, ("def %s(" % fn) in host)
    entry = read(os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"))
    check(u"主程序接上了宿主通道（_install_host_ui）",
          "_install_host_ui" in entry and "host_ui.set_ui(" in entry)
    check(u"接入发生在 load_plugins 之前（否则插件 on_load 用不上）",
          entry.find("self._install_host_ui()") < entry.find("self.plugin_manager.load_plugins()"))
    pm = read(os.path.join(ROOT, "plugin_manager.py"))
    # 只看"真的 import / 真的调用"，注释里提到 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌Tk 是可以的（那段注释正是在解释为什么不再需要它）
    check(u"plugin_manager 不再 import ui_root，也不再建隐藏 Tk 根窗口",
          not re.search(r"^\s*import\s+ui_root", pm, re.M)
          and "ensure_root" not in pm
          and not re.search(r"^\s*(?:import|from)\s+tkinter", pm, re.M))

    print(u"\n== ③ 打包 spec 必须显式排除 Tcl/Tk ==")
    spec = read(os.path.join(ROOT, "DICK_HTML.spec"))
    check(u"excludes 里有 tkinter", "'tkinter'" in spec and "excludes=" in spec)
    check(u"excludes 里有 _tkinter / customtkinter",
          "'_tkinter'" in spec and "'customtkinter'" in spec)
    check(u"hiddenimports 里不再声明 tkinter", "'tkinter.filedialog'" not in spec
          and "'tkinter.messagebox'" not in spec)
    check(u"不再收集 customtkinter 数据", "collect_all('customtkinter')" not in spec
          and "'customtkinter', 'cryptography'" not in spec)
    check(u"不再打包 ui_root/ui_fonts", "('ui_root.py'" not in spec and "('ui_fonts.py'" not in spec)
    check(u"打包 host_ui.py（插件要用）", "('host_ui.py'" in spec)

    print(u"\n== ④ 构建自检不许再要求 ui_root/ui_fonts ==")
    br = read(os.path.join(ROOT, "build_release.py"))
    check(u"必需清单里没有 ui_root/ui_fonts",
          u'"ui_root.py", "插件共用隐藏 Tk 根窗口"' not in br and u'"ui_fonts.py", "插件字体"' not in br)
    check(u"必需清单里改要求 host_ui.py", '"host_ui.py"' in br)

    print(u"\n== ⑤ 退役文件确实离开了运行目录、且被归档 ==")
    for f in ("ui_root.py", "ui_fonts.py", "workshop.py", "creator_wizard.py",
              "generic_plugin_ui.py", "role_manager.py"):
        check(u"根目录不再有 %s" % f, not os.path.isfile(os.path.join(ROOT, f)),
              u"还在根目录")
    for f in ("modern_ui_plugin.py", "pluginsimage_upload_plugin.py",
              "worldbook_editor_plugin.py"):
        check(u"plugins/ 不再有 %s" % f,
              not os.path.isfile(os.path.join(ROOT, "plugins", f)), u"还在 plugins/")
    arch = os.path.join(ARCHIVE, "tk_legacy")
    check(u"归档目录存在且有内容", os.path.isdir(arch) and len(os.listdir(arch)) >= 9,
          str(os.listdir(arch) if os.path.isdir(arch) else "缺失"))

    print(u"\n== ⑥ 核心插件名单不再含已退役的名字 ==")
    check(u"CORE_UI_PLUGINS 里没有「现代界面」",
          '"现代界面"' not in entry.split("CORE_UI_PLUGINS")[1][:120] if "CORE_UI_PLUGINS" in entry else False)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("NO_TK_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
