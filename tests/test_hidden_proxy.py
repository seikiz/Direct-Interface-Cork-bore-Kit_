# -*- coding: utf-8 -*-
"""tests/test_hidden_proxy.py —— 内置隐藏本地按需隧道代理端到端测试。

覆盖：
  1. AES-256-GCM 密封/解封（密文不含明文凭据，篡改/错密钥安全失败）与多源加载优先级；
  2. 回环/私网地址阻断（防 SSRF + 保证 Ollama/SD/ComfyUI 绝不走隧道）；
  3. LocalTunnelProxy 真实 TCP 转发（HTTPS CONNECT + 普通 HTTP 转发 + 白名单 403 拦截）；
  4. core_fetch.ChatCore 直连失败静默切隐藏隧道（零暴露：不改 proxy/relay_on，不进 config）；
  5. modules/image_gen Net 动态代理缓存与 Gemini/GPT 生图网络失败静默兜底；
  6. shell_host 视觉接口（Claude 原生 /messages + OpenAI/Gemini 模型适配 + 隐藏隧道兜底）；
  7. shell_api_media.api_test_and_save_key（Claude 鉴权头 + 隐藏隧道静默兜底 + 返回体零泄漏）。
"""
import base64
import http.server
import io
import json
import os
import socket
import socketserver
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hidden_proxy


class TestSealAndConfig(unittest.TestCase):
    def test_seal_roundtrip_and_opaque(self):
        cfg = {
            "mode": "ssh",
            "host": "203.0.113.42",
            "port": 2222,
            "user": "tunnel_u",
            "password": "super-secret-password-999",
            "idle_sec": 300,
        }
        blob = hidden_proxy.seal_payload(cfg)
        self.assertTrue(blob.startswith(b"DKHP1"))
        # 密文中绝不能出现明文主机、用户名或密码
        self.assertNotIn(b"203.0.113.42", blob)
        self.assertNotIn(b"tunnel_u", blob)
        self.assertNotIn(b"super-secret-password-999", blob)

        out = hidden_proxy.unseal_payload(blob)
        self.assertEqual(out, cfg)
        # 错密钥 / 篡改密文 → 安全返回 None
        self.assertIsNone(hidden_proxy.unseal_payload(blob, secret="wrong-key"))
        tampered = bytearray(blob)
        tampered[-1] ^= 0xFF
        self.assertIsNone(hidden_proxy.unseal_payload(bytes(tampered)))

    def test_local_and_private_blocked(self):
        for bad in (
            "http://localhost:11434/v1",
            "http://127.0.0.1:7860",
            "http://[::1]:8188",
            "http://10.0.0.8/v1",
            "http://172.16.5.2:8080",
            "http://192.168.1.99:5000",
            "http://169.254.169.254/latest/meta-data",
            "http://mybox.local:8080",
            "",
        ):
            self.assertTrue(hidden_proxy.is_local_or_private(bad), f"应阻断: {bad}")
        for ok in (
            "https://api.openai.com/v1",
            "https://generativelanguage.googleapis.com/v1beta",
            "https://api.anthropic.com/v1",
            "https://image.pollinations.ai/prompt/cat",
        ):
            self.assertFalse(hidden_proxy.is_local_or_private(ok), f"应放行: {ok}")

    def test_load_config_priority(self):
        with tempfile.TemporaryDirectory() as td:
            seal_p = os.path.join(td, hidden_proxy.SEAL_FILENAME)
            with open(seal_p, "wb") as f:
                f.write(hidden_proxy.seal_payload({"mode": "proxy", "proxy_url": "http://127.0.0.1:19999"}))
            env = {
                "DICK_TUNNEL_FILE": seal_p,
                "DICK_HIDDEN_PROXY": "http://127.0.0.1:18888",
                "DICK_TUNNEL_HOST": "198.51.100.1",
                "DICK_TUNNEL_PASS": "pw",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                cfg = hidden_proxy.load_config()
                self.assertEqual(cfg["proxy_url"], "http://127.0.0.1:19999")
            # 删掉密封文件 → 落到 DICK_HIDDEN_PROXY
            os.remove(seal_p)
            with mock.patch.dict(os.environ, env, clear=False):
                cfg2 = hidden_proxy.load_config()
                self.assertEqual(cfg2["mode"], "proxy")
                self.assertEqual(cfg2["proxy_url"], "http://127.0.0.1:18888")
            # 清掉 DICK_HIDDEN_PROXY → 落到 SSH 环境变量
            env2 = dict(env, DICK_HIDDEN_PROXY="")
            with mock.patch.dict(os.environ, env2, clear=False):
                cfg3 = hidden_proxy.load_config()
                self.assertEqual(cfg3["mode"], "ssh")
                self.assertEqual(cfg3["host"], "198.51.100.1")


class TestLocalTunnelProxyTCP(unittest.TestCase):
    def setUp(self):
        # 启动一个本地回显 HTTP 服务，假装是远端 API 目标
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(n).decode("utf-8", "ignore")
                out = json.dumps({
                    "path": self.path,
                    "host": self.headers.get("Host", ""),
                    "auth": self.headers.get("Authorization", ""),
                    "body": json.loads(raw) if raw else None,
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self):
                out = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.echo_srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.echo_port = self.echo_srv.server_address[1]
        threading.Thread(target=self.echo_srv.serve_forever, daemon=True).start()

        # 启动一个原始 TCP 回显服务，测试 CONNECT 隧道透传
        self.tcp_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_srv.bind(("127.0.0.1", 0))
        self.tcp_srv.listen(8)
        self.tcp_port = self.tcp_srv.getsockname()[1]
        self._tcp_stop = False

        def _tcp_loop():
            self.tcp_srv.settimeout(0.2)
            while not self._tcp_stop:
                try:
                    c, _ = self.tcp_srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    data = c.recv(4096)
                    c.sendall(b"ECHO:" + data)
                finally:
                    c.close()

        threading.Thread(target=_tcp_loop, daemon=True).start()

        # 拨号器：把白名单域名路由到本地回显服务，验证真实代理帧与隧道转发
        self.dialed = []

        def fake_dial(host, port, src_addr):
            self.dialed.append((host, port))
            if port == 443:
                return socket.create_connection(("127.0.0.1", self.tcp_port), timeout=5)
            return socket.create_connection(("127.0.0.1", self.echo_port), timeout=5)

        self.proxy = hidden_proxy.LocalTunnelProxy(fake_dial, idle_sec=60)
        self.proxy_url = self.proxy.start()
        self.proxy_port = int(self.proxy_url.rsplit(":", 1)[1])

    def tearDown(self):
        self.proxy.stop()
        self._tcp_stop = True
        try:
            self.tcp_srv.close()
        except Exception:
            pass
        self.echo_srv.shutdown()
        self.echo_srv.server_close()

    def test_connect_allowed_hosts_for_openai_gemini_claude(self):
        for host in ("api.openai.com", "generativelanguage.googleapis.com", "api.anthropic.com"):
            with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=5) as s:
                s.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode("ascii"))
                resp = s.recv(4096)
                self.assertTrue(resp.startswith(b"HTTP/1.1 200"), f"{host} CONNECT 应成功: {resp!r}")
                s.sendall(b"ping-" + host.encode("ascii"))
                echoed = s.recv(4096)
                self.assertEqual(echoed, b"ECHO:ping-" + host.encode("ascii"))
        self.assertIn(("api.anthropic.com", 443), self.dialed)

    def test_connect_rejects_unlisted_and_private(self):
        for bad in ("evil.example.com:443", "127.0.0.1:11434", "192.168.1.1:80"):
            with socket.create_connection(("127.0.0.1", self.proxy_port), timeout=5) as s:
                s.sendall(f"CONNECT {bad} HTTP/1.1\r\nHost: {bad}\r\n\r\n".encode("ascii"))
                resp = s.recv(4096)
                self.assertIn(b"403 Forbidden", resp, f"应拦截 {bad}: {resp!r}")
        self.assertFalse(self.proxy.allow_url("http://127.0.0.1:11434/v1"))

    def test_plain_http_proxy_forwarding(self):
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": self.proxy_url, "https": self.proxy_url})
        )
        req = urllib.request.Request(
            "http://api.openai.com/v1/images/generations",
            data=json.dumps({"model": "gpt-image-1"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer sk-ok"},
            method="POST",
        )
        with opener.open(req, timeout=5) as r:
            obj = json.loads(r.read().decode("utf-8"))
        self.assertEqual(obj["path"], "/v1/images/generations")
        self.assertEqual(obj["auth"], "Bearer sk-ok")
        self.assertEqual(obj["body"]["model"], "gpt-image-1")


class TestIntegrationFallbackAndZeroLeak(unittest.TestCase):
    def tearDown(self):
        hidden_proxy.reload_config()

    def test_core_fetch_silent_fallback_without_exposing_proxy(self):
        from DICK_core import ChatCore
        core = ChatCore()
        core.base_url = "https://api.anthropic.com/v1"
        core.proxy = None
        core.relay_base = None
        core.relay_on = False

        with mock.patch("hidden_proxy.ensure_proxy", return_value="http://127.0.0.1:54321") as m_ens, \
             mock.patch.object(core, "_build_client", return_value=mock.MagicMock()) as m_build:
            switched = core._maybe_switch_relay()
            self.assertTrue(switched)
            m_ens.assert_called_once_with("https://api.anthropic.com/v1")
            m_build.assert_called_once()
            # 零暴露：用户 proxy 仍为 None，relay_on 仍为 False
            self.assertIsNone(core.proxy)
            self.assertFalse(core.relay_on)
            self.assertEqual(core._hidden_proxy, "http://127.0.0.1:54321")

        # 显式设了用户代理 → 绝不触发隐藏隧道，且清空旧 _hidden_proxy
        with mock.patch.object(core, "_build_client", return_value=mock.MagicMock()):
            core.set_proxy("http://127.0.0.1:7890")
        self.assertIsNone(core._hidden_proxy)
        with mock.patch("hidden_proxy.ensure_proxy") as m_ens2:
            self.assertFalse(core._maybe_switch_relay())
            m_ens2.assert_not_called()

        # 本机 Ollama → 绝不触发隐藏隧道
        with mock.patch.object(core, "_build_client", return_value=mock.MagicMock()):
            core.set_proxy("")
            core.set_base_url("http://127.0.0.1:11434/v1")
        with mock.patch("hidden_proxy.ensure_proxy") as m_ens3:
            self.assertFalse(core._maybe_switch_relay())
            m_ens3.assert_not_called()

    def test_image_gen_net_fallback_and_cache_invalidation(self):
        import image_gen

        class DummyResp(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        svc = image_gen._svc()
        net = svc.net
        old_proxy = image_gen.proxy
        old_fb = image_gen.fallback_proxy
        fb_calls = []
        seen_proxies = []

        def fake_fb(url):
            fb_calls.append(url)
            return "http://127.0.0.1:55555"

        def fake_opener(proxy_override=None):
            px = proxy_override if proxy_override is not None else net.proxy_of()
            seen_proxies.append(px)
            if not px:
                def _fail(req, timeout=300):
                    raise urllib.error.URLError("connection timed out")
                return _fail
            def _ok(req, timeout=300):
                return DummyResp(b'{"candidates":[]}')
            return _ok

        try:
            image_gen.proxy = ""
            image_gen.fallback_proxy = fake_fb
            with mock.patch.object(net, "_opener", side_effect=fake_opener):
                out = net.post("https://generativelanguage.googleapis.com/v1beta/models/x:generateContent",
                               {"contents": []}, {"x-goog-api-key": "k"})
            self.assertEqual(out, {"candidates": []})
            self.assertEqual(seen_proxies, ["", "http://127.0.0.1:55555"])
            self.assertEqual(len(fb_calls), 1)

            # HTTPError（如 401）绝不触发兜底代理
            fb_calls.clear()
            def _http_401(req, timeout=300):
                raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))
            with mock.patch.object(net, "_opener", return_value=_http_401):
                with self.assertRaises(urllib.error.HTTPError):
                    net.post("https://api.openai.com/v1/images/generations", {}, {})
            self.assertEqual(fb_calls, [])

            # 动态修改 image_gen.proxy 会刷新 _opener_cache
            image_gen.proxy = "http://127.0.0.1:7890"
            op1 = net._opener()
            image_gen.proxy = "http://127.0.0.1:7891"
            op2 = net._opener()
            self.assertIsNot(op1, op2)
        finally:
            image_gen.proxy = old_proxy
            image_gen.fallback_proxy = old_fb

    def test_vision_claude_gemini_and_hidden_fallback(self):
        from shell_host import HostMixin
        import requests

        class FakeApp(HostMixin):
            def __init__(self, cfg, pid):
                self.config = cfg
                self.provider_id = pid
                self.core = types.SimpleNamespace(model=cfg.get("model", ""))

        # Claude 原生视觉格式
        app_c = FakeApp({
            "api_key": "sk-ant-123",
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-sonnet-4-6",
        }, "anthropic")
        url, body, headers, is_claude = app_c._vision_endpoint("AAAA", "image/jpeg", "看图", "人设")
        self.assertTrue(is_claude)
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], "sk-ant-123")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertEqual(body["system"], "人设")
        self.assertEqual(body["messages"][0]["content"][0]["type"], "image")
        self.assertEqual(body["messages"][0]["content"][0]["source"]["media_type"], "image/jpeg")

        fake_resp = types.SimpleNamespace(
            status_code=200,
            json=lambda: {"content": [{"type": "text", "text": "这是一只猫"}]},
        )
        self.assertEqual(app_c._extract_vision_text(fake_resp, is_claude=True), "这是一只猫")

        # Gemini 视觉使用配置的模型而非硬编码 deepseek-flash
        app_g = FakeApp({
            "api_key": "AIza-123",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-2.5-flash",
        }, "gemini")
        url_g, body_g, headers_g, is_c_g = app_g._vision_endpoint("BBBB", "image/png", "描述")
        self.assertFalse(is_c_g)
        self.assertEqual(body_g["model"], "gemini-2.5-flash")
        self.assertEqual(headers_g["Authorization"], "Bearer AIza-123")

        # 直连网络异常 → 静默切隐藏代理重试
        calls = []
        class FakeSess:
            def __init__(self):
                self.trust_env = True
            def post(self, u, **kw):
                calls.append((u, kw.get("proxies"), self.trust_env))
                if kw.get("proxies") is None:
                    raise requests.exceptions.ConnectionError("blocked")
                return fake_resp
            def close(self):
                pass

        with mock.patch("requests.Session", side_effect=FakeSess), \
             mock.patch("hidden_proxy.ensure_proxy", return_value="http://127.0.0.1:51234"):
            r = HostMixin._vision_http_post(url, body, headers, 30, user_proxy=None)
        self.assertIs(r, fake_resp)
        self.assertEqual(calls[0][1], None)
        self.assertEqual(calls[0][2], False)
        self.assertEqual(calls[1][1], {"http": "http://127.0.0.1:51234", "https": "http://127.0.0.1:51234"})

    def test_api_test_and_save_key_claude_and_hidden_fallback(self):
        from shell_api_media import ApiMediaMixin
        import requests

        class FakeMediaApp(ApiMediaMixin):
            def __init__(self):
                self.provider_id = "anthropic"
                self.config = {"proxy": ""}
                self.saved = None
            def api_save_key(self, k, base, m, pid):
                self.saved = (k, base, m, pid)
                return {"ok": True}
            def _probe_reason(self, code, text):
                return f"HTTP {code}"
            def _probe_hint(self, code):
                return "hint"

        app = FakeMediaApp()
        seen = []

        class FakeSess:
            def __init__(self):
                self.trust_env = True
            def get(self, u, headers=None, proxies=None, timeout=12):
                seen.append((u, headers, proxies))
                if proxies is None:
                    raise requests.exceptions.ConnectTimeout("timeout")
                return types.SimpleNamespace(status_code=200, text="{}")
            def close(self):
                pass

        with mock.patch("requests.Session", side_effect=FakeSess), \
             mock.patch("hidden_proxy.ensure_proxy", return_value="http://127.0.0.1:59999"):
            res = app.api_test_and_save_key("sk-ant-key", "https://api.anthropic.com/v1", "claude-sonnet-4-6", "anthropic")

        self.assertTrue(res["ok"])
        self.assertEqual(seen[0][1].get("x-api-key"), "sk-ant-key")
        self.assertEqual(seen[0][1].get("anthropic-version"), "2023-06-01")
        self.assertEqual(seen[1][2], {"http": "http://127.0.0.1:59999", "https": "http://127.0.0.1:59999"})
        # 返回体与 config 中绝不泄漏隐藏代理
        self.assertNotIn("59999", json.dumps(res))
        self.assertEqual(app.config.get("proxy"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
