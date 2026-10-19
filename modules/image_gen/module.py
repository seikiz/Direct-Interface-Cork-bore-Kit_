# -*- coding: utf-8 -*-
"""modules/image_gen/module.py —— 生图引擎模块的唯一入口

铁律 2：模块只有一个入口 `register(kernel)`。`service.py` / `backends.py` / `presets.py`
都是内部实现，外部**不许** import；要能力就 `kernel.service("image_gen")`。

本模块提供什么：
    image_gen → ImageGenService：四个后端（OpenAI 兼容 / Pollinations 免费 / 本地 A1111 /
                本地 ComfyUI）的生图编排 + 预设（内置 6 套 + 用户覆盖）的读写

为什么它值钱：
    原来这 489 行躺在仓库根的 `image_gen.py` 里，被主程序 `import image_gen` 直接调用。
    搬进块里之后：① 换项目能整目录拷走（只要 python + urllib）；② 后端协议终于能脱离
    界面被单测（自检里用假传输把四条协议的两头都钉死，不开 socket）。

宿主能力一律 `bind(host)` 注入：log / time（退避用的时钟）/ proxy（网络代理）/ progress（进度回调）。
缺省时全部退化成"标准库默认行为"，一条宿主代码都不读（ARCHITECTURE.md 十二）。
"""

MODULE_ID = "image_gen"


def register(kernel):
    """内核调它一次：把本模块的服务挂到内核上。"""
    from .service import ImageGenService

    service = ImageGenService(log=kernel.log)
    if not kernel.registry.register("image_gen", service, owner=MODULE_ID):
        raise RuntimeError("服务 image_gen 注册失败（可能已有同名服务）")
    kernel.log.info("生图引擎已就绪（端点决定后端；壳层门面见仓库根 image_gen.py）", MODULE_ID)
    return service
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌