# -*- coding: utf-8 -*-
"""人物卡的 N 种模式：GAL 与乙女·梦向分开，但陪伴感都必须保留。

用户反馈原话：
    「人物卡可以设定为 N 个模式，两个分开，没有备注，但是陪伴感强需要保留，
      女性疑似需要更多的情感反馈。」

本测试钉住四件事：
  ① N 个模式是表驱动的（加模式只需往 MODES 里加一项，不改代码路径）；
  ② GAL 与乙女/梦向的默认不一样（视角/情感强度/演法都分得开）；
  ③ 模式不需要备注就能生效（一个字段就够，用户不用写说明）；
  ④ 陪伴感不许被模式削掉：情感反馈只调强度（高/轻），
     off 只表示不额外加戏，不存在别陪人这一档。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import card_modes as cm   # noqa: E402

PASS = 0
FAIL = 0


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


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
    print(u"人物卡模式：GAL / 乙女·梦向 / 跑团（分开，但陪伴感保留）")
    print("=" * 62)

    print(u"\n== ① 表驱动，N 个模式 ==")
    check(u"模式表里有 gal / otome / trpg",
          {"gal", "otome", "trpg"} <= set(cm.MODES), str(list(cm.MODES)))
    check(u"每个模式都有 label / perspective / emotion / hints",
          all(all(k in v for k in ("label", "perspective", "emotion", "hints"))
              for v in cm.MODES.values()))

    print(u"\n== ② 两个主要模式分得开 ==")
    gal = cm.mode_block("gal")
    oto = cm.mode_block("otome")
    check(u"GAL 与乙女提示不相等", gal != oto)
    check(u"GAL 讲钩子与推进", ("钩子" in gal) and ("推进" in gal), gal[:80])
    check(u"乙女讲留白与情绪", ("留白" in oto) and ("情绪" in oto), oto[:80])
    check(u"乙女情感反馈是高档（含回扣与被影响）", ("回扣" in oto) and ("被影响" in oto), oto[-160:])
    check(u"GAL 情感反馈是轻档（不每轮深情）", u"一两句就够" in gal, gal[-120:])
    check(u"默认视角：两者都是第二人称（陪伴感）",
          cm.mode_defaults("gal")["perspective"] == "second"
          and cm.mode_defaults("otome")["perspective"] == "second")

    print(u"\n== ③ 不需要备注就能生效 ==")
    check(u"只给 mode 一个字段就有完整提示",
          len(cm.mode_block("otome")) > 60 and (u"备注" not in cm.mode_block("otome")))
    check(u"中文与别名都能解析（乙女/梦女/攻略/跑团）",
          cm.resolve_mode(u"乙女") == "otome" and cm.resolve_mode(u"梦女") == "otome"
          and cm.resolve_mode(u"攻略") == "gal" and cm.resolve_mode(u"跑团") == "trpg")
    check(u"认不出的模式给空串（老卡片行为不变）",
          cm.mode_block("") == "" and cm.mode_block(None) == ""
          and cm.mode_block(u"不存在的模式") == "")

    print(u"\n== ④ 陪伴感不许被模式削掉 ==")
    for m in ("gal", "otome", "trpg"):
        b = cm.mode_block(m)
        check(u"%s 仍保留在场感（这一场怎么演）" % m, u"这一场怎么演" in b)
        check(u"%s 没有削减陪伴感的措辞" % m,
              not any(x in b for x in (u"冷淡", u"别理", u"少说话", u"不要温柔")))
    check(u"情感强度只有 high/light/off 三档",
          set(cm.EMOTION) == {"high", "light", "off"})
    check(u"off 只是不额外加戏，不是别陪人",
          cm.EMOTION["off"] == [] and (u"陪" not in "".join(cm.EMOTION["off"])))

    print(u"\n== ⑤ 覆盖与预填 ==")
    check(u"可以强制 light", u"一两句就够" in cm.mode_block("otome", "light"))
    check(u"off 下不加情感块", u"情绪要落在话上" not in cm.mode_block("otome", "off"))
    d = cm.mode_defaults("otome")
    check(u"mode_defaults 给出 label/perspective/emotional",
          bool(d.get("label") and d.get("perspective") and d.get("emotional")), str(d))

    print(u"\n== ⑥ 接入：核心按 persona.mode 注入 ==")
    import _coresrc
    core = _coresrc.read()   # 核心已拆分：DICK_core.py + core_*.py
    check(u"核心调 mode_block", "mode_block(" in core)
    check(u"模式从玩家卡的 mode 字段读，不需要备注",
          ("get('mode')" in core) or ('get("mode")' in core), "没读 mode")

    print(u"\n== \u2466 \u89c2\u6d4b vs \u4ee3\u5165\uff08\u4e59\u5973\u4e0d\u662f\u770b\u620f\uff09==")
    check(u"\u4e59\u5973 measure=immerse", cm.MODES["otome"]["measure"] == "immerse")
    check(u"GAL measure=observe", cm.MODES["gal"]["measure"] == "observe")
    check(u"\u4e59\u5973\u91cc\u89d2\u8272\u66f4\u4e3b\u52a8\uff08initiative=character\uff09",
          cm.MODES["otome"]["initiative"] == "character")
    check(u"GAL \u91cc\u73a9\u5bb6\u63a8\u8fdb\uff08initiative=player\uff09",
          cm.MODES["gal"]["initiative"] == "player")
    check(u"\u4e59\u5973\u5141\u8bb8\u5199\u300c\u4f60\u300d\u7684\u611f\u53d7",
          cm.MODES["otome"]["narrate_player_feelings"] is True)
    check(u"GAL \u4e0d\u5199\u73a9\u5bb6\u5185\u5fc3\uff08\u955c\u5934\u5bf9\u7740\u5979\uff09",
          cm.MODES["gal"]["narrate_player_feelings"] is False)
    oto = cm.mode_block("otome")
    check(u"\u4e59\u5973\u63d0\u793a\u91cc\u6709\u300c\u53ef\u4ee5\u5199\u4f60\u7684\u611f\u53d7\u300d",
          u"\u53ef\u4ee5\u5199\u300c\u4f60\u300d\u7684\u611f\u53d7" in oto, oto[:200])
    check(u"\u4f46\u4e0d\u8bb8\u66ff\u73a9\u5bb6\u8bf4\u8bdd\u505a\u51b3\u5b9a",
          (u"\u4e0d\u8981\u66ff\u300c\u4f60\u300d\u8bf4\u8bdd" in oto) and (u"\u505a\u51b3\u5b9a" in oto))
    gal = cm.mode_block("gal")
    check(u"GAL \u63d0\u793a\u91cc\u7684\u955c\u5934\u5bf9\u7740\u5979", u"\u955c\u5934\u5bf9\u7740\u5979" in gal)
    d = cm.mode_defaults("otome")
    check(u"mode_defaults \u5e26\u51fa measure/initiative/feeling",
          d.get("measure") == "immerse" and d.get("initiative") == "character"
          and d.get("narrate_player_feelings") is True, str(d))

    print(u"\n== \u2467 \u5b89\u5353\u4eba\u8bbe\u5361\u4e5f\u80fd\u586b\uff08\u548c\u684c\u9762\u5bf9\u9f50\uff09==")
    kt = read(os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app",
                           "ui", "screens", "cardEdit", "PersonaScreen.kt"))
    for key in ("mode", "address", "pronoun", "perspective", "relationship", "taboo"):
        check(u"\u5b89\u5353\u4fdd\u5b58 %s \u5b57\u6bb5" % key,
              ('fields["%s"]' % key) in kt, u"\u7f3a %s" % key)
    check(u"\u5b89\u5353\u6709\u6f14\u6cd5\u4e09\u6309\u94ae\uff08\u653b\u7565/\u4e59\u5973/\u8dd1\u56e2\uff09",
          u"\u4e59\u5973/\u68a6\u5411" in kt and u"\u8dd1\u56e2" in kt and u"\u653b\u7565" in kt)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("CARD_MODES_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌