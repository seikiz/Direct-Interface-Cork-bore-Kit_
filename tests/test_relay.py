# -*- coding: utf-8 -*-
"""net.py 内置代理通道（/relay）端到端测试：本地回显目标 ← 转发。"""
import sys, os, json, threading, base64, http.server, socketserver

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import net  # 启动 Flask app 定义

ok = 0
bad = 0
def check(c, m):
    global ok, bad
    if c:
        ok += 1
        print("  OK " + m)
    else:
        bad += 1
        print("  FAIL " + m)

# 1) 本地回显目标（模拟 OpenAI 官方 API）
class EchoHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        auth = self.headers.get("Authorization", "")
        payload = json.dumps({
            "path": self.path,
            "auth": auth,
            "body": json.loads(body) if body else None,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *a):
        pass

with socketserver.TCPServer(("127.0.0.1", 0), EchoHandler) as srv:
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    target = "http://127.0.0.1:%d" % port
    b64 = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")

    client = net.app.test_client()
    # 2) 经 /relay/<b64>/chat/completions 转发
    r = client.post("/relay/%s/chat/completions" % b64,
                    data=json.dumps({"model": "x", "messages": [{"role": "user", "content": "hi"}]}),
                    content_type="application/json",
                    headers={"Authorization": "Bearer sk-test-123"})
    check(r.status_code == 200, "relay 状态 200: %d" % r.status_code)
    got = r.get_json()
    check(got["path"] == "/chat/completions", "路径原样转发: %s" % got["path"])
    check(got["auth"] == "Bearer sk-test-123", "密钥 Authorization 原样透传")
    check(got["body"]["model"] == "x", "请求体原样转发")

    # 3) 非法目标被拒
    r2 = client.post("/relay/%s/chat/completions" %
                     base64.urlsafe_b64encode(b"notaurl").decode().rstrip("="),
                     data="{}", content_type="application/json")
    check(r2.status_code == 400, "非法目标返回 400")

    # 4) base64 编码与 ChatCore 端一致（去 padding 可解回）
    pad = "=" * (-len(b64) % 4)
    dec = base64.urlsafe_b64decode(b64 + pad).decode()
    check(dec == target, "去 padding 编码可还原: %s" % dec)

    srv.shutdown()

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
