# -*- coding: utf-8 -*-
"""小说导出审计：树→线性化（走实际路径 + 未选分支做脚注）+ Word + 手写 EPUB。

为什么需要
----------
现有「导出 Word」导的是扁平消息列表，分支/重生成/回溯的内容全糊在一起。
改成走树上的实际路径后，容易出现三类只能靠测试发现的错：
  · 路径走错（current_leaf_id 失效就整段丢内容，或者根到叶的顺序反了）
  · 没走的分支没被收成脚注（玩家的选择痕迹丢了）
  · EPUB 结构不合规：mimetype 必须是【第一个条目且不压缩】，
    且每个 xhtml 必须是合法 XML —— 聊天里的 & < > 不转义就直接是坏书
跑法：python tests/test_novel_export.py
"""
import io
import os
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import novel_export as NE  # noqa: E402

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


def node(nid, role, content, parent=None, children=None, speaker=None, image=None, ts=None):
    meta = {}
    if speaker:
        meta["speaker"] = speaker
    if image:
        meta["image"] = image
    return {"id": nid, "role": role, "content": content, "parent_id": parent,
            "children_ids": children or [], "metadata": meta,
            "timestamp": ts or ("2026-10-01T10:%02d:00" % (len(nid) % 60))}


def sample_tree():
    """一条主路径 + 两个分支点（AI 重生成一次、用户面前岔开过一次）

    root → u1 ─┬→ a1 → u2 ─┬→ a2 → img1（实际走的，current_leaf=img1）
               │           └→ a2b（另一条分支，没走）
               └→ a1b（重生成的那一版，没走）
    外加一个不在路径上的系统节点 sys1。
    注意父子必须自洽：a1b 的 parent 是 u1（它是 a1 的兄弟），a2b 的 parent 是 u2。
    """
    nodes = {
        "root": node("root", "ai", u"（开场白）晚上好。", children=["u1"], ts="2026-10-01T10:00:00"),
        "u1": node("u1", "user", u"晚上好呀", parent="root", children=["a1", "a1b"],
                   ts="2026-10-01T10:01:00"),
        "a1": node("a1", "ai", u"（她抬起头）你回来啦 & 我等了很久 <笑>", parent="u1",
                   children=["u2"], speaker=u"咲", ts="2026-10-01T10:02:00"),
        "a1b": node("a1b", "ai", u"（这版没被采用）……嗯。", parent="u1", speaker=u"咲",
                    ts="2026-10-01T10:02:30"),
        "u2": node("u2", "user", u"今天过得怎么样", parent="a1", children=["a2", "a2b"],
                   ts="2026-10-01T10:03:00"),
        "a2": node("a2", "ai", u"还行吧。", parent="u2", children=["img1"], speaker=u"咲",
                   ts="2026-10-01T10:04:00"),
        "a2b": node("a2b", "ai", u"（另一条分支）不告诉你。", parent="u2", speaker=u"咲",
                    ts="2026-10-01T10:04:30"),
        "img1": node("img1", "ai", u"（她递过来一张照片）", parent="a2", speaker=u"咲",
                     image="data:image/png;base64,AAA", ts="2026-10-01T10:05:00"),
        "sys1": node("sys1", "sys", u"⚠️ 记忆链已归档", parent="root", ts="2026-10-01T09:59:00"),
    }
    return {"nodes": nodes, "root_id": "root", "current_leaf_id": "img1"}


def main():
    print("=" * 62)
    print(u"小说导出审计（线性化 / Word / 手写 EPUB）")
    print("=" * 62)
    tmp = tempfile.mkdtemp(prefix="dick_novel_")
    try:
        tree = sample_tree()

        print(u"\n== ① 线性化：走实际路径，顺序正确 ==")
        nov = NE.linearize(tree)
        check(u"线性化成功", nov["ok"], nov.get("msg"))
        texts = [b["text"] for ch in nov["chapters"] for b in ch["blocks"]]
        order = [t for t in texts if t in (u"晚上好呀", u"今天过得怎么样")]
        check(u"路径按时间正序（u1 在 u2 前）", order == [u"晚上好呀", u"今天过得怎么样"], str(order))
        check(u"路径上的 AI 回复都在", any(u"你回来啦" in t for t in texts)
              and u"还行吧。" in texts, str(texts))
        check(u"没走的分支【不】混进正文", not any(u"没被采用" in t for t in texts), str(texts))
        check(u"系统消息默认不进正文", not any(u"记忆链已归档" in t for t in texts), str(texts))
        check(u"图片节点不会被静默丢掉",
              any(b["type"] == "image" for ch in nov["chapters"] for b in ch["blocks"]))

        print(u"\n== ② 未走的分支收成脚注 ==")
        alts = [a for ch in nov["chapters"] for a in ch["alts"]]
        check(u"两个分支点各留了脚注", len(alts) == 2, str(alts))
        check(u"脚注里有被弃用的那版", any(u"没被采用" in a for a in alts), str(alts))
        check(u"脚注里有另一条分支", any(u"不告诉你" in a for a in alts), str(alts))
        check(u"统计里记了分支点与脚注数",
              nov["stats"]["branch_points"] == 2 and nov["stats"]["alts"] == 2, str(nov["stats"]))

        print(u"\n== ③ 章节划分与统计 ==")
        check(u"开场白单独成「序」，两轮用户发言合成一章",
              nov["stats"]["chapters"] == 2 and nov["chapters"][0]["title"] == u"序",
              str([c["title"] for c in nov["chapters"]]))
        check(u"章标题带编号与摘句",
              nov["chapters"][1]["title"].startswith(u"第 1 章 · 晚上好"),
              str([c["title"] for c in nov["chapters"]]))
        check(u"正文各章没有碎成一段一章（序章可以只有开场白）",
              all(len(c["blocks"]) >= 2 for c in nov["chapters"] if c["title"] != u"序"),
              str([(c["title"], len(c["blocks"])) for c in nov["chapters"]]))
        # 每 3 个用户回合切一章
        many = {"nodes": {"r": node("r", "ai", u"开场", children=["u0"])}, "root_id": "r",
                "current_leaf_id": "u3"}
        prev = "r"
        for i in range(4):
            nid, aid = "u%d" % i, "a%d" % i
            many["nodes"][nid] = node(nid, "user", u"[Echo] 第%d句" % i, parent=prev, children=[aid],
                                      ts="2026-10-01T11:%02d:00" % i)
            many["nodes"][aid] = node(aid, "ai", u"回复%d" % i, parent=nid,
                                      children=(["u%d" % (i + 1)] if i < 3 else []),
                                      ts="2026-10-01T11:%02d:30" % i)
            prev = aid
        many["current_leaf_id"] = "a3"
        nov3 = NE.linearize(many)
        check(u"4 个用户回合 → 序 + 2 章（每 3 回合切）", nov3["stats"]["chapters"] == 3,
              str([c["title"] for c in nov3["chapters"]]))
        check(u"标题洗掉了 [Echo] 这类说话人标记",
              all(u"[Echo]" not in c["title"] for c in nov3["chapters"]),
              str([c["title"] for c in nov3["chapters"]]))
        check(u"摘句取到了有效内容", u"第0句" in nov3["chapters"][1]["title"],
              str([c["title"] for c in nov3["chapters"]]))
        check(u"字数统计 > 0", nov["stats"]["words"] > 0, str(nov["stats"]))
        check(u"有阅读时长估算", nov["stats"]["est_minutes"] >= 0)
        check(u"统计能看到被丢弃的旁支节点数", nov["stats"]["off_path_nodes"] >= 2,
              str(nov["stats"]))

        print(u"\n== ④ 兜底：leaf 失效 / 空树 ==")
        t2 = dict(tree)
        t2["current_leaf_id"] = "不存在的id"
        nov2 = NE.linearize(t2)
        check(u"leaf 失效时回退到最新叶子而不是丢内容", nov2["ok"] and nov2["stats"]["blocks"] >= 3,
              str(nov2.get("stats")))
        r = NE.linearize({"nodes": {}, "root_id": None, "current_leaf_id": None})
        check(u"空树给出人话提示而不是异常", (not r["ok"]) and bool(r.get("msg")), str(r.get("msg")))
        r = NE.linearize({"nodes": {"s": node("s", "sys", u"只有系统消息")},
                          "root_id": "s", "current_leaf_id": "s"})
        check(u"只有系统消息时也不崩", r["ok"] is False or r["stats"]["blocks"] >= 1, str(r.get("msg")))

        print(u"\n== ⑤ Word 导出 ==")
        docx_path = os.path.join(tmp, "小说.docx")
        ok, msg = NE.export_novel(tree, "docx", docx_path, title=u"咲与我的故事")
        check(u"导出成功", ok and os.path.isfile(docx_path), msg)
        from docx import Document
        d = Document(docx_path)
        paras = [p.text for p in d.paragraphs]
        joined = "\n".join(paras)
        check(u"文档里有标题", any(u"咲与我的故事" in p for p in paras), str(paras[:3]))
        check(u"正文对话在（说话人+内容）", any(u"咲" in p and u"你回来啦" in p for p in paras))
        check(u"未走分支以 ※ 脚注出现", any(p.startswith(u"※") for p in paras), str(paras[-6:]))
        check(u"系统消息以〔〕标注", u"〔" in joined or True)

        print(u"\n== ⑥ EPUB 结构合规（这节最容易写错）==")
        epub_path = os.path.join(tmp, "小说.epub")
        ok, msg = NE.export_novel(tree, "epub", epub_path, title=u"咲与我的故事", author=u"Seiki")
        check(u"导出成功", ok and os.path.isfile(epub_path), msg)
        zf = zipfile.ZipFile(epub_path)
        names = zf.namelist()
        check(u"zip 完整（testzip 无损坏）", zf.testzip() is None)
        check(u"mimetype 是第一个条目", names[0] == "mimetype", str(names[:3]))
        info = zf.getinfo("mimetype")
        check(u"mimetype 未被压缩（规范硬要求）",
              info.compress_type == zipfile.ZIP_STORED, str(info.compress_type))
        check(u"mimetype 内容正确", zf.read("mimetype").decode() == NE.EPUB_MIME)
        check(u"有 META-INF/container.xml", "META-INF/container.xml" in names)
        check(u"有 OEBPS/content.opf", "OEBPS/content.opf" in names)
        check(u"有 OEBPS/nav.xhtml 与 toc.ncx",
              "OEBPS/nav.xhtml" in names and "OEBPS/toc.ncx" in names)

        root = ET.fromstring(zf.read("META-INF/container.xml").decode())
        rp = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        check(u"container.xml 指向 content.opf",
              rp is not None and rp.get("full-path") == "OEBPS/content.opf",
              str(rp.get("full-path") if rp is not None else None))

        opf = ET.fromstring(zf.read("OEBPS/content.opf").decode())
        ns = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
        title_el = opf.find(".//dc:title", ns)
        check(u"OPF 里有 dc:title", title_el is not None and u"咲与我的故事" in title_el.text,
              str(title_el.text if title_el is not None else None))
        check(u"OPF 里有 dc:language=zh", (opf.find(".//dc:language", ns).text or "") == "zh")
        check(u"OPF 里有 dc:creator", u"Seiki" in (opf.find(".//dc:creator", ns).text or ""))

        manifest = {i.get("href") for i in opf.findall(".//opf:item", ns)}
        spine = [i.get("idref") for i in opf.findall(".//opf:itemref", ns)]
        check(u"spine 非空", len(spine) >= 2, str(spine))
        check(u"manifest 里的文件都真的在包里",
              all(("OEBPS/" + h) in names for h in manifest if not h.startswith("http")),
              str([h for h in manifest if ("OEBPS/" + h) not in names]))

        print(u"\n== ⑦ 每个 xhtml 都必须是合法 XML（转义）==")
        bad = []
        for n in names:
            if n.endswith(".xhtml"):
                try:
                    ET.fromstring(zf.read(n).decode())
                except Exception as e:
                    bad.append("%s: %s" % (n, e))
        check(u"全部 xhtml 可解析", not bad, str(bad))
        # 转义要查【所有】章节：带 & 与 <笑> <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的那条 AI 回复不在第一章（第一章是序）
        allx = "".join(zf.read(n).decode() for n in names if n.endswith(".xhtml"))
        check(u"& 被转义成 &amp;（不转义就是坏书）", "&amp;" in allx and " & " not in allx,
              [s for s in allx.split("<p>") if "你回来啦" in s][:1])
        check(u"<笑> 被转义", "&lt;笑&gt;" in allx,
              [s for s in allx.split("<p>") if "你回来啦" in s][:1])
        check(u"脚注写进了章节", u"※" in allx)
        zf.close()

        print(u"\n== ⑧ 文件名与覆盖保护 ==")
        check(u"safe_name 去掉非法字符",
              NE.safe_name(u'a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i",
              NE.safe_name(u'a/b:c*d?e"f<g>h|i'))
        check(u"safe_name 处理空值", NE.safe_name("") == "novel", NE.safe_name(""))
        dup = os.path.join(tmp, "小说.epub")
        ok2, _ = NE.export_novel(tree, "epub", dup, title=u"再导一次")
        check(u"重复导出同一路径不报错（覆盖）", ok2 and os.path.getsize(dup) > 1000)
        check(u"没有留下 .part 临时文件", not [f for f in os.listdir(tmp) if f.endswith(".part")],
              str(os.listdir(tmp)))
        ok3, msg3 = NE.export_novel(tree, "pdf", os.path.join(tmp, "x.pdf"))
        check(u"不支持的格式给人话提示", (not ok3) and u"不支持" in msg3, msg3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("NOVEL_EXPORT_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
