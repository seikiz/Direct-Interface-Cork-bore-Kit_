# -*- coding: utf-8 -*-
"""modules/backup/selftest.py —— backup 块的自检（闭环：不惊动任何别的块）

`python -m modules.backup --selftest`  → 成功时**只有一行** JSON：
    {"block": "backup", "pass": 13, "fail": 0, "ms": 20, "deps": []}

失败时在这行之后追加：FAIL <case>: <原因>  +  一行最小复现命令
（ARCHITECTURE.md 十一：自检失败要能一条命令重跑那一处）。

硬规则（写在这里，改代码的人先看到）：
  · **不许启动别的块**：这里只 import 本块，不 boot 内核；
  · **不许连网、不许占端口**：加密替身与铺盘都是纯内存/本地操作，一条 socket 都不开；
  · **< 2s**：加密是替身，铺盘只写临时目录；
  · 每个 case 都是"输入 → 输出/异常"的闭环，且至少覆盖一条**坏输入**路径。

为什么自检里的加解密是替身（`FakeCrypto`）而不是真 AES：
    ARCHITECTURE.md 十二：块只许依赖 stdlib + kernel。真 AES（`crypto_core` +
    `cryptography`）是**宿主能力**，由 `bind(host, crypto=…)` 注入 —— 块搬去别的项目时，
    那个项目自己给实现。所以自检要证明的是"块有没有把宿主能力用对"（透传、异常、
    阈值、未绑定时报错），不是"AES 实现对不对"：后者由 tests/test_backup_encrypted.py
    直接盯 crypto_core，tests/test_kernel_boundaries.py 还会把真 crypto_core 注进来
    验容器兼容性。
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile

from .service import BackupService

BLOCK = "backup"
MAX_MS = 2000
PASSWORD = "Abcdefgh1234Xy"          # 够强（自检用，不是真口令）
ITERS = 1000                          # 自检专用：真实备份用宿主那边的 600k


# ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌--------------------- 宿主能力的替身（无网络、无真加密）
class FakeCrypto(object):
    """加解密**契约替身**：只保证五个入口的输入/输出/异常形状。

    它不是加密实现，也不假装是：容器里明文写着口令，只为让"错口令"这条路径可验。
    """

    HEADER = b"FAKE1"
    CODE = "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH"

    def __init__(self, level=2):
        self.level = level
        self.calls = []

    def password_strength(self, pw):
        self.calls.append(("password_strength", pw))
        if not pw:
            return 0, "空口令"
        if len(pw) >= 12 and self.level >= 2:
            return 2, "可以"
        return 1, "偏短（建议至少 12 位）"

    def make_recovery_code(self):
        self.calls.append(("make_recovery_code",))
        return self.CODE

    def encrypt(self, password, raw, iters=None):
        self.calls.append(("encrypt", password, len(raw), iters))
        return self.HEADER + b"|" + password.encode("utf-8") + b"|" + raw

    def decrypt(self, password, blob):
        self.calls.append(("decrypt", password, len(blob)))
        if not blob.startswith(self.HEADER + b"|"):
            raise ValueError("不是本格式的容器")
        pw, _sep, raw = blob[len(self.HEADER) + 1:].partition(b"|")
        if pw.decode("utf-8") != password:
            raise ValueError("口令错误，或数据被篡改")
        return raw

    def info(self, blob):
        self.calls.append(("info", len(blob)))
        return {"version": 1, "algo": "FAKE-CONTAINER", "size": len(blob)}


class FakeHost(object):
    """只提供"宿主能力"这一样：加解密实现。故意不带任何壳层代码。"""

    def __init__(self, crypto=None):
        self.crypto = crypto if crypto is not None else FakeCrypto()


# ---------------------------------------------------------------- 小工具
def _tmpdir(label):
    """临时目录：%TEMP% 写不进去时退到工作区 tmp/ 下（venv 版 Python 的已知限制）"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for cand in (os.environ.get("TEMP"), os.environ.get("TMP"),
                 os.path.join(root, "tmp_kernel_tests")):
        if not cand:
            continue
        try:
            # 先自己探一次可写性：mkdtemp 遇到 PermissionError 会重试上万次，
            # 在"只能写工作区"的解释器上会直接把自检拖到超时。
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".probe_%d" % os.getpid())
            os.makedirs(probe, exist_ok=True)
            os.rmdir(probe)
            return tempfile.mkdtemp(prefix="dick_block_%s_" % label, dir=cand)
        except Exception:
            continue
    raise RuntimeError("没有可写的临时目录")


def _eq(got, want, what):
    if got != want:
        raise AssertionError("%s：期望 %r，实际 %r" % (what, want, got))


def _true(cond, what):
    if not cond:
        raise AssertionError(what)


def _deps():
    """依赖声明只认 manifest（唯一真相），不在这里再写一遍"""
    try:
        with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "manifest.json"), encoding="utf-8") as f:
            return list((json.load(f).get("requires") or {}).get("modules") or [])
    except Exception:
        return []


def _svc(level=2):
    """一个绑好假宿主的服务（加解密走 FakeCrypto）"""
    return BackupService().bind(FakeHost(FakeCrypto(level)))


# ---------------------------------------------------------------- cases（宿主能力）
def case_unbound_crypto():
    """异常路径：没绑加密能力就调加密接口，要当场说清楚，而不是偷偷 import 宿主"""
    svc = BackupService()
    for name, call in (("seal", lambda: svc.seal(b"x", PASSWORD)),
                       ("unseal", lambda: svc.unseal(b"x", PASSWORD)),
                       ("password_check", lambda: svc.password_check(PASSWORD))):
        try:
            call()
        except RuntimeError as e:
            _true("bind" in str(e), "%s 的报错要指向 bind：%r" % (name, str(e)))
        else:
            raise AssertionError("%s 在没绑加密能力时居然能跑" % name)


def case_bind_wires_crypto():
    """bind 的两种接线方式都要认：宿主自带 crypto / 显式传 crypto"""
    crypto = FakeCrypto()
    svc = BackupService()
    _true(svc.bind(FakeHost(crypto)) is svc, "bind 要返回自己（壳层能链式取服务）")
    _true(svc.crypto is crypto, "bind(host) 要认宿主身上的 crypto")
    other = FakeCrypto()
    svc.bind(FakeHost(), other)
    _true(svc.crypto is other, "显式传 crypto 时以它为准")


def case_password_check_threshold():
    _eq(_svc(level=1).password_check("abcdef")["ok_to_use"], False, "等级 1 不该可用")
    _eq(_svc(level=2).password_check(PASSWORD)["ok_to_use"], True, "等级 2 应当可用")


def case_require_strong_weak():
    ok, err = _svc(level=1).require_strong("abc")
    _eq(ok, False, "弱口令必须被拦")
    _true("口令不够强" in err, "弱口令文案要说人话：%r" % err)
    _true("偏短" in err, "加密实现给的细节要带上：%r" % err)


def case_require_strong_ok():
    _eq(_svc(level=2).require_strong(PASSWORD), (True, ""), "强口令放行")


def case_make_password_passthrough():
    got = _svc().make_password()
    _eq(got, {"ok": True, "password": FakeCrypto.CODE}, "恢复码由宿主生成，块只透传")


def case_seal_uses_crypto():
    svc = _svc()
    blob = svc.seal(b"hello", PASSWORD, iters=ITERS)
    enc = [c for c in svc.crypto.calls if c[0] == "encrypt"]
    _eq(len(enc), 1, "seal 要真的让宿主加密一次")
    _eq(enc[0][3], ITERS, "iters 要原样传给加密实现")
    _true(blob.startswith(FakeCrypto.HEADER), "容器字节由加密实现产出")
    svc.seal(b"hello", PASSWORD)         # 不传 iters → 宿主默认迭代数
    _eq(svc.crypto.calls[-1][3], None, "不指定 iters 时不要自己塞默认值")


def case_seal_unseal_roundtrip():
    svc = _svc()
    blob = svc.seal(b"hello-block", PASSWORD, iters=ITERS)
    _eq(svc.unseal(blob, PASSWORD), b"hello-block", "封了再解要原样回来")


def case_unseal_wrong_password():
    svc = _svc()
    blob = svc.seal(b"x" * 32, PASSWORD, iters=ITERS)
    try:
        svc.unseal(blob, "wrong-password-123")
    except ValueError as e:
        _true("口令错误" in str(e) or "篡改" in str(e), "错口令的报错要能看懂：%r" % str(e))
        return
    raise AssertionError("错口令居然解开了")


def case_info_passthrough():
    svc = _svc()
    blob = svc.seal(b"y" * 16, PASSWORD, iters=ITERS)
    got = svc.info(blob)
    _eq(got.get("algo"), "FAKE-CONTAINER", "容器头由加密实现解读，块只透传")
    _eq(got.get("size"), len(blob), "size = 原始容器长度")


# ---------------------------------------------------------------- cases（铺盘，不需要宿主）
def _dirs(tree):
    return {"root": tree, "saves": os.path.join(tree, "saves"),
            "worlds": os.path.join(tree, "worlds"),
            "personas": os.path.join(tree, "personas"),
            "codex": os.path.join(tree, "codex"),
            "config_file": os.path.join(tree, "config.json")}


def _zip_of(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in entries:
            z.writestr(name, text)
    return io.BytesIO(buf.getvalue())


def case_restore_zip_counts():
    tree = _tmpdir("restore")
    try:
        dirs = _dirs(tree)
        for d in (dirs["saves"], dirs["worlds"], dirs["personas"], dirs["codex"]):
            os.makedirs(d, exist_ok=True)
        z = _zip_of([("DICK_备份_x/saves/a.json", "{}"),
                     ("DICK_备份_x/worlds/w.json", "{}"),
                     ("DICK_备份_x/config.json", "{}")])
        with zipfile.ZipFile(z) as zf:
            got = BackupService().restore_zip(zf, os.path.join(tree, "bak"), dirs)
        _eq(got, {"saves": 1, "worlds": 1, "personas": 0, "config": 1, "codex": 0},
            "铺盘计数")
        _true(os.path.isfile(os.path.join(dirs["saves"], "a.json")), "文件要真的落盘")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_restore_zip_blocks_traversal():
    """坏输入：备份里带 `..` 的条目绝不能写到数据根之外"""
    tree = _tmpdir("traversal")
    try:
        dirs = _dirs(tree)
        os.makedirs(dirs["saves"], exist_ok=True)
        z = _zip_of([("DICK_备份_x/../evil.json", "{}")])
        with zipfile.ZipFile(z) as zf:
            got = BackupService().restore_zip(zf, os.path.join(tree, "bak"), dirs)
        _eq(sum(got.values()), 0, "穿越条目必须一条都不落")
        _true(not os.path.exists(os.path.join(tree, "evil.json")), "写到了数据根之外")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_restore_zip_unrelated_entries():
    """坏输入：备份里出现不认识的位置 → 跳过而不是乱铺"""
    tree = _tmpdir("unrelated")
    try:
        dirs = _dirs(tree)
        for d in (dirs["saves"], dirs["worlds"], dirs["personas"], dirs["codex"]):
            os.makedirs(d, exist_ok=True)
        z = _zip_of([("DICK_备份_x/random/thing.json", "{}"),
                     ("DICK_备份_x/codex/sub/story.json", "{}")])
        with zipfile.ZipFile(z) as zf:
            got = BackupService().restore_zip(zf, os.path.join(tree, "bak"), dirs)
        _eq(got["codex"], 1, "codex 里连子目录一起铺")
        _eq(sum(got.values()), 1, "不认识的位置要跳过")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def _cases():
    return {
        "unbound_crypto": case_unbound_crypto,
        "bind_wires_crypto": case_bind_wires_crypto,
        "password_check_threshold": case_password_check_threshold,
        "require_strong_weak": case_require_strong_weak,
        "require_strong_ok": case_require_strong_ok,
        "make_password_passthrough": case_make_password_passthrough,
        "seal_uses_crypto": case_seal_uses_crypto,
        "seal_unseal_roundtrip": case_seal_unseal_roundtrip,
        "unseal_wrong_password": case_unseal_wrong_password,
        "info_passthrough": case_info_passthrough,
        "restore_zip_counts": case_restore_zip_counts,
        "restore_zip_blocks_traversal": case_restore_zip_blocks_traversal,
        "restore_zip_unrelated_entries": case_restore_zip_unrelated_entries,
    }


# ---------------------------------------------------------------- 运行
def run(only=None):
    t0 = time.perf_counter()
    passed, failed, errors = 0, 0, []
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):      # 自检期间模块自己的日志收进缓冲区
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
        print("用法：python -m modules.backup --selftest [--only <case>]")
        return 2
    only = argv[argv.index("--only") + 1] if "--only" in argv and \
        len(argv) > argv.index("--only") + 1 else None
    res, errors, log = run(only)
    print(json.dumps(res, ensure_ascii=False))          # 唯一一行 JSON
    if errors:
        for line in log.splitlines():
            print("  | " + line)
        for cid, msg in errors:
            print("FAIL %s: %s" % (cid, msg))
            print("  复现：python -m modules.backup --selftest --only %s" % cid)
    return 1 if res["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
