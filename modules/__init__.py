# -*- coding: utf-8 -*-
"""modules/__init__.py —— 块的容器（这里不是逻辑，只是让 `python -m modules.<id>` 能找到包）

注意：加载器（kernel/loader.py）**不靠**这个名字加载块 —— 它按目录装配合成包名，
所以块的内部文件在外部没有稳定名字可 import。这个 `__init__.py` 只为两件事存在：
  ① `python -m modules.<id> --selftest` 能跑（闭环自检，ARCHITECTURE.md 十一）；
  ② 让 tools/ 里的检查工具能按包路径定位块。
"""
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌