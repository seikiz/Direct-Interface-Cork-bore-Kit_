# -*- coding: utf-8 -*-
"""modules/codex/pack.py —— 包的目录与 zip 格式（自带格式，只认传进来的路径）

搬家来源：`codex_core.py` 的 `make_template` / `import_folder` / `_wire_resources` /
`make_sample_package` / `_write_placeholder_png` / `_write_silent_wav` / `export_zip` /
`import_zip` / `_safe_name`，**目录布局、zip 结构与文件名净化规则一字未改**。

一个 CODEX 包就是一个目录：
    <包名>/codex.json  +  sprites/ bg/ bgm/ voice/
`export_zip` / `import_zip` 是它的交换格式；`make_sample_package` 造的"示例·夏日祭"
带占位 PNG 与静音 WAV，所以零素材也能立刻跑起来。

**这一层不认宿主**：包目录一律由调用方（或 `service.bind(host)` 给的 codex_dir）指路，
块自己不去猜"用户数据目录在哪"。
"""

import json
import os
import shutil
import struct
import zipfile

from .constants import SUBDIRS, classify_file


def make_template(name="我的故事"):
    """生成一个开箱即用的示例剧本（可直接播放，验证播放器）"""
    return {
        "name": name,
        "author": "",
        "intro": "这是一个 CODEX 示例剧本：改改 codex.json 就能做出你的专属 GALGAME。\n"
                 "把立绘放 sprites/、背景放 bg/、音乐放 bgm/、配音放 voice/，"
                 "然后在 scenes 里引用即可（相对路径）。",
        "scenes": [
            {
                "id": "s1",
                "bg": "bg/教室.png",
                "bgm": "bgm/主题曲.mp3",
                "lines": [
                    {"note": "（清晨的教室里，阳光透过窗户洒进来。）"},
                    {"speaker": "咲", "sprite": "sprites/咲_立绘.png",
                     "voice": "voice/01.wav", "text": "早上好！今天也一起走吧。"},
                    {"choice": [
                        {"text": "牵起她的手", "goto": "s2"},
                        {"text": "假装没听见", "goto": "s3"},
                    ]},
                    {"end": "结局：日常的一天"},
                ],
            },
            {
                "id": "s2",
                "bg": "bg/走廊.png",
                "lines": [
                    {"speaker": "咲", "sprite": "sprites/咲_笑.png", "text": "（脸微微一红）嗯……走吧。"},
                    {"jump": "s1"},
                ],
            },
            {
                "id": "s3",
                "bg": "bg/走廊.png",
                "lines": [
                    {"speaker": "咲", "sprite": "sprites/咲_怒.png", "text": "喂！我在跟你说话呢！"},
                    {"end": "结局：惹她生气了"},
                ],
            },
        ],
    }


def import_folder(src_dir, dest_root, name):
    """扫描 src_dir（或其子目录）里的资源，按类别复制到
    dest_root/<name>/{sprites,bg,bgm,voice}/；若已有 codex.json 则一并复制。
    返回 {"ok": bool, "moved": {kind: count}, "msg": str}"""
    import shutil
    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        return {"ok": False, "msg": "源文件夹不存在"}
    dst = os.path.join(dest_root, name)
    os.makedirs(dst, exist_ok=True)
    counts = {k: 0 for k in SUBDIRS}
    copied_json = False
    for root, _dirs, files in os.walk(src_dir):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, src_dir)
            rel_norm = rel.replace("\\", "/")
            # codex.j<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌son 原样保留
            if fn == "codex.json" and not copied_json:
                try:
                    shutil.copy2(full, os.path.join(dst, "codex.json"))
                    copied_json = True
                except Exception:
                    pass
                continue
            kind = classify_file(fn)
            # 已在类别子目录里的文件优先按所在目录归类
            parts = rel_norm.split("/")
            if len(parts) > 1 and parts[0].lower() in SUBDIRS:
                kind = parts[0].lower()
            if not kind:
                continue
            out_dir = os.path.join(dst, kind)
            os.makedirs(out_dir, exist_ok=True)
            out_name = os.path.basename(fn)
            i = 1
            while os.path.exists(os.path.join(out_dir, out_name)):
                stem, ext = os.path.splitext(out_name)
                out_name = f"{stem}_{i}{ext}"
                i += 1
            try:
                shutil.copy2(full, os.path.join(out_dir, out_name))
                counts[kind] += 1
            except Exception:
                pass
    if not copied_json:
        # 没有现成剧本 → 自动生成：以文件名映射到示例引用
        tpl = make_template(name)
        # 把实际存在的资源名写进场景引用，保证播放器开箱能显示
        tpl = _wire_resources(tpl, dst)
        try:
            with open(os.path.join(dst, "codex.json"), "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    total = sum(counts.values())
    return {"ok": True, "moved": counts, "msg": f"导入 {total} 个资源文件"}


def _wire_resources(tpl, dst):
    """把导入的实际文件名回填到模板场景里（立绘/背景/音乐/配音各取第一个）"""
    def first(kind):
        d = os.path.join(dst, kind)
        try:
            for fn in sorted(os.listdir(d)):
                return f"{kind}/{fn}"
        except Exception:
            return None
    sprite = first("sprites")
    bg = first("bg")
    bgm = first("bgm")
    voice = first("voice")
    scenes = tpl.get("scenes") or []
    for sc in scenes:
        if bg:
            sc["bg"] = bg
        if bgm:
            sc["bgm"] = bgm
        for ln in sc.get("lines") or []:
            if isinstance(ln, dict) and "speaker" in ln:
                if sprite:
                    ln.setdefault("sprite", sprite)
                if voice:
                    ln.setdefault("voice", voice)
    return tpl


def make_sample_package(dest_root, name="示例·夏日祭"):
    """生成一个带占位资源的示例 CODEX 包：1x1 渐变立绘/背景（PNG）、
    静音 BGM/配音（WAV），剧本引用真实文件 → 一键即可播放。
    返回 (ok, 包目录)"""
    import shutil
    import struct
    dst = os.path.join(dest_root, _safe_name(name))
    try:
        shutil.rmtree(dst, ignore_errors=True)
        for k in SUBDIRS:
            os.makedirs(os.path.join(dst, k), exist_ok=True)
        # --- 占位立绘（渐变圆角少女剪影，纯代码 PNG） ---
        sprites = {
            "咲_立绘.png": (255, 210, 130),
            "咲_笑.png": (255, 220, 150),
            "咲_怒.png": (255, 150, 120),
        }
        for fn, color in sprites.items():
            _write_placeholder_png(os.path.join(dst, "sprites", fn), color, w=420, h=720)
        bgs = {"教室.png": (120, 160, 200), "走廊.png": (90, 110, 140)}
        for fn, color in bgs.items():
            _write_placeholder_png(os.path.join(dst, "bg", fn), color, w=960, h=540)
        # --- 静音音频（WAV 静音 1 秒） ---
        _write_silent_wav(os.path.join(dst, "bgm", "主题曲.wav"))
        _write_silent_wav(os.path.join(dst, "voice", "01.wav"))
        # --- 剧本 ---
        tpl = make_template(name)
        tpl["intro"] = "这是 DICK 自带的一键示例包：直接点 ▶️ 播放就能看到立绘/背景/选项/结局。\n" \
                       "去 sprites/、bg/、bgm/、voice/ 替换成你自己的素材，再改 codex.json 就是你的专属 GALGAME。"
        tpl["scenes"][0]["bg"] = "bg/教室.png"
        tpl["scenes"][0]["bgm"] = "bgm/主题曲.wav"
        tpl["scenes"][0]["lines"][1]["sprite"] = "sprites/咲_立绘.png"
        tpl["scenes"][0]["lines"][1]["voice"] = "voice/01.wav"
        tpl["scenes"][1]["lines"][0]["sprite"] = "sprites/咲_笑.png"
        tpl["scenes"][2]["lines"][0]["sprite"] = "sprites/咲_怒.png"
        with open(os.path.join(dst, "codex.json"), "w", encoding="utf-8") as f:
            json.dump(tpl, f, ensure_ascii=False, indent=2)
        return True, dst
    except Exception as e:
        return False, str(e)


def _write_placeholder_png(path, rgb, w=420, h=720):
    """纯代码生成一张垂直渐变 PNG（无 PIL 依赖）"""
    import zlib
    r0, g0, b0 = rgb
    rows = []
    for y in range(h):
        t = y / max(1, h - 1)
        # 顶部亮、底部暗的渐变；中间一个简单的"头部/肩部"色块
        r = int(r0 * (1 - t * 0.45))
        g = int(g0 * (1 - t * 0.45))
        b = int(b0 * (1 - t * 0.45))
        row = bytearray([0])  # filter: None
        for x in range(w):
            # 简单剪影：头部圆 + 肩部梯形（深色）
            cx, cy = w // 2, h // 3
            if (x - cx) ** 2 + (y - cy) ** 2 < (h // 9) ** 2:
                row += bytes([r // 2, g // 2, b // 2])
            elif y > h // 3 and y < h * 0.8 and abs(x - cx) < (w // 5) * (1 - (y - h // 3) / (h * 0.5) * 0.5):
                row += bytes([r // 2, g // 2, b // 2])
            else:
                row += bytes([r, g, b])
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def _write_silent_wav(path, seconds=1, rate=22050):
    """生成静音 WAV（可播放、无爆音）"""
    import struct
    n = int(rate * seconds)
    data = b"\x00\x00" * n
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + \
          b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + \
          b"data" + struct.pack("<I", len(data))
    with open(path, "wb") as f:
        f.write(hdr + data)


def export_zip(pkg_dir, zip_path):
    """把 CODEX 包打成 zip（含 codex.json 与全部资源）"""
    pkg_dir = os.path.abspath(pkg_dir)
    if not os.path.isdir(pkg_dir):
        return False
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(pkg_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, pkg_dir).replace("\\", "/")
                z.write(full, rel)
    return True


def import_zip(zip_path, dest_root):
    """解压 zip 到 dest_root/<包名>/（包名 = zip 内 codex.json 的 name 或压缩包名）。
    返回 (ok, name, msg)"""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            # 找 codex.json 的顶层目录
            top = None
            for n in names:
                if n.endswith("codex.json") and n.count("/") <= 1:
                    top = os.path.dirname(n)
                    break
            name = os.path.basename(zip_path)
            low_name = name.lower()
            if low_name.endswith(".zip"):
                name = name[:-4]
            elif low_name.endswith(".codex"):
                name = name[:-6]
            if top:
                try:
                    raw = z.read(os.path.join(top, "codex.json")).decode("utf-8")
                    data = json.loads(raw)
                    if str(data.get("name") or "").strip():
                        name = str(data["name"]).strip()
                except Exception:
                    pass
            dst = os.path.join(dest_root, _safe_name(name))
            os.makedirs(dst, exist_ok=True)
            real_dst = os.path.realpath(dst)
            for n in names:
                if n.endswith("/"):
                    continue
                if top:
                    rel = os.path.relpath(n, top).replace("\\", "/")
                else:
                    rel = n
                # 防 zip 泄路径（zip-slip）：拒绝 .. 逃逸到目标目录之外
                if not rel or rel.startswith("..") or ".." in rel.split("/"):
                    continue
                out = os.path.join(dst, rel)
                if os.path.commonpath([real_dst, os.path.realpath(out)]) != real_dst:
                    continue
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with z.open(n) as src, open(out, "wb") as f:
                    f.write(src.read())
            return True, _safe_name(name), "导入成功"
    except Exception as e:
        return False, "", f"导入失败：{e}"


def _safe_name(name):
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00']:
        name = name.replace(ch, "_")
    # 防目录穿越：'..' 与首尾 '.' 是危险路径段
    name = name.replace("..", "_").strip(". ")
    return (name or "未命名").strip()[:60]
