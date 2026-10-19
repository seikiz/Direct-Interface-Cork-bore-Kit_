# -*- coding: utf-8 -*-
"""modules/voice/module.py —— 语音引擎模块的唯一入口

铁律 2：模块只有一个入口 `register(kernel)`。`engines.py` / `service.py` 都是内部实现，
外部不许 import；要能力就 `kernel.service("voice")`。

本模块提供什么：
    voice → VoiceService：文本 → wav 的统一入口，两个引擎
              utau   —— 本地 UTAU（唱歌式拼接合成，纯本地）
              hanasu —— VOICEVOX 本地 HTTP（说话自然，默认 :50021）
              auto   —— HANASU 就绪就用它，否则回落 UTAU

为什么搬它：
    原来 `voice_engine.py`（260 行）躺在仓库根，路径写死 `utau_env\\Scripts\\python.exe`、
    声库写死 `utau_voicebanks\\默认声库`、合成脚本写死同目录的 `utau_speak.py`，
    还直接 `import putao` —— 这三样都是**宿主**才知道的东西。搬进块以后：
      ① 路径/解释器/声库/合成脚本一律 `bind(host)` 注入（缺了就当场说清楚，不猜目录）；
      ② 第三方合成引擎（putao）由宿主以 `synth` 回调注入，块本身只依赖 stdlib；
      ③ 声卡是独占设备 —— 块自己带一把锁，搬走以后照样不会两条合成同时抢设备。
"""

MODULE_ID = "voice"


def register(kernel):
    """内核调它一次：把本模块的服务挂到内核上。"""
    from .service import VoiceService

    service = VoiceService(log=kernel.log)
    if not kernel.registry.register("voice", service, owner=MODULE_ID):
        raise RuntimeError("服务 voice 注册失败（可能已有同名服务）")
    kernel.log.info("语音引擎已就绪（utau / hanasu 两个引擎，壳层门面见仓库根 voice_engine.py）",
                    MODULE_ID)
    return service
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌