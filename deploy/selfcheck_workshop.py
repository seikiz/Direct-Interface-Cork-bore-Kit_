#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创意工坊服务器自检（只用标准库，服务器上不需要装任何东西）。

用法：
  python3 selfcheck_workshop.py                          # 打本机 5000，只读检查
  python3 selfcheck_workshop.py --base http://1.2.3.4:8080
  python3 selfcheck_workshop.py --key <写Key> --full      # 连上传/下载/删除闭环一起验

退出码：0 = 全过；1 = 有失败（可直接给部署脚本当 gate）。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

PASS = 0
FAIL = 0
WARN = 0


def ok(msg):
    global PASS
    PASS += 1
    print("  [OK]   %s" % msg)


def bad(msg, detail=""):
    global FAIL
    FAIL += 1
    print("  [FAIL] %s  %s" % (msg, detail))


def warn(msg):
    global WARN
    WARN += 1
    print("  [WARN] %s" % msg)


def req(base, path, method="GET", body=None, headers=None, timeout=15):
    url = base.rstrip("/") + path
    data = None
    h = dict(headers or {})
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        else:
            data = body
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def jload(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def multipart(field_file, filename, content, extra=None):
    boundary = "----DICKCHECK" + uuid.uuid4().hex
    crlf = "\r\n"
    out = b""
    for k, v in (extra or {}).items():
        out += ("--" + boundary + crlf +
                'Content-Disposition: form-data; name="%s"' % k + crlf + crlf +
                str(v) + crlf).encode("utf-8")
    out += ("--" + boundary + crlf +
            'Content-Disposition: form-data; name="%s"; filename="%s"' % (field_file, filename) + crlf +
            "Content-Type: application/json" + crlf + crlf).encode("utf-8")
    out += content + (crlf + "--" + boundary + "--" + crlf).encode("utf-8")
    return out, "multipart/form-data; boundary=" + boundary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5000")
    ap.add_argument("--key", default=os.environ.get("WORKSHOP_API_KEY", ""))
    ap.add_argument("--full", action="store_true", help="连写操作闭环一起验（要有写 Key）")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    hk = {"X-API-Key": a.key} if a.key else {}

    print("=" * 64)
    print("创意工坊自检  %s   写Key:%s" % (base, "有" if a.key else "无"))
    print("=" * 64)

    print("\n== ① 存活与能力协商 ==")
    code, raw = req(base, "/api/health")
    if code != 200:
        bad("health 不通（HTTP %s）" % code, raw[:120].decode("utf-8", "replace"))
        print("\n自检中断：服务没起来，先看进程/日志（systemctl status 或 nohup 输出）")
        return 1
    h = jload(raw) or {}
    ok("health 200（service=%s）" % h.get("service"))
    if h.get("api") == 1:
        ok("health 带 api 版本（新版）")
    else:
        bad("health 没有 api 字段 —— 还是旧版 net.py")
    types = h.get("types") or []
    if types:
        ok("health.types = %s" % ",".join(types))
    else:
        bad("health 没有 types —— 还是旧版")
    print("       认证模式: %s | schema: %s | relay: %s | 上限: %s MB" % (
        h.get("auth"), h.get("schema"), h.get("relay"),
        (h.get("limits") or {}).get("upload_max_mb")))
    if h.get("auth") != "key":
        warn("auth=open：任何人都能上传/删除，公网务必设 WORKSHOP_API_KEY")

    code, raw = req(base, "/api/capabilities")
    cap = jload(raw) if code == 200 else None
    if cap is None:
        bad("capabilities 不通（HTTP %s）—— 旧版没有这个接口" % code)
    else:
        ok("capabilities 200")
        if all(isinstance(t, str) for t in (cap.get("types") or [])):
            ok("capabilities.types 是纯字符串列表（契约正常）")
        else:
            bad("capabilities.types 里混了对象 —— 客户端会判不出类型", str(cap.get("types"))[:120])
        reg = cap.get("registry") or []
        if reg:
            ok("registry 有 %d 类细节（中文名/扩展名）" % len(reg))
        if cap.get("types") and sorted(cap["types"]) != sorted(types):
            bad("capabilities.types 与 health.types 不一致")
        else:
            ok("types 两处一致")

    print("\n== ② 统计与列表 ==")
    code, raw = req(base, "/api/stats")
    st = jload(raw) if code == 200 else None
    ok("stats 200") if st else bad("stats 不通（HTTP %s）" % code)
    if st:
        print("       " + " | ".join("%s=%s" % (k, v) for k, v in st.items()
                                     if isinstance(v, int)))
    for t in (types or ["cards", "worlds"]):
        code, raw = req(base, "/api/%s/list" % t)
        data = jload(raw) if code == 200 else None
        if code == 200 and isinstance(data, list):
            ok("%-8s list 200（%d 条）" % (t, len(data)))
        else:
            bad("%-8s list 失败 HTTP %s" % (t, code))

    print("\n== ③ 搜索（含按类型） ==")
    code, raw = req(base, "/api/search?q=")
    hits = jload(raw) if code == 200 else None
    if code != 200 or not isinstance(hits, list):
        bad("search 失败 HTTP %s" % code)
    else:
        ok("search 200（%d 条）" % len(hits))
        kinds = sorted({x.get("type") for x in hits if isinstance(x, dict)})
        print("       出现的类型: %s" % (", ".join(kinds) or "无"))
    if "packs" in (types or []):
        code, raw = req(base, "/api/search?type=packs")
        packs = jload(raw) if code == 200 else None
        if isinstance(packs, list) and all(x.get("type") == u"世界卡包" for x in packs):
            ok("type=packs 只回世界卡包")
        else:
            bad("type=packs 过滤不对", str(packs)[:120])

    if not a.full:
        print("\n（没给 --full：跳过写操作闭环）")
    else:
        print("\n== ④ 写闭环：上传 → 列表 → 下载 → 点赞 → 删除 ==")
        if not a.key:
            bad("--full 需要写 Key")
        else:
            name = "自检探针" + uuid.uuid4().hex[:6]
            payload = json.dumps({"name": name, "description": "部署自检，稍后自动删除"},
                                 ensure_ascii=False).encode("utf-8")
            body, ct = multipart("file", "selfcheck.json", payload, {"author": "selfcheck"})
            target = "worlds" if "worlds" in (types or ["worlds"]) else "cards"
            code, raw = req(base, "/api/%s/upload" % target, "POST", body,
                            dict(hk, **{"Content-Type": ct}))
            item = jload(raw) or {}
            if code in (200, 201) and item.get("id"):
                ok("上传 201（%s → %s）" % (target, item.get("message", "")[:40]))
                rid = item["id"]
                t0 = time.time()
                code, raw = req(base, "/api/%s/list" % target)
                found = [x for x in (jload(raw) or []) if x.get("id") == rid]
                ok("列表里能看到（%.2fs）" % (time.time() - t0)) if found else bad("列表里找不到刚上传的")
                code, raw = req(base, "/api/%s/%s" % (target, rid), "GET", None, hk)
                got = jload(raw) or {}
                content = got.get("content", got)
                if isinstance(content, dict) and content.get("name") == name:
                    ok("下载内容一致")
                else:
                    bad("下载内容不一致", str(content)[:120])
                code, raw = req(base, "/api/%s/%s/like" % (target, rid), "POST", None, hk)
                ok("点赞 200") if code == 200 else warn("点赞 HTTP %s（不影响使用）" % code)
                code, raw = req(base, "/api/%s/%s" % (target, rid), "DELETE", None, hk)
                ok("删除 200") if code == 200 else bad("删除失败 HTTP %s" % code)
                code, raw = req(base, "/api/%s/list" % target)
                left = [x for x in (jload(raw) or []) if x.get("id") == rid]
                ok("删干净了") if not left else bad("删除后列表里还在")
            else:
                bad("上传失败 HTTP %s" % code, (raw or b"")[:160].decode("utf-8", "replace"))

    print("\n" + "=" * 64)
    print("通过 %d ／ 失败 %d ／ 警告 %d" % (PASS, FAIL, WARN))
    if FAIL == 0:
        print("WORKSHOP_SERVER_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌