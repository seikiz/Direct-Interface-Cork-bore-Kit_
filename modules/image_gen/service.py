# -*- coding: utf-8 -*-
"""modules/image_gen/service.py —— 生图服务（模块内部实现，外部不许 import）

壳层拿到的是这一个对象：`kernel.service("image_gen")`，再 `bind(host)` 把宿主能力接进来。

接口分三组（block.json 的 interface.methods 就是这张表）：
    宿主注入  bind
    一键生图  generate / quick_test
    后端识别  backend_of / resolve_backend / needs_key / split_size / mime_of
    预设读写  presets_path / load_presets / save_presets / user_presets_json / list_presets

两个刻意的边界：
  ① **配置不归块管**：key / base_url / model / backend 全由调用方按次传进来（主程序从
     自己的 config 里取）。块不认识 `config.json`，也不缓存密钥 —— 换项目照样能用。
  ② **路径不归块猜**：预设文件路径由调用方给（`load_presets(base_dir)`），块不读宿主的
     `app_paths`（ARCHITECTURE.md 十二：不读宿主，路径一律注入）。

`bind(host)` 认的宿主属性（都可缺省）：
    time      带 sleep/time 的时钟（退避与超时判定）；缺省用标准库 time
    proxy     网络代理 URL；缺省走 urllib 默认（环境变量那套）
    log       有 info/warn/error 的日志对象
    progress  进度回调 (stage, **kw)，生图开始/成功/失败各调一次；缺省什么都不做
"""

from . import backends as be_mod
from . import presets as presets_mod

_BACKENDS = be_mod.BACKENDS


class ImageGenService(object):
    """四个后端的生图编排。方法都不弹对话框、不写用户目录（预设除外，路径由调用方给）。"""

    def __init__(self, log=None):
        self.log = log
        self.host = None
        self.last_error = ""
        self.net = be_mod.Net(log=log)

    # ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 宿主注入
    def bind(self, host, net=None):
        """把宿主接进来（幂等：壳层每次取服务都调一次也没关系）。

        `net` 只在自检里用（塞假传输）；生产环境交给 `bind(host)` 自己建。
        """
        self.host = host
        if net is not None:
            self.net = net
            self.net.host = host
            return self
        self.log = getattr(host, "log", None) or self.log
        self.net = be_mod.Net(host=host, log=self.log)
        return self

    def _progress(self, stage, **kw):
        """进度回调（宿主没给就什么都不做 —— 不许因为"没人听"就报错）"""
        fn = getattr(self.host, "progress", None)
        if not callable(fn):
            return
        try:
            fn(stage, **kw)
        except Exception:
            pass

    # ---------------------------------------------------------------- 后端识别
    def backend_of(self, base_url):
        return be_mod.backend_of(base_url)

    def resolve_backend(self, base_url, backend="auto"):
        return be_mod.resolve_backend(base_url, backend)

    def needs_key(self, base_url, backend="auto"):
        return be_mod.needs_key(base_url, backend)

    def split_size(self, size, default=1024):
        return be_mod.split_size(size, default)

    def mime_of(self, raw):
        return be_mod.mime_of(raw)

    @property
    def BACKENDS(self):
        return _BACKENDS

    # ---------------------------------------------------------------- 一键生图
    def generate(self, prompt, preset="anime", size="1024x1024", api_key="",
                 base_url="https://api.siliconflow.cn/v1",
                 model="black-forest-labs/FLUX.1-schnell",
                 negative_prompt="", extra="", seed=None, presets=None, backend="auto",
                 timeout=None):
        """生图。返回 (ok, 数据, 消息)；数据形如 {"b64"|"url", "mime", "preset", "seed"}。"""
        self._progress("start", preset=preset, size=size, backend=backend)
        ok, data, msg = be_mod.generate(
            self.net, prompt, preset=preset, size=size, api_key=api_key,
            base_url=base_url, model=model, negative_prompt=negative_prompt, extra=extra,
            seed=seed, presets=presets, backend=backend, timeout=timeout)
        self.last_error = "" if ok else str(msg)
        self._progress("done" if ok else "fail", preset=preset, msg=msg)
        return ok, data, msg

    def quick_test(self):
        """给设置面板/自检看的一句话提示"""
        return ("生图引擎就绪。端点决定后端（也可在「生图后端」里手选）：OpenAI 兼容"
                "（硅基流动/智谱…需 Key）· https://image.pollinations.ai（免 Key 免费，有限流）· "
                "http://127.0.0.1:7860（本地 A1111/Forge）· http://127.0.0.1:8188（本地 ComfyUI）")

    # ---------------------------------------------------------------- 预设
    @property
    def PRESETS(self):
        return presets_mod.PRESETS

    @property
    def PRESETS_FILE(self):
        return presets_mod.PRESETS_FILE

    def presets_path(self, base_dir):
        return presets_mod.presets_path(base_dir)

    def load_presets(self, base_dir=None):
        return presets_mod.load_presets(base_dir)

    def save_presets(self, base_dir, obj):
        return presets_mod.save_presets(base_dir, obj)

    def user_presets_json(self, base_dir):
        return presets_mod.user_presets_json(base_dir)

    def list_presets(self, presets=None):
        return presets_mod.list_presets(presets)
