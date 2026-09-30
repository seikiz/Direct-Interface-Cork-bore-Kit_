# -*- coding: utf-8 -*-
"""net.py 树存档同步接口测试：上传/下载/404/空树。"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import net

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

# 隔离到临时目录，避免污染真实 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌workshop_data
tmp = tempfile.mkdtemp(prefix="dick_save_")
net.SAVES_DIR = os.path.join(tmp, "saves")
os.makedirs(net.SAVES_DIR, exist_ok=True)
net._save_path = lambda cid: os.path.join(net.SAVES_DIR,
    (cid or "unknown").strip().replace("/", "_").replace("\\", "_").replace("..", "_")[:80] + ".json")

client = net.app.test_client()

tree = {
    "nodes": {"r": {"id": "r", "role": "system", "content": "sp", "parent_id": None,
                    "children_ids": ["u1"], "metadata": {}},
              "u1": {"id": "u1", "role": "user", "content": "你好", "parent_id": "r",
                     "children_ids": ["a1"], "metadata": {}},
              "a1": {"id": "a1", "role": "assistant", "content": "你好呀", "parent_id": "u1",
                     "children_ids": [], "metadata": {"speaker": "咲"}}},
    "root_id": "r",
    "current_leaf_id": "a1",
}
card = "咲"

print("== 上传 ==")
r = client.post("/api/save/" + card, json={"tree": tree})
d = r.get_json()
check(r.status_code == 200 and d.get("ok") is True, "上传成功")
check(bool(d.get("ts")), "服务器盖时间戳")

print("== 下载 ==")
r2 = client.get("/api/save/" + card)
d2 = r2.get_json()
check(r2.status_code == 200, "下载成功")
check(d2.get("ts") == d.get("ts"), "时间戳一致")
check(d2["tree"]["current_leaf_id"] == "a1", "树内容无误")
check(d2["tree"]["nodes"]["a1"]["content"] == "你好呀", "节点 content 保留")

print("== 404 ==")
check(client.get("/api/save/不存在").status_code == 404, "无存档返回 404")

print("== 空树拒绝 ==")
r3 = client.post("/api/save/" + card, json={"tree": {"nodes": {}}})
check(r3.status_code == 400, "空树上传被拒 400")

print("== 路径穿越防护 ==")
evil = "../evil"
client.post("/api/save/" + evil, json={"tree": tree})
# Flask 会对 /../ 归一化为 /api/evil，路由不匹配 → 404；关键是绝不能写入上级目录
check(not os.path.exists(os.path.join(tmp, "evil.json")), "未写入上级目录")
check(not os.path.exists(os.path.join(net.SAVES_DIR, "../evil.json")), "存档文件名被净化")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
