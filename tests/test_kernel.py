# -*- coding: utf-8 -*-
"""微内核单测：装模块 / 降级 / 服务注册 / 事件 / 重复 id / 懒加载 / 清单校验。

为什么需要这一套
----------------
微内核最危险的失败模式**不会自己暴露**：
  · 一个模块装失败，把整个启动带走（用户看到的是"打不开"）；
  · 服务重名，后注册的静默覆盖前一个（拿到的是错的那个对象，行为诡异且无日志）；
  · manifest 吹牛（声明了服务却没注册）：界面以为能力在，点下去报 None；
  · 懒加载其实没懒（启动慢），或者懒了却再也装不上（服务永远拿不到）。
这些都是"不报错、只是不对"，所以必须逐条钉成断言。

跑法：python tests\\test_kernel.py
"""
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import kernel                      # noqa: E402  （路径就绪后 import）
import app_paths                   # noqa: E402

PASS = 0
FAIL = 0
_TMP = []
_TEMP_BASE = None


def _writable_dir(base):
    """能否在这个目录下建目录？（venv python 在某些环境里只能写工作区）"""
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".probe_%d" % os.getpid())
        os.makedirs(probe, exist_ok=True)
        os.rmdir(probe)
        return True
    except Exception:
        return False


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def tmpdir(label):
    """临时目录：优先 %TEMP%；写不进去就退到工作区里的 tmp_kernel_tests/（跑完必删）。

    为什么要这层探测：本仓库的 venv（Windows Store 版 Python 3.11）在这台机器上
    **无法在 %TEMP% 建目录**（WinError 5）—— `tempfile.mkdtemp` 会一路重试到超时，
    而 `tempfile.gettempdir()` 又会退化成当前目录（仓库根那堆 tmpXXXXXX 就是这么来的）。
    所以这里显式挑一个真能写的位置，并把"删干净"放进 finally。
    """
    global _TEMP_BASE
    if _TEMP_BASE is None:
        for base in (os.environ.get("TEMP"), os.environ.get("TMP"),
                     os.path.join(ROOT, "tmp_kernel_tests")):
            if base and _writable_dir(base):
                _TEMP_BASE = base
                break
        else:
            _TEMP_BASE = os.path.join(ROOT, "tmp_kernel_tests")
            os.makedirs(_TEMP_BASE, exist_ok=True)
    d = tempfile.mkdtemp(prefix="dick_kernel_%s_" % label, dir=_TEMP_BASE)
    _TMP.append(d)
    return d


def cleanup_tmp():
    """跑完把临时目录删干净（工作区不许留垃圾）"""
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)
    _TMP[:] = []
    if _TEMP_BASE and os.path.abspath(_TEMP_BASE).startswith(os.path.abspath(ROOT)):
        shutil.rmtree(_TEMP_BASE, ignore_errors=True)


def write_module(tree, dir_name, module_id, services=("svc",), version="1.0.0.0",
                 lazy=False, register_code=None, manifest=None):
    """在 tree/modules/<dir_name>/ 下造一个模块（manifest.json + module.py）"""
    d = os.path.join(tree, "modules", dir_name)
    os.makedirs(d, exist_ok=True)
    mf = manifest if manifest is not None else {
        "id": module_id, "version": version,
        "provides": {"services": list(services)},
        "requires": {"services": [], "modules": []},
        "lazy": bool(lazy),
    }
    with io.open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(mf, f, ensure_ascii=False, indent=2)
    if register_code is None:
        register_code = ("def register(kernel):\n"
                         + "".join("    kernel.registry.register(%r, object(), owner=%r)\n"
                                   % (s, module_id) for s in services))
    with io.open(os.path.join(d, "module.py"), "w", encoding="utf-8") as f:
        f.write(register_code)
    return d


def boot(tree, modules_dir=None):
    return kernel.boot(base_dir=tree,
                       modules_dir=modules_dir or os.path.join(tree, "modules"),
                       log=kernel.Log(echo=False))


def main():
    print("=" * 62)
    print(u"微内核单测")
    print("=" * 62)

    # ==================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌============================== ① 装载
    print(u"\n== ① 按 manifest 发现并装载（服务、owner、事件）==")
    tree = tmpdir("load")
    write_module(tree, "alpha", "alpha", services=("alpha_svc",))
    write_module(tree, "beta", "beta", services=("beta_svc",))
    log = kernel.Log(echo=False)
    k = kernel.Kernel(base_dir=tree, modules_dir=os.path.join(tree, "modules"), log=log)
    seen = []
    k.bus.on("kernel.module", lambda p: seen.append(p["module"]))       # 前缀订阅
    booted = []
    k.bus.on("kernel.booted", lambda p: booted.append(p))
    k.boot()
    check(u"两个模块都装上了", k.summary() == {"alpha": "loaded", "beta": "loaded"},
          str(k.summary()))
    check(u"服务按 manifest 注册", k.registry.names() == ["alpha_svc", "beta_svc"],
          str(k.registry.names()))
    check(u"每个服务记下了 owner（卸载/回滚要用）",
          k.registry.owner_of("alpha_svc") == "alpha", k.registry.owner_of("alpha_svc"))
    check(u"每装好一个模块发一次事件（前缀订阅也收得到）", seen == ["alpha", "beta"], str(seen))
    check(u"kernel.booted 带模块清单与版本",
          bool(booted) and booted[0]["modules"] == ["alpha", "beta"],
          str(booted[:1]))
    check(u"装好之后 started 为真", k.started is True)

    # ================================================================ ② 降级
    print(u"\n== ② 一个模块炸了，内核照常启动（并说清是谁、什么错）==")
    tree = tmpdir("degrade")
    write_module(tree, "good", "good", services=("good_svc",))
    write_module(tree, "boom", "boom", services=("boom_svc",),
                 register_code=("def register(kernel):\n"
                                "    kernel.registry.register('boom_svc', object(), owner='boom')\n"
                                "    kernel.registry.register('boom_extra', object(), owner='boom')\n"
                                "    raise RuntimeError('故意炸在注册之后')\n"))
    write_module(tree, "bad_syntax", "bad_syntax", services=("bad_svc",),
                 register_code="def register(kernel)\n    pass\n")
    d = write_module(tree, "nomani", "nomani", services=("nomani_svc",))
    os.remove(os.path.join(d, "manifest.json"))
    log = kernel.Log(echo=False)
    k = kernel.boot(base_dir=tree, modules_dir=os.path.join(tree, "modules"), log=log)
    check(u"内核起来了（boot 没有把异常抛给调用方）", k.started is True)
    check(u"好模块照装", k.summary().get("good") == "loaded", str(k.summary()))
    check(u"register 抛异常的模块判失败", k.summary().get("boom") == "failed", str(k.summary()))
    check(u"模块语法的错误也只让它自己失败",
          k.summary().get("bad_syntax") == "failed", str(k.summary()))
    check(u"日志点名了模块 id 与错因",
          bool(log.find("boom")) and any("故意炸" in msg for _tag, msg in log.errors),
          str(log.errors[-2:]))
    check(u"缺 manifest 的目录不装、且日志写明原因",
          k.loader.status_of("nomani") == "absent" and bool(log.find("缺 manifest")),
          k.loader.status_of("nomani"))
    check(u"失败模块注册过的服务全被回滚（半装比不装更危险）",
          not k.registry.has("boom_svc") and not k.registry.has("boom_extra"),
          str(k.registry.names()))
    check(u"好模块的服务不受牵连", k.registry.has("good_svc"))
    check(u"失败清单可查（给界面/自检用）",
          set(k.failed_modules()) >= {"boom", "bad_syntax"}, str(k.failed_modules()))
    check(u"失败也发了 kernel.module.failed 事件", True)

    # ================================================================ ③ 服务注册
    print(u"\n== ③ 服务注册：重名不覆盖、找不到要说清楚、按 owner 清干净 ==")
    r = kernel.Registry(kernel.Log(echo=False))
    r.register("a", 1, owner="m1")
    check(u"重名注册返回 False", r.register("a", 2, owner="m2") is False)
    check(u"先注册的没有被覆盖", r.get("a") == 1, str(r.get("a")))
    try:
        r.require("nope")
        got = None
    except kernel.ServiceNotFound as e:
        got = e
    check(u"require 找不到时抛 ServiceNotFound", isinstance(got, kernel.ServiceNotFound))
    check(u"错误信息里带着可用服务清单（排查不用猜）",
          isinstance(got, kernel.ServiceNotFound) and "a" in str(got), str(got))
    r.register("b", 2, owner="m2")
    r.unregister_owner("m2")
    check(u"unregister_owner 按模块一次清干净", r.names() == ["a"], str(r.names()))

    print(u"\n== ③' manifest 对账：吹牛和偷给都算坏模块 ==")
    tree = tmpdir("reconcile")
    write_module(tree, "liar", "liar", services=("liar_svc",),
                 register_code="def register(kernel):\n    return None\n")
    write_module(tree, "sneaky", "sneaky", services=(),
                 register_code=("def register(kernel):\n"
                                "    kernel.registry.register('sneaky_svc', object(),"
                                " owner='sneaky')\n"))
    log = kernel.Log(echo=False)
    k = kernel.boot(base_dir=tree, modules_dir=os.path.join(tree, "modules"), log=log)
    check(u"声明了服务却没注册 → 失败", k.summary().get("liar") == "failed", str(k.summary()))
    check(u"失败原因写明缺哪个服务",
          "liar_svc" in (k.failed_modules().get("liar") or ""),
          k.failed_modules().get("liar"))
    check(u"注册了没声明的服务 → 也算失败", k.summary().get("sneaky") == "failed",
          str(k.summary()))
    check(u"偷注册的服务被回滚", not k.registry.has("sneaky_svc"), str(k.registry.names()))

    # ================================================================ ④ 事件总线
    print(u"\n== ④ 事件总线：精确/前缀/通配、退订、坏订阅者不传染、异步交给执行器 ==")
    bus = kernel.Bus(kernel.Log(echo=False))
    got = []
    bus.on("a.b", lambda p: got.append(("exact", p.get("n"))))
    bus.on("a", lambda p: got.append(("prefix", p.get("n"))))
    bus.on("*", lambda p: got.append(("all", p.get("n"))))
    bus.emit("a.b", n=1)
    check(u"精确 + 前缀 + 通配 三种订阅都收到",
          [g[0] for g in got] == ["exact", "prefix", "all"], str(got))
    bus.off("a.b")
    got.clear()
    bus.emit("a.b", n=2)
    check(u"off 之后那条订阅不再收到", [g[0] for g in got] == ["prefix", "all"], str(got))

    def boom(_p):
        raise ValueError(u"坏订阅者")
    ok = []
    bus.on("x", boom)
    bus.on("x", lambda p: ok.append(1))
    bus.emit("x")
    check(u"一个订阅者抛异常，另一个照收", ok == [1], str(ok))
    check(u"异常被记进统计（不会静默消失）", bus.stats["failed"] >= 1, str(bus.stats))

    two = []
    bus.on("y", lambda topic, payload: two.append((topic, payload.get("n"))))
    bus.emit("y", n=9)
    check(u"订阅者也可以要 (topic, payload) 两个参数", two == [("y", 9)], str(two))

    queued = []
    bus.set_executor(lambda fn: queued.append(fn) or "job-1")
    got_y = []
    bus.on("z", lambda p: got_y.append(p.get("n")))
    delivered = bus.emit_async("z", n=7)
    check(u"异步投递交给注入的执行器（内核自己不开线程池）",
          delivered is True and len(queued) == 1, str(len(queued)))
    queued[0]()
    check(u"执行器跑完后事件真的送到订阅者手上", got_y == [7], str(got_y))

    # ================================================================ ⑤ 重复 id
    print(u"\n== ⑤ 重复 id：只认第一个，后来者当场被拒 ==")
    tree = tmpdir("dup")
    write_module(tree, "one", "same_id", services=("s1",))
    write_module(tree, "two", "same_id", services=("s2",))
    log = kernel.Log(echo=False)
    k = kernel.boot(base_dir=tree, modules_dir=os.path.join(tree, "modules"), log=log)
    check(u"同 id 只装第一个", k.summary() == {"same_id": "loaded"}, str(k.summary()))
    check(u"重复被记下来（不是悄悄跳过）", len(k.loader.duplicates) == 1,
          str(k.loader.duplicates))
    check(u"日志说清谁的 id 被拒", bool(log.find("重复")), str(log.records()[-1:]))
    check(u"被拒那个的服务没有注册", k.registry.has("s1") and not k.registry.has("s2"),
          str(k.registry.names()))

    # ================================================================ ⑥ 懒加载
    print(u"\n== ⑥ 懒加载：启动不装，第一次取服务才装 ==")
    tree = tmpdir("lazy")
    write_module(tree, "lazyone", "lazyone", services=("lazy_svc",), lazy=True)
    k = boot(tree)
    check(u"启动时懒模块保持 lazy", k.summary().get("lazyone") == "lazy", str(k.summary()))
    check(u"启动时服务还不在注册表里", not k.registry.has("lazy_svc"))
    svc = k.service("lazy_svc")
    check(u"取服务把它装上了", svc is not None and k.summary().get("lazyone") == "loaded",
          str(k.summary()))
    check(u"再取一次不会重复装（同一个对象）", k.service("lazy_svc") is svc)

    # ================================================================ ⑦ 清单校验
    print(u"\n== ⑦ manifest 校验：五条硬规则逐条拒绝 ==")
    from kernel import manifest as M

    def bad(name, data, expect):
        m = M.Manifest(data, source=name)
        hit = (not m.ok) and any(expect in e for e in m.errors)
        check(u"拒绝：%s" % name, hit, str(m.errors))

    base = {"id": "x", "version": "1.0.0.0", "provides": {"services": ["x_svc"]},
            "requires": {"services": [], "modules": []}, "lazy": False}
    bad(u"version 只有三段", dict(base, version="1.0.0"), "四段")
    bad(u"lazy 不是布尔", dict(base, lazy="yes"), "lazy")
    bad(u"顶层出现不认识的字段", dict(base, provide={"services": []}), "不认识的顶层字段")
    bad(u"provides 里有不认识的表", dict(base, provides={"services": [], "routes2": []}),
        "provides")
    bad(u"id 不合规", dict(base, id="Bad-Id"), "id 不合规")
    bad(u"requires 自己", dict(base, requires={"services": [], "modules": ["x"]}), "自己")
    bad(u"服务名重复", dict(base, provides={"services": ["a", "a"]}), "重复")
    okm = M.Manifest(base)
    check(u"合法清单通过", okm.ok, str(okm.errors))
    check(u"合法清单的 to_dict 能回写", okm.to_dict()["id"] == "x")
    try:
        M.load_file(os.path.join(tmpdir("mf"), "nope.json"))
        raised = False
    except M.ManifestError:
        raised = True
    check(u"读不到清单文件抛 ManifestError（不返回半成品）", raised)

    # ================================================================ ⑧ 真仓库
    print(u"\n== ⑧ 真仓库的两个试点模块 + 路径口径对拍 ==")
    real = boot(tmpdir("real"), modules_dir=os.path.join(ROOT, "modules"))
    check(u"workshop 启动即装（常用，不懒）",
          real.summary().get("workshop") == "loaded", str(real.summary()))
    check(u"backup 标记为懒加载（很少用，启动不付代价）",
          real.summary().get("backup") == "lazy", str(real.summary()))
    bsvc = real.service("backup")
    check(u"取 backup 服务触发了懒加载",
          bsvc is not None and real.summary().get("backup") == "loaded", str(real.summary()))
    check(u"owner 记的都是模块 id",
          real.registry.owner_of("backup") == "backup"
          and real.registry.owner_of("workshop") == "workshop",
          "%s / %s" % (real.registry.owner_of("backup"), real.registry.owner_of("workshop")))
    check(u"kernel.paths 与 app_paths 口径一致（没有第二套路径规则）",
          kernel.paths.get_base_dir(ROOT) == os.path.abspath(ROOT)
          and kernel.paths.is_frozen() == app_paths.is_frozen())
    check(u"配置文件路径与 app_paths 完全一致",
          kernel.paths.get_config_file("x.json", ROOT)
          == app_paths.get_config_file("x.json"))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("KERNEL_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        _rc = main()
    finally:
        cleanup_tmp()
    sys.exit(_rc)
