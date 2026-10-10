# -*- coding: utf-8 -*-
"""版号一致性：唯一真相是 version.json，其它地方只许派生。

守的是这件事：版号原来散在 5 处（桌面欢迎语 / 窗口标题 / 前端控制台横幅各写死 "v2.0"，
安卓与播放器的 Gradle 各写死 "1.0"），于是"电脑上是 v2.0、手机上是 1.0"，涨号还得记着改五处。
现在改成：

    version.json（唯一真相）
        ├── 桌面端运行时读 → app_version.display() / full()
        ├── 安卓  Gradle 配置阶段读 → versionName / versionCode
        ├── 播放器 Gradle 配置阶段读 → versionName / versionCode
        └── 前端不读文件：版号由 api_state() 带回（state.version / version_full）

四段号口径（用户定调）：`主.次.补.构建`，**一次架构大更新把最后一段 +1**（手动跑
`python tools/bump_version.py`）。versionCode = 主*10^6 + 次*10^4 + 补*10^2 + 构建。

跑法：python tests\\test_version_consistency.py
"""
import importlib.util
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    print("=" * 58)
    print(u"版号一致性（version.json 是唯一真相）")
    print("=" * 58)

    vp = os.path.join(ROOT, "version.json")
    check(u"version.json 在仓库根目录", os.path.isfile(vp))
    data = json.loads(read(vp))
    ver = str(data.get("version") or "")

    print(u"\n-- ① 四段号本身 --")
    check(u"版号是四段数字（主.次.补.构建）", bool(re.match(r"^\d+\.\d+\.\d+\.\d+$", ver)), ver)
    check(u"写明了涨号口径（一次架构大更新 +1）", bool(str(data.get("scheme") or "").strip()))
    check(u"有 versionCode", isinstance(data.get("code"), int), str(data.get("code")))

    bv = load(os.path.join(ROOT, "tools", "bump_version.py"), "bump_version")
    check(u"code 与四段号算出来的一致", int(data.get("code")) == bv.code_of(ver),
          u"%s vs %s" % (data.get("code"), bv.code_of(ver)))
    check(u"1.0.0.1 → 1000001 的映射没变", bv.code_of("1.0.0.1") == 1000001, str(bv.code_of("1.0.0.1")))
    check(u"+1 只动最后一段", bv.bump_last("1.0.0.1") == "1.0.0.2", bv.bump_last("1.0.0.1"))
    check(u"进位不会串段（1.0.0.99 → 1.0.0.100）", bv.bump_last("1.0.0.99") == "1.0.0.100")

    print(u"\n-- ② 全仓没有第二处写死（bump_version --check） --")
    problems = bv.cmd_check(quiet=True)
    check(u"唯一真相之外没有写死的版号", not problems, u"；".join(problems[:4]))

    print(u"\n-- ③ 三端读的是同一份 --")
    appver = load(os.path.join(ROOT, "app_version.py"), "app_version")
    check(u"桌面端显示 v%s" % ver, appver.display() == "v" + ver, appver.display())
    check(u"桌面端 versionCode 一致", appver.CODE == bv.code_of(ver), str(appver.CODE))
    check(u"桌面端 full() 带上产品名", ver in appver.full() and appver.NAME in appver.full(), appver.full())

    andg = read(os.path.join(ROOT, "DICK-Android", "app", "build.gradle.kts"))
    check(u"安卓 Gradle 读 version.json", "version.json" in andg)
    check(u"安卓没有写死 versionName", not re.search(r'versionName\s*=\s*"', andg))
    check(u"安卓没有写死 versionCode", not re.search(r"versionCode\s*=\s*\d", andg))

    narg = read(os.path.join(ROOT, "DICK-Narrative", "app", "build.gradle.kts"))
    check(u"播放器 Gradle 读 version.json", "version.json" in narg)
    check(u"播放器没有写死 versionName", not re.search(r'versionName\s*=\s*"', narg))

    front = read(os.path.join(ROOT, "web", "index.html"))
    check(u"前端用 state 带回的版号（不读文件、不写死）",
          "s.version_full" in front or "s.version" in front)
    check(u"前端没有写死带 v 的四段号", not re.search(r"\bv\d+\.\d+\.\d+\.\d+\b", front))

    desk = read(os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py"))
    check(u"桌面端 import 了 app_version", "import app_version" in desk)
    check(u"窗口标题来自 app_version", "app_version.display()" in desk)
    check(u"欢迎语来自 app_version", "app_version.full()" in desk)
    check(u"state 里带上了版号", '"version": app_version.display()' in desk)

    print(u"\n-- ④ 冻结版也得读得到号 --")
    spec = read(os.path.join(ROOT, "DICK_HTML.spec"))
    check(u"spec 随包 version.json", "('version.json', '.')" in spec)
    check(u"spec 随包 app_version.py", "('app_version.py', '.')" in spec)

    print("\n" + "=" * 58)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("VERSION_CONSISTENCY_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌