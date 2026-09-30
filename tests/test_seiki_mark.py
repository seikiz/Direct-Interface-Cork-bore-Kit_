# -*- coding: utf-8 -*-
"""
零宽署名水印测试。

最要命的风险只有一个：**把源码搞坏**。
所以核心断言是「嵌入前后 AST 完全相同」——不是"看起来没坏"。

另一条原则：测试不依赖「仓库当前是否已被标记」。
仓库本身现在就是标记过的，所以凡是要嵌入的输入，先 strip 一遍拿到干净底稿。

跑法：utau_env\\Scripts\\python.exe tests\\test_seiki_mark.py
"""

import ast
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import seiki_mark as sm  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def read(p):
    with io.open(p, encoding="utf-8", newline="") as f:
        return f.read()


def clean(p):
    """读一个真实文件并剥掉签名 —— 测试要的是干净底稿，不是仓库当前状态"""
    styles = sm.COMMENT.get(os.path.splitext(p)[1].lower(), ["#"])
    return sm.strip(read(p), styles)[0]


def payload_of(text):
    """无论哪种规范，取出签名内容；没有则 None"""
    hit = sm.detect_one(text)
    return hit[1] if hit else None


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  编解码
# ============================================================
def test_framed_codec():
    print("\n== 1. framed 编解码 ==")
    for text in ["SEIKI", "SEIKI-2026", "A", "署名", "x" * 40]:
        zw = sm.encode(text)
        check(f"往返 {text[:14]!r}", sm.decode(zw) == text)
        check(f"全是零宽 {text[:10]!r}", all(c in sm.ZW_ALL for c in zw))
    check("空串返回 None", sm.decode("") is None)
    check("非零宽返回 None", sm.decode("hello") is None)
    check("缺尾帧返回 None", sm.decode(sm.encode("SEIKI")[:-1]) is None)
    zw = sm.encode("SEIKI")
    mid = len(zw) // 2
    tampered = zw[:mid] + (sm.ZW1 if zw[mid] == sm.ZW0 else sm.ZW0) + zw[mid + 1:]
    check("改 1 位被校验发现", sm.decode(tampered) is None)
    check("半字节长度被拒",
          sm.decode(sm.ZW_FRAME + sm.ZW0 * 5 + sm.ZW_FRAME) is None)


def test_native_codec():
    print("\n== 2. 原生规范（仓库原本就在用的那套）==")
    zw = sm.encode_sig()
    check("带可见前缀 <seiki>", zw.startswith(sm.SIG_PREFIX))
    body = zw[len(sm.SIG_PREFIX):]
    check("零宽长度 = 字节数 x 4",
          len(body) == len(sm.SIG_TEXT.encode("utf-8")) * 4, "%d" % len(body))
    check("零宽长度 92", len(body) == 92, str(len(body)))
    check("只用 4 种符号", all(c in sm.SIG_SYMBOLS for c in body))
    check("解回原文", sm.decode_sig(body) == sm.SIG_TEXT)
    check("内容是 DICK_CODEX_SIG_*", sm.SIG_TEXT.startswith("DICK_CODEX_SIG_"))
    check("符号数不对时拒绝", sm.decode_sig(body[:-1]) is None)
    check("含非法符号时拒绝", sm.decode_sig(body[:-1] + "x") is None)


# ============================================================
#  安全：不许弄坏代码
# ============================================================
def test_python_ast_unchanged():
    print("\n== 3. 嵌入前后 AST 必须完全一致（最关键）==")
    base = clean(os.path.join(ROOT, "go_engine.py"))
    for fmt in ("native", "framed"):
        new, st, why = sm.embed(base, None, "#", fmt=fmt)
        check(f"[{fmt}] 嵌入成功", st == "ok", why)
        if st != "ok":
            continue
        check(f"[{fmt}] 文本变长", len(new) > len(base))
        try:
            check(f"[{fmt}] AST 完全相同",
                  ast.dump(ast.parse(base)) == ast.dump(ast.parse(new)))
        except SyntaxError as e:
            check(f"[{fmt}] AST 完全相同", False, str(e))
        # 原生规范带可见的 <seiki> 前缀，所以必须用 strip 整体剥离，
        # 不能只滤零宽字符 —— 那会剩下前缀。
        back, _n = sm.strip(new, "#")
        check(f"[{fmt}] 剥掉签名等于原文", back == base)


def test_real_files_compile():
    print("\n== 4. 真实源码嵌入后仍能编译 / import ==")
    targets = ["go_engine.py", "text_guard.py", "crypto_core.py",
               "dick_backup_tool.py", "ui_root.py", "seiki_mark.py"]
    tmp = tempfile.mkdtemp()
    for name in targets:
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            continue
        base = clean(p)
        new, st, why = sm.embed(base, None, "#", fmt="native")
        check(f"{name} 嵌入成功", st == "ok", why)
        if st != "ok":
            continue
        dst = os.path.join(tmp, name)
        io.open(dst, "w", encoding="utf-8", newline="").write(new)
        r = subprocess.run([sys.executable, "-m", "py_compile", dst],
                           capture_output=True, text=True)
        check(f"{name} py_compile 通过", r.returncode == 0, (r.stderr or "")[:200])
        check(f"{name} 签名可读回", payload_of(new) == sm.SIG_TEXT)
        mod = os.path.splitext(name)[0]
        r2 = subprocess.run([sys.executable, "-c",
                             "import sys;sys.path.insert(0,%r);import %s" % (tmp, mod)],
                            capture_output=True, text=True)
        check(f"{name} 真的能 import", r2.returncode == 0, (r2.stderr or "")[:300])


def test_other_languages():
    print("\n== 5. JS / Kotlin / HTML 也不许弄坏 ==")
    js = "// DICK 前端主脚本\nvar a = 1;\nfunction f() { return a; }\n"
    new, st, why = sm.embed(js, None, ["//", ("/*", "*/")], fmt="native")
    check("JS 嵌入成功", st == "ok", why)
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "t.js")
    io.open(p, "w", encoding="utf-8").write(new)
    r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
    check("node --check 通过", r.returncode == 0, (r.stderr or "")[:200])

    kt = "// DICK 安卓端\npackage com.dick.core\nfun main() { }\n"
    new2, st2, why2 = sm.embed(kt, None, ["//", ("/*", "*/")], fmt="native")
    check("Kotlin 嵌入成功", st2 == "ok", why2)
    check("Kotlin 签名可读回", payload_of(new2) == sm.SIG_TEXT)
    check("Kotlin 代码行未动",
          "package com.dick.core" in new2 and "fun main() { }" in new2)

    # Kotlin 常用 /** KDoc */，只认 // 会漏掉大量文件
    kdoc = "/** 对话节点 与 Python 版字段逐一对应 */\nclass Node\n"
    new3, st3, why3 = sm.embed(kdoc, None, ["//", ("/*", "*/")], fmt="native")
    check("单行 KDoc 能当插入点", st3 == "ok" and "注释内" in why3, why3)
    check("KDoc 的 */ 没被破坏", new3.count("*/") == 1)
    check("KDoc 正文还在", "对话节点" in new3)

    html = "<!doctype html>\n<!-- DICK 前端主页面 -->\n<html><body>x</body></html>\n"
    new4, st4, why4 = sm.embed(html, None, [("<!--", "-->")], fmt="native")
    check("HTML 嵌入成功", st4 == "ok", why4)
    check("HTML 签名可读回", payload_of(new4) == sm.SIG_TEXT)
    check("HTML 的 --> 没被破坏", new4.count("-->") == 1)
    check("HTML 标签未动", "<html><body>x</body></html>" in new4)


# ============================================================
#  插入点
# ============================================================
def test_idempotent():
    print("\n== 6. 幂等：跑两次不能嵌两份 ==")
    base = "# 这是一个够长的注释行，用来承载水印\nx = 1\n"
    once, _s, _w = sm.embed(base, None, "#", fmt="native")
    twice, st, why = sm.embed(once, None, "#", fmt="native")
    check("第二次被跳过", st == "skip", why)
    check("内容没变", twice == once)
    check("只有一份签名", len(sm.detect(once)) == 1)
    third, st3, _w3 = sm.embed(once, None, "#", fmt="framed")
    check("换规范也不叠加", st3 == "skip")
    check("没有变成两份", len(sm.detect(third)) == 1)


def test_anchor_safety():
    print("\n== 7. 不许碰文件头和编码声明 ==")
    py = ("# -*- coding: utf-8 -*-\n"
          '"""模块说明"""\n'
          "# 一段足够长的普通注释文字\n"
          "import os\n")
    new, st, why = sm.embed(py, None, "#", fmt="native")
    check("嵌入成功", st == "ok", why)
    check("第 1 行完全没动",
          new.split("\n")[0] == "# -*- coding: utf-8 -*-", repr(new.split("\n")[0]))
    check("coding 声明未被污染",
          "coding: utf-8" in new
          and not any(c in sm.SIG_SYMBOLS for c in new.split("\n")[0]))
    she, st2, _w2 = sm.embed("#!python\n# 足够长的注释内容在这里\nx=1\n",
                             None, "#", fmt="native")
    check("shebang 情形嵌入成功", st2 == "ok")
    if st2 == "ok":
        check("shebang 那行没被动", she.split("\n")[0] == "#!python")


def test_anchor_protects_existing_mark():
    print("\n== 8. 绝不往已有零宽水印里插（会把两串连成一条）==")
    # 真实踩过的坑：注释行是 `# <seiki><92 个零宽>`，
    # 取「正文中点」插入正好落在零宽串里，两串连成 142 个，原水印直接解不出来。
    line = ("# " + sm.encode_sig() + "\n"
            "# 另一行足够长的普通注释文字\n"
            "if x:\n    pass\n")
    new, st, why = sm.embed(line, None, "#", fmt="native")
    check("有现成水印时整体跳过", st == "skip", why)
    check("内容一字未动", new == line)

    line2 = ("# " + sm.encode_sig() + "\n"
             "# 另一行足够长的普通注释文字放在这里\n"
             "y = 1\n")
    new2, st2, why2 = sm.embed(line2, None, "#", fmt="framed")
    check("framed 也不会插进原生那行", st2 == "skip", why2)

    # 反过来：普通注释在前、水印行在后 → 插入点必须落在普通那行
    line3 = ("# 普通注释足够长可以放签名\n"
             "# " + sm.encode_sig() + "\n"
             "z = 1\n")
    n3, s3, w3 = sm.embed(line3, None, "#", fmt="framed")
    check("插入点落在不含零宽的那行", s3 == "skip" or "第 1 行" in w3, w3)
    if s3 == "ok":
        hit = sm.find_sig(n3)
        check("原生签名仍可读", hit is not None)
        if hit:
            check("连成一串的问题没发生",
                  hit[2] - hit[1] - len(sm.SIG_PREFIX) == 92,
                  str(hit[2] - hit[1] - len(sm.SIG_PREFIX)))


def test_payload_not_overwritten():
    print("\n== 9. 不许覆盖已有签名的内容 ==")
    text = "# " + sm.encode_sig() + "\n"
    _new, st, _w = sm.embed(text, None, "#", fmt="native")
    check("已有签名 -> 跳过", st == "skip")
    fresh = "# 一段足够长的注释文字用来放签名\nw = 1\n"
    n2, s2, _w2 = sm.embed(fresh, None, "#", fmt="native")
    check("新文件嵌入成功", s2 == "ok")
    check("用的是 SIG_TEXT 而不是别的",
          payload_of(n2) == sm.SIG_TEXT, repr(payload_of(n2)))


def test_survives_whitespace_trim():
    print("\n== 10. 自动清理行尾空白不能删掉它 ==")
    base = "# 一段足够长的注释用来放签名\nx = 1\n"
    new, st, _w = sm.embed(base, None, "#", fmt="native")
    check("嵌入成功", st == "ok")
    trimmed = "\n".join(ln.rstrip() for ln in new.split("\n"))
    check("清理行尾空白后签名仍在", payload_of(trimmed) == sm.SIG_TEXT)


def test_no_comment_fallback():
    print("\n== 11. 没有可用注释时走兜底 ==")
    short = "# 短\nx=1\n"
    new, st, why = sm.embed(short, None, "#", fmt="native")
    check("短注释也能内嵌", st == "ok" and "注释内" in why, why)
    check("标记还在", new.startswith("# "))
    check("正文没丢", "短" in new)
    try:
        ast.parse(new)
        check("短注释情形仍能解析", True)
    except SyntaxError as e:
        check("短注释情形仍能解析", False, str(e))

    plain = "x = 1\ny = 2\n"
    new2, st2, why2 = sm.embed(plain, None, "#", fmt="native")
    check("纯代码走追加兜底", st2 == "ok" and "追加" in why2, why2)
    check("原代码逐字未动", new2.startswith("x = 1\ny = 2\n"))
    check("strip 后逐字节还原", sm.strip(new2, "#")[0] == plain)

    noeol = "x = 1"
    new3, _s3, _w3 = sm.embed(noeol, None, "#", fmt="native")
    check("没换行结尾时先补换行", new3.split("\n")[0] == "x = 1")
    try:
        ast.parse(new3)
        check("无尾换行的代码仍能解析", True)
    except SyntaxError as e:
        check("无尾换行的代码仍能解析", False, str(e))


def test_strip_exact():
    print("\n== 12. strip 必须逐字节还原 ==")
    for name in ["go_engine.py", "text_guard.py", "crypto_core.py"]:
        p = os.path.join(ROOT, name)
        if not os.path.isfile(p):
            continue
        base = clean(p)
        for fmt in ("native", "framed"):
            new, _s, _w = sm.embed(base, None, "#", fmt=fmt)
            back, n = sm.strip(new, "#")
            check(f"{name} [{fmt}] 还原一致", back == base)
            check(f"{name} [{fmt}] 报告移除了字符", n > 0, str(n))


def test_pre_existing_zw():
    print("\n== 13. 文件里本来就有杂散零宽字符（emoji ZWJ） ==")
    p = os.path.join(ROOT, "text_guard.py")
    base = clean(p)
    check("前提成立：底稿里有真实 ZWJ",
          any(c in base for c in ("\u200b", "\u200c", "\u200d")))
    new, st, why = sm.embed(base, None, "#", fmt="native")
    check("含杂散零宽也能嵌", st == "ok", why)
    check("签名可读回", payload_of(new) == sm.SIG_TEXT)
    check("原 emoji 仍是原样",
          "\U0001f468\u200d\U0001f469\u200d\U0001f467" in new)


# ============================================================
#  范围
# ============================================================
def test_tree_ops():
    print("\n== 14. 目录级操作 ==")
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "sub"))
    files = {"a.py": "# 这是 a.py 里足够长的注释行\nx=1\n",
             "sub/b.py": "# 这是 b.py 里足够长的注释行\ny=2\n",
             "c.txt": "不该被处理"}
    for n, t in files.items():
        io.open(os.path.join(d, n), "w", encoding="utf-8").write(t)
    lst = sm.iter_files([d])
    check("只挑出 .py", len(lst) == 2 and all(x.endswith(".py") for x in lst), str(lst))
    check("cmd_mark 返回 0", sm.cmd_mark([d], None, False) == 0)
    got = 0
    for n in files:
        if n.endswith(".py"):
            if payload_of(read(os.path.join(d, n))) == sm.SIG_TEXT:
                got += 1
    check("两个 py 都嵌上了", got == 2, str(got))
    check("txt 没被动", read(os.path.join(d, "c.txt")) == "不该被处理")

    before = {}
    for p in sm.iter_files([ROOT])[:60]:
        try:
            before[p] = os.path.getmtime(p)
        except Exception:
            pass
    sm.cmd_mark([ROOT], None, True)
    changed = [p for p, m in before.items()
               if os.path.isfile(p) and os.path.getmtime(p) != m]
    check("dry-run 没有改任何文件", not changed, str(changed[:3]))


def test_third_party_excluded():
    print("\n== 15. 绝不往第三方 / 别的项目里嵌署名 ==")
    d = tempfile.mkdtemp()
    for sub in ("vendor", "node_modules/x", "third_party",
                "dsh-companion/packages/x", "dsh-vision-router/src"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    mine = os.path.join(d, "mine.py")
    io.open(mine, "w", encoding="utf-8").write("# 我自己的注释足够长可以放签名\nx=1\n")
    others = [("vendor", "pixi.min.js"), ("node_modules/x", "a.js"),
              ("third_party", "lib.js"),
              ("dsh-companion/packages/x", "client.js"),
              ("dsh-vision-router/src", "router.js")]
    for sub, name in others:
        io.open(os.path.join(d, sub, name), "w", encoding="utf-8").write(
            "// 别人的代码 这是一段足够长的注释\nvar a=1;\n")
    io.open(os.path.join(d, "bundle.min.js"), "w", encoding="utf-8").write(
        "// 打包产物 足够长的注释内容在这里\nvar b=2;\n")

    lst = sm.iter_files([d])
    names = [os.path.basename(p) for p in lst]
    check("只挑中自己的文件", names == ["mine.py"], str(names))
    sm.cmd_mark([d], None, False)
    for sub, name in others:
        check("第三方/别项目 %s 未被嵌" % name,
              payload_of(read(os.path.join(d, sub, name))) is None)
    check("打包产物 bundle.min.js 未被嵌",
          payload_of(read(os.path.join(d, "bundle.min.js"))) is None)
    check("自己的文件嵌上了", payload_of(read(mine)) == sm.SIG_TEXT)

    real = sm.iter_files([ROOT])
    bad = [p for p in real if "vendor" in p.replace("\\", "/").lower()
           or p.lower().endswith(".min.js")]
    check("真实项目里没有第三方被扫进来", not bad, str(bad[:4]))
    foreign = [p for p in real
               if any(seg in p.replace("\\", "/").split("/")
                      for seg in ("dsh-companion", "dsh-vision-router",
                                  "dsh-whale-pet", "dskin", "utau_env"))]
    check("没有扫到非 DICK 项目的文件", not foreign, str(foreign[:4]))


def test_repo_is_marked():
    print("\n== 16. 仓库当前状态：应已统一为原生签名 ==")
    files = sm.iter_files([ROOT])
    missing, wrong = [], []
    for p in files:
        got = payload_of(read(p))
        if got is None:
            missing.append(os.path.relpath(p, ROOT))
        elif got != sm.SIG_TEXT:
            wrong.append((os.path.relpath(p, ROOT), got))
    check("全部文件都带签名", not missing, str(missing[:5]))
    check("签名内容统一为 SIG_TEXT", not wrong, str(wrong[:5]))
    print("        共 %d 个文件" % len(files))


if __name__ == "__main__":
    print("=" * 58)
    print("零宽署名水印测试")
    print("=" * 58)
    test_framed_codec()
    test_native_codec()
    test_python_ast_unchanged()
    test_real_files_compile()
    test_other_languages()
    test_idempotent()
    test_anchor_safety()
    test_anchor_protects_existing_mark()
    test_payload_not_overwritten()
    test_survives_whitespace_trim()
    test_no_comment_fallback()
    test_strip_exact()
    test_pre_existing_zw()
    test_tree_ops()
    test_third_party_excluded()
    test_repo_is_marked()
    print("\n" + "=" * 58)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
