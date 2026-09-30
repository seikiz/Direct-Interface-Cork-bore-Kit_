# -*- coding: utf-8 -*-
"""
ui_root.py —— 插件共用的【隐藏 Tk 根窗口】

为什么需要这个文件：
  插件里写 `CTkToplevel()`（不传 master）时，如果此刻还没有根窗口，
  tkinter 会**自作主张造一个可见的、标题为 'tk' 的空窗口**。
  插件自己都记得 withdraw()，这个自动生成的没人管 —— 于是：
    ① 用户运行时会看到一个莫名其妙的空 TK 窗口；
    ② 那个窗口关掉 = Tk 根被销毁 = 该进程里所有 Tk 组件一起崩，
       表现就是「关掉 TK 窗口，整个程序也退出了」。

解决思路（把 UI 生命周期收归宿主，插件只借用）：
  宿主在加载插件之前就建好一个 **隐藏** 的根窗口并登记为默认根，
  插件随后建 CTkToplevel() 就会挂到它下面，不会再冒出空窗口；
  同时把 WM_DELETE_WINDOW 改成「只隐藏、不销毁」，关不掉、也就带不走程序。
"""

import threading

_LOCK = threading.Lock()
_ROOT = None
_MODE = None          # "customtkinter" / "tk"


def ensure_root():
    """取得（必要时创建）隐藏的共用根窗口。失败返回 None，绝不让调用方崩。"""
    global _ROOT, _MODE
    if _ROOT is not None:
        return _ROOT
    with _LOCK:
        if _ROOT is not None:
            return _ROOT
        root = None
        try:
            import customtkinter as ctk
            root = ctk.CTk()
            _MODE = "customtkinter"
        except Exception:
            try:
                import tkinter as tk
                root = tk.Tk()
                _MODE = "tk"
            except Exception:
                _ROOT = None
                return None
        try:
            root.withdraw()                      # 关键：一建出来就藏起来
        except Exception:
            pass
        try:
            root.title("DICK · 插件 UI 根窗口（隐藏）")
        except Exception:
            pass

        def _keep_alive():
            """用户（或误操作）想关它 → 只隐藏，不销毁，绝不连累主程序"""
            try:
                root.withdraw()
            except Exception:
                pass

        try:
            root.protocol("WM_DELETE_WINDOW", _keep_alive)
        except Exception:
            pass
        _ROOT = root
        return _ROOT


def root():
    """已创建的根窗口；没创建过返回 None（不会触发创建）"""
    return _ROOT


def mode():
    return _MODE


def is_alive():
    """根窗口还在不在（关掉后 Tk 调用会报 TclError，插件可据此判断）"""
    r = _ROOT
    if r is None:
        return False
    try:
        r.winfo_exists()
        return True
    except Exception:
        return False
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌