# -*- coding: utf-8 -*-
"""Galgame 选项插件测试：解析器 + 生成流程（stub LLM）。
运行：python tests/test_choices_plugin.py"""
import sys, os, json, time, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "plugins"))

# 隔离插件设置路径（避免读写真实 plugin_settings/）
import app_paths
_iso = tempfile.mkdtemp(prefix="dick_ps_")
app_paths.get_base_dir = lambda: _iso

from galgame_choices_plugin import GalgameChoicesPlugin

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

print("== ① 选项解析 ==")
p = GalgameChoicesPlugin(None)
def texts(items):
    return [x["text"] for x in items]
check(texts(p._parse_options('["轻轻敲门","转身离开","直接推门而入"]', 3)) ==
      ["轻轻敲门", "转身离开", "直接推门而入"], "JSON 数组")
check(texts(p._parse_options('```json\n["A","B","C"]\n```', 3)) == ["A", "B", "C"], "代码块 JSON")
check(texts(p._parse_options('1. 选项甲\n2. 选项乙\n3. 选项丙', 3)) == ["选项甲", "选项乙", "选项丙"], "编号列表")
check(texts(p._parse_options('- 第一\n* 第二\n• 第三', 3)) == ["第一", "第二", "第三"], "项目符号")
check(texts(p._parse_options('["重复","重复","唯一"]', 3)) == ["重复", "唯一"], "去重")
check(len(p._parse_options('["1","2","3","4","5"]', 3)) == 3, "数量上限")
check(texts(p._parse_options('["A"]', 3)) == ["A"], "少于上限不补")
check(p._parse_options('垃圾输出', 3) == [], "无法解析返回空")
# 机制效果选项：{text, result, aff, st} 对象
eff = p._parse_options('[{"text":"温柔关心她","result":"她可能会心头一暖","aff":+3},{"text":"冷嘲热讽","aff":-5,"st":{"mood":"生气"}},"普通选项"]', 3)
check(eff[0]["text"] == "温柔关心她" and eff[0]["aff"] == 3 and eff[0]["result"] == "她可能会心头一暖" and "st" not in eff[0], "对象选项：result+aff 生效")
check(eff[1]["text"] == "冷嘲热讽" and eff[1]["aff"] == -5 and eff[1]["st"]["mood"] == "生气" and "result" not in eff[1], "对象选项：aff+st 无 result")
check(eff[2] == {"text": "普通选项"}, "字符串选项：无效果字段")
# 宽容解析：尾随逗号 / 前后文本包裹 / JSON 残留行跳过 / 末尾括号剥离
check(texts(p._parse_options('[{"text":"甲","aff":+1,},{"text":"乙"}]', 3)) == ["甲", "乙"], "尾随逗号容忍")
check(texts(p._parse_options('好的，为你生成：\n[{"text":"甲"},{"text":"乙"}]\n请选择。', 3)) == ["甲", "乙"], "前后文本包裹提取")
check(texts(p._parse_options('[\n  {"text":"甲"},\n  {"text":"乙"}\n]', 3)) == ["甲", "乙"], "多行 JSON")
check(texts(p._parse_options('1. 温柔关心她（她可能会开心）\n2. 转身离开', 3)) == ["温柔关心她", "转身离开"], "末尾括号说明剥离")
check(p._parse_options('{"text":"甲"}\n{"text":"乙"}', 3) == [], "纯 JSON 对象行不显示为选项")
check(p._parse_options('{"text":"甲"}', 3) == [], "单对象非数组不误当选项")

print("== ② 生成流程 ==")
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

class FakeTree:
    nodes = {}
    current_leaf_id = None
class FakeCore:
    def __init__(self, content=None):
        self.client = FakeClient(content) if content is not None else None
        self.model = "test-model"
        self.is_processing = False
        self.tree = FakeTree()
    def get_current_chain(self): return []

# 无 client → 手动触发报错提示
p2 = GalgameChoicesPlugin(FakeCore(None))
okflag, msg = p2.manual_generate()
check(okflag is False and "启动聊天" in msg, "无 client 时给出提示")

# stub client 返回 JSON → 生成成功
p3 = GalgameChoicesPlugin(FakeCore('["悄悄靠近","大声呼唤","原地等待"]'))
okflag, msg = p3.manual_generate()
check(okflag is True and "正在生成" in msg, "手动触发返回状态")
deadline = time.time() + 10
while p3.choices_loading and time.time() < deadline:
    time.sleep(0.05)
check(p3.choices_loading is False and p3.choices_error == "", "状态复位")
check(texts(p3.choices) == ["悄悄靠近", "大声呼唤", "原地等待"], "生成结果解析正确（对象格式）")

# 无法解析 → error 记录
p4 = GalgameChoicesPlugin(FakeCore("完全不是列表"))
p4.manual_generate()
deadline = time.time() + 10
while p4.choices_loading and time.time() < deadline:
    time.sleep(0.05)
check(p4.choices == [] and p4.choices_error != "", "解析失败记录 error")

# clear_choices 复位
p4.clear_choices()
check(p4.choices == [] and p4.choices_error == "" and p4.choices_loading is False, "clear_choices 复位")

# 同一用户节点不重复自动生成（滑条场景）
class TreeWithLeaf:
    def __init__(self):
        self.nodes = {"u1": type("n", (), {"role": "user", "parent_id": None})(),
                      "a1": type("n", (), {"role": "assistant", "parent_id": "u1"})()}
        self.current_leaf_id = "a1"
class CoreWithLeaf:
    def __init__(self):
        self.client = FakeClient('["甲","乙"]')
        self.model = "m"
        self.is_processing = False
        self.tree = TreeWithLeaf()
    def get_current_chain(self):
        return [{"role": "user", "content": "u", "metadata": {}},
                {"role": "assistant", "content": "a", "metadata": {"speaker": "AI"}}]

p5 = GalgameChoicesPlugin(CoreWithLeaf())
p5.on_message_received("", "第一版回复")
deadline = time.time() + 10
while p5.choices_loading and time.time() < deadline:
    time.sleep(0.05)
first = list(p5.choices)
check(texts(first) == ["甲", "乙"] and p5._gen_user_node == "u1", "自动模式生成并记录用户节点")
p5.on_message_received("", "第二版回复（滑条）")
time.sleep(0.3)
check(p5.choices == first, "同一用户节点不重复生成（滑条）")
p5.clear_choices()
p5.on_message_received("", "第三版回复")
deadline = time.time() + 10
while p5.choices_loading and time.time() < deadline:
    time.sleep(0.05)
check(texts(p5.choices) == ["甲", "乙"], "清空后同一节点可再生成")

print("结果：%d 通过, %d 失败" % (ok, bad))
shutil.rmtree(_iso, ignore_errors=True)
sys.exit(1 if bad else 0)
