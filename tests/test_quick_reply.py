# -*- coding: utf-8 -*-
"""Quick Reply 宏展开 + quick_replies 接口测试。"""
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

tmp = tempfile.mkdtemp(prefix="dick_qr_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

app.api_create_role("咲", json.dumps({"personality": "傲娇"}))
app.api_select_roles(json.dumps(["咲"]))
app.api_set_persona(json.dumps({"name": "主角", "background": "旅人"}))
app.api_create_world("海边小镇", "宁静的渔村", "")
app.api_select_worlds(json.dumps(["海边小镇"]))
app.current_world = "海边小镇"

# 1) <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌宏展开
check(app._expand_macros("我叫{player}") == "我叫主角", "{player} → 玩家名")
check(app._expand_macros("{char}你在吗") == "咲你在吗", "{char} → 当前角色")
check(app._expand_macros("这里是{world}") == "这里是海边小镇", "{world} → 当前世界")
r = app._expand_macros("{random:苹果|香蕉|橘子}")
check(r in ("苹果", "香蕉", "橘子"), "{random} 随机取一: %s" % r)
check(app._expand_macros("保留{未知宏}原样") == "保留{未知宏}原样", "未知宏原样保留")
check(app._expand_macros("无宏") == "无宏", "无宏原样")

# 2) 发送时展开（api_send 正常路径，stub _start_fetch 避免真实请求）
app._start_fetch = lambda node_id: None
r = app.api_send("我叫{player}，你叫{char}", None, None)
check(r.get("ok") is True, "发送成功")
msgs = [m for m in app.api_state()["messages"] if m["kind"] == "user"]
check(msgs and msgs[-1]["content"] == "我叫主角，你叫咲", "发送时宏已展开: %r" % (msgs[-1]["content"] if msgs else None))

# 3) quick_replies 接口（自己造一份放进临时目录）
# 原来这里是"把项目根的 quick_replies.json 拷过去"，但那个文件是**用户运行时状态**
# （.gitignore 里有它，build_release 还会从发布包里剔掉），仓库里根本没有 →
# CI（干净检出）上 shutil.copy 直接 FileNotFoundError。测试要断言的接口行为与
# 那份内容无关，自己写一份即可。
import shutil as _sh
_qr = [{"label": "打招呼", "text": "你好呀"},
       {"label": "夸夸她", "text": "今天真好看"},
       {"label": "道别", "text": "我先走啦"},
       {"label": "没标签的脏数据", "text": "应当被忽略"}]
_qr[3].pop("label")          # 少 label 的条目要被 api_quick_replies 过滤掉
with open(os.path.join(tmp, "quick_replies.json"), "w", encoding="utf-8") as f:
    json.dump(_qr, f, ensure_ascii=False)
qr = app.api_quick_replies()
check(isinstance(qr, list) and len(qr) == 3, "quick_replies 加载并过滤脏条目: %d 条" % len(qr))
check(qr[0]["label"] and qr[0]["text"], "条目含 label/text")
# 文件缺失 → 空列表（打包版与 scrub 之后就是这种状态，不能崩）
os.remove(os.path.join(tmp, "quick_replies.json"))
check(app.api_quick_replies() == [], "文件缺失返回空列表")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
