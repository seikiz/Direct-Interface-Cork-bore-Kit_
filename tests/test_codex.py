# -*- coding: utf-8 -*-
"""CODEX 核心测试：剧本校验 / 模板 / 文件夹归类 / zip 往返 / 示例包资源。
运行：python tests/test_codex.py"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import codex_core

ok = 0
bad = 0
def check(c, m):
    global ok, bad
    if c:
        ok += 1
        print("  OK " + m)
    else:
        bad += 1
        print("  FAIL " + m)

print("== ① 剧本校验 ==")
tpl = codex_core.make_template("测试")
v, issues = codex_core.validate_codex(tpl)
check(v and not issues, "模板剧本校验通过")
bad_sc = {"name": "x", "scenes": [{"id": "s1", "lines": [{"jump": "s99"}]}]}
v2, iss2 = codex_core.validate_codex(bad_sc)
check(not v2 and any("s99" in i for i in iss2), "悬空 jump 拦截")
dup = {"name": "x", "scenes": [{"id": "a", "lines": [{"text": "1"}]}, {"id": "a", "lines": [{"text": "2"}]}]}
v3, iss3 = codex_core.validate_codex(dup)
check(not v3 and any("重复" in i for i in iss3), "重复 id 拦截")
no_scene = {"name": "x"}
v4, iss4 = codex_core.validate_codex(no_scene)
check(not v4, "缺 scenes 拦截")

print("== ② 资源归类 ==")
check(codex_core.classify_file("saki_normal.png") == "sprites", "png → sprites")
check(codex_core.classify_file("bg_classroom.png") == "bg", "bg 前缀 → bg")
check(codex_core.classify_file("theme.mp3") == "bgm", "theme → bgm")
check(codex_core.classify_file("voice_01.wav") == "voice", "voice 前缀 → voice")
check(codex_core.classify_file("readme.txt") is None, "未知类型 → None")

print("== ③ 文件夹导入归类 ==")
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "立绘"), exist_ok=True)
os.makedirs(os.path.join(tmp, "bg"), exist_ok=True)
open(os.path.join(tmp, "立绘", "a.png"), "w").write("x")
open(os.path.join(tmp, "bg", "room.png"), "w").write("x")
open(os.path.join(tmp, "song.mp3"), "w").write("x")
dest = tempfile.mkdtemp()
r = codex_core.import_folder(tmp, dest, "导入包")
check(r["ok"] and r["moved"]["sprites"] == 1 and r["moved"]["bg"] == 1 and r["moved"]["bgm"] == 1,
      "导入归类: %r" % r["moved"])
pkg = os.path.join(dest, "导入包")
check(os.path.isfile(os.path.join(pkg, "codex.json")), "自动生成剧本")
sc = json.load(open(os.path.join(pkg, "codex.json"), encoding="utf-8"))
check(sc["scenes"][0]["lines"][1].get("sprite", "").startswith("sprites/"), "剧本引用实际立绘: %s" % sc["scenes"][0]["lines"][1].get("sprite"))

print("== ④ zip 往返 ==")
zip_path = os.path.join(tmp, "pkg.zip")
check(codex_core.export_zip(pkg, zip_path), "导出 zip")
dest2 = tempfile.mkdtemp()
zok, zname, zmsg = codex_core.import_zip(zip_path, dest2)
check(zok and os.path.isdir(os.path.join(dest2, zname)), "导入 zip: %s %s" % (zname, zmsg))
check(os.path.isfile(os.path.join(dest2, zname, "codex.json")), "zip 含剧本")

print("== ⑤ 一键示例包 ==")
dest3 = tempfile.mkdtemp()
sok, spkg = codex_core.make_sample_package(dest3, "示例·夏日祭")
check(sok, "示例包生成")
for k in codex_core.SUBDIRS:
    d = os.path.join(spkg, k)
    check(os.path.isdir(d) and os.listdir(d), "示例包资源目录 %s 非空" % k)
png = os.path.join(spkg, "sprites", "咲_立绘.png")
check(os.path.isfile(png) and open(png, "rb").read(8) == b"\x89PNG\r\n\x1a\n", "立绘为合法 PNG")
wav = os.path.join(spkg, "bgm", "主题曲.wav")
check(os.path.isfile(wav) and open(wav, "rb").read(4) == b"RIFF", "音乐为合法 WAV")
sc = json.load(open(os.path.join(spkg, "codex.json"), encoding="utf-8"))
sv, si = codex_core.validate_codex(sc)
check(sv, "示例剧本校验通过")

print("== ⑥ 立绘多位置校验 ==")
multi = {"name": "x", "scenes": [{"id": "s1", "lines": [
    {"text": "a", "sprites": [{"file": "sprites/a.png", "pos": "left"},
                              {"file": "sprites/b.png", "pos": "right"}]},
    {"text": "b", "sprite": "sprites/c.png", "pos": "right"},
]}]}
mv, mi = codex_core.validate_codex(multi)
check(mv and not mi, "多立绘 + 单立绘 pos 校验通过")
bad_pos = {"name": "x", "scenes": [{"id": "s1", "lines": [
    {"text": "a", "sprites": [{"file": "sprites/a.png", "pos": "top"}]}]}]}
bv, bi = codex_core.validate_codex(bad_pos)
check(not bv and any("pos" in i for i in bi), "非法 pos 拦截")

print("== ⑦ 打包：自包含单文件 GALGAME ==")
out_html = os.path.join(dest3, "packed.html")
pok, ppath, pcounts = codex_core.build_standalone_file(spkg, out_html)
check(pok and os.path.isfile(ppath) and os.path.getsize(ppath) > 10000, "打包单文件 HTML 生成")
html = open(ppath, encoding="utf-8").read()
check("data:image/png" in html and "data:audio/wav" in html, "资源全部 base64 内嵌")
check("cxStartScene" in html and "cxNextLine" in html and "cxShowChoice" in html, "独立播放器 JS 完整")
check("cxSetSprites" in html and "cxSpriteCss" in html, "独立播放器支持立绘多位置")
check(html.count("<script>") == 1, "剧本含 </script> 不破坏 HTML 结构")
# 剧本里塞 </script> 验证转义
sc["scenes"][0]["lines"].insert(0, {"speaker": "咲", "text": "</script><script>alert(1)</script>"})
json.dump(sc, open(os.path.join(spkg, "codex.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
pok2, ppath2, _ = codex_core.build_standalone_file(spkg, os.path.join(dest3, "packed2.html"))
html2 = open(ppath2, encoding="utf-8").read()
check(pok2 and html2.count("<script>") == 1, "XSS 剧本转义后不截断 script")
check("cxNextLine" in html2, "转义后播放器 JS 仍完整")

print("== ⑧ EXE 打包壳（shell 生成 + PyInstaller 命令） ==")
import py_compile
shell = codex_core.build_exe_shell("<html>测试</html>", "测试游戏")
check("__HTML_B64__" not in shell and "import webview" in shell, "壳脚本生成（HTML base64 内嵌）")
sp = os.path.join(dest3, "codex_shell_check.py")
open(sp, "w", encoding="utf-8").write(shell)
try:
    py_compile.compile(sp, doraise=True)
    check(True, "壳脚本语法 OK")
except Exception:
    check(False, "壳脚本语法 OK")
cmd = codex_core.pyinstaller_cmd("x.py", "out", "我的游戏")
check("--onefile" in cmd and "--windowed" in cmd and "webview" in cmd and "--hidden-import" in cmd,
      "PyInstaller 命令含 onefile/windowed/webview 依赖")

shutil.rmtree(tmp)
shutil.rmtree(dest)
shutil.rmtree(dest2)
shutil.rmtree(dest3)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
