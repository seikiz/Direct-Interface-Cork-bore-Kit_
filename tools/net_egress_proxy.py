# -*- coding: utf-8 -*-
"""按需启动的出口代理：本机 HTTP CONNECT → SSH → 香港服务器 → 外网。

用途：本机到 github.com:443 被掐时，用
    git -c http.proxy=http://127.0.0.1:8888 push origin HEAD:main
把提交推上去。

用法（凭据走环境变量，不写死在脚本里）：
    $env:DICK_SRV_HOST="..."; $env:DICK_SRV_USER="root"; $env:DICK_SRV_PASS="..."
    python tools/net_egress_proxy.py           # 前台跑，Ctrl+C 停
"""
import os
import socket
import sys
import threading

import paramiko

HOST = os.environ.get("DICK_SRV_HOST", "")
USER = os.environ.get("DICK_SRV_USER", "root")
PASS = os.environ.get("DICK_SRV_PASS", "")
LISTEN = ("127.0.0.1", int(os.environ.get("PROXY_PORT", "8888")))


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (src, dst):
            try:
                s.close()
            except Exception:
                pass


def handle(conn, transport):
    try:
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                conn.close()
                return
            buf += chunk
        parts = buf.split(b"\r\n", 1)[0].decode("latin-1").split()
        if len(parts) < 2 or parts[0].upper() != "CONNECT":
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            conn.close()
            return
        host, _, port = parts[1].rpartition(":")
        chan = transport.open_channel("direct-tcpip", (host, int(port or 443)), conn.getpeername())
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        threading.Thread(target=pipe, args=(conn, chan), daemon=True).start()
        threading.Thread(target=pipe, args=(chan, conn), daemon=True).start()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def main():
    if not HOST or not PASS:
        print("缺 DICK_SRV_HOST / DICK_SRV_PASS")
        return 2
    t = paramiko.Transport((HOST, 22))
    t.connect(username=USER, password=PASS)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(50)
    print("出口代理就绪：http://%s:%d（经 %s）" % (LISTEN[0], LISTEN[1], HOST))
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn, t), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌