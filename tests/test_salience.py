# -*- coding: utf-8 -*-
"""记忆清晰度测试：有损、有选择、且不可反推。

起因：原来的 _fit_budget 是【按长度从新到旧填，填满就断】——
最近的全量进，更旧的全量压成摘要。中间那个状态（有的记得清清楚楚、
有的完全没了、有的只剩模糊印象）根本不存在。而这个模块要造的就是中间态。

要证的：
  ① 隐藏衰减率是【确定性】的（同样存档永远同样结果 → 可复现、可测试）
  ② 但不同节点不一样（→ 用户推导不出"她什么时候会忘"，不可建模）
  ③ 单位没搞错（time.time() 是秒，衰减率是天 —— 漏 /86400 就全忘光）
  ④ 近窗无条件保留（对话连贯性不能被"记性"破坏）
  ⑤ 旧但清晰的事能挤在"新但模糊的"前面（现实里就会这样）
  ⑥ 低于阈值的 = 真忘了，【不进摘要】（不能靠摘要把忘掉的救回来）
  ⑦ 被提起过 → 记得更牢
  ⑧ 接到 _fit_budget 上了，而且出网前内部字段被剥干净

跑法：utau_env\\Scripts\\python.exe tests\\test_salience.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import salience as S   # noqa: E402

PASS = 0
FAIL = 0
DAY = 86400.0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [OK] %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s  %s" % (name, detail))


def est(m):
    return max(1, len(str(m)) // 2)      # 粗略 token 估计，测试够用


def msg(nid, text, age_days=0.0, now=None):
    now = now if now is not None else time.time()
    return {"role": "user", "content": text, "_node_id": nid,
            "_ts": now - age_days * DAY}


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_deterministic_but_unmodelable():
    print("\n== ① 确定性：同样 id 永远同样衰减率（可复现、可测试）==")
    a1 = S.hidden_decay("node-abc")
    a2 = S.hidden_decay("node-abc")
    check("同一 id 两次结果相同", a1 == a2, "%.6f vs %.6f" % (a1, a2))
    check("在 [DECAY_MIN, DECAY_MAX] 内",
          S.DECAY_MIN <= a1 <= S.DECAY_MAX, "%.4f" % a1)
    check("空 id 不崩", isinstance(S.hidden_decay(None), float))

    print("\n      不同 id 要不一样 —— 否则就成了「她总是忘第20条」那种可推规则")
    vals = [S.hidden_decay("n%d" % i) for i in range(300)]
    check("300 个节点取值互不相同的比例 > 90%",
          len(set(round(v, 6) for v in vals)) > 270,
          "%d 个不同" % len(set(round(v, 6) for v in vals)))
    fast = [v for v in vals if v > S.DECAY_MAX * 0.6]
    check("确实存在快忘档（不是所有节点一样快）", len(fast) > 0,
          "快忘 %d 个" % len(fast))
    check("快忘档占比接近 DECAY_PORTION(%.2f)" % S.DECAY_PORTION,
          0.10 < len(fast) / len(vals) < 0.40,
          "实际 %.2f" % (len(fast) / len(vals)))
    print("      衰减率分布：min=%.3f  中位=%.3f  max=%.3f"
          % (min(vals), sorted(vals)[len(vals) // 2], max(vals)))


def test_time_units():
    print("\n== ② 单位：秒 vs 天（漏 /86400 会让几秒内忘光）==")
    now = time.time()
    m = msg("u1", "普通一句话", age_days=0.0, now=now)
    s0 = S.salience(m, now=now)
    s10s = S.salience(msg("u1", "普通一句话", age_days=10 / DAY, now=now), now=now)
    check("刚说过：清晰度 ≥ 1（无情绪无提起时基线正好是 1.0）",
          s0 >= 1.0, "%.4f" % s0)
    check("过了 10 秒基本没变化（>90% 残留）",
          s10s > s0 * 0.90, "%.4f vs %.4f" % (s10s, s0))
    d1 = S.salience(msg("u1", "普通一句话", age_days=1, now=now), now=now)
    check("过了 1 天明显下降但还在", 0.0 < d1 < s0, "%.4f" % d1)
    d30 = S.salience(msg("u1", "普通一句话", age_days=30, now=now), now=now)
    check("过了 30 天基本忘了（<1.0）", d30 < S.KEEP_THRESHOLD, "%.4f" % d30)
    print("      0秒=%.3f  10秒=%.3f  1天=%.3f  30天=%.3f" % (s0, s10s, d1, d30))


def test_emotion_and_length():
    print("\n== ③ 情绪强 / 说了一大段 → 记得更牢 ==")
    now = time.time()
    plain = S.salience(msg("x", "今天下雨了，我在看书。", age_days=3, now=now), now=now)
    emot = S.salience(msg("x", "别走！我怕……你答应过我的！", age_days=3, now=now), now=now)
    check("带情绪的更清晰", emot > plain, "%.4f vs %.4f" % (emot, plain))
    longm = S.salience(msg("x", "字" * 400, age_days=3, now=now), now=now)
    check("一大段话比一句话清晰", longm > plain, "%.4f vs %.4f" % (longm, plain))
    check("情绪强度有上限（不能一条感叹号刷满）",
          S.emotion("！" * 200) <= S.EMOTION_MAX, "%.2f" % S.emotion("！" * 200))


def test_mention_boost():
    print("\n== ④ 被提起过 → 记得更牢 ==")
    S.reset_mentions()
    now = time.time()
    m = msg("m1", "普通内容", age_days=5, now=now)
    before = S.salience(m, now=now)
    S.mark_mentioned("m1", now=now)
    after1 = S.salience(m, now=now)
    check("提过一次 → 清晰度上升", after1 > before,
          "%.4f → %.4f" % (before, after1))
    for _ in range(10):
        S.mark_mentioned("m1", now=now)
    after2 = S.salience(m, now=now)
    check("加成有上限", after2 <= S.KEEP_THRESHOLD + S.MENTION_BOOST_MAX + 1.0,
          "%.4f" % after2)
    print("      未提起=%.3f  提1次=%.3f  提11次=%.3f" % (before, after1, after2))
    S.reset_mentions()
    check("reset 之后回到原值",
          abs(S.salience(m, now=now) - before) < 1e-9, "%.4f" % S.salience(m, now=now))


def test_recent_window_kept():
    print("\n== ⑤ 近窗无条件保留（对话连贯性优先）==")
    now = time.time()
    msgs = []
    for i in range(20):
        # 第 0~7 条很旧且无情绪；第 8~19 条是"最近"
        old = i < 8
        msgs.append(msg("n%d" % i, "内容%d" % i,
                        age_days=(40 if old else 0.01), now=now))
    r = S.select(msgs, recent_window=12, budget_tokens=10 ** 6,
                 est_tokens=est, now=now)
    kept_idx = [msgs.index(m) for m in r["kept"]]
    recent = [i for i in range(8, 20)]
    check("12 条近窗全部保留",
          all(i in kept_idx for i in recent), str(sorted(kept_idx)))
    check("保留顺序仍是原始顺序", kept_idx == sorted(kept_idx), str(kept_idx))
    check("忘了足够旧的", len(r["forgotten"]) > 0,
          "忘了 %d 条" % len(r["forgotten"]))


def test_old_but_vivid_beats_new_but_faded():
    print("\n== ⑥ 旧但清晰的事，能挤在「新但已经模糊」的前面 ==")
    now = time.time()
    # 先确认两条的清晰度确实是"旧的反而更高" —— 不然测的是别的东西。
    # 注意：衰减率是每个节点【隐藏且随机】的，所以选 id 时要挑一个慢忘档的，
    # 否则这条"旧但清晰"的会被它自己的快忘率吃掉（第一版就踩了这个）。
    vivid_slow = None
    for i in range(200):
        cand = "vivid%d" % i
        if S.hidden_decay(cand) < S.DECAY_MIN + 0.06:
            vivid_slow = cand
            break
    check("找得到一个慢忘档的节点 id", vivid_slow is not None, str(vivid_slow))
    vivid_text = "我一直记得那天你说过要等我，别忘了。我怕我会等不到。" * 2
    vivid = msg(vivid_slow, vivid_text, age_days=2, now=now)
    faded = msg("faded", "嗯。", age_days=25, now=now)
    s_v, s_f = S.salience(vivid, now=now), S.salience(faded, now=now)
    print("      旧但清晰：%.3f（%s，衰减率 %.3f）" % (s_v, vivid_slow, S.hidden_decay(vivid_slow)))
    print("      新但模糊：%.3f" % s_f)
    check("旧的清晰度确实更高", s_v > s_f, "%.3f vs %.3f" % (s_v, s_f))
    check("旧的够得上保留阈值", s_v >= S.KEEP_THRESHOLD, "%.3f" % s_v)

    head = [msg("h%d" % i, "近的%d" % i, age_days=0.0, now=now) for i in range(3)]
    pool = [vivid, faded] + head
    budget = sum(est(m["content"]) for m in head) + est(vivid_text)
    r = S.select(pool, recent_window=3, budget_tokens=budget,
                 est_tokens=est, now=now)
    got = [m["_node_id"] for m in r["kept"]]
    check("旧但清晰的那条被想起来", vivid_slow in got, str(got))
    print("      想起来：%s" % [x["content"][:16] for x in r["recalled"]])


def test_forgotten_not_summarized():
    print("\n== ⑦ 真忘了的【不进摘要】（不能靠摘要把忘掉的救回来）==")
    now = time.time()
    ancient = msg("old", "很久以前一句平淡的话。", age_days=90, now=now)
    head = [msg("h%d" % i, "近的%d" % i, age_days=0.0, now=now) for i in range(3)]
    r = S.select([ancient] + head, recent_window=3, budget_tokens=10 ** 6,
                 est_tokens=est, now=now)
    check("90 天前的平淡内容被判为忘了", len(r["forgotten"]) == 1,
          str(r["forgotten"]))
    check("忘了的不在 kept 里",
          all(m["_node_id"] != "old" for m in r["kept"]), str(r["kept"]))
    check("忘了的也不在 dropped 里（dropped 才会进摘要）",
          len(r["dropped"]) == 0, str(r["dropped"]))
    check("清晰度确实低于阈值",
          r["forgotten"][0]["score"] < S.KEEP_THRESHOLD,
          str(r["forgotten"][0]["score"]))

    print("\n      对照：清晰度够但预算塞不下 → 进 dropped（会转摘要）")
    vivid = msg("v2", "我一直记得那天你说过要等我，别忘了。" * 4,
                age_days=0.5, now=now)
    head2 = [msg("k%d" % i, "近的%d" % i, age_days=0.0, now=now) for i in range(3)]
    tight = sum(est(m["content"]) for m in head2)      # 只剩 0 预算给远窗
    r2 = S.select([vivid] + head2, recent_window=3, budget_tokens=tight,
                  est_tokens=est, now=now)
    check("塞不下的进了 dropped", len(r2["dropped"]) == 1, str(r2["dropped"]))
    check("dropped 的不是 forgotten", len(r2["forgotten"]) == 0,
          str(r2["forgotten"]))


def test_graceful_degradation():
    print("\n== ⑧ 没有 _node_id 的消息不被误判 ==")
    now = time.time()
    bare = [{"role": "user", "content": "没有内部字段"},
            {"role": "assistant", "content": "也没有"}]
    check("清晰度返回 0（无从判断）",
          all(S.salience(m, now=now) == 0.0 for m in bare))
    r = S.select(bare, recent_window=0, budget_tokens=10 ** 6,
                 est_tokens=est, now=now)
    check("近期窗口为 0 时，最后一条仍在 kept（调用方兜底）",
          len(r["kept"]) >= 1, str(len(r["kept"])))
    check("空输入不崩", S.select([], 5, 100, est, now=now)["kept"] == [])


def test_wired_into_fit_budget():
    print("\n== ⑨ 接到 _fit_budget 上了吗 ==")
    from DICK_core import ChatCore, TreeManager
    core = ChatCore.__new__(ChatCore)
    core.tree = TreeManager()
    core.context_budget = 20000
    core.rolling_summary = ""
    core.rolling_summary_enabled = False
    core._summarizing = False
    core._summary_lock = __import__("threading").RLock()
    core.recent_window = 4

    now = time.time()
    ids = []
    # 必须串成一条链（parent_id 接上一条）—— get_current_chain 是沿父指针走的。
    # 不接的话 30 个节点全挂在根下，链只有 1 条（第一版就踩了）。
    # 内容刻意分成两档：前半【带情绪】（该被记住），后半【平淡】（该被忘掉）。
    # 全用平淡内容的话会全部正确地被忘掉，也就验不出"有选择"这个性质。
    prev = None
    EMOT = ("别走！我怕……你答应过我的！", "我恨你。可是我又想你。",
            "第一次见你的时候，我就在想，千万别喜欢上这个人。")
    for i in range(30):
        text = EMOT[i % len(EMOT)] if i < 14 else "第%d条" % i
        prev = core.tree.add_node("user" if i % 2 == 0 else "assistant",
                                  text, parent_id=prev)
        ids.append(prev)
    # 时间拉开：越靠前越旧（3~20 天），最近 6 条是刚才。
    # 不能全设成 60 天 —— 中位衰减率 0.264 时 0.736^60 ≈ 1e-8，
    # 全都会被正确地忘掉，于是只剩近窗，验不出顺序（第一版就踩了）。
    nodes = list(core.tree.nodes.values())
    for i, n in enumerate(nodes):
        age_days = 0.01 if i >= 24 else (3 + (20 - 3) * (24 - i) / 24.0)
        n.timestamp = _iso(now - age_days * DAY)
    chain = core.tree.get_current_chain()
    check("链里带了 _node_id", all("_node_id" in m for m in chain),
          str([k for k in chain[0].keys()]))
    check("链里带了 _ts", all(isinstance(m.get("_ts"), float) for m in chain))

    msgs = [{"role": m["role"], "content": m["content"],
             "_node_id": m["_node_id"], "_ts": m["_ts"]} for m in chain]
    msgs.append({"role": "user", "content": "现在说话"})
    out = core._fit_budget(msgs)
    check("_fit_budget 跑通", isinstance(out, list) and len(out) > 0,
          str(len(out)))
    check("最后一条用户消息还在",
          out[-1]["content"] == "现在说话", str(out[-1]))
    kept_ids = [m.get("_node_id") for m in out if m.get("_node_id")]
    check("旧的平淡内容被忘掉了（不再全量塞入）",
          len(kept_ids) < len(ids), "留了 %d / %d" % (len(kept_ids), len(ids)))
    # 顺序要按【链里的真实顺序】比 —— 链用的是节点真 id(uuid)，
    # 不是我建节点时编的 n0..n29（第一版拿两套命名比，必然失败）。
    chain_ids = [m["_node_id"] for m in chain]
    want = [i for i in chain_ids if i in kept_ids]
    check("保留的顺序没乱", kept_ids == want,
          "kept=%s want=%s" % (kept_ids[:6], want[:6]))
    # 真正要证的性质：不是"新的全留旧的不要"，而是【有选择】——
    # 有旧事被想起来，也有旧事被忘掉。
    soft = [i for i in chain_ids if i not in chain_ids[-6:]]
    recalled_old = [i for i in kept_ids if i in soft]
    check("确实想起了一些旧事（不是只剩近窗）", len(recalled_old) > 0,
          "想起 %d 条，留了 %d 条，链共 %d 条"
          % (len(recalled_old), len(kept_ids), len(chain_ids)))
    check("也不是全留（确实忘了东西）", len(kept_ids) < len(chain_ids),
          "留了 %d / %d" % (len(kept_ids), len(chain_ids)))
    print("      留下 %d 条 / 链共 %d 条（想起旧事 %d 条）"
          % (len(kept_ids), len(chain_ids), len(recalled_old)))
    # 注意：这里【不】比较"情绪条数 vs 平淡条数"——因为情绪消息落在更旧的
    # 位置、平淡的落在更新的位置，年龄和内容混在一起是混淆变量
    # （第一版就这么错了）。情绪的作用改用下面的控制变量测试。

    print("\n      出网前必须剥掉内部字段")
    try:
        import inspect
        src = inspect.getsource(ChatCore._mk_stream)
        check("_mk_stream 里有剥离逻辑",
              "startswith(\"_\")" in src or "startswith('_')" in src,
              src[:120])
    except Exception as e:
        check("能读到 _mk_stream 源码", False, repr(e))


def test_memory_lifespan():
    print("\n== ⑩ 记忆寿命：参数别拍脑袋，用量出来的数当断言 ==")
    # 这一条是标定过程留下的。第一版参数太狠（中位衰减率 0.264 + 阈值 1.0），
    # 平淡内容半天就掉到阈值以下 —— 角色会把两天前的事全忘掉，那是失忆不是记忆。
    # 所以这里把"该活多久"写成断言，以后谁再调参数会立刻知道有没有调坏。
    now = time.time()
    EMOT = "别走！我怕……你答应过我的！"
    PLAIN = "嗯，知道了。"

    def median_alive(text, days):
        vs = sorted(S.salience({"content": text, "_node_id": "life-%d" % i,
                                "_ts": now - days * DAY}, now=now)
                    for i in range(200))
        return vs[len(vs) // 2] >= S.KEEP_THRESHOLD

    check("平淡内容：3 天后还记得", median_alive(PLAIN, 3))
    check("平淡内容：20 天后忘了", not median_alive(PLAIN, 20))
    check("带情绪内容：14 天后还记得", median_alive(EMOT, 14))
    check("带情绪内容：30 天后忘了", not median_alive(EMOT, 30))

    print("\n      控制变量：同年龄、只变情绪（年龄与内容混在一起是混淆变量）")
    for days in (3, 6):
        e = S.salience({"content": EMOT, "_node_id": "c1",
                        "_ts": now - days * DAY}, now=now)
        p = S.salience({"content": PLAIN, "_node_id": "c1",
                        "_ts": now - days * DAY}, now=now)
        check("%d 天：带情绪的比平淡的清晰" % days, e > p,
              "%.3f vs %.3f" % (e, p))
    # 交叉点在 14 天附近（实测）。但【不能随便挑一个 node_id 去证】——
    # 衰减率是每个节点隐藏且随机的，'c1' 恰好落在最慢档（0.022），
    # 14 天几乎不忘，于是断言会莫名其妙地失败（第一版就踩了）。
    # 正确的做法是测【比值】：情绪的作用与节点 id 无关，比值应当恒定。
    print("\n      同日不同命：用比值验证（与具体 node_id 无关）")
    for days in (1, 7, 14, 21):
        e = S.salience({"content": EMOT, "_node_id": "c1",
                        "_ts": now - days * DAY}, now=now)
        p = S.salience({"content": PLAIN, "_node_id": "c1",
                        "_ts": now - days * DAY}, now=now)
        ratio = e / p if p else 0.0
        check("%d 天：带情绪的清晰度是平淡的 1.5~2 倍" % days,
              1.4 <= ratio <= 2.1, "%.3f（情绪=%.3f 平淡=%.3f）" % (ratio, e, p))

    # 换个"中位衰减率"的节点，看交叉点确实存在
    mid_id = min(("probe-%d" % i for i in range(500)),
                 key=lambda x: abs(S.hidden_decay(x) - 0.086))
    alive_e = S.salience({"content": EMOT, "_node_id": mid_id,
                          "_ts": now - 14 * DAY}, now=now)
    alive_p = S.salience({"content": PLAIN, "_node_id": mid_id,
                          "_ts": now - 14 * DAY}, now=now)
    print("      中位衰减率的节点 %s（衰减 %.3f）：14 天时 情绪=%.3f 平淡=%.3f"
          % (mid_id, S.hidden_decay(mid_id), alive_e, alive_p))
    check("14 天时：情绪还在阈值上、平淡已过（这是真的交叉点）",
          alive_e >= S.KEEP_THRESHOLD > alive_p,
          "情绪=%.3f 平淡=%.3f" % (alive_e, alive_p))
    print("      衰减率分布 min=%.3f 中位=%.3f max=%.3f，阈值=%.2f"
          % (min(S.hidden_decay("n%d" % i) for i in range(300)),
             sorted(S.hidden_decay("n%d" % i) for i in range(300))[150],
             max(S.hidden_decay("n%d" % i) for i in range(300)),
             S.KEEP_THRESHOLD))


def _iso(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts).isoformat()


if __name__ == "__main__":
    print("=" * 64)
    print("记忆清晰度：有损、有选择、不可反推")
    print("=" * 64)
    test_deterministic_but_unmodelable()
    test_time_units()
    test_emotion_and_length()
    test_mention_boost()
    test_recent_window_kept()
    test_old_but_vivid_beats_new_but_faded()
    test_forgotten_not_summarized()
    test_graceful_degradation()
    test_wired_into_fit_budget()
    test_memory_lifespan()
    print("\n" + "=" * 64)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
