# -*- coding: utf-8 -*-
"""kernel/registry.py —— 服务注册/查找（模块之间**只能**通过它通信）

规则（全部有测试盯着）：
    ① 服务名全局唯一。重名注册**返回 False 并记日志**，绝不"后注册的覆盖前面的"——
       覆盖是最隐蔽的故障：A 模块以为自己拿到了 B，其实拿到的是 C。
    ② 每个服务记下它的 owner（注册者），卸载模块时按 owner 一次摘干净。
    ③ track() 是给加载器用的：在它的作用域里注册了哪些服务会被记下来，
       用来跟 manifest.provides.services 对账（少注册/多注册都算坏模块）。
    ④ 只存不造：这里不 import 任何模块，也不认识任何业务类型。

为什么模块不许互相 import：
    直接 import 会把两个模块**编译期焊死**：A 改了内部函数名，B 在另一个进程/另一台机器上
    就 import 失败，连"A 没装"这种情况都表达不出来。经 registry 拿的是**运行时句柄**：
    A 不在 → 拿到 None → 降级路径走起来；A 换实现 → B 一行不用改。
"""

import threading


class ServiceNotFound(KeyError):
    """require() 找不到服务时抛出（带可用服务清单，排查不用猜）"""

    def __init__(self, name, known):
        self.name = name
        self.known = list(known)
        super(ServiceNotFound, self).__init__(
            "服务 %r 没有注册；当前已有：%s" % (name, "、".join(self.known) or "（空）"))


class Registry(object):
    """服务注册表：线程安全、可审计、可回滚。"""

    def __init__(self, log=None):
        self._lock = threading.RLock()
        self._services = {}          # name -> 服务对象
        self._owners = {}            # name -> 模块 id
        self._log = log

    # ---- 注<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌册 ----
    def register(self, name, service, owner=""):
        """注册一个服务。重名 → False（不覆盖）。"""
        name = str(name or "").strip()
        if not name:
            self._warn("服务名不能为空")
            return False
        with self._lock:
            if name in self._services:
                self._warn("服务 %r 已被 %r 注册，拒绝覆盖"
                           % (name, self._owners.get(name) or "?"))
                return False
            self._services[name] = service
            self._owners[name] = str(owner or "")
        if self._log:
            self._log.info("注册服务 %s%s" % (name, ("（来自 %s）" % owner) if owner else ""),
                           "registry")
        return True

    def register_service(self, name, service, owner=""):
        """register 的别名（模块里读起来更像一句话：register_service(...)）"""
        return self.register(name, service, owner)

    # ---- 查找 ----
    def get(self, name, default=None):
        with self._lock:
            return self._services.get(str(name or "").strip(), default)

    def require(self, name):
        with self._lock:
            key = str(name or "").strip()
            if key in self._services:
                return self._services[key]
            raise ServiceNotFound(key, sorted(self._services))

    def has(self, name):
        with self._lock:
            return str(name or "").strip() in self._services

    def names(self):
        with self._lock:
            return sorted(self._services)

    def owner_of(self, name):
        with self._lock:
            return self._owners.get(str(name or "").strip(), "")

    # ---- 卸载 ----
    def unregister(self, name):
        with self._lock:
            key = str(name or "").strip()
            if key not in self._services:
                return False
            self._services.pop(key, None)
            self._owners.pop(key, None)
            return True

    def unregister_owner(self, owner):
        """把一个模块注册过的服务全摘掉（模块加载失败回滚 / 卸载时用）"""
        owner = str(owner or "")
        with self._lock:
            names = [n for n, o in self._owners.items() if o == owner]
        for n in names:
            self.unregister(n)
        return names

    # ---- 对账 ----
    def track(self):
        """with registry.track() as t: ... 之后 t.added 就是这段里新注册的服务名。"""
        return _Tracker(self)

    # ---- 内部 ----
    def _warn(self, msg):
        if self._log:
            self._log.warn(msg, "registry")


class _Tracker(object):
    def __init__(self, registry):
        self.registry = registry
        self.before = set()
        self.added = []

    def __enter__(self):
        self.before = set(self.registry.names())
        return self

    def __exit__(self, *exc):
        self.added = [n for n in self.registry.names() if n not in self.before]
        return False
