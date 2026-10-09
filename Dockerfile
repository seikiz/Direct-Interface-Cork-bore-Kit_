# DICK 测试环境容器 —— 用来在**本机**复现 CI 的 Linux 环境
#
# 为什么需要它
# ------------
# 2026-10 那次 CI 连续全红，两类问题都很致命：
#   · 本机有、CI 没有（缺 cryptography/numpy/python-docx → 五个脚本 ModuleNotFoundError）
#   · Linux 才炸、本机看不见（save_guard 后台清理删掉正在写的临时文件 → 存档随机失败）
# 本机没有 WSL/Docker 时，只能"推上去才知道红"，一轮就是几分钟 + 一次误判风险。
# 这个镜像把 Linux 侧环境固定下来：一条命令，本地就能跑与 CI 同版本的 Python 与依赖。
#
# 用法（在工程根，装了 Docker 或 Podman 之后）：
#     docker build -t dick-tests .
#     docker run --rm dick-tests                       # 跑全套 Python 测试 + Node 图标回归
#     docker run --rm dick-tests python tests/test_save_guard.py   # 只跑某个
#
# ⚠ 边界（别误会它能替代什么）
#   · 它是 **Linux** 环境：DPAPI、PyInstaller 打包、Windows 语音链路、GBK 相关的行为
#     在这里**永远不会出现** —— Windows 独有的坑要靠 CI 的 windows 作业（见 .github/workflows/test.yml）。
#   · 它跑的是**测试套件**，不是 DICK 本体（本体是 Windows 桌面程序，跑不进 Linux 容器）。
#   · 没装 Docker 也能用它的思路：里面的两份文件（requirements-test.txt / 那行循环）就是全部内容。
FROM python:3.12-bookworm

# Node 只为 tests/test_icons.js（纯前端逻辑回归）。Debian 自带的 nodejs 够用：
# 那个脚本只用 ES6，Node 8+ 都能跑，不需要新特性。
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先只拷依赖清单：改代码不会让依赖层缓存失效
COPY requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements-test.txt

COPY . .

# UTF-8：Windows 上 stdin/stdout 默认跟 locale 走（GBK），Linux 默认就是 UTF-8。
# 显式写出来，免得以后加容器时又踩一次"中文被按 GBK 解"（2026-10 真事：协议插件）。
ENV PYTHONPATH=/app \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8

# 跟 CI 的"运行全量测试"一步同构：逐个跑，任一失败就红（别用 pytest 之类的额外依赖）
CMD ["bash", "-lc", "FAIL=0; for t in tests/test_*.py; do echo \"== $t ==\"; python \"$t\" || FAIL=1; done; node tests/test_icons.js || FAIL=1; exit $FAIL"]
