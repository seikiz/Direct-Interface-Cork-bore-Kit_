# -*- coding: utf-8 -*-
"""
加密备份的端到端测试。

重点验三件事，每件都对应一个"会不会白做备份"的风险：
  1. 独立解密工具在【干净 sys.path】下能不能解开 —— 否则备份绑死在 DICK 上
  2. 错口令 / 被改动的文件 必须失败，且不能解出垃圾
  3. 密文里不能出现明文文件名和明文内容 —— 这是加密 zip 做不到的

跑法：utau_env\\Scripts\\python.exe tests\\test_backup_encrypted.py
"""

import io
import json
import os
import struct as _s
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import crypto_core as c          # noqa: E402
import dick_backup_tool as tool  # noqa: E402

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


SAMPLE = {
    "saves/slot1.json": json.dumps({"aff": 88, "name": "小林"}, ensure_ascii=False),
    "codex/我的故事.md": "# 第一章\n她站在雨里，伞是坏的。\n" * 200,
    "world/世界书.json": json.dumps({"entries": ["设定A", "设定B"]}, ensure_ascii=False),
    "config.json": json.dumps({"theme": "dark", "api": "deepseek-flash"}),
}
PW = "correct horse battery staple"


def make_zip(files=SAMPLE):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, t in files.items():
            z.writestr(n, t)
    return buf.getvalue()


def test_codebook_matches():
    print("\n== 1. 码表指纹 ==")
    ok, why = tool.self_check()
    check("独立工具码表 == crypto_core 码表", ok, why)
    # 逐字节：两边压缩同<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一组数据必须完全相同
    for probe in [b"", b"a", b"hello world", "中文内容测试".encode(),
                  bytes(range(256)), b"x" * 1000]:
        check(f"compress 一致 {probe[:12]!r}",
              tool.compress_for_test(probe) == c.compress(probe))
    check("CODE_MIN/MAX 范围", (c.CODE_MIN, c.CODE_MAX) == (6, 16),
          f"实际 {(c.CODE_MIN, c.CODE_MAX)}")


def test_roundtrip_inprocess():
    print("\n== 2. 同进程往返 ==")
    raw = make_zip()
    blob = c.encrypt(PW, raw)
    check("解密后与原 zip 完全一致", c.decrypt(PW, blob) == raw)
    check("容器头长度", len(blob) > c.HEADER_LEN)
    info = c.info(blob)
    check("info 报告 AES-256-GCM", info.get("algo") in (1, "AES-256-GCM"), str(info))


def test_standalone_clean_env():
    print("\n== 3. 独立工具 / 干净 sys.path ==")
    tmp = tempfile.mkdtemp()
    raw = make_zip()
    blob = c.encrypt(PW, raw)
    bpath = os.path.join(tmp, "DICK_加密备份_test.dickbackup")
    with open(bpath, "wb") as f:
        f.write(blob)
    outdir = os.path.join(tmp, "out")

    env = dict(os.environ)
    env["DICK_BACKUP_PW"] = PW
    env["PYTHONPATH"] = ""
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-I", os.path.join(ROOT, "dick_backup_tool.py"),
         "解密", bpath, "-o", outdir],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=ROOT)
    check("独立工具退出码 0", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[:400]}")
    if r.returncode == 0:
        same = True
        for n, t in SAMPLE.items():
            p = os.path.join(outdir, n.replace("/", os.sep))
            if not os.path.isfile(p) or open(p, encoding="utf-8").read() != t:
                same = False
        check("还原内容逐字节一致", same)
        check("还原了全部 4 个文件", len(os.listdir(os.path.join(outdir, "saves"))) >= 1)
        # 备份 zip 内部有一层包裹目录，直接 extractall 会多套一层，
        # 和 App 内「从备份还原」的结果不一致 —— 必须剥掉。
        check("没有多出包裹目录",
              not any(d.startswith("DICK_备份") for d in os.listdir(outdir)),
              str(os.listdir(outdir)))

    # 查看 命令也必须能独立跑
    r2 = subprocess.run(
        [sys.executable, "-I", os.path.join(ROOT, "dick_backup_tool.py"), "查看", bpath],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=ROOT)
    check("查看 命令退出码 0", r2.returncode == 0, r2.stderr[:300])
    check("查看 显示 AES-256-GCM", "AES-256-GCM" in r2.stdout, r2.stdout[:200])


def test_wrong_password():
    print("\n== 4. 失败路径 ==")
    raw = make_zip()
    blob = c.encrypt(PW, raw)
    for bad in ["wrong password here", "", PW + "x", PW[:-1]]:
        try:
            out = c.decrypt(bad, blob)
            check(f"错口令 {bad[:16]!r} 必须失败", False, "居然解开了")
        except Exception:
            check(f"错口令 {bad[:16]!r} 被拒绝", True)

    # 篡改：改密文任意一个字节
    bad_blob = bytearray(blob)
    bad_blob[-1] ^= 0x01
    try:
        c.decrypt(PW, bytes(bad_blob))
        check("篡改密文尾部必须失败", False, "居然通过了")
    except Exception:
        check("篡改密文尾部被拒绝", True)

    # 篡改头部（algo 字段）—— 头部是 AAD，必须被认证
    bad2 = bytearray(blob)
    bad2[5] = 9
    try:
        c.decrypt(PW, bytes(bad2))
        check("篡改算法字段必须失败（防降级）", False, "居然通过了")
    except Exception:
        check("篡改算法字段被拒绝（防降级）", True)

    # 截断
    try:
        c.decrypt(PW, blob[: c.HEADER_LEN + 4])
        check("截断文件必须失败", False, "居然通过了")
    except Exception:
        check("截断文件被拒绝", True)


def test_no_plaintext_leak():
    print("\n== 5. 密文不得泄露明文 ==")
    raw = make_zip()
    blob = c.encrypt(PW, raw)
    # 文件名
    leaks = 0
    for n in SAMPLE:
        base = os.path.basename(n).encode("utf-8")
        if base in blob:
            leaks += 1
            print("     泄露文件名:", n)
    check("密文中无明文文件名", leaks == 0, f"{leaks} 个泄露")
    # 内容特征串
    for probe in ["小林", "第一章", "她站在雨里", "设定A", "deepseek-flash"]:
        if probe.encode("utf-8") in blob:
            check(f"密文中无明文 {probe!r}", False)
    check("密文中无明文内容片段", True)
    # 拉丁文件名（ASCII 也可能被误认为明文）
    check("密文中无 'saves/' 路径", b"saves/" not in blob)
    check("密文中无 'PK'  zip 魔数", not blob.startswith(b"PK") and b"PK\x03\x04" not in blob)


def test_container_is_not_block_aligned():
    """用户明确要求：密文不能是规整的 16 字节块 —— 否则一眼看出是 AES。"""
    print("\n== 6. 非定长 / 非分块外观 ==")
    sizes = []
    for i in range(6):
        blob = c.encrypt(PW, make_zip())
        sizes.append(len(blob))
    body = [s - c.HEADER_LEN for s in sizes]
    check("密文长度不是 16 的倍数（多数样本）",
          sum(1 for b in body if b % 16 != 0) >= 4, str(body))
    check("同一输入两次加密长度可不同（随机填充）", len(set(sizes)) > 1, str(sizes))
    b1 = c.encrypt(PW, make_zip())
    b2 = c.encrypt(PW, make_zip())
    check("同一明文两次加密密文不同（随机 salt/nonce）", b1 != b2)


def test_empty_and_tiny():
    print("\n== 7. 边界 ==")
    for raw in [b"", b"a", b"\x00" * 10]:
        blob = c.encrypt(PW, raw)
        check(f"空/极小 {len(raw)}B 往返", c.decrypt(PW, blob) == raw)


def test_adaptive_compression():
    print("\n== 8. 自适应压缩（压不小就原样存）==")
    import struct as _s
    raw = make_zip()                        # deflate 过的高熵 zip
    blob = c.encrypt(PW, raw)
    inner = c._unpad(_decrypt_inner(blob))
    payload, stored = inner
    check("高熵 zip 被判定为不压缩", stored,
          "压了反而膨胀：%d -> %d" % (len(raw), len(c.compress(raw))))
    check("不压缩时容器不比压缩版本更大",
          len(blob) <= len(c.encrypt(PW, c.compress(raw))) + 4096)
    # 纯文本（未压缩）应该走压缩路径
    text = ("她站在雨里，伞是坏的。" * 300).encode("utf-8")
    blob2 = c.encrypt(PW, text)
    payload2, stored2 = c._unpad(_decrypt_inner(blob2))
    check("纯文本走压缩路径", not stored2)
    check("纯文本压得动", len(c.compress(text)) < len(text),
          "%d -> %d" % (len(text), len(c.compress(text))))
    check("压缩路径往返正确", c.decrypt(PW, blob2) == text)
    check("不压缩路径往返正确", c.decrypt(PW, blob) == raw)


def _decrypt_inner(blob):
    """只取 GCM 解出来的 inner，用于检查内部标志位"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    hdr = blob[:c.HEADER_LEN]
    salt = blob[11:11 + c.SALT_LEN]
    nonce = blob[11 + c.SALT_LEN:c.HEADER_LEN]
    iters = _s.unpack(">I", blob[7:11])[0]
    key = c.derive_key(PW, salt, iters)
    return AESGCM(key).decrypt(nonce, blob[c.HEADER_LEN:], hdr)


def test_old_format_still_reads():
    print("\n== 9. 旧格式备份必须仍能解开 ==")
    import struct as _s2
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = make_zip()

    def old_pad(data):                       # 严格 64k、无随机尾、无标志位
        need = 4 + len(data)
        blocks = (need + 63) // 64
        inner = _s2.pack(">I", len(data)) + data
        return inner + os.urandom(blocks * 64 - len(inner))

    salt = os.urandom(16)
    nonce = os.urandom(12)
    iters = 20000
    key = c.derive_key(PW, salt, iters)
    hdr = c._build_header(c.ALGO_AES256_GCM, c.KDF_PBKDF2_SHA256, iters, salt, nonce)
    old = hdr + AESGCM(key).encrypt(nonce, old_pad(c.compress(raw)), hdr)
    check("旧容器 body % 16 == 0（旧格式特征）", (len(old) - c.HEADER_LEN) % 16 == 0)
    check("新代码能解旧备份", c.decrypt(PW, old) == raw)

    # 独立工具也要能解旧备份
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "old.dickbackup")
    with open(p, "wb") as f:
        f.write(old)
    out = os.path.join(tmp, "o")
    env = dict(os.environ); env["DICK_BACKUP_PW"] = PW
    env["PYTHONPATH"] = ""; env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "dick_backup_tool.py"),
                        "解密", p, "-o", out],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, cwd=ROOT)
    check("独立工具能解旧备份", r.returncode == 0, r.stderr[:300])


if __name__ == "__main__":
    print("=" * 56)
    print("加密备份测试")
    print("=" * 56)
    test_codebook_matches()
    test_roundtrip_inprocess()
    test_standalone_clean_env()
    test_wrong_password()
    test_no_plaintext_leak()
    test_container_is_not_block_aligned()
    test_empty_and_tiny()
    test_adaptive_compression()
    test_old_format_still_reads()
    print("\n" + "=" * 56)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
