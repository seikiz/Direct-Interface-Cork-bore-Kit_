# -*- coding: utf-8 -*-
"""world_packs.py —— 世界卡库：随包附带的成套世界卡（含常识参数）

为什么要有它
------------
1. `worlds/` 被 .gitignore 忽略 —— 仓库里其实**一张世界卡都没有**，
   全新 clone 或打包后会得到空的世界列表（"本机有、别人没有"的老毛病）。
2. 空间层/生活层要靠世界卡才知道"这是哪个年代、哪张地图"。
   没有卡就只能默认现代都市口径 —— 于是"大明"和"仙侠"里都会出现地铁。

所以：库里的一等公民是**卡包**（`world_packs/*.json`，受版本控制），
每个包就是一张标准世界卡，`params` 里带 `era` / `era_kind` / `region` / `space`（地图 JSON）。
装包 = 把它拷进用户的 `worlds/`（**不覆盖**同名，除非显式 overwrite）。

用法（也可以在界面里用 /世界包）：
    import world_packs as wp
    wp.list_packs()                      # [{file, name, era, kind, description, places}]
    wp.install("江南水乡·明末", worlds_dir)   # → (ok, msg)
"""
import io
import json
import os
import re
import shutil

try:
    import app_paths
except Exception:                     # pragma: no cover
    app_paths = None

DIRNAME = "world_packs"


def pack_dirs(extra=None):
    """卡包目录：用户目录（可自己丢包进去）优先，其次随包内置目录"""
    out = []
    if extra:
        out.append(extra)
    try:
        base = app_paths.get_base_dir() if app_paths else None
    except Exception:
        base = None
    if base:
        out.append(os.path.join(base, DIRNAME))
    # 源码工程根 / PyInsta<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ller 的 _MEIPASS
    here = os.path.dirname(os.path.abspath(__file__))
    out.append(os.path.join(here, DIRNAME))
    try:
        import sys
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            out.append(os.path.join(mei, DIRNAME))
    except Exception:
        pass
    seen, uniq = set(), []
    for d in out:
        if d and d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def _read_card(path):
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not str(data.get("name") or "").strip():
        raise ValueError("不是有效的世界卡（缺 name）")
    return data


def _space_of(card):
    """把 params.space 解出来（字符串或 dict 都认）"""
    params = card.get("params") if isinstance(card.get("params"), dict) else {}
    sp = params.get("space")
    if isinstance(sp, str):
        try:
            sp = json.loads(sp)
        except Exception:
            sp = None
    return sp if isinstance(sp, dict) else {}


def list_packs(extra=None):
    """列出所有可装的卡包（同名的以先出现的目录为准）"""
    out, seen = [], set()
    for d in pack_dirs(extra):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json") or fn.startswith("."):
                continue
            p = os.path.join(d, fn)
            try:
                card = _read_card(p)
            except Exception as e:
                print("[world_packs] 跳过坏卡包 %s: %s" % (fn, e))
                continue
            sp = _space_of(card)
            name = str(card["name"])
            if name in seen:
                continue
            seen.add(name)
            out.append({
                "file": fn,
                "path": p,
                "name": name,
                "description": str(card.get("description") or ""),
                "era": str((card.get("params") or {}).get("era") or ""),
                "kind": str((card.get("params") or {}).get("era_kind") or ""),
                "region": str((card.get("params") or {}).get("region") or ""),
                "places": len(sp.get("places") or []),
                "rooms": len(sp.get("rooms") or []),
                "dir": d,
            })
    return out


def find_pack(name, extra=None):
    want = str(name or "").strip()
    if not want:
        return None
    for p in list_packs(extra):
        if p["name"] == want or p["file"] == want or os.path.splitext(p["file"])[0] == want:
            return p
    for p in list_packs(extra):          # 退一步：包含匹配
        if want in p["name"]:
            return p
    return None


def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', "_", str(name or "").strip()) or "world"


def worlds_dir():
    try:
        base = app_paths.get_base_dir() if app_paths else None
    except Exception:
        base = None
    base = base or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "worlds")


def install(name, target_dir=None, overwrite=False):
    """把卡包装进用户的世界卡目录。返回 (ok, msg)

    默认**不覆盖**同名文件 —— 用户可能已经在卡上改过内容；
    要覆盖得显式 overwrite=True（那时也会先留一份 backup）。
    """
    pack = find_pack(name)
    if not pack:
        return False, "没找到这个世界卡包：%s" % name
    dst_dir = target_dir or worlds_dir()
    try:
        os.makedirs(dst_dir, exist_ok=True)
    except Exception as e:
        return False, "世界卡目录建不出来：%s" % e
    dst = os.path.join(dst_dir, safe_name(pack["name"]) + ".json")
    if os.path.exists(dst) and not overwrite:
        return False, "已经有一张同名的世界卡了（%s）。要覆盖请用 /世界包 装 <名字> --force" % os.path.basename(dst)
    try:
        if os.path.exists(dst):
            try:
                import save_guard
                save_guard.backup_file(dst)
            except Exception:
                pass
        card = _read_card(pack["path"])
        tmp = dst + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(card, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dst)
    except Exception as e:
        return False, "装包失败：%s" % e
    return True, "已装入：%s → %s" % (pack["name"], os.path.basename(dst))


def describe(pack):
    """人话摘要（给命令面板用）"""
    if not pack:
        return ""
    bits = []
    if pack.get("era"):
        bits.append("年代 " + pack["era"])
    if pack.get("kind"):
        bits.append("设定 " + pack["kind"])
    if pack.get("region"):
        bits.append("地域 " + pack["region"])
    if pack.get("places"):
        bits.append("%d 个地点" % pack["places"])
    if pack.get("rooms"):
        bits.append("%d 间屋" % pack["rooms"])
    return "%s｜%s" % (pack["name"], "、".join(bits) if bits else "（无参数）")
