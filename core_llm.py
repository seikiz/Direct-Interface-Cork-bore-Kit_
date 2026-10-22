# -*- coding: utf-8 -*-
"""core_llm.py —— 模型客户端的懒加载与公共依赖（从 DICK_core.py 拆出）。

为什么要拆：这些是"发请求"这条路的地基（openai 懒加载、httpx 回退、style_guard），
被 `_fetch_response` / `_build_client` / `_fetch_auto_turn` 等一大组方法共用。
留在 1794 行的 DICK_core 里，拆网络那组方法就没法搬（循环 import）。

兼容：DICK_core 继续 `from core_llm import ...`，
所以 `DICK_core._ensure_openai` / `DICK_core.httpx` 这些老引用都还在。
"""
from __future__ import annotations

# openai 改成【懒加载】：它在顶层 imp<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ort 要 760ms，而启动时根本用不到 ——
# 对比一下：全部插件加载才 70ms。用户不开对话就永远不需要它。
# 占位异常类保证 except (APIConnectionError, APITimeoutError) 在导入前也合法（只是暂时抓不到）。


class _OpenAIUnavailable(Exception):
    """openai 尚未导入时的占位异常类型（导真库后这两个名字会被替换成真类）"""
    pass


OpenAI = None
APIConnectionError = _OpenAIUnavailable
APITimeoutError = _OpenAIUnavailable


def _ensure_openai():
    """第一次真要发请求时才导入 openai，返回 OpenAI 类"""
    global OpenAI, APIConnectionError, APITimeoutError
    if OpenAI is None:
        try:
            from openai import OpenAI as _OpenAI
            from openai import APIConnectionError as _ConnErr
            from openai import APITimeoutError as _TimeoutErr
        except Exception as e:
            raise RuntimeError("缺少 openai 库，无法调用模型：" + str(e)) from e
        OpenAI, APIConnectionError, APITimeoutError = _OpenAI, _ConnErr, _TimeoutErr
    return OpenAI


try:
    import httpx
except Exception:
    try:
        # 本机（及打包环境）只有 httpx2，openai 3.x 用的也是它；
        # 少了这个回退，下面 set_proxy 会静默失效。
        import httpx2 as httpx
    except Exception:
        httpx = None

try:
    from style_guard import style_guard as _style_guard
except Exception:
    _style_guard = None
