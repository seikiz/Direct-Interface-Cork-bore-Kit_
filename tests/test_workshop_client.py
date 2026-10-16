# -*- coding: utf-8 -*-
"""创意工坊**客户端**行为测试（桌面端）：通道回退 / 类型映射 / 能力协商。

为什么单独一个文件
-----------------
线上实测抓到一个很难查的故障：同一个 1.4KB 的世界卡，走系统代理（Clash
127.0.0.1:7890）上传得到 **502 空响应**，直连同一份文件 **201**——代理把稍大的
请求体截断了。而客户端原来 `_ws_proxies()` 没配代理时返回 None，等于"让 requests
自己用系统代理"，于是**只要用户开了代理软件，工坊上传就必坏**。

所以这里钉住三件事：
  ① 通道顺序：手填代理 > 直连 > 系统代理（直连优先，本机地址永远直连）
  ② 换通道重试：一条路吃 5xx / 抛异常就换下一条，并把走通的那条记住；
     重试必须能**重发完整请求体**（上传时文件句柄已到末尾，不能读到空）
  ③ 类型映射与能力协商：世界卡包（packs）只在新服务器上问，老服务器不去问（否则整页报错）

跑法：python tests\\test_workshop_client.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

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


class FakeResp(object):
    def __init__(self, code, payload=None, text="", content=b""):
        self.status_code = code
        self._payload = payload
        self.text = text or json.dumps(payload or {}, ensure_ascii=False)
        self.content = content or self.text.encode("utf-8")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def proxy_key(proxies):
    if not proxies:
        return "<none>"
    return (proxies.get("http") or "") + "|" + (proxies.get("https") or "")


DIRECT_KEY = "|"


def main():
    print("=" * 62)
    print(u"创意工坊客户端：通道回退 / 类型映射 / 能力协商")
    print("=" * 62)

    import app_paths
    import requests

    mod = load_app_module()
    tmp = tempfile.mkdtemp(prefix="dick_ws_client_")
    real_base = app_paths.get_base_dir
    calls = []          # 每次请求的 (方法, URL, 通道, 请求体字节数/内容)
    routes = {}         # 通道 → 该通道的行为

    real_request = requests.request
    real_getproxies = None
    real_module_base = mod.BASE_DIR
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
            calls.append({"method": method, "url": url, "chan": key,
                          "body_len": len(body), "json": kw.get("json")})
            act = routes.get(key)
            if act is None:
                return FakeResp(200, {"ok": True})
            if isinstance(act, Exception):
                raise act
            return act()

        requests.request = fake_request
        from urllib.request import getproxies as _gp
        real_getproxies = _gp
        # 让"系统代理"在测试里可见：urllib.request.g<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌etproxies 被 _ws_system_proxy 调用
        import urllib.request as _ur
        _ur.getproxies = lambda: {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

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
        calls[:] = []
        routes.clear()
        routes[DIRECT_KEY] = lambda: FakeResp(502, None, text="")           # 代理坏掉那种空 502
        routes["http://127.0.0.1:7890|http://127.0.0.1:7890"] = \
            lambda: FakeResp(201, {"success": True, "message": u"上传成功"})
        pack = {"name": u"现代都市·合租", "description": u"合租", "rules": [u"通勤是硬成本"]}
        with io.open(os.path.join(app.pack_dir, u"现代都市·合租.json"), "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
        res = app.api_workshop_upload(u"世界卡包", u"现代都市·合租")
        check(u"世界卡包走 /api/packs/upload", any("/api/packs/upload" in c["url"] for c in calls),
              str([c["url"] for c in calls]))
        check(u"上传成功（内部换过通道）", res.get("ok") is True, str(res))
        check(u"重试那一次带的是完整包体（不是空文件）",
              len(calls) == 2 and calls[1]["body_len"] > 0 and
              calls[1]["body_len"] == calls[0]["body_len"], str(calls))

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
    finally:
        requests.request = real_request
        if real_getproxies is not None:
            import urllib.request as _ur
            _ur.getproxies = real_getproxies
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
