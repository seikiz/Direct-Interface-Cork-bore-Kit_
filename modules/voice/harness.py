# -*- coding: utf-8 -*-
"""modules/voice/harness.py —— voice 自检的脚手架（替身 + 断言小工具）

**没有 case**：cases.py 与 selftest.py 都 import 它，依赖只有一条方向
（selftest → cases → harness → service/engines），不会成环。

四样替身，都为了一件事：**自检不许连网、不许占端口、不许真起 VOICEVOX**。
    FakeHost     宿主端口：路径 + 合成回调 + VOICEVOX 地址，故意不带壳层代码
    FakeHanasu   HANASU 两段 HTTP（audio_query → synthesis）的替身
    FakeUtau     UTAU 合成的替身（可注入并发观测，用来验"声卡独占"）
    FakeLog      只记行的日志（自检失败时打出来）
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from . import engines
from .service import VoiceService


BLOCK = "voice"

MAX_MS = 2000

class FakeHost(object):
    """只提供宿主能力这一样：路径 + 合成回调 + VOICEVOX 地址。故意不带任何壳层代码。"""

    def __init__(self, base_dir=None, voicebank="bank", synth=None, synth_ready=None,
                 utau_speak="", python=None, voicevox_url=None):
        self.base_dir = base_dir
        self.voicebank = voicebank
        self.utau_python = python or "no-such-python.exe"
        self.utau_speak = utau_speak
        self.synth = synth
        self.synth_ready = synth_ready
        if voicevox_url is not None:
            self.voicevox_url = voicevox_url

    def progress(self, stage, **kw):
        pass

class FakeLog(object):
    def __init__(self):
        self.lines = []

    def info(self, msg, tag=""):
        self.lines.append(("info", msg))

    def warn(self, msg, tag=""):
        self.lines.append(("warn", msg))

    def error(self, msg, tag=""):
        self.lines.append(("error", msg))

class FakeHanasu(object):
    """HANASU 的两个 HTTP 请求（audio_query → synthesis）的替身"""

    name = "hanasu"

    def __init__(self, ready=True, audio=b"WAVE-fake"):
        self.ready = ready
        self.audio = audio
        self.calls = []
        self.query = None

    def is_ready(self):
        return self.ready

    def synthesize(self, text, out_path, pitch_mode="auto"):
        self.calls.append((text, pitch_mode))
        with open(out_path, "wb") as f:
            f.write(self.audio)
        return out_path, "hanasu:" + pitch_mode

class FakeUtau(object):
    name = "utau"

    def __init__(self, ready=True, delay=0.0, state=None):
        self.ready = ready
        self.delay = delay
        self.state = state if state is not None else {"now": 0, "peak": 0}
        self.calls = []

    def is_ready(self):
        return self.ready

    def synthesize(self, text, out_path, pitch_mode="auto"):
        self.calls.append((text, pitch_mode))
        st = self.state
        st["now"] += 1
        st["peak"] = max(st["peak"], st["now"])
        time.sleep(self.delay)
        st["now"] -= 1
        with open(out_path, "wb") as f:
            f.write(b"WAVE-utau")
        return out_path, "utau:" + pitch_mode

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

def _raises(fn, needle, what):
    """坏输入必须抛出**带人话**的异常（不是静默返回空）"""
    try:
        fn()
    except engines.VoiceEngineError as e:
        if needle not in str(e):
            raise AssertionError("%s：报错里没有 %r（实际 %r）" % (what, needle, str(e)))
        return
    raise AssertionError("%s：居然没抛 VoiceEngineError" % what)

def _svc(**kw):
    return VoiceService().bind(FakeHost(**kw))

def _bank(tree, name="bank"):
    d = os.path.join(tree, name)
    os.makedirs(d, exist_ok=True)
    return d
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌