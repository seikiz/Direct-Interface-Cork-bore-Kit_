# -*- coding: utf-8 -*-
# <seikiz>  DICK sour<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ce mark (invisible)
# ============================================================
#   html_app.py - HTML 前端（pywebview 壳）
#   后端复用 ChatCore + 插件体系；前端 web/index.html（纯 HTML/CSS/JS）
#   桥接：JS 轮询 api.poll() 拉增量消息 / 流式文本，调用 api.* 触发动作
#
#   架构标识：Direct-Interface Cork-bore Kit (DICK) — CODEX engine
#   本文件及本项目的核心架构（树状记忆 / 机制卡 / 战斗 / CODEX 打包）
#   均受 dick_mark.py 溯源水印保护；抄袭者无法剥离架构签名。
# ============================================================

import base64
import json
import os
import sys
import time
import notices
import threading
import re
import random
import uuid
import text_shield

# PyInstaller windowed 模式（无控制台）下 stdout/stderr 为 None，print 会崩溃。
# 启动即重定向到 exe 旁的 debug.log。
if sys.stdout is None or sys.stderr is None:
    _exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    _log_path = os.path.join(os.path.dirname(_exe), "debug.log")
    try:
        _log = open(_log_path, "w", encoding="utf-8", errors="replace")
        if sys.stdout is None:
            sys.stdout = _log
        if sys.stderr is None:
            sys.stderr = _log
    except Exception:
        pass

import app_paths
from shell_util import (BASE_DIR, DEFAULT_WS_SERVER, XFER_MIN_INTERVAL_MS, XFER_MAX_RETRY,
                        tree_ts_of, BUILTIN_RELAY, PROVIDERS, assemble_role_prompt, ROLE_FIELDS, WORLD_PARAMS, _parse_fields, _render_world_desc, role_prompt_from_card, html_app_clean_battle, html_app_clean_mechanics)
import app_version
import i18n
import card_compat
import save_guard
import secret_store
import codex_core
from DICK_core import ChatCore
from plugin_manager import PluginManager


# 内置代理通道（中转）：固定地址 → Worker → 隧道 → 本地 net.py → 真实厂商
# 中转已停用：香港工坊的 /relay 出于安全关闭，且中转实现是整体缓冲、不支持流式












# ---------- 模型商目录（14 家 / 100+ 模型：选厂商→选模型→跳官网） ----------
_MODEL_STOP_DEFAULTS = {
    "ollama": ["<|im_end|>", "</s>"],
    "qwen": ["<|im_end|>"],
}
for _p in PROVIDERS:
    _p.setdefault("stop", _MODEL_STOP_DEFAULTS.get(_p["id"], []))


def _web_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def _seed_defaults(base_dir):
    """exe 首次运行：把打包内置的默认数据（角色/世界/预设/示例）释放到 exe 旁，仅补缺失不覆盖"""
    bundled = getattr(sys, "_MEIPASS", None)
    if not bundled:
        return
    import shutil
    for name in ("prompt_presets", "personas", "worlds", "saves", "world_packs"):
        src = os.path.join(bundled, name)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(base_dir, name)
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(src):
            s = os.path.join(src, fn)
            d = os.path.join(dst, fn)
            if os.path.isfile(s) and not os.path.exists(d):
                try:
                    shutil.copy2(s, d)
                except OSError:
                    pass
    # 世界卡库（world_packs/）只释放卡包本身，**不**自动装进 worlds/ ——
    # 装哪几张是用户的选择（/世界包 装 <名字>）；否则世界列表会被塞满。
    cfg_src = os.path.join(bundled, "config.json")
    cfg_dst = os.path.join(base_dir, "config.json")
    if os.path.isfile(cfg_src) and not os.path.exists(cfg_dst):
        try:
            shutil.copy2(cfg_src, cfg_dst)
        except OSError:
            pass


# ============================================================
#  创意工坊：传输节奏与"去历史"
# ============================================================
#  两件与具体视图无关、两端（桌面/安卓）必须一致的规矩，放在模块级：
#
#  ① 传输节奏：链路按"每设备每 500ms 一次"设计（40 Mbit ≈ 5MB/s）。
#     并发两条大上传会互相抢带宽、双倍超时，服务器也会按 rate_per_min 回 429。
#     所以工坊的**传输**（上传/下载）走同一个闸门：串行 + 最小间隔。
#     间隔优先用服务器下发的 limits.min_interval_ms（以后换 100MB/s 只改服务器
#     环境变量、客户端不用重新发版），读不到才回落到这个常量。
#  ② 去历史：上传前剔掉本地历史/状态（聊天树/进度/记忆），只发卡面内容。
#     语义是"每次上传都是新卡"——不按 id 覆盖、不按 sha256 去重。
#     实测 咲.json 16KB → 2KB（gzip 前）。服务器侧还会再兜底剔一遍。
# ============================================================

# 与 net.py 的 LOCAL_STATE_KEYS 同一份名单：存在才删，卡面字段一个都不碰。
# 世界书的 entries、params、rules 都**不在**这个名单里（那些是卡内容）；
# 也刻意不递归进 params/rules 里面 —— 那里的同名键是作者自己写的数据。
LOCAL_STATE_KEYS = (
    "history_tree", "_tree_ts", "tree_ts", "messages", "chat_history", "_history",
    "memory", "memories", "preferences", "_indices", "_trpg_lock",
    "last_leaf_id", "current_leaf_id", "session", "state",
)


def strip_local_state(card):
    """剥掉本地历史/状态，只留卡面内容。返回 (新 dict, 剔掉的键名列表)。

    不修改入参（复制一份再删）：调用方手里那份可能还要落盘回本地。
    """
    if not isinstance(card, dict):
        return card, []
    out = dict(card)
    gone = [k for k in LOCAL_STATE_KEYS if k in out]
    for k in gone:
        out.pop(k, None)
    return out, gone


def strip_local_state_bytes(raw):
    """bytes 版：解析 → 剥 → 重新序列化。解析不了就原样返回（让服务器去判 400）。

    返回 (新 bytes, 剔掉的键名列表)。没有可剔的键时**返回原字节**，
    避免"没改也要重新序列化"——那会把用户的排版/缩进悄悄改掉。
    """
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return raw, []
    if not isinstance(obj, dict):
        return raw, []
    clean, gone = strip_local_state(obj)
    if not gone:
        return raw, []
    return json.dumps(clean, ensure_ascii=False, indent=2).encode("utf-8"), gone


def ws_header_name(name):
    """文件名放进 HTTP 头之前转成 ASCII。

    **这条不是可选优化，是必须的**：requests 按 latin-1 编请求头，卡名是中文时
    （工坊里的卡几乎全是中文名）会直接抛
        UnicodeEncodeError: 'latin-1' codec can't encode characters ...
    整次上传当场失败。所以含非 ASCII 就做百分号编码，服务端（net.py 的
    _url_unquote）会解回原名；纯 ASCII 原样发，日志里好读。安卓端
    （Workshop.kt 的 asciiHeaderName）用的是同一套约定。
    """
    s = str(name or "")
    if s.isascii():
        return s
    from urllib.parse import quote
    return quote(s, safe="")

from shell_ws import WsMixin, WsXferSlot
from shell_api_misc import ApiMiscMixin
from shell_api_go import ApiGoMixin
from shell_api_settings import ApiSettingsMixin
from shell_api_ws import ApiWsMixin
from shell_api_codex import ApiCodexMixin
from shell_host import HostMixin
from shell_go import GoMixin
from shell_codex import CodexMixin

from shell_cards import CardsMixin
from shell_flow import FlowMixin
from shell_state import StateMixin
class HtmlApp(StateMixin, FlowMixin, CardsMixin, ApiMiscMixin, ApiGoMixin, ApiSettingsMixin, ApiWsMixin, ApiCodexMixin, HostMixin, GoMixin, CodexMixin, WsMixin):
    # 已并入核心（底层）的 UI 插件：不再作为可开关插件出现，也不可被禁用
    # （Tk 时代的「现代界面」已随 Tk 一起退役 —— HTML 版的主题由前端自己管）
    CORE_UI_PLUGINS = ("Live2D 看板娘",)

    def __init__(self):
        # 运行时可重定向：优先 app_paths.get_base_dir()（测试/自定义数据目录可直接
        # monkeypatch），退回模块级 BASE_DIR。避免历史测试改 BASE_DIR 不生效的问题。
        self.base_dir = getattr(app_paths, "get_base_dir", lambda: BASE_DIR)()
        _seed_defaults(self.base_dir)
        self.save_dir = os.path.join(self.base_dir, "saves")
        self.world_dir = os.path.join(self.base_dir, "worlds")
        # 世界卡包库（world_packs/）：成套世界设定，可上传/下载，不自动进 worlds/
        self.pack_dir = os.path.join(self.base_dir, "world_packs")
        self.preset_dir = os.path.join(self.base_dir, "prompt_presets")
        self.codex_dir = os.path.join(self.base_dir, "codex")
        self.config_file = os.path.join(self.base_dir, "config.json")
        for d in (self.save_dir, self.world_dir, self.pack_dir, self.preset_dir, self.codex_dir):
            os.makedirs(d, exist_ok=True)

        self.config = {}
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        except Exception:
            pass
        self._decrypt_config_secrets(self.config)
        # 架构级水印：config.json 注入来源指纹（一次性，不覆盖已有）
        try:
            import dick_mark
            if not self.config.get("dick_mark"):
                self.config["dick_mark"] = dick_mark.mark_dict({"finger": dick_mark.finger("config")})
                save_guard.atomic_write_json(self.config_file, self._encrypt_config_secrets(self.config))
        except Exception:
            pass

        # 界面语言：配置里有就用配置的；没有就按系统判定
        # （中文 → zh、日文 → ja、英文 → en、认不出 → zh，见 i18n.detect_system_lang）
        lang = self.config.get("language") or i18n.detect_system_lang()
        i18n.set_lang(lang)
        self.language = i18n.lang()

        self.core = ChatCore()
        self.core.humanize = bool(self.config.get("humanize", True))
        self.core.style_guard = bool(self.config.get("style_guard", True))
        self.core.style_guard_long = bool(self.config.get("style_guard_long", False))
        self._last_user = ""          # 最近一次玩家输入（机制事件判定用）
        self.provider_id = self.config.get("provider") or "deepseek"
        self.api_keys = dict(self.config.get("api_keys") or {})
        key = self.api_keys.get(self.provider_id) or self.config.get("api_key")
        if key:
            self.core.set_api_key(key)
            if self.config.get("base_url"):
                self.core.set_base_url(self.config["base_url"])
        # LLM 通道代理（保证被墙厂商可用）
        if self.config.get("proxy"):
            self.core.set_proxy(self.config["proxy"])
        # 内置代理通道：直连失败自动走中转（默认内置地址，可改）
        self.core.set_relay(self.config.get("relay_url") or BUILTIN_RELAY)
        # 指令模板：停止序列（设置覆盖 > 预设 > 模型家族默认）
        self.core.set_stop_sequences(self._effective_stop())
        # 采样参数（温度/top_p，None=模型默认）
        self.core.set_sampling(self.config.get("temperature"), self.config.get("top_p"))
        if self.config.get("model"):
            self.core.set_model(self.config["model"])
        self.core.set_context_budget(int(self.config.get("context_budget", 0) or 0))
        self.core.set_rolling_summary_enabled(bool(self.config.get("rolling_summary", True)))

        self.plugin_manager = PluginManager(self.core, config_file=self.config_file)
        # 插件要界面（选文件/提示）走宿主这条通道；必须在 load_plugins 之前接上，
        # 否则插件 on_load 里想弹提示就只能退回自己拉 GUI 库（Tk 时代就是这么背上的）。
        self._install_host_ui()
        self.plugin_manager.load_plugins()
        for p in self.plugin_manager.get_all_plugins():
            states = self.config.get("plugin_states", {})
            if p.name in states:
                p.enabled = bool(states[p.name])

        # 前端状态
        self.messages = []          # [{"seq":int,"kind":"user|ai|sys","speaker":str,"content":str,"image":str|None,"node_id":str|None}]
        self.sys_msgs = []          # 系统横幅（欢迎语等，树重建时保留）
        self.node_images = {}       # node_id -> dataURL（图片消息，仅内存，不落盘）
        self.node_seq_cache = {}    # (kind, key) -> seq，重建时保持消息 seq 稳定
        self.seq = 0
        self.render_epoch = 0       # 树重建时 +1，前端据此整刷消息列表
        self.streaming = ""
        self.busy = False
        # 「正在加载开场白」。为什么单独一个状态：加载气泡的条件是
        # 「busy 且有流式文本」，而开局时文本还是空的 —— 界面会一片空白。
        # 普通发消息时用户自己那句话说出来了、知道在等；开局本来就是空的，
        # 空白就等于「坏了」。所以开局必须单独给一个加载态。
        self.opening_loading = False
        self.total_tokens = 0
        self.preset_name = ""
        self.persona = None         # {"name","background","notes",...}
        self.auto_turn = bool(self.config.get("auto_turn", False))
        self.font_size = int(self.config.get("ui_font", 0) or 0)
        self.loaded_document = None  # {"name","chars"}
        self._lock = threading.Lock()
        # 模块分道执行：每个模块一条自己的运行线（见 jobs.py）。
        # 现在的慢活儿之所以互相拖，是因为全挤在"一个 busy + 一堆裸线程"上；
        # 这里先把线建起来，随后按模块把活儿搬进去（网络/视觉/语音/生图/记忆/插件/落盘）。
        try:
            import jobs
            jobs.start()
            self._jobs_seq = 0
        except Exception as e:
            print("[jobs] 分道初始化失败（不影响主流程）：%s" % str(e)[:120])
            self._jobs_seq = 0
        # 微内核：只做"装模块、给服务、发事件"。业务在 modules/ 下，壳层只做接线。
        # 内核起不来也不能拖死主程序 —— 那只意味着工坊/备份降级，其余功能照常。
        self.kernel = None
        try:
            import kernel
            self.kernel = kernel.boot(base_dir=self.base_dir)
            try:
                # 异步事件复用现成的运行线（jobs 的分道），不另造一套线程池
                self.kernel.bind_jobs(jobs, lane="plugin")
            except Exception as e:
                print("[kernel] 异步事件没接上运行线（退化为一次性线程）：%s" % str(e)[:120])
            print("[kernel] 已装模块：%s" % ("、".join(self.kernel.loaded_ids()) or "（无）"))
        except Exception as e:
            print("[kernel] 内核启动失败（工坊/备份将不可用）：%s" % str(e)[:160])
        self.ollama_online = False   # 本地 Ollama 是否可用（后台探测）
        self.codex_auto_open = None  # 双击 .codex 文件启动时，待自动打开的包名
        self.codex_volume = 100      # CODEX 播放器音量 0-100
        threading.Thread(target=self._detect_ollama, daemon=True).start()

        self._load_presets()
        self._load_roles()
        self._load_worlds()
        self.current_world = self.config.get("current_world") or ""
        self.core.world_max_entries = int(self.config.get("world_max_entries") or 3)
        # 版号只有 version.json 一个来源：措辞归 i18n.welcome()，号由 app_version 给
        self._append_sys(i18n.welcome(app_version.full()))
        self._append_sys(i18n.t("welcome2", "多角色模式：输入 @角色名 内容 来指定说话者。"))
        # 启动即恢复上次会话：激活上次选中的角色（机制卡/恋爱条/战斗随启动初始化，
        # 与 Android 端一致——否则恋爱条要手动保存一遍角色才出现）
        if self.selected_roles:
            try:
                self._activate_core(reload_tree=True)
            except Exception as e:
                print(f"[HtmlApp] 启动恢复选中角色失败: {e}")
        self._rebuild_messages()
        # 进度同步：后台拉取共享的模型连接配置（不阻塞启动；服务器在线才生效）
        threading.Thread(target=self._ws_pull_api, daemon=True).start()
        # 存档守护：后台扫描一次，坏档自动修复/从备份恢复
        save_guard.sweep_async(self.base_dir)

    # ---------- 数据 ----------









    # ---------- Galgame 选项（插件联动） ----------
    def _effective_stop(self):
        """生效的停止序列：设置覆盖 > 预设 stop_sequences > 当前模型家族默认"""
        ov = self.config.get("stop_sequences") or []
        if ov:
            return [str(x).strip() for x in ov if str(x).strip()]
        preset = getattr(self.core, "prompt_preset", None) or {}
        ps = preset.get("stop_sequences") or []
        if ps:
            return [str(x).strip() for x in ps if str(x).strip()]
        prov = next((p for p in PROVIDERS if p["id"] == self.provider_id), None)
        return list((prov or {}).get("stop", []) or [])

    def _clear_choices(self):
        p = self._choices_plugin()
        if p:
            try:
                p.clear_choices()
            except Exception:
                pass

    def _jobs_delta(self):
        """取分道结果流的增量（供 poll 带走）。没有 jobs 模块时安静返回空。"""
        try:
            import jobs
            evs = jobs.drain(getattr(self, "_jobs_seq", 0))
            if evs:
                self._jobs_seq = evs[-1]["seq"]
            return evs
        except Exception:
            return []


    def _switch_world(self, name):
        """切换到指定世界线（若存在）；同步 UI 状态并加横幅。返回是否成功。"""
        name = str(name or "").strip()
        if not name:
            return False
        if self.core.set_current_world(name):
            self.current_world = name
            self.config["current_world"] = name
            self._save_config()
            self._append_sys("🌐 已穿越到世界线「" + name + "」")
            return True
        return False

    def _maybe_world_line_on(self, kind):
        """机制/ROLL 事件 → 世界线切换（config.world_lines 映射，键：_roll_collapse/_roll_chosen/_roll_rare/crit/fail）。"""
        try:
            wl = self.config.get("world_lines") or {}
            name = wl.get(str(kind))
            if name:
                self._switch_world(name)
        except Exception:
            pass











    # ---------- 管理动作 ----------




    @staticmethod
    def _safe_name(name):
        for ch in [chr(92), "/", ":", "*", "?", '"', "<", ">", "|"]:
            name = name.replace(ch, "_")
        return (name or "").strip()[:60]



    def _trpg_locked_names(self):
        """当前被跑团锁定的角色名集合。
        锁文件由 /trpg 插件与 trpg_server（局域网多人）共同写入 .trpg_lock.json，
        字段 {"locked": [gm]+pcs}，读不到视为无锁定。"""
        try:
            p = os.path.join(self.save_dir, ".trpg_lock.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return set(d.get("locked") or [])
        except Exception:
            pass
        return set()

    def _is_card_locked(self, name):
        """会期锁定：跑团会话进行中（.trpg_lock.json 存在且含该卡）→ 拒绝改卡。"""
        return name in self._trpg_locked_names()

    def _parse_world_params(self, params_json):
        params = {}
        raw = _parse_fields(params_json)
        for key, _label in WORLD_PARAMS:
            v = str(raw.get(key) or "").strip()
            if v:
                params[key] = v
        return params


    @staticmethod
    def _save_summary(entry):
        """存档的轻量摘要（不携带整棵树，避免前端负载过大）"""
        if not isinstance(entry, dict):
            return None
        return {"id": entry.get("id"), "label": entry.get("label") or "未命名存档",
                "created_ts": entry.get("created_ts"), "updated_ts": entry.get("updated_ts"),
                "_tree_ts": entry.get("_tree_ts"),
                "progress": int(entry.get("progress", 0) or 0)}

    def _role_by_name(self, name):
        return next((r for r in self.roles if r["name"] == name), None)

    def _commit_card_data(self, r, data):
        """把改动后的角色卡 data 写回文件 + 同步内存快照（保留 name/system_prompt/kind）"""
        data = dict(data)
        data["name"] = r["name"]
        data["system_prompt"] = r["prompt"]
        data["kind"] = "dick_card"
        try:
            save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
            save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), data)
        except Exception:
            pass
        r["data"] = data
        return data

    @staticmethod
    def _entry_hit(entry, text_lower):
        """仅用于前端状态点亮：判断条目是否命中最近一条用户消息"""
        if not entry.get("enabled", True):
            return False
        if entry.get("constant"):
            return True
        kws = entry.get("keywords") or []
        if not kws:
            return False
        mode = (entry.get("match") or "any").lower()
        if mode == "all":
            return all(str(k).lower() in text_lower for k in kws)
        return any(str(k).lower() in text_lower for k in kws)

    def _wallpaper_path(self):
        for ext in self._WALLPAPER_EXTS:
            p = os.path.join(self.save_dir, "wallpaper" + ext)
            if os.path.isfile(p):
                return p
        return os.path.join(self.save_dir, "wallpaper.png")




    def _drift_keys(self):
        """取当前角色的「本场关键词」（这场戏在讲什么）。

        为什么要作者填：实测下来，泛泛的词面重叠分不出「跑题」和「措辞巧合」，
        只有明确的目标词才是可靠信号。自动抽词在没有分词的情况下抽不准，
        所以这里让作者给 —— 不填就等于不做漂移判定（不会乱定罪）。
        """
        name = (self.selected_roles or [None])[0]
        allk = self.config.get("drift_keys") or {}
        return list(allk.get(name or "", []) or [])

    def _case_text(self):
        """案卷：世界卡 + 选中角色卡 —— 漂移/编造核查要比对的"现实"。"""
        parts = []
        for r in (self.roles or []):
            if r.get("name") in (self.selected_roles or []):
                parts.append(str(r.get("prompt") or ""))
        for w in (self.worlds or []):
            if w.get("name") in (self.selected_worlds or []):
                parts.append(str(w.get("description") or ""))
        return "\n".join(parts)

    def _rubric(self):
        """取当前角色声明的价值标准（rubric）。这是「价值声明」，第 2 步。"""
        name = (self.selected_roles or [None])[0]
        allr = self.config.get("rubrics") or {}
        try:
            import rubric as _rb
            return _rb.normalize(allr.get(name or "", []))
        except Exception:
            return list(allr.get(name or "", []) or [])



    def _sync_speculator(self):
        """按配置挂/摘投机器。挂在 core 上，因为载荷是在 core 里组装的。"""
        cfg = self.config.get("lookahead") or {}
        self.core.speculator = self._speculate if cfg.get("on") else None
        return bool(cfg.get("on"))

    def _ranker_path(self):
        return os.path.join(self.base_dir, "ranker.json")




# ---------- 创意工坊（联网版，端口自 Tk 版） ----------
    # ---- 工坊模块的宿主端口（modules/workshop 只经这些成员跟壳层说话）----
    def _kernel(self):
        """内核实例（懒启动）：启动时已经 boot 过，这里只兜底 ——
        保证"内核没起来"只影响工坊/备份两块，不牵连别的功能。"""
        k = getattr(self, "kernel", None)
        if k is None:
            import kernel as _kernel
            k = _kernel.boot(base_dir=self.base_dir)
            self.kernel = k
        return k

    def _kernel_service(self, name):
        return self._kernel().service(name)

    def _workshop_client(self):
        """门面：工坊客户端已迁到 modules/workshop，这里只按内核找服务并绑宿主。

        bind 是幂等的（每次取都重绑 self）：一个进程里会建多个 HtmlApp（测试尤其明显），
        服务实例必须跟着当前宿主走，不能绑死在"第一个 App"上。
        """
        return self._kernel_service("workshop").bind(self, max_retry=XFER_MAX_RETRY)

    def ws_strip_local_state(self, raw):
        """给工坊模块用：上传前剔掉本地历史/状态（实现在本文件，唯此一份）"""
        return strip_local_state_bytes(raw)

    def ws_header_name(self, name):
        """给工坊模块用：中文文件名 → ASCII 头（理由见 ws_header_name 的说明）"""
        return ws_header_name(name)

        self.roles = []
        try:
            for fn in sorted(os.listdir(self.save_dir)):
                if fn.startswith("."):
                    continue  # 跳过跑团会期锁等隐藏/元数据文件
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.save_dir, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("system_prompt"):
                        prompt, fields, legacy = role_prompt_from_card(
                            data.get("name") or fn[:-5], data)
                        self.roles.append({"name": data.get("name") or fn[:-5], "file": fn,
                                           "prompt": prompt, "data": data,
                                           "fields": fields, "legacy": legacy})
                except Exception:
                    continue
        except Exception:
            pass
        self.selected_roles = [n for n in self.selected_roles if any(r["name"] == n for r in self.roles)]




# ---------- 前版功能补齐：预算 / 自动接话 / 字体 / 插件管理 / 文档 / 导出 ----------
    @staticmethod
    def _zip_entries(entries, root):
        import zipfile
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for path, data in entries:
                z.writestr(root + "/" + path, data)
        return buf.getvalue()

    def _pick_save_path(self, fname, types):
        """保存对话框（失败/无 UI 时退回桌面）"""
        out = None
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is not None:
                res = win.create_file_dialog(webview.FileDialog.SAVE,
                                             save_filename=fname, file_types=types)
                if res:
                    out = res[0]
        except Exception:
            pass
        if not out:
            out = os.path.join(os.path.expanduser("~"), "Desktop", fname)
        return out

    def _restore_from_zip(self, z, bak):
        """门面：铺盘实现已迁到 modules/backup（含 zip 路径穿越防护与覆盖前留原件）。

        这个方法名保留，是因为测试直接调它 ——「铺盘结果」是这条路上唯一重要的契约。
        """
        return self._backup_service().restore_zip(z, bak, self._backup_dirs())


    def _image_gen_cfg(self):
        """生图配置集中一处（Key/端点/后端/模型），免得各处默认值漂移。"""
        try:
            cfg = self.config or {}
        except Exception:
            cfg = {}
        return {
            "key": (cfg.get("image_gen_key") or "").strip(),
            "base_url": (cfg.get("image_gen_base_url")
                         or "https://api.siliconflow.cn/v1").strip(),
            "model": (cfg.get("image_gen_model")
                      or "black-forest-labs/FLUX.1-schnell").strip(),
            "backend": (cfg.get("image_gen_backend") or "auto").strip() or "auto",
        }

    def _install_host_ui(self):
        """把宿主的对话框与提示接给插件（见 host_ui.py 的说明）。"""
        try:
            import host_ui
            host_ui.set_ui(ask_file=self._host_ask_file, ask_save=self._host_ask_save,
                           notify=self._host_notify)
            return True
        except Exception as e:
            print("[host_ui] 接入失败：%s" % str(e)[:120])
            return False

    def _offline_key(self):
        """离线推进按"这一局是谁"记账（按角色名，群聊就按集合）"""
        try:
            names = sorted([n for n in (self.selected_roles or []) if n])
        except Exception:
            names = []
        return "、".join(names) or "default"


    def _persist_offline_undo(self, undo):
        """把 undo 记录暂存起来，供 api_offline_undo 撤销（一次会话内有效）"""
        try:
            self._offline_undo = undo
        except Exception:
            pass



    def _auto_turn_done(self, reply, usage, rounds):
        if usage:
            self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        self._save_tree()
        self._rebuild_messages()
        self._present_ending()  # autoTurn 回复落地后也判/呈现结局
        self.busy = False
        self._maybe_auto_turn(rounds - 1)

    def _auto_turn_fail(self):
        self.busy = False
        self.streaming = ""

    @staticmethod
    def _probe_reason(code, text):
        """把厂商的 HTTP 状态码翻成人话（401/402/404/429 是最常见的四类）。"""
        t = (text or "")[:300].replace("\n", " ")
        if code == 401:
            return "401 无效 Key（厂商拒绝了这枚 Key）"
        if code == 402:
            return "402 余额不足（要先充值）"
        if code == 403:
            return "403 无权访问（Key 没开通这个模型）"
        if code == 404:
            return "404 端点或模型名不对"
        if code == 429:
            return "429 限流（请求太快或额度用完）"
        if code >= 500:
            return "%d 厂商服务端异常" % code
        return "%d %s" % (code, t)

    @staticmethod
    def _probe_hint(code):
        """每种失败给一句「下一步怎么做」——向导只报错不指路等于没做。"""
        if code == 401:
            return "回上一步整条重贴 Key（别带空格，别把 Base URL 粘进来）"
        if code == 402:
            return "去服务商官网充一点，或点「稍后再说」先用免费链"
        if code == 403:
            return "换一个该账号有权限的模型名，或去控制台开通"
        if code == 404:
            return "照教程里的「模型名示例」原样填；Base URL 别漏 /v1"
        if code == 429:
            return "等几十秒再试；免费链最常见，配置一枚 Key 就稳了"
        return "检查网络/代理；不确定就先点「稍后再说」用免费链"

    @staticmethod
    def _encrypt_config_secrets(cfg):
        """对 config 里的敏感字段做加密替换（就地深拷贝，不污染内存中的明文）。
        返回：加密后的副本 dict（密钥字段变为密文串）。"""
        out = dict(cfg)
        # 顶层 api_key / image_gen_key
        for f in ("api_key", "image_gen_key"):
            if out.get(f):
                out[f] = secret_store.encrypt(str(out[f]))
        # 每提供商的 api_keys 字典
        ak = out.get("api_keys")
        if isinstance(ak, dict):
            out["api_keys"] = {k: (secret_store.encrypt(str(v)) if v else v)
                               for k, v in ak.items()}
        # 图床（image_gen）与视觉（vision）通道可能单独存
        for f in ("image_gen_key",):
            if out.get(f):
                out[f] = secret_store.encrypt(str(out[f]))
        return out

    @staticmethod
    def _decrypt_config_secrets(cfg):
        """就地解密 config 的敏感字段（把密文还原为明文，供内存使用）。
        解不开（换机/换账号）的置空，避免拿密文去当 API Key 请求。"""
        if not isinstance(cfg, dict):
            return
        for f in ("api_key", "image_gen_key"):
            if cfg.get(f):
                d = secret_store.decrypt(str(cfg[f]))
                cfg[f] = d if d is not None else ""
        ak = cfg.get("api_keys")
        if isinstance(ak, dict):
            for k, v in list(ak.items()):
                if v:
                    d = secret_store.decrypt(str(v))
                    ak[k] = d if d is not None else ""
        # workshop_config.json 的 api_key 由各自读写处单独处理（见 _ws_*）

    def _save_config(self):
        try:
            # 敏感字段加密后落盘（内存 self.config 仍是明文，仅写盘时加密）
            written = self._encrypt_config_secrets(self.config)
            save_guard.atomic_write_json(self.config_file, written)
        except Exception:
            pass


# ---------- 免费视觉链（传图补丁） ----------
_VISION_MODELS = ["Qwen3.5-397B-A17B", "Qwen2.5-VL-72B-Instruct", "Qwen3.6-27B",
                  "Mistral-Small-3.2-24B-Instruct-2506", "Qwen3.5-9B"]


def _vision_describe(image_b64, mime, proxies=None):
    import requests
    data_url = "data:" + mime + ";base64," + image_b64
    for model in _VISION_MODELS:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "请用中文详细描述这张图片的内容（包括文字、物体、场景、数据，如有表格请逐项列出）。"},
            ]}],
            "max_tokens": 4096,
            "stream": False,
        }
        try:
            r = requests.post("https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
                              json=body, headers={"Content-Type": "application/json"},
                              timeout=90, proxies=proxies)
            if r.status_code == 429:
                continue
            if r.status_code >= 400:
                continue
            content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
        except Exception:
            continue
    return None


def main():
    import webview
    app = HtmlApp()
    # 系统权限：双击 .codex 文件启动 → 自动导入并打开 CODEX 播放器
    if len(sys.argv) > 1:
        p = sys.argv[1]
        if p.lower().endswith(".codex") and os.path.isfile(p):
            try:
                ok, name, msg = codex_core.import_zip(p, app.codex_dir)
                if ok:
                    app.codex_auto_open = name
                    print(f"[CODEX] 双击打开: {name}（{msg}）")
            except Exception as e:
                print(f"[CODEX] 打开失败: {e}")
    html_path = os.path.join(_web_root(), "index.html")
    window = webview.create_window(
        "Direct-Interface Cork-bore Kit " + app_version.display(), html_path, js_api=app,
        width=1060, height=820, min_size=(860, 640), background_color="#0f1115")
    webview.start()
    # 窗口关掉之后收线：别再让分道线程拖着进程
    try:
        import jobs
        jobs.shutdown()
    except Exception:
        pass


if __name__ == "__main__":
    main()
