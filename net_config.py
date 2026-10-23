# -*- coding: utf-8 -*-
"""net_config —— 服务端运行配置（环境变量驱动，从 net.py 拆出）。

只有常量，没有状态；net.py 与 net_store.py 都从这里取，
避免"两边各读一次环境变量"导致值不一致。
"""
from __future__ import annotations

import os

API_KEY = os.environ.get("WORKSHOP_API_KEY", "").strip()
HOST = os.environ.get("WORKSHOP_HOST", "0.0.0.0")
PORT = int(os.environ.get("WORKSHOP_PORT", "5000"))
DEBUG = os.environ.get("WORKSHOP_DEBUG", "0") == "1"
READ_KEY = os.environ.get("WORKSHOP_READ_KEY", "0") == "1"
OPEN_UPLOAD = os.environ.get("WORKSHOP_OPEN_UPLOAD", "1") != "0"
RATE_PER_MIN = int(os.environ.get("WORKSHOP_RATE_PER_MIN", "120"))
RATE_PER_HOUR = int(os.environ.get("WORKSHOP_RATE_PER_HOUR", "10800"))
MIN_INTERVAL_MS = int(os.environ.get("WORKSHOP_MIN_INTERVAL_MS", "500"))
MAX_CONCURRENT = int(os.environ.get("WORKSHOP_MAX_CONCURRENT", "1"))
RELAY_ON = os.environ.get("WORKSHOP_RELAY", "0") == "1"
DISCOVER_PORT = int(os.environ.get("WORKSHOP_DISCOVER_PORT", "5001"))
DISCOVER_MAGIC = b"DICK_DISCOVER_V1"
UPLOAD_MAX_MB = int(os.environ.get("WORKSHOP_UPLOAD_MAX_MB", "64"))
COMPRESS_MIN_BYTES = int(os.environ.get("WORKSHOP_COMPRESS_MIN_BYTES", "1024"))
FEATURES = ("search", "like", "progress", "chunked_upload", "types", "capabilities", "gzip")
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌