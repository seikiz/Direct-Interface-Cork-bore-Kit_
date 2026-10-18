# -*- coding: utf-8 -*-
"""modules/workshop/client.py —— 工坊客户端（块内实现，外部只能经 kernel.service 拿）

宿主端口（Port）
================
本块**不 import 壳层**：所有宿主能力由 `bind(host)` 注入。host 必须提供下面这些成员
（缺一个就是契约破裂，壳层改签名会在这里当场炸，而不是静默降级）：

    连接配置  _ws_load_config() / _ws_save_config(url, key, proxy) / _ws_active_server()
    传输      _ws_call(method, url, fallback=True, **kw) / _ws_url(path)
    能力表    _ws_caps() / _ws_has_gzip() / _ws_kind(rtype) / _ws_local_dir(rtype)
    节流      _ws_headers() / _ws_xfer_slot() / _ws_retry_after(resp) / _ws_gz_body(resp)
    文案      _ws_http_err(resp, what)
    上传前净身  ws_strip_local_state(raw_bytes) -> (bytes, 被剔掉的键名)
    文件名    ws_header_name(name) / _safe_name(name)
    界面      _reload_roles() / _reload_worlds()
    数据      save_dir / world_dir / pack_dir / plugin_manager

文件划分（ARCHITECTURE.md 九.1：单文件目标 ≤400 行）：
    client.py    连接配置 / 能力清单 / 列表 / 搜索 / 连通性  —— 只读
    transfer.py  上传 / 下载 / 点赞 / 删除 / 预览 / 导出 / 插件 / 打开目录 —— 动磁盘或动服务器
`WorkshopClient` 继承 `TransferMixin`，对外仍是**同一个服务、同一组方法**（接口没变）。

为什么端口现在这么宽：本批只迁「这 17 个接口的编排」，传输层（_ws_call 这一族）
第二批才搬进来 —— 那时端口会缩到 `{dirs, config, log}` 三样东西。
现在把话说清楚，比假装已经解耦干净要诚实。
"""

import os

from .transfer import TransferMixin

# 模块自己的重试上限兜底值；壳层 bind(ho<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌st, max_retry=…) 时以壳层为准
DEFAULT_MAX_RETRY = 3


class WorkshopClient(TransferMixin):
    """工坊面板的全部接口。所有方法都返回 dict（与搬家前完全一致），永不抛。"""

    def __init__(self, log=None):
        self.log = log
        self.host = None
        self.max_retry = DEFAULT_MAX_RETRY

    # ---------------------------------------------------------------- 绑定
    def bind(self, host, max_retry=None):
        """把宿主接进来（幂等：壳层每次取服务都调一次也没关系）"""
        self.host = host
        if max_retry:
            self.max_retry = int(max_retry)
        return self

    def _h(self):
        if self.host is None:
            raise RuntimeError("工坊模块还没绑定宿主（壳层没调 bind）")
        return self.host

    # ---------------------------------------------------------------- 连接配置
    def state(self):
        """给界面用的一屏状态：连接配置 + 本地已有的三种作品文件名"""
        h = self._h()
        cfg = h._ws_load_config()
        roles = [fn for fn in sorted(os.listdir(h.save_dir))
                 if not fn.startswith(".") and fn.endswith(".json")]
        worlds = [fn for fn in sorted(os.listdir(h.world_dir)) if fn.endswith(".json")]
        packs = [fn for fn in sorted(os.listdir(h.pack_dir)) if fn.endswith(".json")]
        active = ""
        try:
            active = h._ws_active_server()
        except Exception:
            pass
        return {"server_url": cfg.get("server_url", ""), "active_server": active,
                "has_key": bool(cfg.get("api_key")),
                "proxy": cfg.get("proxy", ""),
                "local_roles": roles, "local_worlds": worlds, "local_packs": packs}

    def save_conn(self, server_url, api_key, proxy=None):
        """存连接信息（api_key 的加密落盘在宿主实现里，模块不碰密钥）"""
        self._h()._ws_save_config(server_url or "", api_key or "", proxy or "")
        return {"ok": True}

    def detect_proxy(self):
        """自动检测本机代理：1) Windows 系统代理设置 2) 常见代理软件端口"""
        import socket
        found = []
        # 1) Windows 系统代理（IE/系统设置里开的代理）
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            winreg.CloseKey(key)
            if enable and server:
                srv = str(server).strip()
                # 可能形如 "127.0.0.1:7890" 或 "http=127.0.0.1:7890;https=..."; 取第一个
                if "=" in srv:
                    srv = srv.split(";")[0].split("=", 1)[1].strip()
                if srv and "://" not in srv:
                    srv = "http://" + srv
                found.append(("系统代理", srv))
        except Exception:
            pass
        # 2) 常见代理软件本地端口探测
        common_ports = [7890, 7891, 10809, 10808, 1080, 8888, 1087, 8080, 20171, 9910]
        for port in common_ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.25)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    found.append((f"本地端口 :{port}", f"http://127.0.0.1:{port}"))
                s.close()
            except Exception:
                pass
        # 去重（同一地址只保留一次）
        seen = set()
        result = []
        for label, url in found:
            if url not in seen:
                seen.add(url)
                result.append({"label": label, "url": url})
        return {"ok": True, "found": result}

    # ---------------------------------------------------------------- 连通性
    def test(self):
        """连通性自检：/api/health + /api/stats（拿得到就多给一份统计）"""
        try:
            h = self._h()
            r = h._ws_call("GET", h._ws_url("/api/health"), timeout=6)
            if r.status_code >= 400:
                print("[工坊] 检测失败：HTTP %s" % r.status_code)
                return {"ok": False, "err": "没连上，稍后再试一次"}
            try:
                health = r.json() if isinstance(r.json(), dict) else {}
            except Exception:
                health = {}
            stats = {}
            try:
                sr = h._ws_call("GET", h._ws_url("/api/stats"), timeout=6)
                if sr.status_code < 400:
                    stats = sr.json()
            except Exception:
                pass
            return {"ok": True, "health": health, "stats": stats}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    # ---------------------------------------------------------------- 列表/搜索
    def list_items(self):
        """列出在线作品。角色卡/世界卡是基础能力（老服务器也有）；
        世界卡包要看服务器能力清单，老服务器没有就别去问（否则整页报错）。"""
        try:
            h = self._h()
            caps = h._ws_caps()
            types = list(caps.get("types") or [])
            out = {"ok": True, "types": types, "server_old": bool(caps.get("old"))}
            for name in ("cards", "worlds", "packs"):
                if name == "packs" and "packs" not in types:
                    continue    # 老服务器没有这种资源，问了只会 404
                r = h._ws_call("GET", h._ws_url("/api/%s/list" % name), timeout=8)
                if r.status_code >= 400:
                    # 基础类型失败才算真失败；新增类型失败只是"这台服务器没开"
                    if name != "packs":
                        print("[工坊] 列表失败（%s）：HTTP %s" % (name, r.status_code))
                        return {"ok": False, "err": "作品列表没拉到，稍后再试一次"}
                    out[name] = []
                    continue
                out[name] = r.json()
            return out
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def search(self, query, rtype):
        try:
            h = self._h()
            params = {}
            if query:
                params["q"] = query
            if rtype:
                params["type"] = rtype
            r = h._ws_call("GET", h._ws_url("/api/search"), params=params, timeout=8)
            if r.status_code >= 400:
                print("[工坊] 搜索失败：HTTP %s" % r.status_code)
                return {"ok": False, "err": "没搜到，稍后再试一次"}
            return {"ok": True, "results": r.json()}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}
