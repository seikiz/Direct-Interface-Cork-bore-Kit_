# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   jobs.py —— 模块分道执行（一个模块一条运行线）
#
#   为什么要它：现在主程序用的是一个全局 self.busy + 一堆"点火即忘"的裸线程
#   （实测 32 个 threading.Thread、0 个线程池、11 个锁）。后果是慢活儿互相拖：
#   工坊请求、视觉描述、TTS、摘要、插件钩子全挤在同一条线上，谁慢谁把别人堵住，
#   而且没有任何地方能看到"现在到底在跑什么"。
#
#   这里给每个模块一条**自己的运行线（lane）**：
#     · 同一条线内 FIFO 串行 —— 保序（对话、落盘必须有序）
#     · 不同线之间并行   —— 互不阻塞（TTS 慢不该拖住下一轮对话）
#     · 每个任务有状态/耗时/错误，供界面显示与排查
#     · 结果进一条带序号的结果流，前端用现成的 poll 取走（不引入新通道）
#
#   用法：
#       import jobs
#       jobs.submit("net", requests.get, url, timeout=8, name="拉工坊列表",
#                   on_done=lambda r: ...)          # 可省，结果也能从结果流取
#       jobs.status()                                # {"lanes": {...}, "queued": n}
#       jobs.drain(seq)                              # 取 seq 之后的结果事件（poll 用）
#       jobs.shutdown()                              # 退出时收线
#
#   设计取舍：
#     · 用线程而不是 asyncio —— 现有代码到处是同步 requests/openai，改 asyncio 等于重写；
#       线程池 + 队列在这个体量下够用，且不改变任何调用方的写法。
#     · 队列有上限：满了 submit 直接返回错误而不是无限堆积（宁可明确失败，也不要内存悄悄涨）。
#     · 任务异常一律被捕获进任务记录 —— 一条线绝不能因为一个坏任务而死掉。
# ============================================================

import queue
import threading
import time
import traceback

DEFAULT_LANES = (
    # 线名      队列上限  说明
    ("talk", 8),      # 主对话生成：保序，必须串行
    ("net", 32),      # 网络请求（工坊、搜索、下载）
    ("vision", 4),    # 看图描述（LLM 调用，慢）
    ("voice", 16),    # TTS / UTAU 合成与播放
    ("image", 8),     # 生图
    ("memory", 8),    # 摘要 / 记忆归档 / 剪枝
    ("plugin", 32),   # 插件钩子与命令
    ("io", 16),       # 落盘 / 导出 / 备份
)


class _Lane:
    def __init__(self, name, cap):
        self.name = name
        self.q = queue.Queue(maxsize=cap)
        self.thread = None
        self.busy = False
        self.current = None
        self.started = 0
        self.done = 0
        self.failed = 0
        self.dropped = 0
        self.last_error = ""
        self.last_ms = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ---- 运行线本体 ----
    def _run(self):
        while not self._stop.is_set():
            try:
                task = self.q.get(timeout=0.25)
            except queue.Empty:
                continue
            if task is None:            # 收线信号
                break
            jid, fn, args, kw, on_done, label = task
            with self._lock:
                self.busy = True
                self.current = label
                self._mark_running(jid)
            t0 = time.time()
            ok, result, err = True, None, ""
            try:
                result = fn(*args, **kw)
            except Exception as e:
                ok, err = False, "%s: %s" % (type(e).__name__, str(e)[:200])
                self.last_error = err
                try:
                    traceback.print_exc()
                except Exception:
                    pass
            ms = (time.time() - t0) * 1000.0
            with self._lock:
                self.busy = False
                self.current = None
                self.last_ms = ms
                self.done += 1
                if not ok:
                    self.failed += 1
                self._mark_finished(jid, ok, result, err, ms)
            if callable(on_done):
                try:
                    on_done(result if ok else None, err)
                except Exception as e:
                    print("[jobs] on_done 回调出错：%s" % str(e)[:140])
            try:
                self.q.task_done()
            except Exception:
                pass

    def _mark_running(self, jid):
        j = _JOBS.get(jid)
        if j:
            j["state"] = "running"
            j["started_at"] = time.time()

    def _mark_finished(self, jid, ok, result, err, ms):
        j = _JOBS.get(jid)
        if j:
            j["state"] = "done" if ok else "error"
            j["ok"] = ok
            j["err"] = err
            j["ms"] = round(ms, 1)
            j["result"] = _safe(result)
            j["finished_at"] = time.time()
        _push({"type": "job", "id": jid, "lane": self.name, "ok": ok,
               "err": err, "ms": round(ms, 1),
               "label": (j or {}).get("label", ""),
               "result": _safe(result)})


# ---------- 模块级状态 ----------
_LANES = {}
_JOBS = {}
_EVENTS = []            # 结果流（带 seq）
_seq = 0
_lock = threading.Lock()
_STARTED = False


def _safe(v):
    """结果流里只放能安全序列化的东西（前端要 JSON）"""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v if not isinstance(v, str) or len(v) <= 4000 else v[:4000] + "…"
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in list(v)[:200]]
    if isinstance(v, dict):
        return {str(k): _safe(x) for k, x in list(v.items())[:200]}
    return str(v)[:500]


def _push(ev):
    global _seq
    with _lock:
        _seq += 1
        ev["seq"] = _seq
        _EVENTS.append(ev)
        if len(_EVENTS) > 2000:      # 结果流有上限，防止长跑把内存吃光
            del _EVENTS[:len(_EVENTS) - 2000]


def start(lanes=DEFAULT_LANES):
    """建线并启动（幂等）。"""
    global _STARTED
    with _lock:
        if _STARTED:
            return
        for name, cap in lanes:
            ln = _Lane(name, cap)
            ln.thread = threading.Thread(target=ln._run, name="dick-" + name, daemon=True)
            ln.thread.start()
            _LANES[name] = ln
        _STARTED = True


def submit(lane, fn, *args, **kw):
    """往某条线投一个任务。返回 job id；线满/线不存在时返回 None（调用方可降级为同步执行）。"""
    start()
    label = kw.pop("name", "") or getattr(fn, "__name__", "task")
    on_done = kw.pop("on_done", None)
    ln = _LANES.get(lane)
    if ln is None:
        return None
    jid = "j%d" % (int(time.time() * 1000) % 10 ** 9) + "-" + str(len(_JOBS) + 1)
    with _lock:
        _JOBS[jid] = {"id": jid, "lane": lane, "label": label, "state": "queued",
                      "queued_at": time.time(), "ok": None, "err": "", "ms": 0.0}
        if len(_JOBS) > 500:
            for k in [k for k, v in _JOBS.items() if v.get("state") in ("done", "error")][:200]:
                _JOBS.pop(k, None)
    try:
        ln.q.put_nowait((jid, fn, args, kw, on_done, label))
    except queue.Full:
        with _lock:
            ln.dropped += 1
            j = _JOBS.get(jid)
            if j:
                j["state"] = "dropped"
                j["err"] = "该条线的队列已满（%s）" % lane
        return None
    return jid


def job(jid):
    with _lock:
        j = _JOBS.get(jid)
        return dict(j) if j else None


def status():
    """给界面/poll 看的快照。

    注意：**不自动起线** —— 查询状态不该把已经收掉的线"复活"（收线后就应该如实报告 False/空）。
    """
    with _lock:
        lanes = {}
        for name, ln in _LANES.items():
            lanes[name] = {"busy": ln.busy, "current": ln.current, "queued": ln.q.qsize(),
                           "done": ln.done, "failed": ln.failed, "dropped": ln.dropped,
                           "last_ms": round(ln.last_ms, 1), "last_error": ln.last_error}
        running = [dict(v) for v in _JOBS.values() if v.get("state") in ("queued", "running")]
        return {"lanes": lanes, "running": running[:40], "seq": _seq,
                "started": _STARTED}


def drain(since_seq=0, limit=200):
    """取 seq 之后的结果事件（poll 用）。

    语义：单一消费者（前端 poll）用同一个水位线 —— 传进来的 since 表示"我已经看到这里了"，
    因此比它更早的事件可以安全丢弃（否则结果流会随长跑无限增长）。
    """
    since = int(since_seq or 0)
    with _lock:
        out = [dict(e) for e in _EVENTS if e["seq"] > since][:limit]
        if out:
            _EVENTS[:] = [e for e in _EVENTS if e["seq"] > since]
        return out


def wait_idle(lane=None, timeout=10.0):
    """等某条线（或全部线）把队列跑完 —— 测试与退出时用。没收线时直接返回 True。"""
    if not _STARTED:
        return True
    t0 = time.time()
    targets = [_LANES[lane]] if lane in _LANES else list(_LANES.values())
    while time.time() - t0 < timeout:
        if all((not ln.busy) and ln.q.qsize() == 0 for ln in targets):
            return True
        time.sleep(0.02)
    return False


def shutdown(timeout=3.0):
    """收线：投 None 信号并等线程结束。"""
    global _STARTED
    with _lock:
        lanes = list(_LANES.values())
    for ln in lanes:
        try:
            ln._stop.set()
            ln.q.put_nowait(None)
        except Exception:
            pass
    for ln in lanes:
        if ln.thread:
            ln.thread.join(timeout=timeout)
    with _lock:
        _LANES.clear()
        _STARTED = False
