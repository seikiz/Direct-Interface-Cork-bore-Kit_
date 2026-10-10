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
#  一、地图（年代常识库提供默认；角色卡 / 世界卡可覆盖）
# ============================================================
HUB = "家"

# 年代常识库（commonsense.py）：地点 / 交通 / 屋里格局都由它给 ——
# 这样"大明"不会出现地铁、"仙侠"能用御剑。**表只有一份**，这里不再抄一遍。
try:
    import commonsense as _cs
except Exception as e:              # 极端情况下退化成最小地图（并明确警告，不静默）
    _cs = None
    print("[space] 常识库 commonsense.py 没加载上（%s）—— 地图退化成 家/楼下" % e)

_FALLBACK_PLACES = [("家", 0), ("楼下", 2)]
_FALLBACK_TRANSPORT = {"走路": 1.0, "步行": 1.0}


def _as_int(v, default):
    """把配置里的数值键安全地转成 int：坏值（None/""/"abc"/对象）退回 default。

    兼容线内"老程序读新文件"和"用户手改配置文件"都允许发生；类型不对时**不能**让
    整个注入那一轮静默变空（审计里那条"不炸但静默降级"），退回默认值继续跑更合理。
    """
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return int(default)
        return int(v)
    except (TypeError, ValueError):
        return int(default)


def _era_places(era):
    return list(_cs.places(era)) if _cs is not None else list(_FALLBACK_PLACES)


def _era_rooms(era):
    return list(_cs.rooms(era)) if _cs is not None else ["卧室", "客厅", "厨房"]


def _era_transports(era):
    return dict(_cs.transports(era)) if _cs is not None else dict(_FALLBACK_TRANSPORT)


# 交通系数：年代表打底，这里再补几个跨年代的通用写法
TRANSPORT = {
    "走路": 1.0, "步行": 1.0, "骑车": 0.4, "自行车": 0.4, "公交": 0.5, "地铁": 0.45,
    "打车": 0.35, "开车": 0.3, "自驾": 0.3, "高铁": 0.06, "飞机": 0.05,
}
DEFAULT_TRANSPORT = "走路"
DEFAULT_ERA_FALLBACK = "现代"   # 常识库认不出年代时的口径
MAX_MINUTES = 60 * 24 * 30      # 超过一个月的"移动"没有意义（倍率很高时会出现）
ROOM_MINUTES = 0.5              # 屋里走动：家门口 → 任一房间（同屋不算"赶路"）

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


def _unknown_on_disk():
    """磁盘上不属于本版 DEFAULTS 的键（更新的版本写的 / 用户手加的）。

    兼容线内"老程序读新文件"是允许发生的（用户回退一次）：写回时按 DEFAULTS 重建、
    把不认识的键丢掉，就等于回退一次永久丢配置 —— 那是破坏性改动，得等换线。
    """
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            return {k: v for k, v in got.items() if k not in DEFAULTS}
    except Exception:
        pass
    return {}


def save_config(cfg):
    data = dict(DEFAULTS)
    data.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    for k, v in _unknown_on_disk().items():
        data.setdefault(k, v)
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
def map_for(role=None, world=None, cfg=None, era=None):
    """地图 = 年代常识（默认）+ 世界卡 space 覆盖 + 角色卡 space 覆盖。

    年代从哪里来：卡里显式写 → 世界卡关键词（复用 life_core 的表）→ 现代。
    仙侠/末世这类"设定类型"优先于年代（它们的地图差别更大）。

    卡里怎么写（world.params.space 或 role.advanced.space 都行，两种写法等价）：
        {"places": [{"name": "学校", "minutes": 20},
                    {"name": "码头", "minutes": 45, "open": [6, 20]}],
         "links":  {"学校|码头": 30},          # 精确两地耗时，覆盖估算
         "transport": {"骑车": 0.4},
         "rooms":  ["卧房", "灶房"]}           # 只覆盖屋里格局也行
    """
    era_key = era or (_cs.effective_era(world, role) if _cs is not None else DEFAULT_ERA_FALLBACK)
    places, links = {}, {}
    home = HUB
    # 交通方式以**年代**为准：唐宋不该有地铁/高铁。
    # 模块级的 TRANSPORT 只当"认不出名字时的通用系数"用（见 _factor），不并进这张表。
    transport = dict(_era_transports(era_key))
    transport.setdefault("走路", 1.0)
    transport.setdefault("步行", 1.0)

    for name, minutes in _era_places(era_key):
        places[name] = {"name": name, "minutes": minutes}
    places.setdefault(HUB, {"name": HUB, "minutes": 0})
    if HUB in places:
        places[HUB]["minutes"] = 0
    # 屋里：都从家门口算（ROOM_MINUTES），并打上 room 标记 ——
    # 这样"够去哪"的列表不会被子分钟的卧室/厨房挤满（它们在屋里，本来就走得到）
    rooms = _era_rooms(era_key)

    def merge(spec, replace=False):
        """把卡里的 space 并进地图。

        replace=True（**世界卡默认**）：卡里给了 places/transport/rooms 就整张换掉年代默认 ——
          世界卡定义的是"一个设定"，不该被现代都市的便利店/地铁站混进来。
          想叠加就写 `"merge": true`。
        replace=False（**角色卡默认**）：只叠加（她自己的几个地方/一间屋），不动大格局。
        """
        nonlocal rooms, home
        if not isinstance(spec, dict):
            return
        if replace and isinstance(spec.get("places"), list) and spec["places"]:
            places.clear()
            places[HUB] = {"name": HUB, "minutes": 0}
        if replace and isinstance(spec.get("transport"), dict) and spec["transport"]:
            transport.clear()
            transport.setdefault("走路", 1.0)
            transport.setdefault("步行", 1.0)
        # 卡可以给"家"起自己的名字（宿舍/洞府/据点/公寓…）：它就是圆心，
        # 省得地图里同时躺着"家"和"宿舍"两个 0 分钟的点，读起来像两个地方。
        if str(spec.get("home") or "").strip():
            home = str(spec["home"]).strip()
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
        if isinstance(spec.get("rooms"), list):
            rooms = [str(r) for r in spec["rooms"] if str(r).strip()]
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
        if isinstance(sp, dict):
            merge(sp, replace=not sp.get("merge"))
    if isinstance(role, dict):
        adv = role.get("advanced")
        if isinstance(adv, dict):
            merge(adv.get("space"), replace=False)
    # 卡自己起的"家"，若没在 places 里就补一个 0 分钟的点；原来的合成"家"删掉，
    # 免得地图里同时有两个"住在哪儿"的点。
    if home != HUB:
        places.setdefault(home, {"name": home, "minutes": 0})
        places[home]["minutes"] = 0
        places.pop(HUB, None)
    else:
        places.setdefault(HUB, {"name": HUB, "minutes": 0})
        places[HUB]["minutes"] = 0
    for r in rooms:
        if r and r != home:
            places.setdefault(r, {"name": r, "minutes": ROOM_MINUTES, "room": True,
                                  "parent": home})
    return {"places": places, "links": links, "transport": transport,
            "era": era_key, "home": home, "rooms": [r for r in rooms if r in places]}


def _factor(transport, by):
    """交通方式 → 耗时系数。

    先查这张地图的（年代）表；表里没有就退回模块级通用表（打车/高铁…这类跨年代写法）。
    两边都没有 → 1.0（按走路算，宁慢不快）。
    """
    if not by:
        return 1.0
    name = str(by).strip()
    if name in (transport or {}):
        return float(transport[name] or 1.0)
    return float(TRANSPORT.get(name, 1.0) or 1.0)


def transport_options(mp):
    """这张地图（这个年代）可选的交通方式 → [(名字, 系数)]，快的在前。

    给别人看的列表要用这个，不要用模块级的 TRANSPORT —— 那是"跨年代通用写法"，
    列出来会让唐宋看上去像有地铁。
    """
    t = (mp or {}).get("transport") or {}
    return sorted(((str(k), float(v)) for k, v in t.items()), key=lambda kv: (kv[1], kv[0]))


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


def reachable(mp, frm, minutes, limit=None, by=None, include_rooms=False):
    """这段时间从 frm 能到哪些地方（按耗时升序）

    默认**不列屋里**：卧室/厨房只有 0.5 分钟，会把"够去哪"的列表挤满 ——
    而它们本来就走得到（同一间屋子），不需要列出来提醒。
    """
    out = []
    if minutes is None:
        return out
    places = mp.get("places") or {}
    for name in places:
        if name == frm:
            continue
        if not include_rooms and (places.get(name) or {}).get("room"):
            continue
        need = travel_minutes(mp, frm, name, by)
        if need <= minutes:
            out.append((name, need))
    out.sort(key=lambda kv: (kv[1], kv[0]))
    return out[:int(limit)] if limit else out


def resolve_place(mp, name):
    """把标签里的地名落到地图上的一个地点。

    支持三种写法：
        学校            → 直接命中
        家/厨房         → 命中"厨房"（屋里路径）
        厨房            → 命中屋里那一间（若地图里有）
    认不出就返回原名（当"编外地点"处理：照记，但提醒里会说明地图上没有它）。
    """
    name = str(name or "").strip()
    if not name:
        return name
    places = mp.get("places") or {}
    if name in places:
        return name
    if "/" in name or "／" in name:
        tail = re.split(r"[/／]", name)[-1].strip()
        if tail in places:
            return tail
    for cand in places:
        if cand != name and (cand in name or name in cand):
            return cand
    return name


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
    """从回复里抽出位置标签 → [(是不是玩家, 地点, 交通方式), ...]

    交通方式**只用竖线**分隔（`[loc:学校|骑车]`）：
    斜线留给屋里路径（`[loc:家/厨房]`），逗号和空格留给地名本身（"朝阳, 北京"）。
    这个约定写在说明书 §8.6.3 里。
    """
    out = []
    for m in MOVE_TAG.finditer(text or ""):
        key = m.group(1).lower()
        body = m.group(2).strip()
        by = ""
        for sep in ("|", "｜"):
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
    mp = mp or map_for(None, None, cfg)
    # 地名落到地图上（家/厨房 → 厨房；认不出就按原名当"编外地点"）
    place = resolve_place(mp, place)
    frm = st.get(key) or ((mp.get("home") or HUB) if not player else "")
    frm = resolve_place(mp, frm) if frm else frm
    have = world_minutes_since(st.get(since_key), scale, now) if st.get(since_key) else None
    need = travel_minutes(mp, frm, place, by or cfg.get("default_transport")) if frm else 0.0
    ok = True
    why = ""
    if frm and frm != place and have is not None:
        if need > min(have, MAX_MINUTES) + 1e-6:
            ok = False
            why = "从%s到%s要 %.0f 分钟，这段时间只过了 %.0f 分钟" % (frm, place, need, have)
    elif frm and frm != place and have is None:
        why = "不知道上次是什么时候到的%s（没有时间戳），按「能到」处理" % frm
    if place not in (mp.get("places") or {}):
        st["offmap"] = place          # 地图上没有这个地方：记住，并在注入里提一句
    else:
        st.pop("offmap", None)
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

    place = st.get("place") or (mp.get("home") or HUB)
    have = world_minutes_since(st.get("since"), scale, now) if st.get("since") else None
    places = mp.get("places") or {}
    meta = places.get(place) or {}
    lines = []
    head = "【空间】%s 现在：%s" % (who, place)
    if meta.get("room"):
        head += "（在家里）"
    if have is not None:
        head += "（%.0f 分钟前到，%s）" % (have, st.get("by") or cfg.get("default_transport"))
    lines.append(head)

    # 屋里格局：她在家时给一句"有哪些屋"（同屋走动 1 分钟内，不算赶路）。
    # 不在家就不提，省字数。
    rooms = [r for r in (mp.get("rooms") or []) if r != place]
    at_home = place == (mp.get("home") or HUB) or meta.get("room")
    if at_home and rooms:
        lines.append("屋里：" + "、".join(rooms) + "（都在 1 分钟内）")
    if st.get("offmap"):
        lines.append("⚠ %s 不在地图上 —— 按你说的记下了，但这地方之后要算路费就只能按邻近代估。"
                     % st["offmap"])

    if world_dt is not None:
        ok, why = open_now(meta, world_dt)
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
                                         for n in (mp.get("places") or {})
                                         if n != place and not (places.get(n) or {}).get("room")]
                                        or [0])))

    pplace = resolve_place(mp, st.get("player_place")) if st.get("player_place") else ""
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
    room = _as_int(cfg.get("max_chars"), DEFAULTS["max_chars"])
    # 截断的算术要连"换行 + 省略号"一起算进去，否则会差一个字（测试逮到过一次：241 > 240）
    if len(text) + 1 + len(GUIDE) > room:
        keep = max(0, room - len(GUIDE) - 2)
        text = text[:keep].rstrip("、，。 ") + "…"
    return text + "\n" + GUIDE


def describe(role=None, world=None, scale=None, cfg=None, now=None, name=None):
    """给 /在哪 看的完整状态"""
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    role = role if isinstance(role, dict) else {}
    who = name or str(role.get("name") or "她")
    mp = map_for(role, world, cfg)
    st = load_state(who, cfg)
    out = ["空间层：%s" % ("开" if cfg.get("enabled") else "关")]
    place = st.get("place") or (mp.get("home") or HUB)
    have = world_minutes_since(st.get("since"), scale, now) if st.get("since") else None
    out.append("%s 现在：%s%s" % (who, place,
                                 ("（%.0f 分钟前到，%s）" % (have, st.get("by") or "走路"))
                                 if have is not None else "（还没记过位置，按%s算）" % (mp.get("home") or HUB)))
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
