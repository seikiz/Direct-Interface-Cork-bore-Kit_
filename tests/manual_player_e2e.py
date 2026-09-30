# -*- coding: utf-8 -*-
"""手动端到端验证：真实包 → 导出 → 真的启动 EXE（不进 CI，因为要 127MB 拷贝 + 会弹窗口）
运行：python tests/manual_player_e2e.py [包名]

做的事：
  1. 把 DICK-HTML/codex 下的某个真实包复制到工程 codex/ 下
  2. 用真实的构建产物（DICK-Narrative.exe）跑一次导出
  3. 检查产物结构
  4. 启动导出的 exe，确认窗口标题 = 故事名（说明它真的读到了故事包）
"""
import sys, os, json, time, shutil, subprocess

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import html_app
html_app.BASE_DIR = ROOT

PKG_NAME = sys.argv[1] if len(sys.argv) > 1 else "我的故事"

app = html_app.HtmlApp()
player = app._find_player_dir()
print("播放器目录：", player)
if not player:
    print("没有构建好的播放器。先在 DICK-Narrative 跑 build.ps1 -Exe")
    sys.exit(2)

# 1) 找<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一个真实包
src = None
for cand in (os.path.join(ROOT, "dist", "DICK-HTML", "codex", PKG_NAME),
             os.path.join(ROOT, "codex", PKG_NAME)):
    if os.path.isfile(os.path.join(cand, "codex.json")):
        src = cand
        break
if not src:
    print("找不到真实包：", PKG_NAME)
    sys.exit(2)

dst_pkg = app._codex_pkg_path(PKG_NAME)
if os.path.normcase(src) != os.path.normcase(dst_pkg):
    if os.path.isdir(dst_pkg):
        shutil.rmtree(dst_pkg, ignore_errors=True)
    shutil.copytree(src, dst_pkg)
print("真实包：", dst_pkg)

data = json.load(open(os.path.join(dst_pkg, "codex.json"), encoding="utf-8"))
print("故事名：", data.get("name"), " 线数：", len(data.get("scenes") or []))

# 2) 导出（跳过对话框 → 落到默认位置）
DEST = os.path.join(ROOT, "codex", "_player_export", PKG_NAME)
STATE = os.path.join(dst_pkg, "dist", ".player_build_state.json")
os.makedirs(os.path.dirname(STATE), exist_ok=True)
t0 = time.time()
app._codex_player_worker(PKG_NAME, player, DEST, STATE)
print("导出耗时：%.1f 秒" % (time.time() - t0))

st = json.load(open(STATE, encoding="utf-8"))
print("状态：", st.get("state"), st.get("msg"), "体积：", st.get("size"), "MB")
print("素材：", st.get("counts"))
assert st.get("state") == "done", "导出失败"

# 3) 结构检查
need = ["DICK-Narrative.exe", "玩这个.txt",
        os.path.join("story", "codex.json")]
for n in need:
    p = os.path.join(DEST, n)
    print(("  OK   " if os.path.exists(p) else "  FAIL ") + n)
    assert os.path.exists(p), n
for kind in ("sprites", "bg", "bgm", "voice"):
    d = os.path.join(DEST, "story", kind)
    n = len(os.listdir(d)) if os.path.isdir(d) else 0
    print("  OK   story/%s/  %d 个文件" % (kind, n))

# 4) 真的启动
exe = os.path.join(DEST, "DICK-Narrative.exe")
print("\n启动：", exe)
proc = subprocess.Popen([exe], cwd=DEST)

want = str(data.get("name") or "")
titles = []


def visible_titles():
    """枚举所有可见窗口标题。
    注意：jpackage 生成的 DICK-Narrative.exe 只是个启动器，真正的窗口属于它拉起来的
    子进程，pid 和 Popen 拿到的不是同一个，所以这里不能按 pid 过滤。"""
    import ctypes
    from ctypes import wintypes
    out = []
    EnumWindows = ctypes.windll.user32.EnumWindows
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible

    def cb(hwnd, _):
        if IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buf, 512)
            if buf.value.strip():
                out.append(buf.value)
        return True

    EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(cb), 0)
    return out


deadline = time.time() + 30
while time.time() < deadline:
    if proc.poll() is not None:
        break
    titles = visible_titles()
    if any(want and want in t for t in titles):
        break
    time.sleep(2)

alive = proc.poll() is None
print("进程还活着：", alive)
found = [t for t in titles if want and want in t]
print("匹配到《%s》的窗口：%s" % (want, found))

if not alive:
    print("\n❌ 播放器没起来")
    sys.exit(1)
if not found:
    print("\n❌ 播放器起来了，但没读到故事包（窗口标题里没有《%s》）" % want)
    print("   前台窗口：", [t for t in titles if "Narrative" in t or "钟楼" in t or "我的" in t])
    sys.exit(1)
print("\n✅ 端到端通过：导出的 exe 真的读到了你的故事包")
print("（窗口还开着，看完自己关掉）")
