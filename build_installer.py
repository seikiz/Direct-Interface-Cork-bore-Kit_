# -*- coding: utf-8 -*-
"""一键构建 DICK 安装包（Inno Setup）：
  1) 确保 DICK-HTML 目录存在且含 exe（用最新构建产物）
  2) 调用 ISCC.exe 编译 installer/DICK_Setup.iss
  3) 输出 DICK-Setup.exe 到 dist/release/
用法：python build_installer.py
"""
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
DICK_DIR = os.path.join(ROOT, "DICK-HTML")
ISS = os.path.join(ROOT, "installer", "DICK_Setup.iss")
RELEASE = os.path.join(ROOT, "dist", "release")


def find_iscc():
    cands = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def main():
    # 1) 检查 DICK-HTML
    exe = os.path.join(DICK_DIR, "DICK-HTML.exe")
    if not os.path.isfile(exe):
        print("❌ 未找到 DICK-HTML.exe，请先运行 PyInstaller 构建")
        return 1
    size_mb = os.path.getsize(exe) / 1024 / 1024
    print(f"✅ DICK-HTML 就绪（exe {size_mb:.1f}MB，目录 {len(os.listdir(DICK_DIR))} 项）")

    # 2) 找 ISCC
    iscc = find_iscc()
    if not iscc:
        print("❌ 未找到 Inno Setup（ISCC.exe）。请安装：winget install JRSoftware.InnoSetup")
        return 1
    print(f"✅ 使用 {iscc}")

    # 3) 编译
    os.makedirs(RELEASE, exist_ok=True)
    print("⏳ 正在编译安装包…")
    r = subprocess.run([iscc, ISS], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("❌ 编译失败：")
        print((r.stdout or "")[-2000:])
        print((r.stderr or "")[-500:])
        return 1

    # 4) 报告
    setup = os.path.join(RELEASE, "DICK-Setup.exe")
    if os.path.isfile(setup):
        mb = os.path.getsize(setup) / 1024 / 1024
        print(f"✅ 安装包已生成：{setup}（{mb:.1f}MB）")
        print("   分发：把 DICK-Setup.exe 发给用户，双击 → 下一步 → 桌面快捷方式直接玩。")
        return 0
    print("❌ 编译完成但未找到输出（检查 OutputDir/OutputBaseFilename）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
