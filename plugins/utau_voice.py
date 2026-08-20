# ============================================================
#   utau_voice.py - UTAU 语音合成（/speak）
#
#   UTAU：每个角色可挂专属声库，纯本地离线合成（putao 纯 Python 引擎）。
#   需要：
#     - 独立 Python 3.11 环境（utau_env）装有 putao + pypinyin
#     - 一个 UTAU 声库目录（已用 `putao extract 声库.zip -t 目录` 解压）
#   命令：/speak <文本> 合成并播放；设置里可开「AI 回复后自动朗读」
# ============================================================

import os
import subprocess
import threading
import time

import app_paths
from plugin_base import PluginBase


def _pygame_ok():
    try:
        import importlib.util
        return importlib.util.find_spec("pygame") is not None
    except Exception:
        return False


class UtauVoicePlugin(PluginBase):
    name = "UTAU 语音"
    version = "0.1"
    description = "UTAU 声库合成语音：/speak <文本>（需 utau_env + putao + 声库）"
    author = "seiki"
    enabled = False

    ui_buttons = [
        {"type": "method", "label": "🔊 朗读", "method": "speak_last"},
    ]

    settings_schema = [
        {"key": "python", "label": "utau 环境 python 路径（相对 DICK 根目录或绝对）",
         "type": "text", "default": "utau_env\\Scripts\\python.exe"},
        {"key": "voicebank", "label": "声库目录（已用 putao extract 解压）",
         "type": "text", "default": "utau_voicebanks\\默认声库"},
        {"key": "pitch", "label": "音高（0-127，60=中音，男低 48 女高 64）",
         "type": "int", "default": 60},
        {"key": "duration", "label": "每音素时长（毫秒，300≈常速 200≈急促）",
         "type": "int", "default": 300},
        {"key": "auto", "label": "AI 回复后自动朗读", "type": "bool", "default": False},
    ]

    def _speak(self, text):
        text = (text or "").strip()
        if not text:
            return "说点啥？/speak <文本>"
        base = app_paths.get_base_dir()
        py = str(self.get_setting("python", "utau_env\\Scripts\\python.exe") or "")
        vb = str(self.get_setting("voicebank", "utau_voicebanks\\默认声库") or "")
        if not os.path.isabs(py):
            py = os.path.join(base, py)
        if not os.path.isabs(vb):
            vb = os.path.join(base, vb)
        if not os.path.exists(py):
            return "⚠️ 找不到 utau 环境：" + py + "（需 Python 3.11 venv 装 putao）"
        if not os.path.exists(vb):
            return "⚠️ 找不到声库：" + vb + "（放一个 UTAU 声库目录）"
        helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "utau_speak.py")
        cache = os.path.join(base, "tts_cache")
        os.makedirs(cache, exist_ok=True)
        out = os.path.join(cache, "utau_" + str(int(time.time() * 1000)) + ".wav")
        pitch = int(self.get_setting("pitch", 60) or 60)
        duration = int(self.get_setting("duration", 300) or 300)
        try:
            r = subprocess.run(
                [py, helper, vb, str(pitch), str(duration), text, out],
                capture_output=True, timeout=180,
                encoding="utf-8", errors="replace",
            )
        except Exception as e:
            return "⚠️ UTAU 合成失败：" + str(e)[:120]
        if r.returncode != 0 or not os.path.exists(out):
            return "⚠️ 合成失败：" + ((r.stdout or "") + (r.stderr or ""))[-200:]
        self._play(out)
        return "🗣️ " + text

    def _play(self, path):
        if not _pygame_ok():
            return
        try:
            import pygame  # 惰性导入
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except Exception as e:
            print(f"[UTAU] pygame 播放失败: {e}")

    def _current_ja(self, fallback):
        """中字日配：优先取当前 assistant 节点的 [ja] 配音句，无则用正文"""
        try:
            leaf = self.core.tree.current_leaf_id
            node = self.core.tree.nodes.get(leaf)
            if node:
                ja = (node.metadata or {}).get("ja")
                if isinstance(ja, str) and ja.strip():
                    return ja
        except Exception:
            pass
        return fallback

    def speak_last(self):
        try:
            chain = self.core.get_current_chain()
            for m in reversed(chain):
                if m.get("role") == "assistant":
                    content = str(m.get("content", "")).strip()
                    if content:
                        return self._speak(self._current_ja(content)[:200])
                    break
        except Exception:
            pass
        return "还没有可朗读的回复"

    def on_message_received(self, user_input, ai_reply):
        if not self.get_setting("auto", False):
            return
        text = self._current_ja(ai_reply)
        if text and text.strip():
            threading.Thread(target=lambda: self._speak(text[:200]),
                             daemon=True).start()

    def on_command(self, command, args):
        if command == "speak":
            return self._speak(args), False
        return None
