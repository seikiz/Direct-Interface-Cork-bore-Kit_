# -*- coding: utf-8 -*-
"""shell_util.py —— 壳层与各 mixin 共用的最小公共层。

只放"两边都要用、且没有任何依赖"的东西：常量 + 纯函数。
拆出它的原因：`shell_ws.py`（从 Kit.py 搬出的 28 个工坊方法）要用
`tree_ts_of` 和几个常量，而 Kit.py 又 import shell_ws —— 想让两边都能用，
只能把它们放到一个谁都不依赖的模块里（否则就是循环 import）。

规矩：这个文件**不许 import 项目内任何模块**（只许标准库）。
"""
from __future__ import annotations

import app_paths

BASE_DIR = app_paths.get_base_dir()

# 工坊默认服务器<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（可在设置里改）
DEFAULT_WS_SERVER = "http://154.94.226.240:8080"

XFER_MIN_INTERVAL_MS = 500      # 每设备两次传输的最小间隔（服务器下发优先）
XFER_MAX_RETRY = 3              # 429 退避重试上限（超过就报"链路限流"）


def tree_ts_of(data):
    """存档里的「进度时间戳」—— 同一件东西，两端键名不一样：
         电脑端写 `_tree_ts`，安卓端写 `tree_ts`（见 DICK-Android 的 Model.kt）。
    跨设备"后写胜"要拿它比新旧，所以**两边都得认**：只认自己那一个键的话，
    从另一端同步/导入过来的存档会被当成"没有进度"，于是随便一个更旧的服务器版本都能盖上去。
    读取侧兼容两种键（不新增/不改写任何字段）；写回时仍按各自的老键写。
    """
    if not isinstance(data, dict):
        return ""
    return str(data.get("_tree_ts") or data.get("tree_ts") or "")
