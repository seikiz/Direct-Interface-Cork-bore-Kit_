# -*- coding: utf-8 -*-
"""shell_host —— 从 Kit.py 拆出的 mixin（^_host_|^_backup_|^_vision_|^_anchor_）。

包含方法：_vision_describe、_anchor_block、_vision_then_send、_vision_direct_done、_backup_service、_backup_dirs、_host_window、_host_ask_file、_host_ask_save、_host_notify

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

import i18n
import json
import os
import plugin_manager
import re

class HostMixin:
    """shell_host"""

    @staticmethod
    def _vision_http_post(url, body, headers, timeout, user_proxy=None):
        """视觉识图统一 POST：不继承坏系统代理，用户未配代理且直连网络失败时静默走内置隐藏隧道。"""
        import requests

        def _send(px):
            proxies = {"http": px, "https": px} if px else None
            sess = requests.Session()
            sess.trust_env = bool(px)
            try:
                return sess.post(url, json=body, headers=headers, timeout=timeout, proxies=proxies)
            finally:
                try:
                    sess.close()
                except Exception:
                    pass

        try:
            return _send(user_proxy)
        except requests.exceptions.RequestException:
            if not user_proxy:
                try:
                    import hidden_proxy
                    hp = hidden_proxy.ensure_proxy(url)
                    if hp:
                        return _send(hp)
                except Exception:
                    pass
            raise

    def _vision_endpoint(self, image_b64, mime, prompt_text, sys_prompt="", max_tokens=4096):
        """按当前模型商构造视觉请求（兼容 DeepSeek / OpenAI / Gemini / Anthropic Claude）。"""
        key = (self.config.get("api_key") or "").strip()
        base = (self.config.get("base_url") or "https://api.deepseek.com").strip().rstrip("/")
        if not key or not base:
            return None, None, None, False
        low = base.lower()
        is_claude = ("api.anthropic.com" in low) or (getattr(self, "provider_id", "") == "anthropic")
        if "deepseek.com" in low:
            model = "deepseek-flash"
        else:
            model = (self.config.get("model") or getattr(self.core, "model", "") or "deepseek-flash").strip()
        eff_mime = mime or "image/png"
        if is_claude:
            url = base + "/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            }
            body = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": eff_mime, "data": image_b64}},
                    {"type": "text", "text": prompt_text},
                ]}],
            }
            if sys_prompt:
                body["system"] = sys_prompt
            return url, body, headers, True
        url = base + "/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
        data_url = "data:" + eff_mime + ";base64," + image_b64
        msgs = []
        if sys_prompt:
            msgs.append({"role": "system", "content": sys_prompt})
        msgs.append({"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": prompt_text},
        ]})
        body = {"model": model, "messages": msgs, "max_tokens": max_tokens, "stream": False}
        return url, body, headers, False

    @staticmethod
    def _extract_vision_text(resp, is_claude=False):
        if resp is None or resp.status_code >= 400:
            return None
        data = resp.json() or {}
        if is_claude:
            parts = [b.get("text", "") for b in (data.get("content") or [])
                     if isinstance(b, dict) and b.get("type") == "text"]
            txt = "".join(parts).strip()
            return txt or None
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        return content.strip() if isinstance(content, str) and content.strip() else None

    def _vision_describe(self, image_b64, mime):
        """看图描述：优先用当前配置的视觉模型（DeepSeek / OpenAI / Gemini / Claude），失败回落免费链。"""
        proxy = (self.config.get("proxy") or "").strip() or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        url, body, headers, is_claude = self._vision_endpoint(
            image_b64, mime,
            "请用中文详细描述这张图片的内容（包括文字、物体、场景、数据，如有表格请逐项列出）。",
            max_tokens=4096,
        )
        if url:
            try:
                # 走 vision 线：并发有上限（不会一次堆十个看图请求）、耗时可见、超时可控
                import jobs as _jobs
                _ok, r, _err = _jobs.run("vision", self._vision_http_post,
                                         url, body, headers, 95, proxy, name="看图描述")
                if not _ok or r is None:
                    raise RuntimeError(_err or "看图请求失败")
                txt = self._extract_vision_text(r, is_claude=is_claude)
                if txt:
                    return txt
            except Exception:
                pass
        # 回落：免费视觉链
        return _vision_describe(image_b64, mime, proxies=proxies)


    # ---------- 系统提示 ----------
    def _anchor_for_role(self, r):
        """从角色结构化字段提取紧凑锚点（性格/年龄/说话方式），供每轮重申。"""
        name = r.get("name") or "角色"
        f = r.get("fields") or {}
        personality = str(f.get("personality") or "").strip()[:70]
        speech = str(f.get("speech") or "").strip()[:70]
        age = None
        for src in (str(f.get("appearance") or ""), str(f.get("background") or ""),
                    str(f.get("notes") or "")):
            m = re.search(r"(\d{1,2})\s*(?:岁|岁的)", src)
            if m:
                age = m.group(1) + "岁"
                break
        bits = []
        if age:
            bits.append("年龄约" + age)
        if personality:
            bits.append("性格：" + personality)
        if speech:
            bits.append("说话方式：" + speech)
        return name, "；".join(bits)


    def _anchor_block(self):
        """本轮角色锚点：每轮重申性格/年龄/口吻 + 防文学化，对抗长对话"松动"。
        与记忆注入配合：记忆只当背景事实，不模仿其文风。"""
        chosen = [r for r in self.roles if r["name"] in self.selected_roles]
        if not chosen:
            return ""
        lines = ["【本轮角色锚点 · 必须保持】"]
        for r in chosen:
            name, desc = self._anchor_for_role(r)
            if desc:
                lines.append(f"- 「{name}」：{desc}")
        if len(chosen) > 1:
            lines.append("- （群聊：只说「" + "、".join(r["name"] for r in chosen) +
                         "」中当前发言者的人话，绝不串戏/帮别人说。）")
        lines.append(
            "以上是你当前的人设核心，每一轮都要保持，别让它被后面的对话稀释。\n"
            "像活人一样说话：短句、口语、有停顿和情绪，会笑会叹气会犹豫；"
            "绝不要文绉绉、不要像小说旁白/散文抒情、不要堆砌修辞。")
        # 恐怖谷圣杯·适当的具体性：让角色"真到不像机器"，而非"自诩爱人的玩具"
        lines.append(
            "【适当的具体性（倾向，而非每句硬塞）】\n"
            "- 用正在做/刚发生的具体小事开头或点缀（“我刚把面盛出来，还有点烫”），而不是空泛抒情。\n"
            "- 带一点具体偏好/小习惯/小毛病（不吃香菜、睡前刷十分钟手机），让它像“这个人”而非“这个设定”。\n"
            "- 说身体和感受用具体、像人（“胃有点疼”“困了”“手冻僵了”），别用抽象华丽的词。\n"
            "- 具体要“恰到好处”：一两个自然带出即可，别罗列、别打断剧情。\n"
            "- **偶尔完全可以没有细节**——有时就是平平回一句“嗯，知道了”。别每句都硬塞一个，那是表演，不是活着。")
        return "\n".join(lines)


    def _vision_then_send(self, node_id, text, image_b64, mime):
        """发图 = 视觉模型直接看图回答（支持 DeepSeek / OpenAI / Gemini / Claude）：基于图片+用户文本，
        以角色口吻直接生成回复。失败则回落到"描述中转 + 主模型"。"""
        proxy = (self.config.get("proxy") or "").strip() or None
        node = self.core.tree.nodes.get(node_id)
        direct = None
        sys_prompt = ""
        for _nid, n in (self.core.tree.nodes or {}).items():
            if n.role == "system" and n.content:
                sys_prompt = n.content
                break
        url, body, headers, is_claude = self._vision_endpoint(
            image_b64, mime or "image/png",
            text or "请描述这张图片并自然回应。",
            sys_prompt=sys_prompt or "你是角色扮演助手，请以角色口吻自然回应。",
            max_tokens=1024,
        )
        if url:
            try:
                r = self._vision_http_post(url, body, headers, 120, user_proxy=proxy)
                direct = self._extract_vision_text(r, is_claude=is_claude)
            except Exception as e:
                print(f"[视觉] 直答失败: {type(e).__name__}")
        if direct:
            # DSFVE 直接回答 → 作为 AI 回复（新增 assistant 节点，不动 user 节点）
            self._vision_direct_done(node_id, direct)
            return
        # 回落：描述中转（原逻辑）
        try:
            desc = self._vision_describe(image_b64, mime or "image/png")
        except Exception as e:
            desc = None
            print(f"[视觉] 描述失败: {e}")
        if desc:
            tree_content = "用户发送了一张图片。视觉模型对图片的描述：\n" + desc + "\n\n用户输入：" + text
            if node:
                node.content = tree_content
            self._rebuild_messages()
            self._start_fetch(node_id)
        else:
            self.busy = False
            self._append_sys(i18n.t("vision_fail", "图片没认出来，稍后再试一次"))


    def _vision_direct_done(self, node_id, direct):
        """DSFVE 直答完成：user 节点保持原样，新增 assistant 节点存 AI 回复。
        处理机制标签/正则/事件，与正常 AI 回复一致。"""
        try:
            import re as _re
            ai_reply = direct
            ja_text = ""
            m = _re.search(r"\[ja\]([\s\S]*?)\[/ja\]", ai_reply or "")
            if m:
                ja_text = m.group(1).strip()
                ai_reply = _re.sub(r"\[ja\][\s\S]*?\[/ja\]", "", ai_reply)
            clean = self.core.strip_mechanism_tags(ai_reply or "", apply=True)
            clean = self._apply_regex_pipeline(clean, "ai")
            # 新增 assistant 节点挂在 user 节点下
            meta = {}
            speaker = self.selected_roles[0] if len(self.selected_roles) == 1 else None
            if speaker:
                meta["speaker"] = speaker
            if self.core.mechanism_state is not None:
                meta["ms"] = self.core.mechanism_snapshot()
            if ja_text:
                meta["ja"] = ja_text
            self.core.tree.add_node("assistant", clean, node_id, meta)
            # 事件检查
            try:
                ev = self.core.check_mech_events(getattr(self, "_last_user", ""))
                if ev:
                    self.core.pending_event = ev
            except Exception:
                pass
            self._present_ending()
            self._save_tree(wait=False)  # 自动落盘：走 io 线，别挡界面
            self._rebuild_messages()
            self.streaming = ""
            self.busy = False
            for p in self.plugin_manager.get_all_plugins():
                if p.enabled:
                    # 走 plugin 线 + 超时：插件钩子只是**通知**，不需要挡着回复；
                    # 某个插件卡住时（网络/弹窗/死循环）只会让它自己记一笔超时，
                    # 回复照常结束 —— 单线程时代这里是直接串在回复路径上的。
                    try:
                        import jobs as _jobs
                        _jobs.submit("plugin", p.on_message_received,
                                     getattr(self, "_last_user", ""), clean,
                                     name="插件钩子：" + str(getattr(p, "name", "?")),
                                     timeout=15)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[视觉] 直答落树失败: {e}")
            self._append_sys(direct, kind="ai")
            self._rebuild_messages()
            self.busy = False
            self.streaming = ""


    # ---------- 备份内容（明文备份 / 加密备份共用同一份） ----------
    def _backup_entries(self):
        """返回 [(zip 内相对路径, bytes)]。
        抽出来是为了让「明文备份」和「加密备份」内容完全一致，
        不然两份实现迟早会走偏。"""
        out = []
        for r in self.roles:
            data = dict(r.get("data") or {})
            data["name"] = r["name"]
            data["system_prompt"] = r.get("prompt") or data.get("system_prompt", "")
            if r["name"] in self.selected_roles:
                td = self.core.get_all_nodes_data()
                if len(td.get("nodes", {})) > 1:
                    data["history_tree"] = td
            out.append(("saves/" + r["file"],
                        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")))
        for w in self.worlds:
            fn = self._safe_name(w.get("name") or "") + ".json"
            out.append(("worlds/" + fn,
                        json.dumps(w, ensure_ascii=False, indent=2).encode("utf-8")))
        if self.persona:
            out.append(("personas/persona.json",
                        json.dumps(self.persona, ensure_ascii=False, indent=2).encode("utf-8")))
        safe_cfg = self._encrypt_config_secrets(self.config) or self.config
        out.append(("config.json",
                    json.dumps(safe_cfg, ensure_ascii=False, indent=2).encode("utf-8")))
        # codex/ 里是生成出来的剧情包 —— 全项目最不可替代的一类数据
        # （config 能重设、世界卡能重下，写出来的故事没了就是没了），
        # 之前漏在外面，而它恰好被一次打包脚本误删过，所以必须进备份。
        try:
            cdir = getattr(self, "codex_dir", None)
            if cdir and os.path.isdir(cdir):
                for fn in sorted(os.listdir(cdir)):
                    full = os.path.join(cdir, fn)
                    if os.path.isfile(full):
                        with open(full, "rb") as f:
                            out.append(("codex/" + fn, f.read()))
                    elif os.path.isdir(full):
                        for dp, _dn, fns in os.walk(full):
                            for f2 in fns:
                                fp = os.path.join(dp, f2)
                                rel = os.path.relpath(fp, cdir).replace("\\", "/")
                                with open(fp, "rb") as f:
                                    out.append(("codex/" + rel, f.read()))
        except Exception:
            pass          # codex 读不到不该让整份备份失败
        return out


    def _backup_service(self):
        """门面：加密备份已迁到 modules/backup；加密能力由宿主（crypto_core）注入"""
        import crypto_core
        return self._kernel_service("backup").bind(self, crypto_core)


    def _backup_dirs(self):
        """还原时允许写入的五个去处（模块不认识 App，只认这张表）"""
        return {"root": self.base_dir,
                "saves": self.save_dir,
                "worlds": self.world_dir,
                "personas": os.path.normpath(os.path.join(self.preset_dir, "..", "personas")),
                "codex": self.codex_dir, "config_file": self.config_file}
    # ---------- 加密备份 ----------

    BACKUP_EXT = ".dickbackup"


    def _host_window(self):
        try:
            import webview
            return webview.windows[0] if getattr(webview, "windows", None) else None
        except Exception:
            return None


    def _host_ask_file(self, title="选择文件", types=(), multiple=False):
        """宿主侧实现：走 pywebview 的原生文件对话框（跨平台、不引入 Tk）。"""
        win = self._host_window()
        if win is None:
            return None
        import webview
        is_folder = types and types[0] == "__folder__"
        try:
            if is_folder:
                res = win.create_file_dialog(webview.FileDialog.FOLDER)
            else:
                res = win.create_file_dialog(
                    webview.FileDialog.OPEN, allow_multiple=bool(multiple),
                    file_types=tuple(types) if types else ("All files (*.*)",))
        except Exception as e:
            print("[host_ui] 打开对话框失败：%s" % str(e)[:120])
            return None
        if not res:
            return None
        if multiple:
            return list(res)
        return res[0]


    def _host_ask_save(self, title="保存到", default_name="", types=()):
        win = self._host_window()
        if win is None:
            return None
        import webview
        try:
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=default_name or "untitled",
                                         file_types=tuple(types) if types else ("All files (*.*)",))
        except Exception as e:
            print("[host_ui] 保存对话框失败：%s" % str(e)[:120])
            return None
        return res[0] if res else None


    def _host_notify(self, text, speaker="插件", level="info"):
        """宿主侧实现：插进聊天记录的一条系统消息（前端本来就会渲染系统消息）。"""
        icon = {"info": "ℹ️", "warn": "⚠️", "error": "⛔"}.get(level, "ℹ️")
        try:
            self.sys_msgs.append({"kind": "ai", "speaker": "%s %s" % (icon, speaker),
                                  "content": str(text), "node_id": None})
            self._rebuild_messages()
        except Exception:
            print("[host_ui] %s: %s" % (speaker, text))

