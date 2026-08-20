# -*- coding: utf-8 -*-
"""角色勾选/取消勾选回归测试：取消勾选清空聊天窗口，勾选时从存档取回记录。
运行：python tests/test_role_uncheck.py
覆盖：①勾选无记录窗口 ②对话落盘 ③取消勾选窗口清空 ④存档保留记录 ⑤重新勾选恢复
      ⑥A→B 切换不串档（旧树写回 A、B 不混入、窗口清空）"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app

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

# 数据根目录重定向到临时目录，不触碰真实 saves/config
tmp = tempfile.mkdtemp(prefix="dick_test_")
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

def conv_msgs():
    return [m for m in app.api_state()["messages"] if m["kind"] in ("user", "ai")]

def save_nodes(name):
    with open(os.path.join(tmp, "saves", name + ".json"), encoding="utf-8") as f:
        data = json.load(f)
    return [n for n in (data.get("history_tree") or {}).get("nodes", {}).values()
            if n.get("role") != "system"]

print("== ① 勾选/取消勾选 聊天记录 ==")
check(bool(app.api_create_role("测试君", json.dumps({"personality": "温和"}))["ok"]), "创建角色")
app.api_select_roles(json.dumps(["测试君"]))
check(conv_msgs() == [], "勾选后窗口无历史记录")

u = app.core.add_user_message("早上好")
app.core.add_assistant_message("早上好呀，今天想聊点什么？", parent_id=u)
app._save_tree()
app._rebuild_messages()
check(len(conv_msgs()) == 2, "对话写入窗口")

app.api_select_roles(json.dumps([]))
check(conv_msgs() == [], "取消勾选后窗口清空")
check(len(save_nodes("测试君")) == 2, "存档保留记录（2 条）")

app.api_select_roles(json.dumps(["测试君"]))
cm = conv_msgs()
check(len(cm) == 2 and cm[0]["content"] == "早上好", "重新勾选恢复记录")

print("== ② A→B 切换不串档 ==")
check(bool(app.api_create_role("角色乙", json.dumps({"personality": "冷静"}))["ok"]), "创建角色乙")
app.api_select_roles(json.dumps(["测试君"]))
u2 = app.core.add_user_message("第二段对话")
app.core.add_assistant_message("乙该有的干净存档", parent_id=u2)
app._rebuild_messages()
app.api_select_roles(json.dumps(["角色乙"]))
check(len(save_nodes("测试君")) == 4, "A 的新对话写回 A 存档（4 条）")
check(len(save_nodes("角色乙")) == 0, "B 的存档不混入 A 的记录")
check(conv_msgs() == [], "切到无历史角色后窗口清空")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
