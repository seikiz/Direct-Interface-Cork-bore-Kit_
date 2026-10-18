# -*- coding: utf-8 -*-
"""kernel/paths.py —— 路径解析（从 app_paths.py 抽出来的最小实现，语义逐条对齐）

为什么不直接 import app_paths：
    内核只允许依赖**标准库**。app_paths 属于"壳层/数据目录"约定，一旦内核反过来
    import 它，依赖方向就倒了（kernel ← modules ← shells 变成了 kernel → shell 工具）。
    所以这里按 app_paths.py 的现有语义**抄一份最小实现**，并允许传入 base_dir：
      · 源码运行  → base_dir = 工程根目录
      · 冻结运行  → base_dir = exe 所在目录
      · 测试     → base_dir = 临时目录（由调用方显式传，不去猜）
    两份实现的口径必须一致：`tests/test_kernel.py` 里对着 app_paths 做了一次对拍。
"""

import os
import sys


def is_frozen():
    """是不是 PyInstaller 打包后的 exe（与 app_paths.is_frozen 同义）"""
    return bool(getattr(sys, "frozen", False))


def get_bundled_dir():
    """打包解包目录（只读）；源码运行时为 None"""
    return getattr(sys, "_MEIPASS", None)


def get_base_dir(base_dir=None):
    """数据根目录：显式给了就用给的，否则按 app_paths 的老规矩推。"""
    if base_dir:
        return os.path.abspath(base_dir)
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_data_dir(name, base_dir=None):
    """数据子目录（saves/worlds/...），不存在就建"""
    d = os.path.join(get_base_dir(base_dir), name)
    os.makedirs(d, exist_ok=True)
    return d


def get_config_file(name="config.json", base_dir=None):
    """配置文件路径（数据根目录下）"""
    return os.path.join(get_base_dir(base_dir), name)


def get_modules_dir(base_dir=None, explicit=None):
    """模块目录：显式优先，否则取「内核所在仓库」的 modules/。

    注意**不**取数据根目录下的 modules/：模块是要跟着代码走的，不是用户数据。
    打包时 DICK_HTML.spec 把 modules/ 作为 datas 拷进 _internal，于是
    base_dir（exe 旁）与代码目录（_MEIPASS）可能不是同一个 —— 后者优先。
    """
    if explicit:
        return os.path.abspath(explicit)
    bundled = get_bundled_dir()
    if bundled:
        p = os.path.join(bundled, "modules")
        if os.path.isdir(p):
            return p
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "modules")
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌