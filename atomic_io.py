# -*- coding: utf-8 -*-
"""atomic_io.py —— 原子写：临时文件 → fsync → os.replace。

为什么要有这一层
----------------
直接 `open(path, "w")` 覆盖写的问题：写到一半断电 / 进程被任务管理器结束 /
更新程序正在替换文件，目标文件就变成**半个 JSON**——下次启动读它就是解析失败，
存档、配置、角色卡一起报废。这类损坏不可逆，也没有"重试"能救。

正确做法三步（本模块实现）：
  ① 同目录建临时文件（**必须同卷**：跨盘 os.replace 会退化成"先删再拷"，
     断电窗口里原文件已经没了）；
  ② 写完 flush + fsync（内容先落盘，再谈换名）；
  ③ os.replace 原子换名（Windows 上也是原子的覆盖），最后尽力 fsync 目录。

失败的约定：任何一步出错都**清理临时文件并原样抛出**——调用方该报错就报错，
但原来的文件必须还在。
"""
from __future__ import annotations

import io
import json
import os
import tempfile

TMP_PREFIX = ".atomic-"
TMP_SUFFIX = ".tmp"


def _same_dir_tmp(path):
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, suffix=TMP_SUFFIX, dir=d)
    return fd, tmp, d


def _fsync_dir(d):
    """目录项也刷一次（POSIX 需要；Windows 上失败就算了，不影响正确性）。"""
    try:
        fd = os.open(d, os.O_RDONLY)
    except Exception:
        return
    try:
        os.fsync(fd)
    except Exception:
        pass
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def write_bytes(path, data):
    """原子写二进制。返回目标路径。"""
    fd, tmp, d = _same_dir_tmp(path)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _fsync_dir(d)
        return path
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def write_text(path, text, encoding="utf-8", newline="\n"):
    """原子写文本。"""
    data = (text or "").replace("\r\n", "\n") if newline == "\n" else (text or "")
    return write_bytes(path, data.encode(encoding))


def write_json(path, obj, indent=2, ensure_ascii=False, sort_keys=False):
    """原子写 JSON。**不要**再套 `with open(...)`——这里的顺序是有讲究的。"""
    text = json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent, sort_keys=sort_keys)
    return write_text(path, text + "\n")


def read_json(path, default=None):
    """读 JSON：坏文件/不存在都返回 default（读侧不负责修，交给 save_guard）。"""
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def leftovers(path):
    """目标目录里由本模块留下的临时文件（用于测试与自检；正常应为空）。"""
    d = os.path.dirname(os.path.abspath(path)) or "."
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in os.listdir(d)
            if n.startswith(TMP_PREFIX) and n.endswith(TMP_SUFFIX)]
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌