# -*- coding: utf-8 -*-
"""GAL 选项骨架测试：api_tree(scope="choices") 保留分支归属 + 选项/当前标记。
确保默认 api_tree()（完整树）行为不变；choices 模式供前端按支线分组并折叠选项间对话。"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app
import app_paths

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

tmp = tempfile.mkdtemp(prefix="dick_treech_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

check(bool(app.api_create_role("选项测试", json.dumps({"personality": "理性"}))["ok"]), "创建角色")
app.api_select_roles(json.dumps(["选项测试"]))

# 构架分线剧情：u1(选项) → a1 → u2(选项) → a2 → u3 → a3(当前)；u1 下另开一条支线 br
u1 = app.core.add_user_message("去哪里")
app.core.tree.nodes[u1].metadata["is_choice"] = True
a1 = app.core.add_assistant_message("你看着地图。", parent_id=u1)
u2 = app.core.add_user_message("去学校")
app.core.tree.nodes[u2].metadata["is_choice"] = True
a2 = app.core.add_assistant_message("校园里很安静。", parent_id=u2)
u3 = app.core.add_user_message("我继续往前走。")          # 非选项（自由输入）
a3 = app.core.add_assistant_message("风拂过树梢。", parent_id=u3)
br = app.core.add_assistant_message("（另一条线：你转身去了公园。）", parent_id=u1)  # 支线
app.core.tree.current_leaf_id = a3
app._rebuild_messages()

print("== api_tree()（默认完整树） ==")
full = app.api_tree()
by_id = {n["id"]: n for n in full}
check(len(full) >= 7, "完整树 >= 7 节点: %d" % len(full))
check(all("is_choice" in n for n in full), "每个节点带 is_choice 标记")
check({n["id"] for n in full if n.get("is_choice")} == {u1, u2}, "选项标记正确")
check(by_id[br]["branch_root"] == br and by_id[br]["on_path"] is False, "支线 br 收纳在自己的分支（branch_root==自身）")

print("== api_tree('choices')（选项骨架，保留分支归属供前端分组） ==")
ch = app.api_tree("choices")
by_ch = {n["id"]: n for n in ch}
check(len(ch) == len(full), "骨架返回完整树（前端再折叠）：%d == %d" % (len(ch), len(full)))
check(by_ch[u1]["is_choice"] is True and by_ch[u2]["is_choice"] is True, "选项标记保留")
check(by_ch[a3]["is_current"] is True, "当前叶子标记保留")
check(by_ch[br]["branch_root"] == br, "支线 br 的分支归属保留（供按支线分组）")
check(by_ch[a1]["is_choice"] is False and by_ch[u3]["is_choice"] is False, "非选项节点不带选项标记（供前端折叠）")

print("== scope 缺省仍为完整树 ==")
check(len(app.api_tree()) >= 7, "无参调用仍是完整树（向后兼容）")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
