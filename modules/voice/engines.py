# -*- coding: utf-8 -*-
"""modules/voice/engines.py —— 两个语音引擎（UTAU / HANASU-VOICEVOX）

搬家来源：仓库根 `voice_engine.py` 的 `UtauEngine` / `HanasuEngine` / `_analyze_tone`，
**音色参数、语气规则、错误文案一字未改**。改的只有三条"宿主依赖"：

  ① 解释器 / 声库 / 合成脚本路径：原来写死相对仓库根的字面量，现在由构造参数给
     （由 `service.bind(host)` 从宿主取）。块不猜任何目录。
  ② 进程内合成（`import putao` + 载入 `utau_speak.py`）：那是**宿主的**第三方引擎，
     改成构造参数 `synth`（一个可调用对象）。宿主不给就是没有，块不偷偷 import。
  ③ HANASU 的 HTTP 传输：收进 `opener`（缺省 = urllib），自检塞替身就能把
     「audio_query → 语气微调 → synthesis」整条链跑通，而不用真开一个 VOICEVOX。

两个引擎的共同约束：**输入是文本，输出是一个 wav 路径**；声卡是独占设备，
同一时刻只许一条合成在跑 —— 这条由 `service.VoiceService` 的锁保证（见 service.py）。
"""

import json
import os
import subprocess
import time
import urllib.request


class VoiceEngineError(Exception):
    """语音合成失败（文案直接给用户看：说清"缺什么、怎么补"）"""
    pass


def analyze_tone(text):
    """文本语气分析（与 utau_speak 的规则一致，供 HANASU 用）

    auto 模式下按这套规则把语气映射成语速/音调微调，避免"死气沉沉地念稿"。
    """
    t = (text or "").strip()
    happy_kw = ("哈哈", "嘿嘿", "好耶", "太好了", "开心", "嘻嘻", "笑", "♪", "~", "～", "うれ", "嬉", "楽し")
    sad_kw = ("哭", "呜呜", "难过", "伤心", "寂寞", "不要走", "泣", "悲", "さみ", "寂")
    angry_kw = ("哼", "才不", "讨厌", "混蛋", "可恶", "生气", "怒", "む", "ふん")
    if any(k in t for k in happy_kw):
        return "happy"
    if any(k in t for k in sad_kw):
        return "sad"
    if any(k in t for k in angry_kw):
        return "angry"
    if t.endswith("？") or t.endswith("?") or t.endswith("吗"):
        return "question"
    if t.endswith("！") or t.endswith("!"):
        return "angry"
    if "……" in t or "..." in t or "。。" in t:
        return "sad"
    return "flat"


class UtauEngine(object):
    """UTAU 合成引擎：唱歌式拼接合成（纯本地，两条路：进程内 / 子进程）"""

    name = "utau"

    def __init__(self, python=None, voicebank=None, pitch=60, duration=300, base_dir=None,
                 helper=None, synth=None, synth_ready=None, log=None):
        # 缺省值只是"名字"，真正的根目录由 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌base_dir 给（块不猜绝对路径）
        self.python = python or os.path.join("utau_env", "Scripts", "python.exe")
        self.voicebank = voicebank or os.path.join("utau_voicebanks", "默认声库")
        self.pitch = int(pitch or 60)
        self.duration = int(duration or 300)
        self.base_dir = base_dir or os.getcwd()
        self.helper = helper or ""          # utau_speak.py 的路径（宿主注入）
        self.synth = synth                  # 进程内合成回调（宿主注入，可为 None）
        self.synth_ready = synth_ready      # 「进程内合成可用吗」（宿主注入，可为 None）
        self.log = log

    # ---- 就绪判断 ----
    def bank_dir(self):
        vb = self.voicebank
        return vb if os.path.isabs(vb) else os.path.join(self.base_dir, vb)

    def resolve_python(self):
        py = self.python
        return py if os.path.isabs(py) else os.path.join(self.base_dir, py)

    def is_ready(self):
        """就绪判断：声库存在，且要么有进程内合成能力，要么 utau_env 的解释器在"""
        if not os.path.exists(self.bank_dir()):
            return False
        if self.synth is not None:
            try:
                if self.synth_ready is None or self.synth_ready():
                    return True
            except Exception:
                pass
        return os.path.exists(self.resolve_python())

    # ---- 合成 ----
    def synthesize(self, text, out_path, pitch_mode="auto"):
        """合成文本 → wav。返回 (wav路径, 说明)。

        pitch_mode: auto=语气分析 / flat / happy / sad / angry / question
        用户不需要装 UTAU 环境：宿主注入的进程内合成优先（打包态 putao 已内嵌）；
        没有进程内能力才回落外部 utau_env 子进程。
        """
        vb = self.bank_dir()
        if not os.path.exists(vb):
            raise VoiceEngineError("未找到声库：" + vb + "（声音需自己准备：放一个 UTAU 声库目录）")
        if self.synth is not None:
            try:
                return self._synthesize_inline(text, out_path, vb, pitch_mode)
            except Exception:
                pass
        py = self.resolve_python()
        if not os.path.exists(py):
            raise VoiceEngineError("UTAU 环境缺失：既无打包 putao，也找不到 " + py)
        if not self.helper:
            raise VoiceEngineError("UTAU 合成脚本没注入（宿主应给 host.utau_speak 路径）")
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        r = subprocess.run(
            [py, self.helper, vb, str(self.pitch), str(self.duration), text, out_path, pitch_mode],
            capture_output=True, timeout=180, encoding="utf-8", errors="replace", env=env,
        )
        if r.returncode != 0 or not os.path.exists(out_path):
            raise VoiceEngineError("UTAU 合成失败：" + ((r.stdout or "") + (r.stderr or ""))[-200:])
        return out_path, "utau:" + pitch_mode

    def _synthesize_inline(self, text, out_path, vb, pitch_mode):
        """进程内合成：调宿主注入的 `synth`（块自己不 import 第三方引擎）"""
        if self.synth is None:
            raise VoiceEngineError("没有进程内合成能力（宿主没注入 synth）")
        self.synth(text, out_path, vb, str(self.pitch), str(self.duration), pitch_mode)
        if not os.path.exists(out_path):
            raise VoiceEngineError("UTAU 进程内合成失败")
        return out_path, "utau:" + pitch_mode


class HanasuEngine(object):
    """HANASU 说话引擎：VOICEVOX 本地 HTTP（默认 :50021）

    传输收在 `opener(method, url, data, headers, timeout) -> (status, bytes)`：
      · 缺省 = urllib（真连本地 VOICEVOX）；
      · 自检 = 替身（把 audio_query / synthesis 两段的请求与响应都钉死，不开 socket）。
    """

    name = "hanasu"
    DEFAULT_URL = "http://127.0.0.1:50021"

    def __init__(self, url=None, speaker=3, speed=1.0, base_dir=None, opener=None):
        self.url = (url or self.DEFAULT_URL).rstrip("/")
        self.speaker = int(speaker or 3)   # 3=ずんだもん? 按需；可设角色
        self.speed = float(speed or 1.0)
        self.base_dir = base_dir
        self.opener = opener

    # ---- 传输 ----
    def request(self, method, url, data=None, headers=None, timeout=30):
        if self.opener is not None:
            return self.opener(method, url, data, headers, timeout)
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return getattr(r, "status", 200), r.read()

    def is_ready(self):
        try:
            status, _body = self.request("GET", self.url + "/version", timeout=2)
            return status == 200
        except Exception:
            return False

    # ---- 合成 ----
    def synthesize(self, text, out_path, pitch_mode="auto"):
        """VOICEVOX 双请求：audio_query → synthesis。返回 (wav路径, 说明)
        pitch_mode: auto=按文本情绪调语速/音调 / flat / happy / sad / angry / question"""
        if not self.is_ready():
            raise VoiceEngineError("HANASU（VOICEVOX）未运行——请先启动 VOICEVOX 引擎（默认 :50021）")
        try:
            q = (self.url + "/audio_query?text=" + urllib.request.quote(text)
                 + "&speaker=" + str(self.speaker))
            _st, raw = self.request("POST", q, timeout=30)
            query = json.loads(raw.decode("utf-8"))
            # 语气 → 语速/音调微调（避免死气沉沉）
            mode = pitch_mode
            if mode == "auto":
                mode = analyze_tone(text)
            spd = self.speed
            intn = 1.0
            if mode == "happy":
                spd *= 1.12
                intn = 1.08
            elif mode == "sad":
                spd *= 0.9
                intn = 0.92
            elif mode == "angry":
                spd *= 1.08
                intn = 1.1
            elif mode == "question":
                spd *= 1.0
                intn = 1.15
            try:
                query["speedScale"] = max(0.5, min(2.0, spd))
                query["intonationScale"] = max(0.0, min(2.0, intn))
                query["pitchScale"] = 0.0
            except Exception:
                pass
            body = json.dumps(query).encode("utf-8")
            _st, data = self.request("POST",
                                     self.url + "/synthesis?speaker=" + str(self.speaker),
                                     data=body, headers={"Content-Type": "application/json"},
                                     timeout=60)
            with open(out_path, "wb") as f:
                f.write(data)
            if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                raise VoiceEngineError("HANASU 返回空音频")
            return out_path, "hanasu:" + mode
        except VoiceEngineError:
            raise
        except Exception as e:
            raise VoiceEngineError("HANASU 合成失败：" + str(e)[:150])


def synth_filename(cache_dir, name):
    """缓存里的文件名（毫秒时间戳：同一秒内多次合成也不会互相覆盖）"""
    return os.path.join(cache_dir, name + "_" + str(int(time.time() * 1000)) + ".wav")
