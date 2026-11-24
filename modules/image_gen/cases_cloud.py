# -*- coding: utf-8 -*-
"""modules/image_gen/cases_cloud.py —— Gemini / Imagen 与 OpenAI GPT Image 块自检用例。"""

import base64

from .harness import FakeNet, JPG, PNG, _contains, _eq, _svc, _true, http_error


def case_gemini_generate_content():
    """Gemini 原生生图：/openai 后缀自动剥离、x-goog-api-key、宽高比映射、inlineData 提取。"""
    b64_png = base64.b64encode(PNG).decode("ascii")
    net = FakeNet(post_handler=lambda u, b: {
        "candidates": [{"content": {"parts": [
            {"text": "here is your image"},
            {"inlineData": {"mimeType": "image/png", "data": b64_png}},
        ]}}]
    })
    svc = _svc(net)
    ok, data, msg = svc.generate(
        "夕阳猫", preset="anime", size="1024x768", api_key="AIza-test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-2.5-flash-image", negative_prompt="模糊", backend="auto",
    )
    _true(ok and data and base64.b64decode(data["b64"]) == PNG, "Gemini 出图: " + str(msg))
    _eq(data["mime"], "image/png", "mime")
    rec = net.posts[0]
    _eq(rec["url"], "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent",
        "剥离 /openai 并拼 :generateContent")
    _eq(rec["headers"].get("x-goog-api-key"), "AIza-test", "走 Header x-goog-api-key")
    _eq(rec["body"]["generationConfig"]["imageConfig"]["aspectRatio"], "4:3", "1024x768 -> 4:3")
    _contains(rec["body"]["contents"][0]["parts"][0]["text"], "Avoid: 模糊", "负面约束并入 prompt")


def case_gemini_imagen_and_fallback():
    """Imagen :predict 协议 + Gemini imageConfig 400 自动降级重试。"""
    b64_jpg = base64.b64encode(JPG).decode("ascii")
    net_im = FakeNet(post_handler=lambda u, b: {
        "predictions": [{"bytesBase64Encoded": b64_jpg, "mimeType": "image/jpeg"}]
    })
    ok, data, msg = _svc(net_im).generate(
        "星海", size="768x1024", api_key="AIza-im",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model="imagen-3.0-generate-002", negative_prompt="文字", backend="gemini",
    )
    _true(ok and data and base64.b64decode(data["b64"]) == JPG, "Imagen 出图: " + str(msg))
    _eq(data["mime"], "image/jpeg", "Imagen mime")
    rec = net_im.posts[0]
    _true(rec["url"].endswith("/models/imagen-3.0-generate-002:predict"), "走 :predict")
    _eq(rec["body"]["parameters"]["aspectRatio"], "3:4", "768x1024 -> 3:4")
    _eq(rec["body"]["parameters"]["negativePrompt"], "文字", "Imagen 透传 negativePrompt")

    # imageConfig 返回 400 → 自动去掉 imageConfig 重试一次
    calls = {"n": 0}

    def _fallback_handler(u, b):
        calls["n"] += 1
        if "imageConfig" in (b.get("generationConfig") or {}):
            raise http_error(400, b'{"error":{"message":"Unknown field imageConfig"}}')
        return {"candidates": [{"content": {"parts": [{"inline_data": {"data": b64_jpg}}]}}]}

    net_fb = FakeNet(post_handler=_fallback_handler)
    ok2, data2, msg2 = _svc(net_fb).generate(
        "森林", api_key="AIza-fb",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model="gemini-2.0-flash-exp", backend="gemini",
    )
    _true(ok2 and calls["n"] == 2 and data2["mime"] == "image/jpeg", "imageConfig 400 降级重试: " + str(msg2))


def case_gpt_image_1_and_dalle():
    """GPT Image：不传 response_format/negative_prompt/seed，自动映射合法尺寸；DALL-E 3 传 response_format。"""
    b64_png = base64.b64encode(PNG).decode("ascii")
    net = FakeNet(post_handler=lambda u, b: {"data": [{"b64_json": b64_png}]})
    ok, data, msg = _svc(net).generate(
        "少女", preset="anime", size="1024x768", api_key="sk-gpt",
        base_url="https://api.openai.com/v1", model="gpt-image-1",
        negative_prompt="变形", seed=42, backend="auto",
    )
    _true(ok and data and base64.b64decode(data["b64"]) == PNG, "gpt-image-1 出图: " + str(msg))
    rec = net.posts[0]
    _eq(rec["url"], "https://api.openai.com/v1/images/generations", "OpenAI 官方端点")
    _eq(rec["headers"].get("Authorization"), "Bearer sk-gpt", "Bearer Key")
    _eq(rec["body"]["size"], "1536x1024", "1024x768 映射到合法横版 1536x1024")
    _true("response_format" not in rec["body"] and "negative_prompt" not in rec["body"]
          and "seed" not in rec["body"], "gpt-image-1 不传非法字段")
    _contains(rec["body"]["prompt"], "Avoid: 变形", "负面词并入 prompt")

    # DALL-E 3：横版映射 1792x1024 且带 response_format
    net2 = FakeNet(post_handler=lambda u, b: {"data": [{"url": "https://img.example/1.png"}]})
    ok2, data2, _ = _svc(net2).generate(
        "海边", size="1024x768", api_key="sk-gpt",
        base_url="https://api.openai.com/v1", model="dall-e-3", backend="gpt",
    )
    _true(ok2 and data2["url"] == "https://img.example/1.png", "DALL-E 3 url 通道")
    _eq(net2.posts[0]["body"]["size"], "1792x1024", "DALL-E 3 横版 1792x1024")
    _eq(net2.posts[0]["body"]["response_format"], "b64_json", "DALL-E 3 带 response_format")


def case_cloud_bad_inputs():
    """坏输入：HTTP 401/429 与无图响应都返回可读中文错误，不抛未捕获异常。"""
    net_g401 = FakeNet(post_handler=lambda u, b: (_ for _ in ()).throw(
        http_error(401, b'{"error":{"message":"API key not valid"}}')))
    ok, data, msg = _svc(net_g401).generate(
        "x", api_key="bad", base_url="https://generativelanguage.googleapis.com/v1beta",
        model="gemini-2.5-flash-image", backend="gemini",
    )
    _true((not ok) and data is None and "401" in msg and "API Key" in msg, "Gemini 401 中文报错: " + msg)

    net_gempty = FakeNet(post_handler=lambda u, b: {"candidates": [{"content": {"parts": [{"text": "refused"}]}}]})
    ok2, _, msg2 = _svc(net_gempty).generate(
        "x", api_key="k", base_url="https://generativelanguage.googleapis.com/v1beta", backend="gemini",
    )
    _true((not ok2) and "未返回图片" in msg2, "Gemini 无图返回报错: " + msg2)

    net_o429 = FakeNet(post_handler=lambda u, b: (_ for _ in ()).throw(
        http_error(429, b'{"error":{"message":"Rate limit exceeded"}}')))
    ok3, data3, msg3 = _svc(net_o429).generate(
        "x", api_key="k", base_url="https://api.openai.com/v1", model="gpt-image-1", backend="gpt",
    )
    _true((not ok3) and data3 is None and "429" in msg3 and "限流" in msg3, "GPT 429 中文报错: " + msg3)
