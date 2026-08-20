# -*- coding: utf-8 -*-
# ============================================================
#   dick_mark.py - DICK 反抄袭溯源水印（架构级，不可剥离）
#
#   用途：在 DICK 的每一层产出（剧本/打包产物/嵌卡/配置/前端）
#   中注入隐蔽的架构签名，任何抄袭都无法清洗干净——
#   只要架构被复制，签名就跟走。
#
#   签名体系（三层）：
#     MARK_JS    : 唯一架构标识符（ASCII，可安全嵌入任何语言/文件）
#     SIGNATURE  : 人类可读来源声明（含版本与年份）
#     finger()   : 生成一次性的来源指纹（用于校验/举证）
#
#   嵌入位置：
#     1. codex.json 打包时 → _signature 字段（格式级，抄格式就带走）
#     2. 打包 HTML → <!-- DICK-MARK --> 注释 + JS 变量 window.__DICK_MARK
#     3. 打包 EXE 壳 → 文件头部注释 + 运行时日志
#     4. 酒馆卡 PNG → tEXt 块 "dick_mark"（跨格式，抄卡带走）
#     5. config.json → "dick_mark" 字段（配置级）
#     6. 前端 → 隐蔽 DOM 属性 + 控制台标识（界面级）
# ============================================================

import hashlib
import time

# 唯一架构标识（ASCII，多处复用，保持完全一致）
MARK_JS = "DICK_CODEX_SIG_7f3a9c2e"

# 人类可读来源声明
SIGNATURE = "Direct-Interface Cork-bore Kit (DICK) v2.0 — CODEX engine"

# 生成一次性来源指纹（时间 + 随机 + 标识 → 哈希）
def finger(salt=""):
    seed = f"{MARK_JS}|{time.time()}|{salt}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def mark_dict(extra=None):
    """生成用于注入 dict 的签名块（_signature / dick_mark 字段共用）"""
    d = {
        "engine": MARK_JS,
        "source": SIGNATURE,
    }
    if extra:
        d.update(extra)
    return d


# ============================================================
# 合作边界声明（重要）
#
#   DICK 的反抄袭水印只存在于【自己的地盘】：
#     剧本打包产物 / 前端 / config / 源码 / 嵌卡 PNG（DICK 导出时）。
#
#   但【导出给酒馆（SillyTavern）的角色卡 / 世界卡】必须保持
#   干净：不注入任何零宽隐写、不夹带 DICK 专属痕迹——
#   酒馆有自己的格式与数据清洗，往人家字段里埋隐写是破坏合作。
#
#   诚意 = 互不侵犯：酒馆的卡进 DICK 无损兼容（我们做的），
#   DICK 的卡进酒馆也干净（这是我们要守的）。
#   卡进入酒馆后水印自动去除，是应有的结果，不是漏洞。
# ============================================================

