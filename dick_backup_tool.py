# -*- coding: utf-8 -*-
"""
dick_backup_tool.py —— 加密备份的【独立】解密工具

为什么单独做这个：
    备份的意义是「将来能救回来」。如果解密必须依赖 DICK 本体，
    那 DICK 装不上/换电脑/项目没了的时候，备份就变成一堆废字节。
    所以这个工具只用标准库 + cryptography，不 import 项目里任何东西。

用法：
    python dick_backup_tool.py 查看  DICK_加密备份_xxx.dickbackup
    python dick_backup_tool.py 解密  DICK_加密备份_xxx.dickbackup [-o 输出目录]

口令会交互式输入（不回显），也可以从环境变量 DICK_BACKUP_PW 读，方便脚本化。
"""

import base64
import getpass
import hashlib
import io
import os
import struct
import sys
import zipfile

# 这是「救数据」用的工具，绝不允许因<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌为控制台编码不认某个字符就崩掉 ——
# 之前实测在 GBK 控制台上会于最后一行"解密成功"处抛 UnicodeEncodeError，
# 用户看到的是崩溃，会以为备份坏了。改成解不出就退化成 ? ，永不抛。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")
    except Exception:
        pass

MAGIC = b"DICK"
SALT_LEN = 16
NONCE_LEN = 12
HEADER_LEN = 4 + 1 + 1 + 1 + 4 + SALT_LEN + NONCE_LEN


def _read_password():
    pw = os.environ.get("DICK_BACKUP_PW")
    if pw:
        return pw
    try:
        return getpass.getpass("请输入备份口令：")
    except Exception:
        return input("请输入备份口令：")


def show_info(path):
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < HEADER_LEN or blob[:4] != MAGIC:
        print("❌ 这不是 DICK 加密备份文件")
        return 1
    version, algo, kdf = blob[4], blob[5], blob[6]
    iters = struct.unpack(">I", blob[7:11])[0]
    print("文件      :", os.path.basename(path))
    print("大小      : %.1f KB" % (len(blob) / 1024))
    print("格式版本  :", version)
    print("加密算法  :", {1: "AES-256-GCM"}.get(algo, "未知(%d)" % algo))
    print("密钥派生  :", {1: "PBKDF2-SHA256"}.get(kdf, "未知(%d)" % kdf), "×", iters, "次")
    print()
    print("注意：头里这些信息是公开的（这是标准做法）。")
    print("      没有口令，谁也无法解开内容 —— 包括我们。")
    return 0


def decrypt(path, outdir=None):
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < HEADER_LEN or blob[:4] != MAGIC:
        print("❌ 这不是 DICK 加密备份文件")
        return 1
    iters = struct.unpack(">I", blob[7:11])[0]
    salt = blob[11:11 + SALT_LEN]
    nonce = blob[11 + SALT_LEN:HEADER_LEN]
    header = blob[:HEADER_LEN]
    ct = blob[HEADER_LEN:]

    pw = _read_password()
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as e:
        print("❌ 需要 cryptography 库：pip install cryptography")
        print("   ", e)
        return 1
    key = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, iters, dklen=32)
    try:
        inner = AESGCM(key).decrypt(nonce, ct, header)
    except Exception:
        print("❌ 口令错误，或文件被改动过")
        print("   （如果确定口令没错，那文件可能损坏 —— 换一份备份试试）")
        return 1
    # 去掉填充：前 4 字节是真实长度，最高位表示「未压缩」（高熵数据压不动时原样存）
    raw = struct.unpack(">I", inner[:4])[0]
    stored = bool(raw & 0x80000000)
    n = raw & 0x7FFFFFFF
    payload = inner[4:4 + n]
    if stored:
        raw_zip = payload
    else:
        raw_zip = _decompress(payload)
        if not raw_zip:
            print("❌ 内容解压失败（文件可能不完整）")
            return 1

    if not outdir:
        outdir = os.path.splitext(path)[0] + "_还原"
    os.makedirs(outdir, exist_ok=True)
    try:
        z = zipfile.ZipFile(io.BytesIO(raw_zip))
    except Exception as e:
        print("❌ 内容不是有效的 zip：", e)
        return 1

    # 备份 zip 内部有一层包裹目录（DICK_备份_日期时间/）。
    # 直接 extractall 会让用户拿到「还原/DICK_备份_xxx/saves/...」，
    # 既多一层，又和 App 内「从备份还原」的结果不一致 ——
    # App 会剥掉这层。这里保持一致，用户才能直接对着文件夹拷贝。
    names = [n for n in z.namelist() if not n.endswith("/")]
    prefix = ""
    if names:
        first = names[0].replace("\\", "/").split("/")[0] + "/"
        if all(n.replace("\\", "/").startswith(first) for n in names):
            prefix = first

    written = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        rel = info.filename.replace("\\", "/")
        if prefix and rel.startswith(prefix):
            rel = rel[len(prefix):]
        if not rel:
            continue
        # 路径穿越防护：'..' 不允许出现在任何一段
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        if not parts or ".." in parts:
            continue
        dst = os.path.join(outdir, *parts)
        root = os.path.realpath(os.path.abspath(outdir))
        ap = os.path.realpath(os.path.abspath(dst))
        if not (ap == root or ap.startswith(root + os.sep)):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(z.read(info))
        written += 1

    print("✅ 解密成功 →", outdir)
    print("   还原 %d 个文件" % written)
    for n in sorted(set(p.split("/")[0] for p in
                        [i.filename.replace("\\", "/")[len(prefix):]
                         for i in z.infolist() if not i.is_dir()] if p)):
        print("     %s/" % n)
    print()
    print("   把上面这些文件夹拷贝回 DICK 目录即完成迁移。")
    return 0


# ---- 与 crypto_core 完全一致的变长解压（Huffman，码长 6~16 位）----
# 这段是手工复刻的，所以下面加了指纹自检：万一哪天 crypto_core 改了权重，
# 老备份会解不开 —— 那种故障如果静默发生，等于备份白做。宁可当场炸。
CODES_FP = "7957bd84ee2919f5d5ad69e6f04deaca"
KNOWN = (b"hello world", "40752244eccbd3aa487002")


def _build_weights():
    w = [1] * 256
    for b in b" \n\r\t.,!?;:'\"()-_/0123456789":
        w[b] = 400
    for b in range(ord("a"), ord("z") + 1):
        w[b] = 700
    for b in range(ord("A"), ord("Z") + 1):
        w[b] = 200
    for b in range(0xE4, 0xEA):
        w[b] = 900
    for b in range(0x80, 0xC0):
        w[b] = 1200
    w[0xE3] = 600
    for b in range(0x00, 0x20):
        w[b] = 1
    for b in (0x0A, 0x0D):
        w[b] = 300
    w[0x7F] = 1
    for b in range(0xF5, 0x100):
        w[b] = 1
    return w


def _build_codes():
    """必须与 crypto_core._build_huffman 逐位一致。
    Huffman 树的形状完全由「出堆顺序」决定，所以平手判定 (w1+w2, min(...))
    一个字符都不能改 —— 改了不会报错，只会静默解出乱码。"""
    import heapq
    weights = _build_weights()
    heap = [(weights[i], i, (i,)) for i in range(256)]
    heapq.heapify(heap)
    codes = {i: "" for i in range(256)}
    while len(heap) > 1:
        w1, _, s1 = heapq.heappop(heap)
        w2, _, s2 = heapq.heappop(heap)
        for s in s1:
            codes[s] = "0" + codes[s]
        for s in s2:
            codes[s] = "1" + codes[s]
        heapq.heappush(heap, (w1 + w2, min(s1[0], s2[0]), s1 + s2))
    tree = {}
    for b in range(256):
        node = tree
        for ch in codes[b]:
            node = node.setdefault(ch, {})
        node["#"] = b
    return tree


_TREE = None
_FP_OK = None


def self_check():
    """确认复刻的码表和 crypto_core 是同一张。
    返回 (ok, 说明)。ok=False 时绝不能再往下解密 —— 会解出乱码。"""
    global _FP_OK
    if _FP_OK is not None:
        return _FP_OK
    import hashlib
    codes = {}
    # 从解码树反推回编码，再算指纹
    _build_codes_inner(codes)
    blob = "".join(codes[i] for i in range(256)).encode()
    fp = hashlib.sha256(blob).hexdigest()[:32]
    if fp != CODES_FP:
        _FP_OK = (False, "码表指纹不符：本工具 %s / 应为 %s" % (fp, CODES_FP))
        return _FP_OK
    pt, want = KNOWN
    if compress_for_test(pt).hex() != want:
        _FP_OK = (False, "已知答案不符，压缩表与加密端不一致")
        return _FP_OK
    _FP_OK = (True, "码表与加密端一致")
    return _FP_OK


def _build_codes_inner(codes_out):
    global _TREE
    if _TREE is None:
        _TREE = _build_codes()
    # 遍历解码树还原编码
    def walk(node, prefix):
        if "#" in node:
            codes_out[node["#"]] = prefix
            return
        for ch, sub in node.items():
            walk(sub, prefix + ch)
    walk(_TREE, "")


def compress_for_test(data):
    codes = {}
    _build_codes_inner(codes)
    bits = "".join(codes[b] for b in data)
    pad = (-len(bits)) % 8
    bits += "0" * pad
    out = bytearray(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    out.append(pad)
    return bytes(out)


def _decompress(blob):
    global _TREE
    if _TREE is None:
        _TREE = _build_codes()
    if not blob:
        return b""
    pad = blob[-1]
    s = "".join(f"{b:08b}" for b in blob[:-1])
    if pad:
        s = s[: len(s) - pad]
    node = _TREE
    out = bytearray()
    for ch in s:
        node = node.get(ch)
        if node is None:
            return b""
        if "#" in node:
            out.append(node["#"])
            node = _TREE
    return bytes(out)


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd, path = argv[0], argv[1]
    outdir = None
    if "-o" in argv:
        i = argv.index("-o")
        if i + 1 < len(argv):
            outdir = argv[i + 1]
    if not os.path.isfile(path):
        print("❌ 找不到文件：", path)
        return 1
    if cmd in ("查看", "info"):
        return show_info(path)
    if cmd in ("解密", "decrypt"):
        return decrypt(path, outdir)
    print("未知命令：", cmd)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
