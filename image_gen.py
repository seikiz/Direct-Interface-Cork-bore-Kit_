# -*- coding: utf-8 -*-
# ===============================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌===============================================
#   image_gen.py - 生图引擎的**壳层门面**（能力已搬进 modules/image_gen/，这里只转调）
#
#   为什么这个文件还在：主程序的 `api_gen_image` / `api_gen_presets` / `api_save_image_gen`
#   / `api_get_image_presets_file` / `api_save_image_presets_file` 五个调用点写的是
#   `image_gen.xxx(...)`；tests/test_image_gen.py 与 tests/test_compat_surface.py 也是这么调用的。
#   ARCHITECTURE.md 七：「门面（facade）= 迁移期保留的旧接口，内部转调新模块 —— 让调用点不用改」。
#   所以这里一个函数名都不许少，行为与搬家前逐字一致。
#
#   唯一真相在哪：四个后端的协议 → modules/image_gen/backends.py；
#                 预设（内置 6 套 + 用户覆盖） → modules/image_gen/presets.py；
#                 对外的接口表 → modules/image_gen/block.json 的 interface.methods。
#   本文件**不含任何后端实现**：改协议要改块，改这里等于又造了第二份真相。
#
#   怎么拿到块：块由内核装载，壳层只能 `kernel.service("image_gen")` 拿服务（铁律 2）。
#   这里用一个「只装这一块的迷你内核」（load=False：不装别的模块），第一次调用时才建，
#   所以 import 本模块不会拖慢启动，也不会启动任何别的块。
#
#   宿主能力怎么注入：`bind(host)` 的 host 就是**本模块自己**（模块对象）。块在用时才取
#   `host.time` / `host.proxy` / `host.log` / `host.progress`，所以下面那个 `import time`
#   不是装饰 —— 它是 `image_gen.time` 这个名字的来源，测试与退避逻辑都认它。
# ==============================================================================================

import time                                      # image_gen.time：块退避用的时钟（可被替换）

_SERVICE = None


def _svc():
    """懒取本块的服务（进程内只建一次；失败时把原因原样抛出来）。"""
    global _SERVICE
    if _SERVICE is None:
        import kernel
        mini = kernel.boot(load=False, echo=False)     # 只发现模块，不装别的块
        _SERVICE = mini.service("image_gen").bind(_host())
    return _SERVICE


def _host():
    """宿主 = 本门面模块（块只认 time/proxy/log/progress 四个属性名）。"""
    import sys
    return sys.modules[__name__]


# ---------------------------------------------------------------- 后端识别
def backend_of(base_url):
    """按 base_url 判断后端：'pollinations' | 'comfyui' | 'sdwebui' | 'openai'。"""
    return _svc().backend_of(base_url)


def resolve_backend(base_url, backend="auto"):
    """设置里显式选了后端就用它，否则按端点自动认。"""
    return _svc().resolve_backend(base_url, backend)


def needs_key(base_url, backend="auto"):
    """这个后端要不要 API Key（三种本地/免费后端都留空即可）。"""
    return _svc().needs_key(base_url, backend)


def _split_size(size, default=1024):
    """'1024x1024' → (1024, 1024)；解析不了就用默认值。"""
    return _svc().split_size(size, default)


def _mime_of(raw):
    return _svc().mime_of(raw)


# ---------------------------------------------------------------- 预设
def presets_path(base_dir):
    return _svc().presets_path(base_dir)


def load_presets(base_dir=None):
    """内置预设 + 用户覆盖。返回 {id: {label, prompt, desc, custom?}}。"""
    return _svc().load_presets(base_dir)


def save_presets(base_dir, obj):
    """写用户覆盖文件。返回 (ok, 消息)。传 {} 即恢复内置默认。"""
    return _svc().save_presets(base_dir, obj)


def user_presets_json(base_dir):
    """给设置面板的编辑器看：用户覆盖文件的原始内容（没有就返回空对象）。"""
    return _svc().user_presets_json(base_dir)


def list_presets(presets=None):
    """预设列表（前端下拉用）。presets 传 load_presets() 的结果即可带上用户预设。"""
    return _svc().list_presets(presets)


# ---------------------------------------------------------------- 生图
def generate(prompt, preset="anime", size="1024x1024", api_key="",
             base_url="https://api.siliconflow.cn/v1", model="black-forest-labs/FLUX.1-schnell",
             negative_prompt="", extra="", seed=None, presets=None, backend="auto", timeout=None):
    """生图。返回 (ok, 数据, 消息)。数据：{"b64"|"url", "mime", "preset", "seed"}。

    预设自动拼 prompt 前缀；extra 追加在内容之后（风格词放这里，别塞进内容里）。
    backend='auto' 时按端点自动认后端；timeout 留空用各后端默认（本地显卡慢就调大）。
    """
    return _svc().generate(prompt, preset=preset, size=size, api_key=api_key,
                           base_url=base_url, model=model,
                           negative_prompt=negative_prompt, extra=extra, seed=seed,
                           presets=presets, backend=backend, timeout=timeout)


def quick_test():
    """给设置面板/自检看的一句话提示"""
    return _svc().quick_test()


# ---------------------------------------------------------------- 数据常量
def __getattr__(name):
    """`image_gen.PRESETS` / `.BACKENDS` / `.PRESETS_FILE` 转发到块里那一份（唯一真相在块）。

    只转发这三个数据名：别的名字一律 AttributeError ——
    门面不许变成"什么都能取到"的万能对象（那样接口就不可查了）。
    """
    if name in ("PRESETS", "BACKENDS", "PRESETS_FILE"):
        return getattr(_svc(), name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
