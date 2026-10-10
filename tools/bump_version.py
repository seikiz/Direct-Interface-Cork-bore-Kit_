# -*- coding: utf-8 -*-
"""bump_version.py —— 改版号的唯一手。

版号是四段：`主 . 次 . 补 . 实验`

    主  兼容纪元。**前两位不变 = 兼容**；一旦无法兼容，直接进 2.0（主 +1、低位归零）
    次  大功能（新的兼容线）
    补  **只用来标记"加了官方可选插件"** —— 不是通用的小功能位（用户定调）
    实验 实验性版本 —— 随便涨，不承诺兼容，随时可以被下一个正式号盖掉

用户定调的口径：**"只要前面两个不变都可以兼容，无法兼容时直接换成 2.0；
加小功能涨第三位，大功能涨第二位，第四位是实验性版本"**，
后一条补充：**"第三位只是加官方可选插件时期"**。
所以纯修补（既不加大功能、也不加官方插件）**不涨号**；要出实验包走 `exp`。

唯一真相是仓库根目录的 `version.json`；其余全是派生的：
  · 电脑端运行时读它（`app_version.py`）；
  · 安卓与播放器在 Gradle 配置阶段读它（versionName / versionCode 都算出来）；
  · 所以"涨号"只需要改这一个文件 —— 没有第二处要同步，也就漏不了。

用法（**不带参数只读，不会改号** —— 涨号必须写清是哪一类）：
    python tools/bump_version.py minor      # 大功能：1.0.3.2 → 1.1.0.0（新兼容线）
    python tools/bump_version.py patch      # 加了官方可选插件：1.0.0.1 → 1.0.1.0
    python tools/bump_version.py major      # 无法兼容：1.4.2.9 → 2.0.0.0
    python tools/bump_version.py exp        # 实验性：1.0.1.0 → 1.0.1.1
    python tools/bump_version.py --set 2.0.0.0
    python tools/bump_version.py --show     # 看当前号、兼容线与各端拿到的值
    python tools/bump_version.py --check    # 校验全仓一致性（测试用，退出码 0/1）
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

SCHEME = ("四段：主.次.补.实验。前两位不变 = 兼容；无法兼容直接进 2.0（主+1、低位归零）；"
          "大功能涨次位；补位只用来标记「加了官方可选插件」；第四位是实验性版本；"
          "纯修补不涨号。")

# 涨号动作 → (动第几位[0.<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌.3], 它后面几位是否归零)
BUMPS = {
    "major": (0, True),    # 无法兼容 → 2.0.0.0
    "minor": (1, True),    # 大功能   → 1.1.0.0
    "patch": (2, True),    # 加了官方可选插件 → 1.0.1.0
    "exp": (3, False),     # 实验性   → 1.0.0.2（只涨第四位）
}

WHAT = {
    "major": "无法兼容（新兼容纪元）",
    "minor": "大功能（新兼容线）",
    "patch": "加了官方可选插件",
    "exp": "实验性版本",
}


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


def fmt(p):
    return "%d.%d.%d.%d" % tuple(p[:4])


def code_of(v):
    a, b, c, d = parts(v)
    return a * 1000000 + b * 10000 + c * 100 + d


def bump(v, kind):
    """按涨号动作算出新号。major/minor/patch 会把后面的段归零（2.0 就是 2.0.0.0）。"""
    if kind not in BUMPS:
        raise ValueError("未知的涨号动作：%r（可用：%s）" % (kind, "、".join(BUMPS)))
    idx, zero_tail = BUMPS[kind]
    p = parts(v)
    p[idx] += 1
    if zero_tail:
        for i in range(idx + 1, 4):
            p[i] = 0
    return fmt(p)


def compat_line(v):
    """兼容线 = 前两位（`1.0`）。同一条线内互相兼容。"""
    a, b = parts(v)[:2]
    return "%d.%d" % (a, b)


def compatible(a, b):
    """两个版号是否同一条兼容线（前两位相同）。"""
    return compat_line(a) == compat_line(b)


def read_text(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def cmd_show():
    data = read_json()
    v = data["version"]
    p = parts(v)
    print("当前版号          %s   （主 %d / 次 %d / 补 %d / 实验 %d）" % (v, p[0], p[1], p[2], p[3]))
    print("兼容线            %s   —— 前两位不变即兼容；不兼容时直接进 %d.0"
          % (compat_line(v), p[0] + 1))
    print("versionCode       %d（= 主*10^6+次*10^4+补*10^2+实验）" % code_of(v))
    print("电脑端显示        %s" % ("v" + v))
    print("安卓 / 播放器     versionName=%s versionCode=%d" % (v, code_of(v)))
    print("下一个号          patch→%s  minor→%s  major→%s  exp→%s"
          % (bump(v, "patch"), bump(v, "minor"), bump(v, "major"), bump(v, "exp")))
    print("口径              %s" % SCHEME)
    return 0


def cmd_set(v):
    v = str(v).strip()
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", v):
        print("版号要四段数字，例如 1.0.1.0；收到：%r" % v)
        return 2
    data = read_json()
    old = data.get("version")
    data["version"] = v
    data["code"] = code_of(v)
    data["scheme"] = SCHEME
    data["updated"] = date.today().isoformat()
    write_json(data)
    tail = "" if compatible(old, v) else "（兼容线 %s → %s：这是一次不兼容变更）" \
        % (compat_line(old), compat_line(v))
    print("版号 %s → %s（versionCode %d）%s" % (old, v, data["code"], tail))
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
    if not str(data.get("scheme") or "").strip():
        problems.append("version.json 没写涨号口径（scheme）")

    # 安卓 / 播放器：必须读 version.json，不许写死 versionName
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
            print("[ok] 版号一致：%s（兼容线 %s，versionCode %d）"
                  % (v, compat_line(v), code_of(v)))
    return problems


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in argv if not a.startswith("--")]
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

    kind = args[0] if args else ""
    if kind not in BUMPS:
        # 不带参数**不改号**：补位只给"加官方插件"、次位给大功能、主位给不兼容，
        # 猜错一次就会在发行说明里写错性质。所以默认只读，把当前号与口径打出来。
        cmd_show()
        print("\n要涨号请写明哪一类：major（不兼容）｜minor（大功能）｜patch（加了官方可选插件）｜exp（实验性）")
        return 0 if not args else 2
    data = read_json()
    old = data.get("version")
    new = bump(old, kind)
    data["version"] = new
    data["code"] = code_of(new)
    data["scheme"] = SCHEME
    data["updated"] = date.today().isoformat()
    write_json(data)
    line = ("兼容线 %s → %s（不兼容变更）" % (compat_line(old), compat_line(new))
            if not compatible(old, new) else "兼容线 %s 不变" % compat_line(new))
    print("%s：%s → %s（versionCode %d）｜%s" % (WHAT[kind], old, new, data["code"], line))
    print("电脑端/安卓/播放器下次启动或构建就用新号；没有第二处需要同步。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
