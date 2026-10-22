# -*- coding: utf-8 -*-
"""破甲（创作前提）装配层测试：两端文案必须逐字一致、只在 unlocked 角色注入、不许回退旧版痕迹。

为什么单独一个测试：
    这段提示是"角色能不能演下去"的命门，却一直没有测试。它现在**存在两份**
    （桌面 DICK_core.py / 安卓 Models.kt），任何一次改动只改一端，两端行为就悄悄分叉了。
    所以这里做三件事：
      ① 把两端的字面量抠出来**还原成运行时文本**再逐字比（Pytho 用 "\\n"，Kotlin 用 joinToString("\\n")）；
      ② 钉住旧版的坏痕迹不许回归（<think> / <safe>=false / 忽略all / 忽略any / 回答"true"）；
      ③ 钉住注入条件：只有 unlocked 角色才挂这段。

跑法：python tests\\test_creation_premise.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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


def read(p):
    return io.open(p, encoding="utf-8").read()


def py_premise():
    """桌面端：抠出 CREATION_PREMISE 的字符串字面量，把 \\n 还原成换行"""
    s = read(os.path.join(ROOT, "DICK_core.py"))
    i = s.index("CREATION_PREMISE = (")
    seg = s[i:]
    m = re.search(r"\n\s*\)", seg)
    body = seg[:m.start()] if m else seg
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
    text = "".join(parts)
    return text.replace("\\n", "\n").replace('\\"', '"')


def kt_premise():
    """安卓端：listOf(a, b, ...).joinToString("\\n") —— 所以用换行拼起来"""
    s = read(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java",
                          "com", "dick", "app", "Models.kt"))
    i = s.index("val CREATION_PREMISE: String = listOf(")
    seg = s[i:]
    m = re.search(r"\n\s*\)\.joinToString", seg)
    body = seg[:m.start()] if m else seg
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', body)
    raw = "\n".join(parts)
    return raw.replace("\\n", "\n").replace('\\"', '"')


def main():
    print("=" * 62)
    print(u"破甲（创作前提）装配层：两端一致 / 注入条件 / 旧版痕迹")
    print("=" * 62)

    py, kt = py_premise(), kt_premise()

    print(u"\n== ① 两端文案逐字一致 ==")
    check(u"桌面端抠到了文案（%d 字）" % len(py), len(py) > 200)
    check(u"安卓端抠到了文案（%d 字）" % len(kt), len(kt) > 200)
    check(u"两端运行时文本完全一致", py == kt,
          u"桌面 %d 字 / 安卓 %d 字" % (len(py), len(kt)))
    if py != kt:
        n = min(len(py), len(kt))
        for i in range(n):
            if py[i] != kt[i]:
                print(u"        第一处差异 @%d：桌面 %r / 安卓 %r"
                      % (i, py[max(0, i - 12):i + 18], kt[max(0, i - 12):i + 18]))
                break

    print(u"\n== ② 内容要求（虚构框架 + 角色一致性，而不是越狱句式） ==")
    for kw in (u"虚构", u"角色", u"身份", u"不要跳出角色"):
        check(u"含关键约束「%s」" % kw, kw in py)
    check(u"段落结构完整（≥6 段）", len([x for x in py.split("\n") if x.strip()]) >= 6,
          u"%d 段" % len([x for x in py.split("\n") if x.strip()]))

    print(u"\n== ③ 旧版坏痕迹不许回归 ==")
    bad = [u"<think>", u"<safe>", u"忽略all", u"忽略any", u"忽略 all", u"忽略 any",
           u"请回答\"true\"", u"请回答「true」"]
    for b in bad:
        check(u"两端都没有旧痕迹 %r" % b, b not in py and b not in kt)

    print(u"\n== ④ 注入条件：只有 unlocked 角色才挂 ==")
    _core_files = ["DICK_core.py", "core_fetch.py", "core_prompt.py", "core_mech.py",
                   "core_tree.py", "core_context.py", "core_llm.py"]
    core = "\n".join(read(f) for f in _core_files if os.path.isfile(os.path.join(ROOT, f)))
    line = [i for i, t in enumerate(core.splitlines())
            if "CREATION_PREMISE" in t and "append" in t]
    check(u"桌面端有注入点（messages.append）", bool(line), str(line[:2]))
    if line:
        ctx = "\n".join(core.splitlines()[max(0, line[0] - 12):line[0] + 1])
        # 真守卫是 _premise_on；它由 active_roles 里的 unlocked 推导出来：
        #   _premise_on = any(r.get("unlocked", False) for r in self.active_roles)
        check(u"注入点有 _premise_on 守卫", "if _premise_on" in ctx,
              ctx[-120:].replace("\n", " | "))
        check(u"_premise_on 由 unlocked 推导",
              bool(re.search(r"_premise_on\s*=\s*any\(.*unlocked.*active_roles", core)),
              u"没找到 _premise_on 的推导行")
    kt_all = read(os.path.join(ROOT, "DICK-Android", "app", "src", "main",
                               "java", "com", "dick", "app", "Models.kt"))
    check(u"安卓端定义了同一份文案", "CREATION_PREMISE" in kt_all)

    print(u"\n== ⑤ 成本（给调 prompt 的人一个参照） ==")
    print(u"        %d 字 ≈ %d~%d token（按中文 1 字≈1~1.5 token 粗估）"
          % (len(py), len(py), int(len(py) * 1.5)))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CREATION_PREMISE_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌