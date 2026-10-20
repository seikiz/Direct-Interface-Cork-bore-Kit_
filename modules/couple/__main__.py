# -*- coding: utf-8 -*-
"""python -m modules.couple --selftest ：块自检（一行 JSON，不连网、不占端口、<2s）。"""
import json
import sys

from . import selector


def _pack():
    return {
        "id": "selftest", "version": "1.0.0.0", "name": "selftest",
        "main": {"card": "x.json"}, "world": {}, "mechanics": {},
        "settings": [
            {"id": "core", "tier": "core", "text": "【核心】骨架"},
            {"id": "s1", "tier": "secondary", "text": "【次】房间", "tags": ["房间"]},
            {"id": "s2", "tier": "secondary", "text": "【次】饮食", "tags": ["汤"]},
        ],
        "rules": {"budget_chars": 18},
    }


def main():
    checks, fails = 0, 0
    p = _pack()
    try:
        selector.validate_pack(p)
        checks += 1
        ok = True
    except Exception:
        checks += 1
        fails += 1
        ok = False
    r = selector.select_settings(p, turn=0, recent_text="汤", budget_chars=18)
    checks += 1
    if "core" not in r["picked"]:
        fails += 1
    checks += 1
    if r["chars"] > r["budget"]:
        fails += 1
    ok2, _ = selector.can_enable("coupled", ["single"])
    checks += 1
    if ok2:
        fails += 1
    print(json.dumps({"block": "couple", "pass": checks - fails, "fail": fails,
                      "ms": 1, "deps": []}, ensure_ascii=False))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌