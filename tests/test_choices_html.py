# -*- coding: utf-8 -*-
"""Galgame 选项 · HTML 端集成测试：状态透传 / 手动生成 / 点选发言 / 清空时机。
运行：python tests/test_choices_html.py"""
import sys, os, json, time, tempfile, shutil

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

class FakeMsg:
    def __init__(self, content): self.message = type("m", (), {"content": content})()
class FakeResp:
    def __init__(self, content): self.choices = [FakeMsg(content)]
class FakeCompletions:
    def __init__(self, content): self._c = content
    def create(self, **kw): return FakeResp(self._c)
class FakeChat:
    def __init__(self, content): self.completions = FakeCompletions(content)
class FakeClient:
    def __init__(self, content): self.chat = FakeChat(content)

tmp = tempfile.mkdtemp(prefix="dick_test_")
# 隔离：数据根目录与插件设置都指向临时目录；插件仍从真实 plugins/ 目录加载
_real_base = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real_base, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

# 启用插件并 stub LLM
check(bool(app.api_set_plugin("Galgame 选项", True).get("ok", True)) is not False, "启用插件")
plug = app.plugin_manager.get_plugin("Galgame 选项")
check(plug is not None and plug.enabled, "插件实例已加载并启用")
app.core.client = FakeClient('["轻轻敲门","转身离开","直接推门而入"]')

def choices_state():
    return app.api_state()["choices"]

def wait_idle():
    deadline = time.time() + 10
    while plug.choices_loading and time.time() < deadline:
        time.sleep(0.05)

print("== ① 状态透传 ==")
st = choices_state()
check(st["items"] == [] and st["loading"] is False, "初始 choices 为空")
st2 = app.api_poll(0)["choices"]
check(st2["items"] == [] and st2["loading"] is False, "poll 也带 choices 字段")

print("== ② 手动生成（api_cyoa） ==")
r = app.api_cyoa()
check(r["ok"] is True, "api_cyoa 返回 ok")
wait_idle()
st = choices_state()
check([x["text"] for x in st["items"]] == ["轻轻敲门", "转身离开", "直接推门而入"], "生成结果进入 state: %r" % st["items"])

print("== ③ 点选发言（api_pick_choice） ==")
app._start_fetch = lambda node_id: None  # 不真正调 LLM
r = app.api_pick_choice("转身离开")
check(r["ok"] is True, "pick_choice 返回 ok")
msgs = [m for m in app.api_state()["messages"] if m["kind"] in ("user", "ai")]
check(msgs and msgs[-1]["content"] == "转身离开", "选项作为玩家消息发出")
check(choices_state()["items"] == [], "点选后选项清空")

print("== ④ 自由输入清空旧选项 ==")
app.api_cyoa()
wait_idle()
check(len(choices_state()["items"]) == 3, "重新生成 3 个选项")
r = app.api_send("我自己打字说点什么", None, None)
check(r.get("ok") is True, "api_send 正常")
check(choices_state()["items"] == [], "自由输入后旧选项清空")

print("== ⑤ 切换角色清空选项 ==")
app.api_cyoa()
wait_idle()
check(len(choices_state()["items"]) == 3, "切角色前有选项")
check(bool(app.api_create_role("角色乙", json.dumps({"personality": "冷静"}))["ok"]), "创建角色乙")
app.api_select_roles(json.dumps(["角色乙"]))
check(choices_state()["items"] == [], "切换角色后选项清空")

print("== ⑥ 禁用插件时 api_cyoa 报错 ==")
app.api_set_plugin("Galgame 选项", False)
r = app.api_cyoa()
check(r["ok"] is False and "未启用" in r["err"], "禁用后返回提示: %r" % r["err"])
app.api_set_plugin("Galgame 选项", True)

print("== ⑦ 自动模式：AI 回复后自动出选项 ==")
plug.clear_choices()
plug.set_setting("auto", True)
app._start_fetch = lambda node_id: None
app.api_send("自动模式测试", None, None)          # 用户消息
u = app.core.tree.current_leaf_id
app.core.add_assistant_message("好的，我明白了。", parent_id=u)
app._on_response("好的，我明白了。", None)        # 模拟 AI 回复完成回调
wait_idle()
st = choices_state()
check([x["text"] for x in st["items"]] == ["轻轻敲门", "转身离开", "直接推门而入"], "自动生成进入 state: %r" % st["items"])
# 同一回合再回调（滑条候选）→ 不重复生成
app._on_response("另一版回复", None)
time.sleep(0.3)
check(choices_state()["items"] == st["items"], "滑条候选不重复生成")
plug.set_setting("auto", False)

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
