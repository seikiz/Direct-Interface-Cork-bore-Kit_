# -*- coding: utf-8 -*-
"""core_mech —— 从 Kit.py 拆出的 mixin（^_mech|^_battle|^_tick_buffs|^_eval_battle|^_pick_mech|^_init_mechanisms|^_leaf_mechanism|^mechanism_snapshot|^set_affection_percent|^restore_mechanisms|^check_mech_events|^_apply_event|^event_progress|^check_endings|^apply_mechanism_effect|^collapse_battle|^resolve_battle_move|^battle_ui_state|^strip_mechanism_tags|^_space_|^_consume_space）。

包含方法：_pick_mech_config、_init_mechanisms_from_tree、_leaf_mechanism_snapshot、mechanism_snapshot、set_affection_percent、restore_mechanisms、_consume_space_tags、_space_injection、strip_mechanism_tags、check_mech_events、_apply_event_affection、event_progress…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。
"""
from __future__ import annotations

import copy
import random
import operator
import math
import ast
import re

_FORMULA_LABELS = {
    "我方攻击": "player_atk", "玩家攻击": "player_atk", "攻击力": "player_atk", "攻击": "player_atk",
    "我方防御": "player_def", "玩家防御": "player_def", "防御力": "_def_", "防御": "_def_",
    "敌方攻击": "atk", "对方攻击": "atk",
    "敌方防御": "def", "对方防御": "def",
    "速度": "spd", "速": "spd",
    "灵力": "mp", "法力": "mp", "灵": "mp",
    "生命": "hp", "血量": "hp", "血": "hp",
}


_BATTLE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

_BATTLE_FUNCS = {
    "max": max, "min": min, "abs": abs,
    "floor": math.floor, "ceil": math.ceil, "round": round,
    "random": random.random, "randint": random.randint,
}


# 傻瓜化公式：中文标签 → 变量名（写卡用大白话，无需背英文变量）


def _normalize_formula(expr):
    """傻瓜化公式 → 可求值表达式：×→*、÷→/、全角括号→半角、中文标签→变量名（长词优先）。"""
    e = (expr or "")
    e = e.replace("×", "*").replace("÷", "/").replace("Ｘ", "x").replace("Ｘ", "X")
    e = e.replace("（", "(").replace("）", ")")
    for k in sorted(_FORMULA_LABELS, key=len, reverse=True):
        e = e.replace(k, _FORMULA_LABELS[k])
    return e


def eval_battle_formula(expr, vars_dict):
    """求值战斗伤害/防御公式（属性变量 + 四则运算 + max/min/floor/ceil/abs/random）。
    只接受白名单节点，杜绝任意代码执行。失败抛 ValueError。
    支持傻瓜化写法：×→*、÷→/、全角括号，以及中文标签（攻击/防御/速度/灵力/生命…）。"""
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("空公式")
    expr = _normalize_formula(expr)
    # 属性名可能是 Python 关键字（防御 def），做标识符替换
    expr = re.sub(r"\bdef\b", "_def_", expr.strip())
    vars_dict = dict(vars_dict)
    if "def" in vars_dict:
        vars_dict["_def_"] = vars_dict["def"]
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in vars_dict:
                v = vars_dict[node.id]
                if isinstance(v, (int, float)):
                    return float(v)
                raise ValueError(f"变量 {node.id} 非数值")
            raise ValueError(f"未知变量: {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in _BATTLE_OPS:
            return _BATTLE_OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _BATTLE_OPS:
            return _BATTLE_OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _BATTLE_FUNCS:
            fn = _BATTLE_FUNCS[node.func.id]
            args = [ev(a) for a in node.args]
            if node.func.id == "randint" and len(args) == 2:
                return float(random.randint(int(args[0]), int(args[1])))
            return float(fn(*args))
        raise ValueError("公式含不支持的语法")

    try:
        return float(ev(tree.body))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"公式求值失败: {e}")
from tree_repair import repair_links  # noqa: E402
from core_context import (ContextInjector, GAP_NOTICE_SECONDS, GAP_MAX_MARKS,  # noqa: E402
                          DAY_NOTICE_HOURS)
from core_tree import MessageNode, TreeManager  # noqa: E402, _iso_to_epoch


class MechMixin:
    """core_mech"""

    @staticmethod
    def _pick_mech_config(roles_data):
        """取第一个带机制配置的角色（群聊只跑第一份，避免状态打架）"""
        for r in roles_data or []:
            adv = r.get("advanced")
            if not isinstance(adv, dict):
                continue
            m = adv.get("mechanics")
            if isinstance(m, dict) and (m.get("affection") or m.get("status") or m.get("events")):
                return m
        return None


    def _init_mechanisms_from_tree(self, reset=False):
        """从角色配置初始化机制状态；若历史树已有快照则从当前叶子恢复。
        reset=True：强制全新会话（切角色/换配置），无快照也用 initial；
        reset=False（回溯兜底）：无快照时保留已累加状态（int 累加不清零）。"""
        _prev = self.mechanism_state
        self.mechanism_state = None
        cfg = self._mech_config
        if not cfg and not self._battle_config():
            return
        cfg = cfg or {}
        st = {"affection": 50, "status": {}, "flags": {},
              "_turn": 0, "event_counts": {}}
        aff = cfg.get("affection")
        if isinstance(aff, dict) and aff.get("enabled"):
            lo = int(aff.get("min", 0) or 0)
            hi = int(aff.get("max", 100) or 100)
            st["affection"] = max(lo, min(hi, int(aff.get("initial", 50) or 50)))
        status = cfg.get("status")
        if isinstance(status, dict) and status.get("enabled"):
            for f in (status.get("fields") or []):
                if not isinstance(f, dict) or not f.get("key"):
                    continue
                key = str(f["key"]).strip()
                st["status"][key] = f.get("initial", "" if f.get("type") == "enum" else 0)
        snap = self._leaf_mechanism_snapshot()
        if snap:
            st = snap
        elif getattr(self, "_persisted_mechanism_state", None):
            # 角色卡显式持久化的机制状态（修复"<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌清空/重选回落 initial"）：
            # 优先用它还原，比 initial 更有语义（这是"上一次保存的状态"）。
            st = dict(self._persisted_mechanism_state)
        elif _prev is not None and not reset:
            # 无快照（回溯到无 ms 的节点）且非强制重置：保留已累加的状态
            old = _prev
            if isinstance(old, dict):
                for k, v in st.items():
                    if k == "status" and isinstance(v, dict) and isinstance(old.get("status"), dict):
                        merged = dict(old["status"])
                        for sk, sv in v.items():
                            if sk not in merged:
                                merged[sk] = sv
                        old["status"] = merged
                    elif k not in old:
                        old[k] = v
                st = old
        self.mechanism_state = st


    def _leaf_mechanism_snapshot(self):
        """从当前叶子向上找最近的机制快照（metadata["ms"]）"""
        nid = self.tree.current_leaf_id
        guard = 0
        while nid and nid in self.tree.nodes and guard < 2000:
            ms = (self.tree.nodes[nid].metadata or {}).get("ms")
            if isinstance(ms, dict):
                return ms
            nid = self.tree.nodes[nid].parent_id
            guard += 1
        return None


    def mechanism_snapshot(self) -> Dict:
        try:
            return copy.deepcopy(self.mechanism_state or {})
        except Exception:
            return dict(self.mechanism_state or {})


    def set_affection_percent(self, percent=100):
        """METTERTOOLS：按上限百分比一键填好感（percent 0-100，默认 100=满上限）。
        按百分比算——因为上限不固定（默认 100 / 可配 1314），写死数值会不满。"""
        cfg = self._mech_config or {}
        aff = cfg.get("affection")
        if not isinstance(aff, dict) or not aff.get("enabled"):
            return None
        lo = int(aff.get("min", 0) or 0)
        hi = int(aff.get("max", 100) or 100)
        try:
            percent = int(percent)
        except (TypeError, ValueError):
            percent = 100
        percent = max(0, min(100, percent))
        val = int(round(hi * percent / 100.0))
        self.mechanism_state["affection"] = max(lo, min(hi, val))
        return self.mechanism_state["affection"]


    def restore_mechanisms(self, node_id):
        """回溯/切换分支：把机制状态恢复到目标节点那一刻的快照"""
        if not self._mech_config and not self._battle_config():
            return
        nid = node_id
        guard = 0
        while nid and nid in self.tree.nodes and guard < 2000:
            ms = (self.tree.nodes[nid].metadata or {}).get("ms")
            if isinstance(ms, dict):
                self.mechanism_state = ms
                return
            nid = self.tree.nodes[nid].parent_id
            guard += 1
        self._init_mechanisms_from_tree()

    # ---------- 空间层（不能瞬移）：位置标签 + 每轮注入 ----------

    # ---------- 空间层（不能瞬移）：位置标签 + 每轮注入 ----------
    def _space_role(self, speaker=None):
        roles = self.active_roles or []
        if not roles:
            return {}
        if speaker:
            for r in roles:
                if isinstance(r, dict) and r.get("name") == speaker:
                    return r
        return roles[0] if isinstance(roles[0], dict) else {}


    def _consume_space_tags(self, text, apply=True, speaker=None):
        """吃掉 [loc:地名] / [ploc:地名]（顺带记下她在哪）。

        为什么单独做、不塞进 strip_mechanism_tags 的主循环：那里面一开头就要求
        `self.mechanism_state` 与机制卡 —— 没有机制卡的角色也该能记位置。
        位置标签必须**永远**从显示文本里剥掉（玩家不该看到 [loc:学校]）。
        """
        if not text:
            return text
        try:
            import space_core as _sp
        except Exception as e:
            print("[space] 空间层加载失败: %s" % e)
            return text
        if not _sp.enabled():
            return _sp.strip_move_tags(text)
        moves = _sp.parse_move(text)
        if moves and apply:
            role = self._space_role(speaker)
            who = str(role.get("name") or "她")
            scale = self._time_scale()
            mp = _sp.map_for(role, self._life_world())
            for is_player, place, by in moves:
                try:
                    if is_player:
                        _sp.note_player_move(who, place, by=by, scale=scale, mp=mp)
                    else:
                        _sp.note_move(who, place, by=by, scale=scale, mp=mp)
                except Exception as e:
                    print("[space] 记位置失败（%s）: %s" % (place, e))
        return _sp.strip_move_tags(text)


    def _space_injection(self, chain=None, speaker=None):
        """每轮注入的【空间】。关掉 / 出错 → ""。"""
        try:
            import space_core as _sp
            if not _sp.enabled():
                return ""
            role = self._space_role(speaker)
            return _sp.injection_text(role, world=self._life_world(),
                                      scale=self._time_scale(), chain=chain,
                                      name=str(role.get("name") or "她"))
        except Exception as e:
            print("[space] 空间层注入失败: %s" % e)
            return ""


    def strip_mechanism_tags(self, text, apply=True, speaker=None):
        """解析机制标签：apply=True 时更新状态并剥离；apply=False 仅做显示剥离（流式）

        空间层的位置标签先处理（它不依赖机制卡），speaker 用来把群聊里的位置记到正确的人身上。
        """
        text = self._consume_space_tags(text, apply=apply, speaker=speaker)
        if not text or not self.mechanism_state:
            return text
        cfg = self._mech_config
        if not cfg and not self._battle_config():
            return text
        cfg = cfg or {}
        aff_cfg = cfg.get("affection") if isinstance(cfg.get("affection"), dict) else None
        status_fields = {}
        status_cfg = cfg.get("status")
        if isinstance(status_cfg, dict) and isinstance(status_cfg.get("fields"), list):
            status_fields = {str(f.get("key", "")).strip(): f
                             for f in status_cfg["fields"] if isinstance(f, dict) and f.get("key")}
        # 合并战斗属性字段（支持 [hp:-10] 等标签更新）
        for key, f in self._battle_attr_fields().items():
            if key not in status_fields:
                status_fields[key] = {"type": "int", "min": f["min"], "max": f["max"]}
        def repl(m):
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key.lower() == "aff":
                if not apply or not (aff_cfg and aff_cfg.get("enabled")):
                    return m.group(0) if not (aff_cfg and aff_cfg.get("enabled")) else ""
                try:
                    delta_pct = int(val)
                except ValueError:
                    return m.group(0)
                lo = int(aff_cfg.get("min", 0) or 0)
                hi = int(aff_cfg.get("max", 100) or 100)
                # 好感度按百分比算：[aff:+5] = 上限的 5%（100 上限时与绝对值一致）
                delta = int(round(hi * delta_pct / 100.0)) if delta_pct != 0 else 0
                cur = int(self.mechanism_state.get("affection", 0) or 0)
                self.mechanism_state["affection"] = max(lo, min(hi, cur + delta))
                try:
                    crit = float(aff_cfg.get("crit", 0.001) or 0.001)
                except (TypeError, ValueError):
                    crit = 0.001
                if crit > 0 and random.random() < crit:
                    self.mechanism_state["affection"] = hi
                return ""
            if key.lower() in ("ph", "player_hp"):
                # 玩家侧 HP（同规格待遇：玩家卡配了战斗属性才能被 AI 打掉）
                if not apply:
                    return ""
                try:
                    delta = int(val)
                except ValueError:
                    return m.group(0)
                player = (self.mechanism_state or {}).get("player")
                if not player:
                    return m.group(0)
                cur = int(player.get("hp", 100) or 100)
                player["hp"] = max(0, min(self.BATTLE_HP_CAP, cur + delta))
                return ""
            if key in status_fields:
                f = status_fields[key]
                if not apply:
                    return ""
                ftype = f.get("type", "enum")
                cur = self.mechanism_state["status"].get(key)
                if ftype == "int":
                    try:
                        raw = int(val)
                    except ValueError:
                        return m.group(0)
                    if isinstance(cur, (int, float)) and (val.startswith("+") or val.startswith("-")):
                        raw = int(cur) + raw
                    lo = int(f.get("min", 0) or 0)
                    hi = int(f.get("max", 100) or 100)
                    self.mechanism_state["status"][key] = max(lo, min(hi, raw))
                else:
                    self.mechanism_state["status"][key] = val
                return ""
            return m.group(0)  # 未知键原样保留（避免误删正文里的 [xx:yy]）

        return self.MECH_TAG.sub(repl, text)


    def check_mech_events(self, last_user_text):
        """检查事件条件；命中则标记并返回事件 dict。

        触发条件 = 好感区间（aff_ge/aff_le）+ 关键词（keywords，可留空）。
        关键词留空 = 不设闸门，只看好感 —— 这是推荐写法：
        玩家不该为了触发一个事件去猜该说哪个词。

        once 语义（once 缺省 True，与旧行为一致）：
          · once=True   → 触发一次后永久置 flag，不再触发
          · once=False  → 只受 cooldown 限制，可反复触发
        cooldown 以【轮】计（用 st["_turn"] 这个回合计数，
        不能用 event_log 长度 —— 那个只在触发时增长，冷却会算错）。
        """
        cfg = self._mech_config
        st = self.mechanism_state
        if not cfg or not st:
            return None
        # 回合计数：每检查一次算一回合
        try:
            st["_turn"] = int(st.get("_turn", 0) or 0) + 1
        except (TypeError, ValueError):
            st["_turn"] = 1
        events = cfg.get("events")
        if not isinstance(events, list):
            return None
        user_lower = (last_user_text or "").lower()
        for ev in events:
            if not isinstance(ev, dict) or not ev.get("id"):
                continue
            eid = str(ev["id"])
            once = ev.get("once", True)
            counts = st.get("event_counts")
            if not isinstance(counts, dict):
                counts = {}
                st["event_counts"] = counts
            rec = counts.get(eid) if isinstance(counts.get(eid), dict) else {}
            fired = int(rec.get("n", 0) or 0)
            if once and (fired > 0 or st.get("flags", {}).get(eid)):
                continue
            # 冷却：距上次触发不到 cooldown 轮就跳过（once=False 时才有意义）
            if not once and fired > 0:
                try:
                    cd = int(ev.get("cooldown", 0) or 0)
                except (TypeError, ValueError):
                    cd = 0
                last = int(rec.get("at", 0) or 0)
                if cd > 0 and (st["_turn"] - last) < cd:
                    continue
            ok = True
            try:
                if ev.get("aff_ge") is not None and int(st.get("affection", 0)) < int(ev["aff_ge"]):
                    ok = False
                if ok and ev.get("aff_le") is not None and int(st.get("affection", 0)) > int(ev["aff_le"]):
                    ok = False
            except (TypeError, ValueError):
                ok = False
            kws = ev.get("keywords")
            if ok and kws:
                if isinstance(kws, str):
                    kws = [kws]
                if not any(k and str(k).lower() in user_lower for k in kws):
                    ok = False
            if ok:
                st.setdefault("flags", {})[eid] = True
                # 事件触发顺序记录（供结局的 events_chain 判定"达成事件链"）
                log = st.setdefault("event_log", [])
                if eid not in log:
                    log.append(eid)
                # 次数 + 时间（cooldown 依赖它）
                counts[eid] = {"n": fired + 1, "at": st["_turn"]}
                # 事件自带的好感加成：让好感随剧情自动走，不必依赖模型每轮标 [aff]
                self._apply_event_affection(ev)
                return ev
        return None


    def _apply_event_affection(self, ev):
        """事件触发时自动加/减好感（ev['aff']，按上限百分比，与 [aff:+N] 同口径）。
        这就是"好感度自动化"：玩家不用管，剧情节点自己推动关系。"""
        try:
            aff = int(ev.get("aff", 0) or 0)
        except (TypeError, ValueError):
            return
        if aff == 0:
            return
        cfg = self._mech_config or {}
        aff_cfg = cfg.get("affection") if isinstance(cfg.get("affection"), dict) else None
        if not aff_cfg or not aff_cfg.get("enabled"):
            return
        st = self.mechanism_state
        if not st:
            return
        lo = int(aff_cfg.get("min", 0) or 0)
        hi = int(aff_cfg.get("max", 100) or 100)
        delta = int(round(hi * aff / 100.0))
        cur = int(st.get("affection", 0) or 0)
        st["affection"] = max(lo, min(hi, cur + delta))


    def event_progress(self, cfg=None):
        """事件进度：给面板用。返回 [{id, name, fired, times, ready, why, aff_ge, keywords}]。

        玩家看不到进度就会觉得事件坏了 —— 所以这个不带副作用，纯读。

        cfg 可显式传入（编辑器想预览"如果按这套配置会怎样"），
        不给就用当前生效的机制卡。
        """
        cfg = cfg if isinstance(cfg, dict) else (self._mech_config or {})
        st = self.mechanism_state or {}
        events = cfg.get("events")
        if not isinstance(events, list):
            return []
        try:
            aff = int(st.get("affection", 0) or 0)
        except (TypeError, ValueError):
            aff = 0
        counts = st.get("event_counts") if isinstance(st.get("event_counts"), dict) else {}
        flags = st.get("flags") if isinstance(st.get("flags"), dict) else {}
        out = []
        turn = int(st.get("_turn", 0) or 0)
        for ev in events:
            if not isinstance(ev, dict) or not ev.get("id"):
                continue
            eid = str(ev["id"])
            rec = counts.get(eid) if isinstance(counts.get(eid), dict) else {}
            fired = int(rec.get("n", 0) or 0)
            # 用 "at" 是否存在判断"触发过"，不能用 rec.get("at", 0) ——
            # 那样"从未触发"和"第 0 回合触发"会混为一谈（踩过一次，
            # 冷却中的事件被判成 ready，面板会骗玩家）。
            last = int(rec.get("at", 0) or 0) if "at" in rec else None
            once = ev.get("once", True)
            if once and (fired > 0 or flags.get(eid)):
                state, why = "fired", "已触发"
            elif fired > 0 and last is not None:
                try:
                    cd = int(ev.get("cooldown", 0) or 0)
                except (TypeError, ValueError):
                    cd = 0
                left = cd - (turn - last)
                if not once and left > 0:
                    state, why = "cooling", "冷却中（还差 %d 轮）" % left
                else:
                    state, why = "ready", "可以再次触发"
            else:
                need = ev.get("aff_ge")
                if need is not None:
                    try:
                        gap = int(need) - aff
                    except (TypeError, ValueError):
                        gap = 0
                    if gap > 0:
                        state, why = "blocked", "好感还差 %d（当前 %d/需要 %s）" % (gap, aff, need)
                    else:
                        state, why = "ready", "好感已达标，下一轮触发"
                else:
                    state, why = "ready", "无条件，下一轮触发"
            out.append({"id": eid, "name": ev.get("name") or eid, "fired": fired > 0,
                        "times": fired, "state": state, "why": why,
                        "aff_ge": ev.get("aff_ge"), "keywords": ev.get("keywords") or []})
        return out


    def check_endings(self):
        """结局达成检测：读取 mechanics.endings，判定是否达成（事件链/状态/好感 组合）。命中返回结局 dict。
        when 支持：aff_ge/aff_le/flag/status/events(全部)/events_any/events_count/events_chain(顺序)。"""
        cfg = self._mech_config
        st = self.mechanism_state
        if not cfg or not st:
            return None
        endings = cfg.get("endings")
        if not isinstance(endings, list):
            return None

        def when_match(w):
            if not isinstance(w, dict):
                return False
            try:
                aff = int(st.get("affection", 0) or 0)
            except (TypeError, ValueError):
                aff = 0
            if w.get("aff_ge") is not None and aff < int(w["aff_ge"]):
                return False
            if w.get("aff_le") is not None and aff > int(w["aff_le"]):
                return False
            flags = st.get("flags", {}) or {}
            if w.get("flag") and not flags.get(str(w["flag"])):
                return False
            status_w = w.get("status")
            if isinstance(status_w, dict):
                status = st.get("status") or {}
                for k, want in status_w.items():
                    cur = status.get(str(k))
                    cur_s = "" if cur is None else str(cur)
                    if str(cur_s) != str(want):
                        return False
            events = w.get("events")
            if isinstance(events, list) and any(not flags.get(str(ev)) for ev in events):
                return False
            any_ = w.get("events_any")
            if isinstance(any_, list) and not any(flags.get(str(ev)) for ev in any_):
                return False
            cnt = w.get("events_count")
            if isinstance(cnt, dict):
                of = cnt.get("of") or []
                mn = int(cnt.get("min", 1) or 1)
                if sum(1 for ev in of if flags.get(str(ev))) < mn:
                    return False
            chain = w.get("events_chain")
            if isinstance(chain, list):
                log = st.get("event_log") or []
                li = 0
                for s in chain:
                    found = False
                    while li < len(log):
                        if str(log[li]) == str(s):
                            found = True
                            li += 1
                            break
                        li += 1
                    if not found:
                        return False
            return True

        ordered = sorted(endings, key=lambda e: (e.get("priority") if isinstance(e.get("priority"), (int, float)) else float("inf")))
        for e in ordered:
            if isinstance(e, dict) and when_match(e.get("when")):
                return e
        return None


    def apply_mechanism_effect(self, effect):
        """应用 GAL 选项附带的效果：{"aff": int, "st": {key: value}}"""
        cfg = self._mech_config
        st = self.mechanism_state
        if not cfg or not st or not isinstance(effect, dict):
            return
        aff = effect.get("aff")
        if aff is not None:
            aff_cfg = cfg.get("affection") if isinstance(cfg.get("affection"), dict) else None
            if aff_cfg and aff_cfg.get("enabled"):
                lo = int(aff_cfg.get("min", 0) or 0)
                hi = int(aff_cfg.get("max", 100) or 100)
                # 好感度按百分比算：aff 值 = 上限的百分比
                delta = int(round(hi * int(aff) / 100.0)) if int(aff) != 0 else 0
                cur = int(st.get("affection", 0) or 0)
                st["affection"] = max(lo, min(hi, cur + delta))
                try:
                    crit = float(aff_cfg.get("crit", 0.001) or 0.001)
                except (TypeError, ValueError):
                    crit = 0.001
                if crit > 0 and random.random() < crit:
                    st["affection"] = hi
        stmap = effect.get("st")
        status_cfg = cfg.get("status")
        if isinstance(stmap, dict) and isinstance(status_cfg, dict) and status_cfg.get("enabled"):
            fields = {str(f.get("key", "")).strip(): f for f in (status_cfg.get("fields") or [])
                      if isinstance(f, dict) and f.get("key")}
            for k, v in stmap.items():
                k = str(k).strip()
                if k not in fields:
                    continue
                f = fields[k]
                if f.get("type") == "int":
                    raw_s = str(v).strip()
                    try:
                        v = int(raw_s)
                    except (TypeError, ValueError):
                        continue
                    lo = int(f.get("min", 0) or 0)
                    hi = int(f.get("max", 100) or 100)
                    cur = st["status"].get(k)
                    # GAL 选项：int 一律按相对值累加（无符号也 +N），杜绝"1 覆盖 2"
                    if isinstance(cur, (int, float)) and v != 0:
                        v = int(cur) + v
                    st["status"][k] = max(lo, min(hi, v))
                else:
                    st["status"][k] = str(v)


    def _mech_prompt_block(self, mech):
        """把机制配置渲染成注入系统提示的规则块"""
        lines = []
        aff = mech.get("affection")
        if isinstance(aff, dict) and aff.get("enabled"):
            lo = int(aff.get("min", 0) or 0)
            hi = int(aff.get("max", 100) or 100)
            cur = (self.mechanism_state or {}).get("affection")
            cur = lo if cur is None else int(cur)
            lines.append(
                f"【机制·好感度】当前好感度 {cur}/{hi}（范围 {lo}-{hi}，数值越高越亲近）。"
                "每轮回复末尾用 [aff:+N] 或 [aff:-N] 标签表示好感度变化（N 为百分比，即上限的 N%，根据剧情自然判定，"
                "通常 -5~+5；无变化则不输出标签，不要解释标签）。")
        status = mech.get("status")
        if isinstance(status, dict) and status.get("enabled"):
            fields = [f for f in (status.get("fields") or []) if isinstance(f, dict) and f.get("key")]
            if fields:
                cur_status = (self.mechanism_state or {}).get("status") or {}
                desc = [f"{f.get('name') or f['key']}={cur_status.get(str(f['key']), f.get('initial', ''))}"
                        for f in fields]
                keys = "、".join(str(f["key"]) for f in fields)
                lines.append("【机制·状态栏】当前状态：" + "，".join(desc) + "。"
                             "状态变化时在回复末尾用 [键:值] 标签标注（键名：" + keys +
                             "；整数型支持 [键:+N] 相对增减、[键:N] 绝对值；枚举型直接给值），无变化则不输出。")
        evs = mech.get("events")
        if isinstance(evs, list) and evs:
            desc = []
            for ev in evs:
                if not isinstance(ev, dict) or not ev.get("id"):
                    continue
                conds = []
                if ev.get("aff_ge") is not None:
                    conds.append(f"好感度≥{ev['aff_ge']}")
                if ev.get("aff_le") is not None:
                    conds.append(f"好感度≤{ev['aff_le']}")
                if ev.get("keywords"):
                    kws = ev["keywords"] if isinstance(ev["keywords"], list) else [ev["keywords"]]
                    conds.append("提到" + "/".join(str(k) for k in kws))
                if ev.get("once") is False:
                    cd = ev.get("cooldown") or 0
                    conds.append("可重复" + (f"，冷却{cd}轮" if cd else ""))
                desc.append(f"{ev.get('name') or ev['id']}（{'且'.join(conds) if conds else '无条件'}）")
            lines.append("【机制·事件】存在条件事件：" + "；".join(desc) + "。条件满足时事件提示会自动注入，照常演出即可。")
        return "\n".join(lines)

    # ================= 战斗系统（招式触发 / 伤害防御公式 / buff） =================
    BATTLE_LEGEND_CHANCE = 0.00001  # 天选之人：战斗系统独占，不能作弊
    # 防数值膨胀：人物血上限 150（写卡不可超，BOSS 卡可豁免）；普攻封顶到「满血 150 至少 5 回合杀不死」（5×29<150，第6回合才死）；招式最高 50。
    BATTLE_HP_CAP = 150
    BASIC_ATTACK_DAMAGE_CAP = max(1, 150 // 5 - 1)  # 29（普攻，5 回合杀不死满血）
    MOVE_DAMAGE_CAP = 50                                    # 招式（技能）最高 50 点


    def _battle_config(self):
        """取激活角色的战斗配置（第一个启用的）"""
        for r in self.active_roles or []:
            adv = r.get("advanced")
            if not isinstance(adv, dict):
                continue
            b = adv.get("battle")
            if isinstance(b, dict) and b.get("enabled"):
                return b
        return None


    def _battle_attr_fields(self):
        """战斗属性字段定义：{key: {type:int, min, max, label}}（供标签解析与 UI 用）"""
        cfg = self._battle_config()
        out = {}
        if not cfg:
            return out
        attrs = cfg.get("attrs") or {}
        for key, a in attrs.items():
            if not isinstance(a, dict):
                continue
            out[str(key)] = {"type": "int", "min": 0,
                             "max": int(a.get("max", 999999) or 999999),
                             "label": str(a.get("label") or key)}
        for a in (cfg.get("mech_attrs") or []):
            if not isinstance(a, dict) or not a.get("key"):
                continue
            key = str(a["key"])
            out[key] = {"type": "int", "min": 0,
                        "max": int(a.get("max", 999999) or 999999),
                        "label": str(a.get("label") or key)}
        return out


    def collapse_battle_values(self):
        """坍缩（十万分之一事件）：把战斗卡的所有数值统一变为 2000。
        角色侧战斗属性 + 玩家侧战斗属性全部坍缩为 2000（名称即效果）。"""
        st = self.mechanism_state
        if st is None:
            st = {"affection": 50, "status": {}, "flags": {}, "buffs": [],
                  "_turn": 0, "event_counts": {}}
            self.mechanism_state = st
        status = st.setdefault("status", {})
        # 角色侧：战斗配置里的所有属性键（attrs + mech_attrs）坍缩为 2000
        for key in self._battle_attr_fields():
            status[key] = 2000
        # 玩家侧：玩家卡战斗属性同样坍缩为 2000
        player = st.setdefault("player", {})
        for key in list(player.keys()):
            if key == "turns":
                continue
            if isinstance(player.get(key), (int, float)):
                player[key] = 2000
        st.setdefault("buffs", [])
        st["collapsed"] = True
        self.battle_state = self.battle_state or {"turns": 0}
        return True


    def _eval_battle_formula(self, expr, extra_vars=None):
        """便捷求值：公式上下文 = 当前敌方(角色)属性 + 玩家属性 + 额外变量"""
        st = (self.mechanism_state or {}).get("status") or {}
        vars_dict = dict(st)
        player = (self.mechanism_state or {}).get("player") or {}
        vars_dict.update({"player_atk": player.get("atk", 10),
                          "player_def": player.get("def", 5),
                          "player_hp": player.get("hp", 100)})
        if extra_vars:
            vars_dict.update(extra_vars)
        return eval_battle_formula(expr, vars_dict)


    def resolve_battle_move(self, move_id):
        """结算玩家出招：消耗→暴击判定→伤害公式→扣敌方 HP→挂 buff→buff tick。
        返回 (结算文本 or None, 是否传说事件)"""
        cfg = self._battle_config()
        st = self.mechanism_state
        if not cfg or not st:
            return None, False
        move = None
        for m in (cfg.get("moves") or []):
            if isinstance(m, dict) and str(m.get("id", "")).strip() == str(move_id):
                move = m
                break
        if not move:
            return None, False
        status = st.setdefault("status", {})
        # 消耗检查
        for k, v in (move.get("cost") or {}).items():
            if int(status.get(str(k), 0) or 0) < int(v):
                return f"⚠️ {move.get('name', move_id)} 需要 {k} {v}，当前不足", False
        # 暴击判定
        formulas = cfg.get("formulas") or {}
        try:
            crit_chance = self._eval_battle_formula(str(formulas.get("crit_chance", "0.1")))
        except Exception:
            crit_chance = 0.1
        is_crit = random.random() < max(0.0, min(1.0, crit_chance))
        try:
            crit_mult = self._eval_battle_formula(str(formulas.get("crit_mult", "2")))
        except Exception:
            crit_mult = 2.0
        mult = crit_mult if is_crit else 1.0
        # 伤害公式（招式自带 > 全局 damage 公式 > 默认）
        expr = str(move.get("formula") or formulas.get("damage") or "player_atk * 2 - def")
        try:
            dmg = int(self._eval_battle_formula(expr) * mult)
        except ValueError as e:
            return f"⚠️ 招式公式错误：{e}", False
        dmg = max(1, dmg)
        # 防数值膨胀：普攻（无自定义公式，走默认伤害）封顶 29（满血150至少5回合打不死）；招式（自带公式）最高50。
        cap = self.MOVE_DAMAGE_CAP if move.get("formula") else self.BASIC_ATTACK_DAMAGE_CAP
        dmg = min(dmg, cap)
        hp_key = "hp"
        status[hp_key] = max(0, int(status.get(hp_key, 0) or 0) - dmg)
        # 消耗
        for k, v in (move.get("cost") or {}).items():
            status[str(k)] = max(0, int(status.get(str(k), 0) or 0) - int(v))
        # 挂 buff（招式附加，同 id 刷新）
        for b in (move.get("buffs") or []):
            if isinstance(b, dict) and b.get("id"):
                buffs = st.setdefault("buffs", [])
                buffs[:] = [x for x in buffs if x.get("id") != str(b["id"])]
                buffs.append({"id": str(b["id"]), "turns": int(b.get("turns", 3) or 3)})
        self._tick_buffs()
        # 天选之人：0.00001%（战斗系统独占）
        is_legend = random.random() < self.BATTLE_LEGEND_CHANCE
        crit_txt = "（暴击！）" if is_crit else ""
        dmg_txt = f"💥 {move.get('name', move_id)}！造成 {dmg} 点伤害{crit_txt}，对方生命 {status[hp_key]}。"
        if is_legend:
            dmg_txt += "【天命触发】"
        return dmg_txt, is_legend


    def _tick_buffs(self):
        """每回合结算 buff：应用回合效果（中毒扣血等）→ 剩余回合 -1 → 到期移除"""
        st = self.mechanism_state
        if not st:
            return
        buffs = st.get("buffs") or []
        if not buffs:
            return
        cfg = self._battle_config() or {}
        defs = {str(b.get("id", "")): b for b in (cfg.get("buffs") or [])
                if isinstance(b, dict) and b.get("id")}
        status = st.setdefault("status", {})
        kept = []
        for b in buffs:
            d = defs.get(str(b.get("id") or ""))
            if d:
                for k, v in (d.get("attrs") or {}).items():
                    key = str(k)
                    if key in status:
                        status[key] = max(0, int(status[key] or 0) + int(v))
                        if key == "hp":
                            status[key] = min(status[key], self.BATTLE_HP_CAP)
            turns = int(b.get("turns", 1) or 1) - 1
            if turns > 0:
                b["turns"] = turns
                kept.append(b)
        st["buffs"] = kept


    def battle_ui_state(self):
        """给前端：战斗配置摘要 + 当前属性 + buff 列表"""
        cfg = self._battle_config()
        if not cfg:
            return None
        st = (self.mechanism_state or {}).get("status") or {}
        collapsed = bool((self.mechanism_state or {}).get("collapsed"))
        attrs = []
        for key, f in self._battle_attr_fields().items():
            attrs.append({"key": key, "label": f["label"],
                          "value": int(st.get(key, 0) or 0),
                          "max": 2000 if collapsed else int(f["max"])})
        moves = [{"id": str(m.get("id", "")), "name": str(m.get("name") or m.get("id", "")),
                  "desc": str(m.get("desc") or "")}
                 for m in (cfg.get("moves") or []) if isinstance(m, dict) and m.get("id")]
        buffs = []
        for b in (st.get("buffs") or []):
            buffs.append({"id": str(b.get("id", "")), "turns": int(b.get("turns", 0) or 0)})
        # 玩家侧属性（同规格：玩家卡配的战斗属性）
        player = (self.mechanism_state or {}).get("player") or {}
        player_attrs = [{"key": k, "label": k, "value": int(v), "max": 2000 if collapsed else 999999}
                        for k, v in player.items() if k != "turns" and isinstance(v, (int, float))]
        return {"attrs": attrs, "moves": moves, "buffs": buffs,
                "hp": int(st.get("hp", 0) or 0), "player": player_attrs}


    def _battle_prompt_block(self, cfg):
        """战斗规则注入系统提示"""
        st = (self.mechanism_state or {}).get("status") or {}
        lines = []
        # 玩家侧属性（同规格：玩家卡配的战斗属性）
        player = (self.mechanism_state or {}).get("player") or {}
        if player:
            pdesc = [f"{k}={v}" for k, v in player.items() if k != "turns" and isinstance(v, (int, float))]
            if pdesc:
                lines.append("【玩家属性】" + "、".join(pdesc)
                             + "。玩家的生命可用 [ph:-N] 标签修正（你攻击玩家时用 [ph:-10] 表示对其造成 10 伤害）。")
        fields = self._battle_attr_fields()
        if fields:
            desc = [f"{f['label']}={st.get(key, 0)}" for key, f in fields.items()]
            lines.append("【战斗属性】" + "、".join(desc) + "（数值由战斗系统维护，你的回复可用 [键:值] 标签修正）。")
        moves = cfg.get("moves") or []
        if moves:
            names = [f"{m.get('name') or m['id']}（{m.get('desc') or ''}）"
                     for m in moves if isinstance(m, dict) and m.get("id")]
            lines.append("【招式】玩家可通过出招战斗：" + "、".join(names)
                         + "。出招伤害与消耗由系统结算，你负责以角色口吻演出战斗过程、受击反应与战况播报。")
        buffs = cfg.get("buffs") or []
        if buffs:
            names = [f"{b.get('name') or b['id']}（{b.get('desc') or ''}）"
                     for b in buffs if isinstance(b, dict) and b.get("id")]
            lines.append("【状态效果】" + "、".join(names) + "。效果持续回合并在每回合结算时生效。")
        return "\n".join(lines)

    def _init_battle(self):
        """战斗初始化：属性并入机制状态 status（新战斗取初值，续聊保留快照）；battle_state 重置"""
        cfg = self._battle_config()
        self.battle_state = None
        if not cfg:
            return
        st = self.mechanism_state
        if st is None:
            # 无机制卡但启用战斗：初始化基础机制状态承载战斗属性
            st = {"affection": 50, "status": {}, "flags": {}, "buffs": [],
                  "_turn": 0, "event_counts": {}}
            self.mechanism_state = st
        status = st.setdefault("status", {})
        attrs = cfg.get("attrs") or {}
        for key, a in attrs.items():
            if not isinstance(a, dict):
                continue
            key = str(key)
            if key not in status:
                if key == "hp":
                    _v = int(a.get("max", 999999) or 999999)
                    # BOSS 卡可突破血上限（cfg.boss=true）；普通人物硬上限 150
                    status[key] = _v if cfg.get("boss") else min(self.BATTLE_HP_CAP, _v)
                else:
                    status[key] = int(a.get("initial", 10) or 10)
        # 机制属性（第四属性等）：独立初值
        for a in (cfg.get("mech_attrs") or []):
            if isinstance(a, dict) and a.get("key") and str(a["key"]) not in status:
                status[str(a["key"])] = int(a.get("initial", 10) or 10)
        st.setdefault("buffs", [])
        # 玩家侧属性：玩家卡 advanced.battle（同规格待遇）→ 否则默认 100/10/5
        # 存入 mechanism_state["player"] → 随树快照，回溯/分支时玩家 HP 一并恢复
        player = {"hp": 100, "atk": 10, "def": 5}
        padv = {}
        if self.player_persona and isinstance(self.player_persona, dict):
            padv = self.player_persona.get("advanced") or {}
            if not isinstance(padv, dict):
                padv = {}
        pb = padv.get("battle")
        if isinstance(pb, dict) and pb.get("enabled"):
            pattrs = pb.get("attrs") or {}
            for key, a in pattrs.items():
                if not isinstance(a, dict):
                    continue
                key = str(key)
                player[key] = min(self.BATTLE_HP_CAP, int(a.get("max", 999999) or 999999)) if key == "hp" \
                    else int(a.get("initial", 10) or 10)
            for a in (pb.get("mech_attrs") or []):
                if isinstance(a, dict) and a.get("key"):
                    player[str(a["key"])] = int(a.get("initial", 10) or 10)
        if "player" in st:
            # 续聊/回溯：保留快照里的玩家状态。hp 是战斗实时值必须保留；
            # 其余属性以配置为准（玩家卡改了 atk/def 应立即生效，不被旧快照覆盖）
            snap = st.get("player") or {}
            if isinstance(snap, dict):
                for k, v in snap.items():
                    if k == "hp" and isinstance(v, (int, float)):
                        player["hp"] = v
        st["player"] = player
        self.battle_state = {"turns": 0}
