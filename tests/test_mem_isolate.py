# -*- coding: utf-8 -*-
"""记忆隔离检测审计：老布局 / 真交叉 / 干净布局 / 世界记忆 / 迁移计划。

为什么需要
----------
"记忆隔离"这事最容易自欺：文件名看着像按角色分的（memory/<角色>.part1.json），
但**索引链是一份全局的**、而且"当前角色"靠文件修改时间猜。所以必须有判据，
能对真实数据说清：谁和谁混了、混在哪一层。这个套件把判据钉死。

跑法：python tests/test_mem_isolate.py
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

import mem_isolate as MI  # noqa: E402

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


def wj(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def any_in(items, *needles):
    return any(all(n in str(x) for n in needles) for x in items)


def main():
    print("=" * 62)
    print(u"记忆隔离检测审计")
    print("=" * 62)
    tmp = tempfile.mkdtemp(prefix="dick_memis_")
    try:
        print(u"\n== ① 空目录不报假警 ==")
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        rep = MI.audit(empty)
        check(u"空布局 = isolated（没有问题是真话，但也没归档）",
              rep["verdict"] == "isolated" and not rep["problems"], str(rep["verdict"]))

        print(u"\n== ② 老布局：一份 chain 混装两个角色 → 必须报出来 ==")
        legacy = os.path.join(tmp, "legacy")
        wj(os.path.join(legacy, MI.LEGACY_CHAIN), {
            u"咲": [{"part": 1, "path": u"咲.part1.json", "nodes": 10}],
            u"老约翰": [{"part": 1, "path": u"老约翰.part1.json", "nodes": 12}],
        })
        wj(os.path.join(legacy, u"咲.part1.json"), {"history_tree": {"nodes": {}}})
        wj(os.path.join(legacy, u"老约翰.part1.json"), {"history_tree": {"nodes": {}}})
        rep = MI.audit(legacy, role_names=[u"咲", u"老约翰"])
        check(u"判定为 legacy", rep["verdict"] == "legacy", str(rep["verdict"]))
        check(u"指出混装了 2 个角色",
              any_in(rep.get("legacy") or [], u"混装了 2 个角色"), str(rep.get("legacy")))
        check(u"提示散着文件", any_in(rep["warnings"], u"散着"), str(rep["warnings"]))
        moves = MI.plan_migration(legacy)
        check(u"迁移计划把 part 文件归到角色目录",
              any(m["to"] == os.path.join(u"咲", u"咲.part1.json") for m in moves), str(moves))
        check(u"迁移计划对 chain 是按 key 拆分而不是整份搬",
              any(m["from"] == MI.LEGACY_CHAIN and u"拆分" in (m.get("note") or "") for m in moves),
              str(moves))

        print(u"\n== ③ 干净布局：人物专属 + 世界共享 → isolated ==")
        clean = os.path.join(tmp, "clean")
        for role in (u"咲", u"老约翰"):
            wj(os.path.join(clean, role, MI.LEGACY_CHAIN),
               {role: [{"part": 1, "path": u"%s.part1.json" % role, "nodes": 8}]})
            wj(os.path.join(clean, role, u"%s.part1.json" % role), {"history_tree": {"nodes": {}}})
        wj(os.path.join(clean, MI.WORLD_DIR_NAME, MI.LEGACY_CHAIN),
           {"timeline": [{"t": "1848-03", "what": u"旧神苏醒"}]})
        io.open(os.path.join(clean, MI.WORLD_DIR_NAME, u"event-0001.json"), "w",
                encoding="utf-8").write(u"{}")
        rep = MI.audit(clean, role_names=[u"咲", u"老约翰"])
        check(u"判定为 isolated", rep["verdict"] == "isolated", str(rep["problems"]))
        check(u"看到了 2 个角色目录", set(rep["layout"]["roles"]) == {u"咲", u"老约翰"},
              str(list(rep["layout"]["roles"])))
        check(u"世界目录被识别（含 2 个文件）",
              rep["layout"]["world"]["exists"] and len(rep["layout"]["world"]["files"]) == 2,
              str(rep["layout"]["world"]))
        check(u"统计里世界归档数正确", rep["stats"]["world_archives"] == 2, str(rep["stats"]))

        print(u"\n== ④ 真交叉：角色目录里放着别人的归档 / 索引里出现别人 ==")
        leaky = os.path.join(tmp, "leaky")
        wj(os.path.join(leaky, u"咲", MI.LEGACY_CHAIN),
           {u"咲": [{"part": 1, "path": u"咲.part1.json"}],
            u"老约翰": [{"part": 1, "path": u"老约翰.part1.json"}]})
        wj(os.path.join(leaky, u"咲", u"咲.part1.json"), {"history_tree": {"nodes": {}}})
        wj(os.path.join(leaky, u"咲", u"老约翰.part1.json"), {"history_tree": {"nodes": {}}})
        rep = MI.audit(leaky, role_names=[u"咲", u"老约翰"])
        check(u"判定为 leaky", rep["verdict"] == "leaky", str(rep["verdict"]))
        check(u"报出目录里放着别人的归档",
              any_in(rep["problems"], u"放着别人的归档", u"老约翰.part1.json"), str(rep["problems"]))
        check(u"报出索引里出现别的角色",
              any_in(rep["problems"], u"索引里出现了别的角色", u"老约翰"), str(rep["problems"]))
        check(u"报出索引指向别人归档",
              any_in(rep["problems"], u"混进了别人的归档"), str(rep["problems"]))

        print(u"\n== ⑤ 缺失与提示：没有世界目录 / 角色没目录 ==")
        nope = os.path.join(tmp, "noworld")
        wj(os.path.join(nope, u"咲", MI.LEGACY_CHAIN), {u"咲": []})
        rep = MI.audit(nope, role_names=[u"咲", u"新人"])
        check(u"缺世界目录 → 提示（不是错误）",
              any_in(rep["warnings"], MI.WORLD_DIR_NAME) and not rep["problems"], str(rep["warnings"]))
        check(u"角色没目录 → 提示", any_in(rep["warnings"], u"新人"), str(rep["warnings"]))

        print(u"\n== ⑥ 世界记忆里混进角色 key → 报错 ==")
        mixed = os.path.join(tmp, "mixedworld")
        wj(os.path.join(mixed, MI.WORLD_DIR_NAME, MI.LEGACY_CHAIN),
           {"timeline": [], u"咲": [{"part": 1, "path": u"咲.part1.json"}]})
        rep = MI.audit(mixed, role_names=[u"咲"])
        check(u"世界记忆混进角色专属 key → leaky",
              rep["verdict"] == "leaky" and any_in(rep["problems"], u"世界记忆里混进了角色"),
              str(rep["problems"]))

        print(u"\n== ⑦ 群聊里出现别人名字 → 只提示，不当错误 ==")
        chatty = os.path.join(tmp, "chatty")
        wj(os.path.join(chatty, u"咲", MI.LEGACY_CHAIN), {u"咲": []})
        io.open(os.path.join(chatty, u"咲", u"咲.part1.json"), "w", encoding="utf-8").write(
            json.dumps({"history_tree": {"nodes": {"n1": {"content": u"老约翰：早上好"}}}},
                       ensure_ascii=False))
        rep = MI.audit(chatty, role_names=[u"咲", u"老约翰"])
        check(u"名字出现只算 warning（群聊正常）",
              (not rep["problems"]) and any_in(rep["warnings"], u"老约翰"),
              u"problems=%s warnings=%s" % (rep["problems"], rep["warnings"]))

        print(u"\n== ⑧ 报告渲染与坏输入 ==")
        rep = MI.audit(leaky, role_names=[u"咲", u"老约翰"])
        text = MI.render_report(rep)
        check(u"报告带标题与问题行", u"记忆" in text and u"⛔" in text, text[:80])
        for bad in (None, "", os.path.join(tmp, "不存在")):
            try:
                r = MI.audit(bad)
                ok = isinstance(r, dict) and "verdict" in r
            except Exception as e:
                ok = False
                print("     ", repr(bad), "->", e)
            check(u"坏输入不抛异常：%s" % (repr(bad)[:20]), ok)
        check(u"无 chain 时迁移计划为空", MI.plan_migration(os.path.join(tmp, "empty")) == [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("MEM_ISOLATE_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌