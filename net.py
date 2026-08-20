# ============================================================
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
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_file

# Windows 中文控制台（GBK）无法打印 emoji，
# 保留控制台编码不变，仅把不可编码字符替换为 ?，避免启动崩溃
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:
            pass

app = Flask(__name__)

# 数据存储目录
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workshop_data")
CARDS_DIR = os.path.join(DATA_DIR, "cards")
WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
PLUGINS_DIR = os.path.join(DATA_DIR, "plugins")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")

# 运行配置（环境变量可覆盖）
API_KEY = os.environ.get("WORKSHOP_API_KEY", "").strip()
HOST = os.environ.get("WORKSHOP_HOST", "0.0.0.0")
PORT = int(os.environ.get("WORKSHOP_PORT", "5000"))
DEBUG = os.environ.get("WORKSHOP_DEBUG", "0") == "1"

# 索引文件进程内锁（防并发读写冲突）
_index_lock = threading.Lock()

for d in [DATA_DIR, CARDS_DIR, WORLDS_DIR, PLUGINS_DIR]:
    os.makedirs(d, exist_ok=True)


def load_index():
    """读取索引，容错处理损坏文件"""
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}
    data.setdefault("cards", [])
    data.setdefault("worlds", [])
    data.setdefault("plugins", [])
    data.setdefault("users", {})
    return data


def save_index(index):
    """原子写入索引（先写临时文件再替换，避免写一半损坏）"""
    tmp = INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_FILE)


if not os.path.exists(INDEX_FILE):
    save_index({"cards": [], "worlds": [], "plugins": [], "users": {}})


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
    """健康检查"""
    return jsonify({
        "status": "ok",
        "service": "创意工坊服务器",
        "auth": "key" if API_KEY else "open",
        "timestamp": datetime.now().isoformat(),
    })


# ============ 内置代理通道（中转转发） ============
@app.route("/relay/<b64target>/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.route("/relay/<b64target>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def relay_proxy(b64target, subpath=""):
    """透明转发：把请求原样转发到 <解码后的目标>/<subpath>，密钥经 Authorization 原样透传。
    客户端把 base_url 做 urlsafe-base64（去 padding）放进路径即可让本地/云端服务代为访问，
    用于直连被墙的通道（如 OpenAI 官方 API）。"""
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
    """工坊统计信息"""
    index = load_index()
    cards = index.get("cards", [])
    worlds = index.get("worlds", [])
    return jsonify({
        "cards": len(cards),
        "worlds": len(worlds),
        "downloads": sum(c.get("downloads", 0) for c in cards + worlds),
        "likes": sum(c.get("likes", 0) for c in cards + worlds),
    })


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
    """统一搜索角色卡+世界卡。
    参数: q=关键词  type=all|cards|worlds
    结果条目均带 type 字段（角色卡/世界卡）。
    """
    query = (request.args.get("q") or "").strip()
    rtype = (request.args.get("type") or "all").strip().lower()
    index = load_index()
    matcher = search_index(index, query)

    results = []
    if rtype in ("all", "card", "cards"):
        for c in index.get("cards", []):
            if matcher(c):
                results.append(dict(c, type="角色卡"))
    if rtype in ("all", "world", "worlds"):
        for w in index.get("worlds", []):
            if matcher(w):
                results.append(dict(w, type="世界卡"))
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
        if filename and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError as e:
                return jsonify({"error": f"删除文件失败：{e}"}), 500
        remove_entry(index, section, item_id)
        save_index(index)
        return jsonify({"success": True, "message": f"已删除：{info.get('name')}"})


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
    ext = os.path.splitext(original_name)[1] or ".json"
    new_filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(target_dir, new_filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    name = content.get("name", default_name) if isinstance(content, dict) else default_name
    entry = {
        "id": str(uuid.uuid4()),
        "name": str(name)[:120],
        "filename": new_filename,
        "original_name": original_name,
        "author": (request.form.get("author") or "anonymous").strip()[:60] or "anonymous",
        "tags": clean_tags(request.form.get("tags", "")),
        "description": (request.form.get("description") or "").strip()[:500],
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
        index[section].append(entry)
        save_index(index)

    return jsonify({
        "success": True,
        "id": entry["id"],
        "message": f"上传成功：{name}"
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


if __name__ == "__main__":
    print("🚀 创意工坊服务器启动中...")
    print(f"📂 数据目录: {DATA_DIR}")
    print(f"🌐 访问地址: http://localhost:{PORT}")
    print(f"🔑 认证模式: {'需要 X-API-Key' if API_KEY else '开放模式（无需认证）'}")
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
