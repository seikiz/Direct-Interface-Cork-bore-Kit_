# -*- coding: utf-8 -*-
"""probe_payload.py —— 用桩把 _fetch_response 的真实载荷截下来（测试用工具）。

放在 tests/ 里而不是工程根：工程根的 `_*.py` 被 .gitignore 忽略（那是开发草稿的约定），
于是 CI 的干净检出里根本没有它 —— tests/test_time_context.py 里
`from _probe_payload import make_probe` 就会 ModuleNotFoundError（2026-10 真事）。
**测试要用的辅助模块必须跟着测试一起进仓库。**

为什么需要它：测试要证"时间那段真的进了 API 载荷"。
但 _fetch_response 依赖 22 个 self 属性，直接用 __new__ 造实例会一路抛
AttributeError 并被 except 吞掉，表现成"载荷截不到"，非常难查。
所以这里一次性把这段代码用到的依赖全装成桩。

这段用到的 self 属性（grep 出来的，共 22 个）：
    tree, injector, active_roles, document_context, mechanism_state,
    _mech_config, pending_event, last_event, opening_cue, speculator,
    player_persona, system_prompt_base, _drift_keys, _case_text,
    _group_speaker, _battle_config(), _build_role_prompt(),
    _fit_budget(), _format_assistant_content(), _inject_world_context(),
    _opening_prompt(), _pick_group_speaker(), _resolve_addressed(),
    _role_by_name(), _roster_names(), CREATION_PREMISE
"""
import os
import sys
import threading
from datetime import datetime, timedelta

# 自己在 tests/ 下，工程根是上一层
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def make_probe():
    from DICK_core import ChatCore, TreeManager

    captured = {}

    class Probe(ChatCore):
        CREATION_PREMISE = "（测试桩）"

        def __init__(self):
            self.tree = TreeManager()
            self.client = object()             # 骗过"没设 API Key"的早退
            self._proc_lock = threading.RLock()
            self.active_roles = []
            self.document_context = ""
            self.mechanism_state = None
            self._mech_config = None
            self.pending_event = None
            self.last_event = None
            self.opening_cue = ""
            self.speculator = None
            self.player_persona = None
            self.system_prompt_base = ""
            self._drift_keys = None
            self._case_text = None
            self._group_speaker = None
            self.context_budget = 20000
            self.injector = None

        # ---- 被调用的方法<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌全给最小实现 ----
        def _battle_config(self):
            return None

        def _build_role_prompt(self, role):
            return ""

        def _role_by_name(self, name):
            return None

        def _roster_names(self):
            return []

        def _pick_group_speaker(self, text, roster):
            return None

        def _resolve_addressed(self, text):
            return None

        def _inject_world_context(self, text):
            return ""

        def _opening_prompt(self, cue):
            return ""

        def _format_assistant_content(self, msg):
            return msg.get("content") or ""

        def _fit_budget(self, messages):
            # 预算裁剪不参与这个测试，原样返回即可
            return messages

        def _stream_create(self, messages, on_stream=None):
            captured["m"] = messages
            return ""

        def _time_scale(self):
            # 固定 1 倍：这个桩用来验"注入链路通不通"，
            # 不该掺进系统设置里的倍率（默认 720 会把 40 小时报成 40 个月，
            # 断言就会莫名其妙地挂）。
            return 1.0

    return Probe, captured


if __name__ == "__main__":
    Probe, captured = make_probe()
    p = Probe()
    uid = p.tree.add_node("user", "你好")
    p.tree.add_node("assistant", "嗯。", parent_id=uid)
    # 造一个 40 小时间隔：倒数第二条在过去，最后一条在现在
    nodes = list(p.tree.nodes.values())
    p.tree.nodes[p.tree.current_leaf_id].timestamp = datetime.now().isoformat()
    if len(nodes) >= 2:
        nodes[-2].timestamp = (datetime.now() - timedelta(hours=40)).isoformat()

    errs = []
    p._fetch_response("在吗", None, lambda *a, **k: None,
                      lambda m, *a, **k: errs.append(m),
                      parent_node_id=None, _locked=True)
    print("on_error =", errs)
    msgs = captured.get("m")
    print("载荷条数 =", len(msgs) if msgs else None)
    if msgs:
        for m in msgs:
            c = str(m.get("content") or "")
            if "【时间】" in c:
                print("时间段落 =", c[:160])
