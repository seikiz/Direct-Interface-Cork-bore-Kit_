# -*- coding: utf-8 -*-
"""空间（不能瞬移）—— `/在哪`、`/空间` 命令入口

功能本体在 `space_core.py`（地图 + 路费 + 开门时间 + 位置状态），它跟着核心走：
每轮回复时由 `DICK_core._space_injection()` 注入一小段【空间】，
模型用 `[loc:地名]` / `[ploc:地名]` 标注移动（标签会从显示文本剥掉）。

这个插件只干两件事：
  · `/在哪` 看状态；`/在哪 学校`、`/在哪 学校|骑车`、`/在哪 我=公司` 直接置位
  · `/空间` 开关与参数（交通方式偏好、可达列表条数、注入上限）

**为什么不声明 settings_schema**：与生活层同一个理由 —— 配置只有一份，住在
`space_config.json`（`space_core` 拥有）。插件再声明一套就会出现两个真相，
改了一个不生效。要看设置就打 `/空间`。
"""
import space_core
from plugin_base import PluginBase


class SpacePlugin(PluginBase):
    name = "空间（不能瞬移）"
    version = "1.0"
    description = "地图 + 路费 + 开门时间：她在哪、去哪要多久、来不及的地方别凭空出现"
    author = "DICK"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "空间：她在哪", "text": "/在哪"},
    ]

    # ---------- 取当前角色 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌/ 世界 ----------
    def _ctx(self):
        core = getattr(self, "core", None)
        role, world, scale = None, None, None
        try:
            roles = getattr(core, "active_roles", None) or []
            role = roles[0] if roles else None
        except Exception:
            role = None
        try:
            world = core.world_data if core else None
        except Exception:
            world = None
        try:
            scale = core._time_scale() if core else None
        except Exception:
            scale = None
        return role, world, scale

    # ---------- 命令 ----------
    def on_command(self, command, args):
        if command not in ("space", "空间", "在哪", "where"):
            return None
        cfg = space_core.load_config()
        role, world, scale = self._ctx()
        who = str((role or {}).get("name") or "她")
        arg = (args or "").strip()

        # 无参数 = 看状态（/在哪 与 /空间 共用）
        if not arg:
            return space_core.describe(role, world=world, scale=scale, cfg=cfg, name=who)

        head, _, tail = arg.partition(" ")
        head_low = head.lower()
        tail = tail.strip()

        if head_low in ("开", "on", "开启"):
            cfg["enabled"] = True
            space_core.save_config(cfg)
            return "空间层已开启（下一轮起注入【空间】）"
        if head_low in ("关", "off", "关闭"):
            cfg["enabled"] = False
            space_core.save_config(cfg)
            return "空间层已关闭"
        if head_low in ("交通", "方式", "transport"):
            if not tail:
                return "交通方式可选：" + "、".join(sorted(space_core.TRANSPORT))
            if tail not in space_core.TRANSPORT:
                return "认不出这个交通方式：%s\n可选：%s" % (
                    tail, "、".join(sorted(space_core.TRANSPORT)))
            cfg["default_transport"] = tail
            space_core.save_config(cfg)
            return "默认交通方式已设为：%s（耗时系数 %.2f）" % (tail, space_core.TRANSPORT[tail])
        if head_low in ("可达", "列表", "reachable"):
            cfg["show_reachable"] = not bool(cfg.get("show_reachable"))
            space_core.save_config(cfg)
            return "注入里%s列出这段时间够去的地方" % ("会" if cfg["show_reachable"] else "不再")
        if head_low in ("条数", "limit"):
            try:
                cfg["reachable_limit"] = max(0, min(12, int(tail)))
            except (TypeError, ValueError):
                return "条数要写数字（0–12）"
            space_core.save_config(cfg)
            return "可达列表最多 %d 条" % cfg["reachable_limit"]
        if head_low in ("长", "长度", "max"):
            try:
                cfg["max_chars"] = max(80, min(1200, int(tail)))
            except (TypeError, ValueError):
                return "注入上限要写数字（80–1200 字符）"
            space_core.save_config(cfg)
            return "注入上限已设为 %d 字符" % cfg["max_chars"]

        # 其余参数按"置位"处理：/在哪 学校 ｜ /在哪 学校|骑车 ｜ /在哪 我=公司
        body = arg
        if body.startswith("我=") or body.startswith("我＝"):
            place_part = body[2:].strip()
            place, _, by = place_part.partition("|")
            st, v = space_core.note_player_move(who, place.strip(), by=by.strip(),
                                                scale=scale, cfg=cfg)
            note = "" if v["ok"] else "（⚠ %s）" % v["why"]
            return "已记下：你 现在在 %s%s" % (place.strip(), note)

        place_part = body
        place, _, by = place_part.partition("|")
        place = place.strip()
        mp = space_core.map_for(role, world, cfg)
        st, v = space_core.note_move(who, place, by=by.strip(), scale=scale, mp=mp, cfg=cfg)
        note = "" if v["ok"] else "\n⚠ %s —— 但先按你说的记下了（下一轮会提醒补交代）" % v["why"]
        return "已记下：%s 现在在 %s%s" % (who, place, note)
