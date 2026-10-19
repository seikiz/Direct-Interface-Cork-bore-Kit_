# -*- coding: utf-8 -*-
"""modules/codex/module.py —— CODEX（GALGAME 引擎）模块的唯一入口

铁律 2：模块只有一个入口 `register(kernel)`。其余 8 个文件都是内部实现，外部不许 import；
要能力就 `kernel.service("codex")`。

本模块提供什么：
    codex → CodexService：一个**自带的视觉小说包格式**（codex.json + 素材目录 + zip 交换）
             的全部能力 —— 文本解析、校验、静态分析、全路径模拟、试玩走查、
              打包成独立 HTML / 独立 EXE。格式是开放的（codex/1.0），任何前端都能实现。

为什么按 400 行预算拆成 8 个文件（原 `codex_core.py` 2030 行）：
    ① `constants.py`  格式常量与文件分类（最底层）
    ② `scene.py`      剧本语法：文本 → codex.json
    ③ `rules.py`      行类型 / 条件 / 选项 / HTML 消毒 / 校验
    ④ `flow.py`       条件推进：单路径走查 + 全路径模拟
    ⑤ `analyze.py`    静态分析：可达性 / 资源引用 / 死分支
    ⑥ `pack.py`       包的目录与 zip 格式（自有格式，只认传进来的路径）
    ⑦ `player_js.py`  导出播放器的内联 JS（326 行，单独成文件）
    ⑧ `player.py`     单文件 HTML 的渲染与导出
    ⑨ `exe.py`        打包独立 EXE（pywebview 壳 + PyInstaller）
    ⑩ `service.py`    对外的接口表（28 个方法，全是转发 + 注入水印模块）
    依赖方向是单向的：constants ← rules ← scene/flow/analyze ← pack ← player ← exe ← service。

为什么它值钱：
    它是"能对外授权的格式 + 参考实现"。搬进块以后，别的项目（酒馆、播放器、命令行工具）
    可以直接把这个目录拷走 —— 只要 stdlib（json/zipfile/struct/zlib/base64）。
"""

MODULE_ID = "codex"


def register(kernel):
    """内核调它一次：把本模块的服务挂到内核上。"""
    from .service import CodexService

    service = CodexService(log=kernel.log)
    if not kernel.registry.register("codex", service, owner=MODULE_ID):
        raise RuntimeError("服务 codex 注册失败（可能已有同名服务）")
    kernel.log.info("CODEX 引擎已就绪（包格式 codex/1.0；壳层门面见仓库根 codex_core.py）",
                    MODULE_ID)
    return service
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌