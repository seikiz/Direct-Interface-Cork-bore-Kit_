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
                        tree_ts_of, BUILTIN_RELAY, PROVIDERS, assemble_role_prompt, ROLE_FIELDS)
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
WORLD_PARAMS = [
    ("tech_level", "科技水平"),
    ("supernatural", "超自然体系"),
    ("physics", "物理法则"),
    ("time_flow", "时间流速"),
    ("climate", "气候环境"),
    ("geography", "地理格局"),
    ("politics", "政治格局"),
    ("economy", "经济体系"),
]


def html_app_clean_battle(battle):
    """规整战斗配置（类型安全）：attrs / mech_attrs / formulas / moves / buffs"""
    if not isinstance(battle, dict):
        return None
    out = {}
    attrs = battle.get("attrs")
    if isinstance(attrs, dict):
        cleaned = {}
        for key, a in attrs.items():
            if not isinstance(a, dict):
                continue
            key = str(key).strip()[:20]
            if not key:
                continue
            entry = {"label": str(a.get("label") or key).strip()[:20]}
            try:
                entry["initial"] = int(a.get("initial", 10) or 10)
            except (TypeError, ValueError):
                entry["initial"] = 10
            if key == "hp":
                try:
                    entry["max"] = int(a.get("max", 100) or 100)
                except (TypeError, ValueError):
                    entry["max"] = 100
                entry["initial"] = min(entry.get("initial", 100), entry["max"])
            cleaned[key] = entry
        if cleaned:
            out["attrs"] = cleaned
    mech_attrs = battle.get("mech_attrs")
    if isinstance(mech_attrs, list):
        cleaned = []
        for a in mech_attrs:
            if not isinstance(a, dict) or not str(a.get("key") or "").strip():
                continue
            key = str(a["key"]).strip()[:20]
            entry = {"key": key, "label": str(a.get("label") or key).strip()[:20]}
            try:
                entry["initial"] = int(a.get("initial", 10) or 10)
            except (TypeError, ValueError):
                entry["initial"] = 10
            try:
                entry["max"] = int(a.get("max", 999999) or 999999)
            except (TypeError, ValueError):
                entry["max"] = 999999
            cleaned.append(entry)
        if cleaned:
            out["mech_attrs"] = cleaned
    formulas = battle.get("formulas")
    if isinstance(formulas, dict):
        cleaned = {}
        for k, v in formulas.items():
            k = str(k).strip()[:30]
            if k and isinstance(v, str) and v.strip():
                cleaned[k] = v.strip()[:200]
        if cleaned:
            out["formulas"] = cleaned
    moves = battle.get("moves")
    if isinstance(moves, list):
        cleaned = []
        for m in moves:
            if not isinstance(m, dict) or not str(m.get("id") or "").strip():
                continue
            entry = {"id": str(m["id"]).strip()[:30],
                     "name": str(m.get("name") or m["id"]).strip()[:30],
                     "desc": str(m.get("desc") or "").strip()[:60]}
            if isinstance(m.get("formula"), str) and m["formula"].strip():
                entry["formula"] = m["formula"].strip()[:200]
            if isinstance(m.get("cost"), dict):
                cost = {}
                for k, v in m["cost"].items():
                    try:
                        cost[str(k).strip()[:20]] = int(v)
                    except (TypeError, ValueError):
                        pass
                if cost:
                    entry["cost"] = cost
            if isinstance(m.get("buffs"), list):
                bl = []
                for b in m["buffs"]:
                    if isinstance(b, dict) and b.get("id"):
                        try:
                            turns = int(b.get("turns", 3) or 3)
                        except (TypeError, ValueError):
                            turns = 3
                        bl.append({"id": str(b["id"]).strip()[:30], "turns": max(1, turns)})
                if bl:
                    entry["buffs"] = bl
            cleaned.append(entry)
        if cleaned:
            out["moves"] = cleaned
    buffs = battle.get("buffs")
    if isinstance(buffs, list):
        cleaned = []
        for b in buffs:
            if not isinstance(b, dict) or not str(b.get("id") or "").strip():
                continue
            entry = {"id": str(b["id"]).strip()[:30],
                     "name": str(b.get("name") or b["id"]).strip()[:30],
                     "desc": str(b.get("desc") or "").strip()[:60]}
            try:
                entry["turns"] = int(b.get("turns", 3) or 3)
            except (TypeError, ValueError):
                entry["turns"] = 3
            if isinstance(b.get("attrs"), dict):
                at = {}
                for k, v in b["attrs"].items():
                    try:
                        at[str(k).strip()[:20]] = int(v)
                    except (TypeError, ValueError):
                        pass
                if at:
                    entry["attrs"] = at
            cleaned.append(entry)
        if cleaned:
            out["buffs"] = cleaned
    return out or None


def _parse_fields(fields_json):
    """fields_json 可能是 dict、JSON 字符串或旧版纯文本设定；返回 dict"""
    if fields_json is None:
        return {}
    if isinstance(fields_json, dict):
        return fields_json
    s = str(fields_json)
    try:
        d = json.loads(s)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def html_app_clean_mechanics(mech):
    """规整机制卡字段（类型安全）：affection / status.fields / events"""
    if not isinstance(mech, dict):
        return None
    out = {}
    aff = mech.get("affection")
    if isinstance(aff, dict) and aff.get("enabled"):
        try:
            mn = int(aff.get("min", 0) or 0)
        except (TypeError, ValueError):
            mn = 0
        try:
            mx = int(aff.get("max", 100) or 100)
        except (TypeError, ValueError):
            mx = 100
        if mn >= mx:
            mn, mx = 0, 100
        try:
            initial = int(aff.get("initial", 50) or 50)
        except (TypeError, ValueError):
            initial = 50
        initial = max(mn, min(mx, initial))
        try:
            crit = float(aff.get("crit", 0.001) or 0.001)
        except (TypeError, ValueError):
            crit = 0.001
        out["affection"] = {"enabled": True, "initial": initial, "min": mn, "max": mx,
                            "crit": max(0.0, min(1.0, crit))}
    status = mech.get("status")
    if isinstance(status, dict) and status.get("enabled"):
        fields = []
        for f in (status.get("fields") or []):
            if not isinstance(f, dict) or not str(f.get("key") or "").strip():
                continue
            key = str(f["key"]).strip()[:20]
            ftype = "int" if f.get("type") == "int" else "enum"
            field = {"key": key, "name": str(f.get("name") or key).strip()[:20], "type": ftype}
            if ftype == "int":
                try:
                    mn = int(f.get("min", 0) or 0)
                except (TypeError, ValueError):
                    mn = 0
                try:
                    mx = int(f.get("max", 100) or 100)
                except (TypeError, ValueError):
                    mx = 100
                if mn >= mx:
                    mn, mx = 0, 100
                try:
                    initial = int(f.get("initial", 0) or 0)
                except (TypeError, ValueError):
                    initial = 0
                field.update({"min": mn, "max": mx, "initial": max(mn, min(mx, initial))})
            else:
                opts = f.get("options")
                if isinstance(opts, str):
                    opts = [o.strip() for o in opts.replace("，", ",").split(",") if o.strip()]
                if isinstance(opts, list):
                    opts = [str(o).strip()[:20] for o in opts if str(o).strip()]
                field["options"] = opts if opts else []
                field["initial"] = str(f.get("initial") or (opts[0] if opts else "")).strip()[:20]
            fields.append(field)
        if fields:
            out["status"] = {"enabled": True, "fields": fields}
    events = mech.get("events")
    if isinstance(events, list):
        evs = []
        for ev in events:
            if not isinstance(ev, dict) or not str(ev.get("id") or "").strip():
                continue
            e = {"id": str(ev["id"]).strip()[:30],
                 "name": str(ev.get("name") or ev["id"]).strip()[:30],
                 "prompt": str(ev.get("prompt") or "").strip()}
            try:
                if ev.get("aff_ge") is not None:
                    e["aff_ge"] = int(ev["aff_ge"])
            except (TypeError, ValueError):
                pass
            try:
                if ev.get("aff_le") is not None:
                    e["aff_le"] = int(ev["aff_le"])
            except (TypeError, ValueError):
                pass
            kws = ev.get("keywords")
            if isinstance(kws, str):
                kws = [x.strip() for x in kws.replace("，", ",").split(",") if x.strip()]
            if isinstance(kws, list):
                kws = [str(k).strip()[:20] for k in kws if str(k).strip()]
            if kws:
                e["keywords"] = kws
            if ev.get("once", True):
                e["once"] = True
            evs.append(e)
        if evs:
            out["events"] = evs
    roll = mech.get("roll")
    if isinstance(roll, dict):
        cleaned_roll = {}
        _DEF = {"crit": 10, "rare": 4, "fail": 2, "chosen": 0.1, "collapse": 0.001}
        for k in _DEF:
            try:
                v = float(roll.get(k, _DEF[k]))
            except (TypeError, ValueError):
                v = _DEF[k]
            cleaned_roll[k] = max(0.0, min(100.0, v))
        out["roll"] = cleaned_roll
    return out or None


def role_prompt_from_card(name, data):
    """由角色卡数据算出真正要用的系统提示，返回 (prompt, fields, legacy)。

    这里有个踩过的坑：
        assemble_role_prompt 恒定追加「角色卡面·角色塑造」小节，所以它的返回值
        【永远非空】。原来两处载入都写成
            assemble_role_prompt(...) or data.get("system_prompt", "")
        那个 or 回退是死代码，永远轮不到。
        后果：把设定只写在 system_prompt 里、一个结构化字段都没用的卡
        （实测两张，其中一张 2230 字），载入时整份设定被替换成 247 字样板文字，
        角色等于完全没有设定，而且界面上看不出任何异常。
    现在的规则：
        有结构化字段 → 按字段渲染（保持可编辑）；
        一个字段都没有 → 存档正文就是角色的全部设定，直接用，不能丢。
    """
    fields = {k: (data.get(k) or "") for k, _ in ROLE_FIELDS}
    legacy = data.get("legacy") or ""
    rendered = assemble_role_prompt(name, fields, legacy)

    def _has(v):
        if isinstance(v, (list, tuple)):
            return any(str(x).strip() for x in v)
        return bool(str(v or "").strip())

    own = any(_has(fields.get(k)) for k, _ in ROLE_FIELDS) or _has(legacy)
    stored = data.get("system_prompt") or ""
    if own or not stored.strip():
        return rendered, fields, legacy
    return stored, fields, legacy


def _render_world_desc(w):
    """把世界卡渲染给 core：背景 + 世界参数（人类可读标签）"""
    desc = str(w.get("description") or "").strip()
    params = w.get("params") or {}
    plines = []
    for key, label in WORLD_PARAMS:
        v = str(params.get(key) or "").strip()
        if v:
            plines.append(label + "：" + v)
    if plines:
        if desc:
            desc += chr(10) + "【世界参数】" + "；".join(plines)
        else:
            desc = "【世界参数】" + "；".join(plines)
    return desc


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

class HtmlApp(ApiMiscMixin, ApiGoMixin, ApiSettingsMixin, ApiWsMixin, ApiCodexMixin, HostMixin, GoMixin, CodexMixin, WsMixin):
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
    def _load_presets(self):
        self.presets = [{"name": "默认"}]
        try:
            for fn in sorted(os.listdir(self.preset_dir)):
                if fn.endswith(".json"):
                    with open(os.path.join(self.preset_dir, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("name"):
                        self.presets.append(data)
        except Exception:
            pass
        self.preset_name = self.config.get("prompt_preset", "") or ""

    def _load_roles(self):
        self.roles = []
        try:
            for fn in sorted(os.listdir(self.save_dir)):
                if fn.startswith("."):
                    continue  # 跳过跑团会期锁等隐藏/元数据文件
                if not fn.endswith(".json"):
                    continue
                try:
                    path = os.path.join(self.save_dir, fn)
                    data = save_guard.guard_loaded(path, kind="role")
                    if data is None:
                        continue
                    if isinstance(data, dict) and data.get("system_prompt"):
                        prompt, fields, legacy = role_prompt_from_card(
                            data.get("name") or fn[:-5], data)
                        self.roles.append({"name": data.get("name") or fn[:-5],
                                           "file": fn, "prompt": prompt, "data": data,
                                           "fields": fields, "legacy": legacy,
                                           "unlocked": bool(data.get("unlocked", False))})
                except Exception:
                    continue
        except Exception:
            pass
        # 恢复上次选中的角色（与 Android 端一致：启动即恢复，恋爱条/机制卡初始就绪，
        # 无需再手动保存一遍才出现）。config.selected_roles（新版数组）或 last_role（旧版单值）。
        self.selected_roles = []
        try:
            saved = self.config.get("selected_roles") or []
            if not isinstance(saved, list):
                saved = []
            if not saved and self.config.get("last_role"):
                lr = str(self.config.get("last_role") or "").strip()
                if lr:
                    saved = [lr]
            self.selected_roles = [n for n in saved
                                   if any(r["name"] == n for r in self.roles)][:8]
        except Exception:
            self.selected_roles = []

    def _detect_ollama(self):
        """后台探测本地 Ollama（localhost / 127.0.0.1），结果进 api_state"""
        try:
            import requests
            for url in ("http://localhost:11434/v1/models",
                        "http://127.0.0.1:11434/v1/models"):
                try:
                    r = requests.get(url, timeout=3)
                    if r.status_code < 500:
                        self.ollama_online = True
                        print("[Ollama] ✅ 本地 Ollama 已检测到")
                        return
                except Exception:
                    continue
        except Exception:
            pass
        self.ollama_online = False
        print("[Ollama] 未检测到本地服务（需要时先安装并启动 Ollama）")

    def _load_worlds(self):
        self.worlds = []
        try:
            for fn in sorted(os.listdir(self.world_dir)):
                if not fn.endswith(".json"):
                    continue
                try:
                    data = save_guard.guard_loaded(os.path.join(self.world_dir, fn), kind="world")
                    if isinstance(data, dict) and data.get("name"):
                        self.worlds.append(data)
                except Exception:
                    continue
        except Exception:
            pass
        self.selected_worlds = []
    def _on_busy(self, msg=""):
        notices.busy_toast(self, msg)      # 忙=轻提示；去重与弹法都在 notices

    def _append_sys(self, content, kind="sys", speaker="系统"):
        """树外横幅（系统提示/命令回显），随重建一直显示"""
        with self._lock:
            self.sys_msgs.append({"kind": kind, "speaker": speaker, "content": content})
            if len(self.sys_msgs) > 200:
                self.sys_msgs = self.sys_msgs[-200:]
        self._rebuild_messages()

    def _chain_nodes(self):
        """从 core 树里取当前链（跳过 system 节点），返回 MessageNode 列表（root→leaf）"""
        tree = self.core.tree
        leaf = tree.current_leaf_id
        if not leaf or leaf not in tree.nodes:
            return []
        chain = []
        node = tree.nodes.get(leaf)
        while node is not None:
            chain.append(node)
            if node.parent_id and node.parent_id in tree.nodes:
                node = tree.nodes.get(node.parent_id)
            else:
                break
        chain.reverse()
        return [n for n in chain if n.role != "system"]

    def _rebuild_messages(self):
        """按 当前聊天树链 + 系统横幅 重建展示消息列表（epoch +1 通知前端整刷）。
        消息 seq 按 (类型,键) 缓存：重建不重排，前端旧 seq 依然有效。"""
        with self._lock:
            def nxt(key):
                if key in self.node_seq_cache:
                    return self.node_seq_cache[key]
                self.seq += 1
                self.node_seq_cache[key] = self.seq
                return self.seq

            msgs = []
            for i, s in enumerate(self.sys_msgs):
                if isinstance(s, str):
                    s = {"kind": "sys", "speaker": "系统", "content": s}
                msgs.append({"seq": nxt(("sys", i)), "kind": s.get("kind", "sys"),
                             "speaker": s.get("speaker", "系统"),
                             "content": s.get("content", ""), "image": s.get("image"), "node_id": None})
            for n in self._chain_nodes():
                seq = nxt(("node", n.id))
                meta = n.metadata or {}
                kind = "user" if n.role == "user" else "ai"
                speaker = meta.get("speaker")
                if kind == "user":
                    # 用户消息显示玩家卡名字（与头像文件名一致），无名字时显示「你」
                    speaker = (self.persona or {}).get("name") or "你"
                elif not speaker:
                    # 单角色：AI 消息显示当前激活角色名；群聊/无角色时显示 AI
                    speaker = self.selected_roles[0] if len(self.selected_roles) == 1 else "AI"
                msgs.append({"seq": seq, "kind": kind, "speaker": speaker,
                             "content": n.content, "image": self.node_images.get(n.id),
                             "node_id": n.id})
            # 滑条信息：AI 消息的父用户节点有多个 assistant 子节点时给箭头
            for i, m in enumerate(msgs):
                if m["kind"] != "ai" or not m["node_id"]:
                    continue
                node = self.core.tree.nodes.get(m["node_id"])
                if node and node.parent_id and node.parent_id in self.core.tree.nodes:
                    sibs = [cid for cid in self.core.tree.nodes[node.parent_id].children_ids
                            if self.core.tree.nodes.get(cid) and self.core.tree.nodes[cid].role == "assistant"]
                    if len(sibs) > 1:
                        m["swipes"] = {"total": len(sibs), "index": sibs.index(m["node_id"])}
            self.messages = msgs
            self.render_epoch += 1

    def _save_tree(self, wait=True):
        """把当前聊天树写回第一个选中角色的文件（保留 name/system_prompt/card_data）

        wait=False：自动落盘走 io 线（见下），界面不必等磁盘。
        """
        if not self.selected_roles:
            return
        # 跑团会期锁定：被锁卡不可被当前会话清写/推送记忆树（防导入存档与跑团混淆）
        if self.selected_roles[0] in self._trpg_locked_names():
            return
        tree_data = self.core.get_all_nodes_data()
        # 空树（只有系统节点）不覆盖已有历史，防止切换/误操作清档
        if len(tree_data.get("nodes", {})) <= 1:
            return
        for r in self.roles:
            if r["name"] == self.selected_roles[0]:
                data = dict(r.get("data") or {})
                data["name"] = r["name"]
                data["system_prompt"] = r["prompt"]
                data["kind"] = "dick_card"
                data["history_tree"] = self.core.get_all_nodes_data()
                # 机制状态显式持久化到角色卡（修复"清空/重选回落 initial"：
                # 不依赖树的临时 ms 快照，保存当前状态供还原）
                try:
                    data["mechanics_state"] = self.core.mechanism_snapshot()
                except Exception:
                    pass
                # 进度同步时间戳（UTC ISO，跨设备按该串比较新旧）
                try:
                    from datetime import datetime, timezone
                    data["_tree_ts"] = datetime.now(timezone.utc).isoformat()
                except Exception:
                    pass
                try:
                    # 存档守护：覆盖前留底 + 原子写入（写一半崩溃也不会截断存档）
                    # 自动落盘（wait=False）走 io 线：整棵树可能几百 KB，写盘不该挡着界面刷新；
                    # 显式保存/备份/退出仍走同步（wait=True）—— 那几处必须确保真的落盘了。
                    _path = os.path.join(self.save_dir, r["file"])
                    if wait:
                        save_guard.backup_file(_path)
                        save_guard.atomic_write_json(_path, data)
                    else:
                        import jobs as _jobs
                        _jobs.submit("io", save_guard.atomic_write_json, _path, data,
                                     name="自动落盘：" + str(r["name"]),
                                     on_done=lambda _r, _e: None)
                except Exception:
                    pass
                # 同步内存快照：勾选/取消勾选切换时 _activate_core 从
                # r["data"]["history_tree"] 取记录，不同步会导致同一会话内
                # 重新勾选只恢复到旧快照（新建角色的记录甚至取不回）
                r["data"] = data
                # 进度同步：把聊天树推送到工坊服务器（后台线程，不阻塞保存）
                self._ws_save_upload_async(r["name"], data["history_tree"])
                break

    def _build_system_prompt(self):
        sb = []
        preset = None
        for p in self.presets:
            if p.get("name") == self.preset_name:
                preset = p
                break
        if preset and preset.get("system_prefix"):
            sb.append(preset["system_prefix"])
        chosen = [r for r in self.roles if r["name"] in self.selected_roles]
        for r in chosen:
            sb.append(r["prompt"])
        if len(chosen) > 1:
            sb.append("当前是群聊，参与角色：" + "、".join(r["name"] for r in chosen) +
                      "。每次由一位角色发言，用 [角色名]: 开头标注。用户 @角色名 表示指定该角色回复。")
        ws = [w for w in self.worlds if w.get("name") in self.selected_worlds]
        if ws:
            sb.append("【世界设定】")
            for w in ws:
                sb.append(str(w.get("name")) + "：" + str(w.get("description", "")))
        if self.persona:
            sb.append("【玩家角色卡】" + json.dumps(self.persona, ensure_ascii=False))
        if preset and preset.get("rules"):
            sb.append(preset["rules"])
        injection = self.plugin_manager.contextInjection() if hasattr(self.plugin_manager, "contextInjection") else ""
        if injection:
            sb.append(injection)
        if preset and preset.get("system_suffix"):
            sb.append(preset["system_suffix"])
        # 本轮角色锚点（最靠后，最贴合模型“最近注意力”）
        anchor = self._anchor_block()
        if anchor:
            sb.append(anchor)
        return "\n\n".join(x for x in sb if x and str(x).strip())

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

    def _roll_option(self, item):
        """点选项时按配置概率表 ROLL（百分比可配：机制卡 mechanics.roll，默认
        暴击10/稀有4/大失败2/天选0.1(千分之一)/坍缩0.001(十万分之一)；概率不公布）。
        返回 (effect, kind, note)"""
        import random as _r
        cfg = getattr(self.core, "_mech_config", None) or {}
        roll = cfg.get("roll") if isinstance(cfg, dict) else None
        if not isinstance(roll, dict):
            roll = {}
        def _p(key, dflt):
            try:
                return float(roll.get(key, dflt))
            except (TypeError, ValueError):
                return dflt
        # 天选 = 千分之一（兼容旧键 legend：旧卡没配 chosen 时沿用其传说概率）
        chosen_p = _p("chosen", _p("legend", 0.1))
        collapse_p = _p("collapse", 0.001)
        fail_p = _p("fail", 2)
        rare_p = _p("rare", 4)
        crit_p = _p("crit", 10)
        chosen_p = max(0.0, min(100.0, chosen_p)) / 100.0
        collapse_p = max(0.0, min(100.0, collapse_p)) / 100.0
        fail_p = max(0.0, min(100.0, fail_p)) / 100.0
        rare_p = max(0.0, min(100.0, rare_p)) / 100.0
        crit_p = max(0.0, min(100.0, crit_p)) / 100.0
        table = [
            (collapse_p, "collapse", "🌌 坍缩：十万分之一的奇迹坍缩成现实！"),
            (collapse_p + chosen_p, "chosen", "🌟 天选：千分之一的天命眷顾被触发了！"),
            (collapse_p + chosen_p + fail_p, "fail", "💥 结果出了岔子！"),
            (collapse_p + chosen_p + fail_p + rare_p, "rare", "✨ 命运的眷顾：触发了稀有事件！"),
            (collapse_p + chosen_p + fail_p + rare_p + crit_p, "crit", "✨ 效果暴击！"),
            (1.0, "normal", ""),
        ]
        r = _r.random()
        kind, note = "normal", ""
        for limit, k, n in table:
            if r < limit:
                kind, note = k, n
                break
        effect = {}
        if isinstance(item, dict):
            aff = item.get("aff")
            st = item.get("st")
            if isinstance(st, dict):
                effect["st"] = st
            if aff is not None:
                try:
                    aff = int(aff)
                except (TypeError, ValueError):
                    aff = None
            if aff is not None:
                if kind == "crit":
                    effect["aff"] = aff * 2
                elif kind == "fail":
                    effect["aff"] = -aff
                else:
                    effect["aff"] = aff
            elif kind in ("crit", "fail"):
                # 无机制效果的选项：暴击/失败仅提示，不空转
                note = ""
        return effect, kind, note

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

    def _expand_macros(self, text):
        """Quick Reply 宏展开（酒馆 {{player}}/{{char}} 的对等物）：
        {player} 玩家卡名 · {char} 当前角色 · {world} 当前世界 · {random:a|b|c} 随机取一
        未知宏原样保留。"""
        if not text or "{" not in text:
            return text
        import random as _r
        player = (self.persona or {}).get("name") or "你"
        char = self.selected_roles[0] if self.selected_roles else "AI"
        world = self.current_world or ""

        def rep(m):
            key = m.group(1).strip()
            if key == "player":
                return player
            if key == "char":
                return char
            if key == "world":
                return world
            if key.startswith("random:"):
                opts = [x for x in key[len("random:"):].split("|") if x]
                return _r.choice(opts) if opts else ""
            return m.group(0)

        import re as _re
        return _re.sub(r"\{([^{}]+)\}", rep, text)

    def _regex_rules_all(self, scope):
        """生效规则：全局 regex_rules.json + 当前角色卡 regex_rules（角色卡优先）"""
        rules = []
        try:
            with open(os.path.join(self.base_dir, "regex_rules.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                rules.extend(data)
        except Exception:
            pass
        for name in self.selected_roles:
            for r in self.roles:
                if r["name"] == name:
                    adv = (r.get("data") or {}).get("advanced") or {}
                    rr = adv.get("regex_rules") or []
                    if isinstance(rr, list):
                        rules = list(rr) + rules
                    break
        # 玩家卡规则（同规格待遇）：对玩家输入生效，优先于角色卡
        p = self.persona or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        if isinstance(p, dict):
            prr = (p.get("advanced") or {}).get("regex_rules") or []
            if isinstance(prr, list):
                rules = list(prr) + rules
        out = []
        for x in rules:
            if not isinstance(x, dict) or not x.get("enabled", True):
                continue
            if not str(x.get("pattern") or "").strip():
                continue
            if (x.get("scope") or "both") not in (scope, "both"):
                continue
            out.append(x)
        return out

    def _apply_regex_pipeline(self, text, scope):
        """应用正则管道（存储前调用 → 树里存转换后文本，回溯/分支天然一致）"""
        if not text:
            return text
        for rule in self._regex_rules_all(scope):
            try:
                pattern = str(rule.get("pattern") or "")
                repl = str(rule.get("replace") or "")
                text = re.sub(pattern, repl, text)
            except Exception:
                continue
        return text

    def _present_ending(self):
        """结局达成：读取 mechanics.endings，命中（达成事件链/状态）→ 弹结局横幅 + 注入收束到下一轮。"""
        try:
            ending = self.core.check_endings()
            if not ending:
                return
            nm = ending.get("name") or "结局"
            desc = ending.get("desc") or ""
            self._append_sys(f"🏁 结局达成：「{nm}」" + ((" · " + desc) if desc else "") + "（可回档到之前重走别的结局）")
            self.core.pending_event = {"id": "_ending", "name": "结局达成",
                "prompt": f"剧情已自然抵达结局「{nm}」。请以这一段收束剧情：{desc}。就写到这里，不要再展开新的支线。"}
        except Exception:
            pass

    def _handle_travel(self, text):
        """/穿越 [世界名]：列出可穿越世界或直接穿越；返回提示文本或 None（不是穿越命令）"""
        parts = text.split(None, 1)
        if (parts[0] if parts else "").strip().lower() not in ("/穿越", "/travel"):
            return None
        target = parts[1].strip() if len(parts) > 1 else ""
        if not self.selected_worlds:
            return "⚠️ 还没有勾选世界卡（左侧世界列表勾选后即可穿梭）"
        if not target:
            lines = ["🌍 可穿越的世界："]
            for i, n in enumerate(self.selected_worlds, 1):
                mark = " ★当前所在" if n == self.current_world else ""
                lines.append(str(i) + ". " + n + mark)
            lines.append("用法：/穿越 世界名")
            return chr(10).join(lines)
        hit = next((n for n in self.selected_worlds if n == target or target in n), None)
        if not hit:
            return "⚠️ 没有找到世界「" + target + "」，可用 /穿越 查看列表"
        self.api_travel(hit)
        return "🚀 已穿越到「" + hit + "」"

    def _start_fetch(self, user_node_id):
        """在指定用户节点下生成回复（候选/滑条/分支共用入口）"""
        self.busy = True
        self.streaming = ""
        self.core.generate_candidate(
            user_node_id,
            on_stream=lambda full: setattr(self, "streaming",
                                           self.core.strip_mechanism_tags(full, apply=False)),
            on_response=self._on_response,
            on_error=self._on_error, on_busy=self._on_busy)

    def _split_hidden(self, processed):
        """翻译隐藏标记解析 → (显示文本, 发送文本)。无标记则两者相同。
        约定：jp_patch 自动日译返回 "\u200b<原文>\u200b<译文>"。"""
        if not processed:
            return processed, processed
        mark = "\u200b"
        if isinstance(processed, str) and processed.startswith(mark):
            parts = processed.split(mark)
            if len(parts) >= 3:
                return parts[1], mark.join(parts[2:])
        return processed, processed

    def _send_text(self, display_text, hidden_send, image, is_choice=False):
        # 零宽字符防线：白烧 token / 卡界面 / 藏提示词注入 / 绕过关键词过滤。
        # 放在最前面 —— 后面入树、发 API、渲染用的都是清干净的文本。
        try:
            import text_guard
            display_text, _grep = text_guard.sanitize(display_text)
            if _grep.get("changed"):
                self._append_sys(text_guard.summary(_grep), kind="warn", speaker="安全")
            if hidden_send:
                hidden_send, _ = text_guard.sanitize(hidden_send)
        except Exception:
            pass
        # 显示/存储用原文；若翻译隐藏（hidden_send 非空且不同），译文存 metadata["ja_input"]，
        # _fetch_response 发 AI 时优先用译文（聊天永远看不到日文）
        content = self._apply_regex_pipeline(display_text or "", "user")
        self._last_user = display_text or ""
        speaker = (self.persona or {}).get("name") or "你"
        node_id = self.core.add_user_message(content)
        try:
            self.core.tree.nodes[node_id].metadata["speaker"] = speaker
            if is_choice:
                # GAL 选项点：标记该用户节点为「选项」，供树视图选项骨架/收纳用
                self.core.tree.nodes[node_id].metadata["is_choice"] = True
            if hidden_send and hidden_send != display_text:
                self.core.tree.nodes[node_id].metadata["ja_input"] = hidden_send
            if self.core.mechanism_state is not None:
                self.core.tree.nodes[node_id].metadata["ms"] = self.core.mechanism_snapshot()
        except Exception:
            pass
        if image:
            self.node_images[node_id] = image
        self._start_fetch(node_id)
        self._rebuild_messages()

    def _on_response(self, ai_reply, usage):
        # 回复到了 → 开场加载态结束（无论这轮是不是开局，清掉都安全）
        self.opening_loading = False
        notices.set_status(self, "")      # 收起输入栏上方那行状态
        # 模型也可能吐零宽字符（尤其被用户诱导时）→ 同样清掉再入树，
        # 否则它会一直躺在聊天记录里，每次请求都白烧 token
        try:
            import text_guard
            ai_reply, _grep = text_guard.sanitize(ai_reply)
        except Exception:
            pass
        if usage:
            self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        # 中字日配：提取 [ja]...[/ja] 隐藏配音句（存节点 metadata，正文剥离）
        ja_text = ""
        try:
            m = re.search(r"\[ja\]([\s\S]*?)\[/ja\]", ai_reply or "")
            if m:
                ja_text = m.group(1).strip()
                ai_reply = re.sub(r"\[ja\][\s\S]*?\[/ja\]", "", ai_reply)
        except Exception:
            pass
        # 机制卡：解析 [aff:+N]/[键:值] 标签 → 应用状态 → 更新节点内容 → 检查事件
        try:
            clean = self.core.strip_mechanism_tags(ai_reply or "", apply=True)
            # 正则管道（ai 作用域）：标签剥离后、写入树前应用
            clean = self._apply_regex_pipeline(clean, "ai")
            if self.core.mechanism_state is not None:
                leaf = self.core.tree.current_leaf_id
                if leaf and leaf in self.core.tree.nodes:
                    node = self.core.tree.nodes[leaf]
                    if clean != (node.content or ""):
                        node.content = clean
                    ev = self.core.check_mech_events(self._last_user)
                    if ev:
                        self.core.pending_event = ev
                    node.metadata["ms"] = self.core.mechanism_snapshot()
                    if ja_text:
                        node.metadata["ja"] = ja_text
            ai_reply = clean
        except Exception:
            pass
        self._present_ending()
        # 世界线切换同步到 UI（GM 标记已由 core 解析并切换）——更新当前世界/配置/横幅
        try:
            sw = getattr(self.core, "last_world_switch", None)
            if sw:
                self.core.last_world_switch = None
                self.current_world = sw
                self.config["current_world"] = sw
                self._save_config()
                self._append_sys("🌐 已穿越到世界线「" + str(sw) + "」")
        except Exception:
            pass
        self._save_tree(wait=False)  # 自动落盘：走 io 线，别挡界面
        self._rebuild_messages()
        self.streaming = ""
        self.busy = False
        if self.auto_turn and len(self.selected_roles) > 1:
            self._maybe_auto_turn(2)
        for p in self.plugin_manager.get_all_plugins():
            if p.enabled:
                # 同上：钩子不挡回复（plugin 线 + 单任务 15 秒超时）
                try:
                    import jobs as _jobs
                    _jobs.submit("plugin", p.on_message_received,
                                 getattr(self, "_last_user", ""), ai_reply,
                                 name="插件钩子：" + str(getattr(p, "name", "?")),
                                 timeout=15)
                except Exception:
                    pass
        # 围棋：从模型回复里解析落子（引擎校验；非法/找不到就驳回重选或兜底）
        try:
            if getattr(self, "_go", None) is not None:
                self._go_after_reply(ai_reply if isinstance(ai_reply, str) else "")
        except Exception:
            pass

    def _on_error(self, err_msg):
        self.streaming = ""
        self.busy = False
        self.opening_loading = False     # 出错也要收掉开场加载态，否则会一直转圈
        self._save_tree(wait=False)  # 自动落盘：走 io 线，别挡界面
        # 商业化质量的错误提示：把裸异常转成"用户能行动"的指引
        msg = str(err_msg or "")
        low = msg.lower()
        hint = None
        if any(k in low for k in ("401", "invalid api key", "unauthorized", "authentication", "api key")):
            hint = "API Key 无效或未填。请到「设置 → 模型」里粘贴你的 Key（或检查是否过期）。"
        elif any(k in low for k in ("404", "not found", "model")):
            hint = "模型名或服务地址可能填错了。请到「设置 → 模型」核对 base_url 与模型名。"
        elif any(k in low for k in ("429", "rate limit", "too many", "超限", "insufficient")):
            hint = "请求过于频繁或余额不足。稍等再试，或检查账户额度。"
        elif any(k in low for k in ("timeout", "timed out", "connection", "network", "refused", "resolve")):
            hint = "网络连不上（可能被墙/代理没配）。可到「设置」开代理，或启用内置中转通道。"
        if hint:
            self._append_sys("❌ " + msg + "\n💡 " + hint)
        else:
            self._append_sys("❌ " + msg)

    # ---------- 管理动作 ----------
    def _activate_core(self, reload_tree=True):
        """把选中角色/世界/预设/玩家卡接入 core（重建系统节点 + 首个角色的历史树）"""
        roles_data = []
        for i, name in enumerate(self.selected_roles):
            for r in self.roles:
                if r["name"] == name:
                    rd = {"name": r["name"], "system_prompt": r["prompt"],
                          "unlocked": r.get("unlocked", False),
                          "advanced": (r.get("data") or {}).get("advanced")}
                    if i == 0 and reload_tree and r.get("data") and r["data"].get("history_tree"):
                        rd["history_tree"] = r["data"]["history_tree"]
                    # 角色卡显式持久化的机制状态：传入 core 以便清空/重选时正确还原
                    if i == 0 and r.get("data"):
                        ms0 = (r["data"] or {}).get("mechanics_state")
                        if isinstance(ms0, dict):
                            rd["mechanics_state"] = ms0
                    roles_data.append(rd)
        self.core.set_active_roles(roles_data)
        self.core.set_worlds(self._worlds_for_core())
        self.core.set_player_persona(self.persona)
        preset = None
        for p in self.presets:
            if p.get("name") == self.preset_name:
                preset = p
                break
        self.core.set_prompt_preset(preset if preset and preset.get("name") else None)
        # 切换角色 = 新会话：旧剧情选项作废
        self._clear_choices()
        self.core.pending_event = None
        # 前瞻投机器的开关状态要跟着走：关键词是按角色存的，
        # 换了角色可能就从"有目标"变成"没目标"，这时必须摘掉投机器。
        self._sync_speculator()
        self._start_opening()
        self._rebuild_messages()

    def _start_opening(self):
        """新会话开场：把角色卡的开场白当【场景】交给模型，由它现场演出第一幕。

        为什么不是直接把开场白贴出来：
            贴出来的是作者写死的文字，和当前选中的世界卡/玩家卡/好感度无关，
            读起来像一段设定文档，而不是「她在对你说话」。
            交给模型演，开场才会对上当前配置，用户才有沉浸感。
        发不出去时（没配 Key / 没有开场白 / 正在忙）退回直接显示原文，
        免得界面一片空白 —— 有开场白总比空着强。
        """
        try:
            if len(self.selected_roles) != 1:
                return 0                     # 群聊不做开场，避免多个角色抢话
            tree = self.core.tree
            # 已有历史（续聊/存档）就不再演，否则每次切回来都重演一遍
            for n in tree.nodes.values():
                if n.role in ("user", "assistant"):
                    return 0
            name = self.selected_roles[0]
            role = next((r for r in self.roles if r["name"] == name), None)
            if not role:
                return 0
            data = role.get("data") or {}
            fields = role.get("fields") or {}
            mes = str(data.get("first_mes") or fields.get("first_mes") or "").strip()
            if not mes:
                return 0

            # 首选：让模型把这段场景演出来
            fired = False
            try:
                self.busy = True
                self.streaming = ""
                self.opening_loading = True      # 让界面在模型吐字之前就有加载提示
                fired = self.core.generate_opening(
                    mes,
                    on_stream=lambda full: setattr(
                        self, "streaming",
                        self.core.strip_mechanism_tags(full, apply=False)),
                    on_response=self._on_response,
                    on_error=self._on_error, on_busy=self._on_busy)
            except Exception:
                fired = False
                self.opening_loading = False
            if fired:
                self._rebuild_messages()
                return 1

            # 退路：发不出去就直接把开场白原文显示出来
            self.busy = False
            self.opening_loading = False
            nid = self.core.add_assistant_message(
                mes, parent_id=tree.current_leaf_id,
                metadata={"speaker": role.get("name"), "usage": None, "greeting": True})
            tree.current_leaf_id = nid
            tree.fix_leaf()
            return 1
        except Exception:
            return 0                          # 开场失败不该阻断开聊

    def _worlds_for_core(self):
        """选中世界 → core 数据结构（背景中内嵌世界参数的人类可读渲染）"""
        out = []
        for w in self.worlds:
            if w.get("name") in self.selected_worlds:
                wc = dict(w)
                wc["description"] = _render_world_desc(w)
                out.append(wc)
        return out

    def _sync_worlds(self):
        """把选中世界接入 core；当前世界若不在选中列表则回退到第一个"""
        selected = self._worlds_for_core()
        self.core.set_worlds(selected)
        if self.current_world not in self.selected_worlds:
            self.current_world = self.selected_worlds[0] if self.selected_worlds else ""
        if self.current_world:
            self.core.set_current_world(self.current_world)
        self.config["current_world"] = self.current_world
        self._save_config()

    @staticmethod
    def _safe_name(name):
        for ch in [chr(92), "/", ":", "*", "?", '"', "<", ">", "|"]:
            name = name.replace(ch, "_")
        return (name or "").strip()[:60]

    def _parse_role_input(self, name, fields_json):
        """解析角色卡输入：结构化字段 dict / JSON / 旧版纯文本设定 → (legacy, fields, unlocked, advanced)"""
        legacy = ""
        fields = {k: "" for k, _ in ROLE_FIELDS}
        raw = _parse_fields(fields_json)
        if isinstance(fields_json, str) and not raw and fields_json.strip() and not fields_json.strip().startswith("{"):
            legacy = fields_json.strip()
        else:
            legacy = (raw.get("legacy") or raw.get("system_prompt") or "")
            if isinstance(legacy, list):
                legacy = "、".join(str(x) for x in legacy)
            legacy = str(legacy).strip()
            fields = {}
            for k, _ in ROLE_FIELDS:
                v = raw.get(k) or ""
                if isinstance(v, list):
                    v = "、".join(str(x) for x in v if str(x).strip())
                fields[k] = str(v).strip()
        unlocked = False
        if isinstance(fields_json, dict):
            unlocked = bool(fields_json.get("unlocked", False))
        elif raw:
            unlocked = bool(raw.get("unlocked", False))
        # 高级设置（开发者模式）：game / extra_prompt / dev_notes / card_quick_replies
        advanced = None
        adv_raw = None
        if isinstance(fields_json, dict):
            adv_raw = fields_json.get("advanced")
        elif raw:
            adv_raw = raw.get("advanced")
        if isinstance(adv_raw, dict):
            advanced = adv_raw
        elif isinstance(adv_raw, str) and adv_raw.strip():
            try:
                parsed = json.loads(adv_raw)
                if isinstance(parsed, dict):
                    advanced = parsed
            except Exception:
                advanced = None
        return legacy, fields, unlocked, advanced

    @staticmethod
    def _clean_advanced(advanced):
        """规整高级设置字段（只保留已知键，类型安全）"""
        if not isinstance(advanced, dict):
            return None
        game = advanced.get("game")
        if isinstance(game, dict):
            game = {
                "name": str(game.get("name") or "").strip()[:60],
                "rules": str(game.get("rules") or "").strip(),
                "state": str(game.get("state") or "").strip(),
            }
        adv = {
            "game": game if isinstance(game, dict) and (game["rules"] or game["name"]) else None,
            "extra_prompt": str(advanced.get("extra_prompt") or "").strip(),
            "dev_notes": str(advanced.get("dev_notes") or "").strip(),
            "card_face": codex_core.sanitize_html(str(advanced.get("card_face") or "").strip()),
        }
        mech = advanced.get("mechanics")
        if isinstance(mech, dict):
            cleaned_mech = html_app_clean_mechanics(mech)
            if cleaned_mech:
                adv["mechanics"] = cleaned_mech
        battle = advanced.get("battle")
        if isinstance(battle, dict):
            cleaned_battle = html_app_clean_battle(battle)
            if cleaned_battle:
                adv["battle"] = cleaned_battle
        regex_rules = advanced.get("regex_rules")
        if isinstance(regex_rules, list):
            cleaned_rr = []
            for x in regex_rules:
                if not isinstance(x, dict) or not str(x.get("pattern") or "").strip():
                    continue
                scope = str(x.get("scope") or "both")
                if scope not in ("ai", "user", "both"):
                    scope = "both"
                cleaned_rr.append({
                    "id": str(x.get("id") or "")[:30],
                    "name": str(x.get("name") or x.get("id") or "")[:30],
                    "pattern": str(x.get("pattern") or "").strip(),
                    "replace": str(x.get("replace") or ""),
                    "scope": scope,
                    "enabled": bool(x.get("enabled", True)),
                })
            if cleaned_rr:
                adv["regex_rules"] = cleaned_rr
        qrs = advanced.get("card_quick_replies")
        if isinstance(qrs, list):
            cleaned = []
            for x in qrs:
                if isinstance(x, dict) and x.get("label"):
                    cleaned.append({"label": str(x.get("label")).strip()[:30],
                                    "text": str(x.get("text") or "").strip()})
            adv["card_quick_replies"] = cleaned
        else:
            adv["card_quick_replies"] = []
        if not any(v for k, v in adv.items() if k != "card_quick_replies") and not adv["card_quick_replies"]:
            return None
        return adv

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

    def _card_snapshot(self):
        """构造一份当前会话的存档快照（对话树 + 机制状态 + 进度元数据）"""
        from datetime import datetime, timezone
        tree = self.core.get_all_nodes_data()
        mech = None
        try:
            mech = self.core.mechanism_snapshot()
        except Exception:
            mech = None
        n_nodes = 0
        if isinstance(tree, dict):
            nodes = tree.get("nodes") or {}
            n_nodes = sum(1 for n in nodes.values()
                          if isinstance(n, dict) and (n.get("role") or "") != "system")
        return {
            "history_tree": tree,
            "mechanism_state": mech,
            "_tree_ts": datetime.now(timezone.utc).isoformat(),
            "progress": n_nodes,  # 正式聊天条数（不含系统节点）
        }

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

    def _wallpaper_data_url(self):
        p = self._wallpaper_path()
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except Exception:
            return None
        import base64 as _b64
        ext = os.path.splitext(p)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp"}.get(ext, "image/png")
        return "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")

    def _l2d_state(self):
        """Live2D 已并入核心：恒启用；设置从插件读取，无则用默认。"""
        try:
            p = self.plugin_manager.get_plugin("Live2D 看板娘")
            if p is not None:
                s = dict(getattr(p, "settings", {}) or {})
                models = []
                for item in getattr(p, "settings_schema", None) or []:
                    if item.get("key") == "model":
                        models = item.get("options") or []
                return {
                    "enabled": True,
                    "model": s.get("model", ""),
                    "scale": s.get("scale", 100),
                    "pos": s.get("pos", "右下"),
                    "opacity": s.get("opacity", 95),
                    "draggable": s.get("draggable", True),
                    "breath": s.get("breath", True),
                    "models": models,
                }
        except Exception:
            pass
        return {"enabled": True, "model": "", "scale": 100, "pos": "右下",
                "opacity": 95, "draggable": True, "breath": True, "models": []}

    def _trpg_state(self):
        """跑团会话态（供前端渲染跑团提示条）。active 期间显示；否则若仍有锁定则提示可解除。"""
        try:
            p = self.plugin_manager.get_plugin("跑团模式")
            if p is not None:
                return {
                    "active": bool(getattr(p, "active", False)),
                    "gm": getattr(p, "gm", "") or "",
                    "pcs": list(getattr(p, "pcs", []) or []),
                    "turn": getattr(p, "turn", "") or "",
                    "round": getattr(p, "round", 0) or 0,
                    "locked": sorted(self._trpg_locked_names()),
                }
        except Exception:
            pass
        return {"active": False, "gm": "", "pcs": [], "turn": "", "round": 0,
                "locked": sorted(self._trpg_locked_names())}

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

    def _judge_endpoint(self, text):
        """价值判定：给端点回复打 0~1。

        优先用【你自己训出来的排序器】——它的权重是从你的偏好里拟合的，
        比手搓的那套更懂你要什么；没有模型时退回 rubric（模型判定）。
        两者都没有就返回 None，前瞻退回纯启发式。
        """
        # ① 训好的排序器（纯本地，零 API 调用 —— 这也是它比 rubric 便宜的地方）
        if (self.config.get("ranker") or {}).get("on"):
            try:
                import ranker
                m = ranker.load(self._ranker_path())
                if m:
                    chain = self.core.get_current_chain()
                    parent = ""
                    for x in reversed(chain):
                        if x.get("role") == "assistant":
                            parent = str(x.get("content") or "")
                            break
                    s = ranker.score(m.get("w"), text, parent, [], 
                                     self._drift_keys(), self._case_text())
                    if s is not None:
                        return s
            except Exception:
                pass
        # ② 退回 rubric（要一次模型调用）
        crit = self._rubric()
        if not crit:
            return None
        try:
            import rubric as _rb
        except Exception:
            return None
        core = self.core

        def _complete(msgs):
            txt, _u = core._stream_create(list(msgs), None)
            return txt or ""

        r = _rb.judge(_complete, crit, self.core.get_current_chain(), text)
        return r.get("score")

    def _speculate(self, messages):
        """投机器：拿到本轮完整载荷，先往前生成几条路，挑端点最正的交给用户。

        返回 None 表示不干预（走原来的单路生成）。
        跑在 _fetch_response 的工作线程里，不阻塞界面。
        """
        cfg = self.config.get("lookahead") or {}
        if not cfg.get("on"):
            return None
        keys = self._drift_keys()
        if not keys:
            return None                      # 没目标就不前瞻（否则等于瞎挑）
        try:
            import lookahead
        except Exception:
            return None
        core = self.core

        def _complete(msgs):
            txt, _usage = core._stream_create(list(msgs), None)
            return txt or ""

        try:
            res = lookahead.expand(
                _complete, list(messages),
                branches=int(cfg.get("branches") or lookahead.DEF_BRANCHES),
                depth=int(cfg.get("depth") or lookahead.DEF_DEPTH),
                keys=keys, case_text=self._case_text(),
                cap=int(cfg.get("cap") or lookahead.COST_CAP),
                judge_fn=self._judge_endpoint
                if (self._rubric() or (self.config.get("ranker") or {}).get("on"))
                else None)
        except Exception as e:
            self._append_sys("⚠️ 前瞻展开异常，已按原路继续：" + str(e)[:120], kind="warn")
            return None
        if not res.get("ok"):
            return None
        try:
            self._append_sys("🧭 " + lookahead.describe(res).replace("\n", "；"))
        except Exception:
            pass
        return res.get("first")

    def _sync_speculator(self):
        """按配置挂/摘投机器。挂在 core 上，因为载荷是在 core 里组装的。"""
        cfg = self.config.get("lookahead") or {}
        self.core.speculator = self._speculate if cfg.get("on") else None
        return bool(cfg.get("on"))

    def _ranker_path(self):
        return os.path.join(self.base_dir, "ranker.json")

    def _do_import_card(self, path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return {"ok": False, "err": "读取失败：" + str(e)}
        low = path.lower()
        if low.endswith(".png") or low.endswith(".webp"):
            data = card_compat.png_extract_card(raw)
            if data is None:
                return {"ok": False, "err": "这张图片里没有找到角色卡（chara/ccv3 块）"}
        else:
            try:
                data = json.loads(raw.decode("utf-8-sig"))
            except Exception as e:
                return {"ok": False, "err": "JSON 解析失败：" + str(e)}
        # 类型校验：拒绝把「聊天树快照」当角色卡导入（{kind:dick_tree} 或 裸 {ts,tree}）。
        # 这是"导入存档 vs 跑团"最容易串的槽位：快照里没有 system_prompt/name，绝不是角色卡。
        if isinstance(data, dict):
            _tree_like = (data.get("kind") == "dick_tree") or (
                isinstance(data.get("tree"), dict) and not data.get("system_prompt") and not data.get("name"))
            if _tree_like:
                return {"ok": False, "err": "这是聊天树快照，不是角色卡（请导入角色卡 .json/.png/.webp）"}
        conv = card_compat.to_dick(data)
        if not conv:
            return {"ok": False, "err": "无法识别的角色卡格式（需要 v1/v2/v3 或 DICK 格式）"}
        name = conv["name"]
        base_name = name
        i = 2
        while any(r["name"] == name for r in self.roles):
            name = base_name + "_" + str(i)
            i += 1
        fn = self._safe_name(name) + ".json"
        saved = {"kind": "dick_card", "name": name, "system_prompt": conv["system_prompt"]}
        if isinstance(conv.get("card_data"), dict):
            saved["card_data"] = conv["card_data"]
        # 完全适配：结构化字段拆分（可编辑）+ 备用开场白
        if isinstance(conv.get("fields"), dict) and conv["fields"]:
            for k, v in conv["fields"].items():
                saved[k] = v
        if conv.get("alternate_greetings"):
            saved["alternate_greetings"] = conv["alternate_greetings"]
        save_guard.atomic_write_json(os.path.join(self.save_dir, fn), saved)
        self.roles.append({"name": name, "file": fn, "prompt": conv["system_prompt"], "data": saved})
        if low.endswith((".png", ".webp")):
            try:
                avdir = os.path.join(self.save_dir, "avatars")
                os.makedirs(avdir, exist_ok=True)
                ext = "webp" if low.endswith(".webp") else "png"
                with open(os.path.join(avdir, self._safe_name(name) + "." + ext), "wb") as f:
                    f.write(raw)
            except Exception:
                pass
        # 完全适配：酒馆 v2 内嵌世界书（extensions.world）→ DICK 世界卡
        world_note = ""
        entries = conv.get("world_entries") or []
        if entries:
            try:
                wn = name + " 的世界书"
                found = next((w for w in self.worlds if w.get("name") == wn), None)
                if found:
                    merged = found.get("entries") or []
                    existing_ids = {str(e.get("id")) for e in merged}
                    for e in entries:
                        if str(e.get("id")) not in existing_ids:
                            merged.append(e)
                    found["entries"] = merged
                    save_guard.atomic_write_json(
                        os.path.join(self.world_dir, self._safe_name(wn) + ".json"), found)
                else:
                    wdata = {"name": wn,
                             "description": "从角色卡「" + name + "」导入的酒馆世界书",
                             "rules": [], "entries": entries, "params": {}}
                    save_guard.atomic_write_json(
                        os.path.join(self.world_dir, self._safe_name(wn) + ".json"), wdata)
                    self.worlds.append(wdata)
                world_note = "，世界书 " + str(len(entries)) + " 条 → 世界卡「" + wn + "」"
            except Exception as e:
                print(f"[导入] 世界书写入失败: {e}")
        return {"ok": True, "name": name, "note": world_note}

    def _do_export_card(self, name, fmt, path):
        role = next((r for r in self.roles if r["name"] == name), None)
        if not role:
            return {"ok": False, "err": "角色不存在"}
        # 关联世界卡（`<角色名> 的世界书`）→ 导出时写回酒馆 extensions.world（无损反向）
        world_entries = []
        try:
            wn = name + " 的世界书"
            w = next((x for x in self.worlds if x.get("name") == wn), None)
            if w:
                world_entries = w.get("entries") or []
        except Exception:
            pass
        card = card_compat.dick_to_v2(name, role["prompt"],
                                      (role.get("data") or {}).get("card_data"),
                                      world_entries=world_entries)
        try:
            if fmt == "json":
                save_guard.atomic_write_json(path, card)
            else:
                png = None
                avdir = os.path.join(self.save_dir, "avatars")
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    p = os.path.join(avdir, self._safe_name(name) + ext)
                    if os.path.exists(p):
                        with open(p, "rb") as f:
                            png = f.read()
                        break
                if png is None:
                    png = card_compat.placeholder_png(name)
                with open(path, "wb") as f:
                    f.write(card_compat.png_embed_card(png, card))
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)}
        return {"ok": True}

    def _norm_entries(self, entries_json):
        """规范化世界书条目列表（字段齐全、类型安全）"""
        try:
            raw = json.loads(entries_json) if isinstance(entries_json, str) else (entries_json or [])
        except Exception:
            raw = []
        if not isinstance(raw, list):
            raw = []

        def num(v, d):
            try:
                return float(v)
            except (TypeError, ValueError):
                return d

        entries = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            keywords = e.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.replace("，", ",").split(",") if k.strip()]
            keywords = [str(k).strip() for k in keywords if str(k).strip()]
            content = str(e.get("content", "")).strip()
            if not content:
                continue
            entries.append({
                "id": str(e.get("id") or ""),
                "keywords": keywords,
                "content": content,
                "match": str(e.get("match") or "any").lower(),
                "weight": num(e.get("weight"), 100),
                "probability": num(e.get("probability"), 100),
                "depth": int(num(e.get("depth"), 1)),
                "enabled": bool(e.get("enabled", True)),
                "constant": bool(e.get("constant", False)),
            })
        return entries

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

    def _reload_roles(self):
        """从磁盘重建角色列表（保留选中项）"""
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


    def _reload_worlds(self):
        """从磁盘重建世界列表（保留选中项）"""
        self.worlds = []
        try:
            for fn in sorted(os.listdir(self.world_dir)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.world_dir, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("name"):
                        self.worlds.append(data)
                except Exception:
                    continue
        except Exception:
            pass
        self.selected_worlds = [n for n in self.selected_worlds if any(w.get("name") == n for w in self.worlds)]

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

    @staticmethod
    def _wire_sprites_to_speakers(self, name):
        """把包内立绘按角色名（或顺序）自动挂到还没立绘的台词上。返回挂接次数。"""
        pkg = self._codex_pkg_path(name)
        jp = os.path.join(pkg, "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0
        sdir = os.path.join(pkg, "sprites")
        allsp = []
        if os.path.isdir(sdir):
            try:
                allsp = sorted(f for f in os.listdir(sdir)
                               if os.path.isfile(os.path.join(sdir, f)))
            except Exception:
                pass
        if not allsp:
            return 0

        def match_sprite(key):
            if not key:
                return None
            for f in allsp:
                stem = os.path.splitext(f)[0]
                if key in stem or stem in key:
                    return f
            return None

        # 收集角色名（首次出现顺序）
        speakers = []
        for sc in data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            for ln in sc.get("lines") or []:
                if isinstance(ln, dict) and ln.get("speaker"):
                    sp = str(ln["speaker"]).strip()
                    if sp and sp not in speakers:
                        speakers.append(sp)
        speaker_sprite = {}
        used = set()
        for sp in speakers:
            m = match_sprite(sp)
            if m and m not in used:
                speaker_sprite[sp] = m
                used.add(m)
            else:
                for f in allsp:
                    if f not in used:
                        speaker_sprite[sp] = f
                        used.add(f)
                        break
        wired = 0
        for sc in data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            for ln in sc.get("lines") or []:
                if not isinstance(ln, dict):
                    continue
                if ln.get("speaker") and not ln.get("sprite"):
                    sp = str(ln["speaker"]).strip()
                    if sp in speaker_sprite and speaker_sprite[sp]:
                        ln["sprite"] = "sprites/" + speaker_sprite[sp]
                        wired += 1
        try:
            save_guard.atomic_write_json(jp, data)
        except Exception:
            pass
        return wired

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

    def _offline_plan(self):
        """算一份离线推进方案（不修改任何状态）"""
        import offline_advance
        import time_scale
        try:
            tree = self.core.get_all_nodes_data()
        except Exception:
            tree = None
        try:
            scale = float(time_scale.load())
        except Exception:
            scale = 1.0
        mech_cfg = getattr(self.core, "_mech_config", None)
        try:
            mech_state = self.core.mechanism_snapshot()
        except Exception:
            mech_state = None
        dismissed = (self.config.get("offline_dismissed") or {}).get(self._offline_key())
        try:
            return offline_advance.plan(tree, mech_cfg, mech_state, scale=scale,
                                        dismissed_ts=dismissed)
        except Exception as e:
            return {"ok": False, "skipped": "离线推进计算失败：" + str(e)[:120]}

    def _persist_offline_undo(self, undo):
        """把 undo 记录暂存起来，供 api_offline_undo 撤销（一次会话内有效）"""
        try:
            self._offline_undo = undo
        except Exception:
            pass

    def _maybe_auto_turn(self, rounds):
        """群聊自动接话：当前回复后由其他角色接力发言（最多 rounds 轮）。
        选角策略 = 公平轮换（防饿死） + 内容相关性 + 小概率意外，并尊重 @角色名 显式指定。
        目标：让每个角色都被轮到、且人设切换发生在"该他说话的时候"，像真人群聊。"""
        if rounds <= 0 or not self.auto_turn or len(self.selected_roles) < 2 or self.busy:
            return
        roster = [r["name"] for r in self.roles if r["name"] in self.selected_roles]
        if not roster:
            return
        last = getattr(self.core, "last_speaker", None)

        # --- 0) 显式指定优先：最后一句用户文本若含 @角色名，直接让他接话 ---
        last_user = str(getattr(self, "_last_user", "") or "")
        explicit = None
        for nm in roster:
            if nm and ("@" + nm) in last_user:
                explicit = nm
                break
        if explicit:
            self._run_auto_turn(explicit, rounds)
            return

        candidates = [n for n in roster if n != last] or roster[:]

        # --- 1) 公平权重：越久没发言，权重越高（用最近链上各角色的发言次数） ---
        speak = {nm: 0 for nm in roster}
        try:
            for m in self.core.tree.get_current_chain():
                sp = (m.get("metadata") or {}).get("speaker")
                if sp in speak:
                    speak[sp] += 1
        except Exception:
            pass
        # 最近几轮里每被点到一次就记一笔；没点到的候选记 0 → 权重更大。
        # 反向：发言少的候选更可能被挑中，避免双人死循环/饿死第三人。

        # --- 2) 相关性：谁跟最后一句话题有关谁更可能接话（CJK 用字符 n-gram，无需分词） ---
        def _ngrams(s, n):
            s = re.sub(r"\s+", "", str(s))
            return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}
        def relevance(name):
            r = next((x for x in self.roles if x["name"] == name), None)
            if not r:
                return 0.0
            f = r.get("fields") or {}
            grain = " ".join(str(f.get(k) or "") for k in
                             ("personality", "speech", "background", "appearance", "notes"))
            # 用 2~4 字 shingles 取"人设主题"与"最后一句"的重叠，表征"这人跟话题有关"
            profile = _ngrams(grain, 2) | _ngrams(grain, 3) | _ngrams(grain, 4)
            msg = _ngrams(last_user, 2) | _ngrams(last_user, 3)
            overlap = msg & profile
            # 只计真正"有信息量的" shingle（含标点/常见字的噪声剔除）
            info = [g for g in overlap if any('\u4e00' <= c <= '\u9fff' for c in g)
                    and not re.search(r"[\s，。！？、的了是在我你他她这那]", g)]
            return min(len(info), 4) / 4.0

        # 从未满 rounds 的权重里加权：公平权重 = 1/(1+发言次数)；相关性加成；意外项减免。
        scorer = []
        for nm in candidates:
            fair = 1.0 / (1.0 + speak.get(nm, 0))
            rel = relevance(nm)
            score = 2.0 * fair + 1.6 * rel
            scorer.append((score, nm))
        scorer.sort(key=lambda pair: -pair[0])
        # 加权随机：按分数占比挑选（分数越高越可能，但也给低分机会）→ 更像真人
        total = sum(p[0] for p in scorer) or 1.0
        r = random.random() * total
        acc = 0.0
        chosen = scorer[0][1]
        for sc, nm in scorer:
            acc += sc
            if r <= acc:
                chosen = nm
                break

        # --- 3) 小概率意外：真人会冷场/抢话/临时改主意（尊重显式指定已排除） ---
        if random.random() < 0.12 and len(candidates) > 1:
            chosen = random.choice(candidates)

        self._run_auto_turn(chosen, rounds)

    def _run_auto_turn(self, speaker, rounds):
        """为指定角色启动一次自动接话（保持 busy/streaming 状态，延迟等 fetch 复位）。"""
        if speaker not in [r["name"] for r in self.roles]:
            return
        self.busy = True
        self.streaming = ""

        def go():
            try:
                self.core.send_auto_turn(
                    speaker,
                    on_response=lambda reply, usage: self._auto_turn_done(reply, usage, rounds),
                    on_error=lambda err: self._auto_turn_fail())
            except Exception:
                self._auto_turn_fail()

        # 延迟启动：等上一轮 fetch 的 is_processing 复位，避免被“正在处理中”拦截
        threading.Timer(0.5, go).start()

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
