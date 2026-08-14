# ============================================================
#   ui_fonts.py - 全局 UI 字体体系
#
#   统一管理整个应用的字体家族与字号层级：
#   - 家族：用户选择的字体（"" 表示自动检测系统中第一个可用字体）
#   - 字号层级：small/list/normal/large/header/title/hero
#     以聊天正文字号 SIZE 为基准温和缩放（0.9x ~ 1.3x），
#     保证界面与聊天区视觉协调，同时不会撑爆固定宽度的控件
#
#   用法：
#     import ui_fonts as uf
#     uf.init("", 12)                    # 启动时初始化（家族, 聊天字号）
#     CTkLabel(..., font=uf.f("header", bold=True))
#     uf.set_size(16)                    # 用户调整字号后更新
# ============================================================

import tkinter.font as tkfont

# 当前状态：FAMILY 为空表示自动检测
FAMILY = ""
SIZE = 12

# 自动检测候选列表（按优先级）
_CANDIDATES = [
    "微软雅黑", "Microsoft YaHei", "黑体", "SimHei",
    "Noto Sans SC", "Source Han Sans SC", "PingFang SC",
    "宋体", "SimSun", "Segoe UI", "Arial", "Consolas",
]

# 语义字号层级（基准值，实际值随 SIZE 缩放）
_KINDS = {
    "small": 10,    # 状态栏、辅助提示
    "list": 11,     # 列表、次级标签
    "normal": 12,   # 正文、输入框、按钮
    "large": 13,    # 副标题
    "header": 14,   # 区块标题
    "title": 16,    # 窗口大标题
    "hero": 22,     # 欢迎页大字
}

_detected = None


def init(family="", size=12):
    """初始化全局字体（family 为空则自动检测）"""
    global FAMILY, SIZE, _detected
    FAMILY = family or ""
    try:
        SIZE = int(size)
    except (TypeError, ValueError):
        SIZE = 12
    if SIZE < 1:
        SIZE = 12
    _detected = None


def set_family(family):
    global FAMILY, _detected
    FAMILY = family or ""
    _detected = None


def set_size(size):
    global SIZE
    try:
        SIZE = int(size)
    except (TypeError, ValueError):
        pass


def get_family():
    """返回当前生效的字体家族（自动检测并缓存）"""
    global _detected
    if _detected is not None:
        return _detected
    _detected = FAMILY
    if not _detected:
        try:
            available = {str(x).lower() for x in tkfont.families()}
            for cand in _CANDIDATES:
                if cand.lower() in available:
                    _detected = cand
                    break
        except Exception:
            pass
    if not _detected:
        # 兜底：Windows 上微软雅黑必然存在；其他平台交给 Tk 默认字体
        _detected = _CANDIDATES[0]
    return _detected


def _scale():
    """UI 缩放系数：聊天字号 12 为基准，限制在 0.9 ~ 1.3"""
    return max(0.9, min(1.3, SIZE / 12.0))


def f(kind="normal", bold=False):
    """返回字体元组 (家族, 字号[, "bold"])，按语义层级缩放"""
    base = _KINDS.get(kind, 12)
    size = max(9, min(26, round(base * _scale())))
    return (get_family(), size, "bold") if bold else (get_family(), size)


def size_of(kind):
    """返回某个层级的实际字号"""
    return f(kind)[1]
