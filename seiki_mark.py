# -*- coding: utf-8 -*-
"""
seiki_mark.py —— 往源码里嵌零宽署名水印

用途：
    别人抄走项目时，代码里仍带着作者署名，但肉眼看代码看不出来。
    它【不是】安全措施，也不是防抄袭手段 —— 见文末「这个水印能做什么」。

设计上必须避开的四个坑（都是真实会踩的）：
  ① 不能破坏语法。零宽字符插在【注释内部】，绝不碰字符串、标识符、代码。
  ② 不能让编辑器/格式化工具顺手删掉。很多编辑器和 lint 会自动清理行尾空白，
     所以签名【不放在行尾】，而是夹在注释正文中间。
  ③ 不能碰文件头。Python 的 `# -*- coding: utf-8 -*-` 必须保持原样，
     否则 PEP 263 的正则匹配不上（Py3 虽然默认 UTF-8，但没必要冒这个险）。
  ④ 必须幂等。跑两次不能嵌两份。

用法：
    python seiki_mark.py mark   [路径...]        # 嵌签名（默认当前目录下的项目源码）
    python seiki_mark.py read   [路径...]        # 检查/读出签名
    python seiki_mark.py strip  [路径...]        # 移除签名
    python seiki_mark.py mark --text "SEIKI" --dry-run
"""

import os
import sys

# ---- 零宽<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌字符表 ----
ZW0 = "\u200b"      # 零宽空格  → 数据位 0
ZW1 = "\u200c"      # 零宽非连接符 → 数据位 1
ZW_FRAME = "\u200d"  # 零宽连接符  → 帧定界
ZW_ALL = (ZW0, ZW1, ZW_FRAME)

# ============================================================
#  项目已有的署名规范（沿用，别另发明一套）
# ============================================================
# 形态:  # <seiki><零宽串>
# 编码:  4 种零宽字符各代表 2 bit（每字节 4 个符号）
# 内容:  DICK_CODEX_SIG_7f3a9c2e
# 这套是仓库里原本就在用的（DICK_core.py / 主程序里已存在），
# 所以设成默认 —— 一个仓库里不该并存两种互不认识的签名。
SIG_PREFIX = "<seiki>"
SIG_TEXT = "DICK_CODEX_SIG_7f3a9c2e"
SIG_SYMBOLS = ("\u200b", "\u200c", "\u200d", "\u200e")


def encode_sig(text=SIG_TEXT):
    """文本 → <seiki>+零宽串（原生规范）"""
    bits = "".join(format(b, "08b") for b in text.encode("utf-8"))
    return SIG_PREFIX + "".join(
        SIG_SYMBOLS[int(bits[i:i + 2], 2)] for i in range(0, len(bits), 2))


def decode_sig(zw):
    """零宽串 → 文本。格式不对返回 None"""
    if not zw or any(c not in SIG_SYMBOLS for c in zw):
        return None
    bits = "".join(format(SIG_SYMBOLS.index(c), "02b") for c in zw)
    if len(bits) % 8:
        return None
    try:
        data = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
        return data.decode("utf-8")
    except Exception:
        return None


def find_sig(text):
    """找原生签名。返回 (payload, 起, 止)，起点含可见的 <seiki>"""
    i = text.find(SIG_PREFIX)
    while i != -1:
        j = i + len(SIG_PREFIX)
        k = j
        while k < len(text) and text[k] in SIG_SYMBOLS:
            k += 1
        if k > j:
            got = decode_sig(text[j:k])
            if got is not None:
                return got, i, k
        i = text.find(SIG_PREFIX, i + 1)
    return None


def detect(text):
    """找出文本里所有签名（两种规范都认）。返回 [(规范, 内容, 起, 止)]"""
    out = []
    hit = find_sig(text)
    if hit:
        out.append(("native", hit[0], hit[1], hit[2]))
    f = find(text)
    if f:
        out.append(("framed", f[0], f[1], f[2]))
    return sorted(out, key=lambda x: x[2])


def detect_one(text):
    """返回第一个签名 (规范, 内容, 起, 止)，没有则 None"""
    allof = detect(text)
    return allof[0] if allof else None


DEFAULT_TEXT = "SEIKI"

# 只处理项目自己的源码，不碰第三方/构建产物。
# 末尾三个是【别的项目】：.gitignore 里明确标了「不属于 DICK 项目」。
# 工作目录下同时躺着多个项目时，不排除它们就会把署名盖到别人的代码上 ——
# 实测漏排除 dsh-companion 时，会多出 40 多个 .js 被误标。
SKIP_DIRS = {
    ".git", ".gradle", ".kotlin", ".idea", ".vscode", "build", "dist",
    "utau_env", "node_modules", "__pycache__", "_ui_evidence", "_install_test",
    "server_build", "tavern-installer", "workshop_data", "_apk_inspect",
    "DICK-HTML", "播放器", ".dsh-vision-router", "dskin", "_wf", "_mock",
    "_kt_test_data", "DICK-发布",
    # 第三方：往别人的代码里嵌自己的署名不是「署名」，是冒名
    "vendor", "third_party", "thirdparty", "libs",
    # 非 DICK 项目（见 .gitignore「DSH 环境目录」一节）
    "dsh-companion", "dsh-vision-router", "dsh-whale-pet",
}

# 第三方常见命名，一并跳过（哪怕不在 vendor 目录里）
SKIP_FILE_PATTERNS = (".min.js", ".min.css", ".bundle.js", ".chunk.js")

# 扩展名 → 可用的注释风格列表。
# 行注释写成字符串；块注释写成 (开, 闭)。
# 一种语言常常有多种：Kotlin 既有 `//` 也有 `/** KDoc */`，
# 只认 `//` 的话，满篇 KDoc 的文件就会被判成「没有注释」。
COMMENT = {
    ".py": ["#"],
    ".ps1": ["#"],
    ".bat": ["REM"],
    ".js": ["//", ("/*", "*/")],
    ".kt": ["//", ("/*", "*/")],
    ".kts": ["//", ("/*", "*/")],
    ".html": [("<!--", "-->")],
    ".htm": [("<!--", "-->")],
}

# 行注释正文至少要有这么多字（只要后面还有字符就不算行尾，所以门槛很低）
MIN_BODY = 1
# 块注释要更保守：太短会插到 `/**` 这种开标记中间，把 KDoc 拆得很难看
MIN_BODY_BLOCK = 4

# 这些行绝对不能碰
FORBIDDEN = ("#!", "coding:", "coding=", "vim:", "noqa")


# ============================================================
#  编解码
# ============================================================
def _bits_to_zw(bits):
    return "".join(ZW1 if b == "1" else ZW0 for b in bits)


def encode(text=DEFAULT_TEXT):
    """文本 → 零宽串。格式：帧 + 8N 数据位 + 8 位校验 + 帧"""
    raw = text.encode("utf-8")
    chk = 0
    for b in raw:
        chk ^= b
    bits = "".join(format(b, "08b") for b in raw)
    bits += format(chk, "08b")
    return ZW_FRAME + _bits_to_zw(bits) + ZW_FRAME


def decode(zw):
    """零宽串 → 文本。格式不对返回 None（绝不抛异常）"""
    if not zw or len(zw) < 2 or zw[0] != ZW_FRAME or zw[-1] != ZW_FRAME:
        return None
    body = zw[1:-1]
    if not body or any(c not in (ZW0, ZW1) for c in body):
        return None
    if len(body) % 8 != 0:
        return None
    bits = "".join("1" if c == ZW1 else "0" for c in body)
    data = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    if len(data) < 2:
        return None
    payload, chk = data[:-1], data[-1]
    c = 0
    for b in payload:
        c ^= b
    if c != chk:
        return None                      # 校验失败 = 被改过
    try:
        return payload.decode("utf-8")
    except Exception:
        return None


def find(text):
    """在文本里找水印。返回 (payload, 起, 止) 或 None"""
    start = text.find(ZW_FRAME)
    while start != -1:
        end = text.find(ZW_FRAME, start + 1)
        if end == -1:
            return None
        cand = text[start:end + 1]
        got = decode(cand)
        if got is not None:
            return got, start, end + 1
        start = text.find(ZW_FRAME, start + 1)
    return None


def strip(text, styles="#"):
    """移除水印。返回 (新文本, 移除了几个零宽字符)

    兜底追加的那一行在移除水印后会剩下一个空的注释标记（`# `），
    那不是原文的一部分，所以要连整行一起删掉 —— 否则 strip 之后
    文件里会永远多出一行，做不到逐字节还原。
    """
    hit = detect_one(text)
    if not hit:
        return text, 0
    _fmt, _payload, s, e = hit
    new = text[:s] + text[e:]
    n = e - s

    # 定位被移除的水印所在行，看它现在是不是「空注释」
    line_start = new.rfind("\n", 0, s) + 1
    line_end = new.find("\n", line_start)
    if line_end == -1:
        line_end = len(new)
    line = new[line_start:line_end]
    opens = {_markers(st)[0] for st in _as_styles(styles)}
    core = line.strip()
    if core in opens:
        # 整行只剩注释标记 → 这是我们追加出来的，删掉整行（含换行）
        cut_end = line_end + 1 if line_end < len(new) else line_end
        new = new[:line_start] + new[cut_end:]
    return new, n


# ============================================================
#  插入位置
# ============================================================
def _markers(style):
    """归一成 (开, 闭)。行注释的「闭」是 None（到行尾）"""
    if isinstance(style, tuple):
        return style[0], style[1]
    return style, None


def _pick_anchor(text, style):
    """挑一处注释，返回可在其中插入的偏移量。

    规则：
      · 跳过文件头（编码声明/shebang 不能被污染）；
      · 插在注释正文【中间】—— 前后都有字符，既不是行首也不是行尾空白，
        常规的空白清理工具动不到它；
      · 块注释要求闭标记在同一行，否则会插进 `/**` 这种开标记里面；
      · 找不到合适注释时返回 (None, None)，由调用方走兜底。
    """
    open_m, close_m = _markers(style)
    is_block = close_m is not None
    need = MIN_BODY_BLOCK if is_block else MIN_BODY
    lines = text.split("\n")
    off = 0
    for idx, line in enumerate(lines):
        raw = line.strip()
        if not raw.startswith(open_m):
            off += len(line) + 1
            continue
        if is_block:
            if close_m not in raw:
                off += len(line) + 1      # 多行块注释的开头行：不碰
                continue
            body_full = raw[len(open_m): raw.rfind(close_m)]
        else:
            body_full = raw[len(open_m):]
        body = body_full.strip()
        low = line.lower()
        if any(f.lower() in low for f in FORBIDDEN):
            off += len(line) + 1
            continue
        # 这一行已经有零宽字符（多半是别的署名水印）→ 绝不能往里插。
        # 插进去会把两串零宽字符连成一条，原有水印就解不出来了。
        if any(c in ZW_ALL or c in SIG_SYMBOLS for c in line):
            off += len(line) + 1
            continue
        if len(body) < need:
            off += len(line) + 1
            continue
        lead = len(line) - len(line.lstrip())
        pos = line.find(body[:1], lead + len(open_m))
        if pos < 0:
            off += len(line) + 1
            continue
        # 插在注释正文中间
        ins = pos + len(body) // 2
        if ins <= pos:
            ins = pos + 1 if len(body) > 1 else pos
        while ins < len(line) and line[ins] == " ":
            ins += 1
        if is_block:
            limit = line.rfind(close_m)
            if limit >= 0 and ins >= limit:
                ins = pos
            if ins >= limit:
                off += len(line) + 1
                continue
        if ins >= len(line):
            off += len(line) + 1
            continue
        return off + ins, idx + 1
    return None, None


def _append_line(text, style):
    """兜底：文件里没有可用的注释行（例如只有编码声明）。

    追加一行只含水印的注释。行尾清理用 rstrip() 是按「空白」定义的，
    而零宽字符的 Unicode 类别是 Cf 不是空白（'\u200b'.isspace() is False），
    所以常规的 rstrip 删不掉它 —— 但确实比插在正文中间稍微脆弱一点，
    因此仅在别无选择时才用。
    """
    open_m = _markers(style)[0]
    if not text.endswith("\n"):
        text += "\n"
    return text + open_m + " ", "追加新注释行"


def _as_styles(styles):
    """允许传单个风格或风格列表"""
    if styles is None:
        return []
    if isinstance(styles, (str, tuple)):
        return [styles]
    return list(styles)


def embed(text, payload=None, styles="#", fmt="native"):
    """返回 (新文本, 状态, 说明)。styles 可以是单个风格或风格列表。"""
    if detect_one(text):
        return text, "skip", "已有签名"
    styles = _as_styles(styles)
    if not styles:
        return text, "skip", "不支持的语言"
    if payload is None:
        payload = SIG_TEXT if fmt == "native" else DEFAULT_TEXT
    maker = encode_sig if fmt == "native" else encode
    for style in styles:
        pos, lineno = _pick_anchor(text, style)
        if pos is not None:
            zw = maker(payload)
            return text[:pos] + zw + text[pos:], "ok", "第 %d 行注释内" % lineno
    # 兜底：追加一行注释。
    # 注意这里【不】因为文件里已有杂散零宽字符就放弃 ——
    # text_guard.py 的文档里那个 emoji（👨👩👧）就带真实 ZWJ。
    # find() 要求完整的帧 + 校验位，杂散零宽字符不会误判。
    new, why = _append_line(text, styles[0])
    return new + maker(payload), "ok", why


# ============================================================
#  文件遍历
# ============================================================
def iter_files(paths):
    out = []
    for p in paths:
        if os.path.isfile(p):
            out.append(p)
            continue
        for dp, dns, fns in os.walk(p):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                if os.path.splitext(fn)[1].lower() not in COMMENT:
                    continue
                low = fn.lower()
                if any(low.endswith(pat) for pat in SKIP_FILE_PATTERNS):
                    continue
                out.append(os.path.join(dp, fn))
    return sorted(out)


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def cmd_mark(paths, payload, dry):
    files = iter_files(paths)
    ok = skip = 0
    for p in files:
        try:
            text = _read(p)
        except Exception as e:
            print("   跳过 %s（读不了：%s）" % (p, e)); skip += 1; continue
        styles = COMMENT.get(os.path.splitext(p)[1].lower())
        new, st, why = embed(text, payload, styles)
        if st == "ok":
            if not dry:
                _write(p, new)
            print("   %s %s  (%s)" % ("[试运行]" if dry else "[已嵌]", p, why)); ok += 1
        else:
            skip += 1
    print("\n嵌入 %d 个，跳过 %d 个（共扫描 %d 个文件）" % (ok, skip, len(files)))
    return 0


def cmd_read(paths, quiet=False):
    files = iter_files(paths)
    found = 0
    for p in files:
        try:
            text = _read(p)
        except Exception:
            continue
        hit = detect_one(text)
        if hit:
            found += 1
            if not quiet:
                print("   ✅ %-52s [%s] %s" % (p, hit[0], hit[1]))
    print("\n%d / %d 个文件带签名" % (found, len(files)))
    return 0 if found else 1


def cmd_strip(paths, dry):
    files = iter_files(paths)
    n = 0
    for p in files:
        try:
            text = _read(p)
        except Exception:
            continue
        styles = COMMENT.get(os.path.splitext(p)[1].lower(), ["#"])
        new, removed = strip(text, styles)
        if removed:
            if not dry:
                _write(p, new)
            print("   %s %s（移除 %d 个零宽字符）" % ("[试运行]" if dry else "[已清]", p, removed))
            n += 1
    print("\n清理 %d 个文件" % n)
    return 0


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass

    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    dry = "--dry-run" in argv
    # 默认 None：由 embed 按所选规范决定用什么内容。
    # 之前默认 "SEIKI"，结果把原生规范的 DICK_CODEX_SIG_* 覆盖掉了。
    payload = None
    if "--text" in argv:
        i = argv.index("--text")
        if i + 1 < len(argv):
            payload = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    paths = [a for a in argv[1:] if not a.startswith("--")] or ["."]

    if cmd == "mark":
        print("== 嵌入签名：%r ==" % (payload or SIG_TEXT))
        return cmd_mark(paths, payload, dry)
    if cmd == "read":
        print("== 检查签名 ==")
        return cmd_read(paths)
    if cmd == "strip":
        print("== 移除签名 ==")
        return cmd_strip(paths, dry)
    print("未知命令：", cmd)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
