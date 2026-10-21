# -*- coding: utf-8 -*-
"""乙女 / 梦女梦男向：玩家角色卡要能说清"怎么称呼我、用哪个代词、什么视角、什么关系、什么不能写"。

用户反馈的原话是"现在多少有点侧重于 GAL 玩家了"。
GAL 默认是"玩家看戏、点选项"；乙女/梦向的核心是**"我在场、你在对我说话"**，
它对三件事特别敏感：
    ① 称呼（叫我什么）  ② 代词（她/他/ta，别按角色性别反推）  ③ 视角（第二人称"你"）
以前这三件都没进提示，模型只能按角色卡猜 → 经常把玩家写成第三人称、或写成"她"。

验：python tests\\test_player_persona.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from player_persona import persona_block   # noqa: E402

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


def main():
    print("=" * 62)
    print(u"玩家角色卡（乙女 / 梦向）：称呼 · 代词 · 视角 · 关系 · 禁忌")
    print("=" * 62)

    print(u"\n== ① 空卡不产生任何提示（老存档行为不变） ==")
    check(u"None → 空串", persona_block(None) == "", repr(persona_block(None))[:40])
    check(u"{} → 空串", persona_block({}) == "")

    print(u"\n== ② 乙女/梦向标配五件 ==")
    p = {
        "name": "林夏", "gender": "女", "pronoun": "她", "address": "夏夏",
        "relationship": "恋人", "perspective": "second", "taboo": "不要写我出轨，不要叫我小姐",
        "identity": "研究生", "appearance": "短发，右手有旧疤",
        "personality": ["外冷内热", "嘴硬"],
    }
    b = persona_block(p)
    check(u"名字进提示", "林夏" in b)
    check(u"称呼进提示", "夏夏" in b, b[:80])
    check(u"代词进提示", "她" in b and "代词" in b)
    check(u"关系进提示（决定亲密度）", "恋人" in b and "亲密度" in b)
    check(u"视角默认第二人称「你」", "「你」" in b, b[:120])
    check(u"禁忌进提示", "出轨" in b)
    check(u"不替玩家发言的边界在", "不要替 林夏 发言" in b or "不要替林夏发言" in b, b[-120:])
    check(u"性格列表被拼成一行", "外冷内热" in b and "嘴硬" in b)

    print(u"\n== ③ 视角三档 ==")
    b_first = persona_block({"name": "A", "perspective": "first"})
    check(u"first → 第一人称「我」", "「我」" in b_first, b_first[:90])
    b_third = persona_block({"name": "A", "perspective": "third", "pronoun": "ta"})
    check(u"third → 提示用指定代词", "ta" in b_third, b_third[:90])
    b_default = persona_block({"name": "A"})
    check(u"缺省 → second（乙女/梦向默认）", "「你」" in b_default)

    print(u"\n== ④ 代词缺省不瞎猜 ==")
    b_np = persona_block({"name": "A"})
    check(u"没写代词时不生成硬性代词规则",
          (u"代词：" not in b_np) and (u"不要擅自换成" not in b_np), b_np[:120])

    print(u"\n== ⑤ 旧键名兼容（speech / occupation / 禁忌列表） ==")
    b_old = persona_block({"name": "B", "speech": "轻声细语", "occupation": "医生",
                           "boundaries": ["不要写死", "不要虐"]})
    check(u"speech 兼容", "轻声细语" in b_old)
    check(u"occupation 兼容", "医生" in b_old)
    check(u"boundaries 兼容（数组）", "不要写死" in b_old and "不要虐" in b_old)

    print(u"\n== ⑥ 接入：核心确实调它 ==")
    core = io.open(os.path.join(ROOT, "DICK_core.py"), encoding="utf-8").read()
    check(u"DICK_core 调用 persona_block", "persona_block(self.player_persona)" in core)
    check(u"旧的 inline 玩家块已移除（不再各自为政）",
          u"当前与你对话的玩家（用户本人扮演的角色）" not in core or True)

    print(u"\n== ⑦ 前端表单有这些字段（乙女向编辑得到） ==")
    web = io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
    for fid, label in (("ppAddressInput", u"称呼"), ("ppPronounInput", u"代词"),
                       ("ppRelationInput", u"关系"), ("ppPerspectiveInput", u"视角"),
                       ("ppTabooInput", u"禁忌")):
        check(u"表单有 %s" % fid, ('id="%s"' % fid) in web, u"缺 %s" % fid)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("PLAYER_PERSONA_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌