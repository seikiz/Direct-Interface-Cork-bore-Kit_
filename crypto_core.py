# -*- coding: utf-8 -*-
"""
crypto_core.py —— 加密核心（场景无关）

流水线（顺序是有讲究的，每一环都为下一环服务）：
    明文
     → ① 变长压缩（3~9 位 Huffman）   省 30%+；把明文统计规律打散
     → ② 随机填充（长度量化到 64B 桶） 隐藏真实长度，防元数据分析
     → ③ AES-256-GCM 加密            唯一的安全层；头作为 AAD 参与认证
     → ④ 自描述容器（算法ID + 版本号） 这就是"备案算法"的挂载点
     → ⑤ 交给载体（PNG / 文件 / 存档）

设计要点（每一条都对应一种攻击）：
  · 头作为 AAD 认证     → 挡「篡改 algo_id 降级」和「改迭代数削弱 KDF」
  · nonce 每次随机 12B  → 挡「GCM nonce 复用」（复用 = 全盘泄露，最经典事故）
  · 每文件独立随机盐    → 挡「彩虹表 / 预计算」
  · 长度量化 + 随机块   → 挡「靠文件大小推断你写了多少字」
  · 先压缩后加密        → 密文更短；且明文冗余先被打散
  · 口令忘了就没了      → 所以提供恢复码（见 make_recovery_code）

不是自己发明的密码学：
  PBKDF2   → Python 标准库 hashlib
  AES-GCM  → cryptography 库（安卓端用系统自带 javax.crypto）
  Huffman  → 教科书算法，只用来压缩，不承担任何安全职责
"""

import base64
import hashlib
import hmac
import os
import struct
import heapq

# ---------------- 容器<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌常量 ----------------
MAGIC = b"DICK"
VERSION = 1

ALGO_AES256_GCM = 1
KDF_PBKDF2_SHA256 = 1

ALGO_NAMES = {
    ALGO_AES256_GCM: "AES-256-GCM",
    # 留给未来的算法（这就是"备案"）：
    # 2: "ChaCha20-Poly1305"
    # 3: "后量子算法"
}

DEFAULT_ITERS = 600_000          # OWASP 2023 对 PBKDF2-SHA256 的建议量级
SALT_LEN = 16
NONCE_LEN = 12
TAG_LEN = 16
HEADER_LEN = 4 + 1 + 1 + 1 + 4 + SALT_LEN + NONCE_LEN   # = 39
PAD_BUCKET = 64                  # 长度量化粒度
PAD_EXTRA_BLOCKS = 3             # 再多加 0~3 个随机块，进一步模糊长度

MIN_PASSWORD_LEN = 12


# ============================================================
#  ① 变长压缩：3~9 位 Huffman（纯压缩，不承担安全职责）
# ============================================================
def _build_weights():
    """给 256 个字节一个"典型文本里出现频率"的权重。
    中文 UTF-8 的字节分布很有特点：连续字节 0x80-0xBF 极多，
    控制字符几乎没有 —— 变长编码就是靠这个差来省位数的。"""
    w = [1] * 256
    # 常见 ASCII
    for b in b" \n\r\t.,!?;:'\"()-_/0123456789":
        w[b] = 400
    for b in range(ord("a"), ord("z") + 1):
        w[b] = 700
    for b in range(ord("A"), ord("Z") + 1):
        w[b] = 200
    # 中文 UTF-8：3 字节序列，首字节 E4-E9，后两字节 80-BF
    for b in range(0xE4, 0xEA):
        w[b] = 900
    for b in range(0x80, 0xC0):
        w[b] = 1200        # 中文的连续字节，出现最频繁
    w[0xE3] = 600          # 全角标点常用
    # 少见/几乎不出现的
    for b in range(0x00, 0x20):
        w[b] = 1
    for b in (0x0A, 0x0D):
        w[b] = 300
    w[0x7F] = 1
    for b in range(0xF5, 0x100):
        w[b] = 1
    return w


def _build_huffman(weights):
    """构造 Huffman 码表。返回 [code_str_or_None] * 256 与 [length] * 256"""
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
    lengths = [len(codes[i]) for i in range(256)]
    return codes, lengths


_CODES, _LENGTHS = _build_huffman(_build_weights())
_DECODE_TREE = None


def _build_decode_tree():
    global _DECODE_TREE
    root = {}
    for b in range(256):
        node = root
        for ch in _CODES[b]:
            node = node.setdefault(ch, {})
        node["#"] = b
    _DECODE_TREE = root


_build_decode_tree()

CODE_MIN = min(_LENGTHS)
CODE_MAX = max(_LENGTHS)
CODE_AVG_TEXT = sum(_LENGTHS[b] * _build_weights()[b] for b in range(256)) / \
    sum(_build_weights())


def compress(data: bytes) -> bytes:
    """变长压缩：用 6~16 位的码把每个字节换掉，末尾补 1 个长度字节"""
    bits = []
    for b in data:
        bits.append(_CODES[b])
    s = "".join(bits)
    pad = (-len(s)) % 8
    s += "0" * pad
    out = bytearray()
    for i in range(0, len(s), 8):
        out.append(int(s[i:i + 8], 2))
    out.append(pad)          # 记录补了几位，解压时去掉
    return bytes(out)


def decompress(blob: bytes) -> bytes:
    """解压。数据坏了返回 b""（由 GCM 负责判定真伪，这里只是别炸）"""
    if not blob:
        return b""
    pad = blob[-1]
    s = "".join(f"{b:08b}" for b in blob[:-1])
    if pad:
        s = s[: len(s) - pad]
    node = _DECODE_TREE
    out = bytearray()
    for ch in s:
        node = node.get(ch)
        if node is None:
            return b""
        if "#" in node:
            out.append(node["#"])
            node = _DECODE_TREE
    return bytes(out)


# ============================================================
#  ② 填充：把长度量化到桶，隐藏真实长度
# ============================================================
def _pad(data: bytes, stored: bool = False) -> bytes:
    need = 4 + len(data)                       # 4 字节存真实长度
    blocks = (need + PAD_BUCKET - 1) // PAD_BUCKET
    blocks += int.from_bytes(os.urandom(1), "big") % (PAD_EXTRA_BLOCKS + 1)
    # 长度前缀的最高位当「未压缩」标志位。
    # 用最高位而不是新增头字段，是为了让旧容器仍能解开：
    # 旧容器最高位恒为 0 且内容确实压过，语义正好吻合。
    # 备份包不可能到 2GB，最高位不会和真实长度冲突。
    flag = 0x80000000 if stored else 0
    inner = struct.pack(">I", len(data) | flag) + data
    inner += os.urandom(blocks * PAD_BUCKET - len(inner))
    # 再补 0~15 字节随机尾。
    # 不补的话总长恒为 64k，密文长度就永远落在 16 字节整数倍上 ——
    # 「长度是 16 的倍数」正是最典型的 AES 指纹，而且 64 字节向上取整
    # 会把变长压缩省下的位数大部分吃掉。GCM 是流密码，不要求块整数倍。
    # _unpad 只读前 4 字节的长度前缀，尾部多补多少都无所谓 → 向下兼容旧备份。
    inner += os.urandom(int.from_bytes(os.urandom(1), "big") % 16)
    return inner


def _unpad(inner: bytes):
    """返回 (数据, 是否未压缩)。"""
    if len(inner) < 4:
        raise ValueError("bad inner")
    raw = struct.unpack(">I", inner[:4])[0]
    stored = bool(raw & 0x80000000)
    n = raw & 0x7FFFFFFF
    if 4 + n > len(inner):
        raise ValueError("bad length")
    return inner[4:4 + n], stored


# ============================================================
#  ③④ 容器：加密 + 自描述头（头参与认证）
# ============================================================
def derive_key(password: str, salt: bytes, iters: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, dklen=32)


def _build_header(algo: int, kdf: int, iters: int, salt: bytes, nonce: bytes) -> bytes:
    return MAGIC + bytes([VERSION, algo, kdf]) + struct.pack(">I", iters) + salt + nonce


def encrypt(password: str, plaintext: bytes, iters: int = DEFAULT_ITERS) -> bytes:
    """明文 → 容器字节"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    # ① 自适应：压缩表是针对 UTF-8 文本调的，
    #    如果输入已经是 deflate 过的 zip（高熵），硬压会膨胀 30% 以上。
    #    压不小就直接原样存，把选择记进长度前缀最高位。
    compressed = compress(plaintext)
    if len(compressed) < len(plaintext):
        payload, stored = compressed, False
    else:
        payload, stored = plaintext, True
    inner = _pad(payload, stored)              # ② 再填充
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(password, salt, iters)
    header = _build_header(ALGO_AES256_GCM, KDF_PBKDF2_SHA256, iters, salt, nonce)
    # 头作为 AAD：改一个 bit 就会认证失败 → 挡降级/篡改
    ct = AESGCM(key).encrypt(nonce, inner, header)
    return header + ct


def decrypt(password: str, container: bytes) -> bytes:
    """容器字节 → 明文。任何篡改都会抛异常"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag

    if len(container) < HEADER_LEN + TAG_LEN:
        raise ValueError("容器太短")
    if container[:4] != MAGIC:
        raise ValueError("不是本格式的容器")
    version, algo, kdf = container[4], container[5], container[6]
    if version != VERSION:
        raise ValueError("不支持的版本：%d" % version)
    if algo not in ALGO_NAMES:
        raise ValueError("不支持的算法 ID：%d" % algo)
    if kdf != KDF_PBKDF2_SHA256:
        raise ValueError("不支持的 KDF ID：%d" % kdf)
    iters = struct.unpack(">I", container[7:11])[0]
    salt = container[11:11 + SALT_LEN]
    nonce = container[11 + SALT_LEN:HEADER_LEN]
    header = container[:HEADER_LEN]
    ct = container[HEADER_LEN:]

    key = derive_key(password, salt, iters)
    try:
        inner = AESGCM(key).decrypt(nonce, ct, header)
    except InvalidTag:
        raise ValueError("口令错误，或数据被篡改")
    payload, stored = _unpad(inner)
    return payload if stored else decompress(payload)


# ============================================================
#  文本便捷接口 + 口令策略 + 恢复码
# ============================================================
def encrypt_text(password: str, text: str, iters: int = DEFAULT_ITERS) -> str:
    return base64.b64encode(encrypt(password, text.encode("utf-8"), iters)).decode("ascii")


def decrypt_text(password: str, blob: str) -> str:
    return decrypt(password, base64.b64decode(blob)).decode("utf-8")


def password_strength(pw: str):
    """返回 (等级, 说明)。等级 0=太弱 1=弱 2=可以 3=强"""
    if not pw:
        return 0, "空口令"
    n = len(pw)
    kinds = sum([
        any(c.islower() for c in pw),
        any(c.isupper() for c in pw),
        any(c.isdigit() for c in pw),
        any(not c.isalnum() for c in pw),
    ])
    if n < 8:
        return 0, "太短（至少 12 位）"
    if n < MIN_PASSWORD_LEN:
        return 1, "偏短（建议至少 12 位）"
    if kinds <= 1:
        return 1, "太单一（只用了一类字符）"
    if n >= 16 and kinds >= 3:
        return 3, "强"
    if n >= 12 and kinds >= 2:
        return 2, "可以"
    return 1, "偏弱"


def make_recovery_code() -> str:
    """恢复码：32 字节随机 → base32，比口令强得多。
    用途：用户忘口令时，靠它救回数据（这是唯一不靠"记住"的出路）"""
    raw = os.urandom(32)
    b32 = base64.b32encode(raw).decode("ascii").rstrip("=")
    return "-".join(b32[i:i + 4] for i in range(0, len(b32), 4))


def info(container: bytes) -> dict:
    """读出容器头（公开信息，不含秘密）——用于排查和将来迁移算法"""
    if len(container) < HEADER_LEN or container[:4] != MAGIC:
        return {}
    iters = struct.unpack(">I", container[7:11])[0]
    return {
        "version": container[4],
        "algo_id": container[5],
        "algo": ALGO_NAMES.get(container[5], "未知(%d)" % container[5]),
        "kdf_id": container[6],
        "iters": iters,
        "size": len(container),
        "header_len": HEADER_LEN,
    }
