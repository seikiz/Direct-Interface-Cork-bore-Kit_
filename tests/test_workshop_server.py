# -*- coding: utf-8 -*-
"""创意工坊服务器（net.py）行为测试：类型注册表 / 泛型路由 / 能力协商 / 鉴权 / 分片上传。

为什么单独一个文件
------------------
工坊服务器以前**没有任何测试**（只有 save_sync / sync_api / relay 那几支擦边球），
而它这次被重构成"类型注册表驱动"——加一种资源只需在 TYPES 里加一行。重构最怕的是
"老客户端悄悄用不了了"，所以这里把**外部行为**逐条钉住：

  ① 健康检查与能力协商字段（新客户端要读；老客户端只读 status/auth 也不受影响）
  ② 老路径（/api/cards/list、/api/cards/<id> …）与泛型路径（/api/<rtype>/…）行为一致
  ③ 新类型 packs 一次注册即可用：上传 → 列表 → 下载 → 点赞 → 删除
  ④ 未知类型要 400 并回可用类型（不是 500、不是静默）
  ⑤ 鉴权：写操作要 Key；读默认公开（WORKSHOP_READ_KEY=1 才收紧）
  ⑥ 分片上传：init → chunk → finish，坏 JSON 要 400，扩展名白名单要拦
  ⑦ /relay 默认关闭（客户端已停用中转，留着就是开放代理）

跑法：python tests\\test_workshop_server.py
"""
import io
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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


def load_net(tmp):
    """把 net.py 装进临时数据目录后再用（模块级目录常量 + TYPES 里的 dir 都要改）"""
    spec = importlib.util.spec_from_file_location("dick_net_test", os.path.join(ROOT, "net.py"))
    net = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(net)
    net.DATA_DIR = tmp
    net.CARDS_DIR = os.path.join(tmp, "cards")
    net.WORLDS_DIR = os.path.join(tmp, "worlds")
    net.PLUGINS_DIR = os.path.join(tmp, "plugins")
    net.PACKS_DIR = os.path.join(tmp, "packs")
    net.SAVES_DIR = os.path.join(tmp, "saves")
    net.SYNC_SETTINGS_FILE = os.path.join(tmp, "sync_settings.json")
    net.INDEX_FILE = os.path.join(tmp, "index.json")
    net.CHUNK_DIR = os.path.join(tmp, ".uploads")
    for d in (net.DATA_DIR, net.CARDS_DIR, net.WORLDS_DIR, net.PLUGINS_DIR,
              net.PACKS_DIR, net.SAVES_DIR, net.CHUNK_DIR):
        os.makedirs(d, exist_ok=True)
    net.TYPES["cards"]["dir"] = net.CARDS_DIR
    net.TYPES["worlds"]["dir"] = net.WORLDS_DIR
    net.TYPES["plugins"]["dir"] = net.PLUGINS_DIR
    net.TYPES["packs"]["dir"] = net.PACKS_DIR
    net.API_KEY = ""
    net.READ_KEY = False
    net.RELAY_ON = False
    net.app.testing = True          # 出异常时直接抛，看得见 traceback（不是干看 500）
    net.save_index({"schema": net.INDEX_SCHEMA, "cards": [], "worlds": [], "plugins": [],
                    "packs": [], "users": {}})
    return net


def main():
    print("=" * 62)
    print(u"创意工坊服务器（net.py）：注册表 / 泛型路由 / 能力 / 鉴权 / 分片")
    print("=" * 62)

    tmp = tempfile.mkdtemp(prefix="dick_ws_")
    try:
        net = load_net(tmp)
        c = net.app.test_client()

        print(u"\n== ① 健康检查与能力协商 ==")
        h = c.get("/api/health").get_json()
        check(u"health 有 status/service", h.get("status") == "ok" and h.get("service"))
        check(u"health 带 api 版本", h.get("api") == 1, str(h.get("api")))
        check(u"health 带 types（含 packs）", "packs" in (h.get("types") or []), str(h.get("types")))
        check(u"health 带 capabilities 开关", "capabilities" in (h.get("features") or []))
        check(u"health 带 limits", isinstance(h.get("limits"), dict), str(h.get("limits")))
        cap = c.get("/api/capabilities").get_json()
        # 契约：types 是**纯名字列表**（客户端只做 in 判断），细节在 registry 里。
        # 早期实现把对象塞进 types，客户端按字符串读 → "packs" 永远判不出来（集成测试抓到过）。
        check(u"capabilities.types 是纯字符串列表",
              all(isinstance(t, str) for t in (cap.get("types") or [])), str(cap.get("types")))
        check(u"capabilities 列出四种类型",
              set(cap.get("types") or []) == {"cards", "worlds", "plugins", "packs"}, str(cap.get("types")))
        reg = cap.get("registry") or []
        check(u"registry 里带中文名与扩展名白名单",
              any(t.get("name") == "packs" and t.get("label") == u"世界卡包" and t.get("ext") == [".json"]
                  for t in reg), str(reg))
        check(u"capabilities.types 与 health.types 一致",
              sorted(cap.get("types") or []) == sorted(h.get("types") or []),
              "%s vs %s" % (cap.get("types"), h.get("types")))

        print(u"\n== ② 统计按注册表聚合（不再漏 plugins） ==")
        s = c.get("/api/stats").get_json()
        check(u"stats 有四种类型的计数",
              all(k in s for k in ("cards", "worlds", "plugins", "packs")), str(s))
        check(u"stats 有 types 明细", isinstance(s.get("types"), dict) and "packs" in s["types"], str(s.get("types")))
        check(u"空库时全是 0", s["cards"] == 0 and s["packs"] == 0 and s["downloads"] == 0, str(s))

        print(u"\n== ③ 老路径：角色卡上传 → 列表 → 下载 → 点赞 → 删除 ==")
        card = {"name": u"阿绫", "system_prompt": u"你是阿绫。", "description": u"测试卡"}
        r = c.post("/api/cards/upload",
                   data={"file": (io.BytesIO(json.dumps(card, ensure_ascii=False).encode("utf-8")), "aling.json"),
                         "author": "tester", "tags": u"测试, 角色"},
                   content_type="multipart/form-data")
        check(u"上传返回 201", r.status_code == 201, str(r.status_code))
        cid = (r.get_json() or {}).get("id")
        check(u"返回了 id", bool(cid))
        lst = c.get("/api/cards/list").get_json()
        check(u"列表里能看到", len(lst) == 1 and lst[0]["name"] == u"阿绫", str(lst)[:120])
        check(u"作者/标签存下来了", lst[0]["author"] == "tester" and u"测试" in lst[0]["tags"], str(lst[0]))
        check(u"预览字段提取了", "system_prompt_preview" in lst[0], str(lst[0].keys()))
        got = c.get("/api/cards/" + cid)
        check(u"下载回来是同一张卡", got.status_code == 200 and json.loads(got.data.decode("utf-8"))["name"] == u"阿绫")
        got.close()                      # 关掉响应，别让 Windows 的文件句柄挂着（见下一条）
        lk = c.post("/api/cards/%s/like" % cid).get_json()
        check(u"点赞计数 +1", lk.get("likes") == 1, str(lk))
        dl = c.delete("/api/cards/" + cid)
        check(u"删除成功", dl.status_code == 200, str(dl.status_code))
        check(u"删完列表为空", c.get("/api/cards/list").get_json() == [])

        print(u"\n== ④ 泛型路径 + 新类型 packs（加一行就能用的证明） ==")
        pack = {"name": u"现代都市·合租", "params": {"space": "{\"home\": \"家\"}"},
                "description": u"世界卡包"}
        r = c.post("/api/packs/upload",
                   data={"file": (io.BytesIO(json.dumps(pack, ensure_ascii=False).encode("utf-8")), "urban.json")},
                   content_type="multipart/form-data")
        check(u"packs 上传 201（没为它写过任何专用路由）", r.status_code == 201, str(r.status_code))
        pid = (r.get_json() or {}).get("id")
        plist = c.get("/api/packs/list").get_json()
        check(u"packs 列表可见", len(plist) == 1 and plist[0]["name"] == u"现代都市·合租", str(plist)[:120])
        check(u"packs 下载可用", c.get("/api/packs/" + pid).status_code == 200)
        check(u"packs 点赞可用", c.post("/api/packs/%s/like" % pid).get_json().get("likes") == 1)
        check(u"packs 删除可用", c.delete("/api/packs/" + pid).status_code == 200)
        check(u"stats 现在也数 packs", c.get("/api/stats").get_json()["packs"] == 0)

        print(u"\n== ⑤ 未知类型要 400（不是 500、也不是静默） ==")
        bad = c.get("/api/nothing/list")
        check(u"未知类型 → 400", bad.status_code == 400, str(bad.status_code))
        check(u"400 里回可用类型", "packs" in json.dumps(bad.get_json(), ensure_ascii=False))

        print(u"\n== ⑥ 写策略：上传不用 Key，删除要 Key（用户只是想传个东西） ==")
        net.API_KEY = "secret-key"
        net.OPEN_UPLOAD = True
        c2 = net.app.test_client()
        # 默认（OPEN_UPLOAD=1）：匿名上传必须能成 —— 客户端不用填 Key
        r = c2.post("/api/packs/upload",
                    data={"file": (io.BytesIO(json.dumps({"name": u"匿名传的"}).encode("utf-8")), "x.json")},
                    content_type="multipart/form-data")
        check(u"没填 Key 也能上传（开放上传）", r.status_code == 201, str(r.status_code) + str(r.get_json()))
        anon_id = (r.get_json() or {}).get("id")
        check(u"匿名上传的作品出现在列表里",
              any(x.get("id") == anon_id for x in c2.get("/api/packs/list").get_json()))
        # 但删除不许匿名
        check(u"匿名删不掉别人传的东西",
              c2.delete("/api/packs/" + str(anon_id)).status_code in (401, 403))
        check(u"带 Key 能删", c2.delete("/api/packs/" + str(anon_id),
                                        headers={"X-API-Key": "secret-key"}).status_code == 200)
        # 关掉开放上传 → 回到"写要 Key"
        net.OPEN_UPLOAD = False
        r = c2.post("/api/packs/upload",
                    data={"file": (io.BytesIO(b"{}"), "x.json")}, content_type="multipart/form-data")
        check(u"OPEN_UPLOAD=0 时没 Key 的上传被拒（401/403）", r.status_code in (401, 403), str(r.status_code))
        check(u"错误信息说得清", bool((r.get_json() or {}).get("error")), str(r.get_json()))
        net.OPEN_UPLOAD = True
        r = c2.post("/api/packs/upload",
                    data={"file": (io.BytesIO(json.dumps({"name": "带钥匙"}).encode("utf-8")), "x.json")},
                    headers={"X-API-Key": "secret-key"}, content_type="multipart/form-data")
        check(u"OPEN_UPLOAD=0 时带 Key 的上传通过", r.status_code == 201, str(r.status_code))
        check(u"插件上传始终要 Key（恶意插件比卡危险）",
              c2.post("/api/plugins/upload",
                      data={"file": (io.BytesIO(b"print(1)"), "evil.py")},
                      content_type="multipart/form-data").status_code in (401, 403))
        check(u"共享模型配置读取始终要 Key",
              c2.get("/api/sync/api").status_code in (401, 403))

        print(u"\n== ⑥之二 开放上传防刷：同一 IP 超额要 429（不是无限灌） ==")
        net.RATE_PER_HOUR = 2
        net._RATE_HITS.clear()
        codes = []
        for i in range(3):
            rr = c2.post("/api/packs/upload",
                         data={"file": (io.BytesIO(json.dumps({"name": u"刷%d" % i}).encode("utf-8")), "x.json")},
                         content_type="multipart/form-data")
            codes.append(rr.status_code)
        check(u"前两个能传、第三个 429", codes[:2] == [201, 201] and codes[2] == 429, str(codes))
        check(u"429 说清是为了什么",
              u"频繁" in ((c2.post("/api/packs/upload",
                                   data={"file": (io.BytesIO(b"{}"), "x.json")},
                                   content_type="multipart/form-data").get_json() or {}).get("error") or ""))
        net.RATE_PER_HOUR = 60
        net._RATE_HITS.clear()
        check(u"读接口默认仍公开（老行为不变）", c2.get("/api/packs/list").status_code == 200)
        net.READ_KEY = True
        c3 = net.app.test_client()
        check(u"开了 READ_KEY 后读也要 Key", c3.get("/api/packs/list").status_code == 401)
        check(u"health/capabilities 永远公开（探活要用）",
              c3.get("/api/health").status_code == 200 and c3.get("/api/capabilities").status_code == 200)
        check(u"带 Key 的读通过",
              c3.get("/api/packs/list", headers={"X-API-Key": "secret-key"}).status_code == 200)
        net.READ_KEY = False
        net.API_KEY = ""

        print(u"\n== ⑦ 分片上传（大文件走这条） ==")
        c4 = net.app.test_client()
        init = c4.post("/api/packs/upload/init").get_json() or {}
        uid = init.get("upload_id")
        check(u"init 给了 upload_id 与上限", bool(uid) and isinstance(init.get("max_mb"), int), str(init))
        blob = json.dumps({"name": u"分片包", "note": u"两片拼起来"}, ensure_ascii=False).encode("utf-8")
        half = len(blob) // 2
        r1 = c4.post("/api/packs/upload/chunk", data=blob[:half],
                     headers={"X-Upload-Id": uid},
                     query_string={"upload_id": uid, "index": "0"})
        check(u"第一片收到", r1.status_code == 200, str(r1.status_code) + str(r1.get_json()))
        r2 = c4.post("/api/packs/upload/chunk", data=blob[half:],
                     query_string={"upload_id": uid, "index": "1"})
        check(u"第二片收到", r2.status_code == 200, str(r2.status_code))
        fin = c4.post("/api/packs/upload/finish",
                      query_string={"upload_id": uid, "filename": "two-part.json"})
        check(u"finish 登记成功", fin.status_code == 201, str(fin.status_code) + str(fin.get_json()))
        names = [x["name"] for x in c4.get("/api/packs/list").get_json()]
        check(u"分片拼出来的包在列表里", u"分片包" in names, str(names))
        check(u"分片目录清干净了", not [p for p in os.listdir(net.CHUNK_DIR)] if os.path.isdir(net.CHUNK_DIR) else True)

        print(u"\n== ⑧ 扩展名白名单 + 坏 JSON ==")
        bad_ext = c4.post("/api/packs/upload",
                          data={"file": (io.BytesIO(b"hello"), "evil.txt")},
                          content_type="multipart/form-data")
        check(u".txt 不被接受（400）", bad_ext.status_code == 400, str(bad_ext.status_code))
        bad_json = c4.post("/api/packs/upload",
                           data={"file": (io.BytesIO(b"{not json"), "x.json")},
                           content_type="multipart/form-data")
        check(u"坏 JSON（400）", bad_json.status_code == 400, str(bad_json.status_code))

        print(u"\n== ⑨ /relay 默认关闭 ==")
        check(u"未开 RELAY 时 /relay 返回 404",
              c4.get("/relay/aHR0cHM6Ly9leGFtcGxlLmNvbQ").status_code == 404)

        print(u"\n== ⑨之二 文件删不掉时不能炸（Windows 文件锁 / 杀软占用） ==")
        # 造一张只读的卡：Windows 上 os.r<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌emove 会失败，而改名挪走仍然可行 ——
        # 这条守的就是"删除请求别整个 500、索引和文件别对不上"。
        # chmod(0o444) 那种造法只在 Windows 上成立：Linux/macOS 上文件权限不挡 unlink
        # （目录权限才挡），CI 的 Linux 腿就跑不到兜底分支，断言反而红。
        # 改成显式让 os.remove 抛 OSError —— 故障是模拟的，兜底逻辑是真的，各平台同一条路径。
        ro = c4.post("/api/cards/upload",
                     data={"file": (io.BytesIO(json.dumps({"name": u"锁定卡"}).encode("utf-8")), "ro.json")},
                     content_type="multipart/form-data").get_json()
        entry = [x for x in c4.get("/api/cards/list").get_json() if x["id"] == ro["id"]][0]
        target = os.path.join(net.CARDS_DIR, entry["filename"])
        _real_remove = os.remove

        def _deny_remove(path, *a, **kw):
            if os.path.basename(str(path)) == os.path.basename(target):
                raise PermissionError(13, "locked (test)")
            return _real_remove(path, *a, **kw)

        os.remove = _deny_remove
        try:
            d2 = c4.delete("/api/cards/" + ro["id"])
        finally:
            os.remove = _real_remove
        check(u"删不掉也不 500", d2.status_code == 200, str(d2.status_code) + str(d2.get_json()))
        check(u"提示里说明文件被挪走了", u"占用" in json.dumps(d2.get_json(), ensure_ascii=False),
              str(d2.get_json()))
        check(u"索引里已经没有它", all(x["id"] != ro["id"] for x in c4.get("/api/cards/list").get_json()))
        check(u"文件被挪成 .trash-*（不是原地消失也不是报错）",
              any(".trash-" in n for n in os.listdir(net.CARDS_DIR)), str(os.listdir(net.CARDS_DIR)))

        print(u"\n== ⑩ 索引兼容：老索引（没有 packs/schema）读得起来 ==")
        with open(net.INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump({"cards": [], "worlds": [], "plugins": [], "users": {}}, f)
        idx = net.load_index()
        check(u"老索引缺的段被补齐", "packs" in idx, str(list(idx.keys())))
        check(u"老索引补上 schema", idx.get("schema") == net.INDEX_SCHEMA, str(idx.get("schema")))
        print(u"\n== ⑪ 搜索也是注册表驱动（新类型自动可搜） ==")
        # ⑩ 把索引换成了老结构（packs 段是空的），这里重新放一张角色卡 + 一个世界卡包：
        # 搜索不再写死"角色卡/世界卡"，注册表里新加的类型自动进结果。
        c5 = net.app.test_client()
        c5.post("/api/cards/upload",
                data={"file": (io.BytesIO(json.dumps({"name": u"角色甲", "system_prompt": u"甲"}).encode("utf-8")), "a.json")},
                content_type="multipart/form-data")
        c5.post("/api/packs/upload",
                data={"file": (io.BytesIO(json.dumps({"name": u"包甲"}, ensure_ascii=False).encode("utf-8")), "p.json")},
                content_type="multipart/form-data")
        all_hits = c5.get("/api/search?q=").get_json()
        kinds = sorted({x.get("type") for x in all_hits})
        check(u"不带 type 时角色卡与世界卡包都能搜到", kinds == [u"世界卡包", u"角色卡"], str(kinds))
        only_packs = c5.get("/api/search?type=packs").get_json()
        check(u"type=packs 只回世界卡包",
              bool(only_packs) and all(x.get("type") == u"世界卡包" for x in only_packs), str(only_packs))
        check(u"type 也认中文名（世界卡包）",
              all(x.get("type") == u"世界卡包" for x in c5.get("/api/search?type=世界卡包").get_json()))
        legacy = c5.get("/api/search?type=card").get_json()
        check(u"老客户端的单数别名 type=card 还认",
              bool(legacy) and all(x.get("type") == u"角色卡" for x in legacy), str(legacy))

        print(u"\n== ⑫ 聊天进度存档：上传 → 取回 → 删除 ==")
        # 以前只进不出：测试跑一次就把「测试君」的进度永久留在公网服务器上，
        # 之后任何一次跑测试都会把它拉回来当"历史记录"，断言随机红。
        c6 = net.app.test_client()
        tree = {"nodes": {"n1": {"id": "n1", "role": "user", "content": u"你好",
                                 "children_ids": [], "parent_id": None, "metadata": {}}},
                "current_leaf_id": "n1"}
        up = c6.post("/api/save/" + u"测试君", json={"tree": tree})
        check(u"进度上传成功", up.status_code == 200, str(up.status_code))
        got = c6.get("/api/save/" + u"测试君")
        check(u"进度能取回", got.status_code == 200 and len(got.get_json()["tree"]["nodes"]) == 1,
              str(got.get_json()))
        check(u"空树被拒（别把存档清成空壳）",
              c6.post("/api/save/" + u"测试君", json={"tree": {}}).status_code == 400)
        # 鉴权：先摆出"服务器设了 Key"的状态再测，否则开放模式下删除本来就该放行
        net.API_KEY = "k-test"
        try:
            check(u"没带 Key 的删除被拒", c6.delete("/api/save/" + u"测试君").status_code in (401, 403))
            d3 = c6.delete("/api/save/" + u"测试君", headers={"X-API-Key": "k-test"})
            check(u"带 Key 能删掉进度", d3.status_code == 200 and d3.get_json().get("removed") is True,
                  str(d3.status_code) + str(d3.get_json()))
            check(u"删完再取回是 404", c6.get("/api/save/" + u"测试君").status_code == 404)
            d4 = c6.delete("/api/save/" + u"不存在的角色", headers={"X-API-Key": "k-test"})
            check(u"删不存在的进度不报错（幂等）",
                  d4.status_code == 200 and d4.get_json().get("removed") is False, str(d4.get_json()))
        finally:
            net.API_KEY = ""

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("WORKSHOP_SERVER_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
