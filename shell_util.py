# -*- coding: utf-8 -*-
"""shell_util.py —— 壳层与各 mixin 共用的最小公共层。

只放"两边都要用、且没有任何依赖"的东西：常量 + 纯函数。
拆出它的原因：`shell_ws.py`（从 Kit.py 搬出的 28 个工坊方法）要用
`tree_ts_of` 和几个常量，而 Kit.py 又 import shell_ws —— 想让两边都能用，
只能把它们放到一个谁都不依赖的模块里（否则就是循环 import）。

规矩：这个文件**不许 import 项目内任何模块**（只许标准库）。
"""
from __future__ import annotations

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
