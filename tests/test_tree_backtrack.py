# -*- coding: utf-8 -*-
"""树状回溯测试：api_tree 完整树 + api_backtrack 跳回任意节点。"""
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

tmp = tempfile.mkdtemp(prefix="dick_bt_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

check(bool(app.api_create_role("回溯测试", json.dumps({"personality": "理性"}))["ok"]), "创建角色")
app.api_select_roles(json.dumps(["回溯测试"]))

# 构造：user1 → [a1, a2]（两个分支叶子），当前在 a1
u1 = app.core.add_user_message("第一条提问")
a1 = app.core.add_assistant_message("回答一", parent_id=u1)
a2 = app.core.add_assistant_message("回答二（分支）", parent_id=u1)
app.core.tree.current_leaf_id = a1
app._rebuild_messages()

print("== api_tree ==")
t = app.api_tree()
check(isinstance(t, list) and len(t) >= 4, "树节点数 >= 4: %d" % len(t))
by_id = {n["id"]: n for n in t}
check(by_id[u1]["role"] == "user" and by_id[a1]["role"] == "assistant", "节点角色正确")
check(all(n["on_path"] for n in t if n["branch_root"] is None), "无分支归属的节点全部在主线（平铺不右窜）")
check(by_id[a1]["is_current"] is True and by_id[a2]["is_current"] is False, "当前叶子标记正确")
check(by_id[a2]["on_path"] is False, "分支节点不在主线")
check(by_id[a2]["branch_root"] == a2 and by_id[a2]["branch_depth"] == 0, "分支根标识正确")
check(by_id[a2]["branch_size"] == 1, "分支尺寸 = 分支节点数: %d" % by_id[a2]["branch_size"])
check(by_id[u1]["branch_root"] is None, "主线节点无分支归属")
check(by_id[a1]["is_leaf"] is True and by_id[a2]["is_leaf"] is True, "叶子标记正确")
check(all(isinstance(n["content"], str) for n in t), "content 均含预览")

print("== api_backtrack ==")
r = app.api_backtrack(a2)
check(r.get("ok") is True, "回溯到分支叶子 a2")
msgs = [m for m in app.api_state()["messages"] if m["kind"] in ("user", "ai")]
check(msgs[-1]["content"] == "回答二（分支）", "窗口切到分支 a2: %s" % msgs[-1]["content"])
r2 = app.api_backtrack(u1)
check(r2.get("ok") is True, "回溯到中间用户节点 u1")
msgs2 = [m for m in app.api_state()["messages"] if m["kind"] in ("user", "ai")]
check(len(msgs2) == 1 and msgs2[0]["content"] == "第一条提问", "窗口显示到 u1 为止")
# 从中间节点继续：新消息挂在 u1 下（开新分支）
u1b = app.core.add_user_message("从回溯点继续")
newa = app.core.add_assistant_message("新分支回复", parent_id=u1b)
app.core.tree.current_leaf_id = newa
app._rebuild_messages()
t2 = app.api_tree()
check(any(n["id"] == u1b for n in t2), "回溯后新分支出现在树里")
b2 = {n["id"]: n for n in t2}
check(b2[u1b]["on_path"] is True and b2[newa]["on_path"] is True, "新主线平铺 on_path")
check(b2[a1]["on_path"] is False and b2[a2]["on_path"] is False, "旧分支保持收纳态（off-path）")
check(b2[a1]["branch_root"] == a1 and b2[a2]["branch_root"] == a2, "各分支独立收纳行")
check(b2[a1]["branch_size"] == 1 and b2[a2]["branch_size"] == 1, "分支尺寸正确")
r3 = app.api_backtrack("不存在的节点")
check(r3.get("ok") is False, "无效节点被拒")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
