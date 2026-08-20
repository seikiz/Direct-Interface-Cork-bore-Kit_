# -*- coding: utf-8 -*-
"""酒馆(SillyTavern)卡完全适配测试：
v1 / v2 / v3 / PNG 嵌卡(chara, ccv3) / 字符串包裹 / data:URI / 世界书提取 / 结构化字段。
运行：python tests/test_card_compat.py"""
import sys, os, json, base64

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

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

def v2_card(name="测试角色", with_world=True):
    d = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "data": {
            "name": name,
            "description": "她是一个温柔的角色",
            "personality": "温柔、傲娇",
            "scenario": "在咖啡馆相遇",
            "first_mes": "你好，要喝点什么吗？",
            "mes_example": "<START>\n{{user}}: 你好\n{{char}}: 你好",
            "creator_notes": "原创角色",
            "system_prompt": "你是测试角色",
            "post_history_instructions": "保持角色",
            "alternate_greetings": ["另一个开场白", "还有一段"],
            "tags": ["test"],
            "creator": "某人",
            "character_version": "1.0",
            "extensions": {},
        },
    }
    if with_world:
        d["data"]["extensions"]["world"] = {
            "entries": [
                {"keys": ["咖啡", "coffee"], "content": "这家咖啡馆叫「蓝猫」，是主角的秘密基地。",
                 "enabled": True, "insertion_order": 100, "case_sensitive": False,
                 "name": "咖啡馆", "priority": 10, "id": 1, "comment": "",
                 "selective": False, "secondary_keys": [], "constant": False,
                 "position": "before_char"},
                {"keys": ["老板娘"], "content": "老板娘叫玲子，喜欢猫。",
                 "enabled": True, "priority": 5, "id": 2},
            ]
        }
    return d

print("== ① v2 JSON（含世界书 + 结构化字段 + 备用开场） ==")
conv = card_compat.to_dick(v2_card())
check(conv is not None and conv["name"] == "测试角色", "v2 识别 + 名字")
check(conv["system_prompt"] and "温柔" in conv["system_prompt"], "system_prompt 含字段")
check(isinstance(conv["card_data"], dict) and conv["card_data"]["spec"] == "chara_card_v2",
      "card_data 无损保留")
check(conv["fields"].get("personality") == "温柔、傲娇", "结构化字段拆分 personality")
check(conv["fields"].get("background") == "在咖啡馆相遇", "结构化字段 background(scenario)")
check(len(conv["world_entries"]) == 2, "世界书提取 2 条")
check(conv["world_entries"][0]["keywords"] == ["咖啡", "coffee"], "世界书关键词列表")
check(conv["world_entries"][0]["content"] and "蓝猫" in conv["world_entries"][0]["content"], "世界书内容保留")
check(len(conv["alternate_greetings"]) == 2, "备用开场白 2 条")

print("== ② v1 JSON ==")
v1 = {"name": "老卡", "description": "旧版卡", "personality": "沉默",
      "first_mes": "嗨", "mes_example": "例"}
conv1 = card_compat.to_dick(v1)
check(conv1 is not None and conv1["name"] == "老卡", "v1 识别")
check(conv1["fields"].get("personality") == "沉默", "v1 字段拆分")

print("== ③ v3 spec ==")
v3 = json.loads(json.dumps(v2_card("V3卡")))
v3["spec"] = "chara_card_v3"
conv3 = card_compat.to_dick(v3)
check(conv3 is not None and conv3["name"] == "V3卡", "v3 spec 识别")

print("== ④ PNG 嵌卡（chara / ccv3） ==")
# 造 1x1 PNG
png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63fcffff3f030005fe02fea72bcb9b0000000049454e44ae426082")
card = v2_card("PNG卡")
payload = base64.b64encode(json.dumps(card, ensure_ascii=False).encode("utf-8"))
# chara 关键字
png_chara = card_compat.png_embed_card(png, card)
check(png_chara[:8] == b"\x89PNG\r\n\x1a\n", "PNG 嵌卡生成合法")
ext = card_compat.png_extract_card(png_chara)
check(ext is not None and ext.get("spec") == "chara_card_v2", "PNG chara 块提取")
# ccv3 关键字（v3 卡）
png_ccv3 = card_compat.png_embed_card(png, card, v3=True)
ext3 = card_compat.png_extract_card(png_ccv3)
check(ext3 is not None and ext3.get("spec") == "chara_card_v2", "PNG ccv3 块提取")
# data: URI 前缀
d = {"name": "dataURI卡", "description": "x"}
conv_d = card_compat.to_dick(d)
check(conv_d is not None, "纯 DICK 格式识别")

print("== ⑤ 字符串包裹 / data: URI ==")
s = json.dumps(v2_card("包裹卡"))
conv_s = card_compat.to_dick(s)
check(conv_s is not None and conv_s["name"] == "包裹卡", "JSON 字符串解包")
wrapped = json.dumps({"data": json.dumps(v2_card("双层卡"))})
conv_w = card_compat.to_dick(wrapped)
check(conv_w is not None and conv_w["name"] == "双层卡", "data 字段字符串解包")
# 无世界书
conv_nw = card_compat.to_dick(v2_card(with_world=False))
check(conv_nw is not None and conv_nw["world_entries"] == [], "无世界书 → 空列表")

print("== ⑥ 导出回酒馆 v2 ==")
out = card_compat.dick_to_v2("导回", "提示", conv["card_data"])
check(out["spec"] == "chara_card_v2" and out["data"]["name"] == "导回", "card_data 无损回导（名字更新）")
check(out["data"].get("description") == "她是一个温柔的角色", "回导保留 description")
check(out["data"].get("personality") == "温柔、傲娇", "回导保留 personality")
out2 = card_compat.dick_to_v2("新卡", "提示")
check(out2["spec"] == "chara_card_v2" and out2["data"]["system_prompt"] == "提示", "无 card_data 新建 v2")

print("== ⑦ 世界书元字段全量保留（无损往返） ==")
v2_full = json.loads(json.dumps(v2_card("元字段卡")))
v2_full["data"]["extensions"]["world"]["entries"][0].update({
    "name": "咖啡馆设定", "insertion_order": 50, "case_sensitive": True,
    "selective": True, "secondary_keys": ["拿铁", "美式"],
    "comment": "测试注释", "position": "after_char",
})
cf = card_compat.to_dick(v2_full)
check(len(cf["world_entries"]) == 2, "元字段卡导入 2 条")
m0 = cf["world_entries"][0]
check(m0["_meta"].get("insertion_order") == 50, "元字段 insertion_order 保留")
check(m0["_meta"].get("case_sensitive") is True, "元字段 case_sensitive 保留")
check(m0["_meta"].get("selective") is True, "元字段 selective 保留")
check(m0["_meta"].get("secondary_keys") == ["拿铁", "美式"], "元字段 secondary_keys 保留")
check(m0["_meta"].get("comment") == "测试注释", "元字段 comment 保留")
check(m0["_meta"].get("position") == "after_char", "元字段 position 保留")
check(m0["_meta"].get("name") == "咖啡馆设定", "元字段 name 保留")
# 反向：DICK 世界条目 → 酒馆 world entry
st = card_compat.world_to_sillytavern(cf["world_entries"])
check(st[0]["insertion_order"] == 50 and st[0]["case_sensitive"] is True, "反向 insertion_order/case_sensitive")
check(st[0]["secondary_keys"] == ["拿铁", "美式"], "反向 secondary_keys")
check(st[0]["position"] == "after_char", "反向 position")
# 完整往返：导入→导出→再导入，字段一致
roundtrip = card_compat.dick_to_v2("往返", "p", conv["card_data"], world_entries=cf["world_entries"])
back = card_compat.to_dick(roundtrip)
check(len(back["world_entries"]) == 2, "往返世界书 2 条")
b0 = back["world_entries"][0]
check(b0["_meta"].get("insertion_order") == 50 and b0["_meta"].get("position") == "after_char"
      and b0["_meta"].get("secondary_keys") == ["拿铁", "美式"],
      "往返后元字段一致: %r" % b0.get("_meta"))
check(b0["keywords"] == ["咖啡", "coffee"] and b0["content"] and "蓝猫" in b0["content"],
      "往返后关键词/内容一致")
# 无 _meta 条目反向默认值
plain = card_compat.world_to_sillytavern([{"keywords": ["a"], "content": "x"}])
check(plain[0]["position"] == "before_char" and plain[0]["insertion_order"] == 0, "无 _meta 反向默认 position/insertion_order")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
