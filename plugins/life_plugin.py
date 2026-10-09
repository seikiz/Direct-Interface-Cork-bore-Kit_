# -*- coding: utf-8 -*-
"""生活（吃饭）—— `/生活` 命令入口

功能本体在 `life_core.py`（世界时钟 + 厨具历史库 + 食材/做法库），它跟着核心走：
每轮回复时由 `DICK_core._life_injection()` 注入一小段【生活·那边】。

这个插件只干两件事：
  · 提供 `/生活` 命令：看状态、开关、改年代/地域/口味/忌口/在哪儿
  · 在插件坞放一个按钮，点一下就把 `/生活` 插进输入框

**为什么不声明 settings_schema**：配置只有一份，住在 `life_config.json`（`life_core` 拥有，
跟 `time_scale.json` 一个规矩）。插件再声明一套设置项就会出现两个真相 ——
改了一个不生效，那种 bug 最难查。要看设置就打 `/生活`。
"""
import life_core
from plugin_base import PluginBase


class LifePlugin(PluginBase):
    name = "生活（吃饭）"
    version = "1.0"
    description = "世界时钟 + 一日三餐 + 厨具历史库：让角色有日子过"
    author = "DICK"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "生活：今天吃什么", "text": "/生活"},
    ]

    # ---------- /<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌生活 ----------
    def on_command(self, command, args):
        if command not in ("life", "生活", "吃饭"):
            return None
        cfg = life_core.load_config()
        arg = (args or "").strip()
        low = arg.lower()

        if not arg or low in ("状态", "status", "看"):
            return self._status(cfg)

        head, _, tail = arg.partition(" ")
        head_low = head.lower()
        tail = tail.strip()

        if head_low in ("开", "on", "开启", "打开"):
            cfg["enabled"] = True
            life_core.save_config(cfg)
            return "生活层已开启（下一轮回复起注入【生活·那边】）"
        if head_low in ("关", "off", "关闭"):
            cfg["enabled"] = False
            life_core.save_config(cfg)
            return "生活层已关闭"
        if head_low in ("年代", "era"):
            if not tail:
                return "年代可选：" + "、".join([e["key"] for e in life_core.ERAS] + ["auto"])
            key = self._match_era(tail)
            if not key:
                return "认不出这个年代：%s\n可选：%s、auto" % (
                    tail, "、".join(e["key"] for e in life_core.ERAS))
            cfg["era"] = key
            life_core.save_config(cfg)
            return "年代已设为：%s（%s）" % (key, self._era_note(key))
        if head_low in ("地域", "region", "地方"):
            if tail not in life_core.REGIONS:
                return "地域可选：" + "、".join(life_core.REGIONS)
            cfg["region"] = tail
            life_core.save_config(cfg)
            return "地域已设为：" + tail
        if head_low in ("口味", "taste"):
            cfg["taste"] = tail
            life_core.save_config(cfg)
            return "口味已设为：%s" % (tail or "（清空）")
        if head_low in ("忌口", "avoid", "不吃"):
            cfg["avoid"] = tail
            life_core.save_config(cfg)
            return "忌口已设为：%s" % (tail or "（清空）")
        if head_low in ("在", "地点", "location"):
            cfg["location"] = tail
            life_core.save_config(cfg)
            return "地点已设为：%s" % (tail or "（清空）")
        if head_low in ("菜", "菜单", "show_meals", "显示"):
            cfg["show_meals"] = not bool(cfg.get("show_meals"))
            life_core.save_config(cfg)
            return "注入里%s显示今天吃了什么" % ("会" if cfg["show_meals"] else "不再")
        if head_low in ("重抽", "换", "roll"):
            # 重抽：把这一天的菜单换成另一套 —— 做法是给角色名加个后缀当种子，
            # 所以"重抽"是稳定的（同一份配置永远给同一套），不是每次随机。
            return self._status(cfg, reroll=True)

        return ("用法：/生活 [开|关|年代 <key>|地域 <名>|口味 <词>|忌口 a,b|在 <地点>|"
                "菜|重抽]\n" + "可选年代：" + "、".join(e["key"] for e in life_core.ERAS))

    # ---------- 内部 ----------
    def _match_era(self, text):
        t = text.strip()
        if t == "auto" or t == "自动":
            return "auto"
        for e in life_core.ERAS:
            if t == e["key"] or t == e["name"] or t in e["name"]:
                return e["key"]
        return None

    def _era_note(self, key):
        for e in life_core.ERAS:
            if e["key"] == key:
                return e.get("note", "")
        return ""

    def _status(self, cfg, reroll=False):
        core = getattr(self, "core", None)
        chain = []
        try:
            chain = core.tree.get_current_chain() if core and core.tree else []
        except Exception:
            chain = []
        role = None
        try:
            roles = getattr(core, "active_roles", None) or []
            role = roles[0] if roles else None
        except Exception:
            role = None
        world = None
        try:
            world = core.world_data if core else None
        except Exception:
            world = None
        scale = None
        try:
            scale = core._time_scale() if core else None
        except Exception:
            scale = None
        if reroll:
            # 换一套：只改角色名参与种子的那一份，不落盘
            if isinstance(role, dict):
                role = dict(role)
                role["name"] = str(role.get("name") or "她") + "·换"
        text = life_core.describe(chain, scale, role=role, world=world, cfg=cfg)
        return text + "\n\n改法：/生活 关 ｜ 年代 明清 ｜ 地域 江南 ｜ 口味 清淡 ｜ 忌口 香菜,海鲜 ｜ 在 灶房"
