# -*- coding: utf-8 -*-
"""世界记忆（演化）回归测试：抽取 / 归并 / 冲突 / 衰减 / 注入 / 落盘 / 命令

为什么测这些
------------
"世界设定会随时间演化"这件事全是**看不见**的逻辑，只有四个可验证的支点：

  ① **抽取准不准**：把「差点塌了」「桥塌了吗」「如果桥塌了」记成「桥塌了」，
     比不记更糟 —— 错的事实会被当"定局"注入，然后污染后面的每一轮。
  ② **归并会不会收敛**：同一件事换个说法说三遍，必须是一条（seen=3），
     否则注入会被同一件事刷屏。
  ③ **冲突按时间取最新**：桥先塌后修好，档案里**不能**同时躺着"塌了"和"修好了" ——
     那是这套东西的头号要防的错误。
  ④ **衰减门槛与倍率挂钩**：世界时间 = 现实间隔 × 倍率（与 life_core / space_core 同口径）。
     1 倍下 45 天才淡出，720 倍下 91 分钟就淡出 —— 两个倍率各钉一条，免得有人
     把"世界天"算成"现实天"（那等于把倍率这段逻辑删了还不报错）。

另外三条是产品约束：注入必须短（≤max_chars，且关掉就返回空串）、落盘字段人能读回
（`memory/_world/<世界名>.json`）、数据目录必须隔离（**用临时目录**，不许碰真实 memory/）。

跑法：python tests\\test_world_memory.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

sys.stdout.reconfigure(encoding="utf-8")   # 控制台是 GBK 时 ①②③ 这类字符会抛 UnicodeEncodeError

import app_paths                # noqa: E402
import world_memory as WM       # noqa: E402

PASS = 0
FAIL = 0
NOW = datetime(2026, 10, 9, 20, 0, 0)
WORLD = {"name": "现代都市·合租"}
WORLD2 = {"name": "江南水乡·明末"}
WHO = "薇拉"


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def with_tmp(fn):
    """把数据目录指到临时目录跑一段（配置/世界记忆都别落到工程根）"""
    tmp = tempfile.mkdtemp(prefix="dick_worldmem_")
    real = app_paths.get_base_dir
    old = WM._cache
    try:
        app_paths.get_base_dir = lambda: tmp
        WM._cache = None
        return fn(tmp)
    finally:
        app_paths.get_base_dir = real
        WM._cache = old
        shutil.rmtree(tmp, ignore_errors=True)


def facts_of(world=WORLD):
    return WM.load_state(world).get("facts") or []


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_extract():
    print(u"\n== ① 抽取：认得出「世界变了」，也认得出「那只是如果」 ==")
    f = WM.extract_facts(u"", u"城南的桥塌了。", speaker=WHO)
    check(u"地点变化认得出", len(f) == 1 and f[0]["kind"] == "place" and f[0]["subject"] == u"城南的桥",
          str(f))
    check(u"状态保留「了」（不是「桥塌」）", f and f[0]["state"] == u"塌了", str(f))
    f = WM.extract_facts(u"她告诉我城南的桥塌了。", u"", speaker=WHO)
    check(u"转述的主语被切干净（不是「她告诉我城南的桥」）",
          len(f) == 1 and f[0]["subject"] == u"城南的桥", str(f))
    check(u"差点塌了 → 不记", not WM.extract_facts(u"城南的桥差点塌了。", u"", speaker=WHO))
    check(u"没有塌 → 不记", not WM.extract_facts(u"城南的桥没有塌。", u"", speaker=WHO))
    check(u"问句 → 不记", not WM.extract_facts(u"桥塌了吗？", u"", speaker=WHO))
    check(u"假设句 → 不记", not WM.extract_facts(u"如果桥塌了，我们就绕路。", u"", speaker=WHO))
    f = WM.extract_facts(u"", u"云梦宗换了掌门。云梦宗的掌门是陆沉。", speaker=WHO)
    check(u"同一主体的两种说法收敛成一条（最新说法算数）",
          len(f) == 1 and f[0]["kind"] == "org" and f[0]["state"] == u"掌门是陆沉", str(f))
    f = WM.extract_facts(u"", u"云梦宗换了掌门。玉佩碎了。", speaker=WHO)
    check(u"不同主体的两件事都记（一条 org 一条 item）",
          len(f) == 2 and sorted(x["kind"] for x in f) == ["item", "org"], str(f))
    f = WM.extract_facts(u"她在码头和你吵过架。", u"", speaker=WHO)
    check(u"关系认得出，且地点不粘进主体",
          len(f) == 1 and f[0]["kind"] == "relation" and f[0]["subject"] == u"她和你", str(f))
    f = WM.extract_facts(u"", u"玉佩碎了，很难过。", speaker=WHO)
    check(u"物品认得出", len(f) == 1 and f[0]["kind"] == "item" and f[0]["subject"] == u"玉佩", str(f))
    f = WM.extract_facts(u"", u"这里的规矩是夜里不许出城。", speaker=WHO)
    check(u"规则认得出（且自动钉住）", len(f) == 1 and f[0]["kind"] == "rule"
          and f[0]["state"] == u"夜里不许出城", str(f))
    check(u"「你不能这样」不会被记成规则（只认显式名词）",
          not WM.extract_facts(u"", u"你不能这样对我。", speaker=WHO))
    f = WM.extract_facts(u"", u"客栈着火了。都说老码头修好了。", speaker=WHO)
    check(u"一句里两件事都认得出", len(f) == 2, str(f))


def test_merge():
    print("\n== ② 归并：同一件事说三遍，只该有一条 ==")

    def run(tmp):
        WM.note_turn(u"", u"城南的桥塌了。", world=WORLD, speaker=WHO, now=NOW, scale=1)
        WM.note_turn(u"", u"城南的桥塌了，大家都在说。", world=WORLD, speaker=WHO,
                     now=NOW + timedelta(minutes=1), scale=1)
        r = WM.note_turn(u"她告诉我城南的桥塌了。", u"", world=WORLD, speaker=WHO,
                         now=NOW + timedelta(minutes=2), scale=1)
        fs = facts_of()
        check(u"三次提及仍是一条", len(fs) == 1, str(fs))
        check(u"seen 累加到 3", fs and int(fs[0]["seen"]) == 3, str(fs))
        check(u"最新说法覆盖旧说法", fs and fs[0]["text"] == u"城南的桥塌了", str(fs))
        check(u"原始说法留了档（给人核对）", fs and len(fs[0]["sources"]) >= 2, str(fs))
        check(u"这一轮报的是 merged", r.get("merged") == 1, str(r))
        check(u"返回里带上总条数（给日志用）", r.get("total") == 1, str(r))
        check(u"主语归一化：带标点、尾部「的」也认成同一条",
              WM.extract_facts(u"", u"城南的桥，塌了。", speaker=WHO)[0]["subject"] == u"城南的桥")

    with_tmp(run)


def test_conflict():
    print("\n== ③ 冲突：桥先塌后修好，档案里只能有一条（最新的算数） ==")

    def run(tmp):
        WM.note_turn(u"", u"城南的桥塌了。", world=WORLD, speaker=WHO, now=NOW, scale=1)
        r = WM.note_turn(u"", u"听说城南的桥修好了。", world=WORLD, speaker=WHO,
                         now=NOW + timedelta(minutes=5), scale=1)
        fs = facts_of()
        check(u"仍然只有一条（不是两条互相打脸）", len(fs) == 1, str(fs))
        check(u"状态是最新的", fs and fs[0]["state"] == u"修好了", str(fs))
        check(u"旧状态记在 prev_state 里（可回溯，不丢）", fs and fs[0]["prev_state"] == u"塌了", str(fs))
        check(u"这一轮报的是 conflict", r.get("conflict") == 1, str(r))
        check(u"改写后强度更高（新变化更值得提）", fs and float(fs[0]["strength"]) > 1.0, str(fs))
        # 再变回去：最新一次仍然算数，且不会长出第二条
        WM.note_turn(u"", u"城南的桥又塌了。", world=WORLD, speaker=WHO,
                     now=NOW + timedelta(minutes=9), scale=1)
        fs = facts_of()
        check(u"反复变化也不会堆积条目", len(fs) == 1 and fs[0]["state"] == u"塌了", str(fs))

    with_tmp(run)


def test_decay():
    print("\n== ④ 衰减：门槛与倍率挂钩（1 倍 vs 720 倍） ==")

    def mk(scale, minutes, strength=1.0):
        st = WM.empty_state(WORLD)
        st["facts"] = [{"id": "place:城南的桥", "kind": "place", "subject": u"城南的桥",
                        "state": u"塌了", "text": u"城南的桥塌了", "strength": strength,
                        "seen": 1, "first_seen": NOW.isoformat(), "last_seen": NOW.isoformat(),
                        "pinned": False, "sources": []}]
        return WM.current_strength(st["facts"][0], scale=scale, now=NOW + timedelta(minutes=minutes))

    thr = float(WM.DEFAULTS["fade_threshold"])
    s720_5 = mk(720, 5)
    check(u"720 倍：现实 5 分钟 = 那边 2.5 天 → 还远在门槛上（%.3f）" % s720_5, s720_5 >= thr)
    days720_5 = WM.world_days_since(NOW.isoformat(), 720, NOW + timedelta(minutes=5))
    check(u"世界天数换算：720 倍下现实 1 分钟 = 0.5 世界天",
          abs(WM.world_days_since(NOW.isoformat(), 720, NOW + timedelta(minutes=1)) - 0.5) < 1e-9,
          str(WM.world_days_since(NOW.isoformat(), 720, NOW + timedelta(minutes=1))))
    check(u"世界天数换算：1 倍下现实 1 天 = 1 世界天",
          abs(WM.world_days_since(NOW.isoformat(), 1, NOW + timedelta(days=1)) - 1.0) < 1e-9)
    s720_90 = mk(720, 90)
    s720_92 = mk(720, 92)
    check(u"720 倍：现实 90 分钟（那边 45 天）还在门槛上（%.3f）" % s720_90, s720_90 >= thr)
    check(u"720 倍：现实 92 分钟（那边 46 天）已淡出（%.3f）" % s720_92, s720_92 < thr)
    check(u"720 倍下淡出只需现实一个半小时（不是 45 天）", days720_5 < 45.0)
    s1_44 = mk(1, 44 * 24 * 60)
    s1_46 = mk(1, 46 * 24 * 60)
    check(u"1 倍：44 天还在门槛上（%.3f）" % s1_44, s1_44 >= thr)
    check(u"1 倍：46 天已淡出（%.3f）" % s1_46, s1_46 < thr)
    check(u"同一个门槛，两种倍率对应的现实时长差很多（这正是要写清楚的地方）",
          (s1_44 >= thr) and (mk(720, 92) < thr))
    check(u"倍率非法 → 当 1 倍（与空间层同一条规矩）",
          abs(WM.world_days_since(NOW.isoformat(), "abc", NOW + timedelta(days=1)) - 1.0) < 1e-9)
    check(u"脏时间戳 → None", WM.world_days_since("不是时间", 720, NOW) is None)
    check(u"贴边：0/负数/NaN 倍率都当 1",
          all(abs(WM.world_days_since(NOW.isoformat(), v, NOW + timedelta(days=1)) - 1.0) < 1e-9
              for v in (0, -5, float("nan"))))

    def run(tmp):
        WM.note_turn(u"", u"城南的桥塌了。", world=WORLD, speaker=WHO, now=NOW, scale=1)
        later = NOW + timedelta(days=200)
        txt = WM.injection_text([], scale=1, world=WORLD, now=later)
        check(u"淡出后不进注入（但档案还在）", txt == "" and len(facts_of()) == 1, repr(txt))
        # 被剧情重新提起 → 回到满强度附近
        WM.note_turn(u"", u"城南的桥塌了，我们绕路吧。", world=WORLD, speaker=WHO,
                     now=later, scale=1)
        txt2 = WM.injection_text([], scale=1, world=WORLD, now=later)
        check(u"重新提起 → 立刻回到注入里", u"城南的桥" in txt2, repr(txt2))
        # 规则不衰减：200 天后照样在
        WM.note_turn(u"", u"这里的规矩是夜里不许出城。", world=WORLD, speaker=WHO,
                     now=NOW, scale=1)
        txt3 = WM.injection_text([], scale=1, world=WORLD, now=later)
        check(u"规则（钉住）不衰减：200 天后仍在", u"夜里不许出城" in txt3, repr(txt3))

    with_tmp(run)


def test_injection():
    print("\n== ⑤ 注入：短、有上限、关掉就空、按优先级截断 ==")

    def run(tmp):
        WM.note_turn(u"", u"城南的桥塌了。云梦宗换了掌门。玉佩碎了。客栈着火了。"
                          u"她和你在码头吵过架。这里的规矩是夜里不许出城。",
                     world=WORLD, speaker=WHO, now=NOW, scale=1)
        chain = [{"role": "user", "content": u"我们去城南看看那座桥吧",
                  "timestamp": NOW.isoformat()}]
        txt = WM.injection_text(chain, scale=1, world=WORLD, now=NOW, name=WHO,
                                focus=u"我们去城南看看那座桥吧")
        check(u"有内容、带头、带使用说明",
              txt.startswith(u"【世界·演化】") and u"别和它们矛盾" in txt, txt[:60])
        check(u"长度不超过上限（%d）" % WM.DEFAULTS["max_chars"],
              len(txt) <= int(WM.DEFAULTS["max_chars"]), str(len(txt)))
        check(u"同样的输入 → 同样的文本（确定性，不靠字典/集合的顺序）",
              txt == WM.injection_text(chain, scale=1, world=WORLD, now=NOW, name=WHO,
                                       focus=u"我们去城南看看那座桥吧"))
        before = io.open(WM.state_path(WORLD), encoding="utf-8").read()
        WM.injection_text(chain, scale=1, world=WORLD, now=NOW, name=WHO)
        after = io.open(WM.state_path(WORLD), encoding="utf-8").read()
        check(u"注入是只读的（重试/重放不会把强度刷上去、不改盘）", before == after)
        check(u"钉住的规则排最前（硬约束优先，截断时先保它）",
              u"夜里不许出城" in txt.splitlines()[1], txt)
        non_rule = [ln for ln in txt.splitlines()[1:] if not ln.startswith(u"· 规矩")]
        check(u"场景里提到的桥排在其它事实最前（相关度加分）",
              non_rule and u"桥" in non_rule[0], str(non_rule[:3]))
        cfg = WM.load_config()
        cfg["max_chars"] = 120
        txt2 = WM.injection_text(chain, scale=1, world=WORLD, now=NOW, cfg=cfg, name=WHO)
        check(u"上限 120 时也不超（截断按优先级）", len(txt2) <= 120, str(len(txt2)))
        check(u"截断了也还是「定局」开头，不是从尾巴硬截", txt2.startswith(u"【世界·演化】"), txt2[:40])
        cfg["enabled"] = False
        check(u"关掉 → 空串", WM.injection_text(chain, scale=1, world=WORLD, now=NOW, cfg=cfg) == "")
        check(u"没有事实的世界 → 空串",
              WM.injection_text(chain, scale=1, world={"name": u"从没演过的世界"}, now=NOW) == "")
        check(u"空链也能算（不抛）", isinstance(WM.injection_text(None, scale=1, world=WORLD, now=NOW), str))
        check(u"没有事实时 describe 也不炸", u"还没有记下任何事" in WM.describe({"name": u"空世界"}))
        # 优先级：前两条是"必须"，预算再小也保留
        cfg2 = WM.load_config()
        cfg2["max_chars"] = 80
        txt3 = WM.injection_text(chain, scale=1, world=WORLD, now=NOW, cfg=cfg2, name=WHO)
        check(u"极小上限（80）也不超", len(txt3) <= 80, str(len(txt3)))

    with_tmp(run)


def test_persist():
    print("\n== ⑥ 落盘：字段可读回、一个世界一份、原子写 ==")

    def run(tmp):
        WM.note_turn(u"", u"城南的桥塌了。", world=WORLD, speaker=WHO, now=NOW, scale=1)
        WM.note_turn(u"", u"玉佩碎了。", world=WORLD2, speaker=WHO, now=NOW, scale=1)
        p1 = WM.state_path(WORLD)
        p2 = WM.state_path(WORLD2)
        check(u"文件落在 memory/_world/ 下", os.path.dirname(p1).endswith(os.path.join("memory", "_world")), p1)
        check(u"一个世界一份（两个世界互不干扰）",
              os.path.isfile(p1) and os.path.isfile(p2) and os.path.basename(p1) != os.path.basename(p2))
        raw = json.load(io.open(p1, encoding="utf-8"))
        check(u"顶层字段可读：world / updated / facts",
              raw.get("world") == WORLD["name"] and "updated" in raw and isinstance(raw["facts"], list),
              str(list(raw)))
        f = raw["facts"][0]
        for key in ("id", "kind", "subject", "state", "text", "strength", "seen",
                    "first_seen", "last_seen", "prev_state", "pinned", "sources"):
            check(u"字段 %s 在（人手改得动）" % key, key in f, str(list(f)))
        check(u"另一个世界只有自己那条", len(facts_of(WORLD2)) == 1
              and facts_of(WORLD2)[0]["subject"] == u"玉佩", str(facts_of(WORLD2)))
        check(u"落盘不留 .tmp（原子写）",
              not [n for n in os.listdir(os.path.dirname(p1)) if n.endswith(".tmp")],
              str(os.listdir(os.path.dirname(p1))))
        with io.open(p1, "w", encoding="utf-8") as f:
            f.write(u"{坏 json")
        check(u"坏文件不抛：读得回空状态", WM.load_state(WORLD).get("facts") == [])
        # 条数上限：唯一的自动删除路径
        cfg = WM.load_config()
        cfg["max_facts"] = 2
        WM.clear(WORLD)
        for i in range(5):
            WM.note_turn(u"", u"第%d座客栈着火了。" % i, world=WORLD, speaker=WHO,
                         now=NOW + timedelta(minutes=i), scale=1, cfg=cfg)
        check(u"超过 max_facts 会丢最弱的（唯一的自动删除）", len(facts_of()) == 2, str(facts_of()))

    with_tmp(run)


def test_commands_and_hook():
    print("\n== ⑦ 命令面板：看 / 忘 / 钉（钉住的不淡出）/ 清 ==")

    def load_plugin(base_dir):
        app_paths.get_base_dir = lambda: base_dir
        WM._cache = None
        path = os.path.join(ROOT, "plugins", "world_memory_plugin.py")
        spec = importlib.util.spec_from_file_location("world_mem_plugin_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["world_mem_plugin_under_test"] = mod
        spec.loader.exec_module(mod)

        class FakeCore:
            active_roles = [{"name": WHO}]
            world_data = WORLD

            def _time_scale(self):
                return 1
        return mod.WorldMemoryPlugin(FakeCore())

    def run(tmp):
        plug = load_plugin(tmp)
        plug.on_message_received(u"", u"城南的桥塌了。玉佩碎了。")
        check(u"钩子把事实记下来了", len(facts_of()) == 2, str(facts_of()))
        out = plug.on_command("世界记忆", "")
        check(u"/世界记忆 面板有文件路径与条数", u"文件：" in out and u"事实 2 条" in out, out[:80])
        out = plug.on_command("世界记忆", u"忘 桥")
        check(u"/世界记忆 忘 桥 删掉 1 条", u"忘了 1 条" in out and len(facts_of()) == 1, out)
        out = plug.on_command("世界记忆", u"钉 玉佩")
        check(u"/世界记忆 钉 玉佩 命中 1 条", u"钉住了 1 条" in out, out)
        far = NOW + timedelta(days=500)
        check(u"钉住的 500 天后仍在注入里",
              u"玉佩" in WM.injection_text([], scale=1, world=WORLD, now=far), "钉住失效")
        out = plug.on_command("世界记忆", u"松 玉佩")
        check(u"/世界记忆 松 玉佩", u"松开了 1 条" in out, out)
        check(u"松开后 500 天就淡出了",
              WM.injection_text([], scale=1, world=WORLD, now=far) == "")
        out = plug.on_command("世界记忆", u"关")
        check(u"/世界记忆 关", u"已关闭" in out and not WM.enabled(), out)
        plug.on_command("世界记忆", u"开")
        check(u"/世界记忆 开", WM.enabled())
        out = plug.on_command("世界记忆", u"长 999")
        check(u"/世界记忆 长", u"999" in out and int(WM.load_config()["max_chars"]) == 999, out)
        out = plug.on_command("世界记忆", u"清")
        check(u"/世界记忆 清 清的是当前世界", u"已清空" in out and len(facts_of()) == 0, out)
        # 清空的作用域：另一个世界的记忆不能被带下水
        WM.note_turn(u"", u"客栈着火了。", world=WORLD2, speaker=WHO, now=NOW, scale=1)
        WM.note_turn(u"", u"城南的桥塌了。", world=WORLD, speaker=WHO, now=NOW, scale=1)
        plug.on_command("世界记忆", u"清")
        check(u"清只清当前世界（别的世界不受影响）",
              len(facts_of()) == 0 and len(facts_of(WORLD2)) == 1, str(facts_of(WORLD2)))
        check(u"别的命令不抢（返回 None）", plug.on_command("dice", "") is None)
        # 外部模型抽取钩子：接了就用，不接就没有（证明这段不是死代码）
        seen = {}

        def fake_extract(user_input, ai_reply):
            seen["called"] = True
            return [{"kind": "place", "subject": u"西城门", "state": u"被封了"}]
        WM.set_model_extractor(fake_extract)
        plug.on_message_received(u"", u"没什么可抽的。")
        check(u"接了模型抽取钩子就会被调用", seen.get("called") is True)
        check(u"模型抽取的结果走同一条归并路径", any(f["subject"] == u"西城门" for f in facts_of()),
              str(facts_of()))
        WM.set_model_extractor(None)
        check(u"关掉钩子后又只剩规则抽取", not WM.has_model_extractor())

    with_tmp(run)


def test_isolation():
    print("\n== ⑧ 数据隔离：真实 memory/ 不许被碰 ==")
    real_dir = os.path.join(ROOT, "memory", "_world")
    before = sorted(os.listdir(real_dir)) if os.path.isdir(real_dir) else None
    with_tmp(lambda tmp: WM.note_turn(u"", u"城南的桥塌了。", world=WORLD, speaker=WHO,
                                      now=NOW, scale=1))
    after = sorted(os.listdir(real_dir)) if os.path.isdir(real_dir) else None
    check(u"真实 memory/_world/ 没多出文件", before == after,
          u"%s → %s" % (before, after))


def main():
    print("=" * 62)
    print(u"世界记忆（演化）：抽取 / 归并 / 冲突 / 衰减 / 注入 / 落盘")
    print("=" * 62)
    test_extract()
    test_merge()
    test_conflict()
    test_decay()
    test_injection()
    test_persist()
    test_commands_and_hook()
    test_isolation()
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("WORLD_MEMORY_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
