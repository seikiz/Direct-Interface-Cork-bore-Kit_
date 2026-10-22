# -*- coding: utf-8 -*-
"""twin.py —— 双子：两个工坊服务器轮流跑，坏一个自动换另一个。

为什么做这个：
    现在只有一个工坊服务器。等第二台部署起来，用户希望"像候鸟一样"——
    不必手动改配置，客户端自己在两台之间来回，哪台活着就走哪台。

三条规矩（都不用猜）：
    ① **轮流**：两台都健康时按 `rotate_seconds` 轮换当前主用（默认 60 秒），
       不是每个请求都跳 —— 跳得太勤会让"刚上传的卡"下次刷新看不到（各自存各自的盘）。
    ② **坏就换**：连接失败 / 5xx / 超时 → 立刻打到另一台，并把坏的那台进冷静期
       （cooldown，默认 90 秒）。冷静期内不再试它，免得每次请求都白等一次超时。
    ③ **好了记得回**：冷静期过了允许再试；试通就恢复，按轮换顺序用回去。

状态落盘（`workshop_twin.json`）：记住当前主用、每台的最近成败，
重启之后不会又从头猜一遍。

这一层是纯逻辑：不 import flask / requests，探测函数由调用方注入
（服务端用 urllib 探 /api/node，客户端用 requests 探 /api/health）。
这样测试里可以完全控制时间与成败。

验：tests/test_twin_pool.py
"""
from __future__ import annotations

import json
import os
import time

DEFAULT_ROTATE_SECONDS = 60
DEFAULT_COOLDOWN = 90


def norm(url):
    """统一写法：去空白、去尾斜杠。"""
    return str(url or "").strip().rstrip("/")


def parse_list(text):
    """把 "a,b,c" / ["a","b"] 统一成去重后的 url 列表（保序）。"""
    if isinstance(text, str):
        items = [x for x in text.replace("\n", ",").split(",")]
    else:
        items = list(text or [])
    out = []
    for x in items:
        u = norm(x)
        if u and u not in out:
            out.append(u)
    return out


class TwinPool(object):
    """两台（或多台）工坊服务器的轮换 + 故障转移。"""

    def __init__(self, servers, state_file=None, rotate_seconds=DEFAULT_ROTATE_SECONDS,
                 cooldown=DEFAULT_COOLDOWN, now=None):
        self.servers = parse_list(servers)
        self.state_file = state_file
        self.rotate_seconds = int(rotate_seconds)
        self.cooldown = int(cooldown)
        self._now = now or time.time
        self.active = self.servers[0] if self.servers else ""
        self.since = self._now()
        # url -> {"ok": bool, "fails": <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌int, "until": ts, "last": ts}
        self._was_cooling = set()
        self.health = {u: {"ok": True, "fails": 0, "until": 0.0, "last": 0.0} for u in self.servers}
        self.load()

    # ---------------------------------------------------------------- 持久化
    def load(self):
        if not self.state_file or not os.path.isfile(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not isinstance(data, dict):
            return
        if data.get("active") in self.servers:
            self.active = data["active"]
        self.since = float(data.get("since") or self.since)
        saved = data.get("health") or {}
        for u, h in saved.items():
            if u in self.health and isinstance(h, dict):
                self.health[u].update({k: h[k] for k in ("ok", "fails", "until", "last") if k in h})

    def save(self):
        if not self.state_file:
            return
        try:
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"active": self.active, "since": self.since, "health": self.health},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.state_file)
        except Exception:
            pass

    # ---------------------------------------------------------------- 选择
    def _usable(self, url, now):
        h = self.health.get(url) or {}
        return now >= float(h.get("until") or 0)

    def pick(self, force_rotate=False):
        """返回这次该用的服务器地址；没有可用服务器时返回空串。

        轮换条件：两台都健康、且当前这台已经用了 >= rotate_seconds（或 force_rotate）。
        """
        if not self.servers:
            return ""
        now = self._now()
        usable = [u for u in self.servers if self._usable(u, now)]
        if not usable:
            # 都在冷静期：挑最早恢复的那台（总比直接失败好），并提示调用方
            return min(self.servers, key=lambda u: float(self.health[u].get("until") or 0))
        # 好了记得回：冷静期刚过、又通了的那台优先切回去（候鸟认得旧巢）
        recovered = [u for u in usable if u in self._was_cooling]
        self._was_cooling = {u for u in self.servers if u not in usable}
        if recovered and self.active not in recovered:
            self.active = recovered[0]
            self.since = now
            self.save()
            return self.active
        if self.active not in usable:
            self.active = usable[0]
            self.since = now
            return self.active
        if len(usable) > 1 and (force_rotate or (now - self.since) >= self.rotate_seconds):
            idx = usable.index(self.active)
            self.active = usable[(idx + 1) % len(usable)]
            self.since = now
            self.save()
        return self.active

    def next_other(self, url=None):
        """换一台（故障转移用）。没有别的可用服务器时返回当前这台。"""
        now = self._now()
        cur = norm(url) or self.active
        others = [u for u in self.servers if u != cur and self._usable(u, now)]
        if not others:
            return cur
        self.active = others[0]
        self.since = now
        self.save()
        return self.active

    # ---------------------------------------------------------------- 回报
    def report(self, url, ok):
        u = norm(url)
        h = self.health.setdefault(u, {"ok": True, "fails": 0, "until": 0.0, "last": 0.0})
        now = self._now()
        h["last"] = now
        if ok:
            h["ok"] = True
            h["fails"] = 0
            h["until"] = 0.0
        else:
            h["ok"] = False
            h["fails"] = int(h.get("fails") or 0) + 1
            h["until"] = now + self.cooldown
        self.save()

    def snapshot(self):
        now = self._now()
        return {
            "active": self.active,
            "rotate_seconds": self.rotate_seconds,
            "cooldown": self.cooldown,
            "nodes": [
                {
                    "url": u,
                    "ok": bool(self.health[u].get("ok")),
                    "fails": int(self.health[u].get("fails") or 0),
                    "cooling": now < float(self.health[u].get("until") or 0),
                    "retry_in": max(0, int(float(self.health[u].get("until") or 0) - now)),
                    "active": u == self.active,
                }
                for u in self.servers
            ],
        }
