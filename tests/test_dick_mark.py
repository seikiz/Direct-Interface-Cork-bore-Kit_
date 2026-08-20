# -*- coding: utf-8 -*-
"""反抄袭溯源水印测试：架构级签名的每一层都必须在位。
① codex.json 打包注入 _signature  ② 打包 HTML 注释+JS 标识
③ PNG 嵌卡 dick_mark 块           ④ config.json 指纹
⑤ 前端 控制台/DOM/角落水印        ⑥ 签名常量一致性
运行：python tests/test_dick_mark.py"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import dick_mark
import codex_core
import card_compat

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

print("== ① 签名常量 ==")
check(dick_mark.MARK_JS == "DICK_CODEX_SIG_7f3a9c2e", "架构标识常量")
check("DICK" in dick_mark.SIGNATURE, "来源声明含 DICK")
check(len(dick_mark.finger("x")) == 24, "指纹 24 位十六进制")
check(dick_mark.finger("a") != dick_mark.finger("b"), "不同盐值指纹不同")

print("== ② 打包 HTML 水印 ==")
tmp = tempfile.mkdtemp()
ok1, pkg = codex_core.make_sample_package(tmp, "水印测试")
out = os.path.join(tmp, "wm.html")
codex_core.build_standalone_file(pkg, out)
html = open(out, encoding="utf-8").read()
check("Direct-Interface" in html, "HTML 注释水印")
check("__DICK_MARK" in html and "DICK_CODEX_SIG" in html, "JS 标识变量")
check("DICK_CODEX_SIG" in html, "剧本 _signature 随打包注入")
check(html.count("<script>") == 1, "水印不破坏 HTML 结构")

print("== ③ PNG 嵌卡水印 ==")
png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63fcffff3f030005fe02fea72bcb9b0000000049454e44ae426082")
card = {"spec": "chara_card_v2", "name": "x", "data": {"name": "x"}}
marked = card_compat.png_embed_card(png, card)
texts = {}
for ct, data in card_compat._chunks(marked):
    if ct == b"tEXt":
        kw, t = card_compat._tEXt_read(data)
        texts[kw] = t
check("dick_mark" in texts, "PNG 含 dick_mark tEXt 块")
check("Direct-Interface" in texts.get("dick_mark", ""), "PNG 水印内容正确")

print("== ④ 前端水印 ==")
web = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
check("console.log" in web and "CODEX engine" in web, "控制台标识")
check("data-dick" in web, "DOM 属性标记")
check("position:fixed;right:2px" in web, "角落极淡水印")

print("== ⑤ 源码架构标识 ==")
core_src = open(os.path.join(ROOT, "DICK_core.py"), encoding="utf-8").read()
check("CODEX engine" in core_src or "Direct-Interface" in core_src, "DICK_core 架构标识")
mark_src = open(os.path.join(ROOT, "dick_mark.py"), encoding="utf-8").read()
check("反抄袭" in mark_src and "不可剥离" in mark_src, "dick_mark 模块声明")

shutil.rmtree(tmp)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
