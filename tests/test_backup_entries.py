# -*- coding: utf-8 -*-
"""
备份内容与还原映射测试。

为什么单独测这个：
  「备份能不能用」和「还原会不会覆盖错东西」是两件事。
  前者已经测过（test_backup_encrypted），这里测后者 ——
  还原逻辑写错不是报错，是静默覆盖用户数据。

跑法：utau_env\\Scripts\\python.exe tests\\test_backup_entries.py
"""

import io
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def load_app_class():
    import importlib.util
    path = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
    spec = importlib.util.spec_from_file_location("dick_app_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dick_app_mod"] = mod
    spec.loader.exec_module(mod)          # 有 __main__ 守卫，不会起 GUI
    return mod


def make_fake_app(cls, base):
    """不跑 __init__（那会拉 GUI），手工装配还原所需的字段"""
    self = cls.__new__(cls)
    self.base_dir = base
    self.save_dir = os.path.join(base, "saves")
    self.world_dir = os.path.join(base, "worlds")
    self.preset_dir = os.path.join(base, "presets")
    self.persona_dir = os.path.join(base, "personas")
    self.codex_dir = os.path.join(base, "codex")
    self.config_file = os.path.join(base, "config.json")
    for d in (self.save_dir, self.world_dir, self.preset_dir,
              self.persona_dir, self.codex_dir):
        os.makedirs(d, exist_ok=True)
    return self


def test_backup_entries_include_codex():
    print("\n== 1. 备份内容覆盖 ==")
    mod = load_app_class()
    base = tempfile.mkdtemp()
    app = make_fake_app(mod.HtmlApp, base)

    # 造点 codex 内容：一个<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌顶层文件 + 一个带子目录的包
    with open(os.path.join(app.codex_dir, "我的故事.codex"), "wb") as f:
        f.write(b"story-bytes")
    pkg = os.path.join(app.codex_dir, "第二部")
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"title": "第二部"}, f, ensure_ascii=False)
    with open(os.path.join(pkg, "ch1.md"), "w", encoding="utf-8") as f:
        f.write("第一章内容")

    # 最小可用的其余字段
    app.roles = [{"name": "小林", "file": "xiaolin.json", "prompt": "你是小林",
                  "data": {"aff": 88}}]
    app.selected_roles = set()
    app.worlds = [{"name": "雨城", "entries": ["设定A"]}]
    app.persona = {"name": "玩家"}
    app.config = {"theme": "dark", "model": "deepseek-flash"}
    app._safe_name = lambda s: (s or "x").replace("/", "_")
    app._encrypt_config_secrets = lambda cfg: cfg

    entries = app._backup_entries()
    names = [p for p, _ in entries]
    print("     条目:", names)
    check("含 saves/", any(n.startswith("saves/") for n in names))
    check("含 worlds/", any(n.startswith("worlds/") for n in names))
    check("含 personas/", any(n.startswith("personas/") for n in names))
    check("含 config.json", "config.json" in names)
    check("含 codex 顶层文件", "codex/我的故事.codex" in names)
    check("含 codex 子目录文件", "codex/第二部/meta.json" in names,
          "子目录未递归")
    check("含 codex 子目录全部文件", "codex/第二部/ch1.md" in names)
    check("codex 条目数 = 3", sum(1 for n in names if n.startswith("codex/")) == 3)

    # 往返：zip → 加密 → 解密 → 解压，内容必须一致
    import crypto_core as c
    raw_zip = app._zip_entries(entries, "DICK_备份_test")
    blob = c.encrypt("test-password-123456", raw_zip)
    got = c.decrypt("test-password-123456", blob)
    z = zipfile.ZipFile(io.BytesIO(got))
    inner = {n[len("DICK_备份_test/"):]: z.read(n) for n in z.namelist()}
    ok = all(inner.get(p) == d for p, d in entries)
    check("加密往返后每个条目逐字节一致", ok)
    return mod, base


def test_restore_mapping(mod, base):
    print("\n== 2. 还原落盘位置 ==")
    src = make_fake_app(mod.HtmlApp, tempfile.mkdtemp())
    # 准备一份 zip：结构 <root>/saves|x|worlds|x|personas|x|codex|x|config.json
    payload = {
        "saves/xiaolin.json": b'{"aff":90}',
        "worlds/雨城.json": '{"name":"雨城"}'.encode("utf-8"),
        "personas/persona.json": '{"name":"玩家"}'.encode("utf-8"),
        "codex/我的故事.codex": b"story",
        "codex/第二部/ch1.md": "正文".encode("utf-8"),
        "config.json": b'{"theme":"dark"}',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p, d in payload.items():
            z.writestr("DICK_备份_test/" + p, d)

    dst = make_fake_app(mod.HtmlApp, tempfile.mkdtemp())
    z = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    r = dst._restore_from_zip(z, os.path.join(dst.save_dir, "backup", "r1"))
    print("     统计:", r)
    check("saves 还原 1", r["saves"] == 1)
    check("worlds 还原 1", r["worlds"] == 1)
    check("personas 还原 1", r["personas"] == 1)
    check("config 还原 1", r["config"] == 1)
    check("codex 还原 2（含子目录）", r["codex"] == 2, str(r))

    check("存档落到 saves/", os.path.isfile(os.path.join(dst.save_dir, "xiaolin.json")))
    check("世界卡落到 worlds/", os.path.isfile(os.path.join(dst.world_dir, "雨城.json")))
    check("config 落到根", os.path.isfile(dst.config_file))
    check("codex 顶层文件落地",
          os.path.isfile(os.path.join(dst.codex_dir, "我的故事.codex")))
    check("codex 子目录层级保留",
          os.path.isfile(os.path.join(dst.codex_dir, "第二部", "ch1.md")))
    with open(os.path.join(dst.codex_dir, "第二部", "ch1.md"), encoding="utf-8") as f:
        check("codex 子目录内容正确", f.read() == "正文")


def test_zip_slip_blocked(mod):
    print("\n== 3. 路径穿越必须被挡住 ==")
    dst = make_fake_app(mod.HtmlApp, tempfile.mkdtemp())
    outside = os.path.join(os.path.dirname(dst.base_dir), "OUTSIDE_EVIL.txt")
    if os.path.exists(outside):
        os.remove(outside)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("DICK_备份_x/codex/../../../OUTSIDE_EVIL.txt", b"pwned")
        z.writestr("DICK_备份_x/saves/../../OUTSIDE2.txt", b"pwned")
        z.writestr("DICK_备份_x/codex/ok.txt", b"fine")
    z = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    r = dst._restore_from_zip(z, os.path.join(dst.save_dir, "backup", "r2"))
    print("     统计:", r)
    check("穿越条目不落地", not os.path.exists(outside))
    check("正常条目仍然还原", r["codex"] == 1, str(r))
    check("正常条目内容正确",
          open(os.path.join(dst.codex_dir, "ok.txt"), "rb").read() == b"fine")

    # 每个穿越变体都别落地
    for evil in ["DICK_x/codex/../../evil1.txt",
                 "DICK_x/saves/..\\..\\evil2.txt",
                 "DICK_x/../../../../evil3.txt"]:
        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, "w") as z2:
            z2.writestr(evil, b"x")
        d2 = make_fake_app(mod.HtmlApp, tempfile.mkdtemp())
        z2 = zipfile.ZipFile(io.BytesIO(buf2.getvalue()))
        d2._restore_from_zip(z2, os.path.join(d2.save_dir, "b"))
        leaked = [f for f in os.listdir(os.path.dirname(d2.base_dir))
                  if f.startswith("evil")]
        check(f"穿越被挡 {evil[:34]}", not leaked, str(leaked))


def test_backup_preserves_existing(mod):
    print("\n== 4. 覆盖前留原件 ==")
    dst = make_fake_app(mod.HtmlApp, tempfile.mkdtemp())
    old = os.path.join(dst.save_dir, "xiaolin.json")
    with open(old, "wb") as f:
        f.write(b'{"aff":10}')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("DICK_x/saves/xiaolin.json", b'{"aff":99}')
    z = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
    bak = os.path.join(dst.save_dir, "backup", "r3")
    r = dst._restore_from_zip(z, bak)
    check("新内容已写入", open(old, "rb").read() == b'{"aff":99}')
    saved = os.path.join(bak, "xiaolin.json")
    check("原件已留底", os.path.isfile(saved))
    if os.path.isfile(saved):
        check("留底内容 = 覆盖前的值", open(saved, "rb").read() == b'{"aff":10}')


if __name__ == "__main__":
    print("=" * 56)
    print("备份内容 / 还原映射测试")
    print("=" * 56)
    mod, base = test_backup_entries_include_codex()
    test_restore_mapping(mod, base)
    test_zip_slip_blocked(mod)
    test_backup_preserves_existing(mod)
    print("\n" + "=" * 56)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
