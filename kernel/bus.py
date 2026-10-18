# -*- coding: utf-8 -*-
"""kernel/bus.py —— 事件总线（emit / on / off，同步 + 可选线程投递）

要说清楚的三件事：
    ① **同步 emit 是默认**。内核里的"事件"多数是通知（模块装好了、备份写完了），
       订阅者应当是快的。慢活儿要自己往模块的运行线（jobs 的分道）里扔。
    ② `emit` 里任何一个订阅者抛异常，**都不会影响其它订阅者**，也不会把发事件的人弄崩：
       异常被记进日志 + 计数，调用方照常往下走。这是"一个坏模块不许拖垮内核"的落点。
    ③ `emit_async` 不自己造线程池：壳层把 `jobs.submit` 注进来（见 kernel/__init__.py 的
       `bind_jobs`），内核只管调它。没注入时退化成一次性守护线程 —— 能跑，但**不保序**，
       所以正式路径一定要注入。

订阅名支持前缀匹配：订阅 `workshop` 能收到 `workshop.upload.done`；
订阅 `*` 收全部（调试/审计用，别在业务里滥用）。
"""

import threading
import traceback

WILDCARD = "*"


class Bus(object):
    """最小事件总线：满足"发出去、有人听、能退订"，不多做。"""

    def __init__(self, log=None):
        self._lock = threading.RLock()
        self._subs = {}              # topic -> [handler, ...]
        self._executor = None        # 由壳层注入：fn(callable) -> job id / None
        self._log = log
        self.stats = {"emitted": 0, "delivered": 0, "failed": 0, "async": 0}

    # ---- 订<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌阅 ----
    def on(self, topic, handler):
        """订阅；返回 handler 本身（方便 `h = bus.on(...)`；off 时原样传回）"""
        if not callable(handler):
            raise TypeError("handler 必须可调用")
        key = self._key(topic)
        with self._lock:
            self._subs.setdefault(key, [])
            if handler not in self._subs[key]:
                self._subs[key].append(handler)
        return handler

    def off(self, topic, handler=None):
        """退订：给了 handler 只摘那一个；不给就把这个 topic 清空。"""
        key = self._key(topic)
        with self._lock:
            if key not in self._subs:
                return 0
            if handler is None:
                n = len(self._subs.pop(key))
                return n
            handlers = self._subs.get(key) or []
            if handler in handlers:
                handlers.remove(handler)
                if not handlers:
                    self._subs.pop(key, None)
                return 1
            return 0

    def clear(self):
        with self._lock:
            self._subs = {}

    def subscribers(self, topic):
        """谁会收到这个 topic（按注册顺序，含前缀与通配）"""
        key = self._key(topic)
        with self._lock:
            out = []
            for sub, handlers in self._subs.items():
                if self._match(sub, key):
                    out.extend(handlers)
            return out

    # ---- 发布 ----
    def emit(self, topic, **payload):
        """同步发一个事件；返回 [(handler, 结果或异常对象)]，供测试断言。"""
        key = self._key(topic)
        targets = self.subscribers(key)
        results = []
        with self._lock:
            self.stats["emitted"] += 1
        for h in targets:
            try:
                r = h(key, dict(payload)) if _wants_two(h) else h(dict(payload))
                results.append((h, r))
                with self._lock:
                    self.stats["delivered"] += 1
            except Exception as e:
                with self._lock:
                    self.stats["failed"] += 1
                self._warn("订阅者 %r 处理 %r 时出错：%s"
                           % (getattr(h, "__name__", h), key, str(e)[:160]))
                # 出错位置只进日志（不往 stdout/stderr 打）：自检与验收要的是干净的一行 JSON
                try:
                    last = traceback.format_exc().strip().splitlines()[-1]
                    self._warn("出错位置：%s" % last[:200])
                except Exception:
                    pass
                results.append((h, e))
        return results

    def emit_async(self, topic, **payload):
        """把 emit 丢到注入的执行器上（jobs 的某条线）；没注入就开一根守护线程。

        返回 True = 已投递；False = 连线程都起不来（极少见）。
        """
        key = self._key(topic)
        data = dict(payload)

        def _fire():
            self.emit(key, **data)

        with self._lock:
            self.stats["async"] += 1
            ex = self._executor
        try:
            if callable(ex):
                jid = ex(_fire)
                if jid is not None:
                    return True
                # 执行器拒绝（例如运行线队列满了）→ 退化成一次性线程，事件不能丢
                self._warn("执行器拒绝了 %r 的投递，退化为一次性线程" % key)
            threading.Thread(target=_fire, name="kernel-bus",
                             daemon=True).start()
            return True
        except Exception as e:
            self._warn("投递 %r 失败：%s" % (key, str(e)[:160]))
            return False

    def set_executor(self, fn):
        """注入执行器：`fn(callable) -> 任务 id`（例如 jobs.submit 的偏函数）"""
        self._executor = fn
        return True

    # ---- 内部 ----
    @staticmethod
    def _key(topic):
        return str(topic or "").strip()

    @staticmethod
    def _match(sub, key):
        if sub == WILDCARD or sub == key:
            return True
        return key.startswith(sub + ".")

    def _warn(self, msg):
        if self._log:
            self._log.warn(msg, "bus")


def _wants_two(handler):
    """订阅者想不想要 (topic, payload) 两个参数？

    不强制所有订阅者都写两个形参（多数人只关心 payload）；这里按函数签名猜一次，
    猜不出（内置函数/partial/可变参数）就按一个参数调 —— 猜错会被 emit 的异常兜住。
    """
    try:
        import inspect
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    params = [p for p in sig.parameters.values()
              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    has_var = any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values())
    return has_var or len(params) >= 2
