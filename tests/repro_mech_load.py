# -*- coding: utf-8 -*-
"""验证『恋爱条加载』PC 端修复：
A) 含 advanced 的角色卡 → 启动恢复选中 → 机制随启动初始化（不再需要手动保存）
B) 选择角色 → config 持久化 → 重启自动恢复
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVES = os.path.join(BASE, "saves")
CONFIG = os.path.join(BASE, "config.json")
TEST_NAME = "ZZ_恋爱条复测"
TEST_FILE = os.path.join(SAVES, TEST_NAME + ".json")

def make_card():
    data = {
        "name": TEST_NAME,
        "system_prompt": "你是测试角色。",
        "legacy": "你是测试角色。",
        "advanced": {
            "mechanics": {
                "affection": {"enabled": True, "initial": 50, "min": 0, "max": 100, "crit": 0.001},
            }
        },
    }
    with open(TEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cleanup():
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)
    # 还原 config（去掉测试写入的 selected_roles/last_role）
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        changed = False
        for k in ("selected_roles", "last_role"):
            if k in cfg:
                cfg.pop(k)
                changed = True
        if changed:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def main():
    cleanup()
    make_card()
    import html_app
    app = html_app.HtmlApp()
    print(f"[1] 启动完成，selected_roles={app.selected_roles}")

    # 模拟前端勾选角色
    app.api_select_roles(json.dumps([TEST_NAME]))
    cfg0 = json.load(open(CONFIG, "r", encoding="utf-8"))
    print(f"[2] 勾选后 config.selected_roles={cfg0.get('selected_roles')}")

    st = app.api_state()
    mech = st.get("mechanism") or {}
    print(f"[3] 勾选后 mechanism.config={'有' if mech.get('config') else 'None'}, "
          f"state={json.dumps(mech.get('state'), ensure_ascii=False) if mech.get('state') else 'None'}")

    # 模拟重启：新实例化 HtmlApp（config 里已有 selected_roles）
    app2 = html_app.HtmlApp()
    print(f"[4] 重启后 selected_roles={app2.selected_roles}")
    st2 = app2.api_state()
    mech2 = st2.get("mechanism") or {}
    ok = bool(mech2.get("config")) and bool(mech2.get("state"))
    print(f"[5] 重启后 mechanism.config={'有' if mech2.get('config') else 'None'}, "
          f"state={json.dumps(mech2.get('state'), ensure_ascii=False) if mech2.get('state') else 'None'}")
    print("[OK] PC 端修复生效：启动即恢复角色，恋爱条随启动初始化" if ok
          else "[X] 修复未生效")

    cleanup()
    print("---- 验证结束 ----")

if __name__ == "__main__":
    main()
