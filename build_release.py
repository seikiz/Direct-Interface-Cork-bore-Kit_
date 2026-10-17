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
    # 2026-10 图标换 Material Symbols：前端必须引用随包字体与生成的图标名表，
    # 否则图标全变空白/豆腐块（字体没随包时最典型）
    "图标·随包字体": "fonts/MaterialSymbolsOutlined.woff2",
    "图标·名字表脚本": "icons.js",
    "图标·字体渲染样式": ".ms{",
    # 2026-12 工坊卡片外显：预览改成结构化卡片（字段表 = design/card_fields.json →
    # web/card_fields.js）。这两串缺任一，打进去的就是旧前端（还在把整份 JSON 当代码显示）。
    "工坊·卡片字段表": "DICK_CARD_FIELDS",
    "工坊·结构化预览样式": "ws-cardview",
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
    # 说明不再单独生成 txt（用户要求：发布目录里别放这种零散说明文件）。
    # 需要的话看 README / 说明书；旧的残留文件顺手清掉，免得打进包里。
    note = os.path.join(BUILD, "备份怎么打开.txt")
    if os.path.isfile(note):
        try:
            os.remove(note)
            print("   已移除遗留的「备份怎么打开.txt」")
        except OSError as e:
            print("   （旧说明文件删不掉：%s）" % e)


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

    # 2026-11 阶段1：页面里的 <style> 已原样拆到 web/styles/ 并按层叠顺序 link 进来。
    # 所以"前端有没有这个特征串"要看 页面 + 拆出去的样式 两边，
    # 而且样式文件是不是真的随包了，本身就是必须查的一项（缺了整个界面会裸奔）。
    style_dir = os.path.join(BUILD, "_internal", "web", "styles")
    css = ""
    if os.path.isdir(style_dir):
        for fn in sorted(os.listdir(style_dir)):
            if fn.endswith(".css"):
                with open(os.path.join(style_dir, fn), encoding="utf-8") as f:
                    css += "\n" + f.read()
    else:
        fail("包里没有 _internal/web/styles/（样式抽取后前端必须带上这个目录）")
    # 2026-11 阶段2：一屏的 DOM/JS 搬到了 web/screens/*.html 与 web/js/screens/*.js，
    # 特征串可能已经不在 index.html 里了 —— 所以"前端"= 页面 + 样式 + 屏片段 + 屏模块。
    # 这几块缺任何一块，界面上的对应屏/样式就是死的（页面能开，但那几屏点不开）。
    parts = [bundled, css]
    for sub in (("web", "screens"), ("web", "js")):
        d = os.path.join(BUILD, "_internal", *sub)
        if not os.path.isdir(d):
            fail("包里没有 _internal/%s/（阶段2 起屏的片段与模块必须随包）" % "/".join(sub))
        for base, _dirs, files in os.walk(d):
            for fn in sorted(files):
                if fn.endswith((".html", ".js")):
                    with open(os.path.join(base, fn), encoding="utf-8") as f:
                        parts.append(f.read())
    front = "\n".join(parts)

    bad = 0
    for name, needle in FEATURES.items():
        hit = needle in front
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
        ("world_memory.py", "世界记忆演化：缺了每轮的【世界·演化】注入静默消失，/世界记忆 命令也废"),
        ("world_packs", "世界卡包目录：缺了 /世界包 列表为空，也没有内置世界可装"),
        ("app_version.py", "版号读取：缺了窗口标题/欢迎语退回兜底版号（与 version.json 不一致）"),
        ("version.json", "版号的唯一真相：缺了 app_version 读不到号"),
        ("web/icons.js", "图标名字表（由 icons/icons.json 生成）：缺了界面上的 emoji 一个都换不成图标"),
        ("web/card_fields.js", "卡片外显字段表（由 design/card_fields.json 生成）：缺了工坊预览退回原文"),
        ("web/styles", "样式已抽到 web/styles/（阶段1）：缺了整个界面没有任何自定义样式，等于裸 HTML"),
        ("web/screens", "屏的 DOM 片段（阶段2）：缺了围棋/生图/裁剪/表盘/编辑消息这几屏的界面直接不出现"),
        ("web/js/screens", "屏的 JS 模块（阶段2）：缺了上面几屏的按钮全是死的（有界面没行为）"),
        ("web/js/state.js", "屏之间的状态总线（阶段2）：缺了 5 个屏模块加载时就报错"),
        ("web/fonts/MaterialSymbolsOutlined.woff2", "Material Symbols 字体（随包，不连 CDN）：缺了图标全变空白/豆腐块"),
        ("web/fonts/LICENSE", "字体许可（Apache-2.0）：随包分发必须带"),
        ("strings.json", "界面文案唯一真相（lang/strings.json）：缺了三语全部退回中文"),
        ("i18n.js", "生成的界面文案表（web/i18n.js）：缺了三语全部退回中文"),
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
    # 阶段2：屏片段/屏模块必须真的进包（web 是整目录递归收的，但 datas 一旦被改坏就会漏）。
    frags = [n for n in names if n.startswith("_internal/web/screens/") and n.endswith(".html")]
    mods = [n for n in names
            if n.startswith("_internal/web/js/screens/") and n.endswith(".js")]
    print("   %s 屏片段 %d 个 ／ 屏模块 %d 个 随包"
          % ("OK  " if (len(frags) >= 5 and len(mods) >= 5) else "FAIL", len(frags), len(mods)))
    if len(frags) < 5 or len(mods) < 5:
        fail("包里的屏片段/屏模块不够（片段 %d、模块 %d）：检查 DICK_HTML.spec 的 datas "
             "是否还收着整个 web/ 目录" % (len(frags), len(mods)))
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
    if "--tag" in argv:
        step_tag()
    print("")
    print("✅ 打包完成：%s（%.1f MB）" % (zpath, size))


def step_tag():
    """按版号打发布 tag（`--tag`）。

    纪律（用户定调）：**发布 tag 一律用版号**（`v1.0.0.1`），不用"代"（`v2.0`）——
    那个名字还与"下一个不兼容纪元 2.0.0.0"撞号。tag 名与提交信息都从 version.json 取，
    所以不存在"手打错一个数字"这种事。**只打本地 tag，不自动推** —— 推是发布动作，
    由人确认（推的命令会打出来）。
    """
    import subprocess
    try:
        import app_version
    except Exception as e:
        print("  [warn] 读不到版号（%s），跳过打 tag" % e)
        return
    name = "v" + app_version.VERSION
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        print("  [warn] 不是 git 仓库，跳过打 tag")
        return
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if dirty.returncode == 0 and dirty.stdout.strip():
        print("  [warn] 工作区不干净，跳过打 tag（发布 tag 要打在干净的提交上）")
        return
    have = subprocess.run(["git", "tag", "-l", name], cwd=ROOT,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if have.returncode == 0 and have.stdout.strip():
        print("  [ok] tag %s 已存在（不重复打）" % name)
        return
    done = subprocess.run(["git", "tag", "-a", name, "-m",
                           "DICK %s（兼容线 %s）" % (name, app_version.compat_line())],
                          cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode == 0:
        print("  [ok] 已打 tag %s —— 推它：git push origin %s" % (name, name))
    else:
        print("  [warn] 打 tag 失败：%s" % done.stdout.decode("utf-8", "replace").strip()[:120])


if __name__ == "__main__":
    main()


