# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   host_ui.py —— 插件向宿主要界面的唯一通道
#
#   为什么需要它（Tk 时代的教训）：
#     以前插件要个文件框就 `from tkinter import filedialog`，要个提示就
#     `messagebox.showinfo`，于是整个应用被迫背着 Tcl/Tk（每次发布 3.5 MB），
#     还得在启动时建一个隐藏 Tk 根，否则插件里 CTkToplevel() 会冒出可见空窗口、
#     而那个窗口被关掉会**连带整个程序退出**。HTML 版明明有原生界面，却要为这些
#     遗留窗口跑每秒一次的 Tk 轮询去补主题。
#     => 插件要界面，应该向【宿主】要，而不是自己拉一套 GUI 库。
#
#   用法（插件侧）：
#       import host_ui
#       path = host_ui.ask_file("选择酒馆卡", types=("卡片 (*.png;*.json)",))
#       if not path:
#           return "已取消"            # 无界面（服务端/测试/手机）时也返回 None
#       host_ui.notify("导入完成")
#
#   宿主侧（主程序启动时接一次）：
#       host_ui.set_ui(ask_file=..., ask_save=..., notify=...)
#
#   没接上宿主也不会炸：ask_* 返回 None、notify 打到控制台 —— 插件据此降级即可。
# ============================================================

_STATE = {
    "ask_file": None,
    "ask_save": None,
    "notify": None,
}


def set_ui(ask_file=None, ask_save=None, notify=None):
    """宿主接入点。传 None 表示保留原有实现（便于逐步接）。"""
    if ask_file is not None:
        _STATE["ask_file"] = ask_file
    if ask_save is not None:
        _STATE["ask_save"] = ask_save
    if notify is not None:
        _STATE["notify"] = notify


def clear_ui():
    """测试/退出时清掉（避免测试之间互相污染）。"""
    for k in _STATE:
        _STATE[k] = None


def capabilities():
    """当前接上了哪些能力（插件可据此决定要不要给按钮）。"""
    return {k: callable(v) for k, v in _STATE.items()}


def ask_file(title="选择文件", types=(), multiple=False):
    """要一个"打开文件"对话框。返回路径（multiple=True 时返回列表）或 None（取消/无界面）。"""
    fn = _STATE["ask_file"]
    if not callable(fn):
        return None
    try:
        return fn(title, tuple(types or ()), bool(multiple))
    except Exception as e:
        print("[host_ui] ask_file 失败：%s" % str(e)[:120])
        return None


def ask_save(title="保存到", default_name="", types=()):
    """要一个"保存文件"对话框。返回路径或 None。"""
    fn = _STATE["ask_save"]
    if not callable(fn):
        return None
    try:
        return fn(title, str(default_name or ""), tuple(types or ()))
    except Exception as e:
        print("[host_ui] ask_save 失败：%s" % str(e)[:120])
        return None


def ask_folder(title="选择文件夹"):
    """要一个"选目录"对话框（走 ask_file 的能力，宿主自己判断类型）。"""
    fn = _STATE["ask_file"]
    if not callable(fn):
        return None
    try:
        return fn(title, ("__folder__",), False)
    except Exception as e:
        print("[host_ui] ask_folder 失败：%s" % str(e)[:120])
        return None


def notify(text, speaker="插件", level="info"):
    """给用户一句提示（走聊天里的系统消息）。返回 True 表示宿主收下了。"""
    fn = _STATE["notify"]
    if not callable(fn):
        print("[host_ui] %s: %s" % (speaker, text))     # 无界面：退回控制台
        return False
    try:
        fn(str(text), str(speaker), str(level))
        return True
    except Exception as e:
        print("[host_ui] notify 失败：%s" % str(e)[:120])
        return False
