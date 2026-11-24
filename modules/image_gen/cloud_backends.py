# -*- coding: utf-8 -*-
"""modules/image_gen/cloud_backends.py —— Google Gemini / Imagen 与 OpenAI GPT Image 协议。

为什么单独拆文件：
  · modules/image_gen/backends.py 已接近 400 行软预算；
  · Gemini（:generateContent / :predict）与 OpenAI 官方 gpt-image-* 的请求体、
    尺寸约束和鉴权头都与通用 OpenAI 兼容网关（硅基流动/智谱）不同：
      - Gemini 用 x-goog-api-key 与 inlineData；
      - gpt-image-1 拒绝 response_format / negative_prompt / seed，且只吃 1024/1536 档尺寸。
"""

import base64
import json
import urllib.error

DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-image"
DEFAULT_GPT_BASE = "https://api.openai.com/v1"
DEFAULT_GPT_MODEL = "gpt-image-1"


def _split_size(size, default=1024):
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


def _http_err_detail(err):
    detail = ""
    try:
        raw = err.read().decode("utf-8", "ignore")
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                eobj = obj.get("error")
                if isinstance(eobj, dict) and eobj.get("message"):
                    detail = str(eobj["message"])
                elif eobj:
                    detail = str(eobj)
                elif obj.get("message"):
                    detail = str(obj["message"])
        except Exception:
            detail = raw
    except Exception:
        pass
    return detail.replace("\n", " ").strip()[:140]


def _human_http_err(prefix, code, detail):
    hints = {
        400: "请求参数被拒",
        401: "API Key 无效或未授权",
        402: "余额不足",
        403: "无权访问该模型或地区受限",
        404: "模型名或接口地址不对",
        429: "触发限流或额度耗尽",
    }
    label = hints.get(code) or ("服务端异常" if 500 <= code <= 599 else "请求失败")
    tail = ("：" + detail) if detail else ""
    return "%s失败：HTTP %d %s%s" % (prefix, code, label, tail)


def aspect_ratio_of(size):
    """把 WxH 映射成 Gemini / Imagen 合法宽高比。"""
    w, h = _split_size(size, 1024)
    if w <= 0 or h <= 0 or w == h:
        return "1:1"
    ratio = float(w) / float(h)
    if ratio >= 1.55:
        return "16:9"
    if ratio >= 1.15:
        return "4:3"
    if ratio <= 0.65:
        return "9:16"
    if ratio <= 0.87:
        return "3:4"
    return "1:1"


def gpt_size_of(size, model):
    """把 UI 尺寸映射到 OpenAI 官方模型合法尺寸（避免 1024x768 触发 400）。"""
    m = (model or "").lower()
    w, h = _split_size(size, 1024)
    if m.startswith("dall-e-2"):
        if w <= 256 and h <= 256:
            return "256x256"
        if w <= 512 and h <= 512:
            return "512x512"
        return "1024x1024"
    if m.startswith("dall-e-3"):
        if w > h:
            return "1792x1024"
        if h > w:
            return "1024x1792"
        return "1024x1024"
    # gpt-image-1 / gpt-image-1.5 / gpt-image-1-mini
    if w > h:
        return "1536x1024"
    if h > w:
        return "1024x1536"
    return "1024x1024"


def _merge_negative(full_prompt, negative_prompt):
    neg = (negative_prompt or "").strip()
    if not neg:
        return full_prompt
    return "%s\nAvoid: %s" % (full_prompt, neg)


def _norm_gemini_base(base_url):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return DEFAULT_GEMINI_BASE
    # 用户常把聊天用的 .../v1beta/openai 粘进来，这里自动还原为原生 REST 根
    if base.lower().endswith("/openai"):
        base = base[:-7].rstrip("/")
    if base.lower().endswith("generativelanguage.googleapis.com"):
        base = base + "/v1beta"
    return base


def _extract_gemini_image(resp):
    """从 generateContent 响应中提取第一张 inlineData / inline_data 图片。"""
    for cand in (resp.get("candidates") or []):
        parts = ((cand or {}).get("content") or {}).get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                b64 = str(inline["data"]).strip()
                mime = str(inline.get("mimeType") or inline.get("mime_type") or "").strip()
                if not mime:
                    try:
                        mime = _mime_of(base64.b64decode(b64[:64]))
                    except Exception:
                        mime = "image/png"
                return b64, mime
    return None, None


def gemini_generate(net, base_url, full_prompt, negative_prompt, size, model, api_key, seed,
                    preset, timeout=300):
    """Google Gemini 原生生图（:generateContent）与 Imagen（:predict）。"""
    base = _norm_gemini_base(base_url)
    m = (model or "").strip()
    if not m or "/" in m:
        m = DEFAULT_GEMINI_MODEL
    if m.startswith("models/"):
        m = m[7:]
    ratio = aspect_ratio_of(size)
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    # 分支 A：Imagen 系列走 :predict
    if m.lower().startswith("imagen"):
        url = "%s/models/%s:predict" % (base, m)
        params = {"sampleCount": 1, "aspectRatio": ratio}
        if negative_prompt:
            params["negativePrompt"] = negative_prompt
        body = {"instances": [{"prompt": full_prompt}], "parameters": params}
        try:
            resp = net.post(url, body, headers, timeout=timeout)
        except urllib.error.HTTPError as e:
            return False, None, _human_http_err("Gemini Imagen 生图", e.code, _http_err_detail(e))
        except Exception as e:
            return False, None, "Gemini Imagen 生图失败：" + str(e)[:120]
        preds = resp.get("predictions") or []
        if preds and isinstance(preds[0], dict) and preds[0].get("bytesBase64Encoded"):
            b64 = str(preds[0]["bytesBase64Encoded"]).strip()
            mime = str(preds[0].get("mimeType") or "image/png")
            return True, {"b64": b64, "preset": preset, "mime": mime, "seed": seed}, "ok"
        return False, None, "Gemini Imagen 响应里没有图片数据"

    # 分支 B：Gemini 原生多模态生图走 :generateContent
    url = "%s/models/%s:generateContent" % (base, m)
    prompt_text = _merge_negative(full_prompt, negative_prompt)
    gen_cfg = {
        "responseModalities": ["TEXT", "IMAGE"],
        "imageConfig": {"aspectRatio": ratio},
    }
    body = {"contents": [{"parts": [{"text": prompt_text}]}], "generationConfig": gen_cfg}
    try:
        resp = net.post(url, body, headers, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            # 早期 Gemini 生图模型不认 imageConfig → 去掉后自动重试一次
            body2 = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            }
            try:
                resp = net.post(url, body2, headers, timeout=timeout)
            except urllib.error.HTTPError as e2:
                return False, None, _human_http_err("Gemini 生图", e2.code, _http_err_detail(e2))
            except Exception as e2:
                return False, None, "Gemini 生图失败：" + str(e2)[:120]
        else:
            return False, None, _human_http_err("Gemini 生图", e.code, _http_err_detail(e))
    except Exception as e:
        return False, None, "Gemini 生图失败：" + str(e)[:120]

    b64, mime = _extract_gemini_image(resp or {})
    if b64:
        return True, {"b64": b64, "preset": preset, "mime": mime or "image/png", "seed": seed}, "ok"
    return False, None, "Gemini 未返回图片（确认模型支持生图，如 gemini-2.5-flash-image）"


def gpt_generate(net, base_url, full_prompt, negative_prompt, size, model, api_key, seed,
                 preset, timeout=300):
    """OpenAI 官方 GPT Image（gpt-image-1 / 1.5 / mini）与 DALL-E 生图协议。"""
    base = (base_url or "").strip().rstrip("/") or DEFAULT_GPT_BASE
    m = (model or "").strip()
    if not m or "/" in m:
        m = DEFAULT_GPT_MODEL
    eff_size = gpt_size_of(size, m)
    prompt_text = _merge_negative(full_prompt, negative_prompt)
    body = {
        "model": m,
        "prompt": prompt_text,
        "n": 1,
        "size": eff_size,
    }
    # gpt-image-* 始终返回 b64_json，传 response_format 反而触发 HTTP 400；dall-e-* 才传
    if not m.lower().startswith("gpt-image"):
        body["response_format"] = "b64_json"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}
    url = base + "/images/generations"
    try:
        resp = net.post(url, body, headers, timeout=timeout)
    except urllib.error.HTTPError as e:
        return False, None, _human_http_err("GPT 生图", e.code, _http_err_detail(e))
    except Exception as e:
        return False, None, "GPT 生图失败：" + str(e)[:120]
    data_list = (resp or {}).get("data") or []
    if not data_list:
        return False, None, "GPT 生图返回为空（" + str(resp)[:100] + "）"
    item = data_list[0]
    if item.get("b64_json"):
        b64 = str(item["b64_json"]).strip()
        try:
            mime = _mime_of(base64.b64decode(b64[:64]))
        except Exception:
            mime = "image/png"
        return True, {"b64": b64, "preset": preset, "mime": mime, "seed": seed}, "ok"
    if item.get("url"):
        return True, {"url": item["url"], "preset": preset, "mime": "", "seed": seed}, "ok"
    return False, None, "GPT 生图响应缺少图片数据"
