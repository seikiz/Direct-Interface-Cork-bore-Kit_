# -*- coding: utf-8 -*-
"""bump_version.py —— 改版号的唯一手。

版号是**四段**：`主.次.补.构建`。按用户定的口径：**一次架构大更新把最后一段 +1**
（也就是说平时不动它，别每次提交都涨号）。

唯一真相是仓库根目录的 `version.json`；其余全是派生的：
  · 电脑端运行时读它（`app_version.py`）；
  · 安卓与播放器在 Gradle 配置阶段读它（versionName / versionCode 都算出来）；
  · 所以"涨号"这件事只需要改这一个文件 —— 没有第二个地方需要同步，也就漏不了。

用法：
    python tools/bump_version.py              # 最后一段 +1（1.0.0.1 → 1.0.0.2）
    python tools/bump_version.py --set 1.2.0.1
    python tools/bump_version.py --show       # 看当前号与各端会拿到的值
    python tools/bump_version.py --check      # 校验全仓一致性（测试用，退出码 0/1）
"""
import io
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERSION_JSON = os.path.join(ROOT, "version.json")

AND_GRADLE = os.path.join(ROOT, "DICK-Android", "app", "build.gradle.kts")
NAR_GRADLE = os.path.join(ROOT, "DICK-Narrative", "app", "build.gradle.kts")
SPEC = os.path.join(ROOT, "DICK_HTML.spec")
DESKTOP = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
HTML = os.path.join(ROOT, "web", "index.html")

VER_RE = re.compile(r"\b\d+\.\d+\.\d+\.\d+\b")


def read_json():
    with io.open(VERSION_JSON, encoding="utf-8") as f:
        return json.load(f)


def write_json(data):
    with io.open(VERSION_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parts(v):
    out = [int(x) for x in str(v).split(".")[:4]]
    while len(out) < 4:
        out.append(0)
    return out


def code_of(v):
    a, b, c, d = parts(v)
    return a * 1000000 + b * 10000 + c * 100 + d


def read_text(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def bump_last(v):
    a, b, c, d = parts(v)
    return "%d.%d.%d.%d" % (a, b, c, d + 1)


def cmd_show():
    data = read_json()
    v = data["version"]
    print("version.json      %s（代号 %s，versionCode %d）"
          % (v, data.get("generation") or "-", data.get("code") or code_of(v)))
    print("电脑端会显示      %s" % ("v" + v))
    print("安卓 / 播放器     versionName=%s versionCode=%d" % (v, code_of(v)))
    print("四段口径          %s" % data.get("scheme", ""))
    return 0


def cmd_set(v):
    v = str(v).strip()
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", v):
        print("版号要四段数字，例如 1.0.0.2；收到：%r" % v)
        return 2
    data = read_json()
    old = data.get("version")
    data["version"] = v
    data["code"] = code_of(v)
    data["updated"] = date.today().isoformat()
    write_json(data)
    print("版号 %s → %s（versionCode %d）" % (old, v, data["code"]))
    return 0


def cmd_check(quiet=False):
    """全仓一致性：唯一真相在 version.json，其它地方只许派生，不许写死。"""
    problems = []
    if not os.path.isfile(VERSION_JSON):
        return ["version.json 不存在"]
    data = read_json()
    v = str(data.get("version") or "")
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", v):
        problems.append("version.json 的 version 不是四段号：%r" % v)
    if int(data.get("code") or 0) != code_of(v):
        problems.append("version.json 的 code 与四段号算出来的不一致：%s vs %d"
                        % (data.get("code"), code_of(v)))

    # 安卓 / 播放器：必须读 version.<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌json，不许写死 versionName
    for p, rel in ((AND_GRADLE, "DICK-Android/app/build.gradle.kts"),
                   (NAR_GRADLE, "DICK-Narrative/app/build.gradle.kts")):
        if not os.path.isfile(p):
            problems.append("%s 不存在" % rel)
            continue
        t = read_text(p)
        if "version.json" not in t:
            problems.append("%s 没读 version.json（版号写死了？）" % rel)
        for m in re.finditer(r'versionName\s*=\s*"([^"]+)"', t):
            problems.append("%s 里写死了 versionName = %r" % (rel, m.group(1)))
        for m in re.finditer(r"versionCode\s*=\s*(\d+)", t):
            problems.append("%s 里写死了 versionCode = %s" % (rel, m.group(1)))

    # 桌面端：不许再写死自己的版本串。
    # 只认「带 v 前缀且紧跟产品名」的形式 —— 模型名里有 Mistral-7B-Instruct-v0.3
    # 这种带 v 的版本，扫宽了全是假警报。
    t = read_text(DESKTOP)
    for m in re.finditer(r"(?:Cork-bore Kit|DICK)\s+v\d+\.\d+(?:\.\d+)*", t):
        problems.append("桌面端还写死了版本串：%r" % m.group(0))
    if "app_version" not in t:
        problems.append("桌面端没用 app_version（版号从哪来？）")

    # 前端：不许写死带 v 的版号（127.0.0.1 这种 IP 不算 —— 所以必须有 v 前缀）
    h = read_text(HTML)
    for m in re.finditer(r"\bv\d+\.\d+\.\d+\.\d+\b", h):
        problems.append("web/index.html 里写死了版号：%s" % m.group(0))

    # 打包清单：冻结版必须能找到 version.json
    if os.path.isfile(SPEC) and "version.json" not in read_text(SPEC):
        problems.append("DICK_HTML.spec 没有随包 version.json（冻结版会读不到号）")

    if not quiet:
        if problems:
            for p in problems:
                print("[问题] " + p)
        else:
            print("[ok] 版号一致：%s（versionCode %d）" % (v, code_of(v)))
    return problems


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in argv:
        return cmd_show()
    if "--check" in argv:
        return 1 if cmd_check() else 0
    if "--set" in argv:
        i = argv.index("--set")
        if i + 1 >= len(argv):
            print("--set 后面要跟四段号")
            return 2
        return cmd_set(argv[i + 1])
    data = read_json()
    old = data.get("version")
    new = bump_last(old)
    data["version"] = new
    data["code"] = code_of(new)
    data["updated"] = date.today().isoformat()
    write_json(data)
    print("版号 %s → %s（versionCode %d）" % (old, new, data["code"]))
    print("电脑端/安卓/播放器下次启动或构建就用新号；没有第二处需要同步。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
