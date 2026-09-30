# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   html_app.py - 兼容桥接层
#
#   入口文件已由 html_app.py 更名为 Direct-Interface Cork-bore Kit.py。
#   保留本模块名，仅供历史测试 / 其它脚本 continue 引用：
#     from html_app import HtmlApp, BASE_DIR
#
#   核心：让 `html_app.BASE_DIR = <tmp>` 真正重定向数据目录。
#   HTML 实现里 HtmlApp.__init__ 从运行时 app_paths.get_base_dir() 解析数据目录，
#   因此这里通过【把本模块的类换成 __setattr__ 子类】来拦截 BASE_DIR 赋值，
#   并同步 monkeypatch app_paths.get_base_dir，使后续 HtmlApp() 落到 <tmp>。
#   这是唯一能可靠拦截 `module.attr = x` 的机制（模块体里的 __setattr__ 无效果）。
# ============================================================

import sys as _sys
import importlib as _importlib

_ENTRY = "Direct-Interface Cork-bore Kit"
_M = _importlib.import_module(_ENTRY)
import app_paths as _ap

# ---- 显式导出常用符号（测试用） ----
HtmlApp = _M.HtmlApp
ROLE_FIELDS = _M.ROLE_FIELDS
WORLD_PARAMS = _M.WORLD_PARAMS
main = _M.main

_THIS = _sys.modules[__name__]

# ---- 用一个子类覆盖 __setattr__ / __getattr__ 来拦截 BASE_DIR 读写 ----
class _ModuleWithBaseDir(type(_THIS)):  # type: ignore[misc]
    def __setattr__(cls, name, value):
        if name == "BASE_DIR":
            # 重定向数据目录：同步 monkeypatch app_paths.get_base_dir
            _ap.get_base_dir = (lambda v: lambda: v)(value)
            return
        super().__setattr__(name, value)

    def __getattr__(cls, name):
        if name == "BASE_DIR":
            return _ap.get_base_dir()
        if hasattr(_M, name):
            return getattr(_M, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 替换本模块的类，使 `html_app.BASE_DIR = x` 走上面的 __setattr__
_THIS.__class__ = _ModuleWithBaseDir  # type: ignore[assignment]
