# -*- coding: utf-8 -*-
"""反讨好守卫：连续同意 / 过度道歉 / 每轮都夸 → 单轮降甜。

用户原话：「讨好反馈真的没啥用。」
讨好让反馈失效：无论你说什么都被同意，你就无法通过行为影响关系，关系也就没有重量。

本测试钉住：
  ① 正常对话不触发（不改变现状，陪伴感优先）；
  ② 三种信号各自能触发；
  ③ 触发时**只注入这一轮**的提醒，不写历史、不改人设；
  ④ 提醒里不许出现"冷淡/别理/少说话"这类削减陪伴感的词。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from sycophancy import detect, guard_text   # noqa: E402

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


def a(t):
    return {"role": "assistant", "content": t}


def u(t):
    return {"role": "user", "content": t}


def main():
    print("=" * 62)
    print(u"反讨好守卫（讨好 = 反馈通道失效）")
    print("=" * 62)

    print(u"\n== ① 正常对话不触发 ==")
    normal = [a("今天下雨，记得带伞。"), u("好"), a("你昨晚睡得好吗？"), a("我刚煮了面，有点咸。")]
    check(u"正常链不注入", guard_text(normal) == "", guard_text(normal)[:80])
    check(u"空链不注入", guard_text([]) == "")
    check(u"只有用户消息也不注入", guard_text([u("在吗"), u("你好")]) == "")

    print(u"\n== ② 三种信号各自触发 ==")
    agree = [a("好的，没问题。"), a("当然，都听你的。"), a("嗯嗯，你说得对。")]
    check(u"连续三轮同意 → 触发", guard_text(agree) != "")
    check(u"提醒里说明原因（连着几轮顺着说）", u"顺着对方" in guard_text(agree), guard_text(agree)[:120])

    appo = [a("对不起，是我不好。抱歉。"), a("我错了，对不起。"), a("抱歉，别生气。")]
    check(u"道歉太密 → 触发", guard_text(appo) != "")

    pra = [a("你真厉害！"), a("你好厉害，太棒了。"), a("你最好了，真聪明。")]
    check(u"每轮都夸 → 触发", guard_text(pra) != "")

    print(u"\n== ③ 只影响一轮（不写历史、不改人设） ==")
    g = guard_text(agree)
    check(u"提醒是独立文本（不改链内容）", isinstance(g, str) and len(agree) == 3)
    check(u"提醒里点明这一轮", u"这一轮" in g, g[:60])
    check(u"提醒不写进人设", (u"设定：" not in g) and (u"身份：" not in g))

    print(u"\n== ④ 不许削减陪伴感 ==")
    for txt in (guard_text(agree), guard_text(appo), guard_text(pra)):
        check(u"无冷淡类措辞", not any(x in txt for x in (u"冷淡", u"别理", u"少说话", u"不理")))
        check(u"保留「不需要变冷」这句（陪伴感优先）", u"不需要变冷" in txt, txt[:80])

    print(u"\n== ⑤ 统计口径 ==")
    st = detect([t["content"] for t in agree])
    check(u"agree_streak 统计正确", st["agree_streak"] == 3, str(st))
    st2 = detect([t["content"] for t in normal])
    check(u"正常链 streak 为 0", st2["agree_streak"] == 0, str(st2))

    print(u"\n== ⑥ 接入核心 ==")
    core = io.open(os.path.join(ROOT, "DICK_core.py"), encoding="utf-8").read()
    check(u"核心调用守卫", "sycophancy_guard_text(" in core)
    check(u"只取最近 6 轮", "[-6:]" in core)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("SYCOPHANCY_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌