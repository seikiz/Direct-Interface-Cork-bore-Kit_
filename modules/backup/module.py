# -*- coding: utf-8 -*-
"""modules/backup/module.py —— 加密备份模块的唯一入口

铁律 2：模块只有一个入口 `register(kernel)`。外部（壳层/别的模块）**不许**
import 本模块下的 service.py —— 那个文件是内部实现，随时可以改名/拆分。
要能力就 `kernel.service("backup")`，要事件就 `kernel.bus.on("backup.*")`。

本模块提供什么（服务名 = manifest.provides.services 里那一个）：
    backup → BackupService：口令强度/恢复码、容器封装（seal/unseal）、还原铺盘

为什么备份要单独成模块：
    它是"救数据"的路径。救数据的功能绝不该跟界面/对话/联网挤在一个文件里 ——
    主程序改出问题时，备份的代码路径必须还是那条被单独测过的路径。
"""

MODULE_ID = "backup"


def register(kernel):
    """内核调它一次：把本模块的服务挂到内核上。"""
    from .service import BackupService

    service = BackupService(log=kernel.log)
    if not kernel.registry.register("backup", service, owner=MODULE_ID):
        raise RuntimeError("服务 backup 注册失败（可能已有同名服务）")
    kernel.log.info("加密备份已就绪（独立解密工具 dick_backup_tool.py 仍然可用）", MODULE_ID)
    return service
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌