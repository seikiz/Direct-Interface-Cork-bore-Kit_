# -*- coding: utf-8 -*-
"""msg_quote 的测试：引用块格式、截断、剥除、metadata 读取。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import msg_quote as Q   # noqa: E402

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
    print(u"\n== ① 构造引用 ==")
    q = Q.make_quote("n12", "assistant", u"咲", u"今晚的月色很好，你要一起去看吗？", seq=5)
    check(u"有 id", q["id"] == "n12")
    check(u"记了角色名", q["speaker"] == u"咲")
    check(u"记了序号", q["seq"] == 5)
    check(u"没有内容就不引用", Q.make_quote("n1", "user", None, "   ") is None)
    check(u"没有 id 也不引用", Q.make_quote("", "user", None, u"内容") is None)

    print(u"\n== ② 提示词里的引用块 ==")
    block = Q.format_block(q)
    check(u"带「引用」字样", u"引用" in block)
    check(u"带发言者", u"咲" in block)
    check(u"单行（不换行）", "\n" not in block)
    check(u"没有引用时是空串", Q.format_block(None) == "" and Q.format_block({}) == "")

    print(u"\n== ③ 长文本截断 ==")
    long_q = Q.make_quote("n2", "user", None, u"啊" * 500)
    check(u"摘要在上限内", len(long_q["excerpt"]) == Q.QUOTE_MAX + 1)   # +1 是省略号
    check(u"以省略号结尾", long_q["excerpt"].endswith(Q.ELLIPSIS))

    print(u"\n== ④ 接到正文前面 ==")
    got = Q.apply_quote(u"我也想去", q)
    lines = got.split("\n")
    check(u"第一行是引用块", lines[0].startswith(u"〔引用"))
    check(u"第二行是原话", lines[1] == u"我也想去")
    check(u"没有引用时正文不变", Q.apply_quote(u"普通消息", None) == u"普通消息")

    print(u"\n== ⑤ 能剥掉（编辑/重生成时用）==")
    check(u"剥完只剩原话", Q.strip_quote(got) == u"我也想去")
    check(u"没有引用块时原样返回", Q.strip_quote(u"普通消息") == u"普通消息")

    print(u"\n== ⑥ metadata 读取 ==")
    check(u"正常读到", Q.from_metadata({"quote": q})["id"] == "n12")
    check(u"老数据（没有 quote）返回 None", Q.from_metadata({"speaker": u"咲"}) is None)
    check(u"脏数据不炸", Q.from_metadata({"quote": "not a dict"}) is None)

    print(u"\n== ⑦ 群聊里「谁」的判定 ==")
    check(u"有 speaker 用 speaker", Q.who({"speaker": u"老约翰", "role": "assistant"}) == u"老约翰")
    check(u"用户消息 → 你", Q.who({"role": "user"}) == u"你")
    check(u"assistant 无名字 → 对方", Q.who({"role": "assistant"}) == u"对方")

    print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌