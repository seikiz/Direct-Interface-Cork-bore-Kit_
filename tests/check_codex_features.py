# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding="utf-8")
html = open(r"C:\Users\seiki\Desktop\dist\web\index.html", encoding="utf-8").read()
checks = {
    "codexSpriteCss": "codexSpriteCss" in html,
    "cxSprites div": 'id="cxSprites"' in html,
    "codexSetSprites": "codexSetSprites" in html,
    "sprites array": "ln.sprites" in html,
    "pos field": "ln.pos" in html,
    "scene sprites": "codexPlayer.scene.sprites" in html,
    "pack btn": "codexPackBtn" in html,
    "pack save btn": "codexPackSaveBtn" in html,
    "pack info": "codexPackInfo" in html,
}
for k, v in checks.items():
    print(k, "->", v)
