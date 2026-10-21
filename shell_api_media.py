# -*- coding: utf-8 -*-
"""shell_api_media —— 从 Kit.py 拆出的 mixin（^api_gen_image|^api_gen_presets|^api_save_image|^api_speak|^api_save_key|^api_test_and_save|^api_open）。

包含方法：api_open_path、api_speak_node、api_gen_image、api_gen_presets、api_save_image_presets_file、api_save_key、api_test_and_save_key、api_save_image_gen、api_open_url

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。
"""
from __future__ import annotations

import app_paths
import os
from shell_util import BASE_DIR, BUILTIN_RELAY, PROVIDERS

class ApiMediaMixin:
    """shell_api_media"""

    def api_open_path(self, path):
        """在资源管理器中打开/定位文件（打包产物定位用）"""
        try:
            if path and os.path.exists(path):
                os.startfile(os.path.dirname(os.path.abspath(path)))
                return {"ok": True}
            return {"ok": False, "err": "not found"}
        except Exception as e:
            return {"ok": False, "err": str(e)}



    def api_speak_node(self, node_id):
        """消息旁喇叭按钮：按 node_id 朗读该条 AI 消息（合成缓存于 tts_cache，重复点击不重合成）。
        取 [ja] 日配句优先，无则用正文；走 UTAU/HANASU 双引擎。"""
        try:
            node = self.core.tree.nodes.get(node_id)
            if not node:
                return {"ok": False, "err": "节点不存在"}
            if node.role != "assistant":
                return {"ok": False, "err": "仅 AI 消息可朗读"}
            p = None
            try:
                if self.plugin_manager:
                    p = self.plugin_manager.get_plugin("UTAU 语音")
            except Exception:
                p = None
            if not p or not getattr(p, "enabled", False):
                return {"ok": False, "err": "未启用语音插件（设置 → 插件 → UTAU 语音）"}
            if not hasattr(p, "_speak"):
                return {"ok": False, "err": "语音插件缺少合成接口"}
            # 优先 [j<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌a] 日配句
            text = ""
            try:
                ja = (node.metadata or {}).get("ja")
                if isinstance(ja, str) and ja.strip():
                    text = ja.strip()
            except Exception:
                pass
            if not text:
                text = str(node.content or "").strip()
            if not text:
                return {"ok": False, "err": "无内容可朗读"}
            # 合成缓存：按 node_id 复用
            base = getattr(app_paths, "get_base_dir", lambda: BASE_DIR)()
            cache = os.path.join(base, "tts_cache")
            os.makedirs(cache, exist_ok=True)
            cached = os.path.join(cache, "node_" + str(node_id) + ".wav")
            if os.path.exists(cached):
                p._play(cached)
                return {"ok": True, "cached": True}
            # 合成前预处理：中文 → 日文（走日文补丁翻译，日文声库才能念）
            final_text = text[:200]
            if hasattr(p, "_prepare_text"):
                final_text, _tr = p._prepare_text(final_text, cache)
            out, _eng = p._engine().synthesize(final_text, cache, pitch_mode="auto") if hasattr(p, "_engine") else (None, None)
            if out and os.path.exists(out):
                try:
                    import shutil
                    shutil.copyfile(out, cached)
                except Exception:
                    pass
                p._play(out)
                return {"ok": True}
            # 兼容旧插件（无 _engine 的 _speak 直接播放）
            res = p._speak(text[:200])
            if isinstance(res, str) and res.startswith("⚠️"):
                return {"ok": False, "err": res}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}



    def api_gen_image(self, prompt, preset="anime", size="1024x1024", negative_prompt="",
                      extra="", seed=None):
        """生图：预设风格 + 提示词 → 图片（base64/url）。配置走设置里的生图 Key/端点/后端。

        seed 留空 = 后端随机；填了就固定（配合「🎲 重抽」可以一直换到满意为止）。
        上一次的输入会记进 config.image_gen_last，下次打开面板自动回填 ——
        调提示词是个反复试的过程，不该每次都重新敲一遍。
        """
        import image_gen
        c = self._image_gen_cfg()
        # 要不要 key 交给引擎按【后端】判断：三种本地/免费后端允许留空，
        # 别在 UI 层写死 —— 写死了就没法用免费生图。
        if not c["key"] and image_gen.needs_key(c["base_url"], c["backend"]):
            return {"ok": False, "err": "未配置生图 API Key（设置 → 生图；"
                                        "或把端点换成免费的 Pollinations / 本地 SD）"}
        presets = image_gen.load_presets(self.base_dir)
        # 只有「空」才算随机；seed=0 是合法种子，别当成没填
        if seed is None or (isinstance(seed, str) and not seed.strip()):
            seed = None
        try:
            seed = int(seed) if seed is not None else None
        except Exception:
            seed = None
        ok, data, msg = image_gen.generate(
            prompt, preset=preset, size=size, api_key=c["key"], base_url=c["base_url"],
            model=c["model"], negative_prompt=negative_prompt, extra=extra,
            seed=seed, presets=presets, backend=c["backend"])
        if not ok:
            return {"ok": False, "err": msg}
        # 记住这次的输入（调提示词要反复试，别让人每次重敲）
        try:
            self.config["image_gen_last"] = {
                "prompt": prompt, "preset": preset, "size": size,
                "negative_prompt": negative_prompt, "extra": extra,
                "seed": data.get("seed") if data.get("seed") is not None else seed,
            }
            self._save_config()
        except Exception:
            pass
        # 生图结果进聊天（sys_msgs 带 image 字段，_rebuild_messages 会展示）
        try:
            if data.get("b64"):
                # 用引擎回报的真实类型：免 Key 后端（Pollinations）回的是 JPEG，
                # 一律写成 image/png 属于谎报类型（浏览器通常能猜对，但别指望）
                mime = data.get("mime") or "image/png"
                data_url = "data:" + mime + ";base64," + data["b64"]
            elif data.get("url"):
                data_url = data["url"]
            else:
                return {"ok": False, "err": "生图无结果"}
            self.sys_msgs.append({"kind": "ai", "speaker": "🎨 生图",
                                  "content": "[" + preset + "] " + prompt,
                                  "image": data_url, "node_id": None})
            self._rebuild_messages()
            return {"ok": True, "image": data_url, "preset": preset,
                    "seed": data.get("seed"), "note": "" if msg == "ok" else msg,
                    "backend": image_gen.resolve_backend(c["base_url"], c["backend"])}
        except Exception as e:
            return {"ok": False, "err": "生图结果处理失败：" + str(e)[:100]}



    def api_gen_presets(self):
        """生图预设列表（内置 + 用户自定义 image_presets.json）"""
        import image_gen
        return {"ok": True, "presets": image_gen.list_presets(
            image_gen.load_presets(self.base_dir))}



    def api_save_image_presets_file(self, text):
        """保存用户预设文件（传 '{}' 即恢复内置默认）。"""
        import json as _json
        import image_gen
        try:
            obj = _json.loads(text or "{}")
        except Exception as e:
            return {"ok": False, "err": "JSON 格式有误：" + str(e)[:120]}
        ok, msg = image_gen.save_presets(self.base_dir, obj)
        if not ok:
            return {"ok": False, "err": msg}
        return {"ok": True, "msg": msg, "presets": image_gen.list_presets(
            image_gen.load_presets(self.base_dir))}

    # ---------- 插件要界面：走 host_ui 这条唯一通道（别让插件自己拉 GUI 库） ----------


    def api_save_key(self, key, base_url, model, provider_id=None):
        pid = (provider_id or self.provider_id or "deepseek").strip()
        self.provider_id = pid
        k = (key or "").strip()
        self.api_keys[pid] = k
        self.config["api_keys"] = self.api_keys
        self.config["provider"] = pid
        self.config["api_key"] = k  # 兼容旧字段
        self.config["base_url"] = (base_url or "").strip()
        self.config["model"] = (model or "").strip()
        # 无条件重建客户端：切换厂商时不能沿用旧厂商的 Key 与 URL
        # 免费厂商（OVH 免费链/Ollama）无 Key：用占位符构造客户端（其服务端忽略认证头）
        self.core.set_api_key(k if k else "free")
        if self.config["base_url"]:
            self.core.set_base_url(self.config["base_url"])
        if self.config["model"]:
            self.core.set_model(self.config["model"])
        # 重建客户端会丢失代理，重新应用
        if self.config.get("proxy"):
            self.core.set_proxy(self.config["proxy"])
        # 换厂商后停止序列按新模型家族默认生效
        self.core.set_stop_sequences(self._effective_stop())
        # 免费厂商默认走中转绕墙：免费链（OVH/本地）常被墙或不稳，直连大概率失败。
        # 若配了中转地址，直接 relay_on，免费模型全程走中转，避免"第一次直连失败"的停顿。
        prov = next((p for p in PROVIDERS if p["id"] == pid), None)
        if prov and prov.get("free"):
            self.core.relay_on = bool(self.core.relay_base or self.config.get("relay_url") or BUILTIN_RELAY)
            self.core.client = self.core._build_client()
        else:
            self.core.relay_on = False
        self._save_config()
        # 进度同步：把模型连接配置推到工坊服务器（后台线程，不阻塞）
        self._ws_push_api()
        return {"ok": True, "provider": pid}

    # ---- 向导第③步：测试并保存（2026-11 新增） ----


    def api_test_and_save_key(self, key, base_url, model, provider_id=None):
        """向导第③步「测试并保存」：**先真连一次，通了才落盘**。

        判据（宁严不松）：
          ① GET {base}/models 返回 2xx → 通；
          ② 该端点 404/405（少数 OpenAI 兼容实现不实现 /models）→ 用一条 1 token 的最小对话兜底；
          ③ 其它状态码 → 不保存，回 `err`（人话）+ `hint`（下一步怎么做）。
        免 Key 厂商（OVH 免费链 / Ollama 本地）没有 Key 可验，直接落到保存。
        """
        import requests
        pid = (provider_id or self.provider_id or "deepseek").strip()
        prov = next((p for p in PROVIDERS if p["id"] == pid), None)
        k = (key or "").strip()
        base = (base_url or (prov or {}).get("base_url") or "").strip().rstrip("/")
        models = (prov or {}).get("models") or []
        m = (model or "").strip() or (models[0] if models else "")
        free = bool(prov and prov.get("free"))
        if not base:
            return {"ok": False, "err": "Base URL 是空的",
                    "hint": "回第①步选一个服务商，Base URL 会跟着填好"}
        if not k and not free:
            return {"ok": False, "err": "还没有填 Key",
                    "hint": "回第②步粘一枚 Key；不想填就点「稍后再说」用免费链"}

        def _save():
            self.api_save_key(k, base, m, pid)
            return {"ok": True, "provider": pid, "model": m, "base_url": base}

        if free:
            return _save()
        proxy = self.config.get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        headers = {"Authorization": "Bearer " + k}
        try:
            r = requests.get(base + "/models", headers=headers, proxies=proxies, timeout=12)
            if r.status_code in (200, 201):
                return _save()
            if r.status_code in (404, 405):
                body = {"model": m, "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1, "stream": False}
                h2 = dict(headers)
                h2["Content-Type"] = "application/json"
                r2 = requests.post(base + "/chat/completions", headers=h2, json=body,
                                   proxies=proxies, timeout=25)
                if r2.status_code in (200, 201):
                    return _save()
                return {"ok": False, "err": self._probe_reason(r2.status_code, r2.text),
                        "hint": self._probe_hint(r2.status_code)}
            return {"ok": False, "err": self._probe_reason(r.status_code, r.text),
                    "hint": self._probe_hint(r.status_code)}
        except Exception as e:
            return {"ok": False, "err": "%s: %s" % (type(e).__name__, e),
                    "hint": "网络层失败：多半是超时或被墙，填个代理再试；也可以先点「稍后再说」用免费链"}



    def api_save_image_gen(self, key, base_url, model, backend="auto"):
        """保存生图配置（key/端点/模型/后端），存 config.json"""
        import image_gen
        self.config["image_gen_key"] = (key or "").strip()
        self.config["image_gen_base_url"] = (base_url or "https://api.siliconflow.cn/v1").strip()
        self.config["image_gen_model"] = (model or "black-forest-labs/FLUX.1-schnell").strip()
        b = (backend or "auto").strip().lower()
        self.config["image_gen_backend"] = b if b in image_gen.BACKENDS else "auto"
        self._save_config()
        return {"ok": True, "backend": image_gen.resolve_backend(
            self.config["image_gen_base_url"], self.config["image_gen_backend"]),
            "needs_key": image_gen.needs_key(self.config["image_gen_base_url"],
                                             self.config["image_gen_backend"])}



    def api_open_url(self, url):
        """在系统浏览器打开模型商官网（注册/充值跳转）"""
        url = (url or "").strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return {"ok": False, "err": "invalid url"}
        try:
            import webbrowser
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)}


