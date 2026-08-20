# -*- coding: utf-8 -*-
"""抽取 index.html 的所有 <script> 块，用 node --check 验证 JS 语法"""
import re
import subprocess
import sys
import tempfile
import os

sys.stdout.reconfigure(encoding="utf-8")
HTML = r"C:\Users\seiki\Desktop\dist\web\index.html"
html = open(HTML, encoding="utf-8").read()

scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", html)
print("script blocks:", len(scripts))

all_ok = True
for i, s in enumerate(scripts):
    if not s.strip():
        continue
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(s)
        path = f.name
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    os.unlink(path)
    if r.returncode != 0:
        all_ok = False
        print(f"--- block {i} SYNTAX ERROR ---")
        print(r.stderr[:3000])
    else:
        print(f"block {i}: OK ({len(s)} chars)")

# CODEX 关键函数存在性
for fn in ["codexOpen", "codexLoadList", "codexPlay", "codexNextLine", "codexTypeText",
           "codexShowChoice", "codexShowEnd", "codexPlayerExit", "codexGoto",
           "codexStartScene", "codexLoadAsset", "codexSkipTyping", "codexScheduleAuto"]:
    print(fn, "->", "OK" if fn in html else "MISSING")

# HTML id 配对
for i in ["codexModal", "codexPlayer", "cxTitle", "cxEnd", "codexJsonInput",
          "codexList", "codexDetail", "cxTextbox", "codexEditor", "codexFiles"]:
    print("id", i, "->", ("OK" if ('id="' + i + '"') in html else "MISSING"))

print("ALL JS OK" if all_ok else "JS ERRORS FOUND")
sys.exit(0 if all_ok else 1)
