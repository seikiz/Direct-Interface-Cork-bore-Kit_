# -*- coding: utf-8 -*-
# ===============================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌===============================================
#   voice_engine.py - 语音引擎的**壳层门面**（能力已搬进 modules/voice/，这里只转调）
#
#   为什么这个文件还在：ARCHITECTURE.md 七「门面（facade）= 迁移期保留的旧接口，内部转调新
#   模块 —— 让调用点不用改」。`VoiceEngine` / `UtauEngine` / `HanasuEngine` /
#   `VoiceEngineError` / `detect_jp_conflicts` / `_analyze_tone` 这些名字一个都不许少。
#
#   唯一真相在哪：两个引擎与语气规则 → modules/voice/engines.py；
#                 挑引擎/独占锁/环境体检 → modules/voice/service.py；
#                 对外的接口表 → modules/voice/block.json 的 interface.methods。
#
#   搬走以后**去掉了三处宿主依赖**（都是块搬去别的项目会当场 ModuleNotFoundError 的东西）：
#     ① 解释器 / 声库 / 合成脚本的路径：改为 bind(host) 注入，本文件就是那个 host；
#     ② `import putao`（第三方合成引擎）：改成宿主回调 `synth`，块里只依赖 stdlib；
#     ③ `_safe_stdout()` 这种"改全局 stdout"的加固：属于宿主，留在本文件、不进块。
# ==============================================================================================

import os
import sys

# ---------------------------------------------------------------- 宿主能力（块只认这几个名字）
base_dir = os.path.dirname(os.path.abspath(__file__))
utau_python = os.path.join("utau_env", "Scripts", "python.exe")
voicebank = os.path.join("utau_voicebanks", "默认声库")
utau_speak = os.path.join(base_dir, "utau_speak.py")
voicevox_url = "http://127.0.0.1:50021"


def _safe_stdout():
    """日语系统下 stdout 可能是 cp932，日文路径/文本 print 会崩 → 强制 UTF-8"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_safe_stdout()  # 模块加载即加固（含独立子进程场景）


def synth_ready():
    """进程内合成可用吗（打包态 putao 已内嵌；开发态没有就回落 utau_env 子进程）"""
    import importlib
    try:
        importlib.import_module("putao")        # 宿主侧允许 import 第三方引擎；块里不许
        return True
    except Exception:
        return False


def synth(text, out_path, voicebank_dir, pitch, duration, pitch_mode):
    """进程内合成：复用 utau_speak.py 的合成逻辑（import 它的函数，避免重复实现）。

    **这是宿主能力**，由 `bind(host)` 注入给块（ARCHITECTURE.md 十二：块只依赖 stdlib）。
    没有 putao 的机器上这里会 ImportError，块捕获后回落 utau_env 子进程 —— 与搬家前一致。
    """
    import importlib
    import importlib.util
    importlib.import_module("putao")            # 打包态内嵌；开发态没有就抛
    spec = importlib.util.spec_from_file_location("utau_speak", utau_speak)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 模拟子进程参数调用核心合成
    mod._run_synthesis(voicebank_dir, str(pitch), str(duration), text, out_path, pitch_mode)
    return out_path


# ---------------------------------------------------------------- 拿块（只装这一块的迷你内核）
_SERVICE = None


def _svc():
    """懒取本块的服务（进程内只建一次；失败时把原因原样抛出来）。"""
    global _SERVICE
    if _SERVICE is None:
        import kernel
        mini = kernel.boot(load=False, echo=False)     # 只发现模块，不装别的块
        _SERVICE = mini.service("voice").bind(_host())
    return _SERVICE


def _host():
    """宿主 = 本门面模块（块用 getattr(host, 名字) 在用时才取，换掉也能生效）。"""
    return sys.modules[__name__]


# ---------------------------------------------------------------- 搬家前的模块级函数
def detect_jp_conflicts():
    """检测与日语系统/日语环境可能冲突的点，返回 {key: (ok, 说明)}。
    用于设置页/启动时提示：日语区域、控制台编码、IME、VOICEVOX 状态等。
    """
    return _svc().detect_conflicts()


def _analyze_tone(text):
    """文本语气分析（与 utau_speak 同规则，供 HANASU 用）"""
    return _svc().analyze_tone(text)


# ---------------------------------------------------------------- 搬家前的统一入口
class VoiceEngine(object):
    """统一入口：按引擎名分发。engine="utau"|"hanasu"|"auto"（auto：HANASU 优先，未就绪回落 UTAU）

    门面版只保留构造签名与 `synthesize`：真正的分发、独占锁、缓存命名都在块里。
    """

    def __init__(self, engine="auto", utau=None, hanasu=None):
        self.engine = engine
        self.service = _svc().bind(_host(), utau=utau, hanasu=hanasu)
        self.service.engine = engine or "auto"

    @property
    def utau(self):
        return self.service.utau

    @property
    def hanasu(self):
        return self.service.hanasu

    def synthesize(self, text, cache_dir, pitch_mode="auto"):
        return self.service.synthesize(text, cache_dir, pitch_mode)


# ---------------------------------------------------------------- 两个引擎类（转发到块里那一份）
def __getattr__(name):
    """`voice_engine.UtauEngine` / `.HanasuEngine` / `.VoiceEngineError` 转发到块里那一份。

    只转发这三个名字：别的名字一律 AttributeError ——
    门面不许变成"什么都能取到"的万能对象（那样接口就不可查了）。
    """
    if name in ("UtauEngine", "HanasuEngine", "VoiceEngineError"):
        return getattr(_svc(), name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
