# -*- coding: utf-8 -*-
"""modules/workshop/selftest.py —— workshop 块的自检（闭环：不惊动任何别的块）

`python -m modules.workshop --selftest`  → 成功时**只有一行** JSON：
    {"block": "workshop", "pass": 11, "fail": 0, "ms": 9, "deps": []}

失败时追加：FAIL <case>: <原因> + 一行最小复现命令。

硬规则（ARCHITECTURE.md 十一）：
  · **不许启动别的块**、**不许连网**、**不许占端口**：这里用一个 FakeHost 假宿主，
    HTTP 全部走内存里的假响应，一条 socket 都不开；
  · **< 2s**：假传输是纯内存操作；
  · 至少覆盖坏输入：服务器 500、文件不存在、未绑宿主。
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

from .client import WorkshopClient

BLOCK = "workshop"
MAX_MS = 2000


# --------------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌-------------------------- 假宿主（无网络、无端口）
class _Resp(object):
    def __init__(self, code=200, payload=None, text=""):
        self.status_code = code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload, ensure_ascii=False)
        self.content = self.text.encode("utf-8")
        self.headers = {}

    def json(self):
        return self._payload


class FakeHost(object):
    """只实现模块声明的宿主端口；故意不带任何壳层代码"""

    WS_KINDS = {"角色卡": ("cards", "saves", "x"),
                "世界卡": ("worlds", "worlds", "x"),
                "世界卡包": ("packs", "packs", "x")}

    def __init__(self, root, fail_cards=False):
        self.save_dir = os.path.join(root, "saves")
        self.world_dir = os.path.join(root, "worlds")
        self.pack_dir = os.path.join(root, "packs")
        for d in (self.save_dir, self.world_dir, self.pack_dir):
            os.makedirs(d, exist_ok=True)
        self.calls = []
        self.saved = None
        self.reloaded = []
        self.plugin_manager = None
        self.fail_cards = fail_cards

    def _ws_kind(self, rtype):
        return self.WS_KINDS.get(str(rtype or "").strip(), self.WS_KINDS["世界卡"])

    def _ws_local_dir(self, rtype):
        _api, folder, _icon = self._ws_kind(rtype)
        return {"saves": self.save_dir, "worlds": self.world_dir,
                "packs": self.pack_dir}[folder]

    def _ws_load_config(self):
        return {"server_url": "http://selftest.invalid", "api_key": "k", "proxy": ""}

    def _ws_save_config(self, url, key, proxy=None):
        self.saved = (url, key, proxy)

    def _ws_active_server(self):
        return "http://selftest.invalid"

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

    def _ws_http_err(self, resp, what="操作"):
        return {"ok": False, "err": "%s没成功" % what}

    def _ws_call(self, method, url, **kw):
        self.calls.append((method, url))
        if url.endswith("/api/cards/list"):
            if self.fail_cards:
                return _Resp(code=500, payload={"err": "boom"})
            return _Resp(payload=[{"id": "c1", "name": "card"}])
        if url.endswith("/api/worlds/list"):
            return _Resp(payload=[])
        if url.endswith("/api/search"):
            return _Resp(payload=[{"id": "s1"}])
        return _Resp(payload={})

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


# ---------------------------------------------------------------- 小工具
def _tmpdir(label):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for cand in (os.environ.get("TEMP"), os.environ.get("TMP"),
                 os.path.join(root, "tmp_kernel_tests")):
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            # 先自己探一次可写性：mkdtemp 遇到 PermissionError 会重试上万次，
            # 在"只能写工作区"的解释器上会直接把自检拖到超时。
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
    try:
        with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "manifest.json"), encoding="utf-8") as f:
            return list((json.load(f).get("requires") or {}).get("modules") or [])
    except Exception:
        return []


def _client(**host_kw):
    """建一个绑好假宿主的客户端 + 临时目录（调用方负责清理）"""
    tree = _tmpdir("ws")
    return WorkshopClient().bind(FakeHost(tree, **host_kw)), tree


# ---------------------------------------------------------------- cases
def case_unbound_host():
    """异常路径：没 bind 就调接口要当场说清楚，而不是 None 崩在后面"""
    try:
        WorkshopClient().state()
    except RuntimeError as e:
        _true("bind" in str(e), "报错要指向 bind：%r" % str(e))
        return
    raise AssertionError("没绑宿主居然能跑")


def case_state_lists_local():
    cli, tree = _client()
    try:
        with io.open(os.path.join(cli.host.save_dir, "a.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        st = cli.state()
        _eq(st["local_roles"], ["a.json"], "本地角色卡列表")
        _eq(st["has_key"], True, "有 key 要报 true")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_list_items_ok():
    cli, tree = _client()
    try:
        got = cli.list_items()
        _eq(got["cards"], [{"id": "c1", "name": "card"}], "卡片列表")
        _true("packs" not in got, "服务器没有 packs 能力时不该去问")
        _eq(got["ok"], True, "ok")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_list_items_http_error():
    """坏输入：服务器 500 → 人话错误，不抛"""
    cli, tree = _client(fail_cards=True)
    try:
        got = cli.list_items()
        _eq(got["ok"], False, "500 要报失败")
        _true("稍后" in got["err"], "错误文案要是人话：%r" % got.get("err"))
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_search_passes_params():
    cli, tree = _client()
    try:
        got = cli.search("喵", "角色卡")
        _eq(got["ok"], True, "搜索应成功")
        _true(any("/api/search" in u for _m, u in cli.host.calls), "应请求 /api/search")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_preview_ok():
    cli, tree = _client()
    try:
        p = os.path.join(cli.host.save_dir, "c.json")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write('{"name": "一张卡"}')
        got = cli.preview("角色卡", "c.json")
        _eq(got["ok"], True, "预览应成功")
        _true("一张卡" in got["preview"], "预览内容")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_preview_missing():
    """坏输入：文件不存在 → ok=False，不抛"""
    cli, tree = _client()
    try:
        got = cli.preview("角色卡", "nope.json")
        _eq((got["ok"], got["err"]), (False, "文件不存在"), "缺失文件")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_upload_missing_file():
    """坏输入：上传一个不存在的文件 → 人话错误"""
    cli, tree = _client()
    try:
        got = cli.upload("角色卡", "不存在")
        _eq(got["ok"], False, "缺文件必须失败")
        _true("找不到" in got["err"], "错误文案：%r" % got.get("err"))
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_delete_local():
    cli, tree = _client()
    try:
        p = os.path.join(cli.host.save_dir, "d.json")
        with io.open(p, "w", encoding="utf-8") as f:
            f.write("{}")
        got = cli.delete_local("角色卡", "d.json")
        _eq(got["ok"], True, "删除应成功")
        _true(not os.path.exists(p), "文件应被删掉")
        _eq(cli.host.reloaded, ["roles"], "删完要刷新角色列表")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_save_conn():
    cli, tree = _client()
    try:
        _eq(cli.save_conn("http://a", "k2", "http://p"), {"ok": True}, "save_conn 返回")
        _eq(cli.host.saved, ("http://a", "k2", "http://p"), "宿主收到连接配置")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def case_download_writes_file():
    cli, tree = _client()
    try:
        got = cli.download("c1", "角色卡", "x.json")
        _eq(got["ok"], True, "下载应成功")
        _true(os.path.isfile(os.path.join(cli.host.save_dir, "x.json")), "文件应落盘")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def _cases():
    return {
        "unbound_host": case_unbound_host,
        "state_lists_local": case_state_lists_local,
        "list_items_ok": case_list_items_ok,
        "list_items_http_error": case_list_items_http_error,
        "search_passes_params": case_search_passes_params,
        "preview_ok": case_preview_ok,
        "preview_missing": case_preview_missing,
        "upload_missing_file": case_upload_missing_file,
        "delete_local": case_delete_local,
        "save_conn": case_save_conn,
        "download_writes_file": case_download_writes_file,
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
        print("用法：python -m modules.workshop --selftest [--only <case>]")
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
            print("  复现：python -m modules.workshop --selftest --only %s" % cid)
    return 1 if res["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
