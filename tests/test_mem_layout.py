# -*- coding: utf-8 -*-
"""记忆布局审计：人物专属子目录 + 世界共享目录 + 老布局迁移（可逆）。

为什么需要
----------
记忆链插件原来把索引写成【一份全局 chain.json】，归档文件散在 memory/ 根目录，
"当前是哪个角色"还靠文件修改时间猜。改成人物专属目录后，最容易出三种错：
  · 迁移把别人的归档搬进了这个角色的目录（那就制造了"混"，比不迁移更糟）
  · 迁移不可逆（记忆是全项目最不可替代的数据，搬错就没了）
  · 索引写回还是写到全局那一份（等于白改）
跑法：python tests/test_mem_layout.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "plugins"))

import mem_isolate as MI  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def load_plugin(base_dir):
    """把记忆链插件按"数据目录=base_dir"加载起来（app_paths 指到临时目录）。"""
    import app_paths
    app_paths.get_base_dir = lambda: base_dir          # 隔离数据根
    path = os.path.join(ROOT, "plugins", "memory_chain_plugin.py")
    spec = importlib.util.spec_from_file_location("mem_chain_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mem_chain_under_test"] = mod
    spec.loader.exec_module(mod)

    class FakeCore:
        pass
    return mod.MemoryChainPlugin(FakeCore())


def wj(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def main():
    print("=" * 62)
    print(u"记忆布局审计（人物专属 / 世界共享 / 迁移）")
    print("=" * 62)
    tmp = tempfile.mkdtemp(prefix="dick_memlayout_")
    try:
        base = os.path.join(tmp, "app")
        os.makedirs(os.path.join(base, "saves"), exist_ok=True)
        mem = os.path.join(base, "memory")

        print(u"\n== ① 新装即建目录：人物专属 + 世界共享 ==")
        plug = load_plugin(base)
        check(u"memory/ 与 memory/_world/ 都建好了",
              os.path.isdir(mem) and os.path.isdir(os.path.join(mem, MI.WORLD_DIR_NAME)),
              str(os.listdir(mem)))

        print(u"\n== ② 老布局迁移：按 key 拆开，且不越界 ==")
        wj(os.path.join(mem, "chain.json"), {
            u"咲": [{"part": 1, "path": u"咲.part1.json", "nodes": 5}],
            u"老约翰": [{"part": 1, "path": u"老约翰.part1.json", "nodes": 6}],
        })
        wj(os.path.join(mem, u"咲.part1.json"), {"history_tree": {"nodes": {"a": {}}}})
        wj(os.path.join(mem, u"老约翰.part1.json"), {"history_tree": {"nodes": {"b": {}}}})
        plug2 = load_plugin(base)
        moved, roles = plug2.migrate_legacy()
        check(u"两个角色都迁过去了", sorted(roles) == [u"咲", u"老约翰"], str(roles))
        check(u"搬了 2 个归档", moved == 2, str(moved))
        check(u"咲的目录里只有咲的归档",
              os.path.isfile(os.path.join(mem, u"咲", u"咲.part1.json"))
              and not os.path.exists(os.path.join(mem, u"咲", u"老约翰.part1.json")),
              str(os.listdir(os.path.join(mem, u"咲"))))
        check(u"老约翰的目录里只有他的归档",
              os.path.isfile(os.path.join(mem, u"老约翰", u"老约翰.part1.json"))
              and not os.path.exists(os.path.join(mem, u"老约翰", u"咲.part1.json")),
              str(os.listdir(os.path.join(mem, u"老约翰"))))
        c1 = json.load(io.open(os.path.join(mem, u"咲", "chain.json"), encoding="utf-8"))
        check(u"咲的索引只含咲一个 key", list(c1) == [u"咲"], str(list(c1)))
        check(u"老索引留了 .migrated 备份（可回退）",
              os.path.isfile(os.path.join(mem, "chain.json.migrated")),
              str(os.listdir(mem)))

        print(u"\n== ③ 迁移后用检测器验：判定为 isolated ==")
        rep = MI.audit(mem, role_names=[u"咲", u"老约翰"])
        check(u"verdict = isolated", rep["verdict"] == "isolated",
              u"%s / %s" % (rep["verdict"], rep["problems"]))

        print(u"\n== ④ 幂等：再迁一次不动任何东西 ==")
        plug3 = load_plugin(base)
        moved2, roles2 = plug3.migrate_legacy()
        check(u"第二次迁移 0 搬动 / 0 角色", moved2 == 0 and roles2 == [], u"%s %s" % (moved2, roles2))

        print(u"\n== ⑤ 索引写回落在角色目录里（不是全局） ==")
        plug3._save_chain({u"咲": [{"part": 2, "path": u"咲.part2.json"}]}, u"咲")
        c2 = json.load(io.open(os.path.join(mem, u"咲", "chain.json"), encoding="utf-8"))
        check(u"角色目录里的索引被更新", c2[u"咲"][0]["part"] == 2, str(c2))
        check(u"全局 chain.json 没有被重新创建",
              not os.path.exists(os.path.join(mem, "chain.json")), str(os.listdir(mem)))

        print(u"\n== ⑥ 摘要路径：优先角色目录，老位置兜底 ==")
        wj(os.path.join(mem, u"咲", u"咲.summary.json"), {"summary": u"角色目录里的"})
        check(u"认角色目录里的摘要",
              (plug3._latest_summary(u"咲") or {}).get("summary") == u"角色目录里的",
              str(plug3._latest_summary(u"咲")))
        os.remove(os.path.join(mem, u"咲", u"咲.summary.json"))
        wj(os.path.join(mem, u"咲.summary.json"), {"summary": u"老位置的"})
        check(u"角色目录没有时回落到老位置",
              (plug3._latest_summary(u"咲") or {}).get("summary") == u"老位置的",
              str(plug3._latest_summary(u"咲")))

        print(u"\n== ⑦ 单个角色的老布局不动（等它自己写新布局）==")
        base2 = os.path.join(tmp, "app2")
        mem2 = os.path.join(base2, "memory")
        os.makedirs(os.path.join(base2, "saves"), exist_ok=True)
        wj(os.path.join(mem2, "chain.json"), {u"单人": [{"part": 1, "path": u"单人.part1.json"}]})
        wj(os.path.join(mem2, u"单人.part1.json"), {})
        p = load_plugin(base2)
        moved3, roles3 = p.migrate_legacy()
        check(u"只有 1 个角色 → 不迁移（避免无谓搬动）",
              moved3 == 0 and roles3 == [], u"%s %s" % (moved3, roles3))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("MEM_LAYOUT_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌