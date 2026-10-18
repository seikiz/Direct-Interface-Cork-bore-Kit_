# -*- coding: utf-8 -*-
"""kernel —— 微内核：只做三件事「装模块、给服务、发事件」，不认识任何业务。

五个组成部分（各自一句话）：
    registry.py  服务注册/查找，模块之间只能经它通信（重名拒绝、可按 owner 回滚）
    bus.py       事件总线，同步 emit + 可注入执行器的异步投递，坏订阅者不传染
    loader.py    按 manifest 发现并加载模块，单个模块失败只记日志、内核照常启动
    manifest.py  清单数据类与校验（id/version/provides/requires/lazy 五条硬规则）
    config.py/paths.py/log.py/version.py  从现有实现抽的最小件（路径/配置/日志/四段号）

依赖方向（铁律 1，由 tools/audit_kernel_boundaries.py 与测试强制）：
    内核只允许 import 标准库和它自己的子模块。
    `import modules.*`、`import DICK_core`、`import net`…… 出现在 kernel/ 下就是红灯。

壳层怎么用（桌面端/服务器/安卓桥接层都一样）：
    import kernel
    k = kernel.boot(base_dir=BASE_DIR)      # 装模块
    k.service("backup")                     # 拿服务
    k.bus.on("backup.done", handler)        # 听事件
"""

import os

from . import config as _config_mod
from . import paths
from . import version as _version
from .bus import Bus
from .loader import ModuleLoader
from .log import Log
from .manifest import Manifest, ManifestError
from .registry import Registry, ServiceNotFound

__all__ = ["Kernel", "boot", "Manifest", "ManifestError", "Registry", "ServiceNotFound",
           "Bus", "ModuleLoader", "Log", "paths", "KERNEL_VERSION"]

KERNEL_VERSION = _version.KERNEL_VERSION


class Kernel(object):
    """内核本体：持有 registry / bus / loader / config，其余一概不管。"""

    def __init__(self, base_dir=None, modules_dir=None, log=None, echo=True):
        self.log = log or Log(echo=echo)
        self.base_dir = paths.get_base_dir(base_dir)
        self.modules_dir = paths.get_modules_dir(self.base_dir, modules_dir)
        self.registry = Registry(self.log)
        self.bus = Bus(self.log)
        self.config = _config_mod.Config("config.json", self.base_dir, self.log)
        self.loader = ModuleLoader(self, self.modules_dir, self.log)
        self.started = False

    # ---------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------- 启动
    def boot(self, load=True):
        """读配置 → 发现模块 → 装非懒模块。**不会因为某个模块失败而抛异常。**"""
        try:
            self.config.load()
        except Exception as e:            # 配置坏了也不该拦住启动
            self.log.error("配置加载失败（按空配置继续）：%s" % str(e)[:160], "boot")
        self.loader.discover()
        if load:
            self.loader.load_all()
        self.started = True
        loaded, failed = self.loader.loaded_ids(), self.loader.failed()
        self.log.info("内核就绪：模块 %d 个装好%s"
                      % (len(loaded), ("，%d 个失败（%s）"
                                       % (len(failed), "、".join(sorted(failed))))
                         if failed else ""), "boot")
        self.bus.emit("kernel.booted", modules=loaded, failed=sorted(failed),
                      version=KERNEL_VERSION)
        return self

    # ---------------------------------------------------------------- 服务
    def service(self, name):
        """取服务（懒模块在这里才会被真正装上）。取不到抛 ServiceNotFound。"""
        svc = self.get_service(name)
        if svc is None:
            raise ServiceNotFound(name, self.registry.names())
        return svc

    def get_service(self, name, default=None):
        svc = self.registry.get(name)
        if svc is not None:
            return svc
        # 注册表里没有：看看是不是某个懒模块声明要提供的
        for mid, st in sorted(self.loader.states.items()):
            m = st.manifest
            if m and name in m.services() and st.status in ("lazy", "discovered"):
                self.loader.ensure(mid)
                svc = self.registry.get(name)
                if svc is not None:
                    return svc
        return default

    def has_service(self, name):
        return self.get_service(name) is not None

    def services(self):
        return self.registry.names()

    # ---------------------------------------------------------------- 事件
    def emit(self, topic, **payload):
        return self.bus.emit(topic, **payload)

    def on(self, topic, handler):
        return self.bus.on(topic, handler)

    def off(self, topic, handler=None):
        return self.bus.off(topic, handler)

    def bind_jobs(self, jobs_module, lane="plugin"):
        """把 jobs 的运行线下成总线执行器（复用现成调度，不发明第二套）。

        内核**不 import jobs**：换成什么都不影响内核，壳层决定用哪套调度。
        """
        def _submit(fn):
            return jobs_module.submit(lane, fn, name="kernel.event")
        self.bus.set_executor(_submit)
        self.log.info("异步事件改走 jobs 的 %r 线" % lane, "bus")
        return True

    # ---------------------------------------------------------------- 查询/收尾
    def module_state(self, module_id):
        return self.loader.states.get(module_id)

    def loaded_ids(self):
        return self.loader.loaded_ids()

    def failed_modules(self):
        return self.loader.failed()

    def summary(self):
        return self.loader.summary()

    def shutdown(self):
        """收尾：退订所有事件、摘掉服务（模块自己的线程/资源由模块负责）。"""
        self.bus.clear()
        for name in self.registry.names():
            self.registry.unregister(name)
        self.started = False
        self.log.info("内核已收尾", "boot")


def boot(base_dir=None, modules_dir=None, log=None, load=True, echo=True):
    """一行启动内核（壳层唯一需要记住的入口）。"""
    k = Kernel(base_dir=base_dir, modules_dir=modules_dir, log=log, echo=echo)
    return k.boot(load=load)


def modules_root():
    """仓库里的 modules/ 绝对路径（自检工具/测试用）"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "modules")
