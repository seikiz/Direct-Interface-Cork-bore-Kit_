# -*- coding: utf-8 -*-
"""壳层 · 工坊同步（从 Kit.py 拆出来的第一块）。

这个文件只装一类东西：**和工坊服务器打交道的方法**（拉取/上传/保存/推送/进度）。
以前它们散在 7292 行的 `HtmlApp` 里，找一处逻辑要滚十屏；现在一个文件看全。

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`。
mixin 只搬代码位置、不动调用点 —— `self._ws_pull()` 照旧能用（MRO 里能查到）。
想要真正的解耦是下一步（把这些方法改成只吃 `(self.host, self.core)`），
但那要动调用点，先保证"搬家不换锁"。"""
from __future__ import annotations

from shell_util import BASE_DIR, DEFAULT_WS_SERVER, XFER_MIN_INTERVAL_MS, tree_ts_of

import json
import net
import os
import save_guard
import secret_store
import threading

class WsXferSlot(object):
    """工坊传输闸门（上下文管理器）：**串行 + 最小间隔**。

        with self._ws_xfer_slot():
            ...真正发请求...

    锁在**整个传输期间**持有，所以并发的第二次调用会先等前一个彻底结束，
    再等到间隔满 —— 这才是"不许并发突发"。只在开始前 sleep 而不占锁，
    等于放任两条传输同时在飞，500ms 的间隔就白设了。
    """

    def __init__(self, app):
        self.app = app
        self.lock = None

    def __enter__(self):
        import time as _t
        lock = getattr(self.app, "_ws_xfer_lock", None)
        if lock is None:
            lock = threading.Lock()
            self.app._ws_xfer_lock = lock
        self.lock = lock
        lock.acquire()
        try:
            gap = self.app._ws_min_interval_ms() / 1000.0
            wait = gap - (_t.time() - getattr(self.app, "_ws_xfer_last", 0.0))
            if wait > 0:
                _t.sleep(wait)            # 还没到下一次的窗口，就等着
            self.app._ws_xfer_last = _t.time()
        except BaseException:
            lock.release()
            raise
        return self

    def __exit__(self, *exc):
        if self.lock is not None:
            self.lock.release()
        return False


class WsMixin:
    """工坊相关方法集合（供 HtmlApp 继承）。"""

    def _ws_module_down(self, err):
        """工坊模块没起来时的降级返回（界面读到 ok=False 就显示一句人话）"""
        print("[工坊] 模块不可用：%s" % str(err)[:160])
        return {"ok": False, "err": "工坊模块没加载起来，稍后再试一次"}

    def _ws_config_file(self):
        # 用实例上的 base_dir（测试与打包版都会重定向它）；没有就退回模块默认
        base = getattr(self, "base_dir", None) or BASE_DIR
        return os.path.join(base, "workshop_config.json")


    def _ws_save_config(self, server_url, api_key, proxy=None):
        # api_key 加密落盘<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（工坊连接串属敏感信息）
        enc = secret_store.encrypt((api_key or "").strip())
        save_guard.atomic_write_json(self._ws_config_file(),
                                     {"server_url": (server_url or "").strip(),
                                      "api_key": enc,
                                      "proxy": (proxy or "").strip()})


    def _ws_load_config(self):
        """读取工坊连接配置；api_key 是密文则解密。返回 dict。"""
        cfg = {}
        try:
            with open(self._ws_config_file(), "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return cfg
        if isinstance(cfg, dict) and cfg.get("api_key"):
            d = secret_store.decrypt(str(cfg["api_key"]))
            cfg["api_key"] = d if d is not None else ""
        return cfg


    def _ws_headers(self):
        key = (self._ws_load_config().get("api_key") or "").strip()
        return {"X-API-Key": key} if key else {}


    def _ws_system_proxy(self):
        """系统/环境里配的代理（requests 默认会悄悄用上的那个）；没有则 None"""
        try:
            from urllib.request import getproxies
            p = getproxies() or {}
        except Exception:
            p = {}
        url = (p.get("https") or p.get("http") or "").strip()
        return url or None


    def _ws_proxy_candidates(self):
        """工坊请求的通道候选（按优先级）：
        ① 工坊设置里手填的代理 —— 填了只走它，不替用户猜；
        ② 直连 —— 公网工坊服务器可直连；而系统代理常把稍大的请求体截断
           （实测：走 Clash 127.0.0.1:7890 传 1.3KB 包体得到 502，同一份文件直连 201）；
        ③ 系统代理 —— 直连不通时的退路，给"只有代理能出网"的网络留活路。"""
        proxy = (self._ws_load_config().get("proxy") or "").strip()
        if proxy:
            if "://" not in proxy:
                proxy = "http://" + proxy
            return [{"http": proxy, "https": proxy}]
        cands = [{"http": "", "https": ""}]
        sysp = self._ws_system_proxy()
        if sysp:
            cands.append({"http": sysp, "https": sysp})
        return cands


    def _ws_proxies(self):
        """当前优先通道（返回 requests 代理字典；保留给不重试的老调用点）"""
        ok = getattr(self, "_ws_proxy_ok", None)
        if ok is not None:
            return ok
        cands = self._ws_proxy_candidates()
        return cands[0] if cands else None


    def _ws_call(self, method, url, fallback=True, **kw):
        """带通道回退的工坊请求：一条路被掐断或吃 5xx 就换下一条，并记住走通的那条。
        返回 requests.Response；所有通道都失败才抛异常。
        fallback=False 用于极短超时的探测，不额外耗时。"""
        import requests
        cands = self._ws_proxy_candidates() if fallback else [self._ws_proxies()]
        ok = getattr(self, "_ws_proxy_ok", None)
        if ok is not None:
            cands = [ok] + [c for c in cands if c != ok]
        if "://127.0.0.1" in url or "://localhost" in url:
            cands = [{"http": "", "https": ""}]     # 本机服务器永远直连，别绕代理（放最后，压过缓存）
        kw.setdefault("headers", self._ws_headers())
        last = None
        for i, prox in enumerate(cands):
            try:
                r = requests.request(method, url, proxies=prox, **kw)
            except Exception as e:
                last = e
                continue
            # 5xx 多半是代理把请求体弄坏了；还有别的通道就换一条再试
            if r.status_code >= 500 and i + 1 < len(cands):
                last = RuntimeError("HTTP " + str(r.status_code))
                continue
            self._ws_proxy_ok = prox
            return r
        raise last if isinstance(last, Exception) else RuntimeError(str(last))


    def _ws_url(self, path):
        base = self._ws_active_server()
        return base + path

    # 工坊资源类型表：中文名 →（接口段名，本地目录键，图标）
    # 服务器那边同样是一张注册表（net.py 的 TYPES），加类型两边各加一行即可。
    WS_KINDS = {
        "角色卡": ("cards", "saves", "🎭"),
        "世界卡": ("worlds", "worlds", "🌍"),
        "世界卡包": ("packs", "packs", "📦"),
    }


    def _ws_kind(self, rtype):
        """把界面上的中文类型名翻成（接口段名，本地目录键，图标），不认得就按世界卡处理"""
        return self.WS_KINDS.get(str(rtype or "").strip(), self.WS_KINDS["世界卡"])


    def _ws_local_dir(self, rtype):
        api, folder, _icon = self._ws_kind(rtype)
        dirs = {"saves": self.save_dir, "worlds": self.world_dir, "packs": self.pack_dir}
        return dirs.get(folder, self.world_dir)


    def _ws_caps(self):
        """服务器能力清单（带缓存）。老服务器没有 /api/capabilities → 退回基础能力，
        这样"新客户端连老服务器"和"老客户端连新服务器"都还能用。

        types 的两种形状都要认：纯名字列表（现在的契约）和对象数组
        （早期版本把 {"name":...,"label":...} 塞进 types；只按字符串读会把
        "世界卡包"永远判成不存在）。"""
        import time as _t
        cached = getattr(self, "_ws_caps_cache", None)
        if cached and _t.time() - cached[1] < 300:
            return cached[0]
        base = {"types": ["cards", "worlds", "plugins"], "features": [], "schema": 0,
                "old": True, "limits": {}}
        try:
            r = self._ws_call("GET", self._ws_url("/api/capabilities"), timeout=6)
            if r.status_code < 400:
                d = r.json() or {}
                names = []
                for t in (d.get("types") or []):
                    if isinstance(t, dict):
                        t = t.get("name") or t.get("type") or ""
                    t = str(t or "").strip().lower()
                    if t:
                        names.append(t)
                if not names:      # 只给了 registry 的老实现
                    for t in (d.get("registry") or []):
                        n = str((t or {}).get("name") or "").strip().lower()
                        if n:
                            names.append(n)
                if names:
                    base = {"types": names,
                            "features": [str(f) for f in (d.get("features") or [])],
                            "schema": d.get("schema") or 0, "old": False,
                            # 服务器下发的节奏（min_interval_ms / max_concurrent / rate_*）
                            "limits": dict(d.get("limits") or {})}
        except Exception:
            pass
        self._ws_caps_cache = (base, _t.time())
        return base


    def _ws_has_gzip(self):
        """服务器支持 gzip 传输通道吗？（有就走压缩上传/下载，没有就退回 multipart）"""
        try:
            feats = [str(f).strip().lower() for f in (self._ws_caps().get("features") or [])]
            return "gzip" in feats
        except Exception:
            return False


    def _ws_min_interval_ms(self):
        """两次传输的最小间隔（毫秒）：**优先用服务器下发的值**，读不到回落本地常量。

        这样"后期换成 100MB/s 的水管"只改服务器 WORKSHOP_MIN_INTERVAL_MS，
        两端客户端都不用重新发版。服务器给了离谱的值（负数/超大）就当没给。
        """
        try:
            v = int((self._ws_caps().get("limits") or {}).get("min_interval_ms") or 0)
            if 0 < v <= 60000:
                return v
        except Exception:
            pass
        return XFER_MIN_INTERVAL_MS


    def _ws_xfer_slot(self):
        """占用一次传输窗口（串行 + 最小间隔）。用法：with self._ws_xfer_slot(): ..."""
        return WsXferSlot(self)


    def _ws_retry_after(self, r):
        """从 429 响应里取 Retry-After（秒）。取不到就按最小间隔来一次。"""
        try:
            return max(XFER_MIN_INTERVAL_MS / 1000.0,
                       float(str(r.headers.get("Retry-After") or "").strip()))
        except Exception:
            pass
        try:
            return max(XFER_MIN_INTERVAL_MS / 1000.0,
                       float((r.json() or {}).get("retry_after") or 0))
        except Exception:
            return XFER_MIN_INTERVAL_MS / 1000.0


    def _ws_gz_body(self, r):
        """把响应体按"可能被压缩过"处理。

        requests 遇到 Content-Encoding: gzip 会**自动解**，所以多数时候这里原样返回；
        但两种情况要自己解：
          · 服务端只回了压缩体、中间的代理/隧道把 Content-Encoding 头丢了；
          · 响应是我们自己拼的（测试/离线）。
        判据用 gzip 魔数 1f 8b —— 比信任头可靠（JSON 文本不可能以这两个字节开头）。
        """
        data = r.content or b""
        if len(data) > 2 and data[0] == 0x1F and data[1] == 0x8B:
            try:
                import gzip as _gz
                return _gz.decompress(data)
            except Exception:
                return data          # 解不开就原样给（让上层按坏 JSON 报错，别吞）
        return data


    def _ws_active_server(self):
        """自动部署：返回当前可用的工坊服务器地址。
        优先使用配置的 server_url；未配置或不可用时自动探测
        ① 本机服务器 ② 默认隧道地址。结果缓存 30 秒避免每次请求都探测。"""
        import time as _t
        cfg_url = (self._ws_load_config().get("server_url") or "").strip().rstrip("/")
        now = _t.time()
        # 缓存有效期内直接返回
        cached = getattr(self, "_ws_active_cache", None)
        if cached and now - cached[1] < 30:
            return cached[0]
        candidates = []
        # 优先使用配置的稳定公网地址（命名隧道 https://<id>.cfargotunnel.com，用户填 server_url）
        if cfg_url:
            candidates.append(cfg_url)
        # 其次本机服务器（局域网直连，最快最稳）
        candidates.append("http://127.0.0.1:5000")
        # 最后是**内置默认服务器**：用户不必填 IP（界面上那栏已删），
        # 与安卓端 Workshop.DEFAULT_PUBLIC_URL 同一个地址。
        if DEFAULT_WS_SERVER:
            candidates.append(DEFAULT_WS_SERVER)
        # 不再硬编码易变的 trycloudflare 临时地址，避免连到失效的旧隧道。
        # 公网访问统一走 server_url（稳定地址）或上面的默认地址。
        import requests as _req
        for base in candidates:
            try:
                r = self._ws_call("GET", base + "/api/health", timeout=2.5)
                if r.status_code < 400:
                    self._ws_active_cache = (base, now)
                    return base
            except Exception:
                continue
        # 全部失败：退回配置地址（后续请求会报错并提示）
        self._ws_active_cache = (cfg_url or candidates[1], now)
        return cfg_url or candidates[1]

    # ---------- 树存档同步（复用工坊服务器，聊天进度互通） ----------

    # ---------- 树存档同步（复用工坊服务器，聊天进度互通） ----------
    def _ws_sync_enabled(self):
        """进度同步开关：
        ① 显式配置了工坊 server_url → 同步（远程/云端）；
        ② 未配置但本机 net.py 服务器在线（局域网直连）→ 同步到本机服务器，手机同网连它。
        本机探测用极短超时，避免每次保存卡顿。"""
        if (self._ws_load_config().get("server_url") or "").strip():
            return True
        try:
            import requests as _req
            r = self._ws_call("GET", "http://127.0.0.1:5000/api/health", timeout=0.6,
                              fallback=False)
            return r.status_code < 400
        except Exception:
            return False


    def _ws_save_upload(self, card_id, tree_data):
        """把某角色的聊天树推送到工坊服务器（后来者胜）。返回 (ok, ts)。"""
        try:
            import requests as _req
            url = self._ws_url("/api/save/" + str(card_id))
            r = self._ws_call("POST", url, json={"tree": tree_data}, timeout=6)
            if r.status_code < 400:
                return True, (r.json() or {}).get("ts", "")
        except Exception as e:
            print(f"[树存档同步] 推送失败: {e}")
        return False, ""


    def _ws_save_upload_async(self, card_id, tree_data):
        """后台线程推送（不阻塞保存）。"""
        if not self._ws_sync_enabled():
            return
        threading.Thread(target=self._ws_save_upload, args=(card_id, tree_data), daemon=True).start()


    def _ws_save_fetch(self, card_id):
        """从工坊服务器拉取某角色最新的聊天树。返回 {"ts":..., "tree":...} 或 None。"""
        try:
            import requests as _req
            url = self._ws_url("/api/save/" + str(card_id))
            r = self._ws_call("GET", url, timeout=6)
            if r.status_code < 400:
                d = r.json() or {}
                if isinstance(d.get("tree"), dict):
                    return d
        except Exception as e:
            print(f"[树存档同步] 拉取失败: {e}")
        return None


    def _ws_pull_tree(self, role_name):
        """拉取服务器上该角色最新的聊天树；若比本地新则替换本地存档（实现跨设备续聊）。
        返回 True 表示采用了服务器版本。"""
        # 跑团会期锁定：被锁卡的记忆树绝不被服务器版本覆盖（避免导入/续聊与跑团混淆）
        if role_name in self._trpg_locked_names():
            return False
        fetched = self._ws_save_fetch(role_name)
        if not fetched:
            return False
        server_ts = str(fetched.get("ts") or "")
        server_tree = fetched.get("tree")
        if not server_ts or not isinstance(server_tree, dict):
            return False
        for r in self.roles:
            if r["name"] == role_name:
                data = dict(r.get("data") or {})
                # 进度时间戳：本机那份可能是安卓端写的（键名 tree_ts），两种都要认，
                # 否则"本地有更新"看不出来 → 被更旧的服务器版本盖掉。
                local_ts = tree_ts_of(data)
                if server_ts <= local_ts:
                    return False
                data["history_tree"] = server_tree
                data["_tree_ts"] = server_ts
                r["data"] = data
                # 同时写回本地文件，避免下次又拉
                try:
                    out = dict(data)
                    out["name"] = r["name"]
                    out["system_prompt"] = r["prompt"]
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), out)
                except Exception:
                    pass
                return True
        return False

    # ---------- 同步设置（API 码等） ----------

    # ---------- 同步设置（API 码等） ----------
    def _ws_push_api(self):
        """把当前模型连接配置（API 码/端点/模型）推送到工坊服务器（后台线程）。"""
        if not self._ws_sync_enabled():
            return
        payload = {
            "api_key": (self.config.get("api_key") or "").strip(),
            "base_url": (self.config.get("base_url") or "").strip(),
            "model": (self.config.get("model") or "").strip(),
            "provider": (self.config.get("provider") or "deepseek").strip(),
        }
        if not payload["api_key"]:
            return   # 本地还没填 Key，不覆盖服务器已有配置
        threading.Thread(target=self._ws_push_api_sync, args=(payload,), daemon=True).start()


    def _ws_push_api_sync(self, payload):
        try:
            import requests as _req
            r = self._ws_call("POST", self._ws_url("/api/sync/api"), json=payload, timeout=6)
            if r.status_code >= 400:
                print(f"[API 同步] 推送失败 HTTP {r.status_code}")
        except Exception as e:
            print(f"[API 同步] 推送失败: {e}")


    def _ws_pull_api(self):
        """拉取共享的模型连接配置；若服务器有 Key 且与本地不同则应用（后来者胜）。"""
        if not self._ws_sync_enabled():
            return False
        try:
            import requests as _req
            r = self._ws_call("GET", self._ws_url("/api/sync/api"), timeout=6)
            if r.status_code >= 400:
                return False
            d = r.json() or {}
            key = (d.get("api_key") or "").strip()
            if not key:
                return False
            # 应用服务器共享的连接配置（覆盖本地）
            self.config["api_key"] = key
            pid = (d.get("provider") or self.config.get("provider") or "deepseek").strip()
            self.config["provider"] = pid
            self.provider_id = pid
            self.api_keys[pid] = key
            self.config["api_keys"] = self.api_keys
            if d.get("base_url"):
                self.config["base_url"] = d["base_url"].strip()
                self.core.set_base_url(self.config["base_url"])
            if d.get("model"):
                self.config["model"] = d["model"].strip()
                self.core.set_model(self.config["model"])
            self.core.set_api_key(key if key else "free")
            if self.config.get("proxy"):
                self.core.set_proxy(self.config["proxy"])
            self.core.set_stop_sequences(self._effective_stop())
            self._save_config()
            print("[API 同步] 已应用服务器共享的模型连接配置")
            return True
        except Exception as e:
            print(f"[API 同步] 拉取失败: {e}")
            return False


    def _ws_http_err(self, r, what="操作"):
        """把工坊的 4xx/5xx 翻成**人话**（2026-12 文案清理）。

        用户原话：「去掉应用内所有技术说明部分，用户不需要看到这些」。
        原来这里直接把状态码和服务端原文拼进界面（"HTTP 401：服务器要求 Key" /
        "HTTP 500：<服务端 traceback 片段>"）。现在状态码与原文只进 stderr 日志
        （开发者排查用），返回给界面的只有一句能照着做的话。
        """
        detail = (r.text or "")[:140].replace("\n", " ").strip()
        print("[工坊] %s失败：HTTP %s %s" % (what, r.status_code, detail))
        if r.status_code in (401, 403):
            has_key = bool(self._ws_headers().get("X-API-Key"))
            return {"ok": False,
                    "err": "没连上，检查一下 Key 再%s%s"
                           % (what, "" if has_key else "（当前没填）")}
        return {"ok": False, "err": "%s没成功，稍后再试一次" % what}

