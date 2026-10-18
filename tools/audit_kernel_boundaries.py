# -*- coding: utf-8 -*-
"""audit_kernel_boundaries.py —— 把「微内核边界」变成机器闸门（不靠自觉）

判断标准只有一份：`ARCHITECTURE.md`（三、四条铁律 / 八、反修正主义）。
本工具是它的执行器，**不是**第二套规则。冲突时改工具，不改铁律；
真要改铁律，按 ARCHITECTURE.md 第八节走流程并写进「修订记录」。

它查五类东西
------------
1. `kernel-*`  内核不许认识业务：
   · kernel/ 下只许 import 标准库和 kernel 自己的子模块；
   · 出现 "角色卡/世界卡/工坊/聊天/记忆" 这类词 → 违规（**注释与 docstring 除外**）。
2. `module-*`  模块边界：
   · 模块只许 import `kernel*`、标准库/三方库、自己的相对文件；
   · 绝对 `modules.*` 一律违规（跨模块 / 外部 import 内部文件都算）——
     模块由 loader 按目录装配（合成包名），外部根本没有稳定名字可以 import，
     所以这条既是纪律也是事实；
   · `from ..` 越出模块目录 → 违规；import 壳层 → 违规；import 别的业务模块 → 违规。
3. `manifest*`  清单必须说真话：能解析、id 与目录名一致、仓库内 id 唯一、
   版本四段、provides/requires 结构合规（复用 kernel.manifest 的校验器，不另写一套）。
4. `limit`     巨型文件行数上限：只许下调，涨了就是红。
5. `whitelist*` 白名单/例外**只许缩短**：条数不得超过基线，且不许出现基线里没有的新条目；
   每条白名单必须带 `reason`（没有 reason 直接红）。

跑法
----
    python tools/audit_kernel_boundaries.py                    # 人看的清单
    python tools/audit_kernel_boundaries.py --json             # 机器可读
    python tools/audit_kernel_boundaries.py --baseline tools/kernel_boundaries_baseline.json
                                                               # 没基线→写<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌；有基线→比
    python tools/audit_kernel_boundaries.py --baseline … --force
                                                               # 只许在"确实变好"时重写基线
    python tools/audit_kernel_boundaries.py --root <另一棵树>   # 判定器自检用
"""

import ast
import io
import json
import os
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASELINE_DEFAULT = os.path.join(HERE, "kernel_boundaries_baseline.json")

# ---------------------------------------------------------------- 层的定义
# 壳层（桌面主程序 / 侧车服务器 / 安卓 / 播放器）。模块**一律不许** import 它们。
SHELL_FILES = {
    "Direct-Interface Cork-bore Kit",
    "html_app",
    "net",
    "trpg_server",
    "trpg_session",
    "host_ui",
    "web_fetch",
    "build_release",
    "build_installer",
}

# 共享叶子库白名单：**只许缩短**。每加一条都要写清 reason（否则测试直接红），
# 并且要按 ARCHITECTURE.md 第八节走流程 —— 白名单是"记录已知欠债"，不是"解决方案"。
SHARED_LEAF_LIBS = {
    "crypto_core": {
        "reason": "场景无关的纯密码学叶子库（只依赖标准库 + cryptography）。"
                  "dick_backup_tool.py 是独立解密工具，必须能脱离 DICK 本体单独运行，"
                  "所以它不能搬进 modules/backup —— 只能由模块单向依赖它。",
        "owner": "modules/backup",
        "cleanup": "不清理：叶子库不是业务模块，ARCHITECTURE.md 第三节已把它归为基础设施",
    },
}

# 内核词表（铁律 3 的落点）。注释与 docstring 里许出现 —— 那是给人看的解释。
KERNEL_FORBIDDEN_WORDS = ("角色卡", "世界卡", "工坊", "聊天", "记忆")

# 巨型文件行数上限（只许下调）。数字是**实测的当前值**，不是拍脑袋的目标值：
# 2026-10-18 用本文件的 measure_lines() 现场量过一遍，六个数字与当天实际行数完全相等
# （web/index.html 6278 / App.kt 30 / Dialogs.kt 142 / net.py 1438 / DICK_core.py 2991 /
#  Direct-Interface Cork-bore Kit.py 7292），所以「上限」此刻就是「当前值」，没有余量。
# 与 tools/kernel_boundaries_baseline.json 的 limits 是同一张表（两处都调高才可能绕过，
# 而两处都各有棘轮拦着）。想调高 = 改铁律，按 ARCHITECTURE.md 第八节走。
LINE_LIMITS = {
    "web/index.html": 6278,
    "DICK-Android/app/src/main/java/com/dick/app/App.kt": 30,
    "DICK-Android/app/src/main/java/com/dick/app/Dialogs.kt": 142,
    "net.py": 1438,
    "DICK_core.py": 2991,
    # 第 6 条不是派单里的五个之一：桌面壳层是本仓库最大的文件（7292 行），
    # 正在被本批迁移拆小，所以一并钉住 —— 它只会越来越小。
    "Direct-Interface Cork-bore Kit.py": 7292,
}

# 扫描时跳过的目录（第三方 / 产物 / 别的端不属于本次边界）
SKIP_DIRS = {"utau_env", "__pycache__", "node_modules", ".git", "build", "dist",
             "archive", "DICK-Android", "DICK-Narrative", "web", "_phone", "lang",
             "tavern-installer", "server_build", ".github", ".devcontainer"}


# ================================================================ 基础设施
def _dirs(root):
    return os.path.join(root, "kernel"), os.path.join(root, "modules")


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _py_files(dir_path, recursive=True):
    out = []
    if not os.path.isdir(dir_path):
        return out
    if not recursive:
        return [os.path.join(dir_path, f) for f in sorted(os.listdir(dir_path))
                if f.endswith(".py") and os.path.isfile(os.path.join(dir_path, f))]
    for dirpath, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(("tmp", "."))]
        for f in sorted(files):
            if f.endswith(".py"):
                out.append(os.path.join(dirpath, f))
    return out


def _doc_files(dir_path):
    """内核里的文档（md/txt/rst）—— 词表规则对它们同样生效，且没有注释白名单"""
    out = []
    if not os.path.isdir(dir_path):
        return out
    for dirpath, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(("tmp", "."))]
        for f in sorted(files):
            if f.lower().endswith((".md", ".txt", ".rst")):
                out.append(os.path.join(dirpath, f))
    return out


def _module_dirs(root):
    _, modules_dir = _dirs(root)
    if not os.path.isdir(modules_dir):
        return []
    return [os.path.join(modules_dir, d) for d in sorted(os.listdir(modules_dir))
            if os.path.isdir(os.path.join(modules_dir, d)) and not d.startswith(("_", "."))]


def _parse(path):
    """返回 ast 树；语法错误返回 None（错误本身由调用方记成违规）"""
    try:
        return ast.parse(_read(path))
    except SyntaxError:
        return None


def _imports(tree):
    """[(行号, 顶层模块名, 是否相对, 相对层级, 原样文本)]"""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((node.lineno, a.name.split(".")[0], False, 0, a.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            top = mod.split(".")[0] if mod else ""
            out.append((node.lineno, top, bool(node.level), node.level, mod or "."))
    return out


def _repo_local_names(root):
    """仓库内可 import 的顶层名字（根目录 .py + 有 __init__.py 的包目录）"""
    names = set()
    if not os.path.isdir(root):
        return names
    for f in os.listdir(root):
        p = os.path.join(root, f)
        if f.endswith(".py"):
            names.add(f[:-3])
        elif os.path.isdir(p) and os.path.isfile(os.path.join(p, "__init__.py")):
            names.add(f)
    names.update({"kernel", "modules"})
    return names


# ================================================================ 规则 1/2：依赖方向
def scan_imports(root=ROOT):
    """内核与模块的 import 方向。返回违规列表。"""
    kernel_dir, _ = _dirs(root)
    local = _repo_local_names(root)
    leaves = set(SHARED_LEAF_LIBS)
    out = []

    def add(rule, path, line, detail):
        out.append({"rule": rule, "file": _rel(path, root), "line": line, "detail": detail})

    # ---- kernel/：只许标准库 + kernel.* ----
    for path in _py_files(kernel_dir):
        tree = _parse(path)
        if tree is None:
            add("kernel-import", path, 0, "语法错误，解析不了")
            continue
        for line, top, relative, _level, text in _imports(tree):
            if relative or top == "kernel":
                continue
            if top in local:
                rule = "kernel-modules" if top == "modules" else "kernel-business"
                add(rule, path, line, "内核 import 了仓库内模块 %r（只许标准库 + kernel.*）" % text)

    # ---- modules/<id>/：只许 kernel* + 相对 + 共享叶子 ----
    for mod_dir in _module_dirs(root):
        for path in _py_files(mod_dir):
            tree = _parse(path)
            if tree is None:
                add("module-import", path, 0, "语法错误，解析不了")
                continue
            for line, top, relative, level, text in _imports(tree):
                if relative:
                    if level >= 2:
                        add("module-cross", path, line,
                            "相对 import 越出模块目录（from %s…）—— 跨模块请注册服务"
                            % ("." * level))
                    continue
                if top in ("kernel", ""):
                    continue
                if top == "modules":
                    add("module-cross", path, line,
                        "模块 import 了 %r：跨模块/内部文件都不许，只能经 kernel.registry / kernel.bus"
                        % text)
                    continue
                if top in leaves:
                    continue
                if top in SHELL_FILES:
                    add("module-shell", path, line, "模块 import 了壳层 %r" % text)
                    continue
                if top in local:
                    add("module-business", path, line,
                        "模块 import 了仓库内业务模块 %r（只许 kernel + 共享叶子库）" % text)
    return out


# ================================================================ 规则 3：内核词表
def _masked_spans(text):
    """注释 + docstring 的字符区间（这些区间里出现业务词是允许的）"""
    spans = []
    line_starts = [0]
    for ln in text.splitlines(True):
        line_starts.append(line_starts[-1] + len(ln))

    def off(row, col):
        return line_starts[min(max(row - 1, 0), len(line_starts) - 1)] + col

    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                spans.append((off(tok.start[0], tok.start[1]), off(tok.end[0], tok.end[1])))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                continue
            body = getattr(node, "body", [])
            if not body:
                continue
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                spans.append((off(first.lineno, first.col_offset),
                              off(first.end_lineno, first.end_col_offset)))
    return spans


def _inside(pos, spans):
    return any(a <= pos < b for a, b in spans)


def scan_kernel_vocab(root=ROOT):
    """内核里出现业务词 → 违规。

    · kernel/**/*.py：注释与 docstring 白名单（铁律许可见人）；
    · kernel/**/*.md|txt：**连白名单都没有** —— 文档也只能拿模块 id 举例，
      否则"内核不认识业务"就成了"只在内核代码里不认识"。
    """
    kernel_dir, _ = _dirs(root)
    out = []
    for path in _py_files(kernel_dir):
        text = _read(path)
        spans = _masked_spans(text)
        for word in KERNEL_FORBIDDEN_WORDS:
            start = 0
            while True:
                i = text.find(word, start)
                if i < 0:
                    break
                start = i + len(word)
                if _inside(i, spans):
                    continue
                line = text.count("\n", 0, i) + 1
                out.append({"rule": "kernel-vocab", "file": _rel(path, root), "line": line,
                            "detail": "内核代码里出现业务词 %r（注释/docstring 除外）" % word})
    for path in _doc_files(kernel_dir):
        text = _read(path)
        for word in KERNEL_FORBIDDEN_WORDS:
            i = text.find(word)
            while i >= 0:
                out.append({"rule": "kernel-vocab", "file": _rel(path, root),
                            "line": text.count("\n", 0, i) + 1,
                            "detail": "内核文档里出现业务词 %r（文档也不许点业务的名）" % word})
                i = text.find(word, i + len(word))
    return out


# ================================================================ 规则 2''：跨块共享可变状态
def scan_shared_state(root=ROOT):
    """块之间共享可变状态 = 0（ARCHITECTURE.md 十一表格第二行）

    判据：块的源文件里**不许有模块级可变全局**（list/dict/set 字面量或推导式），
    也不许出现 `global` 语句。理由：
      · 块之间 import 已经是 0，所以"跨块共享"唯一可能的载体就是模块级状态
        （拿到的模块对象是进程级单例，谁都能改它上面的东西）；
      · 没有模块级可变全局 → 想共享也共享不了，这条指标才是**结构性成立**的。
    dunder（`__all__` 这类）不算：那是给 import 机制看的元数据。
    """
    kernel_dir, _ = _dirs(root)
    targets = _py_files(kernel_dir)
    for mod_dir in _module_dirs(root):
        targets.extend(_py_files(mod_dir))
    mutable_nodes = (ast.List, ast.Dict, ast.Set,
                     ast.ListComp, ast.DictComp, ast.SetComp)
    out = []
    for path in targets:
        tree = _parse(path)
        if tree is None:
            continue
        # global 语句在哪个作用域都算：函数里 `global X` 就是为了改模块级状态
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                out.append({"rule": "shared-state", "file": _rel(path, root),
                            "line": getattr(node, "lineno", 0),
                            "detail": "出现 global 语句：块里不许有可变全局状态"})
        for node in tree.body:
            value = getattr(node, "value", None)
            if not isinstance(value, mutable_nodes):
                continue
            targets_in = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
            for t in targets_in:
                if not isinstance(t, ast.Name) or t.id.startswith("__"):
                    continue
                out.append({"rule": "shared-state", "file": _rel(path, root),
                            "line": getattr(node, "lineno", 0),
                            "detail": "模块级可变全局 %r（list/dict/set）：状态要挂在服务实例上"
                                      % t.id})
    return out


# ================================================================ 规则 2'：单入口
def scan_entry_points(root=ROOT):
    """仓库里任何地方用绝对名字 import modules.* 都违规（模块只能经内核拿，不能 import）"""
    out = []
    targets = []
    for f in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, f)
        if f.endswith(".py"):
            targets.append(p)
    for sub in ("tools", "tests", "deploy"):
        targets.extend(_py_files(os.path.join(root, sub), recursive=False))
    for path in targets:
        tree = _parse(path)
        if tree is None:
            continue
        for line, top, relative, _level, text in _imports(tree):
            if relative or top != "modules":
                continue
            out.append({"rule": "module-entry", "file": _rel(path, root), "line": line,
                        "detail": "外部用绝对名字 import 了 %r —— 模块只能经 kernel.service 拿"
                                  % text})
    return out


# ================================================================ 规则 3'：manifest
def scan_manifests(root=ROOT):
    """清单必须能解析、id 与目录名一致、仓库内唯一、结构合规。"""
    sys.path.insert(0, ROOT)      # 校验器始终用**真仓库**的 kernel.manifest（通用规则）
    try:
        from kernel import manifest as km
    except Exception as e:        # 内核自己坏了要单独报，不能当成"没问题"
        return [{"rule": "manifest-bad", "file": "kernel/manifest.py", "line": 0,
                 "detail": "拿不到内核的清单校验器：%s" % str(e)[:120]}]
    out = []
    seen = {}
    for mod_dir in _module_dirs(root):
        name = os.path.basename(mod_dir)
        p = os.path.join(mod_dir, "manifest.json")
        rel = _rel(p, root)
        if not os.path.isfile(p):
            out.append({"rule": "manifest-bad", "file": _rel(mod_dir, root), "line": 0,
                        "detail": "缺 manifest.json"})
            continue
        try:
            m = km.load_file(p)
        except km.ManifestError as e:
            out.append({"rule": "manifest-bad", "file": rel, "line": 0,
                        "detail": "；".join(e.errors)})
            continue
        if not os.path.isfile(os.path.join(mod_dir, "module.py")):
            out.append({"rule": "manifest-bad", "file": _rel(mod_dir, root), "line": 0,
                        "detail": "缺唯一入口 module.py"})
        if m.id != name:
            out.append({"rule": "manifest-bad", "file": rel, "line": 0,
                        "detail": "id=%r 与目录名 %r 不一致（目录名就是加载单元，不能对不上）"
                                  % (m.id, name)})
        if m.id in seen:
            out.append({"rule": "manifest-bad", "file": rel, "line": 0,
                        "detail": "id=%r 与 %s 重复" % (m.id, seen[m.id])})
        seen[m.id] = rel
    return out


# ================================================================ 规则 4：行数上限
def measure_lines(path, root=ROOT):
    p = os.path.join(root, path)
    if not os.path.isfile(p):
        return None
    return len(_read(p).splitlines())


def effective_limits():
    """行数上限表（常量；只许往下调，工具与基线双重把关）"""
    return {path: int(limit) for path, limit in LINE_LIMITS.items()}


def scan_line_limits(root=ROOT):
    out = []
    for path, limit in effective_limits().items():
        n = measure_lines(path, root)
        if n is None:
            out.append({"rule": "limit", "file": path, "line": 0,
                        "detail": "上限表里的文件不存在（文件被挪走也要同步改这张表）"})
            continue
        if n > limit:
            out.append({"rule": "limit", "file": path, "line": 0,
                        "detail": "现有 %d 行 > 上限 %d 行（只许下调；要拆就真拆）" % (n, limit)})
    return out


# ================================================================ 规则 5：白名单棘轮
def scan_bypass(root=ROOT):
    """反「临时绕过」（ARCHITECTURE.md 第八节）：

    · kernel/ 与 modules/ 里**不许**出现 `# noqa` 之类的静默豁免；
    · 不许用 `except ImportError / ModuleNotFoundError` 给"本地 import 失败"开绿灯 ——
      缺依赖要走向内核对账 + 降级日志，不许条件 import 偷偷放行。
    两条今天都是 0 条；要破例就必须进白名单（带 reason），而白名单只许缩短。
    """
    kernel_dir, _ = _dirs(root)
    out = []
    targets = _py_files(kernel_dir)
    for mod_dir in _module_dirs(root):
        targets.extend(_py_files(mod_dir))
    for path in targets:
        text = _read(path)
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type == tokenize.COMMENT and "noqa" in tok.string.lower():
                    out.append({"rule": "bypass-noqa", "file": _rel(path, root),
                                "line": tok.start[0],
                                "detail": "内核/模块里出现 # noqa：不许静默豁免，缺什么补什么"})
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            names = _handler_type_names(node.type)
            if names & {"ImportError", "ModuleNotFoundError"}:
                out.append({"rule": "bypass-import", "file": _rel(path, root),
                            "line": getattr(node, "lineno", 0),
                            "detail": "用 except ImportError 给 import 开绿灯："
                                      "要降级就走向内核对账/日志，不许条件 import 绕过"})
    return out


def _handler_type_names(node):
    if node is None:
        return set()
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Tuple):
        out = set()
        for e in node.elts:
            out |= _handler_type_names(e)
        return out
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def whitelist_entries():
    """当前白名单（每条必须有 reason）"""
    out = []
    for key, meta in sorted(SHARED_LEAF_LIBS.items()):
        out.append({"key": "shared-leaf:%s" % key,
                    "reason": str((meta or {}).get("reason") or "").strip(),
                    "owner": str((meta or {}).get("owner") or "").strip()})
    return out


def scan_whitelist_health():
    """白名单条目缺 reason → 违规（没有理由的例外等于没有例外）"""
    out = []
    for e in whitelist_entries():
        if not e["reason"] or len(e["reason"]) < 12:
            out.append({"rule": "whitelist-reason",
                        "file": "tools/audit_kernel_boundaries.py", "line": 0,
                        "detail": "白名单条目 %s 没写清 reason（例外必须写明为什么绕不开）"
                                  % e["key"]})
    return out


# ================================================================ 汇总
def scan(root=ROOT):
    """跑全部规则，返回结构化结果"""
    kernel_dir, _ = _dirs(root)
    violations = []
    violations += scan_imports(root)
    violations += scan_kernel_vocab(root)
    violations += scan_entry_points(root)
    violations += scan_shared_state(root)
    violations += scan_manifests(root)
    violations += scan_line_limits(root)
    violations += scan_bypass(root)
    violations += scan_whitelist_health()
    violations.sort(key=lambda v: (v["rule"], v["file"], v["line"]))
    by_rule = {}
    for v in violations:
        by_rule[v["rule"]] = by_rule.get(v["rule"], 0) + 1
    limits = {path: {"limit": limit, "lines": measure_lines(path, root)}
              for path, limit in effective_limits().items()}
    return {
        "schema": 1,
        "root": os.path.abspath(root),
        "counts": {
            "kernel_files": len(_py_files(kernel_dir)),
            "module_dirs": len(_module_dirs(root)),
            "module_files": sum(len(_py_files(d)) for d in _module_dirs(root)),
            "violations": len(violations),
        },
        "by_rule": by_rule,
        "violations": violations,
        "whitelist": whitelist_entries(),
        "whitelist_count": len(whitelist_entries()),
        "limits": limits,
    }


def _baseline_of(res):
    return {
        "schema": 1,
        "violations": ["%s|%s|%s|%s" % (v["rule"], v["file"], v["line"], v["detail"])
                       for v in res["violations"]],
        "whitelist": [e["key"] for e in res["whitelist"]],
        "whitelist_count": res["whitelist_count"],
        "limits": {k: v["limit"] for k, v in res["limits"].items()},
    }


def compare_baseline(res, path, force=False):
    """与基线比对：违规变多、白名单变长/换条目、行数上限被调高 → 返回 1"""
    new = _baseline_of(res)
    if not os.path.isfile(path) or force:
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(new, ensure_ascii=False, indent=2) + "\n")
        print("【基线】%s %s（违规 %d 条 / 白名单 %d 条）"
              % ("已覆盖" if force else "已建立", os.path.basename(path),
                 len(new["violations"]), new["whitelist_count"]))
        return 0 if not new["violations"] else 1
    try:
        with io.open(path, encoding="utf-8") as f:
            old = json.load(f)
    except Exception as e:
        print("【基线】读不出来（%s），本次按「没有基线」处理" % str(e)[:80])
        return 1
    rc = 0
    old_v = set(old.get("violations") or [])
    cur_v = new["violations"]
    added = [v for v in cur_v if v not in old_v]
    if len(cur_v) > len(old_v) or added:
        print("【基线】违规比基线多：基线 %d 条 → 现在 %d 条" % (len(old_v), len(cur_v)))
        for v in added[:10]:
            print("       新增 → %s" % v)
        rc = 1
    elif len(cur_v) < len(old_v):
        print("【基线】违规变少了（%d → %d）：用 --force 把基线调小才算真的进步"
              % (len(old_v), len(cur_v)))

    old_w = set(old.get("whitelist") or [])
    cur_w = set(new["whitelist"])
    if new["whitelist_count"] > int(old.get("whitelist_count") or 0):
        print("【棘轮】白名单变长了：基线 %d 条 → 现在 %d 条（只许缩短）"
              % (old.get("whitelist_count") or 0, new["whitelist_count"]))
        rc = 1
    grown = sorted(cur_w - old_w)
    if grown:
        print("【棘轮】白名单出现基线里没有的新条目：%s" % "、".join(grown))
        rc = 1

    old_limits = old.get("limits") or {}
    for path2, limit in new["limits"].items():
        was = int(old_limits.get(path2) or 0)
        if was and int(limit) > was:
            print("【棘轮】行数上限被调高：%s %d → %d（只许下调）" % (path2, was, int(limit)))
            rc = 1
    if not rc:
        print("【基线】与基线一致（违规 %d 条 / 白名单 %d 条 / 行数上限 %d 项）"
              % (len(cur_v), new["whitelist_count"], len(new["limits"])))
    return rc


# ================================================================ CLI
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    force = "--force" in argv
    root = ROOT
    if "--root" in argv:
        i = argv.index("--root")
        if len(argv) > i + 1:
            root = os.path.abspath(argv[i + 1])
    res = scan(root)

    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("=" * 66)
        print("微内核边界审计（判断标准：ARCHITECTURE.md）")
        print("=" * 66)
        print("扫了 %d 个内核文件 / %d 个模块（%d 个文件）"
              % (res["counts"]["kernel_files"], res["counts"]["module_dirs"],
                 res["counts"]["module_files"]))
        print("\n规则命中：%s"
              % ("、".join("%s=%d" % (k, v) for k, v in sorted(res["by_rule"].items())) or "无"))
        if res["violations"]:
            print("\n违规清单：")
            for v in res["violations"]:
                print("  [%s] %s:%s  %s" % (v["rule"], v["file"], v["line"], v["detail"]))
        print("\n白名单（只许缩短）：%d 条" % res["whitelist_count"])
        for e in res["whitelist"]:
            print("  · %s（%s）" % (e["key"], e["owner"] or "?"))
        print("\n巨型文件行数（上限只许下调）：")
        for path, info in sorted(res["limits"].items()):
            print("  %-52s %5s / 上限 %5d" % (path, info["lines"], info["limit"]))

    rc = 0
    if "--baseline" in argv:
        i = argv.index("--baseline")
        base = argv[i + 1] if len(argv) > i + 1 else BASELINE_DEFAULT
        rc = compare_baseline(res, base, force)
    elif res["violations"]:
        rc = 1
    if not as_json:
        print("\n结论：%s" % ("有违规（见上）" if res["violations"] else "0 违规"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
