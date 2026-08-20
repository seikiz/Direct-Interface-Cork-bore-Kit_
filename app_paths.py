# ============================================================
#   app_paths.py - 统一路径解析
#
#   兼容两种运行方式：
#   1. 源码运行（python 主程序.py）→ 数据目录 = 工程根目录
#   2. 冻结运行（PyInstaller 打包的 exe）→ 数据目录 = exe 所在目录
#      （便携式设计：exe 放哪，saves/worlds/plugins/设置 就跟着建在哪；
#        打包目录 _internal 只作为只读的内置插件来源）
# ============================================================

import os
import sys


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def get_base_dir():
    """应用数据根目录"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_bundled_dir():
    """PyInstaller 打包目录（只读，随 exe 分发的资源所在处）"""
    return getattr(sys, "_MEIPASS", None)


def get_plugin_dirs():
    """插件目录列表：
    [0] exe/工程旁的 plugins（可写，用户安装新插件落在这里）
    [1] 打包内置 plugins（只读，随 exe 分发的插件；源码运行时无此项）
    """
    dirs = []
    base = get_base_dir()
    dirs.append(os.path.join(base, "plugins"))
    if is_frozen():
        bundled = get_bundled_dir()
        if bundled:
            p = os.path.join(bundled, "plugins")
            if os.path.isdir(p) and os.path.normcase(p) != os.path.normcase(dirs[0]):
                dirs.append(p)
    return dirs


def get_data_dir(name):
    """数据目录（saves/worlds/memory/plugin_settings 等），自动创建"""
    d = os.path.join(get_base_dir(), name)
    os.makedirs(d, exist_ok=True)
    return d


def get_config_file(name="config.json"):
    """配置文件路径（exe/工程根目录下）"""
    return os.path.join(get_base_dir(), name)
