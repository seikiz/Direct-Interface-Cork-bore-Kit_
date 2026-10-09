# -*- coding: utf-8 -*-
"""DICK 电脑版一键发布：后处理 + 自检 + 打 zip

用法（在工程根目录）：
    python build_release.py            # 用现有的 dist/DICK-HTML 后处理并打 zip
    python build_release.py --build    # 先清缓存 + 跑 PyInstaller，再后处理打 zip

做了四件事：
  1) 后处理：tavern-installer 从 _internal/ 提到顶层 + 生成 start.bat
  2) 自检：包内 web/index.html 必须和源码一致，且含新功能特征串
     （PyInstaller 会缓存 web/，不清缓存会把旧前端打进包里 —— 真踩过）
  3) 打 zip 到 DICK-发布/DICK-电脑版.zip（包内文件平铺，解压即用）
  4) 顺手核对手机版 apk 的时间戳，提醒是不是旧的

注意：打包前一定要先关掉正在运行的 DICK-HTML.exe，否则它会锁住 debug.log 导致打包失败。
"""
import glob
import os
import shutil
import subprocess
import sys
import time
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "dist", "DICK-HTML")
# 发布目录：默认在工程上一级（DICK-发布/），可用 --out 或环境变量 DICK_REL_DIR 改。
# 为什么需要这个开关：某些环境里 Python 进程写不了那个目录（只能读），
# 而打包本身没问题 —— 那就先写到能写的地方，再自己移过去。
REL = os.environ.get("DICK_REL_DIR") or os.path.join(os.path.dirname(ROOT), "DICK-发布")
PY = os.path.join(ROOT, "utau_env", "Scripts", "python.exe")

# 包内前端必须含这些串，<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌否则说明打进去的是旧前端
FEATURES = {
    "🎬 播放器 按钮": "galPlayerBtn",
    "导出到播放器函数": "galPackPlayer",
    "导出接口": "codex_export_player",
    "导出进度轮询": "codex_player_status",
    "播放器就绪探测": "codex_player_ready",
    "回归·快速加点": "快速加点",
    "回归·11种点类型": "换BGM",
    # 2026-09 新增功能：打进包的前端必须含这些串，否则说明打的是旧前端
    "事件·可视化编辑器": "evEditor",
    "事件·进度面板": "evShowProgress",
    "事件·可重复触发": "可重复触发",
    "事件·好感加成": "好感加成",
    "记忆·调试面板": "memDebugDraw",
    # 2026-09 生图引擎：四种后端 + 种子重抽 + 可编辑预设层
    "生图·后端选择": "stImgBackend",
    "生图·种子重抽": "genReroll",
    "生图·预设编辑器": "stPresetText",
    "生图·补充风格词": "genExtra",
}


def fail(msg):
    print("❌ " + msg)
    sys.exit(1)


# 打包前必须关掉的进程：DICK 自己锁 debug.log，播放器锁 dist/DICK-HTML/播放器/ 里的 exe
LOCKING_IMAGES = ("DICK-HTML.exe", "DICK-Narrative.exe", "DICK.exe")


def locking_processes():
    """返回当前在跑、会锁住构建产物的进程名列表"""
    found = []
    for img in LOCKING_IMAGES:
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + img, "/NH"],
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="ignore")
            if img in (out.stdout or ""):
                found.append(img)
        except Exception:
            pass
    return found


def running_dick():
    return bool(locking_processes())


# 便携版的数据目录：exe 放哪，saves/worlds/codex 就跟着建在哪。
# 所以 dist/DICK-HTML 里既有构建产物，也有【用户数据】—— 清目录时必须先挪走再放回。
RUNTIME_DATA = ("saves", "worlds", "codex", "memory", "plugin_settings",
                "prompt_presets", "personas", "plugins",
                "config.json", "quick_replies.json", "financial_history.json",
                "workshop_config.json")


def stash_runtime_data():
    """把便携版的用户数据挪到一边，返回 (暂存目录, 已挪走的名单)"""
    if not os.path.isdir(BUILD):
        return None, []
    stash = BUILD.rstrip("\\/") + "_data_" + time.strftime("%Y%m%d-%H%M%S")
    moved = []
    for n in RUNTIME_DATA:
        src = os.path.join(BUILD, n)
        if os.path.exists(src):
            os.makedirs(stash, exist_ok=True)
            shutil.move(src, os.path.join(stash, n))
            moved.append(n)
    return (stash if moved else None), moved


def restore_runtime_data(stash, moved):
    """构建完把用户数据放回去（保留构建新生成的其余文件）"""
    if not stash or not moved:
        return
    for n in moved:
        src = os.path.join(stash, n)
        dst = os.path.join(BUILD, n)
        if not os.path.exists(src):
            continue
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        elif os.path.exists(dst):
            os.remove(dst)
        shutil.move(src, dst)
    shutil.rmtree(stash, ignore_errors=True)


def force_rmtree(path):
    """删目录，顺带清掉只读属性。
    jpackage 产出的 DICK-Narrative.exe 带只读位，copytree 会保留，
    而 shutil.rmtree 默认删不掉只读文件（WinError 5）—— 这就是之前清目录老失败的根因。"""
    import stat

    def onerr(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    if os.path.isdir(path):
        shutil.rmtree(path, onerror=onerr)


def step_build():
    stuck = locking_processes()
    if stuck:
        fail("这些进程还在跑，会锁住构建产物：%s —— 先关掉再打包。" % "、".join(stuck))
    print("== 1) 清 PyInstaller 缓存（清掉才会重新收 web/）==")
    shutil.rmtree(os.path.join(ROOT, "build", "DICK_HTML"), ignore_errors=True)
    print("   已清 build/DICK_HTML")
    # 关键：dist/DICK-HTML 同时是便携版的数据目录，不能连用户数据一起删
    stash, moved = stash_runtime_data()
    if moved:
        print("   已把便携版用户数据挪到一边：%s" % "、".join(moved))
    else:
        print("   （便携版目录里没有运行时数据）")
    try:
        # 不带 ignore_errors：删不干净要立刻报出来，而不是留给 PyInstaller 抛 WinError 5
        # 刚拷完的 126MB 播放器常被杀软/索引瞬时占着，所以重试几次
        if os.path.isdir(BUILD):
            last = None
            for attempt in range(6):
                try:
                    force_rmtree(BUILD)
                    if os.path.isdir(BUILD):
                        raise RuntimeError("还有残留")
                    last = None
                    break
                except Exception as e:
                    last = e
                    print("   清目录没干净（第 %d 次）：%s，等 3 秒重试…" % (attempt + 1, e))
                    time.sleep(3)
            if last is not None:
                fail("清不掉 dist/DICK-HTML（%s）。多半是有进程占着：确认没有 "
                     "DICK-HTML.exe / DICK-Narrative.exe 在跑，再重试。" % last)
        print("   已清 dist/DICK-HTML")
        print("== 2) PyInstaller 构建（几分钟）==")
        t0 = time.time()
        r = subprocess.run([PY, "-m", "PyInstaller", "DICK_HTML.spec", "--noconfirm"], cwd=ROOT)
        if r.returncode != 0:
            fail("PyInstaller 失败（退出码 %d）" % r.returncode)
        print("   构建完成，用时 %.0f 秒" % (time.time() - t0))
    finally:
        # 无论成功失败都要把用户数据放回去，不能让它烂在暂存目录里
        restore_runtime_data(stash, moved)
        if moved:
            print("   已把用户数据放回 dist/DICK-HTML：%s" % "、".join(moved))


def step_postprocess():
    print("== 3) 后处理 ==")
    ti = os.path.join(BUILD, "tavern-installer")
    ti_int = os.path.join(BUILD, "_internal", "tavern-installer")
    if os.path.isdir(ti_int):
        if os.path.isdir(ti):
            shutil.rmtree(ti)
        shutil.copytree(ti_int, ti)
        print("   tavern-installer 顶层化")
    tpl = os.path.join(ti, "start.bat.template")
    if os.path.isfile(tpl):
        shutil.copyfile(tpl, os.path.join(ti, "start.bat"))
        print("   start.bat 已生成")
    vg = os.path.join(BUILD, "_internal", "voice_guide.txt")
    if os.path.isfile(vg):
        shutil.copyfile(vg, os.path.join(BUILD, "voice_guide.txt"))
        print("   voice_guide.txt 顶层化")
    # 独立解密工具必须躺在 exe 旁边。
    # datas 会把它放进 _internal/，而 _internal 对用户来说等于不可见 ——
    # 灾难恢复时「找不到那个脚本」等于没有这个脚本。
    tool = os.path.join(BUILD, "_internal", "dick_backup_tool.py")
    if os.path.isfile(tool):
        shutil.copyfile(tool, os.path.join(BUILD, "dick_backup_tool.py"))
        print("   dick_backup_tool.py 顶层化（解密工具与 exe 同级）")
    # 顺手给一份怎么用的说明，省得用户对着 .py 发愣
    note = os.path.join(BUILD, "备份怎么打开.txt")
    try:
        with open(note, "w", encoding="utf-8") as f:
            f.write(
                "DICK 加密备份怎么打开\n"
                "========================================\n\n"
                "正常情况下不用看这个文件：\n"
                "  打开 DICK → 左侧「🔐 加密备份」→ 输入口令 → 「📂 从备份还原」\n\n"
                "如果 DICK 装不上了、换电脑了、或者程序没了：\n"
                "  1) 装 Python 3（python.org，勾选 Add to PATH）\n"
                "  2) 命令行执行： pip install cryptography\n"
                "  3) 在本文件夹打开命令行，执行：\n"
                "       python dick_backup_tool.py 查看  你的备份.dickbackup\n"
                "       python dick_backup_tool.py 解密  你的备份.dickbackup\n"
                "     解密结果会放在备份文件旁边的「_还原」文件夹里。\n\n"
                "口令是什么只有你自己知道 —— 我们没有留任何后门，\n"
                "也没有任何办法帮你找回。请务必单独记好。\n")
        print("   备份怎么打开.txt 已生成")
    except Exception as e:
        print("   （说明文件生成失败：%s）" % e)


def find_player():
    """找已构建好的原生播放器目录（直接含 DICK-Narrative.exe）。
    这里的候选顺序必须和 Direct-Interface Cork-bore Kit.py 的 _find_player_dir 保持一致，
    否则会出现「打包时有、运行时找不到」的错位。"""
    name = "DICK-Narrative"
    dev = os.path.join(name, "app", "build", "compose",
                       "binaries", "main", "app", name)
    cands = [
        os.environ.get("DICK_PLAYER_DIR"),
        os.path.join(ROOT, dev),
        os.path.join(ROOT, "player", name),
        os.path.join(ROOT, name + "-播放器"),
        os.path.join(ROOT, "播放器", name),
        os.path.join(ROOT, "播放器"),
        os.path.join(ROOT, name),
    ]
    for c in cands:
        try:
            if c and os.path.isfile(os.path.join(c, name + ".exe")):
                return c
        except Exception:
            continue
    return None


def step_bundle_player():
    print("== 3.5) 把原生播放器打进包里 ==")
    src = find_player()
    dst = os.path.join(BUILD, "播放器")
    if not src:
        print("   ⚠ 没找到构建好的播放器，跳过。")
        print("     别人点「🎬 播放器」会提示未构建；要带上就先在 DICK-Narrative 跑 build.ps1 -Exe")
        return False
    if os.path.isdir(dst):
        # 必须用 force_rmtree：播放器里的 DICK-Narrative.exe 带只读位，
        # 普通 shutil.rmtree(ignore_errors=True) 会【静默失败】→ 紧接着 copytree 撞
        # FileExistsError(WinError 183)。这条只在"不重新编译、只重打包"的快路径上必现。
        force_rmtree(dst)
    shutil.copytree(src, dst)
    # 播放器自带一份示例故事，让用户直接双击 exe 也有东西看；导出时会自动被清掉
    mb = 0
    for base, _d, files in os.walk(dst):
        for fn in files:
            try:
                mb += os.path.getsize(os.path.join(base, fn))
            except OSError:
                pass
    print("   %s" % src)
    print("   → %s  （%.1f MB）" % (dst, mb / 1048576.0))
    return True


def step_selfcheck():
    print("== 4) 自检：包内前端 ==")
    idx = os.path.join(BUILD, "_internal", "web", "index.html")
    src = os.path.join(ROOT, "web", "index.html")
    if not os.path.isfile(idx):
        fail("包里没有 _internal/web/index.html")
    with open(idx, encoding="utf-8") as f:
        bundled = f.read()
    with open(src, encoding="utf-8") as f:
        source = f.read()

    bad = 0
    for name, needle in FEATURES.items():
        hit = needle in bundled
        print("   %s %s" % ("OK  " if hit else "FAIL", name))
        if not hit:
            bad += 1
    same = bundled == source
    print("   %s 包内前端与源码一致（%d 字符）" % ("OK  " if same else "FAIL", len(source)))
    if not same:
        bad += 1
    if bad:
        fail("包内前端不对（%d 项）。多半是 PyInstaller 缓存了旧的 web/，"
             "用 --build 重打一次。" % bad)

    # 随包必须存在的文件。这些都是「本地跑得通、打包后废掉」的高危项：
    # 插件的 import 不会被 PyInstaller 跟进，懒加载的模块也可能漏收。
    required = [
        ("crypto_core.py", "加密备份模块：缺了备份功能直接报『缺少加密模块』"),
        ("tree_weight.py", "树权重/剪枝：缺了树打分与剪枝整块失效"),
        ("lookahead.py", "前瞻展开：缺了前瞻直接静默不生效（不报错，更难发现）"),
        ("preference_export.py", "偏好导出：缺了就再也抽不出历史偏好数据（不可追溯）"),
        ("rubric.py", "价值声明/判定：缺了 rubric 静默失效（前瞻退回启发式）"),
        ("salience.py", "记忆清晰度：缺了打包版【没有记忆筛选】，且不报错、只是行为不同"),
        ("time_scale.py", "软件时间流速：缺了打包版永远按 1 倍算，表盘怎么调都不生效"),
        ("ranker.py", "平民化训练：缺了训练按钮点了没反应"),
        ("dick_backup_tool.py", "独立解密工具：缺了加密备份就绑死在 DICK 上"),
        ("go_engine.py", "围棋规则引擎"),
        ("text_guard.py", "零宽字符防线"),
        # Tk 时代结束：ui_root/ui_fonts 随三个 Tk 插件一起退役；插件要界面走 host_ui
        ("host_ui.py", "插件向宿主要界面的通道：缺了插件的选文件/提示全失效"),
        ("jobs.py", "模块分道执行：缺了入口/插件里的 jobs.submit 全报错"),
        ("mem_isolate.py", "记忆隔离检测：记忆链插件 import 它，缺了插件加载失败"),
        ("life_core.py", "生活层（吃饭）：缺了每轮的【生活·那边】注入静默消失，/生活 命令也废"),
        ("space_core.py", "空间层（不能瞬移）：缺了每轮的【空间】注入静默消失，/在哪 命令也废"),
        ("commonsense.py", "常识库（年代→地点/交通/屋里）；缺了空间层退化成只有 家/楼下 的最小地图"),
        ("world_packs.py", "世界卡库装载：/世界包 命令会直接报错，卡包装不进 worlds/"),
        ("world_packs", "世界卡包目录：缺了 /世界包 列表为空，也没有内置世界可装"),
        ("gothic_frame.html", "哥特边框前端"),
    ]
    bad2 = 0
    for name, why in required:
        hit = glob.glob(os.path.join(BUILD, "**", name), recursive=True)
        print("   %s 随包文件 %s" % ("OK  " if hit else "FAIL", name))
        if not hit:
            bad2 += 1
            print("        → %s" % why)
    if bad2:
        fail("包内缺少 %d 个必需文件（见上）。检查 DICK_HTML.spec 的 datas。" % bad2)


def step_zip():
    print("== 5) 打 zip ==")
    os.makedirs(REL, exist_ok=True)
    # 先确认这个目录真的能写（有些环境/杀软下 Python 会 PermissionError）——
    # 与其写到一半失败，不如立刻给出可操作的提示。
    try:
        probe = os.path.join(REL, "_write_probe.tmp")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        fail("发布目录不可写：%s（%s）。用 --out 换一个目录，例如："
             "python build_release.py --out .\\_release_out" % (REL, e))
    zpath = os.path.join(REL, "DICK-电脑版.zip")
    # 先写 .part 再原子替换：Defender 实时保护会锁住"刚创建的大文件"，
    # 直接往目标路径写会随机撞 PermissionError（实测：紧跟 126 MB 播放器拷贝之后必现一次）。
    part = zpath + ".part"
    if os.path.exists(part):
        try:
            os.remove(part)
        except OSError:
            pass
    count = 0
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(BUILD):
            for fn in files:
                p = os.path.join(base, fn)
                z.write(p, os.path.relpath(p, BUILD))
                count += 1
    # 落位：目标被占用就退避重试（杀软扫描通常几秒内结束）
    last = None
    for i in range(10):
        try:
            os.replace(part, zpath)
            last = None
            break
        except OSError as e:
            last = e
            time.sleep(1.5)
    if last is not None:
        fail("zip 落位失败（目标被占用）：%s —— 关掉正在读这个 zip 的程序/杀软再试。" % last)
    size = os.path.getsize(zpath) / 1048576.0
    print("   %s" % zpath)
    print("   文件数 %d ／ %.1f MB" % (count, size))

    # 抽查 zip 里关键文件在不在
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
    checks = [
        "DICK-HTML.exe",
        "_internal/web/index.html",
        "tavern-installer/install.js",
        "tavern-installer/start.bat",
    ]
    # 播放器打进去了就一起查（位置必须和运行时 _find_player_dir 对得上）
    player_rel = "播放器/DICK-Narrative.exe"
    if any(n.startswith("播放器/") for n in names):
        checks.append(player_rel)
        checks.append("播放器/runtime/bin/server/jvm.dll")
    for need in checks:
        print("   %s %s" % ("OK  " if need in names else "FAIL", need))
    return zpath, size


def step_report():
    print("== 6) 发布目录 ==")
    if not os.path.isdir(REL):
        return
    # 手机版：安卓是原生 Compose 应用，不打包 web/，所以只跟安卓源码比时间
    and_src = os.path.join(ROOT, "DICK-Android", "app", "src")
    newest = 0.0
    for base, _d, files in os.walk(and_src):
        for fn in files:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(base, fn)))
            except OSError:
                pass
    for f in sorted(os.listdir(REL)):
        p = os.path.join(REL, f)
        if not os.path.isfile(p):
            continue
        mt = os.path.getmtime(p)
        print("   %s  %.2f MB  （%s）" % (f, os.path.getsize(p) / 1048576.0,
                                          time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))))
        if f.lower().endswith(".apk") and newest and mt < newest:
            print("      ⚠ 安卓源码比这个 apk 新，可能要重建："
                  "gradle :app:assembleDebug（在 DICK-Android 下）")
    if os.path.isfile(os.path.join(ROOT, "web", "index.html")):
        print("   提示：网页前端改动只影响电脑版，安卓端不打包 web/，无需重建 apk。")


def step_scrub():
    """打 zip 前，把「开发者的运行时状态 / 个人数据 / 日志」从包里剔掉。

    为什么必须做（都是真事）：
      · 顶层 config.json 是上一次在打包目录里跑出来的运行状态。它带着
        welcome_shown=true —— 随包发出去，**每个下载者都会跳过首次启动的欢迎页与填 Key 引导**，
        等于把 README 里写的「首次启动弹欢迎页」当场作废。
      · _internal/config.json 是 spec 把工程根目录的 config.json 当"种子"烘进包的。
        现在它恰好是空 Key，但**只要开发者哪天填了 Key 再打包，Key 就进了公开包**。
        应用缺 config.json 是安全的（self.config = {} 起步，relay_url 另有 BUILTIN_RELAY 兜底），
        所以这里直接剔除，首启由程序自己生成。
      · saves/.trpg_lock.json 是跑团锁的运行时状态：随包发出去，新装用户一开就是"已锁定"。
      · saves/backup/ 是 save_guard 给开发者自己的存档留的自动备份快照（实测里面躺着 42 个
        测试卡的旧快照），属于开发痕迹，不该进发布包；目录会在运行时按需重建。
      · 其余是个人数据（工坊配置里的 api_key / 生图预设 / 记忆归档 / 导出物）与开发日志。

    ⚠ 注意 financial_history.json 只剔除【顶层】那一份 —— 它是开发者在打包目录里跑过一次后
      留下的副本。包内 _internal/financial_history.json 是【必须留】的功能数据：
      plugins/financial_plugin.py 的 _seed_history() 会从 _MEIPASS 读它，把金融史年表
      1617-2026 播种进政策库；删了它，新装用户的年表就没了（而且不报错，只是静默少功能）。
    """
    print("== 4.5) 剔除开发者状态与个人数据（别随发布包发出去）==")
    targets = [
        "config.json", "_internal/config.json",
        "workshop_config.json", "_internal/workshop_config.json",
        "image_presets.json",
        "financial_history.json",          # 只删顶层那份；包内的年表种子必须留（见上面的 ⚠）
        "debug.log", "_internal/debug.log",
        "saves/.trpg_lock.json", "_internal/saves/.trpg_lock.json",
        # 运行时设置：开发者在本机跑打包版时会写进包里（时间流速 / 生活层的年代口味忌口）。
        # 它们和 config.json 一类：属于"我这台机器的状态"，不该随包发出去 ——
        # 否则下载者一开就是开发者调过的倍率与忌口（而且他不知道为什么）。
        "time_scale.json", "_internal/time_scale.json",
        "life_config.json", "_internal/life_config.json",
    ]
    dirs = ["memory", "exports", "_internal/memory", "_internal/exports",
            "saves/backup", "_internal/saves/backup"]
    removed = 0
    for rel in targets:
        p = os.path.join(BUILD, rel)
        if os.path.isfile(p):
            os.remove(p)
            print("   - %s" % rel)
            removed += 1
    for rel in dirs:
        p = os.path.join(BUILD, rel)
        if os.path.isdir(p) and os.listdir(p):
            shutil.rmtree(p, ignore_errors=True)
            print("   - %s/ （整目录）" % rel)
            removed += 1
    if not removed:
        print("   （没有需要剔除的，包是干净的）")
    return removed


def main():
    global REL
    argv = sys.argv[1:]
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 < len(argv):
            REL = os.path.abspath(argv[i + 1])
            print("发布目录（--out）：%s" % REL)
        else:
            fail("--out 后面要跟目录")
    do_build = "--build" in argv
    if not os.path.isdir(ROOT):
        fail("找不到工程目录")
    if not os.path.isdir(BUILD) and not do_build:
        fail("没有 dist/DICK-HTML。先跑 python build_release.py --build")
    if do_build:
        step_build()
    step_postprocess()
    step_bundle_player()
    step_selfcheck()
    step_scrub()
    zpath, size = step_zip()
    step_report()
    print("")
    print("✅ 打包完成：%s（%.1f MB）" % (zpath, size))


if __name__ == "__main__":
    main()


