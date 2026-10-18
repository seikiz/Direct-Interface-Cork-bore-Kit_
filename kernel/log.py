# -*- coding: utf-8 -*-
"""kernel/log.py —— 内核日志（沿用工程现有的 print 风格，不引入 logging 那套）

为什么不用标准库 logging：
    现有代码到处是 `print("[工坊] ...")`，用户在控制台/打包版日志里已经习惯这个形状。
    为了"看起来专业"换一套 logging 配置，收益是零，代价是排查时两套格式混在一起。
    所以这里只做三件 print 做不到的事：
      ① 统一前缀 + 模块标签（`[kernel][backup] ...`），一眼看出是谁在说话；
      ② 留一份**有上限的环形缓冲**，测试与自检能读到"刚才降级的是哪个模块、什么错"；
      ③ error 级别的记录单独记一份，壳层可以据此给用户一句人话提示。
"""

import time

_MAX_RECORDS = 400          # 环形缓冲上限：内核日志是给排查用的，不是数据


class Log(object):
    """内核日志：print 到控制台，同时留最近 400 条供测试/自检读取。"""

    def __init__(self, sink=None, echo=True):
        self._sink = sink          # 自定义输出（None = 用 print）
        self.echo = bool(echo)
        self._records = []
        self.errors = []           # [(tag, msg)] —— 只留 error 级，供降级检查

    # ---- 写<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌入 ----
    def _emit(self, level, msg, tag=""):
        text = "[kernel]%s %s" % (("[%s]" % tag) if tag else "", msg)
        rec = {"level": level, "tag": tag, "msg": str(msg), "at": time.time()}
        self._records.append(rec)
        if len(self._records) > _MAX_RECORDS:
            del self._records[:len(self._records) - _MAX_RECORDS]
        if level == "error":
            self.errors.append((tag, rec["msg"]))
            if len(self.errors) > 100:
                del self.errors[:len(self.errors) - 100]
        if not self.echo:
            return
        try:
            if callable(self._sink):
                self._sink(text)
            else:
                print(text)
        except Exception:
            pass                  # 日志永远不许把调用方弄崩

    def info(self, msg, tag=""):
        self._emit("info", msg, tag)

    def warn(self, msg, tag=""):
        self._emit("warn", msg, tag)

    def error(self, msg, tag=""):
        self._emit("error", msg, tag)

    # ---- 读取 ----
    def records(self):
        return list(self._records)

    def find(self, needle, level=None):
        """按子串找记录（测试与自检用：确认降级日志里点明了模块与错因）"""
        out = []
        for r in self._records:
            if level and r["level"] != level:
                continue
            if needle in r["msg"] or needle in r["tag"]:
                out.append(r)
        return out

    def clear(self):
        self._records = []
        self.errors = []
