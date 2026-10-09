# -*- coding: utf-8 -*-
"""手机端生活层/空间层：表与对拍基准的结构检查（不需要 Android SDK / kotlinc）。

守的是三件事
------------
  ① **表只有一份真相**：Kotlin 那边的年代/厨具/食材/地点/交通表是从 Python 生成的
     （`tools/gen_parity.py`），手改了或者忘了重新生成 → 这里失败；
  ② **对拍基准不能成为死数据**：`ParityGoldens.kt` 里九组用例，每一组都得被
     `LifeParityTest.kt` / `SpaceParityTest.kt` 真的用到；
  ③ **随机数必须是 CPython 那一套**：菜单的确定性承诺全靠它，改坏了不会报错，
     只会"她今天吃的东西变了"，所以把关键常量/算法点也钉一下。

真正跑 Kotlin 对拍的是 `DICK-Android\\selftest\\run.ps1`（需要 kotlinc，本机有；
CI 上没有，所以 CI 只跑这个 Python 侧的结构与新鲜度检查）。

跑法：python tests\\test_android_parity.py
"""
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AND = os.path.join(ROOT, "DICK-Android")
CORE = os.path.join(AND, "app", "src", "main", "java", "com", "dick", "core")
SELFTEST = os.path.join(AND, "selftest")

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


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, ROOT)
    import commonsense as CS
    import life_core as L
    import space_core as S

    print("=" * 58)
    print(u"手机端生活层/空间层：表 + 对拍基准")
    print("=" * 58)

    # ---------- ① 生成物<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌必须是最新的 ----------
    print(u"\n-- ① 生成物新鲜度（python tools/gen_parity.py --check） --")
    gen = os.path.join(ROOT, "tools", "gen_parity.py")
    check(u"生成脚本在", os.path.isfile(gen))
    proc = subprocess.run([sys.executable, gen, "--check"], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    check(u"Tables.kt / ParityGoldens.kt 与 Python 的表一致（没手改、没忘生成）",
          proc.returncode == 0, out.strip().replace("\n", " | ")[:400])

    # ---------- ② 文件都在 ----------
    print(u"\n-- ② 手机端文件 --")
    files = {
        "core/Tables.kt": os.path.join(CORE, "Tables.kt"),
        "core/TableTypes.kt": os.path.join(CORE, "TableTypes.kt"),
        "core/PyRandom.kt": os.path.join(CORE, "PyRandom.kt"),
        "core/Commonsense.kt": os.path.join(CORE, "Commonsense.kt"),
        "core/LifeCore.kt": os.path.join(CORE, "LifeCore.kt"),
        "core/SpaceCore.kt": os.path.join(CORE, "SpaceCore.kt"),
        "selftest/ParityGoldens.kt": os.path.join(SELFTEST, "ParityGoldens.kt"),
        "selftest/LifeParityTest.kt": os.path.join(SELFTEST, "LifeParityTest.kt"),
        "selftest/SpaceParityTest.kt": os.path.join(SELFTEST, "SpaceParityTest.kt"),
    }
    src = {}
    for label, p in files.items():
        exists = os.path.isfile(p)
        check(u"%s 在" % label, exists)
        if exists:
            src[label] = read(p)

    tables = src.get("core/Tables.kt", "")
    goldens = src.get("selftest/ParityGoldens.kt", "")

    # ---------- ③ 表覆盖了 Python 那边的每一项 ----------
    print(u"\n-- ③ 表覆盖（Kotlin 表 vs Python 表） --")
    check(u"Tables.kt 标了「生成物，别手改」", u"生成物" in tables and u"别手改" in tables)
    missing = [k for k in CS.ERAS if (u'"%s"' % k) not in tables]
    check(u"常识库 12 个年代都在（含仙侠/末世）", not missing, u"缺：%s" % missing)
    missing = [e["key"] for e in L.ERAS if (u'"%s"' % e["key"]) not in tables]
    check(u"生活层 10 个年代都在", not missing, u"缺：%s" % missing)
    missing = [m for m in L.METHOD_SINCE if (u'"%s"' % m) not in tables]
    check(u"做法表齐", not missing, u"缺：%s" % missing)
    missing = [n for n in (u"小米粥", u"东坡肉", u"麻婆豆腐", u"空气炸鸡块") if n not in tables]
    check(u"食材/做法库抽到了（含年代边界菜）", not missing, u"缺：%s" % missing)
    missing = [n for n, _ in CS.ERAS[u"仙侠"][u"places"] if (u'"%s"' % n) not in tables]
    check(u"仙侠地图的地点都在", not missing, u"缺：%s" % missing)
    check(u"默认值也来自 Python（max_chars / reachable_limit）",
          u"maxChars = %d" % L.DEFAULTS[u"max_chars"] in tables and
          u"reachableLimit = %d" % S.DEFAULTS[u"reachable_limit"] in tables)

    # 单一真相：逻辑文件里不许再抄一份表
    for label in ("core/LifeCore.kt", "core/SpaceCore.kt", "core/Commonsense.kt"):
        body = src.get(label, "")
        leaked = [n for n in (u"小米粥", u"东坡肉", u"陶鬲", u"篝火", u"便利店") if n in body]
        check(u"%s 没有把表抄第二份" % label, not leaked, u"出现了：%s" % leaked)

    # ---------- ④ 对拍基准九组，且都被真的用到 ----------
    print(u"\n-- ④ 对拍基准（九组，不许有死数据） --")
    groups = [
        ("eraCases", "selftest/LifeParityTest.kt"),
        ("menuCases", "selftest/LifeParityTest.kt"),
        ("lifeInjectCases", "selftest/LifeParityTest.kt"),
        ("lifeDescribeCases", "selftest/LifeParityTest.kt"),
        ("mapCases", "selftest/SpaceParityTest.kt"),
        ("travelCases", "selftest/SpaceParityTest.kt"),
        ("reachCases", "selftest/SpaceParityTest.kt"),
        ("openCases", "selftest/SpaceParityTest.kt"),
        ("tagCases", "selftest/SpaceParityTest.kt"),
        ("spaceInjectCases", "selftest/SpaceParityTest.kt"),
    ]
    for name, user in groups:
        declared = re.search(r"val %s: List<[^>]+> = listOf\(" % name, goldens) is not None
        used = ("Goldens.%s" % name) in src.get(user, "")
        check(u"基准 %s 有数据" % name, declared, u"ParityGoldens.kt 里找不到声明")
        check(u"基准 %s 被 %s 用到" % (name, os.path.basename(user)), used)

    # 关键场景真的在基准里（不是空跑一遍）
    print(u"\n-- ⑤ 关键场景确实被冻住了 --")
    for label, needle in ((u"720× 倍率", u"720.0"),
                          (u"生活注入头", u"【生活·那边】"),
                          (u"空间注入头", u"【空间】"),
                          (u"屋里那一行", u"屋里："),
                          (u"地图外警告", u"不在地图上"),
                          (u"穿帮已提醒两次的用例", u"不再念"),
                          (u"关掉某一层 → 不注入", u"关掉生活层")):
        check(u"基准里有「%s」" % label, needle in goldens)

    # ---------- ⑥ run.ps1 接线 ----------
    print(u"\n-- ⑥ 自检脚本接线 --")
    run_ps1 = read(os.path.join(SELFTEST, "run.ps1"))
    check(u"第 3 步编进了对拍基准", u"ParityGoldens.kt" in run_ps1)
    check(u"第 3 步跑生活层对拍", u"com.dick.parity.life.LifeParityTestKt" in run_ps1)
    check(u"第 3 步跑空间层对拍", u"com.dick.parity.space.SpaceParityTestKt" in run_ps1)
    check(u"空间层文件不在也能跑（不让整步挂掉）", u"Test-Path $spaceTest" in run_ps1 or u"$hasSpace" in run_ps1)

    # ---------- ⑦ 随机数：CPython 那一套 ----------
    print(u"\n-- ⑦ PyRandom 必须是 CPython 的 MT19937 --")
    rnd = src.get("core/PyRandom.kt", "")
    for label, needle in ((u"种子走 SHA-512", u"SHA-512"),
                          (u"init_by_array 的初值", u"19650218"),
                          (u"init_by_array 的两个乘数", u"1664525"),
                          (u"第二个乘数", u"1566083941"),
                          (u"扭转矩阵常量", u"-0x66f74f21"),
                          (u"53 位小数拼接", u"67108864.0"),
                          (u"key 数组低位在前（曾经搞反过一次）", u"reversedArray()"),
                          (u"randrange 用 bit_length + 拒绝采样", u"numberOfLeadingZeros")):
        check(label, needle in rnd)

    # ---------- ⑧ 接线：界面 → 引擎 → 两层 ----------
    print(u"\n-- ⑧ 接线（注入进载荷、标签被收掉） --")
    app_kt = read(os.path.join(AND, "app", "src", "main", "java", "com", "dick", "app", "App.kt"))
    engine_kt = read(os.path.join(CORE, "ChatEngine.kt"))
    bridge_kt = read(os.path.join(CORE, "ChatBridge.kt"))
    check(u"ChatEngine 有 contextProvider 钩子", u"var contextProvider" in engine_kt)
    t_idx = engine_kt.find(u"TimeContext.build(chain, TimeScale.current)")
    c_idx = engine_kt.find(u"contextProvider?.invoke()")
    check(u"注入插在【时间】之后（与电脑端顺序一致）", 0 <= t_idx < c_idx)
    check(u"界面把钩子接上了", u"engine.contextProvider = { ChatBridge.injections() }" in app_kt)
    check(u"界面把链/角色/世界卡交给桥", all(s in app_kt for s in (
        u"ChatBridge.chainProvider", u"ChatBridge.roleJsonProvider", u"ChatBridge.worldJsonProvider")))
    check(u"边界世界卡是原始 JSON（params 没在界面上丢掉）", u"worldCards[n] = o" in app_kt)
    check(u"回复落地时收位置标签", u"consumeSpaceMoves(stripped, spaceWho)" in app_kt)
    check(u"玩家消息也收（[ploc:…]）", u"consumeSpaceMoves(applyRegex(processed, \"user\")" in app_kt)
    check(u"流式显示也剥（不然标签会闪在屏幕上）",
          app_kt.count(u"ChatBridge.takeMoves(mech.stripTags(full, apply = false)).first") == 2)
    check(u"记账走 io 线（写盘不占主线程）", u'Lanes.on(Lanes.io, "空间位置记账")' in app_kt)

    # ---------- ⑨ 世界卡库 ----------
    print(u"\n-- ⑨ 世界卡库（随 APK 附带 + 一键装） --")
    packs = read(os.path.join(CORE, "WorldPacks.kt"))
    plug = read(os.path.join(AND, "app", "src", "main", "java", "com", "dick", "plugins",
                             "LifeSpacePlugin.kt"))
    check(u"WorldPacks 从 assets 释放", u"seedFromAssets" in packs and u"AssetManager" in packs)
    check(u"默认不覆盖同名世界卡", u"--force" in packs and u"已经有一张同名的世界卡了" in packs)
    check(u"覆盖前先备份", u".bak-" in packs and u"fun backup(" in packs)
    check(u"装包是原子写（临时文件 + 改名）", u".tmp" in packs and u"renameTo" in packs)
    check(u"插件有 /生活", u'"生活" ->' in plug)
    check(u"插件有 /在哪（含记玩家位置）", u'"在哪"' in plug and u"movePlayerTo" in plug)
    check(u"插件有 /世界包（列表/看/装）", all(s in plug for s in (u'"世界包"', u'"看"', u'"装"')))
    check(u"插件注册进注册表", u"registry.register(LifeSpacePlugin())" in app_kt)
    check(u"装完通知界面重扫", u"notifyWorldsChanged" in plug and u"ChatBridge.worldsChanged" in app_kt)
    # assets 与仓库里的卡包一一对应
    src_packs = sorted(f for f in os.listdir(os.path.join(ROOT, "world_packs")) if f.endswith(".json"))
    asset_dir = os.path.join(AND, "app", "src", "main", "assets", "world_packs")
    asset_packs = sorted(os.listdir(asset_dir)) if os.path.isdir(asset_dir) else []
    check(u"APK assets 与 world_packs/ 一一对应", src_packs == asset_packs,
          u"%s vs %s" % (src_packs, asset_packs))
    same = all(read(os.path.join(asset_dir, f)) == read(os.path.join(ROOT, "world_packs", f))
               for f in src_packs)
    check(u"两份内容逐字相同（复制品不许有自己的想法）", same)

    print("\n" + "=" * 58)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ANDROID_PARITY_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
