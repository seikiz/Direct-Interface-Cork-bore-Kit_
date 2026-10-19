# -*- coding: utf-8 -*-
"""modules/backup/service.py —— 加密备份服务（模块内部实现，外部不许 import）

迁移来源（**行为一字未改**，只是搬家）：
    · `crypto_core`：口令策略 / 恢复码 / 容器加解密 / 容器头信息
    · 主程序 HtmlApp 的 `_restore_from_zip`：解密后按目录铺回磁盘（含路径穿越防护）
    · 主程序 `api_backup_*` 里的口令闸门与错误文案

两个刻意的边界：
  ① **写文件对话框、时间戳、选桌面路径留在壳层**。模块负责"密码学 + 铺盘规则"，
     壳层负责"问用户存哪"。这样模块可以脱离界面被测试，壳层换掉 pywebview 也不影响备份格式。
  ② **加密能力由 `bind(host)` 注入**（ARCHITECTURE.md 十二：块只许依赖 stdlib + kernel）。
     以前这里 `import crypto_core` —— 那是仓库根目录的宿主代码，块搬去别的项目当场就
     ModuleNotFoundError。现在宿主把加解密实现（生产环境就是 crypto_core）用
     `bind(host, crypto=…)` 送进来；块只认 5 个方法：
         password_strength(pw) / make_recovery_code() / encrypt(pw, raw, iters=None)
         decrypt(pw, blob) / info(blob)
     铺盘（restore_zip）不需要任何宿主能力，所以它单独也能跑 —— 救数据的路不依赖加密实现。
"""

import os
import shutil

# 容器里允许还原的五个去处（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌键名与返回的计数表一一对应）
RESTORE_KEYS = ("saves", "worlds", "personas", "config", "codex")


class BackupService(object):
    """加密备份：口令 → 容器 → 还原。全部方法都不弹对话框、不写用户目录。"""

    def __init__(self, log=None):
        self.log = log
        self.last_error = ""
        self.host = None
        self.crypto = None

    # ---------------------------------------------------------------- 宿主注入
    def bind(self, host, crypto=None):
        """把宿主接进来（幂等：壳层每次取服务都调一次也没关系）。

        `crypto` 是加解密实现（生产环境 = `crypto_core`）；不给时取 `host.crypto`。
        缺了它，seal/unseal/口令相关的方法会当场说清楚，而不是偷偷去 import 宿主。
        """
        self.host = host
        impl = crypto if crypto is not None else getattr(host, "crypto", None)
        if impl is not None:
            self.crypto = impl
        return self

    def _c(self):
        if self.crypto is None:
            raise RuntimeError("备份模块还没绑定加密能力（壳层没调 bind(host) 或宿主没有 crypto）")
        return self.crypto

    # ---------------------------------------------------------------- 口令
    def password_check(self, password):
        """给界面用：实时告诉用户口令够不够强（不存任何东西）"""
        lvl, msg = self._c().password_strength(password or "")
        return {"ok": True, "level": lvl, "msg": msg, "ok_to_use": lvl >= 2}

    def make_password(self):
        """生成一个随机强口令（32 字节 → base32，抄纸上比"想一个好记的"更可靠）"""
        return {"ok": True, "password": self._c().make_recovery_code()}

    def require_strong(self, password):
        """口令闸门：返回 (是否放行, 不达标时的界面文案)。

        文案与搬家前逐字一致 —— 前端已经按这句话做排版，改字等于改界面。
        """
        lvl, msg = self._c().password_strength(password or "")
        if lvl >= 2:
            return True, ""
        return False, ("口令不够强（%s）。加密备份的安全性 100%% 取决于口令强度，"
                       "请至少 12 位、混合大小写字母和数字。" % msg)

    # ---------------------------------------------------------------- 容器
    def seal(self, raw_zip, password, iters=None):
        """zip 字节 → 容器字节（压缩 + 填充 + AES-GCM，头参与认证）"""
        if iters is None:
            return self._c().encrypt(password, raw_zip)
        return self._c().encrypt(password, raw_zip, iters=iters)

    def unseal(self, blob, password):
        """容器字节 → zip 字节。口令错/被篡改都抛 ValueError（文案来自加密实现）"""
        return self._c().decrypt(password, blob)

    def info(self, blob):
        """容器头（公开信息：版本/算法/迭代数/大小），用于界面显示与排查"""
        return self._c().info(blob)

    # ---------------------------------------------------------------- 铺盘
    def restore_zip(self, z, bak, dirs):
        """把备份 zip 铺回磁盘。返回各类计数（**不需要宿主能力**）。

        dirs 由壳层给（模块不认识 `App` 这个对象）：
            {"root": 数据根, "saves":…, "worlds":…, "personas":…,
             "codex":…, "config_file":…}

        三条安全规则（搬家前就有，一条都不能少）：
          ① zip 条目里的 `..` 一律跳过 —— 备份文件被别人改过也不能写到 DICK 目录之外；
          ② 实际落点必须仍在数据根之下（realpath 判定，防符号链接/大小写绕过）；
          ③ 覆盖前把原文件复制到 `bak`（saves/backup/restore_<ts>），一失手还能捞回来。
        """
        restored = {k: 0 for k in RESTORE_KEYS}
        root = os.path.realpath(os.path.abspath(dirs["root"]))
        for info in z.infolist():
            if info.is_dir():
                continue
            safe = info.filename.replace("\\", "/")
            parts = safe.split("/")
            if len(parts) < 2:
                continue
            if ".." in parts:
                continue
            rel = "/".join(parts[1:])
            target = self._restore_target(rel, dirs)
            if not target:
                continue
            dst, key = target
            ap = os.path.realpath(os.path.abspath(dst))
            if not (ap == root or ap.startswith(root + os.sep)):
                continue
            if os.path.isfile(dst):
                try:
                    os.makedirs(bak, exist_ok=True)
                    shutil.copy2(dst, os.path.join(bak, os.path.basename(dst)))
                except Exception:
                    pass
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(z.read(info))
            restored[key] += 1
        return restored

    @staticmethod
    def _restore_target(rel, dirs):
        """条目相对路径 → (落盘绝对路径, 计数键)；不认识的位置返回 None（跳过）。

        注意判断的是 rel 里的层级，不是 parts 的长度 —— parts 还含最外层根目录名，
        用 len(parts)==2 会把全部条目跳过（这条坑踩过一次）。
        """
        if rel == "config.json":
            return dirs["config_file"], "config"
        if rel.startswith("saves/") and rel.count("/") == 1:
            return os.path.join(dirs["saves"], os.path.basename(rel)), "saves"
        if rel.startswith("worlds/") and rel.count("/") == 1:
            return os.path.join(dirs["worlds"], os.path.basename(rel)), "worlds"
        if rel.startswith("personas/") and rel.count("/") == 1:
            return os.path.join(dirs["personas"], os.path.basename(rel)), "personas"
        if rel.startswith("codex/"):
            # codex 可能是目录，要保留子目录层级
            return (os.path.join(dirs["codex"], rel[len("codex/"):].replace("/", os.sep)),
                    "codex")
        return None
