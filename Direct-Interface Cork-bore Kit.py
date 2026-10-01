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
import i18n
import card_compat
import save_guard
import secret_store
import codex_core
from DICK_core import ChatCore
from plugin_manager import PluginManager

BASE_DIR = app_paths.get_base_dir()

# 内置代理通道（中转）：固定地址 → Worker → 隧道 → 本地 net.py → 真实厂商
BUILTIN_RELAY = "https://dick-workshop.seiki342008.workers.dev"

# ---------- 角色卡结构化字段 / 世界卡参数（精细化创作） ----------
ROLE_FIELDS = [
    ("appearance", "外貌"),
    ("personality", "性格"),
    ("background", "过去经历"),
    ("speech", "说话方式"),
    ("first_mes", "开场白"),
    ("mes_example", "对话示例"),
    ("notes", "备注"),
]

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


def assemble_role_prompt(name, fields, legacy):
    """由结构化字段拼装系统提示：旧版完整设定保留在前，分节字段追加在后"""
    parts = []
    legacy = (legacy or "").strip()
    if legacy:
        parts.append(legacy)
    sections = []
    for key, label in ROLE_FIELDS:
        # 开场白不进系统提示。它是「这一场的起点场景」，由 _start_opening() 交给模型
        # 演出第一幕，不进提示词当设定 —— 同一段文字喂两遍会让模型复述它。
        if key == "first_mes":
            continue
        v = fields.get(key) or ""
        if isinstance(v, list):
            v = "、".join(str(x) for x in v if str(x).strip())
        v = str(v).strip()
        if v:
            sections.append("【" + label + "】" + chr(10) + v)
    if sections:
        if parts:
            parts.append(chr(10).join(sections))
        else:
            parts.append("你现在的身份是：" + (name or "未命名") + "。" + chr(10) + chr(10) + chr(10).join(sections))
    _reality = ("【角色卡面·角色塑造】" + chr(10) +
                "你是一个有血有肉的活人，不是一个只会推进剧情的AI。每句话都要像真人说出来：" + chr(10) +
                "1. 生活细节：自然带出你的日常（刚刚在做什么、周围环境、习惯的小动作），让对话有生活气息，不要干巴巴。" + chr(10) +
                "2. 说话方式：严格贴合人设口吻（语速、语气、口头禅、句式），说人话、有口语感，绝不要书面腔、官方腔。" + chr(10) +
                "3. 情绪与反应：有真实的情感起伏，会笑、会叹气、会停顿、会犹豫；对玩家的每个反应都合乎你的人格。" + chr(10) +
                "4. 不要急着推进剧情，先像个人一样自然地回应；故事由互动推动，不是由你念稿推动。")
    parts.append(_reality)
    return chr(10) + chr(10).join(parts) if len(parts) > 1 else (parts[0] if parts else "")


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
PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek 官方", "free": False,
     "base_url": "https://api.deepseek.com",
     "models": ["deepseek-flash", "deepseek-chat", "deepseek-reasoner",
                "deepseek-v4-flash-vision-exp"],
     "buy_url": "https://platform.deepseek.com/"},
    {"id": "ovh", "name": "OVH 免费链（免 Key）", "free": True,
     "base_url": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
     "models": ["Qwen3.5-397B-A17B", "Qwen3.6-27B", "Qwen2.5-VL-72B-Instruct",
                "Mistral-Small-3.2-24B-Instruct-2506", "Llama-3.3-70B-Instruct",
                "DeepSeek-R1-Distill-Llama-70B", "Qwen3.5-9B", "Mistral-7B-Instruct-v0.3"],
     "buy_url": "https://endpoints.ai.cloud.ovh.net/"},
    {"id": "alibaba", "name": "阿里云百炼（通义千问）", "free": False,
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long", "qwen-flash",
                "qwen3-235b-a22b", "qwen3-32b", "qwen3-30b-a3b", "qwen3-14b", "qwen3-8b",
                "qwen2.5-72b-instruct", "qwen2.5-coder-32b-instruct",
                "qwen-vl-max", "qwen-vl-plus"],
     "buy_url": "https://bailian.console.aliyun.com/"},
    {"id": "zhipu", "name": "智谱 AI（GLM）", "free": False,
     "base_url": "https://open.bigmodel.cn/api/paas/v4",
     "models": ["glm-4.6", "glm-4.5-air", "glm-4-plus", "glm-4-air",
                "glm-4-flash", "glm-4-long", "glm-4v-plus", "glm-4.5v"],
     "buy_url": "https://open.bigmodel.cn/"},
    {"id": "siliconflow", "name": "硅基流动 SiliconFlow", "free": False,
     "base_url": "https://api.siliconflow.cn/v1",
     "models": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3.2-Exp", "deepseek-ai/DeepSeek-R1",
                "Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen3-14B",
                "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct",
                "Qwen/Qwen2.5-VL-72B-Instruct", "zai-org/GLM-4.5-Air", "moonshotai/Kimi-K2-Instruct"],
     "buy_url": "https://siliconflow.cn/"},
    {"id": "moonshot", "name": "Moonshot Kimi", "free": False,
     "base_url": "https://api.moonshot.cn/v1",
     "models": ["kimi-latest", "kimi-k2-0711-preview", "kimi-k2-turbo-preview", "kimi-thinking-preview",
                "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
     "buy_url": "https://platform.moonshot.cn/"},
    {"id": "volcengine", "name": "火山方舟（豆包）", "free": False,
     "base_url": "https://ark.cn-beijing.volces.com/api/v3",
     "models": ["doubao-1-5-pro-32k-250115", "doubao-1-5-lite-32k-250115",
                "doubao-pro-32k", "doubao-lite-32k", "doubao-pro-256k",
                "deepseek-v3-241226", "deepseek-r1-250120"],
     "buy_url": "https://console.volcengine.com/ark"},
    {"id": "baidu", "name": "百度千帆（文心）", "free": False,
     "base_url": "https://qianfan.baidubce.com/v2",
     "models": ["ernie-4.0-turbo-8k", "ernie-4.0-8k", "ernie-4.5-8k-preview",
                "ernie-3.5-8k", "ernie-speed-8k", "ernie-lite-8k"],
     "buy_url": "https://console.bce.baidu.com/qianfan"},
    {"id": "minimax", "name": "MiniMax", "free": False,
     "base_url": "https://api.minimax.chat/v1",
     "models": ["MiniMax-Text-01", "abab6.5s-chat", "abab6.5g-chat"],
     "buy_url": "https://platform.minimaxi.com"},
    {"id": "stepfun", "name": "阶跃星辰 StepFun", "free": False,
     "base_url": "https://api.stepfun.com/v1",
     "models": ["step-2-16k", "step-1-8k", "step-1-32k", "step-1-128k", "step-1v-8k"],
     "buy_url": "https://platform.stepfun.com"},
    {"id": "openai", "name": "OpenAI", "free": False,
     "base_url": "https://api.openai.com/v1",
     "models": ["gpt-5.2", "gpt-5", "gpt-5-mini", "gpt-5-nano", "o5", "o5-mini",
                "gpt-4.1", "gpt-4.1-mini"],
     "buy_url": "https://platform.openai.com/"},
    {"id": "anthropic", "name": "Anthropic Claude", "free": False,
     "base_url": "https://api.anthropic.com/v1",
     "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5",
                "claude-opus-4-8-latest", "claude-sonnet-4-6-latest", "claude-haiku-4-5-latest"],
     "buy_url": "https://console.anthropic.com/"},
    {"id": "gemini", "name": "Google Gemini", "free": False,
     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "models": ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-pro", "gemini-3.0-flash",
                "gemini-2.5-pro", "gemini-2.5-flash"],
     "buy_url": "https://aistudio.google.com/"},
    {"id": "ollama", "name": "Ollama 本地（免费）", "free": True,
     "base_url": "http://localhost:11434/v1",
     "models": ["qwen3:32b", "qwen3:14b", "qwen3:8b", "qwen2.5:14b",
                "llama3.3:70b", "llama3.1:8b", "deepseek-r1:32b", "deepseek-r1:14b",
                "glm4:9b", "phi4:14b", "gemma3:12b", "mistral:7b"],
     "buy_url": "https://ollama.com/"},
]

# 指令模板：各模型家族默认停止序列（设置里可覆盖；预设 stop_sequences 次之）
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
    for name in ("prompt_presets", "personas", "worlds", "saves"):
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
    cfg_src = os.path.join(bundled, "config.json")
    cfg_dst = os.path.join(base_dir, "config.json")
    if os.path.isfile(cfg_src) and not os.path.exists(cfg_dst):
        try:
            shutil.copy2(cfg_src, cfg_dst)
        except OSError:
            pass


class HtmlApp:
    # 已并入核心（底层）的 UI 插件：不再作为可开关插件出现，也不可被禁用
    CORE_UI_PLUGINS = ("现代界面", "Live2D 看板娘")

    def __init__(self):
        # 运行时可重定向：优先 app_paths.get_base_dir()（测试/自定义数据目录可直接
        # monkeypatch），退回模块级 BASE_DIR。避免历史测试改 BASE_DIR 不生效的问题。
        self.base_dir = getattr(app_paths, "get_base_dir", lambda: BASE_DIR)()
        _seed_defaults(self.base_dir)
        self.save_dir = os.path.join(self.base_dir, "saves")
        self.world_dir = os.path.join(self.base_dir, "worlds")
        self.preset_dir = os.path.join(self.base_dir, "prompt_presets")
        self.codex_dir = os.path.join(self.base_dir, "codex")
        self.config_file = os.path.join(self.base_dir, "config.json")
        for d in (self.save_dir, self.world_dir, self.preset_dir, self.codex_dir):
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

        lang = self.config.get("language") or ("en" if i18n.detect_english_system() else "zh")
        i18n.set_lang(lang)
        self.language = lang

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
        self.ollama_online = False   # 本地 Ollama 是否可用（后台探测）
        self.codex_auto_open = None  # 双击 .codex 文件启动时，待自动打开的包名
        self.codex_volume = 100      # CODEX 播放器音量 0-100
        threading.Thread(target=self._detect_ollama, daemon=True).start()

        self._load_presets()
        self._load_roles()
        self._load_worlds()
        self.current_world = self.config.get("current_world") or ""
        self.core.world_max_entries = int(self.config.get("world_max_entries") or 3)
        self._append_sys(i18n.t("welcome1", "👋 欢迎使用 Direct-Interface Cork-bore Kit v2.0！"))
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

    def _vision_describe(self, image_b64, mime):
        """看图描述：DICK 的眼睛 = DeepSeek-V4-Flash-Vision-Exp（DSFVE）。
        只要配了 DeepSeek key 就固定用它看图（与主对话模型无关），失败才回落免费链。"""
        import requests
        proxy = self.config.get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        ds_key = (self.config.get("api_key") or "").strip()
        ds_base = (self.config.get("base_url") or "https://api.deepseek.com").strip()
        # 独立视觉模型 ID（DSFVE），不依赖主模型
        vision_model = "deepseek-v4-flash-vision-exp"
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
                r = requests.post(ds_base.rstrip("/") + "/chat/completions",
                                  json=body,
                                  headers={"Content-Type": "application/json",
                                           "Authorization": "Bearer " + ds_key},
                                  timeout=90, proxies=proxies)
                if r.status_code < 400:
                    content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
            except Exception:
                pass
        # 回落：免费视觉链
        return _vision_describe(image_b64, mime, proxies=proxies)

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

    def _save_tree(self):
        """把当前聊天树写回第一个选中角色的文件（保留 name/system_prompt/card_data）"""
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
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), data)
                except Exception:
                    pass
                # 同步内存快照：勾选/取消勾选切换时 _activate_core 从
                # r["data"]["history_tree"] 取记录，不同步会导致同一会话内
                # 重新勾选只恢复到旧快照（新建角色的记录甚至取不回）
                r["data"] = data
                # 进度同步：把聊天树推送到工坊服务器（后台线程，不阻塞保存）
                self._ws_save_upload_async(r["name"], data["history_tree"])
                break

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

    def _choices_plugin(self):
        try:
            if self.plugin_manager:
                return self.plugin_manager.get_plugin("Galgame 选项")
        except Exception:
            pass
        return None

    def _choices_state(self):
        p = self._choices_plugin()
        if not p or not p.enabled:
            return {"items": [], "loading": False, "error": ""}
        try:
            return {"items": list(getattr(p, "choices", None) or []),
                    "loading": bool(getattr(p, "choices_loading", False)),
                    "error": str(getattr(p, "choices_error", "") or "")}
        except Exception:
            return {"items": [], "loading": False, "error": ""}

    def _clear_choices(self):
        p = self._choices_plugin()
        if p:
            try:
                p.clear_choices()
            except Exception:
                pass

    # ---------- js_api ----------
    def api_state(self):
        with self._lock:
            return {
                "lang": self.language,
                "roles": [r["name"] for r in self.roles],
                "role_unlocked": {r["name"]: bool(r.get("unlocked", False)) for r in self.roles},
                "worlds": [w.get("name", "") for w in self.worlds],
                "presets": [p.get("name", "默认") for p in self.presets],
                "selected_roles": list(self.selected_roles),
                "selected_worlds": list(self.selected_worlds),
                "current_world": self.current_world,
                "preset": self.preset_name,
                "persona": self.persona,
                "has_key": bool(self.api_keys.get(self.provider_id) or self.config.get("api_key")),
                "model": self.config.get("model", "deepseek-flash"),
                "base_url": self.config.get("base_url", "https://api.deepseek.com"),
                "providers": PROVIDERS,
                "provider": self.provider_id,
                "proxy": self.config.get("proxy", ""),
                "relay_url": self.config.get("relay_url") or BUILTIN_RELAY,
                "relay_on": bool(getattr(self.core, "relay_on", False)),
                "stop_input": list(self.config.get("stop_sequences") or []),
                "stop_sequences": list(getattr(self.core, "stop_sequences", None) or []),
                "temperature": self.config.get("temperature"),
                "top_p": self.config.get("top_p"),
                "dev_mode": bool(self.config.get("dev_mode", False)),
                "humanize": bool(getattr(self.core, "humanize", True)),
                "style_guard": bool(getattr(self.core, "style_guard", True)),
                "style_guard_long": bool(getattr(self.core, "style_guard_long", False)),
                "welcome_shown": bool(self.config.get("welcome_shown", False)),
                "ollama_online": bool(getattr(self, "ollama_online", False)),
                "api_keys": self.api_keys,
                "image_gen_key": self.config.get("image_gen_key", ""),
                "image_gen_base_url": self.config.get("image_gen_base_url", "https://api.siliconflow.cn/v1"),
                "image_gen_model": self.config.get("image_gen_model", "black-forest-labs/FLUX.1-schnell"),
                "image_gen_backend": self.config.get("image_gen_backend", "auto"),
                # 上次生图的输入（面板打开时自动回填，省得反复重敲提示词）
                "image_gen_last": dict(self.config.get("image_gen_last") or {}),
                "auto_turn": self.auto_turn,
                "font": self.font_size,
                "budget": int(self.config.get("context_budget", 0) or 0),
                "document": self.loaded_document,
                "plugins": [{"name": p.name, "version": p.version, "description": p.description,
                             "enabled": bool(p.enabled),
                             "schema": getattr(p, "settings_schema", None) or [],
                             "settings": dict(getattr(p, "settings", {}) or {})}
                            for p in self.plugin_manager.get_all_plugins()
                            if p.name not in self.CORE_UI_PLUGINS],
                "l2d": self._l2d_state(),
                "chat_wallpaper": os.path.isfile(self._wallpaper_path()),
                "trpg": self._trpg_state(),
                "theme": self.config.get("ui_theme", 0),
                "accent": self.config.get("ui_accent", 0),
                "messages": self.messages,
                "streaming": self.streaming,
                "busy": self.busy,
                "opening_loading": self.opening_loading,
                "tokens": self.total_tokens,
                "epoch": self.render_epoch,
                "choices": self._choices_state(),
                "mechanism": {"config": getattr(self.core, "_mech_config", None),
                              "state": self.core.mechanism_snapshot()},
                "battle": self.core.battle_ui_state(),
                "codex_auto_open": self.codex_auto_open,
            }

    def api_poll(self, last_seq):
        with self._lock:
            items = [m for m in self.messages if m["seq"] > last_seq]
            return {"items": items, "streaming": self.streaming, "busy": self.busy,
                    "opening_loading": self.opening_loading,
                    "tokens": self.total_tokens, "epoch": self.render_epoch,
                    "choices": self._choices_state(),
                    "mechanism": {"config": getattr(self.core, "_mech_config", None),
                                  "state": self.core.mechanism_snapshot()},
                    "battle": self.core.battle_ui_state()}

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

    def api_pick_choice(self, text):
        """Galgame 选项：点击某个选项 = 隐藏 ROLL 出结果 + 以该行动作为玩家输入发言"""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "err": "empty"}
        if self.busy:
            return {"ok": False, "err": "busy"}
        # 选项效果（好感/状态）：从插件当前选项里按文本匹配
        p = self._choices_plugin()
        item = None
        if p:
            try:
                for it in (getattr(p, "choices", None) or []):
                    if isinstance(it, dict) and it.get("text") == text:
                        item = it
                        break
            except Exception:
                pass
        # 隐藏 ROLL：按内置概率表出结果
        effect, kind, note = self._roll_option(item or {"text": text})
        self.core.apply_mechanism_effect(effect)
        if kind == "rare":
            self.core.pending_event = {"id": "_roll_rare", "name": "命运的眷顾",
                                       "prompt": "（稀有事件）这段剧情出现了意想不到的转折，"
                                                 "请自然地演出一个令人惊喜的展开。"}
            if note:
                self._append_sys(note)
        elif kind == "chosen":
            self.core.pending_event = {"id": "_roll_chosen", "name": "天选",
                                       "prompt": "（天选事件）千分之一的天命眷顾发生了！"
                                                 "请演出一个不可思议的、足以载入史册的剧情转折。"}
            if note:
                self._append_sys(note)
        elif kind == "collapse":
            self.core.pending_event = {"id": "_roll_collapse", "name": "坍缩",
                                       "prompt": "（坍缩事件）十万分之一的奇迹坍缩成现实！"
                                                 "战斗数值全部坍缩为 2000。"
                                                 "请演出一个撼动世界观的、堪称神话的剧情展开。"}
            try:
                self.core.collapse_battle_values()
            except Exception:
                pass
            if note:
                self._append_sys(note)
        elif kind in ("crit", "fail") and note:
            self._append_sys(note)
        # 世界线切换（B）：隐藏 ROLL 命中预设世界线时自动跳线（如坍缩→黑化线）
        self._maybe_world_line_on(kind)
        self._clear_choices()
        self._send_text(text, None, None, is_choice=True)
        return {"ok": True}

    def api_cyoa(self):
        """Galgame 选项：手动生成一组剧情选项（不写进聊天记录）"""
        p = self._choices_plugin()
        if not p or not p.enabled:
            return {"ok": False, "err": "插件未启用（⚙️ 设置 → 插件 → Galgame 选项）"}
        ok, msg = p.manual_generate()
        return {"ok": ok, "msg": msg}

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

    def api_battle_move(self, move_id):
        """战斗：玩家出招 → 引擎结算伤害/消耗 → 结算文本作为系统横幅 + 行动作为玩家消息发出（AI 演出）"""
        move_id = (move_id or "").strip()
        if not move_id:
            return {"ok": False, "err": "empty"}
        if self.busy:
            return {"ok": False, "err": "busy"}
        cfg = self.core._battle_config()
        if not cfg:
            return {"ok": False, "err": "当前角色未启用战斗系统"}
        move_name = move_id
        for m in (cfg.get("moves") or []):
            if isinstance(m, dict) and str(m.get("id", "")).strip() == move_id:
                move_name = str(m.get("name") or m.get("id"))
                break
        txt, is_legend = self.core.resolve_battle_move(move_id)
        if txt is None:
            return {"ok": False, "err": "招式不存在"}
        # 天选之人：0.00001% 战斗奇迹
        if is_legend:
            self.core.pending_event = {"id": "_battle_legend", "name": "天选之人",
                                       "prompt": "（传说事件）战斗中发生了十万分之一的奇迹！"
                                                 "请演出一个足以载入史册的惊天转折。"}
            self._append_sys("🌟 天选之人：十万分之一的战斗奇迹被触发了！")
        if txt.startswith("⚠️"):
            self._append_sys(txt)
            return {"ok": True, "msg": txt}
        self._append_sys(txt)
        # 结算结果注入下一轮请求（AI 知道伤害数字，演出受击反应）
        self.core.pending_event = {"id": "_battle_result", "name": "战斗结算",
                                   "prompt": f"（战斗结算）{txt} 请以角色口吻演出受击反应与战况。"}
        self._send_text(f"使用 {move_name}", None, None)
        return {"ok": True, "msg": txt}

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

    def api_quick_replies(self):
        """Quick Reply 列表：全局 quick_replies.json + 当前激活卡片的 card_quick_replies"""
        out = []
        try:
            with open(os.path.join(self.base_dir, "quick_replies.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                out.extend({"label": str(x.get("label") or ""), "text": str(x.get("text") or "")}
                           for x in data if isinstance(x, dict) and x.get("label"))
        except Exception:
            pass
        # 当前卡片自带快捷回复（高级设置）排在最前
        for name in self.selected_roles:
            for r in self.roles:
                if r["name"] == name:
                    adv = (r.get("data") or {}).get("advanced") or {}
                    for q in adv.get("card_quick_replies") or []:
                        if q.get("label"):
                            out.insert(0, {"label": str(q["label"]), "text": str(q.get("text") or "")})
                    break
        return out

    # ---------- 正则管道（ST 风格：清洗/格式化；存储前应用，树状天然一致） ----------
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

    def api_dismiss_welcome(self):
        """标记首次引导已看完（不再弹引导框）"""
        self.config["welcome_shown"] = True
        self._save_config()
        return {"ok": True}

    def api_send(self, text, image_b64=None, mime=None):
        text = (text or "").strip()
        if self.busy:
            return {"ok": False, "err": "busy"}
        if not text and not image_b64:
            return {"ok": False, "err": "empty"}
        if text.startswith("/"):
            travel = self._handle_travel(text)
            if travel:
                self._append_sys(text, kind="user", speaker="你")
                self._append_sys(travel)
                return {"ok": True}
            if text.strip().lower().startswith("/mettertools"):
                # METTERTOOLS：按上限百分比一键填好感（罪恶都市梗；/mettertools 90 = 填到 90%）
                self._append_sys(text, kind="user", speaker="你")
                parts = text.split()
                pct = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
                val = self.core.set_affection_percent(pct)
                if val is None:
                    self._append_sys("⚠️ 当前角色未启用好感度（机制卡 → ❤ 好感度）")
                else:
                    self._append_sys(f"✨ METTERTOOLS！好感度已填至 {pct}% → {val}。")
                return {"ok": True}
            if text.strip() == "/read" or text.startswith("/read "):
                self._append_sys(text, kind="user", speaker="你")
                arg = text[5:].strip() if text.startswith("/read ") else None
                r = self.api_read_document(arg)
                if r.get("ok"):
                    self._append_sys("✅ 已注入文档上下文（可用 /readclear 清除）")
                elif r.get("err") != "cancelled":
                    self._append_sys("⚠️ " + r.get("err", "读取失败"))
                return {"ok": True}
            if text.strip() == "/readclear":
                self._append_sys(text, kind="user", speaker="你")
                self.api_clear_document()
                return {"ok": True}
            result = self.plugin_manager.handle_command(text)
            self._append_sys(text, kind="user", speaker="你")
            self._append_sys(result or i18n.t("unknown_cmd", "未知命令"))
            return {"ok": True}
        # Quick Reply 宏展开：{player} {char} {world} {random:a|b|c}
        text = self._expand_macros(text)
        processed = self.plugin_manager.onMessageSend(text) if hasattr(self.plugin_manager, "onMessageSend") else text
        if processed is None:
            return {"ok": False, "err": "blocked"}
        # 翻译隐藏：显示/存储用原文，发给 AI 用译文（中字日配不露痕迹）
        display_text, send_text = self._split_hidden(processed)
        # 玩家发送新消息（打字或点选项之外的自由输入）后，旧剧情选项作废
        self._clear_choices()
        image = None
        if image_b64:
            image = "data:" + (mime or "image/png") + ";base64," + image_b64
        # 传图补丁：先视觉描述（后台线程）
        if image_b64:
            self.busy = True
            speaker = (self.persona or {}).get("name") or "你"
            node_id = self.core.add_user_message(display_text)  # 树里存原文（翻译隐藏）
            try:
                self.core.tree.nodes[node_id].metadata["speaker"] = speaker
            except Exception:
                pass
            self.node_images[node_id] = image
            self._rebuild_messages()
            threading.Thread(target=self._vision_then_send,
                             args=(node_id, send_text, image_b64, mime), daemon=True).start()  # 发译文给 AI
            return {"ok": True}
        self._send_text(display_text, send_text, None)

        return {"ok": True}

    def _vision_then_send(self, node_id, text, image_b64, mime):
        """发图 = DSFVE 直接看图回答：视觉模型基于图片+用户文本，以角色口吻直接生成回复。
        失败则回落到"描述中转 + 主模型"。"""
        import requests
        proxy = self.config.get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        node = self.core.tree.nodes.get(node_id)
        ds_key = (self.config.get("api_key") or "").strip()
        ds_base = (self.config.get("base_url") or "https://api.deepseek.com").strip()
        vision_model = "deepseek-v4-flash-vision-exp"
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
            self._append_sys(i18n.t("vision_fail", "⚠️ 图片识别失败（免费视觉链被限流或网络问题），请稍后重试"))

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
            self._save_tree()
            self._rebuild_messages()
            self.streaming = ""
            self.busy = False
            for p in self.plugin_manager.get_all_plugins():
                if p.enabled:
                    try:
                        p.on_message_received(getattr(self, "_last_user", ""), clean)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[视觉] 直答落树失败: {e}")
            self._append_sys(direct, kind="ai")
            self._rebuild_messages()
            self.busy = False
            self.streaming = ""

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
            on_error=self._on_error,
        )

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
        self._save_tree()
        self._rebuild_messages()
        self.streaming = ""
        self.busy = False
        if self.auto_turn and len(self.selected_roles) > 1:
            self._maybe_auto_turn(2)
        for p in self.plugin_manager.get_all_plugins():
            if p.enabled:
                try:
                    p.on_message_received(getattr(self, "_last_user", ""), ai_reply)
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
        self._save_tree()
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
                    on_error=self._on_error,
                )
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

    def api_select_roles(self, names_json):
        try:
            names = json.loads(names_json)
            names = [n for n in names if any(r["name"] == n for r in self.roles)]
        except Exception:
            return {"ok": False}
        # 先把当前聊天树写回「旧」的首个选中角色，再切换选择：
        # 否则取消勾选/切换角色时，旧角色的记录会残留在聊天窗口，
        # 甚至误写进新选角色的存档里。
        self._save_tree()
        self.selected_roles = names
        self.config["selected_roles"] = list(names)
        self.config["last_role"] = names[0] if names else ""
        self._save_config()
        # 切换角色 = 新会话：清空系统横幅（欢迎语/命令回显等），界面彻底初始化
        self.sys_msgs = []
        # 进度同步：拉取该角色最新树存档（若比本地新则用服务器版本，实现跨设备续聊）
        if self._ws_sync_enabled() and names:
            self._ws_pull_tree(names[0])
        self._activate_core(reload_tree=True)
        return {"ok": True}

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

    def api_select_worlds(self, names_json):
        try:
            names = json.loads(names_json)
            self.selected_worlds = [n for n in names if any(w.get("name") == n for w in self.worlds)]
        except Exception:
            pass
        self._sync_worlds()
        return {"ok": True}

    def api_travel(self, name):
        """穿梭：把角色移动到指定世界（世界书条目只跟随当前世界）"""
        name = (name or "").strip()
        if not name or name not in self.selected_worlds:
            return {"ok": False, "err": "请先勾选该世界再穿越"}
        self.current_world = name
        self.core.set_current_world(name)
        self.config["current_world"] = name
        self._save_config()
        return {"ok": True, "current": name}

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
        # 指令模板：预设变更后重新应用停止序列（预设可带 stop_sequences）
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

    def api_create_role(self, name, fields_json=None):
        name = (name or "").strip()
        if not name:
            return {"ok": False, "err": "empty"}
        legacy, fields, unlocked, advanced = self._parse_role_input(name, fields_json)
        advanced = self._clean_advanced(advanced)
        prompt = assemble_role_prompt(name, fields, legacy)
        if not prompt:
            return {"ok": False, "err": "empty"}
        fn = self._safe_name(name) + ".json"
        data = {"name": name, "system_prompt": prompt, "legacy": legacy,
                "unlocked": bool(unlocked)}
        for k, v in fields.items():
            if v:
                data[k] = v
        if advanced:
            data["advanced"] = advanced
        save_guard.atomic_write_json(os.path.join(self.save_dir, fn), data)
        self.roles.append({"name": name, "file": fn, "prompt": prompt, "data": data,
                           "fields": fields, "legacy": legacy, "unlocked": bool(unlocked)})
        return {"ok": True}

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

    def api_update_role(self, name, fields_json=None):
        """编辑人物卡（保持文件名/头像/聊天树/卡数据，只更新设定与结构化字段）"""
        if self._is_card_locked(name):
            return {"ok": False, "err": "🎭 会期进行中，该角色卡已锁定（先 /trpg end 解锁）"}
        legacy, fields, unlocked, advanced = self._parse_role_input(name, fields_json)
        advanced = self._clean_advanced(advanced)
        prompt = assemble_role_prompt(name, fields, legacy)
        if not prompt:
            return {"ok": False, "err": "empty"}
        for r in self.roles:
            if r["name"] == name:
                r["prompt"] = prompt
                r["fields"] = fields
                r["legacy"] = legacy
                r["unlocked"] = bool(unlocked)
                data = dict(r.get("data") or {})
                data["name"] = name
                data["system_prompt"] = prompt
                data["legacy"] = legacy
                data["unlocked"] = bool(unlocked)
                for k, v in fields.items():
                    if v:
                        data[k] = v
                    else:
                        data.pop(k, None)
                if advanced:
                    data["advanced"] = advanced
                else:
                    data.pop("advanced", None)
                r["data"] = data
                try:
                    # 覆盖前先留底：清空机制/结局等"破坏性编辑"也能从 backup/ 恢复回
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), data)
                except Exception:
                    pass
                if name in self.selected_roles:
                    self._activate_core(reload_tree=False)
                return {"ok": True}
        return {"ok": False, "err": "not found"}

    def _parse_world_params(self, params_json):
        params = {}
        raw = _parse_fields(params_json)
        for key, _label in WORLD_PARAMS:
            v = str(raw.get(key) or "").strip()
            if v:
                params[key] = v
        return params

    def api_create_world(self, name, description, rules_text, entries_json=None, params_json=None):
        """创建世界卡：rules 每行一条；entries 世界书条目；params 世界参数（科技/超自然/物理等）"""
        name = (name or "").strip()
        if not name or not (description or "").strip():
            return {"ok": False, "err": "empty"}
        rules = [x.strip() for x in (rules_text or "").splitlines() if x.strip()]
        data = {"name": name, "description": (description or "").strip(),
                "rules": rules, "entries": self._norm_entries(entries_json),
                "params": self._parse_world_params(params_json)}
        fn = self._safe_name(name) + ".json"
        save_guard.atomic_write_json(os.path.join(self.world_dir, fn), data)
        self.worlds.append(data)
        if name in self.selected_worlds:
            self.core.set_worlds(self._worlds_for_core())
        return {"ok": True}

    def api_update_world(self, name, description, rules_text, entries_json=None, params_json=None):
        """编辑世界卡（按名定位；entries_json/params_json 为 None 时保留原值）"""
        for w in self.worlds:
            if w.get("name") == name:
                w["description"] = (description or "").strip()
                w["rules"] = [x.strip() for x in (rules_text or "").splitlines() if x.strip()]
                if entries_json is not None:
                    w["entries"] = self._norm_entries(entries_json)
                if params_json is not None:
                    w["params"] = self._parse_world_params(params_json)
                try:
                    fn = self._safe_name(name) + ".json"
                    # 覆盖前留底：破坏性编辑可从 backup/ 恢复
                    save_guard.backup_file(os.path.join(self.world_dir, fn))
                    save_guard.atomic_write_json(os.path.join(self.world_dir, fn), w)
                except Exception:
                    pass
                if name in self.selected_worlds:
                    self.core.set_worlds(self._worlds_for_core())
                return {"ok": True}
        return {"ok": False, "err": "not found"}

    def api_delete_world(self, name):
        for w in self.worlds:
            if w.get("name") == name:
                try:
                    # 删除前先留底到 backup/：误删可从备份捞回
                    save_guard.backup_file(os.path.join(self.world_dir, self._safe_name(name) + ".json"))
                    os.remove(os.path.join(self.world_dir, self._safe_name(name) + ".json"))
                except Exception:
                    pass
        self.worlds = [w for w in self.worlds if w.get("name") != name]
        self.selected_worlds = [n for n in self.selected_worlds if n != name]
        return {"ok": True}

    def api_ai_draft(self, kind, idea):
        """AI 起草：人物卡/世界卡（需已配置 API Key）"""
        idea = (idea or "").strip()
        if not idea:
            return {"ok": False, "err": "empty idea"}
        client = getattr(self.core, "client", None)
        if not client:
            return {"ok": False, "err": "未配置 API Key，请先在设置里填写"}
        fence = chr(96) * 3
        NL = chr(10)
        if kind == "world":
            prompt = ("根据下面的灵感，设计一个世界卡。只输出 JSON（不要多余解释）：" + NL +
                      '{"name": "世界名", "description": "背景描述", "params": {"tech_level": "科技水平", "supernatural": "超自然体系（无则写：无）", "physics": "物理法则（如：与地球相同）", "time_flow": "时间流速", "climate": "气候环境", "geography": "地理格局", "politics": "政治格局", "economy": "经济体系"}, "rules": ["规则1", "规则2", "规则3"]}' + NL +
                      "灵感：" + idea)
        else:
            prompt = ("根据下面的灵感，撰写一张角色卡。只输出 JSON（不要多余解释）：" + NL +
                      '{"name": "角色名", "appearance": "外貌", "personality": "性格（详写）", "background": "过去经历（详写）", "speech": "说话方式（语气/口癖/句式）", "first_mes": "开场白", "mes_example": "对话示例", "notes": "备注"}' + NL +
                      "灵感：" + idea)
        model = self.config.get("model", "deepseek-flash")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=False, timeout=90,
            )
            text = (resp.choices[0].message.content or "").strip()
            if fence in text:
                parts = text.split(fence)
                for p in parts:
                    p = p.strip()
                    if p.startswith("json"):
                        p = p[4:].strip()
                    if p.startswith("{"):
                        text = p
                        break
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
            data = json.loads(text)
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "err": "AI 起草失败：" + str(e)[:200]}

    def api_delete_role(self, name):
        if self._is_card_locked(name):
            return {"ok": False, "err": "🎭 会期进行中，该角色卡已锁定（先 /trpg end 解锁）"}
        was_selected = name in self.selected_roles
        for r in self.roles:
            if r["name"] == name:
                try:
                    # 删除前先留底到 backup/：误删可从备份捞回（"清空有还原"）
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    os.remove(os.path.join(self.save_dir, r["file"]))
                except Exception:
                    pass
        self.roles = [r for r in self.roles if r["name"] != name]
        self.selected_roles = [n for n in self.selected_roles if n != name]
        self.config["selected_roles"] = list(self.selected_roles)
        self.config["last_role"] = self.selected_roles[0] if self.selected_roles else ""
        self._save_config()
        if was_selected:
            self._activate_core(reload_tree=True)
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

    def api_card_saves(self, name):
        """列出某角色卡的存档点（只返回摘要，不返回整棵树）"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        return {"ok": True, "saves": [self._save_summary(s) for s in saves],
                "active_save": data.get("active_save") or None}

    def api_card_save_new(self, name, label):
        """『新存档』：把当前进度固化为一个新的存档点，并设为当前活动存档"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        snap = self._card_snapshot()
        sid = "s-" + uuid.uuid4().hex[:10]
        entry = {"id": sid,
                 "label": (label or "").strip() or "存档 " + str(len(saves) + 1),
                 "created_ts": snap["_tree_ts"], "updated_ts": snap["_tree_ts"],
                 "history_tree": snap["history_tree"], "mechanism_state": snap["mechanism_state"],
                 "_tree_ts": snap["_tree_ts"], "progress": snap["progress"]}
        saves.append(entry)
        data["saves"] = saves
        data["active_save"] = sid
        self._commit_card_data(r, data)
        return {"ok": True, "save": self._save_summary(entry), "active_save": sid}

    def api_card_save(self, name, label, save_id=None):
        """『存档』：把当前进度写入目标存档点；无目标则新建一个（可附新标签）"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        sid = save_id or data.get("active_save")
        snap = self._card_snapshot()
        entry = None
        if sid:
            entry = next((s for s in saves if s.get("id") == sid), None)
            if entry:
                entry["history_tree"] = snap["history_tree"]
                entry["mechanism_state"] = snap["mechanism_state"]
                entry["_tree_ts"] = snap["_tree_ts"]
                entry["updated_ts"] = snap["_tree_ts"]
                entry["progress"] = snap["progress"]
                if label and str(label).strip():
                    entry["label"] = str(label).strip()
            else:
                sid = None
        if not sid:
            sid = "s-" + uuid.uuid4().hex[:10]
            entry = {"id": sid,
                     "label": (label or "").strip() or "存档 " + str(len(saves) + 1),
                     "created_ts": snap["_tree_ts"], "updated_ts": snap["_tree_ts"],
                     "history_tree": snap["history_tree"], "mechanism_state": snap["mechanism_state"],
                     "_tree_ts": snap["_tree_ts"], "progress": snap["progress"]}
            saves.append(entry)
        data["saves"] = saves
        data["active_save"] = sid
        self._commit_card_data(r, data)
        return {"ok": True, "save": self._save_summary(entry), "active_save": sid}

    def api_card_save_load(self, name, save_id):
        """『读档/切换』：把指定存档点还原为当前会话（对话树 + 机制状态 + 进度时间戳）"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        entry = next((s for s in saves if s.get("id") == save_id), None)
        if not entry:
            return {"ok": False, "err": "存档不存在"}
        data["history_tree"] = entry.get("history_tree")
        data["mechanics_state"] = entry.get("mechanism_state")
        data["_tree_ts"] = entry.get("_tree_ts") or data.get("_tree_ts")
        data["active_save"] = save_id
        self._commit_card_data(r, data)
        # 该角色当前被选中且是核心会话角色时，重载 core 以刷新聊天树与机制状态
        if name in self.selected_roles:
            self._activate_core(reload_tree=True)
        return {"ok": True}

    def api_card_save_delete(self, name, save_id):
        """『删除』：移除一个存档点；若删除的是活动存档则清空活动指针"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        saves = [s for s in saves if s.get("id") != save_id]
        data["saves"] = saves
        if data.get("active_save") == save_id:
            data["active_save"] = None
        self._commit_card_data(r, data)
        return {"ok": True}

    def api_card_save_rename(self, name, save_id, label):
        """『重命名』：修改存档点标签"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        entry = next((s for s in saves if s.get("id") == save_id), None)
        if not entry:
            return {"ok": False, "err": "存档不存在"}
        entry["label"] = (label or "").strip() or entry.get("label") or "未命名存档"
        self._commit_card_data(r, data)
        return {"ok": True, "save": self._save_summary(entry)}

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

    def api_clear_chat_wallpaper(self):
        removed = False
        for e in self._WALLPAPER_EXTS:
            q = os.path.join(self.save_dir, "wallpaper" + e)
            if os.path.exists(q):
                try:
                    os.remove(q)
                    removed = True
                except Exception:
                    pass
        return {"ok": True, "removed": removed}

    # ---------- Live2D 看板娘（核心态） ----------
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

    def api_trpg_end(self):
        """退出跑团（核心）：结束会话、解除角色卡锁定、复位轮次与行动者。"""
        try:
            p = self.plugin_manager.get_plugin("跑团模式")
            if p is not None and hasattr(p, "end_session"):
                msg = p.end_session()
                return {"ok": True, "msg": msg}
            pth = os.path.join(self.save_dir, ".trpg_lock.json")
            if os.path.exists(pth):
                try:
                    os.remove(pth)
                except Exception:
                    pass
            return {"ok": True, "msg": "🏁 已退出跑团模式"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    # ---------- 滑条 / 编辑 / 分支 ----------
    # ---------- 漂移核查（三态 + 延迟定案） ----------
    def _drift_keys(self):
        """取当前角色的「本场关键词」（这场戏在讲什么）。

        为什么要作者填：实测下来，泛泛的词面重叠分不出「跑题」和「措辞巧合」，
        只有明确的目标词才是可靠信号。自动抽词在没有分词的情况下抽不准，
        所以这里让作者给 —— 不填就等于不做漂移判定（不会乱定罪）。
        """
        name = (self.selected_roles or [None])[0]
        allk = self.config.get("drift_keys") or {}
        return list(allk.get(name or "", []) or [])

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

    def api_tree_drift(self, dry_run=True):
        """核查当前主干有没有漂移。三态：cleared / suspected / drifted。

        默认只写状态、**不删任何东西** —— 判定这事儿先让用户看着跑一阵。
        确认漂移的节点可以通过 api_tree_prune 之外的路径手动处理，
        不在这里自动剪，因为"漂移"有时候正是用户想要的走向。
        """
        try:
            import tree_weight
        except Exception as e:
            return {"ok": False, "err": "缺少 tree_weight 模块：" + str(e)[:120]}
        keys = self._drift_keys()
        if not keys:
            return {"ok": False, "err": "还没设本场关键词。点「🔍 漂移核查」上面的输入框填几个词，"
                                        "例如：册子、扉页、铅笔字",
                    "need_keys": True}
        # 案卷 = 世界卡 + 角色卡 + 开局那几轮（"现实"的文本化）
        case_parts = []
        for r in (self.roles or []):
            if r.get("name") in (self.selected_roles or []):
                case_parts.append(str(r.get("prompt") or ""))
        for w in (self.worlds or []):
            if w.get("name") in (self.selected_worlds or []):
                case_parts.append(str(w.get("description") or ""))
        case_text = "\n".join(case_parts)
        try:
            r = tree_weight.audit_tree(self.core.tree, keys, case_text, write=True)
            self._save_tree()
            return r
        except Exception as e:
            return {"ok": False, "err": "核查失败：" + str(e)[:200]}

    # ---------- 前瞻展开（树壳 → 树状AI 的那一步） ----------
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

    def api_export_preferences(self):
        """把树里已经形成的偏好对导出成 JSONL（只读，不改任何东西）。

        为什么现在就要导：偏好信号只在产生的那一刻存在。你滑过去了，
        "他拒绝了哪条"就沉进树里 —— 不导出就永远拿不到，而且它只增不减。
        顺带给出【启发式与你实际选择的一致率】，那是"能不能用这个价值函数做前瞻"的实证依据。
        """
        try:
            import preference_export
        except Exception as e:
            return {"ok": False, "err": "缺少 preference_export 模块：" + str(e)[:120]}
        try:
            r = preference_export.scan_dir(self.save_dir)
        except Exception as e:
            return {"ok": False, "err": "扫描存档失败：" + str(e)[:200]}
        recs = r.get("records") or []
        if not recs:
            return {"ok": True, "samples": 0, "by_role": {},
                    "msg": "还没有可用的偏好样本。样本来自「同一个问题下生成过多条候选」——"
                           "多用几次重 roll（♻ 重新生成）就会有。"}
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self._pick_save_path("DICK_偏好数据_" + ts + ".jsonl", ("JSONL (*.jsonl)",))
        if not out.lower().endswith(".jsonl"):
            out += ".jsonl"
        try:
            n = preference_export.export_jsonl(recs, out)
        except Exception as e:
            return {"ok": False, "err": "写入失败：" + str(e)[:160]}
        s = r.get("sum") or {}
        return {"ok": True, "file": out, "name": os.path.basename(out), "written": n,
                "by_role": r.get("by_role") or {}, "stats": s,
                "msg": "已导出 %d 条偏好对（来自 %d 个角色）" %
                       (n, len(r.get("by_role") or {}))}

    # ---------- 平民化训练（调试面板 · 非开发者可用） ----------
    def _ranker_path(self):
        return os.path.join(self.base_dir, "ranker.json")

    def api_event_progress(self):
        """事件进度面板：每个事件现在是什么状态（已触发/冷却中/差多少好感/可以触发）。

        命名约定：pywebview 暴露给前端的方法一律以 api_ 开头，
        前端写 pywebview.api.event_progress()（前缀由桥自动加）。
        所以这里必须是 api_event_progress，两边去掉前缀后同名才算接上。
        （test_js_api_binding 会抓这个名字不一致，静默失效很难查。）
        """
        cfg = None
        try:
            cfg = self.core._mech_config
        except Exception:
            cfg = None
        try:
            items = self.core.event_progress(cfg)
        except Exception as e:
            return {"ok": False, "err": "读事件进度失败：" + str(e)[:160]}
        st = self.core.mechanism_state or {}
        cfgs = cfg if isinstance(cfg, dict) else {}
        aff_cfg = cfgs.get("affection") if isinstance(cfgs.get("affection"), dict) else None
        return {
            "ok": True,
            "enabled": bool(cfgs.get("events")),
            "affection": st.get("affection"),
            "aff_max": (int(aff_cfg.get("max", 100) or 100) if aff_cfg else None),
            "turn": st.get("_turn", 0),
            "items": items,
            "fired": sum(1 for x in items if x.get("fired")),
            "total": len(items),
        }

    def api_memory_debug(self):
        """记忆调试：看当前历史每条的记忆清晰度、年龄、隐藏衰减率、还剩多少寿命。

        为什么必须有这个：遗忘被刻意设计成【不可建模】的（每个节点一个隐藏衰减率），
        所以从外部观察根本判断不出它有没有坏。必须能直接看内部数字。
        """
        import time as _t
        core = self.core
        try:
            import salience as _sal
        except Exception as e:
            return {"ok": False, "err": "缺 salience 模块：" + str(e)[:120]}
        now = _t.time()
        try:
            chain = core.tree.get_current_chain()
        except Exception as e:
            return {"ok": False, "err": "读历史失败：" + str(e)[:120]}
        rows = []
        for m in chain:
            if m.get("role") == "system":
                continue
            nid = m.get("_node_id")
            s = _sal.salience(m, now=now) if nid else 0.0
            dec = _sal.hidden_decay(nid) if nid else 0.0
            age_days = 0.0
            try:
                ts = float(m.get("_ts") or 0)
                if ts:
                    age_days = max(0.0, (now - ts) / 86400.0)
            except (TypeError, ValueError):
                pass
            rows.append({
                "id": nid,
                "age_days": round(age_days, 2),
                "salience": round(s, 4),
                "decay_per_day": round(dec, 4),
                "alive": bool(s >= _sal.KEEP_THRESHOLD),
                "role": m.get("role"),
                "preview": str(m.get("content") or "")[:40],
            })
        alive = [r for r in rows if r["alive"]]
        return {
            "ok": True,
            "threshold": _sal.KEEP_THRESHOLD,
            "recent_window": getattr(core, "recent_window", None),
            "total": len(rows),
            "alive": len(alive),
            "forgotten": len(rows) - len(alive),
            "rows": rows,
            "params": {"decay_min": _sal.DECAY_MIN, "decay_max": _sal.DECAY_MAX,
                       "decay_portion": _sal.DECAY_PORTION},
        }

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

    def api_ranker_status(self):
        """给非开发者看的：数据够不够、模型有没有、它在用什么特征。"""
        out = {"ok": True}
        try:
            import preference_export, ranker
        except Exception as e:
            return {"ok": False, "err": "缺少模块：" + str(e)[:120]}
        try:
            r = preference_export.scan_dir(self.save_dir)
            recs = r.get("records") or []
            rd = ranker.readiness(recs)
        except Exception as e:
            return {"ok": False, "err": "读偏好数据失败：" + str(e)[:160]}
        out["readiness"] = rd
        out["by_role"] = r.get("by_role") or {}
        # 现在有多少条没打分的样本（训之前先打分才有一致率可比）
        s = r.get("sum") or {}
        out["heuristic_agreement"] = s.get("agreement")
        m = ranker.load(self._ranker_path())
        if m:
            out["model"] = {"train_acc": m.get("train_acc"),
                            "holdout_acc": m.get("holdout_acc"),
                            "n_samples": m.get("n_samples"),
                            "top": ranker.explain(m, top=6)}
        else:
            out["model"] = None
        out["enabled"] = bool((self.config.get("ranker") or {}).get("on"))
        return out

    def api_train_ranker(self):
        """在本地把偏好数据训成一个排序器。纯 numpy，几秒钟，不需要服务器。"""
        try:
            import preference_export, ranker
        except Exception as e:
            return {"ok": False, "err": "缺少模块：" + str(e)[:120]}
        try:
            r = preference_export.scan_dir(self.save_dir)
            recs = r.get("records") or []
        except Exception as e:
            return {"ok": False, "err": "读偏好数据失败：" + str(e)[:160]}
        # 案卷用当前角色的（特征里的 confab 要用）
        try:
            m = ranker.train(recs, keys=self._drift_keys(), case_text=self._case_text())
        except Exception as e:
            return {"ok": False, "err": "训练失败：" + str(e)[:200]}
        if not m.get("ok"):
            return {"ok": False, "err": m.get("err"), "readiness": m.get("readiness")}
        try:
            ranker.save(m, self._ranker_path())
        except Exception as e:
            return {"ok": False, "err": "模型存不下来：" + str(e)[:160]}
        return {"ok": True, "train_acc": m.get("train_acc"),
                "holdout_acc": m.get("holdout_acc"),
                "n_pairs": m.get("n_pairs"), "n_samples": m.get("n_samples"),
                "top": ranker.explain(m, top=6),
                "path": self._ranker_path(),
                "msg": "训练完成（纯本地，没有联网、没有用你的 API Key）"}

    def api_set_ranker(self, enabled):
        """启用/停用训好的排序器。启用后它会替代启发式给前瞻分支打分。"""
        cfg = dict(self.config.get("ranker") or {})
        cfg["on"] = bool(enabled)
        self.config["ranker"] = cfg
        self._save_config()
        return {"ok": True, "on": cfg["on"]}

    def api_tree_weights(self):
        """给整棵树打分并写回节点元数据（主干 70% / 枝干 50%，有效权重 = 可实行性 × 合理性 × 位置）。

        只打分不删任何东西 —— 让用户先看清楚再决定要不要剪。
        """
        try:
            import tree_weight
        except Exception as e:
            return {"ok": False, "err": "缺少 tree_weight 模块：" + str(e)[:120]}
        try:
            st = tree_weight.annotate(self.core.tree)
            self._save_tree()
            return {"ok": True, "stats": st}
        except Exception as e:
            return {"ok": False, "err": "打分失败：" + str(e)[:200]}

    def api_tree_prune(self, dry_run=True):
        """按有效权重剪掉低分枝叶。

        硬规则（都在 tree_weight 里保证，这里不重复实现）：
          主干永不删 / system 永不删 / 主干上没有对话节点时一律不剪 / 不留断头孤儿。
        dry_run=True 时只报告不真删。
        """
        try:
            import tree_weight
        except Exception as e:
            return {"ok": False, "err": "缺少 tree_weight 模块：" + str(e)[:120]}
        try:
            before = len(self.core.tree.nodes)
            r = tree_weight.prune(self.core.tree, dry_run=bool(dry_run))
            if not dry_run and r.get("removed_count"):
                self._save_tree()
                self._rebuild_messages()
            r["before"] = before
            r["after"] = len(self.core.tree.nodes)
            return r
        except Exception as e:
            return {"ok": False, "err": "剪枝失败：" + str(e)[:200]}

    def api_regenerate(self, seq):
        """重新生成：为最后一条 AI 消息生成新候选（滑条）"""
        msg = next((m for m in self.messages if m["seq"] == seq), None)
        if not msg or msg["kind"] != "ai":
            return {"ok": False, "err": "只能对 AI 消息重新生成"}
        if self.busy:
            return {"ok": False, "err": "busy"}
        node = self.core.tree.nodes.get(msg["node_id"])
        if not node or not node.parent_id or node.parent_id not in self.core.tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        self._start_fetch(node.parent_id)
        return {"ok": True}

    def api_switch_swipe(self, seq, index):
        """切换滑条：选择父用户节点下的第 index 条 assistant 候选"""
        msg = next((m for m in self.messages if m["seq"] == seq), None)
        if not msg or msg["kind"] != "ai":
            return {"ok": False, "err": "无效消息"}
        node = self.core.tree.nodes.get(msg["node_id"])
        if not node or not node.parent_id or node.parent_id not in self.core.tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        sibs = [cid for cid in self.core.tree.nodes[node.parent_id].children_ids
                if self.core.tree.nodes.get(cid) and self.core.tree.nodes[cid].role == "assistant"]
        try:
            target = sibs[int(index)]
        except (ValueError, IndexError):
            return {"ok": False, "err": "滑条越界"}
        self.core.tree.current_leaf_id = target
        self._save_tree()
        self._rebuild_messages()
        return {"ok": True}

    def api_edit_message(self, seq, new_content):
        """编辑消息：AI 消息原地改；用户消息开新分支并自动重新生成"""
        new_content = (new_content or "").strip()
        if not new_content:
            return {"ok": False, "err": "内容不能为空"}
        msg = next((m for m in self.messages if m["seq"] == seq), None)
        if not msg:
            return {"ok": False, "err": "无效消息"}
        node = self.core.tree.nodes.get(msg["node_id"])
        if not node:
            return {"ok": False, "err": "节点不存在"}
        if node.role == "assistant":
            node.content = new_content
            self._save_tree()
            self._rebuild_messages()
            return {"ok": True}
        if self.busy:
            return {"ok": False, "err": "busy"}
        new_id = self.core.tree.add_node("user", new_content,
                                         parent_id=node.parent_id,
                                         metadata=dict(node.metadata or {}))
        if node.id in self.node_images:
            self.node_images[new_id] = self.node_images[node.id]
        self._start_fetch(new_id)
        return {"ok": True}

    def api_branches(self):
        """列出可切换的其他分支（叶子节点）"""
        tree = self.core.tree
        out = []
        for nid, node in tree.nodes.items():
            if node.role == "system" or node.children_ids:
                continue
            if nid == tree.current_leaf_id:
                continue
            previews = []
            n = node
            depth = 0
            while n is not None and len(previews) < 2:
                if n.role != "system":
                    previews.append(n.content)
                depth += 1
                if n.parent_id and n.parent_id in tree.nodes:
                    n = tree.nodes[n.parent_id]
                else:
                    break
            previews.reverse()
            out.append({"node_id": nid, "kind": node.role, "depth": depth,
                        "preview": " / ".join((p or "").replace(chr(10), " ")[:40] for p in previews)})
        out.sort(key=lambda x: -x["depth"])
        return out

    def api_switch_branch(self, node_id):
        tree = self.core.tree
        if not node_id or node_id not in tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        tree.current_leaf_id = node_id
        self.core.restore_mechanisms(node_id)
        self._save_tree()
        self._rebuild_messages()
        return {"ok": True}

    def api_tree(self, scope="all"):
        """树状回溯：返回完整历史树（主线平铺 + 分支收纳）。
        当前路径（主线）上的节点 on_path=True（不缩进、不右窜）；
        离线分支以 branch_root 标识：branch_root==自身 的行是「分支收纳行」，
        其 branch_size 为分支节点数，展开后成员按 branch_depth（分支内深度）显示。

        scope="all"：完整树（含选项间对话）。
        scope="choices"：选项骨架——只保留「选项节点」+ 当前叶子，隐藏选项间的对话，
        平铺展示（branch_root 置空，不做分支收纳行），用于分线剧情下快速聚焦选项。"""
        tree = self.core.tree
        nodes = tree.nodes
        # 当前路径（root → 当前叶子），主线 = 路径上的节点
        path = set()
        nid = tree.current_leaf_id
        while nid and nid in nodes:
            path.add(nid)
            nid = nodes[nid].parent_id

        def subtree_size(nid):
            node = nodes.get(nid)
            if not node:
                return 0
            return 1 + sum(subtree_size(c) for c in node.children_ids)

        out = []
        branch_sizes = {}

        def walk(nid, in_branch, branch_depth):
            node = nodes.get(nid)
            if not node:
                return
            on_path = nid in path
            if on_path:
                in_branch = None
                branch_depth = 0
            elif in_branch is None:
                in_branch = nid
                branch_depth = 0
                branch_sizes[nid] = subtree_size(nid)
            else:
                branch_depth += 1
            out.append({
                "id": nid,
                "role": node.role,
                "content": (node.content or "").replace("\n", " ")[:60],
                "on_path": on_path,
                "branch_root": in_branch,
                "branch_depth": branch_depth,
                "branch_size": branch_sizes.get(in_branch, 0),
                "is_current": nid == tree.current_leaf_id,
                "is_leaf": not node.children_ids,
                "is_choice": bool((node.metadata or {}).get("is_choice")),
            })
            for c in node.children_ids:
                walk(c, in_branch, branch_depth)

        if tree.root_id:
            walk(tree.root_id, None, 0)

        if scope == "choices":
            # 选项骨架：保留分支归属（branch_root/branch_depth），前端据此按支线分组，
            # 并把「非选项、非当前」的对话折叠成可展开的 ··· 段。仅视图层折叠，不改存储结构。
            pass
        return out

    def api_backtrack(self, node_id):
        """树状回溯：把对话定位到任意节点（从这里继续/切换分支）"""
        tree = self.core.tree
        if not node_id or node_id not in tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        if node_id == tree.current_leaf_id:
            return {"ok": True}
        tree.current_leaf_id = node_id
        self.core.restore_mechanisms(node_id)
        self._save_tree()
        self._rebuild_messages()
        return {"ok": True}

    # ---------- 酒馆角色卡导入导出 ----------
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

    def api_import_card(self):
        """文件对话框导入酒馆角色卡（.png/.webp/.json）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("角色卡 (*.png;*.webp;*.json)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        return self._do_import_card(res[0])

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

    def api_export_card(self, name, fmt):
        """导出角色卡：fmt = json | png（酒馆 v2 格式，PNG 嵌卡）"""
        fmt = (fmt or "json").lower()
        if fmt not in ("json", "png"):
            return {"ok": False, "err": "格式必须是 json 或 png"}
        ext = "json" if fmt == "json" else "png"
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=self._safe_name(name) + "." + ext,
                file_types=("JSON (*.json)",) if fmt == "json" else ("PNG (*.png)",))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        path = res[0]
        if fmt == "json" and not path.lower().endswith(".json"):
            path += ".json"
        if fmt == "png" and not path.lower().endswith(".png"):
            path += ".png"
        return self._do_export_card(name, fmt, path)

    # ---------- 世界书条目 ----------
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
    def _ws_config_file(self):
        return os.path.join(BASE_DIR, "workshop_config.json")

    def _ws_save_config(self, server_url, api_key, proxy=None):
        # api_key 加密落盘（工坊连接串属敏感信息）
        enc = secret_store.encrypt((api_key or "").strip())
        save_guard.atomic_write_json(self._ws_config_file(),
                                     {"server_url": (server_url or "").strip(),
                                      "api_key": enc,
                                      "proxy": (proxy or "").strip()})

    def _ws_load_config(self):
        """读取工坊连接配置；api_key 是密文则解密。返回 dict。"""
        cfg = {}
        try:
            with open(self._ws_config_file(), "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return cfg
        if isinstance(cfg, dict) and cfg.get("api_key"):
            d = secret_store.decrypt(str(cfg["api_key"]))
            cfg["api_key"] = d if d is not None else ""
        return cfg

    def _ws_headers(self):
        key = (self._ws_load_config().get("api_key") or "").strip()
        return {"X-API-Key": key} if key else {}

    def _ws_proxies(self):
        """从配置读取代理（支持 http/https/socks5），返回 requests 代理字典或 None"""
        proxy = (self._ws_load_config().get("proxy") or "").strip()
        if not proxy:
            return None
        if "://" not in proxy:
            proxy = "http://" + proxy
        return {"http": proxy, "https": proxy}

    def _ws_url(self, path):
        base = self._ws_active_server()
        return base + path

    def _ws_active_server(self):
        """自动部署：返回当前可用的工坊服务器地址。
        优先使用配置的 server_url；未配置或不可用时自动探测
        ① 本机服务器 ② 默认隧道地址。结果缓存 30 秒避免每次请求都探测。"""
        import time as _t
        cfg_url = (self._ws_load_config().get("server_url") or "").strip().rstrip("/")
        now = _t.time()
        # 缓存有效期内直接返回
        cached = getattr(self, "_ws_active_cache", None)
        if cached and now - cached[1] < 30:
            return cached[0]
        candidates = []
        # 优先使用配置的稳定公网地址（命名隧道 https://<id>.cfargotunnel.com，用户填 server_url）
        if cfg_url:
            candidates.append(cfg_url)
        # 其次本机服务器（局域网直连，最快最稳）
        candidates.append("http://127.0.0.1:5000")
        # 不再硬编码易变的 trycloudflare 临时地址，避免连到失效的旧隧道。
        # 公网访问统一走 server_url（稳定地址），需要时把该地址填到工坊地址。
        import requests as _req
        for base in candidates:
            try:
                r = _req.get(base + "/api/health", timeout=2.5,
                             headers=self._ws_headers(), proxies=self._ws_proxies())
                if r.status_code < 400:
                    self._ws_active_cache = (base, now)
                    return base
            except Exception:
                continue
        # 全部失败：退回配置地址（后续请求会报错并提示）
        self._ws_active_cache = (cfg_url or candidates[1], now)
        return cfg_url or candidates[1]

    # ---------- 树存档同步（复用工坊服务器，聊天进度互通） ----------
    def _ws_sync_enabled(self):
        """进度同步开关：
        ① 显式配置了工坊 server_url → 同步（远程/云端）；
        ② 未配置但本机 net.py 服务器在线（局域网直连）→ 同步到本机服务器，手机同网连它。
        本机探测用极短超时，避免每次保存卡顿。"""
        if (self._ws_load_config().get("server_url") or "").strip():
            return True
        try:
            import requests as _req
            r = _req.get("http://127.0.0.1:5000/api/health", timeout=0.6,
                         headers=self._ws_headers(), proxies=self._ws_proxies())
            return r.status_code < 400
        except Exception:
            return False

    def _ws_save_upload(self, card_id, tree_data):
        """把某角色的聊天树推送到工坊服务器（后来者胜）。返回 (ok, ts)。"""
        try:
            import requests as _req
            url = self._ws_url("/api/save/" + str(card_id))
            r = _req.post(url, json={"tree": tree_data}, timeout=6,
                          headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code < 400:
                return True, (r.json() or {}).get("ts", "")
        except Exception as e:
            print(f"[树存档同步] 推送失败: {e}")
        return False, ""

    def _ws_save_upload_async(self, card_id, tree_data):
        """后台线程推送（不阻塞保存）。"""
        if not self._ws_sync_enabled():
            return
        threading.Thread(target=self._ws_save_upload, args=(card_id, tree_data), daemon=True).start()

    def _ws_save_fetch(self, card_id):
        """从工坊服务器拉取某角色最新的聊天树。返回 {"ts":..., "tree":...} 或 None。"""
        try:
            import requests as _req
            url = self._ws_url("/api/save/" + str(card_id))
            r = _req.get(url, timeout=6, headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code < 400:
                d = r.json() or {}
                if isinstance(d.get("tree"), dict):
                    return d
        except Exception as e:
            print(f"[树存档同步] 拉取失败: {e}")
        return None

    def _ws_pull_tree(self, role_name):
        """拉取服务器上该角色最新的聊天树；若比本地新则替换本地存档（实现跨设备续聊）。
        返回 True 表示采用了服务器版本。"""
        # 跑团会期锁定：被锁卡的记忆树绝不被服务器版本覆盖（避免导入/续聊与跑团混淆）
        if role_name in self._trpg_locked_names():
            return False
        fetched = self._ws_save_fetch(role_name)
        if not fetched:
            return False
        server_ts = str(fetched.get("ts") or "")
        server_tree = fetched.get("tree")
        if not server_ts or not isinstance(server_tree, dict):
            return False
        for r in self.roles:
            if r["name"] == role_name:
                data = dict(r.get("data") or {})
                local_ts = str(data.get("_tree_ts") or "")
                if server_ts <= local_ts:
                    return False
                data["history_tree"] = server_tree
                data["_tree_ts"] = server_ts
                r["data"] = data
                # 同时写回本地文件，避免下次又拉
                try:
                    out = dict(data)
                    out["name"] = r["name"]
                    out["system_prompt"] = r["prompt"]
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), out)
                except Exception:
                    pass
                return True
        return False

    # ---------- 同步设置（API 码等） ----------
    def _ws_push_api(self):
        """把当前模型连接配置（API 码/端点/模型）推送到工坊服务器（后台线程）。"""
        if not self._ws_sync_enabled():
            return
        payload = {
            "api_key": (self.config.get("api_key") or "").strip(),
            "base_url": (self.config.get("base_url") or "").strip(),
            "model": (self.config.get("model") or "").strip(),
            "provider": (self.config.get("provider") or "deepseek").strip(),
        }
        if not payload["api_key"]:
            return   # 本地还没填 Key，不覆盖服务器已有配置
        threading.Thread(target=self._ws_push_api_sync, args=(payload,), daemon=True).start()

    def _ws_push_api_sync(self, payload):
        try:
            import requests as _req
            r = _req.post(self._ws_url("/api/sync/api"), json=payload, timeout=6,
                          headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                print(f"[API 同步] 推送失败 HTTP {r.status_code}")
        except Exception as e:
            print(f"[API 同步] 推送失败: {e}")

    def _ws_pull_api(self):
        """拉取共享的模型连接配置；若服务器有 Key 且与本地不同则应用（后来者胜）。"""
        if not self._ws_sync_enabled():
            return False
        try:
            import requests as _req
            r = _req.get(self._ws_url("/api/sync/api"), timeout=6,
                         headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return False
            d = r.json() or {}
            key = (d.get("api_key") or "").strip()
            if not key:
                return False
            # 应用服务器共享的连接配置（覆盖本地）
            self.config["api_key"] = key
            pid = (d.get("provider") or self.config.get("provider") or "deepseek").strip()
            self.config["provider"] = pid
            self.provider_id = pid
            self.api_keys[pid] = key
            self.config["api_keys"] = self.api_keys
            if d.get("base_url"):
                self.config["base_url"] = d["base_url"].strip()
                self.core.set_base_url(self.config["base_url"])
            if d.get("model"):
                self.config["model"] = d["model"].strip()
                self.core.set_model(self.config["model"])
            self.core.set_api_key(key if key else "free")
            if self.config.get("proxy"):
                self.core.set_proxy(self.config["proxy"])
            self.core.set_stop_sequences(self._effective_stop())
            self._save_config()
            print("[API 同步] 已应用服务器共享的模型连接配置")
            return True
        except Exception as e:
            print(f"[API 同步] 拉取失败: {e}")
            return False

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

    def api_workshop_state(self):
        cfg = self._ws_load_config()
        roles = [fn for fn in sorted(os.listdir(self.save_dir)) if not fn.startswith(".") and fn.endswith(".json")]
        worlds = [fn for fn in sorted(os.listdir(self.world_dir)) if fn.endswith(".json")]
        active = ""
        try:
            active = self._ws_active_server()
        except Exception:
            pass
        return {"server_url": cfg.get("server_url", ""), "active_server": active,
                "has_key": bool(cfg.get("api_key")),
                "proxy": cfg.get("proxy", ""),
                "local_roles": roles, "local_worlds": worlds}

    def api_workshop_save_conn(self, server_url, api_key, proxy=None):
        self._ws_save_config(server_url or "", api_key or "", proxy or "")
        return {"ok": True}

    def api_workshop_detect_proxy(self):
        """自动检测本机代理：1) Windows 系统代理设置 2) 常见代理软件端口"""
        import socket
        found = []
        # 1) Windows 系统代理（IE/系统设置里开的代理）
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"SoftwareMicrosoftWindowsCurrentVersionInternet Settings")
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            winreg.CloseKey(key)
            if enable and server:
                srv = str(server).strip()
                # 可能形如 "127.0.0.1:7890" 或 "http=127.0.0.1:7890;https=..."; 取第一个
                if "=" in srv:
                    srv = srv.split(";")[0].split("=", 1)[1].strip()
                if srv and "://" not in srv:
                    srv = "http://" + srv
                found.append(("系统代理", srv))
        except Exception:
            pass
        # 2) 常见代理软件本地端口探测
        common_ports = [7890, 7891, 10809, 10808, 1080, 8888, 1087, 8080, 20171, 9910]
        for port in common_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.25)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    found.append((f"本地端口 :{port}", f"http://127.0.0.1:{port}"))
                s.close()
            except Exception:
                pass
        # 去重（同一地址只保留一次）
        seen = set()
        result = []
        for label, url in found:
            if url not in seen:
                seen.add(url)
                result.append({"label": label, "url": url})
        return {"ok": True, "found": result}

    def api_workshop_test(self):
        import requests
        try:
            r = requests.get(self._ws_url("/api/health"), timeout=6, headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            try:
                health = r.json() if isinstance(r.json(), dict) else {}
            except Exception:
                health = {}
            stats = {}
            try:
                sr = requests.get(self._ws_url("/api/stats"), timeout=6, headers=self._ws_headers(), proxies=self._ws_proxies())
                if sr.status_code < 400:
                    stats = sr.json()
            except Exception:
                pass
            return {"ok": True, "health": health, "stats": stats}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_list(self):
        import requests
        try:
            cr = requests.get(self._ws_url("/api/cards/list"), timeout=8, headers=self._ws_headers(), proxies=self._ws_proxies())
            wr = requests.get(self._ws_url("/api/worlds/list"), timeout=8, headers=self._ws_headers(), proxies=self._ws_proxies())
            if cr.status_code >= 400 or wr.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(cr.status_code) + " / " + str(wr.status_code)}
            return {"ok": True, "cards": cr.json(), "worlds": wr.json()}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_search(self, query, rtype):
        import requests
        try:
            params = {}
            if query:
                params["q"] = query
            if rtype:
                params["type"] = rtype
            r = requests.get(self._ws_url("/api/search"), params=params, timeout=8, headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            return {"ok": True, "results": r.json()}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_download(self, res_id, rtype, filename):
        import requests
        try:
            kind = "cards" if rtype == "角色卡" else "worlds"
            target_dir = self.save_dir if rtype == "角色卡" else self.world_dir
            r = requests.get(self._ws_url("/api/" + kind + "/" + str(res_id)), timeout=30,
                             headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            fname = (filename or (str(res_id) + ".json")).replace("..", "_")
            if not fname.endswith(".json"):
                fname += ".json"
            dst = os.path.join(target_dir, fname)
            base, ext = os.path.splitext(dst)
            i = 1
            while os.path.exists(dst):
                dst = base + "_" + str(i) + ext
                i += 1
            with open(dst, "wb") as f:
                f.write(r.content)
            if rtype == "角色卡":
                self._reload_roles()
            else:
                self._reload_worlds()
            return {"ok": True, "file": os.path.basename(dst)}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_like(self, res_id, rtype):
        import requests
        try:
            kind = "cards" if rtype == "角色卡" else "worlds"
            r = requests.post(self._ws_url("/api/" + kind + "/" + str(res_id) + "/like"),
                              timeout=8, headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_delete(self, res_id, rtype):
        import requests
        try:
            kind = "cards" if rtype == "角色卡" else "worlds"
            r = requests.delete(self._ws_url("/api/" + kind + "/" + str(res_id)),
                                timeout=8, headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_upload(self, rtype, name):
        import requests
        try:
            target_dir = self.save_dir if rtype == "角色卡" else self.world_dir
            fname = self._safe_name(name) + ".json"
            path = os.path.join(target_dir, fname)
            if not os.path.isfile(path):
                return {"ok": False, "err": "本地文件不存在：" + fname}
            with open(path, "rb") as f:
                r = requests.post(
                    self._ws_url("/api/cards/upload" if rtype == "角色卡" else "/api/worlds/upload"),
                    files={"file": (fname, f, "application/json")}, data={"name": name},
                    timeout=30, headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            return {"ok": True, "message": r.text[:200]}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_preview(self, rtype, filename):
        target_dir = self.save_dir if rtype == "角色卡" else self.world_dir
        filename = os.path.basename((filename or "").replace("..", "_"))
        path = os.path.join(target_dir, filename)
        if not os.path.isfile(path):
            return {"ok": False, "err": "文件不存在"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read(8000)
            try:
                json.loads(text)
            except Exception:
                pass
            return {"ok": True, "preview": text}
        except Exception as e:
            return {"ok": False, "err": str(e)}

    def api_workshop_export(self, rtype, filename):
        """本地文件导出到用户选择的位置"""
        target_dir = self.save_dir if rtype == "角色卡" else self.world_dir
        filename = os.path.basename((filename or "").replace("..", "_"))
        src = os.path.join(target_dir, filename)
        if not os.path.isfile(src):
            return {"ok": False, "err": "文件不存在"}
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename,
                                         file_types=("JSON (*.json)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            import shutil
            shutil.copy2(src, res[0])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_plugins(self):
        """拉取工坊插件列表 + 本地已安装插件名（标记用）"""
        import requests
        try:
            r = requests.get(self._ws_url("/api/plugins/list"), timeout=8,
                             headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            plugins = r.json()
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}
        local = set()
        for d in getattr(self.plugin_manager, "plugin_dirs", []) or []:
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.endswith(".py") and not fn.startswith("_"):
                        local.add(fn[:-3])
        return {"ok": True, "plugins": plugins, "local": sorted(local)}

    def api_workshop_install_plugin(self, plugin_id):
        """下载插件到 plugins/ 目录并热加载"""
        import requests
        try:
            r = requests.get(self._ws_url("/api/plugins/" + str(plugin_id)), timeout=30,
                             headers=self._ws_headers(), proxies=self._ws_proxies())
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            info = None
            try:
                lr = requests.get(self._ws_url("/api/plugins/list"), timeout=8,
                                  headers=self._ws_headers(), proxies=self._ws_proxies())
                if lr.status_code < 400:
                    info = next((p for p in lr.json() if str(p.get("id")) == str(plugin_id)), None)
            except Exception:
                pass
            fname = (info or {}).get("original_name") or (str(plugin_id) + ".py")
            fname = os.path.basename(str(fname).replace("..", "_"))
            if not fname.endswith(".py"):
                fname += ".py"
            target_dir = getattr(self.plugin_manager, "plugin_dir", None) or "plugins"
            os.makedirs(target_dir, exist_ok=True)
            dst = os.path.join(target_dir, fname)
            with open(dst, "wb") as f:
                f.write(r.content)
            try:
                self.plugin_manager.reload_plugins()
            except Exception as e:
                print(f"[Plugin] 重载失败: {e}")
            return {"ok": True, "name": (info or {}).get("name") or fname, "file": fname}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_delete_local(self, rtype, filename):
        target_dir = self.save_dir if rtype == "角色卡" else self.world_dir
        filename = os.path.basename((filename or "").replace("..", "_"))
        path = os.path.join(target_dir, filename)
        if not os.path.isfile(path):
            return {"ok": False, "err": "文件不存在"}
        try:
            os.remove(path)
            if rtype == "角色卡":
                self._reload_roles()
            else:
                self._reload_worlds()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_workshop_open_folder(self, which):
        try:
            if which == "roles":
                target = self.save_dir
            elif which == "worlds":
                target = self.world_dir
            elif which == "plugins":
                target = getattr(self.plugin_manager, "plugin_dir", None) or "plugins"
            else:
                target = self.save_dir
            os.startfile(target)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)}

    def api_open_path(self, path):
        """在资源管理器中打开/定位文件（打包产物定位用）"""
        try:
            if path and os.path.exists(path):
                os.startfile(os.path.dirname(os.path.abspath(path)))
                return {"ok": True}
            return {"ok": False, "err": "not found"}
        except Exception as e:
            return {"ok": False, "err": str(e)}

# ---------- 前版功能补齐：预算 / 自动接话 / 字体 / 插件管理 / 文档 / 导出 ----------
    def api_toggle_unlock(self, name):
        """破甲模式快速开关（角色级：任一启用则对话注入破甲提示）"""
        for r in self.roles:
            if r["name"] == name:
                r["unlocked"] = not r.get("unlocked", False)
                data = dict(r.get("data") or {})
                data["unlocked"] = r["unlocked"]
                r["data"] = data
                try:
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), data)
                except Exception:
                    pass
                if name in self.selected_roles:
                    self._activate_core(reload_tree=False)
                return {"ok": True, "unlocked": r["unlocked"]}
        return {"ok": False, "err": "not found"}

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

    def api_read_document(self, path=None):
        """读入 Word/Excel 文档供 AI 分析（文件对话框或给定路径）"""
        if not path:
            try:
                import webview
                win = webview.windows[0] if getattr(webview, "windows", None) else None
                if win is None:
                    return {"ok": False, "err": "窗口未就绪"}
                res = win.create_file_dialog(
                    webview.FileDialog.OPEN, allow_multiple=False,
                    file_types=("文档 (*.docx;*.xlsx;*.txt)", "All files (*.*)"))
                if not res:
                    return {"ok": False, "err": "cancelled"}
                path = res[0]
            except Exception as e:
                return {"ok": False, "err": "对话框失败：" + str(e)}
        path = path.strip().strip('"')
        try:
            import doc_reader
            text = doc_reader.read_document(path)
        except ValueError as e:
            # 兼容 .txt 直读
            if path.lower().endswith(".txt"):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except Exception as e2:
                    return {"ok": False, "err": str(e2)}
            else:
                return {"ok": False, "err": str(e)}
        except Exception as e:
            return {"ok": False, "err": "读取失败：" + str(e)[:200]}
        if not text or not text.strip():
            return {"ok": False, "err": "文档内容为空"}
        cap = 20000
        if len(text) > cap:
            text = text[:cap] + chr(10) + "…（文档过长，已截断，可用 /readclear 清除）"
        self.core.set_document_context(text)
        self.loaded_document = {"name": os.path.basename(path), "chars": len(text)}
        self._append_sys("📄 已读入文档：" + self.loaded_document["name"] +
                         "（" + str(len(text)) + " 字符），后续对话自动参考")
        return {"ok": True, "name": self.loaded_document["name"], "chars": len(text)}

    def api_clear_document(self):
        self.core.clear_document_context()
        self.loaded_document = None
        self._append_sys("🧹 已清除文档上下文")
        return {"ok": True}

    def api_export_chat(self):
        """把当前聊天记录导出为 Word 文档"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename="聊天记录.docx",
                                         file_types=("Word (*.docx)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            if not path.lower().endswith(".docx"):
                path += ".docx"
            from docx import Document
            doc = Document()
            doc.add_heading("Direct-Interface Cork-bore Kit · 聊天记录", level=1)
            for m in self.messages:
                who = m.get("speaker") or ("你" if m.get("kind") == "user" else "AI")
                doc.add_paragraph("")
                p = doc.add_paragraph()
                run = p.add_run(who + "：")
                run.bold = True
                doc.add_paragraph(m.get("content") or "")
            doc.save(path)
            return {"ok": True, "file": os.path.basename(path)}
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)[:200]}

    def api_export_novel(self, fmt="epub"):
        """把当前聊天记录导出成【小说】（EPUB / Word）。

        与 api_export_chat 的区别：那个导的是扁平消息列表（分支、重生成、回溯过的内容
        全糊在一起）；这个走树上的实际路径（root → current_leaf_id），并把当时没走过的
        分支收成脚注 —— 于是每局对话都能变成一部读得下去的作品。
        """
        import novel_export
        try:
            tree = self.core.get_all_nodes_data()
        except Exception as e:
            return {"ok": False, "err": "读取聊天树失败：" + str(e)[:120]}
        # 标题：当前选中的角色名（群聊就拼起来）
        try:
            names = [r.get("name") for r in (self.roles or [])
                     if r.get("name") in (self.selected_roles or [])]
        except Exception:
            names = []
        who = "、".join([n for n in names if n][:3]) or "对话"
        title = who + " · 对话小说"
        try:
            author = ((self.persona or {}).get("name") or "").strip()
        except Exception:
            author = ""
        fmt = (fmt or "epub").strip().lower()
        is_word = fmt in ("docx", "word")
        default_name = novel_export.safe_name(title) + (".docx" if is_word else ".epub")
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            types = ("Word (*.docx)",) if is_word else ("EPUB (*.epub)",)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=default_name, file_types=types)
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            want = ".docx" if is_word else ".epub"
            if not path.lower().endswith(want):
                path += want
        except Exception as e:
            return {"ok": False, "err": "保存对话框失败：" + str(e)[:120]}
        ok, msg = novel_export.export_novel(tree, fmt, path, title=title, author=author)
        if not ok:
            return {"ok": False, "err": msg}
        return {"ok": True, "file": os.path.basename(path), "path": path, "msg": msg,
                "title": title}

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

    # ---------- 加密备份 ----------

    BACKUP_EXT = ".dickbackup"

    def api_backup_password_check(self, password):
        """给界面用：实时告诉用户口令够不够强（不存任何东西）"""
        try:
            import crypto_core
            lvl, msg = crypto_core.password_strength(password or "")
            return {"ok": True, "level": lvl, "msg": msg,
                    "ok_to_use": lvl >= 2}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}

    def api_backup_make_password(self):
        """生成一个随机强口令。

        为什么要这个：备份的安全性 100% 取决于口令，而人自己想的口令
        普遍很弱（生日、拼音、叠字）。更麻烦的是【忘了就永久打不开】——
        我们没留后门，也没有任何找回手段。
        所以让程序给一个 32 字节随机的，用户抄在纸上收好，
        这比「想一个好记的」既更安全、也更不容易忘。
        """
        try:
            import crypto_core
            return {"ok": True, "password": crypto_core.make_recovery_code()}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}

    def api_export_backup_encrypted(self, password):
        """加密备份：整体打包 → 用口令加密成【一个文件】。

        比「加密 zip」更好：连文件名、目录结构、有几个存档、config 里的字段
        全都看不见 —— 加密 zip 只加密内容，文件名和结构仍是明文。
        """
        try:
            import crypto_core
            import datetime as _dt
        except Exception as e:
            return {"ok": False, "err": "缺少加密模块 crypto_core：" + str(e)[:120]}
        lvl, msg = crypto_core.password_strength(password or "")
        if lvl < 2:
            return {"ok": False,
                    "err": "口令不够强（%s）。加密备份的安全性 100%% 取决于口令强度，"
                           "请至少 12 位、混合大小写字母和数字。" % msg}
        try:
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            entries = self._backup_entries()
            raw_zip = self._zip_entries(entries, "DICK_备份_" + ts)
            blob = crypto_core.encrypt(password, raw_zip)
            out = self._pick_save_path("DICK_加密备份_" + ts + self.BACKUP_EXT,
                                       ("DICK 加密备份 (*" + self.BACKUP_EXT + ")",))
            if not out.lower().endswith(self.BACKUP_EXT):
                out += self.BACKUP_EXT
            with open(out, "wb") as f:
                f.write(blob)
            return {"ok": True, "file": out, "name": os.path.basename(out),
                    "size": os.path.getsize(out),
                    "entries": len(entries),
                    "zip_bytes": len(raw_zip),
                    "container_bytes": len(blob),
                    "info": crypto_core.info(blob)}
        except Exception as e:
            return {"ok": False, "err": "加密备份失败：" + str(e)[:200]}

    def api_import_backup_encrypted(self, password):
        """还原加密备份：解密 → 解压 → 覆盖 saves/worlds/personas/config。
        覆盖前会把原文件复制到 saves/backup/ 下，避免一失手全没了。"""
        try:
            import crypto_core
            import zipfile
            import io
            import datetime as _dt
        except Exception as e:
            return {"ok": False, "err": "缺少加密模块：" + str(e)[:120]}
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=("DICK 加密备份 (*" + self.BACKUP_EXT + ")", "所有文件 (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)[:120]}
        if not res:
            return {"ok": False, "err": "cancelled"}
        src = res[0]
        try:
            with open(src, "rb") as f:
                blob = f.read()
        except Exception as e:
            return {"ok": False, "err": "读不到文件：" + str(e)[:120]}
        try:
            raw_zip = crypto_core.decrypt(password, blob)
        except Exception as e:
            return {"ok": False, "err": str(e)[:160]}
        try:
            z = zipfile.ZipFile(io.BytesIO(raw_zip))
        except Exception as e:
            return {"ok": False, "err": "备份内容损坏：" + str(e)[:120]}

        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = os.path.join(self.save_dir, "backup", "restore_" + ts)
        try:
            restored = self._restore_from_zip(z, bak)
        except Exception as e:
            return {"ok": False, "err": "还原失败：" + str(e)[:200]}
        return {"ok": True, "restored": restored,
                "backup_dir": bak if os.path.isdir(bak) else "",
                "msg": "已还原：存档 %d / 世界 %d / 玩家卡 %d / 剧情包 %d / 设置 %d。"
                       "（原文件已备份到 saves/backup/）"
                       % (restored["saves"], restored["worlds"],
                          restored["personas"], restored["codex"],
                          restored["config"])}

    def _restore_from_zip(self, z, bak):
        """把备份 zip 铺回磁盘。抽成独立方法是为了能脱离文件对话框测试 ——
        这段逻辑包含「写到哪」的判断，出错的代价是覆盖用户数据，必须可测。"""
        restored = {"saves": 0, "worlds": 0, "personas": 0, "config": 0, "codex": 0}
        root = os.path.realpath(os.path.abspath(self.base_dir))
        for info in z.infolist():
            if info.is_dir():
                continue
            safe = info.filename.replace("\\", "/")
            parts = safe.split("/")
            if len(parts) < 2:
                continue
            # zip 路径穿越防护：'..' 若被写进备份，还原时就能写到 DICK 目录之外。
            # GCM 已保证文件没被改过，这是纵深防御，成本几乎为零。
            if ".." in parts:
                continue
            rel = "/".join(parts[1:])
            if rel == "config.json":
                dst = self.config_file
                key = "config"
            # 注意：这里判断的是 rel 里的层级，不是 parts 的长度 ——
            # parts 还含最外层根目录名，用 len(parts)==2 会把全部条目跳过。
            elif rel.startswith("saves/") and rel.count("/") == 1:
                dst = os.path.join(self.save_dir, os.path.basename(rel))
                key = "saves"
            elif rel.startswith("worlds/") and rel.count("/") == 1:
                dst = os.path.join(self.world_dir, os.path.basename(rel))
                key = "worlds"
            elif rel.startswith("personas/") and rel.count("/") == 1:
                dst = os.path.normpath(
                    os.path.join(self.preset_dir, "..", "personas", os.path.basename(rel)))
                key = "personas"
            elif rel.startswith("codex/"):
                # codex 可能是目录，要保留子目录层级
                dst = os.path.join(self.codex_dir,
                                   rel[len("codex/"):].replace("/", os.sep))
                key = "codex"
            else:
                continue
            ap = os.path.realpath(os.path.abspath(dst))
            if not (ap == root or ap.startswith(root + os.sep)):
                continue
            # 覆盖前先留一份原件
            if os.path.isfile(dst):
                try:
                    os.makedirs(bak, exist_ok=True)
                    import shutil as _sh
                    _sh.copy2(dst, os.path.join(bak, os.path.basename(dst)))
                except Exception:
                    pass
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(z.read(info))
            restored[key] += 1
        return restored

    def api_export_backup(self):
        """一键备份：把所有角色卡(含聊天树)、世界卡、玩家卡、以及 config 打进一个 zip。
        安全网入口：用户把 zip 存到别处/云端，即可完整迁移/还原。默认存到桌面。"""
        try:
            import zipfile
            import datetime as _dt
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            # 选择保存位置（保存对话框优先；失败/无UI时退回桌面）
            fname = f"DICK_备份_{ts}.zip"
            out = None
            try:
                import webview
                win = webview.windows[0] if getattr(webview, "windows", None) else None
                if win is not None:
                    res = win.create_file_dialog(webview.FileDialog.SAVE,
                                                 save_filename=fname,
                                                 file_types=("Zip (*.zip)",))
                    if res:
                        out = res[0]
            except Exception:
                pass
            if not out:
                out = os.path.join(os.path.expanduser("~"), "Desktop", fname)
            if not out.lower().endswith(".zip"):
                out += ".zip"
            zipname = os.path.splitext(os.path.basename(out))[0]
            count = {"roles": 0, "worlds": 0, "persona": 0, "tree": 0, "config": 0}
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                # 角色卡（带聊天树）
                for r in self.roles:
                    data = dict(r.get("data") or {})
                    data["name"] = r["name"]
                    data["system_prompt"] = r.get("prompt") or data.get("system_prompt", "")
                    # 若内存树比存档新，用最新的
                    if r["name"] in self.selected_roles:
                        td = self.core.get_all_nodes_data()
                        if len(td.get("nodes", {})) > 1:
                            data["history_tree"] = td
                    z.writestr(f"{zipname}/saves/{r['file']}",
                               json.dumps(data, ensure_ascii=False, indent=2))
                    count["roles"] += 1
                    if isinstance(data.get("history_tree"), dict) and data["history_tree"].get("nodes"):
                        count["tree"] += 1
                # 世界卡
                for w in self.worlds:
                    fn = self._safe_name(w.get("name") or "") + ".json"
                    z.writestr(f"{zipname}/worlds/{fn}",
                               json.dumps(w, ensure_ascii=False, indent=2))
                    count["worlds"] += 1
                # 玩家卡 persona
                if self.persona:
                    z.writestr(f"{zipname}/personas/persona.json",
                               json.dumps(self.persona, ensure_ascii=False, indent=2))
                    count["persona"] = 1
                # config（脱敏加密写盘副本）
                safe_cfg = self._encrypt_config_secrets(self.config) or self.config
                z.writestr(f"{zipname}/config.json",
                           json.dumps(safe_cfg, ensure_ascii=False, indent=2))
                count["config"] = 1
            return {"ok": True, "file": out, "zip": os.path.basename(out),
                    "counts": count}
        except Exception as e:
            return {"ok": False, "err": "备份失败：" + str(e)[:200]}

    # ================= CODEX 专属 GALGAME（PC 端独有） =================
    # 傻瓜化：选文件夹自动归类立绘/背景/音乐/配音 → 生成剧本模板 → 播放器直接能播。
    # JSON 功能：codex.json 可视化编辑 + 校验 + zip 导入导出。

    def _codex_pkg_path(self, name):
        p = os.path.join(self.codex_dir, codex_core._safe_name(name))
        # 防目录穿越：确保解析后的路径仍在本目录内（防御性深挖，即便 _safe_name 失效）
        try:
            root = os.path.realpath(self.codex_dir)
            real = os.path.realpath(p)
            if os.path.commonpath([root, real]) != root:
                p = os.path.join(root, "_unsafe")
        except Exception:
            pass
        return p

    def api_codex_list(self):
        """列出所有 CODEX 包：name / intro / 场景数 / 资源统计"""
        out = []
        try:
            for fn in sorted(os.listdir(self.codex_dir)):
                d = os.path.join(self.codex_dir, fn)
                if not os.path.isdir(d):
                    continue
                info = {"name": fn, "intro": "", "scenes": 0,
                        "sprites": 0, "bg": 0, "bgm": 0, "voice": 0,
                        "has_script": False}
                jp = os.path.join(d, "codex.json")
                if os.path.isfile(jp):
                    try:
                        with open(jp, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        info["has_script"] = True
                        info["intro"] = str(data.get("intro") or "")[:120]
                        info["scenes"] = len(data.get("scenes") or [])
                    except Exception:
                        pass
                for kind in codex_core.SUBDIRS:
                    kd = os.path.join(d, kind)
                    if os.path.isdir(kd):
                        try:
                            info[kind] = len([x for x in os.listdir(kd)
                                              if os.path.isfile(os.path.join(kd, x))])
                        except Exception:
                            pass
                out.append(info)
        except Exception:
            pass
        return {"ok": True, "packages": out}

    def api_codex_create(self, name):
        """新建 CODEX 包：生成示例剧本 + 空资源目录"""
        name = (name or "").strip()[:60]
        if not name:
            return {"ok": False, "err": "empty"}
        dst = self._codex_pkg_path(name)
        try:
            os.makedirs(dst, exist_ok=True)
            for k in codex_core.SUBDIRS:
                os.makedirs(os.path.join(dst, k), exist_ok=True)
            jp = os.path.join(dst, "codex.json")
            if not os.path.isfile(jp):
                with open(jp, "w", encoding="utf-8") as f:
                    json.dump(codex_core.make_template(name), f,
                              ensure_ascii=False, indent=2)
            return {"ok": True, "name": os.path.basename(dst)}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_codex_sample(self, name="示例·夏日祭"):
        """一键示例包：生成带占位立绘/背景/音乐/配音的真实可播 CODEX 包"""
        ok, dst = codex_core.make_sample_package(self.codex_dir, name)
        if not ok:
            return {"ok": False, "err": "生成失败：" + str(dst)[:120]}
        return {"ok": True, "name": os.path.basename(dst)}

    def api_codex_auto_voice(self, name, lang="ja"):
        """素材供应链：一键配音——为剧本里所有有 text 的台词批量合成配音，
        写入包内 voice/ 并更新剧本引用。lang: ja(日文) / zh(中文，需声库支持)。
        返回 {ok, done, msg}。"""
        pkg = self._codex_pkg_path(name)
        jp = os.path.join(pkg, "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return {"ok": False, "err": "读剧本失败：" + str(e)[:120]}
        # UTAU 插件
        p = None
        try:
            if self.plugin_manager:
                p = self.plugin_manager.get_plugin("UTAU 语音")
        except Exception:
            p = None
        if not p or not getattr(p, "enabled", False):
            return {"ok": False, "err": "未启用 UTAU 语音插件（设置 → 插件 → UTAU 语音）"}
        if not hasattr(p, "_speak"):
            return {"ok": False, "err": "UTAU 插件缺少合成接口"}
        voice_dir = os.path.join(pkg, "voice")
        os.makedirs(voice_dir, exist_ok=True)
        done = 0
        failed = 0
        scenes = data.get("scenes") or []
        for si, sc in enumerate(scenes):
            for li, ln in enumerate(sc.get("lines") or []):
                if not isinstance(ln, dict):
                    continue
                text = str(ln.get("text") or "").strip()
                if not text or len(text) > 200:
                    continue
                try:
                    res = p._speak(text)
                    # _speak 播放并返回 "🗣️ text"；找到刚生成的 wav（tts_cache 最新）
                    base = getattr(app_paths, "get_base_dir", lambda: BASE_DIR)()
                    cache = os.path.join(base, "tts_cache")
                    cand = []
                    if os.path.isdir(cache):
                        cand = sorted([os.path.join(cache, f) for f in os.listdir(cache)
                                       if f.endswith(".wav")], key=os.path.getmtime, reverse=True)
                    if not cand:
                        failed += 1
                        continue
                    src = cand[0]
                    fn = f"auto_{si}_{li}.wav"
                    import shutil
                    shutil.copy2(src, os.path.join(voice_dir, fn))
                    ln["voice"] = "voice/" + fn
                    done += 1
                except Exception as e:
                    failed += 1
                    print(f"[CODEX voice] {si}/{li} 失败: {e}")
        save_guard.atomic_write_json(jp, data)
        return {"ok": True, "done": done, "failed": failed,
                "msg": f"配音完成：{done} 句成功" + (f"，{failed} 句失败" if failed else "")}

    def api_codex_draft(self, name, idea, count=3):
        """素材供应链：AI 起草剧本——给一句话主题，生成完整 codex.json。
        返回 {ok, script}（不落盘，前端预览后可保存）。"""
        idea = (idea or "").strip()
        if not idea:
            return {"ok": False, "err": "empty idea"}
        client = getattr(self.core, "client", None)
        if not client:
            return {"ok": False, "err": "未配置模型（设置里填 API Key）"}
        try:
            count = max(1, min(5, int(count or 3)))
        except (TypeError, ValueError):
            count = 3
        sys_prompt = (
            "你是视觉小说（GALGAME）剧本作家。根据用户给出的主题，生成一份 CODEX 剧本 JSON。\n"
            "格式（严格遵循，只输出 JSON）：\n"
            "{\n"
            '  "name": "剧本名",\n'
            '  "intro": "一句话简介",\n'
            '  "scenes": [\n'
            '    {"id": "s1", "title": "章节名", "bg": "", "lines": [\n'
            '      {"note": "舞台说明（旁白，无 speaker）"},\n'
            '      {"speaker": "角色名", "text": "台词"},\n'
            '      {"speaker": "角色名", "sprite": "", "text": "带动作的台词"},\n'
            '      {"choice": [{"text": "选项A", "goto": "s2"}, {"text": "选项B", "goto": "s3"}]},\n'
            '      {"end": "结局标题"}\n'
            '    ]}\n'
            '  ]\n'
            "}\n"
            "要求：\n"
            f"1. 生成 {count} 个场景（s1 起，id 连续），至少 2 个分支结局。\n"
            "2. 台词口语化、有情感张力，符合视觉小说节奏；旁白用 note 行。\n"
            "3. 选项分支用 goto 指向对应场景；场景末尾可 jump 回主线或用 end 结束。\n"
            "4. 只输出 JSON，不要 markdown 代码块包裹，不要额外说明。\n"
        )
        resp = client.chat.completions.create(
            model=self.core.model,
            messages=[{"role": "system", "content": sys_prompt},
                      {"role": "user", "content": idea}],
            stream=False, timeout=90,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # 宽容解析：去代码块、取 JSON 对象
        import re as _re
        m = _re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"ok": False, "err": "模型未输出有效 JSON"}
        try:
            data = json.loads(m.group(0))
        except Exception as e:
            return {"ok": False, "err": "JSON 解析失败：" + str(e)[:100]}
        if not isinstance(data, dict) or not data.get("scenes"):
            return {"ok": False, "err": "剧本缺少 scenes"}
        data.setdefault("name", (name or "我的故事"))
        data.setdefault("author", "")
        ok_v, issues = codex_core.validate_codex(data)
        return {"ok": True, "script": data, "valid": ok_v, "issues": issues}


    def api_codex_import_folder(self):
        """文件对话框选文件夹 → 自动归类为 CODEX 包（傻瓜化导入）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(webview.FileDialog.FOLDER)
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        src = res[0]
        base = os.path.basename(src.rstrip("/\\")) or "未命名"
        r = codex_core.import_folder(src, self.codex_dir, base)
        return {"ok": r["ok"], "msg": r.get("msg", ""), "name": base,
                "moved": r.get("moved", {})}

    def api_codex_get(self, name):
        """读取剧本 codex.json（JSON 功能：编辑预填）"""
        jp = os.path.join(self._codex_pkg_path(name), "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, issues = codex_core.validate_codex(data)
            return {"ok": True, "script": data, "valid": ok, "issues": issues}
        except FileNotFoundError:
            return {"ok": False, "err": "not found"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_codex_save(self, name, script_json):
        """保存剧本（校验 + 原子写盘）"""
        try:
            data = json.loads(script_json or "{}")
        except Exception as e:
            return {"ok": False, "err": "JSON 解析失败：" + str(e)[:120]}
        if not isinstance(data, dict):
            return {"ok": False, "err": "剧本必须是 JSON 对象"}
        data.setdefault("name", name)
        # 傻瓜化：保存时对位包内资源（粘贴/文本/AI 剧本统一受益）
        data = codex_core.normalize_script(data, pkg_dir=self._codex_pkg_path(name))
        ok, issues = codex_core.validate_codex(data)
        jp = os.path.join(self._codex_pkg_path(name), "codex.json")
        try:
            save_guard.atomic_write_json(jp, data)
        except Exception as e:
            return {"ok": False, "err": "写入失败：" + str(e)[:120]}
        return {"ok": True, "valid": ok, "issues": issues}

    def api_codex_validate(self, name):
        """重新校验剧本，返回 (valid, issues)"""
        jp = os.path.join(self._codex_pkg_path(name), "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, issues = codex_core.validate_codex(data)
            return {"ok": True, "valid": ok, "issues": issues}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}

    def api_codex_delete(self, name):
        """删除 CODEX 包（整个目录）"""
        import shutil
        d = self._codex_pkg_path(name)
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
            except Exception as e:
                return {"ok": False, "err": str(e)[:120]}
        return {"ok": True}

    def api_codex_export(self, name):
        """导出 CODEX 包为 zip（JSON 功能：分享/备份）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            safe = codex_core._safe_name(name)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=safe + ".zip",
                                         file_types=("CODEX 包 (*.zip)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            if not path.lower().endswith(".zip"):
                path += ".zip"
            if codex_core.export_zip(self._codex_pkg_path(name), path):
                return {"ok": True, "file": os.path.basename(path)}
            return {"ok": False, "err": "导出失败"}
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)[:120]}

    def api_codex_import_zip(self):
        """导入 CODEX zip 包"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("CODEX 包 (*.zip)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        ok, name, msg = codex_core.import_zip(res[0], self.codex_dir)
        return {"ok": ok, "name": name, "msg": msg}

    def api_codex_pack(self, name):
        """打包：把 CODEX 包生成独立单文件 HTML（GALGAME，双击即玩，可分发）。
        默认保存到包内 dist/ 目录，返回可直接打开/分发的路径。"""
        pkg = self._codex_pkg_path(name)
        dist_dir = os.path.join(pkg, "dist")
        try:
            os.makedirs(dist_dir, exist_ok=True)
            safe = codex_core._safe_name(name)
            out = os.path.join(dist_dir, safe + ".html")
            ok, path, counts = codex_core.build_standalone_file(pkg, out)
            if not ok:
                return {"ok": False, "err": "打包失败"}
            size = os.path.getsize(path)
            return {"ok": True, "path": path, "size": size,
                    "counts": counts, "rel": os.path.relpath(path, pkg).replace("\\", "/")}
        except Exception as e:
            return {"ok": False, "err": "打包失败：" + str(e)[:200]}

    def api_codex_pack_save_as(self, name):
        """打包并另存为（另存对话框选位置）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            safe = codex_core._safe_name(name)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=safe + ".html",
                                         file_types=("GALGAME (*.html)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            out = res[0]
            if not out.lower().endswith(".html"):
                out += ".html"
            ok, path, counts = codex_core.build_standalone_file(self._codex_pkg_path(name), out)
            if not ok:
                return {"ok": False, "err": "打包失败"}
            return {"ok": True, "path": path,
                    "size": os.path.getsize(path), "counts": counts}
        except Exception as e:
            return {"ok": False, "err": "打包失败：" + str(e)[:200]}

    # ---------- 打包 EXE（独立可执行，双击即玩） ----------
    def api_codex_pack_exe(self, name):
        """打包 CODEX 包为独立 EXE（后台线程，完成后可 api_codex_pack_exe_status 查询）。
        需要本机 Python 环境含 PyInstaller。输出到 codex/<包名>/dist/。"""
        import threading
        try:
            pkg = self._codex_pkg_path(name)
            if not os.path.isfile(os.path.join(pkg, "codex.json")):
                return {"ok": False, "err": "包不存在"}
            state_file = os.path.join(pkg, "dist", ".exe_build_state.json")
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump({"state": "building", "msg": "开始打包…"}, f)
            except Exception:
                pass
            threading.Thread(target=self._codex_exe_worker, args=(name,), daemon=True).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def _codex_exe_worker(self, name):
        """后台：打包 EXE + 写状态文件"""
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".exe_build_state.json")
        def set_state(st, msg, extra=None):
            d = {"state": st, "msg": msg}
            if extra:
                d.update(extra)
            # 原子写：前端轮询读取时不会读到写一半的残缺 JSON
            try:
                save_guard.atomic_write_json(state_file, d)
            except Exception:
                pass
        try:
            set_state("building", "正在生成独立播放器…")
            pkg = self._codex_pkg_path(name)
            out_dir = os.path.join(pkg, "dist")
            # 找可用的 python 解释器（优先当前；冻结运行时退回 PATH 里的 python）
            import sys as _sys
            py_cmd = None
            if not getattr(_sys, "frozen", False):
                py_cmd = _sys.executable
            set_state("building", "正在调用 PyInstaller（首次约 1-2 分钟）…")
            exe, counts = codex_core.build_standalone_exe(
                pkg, out_dir, name=name, py_cmd=py_cmd,
                log_cb=lambda m: set_state("building", m))
            set_state("done", "打包完成",
                      {"exe": os.path.basename(exe), "size": os.path.getsize(exe),
                       "counts": counts,
                       "rel": os.path.relpath(exe, pkg).replace("\\", "/")})
        except Exception as e:
            set_state("error", str(e)[:300])

    def api_codex_pack_exe_status(self, name):
        """查询打包 EXE 进度（前端轮询）"""
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".exe_build_state.json")
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return {"ok": True, **json.load(f)}
        except FileNotFoundError:
            return {"ok": True, "state": "idle", "msg": "尚未开始"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}

    # ---------- 导出到「叙事引擎」原生播放器（Kotlin，EXE / APK） ----------
    # 和上面「打包 HTML EXE」的区别：这里产出的是真正的原生窗口程序，
    # 引擎与渲染器分离，同一份 codex.json 还能喂给安卓 APK 和 DICK 主程序。

    PLAYER_DIRNAME = "DICK-Narrative"
    PLAYER_EXE = "DICK-Narrative.exe"

    def _find_player_dir(self):
        """找到已构建好的播放器目录（含 DICK-Narrative.exe）；没有返回 None。
        先试约定位置，再在数据目录（及下两层）里扫一遍，容忍用户随便放。"""
        exe = self.PLAYER_EXE

        def has_exe(d):
            try:
                return bool(d) and os.path.isfile(os.path.join(d, exe))
            except Exception:
                return False

        b = self.base_dir
        dev = os.path.join(self.PLAYER_DIRNAME, "app", "build", "compose",
                           "binaries", "main", "app", self.PLAYER_DIRNAME)
        name = self.PLAYER_DIRNAME
        up1 = os.path.dirname(b)          # dist\DICK-HTML → dist\dist
        up2 = os.path.dirname(up1)        # 再上一层：打包版 DICK 就靠这个找到工程里的播放器
        cands = [
            os.environ.get("DICK_PLAYER_DIR"),
            os.path.join(b, dev),                              # 开发：构建输出
            os.path.join(b, "player", name),
            os.path.join(b, name + "-播放器"),
            os.path.join(b, "播放器", name),
            os.path.join(b, "播放器"),
            os.path.join(b, name),
            # 上一层 / 上两层：兼容「DICK-HTML 在子目录、播放器在工程根」这种布局
            os.path.join(up1, dev),
            os.path.join(up1, name + "-播放器"),
            os.path.join(up1, name),
            os.path.join(up2, dev),
            os.path.join(up2, name + "-播放器"),
            os.path.join(up2, name),
        ]
        for c in cands:
            if has_exe(c):
                return c

        # 兜底扫描：数据目录本身 → 一层子目录 → 两层子目录
        def subdirs(d):
            try:
                return [os.path.join(d, n) for n in sorted(os.listdir(d))
                        if os.path.isdir(os.path.join(d, n))]
            except Exception:
                return []

        for d in [b] + subdirs(b) + subdirs(up1) + subdirs(up2):
            if has_exe(d):
                return d
            for d2 in subdirs(d):
                if has_exe(d2):
                    return d2
        return None

    @staticmethod
    def _player_size_mb(path):
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
        return round(total / 1048576.0, 1)

    def api_codex_export_player(self, name):
        """把 CODEX 包导出成「播放器 + 故事」的成品目录（后台线程）。
        产出结构：
            <目标目录>/<包名>/
                DICK-Narrative.exe  app/  runtime/    ← 原生播放器（自带运行时）
                story/codex.json  sprites/ bg/ bgm/ voice/
                玩这个.txt
        """
        try:
            pkg = self._codex_pkg_path(name)
            if not os.path.isfile(os.path.join(pkg, "codex.json")):
                return {"ok": False, "err": "包不存在"}
            player = self._find_player_dir()
            if not player:
                return {"ok": False,
                        "err": "还没构建播放器。先在 DICK-Narrative 目录跑一次 build.ps1 -Exe，"
                               "或把窗口里的「目标目录」指到已构建好的播放器上。"}
            # 选目标目录（默认桌面）
            dest_root = None
            try:
                import webview
                win = webview.windows[0] if getattr(webview, "windows", None) else None
                if win is not None:
                    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                    res = win.create_file_dialog(
                        webview.FileDialog.FOLDER,
                        directory=desktop if os.path.isdir(desktop) else os.path.expanduser("~"))
                    if not res:
                        return {"ok": False, "err": "cancelled"}
                    dest_root = res[0]
            except Exception:
                dest_root = None
            if not dest_root:
                dest_root = os.path.join(pkg, "dist", "player")

            safe = codex_core._safe_name(name)
            dest = os.path.join(dest_root, safe)
            state_file = os.path.join(pkg, "dist", ".player_build_state.json")
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                save_guard.atomic_write_json(state_file,
                                             {"state": "building", "msg": "准备导出…"})
            except Exception:
                pass
            threading.Thread(target=self._codex_player_worker,
                             args=(name, player, dest, state_file),
                             daemon=True).start()
            return {"ok": True, "dest": dest}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def _codex_player_worker(self, name, player, dest, state_file):
        """后台：拷播放器 + 放故事，并写状态文件"""
        def set_state(st, msg, extra=None):
            d = {"state": st, "msg": msg}
            if extra:
                d.update(extra)
            try:
                save_guard.atomic_write_json(state_file, d)
            except Exception:
                pass
        try:
            import shutil
            pkg = self._codex_pkg_path(name)

            set_state("building", "正在复制播放器（约 127 MB，第一次稍慢）…")
            if os.path.isdir(dest):
                # 删不干净通常是播放器还开着（exe 被占用）→ 说人话，别抛 WinError
                try:
                    shutil.rmtree(dest)
                except Exception:
                    locked = []
                    for root, _dirs, files in os.walk(dest):
                        for fn in files:
                            try:
                                os.remove(os.path.join(root, fn))
                            except Exception:
                                locked.append(fn)
                    if locked:
                        set_state("error",
                                  "目标目录里有文件正被占用（多半是播放器还开着）："
                                  + "、".join(sorted(set(locked))[:5])
                                  + " —— 请先关掉 DICK-Narrative.exe 再导出。")
                        return
                    shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)
            shutil.copytree(player, dest, dirs_exist_ok=True)

            set_state("building", "正在放入故事与素材…")
            story = os.path.join(dest, "story")
            # 播放器自带一份示例故事，导出时必须清掉，否则会和你的故事打架
            shutil.rmtree(story, ignore_errors=True)
            os.makedirs(story, exist_ok=True)
            shutil.copy2(os.path.join(pkg, "codex.json"),
                         os.path.join(story, "codex.json"))
            counts = {}
            for kind in codex_core.SUBDIRS:
                src = os.path.join(pkg, kind)
                n = 0
                if os.path.isdir(src):
                    dst = os.path.join(story, kind)
                    os.makedirs(dst, exist_ok=True)
                    for fn in sorted(os.listdir(src)):
                        sp = os.path.join(src, fn)
                        if os.path.isfile(sp):
                            shutil.copy2(sp, os.path.join(dst, fn))
                            n += 1
                counts[kind] = n

            readme = os.path.join(dest, "玩这个.txt")
            try:
                with open(readme, "w", encoding="utf-8") as f:
                    f.write(
                        "《%s》\n\n"
                        "双击 DICK-Narrative.exe 就能玩。\n"
                        "整个文件夹要一起拷走（runtime 和 app 是播放器自带的运行环境）。\n\n"
                        "操作：鼠标点任意处推进 / 空格回车推进 / Esc 打开菜单\n"
                        "剧情分支会按好感度、状态、标记自动筛选。\n" % name)
            except Exception:
                pass

            size = self._player_size_mb(dest)
            set_state("done", "导出完成",
                      {"dest": dest, "size": size, "counts": counts,
                       "rel": os.path.basename(dest)})
        except Exception as e:
            set_state("error", str(e)[:300])

    def api_codex_player_status(self, name):
        """查询「导出到播放器」进度（前端轮询）"""
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".player_build_state.json")
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return {"ok": True, **json.load(f)}
        except FileNotFoundError:
            return {"ok": True, "state": "idle", "msg": "尚未开始"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}

    def api_codex_player_ready(self):
        """播放器是否已构建（前端用来提示/禁用按钮）"""
        p = self._find_player_dir()
        return {"ok": True, "ready": bool(p), "dir": p or ""}

    # ================= CODEX 系统权限（DICK 内置特权引擎） =================

    def api_codex_register_assoc(self):
        """注册 .codex 文件关联：双击 .codex 包 → 用 DICK 打开播放。
        写 HKCU 注册表（无需管理员）。返回 (ok, msg)。"""
        try:
            import winreg
            exe = os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else \
                os.path.join(BASE_DIR, "DICK-HTML.exe")
            if not os.path.isfile(exe):
                exe = sys.executable
            # 1) ProgID
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\DICK.Codex\shell\open\command") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, f'"{exe}" "%1"')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\DICK.Codex\DefaultIcon") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, f'"{exe}",0')
            # 2) 扩展名关联
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\.codex") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, "DICK.Codex")
            return {"ok": True, "msg": "✅ 已注册：双击 .codex 包将直接用 DICK 打开播放"}
        except Exception as e:
            return {"ok": False, "err": "注册失败：" + str(e)[:200]}

    def api_codex_export_codex(self, name):
        """导出 .codex 包（系统权限：保存到用户选的任意位置，双击即可在 DICK 打开）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            safe = codex_core._safe_name(name)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=safe + ".codex",
                                         file_types=("CODEX 包 (*.codex)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            if not path.lower().endswith(".codex"):
                path += ".codex"
            if codex_core.export_zip(self._codex_pkg_path(name), path):
                return {"ok": True, "file": os.path.basename(path)}
            return {"ok": False, "err": "导出失败"}
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)[:200]}

    def api_codex_import_codex(self):
        """导入 .codex 包（系统权限：从任意位置选文件，自动解包到 codex/）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("CODEX 包 (*.codex)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        ok, name, msg = codex_core.import_zip(res[0], self.codex_dir)
        return {"ok": ok, "name": name, "msg": msg}

    def api_codex_import_script(self, text):
        """傻瓜化：粘贴剧本自动转化为 codex.json。支持两种输入：
        - 文本以 '{' 开头 → 当作 codex.json 直接规整（补默认、对位资源）；
        - 否则 → 纯文本剧本（parse_script_text 解析）。
        不落盘，返回 {ok, script, valid, issues, kind, autoName}，前端预览后保存。"""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "err": "empty"}
        kind = "text"
        data = None
        if text.startswith("{"):
            try:
                data = json.loads(text)
                kind = "json"
            except Exception:
                data = None
        if data is None:
            data = codex_core.parse_script_text(text)
            if data is None:
                if text.startswith("{"):
                    return {"ok": False, "err": "JSON 解析失败"}
                return {"ok": False,
                        "err": "无法识别剧本格式（首行用【场景】标题，或用 > 旁白、角色名：台词）"}
            kind = "text"
        data = codex_core.normalize_script(data)
        ok, issues = codex_core.validate_codex(data)
        return {"ok": True, "script": data, "valid": ok, "issues": issues,
                "kind": kind, "autoName": str(data.get("name") or "").strip() or "未命名剧本"}

    def api_codex_import_sprites(self, name):
        """立绘傻瓜化导入：多选图片 → 放入包内 sprites/，自动按角色名/顺序把缺立绘的
        台词挂上立绘并保存。返回 {ok, added, wired, msg}。"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=True,
                file_types=("图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        if not isinstance(res, (list, tuple)):
            res = [res]
        pkg = self._codex_pkg_path(name)
        sprites_dir = os.path.join(pkg, "sprites")
        os.makedirs(sprites_dir, exist_ok=True)
        import shutil as _sh
        added = []
        for src in res:
            base = os.path.basename(str(src))
            ext = os.path.splitext(base)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                continue
            out = os.path.join(sprites_dir, base)
            i = 1
            while os.path.exists(out):
                stem, e = os.path.splitext(base)
                out = os.path.join(sprites_dir, f"{stem}_{i}{e}")
                i += 1
            try:
                _sh.copy2(src, out)
                added.append(os.path.basename(out))
            except Exception:
                pass
        if not added:
            return {"ok": False, "err": "未导入任何图片"}
        wired = self._wire_sprites_to_speakers(name)
        return {"ok": True, "added": added, "wired": wired,
                "msg": f"导入 {len(added)} 张立绘，自动挂接 {wired} 处台词"}

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

    def api_codex_get_player_template(self, name):
        """高级模式：返回可编辑的播放器模板源码。包内若有 player.html（自定义）则用之，
        否则返回系统内置模板。name 为空时恒返回系统内置模板（用于“恢复默认”）。"""
        try:
            if not (name or "").strip():
                return {"ok": True, "html": codex_core.DEFAULT_EDITABLE_TEMPLATE, "is_custom": False}
            pkg = self._codex_pkg_path(name)
            tpl = codex_core._load_custom_template(pkg)
            if tpl is not None:
                return {"ok": True, "html": tpl, "is_custom": True}
            return {"ok": True, "html": codex_core.DEFAULT_EDITABLE_TEMPLATE, "is_custom": False}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_codex_save_player_template(self, name, html):
        """高级模式：保存自定义播放器模板到包内 player.html。模板需保留 __CODEX_PAYLOAD__ 注入点。"""
        html = (html or "").strip()
        if not html:
            return {"ok": False, "err": "empty"}
        if "__CODEX_PAYLOAD__" not in html and "__CODEX_EMBED__" not in html:
            return {"ok": False, "err": "模板需保留 __CODEX_PAYLOAD__（或 __CODEX_EMBED__）数据注入点"}
        try:
            pkg = self._codex_pkg_path(name)
            pt = os.path.join(pkg, "player.html")
            with open(pt, "w", encoding="utf-8") as f:
                f.write(html)
            return {"ok": True, "msg": "模板已保存"}
        except Exception as e:
            return {"ok": False, "err": "保存失败：" + str(e)[:200]}

    def api_codex_render(self, name, html=None):
        """高级模式：用给定模板实时渲染包为独立 HTML（现场试玩）。
        html 为空则用包内自定义/系统默认模板。返回 {ok, html}。"""
        try:
            pkg = self._codex_pkg_path(name)
            if html and html.strip():
                tpl = html
            else:
                tpl = codex_core._load_custom_template(pkg)
            out, _counts = codex_core.render_standalone(pkg, tpl, state=getattr(self.core, "mechanism_state", None))
            return {"ok": True, "html": out}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_codex_run_program(self, cmd):
        """系统权限：执行本地程序/命令（action 钩子扩展）。
        cmd 是命令字符串，如 notepad.exe 或 完整路径。仅限一次调用，不做 shell 拼接注入。"""
        cmd = (cmd or "").strip()
        if not cmd:
            return {"ok": False, "err": "empty"}
        # 安全检查：只允许 exe/bat/cmd/vbs 直接执行；含 & | ; 等拼接符拒绝
        import re as _re
        if _re.search(r"[&|;><`]", cmd):
            return {"ok": False, "err": "禁止命令拼接"}
        low = cmd.lower().split()
        first = low[0] if low else ""
        if not (first.endswith(".exe") or first.endswith(".bat") or first.endswith(".cmd")
                or first in ("notepad", "calc", "mspaint", "explorer", "cmd", "start")):
            return {"ok": False, "err": "仅允许可执行程序"}
        try:
            import subprocess
            subprocess.Popen(cmd, shell=False)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_codex_volume(self, level):
        """多媒体权限：设置播放器音量（0-100）。返回当前音量。"""
        try:
            level = max(0, min(100, int(level)))
        except (TypeError, ValueError):
            level = 100
        self.codex_volume = level
        return {"ok": True, "volume": level}

    def api_codex_fullscreen(self):
        """多媒体权限：CODEX 播放器全屏独占（pywebview 窗口切换）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            win.toggle_fullscreen()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def api_codex_clear_auto_open(self):
        """清除双击打开标记（前端播放器启动后调用，避免重复弹窗）"""
        self.codex_auto_open = None
        return {"ok": True}


    def api_codex_release(self, name):
        """两步发布（决战兵器·分发闭环）：一键打包 EXE + HTML + .codex 三件套到包内 dist/。
        后台线程执行，api_codex_pack_exe_status 轮询进度。"""
        import threading
        try:
            pkg = self._codex_pkg_path(name)
            if not os.path.isfile(os.path.join(pkg, "codex.json")):
                return {"ok": False, "err": "包不存在"}
            state_file = os.path.join(pkg, "dist", ".exe_build_state.json")
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump({"state": "building", "msg": "开始发布…"}, f)
            except Exception:
                pass
            threading.Thread(target=self._codex_release_worker, args=(name,), daemon=True).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def _codex_release_worker(self, name):
        """后台：发布三件套（HTML → EXE → .codex）"""
        import sys as _sys
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".exe_build_state.json")
        def set_state(st, msg, extra=None):
            d = {"state": st, "msg": msg}
            if extra:
                d.update(extra)
            # 原子写：前端轮询读取时不会读到写一半的残缺 JSON
            try:
                save_guard.atomic_write_json(state_file, d)
            except Exception:
                pass
        try:
            pkg = self._codex_pkg_path(name)
            out_dir = os.path.join(pkg, "dist")
            os.makedirs(out_dir, exist_ok=True)
            safe = codex_core._safe_name(name)
            set_state("building", "① 生成独立 HTML…")
            ok, path, counts = codex_core.build_standalone_file(pkg, os.path.join(out_dir, safe + ".html"))
            if not ok:
                set_state("error", "HTML 打包失败")
                return
            # ② EXE
            set_state("building", "② 打包 EXE（首次约 1-2 分钟）…")
            py_cmd = None if getattr(_sys, "frozen", False) else _sys.executable
            exe, counts = codex_core.build_standalone_exe(pkg, out_dir, name=name, py_cmd=py_cmd)
            # ③ .codex
            set_state("building", "③ 生成 .codex 包…")
            codex_path = os.path.join(out_dir, safe + ".codex")
            codex_core.export_zip(pkg, codex_path)
            set_state("done", "发布完成：EXE + HTML + .codex",
                      {"exe": os.path.basename(exe),
                       "html": safe + ".html",
                       "codex": safe + ".codex",
                       "size_exe": os.path.getsize(exe),
                       "size_html": os.path.getsize(os.path.join(out_dir, safe + ".html")),
                       "size_codex": os.path.getsize(codex_path),
                       "rel": "dist",
                       "counts": counts})
        except Exception as e:
            set_state("error", str(e)[:300])



    def api_codex_asset(self, name, kind, file):
        """返回 CODEX 包内资源的 dataURL（播放器/预览用）。
        kind: sprites/bg/bgm/voice；file: 相对该 kind 目录的文件名"""
        kind = (kind or "").lower()
        if kind not in codex_core.SUBDIRS:
            return {"ok": False, "err": "bad kind"}
        base = os.path.basename((file or "").replace("\\", "/"))
        if not base:
            return {"ok": False, "err": "bad file"}
        p = os.path.join(self._codex_pkg_path(name), kind, base)
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except Exception:
            return {"ok": False, "err": "not found"}
        import base64 as _b64
        ext = os.path.splitext(base)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif",
                ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
                ".flac": "audio/flac", ".mp4": "audio/mp4", ".m4a": "audio/mp4"}.get(ext, "application/octet-stream")
        return {"ok": True, "data": "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")}

    # 素材类型 → (文件对话框说明, 允许的扩展名)
    ASSET_KINDS = {
        "sprites": ("图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)", (".png", ".jpg", ".jpeg", ".webp", ".gif")),
        "bg": ("图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)", (".png", ".jpg", ".jpeg", ".webp", ".gif")),
        "bgm": ("音频 (*.mp3;*.wav;*.ogg;*.flac;*.m4a)", (".mp3", ".wav", ".ogg", ".flac", ".m4a")),
        "voice": ("音频 (*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.mp4)", (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4")),
    }

    def api_codex_import_asset(self, name, kind):
        """把素材文件导入包内对应目录（sprites/bg/bgm/voice），支持多选。
        返回 {ok, added:[文件名], files:{按类型分组}}，方便前端刷新下拉。"""
        if kind not in codex_core.SUBDIRS:
            return {"ok": False, "err": "未知素材类型：" + str(kind)}
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            desc, _exts = self.ASSET_KINDS[kind]
            res = win.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                         file_types=(desc, "所有文件 (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        if not isinstance(res, (list, tuple)):
            res = [res]
        ok_exts = self.ASSET_KINDS[kind][1]
        dst_dir = os.path.join(self._codex_pkg_path(name), kind)
        os.makedirs(dst_dir, exist_ok=True)
        import shutil as _sh
        added = []
        for src in res:
            base = os.path.basename(str(src))
            if os.path.splitext(base)[1].lower() not in ok_exts:
                continue
            out = os.path.join(dst_dir, base)
            i = 1
            while os.path.exists(out):
                stem, e = os.path.splitext(base)
                out = os.path.join(dst_dir, f"{stem}_{i}{e}")
                i += 1
            try:
                _sh.copy2(src, out)
                added.append(os.path.basename(out))
            except Exception:
                pass
        if not added:
            return {"ok": False, "err": "没有导入任何文件（格式不支持？）"}
        files = self.api_codex_script_files(name).get("files", {})
        return {"ok": True, "added": added, "files": files}

    def api_codex_script_files(self, name):
        """列出包内全部资源文件（按 kind 分组）——播放器/编辑器引用列表"""
        out = {k: [] for k in codex_core.SUBDIRS}
        for kind in codex_core.SUBDIRS:
            kd = os.path.join(self._codex_pkg_path(name), kind)
            if os.path.isdir(kd):
                try:
                    out[kind] = sorted(x for x in os.listdir(kd)
                                       if os.path.isfile(os.path.join(kd, x)))
                except Exception:
                    pass
        return {"ok": True, "files": out}

    # ================= 围棋（规则引擎 + 提示词注入） =================
    # 设计：规则全部由 go_engine 决定，模型只负责「从候选点里挑一个 + 说台词」。
    # 19 路每步有 250+ 合法点，ASCII 坐标又不携带形状信息，让模型自由算棋必乱下；
    # 所以每轮把引擎挑出的候选点一起注入，模型选，引擎校验。

    def _go_game(self):
        return getattr(self, "_go", None)

    # 棋风关键词：从角色卡的性格描述里推断，让「性格」真的影响落子而不只是台词
    GO_STYLE_WORDS = {
        "aggressive": ["好战", "激进", "暴躁", "强势", "攻击", "争强", "不服输", "凶", "狠",
                       "狂妄", "挑衅", "火爆", "嗜血", "暴虐", "战斗", "危险", "咄咄"],
        "solid": ["谨慎", "稳重", "冷静", "沉着", "细腻", "保守", "理性", "严谨", "稳健",
                  "小心", "缜密", "沉稳", "克制", "耐心", "踏实"],
        "proud": ["骄傲", "自负", "自信", "高傲", "目中无人", "天才", "自恋", "优越",
                  "高贵", "不屑", "傲慢", "大小姐", "冷淡"],
        "playful": ["随性", "懒", "散漫", "调皮", "顽皮", "跳脱", "漫不经心", "任性",
                    "胡闹", "活泼", "开朗", "天真", "好奇", "贪玩"],
    }
    GO_STYLE_LABEL = {
        "aggressive": "好战 —— 喜欢贴身纠缠、追杀、叫吃",
        "solid": "稳重 —— 喜欢连接、围地、稳扎稳打",
        "proud": "高傲 —— 喜欢占大场星位做模样，不屑贴身缠斗",
        "playful": "随性 —— 下得跳脱，偶尔神来一笔或随手一着",
        "balanced": "均衡 —— 该怎么下怎么下",
    }

    # ── 好感度 → 棋局设定（想调难度就改这里）────────────────────
    # 格式：(好感下限, 让子数, 放水概率, 关系描述)
    #
    # 让子数上限是 1 —— 再多就不像在下棋了，而是像在哄人。
    # 所以【放水概率】才是真正决定难度的那一列，想让棋更轻松就调它。
    # 真要让更多子：改下面的 GO_MAX_HANDICAP（引擎支持到 9 子），
    # 同时记得把这张表里对应档位的让子数一起改大。
    GO_MAX_HANDICAP = 1
    GO_KOMI_PER_HANDICAP = 5.0     # 玩家执白时，1 子折成多少目贴还给他

    GO_AFF_TIERS = [
        (85, 1, 0.30, "很亲近，愿意让着你一子"),
        (70, 1, 0.20, "关系不错，会不自觉地放水"),
        (50, 1, 0.05, "还算熟，让一子客气一下"),
        (0, 0, 0.00, "还没什么交情，不留情"),
    ]

    def _go_settings(self):
        """按好感度算出这盘的让子数 / 放水概率 / 额外贴目"""
        aff = 50
        try:
            v = (self.core.mechanism_state or {}).get("affection")
            if isinstance(v, (int, float)):
                aff = v
        except Exception:
            pass
        handicap, mercy, mood = 0, 0.0, self.GO_AFF_TIERS[-1][3]
        for lo, h, m, label in self.GO_AFF_TIERS:
            if aff >= lo:
                handicap, mercy, mood = h, m, label
                break
        # 上限在这里再夹一次：以后有人把表里的数字改大了，也不会真的多让子
        handicap = max(0, min(int(handicap), self.GO_MAX_HANDICAP))
        human = getattr(self, "_go_human", "black")
        komi_extra = 0.0
        if human == "white":
            # 玩家执白时没法给他让子，改成多贴目（她吃亏）
            komi_extra = handicap * self.GO_KOMI_PER_HANDICAP
            handicap = 0
        return {"aff": aff, "handicap": handicap, "mercy": mercy,
                "komi_extra": komi_extra, "mood": mood}

    def api_go_settings(self):
        """给界面显示「这盘棋她打算怎么跟你下」"""
        st = self._go_settings()
        b = self._go_game()
        st["ok"] = True
        st["human"] = getattr(self, "_go_human", "black")
        st["size"] = b.size if b else 19
        st["style"] = self._go_style()
        st["style_label"] = self.GO_STYLE_LABEL.get(st["style"], "")
        st["komi"] = b.komi if b else 7.5
        return st

    def _go_style(self):
        """从当前角色卡推断棋风；好感度也会影响（低→更冲，高→更稳）"""
        try:
            roles = getattr(self.core, "active_roles", None) or []
            text = ""
            for r in roles[:1]:
                if not isinstance(r, dict):
                    continue
                for k in ("personality", "description", "scenario", "name", "system_prompt"):
                    v = r.get(k)
                    if isinstance(v, str):
                        text += v + "\n"
            scores = {}
            for st, words in self.GO_STYLE_WORDS.items():
                scores[st] = sum(text.count(w) for w in words)
            best = "balanced"
            if scores:
                cand = max(scores, key=lambda k: scores[k])
                if scores[cand] > 0:
                    best = cand
            # 机制卡联动：好感度低时更冲，高时更稳（只在没明显性格倾向时生效）
            if best == "balanced":
                aff = None
                try:
                    aff = (self.core.mechanism_state or {}).get("affection")
                except Exception:
                    aff = None
                if isinstance(aff, (int, float)):
                    if aff < 30:
                        best = "aggressive"
                    elif aff >= 80:
                        best = "solid"
            return best
        except Exception:
            return "balanced"

    def _go_note(self, text):
        log = getattr(self, "_go_log", None)
        if log is None:
            log = self._go_log = []
        log.append(text)
        if len(log) > 200:
            del log[:-200]

    def api_go_new(self, size=19, human_color="black", komi=7.5):
        """开新局。human_color: 'black' 或 'white'"""
        try:
            import go_engine as ge
        except Exception as e:
            return {"ok": False, "err": "围棋引擎缺失：" + str(e)[:120]}
        try:
            size = int(size or 19)
        except Exception:
            size = 19
        if size not in (9, 13, 19):
            size = 19
        b = ge.new_game(size=size, komi=float(komi or 7.5))
        self._go = b
        human = "white" if str(human_color).lower().startswith("w") else "black"
        self._go_human = human
        self._go_log = []
        st = self._go_settings()
        if human == "black" and st["handicap"]:
            n = b.setup_handicap(st["handicap"])
            self._go_note("让子局：她让你 %d 子（好感度 %d，%s）" % (n, st["aff"], st["mood"]))
        elif human == "white" and st["komi_extra"]:
            b.komi += st["komi_extra"]
            self._go_note("她多贴 %.1f 目给你（好感度 %d，%s）" % (st["komi_extra"], st["aff"], st["mood"]))
        self._go_note("开新局：%d 路，你执%s，贴目 %.1f，她的棋风「%s」" %
                      (size, "黑" if human == "black" else "白", b.komi,
                       self.GO_STYLE_LABEL.get(self._go_style(), "均衡").split(" —— ")[0]))
        self._go_maybe_ai_first()
        return {"ok": True, "state": b.state(), "human": human,
                "settings": st, "log": self._go_log[-6:]}

    def api_go_state(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        try:
            cands = [c["display"] for c in b.candidates(limit=6)]
        except Exception:
            cands = []
        st = self._go_settings()
        st["style_label"] = self.GO_STYLE_LABEL.get(self._go_style(), "")
        return {"ok": True, "state": b.state(),
                "human": getattr(self, "_go_human", "black"),
                "candidates": cands,
                "settings": st,
                "log": getattr(self, "_go_log", [])[-10:]}

    def api_go_play(self, x, y):
        """玩家落子（x,y 为 0 起算的内部坐标）。落完自动触发 AI 回手。"""
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        r = b.play(int(x), int(y))
        if not r["ok"]:
            return {"ok": False, "err": r["reason"]}
        self._go_note("你落子 %s%s" % (r["display"],
                                    ("，提 %d 子" % len(r["captured"])) if r["captured"] else ""))
        if b.finished:
            return {"ok": True, "state": b.state(), "ended": True, "log": self._go_log[-6:]}
        self._go_ai_turn("我下在 %s。" % r["display"])
        return {"ok": True, "state": b.state(), "log": self._go_log[-6:]}

    def api_go_pass(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        r = b.pass_turn()
        self._go_note("你停一手")
        if r.get("ended") or b.finished:
            return {"ok": True, "state": b.state(), "ended": True, "log": self._go_log[-6:]}
        self._go_ai_turn("我停一手（pass）。")
        return {"ok": True, "state": b.state(), "log": self._go_log[-6:]}

    def api_go_undo(self):
        """悔棋：退回到自己上一次落子之前（退两手：AI 一手 + 自己一手）。"""
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        n = 0
        for _ in range(2):
            if b.undo()["ok"]:
                n += 1
        if n:
            self._go_note("悔棋 %d 手" % n)
        return {"ok": True, "state": b.state(), "undone": n, "log": self._go_log[-6:]}

    def api_go_resign(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        import go_engine as ge
        human = getattr(self, "_go_human", "black")
        color = ge.BLACK if human == "black" else ge.WHITE
        r = b.resign(color)
        self._go_note("你认输 —— " + b.result)
        return {"ok": True, "state": b.state(), "result": b.result}

    def api_go_score(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        s = b.score()
        return {"ok": True, "score": s}

    def _go_ai_first(self):
        """玩家执白时，开局让 AI 先走"""
        b = self._go_game()
        human = getattr(self, "_go_human", "black")
        if b is None or b.finished:
            return
        ai_black = (human == "white")
        if ai_black and b.to_move == b.BLACK and len(b.moves) == 0:
            self._go_ai_turn("（对局开始，你执黑先行。）")

    def _go_maybe_ai_first(self):
        try:
            self._go_ai_first()
        except Exception:
            pass

    def _go_prompt_block(self):
        """构造注入给模型的棋盘说明 + 候选点"""
        import go_engine as ge
        b = self._go_game()
        human = getattr(self, "_go_human", "black")
        ai_color = "白" if human == "black" else "黑"
        my_mark = "O" if ai_color == "白" else "X"
        cands = []
        style = self._go_style()
        gs = self._go_settings()
        try:
            cands = b.candidates(b.to_move, limit=6, style=style, mercy=gs["mercy"])
        except Exception:
            pass
        lines = []
        lines.append("你执%s（棋盘上 %s 是你的子），对方执%s。" % (ai_color, my_mark,
                                                            "黑" if ai_color == "白" else "白"))
        lines.append("你的棋风：%s。选点请贴合你的性格。" %
                     self.GO_STYLE_LABEL.get(style, self.GO_STYLE_LABEL["balanced"]))
        # 好感度 → 这盘棋的设定（让子/放水），让她的态度和棋局一致
        if gs["handicap"]:
            lines.append("这是让子局：你让了对方 %d 子。你们的关系——%s。"
                         "可以偶尔手软，但别放得太明显，输了也别恼。" % (gs["handicap"], gs["mood"]))
        elif gs["komi_extra"]:
            lines.append("你多贴了 %.1f 目给对方，是让着她的。你们的关系——%s。"
                         % (gs["komi_extra"], gs["mood"]))
        else:
            lines.append("分先对局，关系——%s。不必留情，全力下。" % gs["mood"])
        lines.append("")
        lines.append("当前棋盘（X=黑子 O=白子 .=空；列 A-T 跳过 I，行 1-19 自下往上）：")
        lines.append(b.to_ascii())
        lines.append("")
        st = b.score()
        ai_stone = ge.BLACK if ai_color == "黑" else ge.WHITE
        opp_stone = ge.WHITE if ai_color == "黑" else ge.BLACK
        lines.append("已提子：你 %d 子，对方 %d 子。已下 %d 手。" %
                     (b.captured[ai_stone], b.captured[opp_stone], len(b.moves)))
        if cands:
            lines.append("")
            lines.append("【引擎给你的候选点】这几个点都不错，**优先从里面挑一个**：")
            for i, c in enumerate(cands, 1):
                lines.append("   %d. %s —— %s" % (i, c["display"], c["why"]))
        lines.append("")
        lines.append("要求：")
        lines.append("1. 落子必须是**空点**、且不能让你的子自杀；不要下在刚被提掉的打劫点上。")
        lines.append("2. 回复里**必须**用一个坐标明确说出你下在哪里，例如「我下在 Q16」。")
        lines.append("3. 再用你自己的口吻说一两句台词，体现性格（可以吐槽棋局、可以挑衅、可以紧张）。")
        lines.append("4. 不要解释规则，不要输出棋盘。")
        return "\n".join(lines)

    def _go_ai_turn(self, user_line=""):
        """轮到 AI：把棋盘注入 pending_event，然后发一句话触发请求"""
        b = self._go_game()
        if b is None or b.finished:
            return
        human = getattr(self, "_go_human", "black")
        if (b.to_move == b.BLACK) == (human == "black"):
            return                                    # 还没轮到 AI
        try:
            blocks = [self._go_prompt_block()]
            fix = getattr(self, "_go_fix", None)
            if fix:
                blocks.append("")
                blocks.append("【上一手被驳回】%s 请重新选一个合法的点。" % fix)
                self._go_fix = None
            self.core.pending_event = {
                "id": "_go_turn", "name": "围棋·轮到你",
                "prompt": "\n".join(blocks),
            }
        except Exception as e:
            self._append_sys("围棋：注入失败 %s" % str(e)[:120])
            return
        self._send_text(user_line or "（轮到你落子）", None, None)

    def _go_parse_move(self, reply):
        """从回复里解析落子坐标。返回 (x,y) 或 None。
        优先命中引擎给的候选点；否则取最后一个合法坐标。"""
        import re as _re
        b = self._go_game()
        if b is None or not reply:
            return None
        pat = _re.compile(r"(?<![A-Za-z0-9])([A-HJ-Ta-hj-t])\s?(\d{1,2})(?![0-9])")
        found = []
        for m in pat.finditer(str(reply)):
            xy = b.from_display(m.group(1) + m.group(2))
            if xy and xy not in found:
                found.append(xy)
        if not found:
            return None
        try:
            cand = [(c["x"], c["y"]) for c in b.candidates(b.to_move, limit=8, style=self._go_style())]
        except Exception:
            cand = []
        for xy in found:                      # 先看是不是候选点
            if xy in cand and b.is_legal(xy[0], xy[1])[0]:
                return xy
        for xy in reversed(found):            # 再退而求其次：最后一个能下的
            if b.is_legal(xy[0], xy[1])[0]:
                return xy
        return None

    def _go_after_reply(self, reply):
        """模型回复落地后的钩子：解析并落子。解析不到就引擎兜底，保证棋局永远能推进。"""
        import threading as _th
        b = self._go_game()
        if b is None or b.finished:
            return
        human = getattr(self, "_go_human", "black")
        if (b.to_move == b.BLACK) == (human == "black"):
            return                                    # 现在不是 AI 的回合
        xy = self._go_parse_move(reply)
        if xy is not None:
            r = b.play(xy[0], xy[1])
            if r["ok"]:
                self._go_note("对手落子 %s%s" % (r["display"],
                                             ("，提 %d 子" % len(r["captured"])) if r["captured"] else ""))
                if b.finished:
                    self._go_note("终局：" + b.result)
                return
            reason = r.get("reason") or "非法手"
        else:
            reason = "回复里没找到可用的坐标"

        # 驳回重选：最多重试 1 次；延迟一下让本轮 _on_response 先跑完（busy 复位）
        tries = getattr(self, "_go_retry", 0)
        if tries < 1:
            self._go_retry = tries + 1
            self._go_fix = reason
            self._go_note("⚠ 对手这一手有问题（%s），让它重选一次" % reason)
            try:
                _th.Timer(0.8, lambda: self._go_ai_turn("（刚才那手不行，重选一个点）")).start()
                return
            except Exception:
                pass

        # 兜底：引擎替它落一手，棋局绝不停住
        self._go_retry = 0
        try:
            cands = b.candidates(b.to_move, limit=1)
        except Exception:
            cands = []
        if cands:
            c = cands[0]
            r = b.play(c["x"], c["y"])
            if r["ok"]:
                self._go_note("⚠ 对手没给出合法坐标，裁判代落 %s（%s）" % (r["display"], c["why"]))
                if b.finished:
                    self._go_note("终局：" + b.result)

    def api_go_ai(self):
        """手动让 AI 走一手（调试/补救用）"""
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        self._go_retry = 0
        self._go_ai_turn("（继续）")
        return {"ok": True, "state": b.state()}

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
            # 优先 [ja] 日配句
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

    def api_offline_peek(self):
        """看看"你不在的时候世界走了多少" —— 只出方案，什么都不改。"""
        p = self._offline_plan()
        return {"ok": bool(p.get("ok")), "proposal": p, "key": self._offline_key()}

    def api_offline_apply(self, accept=True):
        """应用（accept=True）或忽略（False）刚算出的离线推进。

        应用会改机制状态并往聊天里插一条系统消息（可读的时间说明）；
        忽略则只记下"这段时间处理过了"，避免下次启动又弹一遍。
        两条路都会更新记账点 —— 这是防重复提示的关键。
        """
        import offline_advance
        try:
            p = self._offline_plan()
        except Exception as e:
            return {"ok": False, "err": "计算失败：" + str(e)[:120]}
        if not p.get("ok"):
            return {"ok": False, "err": p.get("skipped") or "没有需要推进的时间"}
        key = self._offline_key()
        # 记账：无论应用还是忽略，都把这局的"已处理到"推进到这次的上次互动时间
        try:
            book = dict(self.config.get("offline_dismissed") or {})
            book[key] = p.get("last_active")
            self.config["offline_dismissed"] = book
        except Exception:
            pass
        if not accept:
            self._save_config()
            return {"ok": True, "applied": False, "summary": p["summary"]}
        undo = None
        try:
            undo = offline_advance.apply(p, self.core.mechanism_state)
        except Exception as e:
            return {"ok": False, "err": "应用失败：" + str(e)[:140]}
        if not undo:
            self._save_config()
            return {"ok": True, "applied": False, "summary": p["summary"],
                    "note": "这次没有数值变化，只推进了时间记账"}
        # 进聊天记录：一条可读的时间说明（沿用生图那种系统消息写法）
        try:
            self.sys_msgs.append({"kind": "ai", "speaker": "🕰 离线推进",
                                  "content": p["summary"], "node_id": None})
            self._rebuild_messages()
        except Exception:
            pass
        self._save_config()
        self._persist_offline_undo(undo)
        return {"ok": True, "applied": True, "summary": p["summary"],
                "turns": p.get("turns", 0), "affection": p.get("affection"),
                "status": p.get("status", []), "undo_saved": bool(undo)}

    def _persist_offline_undo(self, undo):
        """把 undo 记录暂存起来，供 api_offline_undo 撤销（一次会话内有效）"""
        try:
            self._offline_undo = undo
        except Exception:
            pass

    def api_offline_undo(self):
        """撤销上一次离线推进（状态回到应用前；聊天里那条说明留着，但会标注已撤销）"""
        import offline_advance
        undo = getattr(self, "_offline_undo", None)
        if not undo:
            return {"ok": False, "err": "没有可撤销的离线推进"}
        ok = offline_advance.revert(undo, self.core.mechanism_state)
        self._offline_undo = None
        if ok:
            try:
                self.sys_msgs.append({"kind": "ai", "speaker": "🕰 离线推进",
                                      "content": "（已撤销上一次离线结算）", "node_id": None})
                self._rebuild_messages()
            except Exception:
                pass
        return {"ok": bool(ok), "err": "" if ok else "撤销失败"}

    def api_codex_analyze(self, script_json, pkg_name=""):
        """剧本体检：对【编辑器里当前这份（可能还没保存的）剧本】做结构分析。

        script_json 由前端 JSON.stringify(galScript) 直接传过来 —— 不要求先保存，
        所以作者改一行就能立刻体检。pkg_name 用来同时检查素材引用（缺文件/孤儿文件）。
        """
        import codex_core
        try:
            data = json.loads(script_json or "{}")
        except Exception as e:
            return {"ok": False, "err": "剧本 JSON 解析失败：" + str(e)[:120]}
        pkg_dir = None
        try:
            name = (pkg_name or "").strip()
            if name:
                cand = os.path.join(self.codex_dir, name)
                if os.path.isdir(cand):
                    pkg_dir = cand
        except Exception:
            pkg_dir = None
        try:
            rep = codex_core.analyze_codex(data, pkg_dir=pkg_dir)
        except Exception as e:
            return {"ok": False, "err": "体检失败：" + str(e)[:140]}
        rep["checked_pkg"] = pkg_dir or ""
        return rep

    def api_codex_run_action(self, cmd):
        """播放器行动钩子（CODEX 深度集成 DICK 的系统权限）。
        支持：
          plugin:<命令>   调用插件命令（如 plugin:/speak こんにちは）
          model:<文本>    调用模型生成一句话（如 model:请描述这个场景的天气）
          aff:<±N>        修改当前角色好感度（机制卡）
          run:<程序>      调用本地程序（如 run:notepad.exe）
          <其他>          默认按插件命令处理（兼容旧剧本 /speak 等）
        返回 {ok, out}。"""
        cmd = (cmd or "").strip()
        if not cmd:
            return {"ok": True, "out": ""}
        low = cmd.lower()
        try:
            if low.startswith("model:"):
                prompt = cmd[len("model:"):].strip()
                if not prompt:
                    return {"ok": True, "out": ""}
                client = getattr(self.core, "client", None)
                if not client:
                    return {"ok": True, "out": "（未配置模型）"}
                try:
                    resp = client.chat.completions.create(
                        model=self.core.model,
                        messages=[{"role": "user", "content": prompt}],
                        stream=False, timeout=30)
                    text = (resp.choices[0].message.content or "").strip()
                    return {"ok": True, "out": text[:200]}
                except Exception as e:
                    return {"ok": True, "out": "（模型调用失败：" + str(e)[:60] + "）"}
            if low.startswith("aff:"):
                try:
                    delta = int(cmd[len("aff:"):].strip())
                    st = getattr(self.core, "mechanism_state", None)
                    if st is None or "affection" not in st:
                        return {"ok": True, "out": "（未启用好感度）"}
                    cfg = getattr(self.core, "_mech_config", None) or {}
                    aff = cfg.get("affection") if isinstance(cfg.get("affection"), dict) else {}
                    hi = int(aff.get("max", 100) or 100)
                    lo = int(aff.get("min", 0) or 0)
                    cur = int(st.get("affection", 50) or 50)
                    st["affection"] = max(lo, min(hi, cur + delta))
                    return {"ok": True, "out": f"❤️ 好感 {cur}→{st['affection']}"}
                except Exception as e:
                    return {"ok": True, "out": "（好感调整失败）"}
            if low.startswith("run:"):
                prog = cmd[len("run:"):].strip()
                r = self.api_codex_run_program(prog)
                return {"ok": r.get("ok", False), "out": r.get("err", "已调用本地程序")}
            # 默认：插件命令（兼容 plugin: 前缀与旧裸命令）
            plugin_cmd = cmd[len("plugin:"):].strip() if low.startswith("plugin:") else cmd
            if self.plugin_manager:
                out = self.plugin_manager.handle_command(plugin_cmd)
                if isinstance(out, str):
                    return {"ok": True, "out": out}
                if isinstance(out, tuple) and out:
                    return {"ok": True, "out": str(out[0])}
        except Exception as e:
            print(f"[CODEX action] 执行失败: {e}")
        return {"ok": True, "out": ""}

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

    def api_toggle_language(self):
        self.language = "en" if self.language == "zh" else "zh"
        i18n.set_lang(self.language)
        self.config["language"] = self.language
        self._save_config()
        return {"ok": True, "lang": self.language}

    def api_set_theme(self, theme_idx, accent_idx):
        self.config["ui_theme"] = int(theme_idx)
        self.config["ui_accent"] = int(accent_idx)
        self._save_config()
        return {"ok": True}

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
        "Direct-Interface Cork-bore Kit v2.0", html_path, js_api=app,
        width=1060, height=820, min_size=(860, 640), background_color="#0f1115")
    webview.start()


if __name__ == "__main__":
    main()
