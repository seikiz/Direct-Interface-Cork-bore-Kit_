# -*- coding: utf-8 -*-
"""搬家测试的测试：可移植性判定器不能是装饰。

为什么要有这一份
----------------
`tools/portability_check.py` 说"三块都可以搬走"时，必须先证明它**真的会红**：
故意造一个写死 `C:\\…`、站点 IP、读宿主 `config.json`、偷偷 `import requests` 的假块，
判定器必须当场抓到。否则 `portable: 3/3` 可能只是"根本没在查"——这和
`tests/test_kernel_boundaries.py` 的 B 段（判定器自检）是同一个道理。

三段断言：
  A. 真实三块：搬家后能加载、自检通过、进程里没有宿主模块；
  B. 判定器自检：静态规则逐条造违规必须被抓到，干净块必须不报（控制组）；
  C. 搬家测试自检：真搬一个假块，装不上/多出宿主模块时必须红。

跑法：python tests\\test_block_portability.py
"""

import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import portability_check as pc        # noqa: E402
import accept                         # noqa: E402

PASS = 0
FAIL = 0
_TMP = []

CLEAN_MODULE = '''# -*- coding: utf-8 -*-
"""干净假块：只依赖 stdlib + kernel"""
import io
import json
import os


def register(kernel):
    kernel.registry.register("fake", object(), owner="fake")


def work(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)
'''

FAKE_SELFTEST = '''# -*- coding: utf-8 -*-
import json

BLOCK = "fake"


def main(argv=None):
    print(json.dumps({"block": BLOCK, "pass": 1, "fail": 0, "ms": 1, "deps": []}))
    return 0
'''


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def tmpdir(label):
    """临时目录：优先 %TEMP%，写不进去退到工作区（与仓库其它测试同一套路）"""
    base = None
    for cand in (os.environ.get("TEMP"), os.environ.get("TMP"),
                 os.path.join(ROOT, "tmp_kernel_tests")):
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".probe_%d" % os.getpid())
            os.makedirs(probe, exist_ok=True)
            os.rmdir(probe)
            base = cand
            break
        except Exception:
            continue
    d = os.path.join(base, "dick_port_%s_%d" % (label, len(_TMP)))
    os.makedirs(d, exist_ok=True)
    _TMP.append((d, base))
    return d


def cleanup_tmp():
    for d, base in _TMP:
        shutil.rmtree(d, ignore_errors=True)
    _TMP[:] = []
    # 兜底的共享临时根目录：只在确实是空<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的时候删，别拆了并行任务正在用的目录
    shared = os.path.join(ROOT, "tmp_kernel_tests")
    try:
        os.rmdir(shared)
    except OSError:
        pass


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def fake_block(files, requires=None, block_id="fake"):
    """造一个只有源文件的假块，返回 (块目录, block.json 数据, 扫描用的 root)"""
    d = tmpdir("static")
    for name, text in files.items():
        write(os.path.join(d, name), text)
    bj = {"block": block_id, "layer": "module", "id": block_id,
          "files": sorted(set(list(files) + ["block.json", "manifest.json"])),
          "selftest": {"cmd": ["python", "-m", "modules.%s" % block_id, "--selftest"],
                       "max_ms": 2000},
          "interface": {"service": block_id, "methods": ["register"]}}
    if requires is not None:
        bj["requires"] = {"pip": list(requires)}
    write(os.path.join(d, "block.json"), json.dumps(bj, ensure_ascii=False, indent=2))
    return d, bj, os.path.dirname(d)


def rules_of(block_dir, block_json, root):
    return {v["rule"] for v in pc.scan_static(block_dir, block_json, root)}


def fake_repo(label, module_extra="", selftest_extra=""):
    """造一棵最小仓库：真 kernel/ + modules/fake（入口能注册服务）"""
    root = tmpdir(label)
    shutil.copytree(os.path.join(ROOT, "kernel"), os.path.join(root, "kernel"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    d = os.path.join(root, "modules", "fake")
    write(os.path.join(d, "__init__.py"), "")
    write(os.path.join(d, "manifest.json"), json.dumps({
        "id": "fake", "version": "1.0.0.0", "provides": {"services": ["fake"]},
        "requires": {"services": [], "modules": []}, "lazy": False}, ensure_ascii=False))
    write(os.path.join(d, "module.py"),
          module_extra + "def register(kernel):\n"
                         "    kernel.registry.register('fake', object(), owner='fake')\n")
    write(os.path.join(d, "selftest.py"), selftest_extra + FAKE_SELFTEST)
    write(os.path.join(d, "__main__.py"),
          "import sys\n\nfrom .selftest import main\n\n"
          "if __name__ == '__main__':\n    sys.exit(main(sys.argv[1:]))\n")
    write(os.path.join(d, "block.json"), json.dumps({
        "block": "fake", "layer": "module", "id": "fake",
        "files": ["__init__.py", "__main__.py", "block.json", "manifest.json",
                  "module.py", "selftest.py"],
        "selftest": {"cmd": ["python", "-m", "modules.fake", "--selftest"],
                     "max_ms": 2000},
        "interface": {"service": "fake", "methods": ["register"]},
        "requires": {"pip": []}}, ensure_ascii=False, indent=2))
    with io.open(os.path.join(d, "block.json"), encoding="utf-8") as f:
        bj = json.load(f)
    return root, d, bj


# ================================================================ A. 真实块
BLOCK_IDS = ("backup", "codex", "image_gen", "kernel", "voice", "workshop")


def test_real_blocks():
    print(u"\n== A. 真实块：搬走之后还能装上、自检通过、没有宿主模块 ==")
    res = pc.check_all()
    check(u"搬家测试覆盖六块（kernel / backup / workshop / image_gen / voice / codex）",
          res["total"] == len(BLOCK_IDS), str(sorted(res["blocks"])))
    passed = 0
    for bid in BLOCK_IDS:
        r = res["blocks"].get(bid) or {}
        check(u"%s 可移植（portable=True）" % bid, r.get("portable") is True,
              str(r.get("violations"))[:300])
        check(u"%s 搬家后自检 fail=0" % bid,
              int((r.get("selftest") or {}).get("fail", -1)) == 0, str(r.get("selftest")))
        check(u"%s 搬家后经内核 loader 装上了" % bid, bool(r.get("loaded")), str(r))
        check(u"%s 静态扫描 0 违规" % bid, int(r.get("static", -1)) == 0,
              str(r.get("violations"))[:300])
        if r.get("portable"):
            passed += 1
    check(u"六块 portable 计数 = 6/6", passed == len(BLOCK_IDS), str(passed))
    check(u"六块都只声明 stdlib + kernel（requires.pip 为空）",
          all(not (res["blocks"].get(b) or {}).get("declared") for b in res["blocks"]),
          str({b: (res["blocks"][b] or {}).get("declared") for b in res["blocks"]}))


# ================================================================ B. 静态判定器自检
def test_static_rules():
    print(u"\n== B1. 静态规则：造出来的违规必须被抓到 ==")
    d, bj, root = fake_block({"__init__.py": "", "module.py": CLEAN_MODULE})
    check(u"控制组：干净假块 0 违规（否则下面的「抓到」没有意义）",
          pc.scan_static(d, bj, root) == [], str(pc.scan_static(d, bj, root))[:300])

    cases = [
        (u"Windows 绝对路径", {"__init__.py": "",
                               "module.py": 'P = "C:\\\\Users\\\\seiki\\\\DICK"\n'}, "abs-path"),
        (u"/home/ 绝对路径", {"__init__.py": "", "module.py": 'P = "/home/seiki/x"\n'}, "abs-path"),
        (u"/opt/ 绝对路径", {"__init__.py": "", "module.py": 'P = "/opt/dick/data"\n'}, "abs-path"),
        (u"站点 IP", {"__init__.py": "",
                       "module.py": 'U = "http://154.94.226.240:5000"\n'}, "site-ip"),
        (u"私网 IP", {"__init__.py": "", "module.py": 'H = "192.168.1.7"\n'}, "site-ip"),
        (u"sys.path 操作", {"__init__.py": "",
                            "module.py": 'import sys\nsys.path.insert(0, ".")\n'}, "sys-path"),
        (u"读宿主 config.json", {"__init__.py": "",
                                 "module.py": 'import os\n\n\ndef f():\n'
                                              '    return open(os.path.join("..", "config.json"))\n'},
         "host-read"),
        (u"读宿主路径工具 app_paths", {"__init__.py": "",
                                       "module.py": 'import app_paths\n'}, "host-read"),
        (u"未声明第三方库 requests", {"__init__.py": "",
                                      "module.py": 'import requests\n'}, "undeclared-import"),
    ]
    for label, files, rule in cases:
        d2, bj2, root2 = fake_block(files)
        got = rules_of(d2, bj2, root2)
        check(u"静态判定：%s → %s" % (label, rule), rule in got, str(got))

    d3, bj3, root3 = fake_block({"__init__.py": "", "module.py": 'V = "1.2.3.4"\n'})
    check(u"不误报：版本号 1.2.3.4 不是站点 IP", pc.scan_static(d3, bj3, root3) == [],
          str(pc.scan_static(d3, bj3, root3))[:200])


def test_pip_declaration():
    print(u"\n== B2. requires.pip：声明与 import 必须对得上（两个方向）==")
    d, bj, root = fake_block({"__init__.py": "", "module.py": "import requests\n"},
                             requires=["requests"])
    check(u"声明了 requests 且真的 import → 不报",
          pc.scan_static(d, bj, root) == [], str(pc.scan_static(d, bj, root))[:300])

    d, bj, root = fake_block({"__init__.py": "", "module.py": "import os\n"},
                             requires=["requests"])
    check(u"声明了 requests 却没人 import → unused-pip（声明是假话）",
          "unused-pip" in rules_of(d, bj, root), str(rules_of(d, bj, root)))

    d, bj, root = fake_block({"__init__.py": "", "module.py": "from webview import windows\n"},
                             requires=["pywebview"])
    check(u"PyPI 名 pywebview 能对上 import 名 webview（不误报）",
          pc.scan_static(d, bj, root) == [], str(pc.scan_static(d, bj, root))[:300])

    d, bj, root = fake_block({"__init__.py": "", "module.py": "from webview import windows\n"})
    check(u"用了 pywebview 却没声明 → undeclared-import",
          "undeclared-import" in rules_of(d, bj, root), str(rules_of(d, bj, root)))


# ================================================================ C. 搬家测试自检
def test_move_detector():
    print(u"\n== C. 搬家测试：真搬一次，装不上/多出宿主模块必须红 ==")
    root, d, bj = fake_repo("move_ok")
    r = pc.check_block("fake", d, bj, "module", root)
    check(u"控制组：干净假块真能搬走（portable=True, 装上了）",
          r["portable"] is True and r["loaded"] is True,
          str(r.get("violations"))[:300])

    root, d, bj = fake_repo("move_host", module_extra="import crypto_core\n")
    r = pc.check_block("fake", d, bj, "module", root)
    check(u"直接 import 仓库根 crypto_core 的块 → 搬家失败", r["portable"] is False,
          str(r.get("violations"))[:300])
    check(u"失败原因指向「搬走之后装不上」",
          any(v["rule"] in ("load", "selftest") for v in r["violations"]),
          str([v["rule"] for v in r["violations"]]))

    root, d, bj = fake_repo("move_third", selftest_extra="import requests\n")
    r = pc.check_block("fake", d, bj, "module", root)
    rules = {v["rule"] for v in r["violations"]}
    check(u"自检里偷偷 import requests → 搬家失败", r["portable"] is False, str(rules))
    check(u"运行时抓到了未声明第三方库（extra-module / undeclared-import）",
          bool(rules & {"extra-module", "undeclared-import"}), str(rules))


# ================================================================ D. accept 接入
def test_accept_integration():
    print(u"\n== D. accept.py 接入：失败要有 FAIL <块>: 不可移植（原因）==")
    d, bj, root = fake_block({"__init__.py": "", "module.py": 'P = "C:\\\\Users\\\\x\\\\y"\n'})
    blocks = {"noisy": {"dir": d, "block": bj, "layer": "module"}}
    results, failures, summary = accept.check_portability(blocks)
    check(u"accept 把这个块判成不可移植", results["noisy"]["portable"] is False,
          str(results["noisy"]["violations"])[:200])
    check(u"失败原因以「不可移植（」开头（正好拼成 FAIL 行）",
          bool(failures) and failures[0]["reason"].startswith(u"不可移植（"),
          str(failures)[:300])
    check(u"accept 的 portable 汇总计数正确", summary == {"portable": 0, "total": 1},
          str(summary))


def main():
    print("=" * 62)
    print(u"块的可移植性：搬家测试（判定标准：ARCHITECTURE.md 十二）")
    print("=" * 62)
    try:
        test_real_blocks()
        test_static_rules()
        test_pip_declaration()
        test_move_detector()
        test_accept_integration()
    finally:
        cleanup_tmp()
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("BLOCK_PORTABILITY_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
