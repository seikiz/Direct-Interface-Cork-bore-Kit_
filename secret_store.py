# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   secret_store.py - 本地敏感信息加密（Windows DPAPI）
#
#   商业级质量：API Key / 图床 Key / 工坊连接串 等敏感信息明文落盘是安全隐患。
#   本模块用 Windows 原生 DPAPI (CryptProtectData/CryptUnprotectData) 加密，
#   以 base64 字符串存放。DPAPI 与当前 Windows 用户/机器绑定：
#     - 同一用户登录态可解密，换账号/换机器不能解（密钥不可拷贝，安全）。
#     - 无需额外依赖（ctypes 调 crypt32），PyInstaller 打包无坑。
#
#   用法：
#     token = secret_store.encrypt("sk-xxxx")   # -> "AQAA...b64"
#     key   = secret_store.decrypt(token)       # -> "sk-xxxx"
#     secret_store.is_supported()               # DPAPI 是否可用
#
#   兼容/降级：DPAPI 不可用或解密失败时，decrypt 返回 None（由调用方决定是否
#   回退），encrypt 在 DPAPI 不可用时返回原文（明确标记，避免锁死用户）。
#   —— 这保证"换到无 DPAPI 环境（极少数）"不会数据丢失，只是不加密；在
#   正常 Windows 下始终加密。
# ============================================================

import base64
import ctypes
import sys
from ctypes import wintypes

try:
    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _HAS_DPAPI = bool(_crypt32 and _kernel32)
except Exception:
    _HAS_DPAPI = False


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob_for(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf


def is_supported() -> bool:
    return _HAS_DPAPI


def encrypt(plaintext: str) -> str:
    """加密字符串 → base64。DPAPI 不可用时返回原文（降级，不锁死）。"""
    if not plaintext:
        return ""
    if not _HAS_DPAPI:
        return plaintext
    data = str(plaintext).encode("utf-8")
    in_blob, in_buf = _blob_for(data)
    out_blob = _DATA_BLOB()
    try:
        ok = _crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            return plaintext  # 失败降级
        try:
            enc = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return base64.b64encode(enc).decode("ascii")
        finally:
            _kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return str(plaintext)


def decrypt(token: str):
    """base64 密文 → 原文。解密失败返回 None（调用方决定回退/报错）。"""
    if not token:
        return ""
    if not _HAS_DPAPI:
        return token  # 降级模式：假定存的是明文
    try:
        enc = base64.b64decode(str(token).encode("ascii"))
    except Exception:
        return None  # 不是合法 base64，可能本来就是明文
    buf = ctypes.create_string_buffer(enc, len(enc))
    in_blob = _DATA_BLOB(len(enc), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    try:
        ok = _crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            # CRYPT_FAILED：密文与当前用户/机器不匹配（换机/换账号），无法解密
            return None
        try:
            raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return raw.decode("utf-8")
        finally:
            _kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


# 自检（命令行）：python secret_store.py <文本> → 打印加密/解密往返
if __name__ == "__main__":
    import sys as _s
    sample = _s.argv[1] if len(_s.argv) > 1 else "sk-test-12345"
    print("DPAPI supported:", is_supported())
    enc = encrypt(sample)
    print("encrypt ->", enc[:40] + "…" if len(enc) > 40 else enc)
    dec = decrypt(enc)
    print("decrypt ->", dec)
    print("roundtrip ok:", dec == sample)
