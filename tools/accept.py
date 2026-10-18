# -*- coding: utf-8 -*-
"""accept.py —— 一条命令验收（懒人版：只读最后一行）

判断标准：ARCHITECTURE.md 十一「闭环与低耦」。这个脚本把五件事一次跑完：
    ① 每个块的自检（`python -m <块> --selftest`，一行 JSON）
    ② 依赖环（tools/blocks_graph.py）
    ③ 单文件行数（软 400 / 硬 800）
    ④ 边界审计（tools/audit_kernel_boundaries.py，含白名单棘轮与行数上限棘轮）
    ⑤ 唯一真相互检（block.json / manifest.json / 目录名 / 服务名 / 接口方法）

用法：
    python tools/accept.py                    # 人看
    python tools/accept.py --accept-signatures   # 接口签名确实该变时：更新快照（修订流程用）
    python tools/accept.py --json             # 机器可读（供 CI 解析）

出口约定（ARCHITECTURE.md 十一）：
    成功 → 最后一行为 `ALL_BLOCKS_OK`
    失败 → **第一行**就是 `FAIL <块名>: <一行原因>`，后面才是细节
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import audit_kernel_boundaries as audit          # noqa: E402
import blocks_graph as bg                        # noqa: E402

SNAPSHOT = os.path.join(HERE, "block_interfaces.json")


# =================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌=============================== 工具
def _rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def _fail(block, reason):
    return {"block": block, "reason": reason}


def _git(*args):
    try:
        p = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, timeout=60)
        if p.returncode != 0:
            return ""
        return p.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


# ================================================================ ① 块自检
def run_selftest(block_id, spec, timeout=120):
    cmd = list(spec.get("cmd") or [])
    if not cmd:
        return {"ok": False, "why": "block.json 没声明 selftest.cmd"}
    if cmd[0] in ("python", "python.exe"):
        cmd[0] = sys.executable
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=ROOT)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, timeout=timeout)
    except Exception as e:
        return {"ok": False, "why": "自检跑不起来：%s" % str(e)[:120]}
    wall = int((time.time() - t0) * 1000)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    line = ""
    for ln in out.splitlines():
        if ln.strip().startswith("{"):
            line = ln.strip()
    data = None
    if line:
        try:
            data = json.loads(line)
        except Exception as e:
            return {"ok": False, "why": "自检输出不是合法 JSON：%s" % str(e)[:80], "raw": out}
    if data is None:
        return {"ok": False, "why": "自检没有输出 JSON（rc=%d）" % p.returncode,
                "raw": (out + err)[-400:]}
    why = ""
    if data.get("block") != block_id:
        why = "自检报的块名对不上：%r" % data.get("block")
    elif p.returncode != 0 or int(data.get("fail") or 0) != 0:
        why = "自检未通过（fail=%s）" % data.get("fail")
    elif int(data.get("ms") or 0) > int(spec.get("max_ms") or 2000):
        why = "自检耗时 %sms 超过预算 %sms" % (data.get("ms"), spec.get("max_ms"))
    return {"ok": not why, "why": why, "json": data, "wall_ms": wall, "rc": p.returncode,
            "raw": (out if not why else (out + err))[-800:]}


def check_selftests(blocks):
    out, failures = {}, []
    for bid in sorted(blocks):
        bj = blocks[bid].get("block") or {}
        r = run_selftest(bid, bj.get("selftest") or {})
        out[bid] = r
        if not r["ok"]:
            failures.append(_fail(bid, r["why"]))
    return out, failures


# ================================================================ ⑤ 唯一真相
def check_truth(blocks):
    """block.json / manifest.json / 目录名 / 服务名 / 文件清单 五处必须说同一件事"""
    problems, services = [], {}
    sys.path.insert(0, ROOT)
    try:
        from kernel import manifest as km
    except Exception as e:
        return [_fail("kernel", "拿不到内核的清单校验器：%s" % str(e)[:120])], {}
    for bid, info in sorted(blocks.items()):
        bj = info.get("block")
        d = info["dir"]
        if not bj:
            problems.append(_fail(bid, "block.json 读不出来"))
            continue
        if os.path.basename(d) != bid:
            problems.append(_fail(bid, "block.json 的 block=%r 与目录名 %r 不一致"
                                  % (bid, os.path.basename(d))))
        listed = set(bj.get("files") or [])
        actual = {f for f in os.listdir(d)
                  if not f.startswith(".") and f != "__pycache__"}
        undeclared = sorted(actual - listed)
        missing = sorted(listed - actual)
        if undeclared:
            problems.append(_fail(bid, "目录里有未声明的文件：%s（要加文件先改 block.json）"
                                  % "、".join(undeclared)))
        if missing:
            problems.append(_fail(bid, "block.json 声明的文件不存在：%s" % "、".join(missing)))
        mf = info.get("manifest")
        if mf is None:
            # 内核是"宿主"，不是被装载的块：它没有 manifest 是正常的；
            # 模块块没有 manifest 就是坏块（加载器根本认不出来）。
            if info.get("layer") == "kernel":
                itf = bj.get("interface") or {}
                if not (itf.get("methods") or []):
                    problems.append(_fail(bid, "block.json 没声明 interface.methods"))
                continue
            problems.append(_fail(bid, "缺 manifest.json（块必须声明 provides/requires）"))
            continue
        try:
            m = km.Manifest(mf, source=_rel(os.path.join(d, "manifest.json")))
        except Exception as e:
            problems.append(_fail(bid, "manifest 校验炸了：%s" % str(e)[:120]))
            continue
        if m.errors:
            problems.append(_fail(bid, "manifest 不合法：%s" % "；".join(m.errors)))
        if m.id != bid:
            problems.append(_fail(bid, "manifest.id=%r 与块名 %r 不一致" % (m.id, bid)))
        for svc in m.services():
            if svc in services:
                problems.append(_fail(bid, "服务 %r 与块 %r 重复声明" % (svc, services[svc])))
            services[svc] = bid
        itf = bj.get("interface") or {}
        declared = list(itf.get("methods") or [])
        if not declared:
            problems.append(_fail(bid, "block.json 没声明 interface.methods（接口必须可查）"))
        if itf.get("service") and m.services() and itf["service"] not in m.services():
            problems.append(_fail(bid, "interface.service=%r 不在 manifest.provides.services 里"
                                  % itf["service"]))
    return problems, services


# ================================================================ ④ 边界
def check_boundaries():
    res = audit.scan()
    problems = []
    for v in res["violations"]:
        problems.append(_fail("boundary", "%s @ %s:%s" % (v["rule"], v["file"], v["line"])))
    base, err = bg._load_json(audit.BASELINE_DEFAULT)
    if base is None:
        problems.append(_fail("boundary", "基线读不出来：%s" % err))
        return problems, res, {}
    if res["whitelist_count"] > int(base.get("whitelist_count") or 0):
        problems.append(_fail("boundary", "白名单变长：%d > 基线 %s（只许缩短）"
                              % (res["whitelist_count"], base.get("whitelist_count"))))
    old_keys = set(base.get("whitelist") or [])
    new_keys = {e["key"] for e in res["whitelist"]}
    if new_keys - old_keys:
        problems.append(_fail("boundary", "白名单出现新条目：%s"
                              % "、".join(sorted(new_keys - old_keys))))
    for path, info in res["limits"].items():
        was = int((base.get("limits") or {}).get(path) or 0)
        if was and info["limit"] > was:
            problems.append(_fail("boundary", "行数上限被调高：%s %d → %d（只许下调）"
                                  % (path, was, info["limit"])))
    return problems, res, base


# ================================================================ ⑤' 接口签名
def check_signatures(update=False):
    hashes, if_problems = bg.interface_hashes()
    problems = [_fail(bid, why) for bid, why in sorted(if_problems.items())]
    base, err = bg.load_baseline()
    old = (base or {}).get("interface_hashes") or {}
    changed = {b: (old.get(b), h) for b, h in hashes.items() if old.get(b) != h}
    if update:
        bg.save_baseline(hashes)
        changed = {}
    elif changed:
        for b, (was, now) in sorted(changed.items()):
            problems.append(_fail(b, "接口签名变了（%s → %s）：要走修订流程 —— 改 ARCHITECTURE.md "
                                     "修订记录 + `python tools/accept.py --accept-signatures`"
                                  % (was or "无快照", now)))
    return problems, hashes, changed, bool(old)


# ================================================================ 变更摘要
def delta_summary():
    """相对 git HEAD：新增/删除文件 + 行数变化（只看块目录，别的改动与本批无关）

    `-uall` 是必须的：不加它，未跟踪的目录只会显示成 `kernel/` 一个条目，
    报"新增 1 个文件"等于没说。行数变化也要把未跟踪文件算进去
    （numstat 只看已跟踪文件），否则"本次 +0/-0"会让人以为什么都没干。
    """
    st = _git("status", "--porcelain", "-uall", "--", "kernel", "modules")
    added, deleted, modified = [], [], []
    for line in st.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip()
        code = code.strip()
        if code == "??":
            added.append(path)
        elif code == "D":
            deleted.append(path)
        elif code:
            modified.append(path)
    plus = minus = 0
    num = _git("diff", "--numstat", "--", "kernel", "modules")
    for line in num.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            plus += int(parts[0])
            minus += int(parts[1])
    for rel in added:                    # 未跟踪文件不在 numstat 里，自己数
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        try:
            with open(p, "r", encoding="utf-8") as f:
                plus += len(f.read().splitlines())
        except Exception:
            pass
    return {"added": added, "deleted": deleted, "modified": modified,
            "added_lines": plus, "removed_lines": minus}


# ================================================================ 主流程
def main(argv=None):
    argv = list(sys.argv[1:] if argv is not None else sys.argv[1:])
    as_json = "--json" in argv
    update = "--accept-signatures" in argv
    t0 = time.time()

    blocks = bg.blocks()
    failures = []

    self_results, f1 = check_selftests(blocks)
    failures += f1

    graph = bg.check()
    for p in graph["problems"]:
        failures.append(_fail("graph", p))

    soft = [r for r in graph["lines"] if r["level"] == "warn"]
    hard = [r for r in graph["lines"] if r["level"] == "error"]
    for r in hard:
        failures.append(_fail("lines", "%s %d 行 > 硬上限 %d" % (r["file"], r["lines"],
                                                                bg.HARD_LINES)))

    truth_problems, services = check_truth(blocks)
    failures += truth_problems

    boundary_problems, boundary_res, base = check_boundaries()
    failures += boundary_problems

    sig_problems, hashes, sig_changed, had_snapshot = check_signatures(update)
    failures += sig_problems

    delta = delta_summary()
    total_ms = int((time.time() - t0) * 1000)

    result = {
        "blocks": sorted(blocks),
        "selftests": {b: {k: v for k, v in r.items() if k in ("ok", "why", "json")}
                      for b, r in self_results.items()},
        "failures": failures,
        "cycles": graph["cycles"],
        "lines": graph["lines"],
        "boundary_violations": len(boundary_res["violations"]),
        "whitelist": "%d/%s" % (boundary_res["whitelist_count"],
                                (base or {}).get("whitelist_count")),
        "services": services,
        "interface_hashes": hashes,
        "interface_changed": {b: list(v) for b, v in sig_changed.items()},
        "delta": delta,
        "ms": total_ms,
        "ok": not failures,
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    if failures:                      # 懒人要求：第一行就是失败块 + 一行原因
        print("FAIL %s: %s" % (failures[0]["block"], failures[0]["reason"]))
        if len(failures) > 1:
            print("（另有 %d 条失败，见下）" % (len(failures) - 1))
        print("")

    print("=" * 70)
    print("验收：块自检 / 依赖环 / 行数 / 边界 / 唯一真相（ARCHITECTURE.md 十一）")
    print("=" * 70)
    print("\n[1/5] 块自检（%d 块）" % len(self_results))
    for bid, r in sorted(self_results.items()):
        j = r.get("json") or {}
        print("  %-10s pass=%-3s fail=%-2s ms=%-4s %s"
              % (bid, j.get("pass", "?"), j.get("fail", "?"), j.get("ms", "?"),
                 "OK" if r["ok"] else "FAIL ← %s" % r["why"]))
    print("\n[2/5] 依赖环：%s" % ("无环" if not graph["cycles"] else
                                  "发现 %d 个环" % len(graph["cycles"])))
    for e in graph["edges"]:
        print("  %s → %s" % (e["from"], e["to"]))
    top = graph["lines"][0] if graph["lines"] else {"file": "-", "lines": 0}
    print("\n[3/5] 行数：最大 %s（%d 行），软 %d / 硬 %d"
          % (top["file"], top["lines"], bg.SOFT_LINES, bg.HARD_LINES))
    for r in soft:
        print("  ⚠ %s %d 行 > 软上限 %d（不影响验收，但该拆了）"
              % (r["file"], r["lines"], bg.SOFT_LINES))
    print("\n[4/5] 边界审计：%d 违规；白名单 %s；行数上限 %d 项"
          % (len(boundary_res["violations"]), result["whitelist"],
             len(boundary_res["limits"])))
    print("\n[5/5] 唯一真相 + 接口签名：服务 %s；签名快照 %s"
          % ("、".join("%s→%s" % (s, b) for s, b in sorted(services.items())) or "（无）",
             "一致" if not sig_changed else "有变化"))

    print("\n变更摘要（相对 git HEAD，只看 kernel/ 与 modules/）：")
    print("  新增文件：%s" % ("、".join(delta["added"]) or "无"))
    print("  删除文件：%s" % ("、".join(delta["deleted"]) or "无"))
    print("  行数变化：+%d / -%d" % (delta["added_lines"], delta["removed_lines"]))
    print("  接口签名变化：%s" % ("、".join(sorted(sig_changed)) or "无"))

    if failures:
        print("\n失败明细：")
        for f in failures:
            print("  ✗ [%s] %s" % (f["block"], f["reason"]))
        print("\n结论：%d 项不通过（%dms）" % (len(failures), total_ms))
        return 1
    print("\n耗时 %dms" % total_ms)
    print("ALL_BLOCKS_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
