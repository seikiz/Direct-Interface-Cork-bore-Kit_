# -*- coding: utf-8 -*-
"""kernel/loader.py —— 按 manifest 发现并加载模块（单个模块炸了，内核照常起来）

装一个模块要做的事（顺序不能换）：
    ① 读 manifest 并校验（不合规 → 这个模块不装，记日志，继续下一个）；
    ② 查 requires：依赖的模块是否已装、依赖的服务是否已注册（不满足 → 不装，记日志）；
    ③ import `<模块目录>/module.py` 并调用唯一的入口 `register(kernel)`；
    ④ 对账：register 期间**真正注册**的服务必须与 manifest.provides.services 完全一致
       （少注册 = 清单吹牛；多注册 = 偷偷给了没声明的服务。两者都回滚并判失败）；
    ⑤ 成功 → 发 `kernel.module.loaded`；失败 → 回滚 + 发 `kernel.module.failed`。

为什么用"合成包名"而不是 `import modules.xxx.module`：
    按名字 import 要求模块目录必须在 sys.path 上，且**全局唯一**。于是"换一个 modules 目录"
    （测试隔离、打包后的只读目录、以后从 zip 里加载）就没法做了 —— 两个目录里的同名模块
    会互相抢。这里给每个模块目录造一个只属于它的包名（`_dk_mod_<id>_<目录哈希>`），
    从文件系统直接装配。副作用是好的：外部**根本没有稳定的名字**可以 import 到
    `service.py` 这类内部文件，第 2 条铁律因此变成结构上的事实，而不只是纪律。
"""

import hashlib
import importlib
import os
import re
import sys
import traceback
import types

from . import manifest as _manifest

ENTRY_FILE = "module.py"           # 模块唯一入口（铁律 2）


class ModuleState(object):
    """一个模块的加载状态（装上了 / 没装上 / 懒着没装 / 清单坏了）"""

    def __init__(self, module_id, manifest=None, path=""):
        self.id = module_id
        self.manifest = manifest
        self.path = path
        self.status = "discovered"      # discovered/lazy/loaded/failed/skipped
        self.error = ""
        self.services = []
        self.module_obj = None
        self.package = ""

    @property
    def ok(self):
        return self.status == "loaded"

    def describe(self):
        if self.error:
            return "%s：%s" % (self.id, self.error)
        return "%s（%s）" % (self.id, self.status)

    def __repr__(self):
        return "<ModuleState %s %s>" % (self.id, self.status)


class ModuleLoader(object):
    """模块加载器：发现 → 排序 → 逐个装 → 对账。失败只记日志，不往上抛。"""

    def __init__(self, kernel, modules_dir, log=None):
        self.kernel = kernel
        self.log = log or getattr(kernel, "log", None)
        self.modules_dir = os.path.abspath(modules_dir or "")
        self.states = {}                # id -> ModuleState
        self.duplicates = []            # [(id, 保留的目录, 被丢弃的目录)]
        self.broken = []                # [(目录名, 原因)]：清单都读不出来的
        self._order = []

    # ---------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------- 发现
    def discover(self):
        """扫 modules_dir 下的子目录，读 manifest。返回按 id 排序的 Manifest 列表。"""
        self.states, self.duplicates, self.broken, self._order = {}, [], [], []
        if not os.path.isdir(self.modules_dir):
            self._info("模块目录不存在，按「没有模块」启动：%s" % self.modules_dir)
            return []
        found = []
        for name in sorted(os.listdir(self.modules_dir)):
            d = os.path.join(self.modules_dir, name)
            if not os.path.isdir(d) or name.startswith((".", "_")):
                continue
            entry = os.path.join(d, ENTRY_FILE)
            mpath = os.path.join(d, "manifest.json")
            if not os.path.isfile(mpath):
                if os.path.isfile(entry):
                    self.broken.append((name, "缺 manifest.json"))
                    self._err("模块 %r 缺 manifest.json，跳过（入口 %s 存在也不装）"
                              % (name, ENTRY_FILE))
                continue
            try:
                m = _manifest.load_file(mpath)
            except _manifest.ManifestError as e:
                self.broken.append((name, str(e)))
                self._err("模块 %r 的清单不合法，跳过：%s" % (name, "；".join(e.errors)))
                continue
            if not os.path.isfile(entry):
                self.broken.append((name, "缺 %s" % ENTRY_FILE))
                self._err("模块 %r 缺唯一入口 %s，跳过" % (m.id, ENTRY_FILE))
                continue
            found.append((m, d))
        # id 唯一：先到先得（按目录名排序，结果稳定），后来者判失败
        out = []
        for m, d in found:
            if m.id in self.states:
                kept = self.states[m.id].path
                self.duplicates.append((m.id, kept, d))
                self._err("模块 id 重复：%r 已被 %s 占用，%s 被拒绝"
                          % (m.id, os.path.basename(kept), os.path.basename(d)))
                continue
            st = ModuleState(m.id, m, d)
            self.states[m.id] = st
            out.append(m)
        self._order = self._topo(out)
        return self._order

    def _topo(self, manifests):
        """按 requires.modules 拓扑排序（依赖先装）。有环 → 保持剩余顺序并记警告。"""
        by_id = {m.id: m for m in manifests}
        done, out, visiting = set(), [], set()

        def visit(m, chain):
            if m.id in done:
                return
            if m.id in visiting:
                self._err("模块依赖成环：%s；环上的模块按原顺序装，失败会被逐个记下"
                          % " → ".join(chain + [m.id]))
                return
            visiting.add(m.id)
            for dep in m.requires["modules"]:
                if dep in by_id:
                    visit(by_id[dep], chain + [m.id])
            visiting.discard(m.id)
            if m.id not in done:
                done.add(m.id)
                out.append(m)

        for m in sorted(manifests, key=lambda x: x.id):
            visit(m, [])
        return out

    # ---------------------------------------------------------------- 加载
    def load_all(self):
        """装所有非 lazy 模块；单个失败不影响其它，更不影响内核。"""
        if not self._order:
            self.discover()
        for m in self._order:
            st = self.states[m.id]
            if st.status in ("loaded", "failed"):
                continue
            if m.lazy:
                st.status = "lazy"
                self._info("模块 %s 标记为懒加载，等第一次取服务时再装" % m.id)
                continue
            self.load(m.id)
        return self.states

    def ensure(self, module_id):
        """取服务前的"按需加载"：懒模块在这里才真正 register。"""
        st = self.states.get(module_id)
        if st is None:
            if not self._order:
                self.discover()
            st = self.states.get(module_id)
        if st is None:
            return None
        if st.status in ("lazy", "discovered"):
            self.load(module_id)
        return st

    def load(self, module_id, retry=False):
        """装一个模块。**任何异常都在这里被吃掉**，只留下状态与日志。"""
        st = self.states.get(module_id)
        if st is None:
            return None
        if st.status == "loaded" and not retry:
            return st
        if st.status == "failed" and not retry:
            return st
        m = st.manifest
        try:
            self._check_requires(st)
            module_obj = self._import_entry(st)
            register = getattr(module_obj, "register", None)
            if not callable(register):
                raise RuntimeError("%s 里没有 register(kernel) 入口" % ENTRY_FILE)
            with self.kernel.registry.track() as tracked:
                register(self.kernel)
            self._reconcile(st, tracked.added)
            st.module_obj = module_obj
            st.services = list(tracked.added)
            st.status = "loaded"
            st.error = ""
            self._info("模块 %s v%s 装载成功，提供服务：%s"
                       % (m.id, m.version, "、".join(st.services) or "（无）"))
            self.kernel.bus.emit("kernel.module.loaded", module=m.id,
                                 version=m.version, services=st.services)
            return st
        except Exception as e:
            st.status = "failed"
            st.error = "%s: %s" % (type(e).__name__, str(e)[:300])
            self._rollback(st)
            self._err("模块 %s 装载失败（内核继续启动）：%s" % (m.id, st.error))
            try:
                traceback.print_exc()
            except Exception:
                pass
            self.kernel.bus.emit("kernel.module.failed", module=m.id, error=st.error)
            return st

    # ---- 步骤 ----
    def _check_requires(self, st):
        req = st.manifest.requires
        for dep in req["modules"]:
            d = self.states.get(dep)
            if d is None:
                raise RuntimeError("依赖的模块 %r 不存在" % dep)
            if not d.ok:
                if d.status in ("lazy", "discovered"):
                    self.load(dep)
                if not d.ok:
                    raise RuntimeError("依赖的模块 %r 没装上（%s）" % (dep, d.error or d.status))
        for svc in req["services"]:
            if not self.kernel.registry.has(svc):
                raise RuntimeError("依赖的服务 %r 没有注册" % svc)

    def _import_entry(self, st):
        """把 <模块目录>/module.py 当成合成包里的子模块 import 进来。"""
        pkg_name = _package_name(st.path, st.id)
        st.package = pkg_name
        pkg = sys.modules.get(pkg_name)
        if pkg is None:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = [st.path]           # 关键：让 `from .service import X` 能解析
            pkg.__package__ = pkg_name
            pkg.__file__ = os.path.join(st.path, "__init__.py")
            pkg.__dick_module_id__ = st.id
            sys.modules[pkg_name] = pkg
        full = pkg_name + "." + ENTRY_FILE[:-3]
        try:
            return importlib.import_module(full)
        except Exception:
            self._purge(pkg_name)              # 不留半个模块在 sys.modules 里
            raise

    def _reconcile(self, st, registered):
        """manifest 说提供的服务 vs 实际注册的服务，必须一模一样。"""
        want = set(st.manifest.services())
        got = set(registered)
        missing = sorted(want - got)
        extra = sorted(got - want)
        if missing or extra:
            parts = []
            if missing:
                parts.append("清单声明了却没注册：%s" % "、".join(missing))
            if extra:
                parts.append("注册了却没在清单里声明：%s" % "、".join(extra))
            raise RuntimeError("provides.services 对不上（%s）" % "；".join(parts))

    def _rollback(self, st):
        """把失败模块注册过的服务摘掉：半装的模块比没装更危险。"""
        try:
            names = self.kernel.registry.unregister_owner(st.id)
        except Exception:
            names = []
        if names:
            self._info("已回滚模块 %s 注册的服务：%s" % (st.id, "、".join(names)))
        st.services = []
        if st.package:
            self._purge(st.package)

    @staticmethod
    def _purge(pkg_name):
        for name in [n for n in list(sys.modules) if n == pkg_name
                     or n.startswith(pkg_name + ".")]:
            sys.modules.pop(name, None)

    # ---------------------------------------------------------------- 查询
    def loaded_ids(self):
        return sorted(i for i, s in self.states.items() if s.ok)

    def failed(self):
        return {i: s.error for i, s in self.states.items() if s.status == "failed"}

    def status_of(self, module_id):
        st = self.states.get(module_id)
        return st.status if st else "absent"

    def summary(self):
        return {i: s.status for i, s in sorted(self.states.items())}

    # ---------------------------------------------------------------- 日志
    def _info(self, msg):
        if self.log:
            self.log.info(msg, "loader")

    def _err(self, msg):
        if self.log:
            self.log.error(msg, "loader")


def _package_name(module_dir, module_id):
    h = hashlib.sha1(os.path.abspath(module_dir).encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r"[^a-z0-9_]", "_", str(module_id or "m").lower())
    return "_dk_mod_%s_%s" % (safe, h)
