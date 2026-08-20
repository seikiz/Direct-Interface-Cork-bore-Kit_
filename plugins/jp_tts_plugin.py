# ============================================================
#   jp_tts_plugin.py - 可爱日文 TTS（实验版）v0.2
#
#   主引擎：VOICEVOX（免费离线动漫声线：ずんだもん/四国めたん/春日部つむぎ...）
#     - 需自行下载运行 VOICEVOX：https://voicevox.hiroshiba.jp/
#     - 启动后本地引擎监听 http://127.0.0.1:50021
#   备胎：edge-tts（微软神经语音，需联网）
#
#   默认「可爱参数」：音调 +0.15、语速 1.1、语调 1.2（活泼）
# ============================================================

import os
import threading

import requests

import app_paths
from plugin_base import PluginBase

def _edge_ok():
    try:
        import importlib.util
        return importlib.util.find_spec("edge_tts") is not None
    except Exception:
        return False


def _pygame_ok():
    try:
        import importlib.util
        return importlib.util.find_spec("pygame") is not None
    except Exception:
        return False


class JpTTSPlugin(PluginBase):
    name = "日文朗读(TTS实验)"
    version = "0.2"
    description = "可爱日文 TTS：VOICEVOX 动漫声线优先（ずんだもん等），edge-tts 备胎"
    author = "seiki"
    enabled = True

    ui_buttons = [
        {"type": "method", "label": "🔊 朗读", "method": "speak_last"},
    ]

    settings_schema = [
        {"key": "engine", "label": "语音引擎", "type": "choice",
         "options": ["自动（VOICEVOX 优先）", "VOICEVOX", "edge-tts"],
         "default": "自动（VOICEVOX 优先）"},
        {"key": "voicevox_url", "label": "VOICEVOX 引擎地址（默认本机 50021）",
         "type": "text", "default": "http://127.0.0.1:50021"},
        {"key": "voicevox_speaker", "label": "VOICEVOX 声优 ID（/tts speakers 可查）",
         "type": "text", "default": "3"},
        {"key": "vv_pitch", "label": "可爱度·音调", "type": "choice",
         "options": ["+0.15 更可爱", "+0.05 稍高", "正常", "-0.10 低沉"],
         "default": "+0.15 更可爱"},
        {"key": "vv_speed", "label": "语速", "type": "choice",
         "options": ["0.9 稍慢", "1.0 正常", "1.1 稍快", "1.25 更快"],
         "default": "1.1 稍快"},
        {"key": "vv_intonation", "label": "语调起伏", "type": "choice",
         "options": ["1.0 正常", "1.2 活泼", "0.8 平淡"], "default": "1.2 活泼"},
        # ---- edge-tts 备胎设置 ----
        {"key": "edge_voice", "label": "备胎声优（edge-tts）", "type": "choice",
         "options": ["Nanami（女·自然）", "Keita（男）", "Aoi（女·少女）",
                     "Mayu（女·柔和）", "Shiori（女·成熟）"],
         "default": "Nanami（女·自然）"},
        {"key": "auto_speak", "label": "自动朗读每条 AI 回复", "type": "bool",
         "default": False},
    ]

    EDGE_VOICES = {
        "Nanami（女·自然）": "ja-JP-NanamiNeural",
        "Keita（男）": "ja-JP-KeitaNeural",
        "Aoi（女·少女）": "ja-JP-AoiNeural",
        "Mayu（女·柔和）": "ja-JP-MayuNeural",
        "Shiori（女·成熟）": "ja-JP-ShioriNeural",
    }

    # 常见可爱声优 → 默认风格 ID（不同引擎版本可能不同，以 /tts speakers 为准）
    POPULAR_SPEAKERS = {
        "ずんだもん": "3", "四国めたん": "2", "春日部つむぎ": "8",
        "雨晴はう": "10", "波音リツ": "9", "もち子さん": "20",
        "あいえるたん": "52", "ナースロボ＿タイプＴ": "46",
    }

    def __init__(self, core):
        super().__init__(core)
        self._last_reply = ""
        self._speaking = False
        self._cache_dir = os.path.join(app_paths.get_base_dir(), "tts_cache")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._vv_ok = None  # VOICEVOX 可用性缓存

    def on_load(self):
        print("[TTS v0.2] 已加载：VOICEVOX 可爱声线优先（/tts speakers 查看声优）")

    # ============================================================
    # VOICEVOX
    # ============================================================
    def _voicevox_url(self):
        return (self.get_setting("voicevox_url", "http://127.0.0.1:50021") or "").rstrip("/")

    def voicevox_available(self, force=False):
        """检测本机 VOICEVOX 引擎是否可用（结果缓存 60 秒）"""
        import time as _t
        if not force and self._vv_ok is not None and _t.time() - getattr(self, '_vv_ts', 0) < 60:
            return self._vv_ok
        self._vv_ts = _t.time()
        try:
            r = requests.get(f"{self._voicevox_url()}/version", timeout=1.5)
            self._vv_ok = r.status_code == 200
        except Exception:
            self._vv_ok = False
        return self._vv_ok

    def list_voicevox_speakers(self):
        """返回 [(风格ID, 显示名)]"""
        try:
            r = requests.get(f"{self._voicevox_url()}/speakers", timeout=5)
            r.raise_for_status()
            result = []
            for sp in r.json():
                name = sp.get("name", "")
                for style in sp.get("styles", []):
                    result.append((str(style.get("id")), f"{name}（{style.get('name', '默认')}）"))
            return result
        except Exception as e:
            return None

    def _resolve_speaker_id(self, spec):
        """把「3」「ずんだもん」「ずんだもん（ノーマル）」解析为风格 ID"""
        spec = (spec or "").strip()
        if not spec:
            return None
        if spec in self.POPULAR_SPEAKERS:
            return self.POPULAR_SPEAKERS[spec]
        if spec.isdigit():
            return spec
        for spid, name in self.POPULAR_SPEAKERS.items():
            if spid in spec or spec in spid:
                return name
        speakers = self.list_voicevox_speakers()
        if speakers:
            for sid, sname in speakers:
                if spec == sname or spec in sname or sname in spec:
                    return sid
        return None

    def _speak_voicevox(self, text, speaker_id):
        """VOICEVOX 合成 + 可爱参数"""
        url = self._voicevox_url()
        r = requests.post(f"{url}/audio_query",
                          params={"text": text, "speaker": speaker_id}, timeout=15)
        r.raise_for_status()
        query = r.json()
        query["speedScale"] = float(self.get_setting("vv_speed", "1.1 稍快").split()[0])
        query["pitchScale"] = float(self.get_setting("vv_pitch", "+0.15 更可爱").split()[0])
        query["intonationScale"] = float(self.get_setting("vv_intonation", "1.2 活泼").split()[0])
        query["volumeScale"] = 1.1
        r2 = requests.post(f"{url}/synthesis", params={"speaker": speaker_id},
                           json=query, timeout=60)
        r2.raise_for_status()
        wav_path = os.path.join(self._cache_dir, "tts_last.wav")
        with open(wav_path, "wb") as f:
            f.write(r2.content)
        return wav_path

    # ============================================================
    # edge-tts 备胎
    # ============================================================
    def _speak_edge(self, text):
        import asyncio
        import edge_tts  # 惰性导入
        voice = self.EDGE_VOICES.get(self.get_setting("edge_voice", "Nanami（女·自然）"),
                                     "ja-JP-NanamiNeural")
        out = os.path.join(self._cache_dir, "tts_last.mp3")
        async def gen():
            tts = edge_tts.Communicate(text, voice)
            await tts.save(out)
        asyncio.run(gen())
        return out

    # ============================================================
    # 播放
    # ============================================================
    def _play(self, audio_path):
        if _pygame_ok():
            try:
                import pygame  # 惰性导入
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                self._speaking = True
                return
            except Exception as e:
                print(f"[TTS] pygame 播放失败，改用系统播放器: {e}")
        try:
            os.startfile(audio_path)
            self._speaking = True
        except Exception as e:
            print(f"[TTS] 无法播放: {e}")

    def _stop_playback(self):
        if _pygame_ok():
            try:
                import pygame  # 惰性导入
                if pygame.mixer.get_init():
                    pygame.mixer.music.stop()
            except Exception:
                pass
        self._speaking = False

    # ============================================================
    # 对外接口
    # ============================================================
    def speak(self, text):
        text = (text or "").strip()
        if not text:
            return "⚠️ 没有可朗读的内容", False
        engine = self.get_setting("engine", "自动（VOICEVOX 优先）")

        use_vv = engine == "VOICEVOX" or (engine.startswith("自动") and self.voicevox_available())
        if use_vv:
            sid = self._resolve_speaker_id(self.get_setting("voicevox_speaker", "3"))
            if not sid:
                return ("⚠️ VOICEVOX 声优 ID 无效，请运行 /tts speakers 查询", False)

            def worker_vv():
                try:
                    self._stop_playback()
                    path = self._speak_voicevox(text, sid)
                    self._play(path)
                except Exception as e:
                    print(f"[TTS] VOICEVOX 合成失败: {e}")

            threading.Thread(target=worker_vv, daemon=True).start()
            speaker = self.get_setting("voicevox_speaker", "3")
            return f"🔊 VOICEVOX 朗读中（声优 ID {speaker}）...", False

        # edge-tts 备胎
        if not _edge_ok():
            return "⚠️ 未安装 edge-tts：pip install edge-tts", False

        def worker_edge():
            try:
                self._stop_playback()
                path = self._speak_edge(text)
                self._play(path)
            except Exception as e:
                print(f"[TTS] edge-tts 合成失败: {e}")

        threading.Thread(target=worker_edge, daemon=True).start()
        return f"🔊 edge-tts 朗读中（{self.get_setting('edge_voice')}）...", False

    def speak_last(self):
        reply = self._last_reply
        core = self.core
        if not reply:
            nid = core.tree.current_leaf_id
            while nid and nid in core.tree.nodes:
                node = core.tree.nodes[nid]
                if node.role == 'assistant':
                    reply = node.content
                    break
                nid = node.parent_id
        if not reply:
            return "⚠️ 还没有 AI 回复可朗读"
        return self.speak(reply)[0]

    def on_message_received(self, user_input, ai_reply):
        self._last_reply = ai_reply or ""
        if self.get_setting("auto_speak", False) and ai_reply:
            self.speak(ai_reply)

    # ============================================================
    # 命令
    # ============================================================
    def on_command(self, command, args):
        if command != "tts":
            return None
        arg = (args or "").strip()
        low = arg.lower()
        if low in ("stop", "停止", "停"):
            self._stop_playback()
            return "🔇 已停止朗读", False
        if low in ("on", "开"):
            self.set_setting("auto_speak", True)
            return "✅ 已开启自动朗读", False
        if low in ("off", "关"):
            self.set_setting("auto_speak", False)
            return "✅ 已关闭自动朗读", False
        if low in ("speakers", "声优", "声线", "voices"):
            if not self.voicevox_available():
                return ("⚠️ 未检测到 VOICEVOX 引擎。\n"
                        "请到 https://voicevox.hiroshiba.jp/ 下载并启动 VOICEVOX，\n"
                        "然后输入 /tts speakers 重新查询。", False)
            speakers = self.list_voicevox_speakers()
            if not speakers:
                return "⚠️ 查询声优列表失败", False
            lines = "\n".join(f"  · {sid}: {nm}" for sid, nm in speakers[:30])
            return (f"🔊 VOICEVOX 声优（共 {len(speakers)} 个，显示前 30）：\n{lines}\n\n"
                    "选择：/tts voice <ID> 或 /tts voice ずんだもん", False)
        if low.startswith("voice ") or low.startswith("声优 ") or low.startswith("声线 "):
            spec = arg.split(maxsplit=1)[1] if " " in arg else ""
            sid = self._resolve_speaker_id(spec)
            if not sid:
                return f"⚠️ 无法识别声优「{spec}」，用 /tts speakers 查询", False
            self.set_setting("voicevox_speaker", sid)
            return f"✅ 已切换 VOICEVOX 声优（ID {sid}），点 🔊 朗读 试试", False
        if low in ("engine", "引擎"):
            vv = self.voicevox_available()
            edge = "可用" if _edge_ok() else "未安装"
            return (f"🔊 引擎状态\n  VOICEVOX：{'✅ 可用 ' + self._voicevox_url() if vv else '❌ 未运行（voicevox.hiroshiba.jp 下载）'}\n"
                    f"  edge-tts 备胎：{edge}\n  当前选择：{self.get_setting('engine', '自动')}", False)
        return self.speak(self._last_reply)
