# -*- coding: utf-8 -*-
"""真·多角色群聊测试（B 方案：物理隔离）：
1) 公共 system 只列名单不含角色设定
2) 专属 prompt 只含目标角色设定（隔离）
3) 群聊未指定角色 → DICK 轮换（非最后发言者）
4) @指定角色 → 用指定角色
5) 历史消息带 [角色名]: 前缀
运行：python tests/test_groupchat.py"""
import sys, os, json, re

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from DICK_core import ChatCore

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

def make_core():
    c = ChatCore()
    c.set_active_roles([
        {"name": "甲", "system_prompt": "甲的秘密：喜欢猫，怕狗。", "unlocked": False},
        {"name": "乙", "system_prompt": "乙的秘密：讨厌猫，养蛇。", "unlocked": False},
        {"name": "丙", "system_prompt": "丙的秘密：恐高，爱做饭。", "unlocked": False},
    ])
    c._rebuild_system_node()
    return c

print("== ① 公共框架：只列名单，不含角色设定（物理隔离） ==")
c = make_core()
sysnode = c.tree.nodes[c.tree.root_id].content
check("甲" in sysnode and "乙" in sysnode and "丙" in sysnode, "公共框架含全体成员名单")
check("喜欢猫" not in sysnode and "养蛇" not in sysnode and "爱做饭" not in sysnode,
      "公共框架不含任何角色设定（隔离）")
check("[角色名]: 内容" in sysnode, "公共框架含回复格式规则")

print("== ② 专属 prompt：只含目标角色 ==")
p_乙 = c._build_role_prompt(c._role_by_name("乙"))
check("你现在的身份是：乙" in p_乙, "专属 prompt 身份锚")
check("讨厌猫" in p_乙 and "养蛇" in p_乙, "专属 prompt 含乙设定")
check("喜欢猫" not in p_乙 and "爱做饭" not in p_乙, "专属 prompt 不含甲/丙设定（隔离）")
check("[乙]:" in p_乙, "专属 prompt 强制乙的回复格式")

print("== ③ 轮换决策：未指定 → 非最后发言者 ==")
c2 = make_core()
c2.last_speaker = "甲"
# 模拟 _fetch_response 的群聊决策逻辑（与代码一致）
roster = c2._roster_names()
last = getattr(c2, 'last_speaker', None)
cand = [n for n in roster if n != last] or roster[1:] or roster
check(cand[0] != "甲" and cand[0] in roster, "轮换避开最后发言者甲 → %s" % cand[0])

print("== ④ 历史消息带 [角色名]: 前缀 ==")
c3 = make_core()
n1 = c3.add_user_message("大家好")
c3.tree.nodes[n1].metadata["speaker"] = "你"
n2 = c3.tree.add_node('assistant', "早上好", parent_id=n1, metadata={"speaker": "甲"})
chain = c3.get_current_chain()
asst = [m for m in chain if m['role'] == 'assistant']
formatted = [c3._format_assistant_content(m) for m in asst]
check(any(f.startswith("[甲]:") for f in formatted), "历史 assistant 带 [甲]: 前缀")

print("== ⑤ @指定角色解析 ==")
addr = c3._resolve_addressed("[你]: @乙 今天去哪")
check(addr == "乙", "@乙 解析正确: %r" % addr)
addr2 = c3._resolve_addressed("随便聊聊")
check(addr2 is None, "无 @ 返回 None")

print("== ⑥ 归属一致性：addressed == 轮换角色 ==")
c4 = make_core()
c4.last_speaker = "丙"
roster4 = c4._roster_names()
cand4 = [n for n in roster4 if n != "丙"] or roster4[1:] or roster4
chosen = cand4[0]
check(chosen in roster4 and chosen != "丙", "轮换选定 %s（≠丙）" % chosen)
# 公共框架 + 专属 prompt 组合：完整 system（模拟 _fetch_response）
target = c4._role_by_name(chosen)
full = c4.tree.nodes[c4.tree.root_id].content + "\n\n" + c4._build_role_prompt(target)
check(f"你现在的身份是：{chosen}" in full, "完整 system 含目标角色身份锚")

print("== ⑦ 端到端：@指定角色 → system 只含该角色（物理隔离） ==")
import time
captured = {}
class _FakeCompletions:
    def create(self, **kw):
        captured['messages'] = kw['messages']
        ch = type('C', (), {'delta': type('D', (), {'content': '好的。'})()})()
        return iter([type('R', (), {'choices': [ch]})()])
class _FakeChat:
    completions = _FakeCompletions()
class _FakeClient:
    chat = _FakeChat()

c5 = make_core()
c5.client = _FakeClient()
n5 = c5.add_user_message("@乙 你觉得猫怎么样")
done5 = {}; errs5 = []
c5.generate_candidate(n5, on_response=lambda r, u: done5.setdefault('r', r),
                      on_error=lambda e: errs5.append(e))
for _ in range(200):
    if done5 or errs5 or not c5.is_processing:
        break
    time.sleep(0.05)
check(bool(done5) and not errs5, "端到端调用完成 (errs=%r)" % (errs5[:1],))
msgs5 = captured.get('messages', [])
sys5 = " ".join(str(m.get('content', '')) for m in msgs5 if m['role'] == 'system')
check("讨厌猫" in sys5 and "你现在的身份是：乙" in sys5, "@乙 → system 含乙设定与身份锚")
check("喜欢猫" not in sys5 and "爱做饭" not in sys5, "@乙 → system 不含甲/丙设定（物理隔离）")

print("== ⑧ 端到端：未指定 → 轮换角色 ==")
captured.clear()
c6 = make_core()
c6.client = _FakeClient()
c6.last_speaker = "甲"
n6 = c6.add_user_message("随便聊聊")
done6 = {}; errs6 = []
c6.generate_candidate(n6, on_response=lambda r, u: done6.setdefault('r', r),
                      on_error=lambda e: errs6.append(e))
for _ in range(200):
    if done6 or errs6 or not c6.is_processing:
        break
    time.sleep(0.05)
msgs6 = captured.get('messages', [])
sys6 = " ".join(str(m.get('content', '')) for m in msgs6 if m['role'] == 'system')
# 轮换应避开甲（最后发言者），选择乙或丙
check("喜欢猫" not in sys6, "未指定 → 不含甲的设定（隔离）")
check(("你现在的身份是：乙" in sys6) or ("你现在的身份是：丙" in sys6),
      "未指定 → 轮换到非最后发言者角色: %s" % ("乙" if "身份是：乙" in sys6 else "丙"))

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
