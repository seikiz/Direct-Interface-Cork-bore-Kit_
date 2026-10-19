# -*- coding: utf-8 -*-
"""modules/voice/cases.py —— voice 的全部自检 case + CASES 登记表

覆盖两条合成路线（进程内 / 子进程 / VOICEVOX HTTP）、语气规则、声卡独占锁，
以及五条坏输入（缺声库 / 缺环境 / 缺合成脚本 / VOICEVOX 没起来 / 返回空音频）。
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
from .harness import FakeHanasu, FakeHost, FakeLog, FakeUtau, _bank, _eq, _raises, _svc, _tmpdir, _true
import types  # CASES 只读视图（十一：块里不许有模块级可变全局）


def case_tone_rules():
    cases = [("哈哈哈好耶", "happy"), ("呜呜好难过", "sad"), ("哼，才不呢", "angry"),
             ("你要一起走吗", "question"), ("太好了！", "happy"), ("就这样吧……", "sad"),
             ("今天天气不错", "flat"), ("", "flat")]
    bad = [(t, engines.analyze_tone(t), want) for t, want in cases
           if engines.analyze_tone(t) != want]
    _eq(bad, [], "语气规则")
    _eq(_svc().analyze_tone("哈哈哈"), "happy", "服务上的语气函数与引擎层同一个")

def case_utau_missing_bank():
    """坏输入：声库不存在 → 说清"要自己准备声库"，不是静默失败"""
    tree = _tmpdir("nobank")
    try:
        eng = engines.UtauEngine(base_dir=tree, voicebank="nope")
        _eq(eng.is_ready(), False, "声库不存在时 is_ready 为假")
        _raises(lambda: eng.synthesize("喂", os.path.join(tree, "a.wav")),
                "未找到声库", "缺声库")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_utau_missing_env():
    """坏输入：有音库但没有进程内合成、也没有 utau_env 解释器"""
    tree = _tmpdir("noenv")
    try:
        _bank(tree)
        eng = engines.UtauEngine(base_dir=tree, voicebank="bank", python="no-such-python.exe")
        _eq(eng.is_ready(), False, "既无 synth 又无解释器时 is_ready 为假")
        _raises(lambda: eng.synthesize("喂", os.path.join(tree, "a.wav")),
                "UTAU 环境缺失", "缺环境")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_utau_missing_helper():
    """坏输入：解释器在、但宿主没注入合成脚本路径"""
    tree = _tmpdir("nohelper")
    try:
        _bank(tree)
        py = os.path.join(tree, "fake-python.exe")
        with io.open(py, "w", encoding="utf-8") as f:
            f.write("")
        eng = engines.UtauEngine(base_dir=tree, voicebank="bank", python=py)
        _raises(lambda: eng.synthesize("喂", os.path.join(tree, "a.wav")),
                "合成脚本没注入", "缺合成脚本")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_utau_inline():
    """正常路径：宿主注入的进程内合成被调用，参数原样透传"""
    tree = _tmpdir("inline")
    try:
        _bank(tree)
        seen = {}

        def synth(text, out_path, bank, pitch, duration, mode):
            seen.update(text=text, bank=bank, pitch=pitch, duration=duration, mode=mode)
            with io.open(out_path, "wb") as f:
                f.write(b"WAVE-utau")

        eng = engines.UtauEngine(base_dir=tree, voicebank="bank", synth=synth,
                                 synth_ready=lambda: True, pitch=72, duration=240)
        _eq(eng.is_ready(), True, "有进程内合成时 is_ready 为真")
        out = os.path.join(tree, "a.wav")
        got, note = eng.synthesize("你好", out, "happy")
        _eq(note, "utau:happy", "说明里带模式")
        _eq(got, out, "返回落盘路径")
        _eq(seen["pitch"], "72", "音高按字符串透传（与子进程同参）")
        _eq(seen["duration"], "240", "时长按字符串透传")
        _eq(seen["text"], "你好", "文本原样透传")
        _true(seen["bank"].endswith("bank"), "声库绝对路径透传")
        _true(os.path.isfile(out), "文件真的落盘")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_utau_inline_failure_falls_back():
    """进程内合成炸了要**回落**子进程那条路（不是直接失败）"""
    tree = _tmpdir("fallback")
    try:
        _bank(tree)

        def boom(*a):
            raise RuntimeError("putao 炸了")

        eng = engines.UtauEngine(base_dir=tree, voicebank="bank", synth=boom,
                                 python="no-such-python.exe")
        _raises(lambda: eng.synthesize("喂", os.path.join(tree, "a.wav")),
                "UTAU 环境缺失", "进程内失败后应当回落到子进程那条诊断")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_utau_subprocess():
    """子进程那条路：真起一个 python 跑最小合成脚本（本地文件，不连网）"""
    tree = _tmpdir("subproc")
    try:
        _bank(tree)
        helper = os.path.join(tree, "helper.py")
        with io.open(helper, "w", encoding="utf-8") as f:
            # argv: <vb> <pitch> <dura<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌tion> <text> <out> <mode>
            f.write("import sys\nopen(sys.argv[5], 'wb').write(b'WAVE-sub')\n")
        eng = engines.UtauEngine(base_dir=tree, voicebank="bank", helper=helper,
                                 python=sys.executable)
        out = os.path.join(tree, "b.wav")
        got, note = eng.synthesize("喂", out, "flat")
        _eq(note, "utau:flat", "子进程路径的说明")
        _true(os.path.getsize(out) > 0, "子进程真的写出了文件")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_hanasu_not_ready():
    """坏输入：VOICEVOX 没起来 → 明确让用户去启动（不是超时卡住）"""
    eng = engines.HanasuEngine(opener=lambda *a: (_ for _ in ()).throw(OSError("refused")))
    _eq(eng.is_ready(), False, "连不上时 is_ready 为假")
    _raises(lambda: eng.synthesize("喂", "x.wav"), "VOICEVOX", "VOICEVOX 没起来")

def case_hanasu_protocol():
    """正常路径：audio_query → 语气微调 → synthesis 三段都发生，且参数对得上"""
    tree = _tmpdir("hanasu")
    try:
        seen = {"calls": []}

        def opener(method, url, data=None, headers=None, timeout=30):
            seen["calls"].append((method, url, data, headers))
            if url.endswith("/version"):
                return 200, b"0.14"
            if "/audio_query" in url:
                return 200, json.dumps({"speedScale": 1.0}).encode("utf-8")
            if "/synthesis" in url:
                q = json.loads(data.decode("utf-8"))
                seen["query"] = q
                return 200, b"WAVE-hanasu"
            raise AssertionError("不该请求 %s" % url)

        eng = engines.HanasuEngine(opener=opener, speaker=8, speed=1.0)
        _eq(eng.is_ready(), True, "替身回 200 时 is_ready 为真")
        out = os.path.join(tree, "h.wav")
        got, note = eng.synthesize("太好了", out, "auto")
        _eq(note, "hanasu:happy", "auto 模式按文本判成 happy")
        _eq(got, out, "返回落盘路径")
        _true(os.path.getsize(out) > 0, "音频真的落盘")
        q = seen["query"]
        _true(abs(q["speedScale"] - 1.12) < 1e-6, "happy 的语速微调：%r" % q.get("speedScale"))
        _true(abs(q["intonationScale"] - 1.08) < 1e-6, "happy 的语调微调")
        _eq(q["pitchScale"], 0.0, "音高不额外偏移")
        urls = [c[1] for c in seen["calls"]]
        _true(any("speaker=8" in u for u in urls), "speaker 要进 URL")
        # 合成那一段固定是 GET /version → POST /audio_query → POST /synthesis
        _eq([c[0] for c in seen["calls"]][-3:], ["GET", "POST", "POST"],
            "合成过程的请求方法与方法顺序")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_hanasu_empty_audio():
    """坏输入：合成回来是空音频 → 明确报错，不许写出一个 0 字节 wav"""
    tree = _tmpdir("hanasu_empty")
    try:
        def opener(method, url, data=None, headers=None, timeout=30):
            if url.endswith("/version"):
                return 200, b"0.14"
            if "/audio_query" in url:
                return 200, b"{}"
            return 200, b""

        eng = engines.HanasuEngine(opener=opener)
        _raises(lambda: eng.synthesize("喂", os.path.join(tree, "e.wav")),
                "空音频", "空音频")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_hanasu_bad_json():
    """坏输入：audio_query 回的不是 JSON → 包成 VoiceEngineError 而不是抛原始异常"""
    tree = _tmpdir("hanasu_bad")
    try:
        def opener(method, url, data=None, headers=None, timeout=30):
            if url.endswith("/version"):
                return 200, b"0.14"
            return 200, b"not json"

        eng = engines.HanasuEngine(opener=opener)
        _raises(lambda: eng.synthesize("喂", os.path.join(tree, "b.wav")),
                "HANASU 合成失败", "坏 JSON")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_pick_auto():
    svc = _svc(base_dir=tempfile.gettempdir())
    svc.utau = FakeUtau()
    svc.hanasu = FakeHanasu(ready=True)
    _eq(svc.pick("auto")[1], "hanasu", "auto：HANASU 优先")
    svc.hanasu = FakeHanasu(ready=False)
    _eq(svc.pick("auto")[1], "utau", "HANASU 未就绪回落 UTAU")
    _eq(svc.pick("utau")[1], "utau", "显式 utau")
    _eq(svc.pick("hanasu")[1], "hanasu", "显式 hanasu")
    _eq(svc.engines(), ["utau", "hanasu"], "引擎名单")
    _eq(svc.is_ready("hanasu"), (False, "hanasu"), "is_ready 带引擎名")

def case_synthesize_creates_cache_dir():
    tree = _tmpdir("cache")
    try:
        svc = _svc(base_dir=tree)
        svc.utau = FakeUtau()
        svc.hanasu = FakeHanasu(ready=False)
        cache = os.path.join(tree, "deep", "cache")
        out, note = svc.synthesize("你好", cache)
        _true(os.path.isdir(cache), "缓存目录要自动创建")
        _true(out.endswith(".wav") and os.path.basename(out).startswith("utau_"),
              "文件名形如 utau_<毫秒>.wav：%r" % out)
        _eq(note, "utau:auto", "说明透传")
        _eq(svc.last_error, "", "成功时不留 last_error")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_synthesize_exclusive():
    """设备独占：并发调 synthesize 必须排队（峰值并发 = 1），且失败要记 last_error"""
    tree = _tmpdir("exclusive")
    try:
        state = {"now": 0, "peak": 0}
        svc = _svc(base_dir=tree)
        svc.utau = FakeUtau(delay=0.02, state=state)
        svc.hanasu = FakeHanasu(ready=False)
        cache = os.path.join(tree, "c")
        threads = [threading.Thread(target=svc.synthesize, args=("喂", cache))
                   for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        _eq(state["peak"], 1, "同一时刻只许一条合成（声卡独占）")

        svc.utau = FakeUtau(ready=True)
        svc.utau.synthesize = lambda *a: (_ for _ in ()).throw(RuntimeError("设备忙"))
        try:
            svc.synthesize("喂", cache)
        except Exception:
            pass
        _true("设备忙" in svc.last_error, "失败要记进 last_error：%r" % svc.last_error)
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_detect_conflicts():
    svc = _svc(base_dir=tempfile.gettempdir())
    svc.hanasu = FakeHanasu(ready=True)
    got = svc.detect_conflicts()
    _true({"jp_system", "fs_encoding", "console_encoding", "voicevox"} <= set(got),
          "体检表缺项：%r" % sorted(got))
    _eq(got["voicevox"], (True, "VOICEVOX 运行中"), "VOICEVOX 就绪文案")
    svc.hanasu = FakeHanasu(ready=False)
    _eq(svc.detect_conflicts()["voicevox"], (False, "VOICEVOX 未启动（auto 模式会回落 UTAU）"),
        "VOICEVOX 未就绪文案")

def case_bind_wires_host():
    """bind 要把宿主给的路径/地址接上（块自己不猜目录）"""
    tree = _tmpdir("bind")
    try:
        _bank(tree, "我的声库")
        host = FakeHost(base_dir=tree, voicebank="我的声库", voicevox_url="http://127.0.0.1:5999/")
        svc = VoiceService().bind(host)
        _true(svc.utau.bank_dir().endswith("我的声库"), "声库路径按 base_dir 解析")
        _true(os.path.isabs(svc.utau.bank_dir()), "解析成绝对路径")
        _eq(svc.hanasu.url, "http://127.0.0.1:5999", "VOICEVOX 地址去掉尾部斜杠")
        _true(svc.bind(host) is svc, "bind 幂等且返回自己")
        log = FakeLog()
        host.log = log
        VoiceService().bind(host)
        _true(hasattr(svc.utau, "log"), "宿主日志要接进引擎")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


CASES = types.MappingProxyType({
    "tone_rules": case_tone_rules,
    "utau_missing_bank": case_utau_missing_bank,
    "utau_missing_env": case_utau_missing_env,
    "utau_missing_helper": case_utau_missing_helper,
    "utau_inline": case_utau_inline,
    "utau_inline_failure_falls_back": case_utau_inline_failure_falls_back,
    "utau_subprocess": case_utau_subprocess,
    "hanasu_not_ready": case_hanasu_not_ready,
    "hanasu_protocol": case_hanasu_protocol,
    "hanasu_empty_audio": case_hanasu_empty_audio,
    "hanasu_bad_json": case_hanasu_bad_json,
    "pick_auto": case_pick_auto,
    "synthesize_creates_cache_dir": case_synthesize_creates_cache_dir,
    "synthesize_exclusive": case_synthesize_exclusive,
    "detect_conflicts": case_detect_conflicts,
    "bind_wires_host": case_bind_wires_host,
})
