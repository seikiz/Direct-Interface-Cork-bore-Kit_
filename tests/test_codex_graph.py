# -*- coding: utf-8 -*-
"""剧本体检审计：图论层（不可达/死行/死循环）、双播放器一致性、素材引用、统计。

为什么需要
----------
validate_codex 只做字段级校验（缺 id / goto 指向不存在 / sprites 格式）。
它抓不到"结构坏了但字段都合法"的剧本 —— 而这类问题在编辑器里看不出来：
  · 选项后面写的那几行，播放器永远执行不到（项目自带的示例剧本就踩着这个坑）
  · 用了 setflag/roll 的剧本，内嵌预览不置位，导出后才生效
  · 素材改名后剧本还引用旧名；或素材放了却没引用
这里把体检器的每条判定都钉死。

跑法：python tests/test_codex_graph.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import codex_core as CX  # noqa: E402

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


def has(items, needle):
    return any(needle in str(x) for x in items)


def script(scenes, name="体检样本"):
    return {"name": name, "scenes": scenes}


def main():
    print("=" * 62)
    print(u"剧本体检器审计")
    print("=" * 62)

    print(u"\n== ① 选项之后的死行（最常见的坑）==")
    s = script([
        {"id": "s1", "lines": [{"text": "你好"},
                               {"choice": [{"text": "A", "goto": "s2"}, {"text": "B", "goto": "s3"}]},
                               {"end": u"结局：永远不会走到"}]},
        {"id": "s2", "lines": [{"end": u"结局 A"}]},
        {"id": "s3", "lines": [{"end": u"结局 B"}]},
    ])
    r = CX.analyze_codex(s)
    check(u"报出死行", r["stats"]["dead_lines"] == 1, str(r["stats"]))
    check(u"死行定位到 s1 lines[2]", r["dead_lines"] == [("s1", 2)], str(r["dead_lines"]))
    check(u"死行说明点出成因（跟在选项之后）", has(r["issues"], u"跟在选项之后"), str(r["issues"]))

    print(u"\n== ② 不可达场景 ==")
    s = script([
        {"id": "s1", "lines": [{"end": "完"}]},
        {"id": "s9", "lines": [{"text": u"没人能走到我"}]},
    ])
    r = CX.analyze_codex(s)
    check(u"报出不可达场景", has(r["issues"], u"场景 s9 不可达"), str(r["issues"]))
    check(u"统计里 unreachable=1", r["stats"]["unreachable"] == 1, str(r["stats"]))

    print(u"\n== ③ 死循环（永远走不到结局）==")
    s = script([
        {"id": "s1", "lines": [{"text": "a"}, {"jump": "s2"}]},
        {"id": "s2", "lines": [{"text": "b"}, {"jump": "s1"}]},
    ])
    r = CX.analyze_codex(s)
    check(u"报出没有可达结局", has(r["issues"], u"没有任何可达结局"), str(r["issues"]))
    check(u"成因提示指向成环", has(r["issues"], u"成环"), str(r["issues"]))

    print(u"\n== ④ 场景播完的隐性结局（jump/next 都没有）==")
    s = script([
        {"id": "s1", "lines": [{"text": u"就到这里"}]},
    ])
    r = CX.analyze_codex(s)
    check(u"算作一个结局而不是错误", r["stats"]["endings"] == 1 and not r["issues"], str(r))
    check(u"没有 end 行时也不报错", r["ok"] is True, str(r["issues"]))

    print(u"\n== ⑤ 双播放器一致性：内嵌预览不执行的步骤 ==")
    s = script([
        {"id": "s1", "lines": [{"kind": "setflag", "flag": {"k": "met"}},
                               {"kind": "roll", "roll": {"k": "luck", "d": 100}},
                               {"kind": "wait", "ms": 500},
                               {"choice": [{"text": "继续", "goto": "s2",
                                            "if": {"flag": "met", "eq": True}}]}]},
        {"id": "s2", "lines": [{"end": "完"}]},
    ])
    r = CX.analyze_codex(s)
    check(u"setflag 被标为预览不生效", has(r["warnings"], u"「setflag」"), str(r["warnings"]))
    check(u"roll 被标为预览不生效", has(r["warnings"], u"「roll」"), str(r["warnings"]))
    check(u"wait 被标为预览不生效", has(r["warnings"], u"「wait」"), str(r["warnings"]))
    check(u"这些是 warnings 不是 issues（剧本本身没坏）", r["ok"], str(r["issues"]))
    check(u"警告里给出具体位置", has(r["warnings"], u"s1:lines["), str(r["warnings"]))

    s = script([{"id": "s1", "lines": [{"action": "/speak hi"}, {"end": "完"}]}])
    r = CX.analyze_codex(s)
    check(u"action 提示导出后被跳过", has(r["warnings"], u"action"), str(r["warnings"]))

    print(u"\n== ⑥ 素材：缺失与孤儿 ==")
    tmp = tempfile.mkdtemp(prefix="dick_codex_")
    try:
        for kind, fns in (("bg", ["教室.png"]), ("sprites", ["咲_立绘.png", u"没人用的.png"]),
                          ("bgm", ["主题曲.mp3"]), ("voice", [])):
            d = os.path.join(tmp, kind)
            os.makedirs(d, exist_ok=True)
            for fn in fns:
                io.open(os.path.join(d, fn), "w", encoding="utf-8").write("x")
        s = script([{"id": "s1", "bg": "bg/教室.png", "bgm": "bgm/主题曲.mp3",
                     "lines": [{"speaker": u"咲", "sprite": "sprites/咲_立绘.png",
                                "voice": "voice/01.wav", "text": u"早上好"},
                               {"bg": "bg/走廊.png"},
                               {"end": u"完"}]}])
        r = CX.analyze_codex(s, pkg_dir=tmp)
        check(u"报出缺失素材（voice/01.wav、bg/走廊.png）",
              has(r["issues"], "voice/01.wav") and has(r["issues"], "bg/走廊.png"), str(r["issues"]))
        check(u"报出孤儿素材", has(r["warnings"], u"没人用的.png"), str(r["warnings"]))
        check(u"存在的素材不误报缺失", not has(r["issues"], "bg/教室.png"), str(r["issues"]))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(u"\n== ⑦ 统计数字 ==")
    s = script([
        {"id": "s1", "lines": [{"text": u"一二三四五六七八九十"},   # 10 字
                               {"choice": [{"text": "A", "goto": "s2"}, {"text": "B", "goto": "s2"}]}]},
        {"id": "s2", "lines": [{"text": u"再见"}, {"end": u"结局"}]},
    ])
    r = CX.analyze_codex(s)
    st = r["stats"]
    check(u"场景数 2", st["scenes"] == 2, str(st))
    check(u"行数 4", st["lines"] == 4, str(st))
    check(u"选项数 2 / 分支点 1", st["choices"] == 2 and st["branch_points"] == 1, str(st))
    check(u"字数 12", st["words"] == 12, str(st))
    check(u"有阅读时长估算", st["est_seconds"] > 0 and st["est_minutes"] > 0, str(st))

    print(u"\n== ⑧ 对项目自带示例剧本生效（回归证据）==")
    tpl = CX.make_template()
    r = CX.analyze_codex(tpl)
    check(u"自带示例被查出死行（choice 后的 end 走不到）",
          r["stats"]["dead_lines"] >= 1, str(r["stats"]))
    check(u"自带示例的场景都可达", r["stats"]["unreachable"] == 0, str(r["stats"]))
    check(u"自带示例有可达结局", r["stats"]["endings"] >= 1, str(r["stats"]))
    check(u"自带示例的字段级校验仍然通过", CX.validate_codex(tpl)[0], str(CX.validate_codex(tpl)[1]))

    print(u"\n== ⑨ 坏输入不崩 ==")
    for bad in (None, [], {}, {"scenes": "x"}, {"scenes": [{"id": "s1"}]}):
        try:
            CX.analyze_codex(bad)
            ok = True
        except Exception as e:
            ok = False
            print("     崩溃：%r -> %s" % (bad, e))
        check(u"坏输入不抛异常：%s" % (str(bad)[:20] or "None"), ok)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CODEX_GRAPH_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌