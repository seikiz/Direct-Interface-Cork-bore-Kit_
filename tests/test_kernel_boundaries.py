# -*- coding: utf-8 -*-
"""铁律的机器化：`ARCHITECTURE.md` 的四条铁律 + 判定器自检 + 试点模块真的能装。

为什么这份测试是"唯一"的执法者
------------------------------
文档会被跳过，自觉会被疲劳吃掉，只有红灯躲不掉。所以这里把边界拆成三类断言：
  A. **真实仓库干净**：依赖方向、单入口、内核词表一条都不许违反；
  B. **判定器自检**：故意造一份违规样本，判定器必须抓到 —— 否则"0 违规"可能只是
     "根本没在查"（这是所有静态检查最常见的假绿）；
  C. **试点模块真能用**：经 loader 装上、register 成功、脱离壳层也能干活。

跑法：python tests\\test_kernel_boundaries.py
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import kernel                          # noqa: E402
import audit_kernel_boundaries as audit  # noqa: E402
import crypto_core                     # noqa: E402

PASS = 0
FAIL = 0
_TMP = []
_TEMP_BASE = None


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

    本仓库的 venv（Windows Store 版 Python 3.11）在这台机器上无法在 %TEMP% 建目录
    （WinError 5），`tempfile.mkdtemp` 会重试到超时、`gettempdir()` 会退化成当前目录。
    所以显式挑一个真能写的位置，清理责任放进 finally。
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
    d = tempfile.mkdtemp(prefix="dick_kb_%s_" % label, dir=_TEMP_BASE)
    _TMP.append(d)
    return d


def _writable_dir(base):
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".probe_%d" % os.getpid())
        os.makedirs(probe, exist_ok=True)
        os.rmdir(probe)
        return True
    except Exception:
        return False


def cleanup_tmp():
    """跑完删干净（工作区不许留垃圾目录）"""
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)
    _TMP[:] = []
    if _TEMP_BASE and os.path.abspath(_TEMP_BASE).startswith(os.path.abspath(ROOT)):
        shutil.rmtree(_TEMP_BASE, ignore_errors=True)


def rules_of(violations):
    return {v["rule"] for v in violations}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def fake_repo(label):
    """造一棵最小的仓库：kernel/ + modules/alpha + modules/beta（都合法）"""
    root = tmpdir(label)
    write(os.path.join(root, "kernel", "__init__.py"), "")
    write(os.path.join(root, "kernel", "core.py"), "import os\n")
    write(os.path.join(root, "DICK_core.py"), "")
    for mid in ("alpha", "beta"):
        d = os.path.join(root, "modules", mid)
        write(os.path.join(d, "manifest.json"), json.dumps({
            "id": mid, "version": "1.0.0.0", "provides": {"services": [mid + "_svc"]},
            "requires": {"services": [], "modules": []}, "lazy": False}, ensure_ascii=False))
        write(os.path.join(d, "module.py"),
              "def register(kernel):\n"
              "    kernel.registry.register(%r, object(), owner=%r)\n" % (mid + "_svc", mid))
    return root


# ======================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌============================== A. 真实仓库
def test_real_repo():
    print(u"\n== A. 真实仓库：五条边界一条都不许破 ==")
    res = audit.scan()
    by_rule = res["by_rule"]
    check(u"整份审计 0 违规", not res["violations"],
          u"；".join("%s@%s" % (v["rule"], v["file"]) for v in res["violations"][:5]))
    check(u"铁律 1：内核不 import 模块/业务（kernel-modules / kernel-business = 0）",
          not ({"kernel-modules", "kernel-business"} & set(by_rule)), str(by_rule))
    check(u"铁律 1：模块不跨模块、不碰壳层、不碰业务（module-cross/shell/business = 0）",
          not ({"module-cross", "module-shell", "module-business"} & set(by_rule)), str(by_rule))
    check(u"铁律 1：被扫到了（内核与模块文件数不是 0，否则「干净」没意义）",
          res["counts"]["kernel_files"] >= 8 and res["counts"]["module_files"] >= 4,
          str(res["counts"]))
    check(u"铁律 2：外部没有 import 模块内部（module-entry = 0）",
          "module-entry" not in by_rule, str(by_rule))
    check(u"铁律 3：内核代码里没有业务词（kernel-vocab = 0）",
          "kernel-vocab" not in by_rule, str(by_rule))
    check(u"反绕过：没有 # noqa / except ImportError 这类静默豁免",
          not ({"bypass-noqa", "bypass-import"} & set(by_rule)), str(by_rule))
    check(u"低耦：块里没有模块级可变全局（shared-state = 0）",
          "shared-state" not in by_rule, str(by_rule))

    shell_path = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
    shell = io.open(shell_path, encoding="utf-8", errors="replace").read()
    check(u"装配方向正确：壳层 import 内核，并且经内核取两个试点服务",
          "import kernel" in shell
          and '_kernel_service("workshop")' in shell
          and '_kernel_service("backup")' in shell)
    check(u"壳层只留门面：原来的 17 个工坊接口不再自己发请求",
          "_ws_call(\"GET\", self._ws_url(\"/api/cards/list\")" not in shell)

    for mid in ("backup", "workshop"):
        d = os.path.join(ROOT, "modules", mid)
        files = sorted(os.listdir(d))
        check(u"模块 %s 的入口只有 module.py（其余是内部实现）" % mid,
              "module.py" in files and "manifest.json" in files, str(files))


# ==================================================================== B. 判定器自检
def test_detector_selfcheck():
    print(u"\n== B. 判定器自检：故意造的违规必须被抓到 ==")
    root = fake_repo("selfcheck")
    kfile = os.path.join(root, "kernel", "leak.py")
    mfile = os.path.join(root, "modules", "alpha", "leaky.py")

    # --- 内核 import 了模块 ---
    write(kfile, "import modules.beta.module\n")
    got = rules_of(audit.scan_imports(root))
    check(u"内核 import modules.* → kernel-modules", "kernel-modules" in got, str(got))
    os.remove(kfile)

    # --- 内核 import 了业务模块 ---
    write(kfile, "import DICK_core\n")
    got = rules_of(audit.scan_imports(root))
    check(u"内核 import 业务模块 → kernel-business", "kernel-business" in got, str(got))
    os.remove(kfile)

    # --- 模块 import 另一个模块 ---
    write(mfile, "import modules.beta.module\n")
    got = rules_of(audit.scan_imports(root))
    check(u"模块跨模块 import → module-cross", "module-cross" in got, str(got))

    # --- 模块 import 壳层 ---
    write(mfile, "import net\n")
    got = rules_of(audit.scan_imports(root))
    check(u"模块 import 壳层 → module-shell", "module-shell" in got, str(got))

    # --- 模块用相对路径越出目录 ---
    write(mfile, "from ..beta import module\n")
    got = rules_of(audit.scan_imports(root))
    check(u"模块 from .. 越界 → module-cross", "module-cross" in got, str(got))

    # --- 模块 import 业务模块 ---
    write(mfile, "import DICK_core\n")
    got = rules_of(audit.scan_imports(root))
    check(u"模块 import 业务模块 → module-business", "module-business" in got, str(got))
    os.remove(mfile)

    # --- 内核代码里的业务词被抓、注释里的不抓 ---
    write(kfile, 'def f():\n    return "\u5de5\u574a"\n')
    got = rules_of(audit.scan_kernel_vocab(root))
    check(u"内核代码里出现业务词 → kernel-vocab", "kernel-vocab" in got, str(got))
    write(kfile, 'def f():\n    # \u5de5\u574a\u5ba2\u6237\u7aef\u7684\u6ce8\u91ca\u5728\u8fd9\u91cc\uff08\u5141\u8bb8\uff09\n'
                 '    """\u5de5\u574a docstring \u4e5f\u5141\u8bb8"""\n    return 1\n')
    got = rules_of(audit.scan_kernel_vocab(root))
    check(u"业务词只出现在注释/docstring → 不报（白名单生效）", "kernel-vocab" not in got, str(got))
    os.remove(kfile)

    # --- 内核文档也不许点业务的名（注释白名单只在 .py 里有效）---
    docfile = os.path.join(root, "kernel", "NOTES.md")
    write(docfile, u"# \u8bf4\u660e\n\n\u8fd9\u91cc\u4e3e\u4f8b\u7528\u4e86\u5de5\u574a\u8fd9\u4e2a\u8bcd\n")
    got = rules_of(audit.scan_kernel_vocab(root))
    check(u"内核文档里出现业务词 → kernel-vocab（文档也不例外）", "kernel-vocab" in got, str(got))
    write(docfile, u"# \u8bf4\u660e\n\n\u4e3e\u4f8b\u4e00\u5f8b\u7528\u6a21\u5757 id\uff1aworkshop / backup\n")
    got = rules_of(audit.scan_kernel_vocab(root))
    check(u"内核文档只写模块 id → 不报", "kernel-vocab" not in got, str(got))
    os.remove(docfile)

    # --- 外部用绝对名字 import 模块内部 ---
    write(os.path.join(root, "main.py"), "from modules.alpha.service import X\n")
    got = rules_of(audit.scan_entry_points(root))
    check(u"外部 import 模块内部 → module-entry", "module-entry" in got, str(got))
    os.remove(os.path.join(root, "main.py"))

    # --- 块里的模块级可变全局（跨块共享可变状态的载体）---
    write(mfile, "CACHE = {}\n\ndef f():\n    return CACHE\n")
    got = rules_of(audit.scan_shared_state(root))
    check(u"块里出现模块级 dict 全局 → shared-state", "shared-state" in got, str(got))
    write(mfile, "CACHE = ()\n\nclass A(object):\n    pass\n")       # 元组/类不算可变全局
    got = rules_of(audit.scan_shared_state(root))
    check(u"元组常量不算可变全局 → 不报", "shared-state" not in got, str(got))
    write(mfile, "X = 1\n\ndef f():\n    global X\n    X = 2\n")
    got = rules_of(audit.scan_shared_state(root))
    check(u"出现 global 语句 → shared-state", "shared-state" in got, str(got))
    os.remove(mfile)

    # --- 清单不合规 ---
    write(os.path.join(root, "modules", "beta", "manifest.json"), json.dumps({
        "id": "beta", "version": "1.0.0", "provides": {"services": []},
        "requires": {"services": [], "modules": []}, "lazy": False}, ensure_ascii=False))
    got = rules_of(audit.scan_manifests(root))
    check(u"清单 version 三段 → manifest-bad", "manifest-bad" in got, str(got))
    write(os.path.join(root, "modules", "beta", "manifest.json"), json.dumps({
        "id": "not_beta", "version": "1.0.0.0", "provides": {"services": []},
        "requires": {"services": [], "modules": []}, "lazy": False}, ensure_ascii=False))
    got = rules_of(audit.scan_manifests(root))
    check(u"清单 id 与目录名不一致 → manifest-bad", "manifest-bad" in got, str(got))

    # --- 反绕过 ---
    write(mfile, "# \u8fd9\u91cc\u4e0d\u8be5\u6709 noqa\ndef f():\n    return 1  # noqa\n")
    got = rules_of(audit.scan_bypass(root))
    check(u"# noqa → bypass-noqa", "bypass-noqa" in got, str(got))
    write(mfile, "try:\n    import os\nexcept ImportError:\n    pass\n")
    got = rules_of(audit.scan_bypass(root))
    check(u"except ImportError 放行 import → bypass-import", "bypass-import" in got, str(got))
    os.remove(mfile)

    # --- 白名单缺 reason ---
    audit.SHARED_LEAF_LIBS["bogus_leaf"] = {"reason": "", "owner": "modules/x"}
    try:
        got = rules_of(audit.scan_whitelist_health())
        check(u"白名单条目没有 reason → whitelist-reason", "whitelist-reason" in got, str(got))
    finally:
        audit.SHARED_LEAF_LIBS.pop("bogus_leaf", None)


# ==================================================================== C. 试点模块
class FakeResp(object):
    def __init__(self, code=200, payload=None, text="", content=b"", headers=None):
        self.status_code = code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload, ensure_ascii=False)
        self.content = content or self.text.encode("utf-8")
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeHost(object):
    """工坊模块的宿主端口（Port）最小实现 —— 这就是"模块不认识壳层"的证明：

    这份假宿主里没有一行来自 Direct-Interface Cork-bore Kit.py，
    模块照样能列出作品、预览本地卡、删除文件。壳层换掉也不影响模块。
    """
    WS_KINDS = {"\u89d2\u8272\u5361": ("cards", "saves", "\U0001f3ad"),
                "\u4e16\u754c\u5361": ("worlds", "worlds", "\U0001f30d"),
                "\u4e16\u754c\u5361\u5305": ("packs", "packs", "\U0001f4e6")}

    def __init__(self, root):
        self.root = root
        self.save_dir = os.path.join(root, "saves")
        self.world_dir = os.path.join(root, "worlds")
        self.pack_dir = os.path.join(root, "packs")
        for d in (self.save_dir, self.world_dir, self.pack_dir):
            os.makedirs(d, exist_ok=True)
        self.calls = []
        self.saved = None
        self.reloaded = []
        self.plugin_manager = None

    # 资源类型 → 目录
    def _ws_kind(self, rtype):
        return self.WS_KINDS.get(str(rtype or "").strip(), self.WS_KINDS["\u4e16\u754c\u5361"])

    def _ws_local_dir(self, rtype):
        _api, folder, _icon = self._ws_kind(rtype)
        return {"saves": self.save_dir, "worlds": self.world_dir,
                "packs": self.pack_dir}[folder]

    # 连接/能力/节流
    def _ws_load_config(self):
        return {"server_url": "http://w.test", "api_key": "k", "proxy": ""}

    def _ws_save_config(self, url, key, proxy=None):
        self.saved = (url, key, proxy)

    def _ws_active_server(self):
        return "http://w.test"

    def _ws_url(self, path):
        return self._ws_active_server() + path

    def _ws_headers(self):
        return {}

    def _ws_caps(self):
        return {"types": ["cards", "worlds"], "features": [], "limits": {}, "old": False}

    def _ws_has_gzip(self):
        return False

    def _ws_xfer_slot(self):
        return contextlib.nullcontext()

    def _ws_retry_after(self, resp):
        return 0.01

    def _ws_gz_body(self, resp):
        return resp.content

    def _ws_http_err(self, resp, what="\u64cd\u4f5c"):
        return {"ok": False, "err": "%s没成功" % what}

    def _ws_call(self, method, url, **kw):
        self.calls.append((method, url))
        if url.endswith("/api/cards/list"):
            return FakeResp(payload=[{"id": "c1", "name": "一张卡"}])
        if url.endswith("/api/worlds/list"):
            return FakeResp(payload=[])
        return FakeResp(payload={})

    # 上传前净身 / 文件名 / 界面刷新
    def ws_strip_local_state(self, raw):
        return raw, []

    def ws_header_name(self, name):
        return name

    def _safe_name(self, name):
        return name

    def _reload_roles(self):
        self.reloaded.append("roles")

    def _reload_worlds(self):
        self.reloaded.append("worlds")


def test_pilots():
    print(u"\n== C. 两个试点模块：loader 装得上、register 成功、脱离壳层也能干活 ==")
    k = kernel.boot(base_dir=tmpdir("pilot"), modules_dir=os.path.join(ROOT, "modules"),
                    log=kernel.Log(echo=False))
    check(u"loader 把 workshop 装上了", k.loader.status_of("workshop") == "loaded",
          str(k.summary()))
    check(u"workshop 的入口函数 register 真的被调过（module_obj 里能拿到）",
          callable(getattr(getattr(k.module_state("workshop"), "module_obj", None),
                           "register", None)))
    check(u"manifest 声明的服务与真实注册一致",
          k.module_state("workshop").services == ["workshop"],
          str(k.module_state("workshop").services))
    k.service("backup")
    check(u"backup 懒加载后同样注册成功",
          k.loader.status_of("backup") == "loaded" and k.registry.has("backup"),
          str(k.summary()))

    # ---- 工坊模块：假宿主 ----
    host = FakeHost(tmpdir("ws_host"))
    write(os.path.join(host.save_dir, "c1.json"), '{"name": "一张卡"}')
    write(os.path.join(host.pack_dir, "p1.json"), "{}")
    ws = k.service("workshop").bind(host)
    st = ws.state()
    check(u"工坊模块在假宿主上能列出本地作品（不依赖 pywebview / App）",
          st["local_roles"] == ["c1.json"] and st["local_packs"] == ["p1.json"]
          and st["has_key"] is True, str(st))
    listed = ws.list_items()
    check(u"在线列表照旧按服务器能力清单决定问哪几种（老服务器不问 packs）",
          listed.get("ok") is True and listed.get("cards") == [{"id": "c1", "name": "一张卡"}]
          and "packs" not in listed, str(listed))
    check(u"请求确实走的是宿主的传输端口（URL 可核对）",
          ("GET", "http://w.test/api/cards/list") in host.calls, str(host.calls))
    prev = ws.preview("\u89d2\u8272\u5361", "c1.json")
    check(u"预览读的是本地卡内容", prev.get("ok") is True and "一张卡" in prev["preview"],
          str(prev)[:120])
    ws.save_conn("http://w.test", "k2", "http://127.0.0.1:7890")
    check(u"存连接信息仍走宿主的加密落盘实现", host.saved == ("http://w.test", "k2",
                                                              "http://127.0.0.1:7890"),
          str(host.saved))
    deleted = ws.delete_local("\u89d2\u8272\u5361", "c1.json")
    check(u"删除本地文件后要求宿主刷新角色列表",
          deleted.get("ok") is True and host.reloaded == ["roles"], str(host.reloaded))

    # ---- 备份模块 ----
    # 加解密是**宿主能力**（ARCHITECTURE.md 十二）：这里把真 crypto_core 注入，
    # 所以下面验的仍是"真容器格式没变"，而不是自检里的替身。
    bk = k.service("backup").bind(None, crypto_core)
    ok_weak, err_weak = bk.require_strong("123456")
    ok_strong, _e = bk.require_strong("Abcdefgh1234Xy")
    check(u"弱口令被拦下，且文案与搬家前一致",
          ok_weak is False and "\u53e3\u4ee4\u4e0d\u591f\u5f3a" in err_weak, err_weak)
    check(u"强口令放行", ok_strong is True)
    blob = bk.seal(b"hello-dick", "Abcdefgh1234Xy", iters=1000)
    check(u"容器格式没变（老加解密路线仍能解 module 产出的文件）",
          crypto_core.decrypt("Abcdefgh1234Xy", blob) == b"hello-dick")
    check(u"自己封自己解往返一致", bk.unseal(blob, "Abcdefgh1234Xy") == b"hello-dick")
    check(u"容器头信息可读（算法/迭代数都是公开字段）",
          bk.info(blob).get("algo") == "AES-256-GCM", str(bk.info(blob)))
    try:
        bk.unseal(blob, "wrong-password-xx")
        raised = ""
    except Exception as e:
        raised = str(e)
    check(u"错口令 → ValueError（不会静默给出坏数据）",
          "口令错误" in raised or "篡改" in raised, raised)

    # ---- 备份还原：铺盘规则（含路径穿越防护）----
    tree = tmpdir("restore")
    dirs = {k2: os.path.join(tree, k2) for k2 in ("saves", "worlds", "personas", "codex")}
    dirs["root"] = tree
    dirs["config_file"] = os.path.join(tree, "config.json")
    for d in dirs.values():
        if not d.endswith(".json"):
            os.makedirs(d, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("DICK_备份_x/saves/a.json", "{}")
        z.writestr("DICK_备份_x/worlds/w.json", "{}")
        z.writestr("DICK_备份_x/config.json", "{}")
        z.writestr("DICK_备份_x/../evil.json", "{}")      # 路径穿越，必须被丢掉
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
        restored = bk.restore_zip(z, os.path.join(tree, "bak"), dirs)
    check(u"还原铺盘按目录计数正确",
          restored == {"saves": 1, "worlds": 1, "personas": 0, "config": 1, "codex": 0},
          str(restored))
    check(u"路径穿越条目被丢掉（没有写到根目录之外）",
          not os.path.exists(os.path.join(tree, "evil.json")))
    check(u"文件真的落到了 saves/ 下",
          os.path.isfile(os.path.join(dirs["saves"], "a.json")))


# ==================================================================== D. 棘轮
def test_ratchet():
    print(u"\n== D. 棘轮：白名单只许缩短、行数上限只许下调 ==")
    base_path = audit.BASELINE_DEFAULT
    check(u"基线文件存在（没有基线就不算钉住）", os.path.isfile(base_path), base_path)
    old = {}
    if os.path.isfile(base_path):
        old = json.loads(io.open(base_path, encoding="utf-8").read())
    check(u"基线里有 schema / violations / whitelist / whitelist_count / limits",
          set(old) >= {"schema", "violations", "whitelist", "whitelist_count", "limits"},
          str(sorted(old)))
    cur = audit.scan()
    check(u"违规数没有超过基线", len(cur["violations"]) <= len(old.get("violations") or []),
          "%d vs %d" % (len(cur["violations"]), len(old.get("violations") or [])))
    check(u"白名单条数没有超过基线（只许缩短）",
          cur["whitelist_count"] <= int(old.get("whitelist_count") or 0),
          "%d vs %s" % (cur["whitelist_count"], old.get("whitelist_count")))
    old_keys = set(old.get("whitelist") or [])
    cur_keys = {e["key"] for e in cur["whitelist"]}
    check(u"没有出现基线里没有的白名单新条目", cur_keys <= old_keys,
          str(sorted(cur_keys - old_keys)))
    check(u"每条白名单都写了 reason", all(e["reason"] for e in cur["whitelist"]))

    old_limits = old.get("limits") or {}
    raised = [p for p, info in cur["limits"].items()
              if old_limits.get(p) and info["limit"] > int(old_limits[p])]
    check(u"没有行数上限被调高", not raised, str(raised))
    over = [p for p, info in cur["limits"].items()
            if info["lines"] is not None and info["lines"] > info["limit"]]
    check(u"没有文件超过行数上限", not over, str(over))
    check(u"上限表覆盖了派单要求的五个巨型文件",
          {"web/index.html", "net.py", "DICK_core.py",
           "DICK-Android/app/src/main/java/com/dick/app/App.kt",
           "DICK-Android/app/src/main/java/com/dick/app/Dialogs.kt"} <= set(cur["limits"]),
          str(sorted(cur["limits"])))


def test_ratchet_actually_red():
    print(u"\n== D'. 棘轮真的会红（不是装饰）：造一份更严的基线，比对必须非 0 ==")
    d = tmpdir("ratchet")
    res = audit.scan()
    limits = {k: v["limit"] for k, v in res["limits"].items()}

    # (1) 白名单被调长 → 红。当前白名单可以已经是 0 条（欠债还完了），所以这里
    #     临时加一条"当前白名单"再与 0 条的基线比 —— 断言的是棘轮行为，不是仓库现状。
    p1 = os.path.join(d, "base_wl.json")
    write(p1, json.dumps({"schema": 1, "violations": [], "whitelist": [],
                          "whitelist_count": 0, "limits": limits}, ensure_ascii=False))
    audit.SHARED_LEAF_LIBS["probe_leaf"] = {
        "reason": "棘轮自检用的临时白名单条目，跑完立刻摘掉", "owner": "tests"}
    try:
        grown = audit.scan()
        check(u"白名单变长 → 比对返回非 0", audit.compare_baseline(grown, p1) != 0)
    finally:
        audit.SHARED_LEAF_LIBS.pop("probe_leaf", None)

    # (2) 行数上限被调高 → 红（基线里某个上限比现在小）
    p2 = os.path.join(d, "base_lim.json")
    tighter = dict(limits)
    only = sorted(tighter)[0]
    tighter[only] = max(1, int(tighter[only]) - 1)
    write(p2, json.dumps({"schema": 1, "violations": [], "whitelist": ["shared-leaf:crypto_core"],
                          "whitelist_count": 1, "limits": tighter}, ensure_ascii=False))
    check(u"行数上限被调高 → 比对返回非 0", audit.compare_baseline(res, p2) != 0)

    # (3) 完全一致 → 绿（否则上面两条"红"没有对照）
    p3 = os.path.join(d, "base_ok.json")
    write(p3, json.dumps(audit._baseline_of(res), ensure_ascii=False))
    check(u"与基线一致 → 比对返回 0", audit.compare_baseline(res, p3) == 0)


def test_cli():
    print(u"\n== E. 命令行入口（CI 与本地跑的是同一条路）==")
    tool = os.path.join(ROOT, "tools", "audit_kernel_boundaries.py")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, tool], capture_output=True, env=env, cwd=ROOT,
                       timeout=180)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    check(u"无参数跑 → 退出码 0（当前 0 违规）", r.returncode == 0, out[-300:])
    r2 = subprocess.run([sys.executable, tool, "--json"], capture_output=True, env=env,
                        cwd=ROOT, timeout=180)
    try:
        data = json.loads(r2.stdout.decode("utf-8", "replace"))
        ok_json = isinstance(data.get("violations"), list)
    except Exception as e:
        data, ok_json = {}, False
        print("        JSON 解析失败：%s" % str(e)[:120])
    check(u"--json 输出可被机器解析（CI 能拿它当门禁）", ok_json, str(data)[:120])


def test_block_protocol():
    """ARCHITECTURE.md 十、十一：块协议与懒人验收必须真的能跑"""
    print(u"\n== F. 积木协议：block.json + 块自检 + 一条命令验收 ==")
    import blocks_graph as bg
    blocks = bg.blocks()
    check(u"三个块都有 block.json（kernel + 两个试点）",
          set(blocks) == {"kernel", "backup", "workshop"}, str(sorted(blocks)))
    for bid, info in sorted(blocks.items()):
        bj = info.get("block") or {}
        check(u"块 %s 声明了 files / selftest / interface 三样" % bid,
              bool(bj.get("files")) and bool((bj.get("selftest") or {}).get("cmd"))
              and bool((bj.get("interface") or {}).get("methods")), str(sorted(bj)))

    graph = bg.check()
    check(u"依赖图无环、无坏边、无接口漂移", not graph["problems"], str(graph["problems"]))
    check(u"接口签名哈希算得出来（3 个块）", len(graph["hashes"]) == 3, str(graph["hashes"]))

    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=ROOT)
    tool = os.path.join(ROOT, "tools", "accept.py")
    r = subprocess.run([sys.executable, tool], capture_output=True, env=env, cwd=ROOT,
                       timeout=300)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    check(u"tools/accept.py 退出码 0", r.returncode == 0, out[-500:])
    check(u"验收最后一行是 ALL_BLOCKS_OK，且带 portable 汇总（ARCHITECTURE.md 十二）",
          bool(lines) and lines[-1].startswith("ALL_BLOCKS_OK") and "portable:" in lines[-1],
          lines[-1] if lines else "")
    check(u"验收报告里有搬家测试那一段", u"搬家测试" in out, out[-300:])
    check(u"验收报告带变更摘要（新增/删除/行数/接口签名）",
          u"接口签名变化" in out and u"行数变化" in out, out[-300:])
    for bid in ("kernel", "backup", "workshop"):
        r2 = subprocess.run([sys.executable, "-m", bid if bid == "kernel"
                             else "modules." + bid, "--selftest"],
                            capture_output=True, env=env, cwd=ROOT, timeout=120)
        txt = r2.stdout.decode("utf-8", "replace")
        json_line = [ln for ln in txt.splitlines() if ln.strip().startswith("{")]
        ok = False
        if r2.returncode == 0 and json_line:
            try:
                d = json.loads(json_line[-1])
                ok = d.get("block") == bid and d.get("fail") == 0 and d.get("ms", 9999) < 2000
            except Exception:
                ok = False
        check(u"块 %s 的 `--selftest` 输出一行 JSON 且通过、<2s" % bid, ok, txt[-200:])


def main():
    print("=" * 62)
    print(u"微内核边界铁律（ARCHITECTURE.md 的执法者）")
    print("=" * 62)
    try:
        test_real_repo()
        test_detector_selfcheck()
        test_pilots()
        test_ratchet()
        test_ratchet_actually_red()
        test_cli()
        test_block_protocol()
    finally:
        cleanup_tmp()
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("KERNEL_BOUNDARIES_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
