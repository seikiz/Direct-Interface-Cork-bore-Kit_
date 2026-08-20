# ============================================================
#   voice_engine.py - DICK 语音引擎统一层（UTAU + HANASU）
#
#   UTAU（唱歌/合成）：纯本地 putao 引擎，走 utau_voice.py 的合成脚本
#   HANASU（说话）：VOICEVOX 本地引擎（HTTP :50021），自然说话
#
#   傻瓜化：引擎只认"配置好的模型"——每个角色可选挂哪个引擎，
#   用户不用管底层实现，设置页选一下就行。
# ============================================================

import os
import subprocess
import time
import urllib.request
import json


class VoiceEngineError(Exception):
    pass


class UtauEngine:
    """UTAU 合成引擎：唱歌式拼接合成（已有实现，封装统一接口）"""

    name = "utau"

    def __init__(self, python=None, voicebank=None, pitch=60, duration=300, base_dir=None):
        self.python = python or "utau_env\\Scripts\\python.exe"
        self.voicebank = voicebank or "utau_voicebanks\\默认声库"
        self.pitch = int(pitch or 60)
        self.duration = int(duration or 300)
        self.base_dir = base_dir or os.getcwd()

    def is_ready(self):
        py = self.python if os.path.isabs(self.python) else os.path.join(self.base_dir, self.python)
        vb = self.voicebank if os.path.isabs(self.voicebank) else os.path.join(self.base_dir, self.voicebank)
        return os.path.exists(py) and os.path.exists(vb)

    def synthesize(self, text, out_path):
        """合成文本 → wav。返回 (wav路径, 说明)"""
        if not self.is_ready():
            raise VoiceEngineError("UTAU 环境或声库未就绪")
        py = self.python if os.path.isabs(self.python) else os.path.join(self.base_dir, self.python)
        vb = self.voicebank if os.path.isabs(self.voicebank) else os.path.join(self.base_dir, self.voicebank)
        helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utau_speak.py")
        r = subprocess.run(
            [py, helper, vb, str(self.pitch), str(self.duration), text, out_path],
            capture_output=True, timeout=180, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0 or not os.path.exists(out_path):
            raise VoiceEngineError("UTAU 合成失败：" + ((r.stdout or "") + (r.stderr or ""))[-200:])
        return out_path, "utau"


class HanasuEngine:
    """HANASU 说话引擎：VOICEVOX 本地 HTTP（默认 :50021）"""

    name = "hanasu"
    DEFAULT_URL = "http://127.0.0.1:50021"

    def __init__(self, url=None, speaker=3, speed=1.0, base_dir=None):
        self.url = (url or self.DEFAULT_URL).rstrip("/")
        self.speaker = int(speaker or 3)   # 3=ずんだもん? 按需；可设角色
        self.speed = float(speed or 1.0)
        self.base_dir = base_dir

    def is_ready(self):
        try:
            with urllib.request.urlopen(self.url + "/version", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def synthesize(self, text, out_path):
        """VOICEVOX 双请求：audio_query → synthesis。返回 (wav路径, 说明)"""
        if not self.is_ready():
            raise VoiceEngineError("HANASU（VOICEVOX）未运行——请先启动 VOICEVOX 引擎（默认 :50021）")
        try:
            q = self.url + "/audio_query?text=" + urllib.request.quote(text) + "&speaker=" + str(self.speaker)
            req = urllib.request.Request(q, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                query = json.loads(r.read().decode("utf-8"))
            # 调语速
            try:
                query["speedScale"] = self.speed
            except Exception:
                pass
            body = json.dumps(query).encode("utf-8")
            sreq = urllib.request.Request(self.url + "/synthesis?speaker=" + str(self.speaker),
                                          data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(sreq, timeout=60) as r:
                data = r.read()
            with open(out_path, "wb") as f:
                f.write(data)
            if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                raise VoiceEngineError("HANASU 返回空音频")
            return out_path, "hanasu"
        except VoiceEngineError:
            raise
        except Exception as e:
            raise VoiceEngineError("HANASU 合成失败：" + str(e)[:150])


class VoiceEngine:
    """统一入口：按引擎名分发。engine="utau"|"hanasu"|"auto"（auto：HANASU 优先，未就绪回落 UTAU）"""

    def __init__(self, engine="auto", utau=None, hanasu=None):
        self.engine = engine
        self.utau = utau or UtauEngine()
        self.hanasu = hanasu or HanasuEngine()

    def _pick(self):
        e = self.engine
        if e == "utau":
            return self.utau, "utau"
        if e == "hanasu":
            return self.hanasu, "hanasu"
        # auto：HANASU 优先（说话自然），未就绪回落 UTAU
        if self.hanasu.is_ready():
            return self.hanasu, "hanasu"
        return self.utau, "utau"

    def synthesize(self, text, cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
        eng, name = self._pick()
        out = os.path.join(cache_dir, name + "_" + str(int(time.time() * 1000)) + ".wav")
        return eng.synthesize(text, out)
