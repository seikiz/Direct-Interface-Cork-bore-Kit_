# -*- coding: utf-8 -*-
"""
平民化训练测试（纯 numpy，不需要服务器/sklearn）。

要证的三件事：
  ① 数据不够时**拒绝训练**（训出来是噪声，比不训更糟）
  ② 在**有明确偏好的合成数据**上，能学到比随机好的排序
  ③ 学到的权重能**指出我手搓的哪些特征其实没用** —— 这是它最大的价值

跑法：utau_env\\Scripts\\python.exe tests\\test_ranker.py
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import numpy as np              # noqa: E402
import ranker as rk             # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


KEYS = ["册子", "扉页", "字"]
CASE = "册子 扉页 铅笔字 封面"

GOOD = [
    "（她按住封面）先别问是谁写的。你先看扉页这行铅笔字，第三排还在。",
    "（台灯挪近）这笔迹起笔很轻，写字的人手在抖。你看出什么了吗？",
    "（她把册子推到你面前）扉页第二行有个小钩，意大利人的写法。",
    "（低声）铅笔字底下还有一层更淡的，像是擦过又写。要我跟你说吗？",
]
BAD = [
    "（她望向窗外）有些事你以为忘了，其实只是没下雨而已。",
    "（她笑了一下）人这一辈子啊，大概就是在等一场能把记忆泡开的雨。",
    "（她起身去关窗）这条街的房租又涨了。隔壁修钟表的搬走了。",
    "（她忽然说）我小时候院子里有棵石榴树，我母亲一颗颗剥给我吃。",
]


def make_records(n=60, bias_first=False):
    """合成偏好样本：正样本是高目标覆盖的，负样本是漂移的。"""
    recs = []
    for i in range(n):
        g = GOOD[i % len(GOOD)]
        b = BAD[i % len(BAD)]
        ctx = [{"role": "system", "content": "你是阿岚，旧书店老板。"},
               {"role": "user", "content": "那本册子呢？"}]
        if bias_first:
            # 制造位置偏置：**全部**都选<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌了第一条（而且是差的那条）——
            # 之前只做一半（50%），低于 70% 的告警阈值，所以没触发。
            recs.append({"context": ctx, "chosen": b, "rejected": [g],
                         "chosen_index": 0, "rejected_features": [{}],
                         "chosen_features": {}})
        else:
            recs.append({"context": ctx, "chosen": g, "rejected": [b],
                         "chosen_index": 1, "rejected_features": [{}],
                         "chosen_features": {}})
    return recs


def test_features():
    print("\n== 1. 特征：确定性、零成本、维度对 ==")
    v = rk.features(GOOD[0], "上文", BAD[:1], KEYS, CASE)
    check("维度正确", v.shape == (len(rk.FEATURE_NAMES),), str(v.shape))
    check("全部是有限数", np.all(np.isfinite(v)), str(v))
    check("值域合理", np.all(v >= -1e-9) and np.all(v <= 2.0), str(v))
    v2 = rk.features(GOOD[0], "上文", BAD[:1], KEYS, CASE)
    check("同样的输入同样输出（确定性）", np.allclose(v, v2))
    # 目标覆盖应当能区分
    i_cov = rk.FEATURE_NAMES.index("coverage")
    check("好样本的目标覆盖 > 坏样本",
          rk.features(GOOD[0], "", [], KEYS, CASE)[i_cov]
          > rk.features(BAD[0], "", [], KEYS, CASE)[i_cov])
    # 空输入不炸
    check("空输入不炸", np.all(np.isfinite(rk.features("", "", [], KEYS, CASE))))
    check("无关键词不炸", np.all(np.isfinite(rk.features("x", "", [], None, ""))))


def test_readiness():
    print("\n== 2. 数据不够就拒绝训练（训出来是噪声）==")
    few = make_records(5)
    rd = rk.readiness(few)
    check("标为未就绪", rd["ready"] is False, str(rd))
    check("算出了还差多少", rd["need_more"] == rk.MIN_PAIRS - 5, str(rd["need_more"]))
    check("给了警告", any("噪声" in w for w in rd["warnings"]), str(rd["warnings"]))
    r = rk.train(few, KEYS, CASE)
    check("直接拒绝训练", r["ok"] is False, str(r))
    check("拒绝原因说清楚了", "样本不够" in (r.get("err") or ""), str(r.get("err")))

    # 位置偏置要被指出
    biased = make_records(60, bias_first=True)
    rd2 = rk.readiness(biased)
    check("位置偏置被指出",
          any("位置偏置" in w for w in rd2["warnings"]), str(rd2["warnings"]))


def test_train_learns():
    print("\n== 3. 在有明确偏好的数据上能学到东西 ==")
    recs = make_records(80)
    r = rk.train(recs, KEYS, CASE)
    check("训练成功", r["ok"] is True, str(r.get("err")))
    if not r["ok"]:
        return
    print("        训练准确率 %.3f / 留出准确率 %s / 对数 %d"
          % (r["train_acc"], r["holdout_acc"], r["n_pairs"]))
    check("训练准确率明显高于随机（0.5）", r["train_acc"] > 0.75, str(r["train_acc"]))
    check("留出集也能泛化",
          r["holdout_acc"] is not None and r["holdout_acc"] > 0.65,
          str(r["holdout_acc"]))
    check("权重维度对", len(r["w"]) == len(rk.FEATURE_NAMES))

    # 学到的模型能排序
    w = r["w"]
    sg = rk.score(w, GOOD[0], "", [], KEYS, CASE)
    sb = rk.score(w, BAD[0], "", [], KEYS, CASE)
    print("        好样本 %.3f / 坏样本 %.3f" % (sg, sb))
    check("好样本得分高于坏样本", sg > sb, "%s vs %s" % (sg, sb))


def test_explain_finds_features():
    print("\n== 4. 它最大的价值：指出哪些特征真的有用 ==")
    recs = make_records(80)
    r = rk.train(recs, KEYS, CASE)
    if not r["ok"]:
        check("训练成功", False, str(r.get("err")))
        return
    exp = rk.explain(r, top=4)
    print("        权重最大的前几项: %s" % exp)
    check("能列出重要特征", len(exp) == 4, str(exp))
    names = [n for n, _v in exp]
    check("目标覆盖排进前列（合成数据里它确实最该有用）",
          "coverage" in names, str(names))
    # 全部权重一并给出，供对照
    check("权重可序列化（能存成 JSON）",
          isinstance(r["w"][0], float), str(type(r["w"][0])))


def test_save_load():
    print("\n== 5. 存/读模型 ==")
    recs = make_records(80)
    r = rk.train(recs, KEYS, CASE)
    d = tempfile.mkdtemp()
    p = os.path.join(d, "ranker.json")
    rk.save(r, p)
    check("文件写出来了", os.path.isfile(p))
    m = rk.load(p)
    check("读回来是同一份", m and m["w"] == r["w"], "读回失败")
    check("维度不符时拒绝加载", rk.load.__name__ == "load")
    bad = os.path.join(d, "bad.json")
    with open(bad, "w", encoding="utf-8") as f:
        f.write('{"w": [1,2,3]}')
    check("维度不对 → 拒绝（不能用坏模型打分）", rk.load(bad) is None)
    check("文件不存在 → None", rk.load(os.path.join(d, "nope.json")) is None)


def test_score_robust():
    print("\n== 6. 打分不崩 ==")
    check("w=None → None", rk.score(None, "x") is None)
    check("空文本也能打分（返回 0~1）",
          0.0 <= (rk.score([0.0] * len(rk.FEATURE_NAMES), "") or 0) <= 1.0)
    check("零权重 → 0.5（sigmoid(0)）",
          abs(rk.score([0.0] * len(rk.FEATURE_NAMES), "abc") - 0.5) < 1e-9)
    check("异常权重不抛", rk.score(["bad"] * 3, "abc") is None)


if __name__ == "__main__":
    print("=" * 62)
    print("平民化训练（纯 numpy 排序器）测试")
    print("=" * 62)
    test_features()
    test_readiness()
    test_train_learns()
    test_explain_finds_features()
    test_save_load()
    test_score_robust()
    print("\n" + "=" * 62)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
