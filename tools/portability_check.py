# -*- coding: utf-8 -*-
"""portability_check.py —— 搬家测试：块必须能原封不动搬去别的项目

判断标准：`ARCHITECTURE.md` 十二（块的可移植性）。它查两类东西，缺一不可：

  A. **静态扫描**（不看运行，只看块里写了什么）
     ① `abs-path`  绝对路径：`C:\\…` / `/home/…` / `/opt/…` 这类只有某台机器才成立的字面量；
     ② `site-ip`   站点 IP：公网/私网 IPv4 字面量（版本号 `1.2.3.4` 不误报）；
     ③ `sys-path`  块自己改 `sys.path` = 隐式依赖宿主的目录结构；
     ④ `host-read` 读宿主：`app_paths` 引用、`open()` 里出现宿主 `config.json`；
     ⑤ `undeclared-import` / `unused-pip`  第三方库：import 了没声明是违规，
        声明了却没人 import 同样是假话（两个方向都查）。

  B. **搬家测试**（真的搬一次，再跑一遍）
     1) 建临时目录 T（**显式 `dir=`**：本机 `tempfile.gettempdir()` 会退化成当前目录）；
     2) 只把 `kernel/` 与目标块目录复制进 T（别的块、宿主代码一律不带）；
     3) 在 T 里跑该块的 `--selftest`（与 `python -m <包> --selftest` 同一入口）；
     4) 经内核 loader 把块**真的装上**（能加载）；
     5) 断言 `sys.modules` 里没有白名单之外的模块。白名单 = stdlib + kernel + 块自身
        + `requires.pip` 里已声明的第三方库 + 内核装配用的 `_dk_mod_*` 合成包名。
     → `{"block":"workshop","portable":true,"ms":N,"violations":[]}`

用法：
    python tools/portability_check.py                 # 人看：每块一行 JSON + 汇总
    python tools/portability_check.py --json          # 机器可读（accept.py 也调这里的函数）
    python tools/portability_check.py --only workshop
    python tools/portability_check.py --root <另一棵树> # 判定器自检用

出口约定：全部可移植 → 0；任何一块有违规 → 1（并在最后一行说清是哪块、为什么）。
"""

import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import blocks_graph as bg          # noqa: E402  （块的发现规则只有一份，不在这里重写）

MARK = "__PORTABILITY__"
SKIP_DIRS = {"__pycache__", ".git"}
HOST_CONFIG_FILES = ("config.json", "workshop_config.json")

# 模块名 ↔ PyPI 包名<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（只有名字不一样的才要写）
PYPI_TO_MODULE = {
    "pywebview": "webview",
    "pillow": "PIL",
    "python-docx": "docx",
    "pyyaml": "yaml",
    "pycryptodome": "Crypto",
    "beautifulsoup4": "bs4",
    "python-dateutil": "dateutil",
    "python-dotenv": "dotenv",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
}
MODULE_TO_PYPI = {v: k for k, v in PYPI_TO_MODULE.items()}

# 解释器/站点自己塞进来的、与块无关的模块（不属于 stdlib 名单，但也不是块的依赖）
EXTRA_ALLOWED = {"sitecustomize", "usercustomize", "_distutils_hack", "_virtualenv",
                 "pywin32_bootstrap", "apport_python_hook"}

RULE_LABEL = {
    "abs-path": "绝对路径",
    "site-ip": "站点 IP",
    "sys-path": "sys.path 操作",
    "host-read": "读宿主",
    "undeclared-import": "未声明的第三方库",
    "unused-pip": "声明了却没 import 的第三方库",
    "selftest": "自检",
    "load": "加载",
    "host-module": "加载了宿主模块",
    "extra-module": "加载了白名单之外的模块",
    "block-json": "block.json 读不出来",
}

# `C:\` / `C:/`（前面不能是字母数字，否则 `http://` 里的 `p:/` 会误报）
WIN_ABS = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")
# 有明确"根 + 目录"语义的 POSIX 绝对路径（`/tmp` 也算：它在 Windows 上根本不成立）
POSIX_ABS = re.compile(r"(?<![A-Za-z0-9_])/(?:home|opt|tmp|usr|var|etc|root|mnt|Users|srv)/")
IPV4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")

MODULES_STUB = '''# -*- coding: utf-8 -*-
"""搬家测试生成的最小容器：只为让 `python -m modules.<id>` 在临时目录里解析到块。

真实仓库的 modules/__init__.py 不参与块的语义（loader 按目录装配合成包名），
所以搬家测试不复制它，而是生成这份最小替代 —— 否则"只带 kernel + 块"就不是真的。
"""
'''

RUNNER_SRC = r'''# -*- coding: utf-8 -*-
"""搬家测试执行器（由 tools/portability_check.py 生成，随临时目录一起删除）"""
import contextlib
import io
import json
import os
import runpy
import sys
import time

T = os.path.dirname(os.path.abspath(__file__))
BLOCK = "__BLOCK__"
LAYER = "__LAYER__"


def _origin(mod):
    f = getattr(mod, "__file__", None)
    if f:
        return os.path.abspath(f)
    spec = getattr(mod, "__spec__", None)
    o = getattr(spec, "origin", None)
    return "" if o in (None, "built-in", "frozen") else o


def main():
    out = {"block": BLOCK, "loaded": False, "load_state": "", "load_error": "",
           "rc": 0, "selftest_line": "", "selftest_error": "", "extra": []}
    base = set(sys.modules)
    t0 = time.perf_counter()
    # ① 自检：必须与 `python -m <包> --selftest` 走同一个入口
    buf = io.StringIO()
    sys.argv = ["-m", "--selftest"]
    target = BLOCK if LAYER == "kernel" else "modules." + BLOCK
    try:
        with contextlib.redirect_stdout(buf):
            runpy.run_module(target, run_name="__main__")
    except SystemExit as e:
        try:
            out["rc"] = int(e.code or 0)
        except Exception:
            out["rc"] = 1
    except Exception as e:
        out["rc"] = 99
        out["selftest_error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    for ln in buf.getvalue().splitlines():
        if ln.strip().startswith("{"):
            out["selftest_line"] = ln.strip()
    # ② 能加载：模块块必须经内核 loader 真的装上（kernel 块自己就是内核）
    try:
        import kernel as K
        if LAYER == "kernel":
            out["loaded"], out["load_state"] = True, "kernel"
        else:
            k = K.boot(base_dir=os.path.join(T, "_data"),
                       modules_dir=os.path.join(T, "modules"), log=K.Log(echo=False))
            st = k.loader.status_of(BLOCK)
            if st in ("lazy", "discovered"):
                k.service(BLOCK)
                st = k.loader.status_of(BLOCK)
            out["load_state"] = st
            out["loaded"] = (st == "loaded") and not k.failed_modules()
            if not out["loaded"]:
                out["load_error"] = json.dumps(k.failed_modules(), ensure_ascii=False)[:300]
    except Exception as e:
        out["load_error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
    # ③ 搬家后的进程里不许出现"只有宿主才有"的模块
    seen = {}
    for name in sorted(set(sys.modules) - base):
        top = name.split(".")[0]
        if top not in seen:
            seen[top] = _origin(sys.modules.get(name))
    out["extra"] = [{"name": n, "origin": o} for n, o in sorted(seen.items())]
    out["ms"] = int((time.perf_counter() - t0) * 1000)
    print("__MARK__" + json.dumps(out, ensure_ascii=False))


main()
'''.replace("__MARK__", MARK)


# ================================================================ 基础设施
def _read(path):
    with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def _inside(path, base):
    try:
        return os.path.commonpath([os.path.abspath(path),
                                   os.path.abspath(base)]) == os.path.abspath(base)
    except Exception:
        return False


def _v(rule, file, line, detail):
    return {"rule": rule, "file": str(file).replace("\\", "/"), "line": int(line),
            "detail": str(detail)}


def short(v):
    """一条违规的人话描述（accept.py 的 FAIL 行用它）"""
    return "%s（%s:%s %s）" % (RULE_LABEL.get(v["rule"], v["rule"]),
                              v["file"], v["line"], v["detail"])


def _py_files(block_dir):
    if not os.path.isdir(block_dir):
        return []
    return [os.path.join(block_dir, f) for f in sorted(os.listdir(block_dir))
            if f.endswith(".py") and os.path.isfile(os.path.join(block_dir, f))]


def declared_pip(block_json):
    """block.json 的 requires.pip（唯一事实来源；没有就当空表）"""
    req = (block_json or {}).get("requires") or {}
    pip = req.get("pip") if isinstance(req, dict) else None
    if isinstance(pip, str):
        pip = [pip]
    out = []
    for item in pip or []:
        name = str(item or "").strip()
        if name:
            out.append(name)
    return out


def _module_of(pypi):
    key = str(pypi or "").strip().lower()
    return PYPI_TO_MODULE.get(key, key.replace("-", "_"))


def _stdlib():
    return set(getattr(sys, "stdlib_module_names", ()) or ())


# ================================================================ A. 静态扫描
def _literal_problems(text):
    """一条字符串字面量里的可移植性问题（路径 / 站点 IP）"""
    out = []
    m = WIN_ABS.search(text)
    if m:
        out.append(("abs-path", "Windows 绝对路径 %r" % text[max(0, m.start() - 8):
                                                              m.start() + 48]))
    m = POSIX_ABS.search(text)
    if m:
        out.append(("abs-path", "POSIX 绝对路径 %r" % text[max(0, m.start() - 8):
                                                          m.start() + 48]))
    for m in IPV4.finditer(text):
        octets = [int(x) for x in m.groups()]
        if any(o > 255 for o in octets):
            continue
        if octets[0] in (0, 127) or octets[0] >= 224:
            continue                      # 通配 / 环回 / 组播广播：不是"站点"
        if octets == [255, 255, 255, 255]:
            continue
        ctx = text[max(0, m.start() - 8):m.start()]
        private = (octets[0] == 10 or (octets[0] == 192 and octets[1] == 168)
                   or (octets[0] == 172 and 16 <= octets[1] <= 31))
        # 判据：像 IP 而不是版本号（1.2.3.4 全是小数字且无 URL/端口上下文）
        if private or any(o > 99 for o in octets) or "://" in ctx \
                or text[m.end():m.end() + 1] == ":":
            out.append(("site-ip", "站点 IP %r" % m.group(0)))
    return out


def _call_args_literals(node):
    out = []
    for arg in list(node.args) + [k.value for k in node.keywords or []]:
        for sub in ast.walk(arg):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append(sub.value)
    return out


def _local_names(block_json):
    """块自己的文件（不含扩展名）—— 它们不是第三方库"""
    names = set()
    for item in (block_json or {}).get("files") or []:
        base = os.path.basename(str(item))
        if base.endswith(".py"):
            names.add(base[:-3])
    return names


def scan_static(block_dir, block_json, root=ROOT):
    """块的静态可移植性扫描。返回违规列表（每条形如 {"rule","file","line","detail"}）。"""
    out = []
    pip = declared_pip(block_json)
    pip_modules = {_module_of(p) for p in pip}
    local = _local_names(block_json)
    stdlib = _stdlib()
    used = set()

    for path in _py_files(block_dir):
        rel = _rel(path, root)
        try:
            tree = ast.parse(_read(path))
        except SyntaxError as e:
            out.append(_v("selftest", rel, 0, "语法错误，块根本加载不了：%s" % str(e)[:120]))
            continue
        for node in ast.walk(tree):
            # ---- ③ 第三方库：import 了就必须声明 ----
            names = []
            if isinstance(node, ast.Import):
                names = [(a.name, a.name.split(".")[0]) for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                top = (node.module or "").split(".")[0]
                names = [(node.module or "", top)] if top else []
            for full, top in names:
                if top in ("kernel", "modules") or top in local or top in pip_modules:
                    continue
                if top == "app_paths":
                    out.append(_v("host-read", rel, node.lineno,
                                  "import 了宿主路径工具 app_paths（路径要 bind(host) 注入）"))
                    continue
                if top in stdlib:
                    continue
                out.append(_v("undeclared-import", rel, node.lineno,
                              "import %r 没在 block.json 的 requires.pip 里声明" % full))
            for _full, top in names:
                if top:
                    used.add(top)

        for node in ast.walk(tree):
            # ---- ① / ② 绝对路径与站点 IP ----
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for rule, detail in _literal_problems(node.value):
                    out.append(_v(rule, rel, node.lineno, detail))
            # ---- ④ sys.path 操作 ----
            if isinstance(node, ast.Attribute) and node.attr == "path" \
                    and isinstance(node.value, ast.Name) and node.value.id == "sys":
                out.append(_v("sys-path", rel, getattr(node, "lineno", 0),
                              "块里碰了 sys.path（不许靠改 import 路径找宿主）"))
            # ---- ④ 读宿主：app_paths / open(宿主 config.json) ----
            if isinstance(node, ast.Name) and node.id == "app_paths":
                out.append(_v("host-read", rel, getattr(node, "lineno", 0),
                              "读宿主路径工具 app_paths（路径要 bind(host) 注入）"))
            if isinstance(node, ast.Call):
                fname = ""
                if isinstance(node.func, ast.Name):
                    fname = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    fname = node.func.attr
                if fname in ("open", "exists", "isfile", "isdir", "read_text", "load", "Path"):
                    for lit in _call_args_literals(node):
                        if os.path.basename(lit) in HOST_CONFIG_FILES:
                            out.append(_v("host-read", rel, node.lineno,
                                          "读了宿主配置 %r（宿主能力要 bind(host) 注入）" % lit))
                            break

    # ---- ⑤ 反向：声明了却没人 import 的第三方库 ----
    for p in pip:
        mod = _module_of(p)
        if mod not in used and p.replace("-", "_") not in used:
            out.append(_v("unused-pip", _rel(block_dir, root), 0,
                          "requires.pip 声明了 %r，但块里没有任何 import 用到它（声明是假话）"
                          % p))
    # 去重（同一个字面量里重复命中同一条规则）
    seen, uniq = set(), []
    for v in out:
        key = (v["rule"], v["file"], v["line"], v["detail"])
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    return uniq


# ================================================================ B. 搬家测试
_TEMP_BASE_CACHE = {}
FALLBACK_DIRNAME = "tmp_portability"

_PROBE_CODE = (
    "import os, sys, tempfile\n"
    "base = sys.argv[1]\n"
    "os.makedirs(base, exist_ok=True)\n"
    "d = tempfile.mkdtemp(prefix='dick_probe_', dir=base)\n"
    "os.rmdir(d)\n"
)


def _probe_temp_dir(base, timeout=3):
    """这个目录**真的**能建子目录吗？

    必须在子进程里探：本机 %TEMP% 偶发 `WinError 5`，偶发卡住几分钟
    （Windows 安全软件/筛选驱动）。在进程内探会把整个验收挂死，
    子进程 + 超时才能保证"判定器自己不会死在这儿"。

    两个细节都是为了**不留下孤儿进程**：
      · 用 `sys._base_executable`（venv 的启动器只是个转发壳，杀它不会杀到真正
        干活的那个解释器）；
      · stdout/stderr 走 DEVNULL（没有管道要等，超时杀得干净）。
    """
    exe = getattr(sys, "_base_executable", None) or sys.executable
    try:
        p = subprocess.run([exe, "-c", _PROBE_CODE, base],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def _temp_base(root):
    """一个**真的能写**的临时根目录（显式传给 tempfile，不靠 gettempdir 的猜测）

    顺序：%TEMP% → %TMP% → 工作区兜底目录。本机 %TEMP% 会偶发不可写/卡住，
    探不通就退到工作区（跑完删干净）—— 与块自检里的 `_tmpdir()` 同一约定。
    """
    key = os.path.abspath(root)
    if key in _TEMP_BASE_CACHE:
        return _TEMP_BASE_CACHE[key]
    fallback = os.path.join(root, FALLBACK_DIRNAME)
    seen, candidates = set(), []
    for base in (os.environ.get("TEMP"), os.environ.get("TMP"), fallback):
        if not base:
            continue
        abspath = os.path.abspath(base)
        if abspath in seen:            # Windows 上 TEMP/TMP 常常是同一个
            continue
        seen.add(abspath)
        candidates.append(base)
    for base in candidates:
        if not _probe_temp_dir(base):
            continue
        _TEMP_BASE_CACHE[key] = base
        return base
    raise RuntimeError("没有可写的临时目录（%%TEMP%% 与工作区都建不出目录）")


def _copy_tree(src, dst):
    """只搬源码：不带 __pycache__ / .pyc（否则"搬家"搬的是宿主编译产物）"""
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith("tmp")]
        rel = os.path.relpath(dirpath, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for name in sorted(filenames):
            if name.endswith((".pyc", ".pyo")):
                continue
            shutil.copy2(os.path.join(dirpath, name), os.path.join(target, name))


def _selftest_spec(block_json):
    """block.json 里声明的自检命令与耗时预算（只读，不执行 cmd —— 执行走 runpy）"""
    spec = (block_json or {}).get("selftest") or {}
    return {"cmd": list(spec.get("cmd") or []),
            "max_ms": int(spec.get("max_ms") or 2000)}


def move_test(block_id, block_dir, block_json, layer="module", root=ROOT):
    """真的搬一次：T = kernel/ + 该块目录，然后在 T 里加载 + 自检 + 查 sys.modules。"""
    violations = []
    spec = _selftest_spec(block_json)
    base = _temp_base(root)
    os.makedirs(base, exist_ok=True)      # 兜底目录可能被上一轮扫干净了
    T = tempfile.mkdtemp(prefix="dick_move_%s_" % block_id, dir=base)
    data = None
    try:
        _copy_tree(os.path.join(root, "kernel"), os.path.join(T, "kernel"))
        if layer != "kernel":
            _copy_tree(block_dir, os.path.join(T, "modules", block_id))
            _write(os.path.join(T, "modules", "__init__.py"), MODULES_STUB)
        runner = os.path.join(T, "_portability_runner.py")
        _write(runner, RUNNER_SRC.replace("__BLOCK__", block_id).replace("__LAYER__", layer))
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONSTARTUP")}
        env.update({"PYTHONPATH": "", "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1"})
        tmp = os.path.join(T, "_tmp")      # 块自己的临时文件也落在 T 里，跑完一起删
        os.makedirs(tmp, exist_ok=True)
        env.update({"TEMP": tmp, "TMP": tmp, "TMPDIR": tmp})
        try:
            p = subprocess.run([sys.executable, runner], cwd=T, env=env,
                               capture_output=True, timeout=180)
        except Exception as e:
            violations.append(_v("selftest", _rel(block_dir, root), 0,
                                 "搬家后自检跑不起来：%s" % str(e)[:160]))
            return {"violations": violations, "selftest": None, "loaded": False,
                    "extra": [], "ms": 0, "tmp": T}
        out = p.stdout.decode("utf-8", "replace")
        txt = out + p.stderr.decode("utf-8", "replace")
        for line in out.splitlines():
            if line.startswith(MARK):
                try:
                    data = json.loads(line[len(MARK):])
                except Exception as e:
                    err = "执行器结果不是合法 JSON：%s" % str(e)[:120]
        if data is None:
            tail = [ln for ln in txt.strip().splitlines() if ln.strip()][-1:]
            violations.append(_v("selftest", _rel(block_dir, root), 0,
                                 "搬家后自检没有结果（rc=%d）：%s"
                                 % (p.returncode, tail[0][:220] if tail else "")))
            return {"violations": violations, "selftest": None, "loaded": False,
                    "extra": [], "ms": 0, "tmp": T}

        # ---- ① 自检通过？ ----
        selftest, line = None, data.get("selftest_line") or ""
        if not line:
            violations.append(_v("selftest", _rel(block_dir, root), 0,
                                 "自检没有输出 JSON（rc=%s，%s）"
                                 % (data.get("rc"), (data.get("selftest_error") or "")[:200])))
        else:
            try:
                selftest = json.loads(line)
            except Exception as e:
                violations.append(_v("selftest", _rel(block_dir, root), 0,
                                     "自检输出不是合法 JSON：%s" % str(e)[:120]))
        if selftest is not None:
            if selftest.get("block") != block_id:
                violations.append(_v("selftest", _rel(block_dir, root), 0,
                                     "自检报的块名对不上：%r" % selftest.get("block")))
            if int(selftest.get("fail") or 0) or data.get("rc"):
                violations.append(_v("selftest", _rel(block_dir, root), 0,
                                     "搬家后自检没通过（fail=%s rc=%s）"
                                     % (selftest.get("fail"), data.get("rc"))))
            elif int(selftest.get("ms") or 0) > spec["max_ms"]:
                violations.append(_v("selftest", _rel(block_dir, root), 0,
                                     "搬家后自检耗时 %sms 超过预算 %sms"
                                     % (selftest.get("ms"), spec["max_ms"])))
        # ---- ② 能加载？ ----
        if not data.get("loaded"):
            violations.append(_v("load", _rel(block_dir, root), 0,
                                 "搬到干净目录后装不上（状态 %r）：%s"
                                 % (data.get("load_state"),
                                    (data.get("load_error") or "")[:240])))
        # ---- ③ sys.modules 里不许有宿主专有模块 ----
        extra_bad, declared_loaded = _extra_problems(data.get("extra") or [], block_id,
                                                    block_json, block_dir, T, root)
        violations += extra_bad
        ms = int(data.get("ms") or 0)
    finally:
        shutil.rmtree(T, ignore_errors=True)
        if _inside(base, root):        # 工作区兜底目录：空了就删，%TEMP% 绝不动
            try:
                os.rmdir(base)
            except OSError:
                pass
    return {"violations": violations, "selftest": selftest, "loaded": bool(data.get("loaded")),
            "extra": declared_loaded, "ms": ms}


def _extra_problems(extra, block_id, block_json, block_dir, T, root):
    """搬家后进程里多出来的模块：宿主模块 / 未声明第三方库 → 违规

    允许出现：stdlib、kernel、块自身、`requires.pip` 里已声明的第三方库、
    内核装配块用的 `_dk_mod_*` 合成包名。

    未声明的第三方库**汇总成一条**：`import requests` 会顺带把 certifi/urllib3/idna…
    全拖进来，一个一个报只会让 FAIL 行变成噪音（真正的原因只有一个）。
    """
    pip_modules = {_module_of(p) for p in declared_pip(block_json)}
    stdlib = _stdlib()
    where = _rel(block_dir, root)
    host_mods, other_mods, declared_loaded = [], [], []
    for item in extra:
        name = str(item.get("name") or "")
        origin = str(item.get("origin") or "")
        if not name or name in ("kernel", "modules", block_id):
            continue
        if name.startswith("_dk_"):
            continue                    # 内核装配块用的合成包名（kernel 的一部分）
        if name in stdlib or name in EXTRA_ALLOWED:
            continue
        if origin and _inside(origin, T):
            continue                    # 块/kernel 自己带进来的文件
        if name in pip_modules:
            declared_loaded.append(name)     # 已声明的第三方库：允许用
            continue
        if origin and _inside(origin, root):
            host_mods.append((name, origin))
        else:
            other_mods.append(name)
    out = []
    for name, origin in host_mods:
        out.append(_v("host-module", where, 0,
                      "搬家后仍从仓库加载了宿主模块 %r（%s）"
                      % (name, os.path.basename(origin))))
    if other_mods:
        shown = "、".join(sorted(other_mods)[:6])
        more = "" if len(other_mods) <= 6 else " 等 %d 个" % len(other_mods)
        out.append(_v("extra-module", where, 0,
                      "搬家后加载了 %d 个白名单之外的模块：%s%s（要用就写进 requires.pip）"
                      % (len(other_mods), shown, more)))
    return out, sorted(set(declared_loaded))


# ================================================================ 汇总
def check_block(block_id, block_dir, block_json, layer="module", root=ROOT):
    """一个块的完整体检：静态扫描 + 搬家测试"""
    t0 = time.perf_counter()
    static = scan_static(block_dir, block_json, root)
    moved = move_test(block_id, block_dir, block_json, layer, root)
    violations = static + moved["violations"]
    return {"block": block_id,
            "portable": not violations,
            "ms": int((time.perf_counter() - t0) * 1000),
            "violations": violations,
            "static": len(static),
            "move": len(moved["violations"]),
            "loaded": moved["loaded"],
            "selftest": moved["selftest"],
            "declared": declared_pip(block_json)}


def check_all(root=ROOT, only=None):
    """所有块搬家测试：{"blocks":{…}, "portable":N, "total":M, "ok":bool}"""
    specs = bg.blocks(root)
    results = {}
    for bid in sorted(specs):
        if only and bid not in only:
            continue
        info = specs[bid]
        block_json = info.get("block")
        if not block_json:
            results[bid] = {"block": bid, "portable": False, "ms": 0,
                            "violations": [_v("block-json", _rel(info["dir"], root), 0,
                                              "block.json 读不出来：%s"
                                              % "；".join(info.get("errors") or []))],
                            "static": 0, "move": 0, "loaded": False,
                            "selftest": None, "declared": []}
            continue
        results[bid] = check_block(bid, info["dir"], block_json,
                                   str(info.get("layer") or "module"), root)
    total = len(results)
    ok = sum(1 for r in results.values() if r["portable"])
    return {"blocks": results, "portable": ok, "total": total, "ok": ok == total and total > 0}


def summary_line(res):
    return "portable: %d/%d" % (res["portable"], res["total"])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    root = ROOT
    if "--root" in argv:
        i = argv.index("--root")
        if len(argv) > i + 1:
            root = os.path.abspath(argv[i + 1])
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        if len(argv) > i + 1:
            only = {x.strip() for x in argv[i + 1].split(",") if x.strip()}
    res = check_all(root, only)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    for bid in sorted(res["blocks"]):
        r = res["blocks"][bid]
        print(json.dumps({"block": bid, "portable": r["portable"], "ms": r["ms"],
                          "violations": r["violations"]}, ensure_ascii=False))
    bad = [r for r in res["blocks"].values() if not r["portable"]]
    print("\n搬家测试（判断标准：ARCHITECTURE.md 十二）：%s" % summary_line(res))
    if bad:
        print("不可移植的块：%s" % "、".join(sorted(r["block"] for r in bad)))
        for r in bad:
            for v in r["violations"]:
                print("  x [%s] %s" % (r["block"], short(v)))
        return 1
    print("每个块都能只带 kernel/ 搬走：加载得上、自检通过、进程里没有宿主模块。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
