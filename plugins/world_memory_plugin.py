# -*- coding: utf-8 -*-
"""世界记忆（演化）—— `/世界记忆` 命令入口 + 每轮抽取

本体在 `world_memory.py`（抽取 / 归并 / 衰减 / 检索 / 注入）。这个插件只干两件事：

  · `on_message_received`：**一轮结束后**抽取"世界级事实"并归并落盘
    （由界面层派发到 plugin 线，带 15 秒超时，不挡回复）。
  · `/世界记忆`：看状态、清、忘、钉、开关、改注入上限。

为什么抽取放在这个钩子而不是注入里：注入是每轮必经的读路径，**必须只读** ——
同一轮重试/重放不该把强度刷上去（空间层的"穿帮提醒计数"是反例，它必须在注入里 +1；
世界记忆不需要那样：事实已经写下来了，重试只是重新渲染那一段文本）。

**为什么不声明 settings_schema**：与生活层/空间层同一个理由 —— 配置只有一份，
住在 `world_memory_config.json`（`world_memory` 拥有）。插件再声明一套就会出现两个真相，
改了一个不生效。要看设置就打 `/世界记忆`。
"""
import world_memory
from plugin_base import PluginBase


class WorldMemoryPlugin(PluginBase):
    name = "世界记忆（演化）"
    version = "1.0"
    description = "把剧情里发生过的世界级事实沉淀成「这个世界现在是什么样」：冲突按时间取最新，按世界时间衰减"
    author = "DICK"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "世界记忆：这个世界现在什么样", "text": "/世界记忆"},
    ]

    # ---------- 取当前角色 / <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌世界 / 倍率 ----------
    def _ctx(self):
        core = getattr(self, "core", None)
        role, world, scale = None, None, None
        try:
            roles = getattr(core, "active_roles", None) or []
            role = roles[0] if roles else None
        except Exception:
            role = None
        try:
            world = getattr(core, "world_data", None)
        except Exception:
            world = None
        try:
            scale = core._time_scale() if core else None
        except Exception:
            scale = None
        return role, world, scale

    # ---------- 每轮：抽取 → 归并 → 落盘 ----------
    def on_message_received(self, user_input, ai_reply):
        try:
            if not world_memory.enabled():
                return
            role, world, scale = self._ctx()
            who = str((role or {}).get("name") or "她")
            r = world_memory.note_turn(user_input, ai_reply, world=world, speaker=who,
                                      scale=scale)
            if r.get("added") or r.get("conflict"):
                total, live = world_memory.stats(world, scale=scale)
                print("[world_memory] %s：新增 %d、归并 %d、冲突改写 %d，共 %d 条（还在注入里 %d 条）"
                      % (world_memory.world_key(world), r.get("added", 0), r.get("merged", 0),
                         r.get("conflict", 0), total, live))
        except Exception as e:
            # 不静默：世界记忆抽不出来只该少记一条，不该把钩子弄挂（也不该悄悄失败）
            print("[world_memory] 抽取失败: %s" % e)

    # ---------- 命令 ----------
    def on_command(self, command, args):
        if command not in ("world_memory", "世界记忆", "worldmemory"):
            return None
        cfg = world_memory.load_config()
        role, world, scale = self._ctx()
        who = str((role or {}).get("name") or "她")
        arg = (args or "").strip()
        if not arg:
            return world_memory.describe(world, scale=scale, cfg=cfg, name=who)

        head, _, tail = arg.partition(" ")
        head_low = head.lower()
        tail = tail.strip()

        if head_low in ("开", "on", "开启"):
            cfg["enabled"] = True
            world_memory.save_config(cfg)
            return "世界记忆已开启（下一轮起注入【世界·演化】）"
        if head_low in ("关", "off", "关闭"):
            cfg["enabled"] = False
            world_memory.save_config(cfg)
            return "世界记忆已关闭（已记下的事还在 %s 里）" % world_memory.state_path(world, cfg)
        if head_low in ("清", "clear"):
            n = world_memory.clear(world, cfg)
            return ("已清空「%s」的世界记忆（%d 条）。注意：清的是**这个世界**的记忆，"
                    "不是聊天记录；其它世界不受影响。" % (world_memory.world_key(world), n))
        if head_low in ("忘", "forget", "删"):
            if not tail:
                return "用法：/世界记忆 忘 <关键词>（按主语/状态/原始说法匹配）"
            n = world_memory.forget(world, tail, cfg)
            return ("忘了 %d 条（含「%s」的）" % (n, tail)) if n else ("没有匹配「%s」的事实" % tail)
        if head_low in ("钉", "pin"):
            if not tail:
                return "用法：/世界记忆 钉 <关键词>（钉住的永不淡出）"
            n = world_memory.pin(world, tail, True, cfg)
            return ("钉住了 %d 条" % n) if n else ("没有匹配「%s」的事实" % tail)
        if head_low in ("松", "unpin"):
            if not tail:
                return "用法：/世界记忆 松 <关键词>"
            n = world_memory.pin(world, tail, False, cfg)
            return ("松开了 %d 条" % n) if n else ("没有匹配「%s」的事实" % tail)
        if head_low in ("长", "长度", "max"):
            try:
                cfg["max_chars"] = max(80, min(1200, int(tail)))
            except (TypeError, ValueError):
                return "注入上限要写数字（80–1200 字符）"
            world_memory.save_config(cfg)
            return "注入上限已设为 %d 字符" % cfg["max_chars"]
        if head_low in ("半衰", "衰减", "half"):
            try:
                v = max(1.0, min(3650.0, float(tail)))
            except (TypeError, ValueError):
                return ("用法：/世界记忆 半衰 <世界天>（当前地点/物品 %.1f 天，组织/关系 %.1f 天；"
                        "规则不衰减）" % (world_memory.half_life_of("place", cfg),
                                        world_memory.half_life_of("org", cfg)))
            cfg["half_life_days"] = v
            world_memory.save_config(cfg)
            return "地点/物品的半衰期已设为 %.1f 世界天（组织/关系仍为 %.1f 天）" % (
                v, world_memory.half_life_of("org", cfg))

        return ("用法：/世界记忆 ｜ 清 ｜ 忘 <关键词> ｜ 钉|松 <关键词> ｜ 开|关 ｜ "
                "长 <80-1200> ｜ 半衰 <世界天>")
