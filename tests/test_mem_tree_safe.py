# -*- coding: utf-8 -*-
"""记忆压缩不许碰聊天树的闸门（test_mem_tree_safe）。

为什么需要这道闸
----------------
压缩会让"这一轮送进上下文的消息变少"，但**不许**让树里的节点变少。
两者混掉过一次的典型后果：用户点回档图跳回旧节点，发现内容被摘要顶掉了。

四类断言：
  ① plan() 是纯函数：跑完原数组深比较不变
  ② mem_scene 的所有写入都在 memory/ 下（出现 .tree 就红）
  ③ 树 round-trip：saveTree → loadData 后节点数 / 父子关系不变
  ④ 回溯：从中间节点沿父链取历史，窗口里**不能出现**该节点之后的消息
"""
import copy
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import mem_policy as P     # noqa: E402
import mem_scene as S      # noqa: E402
from core_tree import TreeManager   # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def build_tree(n=40):
    """造一条链：n0 → n1 → … → n(n-1)，并把叶子设为最后一条。"""
    t = TreeManager()
    parent = None
    ids = []
    for i in range(n):
        nid = t.add_node("user" if i % 2 == 0 else "assistant", u"第%d条" % i, parent_id=parent)
        ids.append(nid)
        parent = nid
    t.ensure_valid_leaf()
    return t, ids


def chain_from(manager, node_id):
    """从某节点沿父链往上取历史（模拟"回档到旧节点"时的取值方式）。"""
    out = []
    cur = manager.get_node(node_id)
    while cur is not None:
        out.append(cur)
        cur = manager.get_node(cur.parent_id) if cur.parent_id else None
    return list(reversed(out))


def main():
    tmp = tempfile.mkdtemp(prefix="mem_tree_safe_")
    try:
        print(u"\n== ① plan() 是纯函数 ==")
        msgs = [{"role": "user", "content": u"第%d条" % i} for i in range(50)]
        before = copy.deepcopy(msgs)
        plan = P.plan(msgs, "private")
        check(u"入参深比较不变", msgs == before)
        check(u"plan 有 window 与 dropped", "window" in plan and "dropped" in plan)
        check(u"window 是入参里最后那段",
              [m["content"] for m in plan["window"]] == [u"第%d条" % i for i in range(20, 50)])

        print(u"\n== ② 记忆写入不落到 .tree 下 ==")
        S.ensure_role(tmp, "private", u"咲")
        S.write_facts(tmp, "private", u"咲", [{"text": u"喜欢黑咖啡", "source": "n1", "t": 1}])
        S.write_rapport(tmp, "private", u"咲", {"closeness": 0.3})
        S.write_summary(tmp, "private", u"咲", u"摘要", stamp="20260101-000000")
        S.append_archive(tmp, "private", u"咲", [{"role": "user", "content": u"甲"}],
                         stamp="20260101-000000")
        written = []
        for dp, dns, fns in os.walk(tmp):
            for f in fns:
                written.append(os.path.join(dp, f))
        check(u"确实写了文件", len(written) >= 4)
        check(u"没有一条写到 .tree 里", all(".tree" not in p.replace("\\", "/") for p in written))
        check(u"全部都在 memory/<场景>/ 下",
              all("private" in p.replace("\\", "/") or "group" in p.replace("\\", "/")
                  for p in written))

        print(u"\n== ③ 树 round-trip：节点数 / 父子关系不变 ==")
        t1, ids1 = build_tree(40)
        data = t1.get_all_nodes_data()
        dumped = json.dumps(data, ensure_ascii=False)
        check(u"导出是 JSON 可序列化的", bool(dumped))
        t2 = TreeManager()
        t2.load_nodes_data(json.loads(dumped))
        check(u"节点数一致", t2.count_nodes() == t1.count_nodes() == 40)
        check(u"每个节点都还在", all(t2.get_node(i) is not None for i in ids1))
        check(u"父链一致",
              all((t2.get_node(i).parent_id == t1.get_node(i).parent_id) for i in ids1))
        check(u"正文没被摘要替换",
              all(t2.get_node(i).content == t1.get_node(i).content for i in ids1))

        print(u"\n== ④ 回溯：窗口里不出现「该节点之后」的消息 ==")
        mid = ids1[20]
        chain = chain_from(t1, mid)
        check(u"沿父链能取到 21 条（含自己）", len(chain) == 21)
        win, dropped = P.split([{"id": n.id, "content": n.content} for n in chain], "private")
        tail_ids = set(ids1[21:])
        check(u"窗口里没有未来的节点", all(m["id"] not in tail_ids for m in win))
        check(u"窗口最后一条就是当前节点", win[-1]["id"] == mid)
        check(u"不足窗口时 dropped 为空", dropped == [])

        print(u"\n== ⑤ 压缩不改树：先算 plan 再 round-trip ==")
        t3, ids3 = build_tree(60)
        flat = [{"id": i, "content": t3.get_node(i).content} for i in ids3]
        before_nodes = t3.count_nodes()
        P.plan(flat, "group", last_compress_ts=None, now=10 ** 9)
        check(u"跑完 plan 节点数没变", t3.count_nodes() == before_nodes)
        t4 = TreeManager()
        t4.load_nodes_data(json.loads(json.dumps(t3.get_all_nodes_data(), ensure_ascii=False)))
        check(u"再 round-trip 仍是 60 个节点", t4.count_nodes() == 60)
        check(u"叶子仍指向最后一条", t4.get_current_chain() and
              t4.get_current_chain()[-1]["content"] == t3.get_node(ids3[-1]).content)

        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1 if FAIL else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌