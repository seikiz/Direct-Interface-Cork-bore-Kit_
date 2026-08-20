# -*- coding: utf-8 -*-
"""同步端游咲 → Android assets（剔除历史树，保持手机版初始化）
用法：python tools/sync_saki_to_android.py
端游咲更新后运行此脚本，再重新构建 APK。"""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
src = json.load(open(os.path.join(ROOT, "saves", "咲.json"), encoding="utf-8"))
out = {k: v for k, v in src.items() if k != "history_tree"}
for k in ["name", "system_prompt", "legacy", "appearance", "personality",
          "background", "speech", "first_mes", "mes_example", "notes", "unlocked"]:
    if k not in out:
        out[k] = "" if k != "unlocked" else False
dst_dir = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "assets", "roles")
os.makedirs(dst_dir, exist_ok=True)
dst = os.path.join(dst_dir, "saki.json")  # ASCII 文件名（Gradle 打包中文文件名会乱码）
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已同步端游咲 →", dst)
print("字段:", list(out.keys()))
print("无 history_tree:", "history_tree" not in out)
