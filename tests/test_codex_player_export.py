# -*- coding: utf-8 -*-
"""「导出到原生播放器」回归测试（不启动 GUI、不弹对话框、不依赖真的 127MB 播放器）
运行：python tests/test_codex_player_export.py

覆盖：
  ① 播放器目录探测（有/无）
  ② 导出产出的目录结构 = 播放器 + story/codex.json + 四类素材
  ③ codex.json 原样保留制作器写的线级 bg/bgm、sprites 列表、带 if 的选项
  ④ 状态文件 / 说明文件
  ⑤ api_codex_player_status 的轮询状态机
"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

TMP_ROOT = tempfile.mkdtemp(prefix="dick_player_test_")
# 数据目录再往下套两层，而不是直接用 mkdtemp 的返回值：
# `_find_player_dir()` 会往 base_dir 的**上两层**找播放器（打包版 DICK 的兜底逻辑），
# 而有些 Python 环境里 `tempfile.gettempdir()` 会退化成"当前工作目录" —— 那上两层正好是
# 工程根，于是它会找到真的构建产物，「还没构建时探测结果是 None」这条就直接红了
# （本机 venv 的 3.11 就是这样：TEMP 在它的应用程序容器里不可写 → 退化成 cwd）。
TMP = os.path.join(TMP_ROOT, "inner", "data")
os.makedirs(TMP, exist_ok=True)

import html_app
html_app.BASE_DIR = TMP          # 数据目录重定向到临时目录

ok = 0
bad = 0


def check(cond, msg):
    global ok, bad
    if cond:
        ok += 1
        print("  OK   " + msg)
    else:
        bad += 1
        print("  FAIL " + msg)


def write(path, data, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if binary else "w"
    kw = {} if binary else {"encoding": "utf-8"}
    with open(path, mode, **kw) as f:
        f.write(data)


app = html_app.HtmlApp()
NAME = "钟楼之下"
PKG = app._codex_pkg_path(NAME)

print("== ① 播放器目录探测 ==")
check(app._find_player_dir() is None, "还没构建时探测结果是 None")
ready = app.api_codex_player_ready()
check(ready["ok"] is True and ready["ready"] is False, "player_ready 报未就绪")

# 造一个「假播放器」放在约定的探测路<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌径上（省掉 127MB 真实拷贝）
PLAYER = os.path.join(TMP, "DICK-Narrative", "app", "build", "compose",
                      "binaries", "main", "app", "DICK-Narrative")
write(os.path.join(PLAYER, "DICK-Narrative.exe"), b"MZ-fake", binary=True)
write(os.path.join(PLAYER, "app", "app.jar"), b"jar" * 40, binary=True)
write(os.path.join(PLAYER, "runtime", "bin", "server", "jvm.dll"), b"dll" * 60, binary=True)

check(app._find_player_dir() == PLAYER, "构建好之后能探测到播放器目录")
check(app.api_codex_player_ready()["ready"] is True, "player_ready 报已就绪")

print("== ①b 打包版 DICK 也要能找到播放器 ==")
# 打包版的数据目录是 <根>/DICK-HTML，播放器在 <根>/DICK-Narrative/...
# （这个真踩过：只往上一层找，打包版就找不到，按钮会误报「还没构建」）
import app_paths
_real_base = app_paths.get_base_dir
packed_base = os.path.join(TMP, "DICK-HTML")
os.makedirs(packed_base, exist_ok=True)
app_paths.get_base_dir = (lambda v: (lambda: v))(packed_base)
packed_app = html_app.HtmlApp()
check(packed_app.base_dir == packed_base, "打包版 base_dir 模拟正确")
check(packed_app._find_player_dir() == PLAYER, "打包版（子目录）也能找到播放器")
app_paths.get_base_dir = _real_base

print("== ② 造一个「制作器风格」的包 ==")
script = {
    "codex": 1,
    "name": NAME,
    "author": "",
    "intro": "测试用",
    "roles": [{"name": "薇拉", "sprite": "sprites/vera.png", "voice": "voice/vera_01.mp3"}],
    "scenes": [
        {
            "id": "s1", "title": "序章 · 门厅",
            "bg": "bg/hall.png", "bgm": "bgm/theme.mp3",
            "next": "s2",
            "lines": [
                {"kind": "say", "speaker": "薇拉", "text": "你来了。",
                 "sprites": [{"file": "sprites/vera.png"}]},
                {"kind": "choice", "choice": [
                    {"text": "行礼", "goto": "s2"},
                    {"text": "沉默", "if": {"aff": ">=90"}},
                ]},
            ],
        },
        {"id": "s2", "title": "终章", "bg": "bg/tower.png",
         "lines": [{"kind": "end", "end": "完"}]},
    ],
}
write(os.path.join(PKG, "codex.json"), json.dumps(script, ensure_ascii=False, indent=2))
write(os.path.join(PKG, "sprites", "vera.png"), b"png", binary=True)
write(os.path.join(PKG, "bg", "hall.png"), b"png", binary=True)
write(os.path.join(PKG, "bgm", "theme.mp3"), b"mp3", binary=True)
write(os.path.join(PKG, "voice", "vera_01.mp3"), b"mp3", binary=True)

check(os.path.isfile(os.path.join(PKG, "codex.json")), "测试包已就位")

print("== ③ 跑导出 worker（跳过文件夹对话框）==")
DEST = os.path.join(TMP, "导出到这儿", NAME)
STATE = os.path.join(PKG, "dist", ".player_build_state.json")
os.makedirs(os.path.dirname(STATE), exist_ok=True)
# 播放器自带一份示例故事 → 导出时必须被清掉，否则会和用户的故事打架
write(os.path.join(PLAYER, "story", "story.json"), '{"name":"内置示例","scenes":[]}')
app._codex_player_worker(NAME, PLAYER, DEST, STATE)

st = json.load(open(STATE, encoding="utf-8"))
check(st.get("state") == "done", "状态文件 = done（%s）" % st.get("msg"))

check(not os.path.exists(os.path.join(DEST, "story", "story.json")),
      "播放器自带的示例故事被清掉了（不会和用户的故事打架）")

check(os.path.isfile(os.path.join(DEST, "DICK-Narrative.exe")), "播放器 exe 已就位")
check(os.path.isfile(os.path.join(DEST, "runtime", "bin", "server", "jvm.dll")),
      "播放器运行时目录整体拷过来了")
check(os.path.isfile(os.path.join(DEST, "app", "app.jar")), "播放器 app 目录已就位")
check(os.path.isfile(os.path.join(DEST, "story", "codex.json")), "故事放在 story/codex.json")
check(os.path.isfile(os.path.join(DEST, "玩这个.txt")), "附了「玩这个.txt」说明")

counts = st.get("counts") or {}
check(counts.get("sprites") == 1 and counts.get("bg") == 1
      and counts.get("bgm") == 1 and counts.get("voice") == 1,
      "四类素材都拷到了：%s" % counts)

print("== ④ 导出的 codex.json 必须保留制作器写的结构 ==")
data = json.load(open(os.path.join(DEST, "story", "codex.json"), encoding="utf-8"))
sc1 = (data.get("scenes") or [{}])[0]
check(sc1.get("bg") == "bg/hall.png", "线级背景 bg 保留（Kotlin 引擎靠它切背景）")
check(sc1.get("bgm") == "bgm/theme.mp3", "线级音乐 bgm 保留")
check(sc1.get("next") == "s2", "线出口 next 保留")
steps = sc1.get("lines") or []
check(steps and isinstance(steps[0].get("sprites"), list)
      and steps[0]["sprites"][0].get("file") == "sprites/vera.png",
      "多立绘 sprites 列表保留")
check(steps[1].get("choice")[1].get("if") == {"aff": ">=90"},
      "选项的 if 条件保留（数值分支）")
check((data.get("roles") or [{}])[0].get("name") == "薇拉", "角色实体保留")

print("== ⑤ 状态查询接口 ==")
s = app.api_codex_player_status(NAME)
check(s.get("ok") is True and s.get("state") == "done", "player_status 能读到 done")
check(app.api_codex_player_status("不存在的包").get("state") == "idle",
      "没导出过的包状态是 idle")

print("== ⑥ 重复导出要能覆盖旧结果 ==")
write(os.path.join(DEST, "旧文件.txt"), "x")
app._codex_player_worker(NAME, PLAYER, DEST, STATE)
check(not os.path.exists(os.path.join(DEST, "旧文件.txt")),
      "再次导出会重建目录（不留上次的残留）")
check(os.path.isfile(os.path.join(DEST, "story", "codex.json")), "重建后故事仍在")

shutil.rmtree(TMP_ROOT, ignore_errors=True)
print("")
print("通过 %d 项，失败 %d 项" % (ok, bad))
sys.exit(1 if bad else 0)
