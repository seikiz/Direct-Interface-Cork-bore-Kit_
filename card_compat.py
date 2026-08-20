# -*- coding: utf-8 -*-
# ============================================================
#   card_compat.py - 酒馆(SillyTavern)角色卡兼容层
#
#   导入：v1(旧 TavernAI JSON) / v2(chara_card_v2) / v3(chara_card_v3)
#         PNG 嵌卡（tEXt/zTXt/iTXt 块，关键字 chara / ccv3）
#   导出：v2 JSON；PNG 嵌卡（在现有头像图上插入 tEXt chara 块）
# ============================================================

import base64
import json
import struct
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"


# ---------- 格式识别 ----------
def is_v2(data):
    return isinstance(data, dict) and str(data.get("spec", "")) in ("chara_card_v2", "chara_card_v3")


def is_v1(data):
    return (isinstance(data, dict) and "spec" not in data and "data" not in data
            and any(k in data for k in ("description", "personality", "first_mes", "mes_example")))


def _clean(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v or "").strip()


# ---------- v2 世界书（extensions.world）提取 ----------
def extract_world(data):
    """从酒馆 v2/v3 卡的 extensions.world 提取世界书条目，转成 DICK 世界书格式。
    返回 entries 列表（每项含 keywords/content/match/weight/probability/depth/enabled/constant）
    或空列表。"""
    d = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
    if not isinstance(d, dict):
        return []
    ext = d.get("extensions")
    if not isinstance(ext, dict):
        return []
    world = ext.get("world")
    if not isinstance(world, dict):
        return []
    entries_raw = world.get("entries")
    if not isinstance(entries_raw, list):
        return []
    out = []
    for e in entries_raw:
        if not isinstance(e, dict):
            continue
        content = _clean(e.get("content"))
        if not content:
            continue
        keys = e.get("keys") or e.get("keywords") or []
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.replace("，", ",").split(",") if k.strip()]
        elif isinstance(keys, list):
            keys = [str(k).strip() for k in keys if str(k).strip()]
        entry = {
            "id": str(e.get("id") or ""),
            "keywords": keys,
            "content": content,
            "match": "any",
            "weight": _num(e.get("priority", e.get("weight")), 100),
            "probability": _num(e.get("probability"), 100),
            "depth": int(_num(e.get("depth"), 1)),
            "enabled": bool(e.get("enabled", True)),
            "constant": bool(e.get("constant", False)),
        }
        # 酒馆世界书元字段全量保留（无损往返；DICK 引擎忽略未知键）
        meta = {}
        for k in ("name", "insertion_order", "case_sensitive", "selective",
                  "secondary_keys", "comment", "position"):
            if k in e:
                meta[k] = e[k]
        if meta:
            entry["_meta"] = meta
        out.append(entry)
    return out


def _num(v, d):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def world_to_sillytavern(entries, base_id=1):
    """DICK 世界书条目 → 酒馆 v2 extensions.world 条目列表（无损反向）。
    保留 _meta 元字段（insertion_order/case_sensitive/selective 等），
    无 _meta 时按酒馆默认结构生成。"""
    out = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        meta = e.get("_meta") if isinstance(e.get("_meta"), dict) else {}
        keys = e.get("keywords") or []
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.replace("，", ",").split(",") if k.strip()]
        entry = {
            "keys": list(keys),
            "content": str(e.get("content") or ""),
            "enabled": bool(e.get("enabled", True)),
            "insertion_order": int(meta.get("insertion_order", i * 100)),
            "case_sensitive": bool(meta.get("case_sensitive", False)),
            "name": str(meta.get("name") or ""),
            "priority": int(_num(e.get("weight", e.get("priority")), 100)),
            "id": int(_num(e.get("id"), base_id + i)),
            "comment": str(meta.get("comment") or ""),
            "selective": bool(meta.get("selective", False)),
            "secondary_keys": list(meta.get("secondary_keys") or []),
            "constant": bool(e.get("constant", False)),
            "position": str(meta.get("position") or "before_char"),
        }
        # 无 _meta 的条目：position 默认 before_char（酒馆约定）
        out.append(entry)
    return out


# ---------- v1/v2/v3 → DICK 完整转换 ----------
def _sections(data):
    """把 v1/v2 字段拼成 DICK 的 system_prompt（分节标题）"""
    parts = []

    def add(title, val):
        val = _clean(val)
        if val:
            parts.append(title + "：" + val)

    add("【角色简介】", data.get("description"))
    add("【性格】", data.get("personality"))
    add("【背景设定】", data.get("scenario"))
    add("【开场白】", data.get("first_mes"))
    add("【对话示例】", data.get("mes_example"))
    add("【备注】", data.get("creator_notes"))
    sp = _clean(data.get("system_prompt"))
    if sp:
        parts.append(sp)
    phi = _clean(data.get("post_history_instructions"))
    if phi:
        parts.append("【历史后指令】" + phi)
    ag = data.get("alternate_greetings")
    if isinstance(ag, list) and ag:
        parts.append("【备用开场白】\n" + "\n".join("· " + _clean(x) for x in ag))
    return "\n\n".join(parts)


def _fields_dict(data):
    """把酒馆字段拆成 DICK 结构化字段 dict（空值不出现）"""
    out = {}
    mapping = {
        "appearance": None,  # 酒馆无直接对应，留给 name/description
        "personality": "personality",
        "background": "scenario",
        "speech": None,
        "first_mes": "first_mes",
        "mes_example": "mes_example",
        "notes": "creator_notes",
    }
    for k, src in mapping.items():
        if src and _clean(data.get(src)):
            out[k] = _clean(data.get(src))
    return out


def _unstringify(data):
    """JSON 可能是字符串包裹/多包一层：逐层解包到 dict"""
    depth = 0
    while isinstance(data, str) and depth < 5:
        s = data.strip()
        if s.startswith("data:"):
            s = s.split(",", 1)[1] if "," in s else s
        try:
            data = json.loads(s)
        except Exception:
            break
        depth += 1
    # 酒馆 Web 导出偶见 {"data": "<json字符串>"} 包裹
    if isinstance(data, dict) and isinstance(data.get("data"), str):
        try:
            inner = json.loads(data["data"])
            if isinstance(inner, dict):
                data = inner
        except Exception:
            pass
    return data


def v2_to_dick(data):
    d = data.get("data") or {}
    if not isinstance(d, dict):
        d = {}
    name = str(d.get("name") or data.get("name") or "导入角色").strip()
    world = extract_world(data)
    return {
        "name": name,
        "system_prompt": _sections(d) or name,
        "card_data": data,
        "fields": _fields_dict(d),
        "world_entries": world,
        "alternate_greetings": _clean_list(d.get("alternate_greetings")),
    }


def v1_to_dick(data):
    name = str(data.get("name") or "导入角色").strip()
    return {
        "name": name,
        "system_prompt": _sections(data) or name,
        "card_data": data,
        "fields": _fields_dict(data),
        "world_entries": [],
        "alternate_greetings": _clean_list(data.get("alternate_greetings")),
    }


def _clean_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.replace("；", "\n").split("\n") if x.strip()]
    return []


def to_dick(data):
    """任意酒馆/DICK 卡 → dict：{name, system_prompt, card_data, fields, world_entries,
    alternate_greetings} 或 None。完整适配：结构化字段拆分 + 世界书提取。"""
    data = _unstringify(data)
    if not isinstance(data, dict):
        return None
    if is_v2(data):
        return v2_to_dick(data)
    if is_v1(data):
        return v1_to_dick(data)
    if data.get("system_prompt"):
        # DICK 原生格式（自带 card_data 则保留，可无损再导出）
        world = extract_world(data)
        return {
            "name": str(data.get("name") or "导入角色").strip(),
            "system_prompt": str(data["system_prompt"]),
            "card_data": data.get("card_data"),
            "fields": _fields_dict(data),
            "world_entries": world,
            "alternate_greetings": _clean_list(data.get("alternate_greetings")),
        }
    return None


def dick_to_v2(name, system_prompt, card_data=None, world_entries=None):
    """DICK 卡 → 酒馆 v2 JSON。有原始 card_data 则尽量无损回导。
    card_data 两种形态都支持：整卡（含 spec/data）或裸字段块（v1 卡 / v2 内层）。
    world_entries：DICK 世界书条目列表，非空时写回 extensions.world（无损反向）。"""
    if isinstance(card_data, dict) and card_data:
        out = json.loads(json.dumps(card_data, ensure_ascii=False))
        if isinstance(out.get("data"), dict):
            # 整卡形态（v2/v3）：保留原 spec
            d = out["data"]
            out.setdefault("spec", "chara_card_v2")
            out.setdefault("spec_version", "2.0")
        else:
            # 裸字段块：包成标准 v2 卡
            d = out
            out = {"spec": "chara_card_v2", "spec_version": "2.0", "name": name, "data": d}
        out["name"] = name
        d["name"] = name
        if not _clean(d.get("system_prompt")) and system_prompt:
            d["system_prompt"] = system_prompt
        if world_entries:
            ext = d.setdefault("extensions", {})
            if not isinstance(ext, dict):
                ext = {}
                d["extensions"] = ext
            ext["world"] = {"entries": world_to_sillytavern(world_entries)}
        return out
    out = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "data": {
            "name": name, "description": "", "personality": "", "scenario": "",
            "first_mes": "", "mes_example": "", "creator_notes": "",
            "system_prompt": system_prompt, "post_history_instructions": "",
            "alternate_greetings": [], "tags": [], "creator": "DICK",
            "character_version": "1.0", "extensions": {},
        },
    }
    if world_entries:
        out["data"]["extensions"]["world"] = {"entries": world_to_sillytavern(world_entries)}
    return out


# ---------- PNG 块读写 ----------
def _chunks(png_bytes):
    if not png_bytes or png_bytes[:8] != PNG_SIG:
        return None
    chunks = []
    pos = 8
    while pos + 8 <= len(png_bytes):
        (ln,) = struct.unpack(">I", png_bytes[pos:pos + 4])
        ctype = png_bytes[pos + 4:pos + 8]
        if pos + 12 + ln > len(png_bytes):
            return None
        data = png_bytes[pos + 8:pos + 8 + ln]
        chunks.append((ctype, data))
        pos += 12 + ln
        if ctype == b"IEND":
            break
    if not chunks:
        return None
    return chunks


def _tEXt_read(data):
    i = data.find(b"\x00")
    if i < 0:
        return None, None
    return data[:i].decode("latin-1"), data[i + 1:].decode("latin-1")


def _zTXt_read(data):
    i = data.find(b"\x00")
    if i < 0:
        return None, None
    kw = data[:i].decode("latin-1")
    try:
        text = zlib.decompress(data[i + 2:]).decode("latin-1")
    except Exception:
        return None, None
    return kw, text


def _iTXt_read(data):
    i = data.find(b"\x00")
    if i < 0:
        return None, None
    kw = data[:i].decode("latin-1")
    rest = data[i + 1:]
    if not rest:
        return None, None
    comp_flag = rest[0]
    j = rest.find(b"\x00")
    if j < 0:
        return None, None
    k = rest[j + 1:].find(b"\x00")
    if k < 0:
        return None, None
    text_bytes = rest[j + 1 + k + 1:]
    try:
        text = (zlib.decompress(text_bytes) if comp_flag else text_bytes).decode("utf-8")
    except Exception:
        return None, None
    return kw, text


def png_extract_card(png_bytes):
    """从 PNG 嵌卡中提取角色卡 JSON（支持 chara/ccv3 关键字、tEXt/zTXt/iTXt）"""
    chunks = _chunks(png_bytes)
    if not chunks:
        return None
    texts = {}
    for ctype, data in chunks:
        if ctype == b"tEXt":
            kw, text = _tEXt_read(data)
        elif ctype == b"zTXt":
            kw, text = _zTXt_read(data)
        elif ctype == b"iTXt":
            kw, text = _iTXt_read(data)
        else:
            continue
        if kw:
            texts[kw] = text
    raw = texts.get("ccv3") or texts.get("chara")
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        return None


def _make_chunk(ctype, data):
    return (struct.pack(">I", len(data)) + ctype + data +
            struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def png_embed_card(png_bytes, card_dict, v3=False):
    """把角色卡 JSON 嵌入 PNG（插入 tEXt 块；v3 用 ccv3，否则 chara），返回新 PNG 字节。
    同时注入 dick_mark tEXt 块（架构级水印：跨格式溯源，抄卡即带走）。"""
    chunks = _chunks(png_bytes)
    if not chunks:
        raise ValueError("不是有效的 PNG 图片")
    keyword = "ccv3" if v3 else "chara"
    payload = base64.b64encode(json.dumps(card_dict, ensure_ascii=False).encode("utf-8"))
    mark_payload = b""
    try:
        import dick_mark
        mark_payload = dick_mark.SIGNATURE.encode("utf-8", "replace")
    except Exception:
        pass
    out = bytearray(PNG_SIG)
    ihdr_written = False
    for ctype, data in chunks:
        if ctype == b"IHDR":
            if ihdr_written:
                continue
            out += _make_chunk(b"IHDR", data)
            out += _make_chunk(b"tEXt", keyword.encode("latin-1") + b"\x00" + payload)
            if mark_payload:
                out += _make_chunk(b"tEXt", b"dick_mark" + b"\x00" + mark_payload)
            ihdr_written = True
            continue
        if ctype == b"tEXt":
            kw, _ = _tEXt_read(data)
            if kw in ("chara", "ccv3"):
                continue
        out += _make_chunk(ctype, data)
    return bytes(out)


# ---------- 占位头像 ----------
def placeholder_png(name, size=512):
    """给没有头像的角色生成一张渐变 + 首字占位图"""
    from PIL import Image, ImageDraw, ImageFont
    name = name or "?"
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    c1 = (24 + h % 40, 34 + (h >> 3) % 40, 58 + (h >> 6) % 40)
    c2 = (70 + (h >> 5) % 50, 44 + (h >> 8) % 50, 110 + (h >> 11) % 60)
    img = Image.new("RGB", (size, size))
    dr = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        dr.line([(0, y), (size, y)], fill=(
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t)))
    font = None
    for fp in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
               r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc",
               r"C:\Windows\Fonts\arial.ttf"):
        try:
            font = ImageFont.truetype(fp, int(size * 0.42))
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    ch = name[0]
    if font is not None:
        box = dr.textbbox((0, 0), ch, font=font)
        w, ht = box[2] - box[0], box[3] - box[1]
        dr.text(((size - w) / 2 - box[0], (size - ht) / 2 - box[1]), ch,
                font=font, fill=(235, 238, 245))
    else:
        dr.text((size / 2, size / 2), ch, anchor="mm", fill=(235, 238, 245))
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
