# -*- coding: utf-8 -*-
"""指令模板：停止序列 生效逻辑测试。"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app
import app_paths

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

tmp = tempfile.mkdtemp(prefix="dick_st_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

# 1) 模型家族默认（deepseek → 无；ollama → 有）
check(app._effective_stop() == [], "deepseek 默认无停止序列")
app.provider_id = "ollama"
check(app._effective_stop() == ["<|im_end|>", "</s>"], "ollama 默认停止序列: %r" % app._effective_stop())

# 2) 预设 stop_sequences 覆盖模型默认（走 api_set_preset 真实流程）
app.presets.append({"name": "带停止", "stop_sequences": ["<|eot_id|>"]})
app.api_set_preset("带停止")
check(app._effective_stop() == ["<|eot_id|>"], "预设 stop 覆盖模型默认: %r" % app._effective_stop())
app.api_set_preset("默认")

# 3) 设置覆盖 > 预设
r = app.api_set_stop("<|im_end|>, </s>, 再见")
check(r.get("ok") is True and r["stop"] == ["<|im_end|>", "</s>", "再见"], "api_set_stop 解析: %r" % r["stop"])
check(app.core.stop_sequences == ["<|im_end|>", "</s>", "再见"], "core 已应用")
check(app.api_state()["stop_input"] == ["<|im_end|>", "</s>", "再见"], "state 透传 stop_input")

# 4) 清空 → 回落到模型默认
r2 = app.api_set_stop("")
check(r2["stop"] == ["<|im_end|>", "</s>"], "清空后回落 ollama 默认: %r" % r2["stop"])

# 5) 换厂商后按新家族默认
app.api_set_stop("")
app.provider_id = "deepseek"
check(app._effective_stop() == [], "切回 deepseek → 无停止序列")

# 6) 预设 response_style / assistant_prefix 注入系统提示（走 api_set_preset）
app.provider_id = "deepseek"
app.api_create_role("甲", json.dumps({"personality": "冷静"}))
app.api_select_roles(json.dumps(["甲"]))
app.presets.append({"name": "带风格", "response_style": "结尾不要提问", "assistant_prefix": "甲："})
app.api_set_preset("带风格")
sn = next((n for n in app.core.tree.nodes.values() if n.role == "system"), None)
check(sn is not None and "结尾不要提问" in sn.content, "response_style 注入系统提示")
check(sn is not None and "回复时请以「甲：」开头" in sn.content, "assistant_prefix 注入（单角色）")
app.api_set_preset("默认")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
