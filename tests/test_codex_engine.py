# -*- coding: utf-8 -*-
"""GAL 叙事引擎核心测试：表现指令模型 + 数值条件求值 + 校验。
运行：python tests/test_codex_engine.py
覆盖：① step_kind 推断 ② evaluate_condition(aff/status/flags/all/any/组合)
      ③ filter_choices(条件裁剪) ④ normalize_script(kind 补全) ⑤ validate 新指令与条件"""
import sys, os

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import codex_core

ok = 0
bad = 0
def check(c, m):
    global ok, bad
    if c:
        ok += 1
        print("  OK " + m)
    else:
        bad += 1
        print("  FAIL " + m)

STATE = {"affection": 90, "status": {"心情": "开心"}, "flags": {"met": True, "told": False}}

print("== ① step_kind 推断 ==")
check(codex_core.step_kind({"text": "你好"}) == "say", "text → say")
check(codex_core.step_kind({"kind": "show", "sprite": "x.png"}) == "show", "显式 show")
check(codex_core.step_kind({"choice": [{"text": "a", "goto": "s2"}]}) == "choice", "choice")
check(codex_core.step_kind({"jump": "s2"}) == "jump", "jump")
check(codex_core.step_kind({"bg": "x.png", "text": "hi"}) == "say", "多表现以文本优先")
check(codex_core.step_kind({"kind": "wait", "ms": 500}) == "wait", "wait")

print("== ② evaluate_condition ==")
check(codex_core.evaluate_condition(STATE, {"aff": ">=85"}) is True, "aff>=85 命中")
check(codex_core.evaluate_condition(STATE, {"aff": ">=95"}) is False, "aff>=95 不命中")
check(codex_core.evaluate_condition(STATE, {"aff": 90}) is True, "aff==90 命中")
check(codex_core.evaluate_condition(STATE, {"aff": 91}) is False, "aff==91 不命中")
check(codex_core.evaluate_condition(STATE, {"status": {"心情": "开心"}}) is True, "status 命中")
check(codex_core.evaluate_condition(STATE, {"status": {"心情": "难过"}}) is False, "status 不命中")
check(codex_core.evaluate_condition(STATE, {"flags": ["met"]}) is True, "flags 存在")
check(codex_core.evaluate_condition(STATE, {"flags": ["!told"]}) is True, "flags 缺失(!)")
check(codex_core.evaluate_condition(STATE, {"flags": ["told"]}) is False, "flags 不存在")
check(codex_core.evaluate_condition(STATE, {"all": [{"aff": ">=80"}, {"status": {"心情": "开心"}}]}) is True, "all 命中")
check(codex_core.evaluate_condition(STATE, {"any": [{"aff": ">=99"}, {"status": {"心情": "开心"}}]}) is True, "any 命中")
check(codex_core.evaluate_condition(STATE, None) is True, "空条件恒真")
check(codex_core.evaluate_condition(None, {"aff": ">=85"}) is True, "无状态=作者预览恒真")
check(codex_core.evaluate_condition({}, {"flags": ["met"]}) is False, "空状态缺 flags 不命中")

print("== ③ filter_choices ==")
items = [
    {"text": "告白", "goto": "s2", "if": {"aff": ">=85"}},
    {"text": "只是微笑", "goto": "s3"},
    {"text": "撤退", "goto": "s4", "if": {"aff": ">=99"}},
]
kept = codex_core.filter_choices(items, STATE)
check([k["text"] for k in kept] == ["告白", "只是微笑"], "条件裁剪（999 档删掉）")
check(len(codex_core.filter_choices(items, None)) == 3, "预览模式不裁剪")

print("== ④ normalize_script kind 补全 ==")
sc = {"name": "x", "scenes": [{"id": "s1", "lines": [{"text": "hi"}, {"choice": [{"text": "a", "goto": "s1"}]}]}]}
codex_core.normalize_script(sc)
check(sc["scenes"][0]["lines"][0].get("kind") == "say", "line0 补 kind=say")
check(sc["scenes"][0]["lines"][1].get("kind") == "choice", "line1 补 kind=choice")

print("== ⑤ validate 新指令与条件 ==")
good = {"name": "x", "scenes": [{"id": "s1", "lines": [
    {"kind": "show", "sprite": "s.png"},
    {"kind": "effect", "effect": "shake"},
    {"kind": "wait", "ms": 300},
    {"text": "hi"},
    {"choice": [{"text": "a", "goto": "s1", "if": {"aff": ">=80"}}]},
]}]}
v, iss = codex_core.validate_codex(good)
check(v and not iss, "校验通过（新指令+条件）")
bad_if = {"name": "x", "scenes": [{"id": "s1", "lines": [{"choice": [{"text": "a", "goto": "s1", "if": ">=80"}]}]}]}
v2, iss2 = codex_core.validate_codex(bad_if)
check(not v2 and any("if" in i for i in iss2), "if 非对象拦截")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌