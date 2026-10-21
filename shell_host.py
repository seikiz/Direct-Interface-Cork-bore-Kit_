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

    def _vision_describe(self, image_b64, mime):
        """看图描述：DICK 的眼睛 = 官方视觉理解（V4.1 Flash 起原生多模态，模型名仍填 deepseek-flash）。
        只要配了 DeepSeek key 就固定用它看图（与主对话模型无关），失败才回落免费链。"""
        import requests
        proxy = self.config.get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        ds_key = (self.config.get("api_key") or "").strip()
        ds_base = (self.config.get("base_url") or "https://api.deepseek.com").strip()
        # 视觉模型 ID：2026-09-10 起 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌V4.1 Flash 原生支持视觉理解，
        # 旧的 deepseek-v4-flash-vision-exp 已下线（官方暂时路由），统一填 deepseek-flash。
        vision_model = "deepseek-flash"
        if ds_key and ds_base:
            data_url = "data:" + mime + ";base64," + image_b64
            body = {
                "model": vision_model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": "请用中文详细描述这张图片的内容（包括文字、物体、场景、数据，如有表格请逐项列出）。"},
                ]}],
                "max_tokens": 4096,
                "stream": False,
            }
            try:
                # 走 vision 线：并发有上限（不会一次堆十个看图请求）、耗时可见、超时可控
                import jobs as _jobs
                _ok, r, _err = _jobs.run("vision", requests.post,
                                         ds_base.rstrip("/") + "/chat/completions",
                                         timeout=95, name="看图描述",
                                         json=body,
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": "Bearer " + ds_key},
                                         proxies=proxies)
                if not _ok or r is None:
                    raise RuntimeError(_err or "看图请求失败")
                if r.status_code < 400:
                    content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
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
        """发图 = 视觉模型直接看图回答（deepseek-flash 的多模态能力）：基于图片+用户文本，
        以角色口吻直接生成回复。失败则回落到"描述中转 + 主模型"。"""
        import requests
        proxy = self.config.get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        node = self.core.tree.nodes.get(node_id)
        ds_key = (self.config.get("api_key") or "").strip()
        ds_base = (self.config.get("base_url") or "https://api.deepseek.com").strip()
        vision_model = "deepseek-flash"
        data_url = "data:" + (mime or "image/png") + ";base64," + image_b64
        direct = None
        if ds_key and ds_base:
            # 用当前系统提示（角色人设）让 DSFVE 以角色身份看图回答
            try:
                sys_prompt = ""
                for nid, n in (self.core.tree.nodes or {}).items():
                    if n.role == "system" and n.content:
                        sys_prompt = n.content
                        break
                body = {
                    "model": vision_model,
                    "messages": [{"role": "system", "content": sys_prompt or "你是角色扮演助手，请以角色口吻自然回应。"},
                                 {"role": "user", "content": [
                                     {"type": "image_url", "image_url": {"url": data_url}},
                                     {"type": "text", "text": text or "请描述这张图片并自然回应。"},
                                 ]}],
                    "max_tokens": 1024,
                    "stream": False,
                }
                r = requests.post(ds_base.rstrip("/") + "/chat/completions",
                                  json=body,
                                  headers={"Content-Type": "application/json",
                                           "Authorization": "Bearer " + ds_key},
                                  timeout=120, proxies=proxies)
                if r.status_code < 400:
                    content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content")
                    if isinstance(content, str) and content.strip():
                        direct = content.strip()
            except Exception as e:
                print(f"[视觉] DSFVE 直答失败: {e}")
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

