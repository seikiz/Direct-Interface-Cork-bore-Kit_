# -*- coding: utf-8 -*-
"""net_store —— 资源注册表 + 索引读写（从 net.py 拆出的第 2 层）。

只做"数据怎么存/怎么查"，不碰 Flask 请求、不做限流（那些留在 net.py）。
依赖只有 net_paths（路径）与标准库，可以单独测试。
"""
from __future__ import annotations

import uuid

import struct

import gzip

from datetime import datetime

import json
import os
import threading
import time
from flask import jsonify, request  # noqa: E402
from net_config import (UPLOAD_MAX_MB, RATE_PER_MIN, RATE_PER_HOUR, MIN_INTERVAL_MS,
                         MAX_CONCURRENT, PORT, DISCOVER_PORT, DISCOVER_MAGIC)  # noqa: E402
from net_paths import (DATA_DIR, CARDS_DIR, WORLDS_DIR, PLUGINS_DIR, PACKS_DIR,
                       INDEX_FILE, SYNC_SETTINGS_FILE)
import secret_store
TYPES = {
    "cards":   {"dir": CARDS_DIR,   "label": "角色卡", "ext": (".json", ".png"), "index": "cards"},
    "worlds":  {"dir": WORLDS_DIR,  "label": "世界卡", "ext": (".json",),        "index": "worlds"},
    "plugins": {"dir": PLUGINS_DIR, "label": "插件",   "ext": (".py", ".zip"),   "index": "plugins"},
    # 世界卡包（world_packs/ 那 6 张成套卡）<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌：一整包带地图/年代参数，装进 worlds/ 就能用
    "packs":   {"dir": PACKS_DIR,   "label": "世界卡包", "ext": (".json",),      "index": "packs"},
}

INDEX_SCHEMA = 1

_index_lock = threading.Lock()


_OWNER = None


def bind(owner_globals):
    """由 net.py 调用：把它的 globals 交进来，配置以它为准（测试会 patch 它）。"""
    global _OWNER
    _OWNER = owner_globals


def _conf(name, default=None):
    """运行配置以 net.py 的同名属性为准（测试会 monkeypatch 它）。

    net_store 不能 import net（循环），所以用 sys.modules 在调用时取；
    取不到就回落到本模块 import 的那份。
    """
    if _OWNER is not None and name in _OWNER:
        return _OWNER[name]
    import os as _os
    import sys as _sys
    m = _sys.modules.get("net")
    if m is None:
        # 测试可能用 importlib 以别的模块名加载 net.py —— 按文件路径找回来
        for cand in list(_sys.modules.values()):
            f = getattr(cand, "__file__", "") or ""
            if f and _os.path.basename(f).lower() == "net.py":
                m = cand
                break
    if m is not None and hasattr(m, name):
        return getattr(m, name)
    val = globals().get(name)
    return default if val is None else val

def type_of(rtype):
    """把 URL 里的类型名解析成注册表条目；不认得的返回 None（调用方回 400）。"""
    return TYPES.get(str(rtype or "").strip().lower())

def load_index():
    """读取索引，容错处理损坏文件；缺哪个段就补哪个（类型注册表驱动）"""
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    for spec in TYPES.values():
        data.setdefault(spec["index"], [])
    data.setdefault("users", {})
    # 索引结构版本：老索引（没有这个字段）当成 schema 0，读取时补齐即可，不做破坏性迁移
    data.setdefault("schema", INDEX_SCHEMA)
    return data

def save_index(index):
    """原子写入索引（先写临时文件再替换，避免写一半损坏）"""
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_FILE)

def _load_sync_settings() -> dict:
    """读取跨设备共享的同步设置（API 码等），容错 + 解密敏感字段"""
    try:
        with open(SYNC_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        # 解密共享的 api 配置（含 api_key）
        api = data.get("api")
        if isinstance(api, dict) and secret_store is not None:
            if api.get("api_key"):
                d = secret_store.decrypt(str(api["api_key"]))
                api["api_key"] = d if d is not None else ""
        return data
    except Exception:
        return {}

def _save_sync_settings(data: dict):
    """原子写入 + 加密敏感字段（共享的 api_key 不落明文）"""
    out = dict(data)
    api = out.get("api")
    if isinstance(api, dict) and secret_store is not None:
        if api.get("api_key"):
            api["api_key"] = secret_store.encrypt(str(api["api_key"]))
    tmp = SYNC_SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SYNC_SETTINGS_FILE)

def clean_tags(raw):
    """清洗标签：兼容逗号分隔字符串或列表，去掉空白项"""
    if isinstance(raw, list):
        tags = raw
    else:
        tags = str(raw or "").split(",")
    return [str(t).strip() for t in tags if str(t).strip()]

def find_entry(index, section, item_id):
    for item in index.get(section, []):
        if item.get("id") == item_id:
            return item
    return None

def remove_entry(index, section, item_id):
    index[section] = [i for i in index.get(section, []) if i.get("id") != item_id]

def strip_local_state(content):
    """剔除本地历史/状态键。返回 (清洗后的内容, 剔掉的键名列表)。

    只处理 dict（list 那种格式原样放行）；不递归。**不改入参**（复制一份再删），
    免得调用方手里的对象被悄悄改掉。
    """
    if not isinstance(content, dict):
        return content, []
    out = dict(content)
    gone = [k for k in LOCAL_STATE_KEYS if k in out]
    for k in gone:
        out.pop(k, None)
    return out, gone

def _url_unquote(raw):
    """把百分号编码的文件名还原（安卓端只能发 ASCII 头，中文名是编码后传的）。

    只在这三种情况下动手，其余原样返回：
      · 含 % 且解码成功、解出来没有控制字符（百分号编码）；
      · 是「UTF-8 被当 latin-1」的乱码（_repair_utf8_header 能修）；
      · 别的（比如文件名真带一个 %）——原样用，别把人的名字改坏。
    """
    s = _repair_utf8_header(raw)
    if "%" not in s:
        return s
    try:
        from urllib.parse import unquote
        out = unquote(s, encoding="utf-8", errors="strict")
    except Exception:
        return s
    return out if out and not any(ord(c) < 32 for c in out) else s


LOCAL_STATE_KEYS = (
    "history_tree", "_tree_ts", "tree_ts", "messages", "chat_history", "_history",
    "memory", "memories", "preferences", "_indices", "_trpg_lock",
    "last_leaf_id", "current_leaf_id", "session", "state",
)


def _repair_utf8_header(s):
    """把「UTF-8 字节被当成 latin-1 解出来」的头值修回中文。

    WSGI（PEP 3333）规定 environ 里的头是 latin-1 字节串。客户端要是直接塞 UTF-8
    字节（curl 的 `-H 'X-Filename: 中文.json'` 就是这样），到服务端就成了
    「ä¸­æ–‡」这种乱码，于是中文名/标签以乱码落库。这里把那串字符按 latin-1
    还原成字节、再用 UTF-8 解一次；解不出来就原样返回（真正的 latin-1 名字不会被误改）。
    """
    s = str(s or "")
    if not s or s.isascii():
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s


def search_index(index, query):
    """在索引中按 名称/作者/标签/描述 匹配，返回条目列表"""
    q = query.lower()

    def match(entry):
        haystack = " ".join([
            str(entry.get("name", "")),
            str(entry.get("author", "")),
            " ".join(entry.get("tags", [])),
            str(entry.get("description", "")),
        ]).lower()
        return q in haystack

    if not q:
        return lambda entry: True
    return match

def _limits():
    """服务器对客户端下发的**数值契约**（health 与 capabilities 同源）。

    min_interval_ms / max_concurrent 是"传输节奏"：客户端据此排队，而不是各自
    把 500ms 写死在代码里 —— 以后换 100MB/s 的水管只改服务器环境变量，
    两端客户端不用重新发版。客户端读不到（老服务器）才回落到本地常量。
    """
    return {
        "upload_max_mb": _conf("UPLOAD_MAX_MB"),
        "min_interval_ms": _conf("MIN_INTERVAL_MS"),      # 同一设备两次传输的最小间隔
        "max_concurrent": _conf("MAX_CONCURRENT"),        # 同一设备同时允许几个传输
        "rate_per_min": _conf("RATE_PER_MIN"),            # 超出会得到 429 + Retry-After
        "rate_per_hour": _conf("RATE_PER_HOUR"),
    }

def delete_entry(section, target_dir, item_id, label):
    with _index_lock:
        index = load_index()
        info = find_entry(index, section, item_id)
        if not info:
            return jsonify({"error": f"{label}不存在"}), 404
        filename = info.get("filename", "")
        filepath = os.path.join(target_dir, filename)
        trashed = ""
        if filename and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                # Windows 上这个文件可能正被读取（有人正在下载）或被杀软占用：
                # 别让整个删除请求炸成 500 —— 先改名挪开（索引照删，稍后可清理），
                # 改名也失败才如实报错、并**保留**索引项（免得"列表里没了、文件还在"）。
                try:
                    trashed = filepath + ".trash-" + datetime.now().strftime("%Y%m%d%H%M%S")
                    os.replace(filepath, trashed)
                except OSError as e:
                    return jsonify({"error": f"删除文件失败：{e}"}), 500
        remove_entry(index, section, item_id)
        save_index(index)
        msg = f"已删除：{info.get('name')}"
        if trashed:
            msg += "（文件当时被占用，已挪到 %s，稍后可清理）" % os.path.basename(trashed)
        return jsonify({"success": True, "message": msg})

def _store_upload(section, target_dir, original_name, content, form, ext_whitelist=None,
                  report=None):
    """把**已解析好的 JSON 内容**落盘 + 写索引。整包上传、分片上传、gzip 上传共用这一处。

    ext_whitelist 给了就校验扩展名（类型注册表里的 ext），不在白名单里直接报错。
    report 给了就往里塞"这次发生了什么"（目前是剔掉了哪些本地键），给响应/log 用；
    不塞进索引 —— 索引是给所有客户端看的，不该带上传过程的细节。

    落盘前统一过一遍 strip_local_state：**三种上传路径都走这里**，
    所以"去历史"只需要在这一个地方生效（而不是每个视图各抄一遍、迟早漏一个）。
    """
    content, stripped = strip_local_state(content)
    if stripped and report is not None:
        report["stripped"] = stripped
    if stripped:
        print("[上传] 已剔掉 %s%s 等 %d 个本地历史/状态键（每次上传都是新卡）"
              % ("、".join(stripped[:3]), "…" if len(stripped) > 3 else "", len(stripped)))
    original_name = os.path.basename(original_name or "") or "upload.json"
    ext = (os.path.splitext(original_name)[1] or ".json").lower()
    if ext_whitelist and ext not in tuple(ext_whitelist):
        raise ValueError("不接受的扩展名 %s（只收 %s）" % (ext, "、".join(ext_whitelist)))
    new_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(target_dir, new_filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    name = content.get("name", "未命名") if isinstance(content, dict) else "未命名"
    entry = {
        "id": str(uuid.uuid4()),
        "name": str(name)[:120],
        "filename": new_filename,
        "original_name": original_name,
        "author": (form.get("author") or "anonymous").strip()[:60] or "anonymous",
        "tags": clean_tags(form.get("tags", "")),
        "description": (form.get("description") or "").strip()[:500],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "downloads": 0,
        "likes": 0,
    }
    # 提取预览信息
    if isinstance(content, dict):
        for key in ("system_prompt", "background", "description"):
            val = content.get(key)
            if isinstance(val, str) and val:
                entry[f"{key}_preview"] = val[:120]

    with _index_lock:
        index = load_index()
        index.setdefault(section, []).append(entry)
        save_index(index)
    return entry

def handle_upload(section, target_dir, default_name):
    limited = _rate_gate()
    if limited is not None:
        return limited
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400
    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    try:
        content = json.load(file)
    except Exception as e:
        return jsonify({"error": f"JSON 解析失败：{e}"}), 400
    if not isinstance(content, (dict, list)):
        return jsonify({"error": "内容必须是 JSON 对象或数组"}), 400

    original_name = os.path.basename(file.filename or "") or f"{default_name}.json"
    report = {}
    entry = _store_upload(section, target_dir, original_name, content, request.form,
                          report=report)
    return jsonify({
        "success": True,
        "id": entry["id"],
        "stripped": report.get("stripped") or [],
        "message": f"上传成功：{entry['name']}"
    }), 201

def _decompress_gzip(raw, limit_mb=None):
    """gzip 体 → bytes，带体积上限。超限抛 _GzError(413)，坏包抛 _GzError(400)。

    两道关口，顺序是有意的：
      ① 先看 gzip 尾部 4 字节 ISIZE（原长 mod 2^32）—— 压缩炸弹在这一步就挡掉，
         不需要先把 64MB 展开进内存再发现超限；
      ② 再 gzip.decompress() 后复核真实长度 —— ISIZE 可以伪造（改掉尾部几个字节即可），
         所以它只能当"快速否决"，不能当"结论"。
    """
    limit = (_conf("UPLOAD_MAX_MB") if limit_mb is None else limit_mb) * 1024 * 1024
    if not raw:
        raise _GzError("body 是空的（这条接口要 gzip(JSON) 压缩体）", 400)
    if len(raw) >= 18 and raw[:2] == b"\x1f\x8b":
        isize = struct.unpack("<I", raw[-4:])[0]
        if isize > limit:
            raise _GzError("解压后超过上限 %d MB" % _conf("UPLOAD_MAX_MB"), 413)
    try:
        data = gzip.decompress(raw)
    except Exception as e:
        raise _GzError("不是合法的 gzip：%s" % str(e)[:120], 400)
    if len(data) > limit:
        raise _GzError("解压后超过上限 %d MB" % _conf("UPLOAD_MAX_MB"), 413)
    return data

def _lan_ip() -> str:
    """获取本机局域网 IP（连接外网探测到的本地地址；失败回退回环）"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip or "127.0.0.1"
    except Exception:
        return "127.0.0.1"

def _udp_discover_loop():
    """局域网自动发现：手机发 DISCOVER_MAGIC 到本端口，服务器回自己 IP + HTTP 端口。
    手机据此自动找到电脑，无需手动填 IP。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", _conf("DISCOVER_PORT")))
    except Exception as e:
        print(f"[局域网发现] UDP 监听失败（端口 {DISCOVER_PORT}）: {e}")
        return
    print(f"[局域网发现] 已启动：手机发探测包到 UDP {DISCOVER_PORT} 即可自动找到本机")
    while True:
        try:
            data, addr = s.recvfrom(1024)
        except Exception:
            continue
        if data and data.strip() == DISCOVER_MAGIC:
            try:
                reply = json.dumps(
                    {"service": "dick-sync", "name": "DICK 创意工坊", "host": _lan_ip(), "port": PORT}
                ).encode("utf-8")
                s.sendto(reply, addr)
            except Exception:
                pass


class _GzError(Exception):
    """解压失败（区分 400 坏包 / 413 超限：客户端要能分别提示）"""

    def __init__(self, msg, code):
        Exception.__init__(self, msg)
        self.msg = msg
        self.code = code


def _rate_gate():
    """限流闸门：放行返回 None，超限返回**带 Retry-After 的 429**。

    Retry-After 是标准头（秒）：客户端读到就等这么久再来，
    比让客户端自己猜"退避多久"靠谱 —— 猜短了继续撞墙，猜长了白等。
    """
    ok, wait, why = _rate_check()
    if ok:
        return None
    secs = int(max(1.0, round(wait)))
    resp = jsonify({"error": "上传太频繁了，歇一会儿再试（%s）" % why,
                    "retry_after": secs, "limit": why})
    resp.status_code = 429
    resp.headers["Retry-After"] = str(secs)
    resp.headers["X-RateLimit-Limit"] = str(_conf("RATE_PER_MIN"))
    return resp


def _rate_check():
    """滑动窗口限流（两档）。返回 (放行?, 建议等待秒数, 是哪一档超了)。

    分钟档挡"并发突发"（客户端本该 500ms 一次串行发，连打十几次必是异常）；
    小时档挡"整夜刷屏"。两档都不该挡到正常的每 0.5 秒一次。
    """
    now = time.time()
    ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
    with _RATE_LOCK:
        arr = [t for t in _RATE_HITS.get(ip, []) if now - t < 3600]
        _RATE_HITS[ip] = arr
        if _conf("RATE_PER_HOUR") > 0 and len(arr) >= _conf("RATE_PER_HOUR"):
            # 等最早那次滑出一个小时的窗口
            return False, max(1.0, arr[0] + 3600 - now), "每小时 %d 次" % _conf("RATE_PER_HOUR")
        recent = [t for t in arr if now - t < 60]
        if _conf("RATE_PER_MIN") > 0 and len(recent) >= _conf("RATE_PER_MIN"):
            return False, max(0.5, recent[0] + 60 - now), "每分钟 %d 次" % _conf("RATE_PER_MIN")
        arr.append(now)
        if len(_RATE_HITS) > 2000:            # 顺手清掉两小时没动静的 IP
            for k in [k for k, v in _RATE_HITS.items() if not v or now - v[-1] > 7200][:500]:
                _RATE_HITS.pop(k, None)
    return True, 0.0, ""


_RATE_HITS = {}


_RATE_LOCK = threading.Lock()
