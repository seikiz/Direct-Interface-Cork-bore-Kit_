# -*- coding: utf-8 -*-
"""存档守护测试：校验/修复/原子写入/备份恢复/应用集成。
运行：python tests/test_save_guard.py"""
import sys, os, json, time, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import save_guard

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

def healthy_tree():
    return {
        "nodes": {
            "r": {"id": "r", "role": "system", "content": "sys", "parent_id": None, "children_ids": ["u1"], "metadata": {}},
            "u1": {"id": "u1", "role": "user", "content": "你好", "parent_id": "r", "children_ids": ["a1"], "metadata": {}},
            "a1": {"id": "a1", "role": "assistant", "content": "你好呀", "parent_id": "u1", "children_ids": [], "metadata": {"speaker": "咲"}},
        },
        "root_id": "r",
        "current_leaf_id": "a1",
    }

print("== ① 校验 ==")
check(save_guard.validate_history_tree(healthy_tree()) == [], "健康树无问题")
t = healthy_tree()
t["nodes"]["a1"]["children_ids"] = ["ghost"]           # 悬空引用
t["nodes"]["u1"]["role"] = "weird"                      # 非法 role
t["current_leaf_id"] = "gone"                           # 无效叶子
issues = save_guard.validate_history_tree(t)
check(len(issues) >= 3, "悬空/非法role/无效叶子 全部报出: %d" % len(issues))

print("== ② 修复 ==")
t = healthy_tree()
t["nodes"]["a1"]["children_ids"] = ["ghost"]
t["nodes"]["a1"]["parent_id"] = "nope"                  # 悬空 parent
t["root_id"] = "ghost"                                  # 无效 root
t["current_leaf_id"] = "gone"
fixed, repairs = save_guard.repair_history_tree(t)
check(fixed["root_id"] == "r", "root 修正为 r")
check(fixed["current_leaf_id"] == "a1", "leaf 重算为 a1")
check(fixed["nodes"]["a1"]["children_ids"] == [], "悬空子引用清除")
check(fixed["nodes"]["a1"]["parent_id"] == "u1", "悬空 parent 按图重建为 u1")
check(save_guard.validate_history_tree(fixed) == [], "修复后完全健康")
check(len(repairs) >= 4, "修复记录完整: %d" % len(repairs))

print("== ③ 环检测 ==")
t = healthy_tree()
t["nodes"]["r"]["children_ids"] = ["a1"]                # root 直接指向 a1 形成环 r->a1->u1->r
t["nodes"]["u1"]["children_ids"] = ["r"]
fixed2, repairs2 = save_guard.repair_history_tree(t)
check("检测到环" in " ".join(repairs2), "检测到环: %r" % repairs2)
check(save_guard.validate_history_tree(fixed2) == [], "断环后健康")

print("== ④ 原子写入 ==")
tmp = tempfile.mkdtemp(prefix="sg_")
p = os.path.join(tmp, "x.json")
save_guard.atomic_write_json(p, {"a": 1})
check(json.load(open(p, encoding="utf-8")) == {"a": 1}, "原子写入内容正确")
check(not os.path.exists(p + ".tmp"), "无 .tmp 残留")

print("== ⑤ 备份 + 轮转 ==")
p2 = os.path.join(tmp, "角色.json")
save_guard.atomic_write_json(p2, {"v": 1})
for i in range(3):
    time.sleep(1.01)  # 备份节流 300s，用 throttle=0 强制
    save_guard.backup_file(p2, throttle=0)
bdir = os.path.join(tmp, "backup")
baks = [f for f in os.listdir(bdir) if f.startswith("角色.json.")]
check(len(baks) == 3, "3 次强制备份: %d" % len(baks))
save_guard.atomic_write_json(p2, {"v": 2})
backed = save_guard.backup_file(p2, throttle=0)         # 覆盖前留底
check(backed is not None, "覆盖前备份成功")
check(save_guard.newest_backup(p2) is not None, "newest_backup 可用")

print("== ⑥ 损坏恢复 ==")
p3 = os.path.join(tmp, "坏档.json")
save_guard.atomic_write_json(p3, healthy_tree())
save_guard.backup_file(p3, throttle=0)                  # 留一份好备份
with open(p3, "w", encoding="utf-8") as f:              # 模拟写一半崩溃：截断 JSON
    f.write('{"nodes": {"r": {"id": "r", "role": "system", "content": "sys", "parent_id": null, "children_ids": ["u1"], "metadata": {}}')
data = save_guard.guard_loaded(p3, kind="role")
check(data is not None and isinstance(data.get("nodes"), dict), "损坏后从备份恢复")
check(len(data.get("nodes", {})) == 3, "恢复出完整树: %d 节点" % len(data.get("nodes", {})))

print("== ⑦ 结构性损坏自动修复（应用路径） ==")
p4 = os.path.join(tmp, "坏树.json")
save = {"name": "测试", "system_prompt": "sp", "history_tree": healthy_tree()}
save["history_tree"]["nodes"]["a1"]["children_ids"] = ["ghost"]
save["history_tree"]["current_leaf_id"] = "gone"
save_guard.atomic_write_json(p4, save)
data4 = save_guard.guard_loaded(p4, kind="role")
check(save_guard.validate_save(data4) == [], "加载时自动修复坏树")
check(json.load(open(p4, encoding="utf-8"))["history_tree"]["current_leaf_id"] == "a1", "修复已写回磁盘")

print("== ⑧ sweep 汇总 ==")
saves_dir = os.path.join(tmp, "saves")
os.makedirs(saves_dir, exist_ok=True)
broken = os.path.join(saves_dir, "sweep坏档.json")
b2 = dict(save)
b2["history_tree"] = healthy_tree()
b2["history_tree"]["nodes"]["u1"]["children_ids"] = ["ghost", "u1"]  # 悬空 + 自引用
b2["history_tree"]["current_leaf_id"] = "gone"
save_guard.atomic_write_json(broken, b2)
save_guard.atomic_write_json(os.path.join(saves_dir, "健康档.json"),
                             {"name": "测试", "system_prompt": "sp", "history_tree": healthy_tree()})
s = save_guard.sweep(tmp, include_worlds=False, include_memory=False)
check(s["repaired"] >= 1, "sweep 检出并修复坏档: %r" % s)
check(s["ok"] >= 1, "健康档计入 ok: %r" % s)

print("== ⑨ 世界卡校验/修复 ==")
w = {"name": "W", "rules": "not-a-list", "entries": [{"keywords": "x", "content": 123}, "bad"]}
check(len(save_guard.validate_world(w)) >= 2, "世界卡问题报出")
wf, wr = save_guard.repair_world(dict(w))
check(isinstance(wf["rules"], list) and isinstance(wf["entries"], list), "世界卡修复为合法结构")
check(save_guard.validate_world(wf) == [], "修复后健康")

print("== ⑩ 同秒两份备份：必须挑到较新的那份 ==")
same = os.path.join(tmp, "same_sec")
os.makedirs(same, exist_ok=True)
ps = os.path.join(same, "同秒.json")
save_guard.atomic_write_json(ps, {"v": "A"})
b_a = save_guard.backup_file(ps, throttle=0)             # 内容 A
save_guard.atomic_write_json(ps, {"v": "B"})
b_b = save_guard.backup_file(ps, throttle=0)             # 内容 B（与 A 大概率同一秒）
check(b_a is not None and b_b is not None and b_a != b_b,
      "同秒两次备份不互相覆盖：%s / %s"
      % (os.path.basename(b_a or "?"), os.path.basename(b_b or "?")))
check(json.load(open(b_b, encoding="utf-8"))["v"] == "B", "第二份备份内容确实是 B")
# 把两份 mtime 压成**同一个纳秒**：模拟「文件系统只到秒 / mtime 不可信」。
# 这时只能靠文件名里的 时刻+同秒序号 分先后 —— 旧实现 max(mtime) 在这里就是随缘挑一个。
T = 1700000000000000000
os.utime(b_a, ns=(T, T))
os.utime(b_b, ns=(T, T))
best = save_guard.newest_backup(ps)
check(best == b_b, "mtime 并列时按文件名时刻/序号挑到较新的 B（旧实现会随缘）")
check(json.load(open(best, encoding="utf-8"))["v"] == "B", "挑到的内容是 B，不是旧的 A")

print("== ⑪ mtime 与文件名时刻打架：必须报错，绝不静默挑一个 ==")
d2 = os.path.join(tmp, "conflict")
bdir2 = os.path.join(d2, "backup")
os.makedirs(bdir2, exist_ok=True)
p2 = os.path.join(d2, "矛盾.json")
old_bak = os.path.join(bdir2, "矛盾.json.20260101000000")
new_bak = os.path.join(bdir2, "矛盾.json.20260102000000")
save_guard.atomic_write_json(old_bak, {"v": "旧数据"})
save_guard.atomic_write_json(new_bak, {"v": "新数据"})
T2 = 1700000000000000000
os.utime(old_bak, ns=(T2, T2))                            # mtime 看着更新
os.utime(new_bak, ns=(T2 - 3600 * 10 ** 9, T2 - 3600 * 10 ** 9))   # 但文件名时刻更新
caught = None
try:
    save_guard.newest_backup(p2)
except save_guard.AmbiguousBackupError as e:
    caught = e
check(caught is not None, "两路证据矛盾 → 抛 AmbiguousBackupError（不再 max(mtime) 瞎挑）")
check(caught is not None and "指向不同" in (caught.reason or ""),
      "报错原因说清了「mtime 与文件名指向不同」: %r" % (getattr(caught, "reason", None),))
check(caught is not None and len(caught.candidates) == 2,
      "异常里带着两份候选，够用户手动挑")

print("== ⑫ 没有文件名时刻 + mtime 并列：分不出来 → 报错 ==")
d3 = os.path.join(tmp, "legacy")
bdir3 = os.path.join(d3, "backup")
os.makedirs(bdir3, exist_ok=True)
p3b = os.path.join(d3, "旧命名.json")
for fn2, body in (("旧命名.json.bak-a", {"v": "一"}), ("旧命名.json.bak-b", {"v": "二"})):
    save_guard.atomic_write_json(os.path.join(bdir3, fn2), body)
    os.utime(os.path.join(bdir3, fn2), ns=(T2, T2))
caught2 = None
try:
    save_guard.newest_backup(p3b)
except save_guard.AmbiguousBackupError as e:
    caught2 = e
check(caught2 is not None, "无文件名时刻 + mtime 并列 → 报错，不瞎挑")

print("== ⑬ 上层：分不出新旧时绝不自动恢复（不拿旧数据盖存档） ==")
p4b = os.path.join(d2, "坏掉.json")
with open(p4b, "w", encoding="utf-8") as f:
    f.write('{"broken": ')
bdir4 = save_guard.backup_dir_for(p4b)
os.makedirs(bdir4, exist_ok=True)
for fn3, body, shift in (("坏掉.json.20260101000000", {"v": "旧"}, 0),
                         ("坏掉.json.20260102000000", {"v": "新"}, 60)):
    dst4 = os.path.join(bdir4, fn3)
    save_guard.atomic_write_json(dst4, body)
    os.utime(dst4, ns=(T2 - shift * 10 ** 9, T2 - shift * 10 ** 9))
before = open(p4b, encoding="utf-8").read()
data = save_guard.guard_loaded(p4b, kind="role")
check(data is None, "guard_loaded 拒绝恢复（返回 None）")
check(open(p4b, encoding="utf-8").read() == before, "主文件没被旧备份覆盖（数据没回退）")
status, msg = save_guard.guard_file(p4b)
check(status == "failed" and "已停止自动恢复" in msg,
      "guard_file 报 failed 并说清为什么: %r" % (msg[:80],))

print("== ⑭ 应用集成：HtmlApp 启动自动修复坏档 ==")
import app_paths
import html_app
_real_base = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real_base, "plugins")]
html_app.BASE_DIR = tmp
bad_role = {
    "name": "坏档角色", "system_prompt": "sp",
    "history_tree": healthy_tree(),
}
bad_role["history_tree"]["nodes"]["a1"]["children_ids"] = ["ghost"]
bad_role["history_tree"]["current_leaf_id"] = "gone"
save_guard.atomic_write_json(os.path.join(saves_dir, "坏档角色.json"), bad_role)
app = html_app.HtmlApp()
names = [r["name"] for r in app.roles]
check("坏档角色" in names, "坏档角色被加载")
fixed_on_disk = json.load(open(os.path.join(saves_dir, "坏档角色.json"), encoding="utf-8"))
check(fixed_on_disk["history_tree"]["current_leaf_id"] == "a1", "坏档已在启动时修复并写回")
baks = [f for f in os.listdir(os.path.join(saves_dir, "backup")) if "坏档角色" in f]
check(len(baks) >= 1, "修复前坏原件已留底备份: %d" % len(baks))

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌