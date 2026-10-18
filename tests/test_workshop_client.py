# -*- coding: utf-8 -*-
"""创意工坊**客户端**行为测试（桌面端）：通道回退 / 类型映射 / 能力协商 / gzip / 节奏。

为什么单独一个文件
----------------
线上实测抓到一个很难查的故障：同一个 1.4KB 的世界卡，走系统代理（Clash
127.0.0.1:7890）上传得到 **502 空响应**，直连同一份文件 **201**——代理把稍大的
请求体截断了。而客户端原来 `_ws_proxies()` 没配代理时返回 None，等于"让 requests
自己用系统代理"，于是**只要用户开了代理软件，工坊上传就必坏**。

所以这里钉住这些事：
  ① 通道顺序：手填代理 > 直连 > 系统代理（直连优先，本机地址永远直连）
  ② 换通道重试：一条路吃 5xx / 抛异常就换下一条，并把走通的那条记住；
     重试必须能**重发完整请求体**（上传时文件句柄已到末尾，不能读到空）
  ③ 类型映射与能力协商：世界卡包（packs）只在新服务器上问，老服务器不去问（否则整页报错）
  ④ **gzip 传输通道**：能力位有 → 走 /upload/gz 与 /<id>/gz；没有 / 接口不存在 → 回退 multipart
  ⑤ **传输节奏**：每设备最小间隔（服务器下发优先）+ 429 按 Retry-After 退避
  ⑥ **去历史**：上传体里不能有 history_tree 这类本地状态，但卡面字段必须都在
  ⑦ **两端协议对拍**：桌面 gzip 路径 与 安卓协议（同样的头 + 同样的 gz 体）
     打同一个服务器，落下来的条目字段与文件内容必须一致

跑法：python tests\\test_workshop_client.py
"""
import gzip
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def load_app_module():
    path = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
    spec = importlib.util.spec_from_file_location("dick_ws_client_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeHeaders(dict):
    """大小写不敏感的 headers（requests 的 headers 就是这个语义）"""

    def get(self, key, default=None):
        for k, v in self.items():
            if str(k).lower() == str(key).lower():
                return v
        return default


class FakeResp(object):
    def __init__(self, code, payload=None, text="", content=b"", headers=None):
        self.status_code = code
        self._payload = payload
        self.text = text or json.dumps(payload or {}, ensure_ascii=False)
        self.content = content or self.text.encode("utf-8")
        self.headers = FakeHeaders(headers or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def proxy_key(proxies):
    if not proxies:
        return "<none>"
    return (proxies.get("http") or "") + "|" + (proxies.get("https") or "")


DIRECT_KEY = "|"
DIRECT_PROXY = {"http": "", "https": ""}

# 能力清单的两种回答：有 g<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌zip / 没有 gzip
CAPS_GZ = {"schema": 1, "types": ["cards", "worlds", "plugins", "packs"],
           "features": ["search", "like", "progress", "types", "capabilities", "gzip"],
           "limits": {"upload_max_mb": 64, "min_interval_ms": 500, "max_concurrent": 1}}
CAPS_OLD = {"schema": 1, "types": ["cards", "worlds", "plugins"],
            "features": ["search", "like"], "limits": {}}


def load_net(tmp):
    """把 net.py 装进临时目录（与 test_workshop_server.py 里同一套做法）"""
    spec = importlib.util.spec_from_file_location("dick_net_parity", os.path.join(ROOT, "net.py"))
    net = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(net)
    net.DATA_DIR = tmp
    net.CARDS_DIR = os.path.join(tmp, "cards")
    net.WORLDS_DIR = os.path.join(tmp, "worlds")
    net.PLUGINS_DIR = os.path.join(tmp, "plugins")
    net.PACKS_DIR = os.path.join(tmp, "packs")
    net.SAVES_DIR = os.path.join(tmp, "saves")
    net.SYNC_SETTINGS_FILE = os.path.join(tmp, "sync_settings.json")
    net.INDEX_FILE = os.path.join(tmp, "index.json")
    net.CHUNK_DIR = os.path.join(tmp, ".uploads")
    for d in (net.DATA_DIR, net.CARDS_DIR, net.WORLDS_DIR, net.PLUGINS_DIR,
              net.PACKS_DIR, net.SAVES_DIR, net.CHUNK_DIR):
        os.makedirs(d, exist_ok=True)
    for k in ("cards", "worlds", "plugins", "packs"):
        net.TYPES[k]["dir"] = getattr(net, k.upper() + "_DIR")
    net.API_KEY = ""
    net.READ_KEY = False
    net.RELAY_ON = False
    net.RATE_PER_MIN = 0          # 对拍/节奏测试不掺限流
    net.RATE_PER_HOUR = 0
    net.app.testing = True
    net.save_index({"schema": net.INDEX_SCHEMA, "cards": [], "worlds": [], "plugins": [],
                    "packs": [], "users": {}})
    return net


def flask_sender(client, calls):
    """把 requests.request 接到 Flask 的 test_client 上：真走一遍服务端的路由与解析，
    但不占端口、不出网络（对拍测试要的就是"同一份字节喂给真服务器"）。"""

    def send(method, url, proxies=None, **kw):
        u = urlsplit(url)
        path = u.path + (("?" + u.query) if u.query else "")
        headers = dict(kw.get("headers") or {})
        files = kw.get("files") or {}
        raw = kw.get("data")
        if files:
            data = {}
            for key, val in files.items():
                data[key] = (io.BytesIO(val[1]), val[0])
            for key, val in (kw.get("data") or {}).items():
                data[key] = val
            resp = client.post(path, data=data, content_type="multipart/form-data",
                               headers=headers)
        else:
            body = raw if isinstance(raw, (bytes, bytearray)) else (
                json.dumps(raw).encode("utf-8") if raw else None)
            calls.append({"method": method, "url": url, "body": bytes(body or b""),
                          "headers": dict(headers)})
            resp = client.open(path, method=method, data=body, headers=headers)
        payload = None
        try:
            payload = resp.get_json()
        except Exception:
            payload = None
        return FakeResp(resp.status_code, payload, text=resp.get_data(as_text=True) or "{}",
                        content=resp.data, headers=dict(resp.headers))

    return send


def main():
    print("=" * 62)
    print(u"创意工坊客户端：通道回退 / 类型映射 / 能力协商 / gzip / 节奏 / 去历史")
    print("=" * 62)

    import app_paths
    import requests

    mod = load_app_module()
    tmp = tempfile.mkdtemp(prefix="dick_ws_client_")
    real_base = app_paths.get_base_dir
    calls = []          # 每次请求的 (方法, URL, 通道, 请求体字节数/内容/头)
    routes = {}         # 通道 → 该通道的行为

    real_request = requests.request
    real_getproxies = None
    real_module_base = mod.BASE_DIR
    app = None
    try:
        app_paths.get_base_dir = lambda: tmp
        mod.BASE_DIR = tmp        # workshop_config.json 也挪进临时目录，别碰真实的连接配置
        app = mod.HtmlApp()
        app._ws_active_server = lambda: "http://workshop.test:8080"   # 不真联网探测

        def fake_request(method, url, proxies=None, **kw):
            key = proxy_key(proxies)
            body = b""
            files = kw.get("files") or {}
            for _fn, val in files.items():
                body = val[1] if isinstance(val, tuple) else b""
            if not body and kw.get("data") is not None:
                d = kw["data"]
                body = bytes(d) if isinstance(d, (bytes, bytearray)) else \
                    json.dumps(d, ensure_ascii=False).encode("utf-8")
            calls.append({"method": method, "url": url, "chan": key,
                          "body_len": len(body), "body": body,
                          "json": kw.get("json"),
                          "headers": dict(kw.get("headers") or {}),
                          "is_file": bool(files)})
            act = routes.get(key)
            if act is None:
                return FakeResp(200, {"ok": True})
            if isinstance(act, Exception):
                raise act
            return act()

        requests.request = fake_request
        # 让"系统代理"在测试里可见：直接替掉 app 的方法，别依赖 urllib 的取名字时机。
        # （原来 monkeypatch urllib.request.getproxies，在 GitHub Actions 的 Linux/py3.12 上没生效，
        #   导致"下次直接用记住的通道"这条断言红——CI 红过一轮，就是它。）
        app._ws_system_proxy = lambda: "http://127.0.0.1:7890"

        print(u"\n== ① 通道顺序：手填代理 > 直连 > 系统代理 ==")
        app._ws_proxy_ok = None
        cands = app._ws_proxy_candidates()
        check(u"没填代理时候选是[直连, 系统代理]",
              [proxy_key(c) for c in cands] == [DIRECT_KEY, "http://127.0.0.1:7890|http://127.0.0.1:7890"],
              str([proxy_key(c) for c in cands]))
        check(u"第一个候选是直连（默认不走系统代理）", proxy_key(cands[0]) == DIRECT_KEY)

        # 手填了代理：只走它，不再猜
        with io.open(os.path.join(tmp, "workshop_config.json"), "w", encoding="utf-8") as f:
            json.dump({"server_url": "", "api_key": "", "proxy": "socks5://127.0.0.1:1080"}, f)
        app._ws_proxy_ok = None
        cands2 = app._ws_proxy_candidates()
        check(u"填了代理就只走那一条",
              len(cands2) == 1 and cands2[0]["http"] == "socks5://127.0.0.1:1080", str(cands2))
        # 恢复"没填代理"的状态
        with io.open(os.path.join(tmp, "workshop_config.json"), "w", encoding="utf-8") as f:
            json.dump({"server_url": "", "api_key": "", "proxy": ""}, f)

        print(u"\n== ② 换通道重试：直连 502 → 换系统代理 ==")
        app._ws_proxy_ok = None
        calls[:] = []
        routes.clear()
        routes[DIRECT_KEY] = lambda: FakeResp(502, None, text="")
        routes["http://127.0.0.1:7890|http://127.0.0.1:7890"] = lambda: FakeResp(200, {"ok": True})
        r = app._ws_call("GET", "http://workshop.test:8080/api/health", timeout=3)
        check(u"直连 502 后自动换通道成功", r.status_code == 200 and len(calls) == 2,
              str([c["chan"] for c in calls]))
        check(u"记住走通的通道", proxy_key(getattr(app, "_ws_proxy_ok", None)) ==
              "http://127.0.0.1:7890|http://127.0.0.1:7890", str(getattr(app, "_ws_proxy_ok", None)))
        calls[:] = []
        app._ws_call("GET", "http://workshop.test:8080/api/health", timeout=3)
        check(u"下次直接用记住的通道（不再先撞 502）",
              len(calls) == 1 and calls[0]["chan"] == "http://127.0.0.1:7890|http://127.0.0.1:7890",
              str(calls))

        print(u"\n== ③ 本机地址永远直连（压过已记住的通道） ==")
        calls[:] = []
        app._ws_call("GET", "http://127.0.0.1:5000/api/health", timeout=1, fallback=False)
        check(u"127.0.0.1 只发一次、且走直连",
              len(calls) == 1 and calls[0]["chan"] == DIRECT_KEY, str(calls))

        print(u"\n== ④ 所有通道都失败要抛错（不能静默返回空） ==")
        app._ws_proxy_ok = None
        routes.clear()
        routes[DIRECT_KEY] = lambda: FakeResp(502, None, text="")
        routes["http://127.0.0.1:7890|http://127.0.0.1:7890"] = RuntimeError("connection reset")
        raised = False
        try:
            app._ws_call("GET", "http://workshop.test:8080/api/list", timeout=3)
        except Exception:
            raised = True
        check(u"两条通道都坏时抛异常", raised)

        print(u"\n== ⑤ 上传：换通道重试要重发完整包体 ==")
        app._ws_proxy_ok = None
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()
        routes[DIRECT_KEY] = lambda: FakeResp(502, None, text="")           # 代理坏掉那种空 502
        routes["http://127.0.0.1:7890|http://127.0.0.1:7890"] = \
            lambda: FakeResp(201, {"success": True, "message": u"上传成功"})
        pack = {"name": u"现代都市·合租", "description": u"合租", "rules": [u"通勤是硬成本"]}
        with io.open(os.path.join(app.pack_dir, u"现代都市·合租.json"), "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
        # 先把能力探测走完（它的 502→代理 顺带会把"记住的通道"定成代理），
        # 再清掉记忆，这样**上传本身**才是"先撞直连 502、再换代理"的那一次。
        app._ws_caps()
        app._ws_proxy_ok = None
        calls[:] = []
        res = app.api_workshop_upload(u"世界卡包", u"现代都市·合租")
        # 只看**上传**那几次：客户端现在会先问 /api/capabilities（决定走不走 gzip），
        # 那几次探测不属于"重发包体"的断言范围。
        ups = [x for x in calls if "/upload" in x["url"]]
        check(u"世界卡包走 /api/packs/upload", any("/api/packs/upload" in c["url"] for c in ups),
              str([c["url"] for c in calls]))
        check(u"上传成功（内部换过通道）", res.get("ok") is True, str(res))
        check(u"重试那一次带的是完整包体（不是空文件）",
              len(ups) == 2 and ups[1]["body_len"] > 0 and
              ups[1]["body_len"] == ups[0]["body_len"], str(ups))

        print(u"\n== ⑥ 类型映射 ==")
        check(u"角色卡 → cards", app._ws_kind(u"角色卡")[0] == "cards")
        check(u"世界卡 → worlds", app._ws_kind(u"世界卡")[0] == "worlds")
        check(u"世界卡包 → packs", app._ws_kind(u"世界卡包")[0] == "packs")
        check(u"不认得的类型按世界卡处理（不炸）", app._ws_kind(u"喵喵卡")[0] == "worlds")
        check(u"世界卡包落盘到 world_packs/", app._ws_local_dir(u"世界卡包") == app.pack_dir)
        check(u"本地状态里带 world_packs 列表",
              u"现代都市·合租.json" in (app.api_workshop_state().get("local_packs") or []))

        print(u"\n== ⑦ 能力协商：老服务器不去问 packs ==")
        app._ws_proxy_ok = None
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()

        def old_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(404, None, text="not found")     # 老版本没有这条
            if "/api/cards/list" in url:
                return FakeResp(200, [{"id": "c0", "name": u"老卡"}])
            if "/api/worlds/list" in url:
                return FakeResp(200, [])
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = old_server
        got = app.api_workshop_list()
        check(u"老服务器（无 capabilities）列表仍可用", got.get("ok") is True, str(got))
        check(u"老服务器标成 server_old", got.get("server_old") is True, str(got))
        check(u"没去问 /api/packs/list", not any("/api/packs/list" in c["url"] for c in calls),
              str([c["url"] for c in calls]))

        app._ws_proxy_ok = None
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()

        def new_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, {"schema": 1, "types": ["cards", "worlds", "plugins", "packs"],
                                      "features": ["capabilities", "types"]})
            if "/api/cards/list" in url:
                return FakeResp(200, [{"id": "c1", "name": u"角色甲"}])
            if "/api/worlds/list" in url:
                return FakeResp(200, [])
            if "/api/packs/list" in url:
                return FakeResp(200, [{"id": "p1", "name": u"包甲"}])
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = new_server
        got2 = app.api_workshop_list()
        check(u"新服务器会问 packs 并带回来",
              got2.get("ok") is True and [p["name"] for p in got2.get("packs") or []] == [u"包甲"], str(got2))
        check(u"新服务器不算 old", got2.get("server_old") is False, str(got2))
        check(u"能力清单被缓存（第二次不再探）",
              sum(1 for c in calls if "/api/capabilities" in c["url"]) == 1,
              str([c["url"] for c in calls]))

        print(u"\n== ⑧ types 的两种形状都要认（早期实现塞的是对象） ==")
        app._ws_proxy_ok = None
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()

        def obj_types_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                # 早期实现：types 里是 {"name":...,"label":...,"ext":[...]} 对象数组。
                # 只按字符串读会把 "packs" 判成不存在 → 工坊里永远看不到世界卡包
                # （这条正是"客户端单元测试用字符串、服务端回对象"时漏掉的坑）。
                return FakeResp(200, {"schema": 1, "features": ["types"],
                                      "types": [{"name": "cards", "label": u"角色卡", "ext": [".json"]},
                                                {"name": "packs", "label": u"世界卡包", "ext": [".json"]}]})
            if "/api/cards/list" in url:
                return FakeResp(200, [])
            if "/api/worlds/list" in url:
                return FakeResp(200, [])
            if "/api/packs/list" in url:
                return FakeResp(200, [{"id": "p9", "name": u"对象形状也能识别"}])
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = obj_types_server
        check(u"对象形状的 types 也能认出 packs",
              "packs" in (app._ws_caps().get("types") or []), str(app._ws_caps()))
        got3 = app.api_workshop_list()
        check(u"照样能列出世界卡包",
              [p["name"] for p in got3.get("packs") or []] == [u"对象形状也能识别"], str(got3))

        # ---------------- gzip 传输通道 ----------------
        print(u"\n== ⑨ gzip：能力里有 → 走 /upload/gz（压缩体 + X-Filename） ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()
        gz_pack = {"name": u"压缩包", "params": {"space": u"室内"}}
        with io.open(os.path.join(app.pack_dir, u"压缩包.json"), "w", encoding="utf-8") as f:
            json.dump(gz_pack, f, ensure_ascii=False)

        def gz_upload_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_GZ))
            if "/upload/gz" in url:
                return FakeResp(201, {"success": True, "gzip": True, "id": "gz-1"})
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = gz_upload_server
        res = app.api_workshop_upload(u"世界卡包", u"压缩包")
        ups = [x for x in calls if "/upload" in x["url"]]
        check(u"能力有 gzip 时打到 /api/packs/upload/gz",
              len(ups) == 1 and ups[0]["url"].endswith("/api/packs/upload/gz"),
              str([c["url"] for c in calls]))
        check(u"body 是 gzip 压缩体（1f 8b 魔数）",
              bool(ups) and ups[0]["body"][:2] == b"\x1f\x8b",
              str(ups[0]["body"][:6] if ups else b""))
        check(u"文件名走 X-Filename 头（解回来是原名）",
              bool(ups) and unquote(ups[0]["headers"].get("X-Filename") or "") == u"压缩包.json",
              str(ups[0]["headers"] if ups else {}))
        check(u"压缩体解出来就是原卡（内容没被改）",
              bool(ups) and json.loads(gzip.decompress(ups[0]["body"]).decode("utf-8")) == gz_pack)
        check(u"返回里标了 gzip 通道，且报的字节数就是实际发出的压缩体长度",
              res.get("ok") is True and res.get("gzip") is True and
              res.get("bytes") == ups[0]["body_len"], str(res))
        # ⚠ 这条是真机才会炸、mock 不炸的坑：requests 按 **latin-1** 编请求头，
        # 中文卡名直接塞 X-Filename 会抛 UnicodeEncodeError，整次上传当场失败。
        # 所以头里必须是纯 ASCII（百分号编码），服务端再解回原名。
        sent_name = (ups[0]["headers"].get("X-Filename") if ups else "") or ""
        check(u"X-Filename 是纯 ASCII（否则 requests 编头就抛 UnicodeEncodeError）",
              bool(sent_name) and sent_name.isascii(), repr(sent_name))
        check(u"这个 ASCII 头解回来仍是原名（服务端 _url_unquote 的解码契约）",
              unquote(sent_name) == u"压缩包.json", repr(sent_name))

        print(u"\n== ⑩ gzip：能力里没有 → 照旧 multipart（老服务器兼容） ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()

        def no_gz_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_OLD))
            if "/upload/gz" in url:
                return FakeResp(404, None, text="")     # 不该被调到
            if "/api/packs/upload" in url:
                return FakeResp(201, {"success": True})
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = no_gz_server
        res = app.api_workshop_upload(u"世界卡包", u"压缩包")
        ups = [x for x in calls if "/upload" in x["url"]]
        check(u"没有 gzip 能力位时走 multipart",
              len(ups) == 1 and ups[0]["url"].endswith("/api/packs/upload") and ups[0]["is_file"],
              str([(c["url"], c["is_file"]) for c in calls]))
        check(u"没去打 gz 接口", not any("/upload/gz" in c["url"] for c in calls))
        check(u"上传成功", res.get("ok") is True and res.get("gzip") is False, str(res))

        print(u"\n== ⑪ gz 接口不认（404/415）→ 自动回退 multipart ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()

        def gz_404_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_GZ))     # 能力说有，但接口其实没了
            if "/upload/gz" in url:
                return FakeResp(404, None, text="not found")
            if "/api/packs/upload" in url:
                return FakeResp(201, {"success": True})
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = gz_404_server
        res = app.api_workshop_upload(u"世界卡包", u"压缩包")
        ups = [x for x in calls if "/upload" in x["url"]]
        check(u"先撞 gz 接口、再自动回退 multipart",
              len(ups) == 2 and ups[0]["url"].endswith("/upload/gz")
              and ups[1]["url"].endswith("/api/packs/upload"), str([c["url"] for c in ups]))
        check(u"回退那次带的是完整文件（multipart）",
              len(ups) == 2 and ups[1]["is_file"] and ups[1]["body_len"] > 0, str(ups))
        check(u"回退后仍然算成功", res.get("ok") is True and res.get("gzip") is False, str(res))

        print(u"\n== ⑫ 下载：优先 /gz，服务端只回压缩体时也能自己解 ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()
        cloud = {"name": u"云端卡", "system_prompt": u"你是云端卡。"}
        cloud_raw = json.dumps(cloud, ensure_ascii=False, indent=2).encode("utf-8")

        def gz_download_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_GZ))
            if url.endswith("/gz"):
                # 服务端只回压缩体（这里**故意**不带 Content-Encoding：
                # 模拟中间的代理/隧道把头丢了 —— 客户端必须靠魔数自己认出来）
                return FakeResp(200, None, text="{}", content=gzip.compress(cloud_raw))
            return FakeResp(404, None, text="")

        routes[DIRECT_KEY] = gz_download_server
        res = app.api_workshop_download("cid-1", u"角色卡", u"云端卡.json")
        check(u"下载走 /gz 接口并成功落盘", res.get("ok") is True, str(res))
        saved = os.path.join(app.save_dir, res.get("file") or "")
        body = {}
        if os.path.isfile(saved):
            with io.open(saved, "r", encoding="utf-8") as f:
                body = json.load(f)
        check(u"落盘内容 = 服务端那份卡（压缩体已被解开）",
              body.get("name") == u"云端卡" and body.get("system_prompt") == u"你是云端卡。",
              str(body)[:120])
        check(u"下载结果标了 gzip 通道", res.get("gzip") is True, str(res))
        # requests 默认就会发 Accept-Encoding: gzip, deflate；**别有人后来把它硬写成 identity**，
        # 否则服务器那边的响应压缩永远不触发（这条是防回退的钉子）。
        check(u"客户端不覆写 Accept-Encoding（交给 requests 默认的 gzip）",
              all("Accept-Encoding" not in (c.get("headers") or {}) and
                  "accept-encoding" not in (c.get("headers") or {}) for c in calls),
              str([c.get("headers") for c in calls][:3]))

        print(u"\n== ⑬ 429 退避：按 Retry-After 等，最多 XFER_MAX_RETRY 次 ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()
        state = {"n": 0}

        def rate_limit_then_ok():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_GZ))
            state["n"] += 1
            if state["n"] == 1:
                return FakeResp(429, {"error": u"太频繁", "retry_after": 1},
                                headers={"Retry-After": "1"})
            return FakeResp(201, {"success": True})

        routes[DIRECT_KEY] = rate_limit_then_ok
        t0 = time.time()
        res = app.api_workshop_upload(u"世界卡包", u"压缩包")
        elapsed = time.time() - t0
        check(u"429 后重试成功", res.get("ok") is True, str(res))
        check(u"按 Retry-After 等够了（≥1 秒，不是只等 500ms 的闸门）",
              elapsed >= 1.0, "%.2fs" % elapsed)
        check(u"重试次数符合预期（2 次请求）",
              len([x for x in calls if "/upload" in x["url"]]) == 2,
              str([c["url"] for c in calls]))

        routes.clear()
        calls[:] = []
        app._ws_caps_cache = None

        def always_429():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_GZ))
            return FakeResp(429, {"error": u"太频繁", "retry_after": 0},
                            headers={"Retry-After": "0"})

        routes[DIRECT_KEY] = always_429
        res = app.api_workshop_upload(u"世界卡包", u"压缩包")
        tries = len([x for x in calls if "/upload" in x["url"]])
        check(u"一直 429 时按上限停手并如实报错",
              # 2026-12 文案清理：界面不再出现"限流/429"（用户口径：去掉技术说明），
              # 所以这里改成认"稍等一会儿"这句人话 —— 断言的意思没变（错了要说人话）。
              res.get("ok") is False and u"稍等" in (res.get("err") or ""), str(res))
        check(u"重试次数 = XFER_MAX_RETRY（%d）" % mod.XFER_MAX_RETRY,
              tries == mod.XFER_MAX_RETRY, str(tries))

        print(u"\n== ⑭ 传输闸门：串行 + 最小间隔（服务器下发优先，不是硬编码） ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()

        def slow_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, dict(CAPS_GZ))
            return FakeResp(201, {"success": True})

        routes[DIRECT_KEY] = slow_server
        t0 = time.time()
        for _i in range(3):
            app.api_workshop_upload(u"世界卡包", u"压缩包")
        took_500 = time.time() - t0
        check(u"服务器说 500ms → 连续 3 次至少 1.0 秒",
              took_500 >= 1.0, "%.2fs" % took_500)

        # 服务器把间隔调小（以后换 100MB/s 的水管就只改服务器环境变量）：
        # 客户端必须跟着放宽，而不是继续按写死的 500ms 慢慢磨。
        caps_fast = dict(CAPS_GZ)
        caps_fast["limits"] = {"upload_max_mb": 64, "min_interval_ms": 120, "max_concurrent": 1}
        app._ws_caps_cache = None
        calls[:] = []

        def fast_server():
            url = calls[-1]["url"]
            if "/api/capabilities" in url:
                return FakeResp(200, caps_fast)
            return FakeResp(201, {"success": True})

        routes[DIRECT_KEY] = fast_server
        t0 = time.time()
        for _i in range(3):
            app.api_workshop_upload(u"世界卡包", u"压缩包")
        took_120 = time.time() - t0
        check(u"服务器说 120ms → 3 次明显更快（说明用的是服务器的值）",
              took_120 < 1.0 and took_120 >= 0.24, "%.2fs" % took_120)
        check(u"本地常量仍是 500ms 的兜底默认", mod.XFER_MIN_INTERVAL_MS == 500,
              str(mod.XFER_MIN_INTERVAL_MS))

        print(u"\n== ⑮ 去历史：上传体里没有本地状态，卡面字段都在 ==")
        app._ws_proxy_ok = DIRECT_PROXY
        app._ws_caps_cache = None
        calls[:] = []
        routes.clear()
        routes[DIRECT_KEY] = lambda: FakeResp(201, {"success": True}) if "/upload" in calls[-1]["url"] \
            else FakeResp(200, dict(CAPS_GZ))
        dirty = {
            "name": u"咲", "system_prompt": u"你是咲。", "personality": u"安静",
            "greeting": u"……", "description": u"测", "tags": ["测试"], "params": {"k": 1},
            "history_tree": {"nodes": {"n1": {"content": u"私密对话"}}},
            "_tree_ts": "2026-10-18T00:00:00", "messages": [{"role": "user", "content": u"隐私"}],
            "memory": {"x": 1}, "state": {"mood": "calm"},
        }
        with io.open(os.path.join(app.pack_dir, u"咲.json"), "w", encoding="utf-8") as f:
            json.dump(dirty, f, ensure_ascii=False)
        res = app.api_workshop_upload(u"世界卡包", u"咲")
        ups = [x for x in calls if "/upload" in x["url"]]
        sent = json.loads(gzip.decompress(ups[0]["body"]).decode("utf-8")) if ups else {}
        check(u"上传体里没有 history_tree", "history_tree" not in sent, str(list(sent.keys())))
        check(u"也没有 _tree_ts / messages / memory / state",
              not any(k in sent for k in ("_tree_ts", "messages", "memory", "state")),
              str(list(sent.keys())))
        check(u"卡面字段一个都没少（system_prompt/personality/greeting/tags/params）",
              sent.get("system_prompt") == u"你是咲。" and sent.get("personality") == u"安静"
              and sent.get("greeting") == u"……" and sent.get("tags") == ["测试"]
              and sent.get("params") == {"k": 1}, str(sent)[:160])
        check(u"返回里报出剔掉了哪些键", bool(res.get("stripped")), str(res.get("stripped")))

        # ---------------- 两端协议对拍 ----------------
        print(u"\n== ⑯ 两端协议对拍：桌面 gzip 路径 vs 安卓协议（同一个真服务器） ==")
        net_tmp = tempfile.mkdtemp(prefix="dick_ws_parity_")
        try:
            net = load_net(net_tmp)
            client = net.app.test_client()
            parity_calls = []
            requests.request = flask_sender(client, parity_calls)
            app._ws_proxy_ok = DIRECT_PROXY
            app._ws_caps_cache = None

            card = {
                "name": u"对拍卡", "system_prompt": u"你是对拍卡。", "personality": u"稳",
                "greeting": u"你好", "description": u"两端协议要一致", "tags": ["对拍"],
                "params": {"city": u"江南"}, "entries": [{"keywords": [u"雨"], "content": u"下雨"}],
                "history_tree": {"nodes": {"n1": {"content": u"不该被上传"}}},
                "_tree_ts": "2026-10-18T00:00:00",
            }
            with io.open(os.path.join(app.pack_dir, u"对拍卡.json"), "w", encoding="utf-8") as f:
                json.dump(card, f, ensure_ascii=False)

            # ① 桌面：走真实客户端代码（能力协商 → 去历史 → gzip → /upload/gz）
            desk_res = app.api_workshop_upload(u"世界卡包", u"对拍卡")

            # ② 安卓：Workshop.kt 的 uploadGz 等价物 —— 同一份卡、同一套头、同一套 gz 体。
            #    剔键用的是**同一份名单**（下面还有一条结构断言盯着 Kotlin 那边的名单）。
            android_card, gone = mod.strip_local_state(card)
            android_body = gzip.compress(json.dumps(android_card, ensure_ascii=False,
                                                   indent=2).encode("utf-8"))
            # 安卓侧的头照 Kotlin 的做法编码（asciiHeaderName → URLEncoder）：
            # 这样"同一份数据 + 同一套头"才是真的对拍，而不是各发一种形状。
            android_fname = mod.ws_header_name(u"对拍卡.json")
            ar = client.post("/api/packs/upload/gz", data=android_body,
                             headers={"X-Filename": android_fname, "X-Author": "anonymous",
                                      "Content-Type": "application/json"},
                             content_type="application/json")
            android_res = ar.get_json() or {}
            desk_ups = [x for x in parity_calls if "/upload/gz" in x["url"]]
            check(u"两端发出去的 X-Filename 逐字节相同",
                  len(desk_ups) == 1 and
                  desk_ups[0]["headers"].get("X-Filename") == android_fname,
                  "%r vs %r" % (desk_ups[0]["headers"].get("X-Filename") if desk_ups else None,
                                android_fname))
            check(u"两端发的 gz 体解压后是同一份 JSON",
                  len(desk_ups) == 1 and
                  json.loads(gzip.decompress(desk_ups[0]["body"]).decode("utf-8")) == android_card,
                  "desktop body vs android card")

            check(u"桌面 gzip 上传落到真服务器（201）", desk_res.get("ok") is True, str(desk_res))
            check(u"安卓协议上传也 201", ar.status_code == 201, str(ar.status_code) + str(android_res))
            entries = client.get("/api/packs/list").get_json() or []
            check(u"服务器上是**两条**独立条目（新卡语义，不按内容去重）",
                  len(entries) == 2 and len({e["id"] for e in entries}) == 2, str(len(entries)))
            if len(entries) == 2:
                keys = ("name", "original_name", "author", "tags", "description")
                same = {k: (entries[0].get(k), entries[1].get(k)) for k in keys}
                check(u"两端的条目字段完全一致（name/original_name/author/tags/description）",
                      all(a == b for a, b in same.values()), str(same))
                check(u"两端的 original_name 都是 对拍卡.json",
                      entries[0].get("original_name") == entries[1].get("original_name") == u"对拍卡.json",
                      str([e.get("original_name") for e in entries]))
                check(u"两端的预览字段都提取到了 system_prompt",
                      all(e.get("system_prompt_preview") for e in entries),
                      str([e.get("system_prompt_preview") for e in entries]))
                # 落盘文件内容：两边都必须等于"去过历史的卡"，且**都没有** history_tree
                contents = []
                for e in entries:
                    p = os.path.join(net.PACKS_DIR, e["filename"])
                    with io.open(p, "r", encoding="utf-8") as f:
                        contents.append(json.load(f))
                check(u"两边落盘内容逐字节等价（JSON 语义相同）", contents[0] == contents[1],
                      str([sorted(c.keys()) for c in contents]))
                check(u"落盘内容里都没有 history_tree / _tree_ts",
                      all("history_tree" not in c and "_tree_ts" not in c for c in contents),
                      str([sorted(c.keys()) for c in contents]))
                check(u"落盘内容里卡面字段都在（entries/params/greeting）",
                      all(c.get("entries") and c.get("params") == {"city": u"江南"}
                          and c.get("greeting") == u"你好" for c in contents),
                      str([sorted(c.keys()) for c in contents]))
                # 下载方向也对拍：/gz 下来解压 == 普通下载的内容
                gz_dl = client.get("/api/packs/%s/gz" % entries[0]["id"])
                plain = client.get("/api/packs/%s" % entries[0]["id"])
                check(u"/gz 下载带 Content-Encoding: gzip",
                      gz_dl.headers.get("Content-Encoding") == "gzip",
                      str(dict(gz_dl.headers)))
                check(u"/gz 解出来与普通下载的内容一致",
                      json.loads(gzip.decompress(gz_dl.data).decode("utf-8")) ==
                      json.loads(plain.data.decode("utf-8")))
                plain.close()
            # Kotlin 那边的剔键名单必须和 Python 是同一份（文本级结构断言：
            # 名单散成两份、改一边忘另一边，正是这种"看着能跑、跨端不一致"的根源）
            kt = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com",
                              "dick", "core", "Workshop.kt")
            kt_text = ""
            if os.path.isfile(kt):
                with io.open(kt, "r", encoding="utf-8") as f:
                    kt_text = f.read()
            missing = [k for k in mod.LOCAL_STATE_KEYS if ('"%s"' % k) not in kt_text]
            check(u"安卓 Workshop.kt 的剔键名单与桌面一致（%d 个键）" % len(mod.LOCAL_STATE_KEYS),
                  os.path.isfile(kt) and not missing, str(missing))
        finally:
            shutil.rmtree(net_tmp, ignore_errors=True)
    finally:
        requests.request = real_request
        if real_getproxies is not None:
            import urllib.request as _ur2
            _ur2.getproxies = real_getproxies
        app_paths.get_base_dir = real_base
        mod.BASE_DIR = real_module_base
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("WORKSHOP_CLIENT_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
