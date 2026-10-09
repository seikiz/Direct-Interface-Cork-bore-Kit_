# -*- coding: utf-8 -*-
"""PowerShell 脚本的编码防线：带中文的 .ps1 必须有 UTF-8 BOM。

为什么这条要单独守
------------------
Windows PowerShell 5.1（就是 `powershell -File xxx.ps1` 那个）读脚本文件时**默认按 ANSI/GBK**
解码，只有当文件开头有 UTF-8 BOM 时才按 UTF-8 读。手机端的 `selftest\\run.ps1` 里全是中文注释，
于是发生了一件很隐蔽的事：

  · 注释里的 UTF-8 中文字节被按 GBK 成对解码 → 出现乱码；
  · GBK 的双字节序列会把行尾的 `\\n`(0x0A) 一起"吃掉" → **注释行被合并**；
  · 合并之后 `function Invoke-Kotlinc {` 落进了上一行的注释里 → 函数体裸露 →
    整个脚本报 `意外的标记"}"`，而报错行号指向一句无害的注释。

它不会报"编码错误"，只会报语法错，而且报错行跟真正的原因差着好几行 —— 这种坑值得用测试钉住。
本仓库里 `DICK-Narrative\\build.ps1`、`tunnel_keepalive.ps1`、`_ui.ps1` 一直带 BOM 就是这个原因。

规则：**含非 ASCII 字符的 .ps1 必须带 BOM**；纯 ASCII 的脚本（npm.ps1 / Activate.ps1 之类）
不强制 —— 它们没有解码风险。

跑法：python tests\\test_ps1_encoding.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 第三方/工具自带目录：不参与（它们<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌要么是 ASCII，要么不该我们改）
SKIP_DIRS = ("node_modules", ".git", ".gradle", ".kotlin", "build", ".idea",
             "utau_env", "tavern-installer", "_internal", "site-packages")

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


def ps1_files():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.lower().endswith(".ps1"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 58)
    print(u"PowerShell 脚本编码检查（带中文 → 必须有 BOM）")
    print("=" * 58)

    files = ps1_files()
    check(u"扫到了 PowerShell 脚本", len(files) >= 5, u"只找到 %d 个" % len(files))

    need_bom, has_bom, ascii_only, bad_utf8 = [], [], [], []
    for p in files:
        rel = os.path.relpath(p, ROOT)
        with open(p, "rb") as f:
            raw = f.read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text = raw.decode("utf-8-sig")
            ok_utf8 = True
        except UnicodeDecodeError as e:
            ok_utf8 = False
            text = ""
            bad_utf8.append((rel, str(e)))
        non_ascii = any(ord(c) > 127 for c in text)
        if not ok_utf8:
            continue
        if non_ascii:
            (has_bom if bom else need_bom).append(rel)
        else:
            ascii_only.append(rel)

    check(u"没有解不成 UTF-8 的脚本", not bad_utf8, u"%s" % bad_utf8[:3])

    print(u"\n-- 含中文的脚本：%d 个 --" % (len(has_bom) + len(need_bom)))
    for rel in has_bom:
        print(u"  [OK] %s（有 BOM）" % rel)
    check(u"含中文的脚本都带 BOM（否则 PS 5.1 会按 GBK 读、注释行被吃掉）",
          not need_bom, u"缺 BOM：%s" % need_bom)

    # 手机端自检脚本是这条规矩的来源：它必须能被 PS 5.1 解析
    run_ps1 = os.path.join(ROOT, "DICK-Android", "selftest", "run.ps1")
    check(u"手机端 selftest\\run.ps1 存在", os.path.isfile(run_ps1))
    if os.path.isfile(run_ps1):
        with open(run_ps1, "rb") as f:
            raw = f.read()
        check(u"selftest\\run.ps1 带 BOM（README 里写的是 powershell -File 调它）",
              raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        check(u"它对拍步骤在（第 3 步）", u"ParityGoldens.kt" in text and u"LifeParityTest.kt" in text)
        check(u"它写了为什么必须有 BOM（免得下一个人又踩）", u"BOM" in text or u"GBK" in text)

    print(u"\n-- 纯 ASCII 的脚本（不强制）：%d 个 --" % len(ascii_only))

    print("\n" + "=" * 58)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("PS1_ENCODING_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
