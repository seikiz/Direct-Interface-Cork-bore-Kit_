# -*- coding: utf-8 -*-
"""手机端（Kotlin）分道执行的结构检查。

为什么需要
----------
手机端原来的写法是到处 `scope.launch(Dispatchers.IO) { …; launch(Main) { 更新界面 } }`：
没有并发控制、没有顺序保证，而且**保序类的重活**（整棵树的序列化 + 写盘、机制状态落盘、
插件钩子）就压在**主线程**上 —— 每落一次回复就卡一下。

于是加了 `Lanes.kt`（与电脑端 `jobs.py` 同一套想法：一个模块一条运行线，同线保序、跨线并行），
并把主线程上的重活挪出去。这个测试守住的就是这件事 —— **它只做文本层面的结构检查，
证明"谁在跑、跑在哪条线上"，不证明运行时真的不卡**（那要在真机上量，不是这里能给的证据）。
所以它只盯三类回归：
  ① 有人把重活又搬回主线程；
  ② 有人把 `Lanes` 的 import 删了却留着调用（编译能过才怪，但那是 IDE 的事）；
  ③ 有人把 `persistState()` 之类的"快照 + 异步写"退回成"异步时现取现写"（写下去的是下一轮的状态）。

跑法：python tests\\test_android_lanes.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AND = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick")

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


def read(*parts):
    with io.open(os.path.join(AND, *parts), encoding="utf-8") as f:
        return f.read()


def seg_of(text, start, limit=6000):
    """从 start 标记处截一段，遇到下一个同级 `    fun ` 就停（别切进别人的代码）"""
    i = text.find(start)
    if i < 0:
        return ""
    seg = text[i:i + limit]
    j = seg.find("\n    fun ", len(start))
    return seg[:j] if j > 0 else seg


def test_lanes_exists():
    print("\n== 1. Lanes.kt：每条线都在用 + 同线保序 ==")
    lanes = read("core", "Lanes.kt")
    check("用 limitedParallelism 划并行度", "limitedParallelism" in lanes)
    check("用 SupervisorJob（一条线炸了不拖垮别的）", "SupervisorJob" in lanes)
    names = re.findall(r"val (\w+): CoroutineScope by lazy", lanes)
    check("声明了四条线", names == ["io", "vision", "plugin", "net"], str(names))
    check("io/plugin/vision 并行度是 1（保序）",
          lanes.count('lane("io", 1)') == 1 and lanes.count('lane("plugin", 1)') == 1 and
          lanes.count('lane("vision", 1)') == 1)
    check("net 可并行", "NET_PARALLELISM = 4" in lanes)
    check("任务失败被吃掉并记账（不会静默消失）",
          "catch (t: Throwable)" in lanes and "failCount" in lanes)
    check("有状态快照接口", "fun status()" in lanes and "fun busyNames()" in lanes)

    # 空线是负债：声明了却没人用，读代码的人会以为它在跑东西。
    used = []
    for dirpath, _, files in os.walk(AND):
        for fn in files:
            if fn.endswith(".kt") and fn != "Lanes.kt":
                with io.open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    used.append(f.read())
    blob = "\n".join(used)
    dead = [n for n in names if ("Lanes.%s" % n) not in blob]
    check("每条线都真被调用过（没有空线）", not dead, "没人用：%s" % dead)
    check("all 表里列全（否则状态页看不到这条线）",
          all(('"%s" to %s' % (n, n)) in lanes for n in names))


def test_app_uses_lanes():
    print("\n== 2. App.kt：重活都在线上，不在主线程 ==")
    app = read("app", "App.kt")
    check("导入了 Lanes", "import com.dick.core.Lanes" in app)
    check("再也不 new 裸线程", "Thread {" not in app and "Thread(" not in app)

    save = seg_of(app, "    fun saveTree()")
    check("找得到 saveTree()", bool(save))
    if save:
        i_snap = save.find("SaveFile(")
        i_lane = save.find('Lanes.on(Lanes.io, "存档落盘")')
        check("先取快照、再交给 io 线（顺序不能反）", 0 <= i_snap < i_lane,
              "snapshot=%d lane=%d" % (i_snap, i_lane))
        check("工坊同步走 net 线", 'Lanes.on(Lanes.net, "推工坊同步")' in save)

    land = seg_of(app, "    fun landAssistantReply(")
    check("找得到 landAssistantReply()", bool(land))
    if land:
        check("插件钩子在 plugin 线上", 'Lanes.on(Lanes.plugin, "插件钩子")' in land)
        check("插件钩子不再是主线程直调", "registry.onMessageReceived" in land and
              land.count("registry.onMessageReceived(") == 1)

    check("机制状态落盘统一走 persistMechAsync()",
          app.count("persistMechAsync()") >= 3 and "mech.persistState()" not in app)
    helper = seg_of(app, "    fun persistMechAsync()")
    check("找得到 persistMechAsync()", bool(helper))
    if helper:
        check("先取快照（pendingStateWrite）", "pendingStateWrite()" in helper)
        check("写盘才交给 io 线", 'Lanes.on(Lanes.io, "机制状态落盘")' in helper and "flushState(" in helper)


def test_mech_split():
    print("\n== 3. MechanicsEngine：快照与写盘分开（异步不许现取现写）==")
    mech = read("core", "MechanicsEngine.kt")
    check("有 pendingStateWrite()", "fun pendingStateWrite()" in mech)
    check("有 flushState()", "fun flushState(" in mech)
    body = seg_of(mech, "    fun persistState()")
    check("persistState() 退化成两步的组合（不再是各写一份）",
          "pendingStateWrite()" in body and "flushState(" in body)
    check("flushState() 里不读 state（谁都能在线程池里跑）",
          "state?" not in seg_of(mech, "    fun flushState("))


def test_card_io_off_main():
    print("\n== 4. 角色卡导入/导出：文件活挪出主线程 ==")
    app = read("app", "App.kt")
    cardio = read("app", "CardIo.kt")
    check("CardIo.kt 里没有 Compose 状态（不碰界面）",
          all(k not in cardio for k in ("sysMsgs.add", "wsStatus =", "avatarCache.",
                                        "mutableStateOf", "by vm.")))
    check("导入写了重名保护（连点两次不撞名）", "importingNames" in cardio)
    check("重名要算上磁盘真实状态", "roleNamesOnDisk()" in cardio)
    check("世界书写失败不谎报整卡失败", "世界书写入失败" in cardio)

    for marker, lane in (("val importCardLauncher", "导入角色卡"),
                         ("val exportCardLauncher", "导出角色卡"),
                         ("val wsExportLauncher", "工坊导出")):
        seg = seg_of(app, marker, 3000)
        check("%s 走 io 线" % marker, ('Lanes.on(Lanes.io, "%s")' % lane) in seg)
        check("%s 里不再直接读文件/写 URI" % marker,
              "contentResolver" not in seg and "readBytes()" not in seg)
    check("界面更新回到主线程（withContext(Dispatchers.Main)）",
          app.count("withContext(Dispatchers.Main)") >= 3)


def test_no_main_thread_io_regression():
    print("\n== 5. 剩下的主线程活儿必须是“只能主线程做的” ==")
    app = read("app", "App.kt")
    # scope.launch { … }（不带 dispa<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌tcher）只允许出现在 Compose 挂起调用处：
    # 抽屉开关 / 列表滚动 —— 这些本来就只能在主线程做，挪走反而错。
    bare = [ln.strip() for ln in app.splitlines()
            if re.search(r"scope\.launch\s*\{", ln)]
    bad = [ln for ln in bare if ("drawerState" not in ln and "animateScrollToItem" not in ln)]
    check("裸 launch 只剩 Compose 挂起调用", not bad, "可疑：%s" % bad[:3])
    # 反例存档：stripTags 会写 mech 的 state（apply=false 时也可能新建 status 字段），
    # 属于"多个线程不能同时碰"的东西 → 它必须留在主线程串行执行，不能为了快就丢到别的线上。
    check("stripTags 没有被丢到别的线程去跑",
          not re.search(r"Lanes\.on\([^)]*\)\s*\{[^}]*stripTags", app, re.S))
    check("App.kt 里写明了这个取舍", "stripTags 会写" in app)


def test_no_raw_threads_left():
    print("\n== 6. 全仓 Kotlin：裸线程只剩两处被说明过的 ==")
    # 这两处是"线程本来就是对的"：
    #   ChatEngine  —— 流式读取的工作线程，要能被 stop() interrupt，也不能长期占住一条线
    #   TrpgServer  —— 常驻的 accept/handle 循环（不是干完就完的任务，塞进线里会永久占名额）
    allowed = {"ChatEngine.kt": "流式读取", "TrpgServer.kt": "常驻的服务端循环"}
    hits, missing_note = {}, []
    for dirpath, _, files in os.walk(AND):
        for fn in files:
            if not fn.endswith(".kt") or fn == "Lanes.kt":
                continue
            with io.open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                src = f.read()
            n = len(re.findall(r"\bThread\s*\{|\bThread\s*\(", src))
            n -= src.count("Thread.sleep(")          # 限速用的 Thread.sleep 不算
            if n > 0:
                hits[fn] = n
            if fn in allowed and allowed[fn] not in src:
                missing_note.append(fn)
    unexpected = dict((k, v) for k, v in hits.items() if k not in allowed)
    check("裸线程只出现在被说明的两个文件里", not unexpected, "意外：%s" % unexpected)
    check("被说明的文件里真的写了原因", not missing_note, "没写：%s" % missing_note)
    for fn in allowed:
        check("%s 仍保留裸线程（豁免没被误删）" % fn, fn in hits)


if __name__ == "__main__":
    print("=" * 58)
    print(u"手机端分道执行结构检查")
    print("=" * 58)
    test_lanes_exists()
    test_app_uses_lanes()
    test_mech_split()
    test_card_io_off_main()
    test_no_main_thread_io_regression()
    test_no_raw_threads_left()
    print("\n" + "=" * 58)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ANDROID_LANES_TEST_OK")
    sys.exit(1 if FAIL else 0)
