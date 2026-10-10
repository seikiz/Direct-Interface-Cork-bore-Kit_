# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   image_gen.py - DICK 生图引擎（多后端 · 预设可覆盖 · 支持 seed）
#
#   后端按 base_url 自动识别，设置里只改「生图端点」一个字段：
#     ① openai      POST {base}/images/generations
#                   —— 硅基流动 FLUX / 智谱 CogView / 任意兼容中转 / 自建，需要 API Key
#     ② pollinations GET {base}/prompt/<提示词>
#                   —— 【免 Key 免费】，填 https://image.pollinations.ai 即可（图片字节）
#                      免费公共档：间歇性 402（额度/队列），自带一次退避重试
#                      实测（2026-09，seed=777）：9.7 秒返回 59944 字节 JPEG，右下角
#                      **带 pollinations.ai 水印**（nologo=true 去不掉），且请求 1024x1024
#                      实际回的是 768x768 —— 免费档会压尺寸，别拿它当"精确尺寸"后端用
#     ③ sdwebui     POST {base}/sdapi/v1/txt2img
#                   —— 本地 A1111 / Forge / reForge / SD.Next / Fooocus-API，免 Key
#                      端点填 http://127.0.0.1:7860 即可
#     ④ comfyui     POST {base}/prompt + 轮询 /history + 取 /view
#                   —— 本地 ComfyUI（默认 8188），免 Key；「生图模型」填 checkpoint 文件名
#
#   预设：内置 6 套 + 用户覆盖（数据目录下 image_presets.json，同名 id 覆盖内置）
#   seed：留空=让后端随机；填了就透传（Pollinations / A1111 / ComfyUI / 兼容端点都支持）
#   输出：{"b64"|"url", "mime", "preset", "seed"} → 前端展示 / 存聊天
# ============================================================

import base64
import json
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

PRESETS_FILE = "image_presets.json"

BACKENDS = ("openai", "pollinations", "sdwebui", "comfyui")

# 后端识别关键字（base_url 里出现即命中）；顺序有意义：先具体后笼统
BACKEND_HINTS = (
    ("pollinations", ("pollinations",)),
    ("comfyui", ("comfyui", ":8188")),
    ("sdwebui", ("sdwebui", "a1111", "automatic1111", "forge", "fooocus", ":7860")),
)


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


def _split_size(size, default=1024):
    """'1024x1024' → (1024, 1024)；解析不了就用默认值。"""
    try:
        w, h = str(size).lower().split("x")
        return int(w), int(h)
    except Exception:
        return default, default


def _mime_of(raw):
    if raw[:2] == b"\xff\xd8":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


# ---------- 预设：内置 + 用户覆盖 ----------
# 内置风格：名字 → prompt 前缀 + 说明。用户选预设即自动拼提示词。
PRESETS = {
    "anime": {
        "label": "动漫风",
        "prompt": "anime style, clean line art, vibrant colors, detailed eyes, ",
        "desc": "日式动漫插画风，适合角色立绘",
    },
    "realistic": {
        "label": "写实风",
        "prompt": "photorealistic, 8k, detailed skin texture, natural lighting, ",
        "desc": "照片级写实，适合场景/人像",
    },
    "painterly": {
        "label": "厚涂油画",
        "prompt": "oil painting style, thick brush strokes, warm palette, ",
        "desc": "油画厚涂风，氛围感强",
    },
    "chibi": {
        "label": "Q版",
        "prompt": "chibi style, cute, big head small body, simple background, ",
        "desc": "Q版可爱风，适合头像/表情",
    },
    "cyberpunk": {
        "label": "赛博朋克",
        "prompt": "cyberpunk, neon lights, rain, futuristic city, high contrast, ",
        "desc": "赛博朋克霓虹风",
    },
    "watercolor": {
        "label": "水彩",
        "prompt": "watercolor painting, soft edges, pastel colors, paper texture, ",
        "desc": "水彩清新风",
    },
}


def presets_path(base_dir):
    return os.path.join(base_dir or ".", PRESETS_FILE)


def load_presets(base_dir=None):
    """内置预设 + 用户覆盖。返回 {id: {label, prompt, desc, custom?}}。

    用户文件 image_presets.json 支持两种写法：
      · 完整写法：{"guofeng": {"label": "国风线稿", "prompt": "chinese ink line art, ", "desc": "…"}}
      · 简写：    {"guofeng": "chinese ink line art, "}
    下划线开头的键（如 "_说明"）会跳过，方便在文件里写注释。
    """
    out = {k: dict(v) for k, v in PRESETS.items()}
    path = presets_path(base_dir)
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except Exception:
        return out
    if not isinstance(user, dict):
        return out
    for k, v in user.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, str) and v.strip():
            out[k] = {"label": k, "prompt": v, "desc": "（自定义）", "custom": True}
        elif isinstance(v, dict) and str(v.get("prompt") or "").strip():
            base = out.get(k, {})
            out[k] = {
                "label": v.get("label") or base.get("label") or k,
                "prompt": v["prompt"],
                "desc": v.get("desc") or base.get("desc") or "（自定义）",
                "custom": True,
            }
    return out


def save_presets(base_dir, obj):
    """写用户覆盖文件。返回 (ok, 消息)。传 {} 即恢复内置默认。

    兼容线内"老程序读新文件"是允许发生的（用户回退一次），所以写回时**保留不认识的键**：
      · 下划线开头的顶层键（用户手写的注释）原样留着；
      · 预设对象里本版不认识的字段（将来版本加的、或用户手加的）原样留着。
    否则回退一次就永久丢掉 —— 与三层配置、世界记忆那几处是同一类问题。
    """
    if not isinstance(obj, dict):
        return False, "预设必须是一个 JSON 对象"
    # 磁盘上那一份：用来把"本版不认识的东西"带回去。
    # 注意要点：调用方通常是 `load_presets()` 的**合并视图**（只有 label/prompt/desc/custom），
    # 所以不认识的键在到达这里之前就已经被它滤掉了 —— 只靠 obj 保留不住，
    # 必须从磁盘原件补回来（与三层配置、世界记忆那几处同一类问题）。
    disk = {}
    try:
        with open(presets_path(base_dir), encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            disk = got
    except Exception:
        disk = {}
    clean = {}
    for k, v in obj.items():
        if str(k).startswith("_"):
            clean[k] = v          # 注释键：不当预设，也不许丢
            continue
        if isinstance(v, str):
            if not v.strip():
                return False, "预设「%s」的提示词是空的" % k
            clean[k] = v
        elif isinstance(v, dict):
            if not str(v.get("prompt") or "").strip():
                return False, "预设「%s」缺少 prompt 字段" % k
            item = {"prompt": v["prompt"]}
            for f in ("label", "desc"):
                if v.get(f):
                    item[f] = v[f]
            old = disk.get(k)
            for f, fv in (old if isinstance(old, dict) else {}).items():
                if f not in item:              # 磁盘原件里本版不认识的字段
                    item[f] = fv
            for f, fv in v.items():            # 调用方多给的字段（也不许丢）
                if f not in item:
                    item[f] = fv
            clean[k] = item
        else:
            return False, "预设「%s」的格式不对（应为字符串或对象）" % k
    for k, v in disk.items():                  # 顶层注释键：磁盘上有就带走
        if str(k).startswith("_") and k not in clean:
            clean[k] = v
    try:
        with open(presets_path(base_dir), "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return False, "写入失败：" + str(e)[:120]
    return True, "已保存 %d 个自定义预设" % len(clean)


def user_presets_json(base_dir):
    """给设置面板的编辑器看：用户覆盖文件的原始内容（没有就返回空对象）。"""
    path = presets_path(base_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def list_presets(presets=None):
    """预设列表（前端下拉用）。presets 传 load_presets() 的结果即可带上用户预设。"""
    src = presets or PRESETS
    return [{"id": k, "label": v.get("label", k), "desc": v.get("desc", ""),
             "custom": bool(v.get("custom"))} for k, v in src.items()]


def _post(url, body, headers, timeout=300):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "DICK/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- ② Pollinations（免 Key 免费）----------
def _pollinations_bytes(base_url, full_prompt, size, model, seed=None,
                        timeout=180, attempts=2):
    """GET {base}/prompt/<提示词>?width=&height=&nologo=true —— 回的是图片本身，不是 JSON。

    两个实测坑（别踩回去）：
      · `private=true` 是【付费档】参数，带上必返 402 Payment Required；
      · 免费档【间歇性可用】：需要真生成时可能返 402/429（额度/队列），
        命中它缓存的图则直接 200 —— 偶发失败是常态，所以带退避重试 + 明确报错。
    """
    w, h = _split_size(size)
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
            raw = _get(url, timeout=timeout)
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
            time.sleep(8)      # 免费档限流：退避一下再试一次
    return False, None, "免 Key 生图失败：" + last


# ---------- ③ 本地 A1111 / Forge / SD.Next ----------
def _sdwebui_bytes(base_url, full_prompt, negative_prompt, size, seed=None, timeout=600):
    """POST {base}/sdapi/v1/txt2img → {"images": ["<base64>", ...]}（可能是 dataURL 前缀）"""
    w, h = _split_size(size, 512)
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
        resp = _post(url, body, {"Content-Type": "application/json"}, timeout=timeout)
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


# ---------- ④ 本地 ComfyUI ----------
def _comfyui_workflow(ckpt, full_prompt, negative_prompt, w, h, seed, steps=20, cfg=7.0):
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


def _comfyui_bytes(base_url, full_prompt, negative_prompt, size, model=None,
                   seed=None, timeout=600, poll_interval=1.0):
    """POST {base}/prompt → 轮询 {base}/history/<id> → GET {base}/view 取图。"""
    base = base_url.rstrip("/")
    m = (model or "").strip()
    if not m.lower().endswith((".safetensors", ".ckpt", ".sft")):
        m = "v1-5-pruned-emaonly.safetensors"      # 猜一个常见的；不行会把提示写进报错
    w, h = _split_size(size, 512)
    if seed in (None, ""):
        seed = int(time.time() * 1000) % 2 ** 31
    wf = _comfyui_workflow(m, full_prompt, negative_prompt, w, h, int(seed))
    client_id = uuid.uuid4().hex
    try:
        resp = _post(base + "/prompt", {"prompt": wf, "client_id": client_id},
                     {"Content-Type": "application/json"})
    except Exception as e:
        return False, None, ("连不上本地 ComfyUI：%s（确认已启动，端口默认 8188）" % str(e)[:100])
    pid = resp.get("prompt_id")
    if not pid:
        return False, None, ("ComfyUI 没给 prompt_id（多为 checkpoint 名不对）：%s"
                             % str(resp)[:140])
    deadline = time.time() + timeout
    info = None
    while time.time() < deadline:
        time.sleep(poll_interval)
        try:
            hist = json.loads(_get("%s/history/%s" % (base, pid), timeout=30).decode("utf-8"))
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
                return True, _get(base + "/view?" + q, timeout=60), "ok"
            except Exception as e:
                return False, None, "取图失败：" + str(e)[:100]
    return False, None, "ComfyUI 输出里没有图片节点"


# ---------- ① OpenAI 兼容 ----------
def _openai_generate(base_url, full_prompt, negative_prompt, size, model, api_key, seed, preset,
                     timeout=300):
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
        resp = _post(url, body, headers, timeout=timeout)
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


def generate(prompt, preset="anime", size="1024x1024", api_key="",
             base_url="https://api.siliconflow.cn/v1", model="black-forest-labs/FLUX.1-schnell",
             negative_prompt="", extra="", seed=None, presets=None, backend="auto", timeout=None):
    """生图。返回 (ok, 数据, 消息)。数据：{"b64"|"url", "mime", "preset", "seed"}。

    预设自动拼 prompt 前缀；extra 追加在内容之后（风格词放这里，别塞进内容里）。
    backend='auto' 时按端点自动认后端；timeout 留空用各后端默认（本地显卡慢就调大）。
    """
    table = presets or PRESETS
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
        ok, raw, msg = _pollinations_bytes(base_url, full, size, model, seed,
                                           timeout=timeout or 180)
        if not ok:
            return False, None, msg
        note = "ok" if not negative_prompt else "ok（该后端不支持负面提示词，已忽略）"
        return True, {"b64": base64.b64encode(raw).decode("ascii"), "preset": preset,
                      "mime": _mime_of(raw), "seed": seed}, note

    if be == "sdwebui":
        ok, raw, msg = _sdwebui_bytes(base_url, full, negative_prompt, size, seed,
                                      timeout=timeout or 600)
        if not ok:
            return False, None, msg
        return True, {"b64": base64.b64encode(raw).decode("ascii"), "preset": preset,
                      "mime": _mime_of(raw), "seed": seed}, "ok"

    if be == "comfyui":
        ok, raw, msg = _comfyui_bytes(base_url, full, negative_prompt, size, model, seed,
                                      timeout=timeout or 600)
        if not ok:
            return False, None, msg
        return True, {"b64": base64.b64encode(raw).decode("ascii"), "preset": preset,
                      "mime": _mime_of(raw), "seed": seed}, "ok"

    return _openai_generate(base_url, full, negative_prompt, size, model, api_key, seed, preset,
                            timeout=timeout or 300)


def quick_test():
    """给设置面板/自检看的一句话提示"""
    return ("生图引擎就绪。端点决定后端（也可在「生图后端」里手选）：OpenAI 兼容"
            "（硅基流动/智谱…需 Key）· https://image.pollinations.ai（免 Key 免费，有限流）· "
            "http://127.0.0.1:7860（本地 A1111/Forge）· http://127.0.0.1:8188（本地 ComfyUI）")
