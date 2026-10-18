# -*- coding: utf-8 -*-
"""modules/backup/selftest.py —— backup 块的自检（闭环：不惊动任何别的块）

`python -m modules.backup --selftest`  → 成功时**只有一行** JSON：
    {"block": "backup", "pass": 10, "fail": 0, "ms": 120, "deps": []}

失败时在这行之后追加：FAIL <case>: <原因>  +  一行最小复现命令
（ARCHITECTURE.md 十一：自检失败要能一条命令重跑那一处）。

硬规则（写在这里，改代码的人先看到）：
  · **不许启动别的块**：这里只 import 本块 + crypto_core（叶子库），不 boot 内核；
  · **不许连网、不许占端口**：加解密与铺盘都是纯本地操作，一条 socket 都不开；
  · **< 2s**：PBKDF2 迭代数压到 1000（只为验协议，不是为了安全）；
  · 每个 case 都是"输入 → 输出/异常"的闭环，且至少覆盖一条**坏输入**路径。
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
ITERS = 1000                          # 自检专用：真实备份用 crypto_core 的 600k


# ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 小工具
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


# ---------------------------------------------------------------- cases
def case_require_strong_weak():
    svc = BackupService()
    ok, err = svc.require_strong("abc")
    _eq(ok, False, "弱口令必须被拦")
    _true("口令不够强" in err, "弱口令文案要说人话：%r" % err)


def case_require_strong_ok():
    ok, err = BackupService().require_strong(PASSWORD)
    _eq((ok, err), (True, ""), "强口令放行")


def case_password_check():
    svc = BackupService()
    _eq(svc.password_check("abc")["ok_to_use"], False, "太短不该可用")
    _eq(svc.password_check(PASSWORD)["ok_to_use"], True, "够强应当可用")


def case_make_password():
    svc = BackupService()
    pw = svc.make_password()["password"]
    _true(len(pw) >= 40 and pw.count("-") >= 4, "恢复码应当够长且分组：%r" % pw[:20])


def case_seal_unseal_roundtrip():
    svc = BackupService()
    blob = svc.seal(b"hello-block", PASSWORD, iters=ITERS)
    _true(blob[:4] == b"DICK", "容器魔数不对")
    _eq(svc.unseal(blob, PASSWORD), b"hello-block", "封了再解要原样回来")


def case_unseal_wrong_password():
    svc = BackupService()
    blob = svc.seal(b"x" * 32, PASSWORD, iters=ITERS)
    try:
        svc.unseal(blob, "wrong-password-123")
    except ValueError as e:
        _true("口令错误" in str(e) or "篡改" in str(e), "错口令的报错要能看懂：%r" % str(e))
        return
    raise AssertionError("错口令居然解开了")


def case_info_fields():
    svc = BackupService()
    info = svc.info(svc.seal(b"y" * 16, PASSWORD, iters=ITERS))
    _eq(info.get("algo"), "AES-256-GCM", "容器头里的算法名")
    _eq(info.get("version"), 1, "容器版本")


def case_restore_zip_counts():
    tree = _tmpdir("restore")
    try:
        dirs = {"root": tree,
                "saves": os.path.join(tree, "saves"),
                "worlds": os.path.join(tree, "worlds"),
                "personas": os.path.join(tree, "personas"),
                "codex": os.path.join(tree, "codex"),
                "config_file": os.path.join(tree, "config.json")}
        for d in (dirs["saves"], dirs["worlds"], dirs["personas"], dirs["codex"]):
            os.makedirs(d, exist_ok=True)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("DICK_备份_x/saves/a.json", "{}")
            z.writestr("DICK_备份_x/worlds/w.json", "{}")
            z.writestr("DICK_备份_x/config.json", "{}")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            got = BackupService().restore_zip(z, os.path.join(tree, "bak"), dirs)
        _eq(got, {"saves": 1, "worlds": 1, "personas": 0, "config": 1, "codex": 0},
            "铺盘计数")
        _true(os.path.isfile(os.path.join(dirs["saves"], "a.json")), "文件要真的落盘")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_restore_zip_blocks_traversal():
    """坏输入：备份里带 `..` 的条目绝不能写到数据根之外"""
    tree = _tmpdir("traversal")
    try:
        dirs = {"root": tree, "saves": os.path.join(tree, "saves"),
                "worlds": os.path.join(tree, "worlds"),
                "personas": os.path.join(tree, "personas"),
                "codex": os.path.join(tree, "codex"),
                "config_file": os.path.join(tree, "config.json")}
        os.makedirs(dirs["saves"], exist_ok=True)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("DICK_备份_x/../evil.json", "{}")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            got = BackupService().restore_zip(z, os.path.join(tree, "bak"), dirs)
        _eq(sum(got.values()), 0, "穿越条目必须一条都不落")
        _true(not os.path.exists(os.path.join(tree, "evil.json")), "写到了数据根之外")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_restore_zip_unrelated_entries():
    """坏输入：备份里出现不认识的位置 → 跳过而不是乱铺"""
    tree = _tmpdir("unrelated")
    try:
        dirs = {"root": tree, "saves": os.path.join(tree, "saves"),
                "worlds": os.path.join(tree, "worlds"),
                "personas": os.path.join(tree, "personas"),
                "codex": os.path.join(tree, "codex"),
                "config_file": os.path.join(tree, "config.json")}
        for d in (dirs["saves"], dirs["worlds"], dirs["personas"], dirs["codex"]):
            os.makedirs(d, exist_ok=True)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("DICK_备份_x/random/thing.json", "{}")
            z.writestr("DICK_备份_x/codex/sub/story.json", "{}")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            got = BackupService().restore_zip(z, os.path.join(tree, "bak"), dirs)
        _eq(got["codex"], 1, "codex 里连子目录一起铺")
        _eq(sum(got.values()), 1, "不认识的位置要跳过")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def _cases():
    return {
        "require_strong_weak": case_require_strong_weak,
        "require_strong_ok": case_require_strong_ok,
        "password_check": case_password_check,
        "make_password": case_make_password,
        "seal_unseal_roundtrip": case_seal_unseal_roundtrip,
        "unseal_wrong_password": case_unseal_wrong_password,
        "info_fields": case_info_fields,
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
