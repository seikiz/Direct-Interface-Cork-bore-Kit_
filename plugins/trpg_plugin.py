# ============================================================
#   trpg_plugin.py - 跑团模式（剧情为主）v0.1
#
#   用 DICK 自己的角色卡跑 TRPG：一张卡当 GM（主持），若干张卡当
#   PC（玩家角色），剧情驱动，掷骰调味，GAL 选项分支。
#
#   命令：
#     /trpg start            进入跑团模式（需先设置 GM 与 PC）
#     /trpg gm <角色名>       指定 GM（主持）卡
#     /trpg pc <角色名>       添加一张 PC 卡（可多次）
#     /trpg pc clear          清空 PC 列表
#     /trpg turn <名字>       指定/轮到谁行动（也可不指定，默认轮换）
#     /trpg status            查看当前跑团配置与轮次
#     /trpg roll 2d6+3        掷骰（GM 判定用；同骰子大师）
#     /trpg end               退出跑团模式
#
#   联动：启用后通过 contextInjection() 往系统提示词注入「剧情为主 GM
#   提示词 + 当前行动者」，让 GM 以剧情驱动方式叙事、给 GAL 分支、掷骰。
#   需配合把 GM 与 PC 卡也勾选为活动角色（群聊物理隔离）。
# ============================================================

import random
import re
import socket
import json
import time
import os
import webbrowser

from plugin_base import PluginBase
import app_paths

# 剧情为主的 GM 提示词（注入系统提示词，强制 GM 以剧情为重）
_GM_PROMPT = (
    "【跑团模式 · 剧情为主】\n"
    "你是一名 TRPG 主持人（GM），正主持一场以剧情为核心的冒险。规则：\n"
    "1. 节奏由剧情驱动：玩家角色（PC）的行动不断推进故事，你把每个行动演成有画面感的场景，"
    "并自然引出下一段剧情；不要机械播报数值，让对方的感觉和行动驱动剧情。\n"
    "2. 在合适的节点用 GAL 选项的方式给出 2-4 个下一步行动选项（面向当前行动者），"
    "让剧情可分支；有「当前剧情事件」时就围绕事件展开。\n"
    "3. 需要不确定性（判定/运气/战斗）时用掷骰，把大成功/大失败/暴击演得戏剧化。\n"
    "4. 每个 PC 各有一张角色卡（性格/台词/机制/战斗/好感），演出务必贴合各自设定，绝不串戏。\n"
    "5. 保持世界观一致（参考世界书），让故事有因果、有悬念、有情感。"
)


class TrpgPlugin(PluginBase):
    name = "跑团模式"
    version = "0.1"
    description = "剧情为主的 TRPG：一张角色卡当 GM、若干张当 PC，剧情驱动 + GAL 分支 + 掷骰（/trpg）"
    author = "seiki"
    enabled = False

    ui_buttons = [
        {"type": "insert", "label": "🎲 跑团", "text": "/trpg status"},
        {"type": "method", "label": "🌐 附近跑团", "method": "nearby_open"},
    ]

    settings_schema = [
        {"key": "auto_turn", "label": "自动按 PC 列表轮换行动者", "type": "bool", "default": True},
        {"key": "choices", "label": "让 GM 给 GAL 选项分支", "type": "bool", "default": True},
        {"key": "roll", "label": "允许 GM 掷骰", "type": "bool", "default": True},
    ]

    def __init__(self, core):
        super().__init__(core)
        self.active = False
        self.gm = ""              # GM 卡名
        self.pcs = []             # PC 卡名列表
        self.turn = ""            # 当前行动者卡名
        self.turn_idx = 0
        self.round = 0            # 已进行的行动轮数(每轮=一个PC行动)

    def on_load(self):
        print("[跑团模式] 已加载：/trpg 进入剧情向跑团，需设置 GM 与 PC（默认关闭）")

    # ---------- 系统提示词注入 ----------
    def contextInjection(self):
        if not self.active:
            return ""
        lines = [_GM_PROMPT]
        if self.pcs:
            lines.append("本次队伍（PC）：" + "、".join(self.pcs))
        if self.gm:
            lines.append("（主持者 GM 是「" + self.gm + "」，你以 GM 口吻叙事；除非 PC 指定，否则不要替 PC 做决定。）")
        if self.turn:
            lines.append("当前行动者：" + self.turn + "——请优先围绕他/她的行动叙事，并给他/她 2-4 个下一步选项。")
        lines.append("【掷骰】可用 /trpg roll 或直接叙述；不要让剧情被数值绑架，数值只做戏剧化调味。")
        return "\n".join(lines)

    # ---------- 命令 ----------
    def on_command(self, command, args):
        if command != "trpg":
            return None
        arg = (args or "").strip()
        if not arg:
            return self._status(), False
        head, _, rest = arg.partition(" ")
        head = head.lower()
        rest = (rest or "").strip()

        if head == "start":
            if not self.gm or not self.pcs:
                return "⚠️ 先设置 GM 和 PC：/trpg gm <名>、/trpg pc <名>", False
            self.active = True
            self.turn_idx = 0
            self.round = 0
            self.turn = self.pcs[0]
            self._write_lock()   # 会期锁定：GM+PC 卡不可改
            return ("🎭 跑团开始（剧情为主）。GM「" + self.gm + "」，队伍：" + "、".join(self.pcs)
                    + "（会期已锁定以下角色卡：" + "、".join([self.gm] + self.pcs)
                    + "，/trpg end 解锁）\n先让 " + self.turn + " 行动，或直接开始：描述场景/剧情。", False)

        if head == "gm":
            self.gm = rest
            return ("GM 已设为「" + self.gm + "」", False)

        if head == "pc":
            if not rest or rest.lower() == "clear":
                n = len(self.pcs)
                self.pcs = []
                return ("已清空 PC 列表（原 " + str(n) + " 张）", False)
            if rest in self.pcs:
                return ("「" + rest + "」已在 PC 列表", False)
            self.pcs.append(rest)
            return ("已添加 PC「" + rest + "」（共 " + str(len(self.pcs)) + " 张）", False)

        if head == "turn":
            if rest and rest in self.pcs:
                self.turn = rest
                self.turn_idx = self.pcs.index(rest)
            elif self.pcs:
                self.turn_idx = (self.turn_idx + 1) % len(self.pcs)
                self.turn = self.pcs[self.turn_idx]
            else:
                return "⚠️ 还没有 PC，先 /trpg pc <名> 添加", False
            self.round += 1
            return ("⏳ 轮到「" + self.turn + "」行动", False)

        if head == "roll":
            return self._roll(rest), False

        if head == "nearby":
            return self._nearby_report(), False

        if head == "join":
            near = self.discover()
            if not near:
                return "未发现附近的跑团主机", False
            try:
                sel = near[max(0, int(rest) - 1) if rest.isdigit() else 0]
            except Exception:
                sel = near[0]
            return self.open_url(sel.get("url", "")), False

        if head == "status":
            return self._status(), False

        if head == "end":
            return self.end_session(), False

        return self._status(), False

    def end_session(self):
        """退出跑团（核心）：停用会话、解除角色卡锁定、复位轮次与行动者。
        保留 GM/PC 配置便于重新开始。返回提示字符串。"""
        self.active = False
        self.turn = ""
        self.turn_idx = 0
        self.round = 0
        self._clear_lock()
        return "🏁 已退出跑团模式（已解除角色卡锁定）"

    # ---------- 工具 ----------
    def _lockfile(self):
        return os.path.join(app_paths.get_base_dir(), "saves", ".trpg_lock.json")

    def _write_lock(self):
        """会期锁定：写 .trpg_lock.json（GM+PC 卡名），app 改卡前会检查拒绝。"""
        try:
            os.makedirs(os.path.dirname(self._lockfile()), exist_ok=True)
            with open(self._lockfile(), "w", encoding="utf-8") as f:
                json.dump({"locked": [self.gm] + self.pcs, "gm": self.gm, "pcs": self.pcs},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _clear_lock(self):
        try:
            if os.path.exists(self._lockfile()):
                os.remove(self._lockfile())
        except Exception:
            pass

    @staticmethod
    def discover(discover_port=5081, timeout=2.0):
        """局域网发现：向 255.255.255.255:<port> 发探测，收集跑团主机回复。
        返回 [{"service":"trpg","url":...,"gm":...}, ...]。"""
        found = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            magic = b"DICK_TRPG_DISCOVER_V1"
            # 同时向回环与子网广播发探测：本机/局域网都能扫到
            for target in ("255.255.255.255", "127.0.0.1"):
                try:
                    s.sendto(magic, (target, discover_port))
                except Exception:
                    continue
            end = time.time() + timeout
            s.settimeout(0.6)
            while time.time() < end:
                try:
                    data, addr = s.recvfrom(1024)
                except socket.timeout:
                    break
                try:
                    d = json.loads(data.decode("utf-8"))
                    if isinstance(d, dict) and d.get("service") == "trpg" and d.get("url"):
                        d["host_ip"] = addr[0]
                        found.append(d)
                except Exception:
                    continue
            s.close()
        except Exception:
            pass
        # 去重（按 url）
        seen, uniq = set(), []
        for d in found:
            if d["url"] not in seen:
                seen.add(d["url"]); uniq.append(d)
        return uniq

    def open_url(self, url):
        """打开浏览器；失败返回提示。"""
        try:
            webbrowser.open(url)
            return "已打开 " + url
        except Exception as e:
            return "打开失败: " + str(e)

    def nearby_open(self):
        """UI 按钮：发现并打开第一个跑团主机浏览器地址（一键加入）。"""
        near = self.discover()
        if not near:
            return "未发现附近的跑团主机（先让主机跑 python trpg_server.py，同一 Wi-Fi）"
        return self.open_url(near[0]["url"])

    def _nearby_report(self):
        near = self.discover()
        if not near:
            return "未发现附近的跑团主机。先让主机：python trpg_server.py，双方同一 Wi-Fi"
        lines = ["🌐 附近跑团："]
        for i, d in enumerate(near, 1):
            lines.append(f"  {i}. {d.get('gm') or '未知GM'} @ {d['url']}")
        lines.append("用 /trpg join <序号> 打开进入，或直接复制地址。")
        return "\n".join(lines)

    def _status(self):
        if not self.active:
            return ("🎭 跑团模式【未开始】\n"
                    "  0) 用「勾选角色」把 GM 与若干 PC 卡选为活动角色\n"
                    "  1) /trpg gm <角色名>   设 GM\n"
                    "  2) /trpg pc <角色名>   加 PC（可多次）\n"
                    "  3) /trpg start         开始\n"
                    "  当前 GM：{gm} | PC：{pcs}".format(
                        gm=self.gm or "（未设）", pcs="、".join(self.pcs) or "（未设）"))
        return ("🎭 跑团中 · 第 " + str(self.round) + " 轮\n"
                "  GM：" + (self.gm or "?") + "\n"
                "  PC：" + "、".join(self.pcs) + "\n"
                "  当前行动者：" + (self.turn or "?") + "\n"
                "  命令：/trpg turn [名]（下一人）· /trpg roll 2d6+3 · /trpg end")

    def _roll(self, spec):
        """同骰子大师的极简掷骰（/r 2d6+3 /d20），确定性，供 GM 判定。"""
        m = re.match(r'^\s*(\d*)\s*d(\d+)\s*([+-]\s*\d+)?\s*$', spec or "1d20", re.I)
        if not m:
            return "❌ 格式：/trpg roll 2d6+3（支持 4/6/8/10/12/20/100 面）"
        count = int(m.group(1)) if m.group(1) else 1
        faces = int(m.group(2))
        mod = int(re.sub(r"\s+", "", m.group(3))) if m.group(3) else 0
        if faces not in (4, 6, 8, 10, 12, 20, 100):
            return "⚠️ 暂不支持 d" + str(faces)
        rolls = [random.randint(1, faces) for _ in range(count)]
        total = sum(rolls) + mod
        s = "🎲 " + str(count) + "d" + str(faces) + (("+" + str(mod)) if mod > 0 else (str(mod) if mod < 0 else "")) \
            + " = [" + ", ".join(str(r) for r in rolls) + "]" + (" + " + str(mod) if mod else "") \
            + " = **" + str(total) + "**"
        if mod == 0:
            if all(r == faces for r in rolls):
                s += " —— ✨ 大成功！"
            elif all(r == 1 for r in rolls):
                s += " —— 💥 大失败！"
        return s
