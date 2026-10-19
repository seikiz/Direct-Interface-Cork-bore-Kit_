# -*- coding: utf-8 -*-
"""modules/voice/service.py —— 语音服务（模块内部实现，外部不许 import）

壳层拿到的是这一个对象：`kernel.service("voice")`，再 `bind(host)` 把宿主能力接进来。

接口（block.json 的 interface.methods 就是这张表）：
    bind(host)                        宿主注入
    synthesize(text, cache_dir, …)    文本 → wav（一条闭环：挑引擎 → 合成 → 返回路径）
    pick(engine)                      按引擎名挑实例（auto：HANASU 优先，未就绪回落 UTAU）
    is_ready(engine)                  这个引擎现在能用吗
    detect_conflicts()                日语系统/编码/VOICEVOX 的就绪体检表
    engines()                         引擎名单

`bind(host)` 认的宿主属性（全可缺省）：
    base_dir      数据/环境根目录（解释器、声库的相对路径从这儿算）
    utau_python   UTAU 解释器（相对 base_dir 或绝对）
    voicebank     UTAU 声库目录（相对 base_dir 或绝对）
    utau_speak    合成脚本 utau_speak.py 的路径
    synth         进程内合成回调 (text, out, bank, pitch, duration, mode)
    synth_ready   进程内合成可用吗 () → bool
    voicevox_url  VOICEVOX 地址（默认 http://127.0.0.1:50021）
    hanasu_speaker / hanasu_speed
    log           有 info/warn/error 的日志对象

**声卡是独占设备**：`synthesize` 自带一把锁 —— 并发调用会排队，不会两条合成同时抢设备。
（搬家前这条串行是由壳层 jobs 的 "voice" 线保证的；块自己搬走以后必须自带这条约束。）
"""

import os
import threading
import time

from . import engines


class VoiceService(object):
    """文本 → wav。方法不弹对话框、不选路径（cache_dir 由调用方给）。"""

    def __init__(self, log=None):
        self.log = log
        self.host = None
        self.last_error = ""
        self.engine = "auto"
        self._lock = threading.Lock()          # 声卡独占：一次只许一条合成
        self.utau = engines.UtauEngine(log=log)
        self.hanasu = engines.HanasuEngine()

    # ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 宿主注入
    def bind(self, host, utau=None, hanasu=None):
        """把宿主接进来（幂等：壳层每次取服务都调一次也没关系）。

        `utau` / `hanasu` 只在"换实现/自检"时显式传；生产环境交给 host 的属性。
        """
        self.host = host
        self.log = getattr(host, "log", None) or self.log
        base = getattr(host, "base_dir", None)
        if utau is None:
            utau = engines.UtauEngine(
                python=getattr(host, "utau_python", None),
                voicebank=getattr(host, "voicebank", None),
                pitch=getattr(host, "utau_pitch", 60),
                duration=getattr(host, "utau_duration", 300),
                base_dir=base,
                helper=getattr(host, "utau_speak", None),
                synth=getattr(host, "synth", None),
                synth_ready=getattr(host, "synth_ready", None),
                log=self.log,
            )
        if hanasu is None:
            hanasu = engines.HanasuEngine(
                url=getattr(host, "voicevox_url", None),
                speaker=getattr(host, "hanasu_speaker", 3),
                speed=getattr(host, "hanasu_speed", 1.0),
                base_dir=base,
            )
        self.utau = utau
        self.hanasu = hanasu
        return self

    def _log(self, level, msg):
        fn = getattr(self.log, level, None)
        if callable(fn):
            try:
                fn(msg, "voice")
            except Exception:
                pass

    # ---------------------------------------------------------------- 挑引擎
    def pick(self, engine=None):
        """按引擎名挑实例，返回 (引擎实例, 名字)。

        auto：HANASU 优先（说话自然），未就绪回落 UTAU —— 与搬家前逐字一致。
        """
        e = (engine or self.engine or "auto")
        if e == "utau":
            return self.utau, "utau"
        if e == "hanasu":
            return self.hanasu, "hanasu"
        if self.hanasu.is_ready():
            return self.hanasu, "hanasu"
        return self.utau, "utau"

    def engines(self):
        return [self.utau.name, self.hanasu.name]

    def is_ready(self, engine="auto"):
        try:
            eng, name = self.pick(engine)
            return bool(eng.is_ready()), name
        except Exception as e:
            return False, str(e)[:120]

    # ---------------------------------------------------------------- 合成
    def synthesize(self, text, cache_dir, pitch_mode="auto", engine=None):
        """文本 → wav。返回 (wav 路径, 说明)。cache_dir 由调用方给（块不猜宿主目录）。"""
        os.makedirs(cache_dir, exist_ok=True)
        eng, name = self.pick(engine)
        out = engines.synth_filename(cache_dir, name)
        with self._lock:                      # 声卡独占：并发调用在这里排队
            try:
                got = eng.synthesize(text, out, pitch_mode)
                self.last_error = ""
                return got
            except Exception as e:
                self.last_error = "%s: %s" % (type(e).__name__, str(e)[:200])
                self._log("error", "合成失败（%s）：%s" % (name, self.last_error))
                raise

    # ---------------------------------------------------------------- 环境体检
    def detect_conflicts(self):
        """检测与日语系统/日语环境可能冲突的点，返回 {key: (ok, 说明)}。

        用于设置页/启动时提示：日语区域、控制台编码、IME、VOICEVOX 状态等。
        """
        import sys
        out = {}
        # 1) 系统语言/区域（Windows）
        try:
            import ctypes
            lang = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            lang_id = lang & 0xFFFF
            is_jp_system = (lang_id == 0x0411)  # ja-JP
            out["jp_system"] = (not is_jp_system,
                                "系统界面为日语（可能影响控制台编码/路径显示）" if is_jp_system else "系统非日语")
        except Exception:
            out["jp_system"] = (True, "无法检测系统语言")
        # 2) Python 默认编码（日语系统 cp932 风险）
        try:
            pref = sys.getfilesystemencoding()
            out["fs_encoding"] = (pref.lower() in ("utf-8", "utf8"),
                                  "文件系统编码: " + pref + ("（UTF-8 安全）" if pref.lower() in ("utf-8", "utf8") else "（非 UTF-8，日文路径可能出错）"))
        except Exception:
            out["fs_encoding"] = (True, "无法检测编码")
        # 3) 控制台输出编码
        try:
            try:
                out_enc = sys.stdout.encoding or "unknown"
            except Exception:
                out_enc = "unknown"
            out["console_encoding"] = (out_enc.lower() in ("utf-8", "utf8"),
                                       "控制台编码: " + str(out_enc))
        except Exception:
            out["console_encoding"] = (True, "无法检测")
        # 4) VOICEVOX 就绪状态
        try:
            vv = self.hanasu.is_ready()
            out["voicevox"] = (vv, "VOICEVOX 运行中" if vv else "VOICEVOX 未启动（auto 模式会回落 UTAU）")
        except Exception:
            out["voicevox"] = (True, "无法检测 VOICEVOX")
        return out

    # ---------------------------------------------------------------- 名字表
    @property
    def UtauEngine(self):
        return engines.UtauEngine

    @property
    def HanasuEngine(self):
        return engines.HanasuEngine

    @property
    def VoiceEngineError(self):
        return engines.VoiceEngineError

    def analyze_tone(self, text):
        return engines.analyze_tone(text)

    def now_ms(self):
        return int(time.time() * 1000)
