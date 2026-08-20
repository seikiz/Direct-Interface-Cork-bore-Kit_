# ============================================================
#   dice_plugin.py - 骰子大师（泛用设置界面示例插件）
#
#   演示新插件体系：
#   1. 声明 settings_schema 即可在插件管理器中获得 ⚙️ 设置窗口
#      （无需编写任何 Tkinter 代码）
#   2. 设置自动持久化到 plugin_settings/骰子大师.json
#   3. 提供掷骰命令：/r 2d6、/r 1d20+3、/d20、/d6、/d100、/dice
# ============================================================

import random
import re

from plugin_base import PluginBase


class DiceMasterPlugin(PluginBase):
    name = "骰子大师"
    version = "1.0"
    description = "掷骰与随机事件：/r 2d6+3、/d20，设置面板可调默认骰子与显示风格"
    author = "seiki"
    enabled = True

    # 声明式 UI 模组：插件坞快捷掷骰按钮（点击把命令填入输入框，回车即掷）
    ui_buttons = [
        {"type": "insert", "label": "🎲 d20", "text": "/r 1d20"},
        {"type": "insert", "label": "🎲 d6", "text": "/r 1d6"},
    ]

    # ---- 声明式设置（泛用 UI 自动生成设置窗口）----
    settings_schema = [
        {"key": "default_dice", "label": "默认骰子（/d20 快捷命令使用）",
         "type": "choice", "options": ["d6", "d20", "d100"], "default": "d20"},
        {"key": "max_count", "label": "单次最多骰数（防刷屏）",
         "type": "int", "default": 10, "min": 1, "max": 100},
        {"key": "detailed", "label": "显示每次点数明细",
         "type": "bool", "default": True},
        {"key": "fortune", "label": "大成功判定的自定义提示语",
         "type": "text", "default": "✨ 大成功！"},
    ]

    # 骰子面数表
    DICE_FACES = {"d4": 4, "d6": 6, "d8": 8, "d10": 10, "d12": 12, "d20": 20, "d100": 100}

    def on_command(self, command, args):
        cmd = command.lower()

        # 快捷命令：/d20 /d6 /d100 /d12 ...
        if cmd in self.DICE_FACES:
            return self._roll(f"1{cmd}", 1), False

        if cmd in ("r", "roll"):
            return self._roll(args.strip(), 1), False

        if cmd in ("dice", "骰子"):
            return self._help_text(), False

        return None

    # ---------- 核心掷骰 ----------
    def _roll(self, spec, crit_face):
        """解析 '2d6' / '1d20+3' / 'd20' 并掷骰，返回结果文本"""
        if not spec:
            spec = self.get_setting("default_dice", "d20")
        m = re.match(r'^\s*(\d*)\s*d(\d+)\s*([+-]\s*\d+)?\s*$', spec, re.I)
        if not m:
            return (f"❌ 无法解析「{spec}」。格式示例：/r 2d6、/r 1d20+3、/r d100\n"
                    f"快捷命令：/d20 /d6 /d100（默认骰子可在 ⚙️ 设置 中修改）")

        count = int(m.group(1)) if m.group(1) else 1
        faces = int(m.group(2))
        modifier = int(re.sub(r'\s+', '', m.group(3))) if m.group(3) else 0
        max_count = int(self.get_setting("max_count", 10))

        if faces not in self.DICE_FACES.values():
            return f"⚠️ 暂不支持 d{faces}（支持 4/6/8/10/12/20/100 面）"
        if count < 1:
            return "⚠️ 骰数至少为 1"
        if count > max_count:
            return f"⚠️ 骰数超过上限（当前设置上限 {max_count} 个，可在 ⚙️ 设置 中调整）"

        rolls = [random.randint(1, faces) for _ in range(count)]
        total = sum(rolls) + modifier

        detailed = bool(self.get_setting("detailed", True))
        if detailed:
            parts = ", ".join(str(r) for r in rolls)
            line = f"🎲 {count}d{faces}{self._fmt_mod(modifier)} = [{parts}]"
            if modifier:
                line += f" {self._fmt_mod(modifier)}"
            line += f" = **{total}**"
        else:
            line = f"🎲 {count}d{faces}{self._fmt_mod(modifier)} = **{total}**"

        # 大成功/大失败判定（骰出最大/最小点且无修正时）
        if modifier == 0:
            if all(r == faces for r in rolls):
                line += f" —— {self.get_setting('fortune', '✨ 大成功！')}"
            elif all(r == 1 for r in rolls):
                line += " —— 💥 大失败！"
        return line

    @staticmethod
    def _fmt_mod(modifier):
        return f"+{modifier}" if modifier > 0 else (str(modifier) if modifier < 0 else "")

    def _help_text(self):
        default = self.get_setting("default_dice", "d20")
        return (f"🎲 骰子大师 使用说明\n"
                f"  /r 2d6      掷 2 个 6 面骰\n"
                f"  /r 1d20+3   掷 d20 并 +3 修正\n"
                f"  /d20       快捷掷默认骰子（当前：{default}）\n"
                f"  /d6 /d100  其他快捷骰\n"
                f"  ⚙️ 在「插件管理 → 骰子大师 → 设置」中可调整默认骰子、上限与显示风格")
