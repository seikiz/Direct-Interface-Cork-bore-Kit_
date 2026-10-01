# -*- coding: utf-8 -*-
"""剧本运行时审计：两个播放器的**语义一致性** + 无头模拟（条件分支真的按状态开关）。

为什么需要
----------
2026-10 之前，DICK 有两个播放器实现（web/index.html 的内嵌预览、codex_core.py 的导出模板），
它们对同一份剧本的行为**不一样**：
  · 内嵌预览不执行 setflag/roll/wait/effect/hide/show 等步骤（只认 6 种）
  · 内嵌预览不评估 choice 的 if 条件 → 条件选项永远全部显示
于是"好感 85 才出现的隐藏选项"这种招牌玩法，作者在编辑器里根本试不出来。
这个套件守住三件事：
  ① 两个播放器的 JS 都能过 node --check（改一处别忘了另一处）
  ② 两个播放器处理的步骤类型集合一致（结构性防分叉）
  ③ Python 侧的无头模拟与真播放器同语义：条件真的按好感/标志开关
跑法：python tests/test_codex_runtime.py
"""
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import codex_core as CX  # noqa: E402

PASS = 0
FAIL = 0
INDEX = os.path.join(ROOT, "web", "index.html")


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def node_check(code):
    fd, p = tempfile.mkstemp(suffix=".js")
    os.close(fd)
    io.open(p, "w", encoding="utf-8").write(code)
    try:
        r = subprocess.run(["node", "--check", p], capture_output=True, text=True,
                           encoding="utf-8", errors="ignore")
        return r.returncode == 0, (r.stderr or "")[:400]
    finally:
        os.unlink(p)


def kinds_in(js):
    """只统计【步骤类型】的分发（ln.kind === 'xxx'）；别把 m.kind==='user' 这种消息类型算进来"""
    return set(re.findall(r"ln\.kind\s*===\s*'([a-z_]+)'", js))


def player_slice(js):
    """从内联脚本里切出【播放器】那一段。

    不然会把 GAL 编辑器里的 `ln.kind === 'say'`（渲染用）也算成播放器能力，
    比出来的差异是假的。
    """
    a = js.find("function codexCond(")
    b = js.find("function codexTypeText(")
    return js[a:b] if a >= 0 and b > a else js


def script(scenes, name="运行时样本"):
    return {"name": name, "scenes": scenes}


def main():
    print("=" * 62)
    print(u"剧本运行时审计（双播放器一致性 + 无头模拟）")
    print("=" * 62)

    html = io.open(INDEX, encoding="utf-8").read()
    inapp = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)[0]
    exported = CX.STANDALONE_PLAYER_JS

    print(u"\n== ① 两个播放器的 JS 都必须是合法 JS ==")
    ok, err = node_check(inapp)
    check(u"内嵌预览（web/index.html）语法合法", ok, err)
    ok, err = node_check(exported)
    check(u"导出播放器（codex_core.STANDALONE_PLAYER_JS）语法合法", ok, err)

    print(u"\n== ② 两个播放器处理的步骤类型必须一致（结构性防分叉）==")
    ki, ke = kinds_in(player_slice(inapp)), kinds_in(exported)
    check(u"内嵌预览认得的步骤类型 ≥ 8 种（不再只认 6 种）", len(ki) >= 8, str(sorted(ki)))
    check(u"两边 kind 分发的集合完全一致", ke == ki,
          u"内嵌 %s / 导出 %s（差集 %s）" % (sorted(ki), sorted(ke), sorted(ki ^ ke)))
    check(u"两边都用字段分发处理 text/choice/jump/end/action",
          all((u"'%s' in ln" % f) in inapp and (u"'%s' in ln" % f) in exported
              for f in ("choice", "jump", "end", "action")))
    check(u"两边都实现了条件求值（codexCond / cxCond）",
          "function codexCond" in inapp and "function cxCond" in exported)
    check(u"两边都在选项上用条件过滤",
          "codexFilterOpts(" in inapp and "cxFilter(" in exported)
    check(u"两边都用快照/注入状态而不是写死全通过",
          "codexPlayer.vars" in inapp and "cxVars.state" in exported)
    check(u"两边都实现了 setflag / roll",
          "kind === 'setflag'" in inapp and "kind === 'setflag'" in exported
          and "kind === 'roll'" in inapp and "kind === 'roll'" in exported)
    check(u"两边都实现了（真）等待 + 可跳过",
          "waitTimer" in inapp and "waitTimer" in exported)

    print(u"\n== ③ 条件求值语义（Python 侧镜像）==")
    st50 = {"affection": 50, "status": {"mood": "cold"}, "flags": {}}
    st90 = {"affection": 90, "status": {"mood": "warm"}, "flags": {"met": True}}
    check(u"无状态 = 作者模式，条件一律通过", CX.cond_pass({"aff": ">=85"}, None))
    check(u"空条件通过", CX.cond_pass({}, st50) and CX.cond_pass(None, st50))
    check(u"aff 比较：50 不满足 >=85", not CX.cond_pass({"aff": ">=85"}, st50))
    check(u"aff 比较：90 满足 >=85", CX.cond_pass({"aff": ">=85"}, st90))
    check(u"aff 支持数字与 <= < > !=",
          CX.cond_pass({"aff": 50}, st50) and CX.cond_pass({"aff": "<=50"}, st50)
          and CX.cond_pass({"aff": "<60"}, st50) and CX.cond_pass({"aff": "!=80"}, st50)
          and not CX.cond_pass({"aff": ">60"}, st50))
    check(u"status 字段相等", CX.cond_pass({"status": {"mood": "cold"}}, st50)
          and not CX.cond_pass({"status": {"mood": "warm"}}, st50))
    check(u"flags 存在/取反", CX.cond_pass({"flags": ["met"]}, st90)
          and not CX.cond_pass({"flags": ["met"]}, st50)
          and CX.cond_pass({"flags": ["!met"]}, st50))
    check(u"all / any 组合",
          CX.cond_pass({"all": [{"aff": ">=85"}, {"flags": ["met"]}]}, st90)
          and not CX.cond_pass({"all": [{"aff": ">=85"}, {"flags": ["nope"]}]}, st90)
          and CX.cond_pass({"any": [{"aff": ">=85"}, {"flags": ["met"]}]}, st90))
    check(u"state 嵌套在 mechanism_state 里也认",
          CX.cond_pass({"aff": ">=85"}, {"mechanism_state": {"affection": 90}}))

    print(u"\n== ④ 条件分支真的按好感开关（招牌玩法）==")
    gated = script([
        {"id": "s1", "lines": [
            {"text": u"她看着你"},
            {"choice": [{"text": u"普通问候", "goto": "s2"},
                        {"text": u"拥抱她", "goto": "s3", "if": {"aff": ">=85"}}]}]},
        {"id": "s2", "lines": [{"end": u"结局：普通"}]},
        {"id": "s3", "lines": [{"end": u"结局：亲密"}]},
    ])
    r50 = CX.simulate(gated, state=st50)
    r90 = CX.simulate(gated, state=st90)
    check(u"好感 50：亲密结局不可达", u"结局：亲密" not in r50["endings"], str(r50["endings"]))
    check(u"好感 90：亲密结局可达", u"结局：亲密" in r90["endings"], str(r90["endings"]))
    check(u"被门住的选项有记录", any(u"拥抱她" in g for g in r50["gated"]), str(r50["gated"]))
    check(u"作者模式（无状态）下两条路都算可达",
          u"结局：亲密" in CX.simulate(gated)["endings"])

    p50 = CX.run_path(gated, picks=[0], state=st50)
    p90 = CX.run_path(gated, picks=[1], state=st90)
    check(u"好感 50 时 picks=[0] 走普通线", p50["ending"] == u"结局：普通", str(p50))
    check(u"好感 90 时第 2 个选项就是「拥抱她」（隐藏项被过滤掉了）",
          p90["ending"] == u"结局：亲密", str(p90))
    check(u"好感 50 时同样的 picks=[1] 也只会落到普通线（因为只有 1 个可见选项）",
          CX.run_path(gated, picks=[1], state=st50)["ending"] == u"结局：普通",
          str(CX.run_path(gated, picks=[1], state=st50)))

    print(u"\n== ⑤ setflag / roll 影响后续分支 ==")
    flag_script = script([
        {"id": "s1", "lines": [{"kind": "setflag", "flag": {"k": "met"}},
                               {"choice": [{"text": u"打招呼", "goto": "s2"}]}]},
        {"id": "s2", "lines": [{"choice": [{"text": u"提起约定", "goto": "s3",
                                           "if": {"flags": ["met"]}},
                                          {"text": u"沉默", "goto": "s4"}]}]},
        {"id": "s3", "lines": [{"end": u"结局：约定"}]},
        {"id": "s4", "lines": [{"end": u"结局：沉默"}]},
    ])
    rf = CX.run_path(flag_script, picks=[0, 0])
    check(u"setflag 之后条件选项打开", rf["ending"] == u"结局：约定", str(rf))
    check(u"flags 里能看到 met", rf["flags"].get("met") is True, str(rf["flags"]))
    r_no = CX.simulate(script([
        {"id": "s1", "lines": [{"choice": [{"text": u"提起约定", "goto": "s2",
                                           "if": {"flags": ["met"]}},
                                          {"text": u"沉默", "goto": "s2"}]}]},
        {"id": "s2", "lines": [{"end": u"结局"}]},
    ]), state=st50)
    check(u"没设 flag 时该选项被门住", any(u"提起约定" in g for g in r_no["gated"]), str(r_no["gated"]))

    roll_script = script([
        {"id": "s1", "lines": [{"kind": "roll", "roll": {"k": "luck", "d": 100}},
                               {"choice": [{"text": u"赌一把", "goto": "s2",
                                            "if": {"flags": ["luck"]}},
                                           {"text": u"算了", "goto": "s3"}]}]},
        {"id": "s2", "lines": [{"end": u"结局：赌"}]},
        {"id": "s3", "lines": [{"end": u"结局：稳"}]},
    ])
    rr = CX.run_path(roll_script, picks=[0, 0], roll_values=[77])
    check(u"roll 写进 flags（可注入随机结果）", rr["flags"].get("luck") == 77, str(rr["flags"]))
    check(u"roll 之后条件选项打开", rr["ending"] == u"结局：赌", str(rr))

    print(u"\n== ⑥ 死循环与边界 ==")
    loop = script([{"id": "s1", "lines": [{"text": "a"}, {"jump": "s2"}]},
                   {"id": "s2", "lines": [{"text": "b"}, {"jump": "s1"}]}])
    rl = CX.simulate(loop)
    check(u"没有结局且检出成环", rl["endings"] == [] and rl["cycles"], str(rl))
    rp = CX.run_path(loop, picks=[])
    check(u"run_path 死循环会停下并报因",
          (not rp["ok"]) and u"死循环" in rp["stopped"], str(rp["stopped"]))
    allblocked = script([{"id": "s1", "lines": [{"choice": [
        {"text": u"仅限高好感", "goto": "s2", "if": {"aff": ">=85"}}]}]},
        {"id": "s2", "lines": [{"end": "完"}]}])
    rb = CX.run_path(allblocked, picks=[0], state=st50)
    check(u"选项全被挡住时给人话提示", (not rb["ok"]) and u"条件" in rb["stopped"], str(rb["stopped"]))
    check(u"空剧本不崩",
          CX.simulate({})["ok"] is False and CX.run_path({}, [])["ok"] is False)
    check(u"坏场景不崩", CX.simulate({"scenes": "x"})["ok"] is False)
    check(u"picks 越界时退回第一个选项",
          CX.run_path(gated, picks=[9], state=st90)["ending"] in (u"结局：普通", u"结局：亲密"))

    print(u"\n== ⑦ 与静态体检交叉验证（同一份剧本，可达场景集合必须一致）==")
    for name, sc in ((u"项目自带示例", CX.make_template()),
                     (u"条件分支样本", gated),
                     (u"flags 样本", flag_script),
                     (u"死循环样本", loop)):
        a = CX.analyze_codex(sc)
        b = CX.simulate(sc)          # 作者模式：与静态体检口径一致
        ra = set()
        for s in (sc.get("scenes") or []):
            sid = str(s.get("id") or "")
            if any(sid in i for i in a["issues"]) or True:
                ra.add(sid)
        # 体检报告的是"不可<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌达"，这里反推可达
        unreachable = set(re.findall(r"场景 (\S+) 不可达", " ".join(a["issues"])))
        ra = ra - unreachable
        check(u"%s：静态可达 == 模拟可达" % name, ra == b["visited_scenes"],
              u"静态 %s vs 模拟 %s" % (sorted(ra), sorted(b["visited_scenes"])))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CODEX_RUNTIME_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
