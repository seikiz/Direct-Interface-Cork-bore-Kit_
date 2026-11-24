# -*- coding: utf-8 -*-
"""GALGAME 逻辑改善 & API 优化专项测试。
覆盖：
  1. GAL 选项竞态保护（发新消息/清空后，在途旧线程不覆盖新回合）
  2. GAL 选项写进节点 metadata["gal_options"] + 回档/切分支复原（含 say 字段）
  3. GAL 选项联动角色卡模式（乙女·梦向 choice_role=feeling 口径）+ aff 钳制护栏
  4. 负面好感选项 ROLL 逻辑（crit 减轻惩罚、fail 加重惩罚；正向仍翻倍/反转）
  5. API：本机地址（Ollama/localhost）绝不走云端中转；stream_options 400/422 降级缓存
  6. API：429/503 瞬态重试、友好中文报错格式化、complete_text 统一非流式通道、_fetch_auto_turn on_busy
  7. 安卓端结构核对：GalgamePlugin say 持久化与 genSeq；ChatEngine 真流式、finally 释放锁、stop()、SOCKS5
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from unittest import mock

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "plugins"))

import app_paths
_iso = tempfile.mkdtemp(prefix="dick_gal_api_")
_real_base = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: _iso
app_paths.get_plugin_dirs = lambda: [os.path.join(_real_base, "plugins")]

from DICK_core import ChatCore
from core_fetch import _is_local_url
from galgame_choices_plugin import GalgameChoicesPlugin
import html_app

ok = 0
bad = 0


def check(cond, msg):
    global ok, bad
    if cond:
        ok += 1
        print("  OK " + msg)
    else:
        bad += 1
        print("  FAIL " + msg)


class FakeStatusError(Exception):
    def __init__(self, status_code, msg="err", body=None):
        super().__init__(msg)
        self.status_code = status_code
        self.body = body


def main():
    try:
        print("== ① GAL 选项竞态保护 + 节点持久化/回档复原 ==")
        evt_start = threading.Event()
        evt_release = threading.Event()

        class SlowCore:
            def __init__(self):
                self.model = "m"
                self.is_processing = False
                self.active_roles = [{"name": "咲", "advanced": {"mode": "otome"}}]
                self.captured_system = ""
                n_u = type("N", (), {"id": "u1", "role": "user", "parent_id": None, "metadata": {}})()
                n_a = type("N", (), {"id": "a1", "role": "assistant", "parent_id": "u1", "metadata": {}})()
                n_b = type("N", (), {"id": "a2", "role": "assistant", "parent_id": "u1", "metadata": {}})()
                self.tree = type("T", (), {"nodes": {"u1": n_u, "a1": n_a, "a2": n_b}, "current_leaf_id": "a1"})()
                self.client = object()

            def get_current_chain(self):
                return [{"role": "user", "content": "你好", "metadata": {}},
                        {"role": "assistant", "content": "嗯，我在。", "metadata": {"speaker": "咲"}}]

            def complete_text(self, messages, timeout=60):
                self.captured_system = messages[0]["content"]
                evt_start.set()
                evt_release.wait(timeout=5)
                return json.dumps([
                    {"text": "轻声问候", "say": "「你今天还好吗？」", "result": "她会微笑", "aff": 99},
                    {"text": "沉默不语", "say": "我看着她，没有说话。", "result": "气氛安静", "aff": -99},
                ], ensure_ascii=False)

        sc = SlowCore()
        plug = GalgameChoicesPlugin(sc)
        plug.manual_generate()
        check(evt_start.wait(timeout=5), "后台生成线程已启动")
        # 在途期间玩家发新消息 → clear_choices 递增世代号
        plug.on_message_send("新消息")
        evt_release.set()
        time.sleep(0.2)
        check(plug.choices == [] and plug.choices_loading is False, "过期线程结果被丢弃，不污染新回合")
        check("gal_options" not in sc.tree.nodes["a1"].metadata, "过期线程未写入节点 metadata")
        check("乙女" in sc.captured_system, "乙女·梦向模式口径已注入选项生成提示词")

        # 正常完成：写入节点 metadata + aff 钳制在 [-20, 20] + 切节点回档复原
        evt_start.clear()
        evt_release.set()
        plug.manual_generate()
        deadline = time.time() + 5
        while plug.choices_loading and time.time() < deadline:
            time.sleep(0.03)
        check(len(plug.choices) == 2, "正常生成 2 个选项")
        check(plug.choices[0]["aff"] == 20 and plug.choices[1]["aff"] == -20, "aff 越界值被钳制在 [-20, 20]")
        check(len(sc.tree.nodes["a1"].metadata.get("gal_options") or []) == 2, "选项持久化进 AI 节点 metadata")

        # 切到未存选项的 a2 → 清空；再切回 a1 → 完整复原含 say
        check(plug.restore_options_from_node("a2") is False and plug.choices == [], "回档到无选项节点清空旧选项")
        check(plug.restore_options_from_node("a1") is True and len(plug.choices) == 2, "回档到有选项节点复原成功")
        check(plug.choices[0].get("say") == "「你今天还好吗？」", "复原保留 say 台词字段")

        print("== ② 负面选项 ROLL 逻辑（不反向奖惩） ==")
        html_app.BASE_DIR = _iso
        app = html_app.HtmlApp()
        neg_item = {"text": "冷嘲热讽", "aff": -5}
        with mock.patch("random.random", return_value=0.1):   # crit
            eff, kind, _ = app._roll_option(neg_item)
        check(kind == "crit" and eff["aff"] == -2, "负面选项暴击减轻惩罚: -5 -> %s" % eff.get("aff"))
        with mock.patch("random.random", return_value=0.01):  # fail
            eff, kind, _ = app._roll_option(neg_item)
        check(kind == "fail" and eff["aff"] == -10, "负面选项大失败加重惩罚: -5 -> %s" % eff.get("aff"))

        print("== ③ API：本地地址保护 + stream_options 400 降级缓存 + 429 重试 + 友好报错 ==")
        check(_is_local_url("http://localhost:11434/v1") is True, "识别 localhost 为本地地址")
        check(_is_local_url("http://127.0.0.1:8080/v1") is True, "识别 127.0.0.1 为本地地址")
        check(_is_local_url("https://api.deepseek.com") is False, "公网地址非本地")

        core = ChatCore()
        core.base_url = "http://localhost:11434/v1"
        core.relay_base = "https://relay.example.com"
        check(core._maybe_switch_relay() is False and core.relay_on is False, "Ollama 本机地址绝不切云端中转")
        check(core._relay_target_url() == "http://localhost:11434/v1", "本地地址不拼中转 URL")

        # api_save_key 对 ollama 不开 relay_on
        app.core.relay_base = "https://relay.example.com"
        app.api_save_key("", "http://localhost:11434/v1", "qwen3:8b", "ollama")
        check(app.core.relay_on is False, "api_save_key(ollama) 不开启云端中转")

        # stream_options 400 降级 + 缓存命中（第二次不再传 stream_options）
        calls = []
        class StreamStub:
            def create(self, **kw):
                calls.append(dict(kw))
                if "stream_options" in kw:
                    raise FakeStatusError(400, "unsupported stream_options")
                chunk = type("C", (), {
                    "usage": None,
                    "choices": [type("Ch", (), {"delta": type("D", (), {"content": "ok"})()})()],
                })()
                return [chunk]

        core2 = ChatCore()
        core2.base_url = "https://compat.example.com/v1"
        core2.model = "m-compat"
        core2.client = type("Cl", (), {"chat": type("Ch", (), {"completions": StreamStub()})()})()
        txt1, _ = core2._stream_create([{"role": "user", "content": "hi", "_node_id": "n1"}], None)
        txt2, _ = core2._stream_create([{"role": "user", "content": "hi2"}], None)
        check(txt1 == "ok" and txt2 == "ok", "stream_options 400 自动降级返回正文")
        check(len(calls) == 3 and "stream_options" not in calls[2], "不支持 stream_options 已按端点缓存（第二次直发）")
        check("_node_id" not in calls[0]["messages"][0], "内部 _ 字段仍被剥离")

        # 429 瞬态重试（stream + complete_text）
        tries = {"n": 0}
        class RetryStub:
            def create(self, **kw):
                tries["n"] += 1
                if tries["n"] == 1:
                    raise FakeStatusError(429, "rate limit")
                if kw.get("stream"):
                    return [type("C", (), {"usage": None, "choices": [type("Ch", (), {"delta": type("D", (), {"content": "retry-ok"})()})()]})()]
                return type("R", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": "comp-ok"})()})()]})()

        core3 = ChatCore()
        core3.base_url = "https://api.example.com/v1"
        core3.model = "m-retry"
        core3.client = type("Cl", (), {"chat": type("Ch", (), {"completions": RetryStub()})()})()
        with mock.patch("core_fetch.time.sleep"):
            t_stream, _ = core3._stream_create([{"role": "user", "content": "hi"}], None)
        check(t_stream == "retry-ok" and tries["n"] == 2, "流式 429 瞬态退避重试成功")

        tries["n"] = 0
        with mock.patch("core_fetch.time.sleep"):
            t_comp = core3.complete_text([{"role": "user", "content": "hi", "_ts": 123}])
        check(t_comp == "comp-ok" and tries["n"] == 2, "complete_text 429 瞬态退避重试成功")

        # 友好中文报错格式化
        e401 = FakeStatusError(401, "bad key", body={"error": {"message": "Incorrect API key"}})
        e429 = FakeStatusError(429, "too many", body={"error": {"message": "Quota exceeded"}})
        check("401" in core3._format_api_error(e401) and "API Key" in core3._format_api_error(e401), "401 友好中文报错")
        check("429" in core3._format_api_error(e429) and "限流" in core3._format_api_error(e429), "429 友好中文报错")

        # _fetch_auto_turn 支持 on_busy 参数（不再 NameError）
        busy_hit = []
        core3.is_processing = True
        core3._fetch_auto_turn("咲", None, None, None, False, on_busy=lambda msg: busy_hit.append(msg))
        check(len(busy_hit) == 1 and "处理中" in busy_hit[0], "_fetch_auto_turn 支持 on_busy 无 NameError")

        print("== ④ 安卓端结构核对（GalgamePlugin.kt & ChatEngine.kt） ==")
        gp = io.open(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "plugins", "GalgamePlugin.kt"), encoding="utf-8").read()
        ce = io.open(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "core", "ChatEngine.kt"), encoding="utf-8").read()
        check("genSeq" in gp and 'o.fields["say"]' in gp, "安卓 GalgamePlugin 含 genSeq 防竞态与 say 持久化")
        check("streamPost(" in ce and "reader.readLine()" in ce, "安卓 ChatEngine 使用逐行真流式读取")
        check("fun stop()" in ce and "finally {\n                isProcessing = false" in ce, "安卓 ChatEngine 有 stop() 且 finally 必释放 isProcessing")
        check("Proxy.Type.SOCKS" in ce and "isLocalUrl(" in ce, "安卓 ChatEngine 区分 SOCKS 代理并保护本机地址")
    finally:
        shutil.rmtree(_iso, ignore_errors=True)

    print("结果：%d 通过, %d 失败" % (ok, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
