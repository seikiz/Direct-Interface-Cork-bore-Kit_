# -*- coding: utf-8 -*-
"""modules/codex/harness.py —— codex 自检的脚手架（替身 + 断言小工具）

**没有 case**：cases.py 与 selftest.py 都 import 它，依赖只有一条方向
（selftest → cases → harness → service），不会成环。

    FakeMark     水印模块的替身（真货是仓库根 dick_mark，由 bind(host) 注入）
    FakeHost     宿主端口：codex_dir / mark / progress 三样，故意不带壳层代码
    _fixture()   轻量夹具包（真 codex.json + 各目录一个小文件）—— 造它只花几毫秒，
                 而 make_sample_package 要逐像素画 5 张 420×720 占位图（~760ms），
                 所以示例包布局那个 case 用的是"生成器换桩"。
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
from . import pack as pack_mod
from .service import CodexService


BLOCK = "codex"

MAX_MS = 2000

PNG_STUB = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

WAV_STUB = b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x00" * 64

SCRIPT_TEXT = """【场景】序章
【背景】bg/教室.png
【音乐】bgm/theme.mp3
> 天亮了
咲：早上好
【选项】
- 打招呼 → s2
- 无视 → s3
"""

class FakeMark(object):
    """水印替身（生产环境 = 仓库根 `dick_mark`）：只保证三样东西的形状"""

    SIGNATURE = "SEIKI-FAKE-SIG"
    MARK_JS = "fake-mark-js"

    def mark_dict(self):
        return {"sig": "SEIKI-FAKE-SIG", "kind": "selftest"}

class FakeHost(object):
    """宿主端口：只给 codex_dir / mark / log / progress 四样，故意不带壳层代码"""

    def __init__(self, codex_dir=None, mark=None):
        self.codex_dir = codex_dir
        self.mark = mark
        self.events = []

    def progress(self, stage, **kw):
        self.events.append(stage)

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
    return got

def _true(cond, what):
    if not cond:
        raise AssertionError(what)

def _contains(hay, needle, what):
    if needle not in hay:
        raise AssertionError("%s：结果里没有 %r" % (what, needle))

def _svc(mark=None, codex_dir=None):
    return CodexService().bind(FakeHost(codex_dir=codex_dir, mark=mark))

def _fixture(tree, name="夹具", mark=None):
    """轻量夹具包：真 codex.json（make_template）+ 四个目录各一个小文件。

    不用 `make_sample_package` 的原因只有一个：它逐像素画 5 张 420×720 占位图（~760ms），
    而自检总预算只有 2s。示例包布局有专门一个 case（把画图/造音频换成桩）盯着。
    """
    svc = _svc(mark)
    pkg = os.path.join(tree, name)
    os.makedirs(pkg, exist_ok=True)
    with io.open(os.path.join(pkg, "codex.json"), "w", encoding="utf-8") as f:
        json.dump(svc.make_template(name), f, ensure_ascii=False, indent=1)
    for sub, blob, fn in (("sprites", PNG_STUB, "a.png"), ("bg", PNG_STUB, "a.png"),
                          ("bgm", b"ID3" + b"\x00" * 32, "a.mp3"),
                          ("voice", WAV_STUB, "a.wav")):
        d = os.path.join(pkg, sub)
        os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(d, fn), "wb") as f:
            f.write(blob)
    return pkg
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌