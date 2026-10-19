# -*- coding: utf-8 -*-
"""python -m modules.voice --selftest 的入口（逻辑在 selftest.py，保持这个文件极薄）"""

import sys

from .selftest import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌