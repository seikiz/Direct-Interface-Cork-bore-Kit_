# -*- coding: utf-8 -*-
"""shell_util.py —— 壳层与各 mixin 共用的最小公共层。

只放"两边都要用、且没有任何依赖"的东西：常量 + 纯函数。
拆出它的原因：`shell_ws.py`（从 Kit.py 搬出的 28 个工坊方法）要用
`tree_ts_of` 和几个常量，而 Kit.py 又 import shell_ws —— 想让两边都能用，
只能把它们放到一个谁都不依赖的模块里（否则就是循环 import）。

规矩：这个文件**不许 import 项目内任何模块**（只许标准库）。
"""
from __future__ import annotations

import json

import app_paths

BASE_DIR = app_paths.get_base_dir()

# 工坊默认服务器<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（可在设置里改）
DEFAULT_WS_SERVER = "http://154.94.226.240:8080"

XFER_MIN_INTERVAL_MS = 500      # 每设备两次传输的最小间隔（服务器下发优先）
XFER_MAX_RETRY = 3              # 429 退避重试上限（超过就报"链路限流"）


def tree_ts_of(data):
    """存档里的「进度时间戳」—— 同一件东西，两端键名不一样：
         电脑端写 `_tree_ts`，安卓端写 `tree_ts`（见 DICK-Android 的 Model.kt）。
    跨设备"后写胜"要拿它比新旧，所以**两边都得认**：只认自己那一个键的话，
    从另一端同步/导入过来的存档会被当成"没有进度"，于是随便一个更旧的服务器版本都能盖上去。
    读取侧兼容两种键（不新增/不改写任何字段）；写回时仍按各自的老键写。
    """
    if not isinstance(data, dict):
        return ""
    return str(data.get("_tree_ts") or data.get("tree_ts") or "")


BUILTIN_RELAY = ""

# 创意工坊的**默认服务器地址**：用户不必再填 IP（界面上那栏已经删掉）。
# 探测顺序：用户显式配的 server_url → 本机服务器 127.0.0.1:5000 → 这个默认地址。
# 与安卓端 Workshop.DEFAULT_PUBLIC_URL 是同一个地址，换机器时两处一起改。
# 注意：这里**只影响工坊（作品列表/下载/上传）**；聊天进度同步仍要求"显式配置 server_url
# 或本机服务器在线"（_ws_sync_enabled），不会因为有了默认地址就把你的存档自动推到公网。

# ---------- 角色卡结构化字段 / 世界卡参数（精细化创作） ----------


PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek 官方", "free": False,
     "base_url": "https://api.deepseek.com",
     # 2026-11 对齐官方更新日志：主力 deepseek-flash（默认）；deepseek-v4-pro 是可选的
     # 高思考档（按量更贵，别当默认）；deepseek-chat / deepseek-reasoner 已于
     # 2026-07-24 停用，deepseek-v4-flash-vision-exp 已并入 V4.1 Flash 的多模态能力。
     "models": ["deepseek-flash", "deepseek-v4-pro"],
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

    @staticmethod
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
