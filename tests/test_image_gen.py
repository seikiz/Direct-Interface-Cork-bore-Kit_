# -*- coding: utf-8 -*-
"""生图引擎审计：四个后端 + 预设覆盖 + seed 透传，全部打本地假服务器。

为什么需要
----------
image_gen 的每一条路径都是「发 HTTP + 解析对方的格式」：
  · Pollinations 回的是图片字节，不是 JSON（曾经把 private=true 带上去 → 必然 402）
  · A1111 回 base64，还可能带 dataURL 前缀
  · ComfyUI 要 POST 工作流 + 轮询 /history + 再去 /view 取图（三段式，最容易写错）
  · OpenAI 兼容回 b64_json 或 url
四条路径都不能靠「跑一次试试」来保证 —— 真跑要 Key、要本地服务、要外网。
所以这里起本地假服务器，把「发出去的请求」和「拿回来的响应」两头都钉死。

跑法：python tests/test_image_gen.py
"""
import base64
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import types
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# 本地假服务器不能被系统代理劫持（本机会装 FlClash <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌之类，:7890 会吃掉 127.0.0.1 的请求）
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

import image_gen  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 600
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 600
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 600

PASS = 0
FAIL = 0
SERVERS = []
_CURRENT = [None]


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


class Handler(BaseHTTPRequestHandler):
    state = {}

    def log_message(self, *a):
        pass

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        return self._send(404, "{}")


def use(handler):
    """本段测试要起的假后端（每个测试函数开头声明一次）。"""
    _CURRENT[0] = handler


def start(state, handler=None):
    cls = type("Mock", (handler or _CURRENT[0] or Handler,), {"state": state})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    SERVERS.append(srv)
    return "http://127.0.0.1:%d" % srv.server_address[1]


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def b64_of(raw):
    return base64.b64encode(raw).decode("ascii")


# ---------------- 假后端 ----------------
class FakeOpenAI(Handler):
    def do_POST(self):
        st = type(self).state
        st.setdefault("calls", []).append({
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "body": self._read_json(),
        })
        if "/images/generations" not in self.path:
            return self._send(404, "{}")
        if st.get("fail"):
            return self._send(400, json.dumps({"error": {"message": "model not found"}}))
        if st.get("empty"):
            return self._send(200, json.dumps({"data": []}))
        if st.get("mode") == "url":
            return self._send(200, json.dumps({"data": [{"url": "http://x.invalid/a.png"}]}))
        return self._send(200, json.dumps({"data": [{"b64_json": b64_of(PNG)}]}))


class FakeSD(Handler):
    def do_POST(self):
        st = type(self).state
        st.setdefault("calls", []).append({"path": self.path, "body": self._read_json()})
        if st.get("http500"):
            return self._send(500, "boom")
        if st.get("empty"):
            return self._send(200, json.dumps({"images": []}))
        return self._send(200, json.dumps({"images": ["data:image/png;base64," + b64_of(PNG)]}))


class FakeComfy(Handler):
    def do_POST(self):
        st = type(self).state
        payload = self._read_json()
        st["workflow"] = payload.get("prompt")
        st["client_id"] = payload.get("client_id")
        if st.get("no_pid"):
            return self._send(200, json.dumps({"error": "invalid prompt"}))
        return self._send(200, json.dumps({"prompt_id": "pid-1"}))

    def do_GET(self):
        st = type(self).state
        if self.path.startswith("/history/"):
            st["polls"] = st.get("polls", 0) + 1
            if st.get("never") or st["polls"] < st.get("ready_at", 1):
                return self._send(200, "{}")
            pid = self.path.rsplit("/", 1)[-1]
            return self._send(200, json.dumps({pid: {"outputs": {"9": {"images": [
                {"filename": "dick_00001_.png", "subfolder": "sub", "type": "output"}]}}}}))
        if self.path.startswith("/view?"):
            st["view_path"] = self.path
            return self._send(200, PNG, "image/png")
        return self._send(404, "{}")


class FakePoll(Handler):
    def do_GET(self):
        st = type(self).state
        st.setdefault("paths", []).append(self.path)
        st["n"] = st.get("n", 0) + 1
        if st.get("fail_times") and st["n"] <= st["fail_times"]:
            return self._send(st.get("code", 402), "payment required")
        if st.get("tiny"):
            return self._send(200, b"x", "image/jpeg")
        return self._send(200, JPG, "image/jpeg")


# ---------------- 各段审计 ----------------
def test_backend_detect():
    print(u"\n== ① 后端识别与 Key 需求 ==")
    cases = [
        ("https://api.siliconflow.cn/v1", "openai", True),
        ("https://open.bigmodel.cn/api/paas/v4", "openai", True),
        ("http://127.0.0.1:3000/v1", "openai", True),
        ("https://image.pollinations.ai", "pollinations", False),
        ("https://image.pollinations.ai/prompt", "pollinations", False),
        ("http://127.0.0.1:7860", "sdwebui", False),
        ("http://127.0.0.1:7860/", "sdwebui", False),
        ("http://192.168.1.9:7860", "sdwebui", False),
        ("http://127.0.0.1:8188", "comfyui", False),
        ("http://127.0.0.1:8188/", "comfyui", False),
        ("", "openai", True),
        (None, "openai", True),
    ]
    bad = [(u, image_gen.backend_of(u), image_gen.needs_key(u)) for u, be, nk in cases
           if image_gen.backend_of(u) != be or image_gen.needs_key(u) != nk]
    check(u"%d 种端点都识别正确" % len(cases), not bad, u"错的：%s" % bad)
    check(u"只有 OpenAI 兼容后端要 Key",
          image_gen.needs_key("https://api.siliconflow.cn/v1")
          and not any(image_gen.needs_key(u) for u in
                      ("https://image.pollinations.ai", "http://127.0.0.1:7860",
                       "http://127.0.0.1:8188")))
    check(u"显式指定后端可覆盖自动识别（非默认端口也能用）",
          image_gen.resolve_backend("http://192.168.1.9:9999", "comfyui") == "comfyui"
          and image_gen.resolve_backend("https://api.siliconflow.cn/v1", "sdwebui") == "sdwebui")
    check(u"显式后端填了非法值/auto/空 就回落到自动识别",
          image_gen.resolve_backend("http://127.0.0.1:7860", "banana") == "sdwebui"
          and image_gen.resolve_backend("http://127.0.0.1:7860", "auto") == "sdwebui"
          and image_gen.resolve_backend("http://127.0.0.1:7860", "") == "sdwebui")
    check(u"显式选本地后端时不再要求 Key",
          not image_gen.needs_key("http://192.168.1.9:9999", "comfyui")
          and not image_gen.needs_key("http://192.168.1.9:9999", "sdwebui"))
    check(u"后端清单与 resolve 取值一致",
          set(image_gen.BACKENDS) == {"openai", "pollinations", "sdwebui", "comfyui"})


def test_sizes_and_mime():
    print(u"\n== ② 尺寸解析与图片格式嗅探 ==")
    check(u"'1024x1024' → (1024, 1024)", image_gen._split_size("1024x1024") == (1024, 1024))
    check(u"'768x512' → (768, 512)", image_gen._split_size("768x512") == (768, 512))
    check(u"乱填回落到 1024x1024", image_gen._split_size("abc") == (1024, 1024))
    check(u"乱填可按后端回落（本地 512）", image_gen._split_size("", 512) == (512, 512))
    check(u"JPEG 嗅探", image_gen._mime_of(JPG) == "image/jpeg")
    check(u"PNG 嗅探", image_gen._mime_of(PNG) == "image/png")
    check(u"WebP 嗅探", image_gen._mime_of(WEBP) == "image/webp")


def test_presets():
    print(u"\n== ③ 预设：内置 + 用户覆盖 ==")
    tmp = tempfile.mkdtemp(prefix="dick_preset_")
    try:
        builtin = image_gen.load_presets(tmp)
        check(u"没有用户文件时就是内置 %d 套" % len(image_gen.PRESETS),
              set(builtin) == set(image_gen.PRESETS))
        check(u"内置预设都带 label/prompt",
              all(v.get("label") and v.get("prompt") for v in builtin.values()))
        check(u"内置预设都不是 custom",
              not any(v.get("custom") for v in builtin.values()))

        with io.open(image_gen.presets_path(tmp), "w", encoding="utf-8") as f:
            json.dump({
                "_说明": "注释键必须被跳过",
                "guofeng": {"label": u"国风线稿", "prompt": "ink line art, ", "desc": u"自定"},
                "anime": {"prompt": "MY OVERRIDE, "},
                "short": "flat vector, ",
                "broken": {"label": u"没 prompt"},
                "empty": "",
            }, f, ensure_ascii=False)

        got = image_gen.load_presets(tmp)
        check(u"新增自定义预设带 custom 标记",
              got.get("guofeng", {}).get("custom") and got["guofeng"]["prompt"] == "ink line art, ")
        check(u"同名 id 覆盖内置的 prompt，但保留内置 label",
              got["anime"]["prompt"] == "MY OVERRIDE, "
              and got["anime"]["label"] == image_gen.PRESETS["anime"]["label"])
        check(u"简写（纯字符串）也能用",
              got.get("short", {}).get("prompt") == "flat vector, ")
        check(u"下划线开头的注释键被跳过", "_说明" not in got)
        check(u"缺 prompt 的条目不进预设表", "broken" not in got and "empty" not in got)
        check(u"覆盖后预设总数 = 内置 + 2",
              len(got) == len(image_gen.PRESETS) + 2, u"实际 %d" % len(got))

        lst = image_gen.list_presets(got)
        check(u"list_presets 标出 custom 项",
              any(p["custom"] and p["id"] == "guofeng" for p in lst)
              and all(set(("id", "label", "desc", "custom")) == set(p) for p in lst))

        # 坏 JSON 不能让设置页崩掉
        with io.open(image_gen.presets_path(tmp), "w", encoding="utf-8") as f:
            f.write("{ not json")
        check(u"坏 JSON 时回落到内置预设",
              set(image_gen.load_presets(tmp)) == set(image_gen.PRESETS))

        ok, msg = image_gen.save_presets(tmp, {"a": "p, ", "b": {"label": u"乙", "prompt": "q, "}})
        check(u"save_presets 写入成功", ok, msg)
        round_trip = image_gen.user_presets_json(tmp)
        check(u"写完能读回同样内容", round_trip.get("b", {}).get("label") == u"乙", str(round_trip))
        check(u"读回后 load_presets 能合并",
              image_gen.load_presets(tmp).get("b", {}).get("prompt") == "q, ")
        check(u"save_presets 拒绝非对象", not image_gen.save_presets(tmp, ["x"])[0])
        check(u"save_presets 拒绝空 prompt", not image_gen.save_presets(tmp, {"x": "  "})[0])
        check(u"save_presets 拒绝缺 prompt 的对象",
              not image_gen.save_presets(tmp, {"x": {"label": u"甲"}})[0])
        ok, msg = image_gen.save_presets(tmp, {})
        check(u"传 {} 等于恢复内置默认", ok and image_gen.user_presets_json(tmp) == {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_openai():
    print(u"\n== ④ OpenAI 兼容后端（Key / b64 / url / 报错）==")
    use(FakeOpenAI)
    st = {}
    url = start(st)
    ok, data, msg = image_gen.generate(u"一只猫", preset="anime", base_url=url,
                                       api_key="sk-test", model="m1", size="512x512", backend="openai")
    check(u"出图成功", ok and data and data.get("b64"), msg)
    check(u"base64 解得回 PNG 字节",
          ok and base64.b64decode(data["b64"]) == PNG)
    check(u"mime 标成 image/png", ok and data["mime"] == "image/png")
    check(u"回显 preset 名", ok and data["preset"] == "anime")
    call = st["calls"][0]
    check(u"打到 {base}/images/generations", call["path"] == "/images/generations", call["path"])
    check(u"带上 Bearer Key", call["auth"] == "Bearer sk-test", str(call["auth"]))
    body = call["body"]
    check(u"预设前缀自动拼接",
          body["prompt"] == image_gen.PRESETS["anime"]["prompt"] + u"一只猫", body["prompt"])
    check(u"size 原样透传", body["size"] == "512x512" and body["n"] == 1
          and body["response_format"] == "b64_json")
    check(u"没填 seed 就不发 seed 字段", "seed" not in body)
    check(u"没填负面提示词就不发该字段", "negative_prompt" not in body)

    st["calls"] = []
    ok, data, _ = image_gen.generate(u"风景", preset="realistic", base_url=url, api_key="k",
                                     negative_prompt=u"低质量", extra="golden hour", seed=4242, backend="openai")
    body = st["calls"][0]["body"]
    check(u"extra 追加在内容之后",
          body["prompt"].endswith(u"风景, golden hour"), body["prompt"])
    check(u"负面提示词透传", body["negative_prompt"] == u"低质量")
    check(u"填了 seed 就透传为整数", body["seed"] == 4242)
    check(u"回显 seed", data["seed"] == 4242)

    st["mode"] = "url"
    ok, data, _ = image_gen.generate(u"x", base_url=url, api_key="k", backend="openai")
    check(u"后端回 url 时走 url 通道", ok and data.get("url") == "http://x.invalid/a.png"
          and not data.get("b64"), str(data))

    st.pop("mode")
    st["fail"] = True
    ok, data, msg = image_gen.generate(u"x", base_url=url, api_key="k", backend="openai")
    check(u"HTTP 报错要报出来而不是静默",
          (not ok) and data is None and "HTTP 400" in msg, msg)
    check(u"报错里带上后端原文", "model not found" in msg, msg)
    st["fail"] = False

    st["empty"] = True
    ok, data, msg = image_gen.generate(u"x", base_url=url, api_key="k", backend="openai")
    check(u"空 data 数组要判为失败", (not ok) and u"为空" in msg, msg)
    st["empty"] = False

    ok, data, msg = image_gen.generate(u"x", base_url="http://127.0.0.1:%d/v1" % free_port(),
                                       api_key="k", backend="openai")
    check(u"连不上时报错不抛异常", (not ok) and data is None and bool(msg), msg)


def test_sdwebui():
    print(u"\n== ⑤ 本地 A1111 / Forge 后端 ==")
    use(FakeSD)
    st = {}
    url = start(st)
    ok, data, msg = image_gen.generate(u"少女", preset="anime", base_url=url,
                                       negative_prompt=u"模糊", size="768x512", seed=77, backend="sdwebui")
    check(u"出图成功", ok and data and data.get("b64"), msg)
    check(u"dataURL 前缀被剥掉，字节正确",
          ok and base64.b64decode(data["b64"]) == PNG)
    check(u"mime 标成 PNG", ok and data["mime"] == "image/png")
    call = st["calls"][0]
    check(u"打到 /sdapi/v1/txt2img", call["path"] == "/sdapi/v1/txt2img", call["path"])
    body = call["body"]
    check(u"宽高按 size 拆开", body["width"] == 768 and body["height"] == 512)
    check(u"步骤/CFG 有默认值", body["steps"] == 20 and body["cfg_scale"] == 7)
    check(u"负面提示词透传", body["negative_prompt"] == u"模糊")
    check(u"seed 透传", body["seed"] == 77)
    check(u"提示词带预设前缀", body["prompt"].startswith(image_gen.PRESETS["anime"]["prompt"]))

    st["calls"] = []
    ok, data, _ = image_gen.generate(u"x", base_url=url, size="bad", backend="sdwebui")
    body = st["calls"][0]["body"]
    check(u"尺寸乱填回落 512x512（本地模型不吃 1024）",
          body["width"] == 512 and body["height"] == 512)
    check(u"没填 seed 就不发 seed", "seed" not in body)

    st["empty"] = True
    ok, data, msg = image_gen.generate(u"x", base_url=url, backend="sdwebui")
    check(u"没返回图片要判失败", (not ok) and u"没返回图片" in msg, msg)
    st["empty"] = False

    st["http500"] = True
    ok, data, msg = image_gen.generate(u"x", base_url=url, backend="sdwebui")
    check(u"HTTP 500 报错带状态码", (not ok) and "HTTP 500" in msg, msg)
    st["http500"] = False

    ok, data, msg = image_gen.generate(u"x", base_url="http://127.0.0.1:%d" % free_port(), backend="sdwebui")
    check(u"没开本地 SD 时给出可操作提示",
          (not ok) and u"连不上本地 SD" in msg and u"--api" in msg, msg)


def test_comfyui():
    print(u"\n== ⑥ 本地 ComfyUI 后端（工作流 / 轮询 / 取图）==")
    use(FakeComfy)
    st = {"ready_at": 2}
    url = start(st)
    ok, data, msg = image_gen.generate(u"机械猫", preset="cyberpunk", base_url=url,
                                       model="sd_xl_base_1.0.safetensors",
                                       negative_prompt=u"水印", size="640x896", seed=123, backend="comfyui")
    check(u"出图成功（等了两轮 history）", ok and data and data.get("b64"), msg)
    check(u"字节正确", ok and base64.b64decode(data["b64"]) == PNG)
    check(u"真轮询了 /history", st["polls"] >= 2, str(st.get("polls")))
    wf = st["workflow"]
    check(u"工作流是 5 段标准节点",
          set(wf) == {"3", "4", "5", "6", "7", "8", "9"}, str(sorted(wf)))
    check(u"checkpoint 名来自「生图模型」",
          wf["4"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors")
    check(u"宽高正确", wf["5"]["inputs"]["width"] == 640 and wf["5"]["inputs"]["height"] == 896)
    check(u"seed 透传为整数", wf["3"]["inputs"]["seed"] == 123)
    check(u"正面提示词带预设前缀并接到 KSampler",
          wf["6"]["inputs"]["text"].startswith(image_gen.PRESETS["cyberpunk"]["prompt"])
          and wf["3"]["inputs"]["positive"] == ["6", 0])
    check(u"负面提示词进 7 号节点",
          wf["7"]["inputs"]["text"] == u"水印" and wf["3"]["inputs"]["negative"] == ["7", 0])
    check(u"有 client_id（后端用来配对）", bool(st.get("client_id")))

    view = st.get("view_path", "")
    check(u"取图请求带 filename/subfolder/type",
          "filename=dick_00001_.png" in view and "subfolder=sub" in view
          and "type=output" in view, view)

    st2 = {"ready_at": 1}
    url2 = start(st2)
    ok, data, _ = image_gen.generate(u"x", base_url=url2, model="black-forest-labs/FLUX.1-schnell", backend="comfyui")
    ckpt = st2["workflow"]["4"]["inputs"]["ckpt_name"]
    check(u"模型名不是 checkpoint 文件时回落到常见 ckpt 并仍可跑",
          ckpt == "v1-5-pruned-emaonly.safetensors", ckpt)
    check(u"没填 seed 时自动生成一个整数 seed",
          isinstance(st2["workflow"]["3"]["inputs"]["seed"], int))

    st3 = {"no_pid": True}
    url3 = start(st3)
    ok, data, msg = image_gen.generate(u"x", base_url=url3, backend="comfyui")
    check(u"后端不给 prompt_id 时报 checkpoint 相关问题",
          (not ok) and u"checkpoint" in msg, msg)

    st4 = {"never": True}
    url4 = start(st4)
    ok, data, msg = image_gen.generate(u"x", base_url=url4, timeout=1, backend="comfyui")
    check(u"迟迟不出图会超时而不是卡死", (not ok) and u"超时" in msg, msg)

    ok, data, msg = image_gen.generate(u"x", base_url="http://127.0.0.1:%d" % free_port(), backend="comfyui")
    check(u"没开 ComfyUI 时给出可操作提示",
          (not ok) and u"连不上本地 ComfyUI" in msg and "8188" in msg, msg)


def test_pollinations():
    print(u"\n== ⑦ Pollinations 免 Key 后端 ==")
    use(FakePoll)
    st = {}
    url = start(st)
    ok, data, msg = image_gen.generate(u"猫咪", preset="chibi", base_url=url,
                                       model="flux", size="1024x1024", seed=9, backend="pollinations")
    check(u"出图成功", ok and data and data.get("b64"), msg)
    check(u"字节正确（回的是图片本身）", ok and base64.b64decode(data["b64"]) == JPG)
    check(u"mime 标成 image/jpeg", ok and data["mime"] == "image/jpeg")
    path = st["paths"][0]
    check(u"走 GET /prompt/<提示词>", path.startswith("/prompt/"), path[:60])
    check(u"带 width/height/nologo", "width=1024" in path and "height=1024" in path
          and "nologo=true" in path, path)
    check(u"绝不带 private（付费档参数，带上必 402）", "private" not in path, path)
    check(u"简单模型名透传", "model=flux" in path, path)
    check(u"seed 透传", "seed=9" in path, path)
    check(u"提示词里带预设前缀（URL 编码后原样出现在路径里）",
          urllib.parse.quote(image_gen.PRESETS["chibi"]["prompt"] + u"猫咪", safe="") in path,
          path)

    st["paths"] = []
    ok, data, _ = image_gen.generate(u"x", base_url=url,
                                     model="black-forest-labs/FLUX.1-schnell", backend="pollinations")
    check(u"『厂商/模型』这种路径式模型名不传给 Pollinations（会被拒）",
          "model=" not in st["paths"][0], st["paths"][0])

    st["paths"] = []
    ok, data, msg = image_gen.generate(u"x", base_url=url, negative_prompt=u"丑", backend="pollinations")
    check(u"该后端不支持负面提示词时要说明已忽略",
          ok and u"忽略" in msg, msg)

    # 限流重试：把 8 秒退避换掉，免得测试白等
    real_time = image_gen.time
    st = {"fail_times": 1}
    url2 = start(st)
    try:
        image_gen.time = types.SimpleNamespace(sleep=lambda s: None)
        ok, data, msg = image_gen.generate(u"x", base_url=url2, backend="pollinations")
    finally:
        image_gen.time = real_time
    check(u"第一次被限流时退避重试成功", ok and st["n"] == 2, u"尝试 %s 次：%s" % (st.get("n"), msg))

    st = {"fail_times": 99, "code": 402}
    url3 = start(st)
    try:
        image_gen.time = types.SimpleNamespace(sleep=lambda s: None)
        ok, data, msg = image_gen.generate(u"x", base_url=url3, backend="pollinations")
    finally:
        image_gen.time = real_time
    check(u"一直限流时给出人话解释", (not ok) and u"限流" in msg and u"Key" in msg, msg)
    check(u"重试次数有上限（不会无限打）", st["n"] == 2, str(st.get("n")))

    st = {"tiny": True}
    url4 = start(st)
    ok, data, msg = image_gen.generate(u"x", base_url=url4, backend="pollinations")
    check(u"返回内容明显不是图片时报错", (not ok) and u"过小" in msg, msg)

    ok, data, msg = image_gen.generate(u"x", base_url="http://127.0.0.1:%d" % free_port(), backend="pollinations")
    check(u"连不上时报错不抛异常", (not ok) and data is None and bool(msg), msg)


def test_dispatch():
    print(u"\n== ⑧ 分发：预设表可整体替换 ==")
    use(FakeOpenAI)
    st = {}
    url = start(st)
    custom = {"mine": {"label": u"我的", "prompt": "MYPREFIX, ", "desc": u"自定"}}
    ok, data, _ = image_gen.generate(u"内容", preset="mine", base_url=url, api_key="k",
                                     presets=custom, backend="openai")
    check(u"传了 presets 就用传进来的表",
          ok and st["calls"][0]["body"]["prompt"] == "MYPREFIX, " + u"内容",
          str(st["calls"][0]["body"]["prompt"]))
    check(u"回显自定义 preset id", ok and data["preset"] == "mine")

    st["calls"] = []
    ok, data, _ = image_gen.generate(u"内容", preset=u"不存在的预设", base_url=url, api_key="k", backend="openai")
    check(u"预设 id 不存在时回落到 anime 而不是崩",
          ok and st["calls"][0]["body"]["prompt"].startswith(image_gen.PRESETS["anime"]["prompt"]))

    st["calls"] = []
    ok, data, _ = image_gen.generate(u"内容", preset="anime", base_url=url, api_key="k",
                                     presets={"anime": "PLAIN, "}, backend="openai")
    check(u"预设值退化成字符串也不炸", ok and st["calls"][0]["body"]["prompt"] == "PLAIN, " + u"内容")


def _js_call_args(html, name):
    """抽出 pywebview.api.<name>(...) 的实参列表（按括号配平切分）。"""
    key = "pywebview.api.%s(" % name
    i = html.find(key)
    if i < 0:
        return None
    i += len(key)
    depth = 1
    j = i
    while j < len(html) and depth:
        c = html[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if not depth:
                break
        j += 1
    raw = html[i:j]
    out, depth, cur = [], 0, ""
    for c in raw:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
    if cur.strip():
        out.append(cur.strip())
    return out


def test_web_bridge():
    print(u"\n== ⑨ 前端调用与后端签名对得上（位置参数错了 pywebview 不会报错）==")
    app = io.open(os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"), encoding="utf-8").read()
    html = io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()

    def py_params(name):
        m = re.search(r"def api_%s\(self,?([^)]*)\)" % name, app)
        if m is None:
            return None
        return [p.strip().split("=")[0].strip() for p in m.group(1).split(",") if p.strip()]

    expected = {
        "gen_image": ["prompt", "preset", "size", "negative_prompt", "extra", "seed"],
        "save_image_gen": ["key", "base_url", "model", "backend"],
        "gen_presets": [],
        "get_image_presets_file": [],
        "save_image_presets_file": ["text"],
    }
    for name, params in expected.items():
        got = py_params(name)
        check(u"后端 api_%s 参数表 = %s" % (name, params), got == params, str(got))
        js = _js_call_args(html, name)
        check(u"前端调用了 %s 且实参个数一致（%d 个）" % (name, len(params)),
              js is not None and len(js) == len(params),
              u"前端实参：%s" % js)

    js = _js_call_args(html, "gen_image") or []
    check(u"gen_image 第 4 个实参是负面提示词", len(js) > 3 and "neg" in js[3], str(js))
    check(u"gen_image 第 5 个实参是补充风格词", len(js) > 4 and js[4].endswith("extra"), str(js))
    check(u"gen_image 第 6 个实参是种子", len(js) > 5 and js[5].endswith("seed"), str(js))

    js = _js_call_args(html, "save_image_gen") or []
    check(u"save_image_gen 第 4 个实参来自后端下拉",
          len(js) > 3 and ("stImgBackend" in js[3] or re.search(
              r"var %s\s*=\s*\(document\.getElementById\('stImgBackend'\)" % re.escape(js[3]),
              html) is not None), str(js))

    check(u"api_state 带出生图后端与上次输入",
          '"image_gen_backend"' in app and '"image_gen_last"' in app)
    check(u"前端把上次输入回填进面板", "applyGenLast(s.image_gen_last)" in html)
    check(u"面板有重抽按钮与提示区", 'id="genReroll"' in html and 'id="genNote"' in html)
    check(u"设置里有预设编辑器与后端下拉",
          'id="stPresetText"' in html and 'id="stImgBackend"' in html)
    check(u"生图预设文件名与引擎一致", image_gen.PRESETS_FILE in app)


def main():
    print("=" * 62)
    print(u"生图引擎审计（本地假服务器，不需要外网/Key）")
    print("=" * 62)
    try:
        test_backend_detect()
        test_sizes_and_mime()
        test_presets()
        test_openai()
        test_sdwebui()
        test_comfyui()
        test_pollinations()
        test_dispatch()
        test_web_bridge()
    finally:
        for s in SERVERS:
            try:
                s.shutdown()
                s.server_close()
            except Exception:
                pass
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("IMAGE_GEN_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
