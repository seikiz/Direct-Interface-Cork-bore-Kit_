# -*- coding: utf-8 -*-
"""提示分级：忙 / 提示 / 错误。

为什么单独一个模块：这才是"警报体系"的**唯一真相**。
以前那句“忙”的提示走的是错误通道（on_error），被壳子画成红叉气泡、
还存进对话历史 —— 用户连点几次就刷屏。忙是可重试的瞬时状态，不是错误。

分级：
    busy  → 轻提示（toast），去重，**不进对话、不进历史**
    error → 错误气泡（带可行动指引），进对话
"""

BUSY_TEXT = "正在处理中，请稍候"
BUSY_DEDUPE_SECONDS = 1.5      # 同一句"忙"提示的最短间隔


def notify_busy(on_busy=None, on_error=None):
    """忙碌通知：优先走 on_busy（轻提示）；没给就退回 on_error（向后兼容）。"""
    if on_busy is not None:
        try:
            on_busy(BUSY_TEXT)
        except Exception:
            pass
        return
    if on_error is not None:
        on_error(BUSY_TEXT)


def should_show(last_ts, now, window=BUSY_DEDUPE_SECONDS):
    """去重判定：离上次提示不足 window 秒就不弹。纯函数，便于单测。"""
    try:
        return (now - float(last_ts)) >= float(window)
    except (TypeError, ValueError):
        return True


def busy_toast(app, msg=""):
    """在壳层弹一条"忙"的轻提示（去重、不进对话、不进历史）。

    app 只需要两个东西：`evaluate_js(js)` 与可写的 `_last_busy_ts`。
    为什么放在这里而不是壳层：壳层与核心有行数棘轮（只许降），
    提示分级本身也不属于"界面装配"，它属于这套提示约定。
    """
    import time as _t
    now = _t.time()
    last = getattr(app, "_last_busy_ts", 0.0)
    if not should_show(last, now):
        return False
    app._last_busy_ts = now
    text = msg or "上一轮还在跑"
    try:
        app.evaluate_js("window.DICK_STATUS && window.DICK_STATUS(%r)" % text)
    except Exception:
        pass
    return True
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌


def set_status(app, text):
    """把一行状态写到输入栏上方（空串 = 收起）。忙/生成中都走这里。"""
    try:
        app.evaluate_js("window.DICK_STATUS && window.DICK_STATUS(%r)" % (text or ""))
    except Exception:
        pass
