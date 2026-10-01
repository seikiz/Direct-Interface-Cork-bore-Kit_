# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   offline_advance.py —— 离线世界推进（你不在的时候，世界自己走了一小步）
#
#   现状：DICK 已经有"距离上一次说话已经过了 X（×时间流速）"这类**提示**，
#        但世界本身不会变 —— 回来时她的好感、状态、事件冷却都还停在离开那一刻。
#   这里补上后半截：把离线时长**结算**成实际变化，并给出可读的说明。
#
#   两条设计原则（都是被前面几轮教训逼出来的）：
#     ① 只算"说得清"的变化：好感缓慢下滑、数值状态回归初值、回合数推进（→ 事件冷却前进）。
#        绝不在没有 LLM 参与时凭空编事件 —— 编出来的东西玩家没法追溯。
#     ② 一律先出【方案】再应用：plan() 不碰任何状态，apply() 才改，且返回 undo 记录。
#        玩家点了"忽略"就什么都不发生。
#
#   时间从哪来：树里最新的节点时间戳（存档自带，随备份走）；没有就退回存档的 _tree_ts。
#   时间怎么算：现实秒数 × 时间流速倍率 = 软件时间（她那边过的时长）。
# ============================================================

import os
import re
from datetime import datetime, timezone

# 默认参数（可被机制卡里的 "offline" 段覆盖，见 DEFAULTS 的键名）
DEFAULTS = {
    "enabled": True,
    "min_real_minutes": 10.0,  # 【现实】里至少离开这么久才值得算（关键：绝不能按软件时间判）
    "min_hours": 6.0,          # 且软件时间也要够（她那边确实过了一段）
    "max_days": 30.0,          # 上限：再长也不按更长算（防数值失控）
    "aff_decay_per_day": 1.0,  # 软件时间每过一天，好感往下走多少
    "aff_max_delta": 8.0,      # 一次最多掉多少（防一次掉光）
    "aff_floor_ratio": 0.15,   # 好感下限：不低于量程的这个比例（关系不会归零）
    "status_decay_per_day": 0.5,  # 数值状态每天回归初值的比例（0.5 → 约十天走完）
    "turn_per_day": 1.0,       # 折算成几个"回合"（喂给按回合计的机制事件冷却）
    "turn_cap": 30,            # 折算回合的上限
}


def _cfg_of(mech_cfg):
    """从机制卡配置里取 offline 段，与默认值合并（缺项/坏值一律回落默认）"""
    out = dict(DEFAULTS)
    raw = None
    if isinstance(mech_cfg, dict):
        raw = mech_cfg.get("offline")
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k not in out:
                continue
            try:
                if isinstance(out[k], bool):
                    out[k] = bool(v)
                elif isinstance(out[k], int) and not isinstance(out[k], bool):
                    out[k] = int(v)
                else:
                    out[k] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def parse_ts(s):
    """容忍各种时间戳写法：ISO（带/不带时区、Z 结尾）、空格分隔、纯日期"""
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    if not isinstance(s, str) or not s.strip():
        return None
    t = s.strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                d = datetime.strptime(t[:len(fmt) + 2].strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def last_active(tree, fallback_ts=None):
    """这一局最后一次互动的时间：树里最新的节点时间戳 → 存档 _tree_ts → None"""
    best = None
    nodes = (tree or {}).get("nodes") if isinstance(tree, dict) else None
    if isinstance(nodes, dict):
        for n in nodes.values():
            if not isinstance(n, dict):
                continue
            d = parse_ts(n.get("timestamp"))
            if d and (best is None or d > best):
                best = d
    if best is None:
        best = parse_ts(fallback_ts)
    return best


def human_span(sec):
    """把软件时长说成人话（与 DICK_core 的时间提示同一口径）"""
    sec = float(max(0.0, sec))
    if sec < 90:
        return "%d 秒" % int(sec)
    if sec < 5400:
        return "%.1f 分钟" % (sec / 60.0)
    if sec < 86400 * 2:
        return "%.1f 小时" % (sec / 3600.0)
    days = sec / 86400.0
    return ("%.1f 天" % days) if days < 30 else ("%.1f 个月" % (days / 30.0))


def plan(tree, mech_cfg=None, mech_state=None, scale=None, now=None, cfg=None,
         dismissed_ts=None):
    """算一份【离线推进方案】—— 不修改任何状态。

    返回 dict：
      ok/skipped      是否有效；无效时 skipped 是人话原因
      elapsed_real_sec / elapsed_sw_sec / days   现实时长、软件时长、折算天数（已限量）
      affection       {"before","after","delta"} 或 None
      status          [{"k","before","after"}]    数值状态回归
      turns           折算出的回合数（喂事件冷却）
      summary / llm_brief                        人话说明、以及给可选 LLM 的上下文
    """
    conf = _cfg_of(mech_cfg)
    if cfg:
        conf.update({k: v for k, v in cfg.items() if k in conf})
    try:
        scale = float(scale if scale is not None else 1.0)
    except (TypeError, ValueError):
        scale = 1.0
    scale = max(0.0, scale)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    out = {"ok": False, "skipped": None, "scale": scale, "elapsed_real_sec": 0.0,
           "elapsed_sw_sec": 0.0, "days": 0.0, "affection": None, "status": [],
           "turns": 0, "summary": "", "llm_brief": "", "capped": False,
           "changes": False, "last_active": None}

    if not conf["enabled"]:
        out["skipped"] = "离线推进已在机制卡里关闭"
        return out
    last = last_active(tree)
    if last is None:
        out["skipped"] = "这局还没有可判断的时间戳（没有任何对话节点）"
        return out
    out["last_active"] = last.isoformat()
    dismissed = parse_ts(dismissed_ts)
    if dismissed and dismissed >= last:
        out["skipped"] = "这段时间已经处理过了"
        return out

    real = (now - last).total_seconds()
    if real < 0:                       # 时钟回拨/时区问题：别算出负的离线时间
        real = 0.0
    sw = real * scale
    out["elapsed_real_sec"] = real
    out["elapsed_sw_sec"] = sw
    # 两道门槛，缺一不可：
    #   ① 现实时间够久 —— 否则高速率下"切出去半分钟"就会弹一次（默认 720 倍时 6 软件小时
    #      只等于现实 30 秒，等于每次都触发）；
    #   ② 软件时间也够 —— 低倍率（甚至 ×1）时，现实十分钟在她那边也只过十分钟，不值得结算。
    # 这个口径是照 DICK_core.time_context_for 的既有判断来的："阈值按【现实】判，
    # 但报出来的数字要乘倍率"。
    min_real = conf["min_real_minutes"] * 60.0
    if real < min_real:
        out["skipped"] = "离开不到 %s（现实时间；判定按现实算，避免高倍率下频繁触发）" % \
                         human_span(min_real)
        return out
    need = conf["min_hours"] * 3600.0
    if sw < need:
        out["skipped"] = "她那边只过了 %s（软件时间不足 %s：现实 %.1f 分钟 ×%g 倍）" % (
            human_span(sw), human_span(need), real / 60.0, scale)
        return out
    days_raw = sw / 86400.0
    days = min(days_raw, conf["max_days"])
    out["days"] = days
    out["capped"] = days < days_raw

    st = None
    if isinstance(mech_state, dict):
        st = mech_state.get("mechanism_state") if isinstance(mech_state.get("mechanism_state"), dict) else mech_state
    aff_cfg = (mech_cfg or {}).get("affection") if isinstance(mech_cfg, dict) else None
    # ---- 好感：长时间不联系缓慢下滑（有上限与下限保护）----
    if isinstance(aff_cfg, dict) and aff_cfg.get("enabled") and isinstance(st, dict) \
            and st.get("affection") is not None:
        try:
            before = float(st.get("affection"))
        except (TypeError, ValueError):
            before = None
        if before is not None:
            try:
                lo = float(aff_cfg.get("min", 0) or 0)
                hi = float(aff_cfg.get("max", 100) or 100)
            except (TypeError, ValueError):
                lo, hi = 0.0, 100.0
            if hi <= lo:
                hi = lo + 100.0
            delta = -abs(conf["aff_decay_per_day"]) * days
            delta = max(-abs(conf["aff_max_delta"]), delta)
            floor = lo + (hi - lo) * float(conf["aff_floor_ratio"])
            after = max(floor, before + delta)
            after = min(hi, max(lo, after))
            if abs(after - before) >= 1e-9:
                out["affection"] = {"before": before, "after": round(after, 2),
                                    "delta": round(after - before, 2)}
                out["changes"] = True
    # ---- 数值状态：按比例回归初值（int/number 字段才动）----
    fields = ((mech_cfg or {}).get("status") or {}).get("fields") if isinstance(mech_cfg, dict) else None
    if isinstance(fields, list) and isinstance(st, dict):
        cur_status = st.get("status") if isinstance(st.get("status"), dict) else {}
        for f in fields:
            if not isinstance(f, dict):
                continue
            k = str(f.get("key") or f.get("k") or "").strip()
            typ = str(f.get("type") or "int").lower()
            if not k or typ in ("enum", "str", "string", "text", "bool"):
                continue
            try:
                before = float(cur_status.get(k))
                init = float(f.get("initial", 0) or 0)
            except (TypeError, ValueError):
                continue
            frac = min(1.0, abs(conf["status_decay_per_day"]) * days / 10.0)
            after = before + (init - before) * frac
            if abs(after - before) >= 1e-9:
                out["status"].append({"k": k, "before": before, "after": round(after, 2)})
                out["changes"] = True
    # ---- 折算回合（事件冷却是按回合计的，推进它 = 世界往前走了）----
    turns = int(days * conf["turn_per_day"])
    turns = max(0, min(int(conf["turn_cap"]), turns))
    out["turns"] = turns
    if turns:
        out["changes"] = True

    # ---- 人话说明 + 给可选 LLM 的上下文 ----
    parts = ["你离开了 %s（软件时间%s）" % (
        human_span(sw), "，已按上限 %g 天计" % conf["max_days"] if out["capped"] else "")]
    if out["affection"]:
        a = out["affection"]
        parts.append("好感 %g → %g" % (a["before"], a["after"]))
    for s in out["status"]:
        parts.append("%s %g → %g" % (s["k"], s["before"], s["after"]))
    if turns:
        parts.append("世界往前走了 %d 个回合（事件冷却据此推进）" % turns)
    out["ok"] = True
    out["summary"] = "；".join(parts) + "。"
    out["llm_brief"] = (
        "【离线推进】玩家离开了一段时间（软件时间 %s，约 %g 天%s）。"
        "这段时间里角色按自己的日常过活。请在回复里自然地体现这一点"
        "（她做过什么、心情如何、有没有提起你不在的时候），不要提问、不要复述这段说明。"
        % (human_span(sw), days, "，已按上限计" if out["capped"] else ""))
    return out


def apply(proposal, mech_state):
    """把方案落到机制状态上，返回 undo 记录（供 revert 或界面"撤销"用）"""
    if not isinstance(proposal, dict) or not proposal.get("ok") or not proposal.get("changes"):
        return None
    if not isinstance(mech_state, dict):
        return None
    st = mech_state.get("mechanism_state") if isinstance(mech_state.get("mechanism_state"), dict) else mech_state
    undo = {"affection": None, "status": {}, "turn": st.get("_turn")}
    if proposal.get("affection") and st.get("affection") is not None:
        undo["affection"] = st.get("affection")
        st["affection"] = proposal["affection"]["after"]
    if proposal.get("status"):
        cur = st.get("status") if isinstance(st.get("status"), dict) else {}
        st["status"] = cur
        for s in proposal["status"]:
            undo["status"][s["k"]] = cur.get(s["k"])
            cur[s["k"]] = s["after"]
    if proposal.get("turns"):
        try:
            st["_turn"] = int(st.get("_turn", 0) or 0) + int(proposal["turns"])
        except (TypeError, ValueError):
            st["_turn"] = int(proposal["turns"])
    undo["proposal_ok"] = True
    return undo


def revert(undo, mech_state):
    """撤销一次 apply（界面上的"撤销"按钮 / 测试用）"""
    if not isinstance(undo, dict) or not isinstance(mech_state, dict):
        return False
    st = mech_state.get("mechanism_state") if isinstance(mech_state.get("mechanism_state"), dict) else mech_state
    if undo.get("affection") is not None:
        st["affection"] = undo["affection"]
    for k, v in (undo.get("status") or {}).items():
        cur = st.get("status") if isinstance(st.get("status"), dict) else {}
        st["status"] = cur
        cur[k] = v
    if undo.get("turn") is not None:
        st["_turn"] = undo["turn"]
    return True


def summarize_for_chat(proposal):
    """把方案变成一条能进聊天记录的系统消息文本"""
    if not isinstance(proposal, dict) or not proposal.get("ok"):
        return ""
    return "🕰 " + (proposal.get("summary") or "")
