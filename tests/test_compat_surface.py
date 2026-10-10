# -*- coding: utf-8 -*-
"""兼容性审计（兼容线 1.0.x.x）—— 把"升级时哪些东西会炸 / 会静默丢"实测钉住。

判断依据（用户定稿的版号口径）
------------------------------
版号四段 `主.次.补.实验`，**前两位相同 = 同一条兼容线**。同一条线内：

  · 老数据目录必须能被新版读起来；
  · 新增字段只能是"缺了也能跑"的可选项；
  · **写回时不许把不认识的键抹掉** —— 那等于"用户回退一次就丢档"，属于破坏性变更，
    要等换线（1.1 / 2.0）才允许。

这个脚本按类别造"老格式"的最小样本（手写 JSON），丢进**临时数据目录**，
让真代码去读一次，把实际行为记成断言。绝不碰真实的 saves/ memory/ worlds/ space/。

跑法：python tests\\test_compat_surface.py
"""
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

import app_paths          # noqa: E402
import card_compat as CC  # noqa: E402
import image_gen as IG    # noqa: E402
import life_core as L     # noqa: E402
import ranker as RK       # noqa: E402
import save_guard as SG   # noqa: E402
import space_core as S    # noqa: E402
import time_scale as TS   # noqa: E402
import world_memory as W  # noqa: E402

PASS = 0
FAIL = 0
FINDINGS = []          # (类别, 有无版本标记, 结论)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def finding(kind, marker, verdict):
    FINDINGS.append((kind, marker, verdict))


def with_tmp(fn):
    """把数据目录指到临时目录跑一段；顺手清掉各模块的配置缓存（不然串味）。"""
    tmp = tempfile.mkdtemp(prefix="dick_compat_")
    real = app_paths.get_base_dir
    caches = (L._cache, S._Cfg._cache, W._cache, TS._cache)
    try:
        app_paths.get_base_dir = lambda: tmp
        L._cache = S._Cfg._cache = W._cache = TS._cache = None
        return fn(tmp)
    finally:
        app_paths.get_base_dir = real
        L._cache, S._Cfg._cache, W._cache, TS._cache = caches
        shutil.rmtree(tmp, ignore_errors=True)


def wj(path, obj):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def wtext(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def rj(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  ① 三层配置 + 时间流速：唯一真相是各自的 json，靠 DEFAULTS 合并兜底
# ============================================================
def t_configs():
    print(u"\n-- ① 配置类（life_config / space_config / world_memory_config / time_scale.json） --")

    def body(tmp):
        # 缺文件 → 全是默认值，不抛
        check(u"缺 life_config.json → 默认值", L.load_config() == dict(L.DEFAULTS))
        check(u"缺 space_config.json → 默认值", S.load_config() == dict(S.DEFAULTS))
        check(u"缺 world_memory_config.json → 默认值", W.load_config() == dict(W.DEFAULTS))
        check(u"缺 time_scale.json → 默认倍率", TS.load() == TS.DEFAULT_SCALE)

        # 缺字段（老文件少新键）→ 新键拿默认值
        wj(L.config_path(), {"enabled": False})
        wj(S.config_path(), {"max_chars": 300})
        wj(W.config_path(), {"enabled": False})
        L._cache = S._Cfg._cache = W._cache = None
        check(u"life 缺字段：给的用给的、没给的用默认",
              L.load_config()["enabled"] is False and L.load_config()["era"] == L.DEFAULTS["era"],
              str(L.load_config()))
        check(u"space 缺字段：同上",
              S.load_config()["max_chars"] == 300 and S.load_config()["state_dir"] == S.DEFAULTS["state_dir"])
        check(u"world_memory 缺字段：同上",
              W.load_config()["enabled"] is False and "max_facts" in W.load_config())

        # 多字段（更新的版本写的键）→ 写回时必须留着（本轮修的）
        wj(L.config_path(), {"enabled": True, "future_key": {"x": 1}})
        L._cache = None
        L.save_config(L.load_config())
        check(u"life 写回保留未知键（老程序读新文件不丢）", rj(L.config_path()).get("future_key") == {"x": 1},
              str(rj(L.config_path())))

        wj(S.config_path(), {"enabled": True, "future_key": 7})
        S._Cfg._cache = None
        S.save_config(S.load_config())
        check(u"space 写回保留未知键", rj(S.config_path()).get("future_key") == 7)

        wj(W.config_path(), {"enabled": True, "future_key": [1, 2]})
        W._cache = None
        W.save_config(W.load_config())
        check(u"world_memory 写回保留未知键", rj(W.config_path()).get("future_key") == [1, 2])

        # 类型变了 → 兜底策略各不相同（照实记录）
        wj(TS.config_path(), {"scale": "abc"})
        TS._cache = None
        check(u"time_scale 类型错 → clamp 回默认（不炸）", TS.load() == TS.DEFAULT_SCALE)
        wj(TS.config_path(), {"scale": "720"})
        TS._cache = None
        check(u"time_scale 数字字符串 → 认（宽容）", TS.load() == 720.0)

        wj(L.config_path(), {"max_chars": "abc"})
        L._cache = None
        ok = True
        try:
            prof = L.profile_for(None, L.load_config(), None)
            prof["max_chars"]
        except Exception:
            ok = False
        check(u"life 类型错：load_config 本身不抛（值原样带出来）", L.load_config()["max_chars"] == "abc")
        finding(u"life/space/world_memory 配置", u"无版本标记",
                u"靠 DEFAULTS 合并：缺文件/缺字段→默认；多字段→已改成写回保留；"
                u"类型错不校验（life 的 max_chars 非数字会在 profile_for 里抛，"
                u"但注入外层有 try → 该轮注入为空并打日志：降级不炸）")

    with_tmp(body)


# ============================================================
#  ② 空间状态 space/<角色>.json
# ============================================================
def t_space_state():
    print(u"\n-- ② 空间状态（space/<角色>.json） --")

    def body(tmp):
        check(u"缺文件 → 空状态（不炸）", S.load_state("薇拉") == {})
        mp = S.map_for(None, None, S.load_config())
        st, _v = S.note_move("薇拉", u"便利店", "走路", scale=1.0, mp=mp)
        check(u"首次记位置：从家出发", st.get("place") == u"便利店" and st.get("prev") == u"家", str(st))

        path = S.state_path("薇拉")
        st2 = rj(path)
        st2["future_key"] = {"a": 1}
        wj(path, st2)
        S.note_move("薇拉", u"超市", "走路", scale=1.0, mp=mp)
        check(u"记一次新位置后，未知键还在（写回不丢）",
              rj(path).get("future_key") == {"a": 1}, str(rj(path)))

        wj(path, {"place": u"家", "since": u"不是时间"})
        st3 = S.load_state("薇拉")
        check(u"since 非法 → 读回来不抛", st3.get("since") == u"不是时间")
        st4, v = S.note_move("薇拉", u"学校", "走路", scale=1.0, mp=mp)
        check(u"since 非法 → 当'不知道上次什么时候到的'（按能到处理，不穿帮）",
              v["ok"] is True and (u"不知道上次" in v["why"]), str(v))

        wtext(path, u"{坏 json")
        check(u"状态文件坏掉 → 返回空状态（不炸）", S.load_state("薇拉") == {})
        finding(u"space/<角色>.json", u"无版本标记",
                u"缺文件→空状态并按'家'算；字段缺失/非法→按能到处理；写回保留未知键")

    with_tmp(body)


# ============================================================
#  ③ 世界记忆 memory/_world/<世界名>.json
# ============================================================
def t_world_memory_state():
    print(u"\n-- ③ 世界记忆（memory/_world/<世界名>.json） --")

    def body(tmp):
        st = W.load_state(u"现代都市")
        check(u"缺文件 → 空状态且带 world 键",
              isinstance(st, dict) and st.get("facts") == [] and bool(st.get("world")))
        check(u"空状态不炸（能直接进注入流程）", W.injection_text(None, None, u"现代都市", None, []) == "")

        # 攒一条事实（真实抽取路径），再补一个未来键
        st = W.load_state(u"现代都市")
        st["facts"] = [{"id": "p:城南的桥", "kind": "place", "subject": u"城南的桥",
                        "state": u"塌了", "text": u"城南的桥塌了", "strength": 2.0,
                        "seen": 1, "pinned": False}]
        st["future_key"] = "keep-me"
        W.save_state(u"现代都市", st)
        back = W.load_state(u"现代都市")
        check(u"写回保留未知键", back.get("future_key") == "keep-me", str(back))
        check(u"事实字段读得回来", back["facts"][0]["subject"] == u"城南的桥")

        wj(W.state_path(u"现代都市"), {"facts": "不是列表", "world": u"现代都市"})
        st2 = W.load_state(u"现代都市")
        check(u"facts 类型错 → 归正成空列表（不炸）", st2["facts"] == [])

        wtext(W.state_path(u"现代都市"), u"{坏")
        check(u"文件坏掉 → 空状态（不炸）", W.load_state(u"现代都市")["facts"] == [])
        finding(u"memory/_world/<世界名>.json", u"无版本标记（有 world 名做索引键）",
                u"缺文件/坏文件→空状态；facts 非列表→归正；写回保留未知键（整 dict 落盘）")

    with_tmp(body)


# ============================================================
#  ④ 角色卡 / 存档树 saves/<角色>.json
# ============================================================
def t_saves():
    print(u"\n-- ④ 角色卡 + 存档树（saves/<角色>.json，含 _tree_ts 跨设备时间戳） --")

    def body(tmp):
        saves = os.path.join(tmp, "saves")
        p = os.path.join(saves, u"阿绫.json")
        good = {
            "name": u"阿绫", "system_prompt": u"你是谁", "kind": "dick_card",
            "unlocked": True, "first_mes": u"你好",
            "history_tree": {"nodes": {"n1": {"id": "n1", "role": "user", "content": u"在吗",
                                              "parent_id": None, "children_ids": []}},
                             "root_id": "n1", "current_leaf_id": "n1"},
            "_tree_ts": "2026-10-10T00:00:00+00:00",
            "treeTs": "2026-10-10T00:00:00Z",       # 安卓端写的时间戳键
            "future_key": {"x": 1},                  # 更新的版本写的键
        }

        # 多字段 + 结构坏（节点缺 children_ids）→ 修复写回后未知键必须都在
        broken = json.loads(json.dumps(good))
        broken["history_tree"]["nodes"]["n1"].pop("children_ids")
        wj(p, broken)
        data = SG.guard_loaded(p, kind="role")
        check(u"结构坏了 → 守护能读出来并修好", isinstance(data, dict) and
              isinstance(data["history_tree"]["nodes"]["n1"].get("children_ids"), list))
        on_disk = rj(p)
        check(u"修复写回后 future_key 还在（不丢新字段）", on_disk.get("future_key") == {"x": 1})
        check(u"修复写回后 _tree_ts 还在（桌面端时间戳）",
              on_disk.get("_tree_ts") == "2026-10-10T00:00:00+00:00")
        check(u"修复写回后 treeTs 还在（**安卓端时间戳键**）",
              on_disk.get("treeTs") == "2026-10-10T00:00:00Z",
              u"丢了这个键，跨端同步就会以为对方没有进度")

        # 缺 system_prompt（老卡/裸 v2 卡）→ 守护补空串；但 GUI 的收录条件是"有 system_prompt"
        wj(p, {"name": u"乙", "history_tree": good["history_tree"]})
        data2 = SG.guard_loaded(p, kind="role")
        check(u"缺 system_prompt → 补空串（不炸）", data2.get("system_prompt") == "")
        check(u"缺 name → 补默认名", bool(SG.repair_save_data({})[0]["name"]))

        # 坏 JSON + 有备份 → 从备份恢复
        wj(p, good)
        SG.backup_file(p, throttle=0)
        wtext(p, u"{这不是 json")
        rec = SG.guard_loaded(p, kind="role")
        check(u"坏 JSON + 有备份 → 从备份恢复（不丢档）", isinstance(rec, dict) and rec.get("name") == u"阿绫")

        # 坏 JSON 且无备份 → None（调用方跳过，不炸）
        p2 = os.path.join(saves, u"丙.json")
        wtext(p2, u"{")
        check(u"坏 JSON 且无备份 → 返回 None（调用方跳过）", SG.guard_loaded(p2, kind="role") is None)

        # 旧格式（只有 v1 字段、没有 system_prompt 的裸卡）→ 主程序的转换能拼出提示词
        v1 = {"name": u"丙", "description": u"描述", "personality": u"性格", "scenario": u"场景"}
        try:
            import html_app  # 兼容垫片：它就是加载入口脚本的那个模块
            conv = html_app.role_prompt_from_card(u"丙", v1)
            check(u"老 v1 卡（只有 description/personality）→ 拼得出 system_prompt",
                  isinstance(conv, tuple) and bool(conv[0]), str(conv)[:80])
            conv2 = html_app.role_prompt_from_card(u"丁", {"system_prompt": u"整段设定" * 3})
            check(u"一个结构化字段都没有的卡 → 原样用 system_prompt（不套样板）",
                  u"整段设定" in conv2[0])
        except Exception as e:
            check(u"老卡转换探测没抛异常", False, u"%s: %s" % (type(e).__name__, e))
        # 卡里的世界书条目（老 v2 卡的 extensions.world）→ 提取成 DICK 世界书
        v2 = {"data": {"extensions": {"world": {"entries": [
            {"keys": [u"码头"], "content": u"码头在城北", "insertion_order": 10}]}}}}
        entries = CC.extract_world(v2)
        check(u"老 v2 卡的 extensions.world → 提得出条目", len(entries) == 1 and entries[0]["content"] == u"码头在城北",
              str(entries))
        finding(u"saves/<角色>.json", u"无版本标记（有 kind= dick_card / history_tree 结构特征）",
                u"缺字段→守护补默认；结构坏→修复写回；坏 JSON→从 saves/backup 恢复；"
                u"**未知顶层键（含安卓的 treeTs）写回时保留**；纯 v2 裸卡缺 system_prompt 时"
                u"守护会补空串，但 GUI 收录条件是'有 system_prompt'，手抄进 saves/ 的裸卡不会出现在列表里")

    with_tmp(body)


# ============================================================
#  ⑤ 世界卡 worlds/<名字>.json（含 params.space「字符串里套 JSON」的老写法）
# ============================================================
def t_worlds():
    print(u"\n-- ⑤ 世界卡（worlds/<名字>.json，params.space 两种写法） --")

    def body(tmp):
        cfg = S.load_config()
        space_obj = {"places": [{"name": u"宿舍", "minutes": 0},
                                {"name": u"食堂", "minutes": 8}],
                     "home": u"宿舍", "rooms": [u"卧室"], "transport": {"走路": 1.0}}
        w_str = {"name": u"老写法", "params": {"space": json.dumps(space_obj, ensure_ascii=False)}}
        w_obj = {"name": u"新写法", "params": {"space": space_obj}}
        mp_str = S.map_for(None, w_str, cfg)
        mp_obj = S.map_for(None, w_obj, cfg)
        check(u"params.space 是 JSON 字符串 → 认（老写法）", u"食堂" in mp_str["places"], str(list(mp_str["places"])))
        check(u"params.space 是对象 → 认（新写法）", u"食堂" in mp_obj["places"])
        check(u"两种写法结果一致", sorted(mp_str["places"]) == sorted(mp_obj["places"]))

        p_world = os.path.join(tmp, "worlds", u"甲.json")
        wj(p_world, {"description": u"没有 name", "future_key": {"y": 2}})
        w = SG.guard_loaded(p_world, kind="world")
        check(u"缺 name 的世界卡 → 守护补上（不炸）", isinstance(w, dict) and bool(w.get("name")), str(w))
        check(u"世界卡的未知键写回后保留", rj(p_world).get("future_key") == {"y": 2}, str(rj(p_world)))
        finding(u"worlds/<名字>.json", u"无版本标记（kind/entries/params 结构特征）",
                u"params.space 字符串/对象两种写法都认（老卡不用改）；缺 name→守护补；"
                u"未知键保留；坏 JSON→从 worlds/backup 恢复")

    with_tmp(body)


# ============================================================
#  ⑥ 插件设置 plugin_settings/<插件>.json + config.json 的插件开关
# ============================================================
def t_plugin_settings():
    print(u"\n-- ⑥ 插件设置（plugin_settings/*.json）+ config.json 里的 plugin_states --")

    def body(tmp):
        # 用真实插件类（Galgame 选项有 settings_schema），只喂一个 core=None
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "galgame_choices_plugin", os.path.join(ROOT, "plugins", "galgame_choices_plugin.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plug = mod.GalgameChoicesPlugin(None)
            check(u"插件实例能建（设置文件按插件名）", plug._settings_file is not None)
            check(u"缺设置文件 → 全默认（不炸）", plug.get_setting("count") == 3, str(plug.settings))

            path = plug._settings_file
            wj(path, {"count": 4, "future_key": "keep"})
            plug._load_settings()
            check(u"老设置文件缺新键 → 拿 schema 默认值",
                  plug.get_setting("count") == 4 and plug.get_setting("use_say") is True,
                  str(plug.settings))
            plug._save_settings()
            check(u"写回保留未知键", rj(path).get("future_key") == "keep", str(rj(path)))
        except Exception as e:
            check(u"插件设置探测没抛异常", False, u"%s: %s" % (type(e).__name__, e))

        # config.json：PluginManager._save_states 只改 plugin_states，别的键要留着
        try:
            import plugin_manager as PM
            cfg_path = os.path.join(tmp, "config.json")
            wj(cfg_path, {"api_keys": {"deepseek": "x"}, "future_key": 1, "plugin_states": {"旧插件": True}})
            pm = PM.PluginManager(None, config_file=cfg_path)
            pm._save_states()
            after = rj(cfg_path)
            check(u"config.json 的其它键不被抹（api_keys 还在）", after.get("api_keys") == {"deepseek": "x"})
            check(u"config.json 的未知键也留着", after.get("future_key") == 1)
            check(u"plugin_states 被重写（插件没了就落成空表）", "plugin_states" in after)
        except Exception as e:
            check(u"config.json 探测没抛异常", False, u"%s: %s" % (type(e).__name__, e))
        finding(u"plugin_settings/*.json + config.json", u"无版本标记",
                u"插件设置按 schema 补默认值、未知键保留；config.json 是整 dict 读改写，"
                u"plugin_states 之外不碰（本轮实测）")

    with_tmp(body)


# ============================================================
#  ⑦ 生图预设 image_presets.json（老简写 vs 新对象）
# ============================================================
def t_image_presets():
    print(u"\n-- ⑦ 生图预设（image_presets.json） --")

    def body(tmp):
        p = IG.presets_path(tmp)
        wj(p, {"guofeng": "chinese ink line art, ", "full": {"label": u"全写", "prompt": "x, ", "desc": u"d"}})
        got = IG.load_presets(tmp)
        check(u"老简写（值就是字符串）→ 认", got.get("guofeng", {}).get("prompt") == "chinese ink line art, ")
        check(u"对象写法 → 认", got.get("full", {}).get("label") == u"全写")

        wj(p, {"k": {"prompt": "p, ", "future_field": 1}, "_note": u"手写注释"})
        IG.save_presets(tmp, IG.load_presets(tmp))
        after = rj(p)
        # 兼容线内"老程序读新文件"允许发生（回退一次）：写回必须保留不认识的键，
        # 否则回退一次就永久丢配置 —— 与三层配置、世界记忆同一类问题（已修）。
        check(u"预设对象里的未知键写回后仍在", after.get("k", {}).get("future_field") == 1,
              str(after))
        check(u"下划线注释键也留着（不被当预设、也不被丢）", after.get("_note") == u"手写注释",
              str(after))
        finding(u"image_presets.json", u"无版本标记",
                u"老简写/新对象都认；写回保留未知键与下划线注释键（已修）。"
                u"没有版本标记，但 1.0.x.x 内靠默认值合并足够")

    with_tmp(body)


# ============================================================
#  ⑧ ranker 模型（有 version 字段，但以前不看）
# ============================================================
def t_ranker():
    print(u"\n-- ⑧ 排序器模型（ranker 的 save/load） --")

    def body(tmp):
        path = os.path.join(tmp, "ranker_model.json")
        model = {"version": RK.MODEL_VERSION, "features": list(RK.FEATURE_NAMES),
                 "w": [0.1] * len(RK.FEATURE_NAMES), "bias": 0.0, "meta": {}}
        RK.save(model, path)
        check(u"当前版本模型 → 读得回来", RK.load(path) is not None)

        old = json.loads(json.dumps(model))
        old.pop("version")                      # 更老的模型（没写 version）
        RK.save(old, path)
        check(u"缺 version 的老模型 → 仍然收下（兼容线内认老数据）", RK.load(path) is not None)

        future = json.loads(json.dumps(model))
        future["version"] = RK.MODEL_VERSION + 1
        RK.save(future, path)
        check(u"显式写了更高的 version → 拒收（宁可不排序，也别用错模型）", RK.load(path) is None)

        bad = json.loads(json.dumps(model))
        bad["w"] = [0.1] * (len(RK.FEATURE_NAMES) + 1)
        RK.save(bad, path)
        check(u"特征数不符 → 拒收（老模型不会静默失真）", RK.load(path) is None)
        finding(u"ranker 模型文件", u"**有** version 字段（MODEL_VERSION=1）",
                u"以前只校验特征个数、不看 version（特征数相同但含义变了就会用错模型）；"
                u"本轮改成：缺 version 仍收下，显式更高版本拒收")

    with_tmp(body)


# ============================================================
#  ⑨ 版本标记普查：谁有、谁没有、有没有被校验
# ============================================================
def t_markers():
    print(u"\n-- ⑨ 版本标记普查 --")

    def body(tmp):
        # 这些文件都是"纯 JSON + 靠 DEFAULTS/守护兜底"，没有 version 字段
        L.save_config(dict(L.DEFAULTS))
        S.save_config(dict(S.DEFAULTS))
        W.save_config(dict(W.DEFAULTS))
        TS.save(TS.DEFAULT_SCALE)
        for name, path in ((u"life_config.json", L.config_path()), (u"space_config.json", S.config_path()),
                           (u"world_memory_config.json", W.config_path()), (u"time_scale.json", TS.config_path())):
            keys = rj(path)
            check(u"%s 没有版本标记（靠默认值合并兜底）" % name,
                  not any(k in keys for k in ("version", "format", "schema")), str(list(keys)))

        # 加密容器是**样板**：有 MAGIC + VERSION，而且 decrypt 真校验
        try:
            import crypto_core as CR
            blob = CR.encrypt("Aa123456789012", b"hello")
            check(u"加密容器有 MAGIC（DICK）", blob[:4] == CR.MAGIC)
            check(u"加密容器里有版本号", blob[4] == CR.VERSION)
            check(u"往返能解开", CR.decrypt("Aa123456789012", blob) == b"hello")
            tampered = bytearray(blob)
            tampered[4] = 9                      # 改版本字节
            bad = False
            try:
                CR.decrypt("Aa123456789012", bytes(tampered))
            except Exception:
                bad = True
            check(u"版本不认识 → 明确报错（不是静默乱解）", bad)
            finding(u"加密备份容器（crypto_core）", u"**有** MAGIC+VERSION，且 decrypt 逐项校验",
                    u"仓库里唯一「版本号当真用」的格式：magic/版本/算法/KDF/迭代数全进 AAD")
        except Exception as e:
            check(u"crypto_core 探测没抛异常", False, u"%s: %s" % (type(e).__name__, e))

        # codex 剧本格式：常量声明了格式版本，但全仓只出现一次 → 没有被写入/校验
        src = io.open(os.path.join(ROOT, "codex_core.py"), encoding="utf-8").read()
        check(u"codex 里有格式版本常量", "CODEX_FORMAT" in src)
        check(u"但 CODEX_FORMAT 只在定义处出现（没写进包、也没校验）", src.count("CODEX_FORMAT") == 1)
        finding(u"codex 剧本包（codex/1.0）", u"常量声明了版本，但**没写进包、也没校验**",
                u"常量 CODEX_FORMAT 全仓只出现一次；DICK-Narrative 侧同样没有版本协商（未细查）")

    with_tmp(body)


# ============================================================
#  ⑩ 总结表
# ============================================================
def t_summary():
    print(u"\n-- ⑩ 审计结论表（格式 → 版本标记 → 结论） --")
    for kind, marker, verdict in FINDINGS:
        print(u"  · %s ｜ 版本标记：%s\n      %s" % (kind, marker, verdict))
    check(u"审计覆盖了至少 8 类持久化格式", len(FINDINGS) >= 8, str(len(FINDINGS)))


def t_cross_end():
    print(u"\n-- ⑪ 跨端互读（电脑端 ↔ 安卓端的存档/世界卡/三层配置） --")

    def body(tmp):
        # 进度时间戳：桌面 _tree_ts / 安卓 tree_ts —— 同一件东西两个键名
        try:
            import html_app
            check(u"桌面端认自己的 _tree_ts", html_app.tree_ts_of({"_tree_ts": "A"}) == "A")
            check(u"桌面端也认安卓的 tree_ts（否则同步过来的进度被当成没有）",
                  html_app.tree_ts_of({"tree_ts": "B"}) == "B")
            check(u"两个都没有 → 空串（调用方按'没有进度'处理）", html_app.tree_ts_of({}) == "")
            check(u"坏数据不炸（None/列表）", html_app.tree_ts_of(None) == "" and html_app.tree_ts_of([]) == "")
        except Exception as e:
            check(u"跨端时间戳探测没抛异常", False, u"%s: %s" % (type(e).__name__, e))

        # 世界卡/角色卡的"文件名即 ID"：两端都按名字取文件，不含路径分隔
        world = {"name": u"校园日常/测试", "description": u"x"}
        SG.atomic_write_json(os.path.join(tmp, "worlds", u"校园日常_测试.json"), world)
        back = rj(os.path.join(tmp, "worlds", u"校园日常_测试.json"))
        check(u"世界卡文件可读写（名字里的分隔符由 _safe_name 处理，见 world_packs）", back["name"] == world["name"])

        # 三层配置：两端字段名一致（内存里现读一遍，字段名照抄两端共用的那套）
        L.save_config(dict(L.DEFAULTS))
        S.save_config(dict(S.DEFAULTS))
        W.save_config(dict(W.DEFAULTS))
        lk = rj(L.config_path())
        check(u"life_config 字段名与安卓端一致（snake_case）",
              all(k in lk for k in ("enabled", "era", "region", "taste", "avoid", "show_meals",
                                    "max_chars", "location")), str(sorted(lk)))
        sk = rj(S.config_path())
        check(u"space_config 字段名与安卓端一致",
              all(k in sk for k in ("enabled", "max_chars", "show_reachable", "reachable_limit",
                                    "default_transport", "warn_when_impossible", "state_dir")), str(sorted(sk)))
        check(u"world_memory_config 有 max_facts（安卓端目前没有这一层）", "max_facts" in rj(W.config_path()))

        # 安卓独有的 mech_state/：电脑端代码里没有它的读写路径
        py_src = u""
        for fn in os.listdir(ROOT):
            if fn.endswith(".py"):
                try:
                    py_src += io.open(os.path.join(ROOT, fn), encoding="utf-8").read()
                except Exception:
                    pass
        check(u"电脑端没有读写 mech_state/ 目录（那是安卓端的第三个文件夹）",
              u'"mech_state"' not in py_src and u"'mech_state'" not in py_src)
        finding(u"跨端（桌面 ↔ 安卓）", u"各有各的：桌面 _tree_ts / 安卓 tree_ts",
                u"**实测发现键名不一致**：桌面只读 _tree_ts，安卓读写 tree_ts（Model.kt）→ "
                u"从另一端拿到的存档会被当成'没有进度'，LWW 可能被更旧的服务器版本盖掉。"
                u"本轮做了读取侧兼容（tree_ts_of 两种都认），**写入侧没有动**（是否镜像写另一个键，"
                u"会动存档结构，留给下次决定）。另：安卓独有 mech_state/，电脑端不读它")

    with_tmp(body)


def t_memory_chain():
    print(u"\n-- ⑫ 记忆链（memory/<角色>/chain.json，含老布局迁移） --")

    def body(tmp):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "memory_chain_plugin", os.path.join(ROOT, "plugins", "memory_chain_plugin.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plug = mod.MemoryChainPlugin(None)
            check(u"记忆链插件能建（core=None）", plug is not None)

            # 老布局：一份全局 memory/chain.json + 归档文件散在 memory/ 根
            mem = os.path.join(tmp, "memory")
            if not os.path.isdir(mem):
                os.makedirs(mem)
            # 老 chain.json 的形状：{角色: [{"path": "归档文件名", ...}, ...]}
            wj(os.path.join(mem, "chain.json"),
               {u"阿绫": [{"path": u"阿绫.part1.json", "ts": "2026-01-01T00:00:00"}],
                u"乙": [{"path": u"乙.part1.json"}]})
            wj(os.path.join(mem, u"阿绫.part1.json"), {"role": u"阿绫", "text": u"旧归档"})
            wj(os.path.join(mem, u"乙.part1.json"), {"role": u"乙", "text": u"旧归档"})
            moved, roles = plug.migrate_legacy()
            check(u"老布局能迁移（拆到各角色目录）", moved >= 1 and len(roles) >= 2,
                  u"moved=%s roles=%s" % (moved, roles))
            check(u"迁移后老 chain 改名留底（可回退）", os.path.isfile(os.path.join(mem, "chain.json.migrated")),
                  str(sorted(os.listdir(mem))))
            check(u"迁移只搬不删：原归档落到角色目录里",
                  any(os.path.isfile(os.path.join(mem, r, u"阿绫.part1.json")) for r in roles),
                  str(sorted(os.listdir(mem))))
            check(u"每个角色有自己的 chain.json", all(
                os.path.isfile(os.path.join(mem, r, "chain.json")) for r in roles))
            finding(u"memory/<角色>/chain.json（记忆链）", u"无版本标记，但有**布局迁移**",
                    u"老布局（全局 chain.json + 归档散在根）首次加载时按 key 拆到各角色目录，"
                    u"老文件改名 .migrated 留底（只搬不删，可回退）")

            # 形状不认识（例如 parts 是字符串而不是 {"path": ...}）→ 迁移函数会抛，
            # 但 on_load 外面包了 try（"不影响使用"）→ 结果是**安全失败**：不迁移、原数据不动
            wj(os.path.join(mem, "chain.json"), {u"甲": [u"甲.part1.json"], u"乙": [u"乙.part1.json"]})
            raised = False
            try:
                plug.migrate_legacy()
            except Exception:
                raised = True
            check(u"形状不认识 → 迁移抛异常（由 on_load 兜住，属于安全失败）", raised)
            check(u"抛异常时老 chain 仍在（没有被改名/没有被删）",
                  os.path.isfile(os.path.join(mem, "chain.json")))
            src = io.open(os.path.join(ROOT, "plugins", "memory_chain_plugin.py"), encoding="utf-8").read()
            check(u"on_load 确实把迁移包在 try 里（失败只打日志）",
                  u"老布局迁移出错（不影响使用）" in src)
        except Exception as e:
            check(u"记忆链探测没抛异常", False, u"%s: %s" % (type(e).__name__, e))

    with_tmp(body)


if __name__ == "__main__":
    print("=" * 70)
    print(u"兼容性审计（兼容线 1.0.x.x：同线内老数据必须读得起来、写回不许丢键）")
    print("=" * 70)
    t_configs()
    t_space_state()
    t_world_memory_state()
    t_saves()
    t_worlds()
    t_plugin_settings()
    t_image_presets()
    t_ranker()
    t_markers()
    t_cross_end()
    t_memory_chain()
    t_summary()
    print("\n" + "=" * 70)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("COMPAT_SURFACE_OK")
    sys.exit(1 if FAIL else 0)
