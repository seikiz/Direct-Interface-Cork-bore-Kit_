# -*- coding: utf-8 -*-
"""modules/codex/service.py —— CODEX 服务（模块内部实现，外部不许 import）

壳层拿到的是这一个对象：`kernel.service("codex")`，再 `bind(host)` 把宿主接进来。
方法的实现全在内部模块里，这里只做三件事：**转发**、**注入 mark**、**给缺省 codex_dir**。

接口分五组（block.json 的 interface.methods 就是这张表）：
    宿主注入    bind / pack_dir / list_packages
    剧本语法    classify_file / parse_script_text / normalize_script / sanitize_html /
                validate_codex / step_kind
    条件与推进  evaluate_condition / filter_choices / cond_pass / simulate / run_path
    静态分析    analyze_codex
    包与导出    make_template / import_folder / make_sample_package / export_zip /
                import_zip / build_standalone_html / build_standalone_file /
                render_standalone / build_exe_shell / pyinstaller_cmd / build_standalone_exe

`bind(host)` 认的宿主属性（全可缺省）：
    codex_dir   CODEX 包的根目录（只在 pack_dir / list_packages 用；别的方法仍然按调用方
                传进来的路径干活 —— 与搬家前逐字一致，没有一处改成"猜目录"）
    mark        水印模块（生产环境 = 仓库根 `dick_mark`），提供 mark_dict() / SIGNATURE /
                MARK_JS；没给就跳过水印（与原来 try/except 的降级一致）
    log         有 info/warn/error 的日志对象
    progress    进度回调 (stage, **kw)；打包 EXE 时能听到"壳脚本已生成"这类事件

**这一层不 import 宿主**：搬家前的 `import dick_mark` 是块唯一"长在宿主身上"的地方，
现在改成注入（ARCHITECTURE.md 十二：宿主能力一律 bind(host)）。
"""

import os

from . import analyze as analyze_mod
from . import constants as constants_mod
from . import exe as exe_mod
from . import flow as flow_mod
from . import pack as pack_mod
from . import player as player_mod
from . import rules as rules_mod
from . import scene as scene_mod


class CodexService(object):
    """CODEX 包的解析 / 校验 / 分析 / 试玩 / 导出。方法都不弹对话框、不写用户目录。"""

    def __init__(self, log=None):
        self.log = log
        self.host = None
        self.codex_dir = ""
        self.mark = None
        self.last_error = ""

    # ----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------ 宿主注入
    def bind(self, host):
        """把宿主接进来（幂等：壳层每次取服务都调一次也没关系）。"""
        self.host = host
        self.codex_dir = str(getattr(host, "codex_dir", "") or "")
        self.mark = getattr(host, "mark", None)
        self.log = getattr(host, "log", None) or self.log
        return self

    def _progress(self, stage, **kw):
        fn = getattr(self.host, "progress", None)
        if callable(fn):
            try:
                fn(stage, **kw)
            except Exception:
                pass

    # ---- 包目录（只有这里用 codex_dir；别的方法仍按调用方给的路径干活）----
    def pack_dir(self, name):
        """`<codex_dir>/<净化后的包名>`（没绑 codex_dir 时当场说清楚，不猜目录）"""
        if not self.codex_dir:
            raise RuntimeError("CODEX 模块还没绑定包目录（壳层没调 bind(host) 或宿主没有 codex_dir）")
        return os.path.join(self.codex_dir, pack_mod._safe_name(name))

    def list_packages(self):
        """列出 codex_dir 下所有包（有 codex.json 的目录），按名字排序"""
        if not self.codex_dir or not os.path.isdir(self.codex_dir):
            return []
        out = []
        for fn in sorted(os.listdir(self.codex_dir)):
            d = os.path.join(self.codex_dir, fn)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "codex.json")):
                out.append(fn)
        return out

    # ---------------------------------------------------------------- 剧本语法
    def classify_file(self, name):
        return constants_mod.classify_file(name)

    def parse_script_text(self, text, name="我的故事"):
        return scene_mod.parse_script_text(text, name)

    def normalize_script(self, data, pkg_dir=None):
        return scene_mod.normalize_script(data, pkg_dir)

    def sanitize_html(self, html):
        return rules_mod.sanitize_html(html)

    def validate_codex(self, data):
        return rules_mod.validate_codex(data)

    def step_kind(self, ln):
        return rules_mod.step_kind(ln)

    # ---------------------------------------------------------------- 条件与推进
    def evaluate_condition(self, state, cond):
        return rules_mod.evaluate_condition(state, cond)

    def filter_choices(self, items, state):
        return rules_mod.filter_choices(items, state)

    def cond_pass(self, cond, state):
        return flow_mod.cond_pass(cond, state)

    def simulate(self, data, state=None, max_states=20000, roll_values=None):
        return flow_mod.simulate(data, state, max_states, roll_values)

    def run_path(self, data, picks, state=None, max_steps=1000, roll_values=None):
        return flow_mod.run_path(data, picks, state, max_steps, roll_values)

    # ---------------------------------------------------------------- 静态分析
    def analyze_codex(self, data, pkg_dir=None):
        return analyze_mod.analyze_codex(data, pkg_dir)

    # ---------------------------------------------------------------- 包
    def make_template(self, name="我的故事"):
        return pack_mod.make_template(name)

    def import_folder(self, src_dir, dest_root, name):
        return pack_mod.import_folder(src_dir, dest_root, name)

    def make_sample_package(self, dest_root, name="示例·夏日祭"):
        return pack_mod.make_sample_package(dest_root, name)

    def export_zip(self, pkg_dir, zip_path):
        return pack_mod.export_zip(pkg_dir, zip_path)

    def import_zip(self, zip_path, dest_root):
        return pack_mod.import_zip(zip_path, dest_root)

    def safe_name(self, name):
        return pack_mod._safe_name(name)

    # ---------------------------------------------------------------- 播放器 / 导出
    def load_custom_template(self, pkg_dir):
        return player_mod._load_custom_template(pkg_dir)

    def build_standalone_html(self, pkg_dir, embed_script=True):
        return player_mod.build_standalone_html(pkg_dir, embed_script, mark=self.mark)

    def build_standalone_file(self, pkg_dir, out_path=None):
        return player_mod.build_standalone_file(pkg_dir, out_path, mark=self.mark)

    def render_standalone(self, pkg_dir, template_html=None, state=None):
        return player_mod.render_standalone(pkg_dir, template_html, state, mark=self.mark)

    def build_exe_shell(self, html, title="CODEX GALGAME"):
        return exe_mod.build_exe_shell(html, title)

    def pyinstaller_cmd(self, shell_path, out_dir, name):
        return exe_mod.pyinstaller_cmd(shell_path, out_dir, name)

    def build_standalone_exe(self, pkg_dir, out_dir, name=None, py_cmd=None, log_cb=None):
        self._progress("exe.start", pkg_dir=pkg_dir, out_dir=out_dir)
        return exe_mod.build_standalone_exe(pkg_dir, out_dir, name, py_cmd, log_cb,
                                            mark=self.mark)

    # ---------------------------------------------------------------- 数据常量
    @property
    def SUBDIRS(self):
        return constants_mod.SUBDIRS

    @property
    def CODEX_VERSION(self):
        return constants_mod.CODEX_VERSION

    @property
    def DEFAULT_EDITABLE_TEMPLATE(self):
        return player_mod.DEFAULT_EDITABLE_TEMPLATE

    @property
    def STANDALONE_PLAYER_JS(self):
        return player_mod.STANDALONE_PLAYER_JS

    @property
    def EXE_SHELL_TEMPLATE(self):
        return exe_mod.EXE_SHELL_TEMPLATE
