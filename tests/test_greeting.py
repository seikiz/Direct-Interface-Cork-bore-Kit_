# -*- coding: utf-8 -*-
"""
开场白测试（需求端要求：以「响应」的形式出来，而不是直接贴卡片文字）。

背景：
    开场白过去只是被拼进 system 提示里的一个【开场白】字段，对话树里根本没有
    这条消息 —— 界面一片空白，作者写的东西用户一次都没见过。
    第一版修法是「直接插一条 assistant 消息」，但那样贴出来的是作者写死的文字，
    和当前选中的世界卡/玩家卡/好感度无关，读起来像设定文档而不是「她在说话」。
    现在改为：把开场白当【场景】交给模型，由它现场演出第一幕。

锁住的行为：
  · 新会话 → 发出一次「没有用户消息」的请求，载荷里带上开场场景
  · 载荷里不能有 user 消息（有的话就不是开局了）
  · 场景指令必须写明「你」= 玩家角色，否则玩家卡白选
  · 发不出去（没 Key / 没开场白 / 忙）→ 退回直接显示原文，界面不能空着
  · 续聊 / 群聊 / 无开场白 → 不触发
  · Android「彻底清空历史」之后要重演开场白（状态如初 = 连第一句也在）

跑法：utau_env\\Scripts\\python.exe tests\\test_greeting.py
"""

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import html_app                      # noqa: E402
import prompt_inspect as pi          # noqa: E402
from DICK_core import ChatCore       # noqa: E402

PASS = 0
FAIL = 0
GREET = "（在窗边回头）你终于来了。茶刚泡好，还热着。"


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


class CoreStub:
    """只装 _start_opening 用到的东西；generate_opening 只记录不真发（避免线程）"""

    def __init__(self, fire=True):
        self.tree = ChatCore().tree
        self.calls = []
        self._fire = fire
        self.opening_cue = None
        self.client = object() if fire else None

    def generate_opening(self, cue, on_response=None, on_error=None, on_stream=None):
        self.calls.append(cue)
        if not self._fire:
            return False
        if on_stream:
            on_stream("")
        if on_response:
            on_response("（她回过头）来了？坐吧。", None)
        return True

    def add_assistant_message(self, content, parent_id=None, metadata=None):
        return self.tree.add_node("assistant", content, parent_id=parent_id,
                                  metadata=metadata)

    def strip_mechanism_tags(self, text, apply=True):
        return text


class AppStub:
    def __init__(self, roles, selected, core):
        self.roles = roles
        self.selected_roles = selected
        self.core = core
        self.busy = False
        self.streaming = ""
        self._last_user = ""
        self.total_tokens = 0
        self.rebuilt = False

    def _on_response(self, reply, usage):
        # 忠实一点：真实链路里 _fetch_respo<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌nse 会先把 assistant 节点建好，
        # _on_response 只是后处理那条。桩不建节点的话，就测不出
        # 「显示的是模型演出来的，还是卡片原文」这个关键区别。
        self.core.tree.add_node("assistant", reply,
                                parent_id=self.core.tree.current_leaf_id,
                                metadata={"speaker": "阿岚"})
        self.reply = reply

    def _on_error(self, msg):
        self.err = msg

    def _rebuild_messages(self):
        self.rebuilt = True


def role_with(name, mes):
    return {"name": name, "file": name + ".json", "prompt": "p",
            "data": {"name": name, "first_mes": mes}, "fields": {"first_mes": mes}}


def mk(roles, selected, fire=True):
    core = CoreStub(fire=fire)
    return AppStub(roles, selected, core), core


def nodes(core, role):
    return [n for n in core.tree.nodes.values() if n.role == role]


# ============================================================
def test_opening_is_generated():
    print("\n== 1. 开场要「演出来」，不是贴卡片文字 ==")
    s, core = mk([role_with("阿岚", GREET)], ["阿岚"])
    n = html_app.HtmlApp._start_opening(s)
    check("触发了开场", n == 1, str(n))
    check("调用的是 generate_opening（交给模型演）",
          core.calls == [GREET], str(core.calls))
    check("卡片原文没有被直接插成消息（模型回什么才显示什么）",
          [x.content for x in nodes(core, "assistant")] == ["（她回过头）来了？坐吧。"],
          str([x.content for x in nodes(core, "assistant")]))
    check("标记为忙（前端要显示加载）", s.busy is True)
    check("刷新了消息", s.rebuilt is True)


def test_fallback_when_cannot_generate():
    print("\n== 2. 发不出去时退回显示原文（界面不能空着）==")
    s, core = mk([role_with("阿岚", GREET)], ["阿岚"], fire=False)
    n = html_app.HtmlApp._start_opening(s)
    check("仍然返回 1", n == 1, str(n))
    a = nodes(core, "assistant")
    check("插入了原文作为退路", len(a) == 1 and a[0].content == GREET,
          str([x.content for x in a]))
    check("标了 greeting 标记", (a[0].metadata or {}).get("greeting") is True)
    check("busy 已复位（没有请求在飞）", s.busy is False)


def test_no_trigger_cases():
    print("\n== 3. 不该触发的场合 ==")
    s, core = mk([role_with("阿岚", GREET)], ["阿岚"])
    core.tree.add_node("assistant", "之前的对话", parent_id=core.tree.current_leaf_id)
    check("已有历史 → 不重演", html_app.HtmlApp._start_opening(s) == 0)
    check("没有发出请求", not core.calls)

    s2, core2 = mk([role_with("甲", "甲的开场"), role_with("乙", "乙的开场")], ["甲", "乙"])
    check("群聊 → 不触发", html_app.HtmlApp._start_opening(s2) == 0)
    check("没有发出请求", not core2.calls)

    s3, _c3 = mk([{"name": "无白", "data": {}, "fields": {}}], ["无白"])
    check("无开场白 → 不触发", html_app.HtmlApp._start_opening(s3) == 0)

    s4, _c4 = mk([role_with("丙", "丙的开场")], [])
    check("未选角色 → 不触发", html_app.HtmlApp._start_opening(s4) == 0)

    s5, _c5 = mk([role_with("丁", "   \n ")], ["丁"])
    check("空白开场白 → 不触发", html_app.HtmlApp._start_opening(s5) == 0)

    s6, core6 = mk([{"name": "戊", "data": {"name": "戊"},
                     "fields": {"first_mes": "旧存档的开场白"}}], ["戊"])
    check("旧存档 fields 里的开场白也能用",
          html_app.HtmlApp._start_opening(s6) == 1)
    check("用的是旧存档那份", core6.calls == ["旧存档的开场白"], str(core6.calls))


# ============================================================
def test_payload_has_no_user_message():
    print("\n== 4. 开局载荷里不能有 user 消息 ==")
    core = ChatCore()
    core.client = pi._Client(pi.CAPTURE)
    core.set_model("deepseek-v4-flash")
    core.set_active_roles([{"name": "阿岚",
                            "system_prompt": "你现在的身份是：阿岚。\n【性格】\n温和\n"}])
    core.opening_cue = GREET
    pi.CAPTURE.clear()
    try:
        core._fetch_response(GREET, "阿岚", None, None, core.tree.current_leaf_id)
    except pi._Capture:
        pass
    msgs = pi.CAPTURE[0]["messages"] if pi.CAPTURE else []
    roles = [m["role"] for m in msgs]
    print("        载荷角色序列:", roles)
    check("没有 user 消息", "user" not in roles, str(roles))
    check("有 system", roles.count("system") >= 1, str(roles))
    body = "\n".join(m.get("content", "") for m in msgs)
    check("载荷里带上了开场场景", GREET in body)
    check("场景是最后一条 system",
          msgs[-1]["role"] == "system" and GREET in msgs[-1]["content"],
          "最后一条是 %s" % msgs[-1]["role"])


def test_cue_is_one_shot():
    print("\n== 5. 开场场景只能用一次（否则每轮都重演开场）==")
    core = ChatCore()
    core.client = pi._Client(pi.CAPTURE)
    core.set_model("deepseek-v4-flash")
    core.set_active_roles([{"name": "阿岚",
                            "system_prompt": "你现在的身份是：阿岚。\n【性格】\n温和\n"}])
    core.opening_cue = GREET
    for i in range(2):
        pi.CAPTURE.clear()
        try:
            core._fetch_response(GREET, "阿岚", None, None, core.tree.current_leaf_id)
        except pi._Capture:
            pass
        body = "\n".join(m.get("content", "") for m in pi.CAPTURE[0]["messages"])
        if i == 0:
            check("第 1 轮带场景", GREET in body)
        else:
            check("第 2 轮不再带场景", GREET not in body)
    check("cue 已被清空", core.opening_cue is None)


def test_opening_prompt_mentions_player():
    print("\n== 6. 场景指令必须点明「你」= 玩家角色 ==")
    core = ChatCore()
    core.set_player_persona({"name": "小林", "background": "记者"})
    txt = core._opening_prompt("（她把伞收起来）进来吧，外面雨大。")
    check("写明了「你」指玩家角色", "小林" in txt, "没提到玩家名")
    check("写了按玩家卡来演", "按玩家角色" in txt)
    check("写明了不要复述设定文字", "不要复述" in txt)
    check("写了留接话口子", "接话" in txt)
    check("场景原文附在里面", "进来吧，外面雨大" in txt)

    core2 = ChatCore()
    core2.set_player_persona(None)
    t2 = core2._opening_prompt("场景")
    check("无玩家卡时不崩", "玩家" in t2)


def test_prompt_no_longer_repeats_greeting():
    print("\n== 7. 开场白不再进 system 提示 ==")
    fields = {"appearance": "高个", "personality": "温和", "background": "旧书店老板",
              "speech": "慢", "first_mes": GREET, "mes_example": "例", "notes": "备注"}
    prompt = html_app.assemble_role_prompt("阿岚", fields, "")
    check("开场白不在提示里", GREET not in prompt)
    check("【开场白】小节也没了", "【开场白】" not in prompt)
    for label in ("外貌", "性格", "过去经历", "说话方式", "对话示例", "备注"):
        check(f"仍然包含【{label}】", ("【" + label + "】") in prompt)


def test_opening_loading_state():
    print("\n== 8. 开场加载态（不置位的话开局那段等待期界面一片空白）==")
    s, _core = mk([role_with("阿岚", GREET)], ["阿岚"])
    s.opening_loading = False
    html_app.HtmlApp._start_opening(s)
    check("开局时置位 opening_loading", s.opening_loading is True)
    check("同时 busy", s.busy is True)

    s2, _c2 = mk([role_with("阿岚", GREET)], ["阿岚"], fire=False)
    s2.opening_loading = False
    html_app.HtmlApp._start_opening(s2)
    check("退路分支收掉了加载态", s2.opening_loading is False)

    # 回复/出错路径要收掉 —— 读源码断言。
    # 这两条路径依赖大量应用状态，硬造桩反而容易测出假的通过/失败。
    src = io.open(os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"),
                  encoding="utf-8").read()
    i_resp = src.find("def _on_response(self")
    i_err = src.find("def _on_error(self")
    check("_on_response 里会收掉加载态",
          i_resp > 0 and "self.opening_loading = False" in src[i_resp:i_resp + 300])
    check("_on_error 里会收掉加载态",
          i_err > 0 and "self.opening_loading = False" in src[i_err:i_err + 400])

    check("api_state 暴露 opening_loading",
          '"opening_loading": self.opening_loading' in src)
    check("api_state / api_poll 都暴露",
          src.count('"opening_loading": self.opening_loading') >= 2,
          "只出现 %d 次" % src.count('"opening_loading": self.opening_loading'))

    html = io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    i_ss = html.find("function setStreaming")
    seg = html[i_ss:i_ss + 600]
    check("setStreaming 接受 loading 参数", "loading" in seg.split("{")[0])
    check("loading 时不移除元素", "if (!text && !loading)" in seg)
    check("空文本时显示占位符", "'…'" in seg)
    check("轮询处把 opening_loading 传下去了",
          "setStreaming(res.streaming, res.opening_loading)" in html)
    check("状态初始化处也传了",
          "setStreaming(s.streaming, s.opening_loading)" in html)


def test_android_has_same_loading_state():
    print("\n== 9. Android 也要有同一个加载态 ==")
    a = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")
    vm = io.open(os.path.join(a, "ChatViewModel.kt"), encoding="utf-8").read()
    app = io.open(os.path.join(a, "App.kt"), encoding="utf-8").read()
    check("ViewModel 里有 openingLoading 状态",
          "var openingLoading = mutableStateOf(false)" in vm)
    check("App 里接了 openingLoading", "var openingLoading by vm.openingLoading" in app)
    check("开局时置位", "openingLoading = true" in app)
    check("出错/回复时收掉", app.count("openingLoading = false") >= 2,
          "只出现 %d 次" % app.count("openingLoading = false"))
    check("加载气泡条件含 openingLoading",
          "streaming.isNotEmpty() || openingLoading" in app)
    check("没有流式文本时显示占位符", 'if (streaming.isEmpty()) "…"' in app)


def test_clear_history_restarts_opening():
    print("\n== 10. 清空历史后要重演开场白（复用开局路径）==")
    a = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")
    app = io.open(os.path.join(a, "App.kt"), encoding="utf-8").read()
    i = app.find("fun clearHistory(")
    check("找得到 App.kt 的 clearHistory", i > 0)
    if i < 0:
        return
    seg = app[i:i + 4000]
    j = seg.find("\n    fun ", 10)          # 截到下一个同级函数为止，别切进别人的代码
    if j > 0:
        seg = seg[:j]

    check("仍然重置机制状态（forceInitial，全量重建）", "forceInitial = true" in seg)
    check("仍然写回空树（防同步把旧历史捞回来）", "saveTree()" in seg)
    check("清空后会重演开场白（复用 ensureOpeningLine）", "ensureOpeningLine()" in seg)
    check("不会在生成中抢跑（有 busy 守卫）", "busy" in seg)
    # 顺序很关键：必须先把树清空，守卫里的「树为空」才成立，否则重演是空转
    check("重演排在清空之后", "tree.loadData" in seg and seg.find("ensureOpeningLine()") > seg.find("tree.loadData"),
          "ensureOpeningLine 在第 %d 字，tree.loadData 在第 %d 字"
          % (seg.find("ensureOpeningLine()"), seg.find("tree.loadData")))


if __name__ == "__main__":
    print("=" * 60)
    print("开场白测试（以「响应」形式演出）")
    print("=" * 60)
    test_opening_is_generated()
    test_fallback_when_cannot_generate()
    test_no_trigger_cases()
    test_payload_has_no_user_message()
    test_cue_is_one_shot()
    test_opening_prompt_mentions_player()
    test_prompt_no_longer_repeats_greeting()
    test_opening_loading_state()
    test_android_has_same_loading_state()
    test_clear_history_restarts_opening()
    print("\n" + "=" * 60)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
