# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   mem_isolate.py —— 记忆隔离检测（谁的记忆里混进了别人）
#
#   为什么需要它：
#     现在的记忆归档是「memory/<角色>.partN.json + 全局 chain.json」，
#     而且"当前角色"是靠**文件修改时间**猜的（找最近改动的存档）。
#     群聊里 `_save_tree` 只写【第一个选中角色】的文件 → 归档跟着"最后被保存的那个人"走。
#     也就是说：**结构上并不保证专属记忆**，只是文件名叫得像。
#     所以先要一个"判据"——能对真实数据说清：谁和谁混了、混在哪一层。
#
#   检测口径（只报**结构性**问题，避免误报）：
#     ✅ 会报：角色目录里出现别人的归档/key；全局 chain 混装多角色；
#              索引里指向的 part 文件不属于这个角色；世界记忆混进角色内容
#     ⚠️ 只提示：角色文件里出现别的角色名字
#              —— 群聊里是**正常**的（同一场对话本来就互相出现），所以不能当错误
#
#   目录约定（"人物专属 + 世界共享"）：
#       memory/<角色>/chain.json          该角色自己的归档索引
#       memory/<角色>/<角色>.part1.json   该角色的原文归档
#       memory/<角色>/summary-*.md        该角色的压缩记忆
#       memory/_world/chain.json          世界记忆（所有角色共享，可同时演进）
#       memory/_world/…                   世界侧归档（事件、时间线、世界书快照）
#
#   用法：
#       import mem_isolate
#       rep = mem_isolate.audit("memory", role_names=["咲", "老约翰"])
#       print(rep["verdict"], rep["problems"])
# ============================================================

import io
import json
import os
import re

WORLD_DIR_NAME = "_world"          # 世界记忆（共享）
LEGACY_CHAIN = "chain.json"        # 老布局：memory/chain.json 一份混装所有角色
PART_RE = re.compile(r"^(?P<stem>.+?)\.part(?P<seq>\d+)\.json$")
SUMMARY_RE = re.compile(r"^(?:summary|压缩记忆)[-_]?(?P<stem>.*?)\.md$")


def _read_json(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _role_dirs(memory_dir):
    out = []
    if not os.path.isdir(memory_dir):
        return out
    for name in sorted(os.listdir(memory_dir)):
        p = os.path.join(memory_dir, name)
        if os.path.isdir(p) and name != WORLD_DIR_NAME:
            out.append(name)
    return out


def _files(memory_dir, *sub):
    d = os.path.join(memory_dir, *sub)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))


def audit(memory_dir, role_names=None, save_dir=None):
    """体检一个 memory 目录。返回 {verdict, problems, warnings, layout, stats}。

    verdict: "isolated"（结构上隔离）/ "legacy"（老布局，需要迁移）/ "leaky"（真混了）
    """
    role_names = [str(r) for r in (role_names or []) if str(r).strip()]
    problems, warnings, legacy_issues = [], [], []
    memory_dir = str(memory_dir or "")
    layout = {"exists": bool(memory_dir) and os.path.isdir(memory_dir), "roles": {},
              "world": {}, "legacy_files": []}
    if not layout["exists"]:
        return {"verdict": "empty", "problems": [], "warnings": ["memory 目录还不存在"],
                "layout": layout, "stats": {"roles": 0, "archives": 0, "world_archives": 0}}

    # ---- 1) 老布局：全局 chain.json 混装多角色 ----
    legacy = os.path.join(memory_dir, LEGACY_CHAIN)
    legacy_chain = _read_json(legacy) if os.path.isfile(legacy) else None
    if isinstance(legacy_chain, dict) and legacy_chain:
        keys = [str(k) for k in legacy_chain.keys()]
        layout["legacy_files"].append(LEGACY_CHAIN)
        if len(keys) > 1:
            # 这是【布局】问题，不是"内容串了" —— 单独记一类，
            # 否则它会把 verdict 顶成 leaky，永远报不出"需要迁移"这个中间状态。
            legacy_issues.append(u"老布局：memory/chain.json 一份索引混装了 %d 个角色（%s）"
                                 u"—— 应该拆成 memory/<角色>/chain.json"
                                 % (len(keys), u"、".join(keys[:5])))
        else:
            warnings.append(u"老布局：memory/chain.json 索引还没迁到 memory/<角色>/ 下（当前只有 %s）"
                            % (keys[0] if keys else u"空"))
    migrated_backups = []
    for f in _files(memory_dir):
        if f == LEGACY_CHAIN:
            continue
        if f.endswith(".migrated"):
            # 迁移时故意留下的墓碑（老索引备份）。它不代表"还是老布局"，
            # 否则迁移完检测器还喊 legacy，人就不信它了。
            migrated_backups.append(f)
            continue
        layout["legacy_files"].append(f)
    layout["migrated_backups"] = migrated_backups
    if migrated_backups:
        warnings.append(u"迁移备份还在（%s）—— 确认新布局无误后可以删掉"
                        % u"、".join(migrated_backups[:3]))
    if [f for f in layout["legacy_files"] if f != LEGACY_CHAIN]:
        warnings.append(u"memory 根目录还散着 %d 个文件（应收进角色子目录）"
                        % len([f for f in layout["legacy_files"] if f != LEGACY_CHAIN]))

    # ---- 2) 每个角色目录：key 与归档文件名必须只属于这个角色 ----
    total_archives = 0
    for role in _role_dirs(memory_dir):
        info = {"chain_keys": [], "archives": [], "others": []}
        chain = _read_json(os.path.join(memory_dir, role, LEGACY_CHAIN))
        if isinstance(chain, dict):
            info["chain_keys"] = [str(k) for k in chain.keys()]
            for key in info["chain_keys"]:
                # 关键：跟【这个目录的主人】比，而不是跟全部角色名比 ——
                # 拿全名单比等于永远不报（群聊里所有角色都在名单上）。
                if key != role:
                    info["others"].append(key)
                # 索引里指到的 part 文件必须真的在这个目录里，且属于这个目录的主人
                for part in (chain.get(key) or []):
                    pname = str((part or {}).get("path") or "")
                    if not pname:
                        continue
                    if not os.path.isfile(os.path.join(memory_dir, role, pname)):
                        problems.append(u"角色「%s」的索引指向了不存在的归档：%s" % (role, pname))
                    m = PART_RE.match(pname)
                    if m and m.group("stem") != role:
                        problems.append(u"角色「%s」的索引里混进了别人的归档：%s（属于 %s）"
                                        % (role, pname, m.group("stem")))
        for f in _files(memory_dir, role):
            if f == LEGACY_CHAIN:
                continue
            m = PART_RE.match(f)
            if m:
                total_archives += 1
                info["archives"].append(f)
                if m.group("stem") != role:
                    problems.append(u"角色目录「%s」里放着别人的归档：%s" % (role, f))
                continue
            s = SUMMARY_RE.match(f)
            if s and s.group("stem") and s.group("stem") != role:
                problems.append(u"角色目录「%s」里放着别人的摘要：%s" % (role, f))
            else:
                info["archives"].append(f)
        for other in info["others"]:
            problems.append(u"角色「%s」的索引里出现了别的角色：%s" % (role, other))
        # 名字提示（不算错：群聊里互相出现是正常的）
        if role_names and len(role_names) > 1:
            for f in info["archives"]:
                p = os.path.join(memory_dir, role, f)
                try:
                    text = io.open(p, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                hit = [n for n in role_names if n != role and n in text]
                if hit:
                    warnings.append(u"「%s」的 %s 里出现了 %s 的名字"
                                    u"（群聊里正常；若这是单聊才需要查）"
                                    % (role, f, u"、".join(hit[:3])))
        layout["roles"][role] = info
    if role_names:
        for role in role_names:
            if role not in layout["roles"]:
                warnings.append(u"角色「%s」还没有自己的记忆目录（memory/%s/）" % (role, role))

    # ---- 3) 世界记忆：必须独立成目录，且不该混进单个角色的 key ----
    world_dir = os.path.join(memory_dir, WORLD_DIR_NAME)
    world_archives = _files(memory_dir, WORLD_DIR_NAME)
    layout["world"] = {"exists": os.path.isdir(world_dir), "files": world_archives}
    if not os.path.isdir(world_dir):
        warnings.append(u"没有世界记忆目录 memory/%s/ —— 世界侧的演进（事件/时间线）"
                        u"目前无处存放，只能塞进角色记忆里" % WORLD_DIR_NAME)
    else:
        wchain = _read_json(os.path.join(world_dir, LEGACY_CHAIN))
        if isinstance(wchain, dict) and role_names:
            mixed = [k for k in wchain.keys() if str(k) in role_names]
            if mixed:
                problems.append(u"世界记忆里混进了角色专属 key：%s" % u"、".join(mixed[:5]))

    verdict = "leaky" if problems else ("legacy" if (legacy_issues or layout["legacy_files"])
                                       else "isolated")
    return {"verdict": verdict, "problems": problems, "legacy": legacy_issues,
            "warnings": warnings, "layout": layout,
            "stats": {"roles": len(layout["roles"]), "archives": total_archives,
                      "world_archives": len(world_archives),
                      "legacy_files": len(layout["legacy_files"])}}


def plan_migration(memory_dir, role_names=None):
    """给出"老布局 → 人物专属目录"的迁移计划（不改任何文件，只算清单）。

    注意 chain.json **不能整份移动**：它一份混装了所有角色的 key，必须按 key 拆开
    分别写进各角色目录（否则角色 A 的目录里会出现角色 B 的索引 —— 那正是要检测的"混"）。
    """
    moves = []
    legacy = os.path.join(memory_dir, LEGACY_CHAIN)
    chain = _read_json(legacy)
    if not isinstance(chain, dict):
        return moves
    by_role = {}
    for role, parts in chain.items():
        role = str(role)
        for part in (parts or []):
            pname = str((part or {}).get("path") or "")
            if not pname:
                continue
            src = os.path.join(memory_dir, pname)
            if os.path.isfile(src):
                moves.append({"from": pname, "to": os.path.join(role, pname), "role": role})
                by_role.setdefault(role, []).append(part)
    for role in sorted(by_role):
        moves.append({"from": LEGACY_CHAIN, "to": os.path.join(role, LEGACY_CHAIN),
                      "role": role, "note": u"按 key 拆分（只搬 %s 自己的条目）" % role})
    return moves


def render_report(rep):
    """把体检结果说成人话（给界面/命令行用）。"""
    lines = []
    v = rep.get("verdict")
    title = {"isolated": u"✅ 记忆是隔离的（结构上没有交叉）",
             "leaky": u"⛔ 记忆存在交叉（见下）",
             "legacy": u"⚠️ 还是老布局（单份索引混装），建议迁移",
             "empty": u"○ 还没有记忆归档"}.get(v, v)
    lines.append(title)
    st = rep.get("stats") or {}
    lines.append(u"角色 %d 个 · 归档 %d 份 · 世界归档 %d 份"
                 % (st.get("roles", 0), st.get("archives", 0), st.get("world_archives", 0)))
    for p in rep.get("problems") or []:
        lines.append(u"⛔ " + p)
    for p in rep.get("legacy") or []:
        lines.append(u"⚠️ " + p)
    for w in rep.get("warnings") or []:
        lines.append(u"⚠️ " + w)
    return "\n".join(lines)
