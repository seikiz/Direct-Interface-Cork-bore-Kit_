# -*- coding: utf-8 -*-
"""世界卡库 —— `/世界包` 命令入口

功能本体在 `world_packs.py`（列出/查找/装入世界卡包）。这个插件只把命令接上：

    /世界包                 列出随包的卡包（含年代/设定/地点数）
    /世界包 装 江南水乡      装进 worlds/（同名不覆盖）
    /世界包 装 江南水乡 --force   覆盖同名（覆盖前留备份）
    /世界包 看 江南水乡      看一眼卡里的规则与地点

**为什么不声明 settings_schema**：与生活/空间两层同一个理由 —— 没有需要长期保存的配置，
装了哪些包就是 `worlds/` 里的文件本身，那才是唯一真相。
"""
import world_packs
from plugin_base import PluginBase


class WorldPackPlugin(PluginBase):
    name = "世界卡库"
    version = "1.0"
    description = "随包的成套世界卡（含年代/地图/常识参数）：/世界包 列出与装入"
    author = "DICK"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "世界包：看看有哪些", "text": "/世界包"},
    ]

    def on_command(self, command, args):
        if command not in ("worldpack", "世界包", "worldpacks"):
            return None
        arg = (args or "").strip()
        packs = world_packs.list_packs()
        if not arg or arg.lower() in ("list", "列表"):
            if not packs:
                return ("世界卡库里一个包都没有。\n"
                        "卡包目录：%s" % "、".join(world_packs.pack_dirs()))
            lines = ["世界卡库（%d 个包）：" % len(packs)]
            lines += ["  · " + world_packs.describe(p) for p in packs]
            lines.append("装法：/世界包 装 <名字>　看一眼：/世界包 看 <名字>")
            return "\n".join(lines)

        head, _, tail = arg.partition(" ")
        head_low = head.lower()
        tail = tail.strip()
        force = False
        for flag in ("--force", "-f", "--覆盖"):
            if flag in tail:
                force = True
                tail = tail.replace(flag, "").strip()
        if not tail:
            return "写法：/世界包 装 <名字> 或 /世界包 看 <名字>"

        pack = world_packs.find_pack(tail)
        if not pack:
            names = "、".join(p["name"] for p in packs) or "（没有包）"
            return "没找到这个世界卡包：%s\n现有：%s" % (tail, names)

        if head_low in ("装", "install", "加", "导入"):
            ok, msg = world_packs.install(pack["name"], overwrite=force)
            if not ok and force is False and "同名" in msg:
                msg += "\n（想覆盖就在命令末尾加 --force）"
            return msg

        if head_low in ("看", "show", "详情"):
            try:
                import json
                with open(pack["path"], encoding="utf-8") as f:
                    card = json.load(f)
            except Exception as e:
                return "这张卡读不出来：%s" % e
            lines = [world_packs.describe(pack),
                     "说明：" + (card.get("description") or "（无）")]
            rules = card.get("rules") or []
            if rules:
                lines.append("规则：")
                lines += ["  · " + str(r) for r in rules[:6]]
            for e in (card.get("entries") or [])[:3]:
                keys = "、".join(e.get("keys") or [])
                lines.append("世界书[%s]：%s" % (keys, str(e.get("content") or "")[:60]))
            lines.append("装法：/世界包 装 %s" % pack["name"])
            return "\n".join(lines)

        return "写法：/世界包 [列表] ｜ /世界包 装 <名字> [--force] ｜ /世界包 看 <名字>"
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌