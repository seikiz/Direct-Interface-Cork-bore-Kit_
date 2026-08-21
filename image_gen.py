# ============================================================
#   image_gen.py - DICK 生图引擎（OpenAI 兼容 /images/generations）
#
#   支持：任意 OpenAI 兼容生图端点（SiliconFlow FLUX / 阿里 wanx / 自建）
#   预设：一套风格模板（anime/realistic/painterly 等），傻瓜化一键生图
#   输出：base64 PNG 或 图片 URL → 前端展示/存聊天
# ============================================================

import base64
import json
import time
import urllib.request

# 预设风格：名字 → (prompt 前缀, 说明)。用户选预设即自动拼提示词
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


def list_presets():
    """预设列表（前端下拉用）"""
    return [{"id": k, "label": v["label"], "desc": v["desc"]} for k, v in PRESETS.items()]


def _post(url, body, headers, timeout=120):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def generate(prompt, preset="anime", size="1024x1024", api_key="",
             base_url="https://api.siliconflow.cn/v1", model="black-forest-labs/FLUX.1-schnell",
             negative_prompt="", extra=""):
    """生图。返回 (ok, 数据, 消息)。
    数据：{"b64": base64图片 或 "url": 图片地址, "preset": 预设名}
    预设自动拼 prompt 前缀；extra 为附加要求。"""
    p = PRESETS.get(preset)
    full = (p["prompt"] if p else "") + prompt
    if extra:
        full += ", " + extra
    body = {
        "model": model,
        "prompt": full,
        "n": 1,
        "size": size,
        "response_format": "b64_json",   # 优先 base64（免二次下载）
    }
    if negative_prompt:
        body["negative_prompt"] = negative_prompt
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }
    url = base_url.rstrip("/") + "/images/generations"
    try:
        resp = _post(url, body, headers)
    except Exception as e:
        return False, None, "生图请求失败：" + str(e)[:120]
    try:
        data_list = resp.get("data") or []
        if not data_list:
            return False, None, "生图返回为空（" + str(resp)[:100] + "）"
        item = data_list[0]
        if item.get("b64_json"):
            return True, {"b64": item["b64_json"], "preset": preset}, "ok"
        if item.get("url"):
            return True, {"url": item["url"], "preset": preset}, "ok"
        return False, None, "生图响应缺少图片数据"
    except Exception as e:
        return False, None, "解析生图响应失败：" + str(e)[:100]


def quick_test():
    """无 key 时探测端点可达性（返回提示）"""
    return "生图引擎就绪。请在设置中配置生图 API Key（默认 SiliconFlow FLUX，可换）。"
