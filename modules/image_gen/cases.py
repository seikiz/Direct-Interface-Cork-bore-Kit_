# -*- coding: utf-8 -*-
"""modules/image_gen/cases.py —— image_gen 的全部自检 case + CASES 登记表

一条 case = 一次"输入 → 输出/异常"的闭环。四条后端协议的两头都在这里钉死
（真服务器版本在 tests/test_image_gen.py，那才是抓包的地方）。
"""

import base64
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
from .service import ImageGenService
from .harness import FakeHost, FakeLog, FakeNet, JPG, PNG, WEBP, _contains, _eq, _svc, _tmpdir, _true, http_error
import types  # CASES 只读视图（十一：块里不许有模块级可变全局）


def case_backend_table():
    cases = [
        ("https://api.siliconflow.cn/v1", "openai", True),
        ("http://127.0.0.1:3000/v1", "openai", True),
        ("https://image.pollinations.ai", "pollinations", False),
        ("http://127.0.0.1:7860", "sdwebui", False),
        ("http://gpu-box:7860", "sdwebui", False),
        ("http://127.0.0.1:8188", "comfyui", False),
        ("", "openai", True),
        (None, "openai", True),
    ]
    svc = _svc()
    bad = [(u, svc.backend_of(u), svc.needs_key(u)) for u, b, n in cases
           if svc.backend_of(u) != b or svc.needs_key(u) != n]
    _eq(bad, [], "端点识别")
    _eq(svc.resolve_backend("http://gpu-box:9999", "comfyui"), "comfyui",
        "显式后端要覆盖自动识别")
    _eq(svc.resolve_backend("http://127.0.0.1:7860", "banana"), "sdwebui", "非法后端回落自动识别")
    _eq(set(svc.BACKENDS), {"openai", "pollinations", "sdwebui", "comfyui"}, "后端清单")

def case_size_and_mime():
    svc = _svc()
    _eq(svc.split_size("1024x1024"), (1024, 1024), "常规尺寸")
    _eq(svc.split_size("768x512"), (768, 512), "非常规尺寸")
    _eq(svc.split_size("abc"), (1024, 1024), "坏输入回落 1024")
    _eq(svc.split_size("", 512), (512, 512), "坏输入可按后端回落 512")
    _eq(svc.mime_of(JPG), "image/jpeg", "JPEG 嗅探")
    _eq(svc.mime_of(PNG), "image/png", "PNG 嗅探")
    _eq(svc.mime_of(WEBP), "image/webp", "WebP 嗅探")
    _eq(svc.mime_of(b"\x00"), "image/png", "认不出按 PNG")

def case_presets_builtin():
    tree = _tmpdir("presets")
    try:
        svc = _svc()
        got = svc.load_presets(tree)
        _eq(set(got), set(svc.PRESETS), "没有用户文件时就是内置那几套")
        _true(all(v.get("label") and v.get("prompt") for v in got.values()), "内置预设要带 label/prompt")
        lst = svc.list_presets(got)
        _true(all(set(p) == {"id", "label", "desc", "custom"} for p in lst), "list_presets 字段表")
        _true(svc.PRESETS_FILE and svc.PRESETS_FILE.endswith(".json"), "预设文件名")
        _eq(os.path.basename(svc.presets_path(tree)), svc.PRESETS_FILE, "预设路径")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_presets_override():
    """用户覆盖：注释键跳过、同名覆盖保留内置 label、简写能用、缺 prompt 不进表"""
    tree = _tmpdir("presets_ov")
    try:
        svc = _svc()
        with io.open(svc.presets_path(tree), "w", encoding="utf-8") as f:
            json.dump({"_说明": "注释键", "guofeng": {"label": "国风", "prompt": "ink, "},
                       "anime": {"prompt": "MY OVERRIDE, "}, "short": "flat, ",
                       "broken": {"label": "没 prompt"}, "empty": ""}, f, ensure_ascii=False)
        got = svc.load_presets(tree)
        _true(got["guofeng"]["custom"], "自定义预设要带 custom")
        _eq(got["anime"]["prompt"], "MY OVERRIDE, ", "同名覆盖 prompt")
        _eq(got["anime"]["label"], svc.PRESETS["anime"]["label"], "覆盖时保留内置 label")
        _eq(got["short"]["prompt"], "flat, ", "简写也能用")
        _true("_说明" not in got, "注释键要跳过")
        _true("broken" not in got and "empty" not in got, "缺 prompt 的不进表")
        _eq(len(got), len(svc.PRESETS) + 2, "覆盖后总数")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_presets_bad_json():
    """坏输入：坏 JSON 不许让设置页崩掉，回落到内置"""
    tree = _tmpdir("presets_bad")
    try:
        svc = _svc()
        with io.open(svc.presets_path(tree), "w", encoding="utf-8") as f:
            f.write("{ not json")
        _eq(set(svc.load_presets(tree)), set(svc.PRESETS), "坏 JSON 回落内置")
        _eq(svc.user_presets_json(tree), {}, "坏 JSON 时编辑器看到空对象")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_presets_save():
    tree = _tmpdir("presets_save")
    try:
        svc = _svc()
        ok, msg = svc.save_presets(tree, {"a": "p, ", "b": {"label": "乙", "prompt": "q, "}})
        _true(ok, msg)
        _eq(svc.user_presets_json(tree).get("b", {}).get("label"), "乙", "写完能读回")
        _eq(svc.load_presets(tree).get("b", {}).get("prompt"), "q, ", "读回后能合并")
        _true(not svc.save_presets(tree, ["x"])[0], "拒绝非对象")
        _true(not svc.save_presets(tree, {"x": "  "})[0], "拒绝空 prompt")
        _true(not svc.save_presets(tree, {"x": {"label": "甲"}})[0], "拒绝缺 prompt 的对象")
        _true(svc.save_presets(tree, {})[0], "传 {} 等于恢复内置")
        _eq(svc.user_presets_json(tree), {}, "恢复后用户文件为空对象")
    finally:
        shutil.rmtree(tree, ignore_errors=True)

def case_openai_b64():
    net = FakeNet(post_handler=lambda url, body: {"data": [{"b64_json": "UE5H"}]})
    svc = _svc(net)
    ok, data, msg = svc.generate("一只猫", preset="anime", base_url="http://fake/v1",
                                 api_key="sk-test", model="m1", size="512x512",
                                 seed=4242, backend="openai")
    _true(ok, msg)
    _eq(data["b64"], "UE5H", "b64 原样透传")
    _eq(data["preset"], "anime", "回显 preset")
    _eq(data["seed"], 4242, "回显 seed")
    call = net.posts[0]
    _eq(call["url"], "http://fake/v1/images/generations", "打到哪里")
    _eq(call["headers"]["Authorization"], "Bearer sk-test", "Bearer Key")
    _eq(call["body"]["prompt"], svc.PRESETS["anime"]["prompt"] + "一只猫", "预设前缀拼接")
    _eq(call["body"]["size"], "512x512", "size 透传")
    _eq(call["body"]["seed"], 4242, "seed 透传为整数")
    _true("negative_prompt" not in call["body"], "没填负面提示词就不发该字段")

def case_openai_missing_seed_field():
    net = FakeNet(post_handler=lambda url, body: {"data": [{"b64_json": "QQ=="}]})
    svc = _svc(net)
    svc.generate("x", base_url="http://fake/v1", api_key="k", backend="openai")
    _true("seed" not in net.posts[0]["body"], "没填 seed 就不发 seed 字段")

def case_openai_url_and_errors():
    svc = _svc(FakeNet(post_handler=lambda u, b: {"data": [{"url": "http://x.invalid/a.png"}]}))
    ok, data, _ = svc.generate("x", base_url="http://fake/v1", api_key="k", backend="openai")
    _true(ok and data.get("url") and not data.get("b64"), "后端回 url 时走 url 通道")

    svc = _svc(FakeNet(post_handler=lambda u, b: {"data": []}))
    ok, data, msg = svc.generate("x", base_url="http://fake/v1", api_key="k", backend="openai")
    _true(not ok and data is None and "为空" in msg, "空 data 判失败：%r" % msg)

    net = FakeNet()
    net.post_error = http_error(400)
    svc = _svc(net)
    ok, data, msg = svc.generate("x", base_url="http://fake/v1", api_key="k", backend="openai")
    _true((not ok) and "HTTP 400" in msg, "HTTP 报错要报出来：%r" % msg)
    _contains(msg, "model not found", "报错要带后端原文")

def case_sdwebui():
    net = FakeNet(post_handler=lambda u, b: {"images": ["data:image/png;base64,UE5H"]})
    svc = _svc(net)
    ok, data, msg = svc.generate("少女", preset="anime", base_url="http://fake",
                                 negative_prompt="模糊", size="768x512", seed=77,
                                 backend="sdwebui")
    _true(ok, msg)
    _eq(data["mime"], "image/png", "dataURL 前缀剥掉后按字节嗅探")
    call = net.posts[0]
    _eq(call["url"], "http://fake/sdapi/v1/txt2img", "打到哪里")
    _eq((call["body"]["width"], call["body"]["height"]), (768, 512), "宽高拆开")
    _eq((call["body"]["steps"], call["body"]["cfg_scale"]), (20, 7), "步骤/CFG 默认值")
    _eq(call["body"]["negative_prompt"], "模糊", "负面提示词透传")
    _eq(call["body"]["seed"], 77, "seed 透传")

def case_sdwebui_bad_inputs():
    svc = _svc(FakeNet(post_handler=lambda u, b: {"images": []}))
    ok, data, msg = svc.generate("x", base_url="http://fake", backend="sdwebui")
    _true((not ok) and "没返回图片" in msg, "没返回图片要判失败")

    net = FakeNet()
    net.post_error = http_error(500, b"boom")
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="sdwebui")
    _true((not ok) and "HTTP 500" in msg, "HTTP 500 报错带状态码")

    net = FakeNet()
    net.post_error = OSError("connection refused")
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="sdwebui")
    _true((not ok) and "连不上本地 SD" in msg and "--api" in msg, "连不上给可操作提示：%r" % msg)

def case_comfyui():
    state = {"polls": 0}

    def post(url, body):
        if url.endswith("/prompt"):
            return {"prompt_id": "pid-1"}
        raise AssertionError("不该 POST %s" % url)

    def get(url):
        if "/history/" in url:
            state["polls"] += 1
            if state["polls"] < 2:
                return b"{}"
            return json.dumps({"pid-1": {"outputs": {"9": {"images": [
                {"filename": "dick_00001_.png", "subfolder": "sub", "type": "output"}]}}}}).encode()
        if "/view?" in url:
            return PNG
        raise AssertionError("不该 GET %s" % url)

    net = FakeNet(post_handler=post, get_handler=get)
    svc = _svc(net)
    ok, data, msg = svc.generate("机械猫", preset="cyberpunk", base_url="http://fake",
                                 model="sd_xl_base_1.0.safetensors", size="640x896",
                                 seed=123, backend="comfyui")
    _true(ok, msg)
    _eq(data["b64"], base64.b64encode(PNG).decode(), "取回的就是图片字节")
    _true(state["polls"] >= 2, "要真的轮询 /history")
    wf = net.posts[0]["body"]["prompt"]
    _eq(set(wf), {"3", "4", "5", "6", "7", "8", "9"}, "工作流是 7 个标准节点")
    _eq(wf["4"]["inputs"]["ckpt_name"], "sd_xl_base_1.0.safetensors", "checkpoint 来自 model")
    _eq((wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]), (640, 896), "宽高")
    _eq(wf["3"]["inputs"]["seed"], 123, "seed 透传")
    _eq(wf["7"]["inputs"]["text"], "", "没给负面提示词就是空串")
    _true(net.posts[0]["body"]["client_id"], "要带 client_id")
    view = [g["url"] for g in net.gets if "/view?" in g["url"]][0]
    _true("filename=dick_00001_.png" in view and "subfolder=sub" in view, "取图请求带三段参数")

def case_comfyui_bad_inputs():
    svc = _svc(FakeNet(post_handler=lambda u, b: {"error": "invalid prompt"}))
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="comfyui")
    _true((not ok) and "checkpoint" in msg, "没给 prompt_id 要指向 checkpoint")

    net = FakeNet(post_handler=lambda u, b: {"prompt_id": "p2"},
                  get_handler=lambda u: b"{}")
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", timeout=1, backend="comfyui")
    _true((not ok) and "超时" in msg, "迟迟不出图要超时而不是卡死")

    net = FakeNet()
    net.post_error = OSError("refused")
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="comfyui")
    _true((not ok) and "连不上本地 ComfyUI" in msg and "8188" in msg, "连不上给可操作提示")

    net = FakeNet(post_handler=lambda u, b: ({"prompt_id": "p3"}),
                  get_handler=lambda u: json.dumps(
                      {"p3": {"outputs": {"9": {"text": []}}}}).encode())
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", timeout=1, backend="comfyui")
    _true((not ok) and "没有图片节点" in msg, "输出里没图要说明白：%r" % msg)

def case_pollinations():
    net = FakeNet(get_handler=lambda u: JPG)
    svc = _svc(net)
    ok, data, msg = svc.generate("猫咪", preset="chibi", base_url="http://fake",
                                 model="flux", size="1024x1024", seed=9, backend="pollinations")
    _true(ok, msg)
    _eq(data["mime"], "image/jpeg", "mime 按字节嗅探")
    url = net.gets[0]["url"]
    _contains(url, "/prompt/", "走 GET /prompt/<提示词>")
    _true("width=1024" in url and "height=1024" in url and "nologo=true" in url, "带尺寸与 nologo")
    _true("private" not in url, "绝不带 private（付费档参数，带上必 402）")
    _true("model=flux" in url and "seed=9" in url, "简单模型名与 seed 透传")

def case_pollinations_bad_inputs():
    svc = _svc(FakeNet(get_handler=lambda u: b"x"))
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="pollinations")
    _true((not ok) and "过小" in msg, "返回内容明显不是图片要报错")

    state = {"n": 0}

    def get(url):
        state["n"] += 1
        if state["n"] <= 1:
            raise http_error(402, b"payment required")
        return JPG

    net = FakeNet(get_handler=get)
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="pollinations")
    _true(ok and state["n"] == 2, "第一次限流时退避重试成功")
    _eq(net.sleeps, [8], "退避只睡一次（假时钟，不真等）")

    net = FakeNet(get_handler=lambda u: (_ for _ in ()).throw(http_error(402, b"pay")))
    svc = _svc(net)
    ok, _d, msg = svc.generate("x", base_url="http://fake", backend="pollinations")
    _true((not ok) and "限流" in msg and "Key" in msg, "一直限流给人话解释")
    _eq(len(net.gets), 2, "重试次数有上限")

    net = FakeNet(get_handler=lambda u: (_ for _ in ()).throw(OSError("dns")))
    svc = _svc(net)
    ok, data, msg = svc.generate("x", base_url="http://fake", backend="pollinations")
    _true((not ok) and data is None and bool(msg), "连不上时报错不抛异常")

def case_pollinations_model_path():
    net = FakeNet(get_handler=lambda u: JPG)
    svc = _svc(net)
    svc.generate("x", base_url="http://fake", model="black-forest-labs/FLUX.1-schnell",
                 backend="pollinations")
    _true("model=" not in net.gets[0]["url"], "『厂商/模型』式名字不传给 Pollinations（会被拒）")

def case_dispatch_presets_table():
    net = FakeNet(post_handler=lambda u, b: {"data": [{"b64_json": "QQ=="}]})
    svc = _svc(net)
    custom = {"mine": {"label": "我的", "prompt": "MYPREFIX, ", "desc": "自定"}}
    ok, data, _ = svc.generate("内容", preset="mine", base_url="http://fake/v1", api_key="k",
                               presets=custom, backend="openai")
    _true(ok, "传了 presets 就用传进来的表")
    _eq(net.posts[0]["body"]["prompt"], "MYPREFIX, 内容", "自定义前缀")
    _eq(data["preset"], "mine", "回显自定义 preset")

    net = FakeNet(post_handler=lambda u, b: {"data": [{"b64_json": "QQ=="}]})
    svc = _svc(net)
    svc.generate("内容", preset="不存在", base_url="http://fake/v1", api_key="k",
                 backend="openai")
    _true(net.posts[0]["body"]["prompt"].startswith(svc.PRESETS["anime"]["prompt"]),
          "预设 id 不存在时回落 anime")

    net = FakeNet(post_handler=lambda u, b: {"data": [{"b64_json": "QQ=="}]})
    svc = _svc(net)
    svc.generate("内容", preset="anime", base_url="http://fake/v1", api_key="k",
                 presets={"anime": "PLAIN, "}, backend="openai")
    _eq(net.posts[0]["body"]["prompt"], "PLAIN, 内容", "预设值退化成字符串也不炸")

def case_bind_and_progress():
    """宿主注入：log / progress / net 三样都认；没绑宿主时也不许崩"""
    log = FakeLog()
    host = FakeHost()
    host.log = log
    net = FakeNet(post_handler=lambda u, b: {"data": [{"b64_json": "QQ=="}]})
    svc = ImageGenService()
    _true(svc.bind(host, net) is svc, "bind 返回自己（壳层能链式取服务）")
    _true(svc.host is host and svc.net is net, "bind 要认宿主与传输")
    svc.generate("x", base_url="http://fake/v1", api_key="k", backend="openai")
    _eq([c[0] for c in host.progress_calls], ["start", "done"], "进度回调的两次事件")

    net2 = FakeNet(post_handler=lambda u, b: {"data": []})
    svc2 = ImageGenService().bind(FakeHost(), net2)
    svc2.generate("x", base_url="http://fake/v1", api_key="k", backend="openai")
    _eq(svc2.last_error[:4], "生图返回", "失败要记 last_error")

    bare = ImageGenService()          # 不 bind：不许崩，只是没人听进度
    bare._progress("start")
    _eq(bare.net.proxy_of(), "", "没绑宿主时代理为空（走 urllib 默认）")

def case_quick_test():
    msg = _svc().quick_test()
    _true("pollinations" in msg and "8188" in msg and "7860" in msg, "提示要覆盖四个后端")


CASES = types.MappingProxyType({
    "backend_table": case_backend_table,
    "size_and_mime": case_size_and_mime,
    "presets_builtin": case_presets_builtin,
    "presets_override": case_presets_override,
    "presets_bad_json": case_presets_bad_json,
    "presets_save": case_presets_save,
    "openai_b64": case_openai_b64,
    "openai_missing_seed_field": case_openai_missing_seed_field,
    "openai_url_and_errors": case_openai_url_and_errors,
    "sdwebui": case_sdwebui,
    "sdwebui_bad_inputs": case_sdwebui_bad_inputs,
    "comfyui": case_comfyui,
    "comfyui_bad_inputs": case_comfyui_bad_inputs,
    "pollinations": case_pollinations,
    "pollinations_bad_inputs": case_pollinations_bad_inputs,
    "pollinations_model_path": case_pollinations_model_path,
    "dispatch_presets_table": case_dispatch_presets_table,
    "bind_and_progress": case_bind_and_progress,
    "quick_test": case_quick_test,
})
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌