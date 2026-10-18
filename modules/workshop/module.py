# -*- coding: utf-8 -*-
"""modules/workshop/module.py —— 创意工坊客户端模块的唯一入口

铁律 2：模块只有一个入口 `register(kernel)`；`client.py` 是内部实现，外部不许 import。
壳层通过 `kernel.service("workshop")` 拿服务，通过 `bind(host)` 把"宿主能力"接进来。

本模块提供什么：
    workshop → WorkshopClient：工坊面板那 17 个接口的**编排**（列表/搜索/上传/下载/
               点赞/删除/预览/导出/插件/打开目录/连接配置/代理探测/连通性自检）

为什么先迁它：
    它是"最容易单独搬走、又最值钱"的一块 —— 不碰对话状态、不碰记忆、不碰存档写盘，
    只跟 HTTP 与本地文件列表打交道；搬走之后主程序少了约 300 行，且这部分终于能
    脱离 pywebview / 脱离 App 被单独测试（见 tests/test_kernel_boundaries.py 的假宿主）。
"""

MODULE_ID = "workshop"


def register(kernel):
    """内核调它一次：把本模块的服务挂到内核上。"""
    from .client import WorkshopClient

    service = WorkshopClient(log=kernel.log)
    if not kernel.registry.register("workshop", service, owner=MODULE_ID):
        raise RuntimeError("服务 workshop 注册失败（可能已有同名服务）")
    kernel.log.info("创意工坊客户端已就绪（宿主绑定见 HtmlApp._workshop_client）", MODULE_ID)
    return service
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌