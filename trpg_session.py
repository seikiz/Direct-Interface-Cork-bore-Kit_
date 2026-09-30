# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   trpg_session.py - 去中心化跑团会话引擎（可嵌入任意设备）
#
#   把跑团核心从"单机 Flask 服务器"提炼成自治会话单元：
#     - 构造时给 GM 卡 + PC 卡 + 模型配置（key/base/model）
#     - 内置 GM(AI) 本地推理（GM 设备本地跑，无需外部服务器）
#     - 纯逻辑接口 state/join/leave/act/end，无任何 Flask 依赖 ——
#       因此既可嵌入 PC 的 HTTP 壳，也可由手机端 Kotlin 复刻同一逻辑，
#       实现"任一设备发起当 GM、成员直连它"的去中心化跑团。
#
#   用法（PC 端）：
#     s = TrpgSession(config, gm="咲", pcs=["凛","咲"])
#     s.act("凛", "我推开那扇门")          # -> {"ok":True,"gm":..,"turn":..}
#     s.state()                            # -> {"gm","pcs","turn","story","joined"}
#
#   角色卡 system_prompt 通过 card_prompt(name) 回调注入（缺省从 saves/<name>.json 读，
#   手机上可换成从内存/包内读取 —— 去中心化的关键：不绑定 PC 的文件系统）。
# ============================================================

import json
import os
import threading

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

_GM_PROMPT = (
    "【跑团模式 · 剧情为主】你是一名 TRPG 主持人(GM)，正在一场以剧情为核心的冒险。规则："
    "① 节奏由剧情驱动，把每个行动演成有画面感的场景并自然引出下一段剧情，不机械播报数值；"
    "② 在节点给当前行动者 2-4 个下一步选项(GAL 分支)；③ 不确定性用掷骰(大成功/大失败/暴击要演出)；"
    "④ 每个 PC 一张角色卡，贴合各自设定，绝不串戏；⑤ 保持世界观一致，让故事有因果、悬念、情感。"
    "你用 GM 口吻叙述：先一句场景，再给该行动的结果，结尾给 2-4 个下一步选项。"
)


class TrpgSession:
    """去中心化跑团会话引擎 —— 可跑在 PC 或任一手机(GM 设备)上。"""

    def __init__(self, config=None, gm="", pcs=None, card_prompt=None, save_dir=""):
        self.conf = config or {}
        self.gm = gm or ""
        self.pcs = list(pcs or [])
        self.turn = self.pcs[0] if self.pcs else ""
        self.story = []          # [{"actor","action","gm"}]
        self.joined = {}         # pc名 -> 玩家名
        self._lock = threading.Lock()
        self.save_dir = save_dir or ""
        # 角色卡读取回调：去中心化关键 —— 允许外部注入（手机从内存/包内读，PC 从 saves 读）
        self.card_prompt = card_prompt or self._default_card_prompt

    # ---- 角色卡 ---- 
    def _default_card_prompt(self, name):
        try:
            p = os.path.join(self.save_dir, name + ".json")
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d.get("system_prompt") or d.get("name") or ""
        except Exception:
            return ""

    # ---- GM 提示构建 ----
    def _gm_system(self, actor):
        parts = [_GM_PROMPT]
        if self.gm:
            parts.append("（主持者 GM 卡：\n" + self.card_prompt(self.gm) + "\n）")
        if self.pcs:
            parts.append("本次队伍(PC)：" + "、".join(self.pcs) + "。各角色设定如下：")
            for pc in self.pcs:
                sp = self.card_prompt(pc)
                if sp:
                    parts.append("■ " + pc + "：\n" + sp)
        if self.story:
            parts.append("【剧情回顾】")
            for s in self.story[-12:]:
                parts.append("- " + s["actor"] + "：" + s["action"] + " → 「" + s["gm"] + "」")
        parts.append("当前行动者：" + actor + "，请围绕他/她的行动叙事并给 2-4 个下一步选项。")
        return "\n\n".join(parts)

    # ---- LLM 推理（GM 设备本地跑，A 方案） ----
    def _llm(self, system, user):
        if OpenAI is None:
            return "（GM 推理不可用：未找到 openai 客户端）"
        key = (self.conf.get("api_key") or "").strip() or "free"
        base = (self.conf.get("base_url") or "https://api.deepseek.com").strip()
        model = (self.conf.get("model") or "deepseek-v4-flash").strip()
        client = OpenAI(api_key=key, base_url=base)
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                stream=False, timeout=120,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception as e:
            return "（GM 叙事失败：" + str(e)[:120] + "）"

    # ---- 会话接口（与传 /api/* 一一对应，纯逻辑） ----
    def state(self):
        with self._lock:
            return {"gm": self.gm, "pcs": self.pcs, "turn": self.turn,
                    "story": self.story[-40:], "joined": dict(self.joined)}

    def setup(self, gm=None, pcs=None):
        with self._lock:
            if gm:
                self.gm = str(gm).strip()
            if isinstance(pcs, list):
                self.pcs = [str(x).strip() for x in pcs if str(x).strip()]
            if self.pcs:
                self.turn = self.pcs[0]
        return {"ok": True, "turn": self.turn}

    def join(self, name, player=""):
        with self._lock:
            if name not in self.pcs:
                return {"error": "该角色不在队伍中"}
            self.joined[name] = player or "玩家"
        return {"ok": True, "turn": self.turn}

    def leave(self, name):
        with self._lock:
            if name:
                self.joined.pop(name, None)
        return {"ok": True, "joined": list(self.joined.keys())}

    def act(self, actor, action):
        actor = (actor or "").strip()
        action = (action or "").strip()
        if not action:
            return {"error": "行动不能为空"}
        if not actor:
            actor = self.turn or (self.pcs[0] if self.pcs else "你")

        system = self._gm_system(actor)
        narration = self._llm(system, f"{actor}的行动：{action}\n请叙述接下来发生什么，结尾给 2-4 个下一步选项。")

        with self._lock:
            self.story.append({"actor": actor, "action": action, "gm": narration})
            if self.pcs:
                i = self.pcs.index(actor) if actor in self.pcs else 0
                self.turn = self.pcs[(i + 1) % len(self.pcs)]
        return {"ok": True, "gm": narration, "turn": self.turn}

    def end(self):
        with self._lock:
            self.story = []
            self.joined = {}
            self.turn = self.pcs[0] if self.pcs else ""
        return {"ok": True}
