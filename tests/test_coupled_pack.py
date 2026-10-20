# -*- coding: utf-8 -*-
"""耦合块测试（经内核服务调用）。

为什么这样写：边界规则 `module-entry` 不许测试直接 import 块内部文件
（`modules.couple.selector`）——块的唯一入口是 `module.py:register()`，
外部只能通过 `kernel.service("couple")` 用它。这条规则是对的：
如果测试能直接摸内部，那"一个块只有一个入口"就是纸糊的。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import kernel   # noqa: E402

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


def pack():
    return {
        "id": "sakura-test",
        "version": "1.0.0.0",
        "name": u"测试耦合包",
        "main": {"card": "x.json"},
        "world": {"card": "y.json", "entries": []},
        "mechanics": {"affection": {"min": 0, "max": 100}},
        "settings": [
            {"id": "core-1", "tier": "core", "text": u"【核心】樱是安静的少女，说话很轻。"},
            {"id": "sec-room", "tier": "secondary",
             "text": u"【房间】书桌上摆着一盆薄荷。", "tags": [u"房间", u"薄荷"], "weight": 1.0},
            {"id": "sec-food", "tier": "secondary",
             "text": u"【饮食】她不吃香菜，喜欢热的汤。", "tags": [u"吃", u"汤"], "weight": 1.0},
            {"id": "sec-past", "tier": "secondary",
             "text": u"【过去】她小时候在老城住过三年。", "tags": [u"过去"], "weight": 0.8},
        ],
        "rules": {"budget_chars": 45},
    }


def main():
    print("=" * 62)
    print(u"耦合卡：经内核服务验证（卡包校验 / 分次设定 / 模式互斥）")
    print("=" * 62)

    k = kernel.boot(base_dir=ROOT, modules_dir=os.path.join(ROOT, "modules"), echo=False)
    svc = k.service("couple")
    check(u"内核能装出 couple 服务", svc is not None)

    print(u"\n== ① 耦合包必须四件齐全（不可拆） ==")
    try:
        svc.validate(pack())
        check(u"合法包通过", True)
    except Exception as e:                      # noqa: BLE001
        check(u"合法包通过", False, str(e))

    for miss in ("main", "world", "mechanics", "settings"):
        bad = pack()
        bad.pop(miss)
        try:
            svc.validate(bad)
            check(u"缺 %s 必须报错" % miss, False, u"没报错")
        except Exception:                       # noqa: BLE001
            check(u"缺 %s 必须报错" % miss, True)

    bad = pack()
    bad["version"] = "1.0"
    try:
        svc.validate(bad)
        check(u"版号非四段必须报错", False)
    except Exception:                           # noqa: BLE001
        check(u"版号非四段必须报错", True)

    print(u"\n== ② 模式互斥（耦合与单推/群聊不兼容） ==")
    r = svc.can_enable("coupled", [])
    check(u"空状态下可开耦合", r["ok"], str(r))
    r = svc.can_enable("coupled", ["single"])
    check(u"单推开着 → 开耦合被拒", (not r["ok"]) and (u"不兼容" in r["reason"]), str(r))
    r = svc.can_enable("coupled", ["group"])
    check(u"群聊开着 → 开耦合被拒", not r["ok"], str(r))
    r = svc.switch_to("coupled", ["single", "group"])
    check(u"强制切到耦合 → 只剩 coupled", r["modes"] == ["coupled"], str(r))
    r = svc.switch_to("single", ["coupled"])
    check(u"反向切到单推 → 只剩 single", r["modes"] == ["single"], str(r))
    r = svc.can_enable("single", [])
    check(u"单推与群聊不互斥", r["ok"], str(r))

    print(u"\n== ③ 分次设定 ==")
    a = svc.build(pack(), turn=0, recent_text="", budget_chars=45)
    check(u"核心常驻", "core-1" in a["picked"], str(a["picked"]))
    check(u"不超预算", a["chars"] <= a["budget"], u"%d/%d" % (a["chars"], a["budget"]))
    check(u"至少一条次要", len(a["picked"]) >= 2, str(a["picked"]))

    b = svc.build(pack(), turn=1, recent_text=u"今天想喝点热的汤", budget_chars=45)
    check(u"话题提到汤 → 饮食优先", "sec-food" in b["picked"], str(b["picked"]))

    c = svc.build(pack(), turn=2, recent_text=u"今天想喝点热的汤",
                  used_recently={"sec-food"}, budget_chars=45)
    check(u"刚用过 → 让位（不再选中）", "sec-food" not in c["picked"], str(c["picked"]))

    d = svc.build(pack(), turn=0, recent_text="", budget_chars=5)
    check(u"预算极小 → 只剩核心", d["picked"] == ["core-1"], str(d["picked"]))

    e1 = svc.build(pack(), turn=3, recent_text=u"房间里有薄荷", budget_chars=45)
    e2 = svc.build(pack(), turn=3, recent_text=u"房间里有薄荷", budget_chars=45)
    check(u"同输入 → 同输出", e1["picked"] == e2["picked"], str(e1["picked"]))
    check(u"话题提到薄荷 → 房间优先", "sec-room" in e1["picked"], str(e1["picked"]))

    p2 = pack()
    p2.pop("rules", None)
    f = svc.build(p2, turn=0, recent_text="")
    check(u"没有 rules → 预算默认 1200", f["budget"] == 1200, str(f["budget"]))
    check(u"预算够 → 全部条目都注入", len(f["picked"]) == 4, str(f["picked"]))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("COUPLED_PACK_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌