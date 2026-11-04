# -*- coding: utf-8 -*-
"""mem_scene 的测试：两个场景互不污染、随时可互读、老布局只读回退、迁移。

这一层是纯文件逻辑，测试全在临时目录里跑，不碰真实 memory/。
"""
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mem_scene as M   # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def main():
    tmp = tempfile.mkdtemp(prefix="mem_scene_")

    print(u"\n== ① 场景别名与非法输入 ==")
    check(u"'私聊' → private", M.norm_scene(u"私聊") == "private")
    check(u"'群聊' → group", M.norm_scene(u"群聊") == "group")
    check(u"'dm' → private", M.norm_scene("dm") == "private")
    bad = False
    try:
        M.norm_scene("work")
    except M.SceneError:
        bad = True
    check(u"未知场景要报错（不再支持工作任务）", bad)
    bad = False
    try:
        M.check_role("../etc")
    except M.SceneError:
        bad = True
    check(u"角色名不许带路径", bad)

    print(u"\n== ② 两个场景互不污染 ==")
    M.write_facts(tmp, "private", "咲", [{"k": "私聊里说的秘密", "source": "m1", "t": 1}])
    M.write_facts(tmp, "group", "咲", [{"k": "群里说的", "source": "m2", "t": 2}])
    pf = M.read_facts(tmp, "private", "咲")
    gf = M.read_facts(tmp, "group", "咲")
    check(u"私聊事实不被群聊看见", [f["k"] for f in pf] == [u"私聊里说的秘密"])
    check(u"群聊事实不被私聊看见", [f["k"] for f in gf] == [u"群里说的"])
    check(u"两条真的落在不同目录",
          M.role_dir(tmp, "private", "咲") != M.role_dir(tmp, "group", "咲"))

    print(u"\n== ③ facts 与 rapport 永不合并 ==")
    M.write_rapport(tmp, "private", "咲", {"closeness": 0.4, "note": u"我觉得她在躲我"})
    pkg = M.read_one(tmp, "private", "咲")
    check(u"读到的 facts 里没有 rapport 的字段",
          all("closeness" not in f for f in pkg["facts"]))
    check(u"rapport 单独可取", pkg["rapport"].get("closeness") == 0.4)
    check(u"事实里每条都带出处", all(f.get("source") for f in pkg["facts"]))

    print(u"\n== ④ 随时可以互读（场景是存储维度，不是闸门）==")
    both = M.read_all(tmp, "咲")
    check(u"一次拿到 private 与 group", set(both) == {"private", "group"})
    check(u"private 包是私聊那份", both["private"]["facts"][0]["k"] == u"私聊里说的秘密")
    check(u"group 包是群聊那份", both["group"]["facts"][0]["k"] == u"群里说的")
    check(u"没写过记忆的场景返回空壳而不是报错",
          M.read_one(tmp, "group", u"没这个人")["facts"] == [])

    print(u"\n== ⑤ 原文归档 / 摘要 / 索引 ==")
    M.append_archive(tmp, "group", "咲", [{"role": "user", "content": u"甲"}], stamp="20260101-000000")
    M.append_archive(tmp, "group", "咲", [{"role": "assistant", "content": u"乙"}], stamp="20260101-000000")
    check(u"同一份 archive 是追加不是覆盖",
          len(json.load(io.open(M.archive_files(tmp, "group", "咲")[0], encoding="utf-8"))) == 2)
    M.write_summary(tmp, "group", "咲", u"# 摘要\n群聊聊了甲和乙", stamp="20260101-000000")
    check(u"摘要能读回来", u"群聊聊了甲和乙" in M.read_summary(tmp, "group", "咲"))
    M.write_chain(tmp, "group", "咲", [{"id": "n1"}])
    check(u"chain 能读回来", M.read_chain(tmp, "group", "咲") == [{"id": "n1"}])
    check(u"私聊那份没被写脏", M.read_summary(tmp, "private", "咲") == "")

    print(u"\n== ⑥ 快照（记忆面板要看的东西）==")
    snap = M.snapshot(tmp)
    check(u"snapshot 有 private 与 group", set(snap) == {"private", "group"})
    check(u"snapshot 数出私聊 1 条事实", snap["private"][u"咲"]["facts"] == 1)
    check(u"snapshot 数出群聊 1 份归档", snap["group"][u"咲"]["archives"] == 1)

    print(u"\n== ⑦ 老布局只读回退 + 显式迁移 ==")
    legacy_dir = os.path.join(tmp, u"老角色")
    os.makedirs(legacy_dir)
    io.open(os.path.join(legacy_dir, "chain.json"), "w", encoding="utf-8").write(
        json.dumps([{"id": "old"}], ensure_ascii=False))
    check(u"老布局能被读到", M.read_legacy(tmp, u"老角色")["chain"] == [{"id": "old"}])
    check(u"老角色出现在 legacy 列表", u"老角色" in M.list_legacy_roles(tmp))
    rep = M.migrate_legacy(tmp, "private", dry_run=True)
    check(u"dry_run 只计算不搬", rep["moved"] == [u"老角色"] and os.path.isdir(legacy_dir))
    rep = M.migrate_legacy(tmp, "private")
    check(u"真迁移把目录搬进 private",
          rep["moved"] == [u"老角色"] and
          os.path.isfile(os.path.join(M.role_dir(tmp, "private", u"老角色"), "chain.json")))
    check(u"迁移后老位置没了", not os.path.isdir(legacy_dir))
    rep2 = M.migrate_legacy(tmp, "private")
    check(u"重复迁移不会覆盖已存在的场景目录", rep2["moved"] == [] and rep2["skipped"] == [])

    print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌