# -*- coding: utf-8 -*-
"""kernel/selftest.py —— 内核块的自检（闭环：不装任何模块就能自证）

`python -m kernel --selftest`  → 成功时**只有一行** JSON：
    {"block": "kernel", "pass": 12, "fail": 0, "ms": 3, "deps": []}

为什么不 boot 真模块：内核的自检要证明的是"**没有模块也能起来**"（可降级），
所以这里故意指向一个不存在的模块目录 —— 装上别人的块反而证明不了这件事。

硬规则：不连网、不占端口、不写磁盘（配置目录给的是不存在的路径）。
"""

import io
import json
import os
import sys
import time

from . import paths
from . import version as _version
from .bus import Bus
from .loader import ModuleLoader, ModuleState
from .log import Log
from .manifest import Manifest
from .registry import Registry, ServiceNotFound

BLOCK = "kernel"
MAX_MS = 2000
_NO_SUCH_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_no_such_dir_")


# ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 小工具
def _eq(got, want, what):
    if got != want:
        raise AssertionError("%s：期望 %r，实际 %r" % (what, want, got))
    return True


def _true(cond, what):
    if not cond:
        raise AssertionError(what)
    return True


def _kernel():
    """一个什么都指向空位置的内核（不写盘、不装块）"""
    from . import Kernel
    return Kernel(base_dir=_NO_SUCH_DIR, modules_dir=_NO_SUCH_DIR, echo=False)


def _deps():
    return []


# ---------------------------------------------------------------- cases
def case_boot_without_modules():
    k = _kernel().boot()
    _eq(k.started, True, "空模块目录也要能启动")
    _eq(k.loaded_ids(), [], "没有模块时 loaded_ids 为空")

def case_boot_is_idempotent_state():
    k = _kernel().boot()
    _eq(k.summary(), {}, "没有模块时 summary 为空表")
    _eq(k.failed_modules(), {}, "没有模块时失败表为空")

def case_manifest_ok():
    m = Manifest({"id": "demo", "version": "1.0.0.0",
                  "provides": {"services": ["demo"]}, "lazy": False})
    _eq(m.ok, True, "合法清单应当通过：%s" % m.errors)
    _eq(m.services(), ["demo"], "services 归一化")

def case_manifest_reject_version():
    m = Manifest({"id": "demo", "version": "1.0.0"})
    _eq(m.ok, False, "三段版号必须被拒")
    _true(any("四段" in e for e in m.errors), str(m.errors))

def case_manifest_reject_extra_key():
    m = Manifest({"id": "demo", "version": "1.0.0.0", "provide": {}})
    _eq(m.ok, False, "不认识的顶层字段必须被拒")
    _true(any("不认识" in e for e in m.errors), str(m.errors))

def case_registry_dup():
    r = Registry(Log(echo=False))
    _eq(r.register("svc", 1, owner="a"), True, "第一次注册成功")
    _eq(r.register("svc", 2, owner="b"), False, "重名必须被拒")
    _eq(r.get("svc"), 1, "先注册的不能被覆盖")

def case_registry_require():
    r = Registry(Log(echo=False))
    try:
        r.require("nope")
    except ServiceNotFound as e:
        _true("nope" in str(e), "报错要带服务名：%r" % str(e))
        return
    raise AssertionError("找不到服务居然不抛")

def case_registry_owner_rollback():
    r = Registry(Log(echo=False))
    r.register("a", 1, owner="m")
    r.register("b", 2, owner="m")
    _eq(r.unregister_owner("m"), ["a", "b"], "按 owner 清干净")
    _eq(r.names(), [], "清完之后没有残留")

def case_bus_sync_off():
    bus = Bus(Log(echo=False))
    got = []
    h = bus.on("t", lambda p: got.append(p["n"]))
    bus.emit("t", n=1)
    bus.off("t", h)
    bus.emit("t", n=2)
    _eq(got, [1], "退订之后不再收到")

def case_bus_prefix():
    bus = Bus(Log(echo=False))
    got = []
    bus.on("a", lambda p: got.append("prefix"))
    bus.emit("a.b", n=1)
    _eq(got, ["prefix"], "前缀订阅要能收到子事件")

def case_bus_bad_handler_isolated():
    bus = Bus(Log(echo=False))
    ok = []

    def boom(_p):
        raise ValueError("坏订阅者")
    bus.on("x", boom)
    bus.on("x", lambda p: ok.append(1))
    bus.emit("x")
    _eq(ok, [1], "坏订阅者不能影响别人")
    _true(bus.stats["failed"] >= 1, "失败要计数")

def case_bus_async_executor():
    bus = Bus(Log(echo=False))
    queued = []
    bus.set_executor(lambda fn: queued.append(fn) or "job")
    got = []
    bus.on("z", lambda p: got.append(p["n"]))
    _eq(bus.emit_async("z", n=7), True, "投递成功")
    _eq(len(queued), 1, "交给注入的执行器，而不是自己开线程")
    queued[0]()
    _eq(got, [7], "执行后事件送达")

def case_loader_absent():
    k = _kernel()
    _eq(k.loader.load("nope"), None, "不存在的块返回 None")
    _eq(k.loader.status_of("nope"), "absent", "状态应如实报 absent")

def case_loader_reconcile_missing_service():
    """坏输入：清单吹牛（声明了服务却没注册）必须被判失败"""
    k = _kernel()
    k.registry.names()
    m = Manifest({"id": "lie", "version": "1.0.0.0", "provides": {"services": ["lie_svc"]}})
    st = ModuleState("lie", m, _NO_SUCH_DIR)
    try:
        k.loader._reconcile(st, [])
    except RuntimeError as e:
        _true("lie_svc" in str(e), "报错要点名缺哪个服务：%r" % str(e))
        return
    raise AssertionError("吹牛居然没被抓住")

def case_version_rules():
    _eq(_version.is_valid("1.0.0.0"), True, "四段号合法")
    _eq(_version.is_valid("1.0.0"), False, "三段号非法")
    _eq(_version.compat_line("1.2.3.4"), "1.2", "兼容线取前两位")

def case_paths_are_parameterised():
    # 探针路径用 os.sep 拼，不写字面量绝对路径：块要能原封不动搬去别的项目
    # （ARCHITECTURE.md 十二.3：`C:\`、/tmp/ 这类字面量出现即违规）。
    probe = os.path.join(os.sep, "kernel_selftest_abs")
    _eq(paths.get_base_dir(probe), os.path.abspath(probe), "显式 base_dir 优先")
    _true(paths.get_config_file("a.json", probe).endswith("a.json"), "配置路径规则")


def _cases():
    return {
        "boot_without_modules": case_boot_without_modules,
        "boot_is_idempotent_state": case_boot_is_idempotent_state,
        "manifest_ok": case_manifest_ok,
        "manifest_reject_version": case_manifest_reject_version,
        "manifest_reject_extra_key": case_manifest_reject_extra_key,
        "registry_dup": case_registry_dup,
        "registry_require": case_registry_require,
        "registry_owner_rollback": case_registry_owner_rollback,
        "bus_sync_off": case_bus_sync_off,
        "bus_prefix": case_bus_prefix,
        "bus_bad_handler_isolated": case_bus_bad_handler_isolated,
        "bus_async_executor": case_bus_async_executor,
        "loader_absent": case_loader_absent,
        "loader_reconcile_missing_service": case_loader_reconcile_missing_service,
        "version_rules": case_version_rules,
        "paths_are_parameterised": case_paths_are_parameterised,
    }


# ---------------------------------------------------------------- 运行
def run(only=None):
    import contextlib
    t0 = time.perf_counter()
    passed, failed, errors = 0, 0, []
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        for cid in sorted(_cases()):
            if only and cid != only:
                continue
            try:
                _cases()[cid]()
                passed += 1
            except Exception as e:
                failed += 1
                errors.append((cid, "%s: %s" % (type(e).__name__, str(e)[:200])))
    ms = int((time.perf_counter() - t0) * 1000)
    if not only and ms > MAX_MS:
        failed += 1
        errors.append(("budget", "自检耗时 %dms 超过上限 %dms" % (ms, MAX_MS)))
    return ({"block": BLOCK, "pass": passed, "fail": failed, "ms": ms, "deps": _deps()},
            errors, sink.getvalue())


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" not in argv:
        print("用法：python -m kernel --selftest [--only <case>]")
        return 2
    only = argv[argv.index("--only") + 1] if "--only" in argv and \
        len(argv) > argv.index("--only") + 1 else None
    res, errors, log = run(only)
    print(json.dumps(res, ensure_ascii=False))
    if errors:
        for line in log.splitlines():
            print("  | " + line)
        for cid, msg in errors:
            print("FAIL %s: %s" % (cid, msg))
            print("  复现：python -m kernel --selftest --only %s" % cid)
    return 1 if res["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
