# -*- coding: utf-8 -*-
"""角色卡高级设置（内置游戏 / 额外提示 / 开发者模式）测试。"""
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

tmp = tempfile.mkdtemp(prefix="dick_adv_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

# 开发者模式开关
r = app.api_set_dev_mode(True)
check(r.get("ok") is True and app.api_state()["dev_mode"] is True, "开发者模式开启")
app.api_set_dev_mode(False)
check(app.api_state()["dev_mode"] is False, "开发者模式关闭")
app.api_set_dev_mode(True)

# 创建带高级设置的角色（内置游戏 + 额外提示 + 卡片 QR + 开发者备注）
adv = {
    "game": {"name": "密室逃脱", "rules": "你被困在一间密室，通过观察与互动找出线索逃脱。\n规则：每次行动给出环境反馈。", "state": "房间：书房，有书架、壁炉、上锁的门。"},
    "extra_prompt": "节奏紧凑，悬念感强。",
    "dev_notes": "作者：seiki；本卡测试用。",
    "card_quick_replies": [{"label": "🔍 查看书架", "text": "我走向书架，仔细查看。"}],
}
r = app.api_create_role("密室", json.dumps({"personality": "神秘", "advanced": adv}))
check(r.get("ok") is True, "创建带高级设置角色")

# 选中后系统提示注入内置游戏
app.api_select_roles(json.dumps(["密室"]))
sn = next((n for n in app.core.tree.nodes.values() if n.role == "system"), None)
check(sn is not None and "【内置游戏：密室逃脱】" in sn.content, "内置游戏注入系统提示")
check(sn is not None and "初始状态：房间：书房" in sn.content, "初始状态注入")
check(sn is not None and "节奏紧凑，悬念感强" in sn.content, "额外提示注入")
check("作者：seiki" not in sn.content, "开发者备注不注入")

# api_get_role 返回 advanced 预填
g = app.api_get_role("密室")
check(g["advanced"]["game"]["name"] == "密室逃脱", "get_role 返回 advanced")
check(g["advanced"]["card_quick_replies"][0]["label"] == "🔍 查看书架", "卡片 QR 返回")

# 存档里持久化
with open(os.path.join(tmp, "saves", "密室.json"), encoding="utf-8") as f:
    saved = json.load(f)
check(saved.get("advanced", {}).get("game", {}).get("rules", "").startswith("你被困在一间密室"), "advanced 落盘")

# 卡片快捷回复进 api_quick_replies（排最前）
qr = app.api_quick_replies()
check(any(q["label"] == "🔍 查看书架" for q in qr), "卡片 QR 合并进快捷回复")

# 更新角色（无 advanced → 移除）
r2 = app.api_update_role("密室", json.dumps({"personality": "神秘", "advanced": None}))
check(r2.get("ok") is True, "更新角色（清空 advanced）")
g2 = app.api_get_role("密室")
check(g2["advanced"] is None, "advanced 已清空")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
