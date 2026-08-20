# ============================================================
#   utau_voice.py - DICK 语音插件（UTAU + HANASU 双引擎）
#
#   UTAU：每个角色可挂专属声库，纯本地离线合成（putao 纯 Python 引擎）。
#   HANASU：VOICEVOX 本地说话引擎（HTTP :50021），自然说话。
#
#   傻瓜化：设置里选「引擎」即可——utau / hanasu / auto（auto 优先 HANASU，未就绪回落 UTAU）。
#   命令：/speak <文本> 合成并播放；设置里可开「AI 回复后自动朗读」
# ============================================================

import os
import threading

import app_paths
from plugin_base import PluginBase

try:
    from voice_engine import VoiceEngine, UtauEngine, HanasuEngine
except Exception:
    VoiceEngine = None


def _pygame_ok():
    try:
        import importlib.util
        return importlib.util.find_spec("pygame") is not None
    except Exception:
        return False


class UtauVoicePlugin(PluginBase):
    name = "UTAU 语音"
    version = "0.2"
    description = "语音引擎：UTAU（唱歌合成）+ HANASU（VOICEVOX 说话）双引擎，/speak <文本> 朗读（可自动朗读）"
    author = "seiki"
    enabled = False

    ui_buttons = [
        {"type": "method", "label": "🔊 朗读", "method": "speak_last"},
    ]

    settings_schema = [
        {"key": "engine", "label": "引擎（utau=UTAU / hanasu=VOICEVOX说话 / auto=自动优先HANASU）",
         "type": "text", "default": "auto"},
        {"key": "python", "label": "utau 环境 python 路径（相对 DICK 根目录或绝对）",
         "type": "text", "default": "utau_env\\Scripts\\python.exe"},
        {"key": "voicebank", "label": "UTAU 声库目录（已用 putao extract 解压）",
         "type": "text", "default": "utau_voicebanks\\默认声库"},
        {"key": "pitch", "label": "UTAU 音高（0-127，60=中音，男低 48 女高 64）",
         "type": "int", "default": 60},
        {"key": "duration", "label": "UTAU 每音素时长（毫秒，300≈常速 200≈急促）",
         "type": "int", "default": 300},
        {"key": "hanasu_url", "label": "HANASU（VOICEVOX）地址（默认 http://127.0.0.1:50021）",
         "type": "text", "default": "http://127.0.0.1:50021"},
        {"key": "hanasu_speaker", "label": "HANASU 音色 ID（VOICEVOX 音色编号，如 3）",
         "type": "int", "default": 3},
        {"key": "hanasu_speed", "label": "HANASU 语速（0.5-2.0，1.0=正常）",
         "type": "text", "default": "1.0"},
        {"key": "auto_ja", "label": "合成前中译日（中文正文自动翻译成日文再朗读，日文声库专用）",
         "type": "bool", "default": True},
        {"key": "auto", "label": "AI 回复后自动朗读", "type": "bool", "default": False},
    ]

    def _jp_plugin(self):
        """找日文补丁插件（提供 LLM 翻译）"""
        try:
            if self.plugin_manager:
                return self.plugin_manager.get_plugin("日文补丁")
        except Exception:
            pass
        return None

    def _is_japanese(self, text):
        import re
        return bool(re.search(r'[\u3040-\u30ff]', text or ""))

    def _prepare_text(self, text, cache_dir):
        """合成前预处理：中文 → 日文（走日文补丁 LLM 翻译，带文本 hash 缓存）。
        已是日文 / 翻译不可用 / 关闭开关 → 原样返回。返回 (最终文本, 是否翻译过)"""
        if not self.get_setting("auto_ja", True):
            return text, False
        if self._is_japanese(text):
            return text, False
        jp = self._jp_plugin()
        if jp is None or not hasattr(jp, "_translate"):
            return text, False
        # 翻译缓存：tts_cache/ja_<hash>.txt
        try:
            import hashlib
            h = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
            os.makedirs(cache_dir, exist_ok=True)
            cf = os.path.join(cache_dir, "ja_" + h + ".txt")
            if os.path.exists(cf):
                with open(cf, encoding="utf-8") as f:
                    return f.read().strip(), True
            translated = jp._translate(text, "jp")
            if not translated or translated.startswith("⚠️"):
                return text, False
            try:
                with open(cf, "w", encoding="utf-8") as f:
                    f.write(translated)
            except Exception:
                pass
            return translated, True
        except Exception:
            return text, False

    def _engine(self):
        if VoiceEngine is None:
            return None
        base = app_paths.get_base_dir()
        eng = str(self.get_setting("engine", "auto") or "auto").strip().lower()
        utau = UtauEngine(
            python=str(self.get_setting("python", "utau_env\\Scripts\\python.exe") or ""),
            voicebank=str(self.get_setting("voicebank", "utau_voicebanks\\默认声库") or ""),
            pitch=int(self.get_setting("pitch", 60) or 60),
            duration=int(self.get_setting("duration", 300) or 300),
            base_dir=base,
        )
        try:
            spd = float(str(self.get_setting("hanasu_speed", "1.0") or "1.0"))
        except (TypeError, ValueError):
            spd = 1.0
        hanasu = HanasuEngine(
            url=str(self.get_setting("hanasu_url", "http://127.0.0.1:50021") or ""),
            speaker=int(self.get_setting("hanasu_speaker", 3) or 3),
            speed=spd,
            base_dir=base,
        )
        return VoiceEngine(engine=eng if eng in ("utau", "hanasu", "auto") else "auto",
                           utau=utau, hanasu=hanasu)

    def _speak(self, text):
        text = (text or "").strip()
        if not text:
            return "说点啥？/speak <文本>"
        ve = self._engine()
        if ve is None:
            return "⚠️ voice_engine 加载失败（缺依赖？）"
        base = app_paths.get_base_dir()
        cache = os.path.join(base, "tts_cache")
        # 合成前预处理：中文 → 日文（日文声库才能念），带缓存；翻译全程隐藏，不显示任何标记
        final_text, translated = self._prepare_text(text, cache)
        try:
            out, eng_name = ve.synthesize(final_text, cache, pitch_mode="auto")  # 语气分析，避免死气沉沉
        except Exception as e:
            return "⚠️ 语音合成失败：" + str(e)[:150]
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
        if command in ("voicecheck", "语音检测"):
            return self._voice_check(), False
        return None

    def _voice_check(self):
        """日语系统/语音环境冲突检测报告"""
        try:
            from voice_engine import detect_jp_conflicts
            rep = detect_jp_conflicts()
            lines = ["🎙️ 语音环境检测："]
            for k, (ok, desc) in rep.items():
                lines.append(("  ✅ " if ok else "  ⚠️ ") + desc)
            # UTAU 就绪
            ve = self._engine()
            if ve:
                lines.append(("  ✅ " if ve.utau.is_ready() else "  ⚠️ ") + "UTAU 声库/环境" +
                             ("就绪" if ve.utau.is_ready() else "未就绪"))
                lines.append(("  ✅ " if ve.hanasu.is_ready() else "  ⚠️ ") + "HANASU(VOICEVOX)" +
                             ("运行中" if ve.hanasu.is_ready() else "未启动"))
                lines.append("  当前引擎: " + ve.engine)
            return "\n".join(lines)
        except Exception as e:
            return "⚠️ 语音环境检测失败：" + str(e)[:120]
