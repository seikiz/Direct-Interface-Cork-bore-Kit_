# -*- coding: utf-8 -*-
"""shell_api_settings —— 从 Kit.py 拆出的 mixin（^api_set|^api_get）。

包含方法：api_set_stop、api_set_sampling、api_get_regex_rules、api_set_regex_rules、api_set_dev_mode、api_set_humanize、api_set_style_guard、api_set_preset、api_get_persona、api_set_persona、api_get_role、api_get_world…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

from shell_util import BUILTIN_RELAY

import base64
import codex_core
import i18n
import image_gen
import json
import lookahead
import os
import plugin_manager
import re

class ApiSettingsMixin:
    """shell_api_settings"""

    def api_set_stop(self, stop_text):
        """设置停止序列（逗号/换行分隔；空 = 用预设/模型默认）"""
        parts = (stop_text or "").replace("，", ",").replace("\n", ",").split(",")
        self.config["stop_sequences"] = [x.strip() for x in parts if x.strip()]
        self.core.set_stop_sequences(self._effective_stop())
        self._save_config()
        return {"ok": True, "stop": list(self.core.stop_sequences or [])}


    def api_set_sampling(self, temperature, top_p):
        """设置采样参数（温度/top_p；空 = 模型默认）"""
        self.config["temperature"] = temperature
        self.config["top_p"] = top_p
        self.core.set_sampling(temperature, top_p)
        self._save_config()
        return {"ok": True,
                "temperature": self.core.temperature,
                "top_p": self.core.top_p}


    def api_get_regex_rules(self):
        """全局正则规则（编辑预填）"""
        rules = []
        try:
            with open(os.path.join(self.base_dir, "regex_rules.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                rules = data
        except Exception:
            pass
        return {"rules": rules}


    def api_set_regex_rules(self, rules_json):
        """保存全局正则规则"""
        try:
            parsed = json.loads(rules_json) if isinstance(rules_json, str) else rules_json
            if not isinstance(parsed, list):
                return {"ok": False, "err": "格式错误"}
            cleaned = []
            for x in parsed:
                if not isinstance(x, dict) or not str(x.get("pattern") or "").strip():
                    continue
                scope = str(x.get("scope") or "both")
                if scope not in ("ai", "user", "both"):
                    scope = "both"
                cleaned.append({
                    "id": str(x.get("id") or "")[:30],
                    "name": str(x.get("name") or x.get("id") or "")[:30],
                    "pattern": str(x.get("pattern") or "").strip(),
                    "replace": str(x.get("replace") or ""),
                    "scope": scope,
                    "enabled": bool(x.get("enabled", True)),
                })
            with open(os.path.join(self.base_dir, "regex_rules.json"), "w", encoding="utf-8") as f:
                json.dump(cleaned, f, ensure_ascii=False, indent=2)
            return {"ok": True, "count": len(cleaned)}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_set_dev_mode(self, enabled):
        """开发者模式开关（解锁角色卡高级设置：内置游戏等）"""
        self.config["dev_mode"] = bool(enabled)
        self._save_config()
        return {"ok": True, "dev_mode": bool(enabled)}


    def api_set_humanize(self, enabled):
        """去 AI 味开关（默认开）：注入人性化对话规则"""
        self.config["humanize"] = bool(enabled)
        self.core.humanize = bool(enabled)
        self._save_config()
        return {"ok": True, "humanize": bool(enabled)}


    def api_set_style_guard(self, enabled, long_sentence=None):
        """确定性风格闸开关（默认开）：写树前洗文学腔表达，架构外防漂移。
        long_sentence=True 时开启长句模式：不拆长句，允许更流畅/文学化的表达。"""
        self.config["style_guard"] = bool(enabled)
        self.core.style_guard = bool(enabled)
        if long_sentence is not None:
            self.config["style_guard_long"] = bool(long_sentence)
            self.core.style_guard_long = bool(long_sentence)
        self._save_config()
        return {"ok": True, "style_guard": bool(enabled),
                "style_guard_long": bool(getattr(self.core, "style_guard_long", False))}


    def api_set_preset(self, name):
        self.preset_name = name or ""
        self.config["prompt_preset"] = self.preset_name
        self._save_config()
        preset = None
        for p in self.presets:
            if p.get("name") == self.preset_name:
                preset = p
                break
        self.core.set_prompt_preset(preset if preset and preset.get("name") else None)
        # 指令模板：预设变更后重新应用停止序列（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌预设可带 stop_sequences）
        self.core.set_stop_sequences(self._effective_stop())
        return {"ok": True}


    def api_get_persona(self):
        """返回玩家角色卡结构化字段（供精细化表单预填）"""
        p = self.persona
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = None
        p = p or {}
        return {
            "name": str(p.get("name") or ""),
            "legacy": str(p.get("legacy") or ""),
            "appearance": str(p.get("appearance") or ""),
            "personality": str(p.get("personality") or ""),
            "background": str(p.get("background") or ""),
            "speech": str(p.get("speech") or ""),
            "first_mes": str(p.get("first_mes") or ""),
            "mes_example": str(p.get("mes_example") or ""),
            "notes": str(p.get("notes") or ""),
            "advanced": p.get("advanced") if isinstance(p.get("advanced"), dict) else None,
        }


    def api_set_persona(self, persona_json):
        old = (self.persona or {}).get("name") or ""
        try:
            self.persona = json.loads(persona_json) or None
        except Exception:
            self.persona = None
        new = (self.persona or {}).get("name") or ""
        self.config["persona"] = json.dumps(self.persona, ensure_ascii=False) if self.persona else ""
        self._save_config()
        self.core.set_player_persona(self.persona)
        # 玩家卡改名：头像文件跟着改，保持「聊天显示名 = 头像文件名」一致
        eff = new or "你"
        if old and old != new and old != eff:
            avdir = os.path.join(self.save_dir, "avatars")
            for src in (old, "你"):
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    f = os.path.join(avdir, src + ext)
                    if os.path.exists(f):
                        try:
                            dst = os.path.join(avdir, eff + ext)
                            if os.path.exists(dst):
                                os.remove(dst)
                            os.rename(f, dst)
                        except Exception:
                            pass
                        break
        return {"ok": True}


    def api_get_role(self, name):
        """编辑预填：返回人物卡完整数据（结构化字段 + 旧版完整设定）
        旧卡（无结构化字段）→ legacy 预填其原始设定，编辑不丢内容"""
        for r in self.roles:
            if r["name"] == name:
                fields = r.get("fields") or {}
                has_fields = any(v for v in fields.values() if v)
                legacy = r.get("legacy") or ""
                if not legacy and not has_fields:
                    legacy = (r.get("data") or {}).get("system_prompt") or ""
                adv = (r.get("data") or {}).get("advanced") or None
                # 二次防护：读取时对已有卡面做 HTML 注入清洗（兼容旧数据）
                if isinstance(adv, dict) and adv.get("card_face"):
                    adv["card_face"] = codex_core.sanitize_html(str(adv["card_face"]))
                return {"name": r["name"], "prompt": r["prompt"],
                        "legacy": legacy, "fields": fields,
                        "unlocked": bool(r.get("unlocked", False)),
                        "advanced": adv}
        return None

    # ---------- 角色卡·多存档（新存档功能：保存/读取/切换/删除/重命名） ----------

    def api_get_world(self, name, last_user_text=""):
        """编辑预填：返回世界卡完整数据（附带条目触发状态）"""
        for w in self.worlds:
            if w.get("name") == name:
                w = dict(w)
                txt = (last_user_text or "").lower()
                ent = []
                for e in w.get("entries", []):
                    e = dict(e)
                    e["triggered"] = self._entry_hit(e, txt)
                    ent.append(e)
                w["entries"] = ent
                return w
        return None


    def api_get_avatar(self, name):
        """自定义头像 base64（无则 null，前端画首字圆头像）"""
        avdir = os.path.join(self.save_dir, "avatars")
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = os.path.join(avdir, str(name) + ext)
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f:
                        mime = "image/" + ("jpeg" if ext == ".jpg" else ext[1:])
                        return "data:" + mime + ";base64," + base64.b64encode(f.read()).decode()
                except Exception:
                    return None
        return None


    def api_set_avatar(self, name, b64, ext):
        try:
            raw = base64.b64decode(b64.split(",", 1)[-1])
            avdir = os.path.join(self.save_dir, "avatars")
            os.makedirs(avdir, exist_ok=True)
            ext = (ext or "png").replace("jpeg", "jpg")
            with open(os.path.join(avdir, str(name) + "." + ext), "wb") as f:
                f.write(raw)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)}

    # ---------- 聊天壁纸（核心，自定义图片；无则默认主题背景） ----------
    _WALLPAPER_EXTS = (".png", ".jpg", ".jpeg", ".webp")


    def api_get_chat_wallpaper(self):
        return {"ok": True, "data": self._wallpaper_data_url()}


    def api_set_chat_wallpaper(self):
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("图片 (*.png;*.jpg;*.jpeg;*.webp)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        src = res[0] if isinstance(res, (list, tuple)) else res
        ext = os.path.splitext(str(src))[1].lower()
        if ext not in self._WALLPAPER_EXTS:
            ext = ".png"
        try:
            import shutil as _sh
            for e in self._WALLPAPER_EXTS:
                q = os.path.join(self.save_dir, "wallpaper" + e)
                if os.path.exists(q):
                    os.remove(q)
            _sh.copy2(src, os.path.join(self.save_dir, "wallpaper" + ext))
        except Exception as e:
            return {"ok": False, "err": "保存失败：" + str(e)[:200]}
        return {"ok": True, "data": self._wallpaper_data_url()}


    def api_set_l2d(self, key, value):
        if key not in ("model", "scale", "pos", "opacity", "draggable", "breath"):
            return {"ok": False, "err": "bad key"}
        try:
            p = self.plugin_manager.get_plugin("Live2D 看板娘")
            if p is not None and hasattr(p, "set_setting"):
                p.set_setting(key, value)
                return {"ok": True}
        except Exception:
            pass
        return {"ok": False, "err": "看板娘模块未加载"}

    # ---------- 跑团（TRPG）会话态 / 退出机制 ----------

    def api_set_drift_keys(self, keys_json):
        """设置当前角色的本场关键词（逗号/顿号分隔的字符串）。"""
        name = (self.selected_roles or [None])[0]
        if not name:
            return {"ok": False, "err": "先选一个角色"}
        raw = keys_json or ""
        if isinstance(raw, str) and raw.strip().startswith("["):
            try:
                keys = [str(x).strip() for x in json.loads(raw) if str(x).strip()]
            except Exception:
                keys = []
        else:
            keys = [k.strip() for k in re.split(r"[,，、\s]+", str(raw)) if k.strip()]
        allk = dict(self.config.get("drift_keys") or {})
        allk[name] = keys
        self.config["drift_keys"] = allk
        self._save_config()
        return {"ok": True, "keys": keys, "role": name}


    def api_set_rubric(self, text):
        """设置当前角色的价值标准（每行一条，或用 ；分隔）。

        这是「价值声明」——比训练一个 PRM 便宜几个数量级的替代品。
        但代价必须说清楚：**写不好比不写更糟**，声明错了，搜索会忠实地放大它。
        """
        name = (self.selected_roles or [None])[0]
        if not name:
            return {"ok": False, "err": "先选一个角色"}
        try:
            import rubric as _rb
            items = _rb.normalize(text or "")
            cap = _rb.MAX_CRITERIA
        except Exception:
            items = [x.strip() for x in str(text or "").split("\n") if x.strip()]
            cap = 8
        allr = dict(self.config.get("rubrics") or {})
        allr[name] = items
        self.config["rubrics"] = allr
        self._save_config()
        return {"ok": True, "role": name, "criteria": items, "max": cap,
                "note": "最多 %d 条；条数越多模型越容易平均化、判不出差别" % cap}


    def api_set_lookahead(self, enabled, branches=None, depth=None, cap=None):
        """开关前瞻展开。开之前请先设好本场关键词 —— 没目标就无从比较。"""
        cfg = dict(self.config.get("lookahead") or {})
        cfg["on"] = bool(enabled)
        if branches is not None:
            cfg["branches"] = max(1, min(int(branches or 2), 5))
        if depth is not None:
            cfg["depth"] = max(1, min(int(depth or 2), 5))
        if cap is not None:
            cfg["cap"] = max(1, min(int(cap or 12), 40))
        self.config["lookahead"] = cfg
        self._save_config()
        on = self._sync_speculator()
        try:
            import lookahead
            b = int(cfg.get("branches") or lookahead.DEF_BRANCHES)
            d = int(cfg.get("depth") or lookahead.DEF_DEPTH)
            cost = b * d
        except Exception:
            cost = 0
        return {"ok": True, "on": on, "config": cfg,
                "per_turn_calls": cost,
                "note": "每轮最多 %d 次额外调用；没设本场关键词时不会前瞻" % cost}


    def api_get_time_scale(self):
        """当前软件时间流速 + 可选的预设档位（给按钮用，不需要用户输入数字）。"""
        try:
            import time_scale as _ts
        except Exception as e:
            return {"ok": False, "err": "缺 time_scale 模块：" + str(e)[:120]}
        cur = _ts.load()
        return {
            "ok": True,
            "scale": cur,
            "describe": _ts.describe(cur),
            "min": _ts.MIN_SCALE,
            "max": _ts.MAX_SCALE,
            "presets": [{"scale": m, "name": n} for m, n in _ts.PRESETS],
            "age_mode": getattr(__import__("salience"), "AGE_MODE", "real"),
        }


    def api_set_time_scale(self, scale):
        """设定流速。只接受预设里有的值（或合法范围内的数字）。"""
        try:
            import time_scale as _ts
        except Exception as e:
            return {"ok": False, "err": "缺 time_scale 模块：" + str(e)[:120]}
        val = _ts.save(scale)
        return {"ok": True, "scale": val, "describe": _ts.describe(val)}


    def api_set_ranker(self, enabled):
        """启用/停用训好的排序器。启用后它会替代启发式给前瞻分支打分。"""
        cfg = dict(self.config.get("ranker") or {})
        cfg["on"] = bool(enabled)
        self.config["ranker"] = cfg
        self._save_config()
        return {"ok": True, "on": cfg["on"]}


    def api_set_budget(self, tokens):
        try:
            tokens = int(tokens or 0)
        except (TypeError, ValueError):
            tokens = 0
        tokens = max(0, tokens)
        self.config["context_budget"] = tokens
        self.core.set_context_budget(tokens)
        self._save_config()
        return {"ok": True, "budget": tokens}


    def api_set_auto_turn(self, on):
        self.auto_turn = bool(on)
        self.config["auto_turn"] = self.auto_turn
        self._save_config()
        return {"ok": True, "auto_turn": self.auto_turn}


    def api_set_font(self, idx):
        try:
            idx = int(idx or 0)
        except (TypeError, ValueError):
            idx = 0
        idx = max(0, min(2, idx))
        self.font_size = idx
        self.config["ui_font"] = idx
        self._save_config()
        return {"ok": True, "font": idx}


    def api_set_plugin(self, name, enabled):
        p = self.plugin_manager.get_plugin(name)
        if not p:
            return {"ok": False, "err": "插件不存在"}
        # 已并入核心的 UI 插件禁止禁用（底层能力，恒生效）
        if p.name in self.CORE_UI_PLUGINS and not enabled:
            return {"ok": False, "err": "该能力已并入核心，无法关闭"}
        p.enabled = bool(enabled)
        states = dict(self.config.get("plugin_states") or {})
        states[p.name] = p.enabled
        self.config["plugin_states"] = states
        self._save_config()
        return {"ok": True}


    def api_set_plugin_setting(self, name, key, value):
        p = self.plugin_manager.get_plugin(name)
        if not p:
            return {"ok": False, "err": "插件不存在"}
        schema = {item.get("key"): item for item in (getattr(p, "settings_schema", None) or [])}
        item = schema.get(key)
        if not item:
            return {"ok": False, "err": "未知设置项"}
        vtype = item.get("type", "text")
        try:
            if vtype == "bool":
                value = bool(value)
            elif vtype == "int":
                value = int(float(value or 0))
            else:
                value = str(value or "")
        except (TypeError, ValueError):
            return {"ok": False, "err": "数值格式错误"}
        p.set_setting(key, value)
        return {"ok": True}


    def api_get_image_presets_file(self):
        """给设置面板的预设编辑器：用户自定义预设文件的原始内容。"""
        import image_gen
        obj = image_gen.user_presets_json(self.base_dir)
        example = {
            "guofeng": {"label": "国风线稿", "prompt": "chinese ink line art, ",
                        "desc": "自己加的风格"},
            "photoreal2": "raw photo, 85mm, f1.8, ",
            "_说明": "下划线开头的键会被忽略，可以拿来写注释；同名 id 会覆盖内置预设",
        }
        return {"ok": True, "presets": obj, "example": example,
                "path": image_gen.presets_path(self.base_dir),
                "builtin": [{"id": k, "label": v["label"]} for k, v in image_gen.PRESETS.items()]}


    def api_set_language(self, lang):
        """切换界面语言：zh / en / ja（认不出的值退回中文，与 i18n.set_lang 一致）"""
        i18n.set_lang(lang)
        self.language = i18n.lang()
        self.config["language"] = self.language
        self._save_config()
        return {"ok": True, "lang": self.language}


    def api_set_theme(self, theme_idx, accent_idx):
        self.config["ui_theme"] = int(theme_idx)
        self.config["ui_accent"] = int(accent_idx)
        self._save_config()
        return {"ok": True}


    def api_set_proxy(self, proxy):
        """设置 LLM 通道代理（http/https/socks5；空串 = 直连）"""
        proxy = (proxy or "").strip()
        self.config["proxy"] = proxy
        self.core.set_proxy(proxy)
        self._save_config()
        return {"ok": True}


    def api_set_relay(self, url):
        """设置内置代理通道地址；空串 = 关闭（恢复纯直连）"""
        url = ((url or "").strip().rstrip("/")) or ""
        self.config["relay_url"] = url
        self.core.relay_on = False          # 重置，回到「直连优先」模式
        self.core.set_relay(url or BUILTIN_RELAY)
        self._save_config()
        return {"ok": True}

