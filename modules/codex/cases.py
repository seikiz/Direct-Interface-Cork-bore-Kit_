# -*- coding: utf-8 -*-
"""modules/codex/cases.py —— codex 的全部自检 case + CASES 登记表

覆盖：剧本语法解析（含坏输入）/ 行类型 / 条件求值 / 选项裁剪 / HTML 消毒 / 校验 /
静态分析 / 全路径模拟与单路径走查 / 包布局与占位素材 / zip 往返 / 单文件 HTML 导出 /
模板注入点 / 水印注入 / EXE 壳与 PyInstaller 命令 / 宿主绑定。
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
from . import pack as pack_mod
from .service import CodexService
from .harness import FakeHost, FakeMark, PNG_STUB, SCRIPT_TEXT, WAV_STUB, _contains, _eq, _fixture, _svc, _tmpdir, _true
import types  # CASES 只读视图（十一：块里不许有模块级可变全局）


def case_classify_file():
    svc = _svc()
    _eq(svc.classify_file("saki_normal.png"), "sprites", "png → sprites")
    _eq(svc.classify_file("bg_classroom.png"), "bg", "bg 前缀 → bg")
    _eq(svc.classify_file("theme.mp3"), "bgm", "theme → bgm")
    _eq(svc.classify_file("voice_01.wav"), "voice", "voice 前缀 → voice")
    _eq(svc.classify_file("readme.txt"), None, "未知类型 → None")
    _eq(svc.classify_file("sprites/咲_立绘.png"), "sprites", "带目录的相对路径也认")
    _eq(svc.classify_file(""), None, "坏输入：空文件名 → None")

def case_parse_script_text():
    svc = _svc()
    got = svc.parse_script_text(SCRIPT_TEXT, "手写")
    _eq(got["codex"], svc.CODEX_VERSION, "格式版本要写进包")
    _eq(got["name"], "手写", "剧本名透传")
    _eq(len(got["scenes"]), 1, "一个场景")
    sc = got["scenes"][0]
    _eq(sc["bg"], "bg/教室.png", "背景行")
    _eq(sc["bgm"], "bgm/theme.mp3", "音乐行")
    _eq([svc.step_kind(ln) for ln in sc["lines"]], ["note", "say", "choice"], "解析出来的行类型")
    _eq(sc["lines"][1]["speaker"], "咲", "说话人")
    _eq([c["goto"] for c in sc["lines"][2]["choice"]], ["s2", "s3"], "选项目标")

def case_parse_bad_input():
    svc = _svc()
    _eq(svc.parse_script_text(""), None, "坏输入：空文本 → None")
    _eq(svc.parse_script_text("   \n\n "), None, "坏输入：全空白 → None")
    _eq(svc.parse_script_text(None), None, "坏输入：非字符串 → None")

def case_step_kind():
    svc = _svc()
    table = [({"text": "你好"}, "say"), ({"kind": "show", "sprite": "x.png"}, "show"),
             ({"choice": [{"text": "a", "goto": "s2"}]}, "choice"), ({"jump": "s2"}, "jump"),
             ({"bg": "x.png", "text": "hi"}, "say"), ({"kind": "wait", "ms": 500}, "wait")]
    bad = [(ln, svc.step_kind(ln), want) for ln, want in table if svc.step_kind(ln) != want]
    _eq(bad, [], "行类型")

def case_evaluate_condition():
    svc = _svc()
    state = {"aff": 90, "flags": ["met"], "status": {"心情": "开心"}}
    true_cases = [{"aff": ">=85"}, {"aff": 90}, {"status": {"心情": "开心"}},
                  {"flags": ["met"]}, {"flags": ["!told"]},
                  {"all": [{"aff": ">=80"}, {"status": {"心情": "开心"}}]},
                  {"any": [{"aff": ">=99"}, {"status": {"心情": "开心"}}]},
                  None]
    false_cases = [{"aff": ">=95"}, {"aff": 91}, {"status": {"心情": "难过"}},
                   {"flags": ["told"]}]
    bad = [c for c in true_cases if not svc.evaluate_condition(state, c)]
    bad += [c for c in false_cases if svc.evaluate_condition(state, c)]
    _eq(bad, [], "条件求值")
    _eq(svc.evaluate_condition(None, {"aff": ">=85"}), True, "无状态=作者预览恒真")
    _eq(svc.evaluate_condition({}, {"flags": ["met"]}), False, "空状态缺 flags 不命中")

def case_filter_choices():
    svc = _svc()
    items = [{"text": "a"}, {"text": "b", "if": {"aff": ">=85"}}, {"text": "c"}]
    _eq(len(svc.filter_choices(items, {"aff": 90})), 3, "条件满足时全留")
    _eq([i["text"] for i in svc.filter_choices(items, {"aff": 10})], ["a", "c"],
        "条件不满足的要裁掉")
    _eq(len(svc.filter_choices(items, None)), 3, "预览模式（无状态）不裁剪")
    _eq(svc.filter_choices("不是列表", None), "不是列表", "坏输入：非列表原样返回")

def case_sanitize_html():
    svc = _svc()
    got = svc.sanitize_html('<p onclick="x()">a<script>bad()</script>'
                            '<iframe src=1></iframe>javascript:alert(1)</p>')
    _eq(got, "<p>ablocked:alert(1)</p>", "消毒结果")
    _true("<script" not in got and "<iframe" not in got, "危险标签必须去掉")
    _true("onclick" not in got, "事件属性必须去掉")
    _eq(svc.sanitize_html(None), "", "坏输入：非字符串 → 空串")

def case_validate_codex():
    svc = _svc()
    _eq(svc.validate_codex(svc.make_template("好剧本")), (True, []), "示例模板必须合法")
    ok, issues = svc.validate_codex("不是 dict")
    _true(not ok and issues == ["剧本必须是 JSON 对象"], "坏输入：非对象")
    ok, issues = svc.validate_codex({"name": "x"})
    _true(not ok and issues, "缺 scenes 要有 issues")
    dup = {"name": "x", "scenes": [{"id": "s1", "lines": []}, {"id": "s1", "lines": []}]}
    ok, issues = svc.validate_codex(dup)
    _true(not ok and any("重复" in i or "s1" in i for i in issues), "重复场景 id：%r" % issues)
    badjump = {"name": "x", "scenes": [{"id": "s1", "lines": [{"jump": "不存在"}]}]}
    ok, issues = svc.validate_codex(badjump)
    _true(not ok and issues, "跳转到不存在的场景：%r" % issues)

def case_analyze_codex():
    tree = _tmpdir("analyze")
    try:
        svc = _svc()
        pkg = _fixture(tree)
        rep = svc.analyze_codex(svc.make_template("分析"), pkg)
        _true({"ok", "issues", "warnings", "stats", "dead_lines"} <= set(rep),
              "分析结果缺字段：%r" % sorted(rep))
        _eq(rep["stats"]["scenes"], 3, "场景统计")
        _true(rep["stats"]["words"] > 0, "字数统计要大于 0")
        _true(svc.analyze_codex("不是 dict")["issues"], "坏输入：非对象剧本要有 issues")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_simulate_and_run_path():
    svc = _svc()
    tpl = svc.make_template("模拟")
    sim = svc.simulate(tpl)
    _true(sim["ok"] and "结局：惹她生气了" in sim["endings"],
          "全路径模拟要能走到结局：%r" % sim["endings"])
    _true(sim["states"] >= 1, "可达状态数")
    got = svc.run_path(tpl, [1])
    _eq(got["stopped"], "到达结局", "按选择走一遍要到达结局")
    _eq(got["ending"], "结局：惹她生气了", "结局标题")
    _true(any("假装没听见" in s for s in got["steps"]), "轨迹里要有选择记录")
    loop = svc.run_path(tpl, [0], None, 5)          # 走 s1→s2→s1 的环
    _eq(loop["ok"], False, "死循环必须被步数上限拦住")
    _contains(loop["stopped"], "步数超限", "死循环的停止原因")

def case_placeholder_assets():
    """占位素材的**字节**要真的合法（示例包布局那个 case 把生成器换成了桩）"""
    tree = _tmpdir("placeholder")
    try:
        png = os.path.join(tree, "a.png")
        wav = os.path.join(tree, "a.wav")
        pack_mod._write_placeholder_png(png, (30, 40, 60))
        pack_mod._write_silent_wav(wav)
        with io.open(png, "rb") as f:
            raw = f.read()
        _true(raw.startswith(b"\x89PNG\r\n\x1a\n"), "占位图要带 PNG 魔数")
        _true(b"IHDR" in raw and raw.rstrip().endswith(b"\x82"), "PNG 结构要完整（IHDR…IEND）")
        _true(len(raw) > 2000, "420×720 的渐变图不该这么小（%d 字节）" % len(raw))
        with io.open(wav, "rb") as f:
            wav_bytes = f.read()
        _eq(wav_bytes[:4], b"RIFF", "静音音频要带 RIFF 头")
        _eq(wav_bytes[8:12], b"WAVE", "静音音频要带 WAVE 标记")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_sample_package_layout():
    """示例包布局：四个素材目录 + codex.json + 引用对齐（占位图/音频换成桩，理由见文件头）"""
    tree = _tmpdir("sample")
    orig_png, orig_wav = pack_mod._write_placeholder_png, pack_mod._write_silent_wav
    pack_mod._write_placeholder_png = (
        lambda path, rgb, w=420, h=720: io.open(path, "wb").write(PNG_STUB))
    pack_mod._write_silent_wav = (
        lambda path, seconds=1, rate=22050: io.open(path, "wb").write(WAV_STUB))
    try:
        svc = _svc()
        ok, pkg = svc.make_sample_package(tree, "示例·夏日祭")
        _true(ok and os.path.isdir(pkg), "示例包没造出来")
        _true(os.path.isfile(os.path.join(pkg, "codex.json")), "包里要有 codex.json")
        for sub in svc.SUBDIRS:
            _true(os.path.isdir(os.path.join(pkg, sub)), "包里要有 %s/" % sub)
        with io.open(os.path.join(pkg, "codex.json"), encoding="utf-8") as f:
            data = json.load(f)
        _eq(data["name"], "示例·夏日祭", "包名")
        _eq(svc.validate_codex(data), (True, []), "示例包必须自洽（引用都能解析）")
        sprites = os.listdir(os.path.join(pkg, "sprites"))
        _true([f for f in sprites if f.endswith(".png")], "占位立绘要落进 sprites/")
        _true(os.path.isfile(os.path.join(pkg, "voice", "01.wav")), "示例配音要落进 voice/")
    finally:
        pack_mod._write_placeholder_png, pack_mod._write_silent_wav = orig_png, orig_wav
        shutil.rmtree(tree, ignore_errors=True)

def case_import_folder():
    tree = _tmpdir("importfolder")
    try:
        src = os.path.join(tree, "src")
        os.makedirs(src, exist_ok=True)
        for fn in ("saki_normal.png", "bg_classroom.png", "theme.mp3", "readme.txt"):
            with io.open(os.path.join(src, fn), "wb") as f:
                f.write(b"x" * 32)
        dest = os.path.join(tree, "dest")
        os.makedirs(dest, exist_ok=True)
        _svc().import_folder(src, dest, "导入包")
        pkg = os.path.join(dest, "导入包")
        _true(os.path.isfile(os.path.join(pkg, "codex.json")), "导入后要有 codex.json")
        _true(os.path.isfile(os.path.join(pkg, "sprites", "saki_normal.png")),
              "立绘要按类型落到 sprites/")
        _true(os.path.isfile(os.path.join(pkg, "bg", "bg_classroom.png")),
              "背景要按类型落到 bg/")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_zip_roundtrip():
    tree = _tmpdir("zip")
    try:
        svc = _svc()
        pkg = _fixture(tree)
        zpath = os.path.join(tree, "out.zip")
        _true(svc.export_zip(pkg, zpath), "导出 zip 失败")
        _true(os.path.getsize(zpath) > 0, "zip 不能是空文件")
        dest2 = os.path.join(tree, "dest2")
        os.makedirs(dest2, exist_ok=True)
        ok, name, msg = svc.import_zip(zpath, dest2)
        _true(ok, "导入 zip 失败：%s" % msg)
        _true(os.path.isfile(os.path.join(dest2, name, "codex.json")),
              "导入后的包要有 codex.json（实际 %r）" % name)
        ok2, _n2, msg2 = svc.import_zip(os.path.join(tree, "没有这个.zip"), dest2)
        _true(not ok2 and msg2, "坏输入：不存在的 zip 要报错")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_build_standalone_html():
    tree = _tmpdir("html")
    try:
        svc = _svc()
        pkg = _fixture(tree)
        payload, counts = svc.build_standalone_html(pkg)
        _contains(payload, "data:image/png;base64,", "资源要内嵌成 dataURL")
        _contains(payload, "sprites", "payload 里要按素材类别分组")
        _eq(set(counts), set(svc.SUBDIRS), "资源统计按四个目录分组")
        _true(sum(int(v) for v in counts.values()) >= 1, "至少要嵌进一个资源")
        try:
            svc.build_standalone_html(os.path.join(tree, "没有这个包"))
        except FileNotFoundError as e:
            _contains(str(e), "codex.json", "坏输入：缺 codex.json 要报错")
        else:
            raise AssertionError("没有 codex.json 的目录居然打包成功了")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_render_standalone():
    tree = _tmpdir("render")
    try:
        svc = _svc()
        pkg = _fixture(tree)
        html, _counts = svc.render_standalone(pkg)
        _contains(html, "__CODEX_DATA__", "默认模板要注入数据")
        _true("__CODEX_PAYLOAD__" not in html, "注入点必须被替换掉")
        custom = "<html><body><script>__CODEX_PAYLOAD__</script></body></html>"
        html2, _c2 = svc.render_standalone(pkg, custom)
        _true("__CODEX_PAYLOAD__" not in html2, "自定义模板的注入点也要被替换")
        _contains(html2, "sprites", "自定义模板里要看得到资源数据")
        try:
            svc.render_standalone(pkg, "<html>没有注入点</html>")
        except ValueError as e:
            _contains(str(e), "__CODEX_PAYLOAD__", "坏模板的报错要指出注入点")
        else:
            raise AssertionError("坏模板（没有注入点）居然渲染成功了")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_build_standalone_file():
    tree = _tmpdir("file")
    try:
        svc = _svc()
        pkg = _fixture(tree)
        out = os.path.join(tree, "game.html")
        ok, path, counts = svc.build_standalone_file(pkg, out)
        _true(ok and path == out, "导出单文件 HTML")
        _true(os.path.getsize(out) > 1000, "导出物太小了")
        with io.open(out, encoding="utf-8") as f:
            head = f.read(400)
        _contains(head, "<!DOCTYPE html", "导出物要是一份 HTML")
        _eq(set(counts), set(svc.SUBDIRS), "资源统计")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_mark_injection():
    """水印：宿主给了 mark 就注入（产物），没给就静默跳过"""
    tree = _tmpdir("mark")
    try:
        pkg = _fixture(tree, mark=FakeMark())
        html, _c = _svc(mark=FakeMark()).render_standalone(pkg)
        _contains(html, FakeMark.SIGNATURE, "产物里要有宿主水印")
        _contains(html, FakeMark.MARK_JS, "产物里要有水印 JS")
        plain, _c2 = _svc().render_standalone(pkg)       # 没绑 mark
        _contains(plain, "<!-- DICK-MARK -->", "没给 mark 时占位符要原样留着")
        _true(FakeMark.SIGNATURE not in plain, "没给 mark 时不许凭空造一个水印")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_exe_shell_and_cmd():
    svc = _svc()
    shell = svc.build_exe_shell("<html>测试</html>", "测试游戏")
    _contains(shell, "base64.b64decode", "壳脚本要内嵌 base64 并解回来")
    _contains(shell, "测试游戏", "标题要写进壳脚本")
    _contains(shell, "import webview", "壳脚本要用 pywebview 起窗口")
    cmd = svc.pyinstaller_cmd("x.py", "out", "我的游戏")
    for flag in ("--onefile", "--windowed", "--name", "--distpath", "--workpath"):
        _true(flag in cmd, "PyInstaller 命令缺 %s" % flag)
    _eq(cmd[-1], "x.py", "壳脚本要放在命令最后")
    _contains(svc.EXE_SHELL_TEMPLATE, "__HTML_B64__", "壳模板要有 HTML 占位符")

def case_bind_and_paths():
    """宿主注入：codex_dir 只给 pack_dir / list_packages 用；没绑就当场说清楚"""
    tree = _tmpdir("bind")
    try:
        svc = _svc(codex_dir=tree)
        _fixture(tree)
        _eq(svc.list_packages(), ["夹具"], "列出 codex_dir 下的包")
        _true(svc.pack_dir("夹具").endswith("夹具"), "包路径")
        bare = CodexService()
        try:
            bare.pack_dir("x")
        except RuntimeError as e:
            _contains(str(e), "bind", "没绑宿主的报错要指向 bind")
        else:
            raise AssertionError("没绑 codex_dir 居然能算包路径")
        _eq(bare.list_packages(), [], "没绑 codex_dir 时列表为空而不是崩")
        _true(_svc().safe_name("a/b:c") == "a_b_c", "文件名净化")
        _eq(_svc().safe_name(""), "未命名", "空名字给个安全默认")
        _true(_svc(codex_dir=tree).bind(FakeHost(codex_dir=tree, mark=FakeMark())).mark
              is not None, "bind 要接住宿主的水印模块")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_service_shape():
    """服务要在脱离宿主的情况下也说得清自己有什么（接口可查）"""
    svc = CodexService()
    _true(isinstance(svc.SUBDIRS, tuple) and len(svc.SUBDIRS) == 4, "四个素材目录")
    _true(svc.DEFAULT_EDITABLE_TEMPLATE.count("__CODEX_PAYLOAD__") >= 1,
          "可编辑模板必须留数据注入点")
    _true(len(svc.STANDALONE_PLAYER_JS) > 1000, "内联播放器脚本不该是空的")
    _eq(svc.CODEX_VERSION, "1.0", "格式版本")
    _true(svc.mark is None and svc.codex_dir == "", "没 bind 时宿主字段为空")


CASES = types.MappingProxyType({
    "classify_file": case_classify_file,
    "parse_script_text": case_parse_script_text,
    "parse_bad_input": case_parse_bad_input,
    "step_kind": case_step_kind,
    "evaluate_condition": case_evaluate_condition,
    "filter_choices": case_filter_choices,
    "sanitize_html": case_sanitize_html,
    "validate_codex": case_validate_codex,
    "analyze_codex": case_analyze_codex,
    "simulate_and_run_path": case_simulate_and_run_path,
    "placeholder_assets": case_placeholder_assets,
    "sample_package_layout": case_sample_package_layout,
    "import_folder": case_import_folder,
    "zip_roundtrip": case_zip_roundtrip,
    "build_standalone_html": case_build_standalone_html,
    "render_standalone": case_render_standalone,
    "build_standalone_file": case_build_standalone_file,
    "mark_injection": case_mark_injection,
    "exe_shell_and_cmd": case_exe_shell_and_cmd,
    "bind_and_paths": case_bind_and_paths,
    "service_shape": case_service_shape,
})
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌