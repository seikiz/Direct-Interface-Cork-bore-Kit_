# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   net.py - 创意工坊服务器 (workshop_server)
#   提供角色卡/世界卡的在线分享接口
#
#   启动:   python net.py
#   可选环境变量:
#     WORKSHOP_HOST     监听地址（默认 0.0.0.0，即局域网可访问）
#     WORKSHOP_PORT     端口（默认 5000）
#     WORKSHOP_API_KEY  设置后，上传/删除等写操作需要请求头 X-API-Key
#                       （不设置则工坊为开放模式，任何人可上传）
#     WORKSHOP_DEBUG    设为 1 开启 Flask debug 模式（默认关闭）
# ============================================================

import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, send_file

# 敏感信息加密（与主程序共用）：sync_settings.json 里共享的 API 码不再明文落盘
try:
    import secret_store
except Exception:
    secret_store = None

# Windows 中文控制台（GBK）无法打印 emoji，
# 保留控制台编码不变，仅把不可编码字符替换为 ?，避免启动崩溃
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:
            pass

app = Flask(__name__)


def _app_root() -> str:
    """应用根目录：源码运行用 __file__；冻结为 EXE 后用 sys.executable，
    保证 net_server.exe 能定位旁边的 config.json / workshop_data。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# 数据存储目录
DATA_DIR = os.path.join(_app_root(), "workshop_data")
CARDS_DIR = os.path.join(DATA_DIR, "cards")
WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
PLUGINS_DIR = os.path.join(DATA_DIR, "plugins")
PACKS_DIR = os.path.join(DATA_DIR, "packs")
SAVES_DIR = os.path.join(DATA_DIR, "saves")
SYNC_SETTINGS_FILE = os.path.join(DATA_DIR, "sync_settings.json")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")

# ============================================================
#  资源类型注册表 —— **加一种资源 = 加一行**
# ============================================================
#  以前每种资源（角色卡/世界卡/插件）都手写一整套路由（list/download/upload/like/delete），
#  加第四种就要抄 6~8 个函数。现在路由是泛型的（`/api/<rtype>/...`），类型差异全写在这里：
#    dir      落盘目录
#    label    给人看的名字（错误信息里用）
#    ext      允许的扩展名（白名单，上传时校验）
#    index    索引里对应的段名（同时也是 /api/<rtype>/list 的数据源）
#  想再加类型（剧本 codex 包、语音/声库、Live2D、生图预设…）只要往这里加一行，
#  再确保目录建出来（见下面的 for 循环）——路由、搜索、统计、点赞、删除全都自动生效。
# ============================================================
TYPES = {
    "cards":   {"dir": CARDS_DIR,   "label": "角色卡", "ext": (".json", ".png"), "index": "cards"},
    "worlds":  {"dir": WORLDS_DIR,  "label": "世界卡", "ext": (".json",),        "index": "worlds"},
    "plugins": {"dir": PLUGINS_DIR, "label": "插件",   "ext": (".py", ".zip"),   "index": "plugins"},
    # 世界卡包（world_packs/ 那 6 张成套卡）：一整包带地图/年代参数，装进 worlds/ 就能用
    "packs":   {"dir": PACKS_DIR,   "label": "世界卡包", "ext": (".json",),      "index": "packs"},
}

# 索引结构版本：以后真要迁移时靠它判断"这是老索引"（照 crypto_core 的做法）
INDEX_SCHEMA = 1

# 能力清单：客户端据此决定"走整包还是分片""能不能按类型搜"（见 /api/capabilities）
FEATURES = ("search", "like", "progress", "chunked_upload", "types", "capabilities")
UPLOAD_MAX_MB = int(os.environ.get("WORKSHOP_UPLOAD_MAX_MB", "64"))

# 运行配置（环境变量可覆盖）
API_KEY = os.environ.get("WORKSHOP_API_KEY", "").strip()
HOST = os.environ.get("WORKSHOP_HOST", "0.0.0.0")
PORT = int(os.environ.get("WORKSHOP_PORT", "5000"))
DEBUG = os.environ.get("WORKSHOP_DEBUG", "0") == "1"
# 读接口是否也要 Key（默认关 = 保持老行为：只读公开）。公网部署建议开。
READ_KEY = os.environ.get("WORKSHOP_READ_KEY", "0") == "1"
# 内置中转（/relay）：默认关。客户端已停用它（香港工坊 /relay 出于安全关闭），
# 留着只是历史包袱 + 开放代理风险；真要临时用就显式设 WORKSHOP_RELAY=1。
RELAY_ON = os.environ.get("WORKSHOP_RELAY", "0") == "1"

# 局域网发现：手机向该 UDP 端口发探测包，服务器回复自身 IP + HTTP 端口
DISCOVER_PORT = int(os.environ.get("WORKSHOP_DISCOVER_PORT", "5001"))
DISCOVER_MAGIC = b"DICK_DISCOVER_V1"

# 索引文件进程内锁（防并发读写冲突）
_index_lock = threading.Lock()

for d in [DATA_DIR, CARDS_DIR, WORLDS_DIR, PLUGINS_DIR, PACKS_DIR, SAVES_DIR]:
    os.makedirs(d, exist_ok=True)


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


if not os.path.exists(INDEX_FILE):
    save_index({"schema": INDEX_SCHEMA, "cards": [], "worlds": [], "plugins": [], "packs": [],
                "users": {}})


# ============ 工具函数 ============

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


def require_auth(f):
    """写操作认证（可选）：
    - GET 一律公开；
    - 未设置 WORKSHOP_API_KEY 时为开放模式，写操作无需认证；
    - 设置了 KEY 则 POST/DELETE 必须携带 X-API-Key 请求头。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "GET":
            return f(*args, **kwargs)
        if not API_KEY:
            return f(*args, **kwargs)
        api_key = request.headers.get("X-API-Key", "")
        if api_key != API_KEY:
            return jsonify({"error": "API Key 无效或缺失"}), 401
        return f(*args, **kwargs)
    return decorated


def require_auth_strict(f):
    """含敏感数据的接口（返回/写入共享 API 码）：设置了 KEY 时，GET 也要认证。
    客户端（手机/PC）同步时始终带 X-API-Key 头，因此不会破坏合法同步；
    但无 KEY 的公网/局域网陌生人无法白拿共享的 API 码。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        api_key = request.headers.get("X-API-Key", "")
        if api_key != API_KEY:
            return jsonify({"error": "API Key 无效或缺失"}), 401
        return f(*args, **kwargs)
    return decorated


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


# ============ 基础接口 ============

@app.get("/api/health")
def health():
    """健康检查 + **能力协商**：客户端不必再猜服务端支持什么。

    老客户端只读 status/auth（照旧）；新客户端读 api/types/features/limits 决定
    走整包还是分片上传、能不能按类型搜索、读接口是否要 Key。
    """
    return jsonify({
        "status": "ok",
        "service": "创意工坊服务器",
        "auth": "key" if API_KEY else "open",
        "api": 1,
        "schema": INDEX_SCHEMA,
        "types": sorted(TYPES.keys()),
        "features": list(FEATURES),
        "read_key": bool(READ_KEY),
        "relay": bool(RELAY_ON),
        "limits": {"upload_max_mb": UPLOAD_MAX_MB},
        "timestamp": datetime.now().isoformat(),
    })


@app.get("/api/capabilities")
def capabilities():
    """单独一份能力清单（与 /api/health 的字段同源；给"只想知道能干什么"的调用方）

    字段形状是**契约**：
      types     纯类型名列表（"cards"/"worlds"/"plugins"/"packs"）—— 客户端只拿它做判断；
      registry  每种类型的细节（中文名、扩展名白名单）—— 界面/校验用；
    两者分开，客户端就不必去解析对象数组（早期版本 types 里塞对象，
    客户端按字符串列表读，结果"世界卡包"永远判不出来）。
    """
    return jsonify({
        "api": 1,
        "schema": INDEX_SCHEMA,
        "types": sorted(TYPES.keys()),
        "registry": [{"name": k, "label": v["label"], "ext": list(v["ext"])} for k, v in TYPES.items()],
        "features": list(FEATURES),
        "limits": {"upload_max_mb": UPLOAD_MAX_MB},
    })


@app.before_request
def _read_key_gate():
    """WORKSHOP_READ_KEY=1 时，读接口也要 Key（默认关，保持老行为：只读公开）。

    实测过的现状：不开这个开关时 /api/cards/list、/api/search、/api/stats
    **不带 Key 也返回 200** —— 内容全公开可列。公网部署建议打开。
    """
    if not READ_KEY or not API_KEY:
        return None
    if request.method not in ("GET", "HEAD"):
        return None
    p = request.path or ""
    if not p.startswith("/api/") or p in ("/api/health", "/api/capabilities"):
        return None          # 健康检查/能力清单永远公开（探活要用）
    if request.headers.get("X-API-Key", "") != API_KEY:
        return jsonify({"error": "需要 API Key（服务端开了 WORKSHOP_READ_KEY）"}), 401
    return None


# ============ 内置代理通道（中转转发） ============
@app.route("/relay/<b64target>/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.route("/relay/<b64target>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def relay_proxy(b64target, subpath=""):
    """透明转发：把请求原样转发到 <解码后的目标>/<subpath>，密钥经 Authorization 原样透传。
    客户端把 base_url 做 urlsafe-base64（去 padding）放进路径即可让本地/云端服务代为访问，
    用于直连被墙的通道（如 OpenAI 官方 API）。

    **默认关闭**：两端客户端已停用中转（BUILTIN_RELAY = ""），留着等于对外挂一个开放代理。
    要临时用就设 WORKSHOP_RELAY=1（health 里的 relay 字段会告诉你开没开）。
    """
    if not RELAY_ON:
        return jsonify({"error": "relay 已停用（需服务端设 WORKSHOP_RELAY=1）"}), 404
    try:
        import base64
        pad = "=" * (-len(b64target) % 4)
        target = base64.urlsafe_b64decode(b64target + pad).decode("utf-8")
    except Exception:
        return jsonify({"error": "bad target"}), 400
    if not (target.startswith("http://") or target.startswith("https://")):
        return jsonify({"error": "bad target"}), 400
    url = target.rstrip("/") + (("/" + subpath) if subpath else "")
    hdrs = {}
    for k, v in request.headers.items():
        if k.lower() in ("authorization", "content-type", "accept", "x-api-key", "user-agent"):
            hdrs[k] = v
    try:
        import requests as _rq
        r = _rq.request(request.method, url, headers=hdrs,
                        data=request.get_data(), timeout=600)
        resp = app.response_class(
            response=r.content,
            status=r.status_code,
            content_type=r.headers.get("Content-Type", "application/json"))
        return resp
    except Exception as e:
        return jsonify({"error": "relay fail: " + str(e)[:200]}), 502


@app.get("/api/stats")
def stats():
    """工坊统计：**按类型注册表聚合**（以前手写 cards+worlds，漏了 plugins；现在加类型也不会漏）"""
    index = load_index()
    out = {"downloads": 0, "likes": 0, "types": {}}
    for key, spec in TYPES.items():
        items = index.get(spec["index"], []) or []
        out[spec["index"]] = len(items)          # 老键名照旧（cards/worlds/plugins）
        out["types"][key] = len(items)
        out["downloads"] += sum(int(it.get("downloads", 0) or 0) for it in items)
        out["likes"] += sum(int(it.get("likes", 0) or 0) for it in items)
    return jsonify(out)


# ============ 树存档同步（聊天进度互通） ============

def _save_path(card_id: str) -> str:
    """把角色名转成安全的存档文件名（防路径穿越）"""
    safe = (card_id or "unknown").strip()
    safe = safe.replace("/", "_").replace("\\", "_").replace("..", "_")
    safe = safe[:80] or "unknown"
    return os.path.join(SAVES_DIR, safe + ".json")


@app.post("/api/save/<card_id>")
@require_auth
def save_upload(card_id):
    """上传某个角色的聊天树存档（后来者胜，服务器盖时间戳）。"""
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}
    tree = body.get("tree")
    if not isinstance(tree, dict):
        return jsonify({"error": "tree 缺失或非法"}), 400
    if not (tree.get("nodes") or {}):
        return jsonify({"error": "empty tree"}), 400
    ts = datetime.now(timezone.utc).isoformat()
    with _index_lock:
        try:
            with open(_save_path(card_id), "w", encoding="utf-8") as f:
                json.dump({"kind": "dick_tree", "ts": ts, "tree": tree}, f, ensure_ascii=False)
        except Exception as e:
            return jsonify({"error": "save fail: " + str(e)[:200]}), 500
    return jsonify({"ok": True, "ts": ts})


@app.get("/api/save/<card_id>")
def save_download(card_id):
    """下载某个角色最新的聊天树存档；不存在返回 404。"""
    p = _save_path(card_id)
    if not os.path.exists(p):
        return jsonify({"error": "no save"}), 404
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return jsonify({"error": "bad save"}), 500
    return jsonify({"kind": data.get("kind"), "ts": data.get("ts", ""), "tree": data.get("tree", {})})


@app.delete("/api/save/<card_id>")
@require_auth
def save_delete(card_id):
    """删掉某个角色的聊天树存档（要 Key）。
    用途：清掉服务器上不该留的进度（换设备不想续聊、测试留下的脏数据）。"""
    p = _save_path(card_id)
    if not os.path.exists(p):
        return jsonify({"ok": True, "removed": False})
    try:
        os.remove(p)
        return jsonify({"ok": True, "removed": True})
    except OSError:
        # Windows 上文件被占用时改名挪走（与作品删除同一套兜底）
        try:
            os.replace(p, p + ".trash-" + str(int(datetime.now().timestamp())))
            return jsonify({"ok": True, "removed": True, "note": "文件被占用，已挪走"})
        except Exception as e:
            return jsonify({"error": "删除失败：" + str(e)[:200]}), 500


# ============ 同步设置（API 码等跨设备共享） ============

@app.get("/api/sync/api")
@require_auth_strict
def sync_api_get():
    """获取共享的模型连接配置（API 码等）；无则返回空对象。
    设置了 WORKSHOP_API_KEY 时该接口也需要认证，避免共享的 API 码被公开读取。"""
    return jsonify(_load_sync_settings().get("api") or {})


@app.post("/api/sync/api")
@require_auth_strict
def sync_api_post():
    """保存共享的模型连接配置（后来者胜）。"""
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return jsonify({"error": "bad payload"}), 400
    with _index_lock:
        cfg = _load_sync_settings()
        cfg["api"] = body
        try:
            _save_sync_settings(cfg)
        except Exception as e:
            return jsonify({"error": "save fail: " + str(e)[:200]}), 500
    return jsonify({"ok": True})


# ============ 列表与搜索 ============

@app.get("/api/cards/list")
def list_cards():
    """获取所有角色卡列表"""
    index = load_index()
    cards = sorted(index.get("cards", []), key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify(cards)


@app.get("/api/worlds/list")
def list_worlds():
    """获取所有世界卡列表"""
    index = load_index()
    worlds = sorted(index.get("worlds", []), key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify(worlds)


@app.get("/api/search")
def search_all():
    """统一搜索（类型注册表驱动），结果条目均带 type 字段（中文名）。
    参数: q=关键词  type=all|cards|worlds|packs|角色卡|世界卡|世界卡包
    加一种资源后这里不用改：注册表里新加的类型自动进搜索。"""
    query = (request.args.get("q") or "").strip()
    want = (request.args.get("type") or "all").strip()
    index = load_index()
    matcher = search_index(index, query)

    results = []
    for code, spec in TYPES.items():
        # type 过滤：接口名（cards）、单数别名（card）、中文名（角色卡）都认；all 全给
        if want and want.lower() not in ("all", code, code.rstrip("s"), spec["label"]):
            continue
        for item in index.get(spec["index"], []) or []:
            if matcher(item):
                results.append(dict(item, type=spec["label"]))
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify(results[:100])


@app.get("/api/cards/search")
def search_cards():
    """搜索角色卡（兼容旧接口），结果带 type 字段"""
    query = (request.args.get("q") or "").strip()
    index = load_index()
    matcher = search_index(index, query)
    results = [dict(c, type="角色卡") for c in index.get("cards", []) if matcher(c)]
    return jsonify(results[:50])


# ============ 下载 / 点赞 / 删除 ============

def download_entry(section, target_dir, item_id, label):
    with _index_lock:
        index = load_index()
        info = find_entry(index, section, item_id)
        if not info:
            return jsonify({"error": f"{label}不存在"}), 404
        filename = info.get("filename", "")
        filepath = os.path.join(target_dir, filename)
        if not filename or not os.path.exists(filepath):
            return jsonify({"error": "文件丢失"}), 404
        # 更新下载次数
        info["downloads"] = info.get("downloads", 0) + 1
        save_index(index)
    download_name = info.get("original_name") or filename
    return send_file(filepath, as_attachment=True, download_name=download_name)


@app.get("/api/cards/<card_id>")
def download_card(card_id):
    """下载指定角色卡"""
    return download_entry("cards", CARDS_DIR, card_id, "角色卡")


@app.get("/api/worlds/<world_id>")
def download_world(world_id):
    """下载指定世界卡"""
    return download_entry("worlds", WORLDS_DIR, world_id, "世界卡")


def like_entry(section, item_id, label):
    with _index_lock:
        index = load_index()
        info = find_entry(index, section, item_id)
        if not info:
            return jsonify({"error": f"{label}不存在"}), 404
        info["likes"] = info.get("likes", 0) + 1
        save_index(index)
        return jsonify({"success": True, "likes": info["likes"]})


@app.post("/api/cards/<card_id>/like")
def like_card(card_id):
    """点赞角色卡"""
    return like_entry("cards", card_id, "角色卡")


@app.post("/api/worlds/<world_id>/like")
def like_world(world_id):
    """点赞世界卡"""
    return like_entry("worlds", world_id, "世界卡")


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


@app.delete("/api/cards/<card_id>")
@require_auth
def delete_card(card_id):
    """删除角色卡"""
    return delete_entry("cards", CARDS_DIR, card_id, "角色卡")


@app.delete("/api/worlds/<world_id>")
@require_auth
def delete_world(world_id):
    """删除世界卡"""
    return delete_entry("worlds", WORLDS_DIR, world_id, "世界卡")


# ============ 上传 ============

def _store_upload(section, target_dir, original_name, content, form, ext_whitelist=None):
    """把**已解析好的 JSON 内容**落盘 + 写索引。整包上传与分片上传共用这一处。

    ext_whitelist 给了就校验扩展名（类型注册表里的 ext），不在白名单里直接报错。
    """
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
    entry = _store_upload(section, target_dir, original_name, content, request.form)
    return jsonify({
        "success": True,
        "id": entry["id"],
        "message": f"上传成功：{entry['name']}"
    }), 201


@app.post("/api/cards/upload")
@require_auth
def upload_card():
    """上传角色卡"""
    return handle_upload("cards", CARDS_DIR, "未命名角色")


@app.post("/api/worlds/upload")
@require_auth
def upload_world():
    """上传世界卡"""
    return handle_upload("worlds", WORLDS_DIR, "未命名世界")


# ============ 泛型资源路由（类型注册表驱动） ============
#  加一种资源 = 在 TYPES 里加一行 + 目录建出来；下面这几个视图对所有类型都生效。
#  老路径（/api/cards/list 等）与泛型路径**形状相同**，Werkzeug 里静态段优先，
#  所以老客户端照旧能用，新类型不用再抄一遍路由。
app.config["MAX_CONTENT_LENGTH"] = UPLOAD_MAX_MB * 1024 * 1024


def _bad_type(rtype):
    return jsonify({"error": "未知的资源类型：%s" % rtype,
                    "types": sorted(TYPES.keys())}), 400


@app.get("/api/<rtype>/list")
def list_any(rtype):
    """列出一个类型的全部作品（索引里那一段）"""
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    return jsonify(load_index().get(spec["index"], []) or [])


@app.get("/api/<rtype>/<item_id>")
def download_any(rtype, item_id):
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    return download_entry(spec["index"], spec["dir"], item_id, spec["label"])


@app.post("/api/<rtype>/<item_id>/like")
def like_any(rtype, item_id):
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    return like_entry(spec["index"], item_id, spec["label"])


@app.delete("/api/<rtype>/<item_id>")
@require_auth
def delete_any(rtype, item_id):
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    return delete_entry(spec["index"], spec["dir"], item_id, spec["label"])


@app.post("/api/<rtype>/upload")
@require_auth
def upload_any(rtype):
    """整包上传（小文件走这条；大文件走下面的分片）"""
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    return handle_upload(spec["index"], spec["dir"], spec["label"])


# ---- 分片上传：大文件（声库 / Live2D / 卡包）不再顶 body 上限 ----
CHUNK_DIR = os.path.join(DATA_DIR, ".uploads")


@app.post("/api/<rtype>/upload/init")
@require_auth
def upload_init(rtype):
    """开一次分片上传，拿到 upload_id"""
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    uid = uuid.uuid4().hex
    os.makedirs(os.path.join(CHUNK_DIR, uid), exist_ok=True)
    return jsonify({"success": True, "upload_id": uid, "max_mb": UPLOAD_MAX_MB}), 201


def _arg(name, default=""):
    """分片上传的参数读法：**优先 query string**（因为 body 是裸分片字节，塞不进表单）。

    也兼容 form（客户端要是把元数据放表单里发也能用），两处都看。
    """
    v = request.args.get(name)
    if v is None:
        v = request.form.get(name)
    return default if v is None else str(v).strip()


@app.post("/api/<rtype>/upload/chunk")
@require_auth
def upload_chunk(rtype):
    """收一片：body 就是裸字节（不走 multipart），元数据走 query string"""
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    uid = _arg("upload_id")
    idx = _arg("index")
    if not uid or not idx.isdigit():
        return jsonify({"error": "缺少 upload_id / index（放 query string 里）"}), 400
    d = os.path.join(CHUNK_DIR, uid)
    if not os.path.isdir(d):
        return jsonify({"error": "upload_id 不存在（先 init）"}), 404
    data = request.get_data()
    if not data:
        return jsonify({"error": "空分片"}), 400
    with open(os.path.join(d, "%08d.part" % int(idx)), "wb") as f:
        f.write(data)
    return jsonify({"success": True, "index": int(idx), "bytes": len(data)})


@app.post("/api/<rtype>/upload/finish")
@require_auth
def upload_finish(rtype):
    """把分片按序拼起来，当作一次整包上传登记（扩展名白名单照查）"""
    spec = type_of(rtype)
    if not spec:
        return _bad_type(rtype)
    uid = _arg("upload_id")
    d = os.path.join(CHUNK_DIR, uid)
    if not uid or not os.path.isdir(d):
        return jsonify({"error": "upload_id 不存在（先 init）"}), 404
    parts = sorted(p for p in os.listdir(d) if p.endswith(".part"))
    if not parts:
        return jsonify({"error": "没有收到任何分片"}), 400
    raw = b""
    for p in parts:
        with open(os.path.join(d, p), "rb") as f:
            raw += f.read()
    if len(raw) > UPLOAD_MAX_MB * 1024 * 1024:
        return jsonify({"error": "超过上限 %d MB" % UPLOAD_MAX_MB}), 413
    try:
        content = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return jsonify({"error": "拼起来不是合法 JSON：%s" % e}), 400
    name = (_arg("filename") or "upload.json")
    try:
        entry = _store_upload(spec["index"], spec["dir"], name, content, request.form, spec["ext"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    for p in parts:
        try:
            os.remove(os.path.join(d, p))
        except OSError:
            pass
    try:
        os.rmdir(d)
    except OSError:
        pass
    return jsonify({"success": True, "id": entry["id"],
                    "message": "分片上传完成：%s" % entry["name"]}), 201


# ============ 插件市场（创意工坊插件 Tab） ============

@app.get("/api/plugins/list")
def list_plugins():
    """获取所有插件列表"""
    index = load_index()
    plugins = sorted(index.get("plugins", []), key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify(plugins)


@app.get("/api/plugins/<plugin_id>")
def download_plugin(plugin_id):
    """下载插件 .py 文件"""
    with _index_lock:
        index = load_index()
        info = find_entry(index, "plugins", plugin_id)
        if not info:
            return jsonify({"error": "插件不存在"}), 404
        filename = info.get("filename", "")
        filepath = os.path.join(PLUGINS_DIR, filename)
        if not filename or not os.path.exists(filepath):
            return jsonify({"error": "文件丢失"}), 404
        info["downloads"] = info.get("downloads", 0) + 1
        save_index(index)
    download_name = info.get("original_name") or filename
    return send_file(filepath, as_attachment=True, download_name=download_name)


@app.post("/api/plugins/upload")
@require_auth
def upload_plugin():
    """上传插件（.py 文件 + 表单 name/version/description）"""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "缺少插件文件"}), 400
    if not file.filename.lower().endswith(".py"):
        return jsonify({"error": "仅支持 .py 插件文件"}), 400
    original_name = os.path.basename(file.filename or "") or "plugin.py"
    content = file.read()
    if not content.strip():
        return jsonify({"error": "插件文件为空"}), 400
    new_filename = f"{uuid.uuid4().hex}.py"
    filepath = os.path.join(PLUGINS_DIR, new_filename)
    with open(filepath, "wb") as f:
        f.write(content)
    name = (request.form.get("name") or original_name[:-3]).strip()[:60]
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "version": (request.form.get("version") or "1.0").strip()[:20],
        "filename": new_filename,
        "original_name": original_name,
        "author": (request.form.get("author") or "anonymous").strip()[:60] or "anonymous",
        "description": (request.form.get("description") or "").strip()[:500],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "downloads": 0,
        "likes": 0,
    }
    with _index_lock:
        index = load_index()
        index["plugins"].append(entry)
        save_index(index)
    return jsonify({"success": True, "id": entry["id"], "message": f"上传成功：{name}"}), 201


@app.post("/api/plugins/<plugin_id>/like")
def like_plugin(plugin_id):
    """点赞插件"""
    return like_entry("plugins", plugin_id, "插件")


@app.delete("/api/plugins/<plugin_id>")
@require_auth
def delete_plugin(plugin_id):
    """删除插件（保留本地文件，仅从索引移除）"""
    with _index_lock:
        index = load_index()
        info = find_entry(index, "plugins", plugin_id)
        if not info:
            return jsonify({"error": "插件不存在"}), 404
        remove_entry(index, "plugins", plugin_id)
        save_index(index)
    return jsonify({"success": True})


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
        s.bind(("0.0.0.0", DISCOVER_PORT))
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


if __name__ == "__main__":
    import threading as _th
    _th.Thread(target=_udp_discover_loop, daemon=True).start()
    print("🚀 创意工坊服务器启动中...")
    print(f"📂 数据目录: {DATA_DIR}")
    print(f"🌐 本机访问: http://localhost:{PORT}")
    print(f"📱 手机直连（同一 Wi-Fi）: http://{_lan_ip()}:{PORT}   ← 把这段填到手机工坊地址")
    print(f"🔑 认证模式: {'需要 X-API-Key' if API_KEY else '开放模式（无需认证）'}")
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
