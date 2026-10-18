# -*- coding: utf-8 -*-
"""kernel/manifest.py —— 模块清单（manifest.json）的数据类与校验

清单是**契约**，不是注释：
    · 模块说自己提供什么（provides）、依赖什么（requires）、要不要懒加载（lazy）；
    · 加载器据此决定"能不能装、装完对不对"，装完还要把 provides 与真实注册的服务对账；
    · 校验失败一律**拒绝加载并记日志**，绝不允许"清单写一套、代码做一套"。

顶层字段（多一个不认，少一个不填都不行）：
    id       小写字母开头的标识符（[a-z][a-z0-9_]*），全仓库唯一
    version  四段版号 主.次.补.实验（见 kernel/version.py）
    provides {services, routes, ui_screens, commands}  四张表，缺省视为空表
    requires {services, modules}                       缺省视为空
    lazy     true = 不在启动时 register，等第一次取服务时再装
"""

import json
import os
import re

from . import version as _version

PROVIDES_KEYS = ("services", "routes", "ui_screens", "commands")
REQUIRES_KEYS = ("services", "modules")
TOP_KEYS = ("id", "version", "provides", "requires", "lazy")

_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# 服务名允许点号分段（`workshop.tran<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌sport`），因为一个模块以后可能拆出多个服务
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9_.]*$")


class ManifestError(ValueError):
    """清单不合法（id/version/provides/requires/lazy 任一不合规）"""

    def __init__(self, errors, source=""):
        self.errors = list(errors or [])
        self.source = source
        head = "manifest 校验失败" + (("（%s）" % source) if source else "")
        super(ManifestError, self).__init__(head + "：" + "；".join(self.errors))


class Manifest(object):
    """一个模块的清单。构造后 `errors` 为空才算可用。"""

    def __init__(self, data, source=""):
        self.source = source
        self.raw = dict(data or {})
        self.errors = []
        self.id = str(self.raw.get("id") or "").strip()
        self.version = str(self.raw.get("version") or "").strip()
        self.lazy = bool(self.raw.get("lazy", False))
        self.provides = _norm_tables(self.raw.get("provides"), PROVIDES_KEYS)
        self.requires = _norm_tables(self.raw.get("requires"), REQUIRES_KEYS)
        self._validate()

    # ---- 校验 ----
    def _validate(self):
        extra = [k for k in self.raw if k not in TOP_KEYS]
        if extra:
            self.errors.append("出现不认识的顶层字段：%s" % "、".join(sorted(extra)))
        missing = [k for k in ("id", "version") if not str(self.raw.get(k) or "").strip()]
        if missing:
            self.errors.append("缺少必填字段：%s" % "、".join(missing))
        if self.id and not _ID_RE.match(self.id):
            self.errors.append("id 不合规（应形如 backup / workshop_v2）：%r" % self.id)
        if self.version and not _version.is_valid(self.version):
            self.errors.append("version 必须是四段版号（如 1.0.0.0）：%r" % self.version)
        if not isinstance(self.raw.get("lazy", False), bool):
            self.errors.append("lazy 必须是 true/false")
        for table in ("provides", "requires"):
            bad = self._bad_tables(table)
            if bad:
                self.errors.append("%s 必须是对象，且键只能是 %s：%s"
                                   % (table, "/".join(PROVIDES_KEYS if table == "provides"
                                                      else REQUIRES_KEYS), "、".join(bad)))
        for name in self.provides["services"]:
            if not _SERVICE_RE.match(name):
                self.errors.append("provides.services 里的名字不合规：%r" % name)
        dups = _dups(self.provides["services"])
        if dups:
            self.errors.append("provides.services 里有重复项：%s" % "、".join(dups))
        for name in self.requires["modules"]:
            if not _ID_RE.match(name):
                self.errors.append("requires.modules 里的 id 不合规：%r" % name)
        if self.id in self.requires["modules"]:
            self.errors.append("模块不能 requires 自己：%s" % self.id)

    def _bad_tables(self, table):
        raw = self.raw.get(table)
        if raw is None:
            return []
        if not isinstance(raw, dict):
            return ["<整个字段>"]
        allowed = PROVIDES_KEYS if table == "provides" else REQUIRES_KEYS
        bad = [k for k in raw if k not in allowed]
        for k in raw:
            if k in allowed and not _is_str_list(raw.get(k)):
                bad.append(k)
        return bad

    # ---- 便利 ----
    @property
    def ok(self):
        return not self.errors

    def services(self):
        return list(self.provides["services"])

    def to_dict(self):
        return {"id": self.id, "version": self.version,
                "provides": {k: list(v) for k, v in self.provides.items()},
                "requires": {k: list(v) for k, v in self.requires.items()},
                "lazy": self.lazy}

    def __repr__(self):
        return "<Manifest %s v%s%s>" % (self.id, self.version, " lazy" if self.lazy else "")


# ---------------------------------------------------------------- 读取
def load_file(path):
    """从 manifest.json 读一个 Manifest；读不动抛 ManifestError（不返回半成品）"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ManifestError(["文件读不出来或不是合法 JSON：%s" % str(e)[:120]], path)
    if not isinstance(data, dict):
        raise ManifestError(["顶层必须是 JSON 对象"], path)
    m = Manifest(data, source=path)
    if m.errors:
        raise ManifestError(m.errors, path)
    return m


def load_module_manifest(module_dir):
    """读 `<模块目录>/manifest.json`"""
    return load_file(os.path.join(module_dir, "manifest.json"))


# ---------------------------------------------------------------- 小工具
def _is_str_list(v):
    return isinstance(v, (list, tuple)) and all(isinstance(x, str) and x.strip() for x in v)


def _norm_tables(raw, allowed):
    """把 provides/requires 归一成 {键: [字符串]}（缺省补空表，脏数据原样留着等校验报错）"""
    out = {k: [] for k in allowed}
    if not isinstance(raw, dict):
        return out
    for k in allowed:
        v = raw.get(k)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
    return out


def _dups(seq):
    seen, out = set(), []
    for x in seq:
        if x in seen and x not in out:
            out.append(x)
        seen.add(x)
    return out
