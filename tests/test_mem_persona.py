# -*- coding: utf-8 -*-
"""mem_persona 的测试：画像只由事实聚合、证据不足不写、推测不掺、指纹缓存。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mem_facts as F      # noqa: E402
import mem_persona as P    # noqa: E402

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
    print(u"\n== ① 一条事实不成画像 ==")
    one = [F.make_fact(u"喜欢黑咖啡", "u1", t=1)]
    p1 = P.build(one)
    check(u"只有 1 条 → 不产生特征", p1["empty"] is True)
    check(u"画像段为空串", P.persona_block(p1) == "")

    print(u"\n== ② 同类两条才算长期特征 ==")
    facts = [
        F.make_fact(u"喜欢黑咖啡", "u1", t=1, key=u"饮品"),
        F.make_fact(u"每天喝两杯咖啡", "u2", t=2, key=u"饮品"),
        F.make_fact(u"讨厌香菜", "u3", t=3),
    ]
    p2 = P.build(facts)
    check(u"产生了 1 条特征（饮品）", len(p2["traits"]) == 1)
    check(u"特征取最近一次说法", p2["traits"][0]["text"] == u"每天喝两杯咖啡")
    check(u"带依据条数", p2["traits"][0]["evidence"] == 2)
    check(u"能追回出处", p2["traits"][0]["sources"] == ["u1", "u2"])
    check(u"单条那条没进画像", all(u"香菜" not in t["text"] for t in p2["traits"]))

    print(u"\n== ③ 用户明确说「一直」→ 一条也算 ==")
    always = [F.make_fact(u"我一直住杭州", "u5", t=5)]
    p3 = P.build(always)
    check(u"一直类事实单独成立", len(p3["traits"]) == 1)
    check(u"依据仍是 1 条", p3["traits"][0]["evidence"] == 1)

    print(u"\n== ④ 推测不掺进画像 ==")
    rapport = [F.make_rapport(u"我觉得她很孤僻", "a9", confidence=0.8)]
    p4 = P.build(facts)
    block = P.persona_block(p4)
    check(u"画像段里没有推测", u"孤僻" not in block)
    check(u"画像里也没有 rapport 字段", "rapport" not in P.dumps(p4))
    rb = F.rapport_block(rapport)
    check(u"推测在 rapport 段里单独出现", u"孤僻" in rb)

    print(u"\n== ⑤ 上限与排序 ==")
    many = []
    for i in range(12):
        many.append(F.make_fact(u"习惯%d-1" % i, "s%d1" % i, t=i * 2, key=u"k%d" % i))
        many.append(F.make_fact(u"习惯%d-2" % i, "s%d2" % i, t=i * 2 + 1, key=u"k%d" % i))
    many.append(F.make_fact(u"习惯0-3", "s03", t=100, key=u"k0"))
    p5 = P.build(many, max_traits=8)
    check(u"最多 8 条", len(p5["traits"]) <= 8)
    check(u"证据最多的排第一（k0 有 3 条）", p5["traits"][0]["evidence"] == 3)
    check(u"输出稳定（同样输入两次一致）", P.dumps(P.build(many)) == P.dumps(P.build(many)))

    print(u"\n== ⑥ 指纹与缓存 ==")
    fp1 = P.fingerprint(facts)
    fp2 = P.fingerprint(list(reversed(facts)))
    check(u"指纹与顺序无关", fp1 == fp2)
    check(u"内容变了指纹就变", P.fingerprint(facts + [F.make_fact(u"养猫", "u7")]) != fp1)

    calls = {"n": 0}

    def counting(fs):
        calls["n"] += 1
        return P.build(fs)

    cache = P.Cache(counting)
    cache.get(facts)
    cache.get(facts)
    check(u"同一批事实只算一次", calls["n"] == 1)
    cache.get(facts + [F.make_fact(u"养猫", "u7")])
    check(u"事实变了会重算", calls["n"] == 2)

    print(u"\n== ⑦ 序列化往返 ==")
    text = P.dumps(p2)
    back = P.loads(text)
    check(u"往返后特征还在", len(back["traits"]) == len(p2["traits"]))
    check(u"坏数据不炸", P.loads("not json") == {})

    print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌