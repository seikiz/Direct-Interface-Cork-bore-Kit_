# -*- coding: utf-8 -*-
"""modules/image_gen/backends.py —— 四个后端的协议实现（纯 HTTP，无界面、无宿主）

搬家来源：仓库根 `image_gen.py` 的 `_pollinations_bytes` / `_sdwebui_bytes` /
`_comfyui_workflow` / `_comfyui_bytes` / `_openai_generate` / `generate`，
**协议与文案一字未改**，只把"怎么发请求"收进一个可替换的 `Net`：

    · 生产环境：`Net(host=…)` —— 代理/时钟从宿主（壳层门面）取；
    · 自检：     `FakeNet` —— 同一个接口，回放预先编好的响应，一条 socket 都不开。

`Net` 的三件事（宿主能力，ARCHITECTURE.md 十二）：
    sleep / now  → 退避与超时判定的时钟（测试可以整块换掉，不必真等 8 秒）；
    proxy        → 网络代理（宿主没给就走 urllib 默认，即环境变量那套）；
    log          → 失败时的排障日志（可选）。

后端识别顺序有意义：先具体后笼统（comfyui 的 :8188 不能被 sdwebui 的 forge 抢走）。
"""

import base64
import json
import time as _time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import presets as presets_mod

BACKENDS = ("openai", "pollinations", "sdwebui", "comfyui")

# 后端识别关键字（base_url 里<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌出现即命中）；顺序有意义：先具体后笼统
BACKEND_HINTS = (
    ("pollinations", ("pollinations",)),
    ("comfyui", ("comfyui", ":8188")),
    ("sdwebui", ("sdwebui", "a1111", "automatic1111", "forge", "fooocus", ":7860")),
)

USER_AGENT = "DICK/2.0"


# ================================================================ 网络通道
class Net(object):
    """发请求 + 等时间 + 读代理：块里唯一碰网络的地方。

    `host` 是宿主（壳层门面）模块对象；一切能力**在用时才取**，
    所以宿主运行中换掉 `host.time` / `host.proxy` 也能生效（测试就靠这个跳过退避）。
    """

    def __init__(self, host=None, proxy="", log=None):
        self.host = host
        self.proxy = proxy
        self.log = log
        self._opener_cache = None

    # ---- 宿主能力 ----
    def clock(self):
        return getattr(self.host, "time", None) or _time

    def sleep(self, seconds):
        try:
            self.clock().sleep(seconds)
        except Exception:
            pass

    def now(self):
        try:
            return float(self.clock().time())
        except Exception:
            return _time.time()

    def proxy_of(self):
        return getattr(self.host, "proxy", "") or self.proxy or ""

    def _opener(self):
        proxy = self.proxy_of()
        if not proxy:
            return urllib.request.urlopen          # 默认行为：环境变量代理
        if self._opener_cache is None:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            self._opener_cache = urllib.request.build_opener(handler).open
        return self._opener_cache

    def _note(self, msg):
        log = self.log or getattr(self.host, "log", None)
        if log is not None:
            try:
                log.warn(msg, "image_gen")
            except Exception:
                pass

    # ---- 两个动词 ----
    def post(self, url, body, headers, timeout=300):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with self._opener()(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def get(self, url, timeout=60):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with self._opener()(req, timeout=timeout) as r:
            return r.read()


# ================================================================ 后端识别
def backend_of(base_url):
    """按 base_url 判断后端：'pollinations' | 'comfyui' | 'sdwebui' | 'openai'。"""
    u = (base_url or "").lower()
    for name, hints in BACKEND_HINTS:
        if any(h in u for h in hints):
            return name
    return "openai"


def resolve_backend(base_url, backend="auto"):
    """设置里显式选了后端就用它，否则按端点自动认。
    （显式选择是给「ComfyUI 不在 8188」「本地 SD 走局域网别的端口」这类情况留的后路）"""
    b = (backend or "auto").strip().lower()
    return b if b in BACKENDS else backend_of(base_url)


def needs_key(base_url, backend="auto"):
    """这个后端要不要 API Key（三种本地/免费后端都留空即可）。"""
    return resolve_backend(base_url, backend) == "openai"


def split_size(size, default=1024):
    """'1024x1024' → (1024, 1024)；解析不了就用默认值。"""
    try:
        w, h = str(size).lower().split("x")
        return int(w), int(h)
    except Exception:
        return default, default


def mime_of(raw):
    if raw[:2] == b"\xff\xd8":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


# ================================================================ ② Pollinations（免 Key 免费）
def pollinations_bytes(net, base_url, full_prompt, size, model, seed=None,
                       timeout=180, attempts=2):
    """GET {base}/prompt/<提示词>?width=&height=&nologo=true —— 回的是图片本身，不是 JSON。

    两个实测坑（别踩回去）：
      · `private=true` 是【付费档】参数，带上必返 402 Payment Required；
      · 免费档【间歇性可用】：需要真生成时可能返 402/429（额度/队列），
        命中它缓存的图则直接 200 —— 偶发失败是常态，所以带退避重试 + 明确报错。
    """
    w, h = split_size(size)
    params = {"width": str(w), "height": str(h), "nologo": "true"}
    m = (model or "").strip()
    # 只透传简单模型名（flux / turbo 这类）；"厂商/模型" 那种路径传给它会被拒
    # （默认的 siliconflow 模型名恰好是 "black-forest-labs/FLUX.1-schnell" → 不传更稳）
    if m and "/" not in m:
        params["model"] = m
    if seed not in (None, ""):
        params["seed"] = str(seed)
    url = (base_url.rstrip("/") + "/prompt/" + urllib.parse.quote(full_prompt, safe="")
           + "?" + urllib.parse.urlencode(params))
    last = ""
    for i in range(max(1, attempts)):
        try:
            raw = net.get(url, timeout=timeout)
            if not raw or len(raw) < 512:
                return False, None, "免 Key 生图返回内容过小（%d 字节）" % len(raw or b"")
            return True, raw, "ok"
        except urllib.error.HTTPError as e:
            if e.code in (402, 429):
                last = ("免费额度被限流（HTTP %d）：等十几秒再试；"
                        "要稳定出图请在设置里填一个生图 Key（硅基流动 / 智谱 CogView）" % e.code)
            else:
                last = "HTTP %d" % e.code
        except Exception as e:
            last = str(e)[:120]
        if i + 1 < attempts:
            net.sleep(8)      # 免费档限流：退避一下再试一次
    return False, None, "免 Key 生图失败：" + last


# ================================================================ ③ 本地 A1111 / Forge / SD.Next
def sdwebui_bytes(net, base_url, full_prompt, negative_prompt, size, seed=None, timeout=600):
    """POST {base}/sdapi/v1/txt2img → {"images": ["<base64>", ...]}（可能是 dataURL 前缀）"""
    w, h = split_size(size, 512)
    body = {
        "prompt": full_prompt,
        "negative_prompt": negative_prompt or "",
        "width": w, "height": h,
        "steps": 20, "cfg_scale": 7,
        "batch_size": 1, "n_iter": 1,
    }
    if seed not in (None, ""):
        body["seed"] = int(seed)
    url = base_url.rstrip("/") + "/sdapi/v1/txt2img"
    try:
        resp = net.post(url, body, {"Content-Type": "application/json"}, timeout=timeout)
    except urllib.error.HTTPError as e:
        return False, None, "本地 SD 返回 HTTP %d（端点应为 A1111 风格 /sdapi/v1/txt2img）" % e.code
    except Exception as e:
        return False, None, ("连不上本地 SD：%s（确认已启动 WebUI 并开了 --api）" % str(e)[:100])
    imgs = resp.get("images") or []
    if not imgs:
        return False, None, "本地 SD 没返回图片（" + str(resp)[:100] + "）"
    b64 = str(imgs[0]).split(",", 1)[-1]
    try:
        return True, base64.b64decode(b64), "ok"
    except Exception as e:
        return False, None, "本地 SD 返回的图片解不开：" + str(e)[:100]


# ================================================================ ④ 本地 ComfyUI
def comfyui_workflow(ckpt, full_prompt, negative_prompt, w, h, seed, steps=20, cfg=7.0):
    """最小标准工作流：CheckpointLoader→CLIP×2→KSampler→VAEDecode→SaveImage。
    只吃 SD1.5/SDXL 这类常规 checkpoint；自定义节点的复杂工作流不在支持范围内。"""
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode",
              "inputs": {"text": full_prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative_prompt or "", "clip": ["4", 1]}},
        "3": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                         "model": ["4", 0], "positive": ["6", 0],
                         "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "dick", "images": ["8", 0]}},
    }


def comfyui_bytes(net, base_url, full_prompt, negative_prompt, size, model=None,
                  seed=None, timeout=600, poll_interval=1.0):
    """POST {base}/prompt → 轮询 {base}/history/<id> → GET {base}/view 取图。"""
    base = base_url.rstrip("/")
    m = (model or "").strip()
    if not m.lower().endswith((".safetensors", ".ckpt", ".sft")):
        m = "v1-5-pruned-emaonly.safetensors"      # 猜一个常见的；不行会把提示写进报错
    w, h = split_size(size, 512)
    if seed in (None, ""):
        seed = int(net.now() * 1000) % 2 ** 31
    wf = comfyui_workflow(m, full_prompt, negative_prompt, w, h, int(seed))
    client_id = uuid.uuid4().hex
    try:
        resp = net.post(base + "/prompt", {"prompt": wf, "client_id": client_id},
                        {"Content-Type": "application/json"})
    except Exception as e:
        return False, None, ("连不上本地 ComfyUI：%s（确认已启动，端口默认 8188）" % str(e)[:100])
    pid = resp.get("prompt_id")
    if not pid:
        return False, None, ("ComfyUI 没给 prompt_id（多为 checkpoint 名不对）：%s"
                             % str(resp)[:140])
    deadline = net.now() + timeout
    info = None
    while net.now() < deadline:
        net.sleep(poll_interval)
        try:
            hist = json.loads(net.get("%s/history/%s" % (base, pid), timeout=30).decode("utf-8"))
        except Exception:
            continue
        rec = (hist or {}).get(pid)
        if rec and rec.get("outputs"):
            info = rec["outputs"]
            break
    if not info:
        return False, None, "ComfyUI 超时没出图（%d 秒）；检查 checkpoint 名与控制台报错" % timeout
    for node_out in info.values():
        for img in (node_out.get("images") or []):
            q = urllib.parse.urlencode({
                "filename": img.get("filename", ""),
                "subfolder": img.get("subfolder", ""),
                "type": img.get("type", "output"),
            })
            try:
                return True, net.get(base + "/view?" + q, timeout=60), "ok"
            except Exception as e:
                return False, None, "取图失败：" + str(e)[:100]
    return False, None, "ComfyUI 输出里没有图片节点"


# ================================================================ ① OpenAI 兼容
def openai_generate(net, base_url, full_prompt, negative_prompt, size, model, api_key, seed,
                    preset, timeout=300):
    body = {
        "model": model,
        "prompt": full_prompt,
        "n": 1,
        "size": size,
        "response_format": "b64_json",   # 优先 base64（免二次下载）
    }
    if negative_prompt:
        body["negative_prompt"] = negative_prompt
    if seed not in (None, ""):
        body["seed"] = int(seed)
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    url = base_url.rstrip("/") + "/images/generations"
    try:
        resp = net.post(url, body, headers, timeout=timeout)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:120]
        except Exception:
            pass
        return False, None, "生图请求失败：HTTP %d %s" % (e.code, detail)
    except Exception as e:
        return False, None, "生图请求失败：" + str(e)[:120]
    data_list = resp.get("data") or []
    if not data_list:
        return False, None, "生图返回为空（" + str(resp)[:100] + "）"
    item = data_list[0]
    if item.get("b64_json"):
        return True, {"b64": item["b64_json"], "preset": preset, "mime": "image/png",
                      "seed": seed}, "ok"
    if item.get("url"):
        return True, {"url": item["url"], "preset": preset, "mime": "", "seed": seed}, "ok"
    return False, None, "生图响应缺少图片数据"


# ================================================================ 分发
def generate(net, prompt, preset="anime", size="1024x1024", api_key="",
             base_url="https://api.siliconflow.cn/v1",
             model="black-forest-labs/FLUX.1-schnell",
             negative_prompt="", extra="", seed=None, presets=None, backend="auto",
             timeout=None):
    """生图。返回 (ok, 数据, 消息)。数据：{"b64"|"url", "mime", "preset", "seed"}。

    预设自动拼 prompt 前缀；extra 追加在内容之后（风格词放这里，别塞进内容里）。
    backend='auto' 时按端点自动认后端；timeout 留空用各后端默认（本地显卡慢就调大）。
    """
    table = presets or presets_mod.PRESETS
    p = table.get(preset) or table.get("anime") or {}
    if isinstance(p, dict):
        base_prefix = p.get("prompt", "")
    elif isinstance(p, str):
        base_prefix = p              # 容忍 {"anime": "前缀, "} 这种简写
    else:
        base_prefix = ""
    full = base_prefix + (prompt or "")
    if extra:
        full += ", " + extra
    be = resolve_backend(base_url, backend)

    if be == "pollinations":
        ok, raw, msg = pollinations_bytes(net, base_url, full, size, model, seed,
                                          timeout=timeout or 180)
        if not ok:
            return False, None, msg
        note = "ok" if not negative_prompt else "ok（该后端不支持负面提示词，已忽略）"
        return True, {"b64": base64.b64encode(raw).decode("ascii"), "preset": preset,
                      "mime": mime_of(raw), "seed": seed}, note

    if be == "sdwebui":
        ok, raw, msg = sdwebui_bytes(net, base_url, full, negative_prompt, size, seed,
                                     timeout=timeout or 600)
        if not ok:
            return False, None, msg
        return True, {"b64": base64.b64encode(raw).decode("ascii"), "preset": preset,
                      "mime": mime_of(raw), "seed": seed}, "ok"

    if be == "comfyui":
        ok, raw, msg = comfyui_bytes(net, base_url, full, negative_prompt, size, model, seed,
                                     timeout=timeout or 600)
        if not ok:
            return False, None, msg
        return True, {"b64": base64.b64encode(raw).decode("ascii"), "preset": preset,
                      "mime": mime_of(raw), "seed": seed}, "ok"

    return openai_generate(net, base_url, full, negative_prompt, size, model, api_key, seed,
                           preset, timeout=timeout or 300)
