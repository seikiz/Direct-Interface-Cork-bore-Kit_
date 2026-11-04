# -*- coding: utf-8 -*-
"""mem_facts 的测试：只收用户侧、必须带出处、更新以新为准、rapport 不混入事实。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mem_facts as F   # noqa: E402

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
    print(u"\n== ① 只收用户侧 ==")
    msgs = [
        {"role": "user", "id": "u1", "content": u"我住在杭州"},
        {"role": "assistant", "id": "a1", "content": u"好的，你住杭州"},
        {"role": "user", "id": "u2", "content": u"我养了一只猫"},
    ]
    got = F.from_messages(msgs, lambda m: [m["content"]])
    texts = [f["text"] for f in got]
    check(u"只抽到 2 条（assistant 被排除）", len(got) == 2)
    check(u"内容是用户说过的", texts == [u"我住在杭州", u"我养了一只猫"])
    check(u"出处记的是消息 id", [f["source"] for f in got] == ["u1", "u2"])

    print(u"\n== ② 没有出处的一律不记 ==")
    check(u"make_fact 缺 source → None", F.make_fact(u"住杭州", "") is None)
    check(u"make_fact 缺 text → None", F.make_fact(u"", "u1") is None)
    m = F.merge([], [{"text": u"无源条目"}])
    check(u"合并时把无源条目丢掉", m[0] == [])

    print(u"\n== ③ 同一件事以新的为准 ==")
    old = [F.make_fact(u"我住在杭州", "u1", t=100, key=u"居住地")]
    new = [F.make_fact(u"我住在上海", "u9", t=200, key=u"居住地")]
    merged, replaced = F.merge(old, new, now=300)
    check(u"只留一条", len(merged) == 1)
    check(u"留下的是新的", merged[0]["text"] == u"我住在上海")
    check(u"记录被替换", replaced and replaced[0]["new"] == u"我住在上海")
    check(u"带 updated 时间", merged[0].get("updated") == 300)
    check(u"出处跟着更新", merged[0]["source"] == "u9")

    print(u"\n== ④ 不同事实各自保留，顺序稳定 ==")
    a = F.make_fact(u"喜欢黑咖啡", "u1", t=100)
    b = F.make_fact(u"讨厌香菜", "u2", t=110)
    merged2, rep2 = F.merge([a], [b], now=120)
    check(u"两条都在", len(merged2) == 2)
    check(u"顺序是插入序", [x["text"] for x in merged2] == [u"喜欢黑咖啡", u"讨厌香菜"])
    check(u"没有误判替换", rep2 == [])

    print(u"\n== ⑤ 用户反悔：forget 按 key 删 ==")
    facts = [F.make_fact(u"我住在上海", "u9", t=200), F.make_fact(u"养了猫", "u2", t=210)]
    left = F.forget(facts, u"我住在上海。")
    check(u"那条没了（标点也算同一条）", [f["text"] for f in left] == [u"养了猫"])

    print(u"\n== ⑥ 进提示词的只有事实 ==")
    block = F.to_prompt_block(facts)
    check(u"有事实段标题", u"已知事实" in block)
    check(u"两条都列出来", block.count(u"- ") == 2)
    r = F.make_rapport(u"我觉得她今天心情不好", "a7", confidence=0.4)
    rb = F.rapport_block([r])
    check(u"推测单独成段", u"相处印象" in rb and u"心情不好" in rb)
    check(u"事实段里没有推测", u"心情不好" not in block)
    check(u"推测不在事实列表里", all(u"心情不好" not in f["text"] for f in facts))

    print(u"\n== ⑦ rapport 累加与裁剪 ==")
    notes = [F.make_rapport(u"印象%d" % i, "a%d" % i, t=100 + i) for i in range(5)]
    merged_r = F.merge_rapport([], notes, keep=3)
    check(u"只留最近 3 条", len(merged_r) == 3)
    check(u"最近的在最前", merged_r[0]["note"] == u"印象4")
    check(u"置信度被夹在 0~1", F.make_rapport(u"x", "a", confidence=9)["confidence"] == 1.0)

    print(u"\n== ⑧ 长度与清洗 ==")
    long = F.make_fact(u"啊" * 500, "u1")
    check(u"超长被截断", len(long["text"]) == F.MAX_FACT_LEN)
    check(u"多余空白被压平", F.make_fact(u"a   b\n c", "u1")["text"] == u"a b c")

    print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌