# -*- coding: utf-8 -*-
"""hidden_proxy.py —— 内置隐藏本地按需隧道代理（零外泄、直连失败静默兜底）。

设计边界：
  1. 零暴露：不回显到设置 UI，不写入 config.json，不在日志/报错里打印节点地址、端口或凭据；
  2. 按需启动：程序启动时不建连、不占端口；仅当用户未手动配置代理且直连受阻目标失败时，
     才在 127.0.0.1:<随机端口> 拉起本地回环代理，并通过内嵌 SSH 隧道（direct-tcpip）转发；
  3. 仅放行目标：默认放行 OpenAI / Gemini / Claude / Pollinations / OVH 等外网模型与生图域名，
     以及调用方显式注册的非本机外网目标；严格拦截 localhost / 回环 / 内网私有 IP（防 SSRF、
     同时保证 Ollama / ComfyUI / SD-WebUI 绝不走隧道）；
  4. 空闲回收：默认空闲 600 秒自动断开 SSH 传输，下次请求时静默重连；退出时自动清理；
  5. 凭据来源（优先级从高到低，均不进入公开仓库）：
       a) 密封加密文件 hidden_proxy.enc（AES-256-GCM，已加入 .gitignore，可选随打包分发）；
       b) 环境变量 DICK_HIDDEN_PROXY（已有上行代理）或
          DICK_TUNNEL_HOST / DICK_TUNNEL_PORT / DICK_TUNNEL_USER / DICK_TUNNEL_PASS / DICK_TUNNEL_KEY
          （兼容旧变量 DICK_SRV_HOST / DICK_SRV_USER / DICK_SRV_PASS）。
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import io
import ipaddress
import json
import os
import socket
import threading
import time
from urllib.parse import urlsplit

# 内置放行的外部 AI / 生图 / 视觉域名（仅限这些 + 进程内显式登记的外网目标）
BUILTIN_ALLOWED_HOSTS = frozenset({
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "api.anthropic.com",
    "image.pollinations.ai",
    "gen.pollinations.ai",
    "text.pollinations.ai",
    "oai.endpoints.kepler.ai.cloud.ovh.net",
    "openrouter.ai",
    "api.x.ai",
    "api.groq.com",
    "api.together.xyz",
    "api.mistral.ai",
})

SEAL_FILENAME = "hidden_proxy.enc"
_SEAL_MAGIC = b"DKHP1"
_SEAL_SALT = b"dick.hidden_proxy.v1.seal"
_DEFAULT_SEAL_SECRET = "dick-builtin-tunnel-envelope-v1"
_DEFAULT_IDLE_SEC = 600


def _host_from_url(url_or_host: str) -> str:
    s = (url_or_host or "").strip()
    if not s:
        return ""
    if "://" in s:
        return (urlsplit(s).hostname or "").strip().lower().rstrip(".")
    # 裸 host 或 host:port
    if s.startswith("[") and "]" in s:
        return s[1:s.index("]")].strip().lower()
    if ":" in s and s.count(":") == 1:
        s = s.split(":", 1)[0]
    return s.strip().lower().rstrip(".")


def is_local_or_private(url_or_host: str) -> bool:
    """判断地址是否为本机回环或局域网私有地址：此类地址绝不经隧道转发。"""
    host = _host_from_url(url_or_host)
    if not host:
        return True
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return bool(
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        return False


def _derive_seal_key(secret: str = "") -> bytes:
    raw = (secret or os.environ.get("DICK_TUNNEL_SEAL_KEY") or _DEFAULT_SEAL_SECRET).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", raw, _SEAL_SALT, 120_000, dklen=32)


def seal_payload(cfg: dict, secret: str = "") -> bytes:
    """用 AES-256-GCM 密封隧道配置字典（落盘为不透明二进制，不含明文节点信息）。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = _derive_seal_key(secret)
    nonce = os.urandom(12)
    pt = json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = AESGCM(key).encrypt(nonce, pt, _SEAL_MAGIC)
    return _SEAL_MAGIC + nonce + ct


def unseal_payload(blob: bytes, secret: str = "") -> dict | None:
    """解封 hidden_proxy.enc；格式或密钥不对时静默返回 None。"""
    if not blob or len(blob) <= len(_SEAL_MAGIC) + 12 + 16:
        return None
    if not blob.startswith(_SEAL_MAGIC):
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _derive_seal_key(secret)
        nonce = blob[len(_SEAL_MAGIC):len(_SEAL_MAGIC) + 12]
        ct = blob[len(_SEAL_MAGIC) + 12:]
        pt = AESGCM(key).decrypt(nonce, ct, _SEAL_MAGIC)
        obj = json.loads(pt.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _seal_search_paths() -> list[str]:
    paths = []
    seen = set()

    def _add(d):
        if not d:
            return
        p = os.path.abspath(os.path.join(d, SEAL_FILENAME))
        if p not in seen:
            seen.add(p)
            paths.append(p)

    env_file = (os.environ.get("DICK_TUNNEL_FILE") or "").strip()
    if env_file:
        p = os.path.abspath(env_file)
        seen.add(p)
        paths.append(p)
    try:
        import app_paths
        _add(app_paths.get_base_dir())
        _add(app_paths.get_resource_dir())
    except Exception:
        pass
    _add(os.path.dirname(os.path.abspath(__file__)))
    return paths


def load_config(seal_path: str | None = None, secret: str = "") -> dict | None:
    """按优先级加载隐藏代理配置：密封文件 > 环境变量。任何错误静默返回 None。"""
    candidates = [seal_path] if seal_path else _seal_search_paths()
    for p in candidates:
        if p and os.path.isfile(p):
            try:
                with open(p, "rb") as f:
                    obj = unseal_payload(f.read(), secret=secret)
                if obj and _valid_cfg(obj):
                    return obj
            except Exception:
                pass

    # 环境变量：直接上行隐藏代理
    direct_proxy = (os.environ.get("DICK_HIDDEN_PROXY") or "").strip()
    if direct_proxy:
        return {"mode": "proxy", "proxy_url": direct_proxy}

    # 环境变量：SSH 隧道（兼容 tools/net_egress_proxy.py 的 DICK_SRV_*）
    host = (os.environ.get("DICK_TUNNEL_HOST") or os.environ.get("DICK_SRV_HOST") or "").strip()
    if host:
        port_s = (os.environ.get("DICK_TUNNEL_PORT") or "22").strip()
        try:
            port = int(port_s)
        except ValueError:
            port = 22
        user = (os.environ.get("DICK_TUNNEL_USER") or os.environ.get("DICK_SRV_USER") or "root").strip()
        pwd = os.environ.get("DICK_TUNNEL_PASS") or os.environ.get("DICK_SRV_PASS") or ""
        key_path = (os.environ.get("DICK_TUNNEL_KEY") or "").strip()
        pkey_pem = ""
        if key_path and os.path.isfile(key_path):
            try:
                with open(key_path, "r", encoding="utf-8", errors="ignore") as f:
                    pkey_pem = f.read()
            except Exception:
                pass
        cfg = {
            "mode": "ssh",
            "host": host,
            "port": port,
            "user": user,
            "password": pwd,
            "pkey_pem": pkey_pem,
            "passphrase": os.environ.get("DICK_TUNNEL_KEY_PASS") or "",
            "idle_sec": int(os.environ.get("DICK_TUNNEL_IDLE_SEC") or _DEFAULT_IDLE_SEC),
        }
        if _valid_cfg(cfg):
            return cfg
    return None


def _valid_cfg(cfg: dict) -> bool:
    if not isinstance(cfg, dict):
        return False
    mode = (cfg.get("mode") or "ssh").strip().lower()
    if mode == "proxy":
        return bool((cfg.get("proxy_url") or "").strip())
    if mode == "ssh":
        has_host = bool((cfg.get("host") or "").strip())
        has_auth = bool(cfg.get("password") or cfg.get("pkey_pem"))
        return has_host and has_auth
    return False


def _load_paramiko_key(pkey_pem: str, passphrase: str = ""):
    import paramiko
    pw = passphrase or None
    for cls_name in ("Ed25519Key", "RSAKey", "ECDSAKey"):
        cls = getattr(paramiko, cls_name, None)
        if cls is None:
            continue
        try:
            return cls.from_private_key(io.StringIO(pkey_pem), password=pw)
        except Exception:
            continue
    raise ValueError("unsupported private key")


def _pipe_half(src, dst, touch):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            touch()
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass


def _close_quiet(obj):
    if obj is None:
        return
    try:
        obj.close()
    except Exception:
        pass


class _SshDialer:
    """单连接可复用 SSH 隧道拨号器：懒连接、保活、断线自动重连、空闲自动关闭。"""

    def __init__(self, cfg: dict):
        self._cfg = dict(cfg)
        self._lock = threading.Lock()
        self._transport = None
        self._last_used = 0.0

    def _connect_locked(self):
        import paramiko
        if self._transport is not None:
            try:
                if self._transport.is_active():
                    return self._transport
            except Exception:
                pass
            _close_quiet(self._transport)
            self._transport = None

        host = str(self._cfg["host"]).strip()
        port = int(self._cfg.get("port") or 22)
        user = str(self._cfg.get("user") or "root").strip()
        sock = socket.create_connection((host, port), timeout=15)
        t = paramiko.Transport(sock)
        t.set_keepalive(30)
        pkey_pem = self._cfg.get("pkey_pem") or ""
        if pkey_pem:
            pkey = _load_paramiko_key(pkey_pem, self._cfg.get("passphrase") or "")
            t.connect(username=user, pkey=pkey)
        else:
            t.connect(username=user, password=str(self._cfg.get("password") or ""))
        self._transport = t
        self._last_used = time.monotonic()
        return t

    def dial(self, host: str, port: int, src_addr=("127.0.0.1", 0), timeout: float = 15.0):
        # 首选复用传输；若底层断线则重连一次
        last_err = None
        for _attempt in range(2):
            with self._lock:
                try:
                    t = self._connect_locked()
                except Exception as e:
                    last_err = e
                    _close_quiet(self._transport)
                    self._transport = None
                    continue
            try:
                chan = t.open_channel("direct-tcpip", (host, int(port)), src_addr, timeout=timeout)
                self._last_used = time.monotonic()
                return chan
            except Exception as e:
                last_err = e
                with self._lock:
                    if self._transport is t:
                        _close_quiet(self._transport)
                        self._transport = None
        raise OSError("tunnel dial failed") from last_err

    def close_if_idle(self, idle_sec: float):
        if idle_sec <= 0:
            return
        with self._lock:
            if self._transport is None:
                return
            if (time.monotonic() - self._last_used) >= idle_sec:
                _close_quiet(self._transport)
                self._transport = None

    def close(self):
        with self._lock:
            _close_quiet(self._transport)
            self._transport = None


class LocalTunnelProxy:
    """本地回环 HTTP/CONNECT 隧道代理（127.0.0.1:<随机端口>）。"""

    def __init__(self, dialer, idle_sec: float = _DEFAULT_IDLE_SEC,
                 allowed_hosts=None, block_private: bool = True):
        self._dialer = dialer
        self._idle_sec = float(idle_sec or _DEFAULT_IDLE_SEC)
        self._block_private = bool(block_private)
        self._allowed = set(BUILTIN_ALLOWED_HOSTS)
        if allowed_hosts:
            for h in allowed_hosts:
                nh = _host_from_url(h)
                if nh:
                    self._allowed.add(nh)
        self._lock = threading.Lock()
        self._srv = None
        self._port = 0
        self._running = False
        self._last_activity = 0.0

    @property
    def proxy_url(self) -> str:
        return f"http://127.0.0.1:{self._port}" if self._port else ""

    def allow_url(self, url_or_host: str) -> bool:
        """为本进程合法外网请求登记放行主机（严禁放行回环/私网地址）。"""
        host = _host_from_url(url_or_host)
        if not host:
            return False
        if self._block_private and is_local_or_private(host):
            return False
        with self._lock:
            self._allowed.add(host)
        return True

    def is_host_allowed(self, host: str) -> bool:
        h = _host_from_url(host)
        if not h:
            return False
        if self._block_private and is_local_or_private(h):
            return False
        with self._lock:
            if h in self._allowed:
                return True
            return any(h.endswith("." + a) for a in self._allowed)

    def start(self) -> str:
        with self._lock:
            if self._running and self._port:
                self._last_activity = time.monotonic()
                return self.proxy_url
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            srv.listen(64)
            srv.settimeout(1.0)
            self._srv = srv
            self._port = srv.getsockname()[1]
            self._running = True
            self._last_activity = time.monotonic()
            threading.Thread(target=self._accept_loop, daemon=True).start()
            return self.proxy_url

    def stop(self):
        with self._lock:
            self._running = False
            srv = self._srv
            self._srv = None
            self._port = 0
        _close_quiet(srv)
        if hasattr(self._dialer, "close"):
            try:
                self._dialer.close()
            except Exception:
                pass

    def _touch(self):
        self._last_activity = time.monotonic()

    def _accept_loop(self):
        while self._running:
            srv = self._srv
            if srv is None:
                break
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                if hasattr(self._dialer, "close_if_idle"):
                    self._dialer.close_if_idle(self._idle_sec)
                continue
            except OSError:
                break
            self._touch()
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _dial(self, host: str, port: int, src_addr):
        if callable(self._dialer):
            return self._dialer(host, port, src_addr)
        return self._dialer.dial(host, port, src_addr)

    def _handle_client(self, conn: socket.socket, addr):
        remote = None
        try:
            conn.settimeout(30.0)
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 65536:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            head_end = buf.find(b"\r\n\r\n")
            if head_end < 0:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            head_bytes = buf[:head_end]
            rest = buf[head_end + 4:]
            lines = head_bytes.split(b"\r\n")
            req_line = lines[0].decode("latin-1", "ignore").split()
            if len(req_line) < 3:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            method, target, proto = req_line[0].upper(), req_line[1], req_line[2]

            if method == "CONNECT":
                host, port = self._parse_authority(target, 443)
                if not host or not self.is_host_allowed(host):
                    conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                    return
                remote = self._dial(host, port, addr)
                conn.settimeout(None)
                conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                if rest:
                    remote.sendall(rest)
                self._relay_both(conn, remote)
                return

            # 普通 HTTP 代理请求（如 GET/POST http://host[:port]/path HTTP/1.1）
            sp = urlsplit(target)
            if sp.scheme.lower() != "http" or not sp.hostname:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return
            host = sp.hostname
            port = sp.port or 80
            if not self.is_host_allowed(host):
                conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                return
            path = sp.path or "/"
            if sp.query:
                path += "?" + sp.query
            out_lines = [f"{method} {path} {proto}".encode("latin-1")]
            has_host = False
            for raw_hdr in lines[1:]:
                low = raw_hdr.lower()
                if low.startswith((b"proxy-connection:", b"proxy-authorization:")):
                    continue
                if low.startswith(b"host:"):
                    has_host = True
                out_lines.append(raw_hdr)
            if not has_host:
                host_hdr = host if port == 80 else f"{host}:{port}"
                out_lines.append(f"Host: {host_hdr}".encode("latin-1"))
            forwarded = b"\r\n".join(out_lines) + b"\r\n\r\n" + rest
            remote = self._dial(host, port, addr)
            conn.settimeout(None)
            remote.sendall(forwarded)
            self._relay_both(conn, remote)
        except Exception:
            try:
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except Exception:
                pass
        finally:
            _close_quiet(remote)
            _close_quiet(conn)

    @staticmethod
    def _parse_authority(target: str, default_port: int):
        s = (target or "").strip()
        if s.startswith("[") and "]" in s:
            host = s[1:s.index("]")]
            tail = s[s.index("]") + 1:]
            port = int(tail[1:]) if tail.startswith(":") and tail[1:].isdigit() else default_port
            return host, port
        if ":" in s:
            host, _, p = s.rpartition(":")
            if p.isdigit():
                return host, int(p)
        return s, default_port

    def _relay_both(self, conn, remote):
        t1 = threading.Thread(target=_pipe_half, args=(conn, remote, self._touch), daemon=True)
        t2 = threading.Thread(target=_pipe_half, args=(remote, conn, self._touch), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()


# ================================================================ 进程级单例入口
_GLOBAL_LOCK = threading.Lock()
_GLOBAL_PROXY: LocalTunnelProxy | None = None
_GLOBAL_STATIC_URL: str = ""
_CONFIG_LOADED = False
_CACHED_CFG: dict | None = None


def reload_config():
    """清空缓存配置（测试或重新密封后调用）。"""
    global _GLOBAL_PROXY, _GLOBAL_STATIC_URL, _CONFIG_LOADED, _CACHED_CFG
    with _GLOBAL_LOCK:
        old = _GLOBAL_PROXY
        _GLOBAL_PROXY = None
        _GLOBAL_STATIC_URL = ""
        _CONFIG_LOADED = False
        _CACHED_CFG = None
    if old is not None:
        old.stop()


def _get_cfg_locked() -> dict | None:
    global _CONFIG_LOADED, _CACHED_CFG
    if not _CONFIG_LOADED:
        _CACHED_CFG = load_config()
        _CONFIG_LOADED = True
    return _CACHED_CFG


def is_configured() -> bool:
    """是否已配置隐藏隧道（不触发建连、不暴露任何节点细节）。"""
    with _GLOBAL_LOCK:
        return _get_cfg_locked() is not None


def ensure_proxy(for_url: str | None = None) -> str | None:
    """按需拉起隐藏本地代理，返回回环代理 URL（如 http://127.0.0.1:<port>）。

    - 本机/私网地址一律返回 None（绝不走隧道）；
    - 未配置隐藏节点时静默返回 None；
    - 首次调用时才绑定回环端口并准备按需 SSH 传输，绝不在应用启动时建连。
    """
    global _GLOBAL_PROXY, _GLOBAL_STATIC_URL
    if for_url and is_local_or_private(for_url):
        return None
    with _GLOBAL_LOCK:
        cfg = _get_cfg_locked()
        if not cfg:
            return None
        mode = (cfg.get("mode") or "ssh").strip().lower()
        if mode == "proxy":
            _GLOBAL_STATIC_URL = (cfg.get("proxy_url") or "").strip()
            return _GLOBAL_STATIC_URL or None
        if _GLOBAL_PROXY is None:
            dialer = _SshDialer(cfg)
            idle = float(cfg.get("idle_sec") or _DEFAULT_IDLE_SEC)
            _GLOBAL_PROXY = LocalTunnelProxy(dialer, idle_sec=idle)
        if for_url:
            _GLOBAL_PROXY.allow_url(for_url)
        try:
            return _GLOBAL_PROXY.start()
        except Exception:
            return None


def fallback_for_url(url: str) -> str:
    """生图/视觉模块的回调适配器：返回代理 URL 或空串。"""
    return ensure_proxy(url) or ""


def shutdown():
    """退出时关闭本地回环端口与 SSH 隧道。"""
    global _GLOBAL_PROXY
    with _GLOBAL_LOCK:
        p = _GLOBAL_PROXY
        _GLOBAL_PROXY = None
    if p is not None:
        p.stop()


atexit.register(shutdown)


# ================================================================ CLI：密封节点 & 自测
def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="DICK 内置隐藏代理密封与探测工具")
    ap.add_argument("--seal", action="store_true", help="加密密封隧道配置到 hidden_proxy.enc")
    ap.add_argument("--status", action="store_true", help="检查隐藏代理是否已配置（不输出节点信息）")
    ap.add_argument("--test", action="store_true", help="通过本地按需隧道探测 OpenAI/Gemini/Claude 连通性")
    ap.add_argument("--mode", choices=["ssh", "proxy"], default="ssh")
    ap.add_argument("--host", default="")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default="")
    ap.add_argument("--key-file", default="")
    ap.add_argument("--passphrase", default="")
    ap.add_argument("--proxy-url", default="")
    ap.add_argument("--idle-sec", type=int, default=_DEFAULT_IDLE_SEC)
    ap.add_argument("--out", default=SEAL_FILENAME)
    args = ap.parse_args(argv)

    if args.seal:
        if args.mode == "proxy":
            cfg = {"mode": "proxy", "proxy_url": args.proxy_url.strip()}
        else:
            pkey_pem = ""
            if args.key_file:
                with open(args.key_file, "r", encoding="utf-8") as f:
                    pkey_pem = f.read()
            cfg = {
                "mode": "ssh",
                "host": args.host.strip(),
                "port": int(args.port),
                "user": args.user.strip() or "root",
                "password": args.password,
                "pkey_pem": pkey_pem,
                "passphrase": args.passphrase,
                "idle_sec": int(args.idle_sec),
            }
        if not _valid_cfg(cfg):
            print("参数不完整：ssh 模式需要 --host 与 --password/--key-file；proxy 模式需要 --proxy-url")
            return 2
        blob = seal_payload(cfg)
        with open(args.out, "wb") as f:
            f.write(blob)
        print(f"已加密密封到 {args.out}（{len(blob)} 字节，已在 .gitignore 中忽略）")
        return 0

    if args.status:
        cfg = load_config()
        if not cfg:
            print("状态：未配置内置隐藏代理（直连模式）")
            return 1
        print(f"状态：已就绪（模式={cfg.get('mode', 'ssh')}，按需懒启动，节点信息已隐藏）")
        return 0

    if args.test:
        import requests
        probes = [
            ("OpenAI", "https://api.openai.com/v1/models"),
            ("Gemini", "https://generativelanguage.googleapis.com/v1beta/models"),
            ("Claude", "https://api.anthropic.com/v1/models"),
        ]
        ok_all = True
        for name, url in probes:
            px = ensure_proxy(url)
            if not px:
                print(f"  FAIL {name}: 未配置隐藏代理")
                ok_all = False
                continue
            t0 = time.monotonic()
            try:
                r = requests.get(url, proxies={"http": px, "https": px}, timeout=15)
                ms = int((time.monotonic() - t0) * 1000)
                print(f"  OK   {name}: HTTP {r.status_code}（{ms} ms，已连通）")
            except Exception as e:
                print(f"  FAIL {name}: {type(e).__name__}")
                ok_all = False
        shutdown()
        return 0 if ok_all else 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
