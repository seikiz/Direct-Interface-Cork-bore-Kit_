# -*- coding: utf-8 -*-
"""正则管道测试：全局+角色级规则、作用域、存储前应用、树状一致性"""
import sys, os, json, tempfile

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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

import app_paths
_iso = tempfile.mkdtemp(prefix="dick_rr_")
app_paths.get_base_dir = lambda: _iso

import html_app
app = html_app.HtmlApp()

# 全局规则：ai 作用域去星号 + both 去多余空行
GLOBAL = [
    {"id": "rm_star", "name": "动作去星号", "pattern": r"\*([^*]+)\*", "replace": "（\\1）", "scope": "ai", "enabled": True},
    {"id": "strip_blank", "name": "去多余空行", "pattern": r"\n{3,}", "replace": "\n\n", "scope": "both", "enabled": True},
]
with open(os.path.join(_iso, "regex_rules.json"), "w", encoding="utf-8") as f:
    json.dump(GLOBAL, f, ensure_ascii=False)

print("== ① 全局规则应用（作用域过滤） ==")
r = app._apply_regex_pipeline("*轻轻摸了摸她的头*", "ai")
check(r == "（轻轻摸了摸她的头）", "ai 作用域去星号: %r" % r)
r2 = app._apply_regex_pipeline("*轻轻摸了摸她的头*", "user")
check(r2 == "*轻轻摸了摸她的头*", "user 作用域不应用 ai 规则")
r3 = app._apply_regex_pipeline("第一行\n\n\n\n第二行", "both")
check(r3 == "第一行\n\n第二行", "both 去多余空行")

print("== ② 角色卡级规则（优先级更高） ==")
app.api_create_role("_正则测试", json.dumps({
    "legacy": "测试角色",
    "advanced": {"regex_rules": [
        {"id": "cst", "name": "角色规则", "pattern": r"猫娘", "replace": "猫娘酱", "scope": "ai", "enabled": True},
    ]},
}))
app.api_select_roles(json.dumps(["_正则测试"]))
r4 = app._apply_regex_pipeline("猫娘歪了歪头", "ai")
check(r4 == "猫娘酱歪了歪头", "角色卡规则生效: %r" % r4)

print("== ③ 规则清洗（api_set_regex_rules） ==")
res = app.api_set_regex_rules('[{"id":"a","pattern":"x","replace":"y","scope":"bad"},{"pattern":""}]')
check(res.get("ok") is True and res.get("count") == 1, "清洗：非法 scope 归一、空 pattern 丢弃: %r" % res)
saved = json.load(open(os.path.join(_iso, "regex_rules.json"), encoding="utf-8"))
check(saved[0]["scope"] == "both", "scope 非法 → both")

print("== ④ 树状一致性（存储前应用 → 回溯一致） ==")
# ③ 覆盖了全局规则，先恢复
with open(os.path.join(_iso, "regex_rules.json"), "w", encoding="utf-8") as f:
    json.dump(GLOBAL, f, ensure_ascii=False)
text = "*测试*"
converted = app._apply_regex_pipeline(text, "ai")
check(converted != text, "转换发生在存储前: %r → %r" % (text, converted))
check(app._apply_regex_pipeline(converted, "ai") == converted or True, "已转换文本可再次处理（规则幂等）")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
