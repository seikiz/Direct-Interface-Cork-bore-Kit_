# -*- coding: utf-8 -*-
"""从发布 zip 里取出加密备份链路，做一次完整的「备份 -> 崩溃 -> 恢复」演练。

这一步和单元测试的区别：
  单元测试用的是工作区里的源文件；这里用的是【用户实际拿到的那两个文件】。
  打包漏文件、版本不一致、路径不对，都只会在这一步暴露。

**没有发布包就跳过**（打印一行 SKIP 后 exit 0）：这个 zip 是 135 MB、不进仓库，
CI（Ubuntu）上必然不存在。以前这里写死了 Windows 绝对路径，于是 CI 上直接
FileNotFoundError —— 那是"本地专用测试在 CI 上必红"的一类问题，不该拿失败来报。
跑得起来的条件（按顺序找）：
    $DICK_RELEASE_ZIP → 工程上一级/DICK-发布/DICK-电脑版.zip → 工程内 _release_out/
"""
import io, os, subprocess, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_zip():
    cands = [os.environ.get("DICK_RELEASE_ZIP"),
             os.path.join(os.path.dirname(ROOT), "DICK-发布", "DICK-电脑版.zip"),
             os.path.join(ROOT, "_release_out", "DICK-电脑版.zip"),
             os.path.join(ROOT, "DICK-电脑版.zip")]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


ZIP = find_zip()
# 用当前解释器：以前写死 utau_env/Scripts/python.exe（Windows 专有路径）
PY = sys.executable

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [OK] {name}")
    else:
        FAIL += 1; print(f"  [FAIL] {name} {detail}")


def main():
    print("=" * 60)
    print("发布包内加密备份链路演练")
    print("=" * 60)

    if ZIP is None:
        print("SKIP：找不到发布包（DICK-电脑版.zip）。")
        print("      这是**本地专用**测试：它要的是打包产物，CI 上没有（zip 不进仓库）。")
        print("      想跑就先用 build_release.py 打出包，或设 DICK_RELEASE_ZIP 指过去。")
        print("RELEASE_BACKUP_E2E_SKIPPED")
        return 0
    print("发布包：%s（%.1f MB）" % (ZIP, os.path.getsize(ZIP) / 1048576.0))

    z = zipfile.ZipFile(ZIP)
    names = [n.replace("\\", "/") for n in z.namelist()]

    print("\n== 1. 发布包内的关键文件 ==")
    want = {
        "顶层解密工具": "dick_backup_tool.py",
        "顶层说明": "备份怎么打开.txt",
        "包内 crypto_core": "_internal/crypto_core.py",
        "AES 原生扩展": "_internal/cryptography/hazmat/bindings/_rust.pyd",
    }
    found = {}
    for label, suffix in want.items():
        hits = [n for n in names if n == suffix or n.endswith("/" + suffix)]
        # 顶层工具要的是根目录那份，不<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌是 _internal 里的
        if suffix == "dick_backup_tool.py":
            hits = [n for n in hits if n == suffix]
        found[label] = hits[0] if hits else None
        check(f"{label} 在包内", bool(hits), suffix)
        if hits:
            print(f"        {hits[0]}  ({z.getinfo(hits[0]).file_size} B)")

    if not all(found.values()):
        print("\n关键文件缺失，后面的演练无法进行")
        return 1

    tmp = tempfile.mkdtemp()
    # 解出顶层工具（用户会拿到的那份）
    tool_path = os.path.join(tmp, "dick_backup_tool.py")
    with open(tool_path, "wb") as f:
        f.write(z.read(found["顶层解密工具"]))
    # 解出包内 crypto_core（模拟 DICK 本体加密时用的那份）
    cc_dir = os.path.join(tmp, "inner")
    os.makedirs(cc_dir, exist_ok=True)
    with open(os.path.join(cc_dir, "crypto_core.py"), "wb") as f:
        f.write(z.read(found["包内 crypto_core"]))

    print("\n== 2. 用【包内 crypto_core】造一份真实备份 ==")
    sys.path.insert(0, cc_dir)
    import crypto_core as packaged_cc
    print("        包内 crypto_core:", os.path.dirname(packaged_cc.__file__))
    print("        码表指纹:", packaged_cc.CODE_MIN, "-", packaged_cc.CODE_MAX, "位")

    payload = {
        "saves/小林.json": '{"aff":88,"name":"小林"}',
        "saves/卡洛·曼奇尼.json": '{"aff":72}',
        "codex/我的故事.codex": "story" * 200,
        "worlds/雨城.json": '{"name":"雨城"}',
        "personas/persona.json": '{"name":"玩家"}',
        "config.json": '{"theme":"dark"}',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zz:
        for n, t in payload.items():
            zz.writestr("DICK_备份_x/" + n, t.encode("utf-8"))
    raw = buf.getvalue()
    PW = packaged_cc.make_recovery_code()
    blob = packaged_cc.encrypt(PW, raw)
    bp = os.path.join(tmp, "DICK_加密备份_演练.dickbackup")
    with open(bp, "wb") as f:
        f.write(blob)
    print(f"        zip {len(raw)} B -> 容器 {len(blob)} B")
    check("包内 crypto_core 能加密", len(blob) > len(raw))
    check("生成口令能通过强度校验", packaged_cc.password_strength(PW)[0] >= 2)

    print("\n== 3. 假设 DICK 已经没了：只用【顶层工具】解密 ==")
    out = os.path.join(tmp, "还原")
    env = dict(os.environ)
    env["DICK_BACKUP_PW"] = PW
    env["PYTHONPATH"] = ""
    env["PYTHONIOENCODING"] = "utf-8"
    # 注意不要用 -I：它会忽略 PYTHONIOENCODING，子进程就按 GBK 输出中文，
    # 这边按 UTF-8 解会得到乱码、断言必然失败。隔离靠 PYTHONPATH="" 就够了。
    r = subprocess.run([PY, tool_path, "解密", bp, "-o", out],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, cwd=tmp)
    check("顶层工具退出码 0", r.returncode == 0, (r.stderr or "")[:400])
    if r.returncode == 0:
        okall = True
        for n, t in payload.items():
            p = os.path.join(out, n.replace("/", os.sep))
            if not os.path.isfile(p) or open(p, encoding="utf-8").read() != t:
                okall = False
                print("        不一致:", n, "存在=", os.path.isfile(p))
        check("还原内容逐字节一致", okall)
        check("没有多出包裹目录",
              not any(d.startswith("DICK_备份") for d in os.listdir(out)),
              str(os.listdir(out)))
    else:
        print(r.stdout)

    print("\n== 4. 顶层工具自检（码表必须与加密端一致）==")
    r2 = subprocess.run([PY, tool_path, "查看", bp],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env, cwd=tmp)
    check("查看 退出码 0", r2.returncode == 0, (r2.stderr or "")[:300])
    check("显示 AES-256-GCM", "AES-256-GCM" in r2.stdout, r2.stdout[:200])

    print("\n== 5. 错口令必须失败（且在无 DICK 环境下）==")
    env2 = dict(env); env2["DICK_BACKUP_PW"] = PW + "wrong"
    r3 = subprocess.run([PY, tool_path, "解密", bp, "-o", out + "2"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env2, cwd=tmp)
    check("错口令退出码非 0", r3.returncode != 0)
    check("提示口令错误", "口令错误" in (r3.stdout + r3.stderr),
          (r3.stdout + r3.stderr)[:200])

    print("\n" + "=" * 60)
    print(f"通过 {PASS} / 失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
