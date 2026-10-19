# -*- coding: utf-8 -*-
"""modules/image_gen/harness.py —— image_gen 自检的脚手架（替身 + 断言小工具）

**没有 case**：cases.py 与 selftest.py 都 import 它，依赖只有一条方向
（selftest → cases → harness → service.py），不会成环。

三样替身，都为了一件事：**自检不许连网、不许占端口、不许等真时间**。
    FakeNet     backends.Net 的替身：同样的四个动词（post/get/sleep/now），回放预编响应
    FakeHost    宿主端口：只给时钟/日志/进度回调，故意不带任何壳层代码
    FakeLog     只记行的日志（自检失败时打出来，方便定位）
"""

import base64
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
from .service import ImageGenService


BLOCK = "image_gen"

MAX_MS = 2000

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 600

JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 600

WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 600

class FakeNet(object):
    """`backends.Net` 的替身：同样的四个动词，不发一个字节。

    `post_handler(url, body)` / `get_handler(url)` 返回响应；抛异常就模拟失败。
    时钟是假的（`t` 每次 sleep 前进），所以退避与超时判定都是确定性的。
    """

    def __init__(self, post_handler=None, get_handler=None):
        self.host = None
        self.log = None
        self.posts = []
        self.gets = []
        self.sleeps = []
        self.t = 1000.0
        self.post_handler = post_handler
        self.get_handler = get_handler
        self.post_error = None

    def post(self, url, body, headers, timeout=300):
        self.posts.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        if self.post_error is not None:
            raise self.post_error
        return self.post_handler(url, body) if self.post_handler else {}

    def get(self, url, timeout=60):
        self.gets.append({"url": url, "timeout": timeout})
        if self.get_handler is None:
            raise AssertionError("这个 case 不该发 GET：%s" % url)
        return self.get_handler(url)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += float(seconds or 0)

    def now(self):
        return self.t

class FakeHost(object):
    """只提供宿主能力这一样：时钟 + 日志 + 进度回调。故意不带任何壳层代码。"""

    def __init__(self):
        self.events = []
        self.progress_calls = []

    def progress(self, stage, **kw):
        self.progress_calls.append((stage, kw))

class FakeLog(object):
    def __init__(self):
        self.lines = []

    def info(self, msg, tag=""):
        self.lines.append(("info", msg))

    def warn(self, msg, tag=""):
        self.lines.append(("warn", msg))

    def error(self, msg, tag=""):
        self.lines.append(("error", msg))

def http_error(code, body=b'{"error": "model not found"}'):
    return urllib.error.HTTPError("http://fake/x", code, "err", {}, io.BytesIO(body))

def _tmpdir(label):
    """临时目录：%TEMP% 写不进去时退到工作区 tmp/ 下（venv 版 Python 的已知限制）"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for cand in (os.environ.get("TEMP"), os.environ.get("TMP"),
                 os.path.join(root, "tmp_kernel_tests")):
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".probe_%d" % os.getpid())
            os.makedirs(probe, exist_ok=True)
            os.rmdir(probe)
            return tempfile.mkdtemp(prefix="dick_block_%s_" % label, dir=cand)
        except Exception:
            continue
    raise RuntimeError("没有可写的临时目录")

def _eq(got, want, what):
    if got != want:
        raise AssertionError("%s：期望 %r，实际 %r" % (what, want, got))

def _true(cond, what):
    if not cond:
        raise AssertionError(what)

def _contains(hay, needle, what):
    if needle not in hay:
        raise AssertionError("%s：%r 里没有 %r" % (what, hay, needle))

def _svc(net=None, host=None):
    svc = ImageGenService()
    svc.bind(host if host is not None else FakeHost(), net if net is not None else FakeNet())
    return svc
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌