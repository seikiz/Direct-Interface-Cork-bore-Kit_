# -*- coding: utf-8 -*-
"""kernel/config.py —— 内核配置读写（JSON，原子写）

和现有代码的关系：
    · 路径规则抄 kernel/paths.py（它抄 app_paths.py），不另立一套；
    · 原子写用「同目录临时文件 + os.replace」——与 save_guard.atomic_write_json 同一个手法，
      内核不 import save_guard（那是业务侧的数据保护模块），但这几行必须等价：
      写一半断电会留下半个 JSON，配置文件坏了就等于用户所有设置丢失。
    · **不**碰敏感字段的加解密：那是壳层/加密模块的事，内核不该认识 API Key 这种东西。
"""

import json
import os
import tempfile

from . import paths


class Config(object):
    """一个 JSON 配置文件的读写。故意做得薄：内核只要"能读默认值、能存"。"""

    def __init__(self, name="config.json", base_dir=None, log=None, autosave=False):
        self.name = name
        self.base_dir = paths.get_base_dir(base_dir)
        self.path = paths.get_config_file(name, self.base_dir)
        self.log = log
        self.autosave = bool(autosave)
        self._data = {}

    # ---- <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌读 ----
    def load(self):
        self._data = {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data = data
        except FileNotFoundError:
            pass                      # 首次运行没有配置是正常的
        except Exception as e:
            if self.log:
                self.log.warn("配置读不出来（按空配置继续）：%s" % str(e)[:120], "config")
        return self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        if self.autosave:
            self.save()
        return value

    def update(self, mapping):
        self._data.update(dict(mapping or {}))
        if self.autosave:
            self.save()
        return self._data

    def snapshot(self):
        return dict(self._data)

    # ---- 写 ----
    def save(self, data=None):
        payload = self._data if data is None else data
        return atomic_write_json(self.path, payload)


def atomic_write_json(path, data):
    """原子写 JSON：同目录临时文件 → fsync → os.replace。

    为什么不用 tempfile.gettempdir()：跨盘 rename 会退化成"先删再拷"，
    断电窗口里原文件就没了。临时文件必须与目标同目录（同一个卷）。
    """
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kernel_cfg_", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise
