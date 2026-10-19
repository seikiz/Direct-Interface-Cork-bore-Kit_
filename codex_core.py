# -*- coding: utf-8 -*-
# ===============================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌===============================================
#   codex_core.py - CODEX 专属 GALGAME 引擎的**壳层门面**（能力已搬进 modules/codex/，这里只转调）
#
#   CODEX（COMmon eXperience format）v1.0，授权 MIT —— 格式与参考实现均开放，
#   任何前端/工具都可实现与嵌入。傻瓜化资源导入（立绘/音乐/声音/剧情）→ 剧本 codex.json
#   → 全屏播放器（背景 + 立绘 + 打字机文本 + 选项分支 + BGM/配音）→ 一键打包独立 HTML / EXE。
#
#   为什么这个文件还在：主程序有 50 处 `codex_core.xxx(...)`（api_codex_* 一整套），
#   tests/test_codex*.py 五个脚本也按这个名字调用。ARCHITECTURE.md 七「门面（facade）=
#   迁移期保留的旧接口，内部转调新模块 —— 让调用点不用改」。所以这里一个函数名都不许少。
#
#   唯一真相在哪：modules/codex/ 的九个文件（constants / scene / rules / flow / analyze /
#   pack / player_js / player / exe / service）—— 那份 2030 行的实现按 400 行预算拆开搬过去了。
#   本文件**不含任何实现**：改格式要改块，改这里等于又造了第二份真相。
#
#   怎么拿到块：块由内核装载，壳层只能 `kernel.service("codex")` 拿服务（铁律 2）。
#   这里用一个「只装这一块的迷你内核」（load=False：不装别的模块），第一次调用时才建。
#
#   宿主能力怎么注入：`bind(host)` 的 host 就是**本模块自己**。块会向它要两样东西：
#       host.mark      → 水印模块（生产环境 = 仓库根 `dick_mark`，见下面的 __getattr__）
#       host.codex_dir → 包根目录（本门面不提供：主程序一直按次传路径，块照旧按次用）
#
#   格式版本常量留在本文件里（它在原实现里只出现在定义处、没写进包也没校验；
#   tests/test_compat_surface.py 专门钉住了"全仓只出现一次"这个现状，别把它搬走也别加引用）。
# ==============================================================================================

import sys

CODEX_FORMAT = "codex/1.0"

_SERVICE = None


def _svc():
    """懒取本块的服务（进程内只建一次；失败时把原因原样抛出来）。"""
    global _SERVICE
    if _SERVICE is None:
        import kernel
        mini = kernel.boot(load=False, echo=False)     # 只发现模块，不装别的块
        _SERVICE = mini.service("codex").bind(_host())
    return _SERVICE


def _host():
    """宿主 = 本门面模块（块用 getattr(host, 名字) 在用时才取）。"""
    return sys.modules[__name__]


# ---------------------------------------------------------------- 剧本语法
def classify_file(name):
    """按文件名猜资源类别（sprites/bg/bgm/voice）；无法识别返回 None"""
    return _svc().classify_file(name)


def parse_script_text(text, name="我的故事"):
    """把纯文本剧本解析成 codex.json 对象（傻瓜化：粘贴文本 → 可播剧本）。解析失败返回 None。"""
    return _svc().parse_script_text(text, name)


def normalize_script(data, pkg_dir=None):
    """把剧本补全成可播的形状（补 codex 版本、场景 id、资源路径）"""
    return _svc().normalize_script(data, pkg_dir)


def sanitize_html(html):
    """基础 HTML 注入防护（去 script/iframe/事件属性，中立化 javascript:）"""
    return _svc().sanitize_html(html)


def validate_codex(data):
    """校验剧本 dict。返回 (ok, issues)"""
    return _svc().validate_codex(data)


def step_kind(ln):
    """这一行属于哪种步骤（say/note/show/hide/bg/bgm/sfx/effect/choice/jump/end/action…）"""
    return _svc().step_kind(ln)


# ---------------------------------------------------------------- 条件 / 选项 / 推进
def evaluate_condition(state, cond):
    """条件求值（{"aff": ">=85"} / all / any / flags / status；无状态=作者预览恒真）"""
    return _svc().evaluate_condition(state, cond)


def filter_choices(items, state):
    """过滤选项：丢弃 if 条件不满足的项（作者预览：无运行时状态时不丢弃）"""
    return _svc().filter_choices(items, state)


def cond_pass(cond, state):
    """播放器侧的条件判定（与作者侧同一套规则）"""
    return _svc().cond_pass(cond, state)


def simulate(data, state=None, max_states=20000, roll_values=None):
    """穷举所有可达状态：有几个结局、有没有死路（带上限，不会跑飞）"""
    return _svc().simulate(data, state, max_states, roll_values)


def run_path(data, picks, state=None, max_steps=1000, roll_values=None):
    """按给定选择序列跑一条路径。返回 {"ok","steps":[...],"ending","flags","stopped"}"""
    return _svc().run_path(data, picks, state, max_steps, roll_values)


# ---------------------------------------------------------------- 静态分析
def analyze_codex(data, pkg_dir=None):
    """剧本静态分析：可达性 / 资源引用 / 死分支。返回 {"ok","issues","warnings","stats",…}"""
    return _svc().analyze_codex(data, pkg_dir)


# ---------------------------------------------------------------- 包的目录与 zip
def make_template(name="我的故事"):
    """生成一个开箱即用的示例剧本（可直接播放，验证播放器）"""
    return _svc().make_template(name)


def import_folder(src_dir, dest_root, name):
    """把一个素材文件夹按类型摊进 sprites/bg/bgm/voice 并生成 codex.json"""
    return _svc().import_folder(src_dir, dest_root, name)


def make_sample_package(dest_root, name="示例·夏日祭"):
    """造一个带占位素材的示例包（零素材也能立刻跑起来）"""
    return _svc().make_sample_package(dest_root, name)


def export_zip(pkg_dir, zip_path):
    """把 CODEX 包打成 zip（含 codex.json 与全部资源）"""
    return _svc().export_zip(pkg_dir, zip_path)


def import_zip(zip_path, dest_root):
    """从 zip 还原一个 CODEX 包到 dest_root。返回 (ok, 包名, 消息)"""
    return _svc().import_zip(zip_path, dest_root)


def _safe_name(name):
    """包名净化（去路径分隔符/危险字符，防目录穿越）"""
    return _svc().safe_name(name)


# ---------------------------------------------------------------- 播放器 / 导出
def _load_custom_template(pkg_dir):
    """读包内 player.html（高级自定义模板）；无则返回 None（用系统默认）。"""
    return _svc().load_custom_template(pkg_dir)


def build_standalone_html(pkg_dir, embed_script=True):
    """把包打成"资源全 base64 内嵌"的数据块（返回 (数据字符串, 资源统计)）"""
    return _svc().build_standalone_html(pkg_dir, embed_script)


def build_standalone_file(pkg_dir, out_path=None):
    """生成独立单文件 HTML（打包 GALGAME）。返回 (成功?, 输出路径, 资源统计)"""
    return _svc().build_standalone_file(pkg_dir, out_path)


def render_standalone(pkg_dir, template_html=None, state=None):
    """根据播放器模板渲染包为独立 HTML 字符串（现场试玩 / 打包共用）。返回 (html, counts)"""
    return _svc().render_standalone(pkg_dir, template_html, state)


def build_exe_shell(html, title="CODEX GALGAME"):
    """生成 pywebview 播放器壳脚本（内嵌 base64 HTML）"""
    return _svc().build_exe_shell(html, title)


def pyinstaller_cmd(shell_path, out_dir, name):
    """构造 PyInstaller 命令：单文件无控制台 EXE。返回 (cmd 列表, 说明)"""
    return _svc().pyinstaller_cmd(shell_path, out_dir, name)


def build_standalone_exe(pkg_dir, out_dir, name=None, py_cmd=None, log_cb=None):
    """完整打包 EXE：生成 HTML → 写壳脚本 → 调 PyInstaller → 返回 (exe 路径, counts)"""
    return _svc().build_standalone_exe(pkg_dir, out_dir, name, py_cmd, log_cb)


# ---------------------------------------------------------------- 数据常量 / 宿主能力
def __getattr__(name):
    """转发三类东西，别的名字一律 AttributeError（门面不许变成万能对象）。

    · `mark`            —— 宿主能力：水印模块（生产环境 = 仓库根 `dick_mark`），
                           块靠 `bind(host)` 取它，所以这里必须回**模块对象**而不是函数；
    · `SUBDIRS` / `DEFAULT_EDITABLE_TEMPLATE` / `STANDALONE_PLAYER_JS` /
      `EXE_SHELL_TEMPLATE` / `CODEX_VERSION` —— 数据常量，唯一真相在块里。
    """
    if name == "mark":
        import dick_mark
        return dick_mark
    if name in ("SUBDIRS", "DEFAULT_EDITABLE_TEMPLATE", "STANDALONE_PLAYER_JS",
                "EXE_SHELL_TEMPLATE", "CODEX_VERSION"):
        return getattr(_svc(), name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
