# -*- coding: utf-8 -*-
"""mem_scene.py —— 记忆的场景隔离（私聊 / 群聊），且随时可以互读。

为什么要这一层
--------------
以前的目录是 `memory/<角色>/`：不管这段对话是私聊还是群聊，记忆都堆在同一处。
结果就是"群聊里发生的事，被私聊当成两人之间发生过"——这不是角色演得好，
是**结构上根本没分开**。mem_isolate.py 能查出"混了"，但它只审计、不搬家。

这一层做的是结构：
    memory/private/<角色>/{chain.json, archive-*.json, summary-*.md, facts.json, rapport.json}
    memory/group/<角色>/…
    memory/<场景>/_world/…        世界记忆按场景各一份（群聊的世界 ≠ 私聊的世界）
    memory/<角色>/…               老布局：只读回退，不删不搬（迁移由 migrate_legacy 显式做）

"随时可以读取"
--------------
场景是**存储维度**，不是访问闸门。read_all() 一次给出两个场景的完整记忆，
调用方（界面/记忆面板/提示词组装）想读哪个读哪个，不需要"切场景"。

约定
----
  · 角色名只允许单层名字（不许路径分隔符 / .. / 空）
  · 写操作只写 `<场景>/` 下；老布局永远只读
  · 事实（facts）与相处推测（rapport）分开两个文件，永不合并
"""
from __future__ import annotations

import io
import json
import os
import re
import time

SCENES = ("private", "group")
SCENE_ALIASES = {
    "private": "private", "私聊": "private", "单聊": "private", "dm": "private",
    "group": "group", "群聊": "group", "群": "group", "gc": "group",
}
WORLD_DIR_NAME = "_world"
LEGACY_CHAIN = "chain.json"
FACTS_FILE = "facts.json"
RAPPORT_FILE = "rapport.json"
SUMMARY_PREFIX = "summary-"
_SAFE_ROLE = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]{1,64}$")


class SceneError(ValueError):
    """场景或角色名不合法。"""


def norm_scene(scene):
    """把 '私聊' / 'dm' / 'group' 之类统一成 'private' / 'group'。"""
    key = (scene or "").strip().lower()
    if key in SCENE_ALIASES:
        return SCENE_ALIASES[key]
    raise SceneError("未知场景：%r（只支持 private/私聊、group/群聊）" % (scene,))


def check_role(role):
    name = (role or "").strip()
    if not name or not _SAFE_ROLE.match(name) or name in (".", ".."):
        raise SceneError("角色名不合法：%r" % (role,))
    return name


# ---------------- 路<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌径 ----------------
def scene_root(memory_dir, scene):
    s = norm_scene(scene)
    return os.path.join(memory_dir, s)


def role_dir(memory_dir, scene, role):
    base = scene_root(memory_dir, scene)
    return os.path.join(base, check_role(role))


def world_dir(memory_dir, scene):
    base = scene_root(memory_dir, scene)
    return os.path.join(base, WORLD_DIR_NAME)


def ensure_role(memory_dir, scene, role):
    d = role_dir(memory_dir, scene, role)
    os.makedirs(d, exist_ok=True)
    return d


def ensure_world(memory_dir, scene):
    d = world_dir(memory_dir, scene)
    os.makedirs(d, exist_ok=True)
    return d


# ---------------- 读写 ----------------
def _read_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def read_chain(memory_dir, scene, role):
    return _read_json(os.path.join(role_dir(memory_dir, scene, role), LEGACY_CHAIN), [])


def write_chain(memory_dir, scene, role, entries):
    return _write_json(os.path.join(role_dir(memory_dir, scene, role), LEGACY_CHAIN), entries)


def read_facts(memory_dir, scene, role):
    """事实：用户明确说过/做过的事。每条带 source（消息 id）与 t（时间戳）。"""
    return _read_json(os.path.join(role_dir(memory_dir, scene, role), FACTS_FILE), [])


def write_facts(memory_dir, scene, role, facts):
    return _write_json(os.path.join(role_dir(memory_dir, scene, role), FACTS_FILE), facts)


def read_rapport(memory_dir, scene, role):
    """相处推测：模型自己觉得的亲近度/印象。**不进事实表**，永不与 facts 合并。"""
    return _read_json(os.path.join(role_dir(memory_dir, scene, role), RAPPORT_FILE), {})


def write_rapport(memory_dir, scene, role, rapport):
    return _write_json(os.path.join(role_dir(memory_dir, scene, role), RAPPORT_FILE), rapport)


def read_summary(memory_dir, scene, role):
    d = role_dir(memory_dir, scene, role)
    if not os.path.isdir(d):
        return ""
    names = sorted(n for n in os.listdir(d) if n.startswith(SUMMARY_PREFIX) and n.endswith(".md"))
    if not names:
        return ""
    with io.open(os.path.join(d, names[-1]), encoding="utf-8") as f:
        return f.read()


def write_summary(memory_dir, scene, role, text, stamp=None):
    d = ensure_role(memory_dir, scene, role)
    name = "%s%s.md" % (SUMMARY_PREFIX, stamp or time.strftime("%Y%m%d-%H%M%S"))
    path = os.path.join(d, name)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def append_archive(memory_dir, scene, role, entries, stamp=None):
    """原文归档：只进不出（摘要留在主记忆，原文进 archive）。"""
    d = ensure_role(memory_dir, scene, role)
    name = "archive-%s.json" % (stamp or time.strftime("%Y%m%d-%H%M%S"))
    path = os.path.join(d, name)
    old = _read_json(path, [])
    old.extend(entries)
    _write_json(path, old)
    return path


def archive_files(memory_dir, scene, role):
    d = role_dir(memory_dir, scene, role)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d)
                  if n.startswith("archive-") and n.endswith(".json"))


# ---------------- 随时可读 ----------------
def read_one(memory_dir, scene, role):
    """读单个场景的记忆包（读老布局也可以：不存在就返回空壳）。"""
    s = norm_scene(scene)
    return {
        "scene": s,
        "role": check_role(role),
        "exists": os.path.isdir(role_dir(memory_dir, s, role)),
        "chain": read_chain(memory_dir, s, role),
        "facts": read_facts(memory_dir, s, role),
        "rapport": read_rapport(memory_dir, s, role),
        "summary": read_summary(memory_dir, s, role),
        "archives": len(archive_files(memory_dir, s, role)),
    }


def read_all(memory_dir, role):
    """一次给出**两个场景**的记忆——场景是存储维度，不是访问闸门。"""
    return {s: read_one(memory_dir, s, role) for s in SCENES}


def read_legacy(memory_dir, role):
    """老布局（memory/<角色>/）：只读回退，方便迁移期两边都看得见。"""
    d = os.path.join(memory_dir, check_role(role))
    if not os.path.isdir(d):
        return None
    return {
        "legacy": True,
        "chain": _read_json(os.path.join(d, LEGACY_CHAIN), []),
        "facts": _read_json(os.path.join(d, FACTS_FILE), []),
        "summary": read_summary(memory_dir, "private", role) if False else _read_summary_in(d),
        "archives": len([n for n in os.listdir(d) if n.startswith("archive-")]),
    }


def _read_summary_in(d):
    names = sorted(n for n in os.listdir(d) if n.startswith(SUMMARY_PREFIX) and n.endswith(".md"))
    if not names:
        return ""
    with io.open(os.path.join(d, names[-1]), encoding="utf-8") as f:
        return f.read()


def list_roles(memory_dir, scene):
    d = scene_root(memory_dir, scene)
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d)
                  if os.path.isdir(os.path.join(d, n)) and n != WORLD_DIR_NAME)


def list_legacy_roles(memory_dir):
    if not os.path.isdir(memory_dir):
        return []
    out = []
    for n in sorted(os.listdir(memory_dir)):
        p = os.path.join(memory_dir, n)
        if os.path.isdir(p) and n not in SCENES and n != WORLD_DIR_NAME:
            out.append(n)
    return out


def snapshot(memory_dir):
    """一张表：每个场景有哪些角色、各有几条事实/归档。给记忆面板用。"""
    out = {}
    for s in SCENES:
        rows = {}
        for role in list_roles(memory_dir, s):
            rows[role] = {
                "facts": len(read_facts(memory_dir, s, role)),
                "archives": len(archive_files(memory_dir, s, role)),
                "has_summary": bool(read_summary(memory_dir, s, role)),
            }
        out[s] = rows
    return out


# ---------------- 迁移（显式调用） ----------------
def migrate_legacy(memory_dir, scene="private", dry_run=False):
    """把老布局 `memory/<角色>/` 挪进 `memory/<场景>/<角色>/`。

    默认归到 private（一对一对话），返回报告；dry_run 只算不动。
    老布局的 `memory/chain.json`（全局索引）**不整份移动** —— 那是所有角色混装的，
    拆分属于 mem_isolate 的职责，这里只搬目录。
    """
    s = norm_scene(scene)
    moved, skipped = [], []
    for role in list_legacy_roles(memory_dir):
        src = os.path.join(memory_dir, role)
        dst = os.path.join(scene_root(memory_dir, s), role)
        if os.path.exists(dst):
            skipped.append(role)
            continue
        moved.append(role)
        if not dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
    return {"scene": s, "moved": moved, "skipped": skipped, "dry_run": bool(dry_run)}
