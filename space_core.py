# -*- coding: utf-8 -*-
"""space_core.py —— 空间层：人不能瞬移

为什么做
--------
吃饭那层解决的是"她有日子"；这层解决的是"她不会瞬移"。
现在的提示词里没有任何空间约束：上一轮她还在家，下一轮就能出现在学校、外地、甚至另一个城市，
中间连一句"路上"都不用交代。这不是模型笨 —— 是**根本没人告诉它两地要多久**。

和 life_core 同一套思路：
  · 资料是**约束**（地图 + 路上要多久 + 开门时间），不是装饰
  · 状态能算就算、必须存就存得极小（一个角色一个 json，只记"她此刻在哪、什么时候到的"）
  · 每轮只注入一小段（默认 ≤ 240 字），按优先级吃预算
  · 出错不静默（打印），没配置也能降级跑

世界时间怎么算（与 life_core 同源）
----------------------------------
节点时间戳就是系统本地时间；位置状态里记的是**现实时刻**。于是：
    那边过了多少分钟 =（现在 − 到达时刻）× 倍率 / 60
倍率取 time_scale（默认 720）。所以"现实里隔了 2 分钟"，在那边就是 24 小时 ——
足够她坐高铁去外地了；反过来现实只隔 5 秒，那边才过 1 小时，她就不能跨城。

地图：轮辐模型（hub-and-spoke）
-------------------------------
家 = 圆心。每个地点只记"从家过去要多少分钟"，两地之间按 经过家 估算：
    cost(家→X) = travel[X]
    cost(A→B)  = travel[A] + travel[B]      （A、B 都不是家时，走 家 中转）
这样估出来**偏保守**（不允许瞬移），比"随便给个相近值"安全；要精确就在卡里写 links 覆盖。
交通方式给速度系数：走路 1.0 / 骑车 0.4 / 公交地铁 0.5 / 打车 0.35 / 开车 0.3 / 高铁 0.06。

地点标签（模型怎么告诉我们她在哪）
----------------------------------
    [loc:学校]            她移动到学校（走默认交通方式）
    [loc:学校|骑车]        带交通方式
    [ploc:公司]           玩家（你）的位置
这两个标签会从显示文本里剥掉（和 [aff:+3] 一个规矩），并在 apply=True 时写进状态。
**已经发生的事不逆转**：如果这一跳时间不够，我们照样记下新位置（文本都写出来了），
但会在下一轮的注入里点名："上一轮她 2 分钟前还在家，现在写到学校：路上要 25 分钟，
缺交代 —— 要么补一句骑车/路上，要么改回原处。"
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta

import app_paths

try:                      # 原子写：跟存档一个待遇，别写出半个 json
    import save_guard
except Exception:         # pragma: no cover - 极端情况下退化成普通写
    save_guard = None

# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  一、地图（内置默认；角色卡 / 世界卡可覆盖）
# ============================================================
HUB = "家"

# minutes 取值口径：步行/常规交通，从家出发单程
DEFAULT_PLACES = [
    {"name": "家", "minutes": 0, "open": None, "note": "她的据点"},
    {"name": "楼下", "minutes": 2, "open": None},
    {"name": "小区门口", "minutes": 3, "open": None},
    {"name": "便利店", "minutes": 6, "open": (7, 23)},
    {"name": "公交站", "minutes": 8, "open": (5, 23)},
    {"name": "菜市场", "minutes": 10, "open": (6, 19)},
    {"name": "超市", "minutes": 12, "open": (8, 22)},
    {"name": "公园", "minutes": 15, "open": (5, 22)},
    {"name": "餐厅", "minutes": 15, "open": (10, 22)},
    {"name": "咖啡馆", "minutes": 18, "open": (8, 22)},
    {"name": "医院", "minutes": 20, "open": (0, 24)},
    {"name": "学校", "minutes": 25, "open": (7, 21)},
    {"name": "朋友家", "minutes": 25, "open": None},
    {"name": "电影院", "minutes": 30, "open": (10, 24)},
    {"name": "公司", "minutes": 35, "open": (9, 18)},
    {"name": "火车站", "minutes": 40, "open": (5, 23)},
    {"name": "邻近城市", "minutes": 180, "open": None, "kind": "city"},
    {"name": "远方（省外）", "minutes": 600, "open": None, "kind": "far"},
]

# 交通方式速度系数（乘在分钟数上）
TRANSPORT = {
    "走路": 1.0, "步行": 1.0, "骑车": 0.4, "自行车": 0.4, "公交": 0.5, "地铁": 0.45,
    "打车": 0.35, "开车": 0.3, "自驾": 0.3, "高铁": 0.06, "飞机": 0.05,
}
DEFAULT_TRANSPORT = "走路"
MAX_MINUTES = 60 * 24 * 30      # 超过一个月的"移动"没有意义（倍率很高时会出现）

DEFAULTS = {
    "enabled": True,
    "max_chars": 240,
    "show_reachable": True,     # 注入里列出"这段时间够去的地方"
    "reachable_limit": 4,
    "default_transport": DEFAULT_TRANSPORT,
    "warn_when_impossible": True,
    "state_dir": "space",       # 状态目录（相对游戏目录）
}


def _safe(name):
    return re.sub(r'[\\/:*?"<>|]', "_", str(name or "default")).strip() or "default"


class _Cfg(object):
    _lock = threading.Lock()
    _cache = None


def config_path():
    try:
        base = app_paths.get_base_dir()
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "space_config.json")


def load_config():
    with _Cfg._lock:
        if _Cfg._cache is not None:
            return dict(_Cfg._cache)
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            for k in DEFAULTS:
                if k in got:
                    data[k] = got[k]
    except Exception:
        pass
    with _Cfg._lock:
        _Cfg._cache = dict(data)
    return data


def save_config(cfg):
    data = dict(DEFAULTS)
    data.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    with _Cfg._lock:
        _Cfg._cache = dict(data)
    try:
        p = config_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception as e:
        print("[space] 配置保存失败: %s" % e)
    return data


def enabled():
    try:
        return bool(load_config().get("enabled"))
    except Exception:
        return False


# ============================================================
#  二、状态：她此刻在哪（一个角色一个文件，只记必要字段）
# ============================================================
def state_path(role, cfg=None):
    cfg = cfg or load_config()
    try:
        base = app_paths.get_base_dir()
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, str(cfg.get("state_dir") or "space"))
    return os.path.join(d, _safe(role) + ".json")


def load_state(role, cfg=None):
    p = state_path(role, cfg)
    try:
        with open(p, "r", encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def save_state(role, st, cfg=None):
    p = state_path(role, cfg)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if save_guard is not None:
            save_guard.atomic_write_json(p, st)
        else:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[space] 位置状态保存失败: %s" % e)
    return p


def _parse_ts(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
    return d


def _scale(scale=None):
    """倍率：None = 读应用设置（time_scale）；显式给了但非法 → 当 1 倍（不偷偷用应用设置）。

    与 life_core.world_clock 同口径：调用方明确传了个坏值时，退回"不加速"比"用另一个来源
    的倍率"更容易解释（否则测试与调用点都会意外受到全局设置影响）。
    """
    if scale is None:
        try:
            import time_scale as _ts
            return float(_ts.load())
        except Exception:
            return 1.0
    try:
        v = float(scale)
        return v if v > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def world_minutes_since(ts, scale=None, now=None):
    """现实时刻 → 那边过了多少分钟（系统时间 = 1× 起源，× 倍率）"""
    d = _parse_ts(ts)
    if d is None:
        return None
    end = now if isinstance(now, datetime) else datetime.now()
    real = max(0.0, (end - d).total_seconds())
    return real * _scale(scale) / 60.0


# ============================================================
#  三、地图：地点 / 路费 / 开门时间
# ============================================================
def map_for(role=None, world=None, cfg=None):
    """地图 = 内置默认 + 世界卡里的 space 覆盖 + 角色卡里的 space 覆盖。

    卡里怎么写（world.params.space 或 role.advanced.space 都行，两种写法等价）：
        {"places": [{"name": "学校", "minutes": 20},
                    {"name": "码头", "minutes": 45, "open": [6, 20]}],
         "links":  {"学校|码头": 30},          # 精确两地耗时，覆盖估算
         "transport": {"骑车": 0.4}}
    """
    places, links, transport = {}, {}, dict(TRANSPORT)
    for p in DEFAULT_PLACES:
        places[p["name"]] = dict(p)

    def merge(spec):
        if not isinstance(spec, dict):
            return
        for p in spec.get("places") or []:
            if isinstance(p, dict) and p.get("name"):
                item = dict(p)
                item.setdefault("minutes", 0)
                places[str(p["name"])] = item
        for k, v in (spec.get("links") or {}).items():
            try:
                links[str(k)] = float(v)
            except (TypeError, ValueError):
                pass
        for k, v in (spec.get("transport") or {}).items():
            try:
                transport[str(k)] = float(v)
            except (TypeError, ValueError):
                pass

    # 世界卡：params.space 里放 JSON 字符串，或直接放 dict
    if isinstance(world, dict):
        sp = world.get("space")
        if sp is None and isinstance(world.get("params"), dict):
            sp = world["params"].get("space")
        if isinstance(sp, str):
            try:
                sp = json.loads(sp)
            except Exception:
                sp = None
        merge(sp)
    if isinstance(role, dict):
        adv = role.get("advanced")
        if isinstance(adv, dict):
            merge(adv.get("space"))
    return {"places": places, "links": links, "transport": transport}


def _factor(transport, by):
    if not by:
        return 1.0
    return float(transport.get(str(by).strip(), 1.0) or 1.0)


def travel_minutes(mp, a, b, by=None):
    """a → b 要多少分钟。a、b 都不是家时按"经过家"估（偏保守），links 可精确覆盖。"""
    if not a or not b or a == b:
        return 0.0
    links = mp.get("links") or {}
    for key in ("%s|%s" % (a, b), "%s|%s" % (b, a)):
        if key in links:
            return max(0.0, float(links[key]) * _factor(mp.get("transport"), by))
    places = mp.get("places") or {}
    ta = float((places.get(a) or {}).get("minutes", 0) or 0)
    tb = float((places.get(b) or {}).get("minutes", 0) or 0)
    raw = tb if a == HUB else (ta if b == HUB else ta + tb)
    return max(0.0, raw * _factor(mp.get("transport"), by))


def reachable(mp, frm, minutes, limit=None, by=None):
    """这段时间从 frm 能到哪些地方（按耗时升序）"""
    out = []
    if minutes is None:
        return out
    for name in (mp.get("places") or {}):
        if name == frm:
            continue
        need = travel_minutes(mp, frm, name, by)
        if need <= minutes:
            out.append((name, need))
    out.sort(key=lambda kv: (kv[1], kv[0]))
    return out[:int(limit)] if limit else out


def open_now(place_meta, world_dt):
    """地点此刻开不开门（没写 open 视为一直开）"""
    if not isinstance(place_meta, dict):
        return True, ""
    o = place_meta.get("open")
    if not o or not isinstance(o, (list, tuple)) or len(o) != 2:
        return True, ""
    try:
        start, end = int(o[0]), int(o[1])
    except (TypeError, ValueError):
        return True, ""
    h = world_dt.hour + world_dt.minute / 60.0
    if start <= end:
        ok = start <= h < end
    else:                       # 跨天营业（22:00–02:00）
        ok = h >= start or h < end
    if ok:
        return True, ""
    return False, "%s 的营业时间是 %02d:00–%02d:00" % (
        place_meta.get("name") or "那儿", start, end)


# ============================================================
#  四、移动：记位置 + 判合理性
# ============================================================
MOVE_TAG = re.compile(r"\[\s*(loc|ploc|位置|地点)\s*[:：]\s*([^\[\]]+?)\s*\]", re.I)


def parse_move(text):
    """从回复里抽出位置标签 → [(是不是玩家, 地点, 交通方式), ...]"""
    out = []
    for m in MOVE_TAG.finditer(text or ""):
        key = m.group(1).lower()
        body = m.group(2).strip()
        by = ""
        for sep in ("|", "/", "，", ",", " "):
            if sep in body:
                head, _, tail = body.partition(sep)
                if tail.strip():
                    by, body = tail.strip(), head.strip()
                break
        out.append((key in ("ploc",), body, by))
    return out


def strip_move_tags(text):
    """把位置标签从显示文本里剥掉（和 [aff:+3] 一个规矩）"""
    if not text:
        return text
    return MOVE_TAG.sub("", text)


def note_move(role, place, by="", scale=None, now=None, mp=None, player=False, cfg=None):
    """记下"谁在哪"。返回 (st, verdict)：
         verdict = {"ok": bool, "need": 分钟, "have": 分钟, "from": 上一处, "why": 说明}
    ok=False 表示这一跳时间不够（**照样记下新位置**，只在下一轮注入里点名要求补交代）。
    """
    cfg = cfg or load_config()
    st = load_state(role, cfg)
    now = now if isinstance(now, datetime) else datetime.now()
    slots = ("player_place", "player_since", "player_prev") if player else \
            ("place", "since", "prev")
    key, since_key, prev_key = slots
    frm = st.get(key) or (HUB if not player else "")
    have = world_minutes_since(st.get(since_key), scale, now) if st.get(since_key) else None
    mp = mp or map_for(None, None, cfg)
    need = travel_minutes(mp, frm, place, by or cfg.get("default_transport")) if frm else 0.0
    ok = True
    why = ""
    if frm and frm != place and have is not None:
        if need > min(have, MAX_MINUTES) + 1e-6:
            ok = False
            why = "从%s到%s要 %.0f 分钟，这段时间只过了 %.0f 分钟" % (frm, place, need, have)
    elif frm and frm != place and have is None:
        why = "不知道上次是什么时候到的%s（没有时间戳），按「能到」处理" % frm
    st[prev_key] = frm
    st[key] = place
    st[since_key] = now.isoformat()
    st["scale"] = _scale(scale)
    st["by"] = by or cfg.get("default_transport")
    if not ok and cfg.get("warn_when_impossible"):
        st["violation"] = {"from": frm, "to": place, "need": need, "have": have,
                           "at": now.isoformat(), "why": why}
    elif ok:
        st.pop("violation", None)
    save_state(role, st, cfg)
    return st, {"ok": ok, "need": need, "have": have, "from": frm, "why": why}


def note_player_move(role, place, by="", scale=None, now=None, mp=None, cfg=None):
    return note_move(role, place, by=by, scale=scale, now=now, mp=mp, player=True, cfg=cfg)


# ============================================================
#  五、给模型的那一小段
# ============================================================
GUIDE = ("（换地方要交代怎么去的、路上花了多久；来不及去的地方就别凭空出现 —— "
         "可以用 [loc:地名] / [loc:地名|骑车] 标注她到了哪，[ploc:地名] 标你到哪；标注不会显示给玩家。）")


def _last_gap_minutes(chain, scale, now=None):
    """上一轮对话到现在的世界分钟数（"下一幕之前她有多少时间可用"）

    与 life_core 的时间纸带同源：节点时间戳是系统本地时间，现实间隔 × 倍率 = 那边过了多久。
    没有链（开局第一轮）就返回 None —— 那就退回"她在这个地方已经待了多久"。
    """
    if not chain:
        return None
    last = None
    for m in chain:
        if isinstance(m, dict) and m.get("role") != "system":
            d = _parse_ts(m.get("timestamp"))
            if d is not None and (last is None or d > last):
                last = d
    if last is None:
        return None
    return world_minutes_since(last.isoformat(), scale, now)


def injection_text(role=None, world=None, scale=None, cfg=None, now=None, name=None, chain=None):
    """每轮注入的【空间】。关掉 / 出错 → 返回 ""。"""
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    if not cfg.get("enabled"):
        return ""
    role = role if isinstance(role, dict) else {}
    who = name or str(role.get("name") or "她")
    mp = map_for(role, world, cfg)
    st = load_state(who, cfg)
    now = now if isinstance(now, datetime) else datetime.now()
    world_dt = None
    if st.get("since"):
        # 用到达时刻 + 世界流逝推断"那边现在"（与 life_core 同一模型：现实 × 倍率）
        try:
            wm = world_minutes_since(st.get("since"), scale, now) or 0.0
            world_dt = _parse_ts(st.get("since")) + timedelta(minutes=wm)
        except Exception:
            world_dt = None

    place = st.get("place") or HUB
    have = world_minutes_since(st.get("since"), scale, now) if st.get("since") else None
    lines = []
    head = "【空间】%s 现在：%s" % (who, place)
    if have is not None:
        head += "（%.0f 分钟前到，%s）" % (have, st.get("by") or cfg.get("default_transport"))
    lines.append(head)
    if world_dt is not None:
        ok, why = open_now((mp.get("places") or {}).get(place), world_dt)
        if not ok:
            lines.append("⚠ " + why + " —— 这个点她不该在那儿，给个由头或换个地方。")

    # "够去哪"用**这一轮之前过了多久**做预算（下一幕可用时间），而不是"她已经待了多久"。
    # 待了多久只说明她有机会走（但没走）；过了多久才是下一幕的预算。
    gap = _last_gap_minutes(chain, scale, now)
    budget = gap if gap is not None else have
    if cfg.get("show_reachable") and budget is not None:
        by = cfg.get("default_transport")
        near = reachable(mp, place, budget, limit=cfg.get("reachable_limit"), by=by)
        if near:
            lines.append("这%.0f分钟够去：" % budget
                         + "、".join("%s(%.0f分)" % (n, m) for n, m in near))
        elif budget >= 1:
            lines.append("这%.0f分钟哪儿都去不了（最近的也要 %.0f 分钟）"
                         % (budget, min([travel_minutes(mp, place, n, by)
                                         for n in (mp.get("places") or {}) if n != place] or [0])))

    pplace = st.get("player_place")
    if pplace:
        need = travel_minutes(mp, pplace, place, cfg.get("default_transport"))
        lines.append("你在%s，到这儿要 %.0f 分钟" % (pplace, need))

    # 穿帮提醒：最多提醒两次（免得每轮都念同一句），之后留着记录但不再注入
    v = st.get("violation")
    if cfg.get("warn_when_impossible") and isinstance(v, dict) and int(v.get("warned") or 0) < 2:
        v["warned"] = int(v.get("warned") or 0) + 1
        try:
            save_state(who, st, cfg)
        except Exception:
            pass
        lines.append("⚠ 上一轮她 %.0f 分钟前还在%s，现在写到%s：%s —— 要么补一句路上/交通方式，"
                     "要么把她拉回原处。" % (v.get("have") or 0, v.get("from"), v.get("to"),
                                            v.get("why") or ""))

    text = "\n".join(lines)
    room = int(cfg.get("max_chars") or DEFAULTS["max_chars"])
    if len(text) + len(GUIDE) > room:
        text = text[:max(0, room - len(GUIDE) - 1)].rstrip("、，。 ") + "…"
    return text + "\n" + GUIDE


def describe(role=None, world=None, scale=None, cfg=None, now=None, name=None):
    """给 /在哪 看的完整状态"""
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    role = role if isinstance(role, dict) else {}
    who = name or str(role.get("name") or "她")
    mp = map_for(role, world, cfg)
    st = load_state(who, cfg)
    out = ["空间层：%s" % ("开" if cfg.get("enabled") else "关")]
    place = st.get("place") or HUB
    have = world_minutes_since(st.get("since"), scale, now) if st.get("since") else None
    out.append("%s 现在：%s%s" % (who, place,
                                 ("（%.0f 分钟前到，%s）" % (have, st.get("by") or "走路"))
                                 if have is not None else "（还没记过位置，按家算）"))
    if st.get("player_place"):
        out.append("你 现在：%s" % st["player_place"])
    if isinstance(st.get("violation"), dict):
        v = st["violation"]
        out.append("⚠ 上次跳得不合理：%s→%s（要 %.0f 分钟，只过了 %.0f 分钟）"
                   % (v.get("from"), v.get("to"), v.get("need") or 0, v.get("have") or 0))
    out.append("地图（%d 个地点，下面是从「%s」出发的耗时）：" % (len(mp["places"]), place))
    for name_, meta in sorted(mp["places"].items(), key=lambda kv: kv[1].get("minutes", 0)):
        if name_ == place:
            continue
        need = travel_minutes(mp, place, name_, cfg.get("default_transport"))
        o = meta.get("open")
        o = ("　营业 %02d:00–%02d:00" % (o[0], o[1])) if isinstance(o, (list, tuple)) and len(o) == 2 else ""
        out.append("  %-6s %5.0f 分钟%s" % (name_, need, o))
    out.append("改法：/在哪 <地点> ｜ /在哪 <地点>|骑车 ｜ /在哪 我=<地点> ｜ /空间 关 ｜ /空间 交通 打车")
    return "\n".join(out)
