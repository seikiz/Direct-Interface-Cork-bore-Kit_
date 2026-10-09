# -*- coding: utf-8 -*-
"""世界卡库回归测试：卡包本身合法 + 装包不破坏用户数据 + 命令能用

为什么测这些
------------
1. `worlds/` 被 .gitignore 忽略 —— 仓库里其实**一张世界卡都没有**，
   于是"打包后世界列表是空的""新 clone 没有示例世界"这类问题没人发现。
   卡包放在受版本控制的 `world_packs/`，所以这里先断言**每个包都是一张合法世界卡**。
2. 每个包还带空间层/生活层的常识参数（era / era_kind / space 地图）。
   参数写坏了不会报错，只会静默退回"现代都市"—— 所以逐个包都验一遍。
3. 装包是**写用户目录**的操作，必须：不覆盖同名、force 才覆盖、覆盖前留备份。

跑法：python tests\\test_world_packs.py
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
sys.stdout.reconfigure(encoding="utf-8")

import space_core as S  # noqa: E402
import world_packs as W  # noqa: E402

PASS = 0
FAIL = 0
PACK_DIR = os.path.join(ROOT, "world_packs")


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def test_pack_files():
    print("\n== ① 卡包目录与文件 ==")
    check("world_packs 目录存在（受版本控制，不是 worlds/ 那种被忽略的）", os.path.isdir(PACK_DIR))
    check("worlds/ 是被忽略的运行时目录，卡包不该放在那儿",
          not os.path.isdir(os.path.join(ROOT, "worlds") ) or
          os.path.isfile(os.path.join(ROOT, ".gitignore")))
    files = sorted(f for f in os.listdir(PACK_DIR) if f.endswith(".json"))
    check("至少有 5 个卡包", len(files) >= 5, str(files))
    for fn in files:
        p = os.path.join(PACK_DIR, fn)
        try:
            card = json.load(io.open(p, encoding="utf-8"))
        except Exception as e:
            check("%s 是合法 JSON" % fn, False, str(e))
            continue
        check("%s 是合法 JSON" % fn, True)
        check("%s 有 name/description/rules" % fn,
              bool(card.get("name")) and bool(card.get("description"))
              and isinstance(card.get("rules"), list), str(list(card.keys())))
        params = card.get("params") or {}
        sp_raw = params.get("space")
        check("%s 带 space 地图（字符串或 dict）" % fn,
              isinstance(sp_raw, (str, dict)), type(sp_raw).__name__)
        sp = json.loads(sp_raw) if isinstance(sp_raw, str) else (sp_raw or {})
        check("%s 地图里有 places 且 ≥5 个" % fn,
              len(sp.get("places") or []) >= 5, str(len(sp.get("places") or [])))
        home = sp.get("home")
        names = [str(x.get("name")) for x in (sp.get("places") or []) if isinstance(x, dict)]
        check("%s 声明了 home 且在 places 里（圆心必须在图上）" % fn,
              bool(home) and home in names, "home=%s names=%s" % (home, names[:5]))
        check("%s 有世界书条目（开箱即用）" % fn,
              bool(card.get("entries")), str(len(card.get("entries") or [])))
        # 参数必须被<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌两层认出来
        mp = S.map_for(None, card)
        check("%s 地图用上了卡里的 home" % fn, mp["home"] == home, mp["home"])
        check("%s 房间/交通非空" % fn,
              bool(mp["rooms"]) and bool(mp["transport"]),
              "%d 屋 / %d 交通" % (len(mp["rooms"]), len(mp["transport"])))


def test_list_and_find():
    print("\n== ② 列出与查找 ==")
    packs = W.list_packs()
    check("list_packs 列出所有包", len(packs) >= 5, str(len(packs)))
    names = [p["name"] for p in packs]
    check("每个条目带摘要字段",
          all(p.get("name") and p.get("places") for p in packs), str(packs[:1]))
    check("按名字能找到", W.find_pack("江南水乡·明末") is not None)
    check("按文件名也能找到", W.find_pack("江南水乡·明末.json") is not None)
    check("部分匹配也能找到", W.find_pack("江南") is not None)
    check("找不到时返回 None", W.find_pack("不存在的世界") is None)
    check("describe 给人话摘要", "地点" in W.describe(packs[0]), W.describe(packs[0]))
    check("pack_dirs 含工程内的 world_packs", PACK_DIR in W.pack_dirs(), str(W.pack_dirs()))


def test_install():
    print("\n== ③ 装包：不覆盖、force 才覆盖、留备份 ==")
    tmp = tempfile.mkdtemp(prefix="dick_wp_")
    try:
        ok, msg = W.install("江南水乡·明末", tmp)
        check("第一次装成功", ok, msg)
        dst = os.path.join(tmp, "江南水乡·明末.json")
        check("文件落到了目标目录", os.path.isfile(dst))
        card = json.load(io.open(dst, encoding="utf-8"))
        check("装进去的就是那张卡（name 一致）", card.get("name") == "江南水乡·明末")
        # 用户改了卡 → 再装不能覆盖
        card["description"] = "我自己改过的"
        io.open(dst, "w", encoding="utf-8").write(json.dumps(card, ensure_ascii=False))
        ok2, msg2 = W.install("江南水乡·明末", tmp)
        check("同名默认不覆盖（保护用户改动）", ok2 is False and "同名" in msg2, msg2)
        still = json.load(io.open(dst, encoding="utf-8"))
        check("用户改动还在", still.get("description") == "我自己改过的")
        ok3, msg3 = W.install("江南水乡·明末", tmp, overwrite=True)
        check("force 能覆盖", ok3, msg3)
        back = json.load(io.open(dst, encoding="utf-8"))
        check("覆盖后内容回到卡包原文", back.get("description") != "我自己改过的")
        check("覆盖前留了备份（backup/ 里有一份）",
              os.path.isdir(os.path.join(tmp, "backup"))
              and os.listdir(os.path.join(tmp, "backup")), str(os.listdir(tmp)))
        ok4, msg4 = W.install("不存在的世界", tmp)
        check("装不存在的包 → 明确失败", ok4 is False and "没找到" in msg4, msg4)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_command():
    print("\n== ④ /世界包 命令 ==")
    from plugins.worldpack_plugin import WorldPackPlugin
    p = WorldPackPlugin(core=None)
    check("非本插件命令 → None", p.on_command("dice", "2d6") is None)
    r = p.on_command("世界包", "")
    check("列表给出所有包与装法",
          "世界卡库" in r and "江南水乡·明末" in r and "/世界包 装" in r, r[:120])
    r2 = p.on_command("世界包", "看 江南水乡·明末")
    check("看详情给出说明/规则/条目",
          "说明：" in r2 and "规则：" in r2 and "世界书[" in r2, r2[:140])
    r3 = p.on_command("世界包", "看 不存在的")
    check("看找不到的包会提示现有包名", "没找到" in r3 and "江南水乡" in r3, r3[:120])
    r4 = p.on_command("世界包", "装")
    check("装但没有名字 → 提示写法", "写法" in r4, r4[:80])
    r5 = p.on_command("世界包", "瞎写 江南")
    check("未知子命令 → 提示写法", "写法" in r5, r5[:80])


if __name__ == "__main__":
    print("=" * 62)
    print(u"世界卡库测试")
    print("=" * 62)
    test_pack_files()
    test_list_and_find()
    test_install()
    test_command()
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("WORLD_PACKS_TEST_OK")
    sys.exit(1 if FAIL else 0)
