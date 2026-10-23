# -*- coding: utf-8 -*-
"""net_paths —— 服务端的路径与运行配置（从 net.py 拆出的第 1 层）。

只放**无状态**的东西：应用根目录、数据目录、各资源子目录、索引/设置文件路径。
不放锁、不放计数器、不放 Flask app —— 这样它谁都不依赖，能被任何模块安全 import
（上一轮把带状态的函数一起搬，导致限流/解压行为坏掉，就是踩了这个）。

环境变量（与老版本一致，不新增）：
    WORKSHOP_DATA_DIR   数据根目录（双子里每台指不同目录）
"""
from __future__ import annotations

import os
import sys


def _app_root() -> str:
    """应用根目录：源码运行用 __file__；冻结为 EXE 后用 sys.executable，
    保证 net_server.exe 能定位旁边的 config.json / workshop_data。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# 数据存<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌储目录
# 双子里每台要存自己的盘：允许用 WORKSHOP_DATA_DIR 指到不同目录
DATA_DIR = os.environ.get("WORKSHOP_DATA_DIR") or os.path.join(_app_root(), "workshop_data")
CARDS_DIR = os.path.join(DATA_DIR, "cards")
WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
PLUGINS_DIR = os.path.join(DATA_DIR, "plugins")
PACKS_DIR = os.path.join(DATA_DIR, "packs")
SAVES_DIR = os.path.join(DATA_DIR, "saves")
SYNC_SETTINGS_FILE = os.path.join(DATA_DIR, "sync_settings.json")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")


def ensure_dirs() -> None:
    """确保数据目录都在（幂等）。"""
    for d in (DATA_DIR, CARDS_DIR, WORLDS_DIR, PLUGINS_DIR, PACKS_DIR, SAVES_DIR):
        os.makedirs(d, exist_ok=True)


# 导入即建目录（与原 net.py 的行为一致：模块加载时就把目录准备好）
ensure_dirs()
