# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   save_guard.py - 存档守护：校验 / 自动修复 / 备份恢复 / 原子写入
#
#   目标：存档永远救得回来 —— 写不坏（原子写入）、覆盖前留底（自动备份）、
#   坏了能自愈（加载时校验 + 修复）、连文件都读不了也能从备份捞回。
#
#   命令行用法：
#     python save_guard.py check            # 只检查并报告，不改文件
#     python save_guard.py repair           # 校验 + 修复 + 写回（坏文件先备份）
#     python save_guard.py backup           # 强制备份全部存档（含 worlds/memory）
#     python save_guard.py check --dir <路径>    # 指定数据目录
#
#   应用内集成：html_app 在 __init__ 后台跑 sweep()，每次写盘走 atomic_write_json
#   并在覆盖前 backup_file()（节流），加载每个存档时 repair_save_data()。
# ============================================================

import argparse
import json
import os
import re
import shutil
import threading
import time
import traceback

VALID_ROLES = ("system", "user", "assistant")
BACKUP_SUBDIR = "backup"
BACKUP_KEEP = 20          # 每个存档保留的备份份数
BACKUP_THROTTLE_S = 300   # 覆盖前备份的节流秒数（同一存档 5 分钟内不重复备份）
# sweep 清理原子写入残留时的"陈旧阈值"：比这新的 tmp 文件一律不动
# （它可能正在被写；顺手的清理不该把一次正常存档搅黄，见 sweep 里的长注释）
TMP_STALE_S = 600


# ============================================================
#  原子写入 / 备份
# ============================================================
def atomic_write_json(path, data):
    """临时文件（唯一名）+ os.replace：写一半崩溃也不会留下截断的存档。
    唯一临时名避免并发写同一文件时互相覆盖（自动存档 + 用户操作可能同时写同一档）。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    # 唯一临时名：pid + 线程随机短串 + 时间戳，防止并发写 clash
    tmp = f"{path}.tmp.{os.getpid()}_{int(time.time() * 1000)}_{threading.get_ident()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise


def backup_dir_for(path):
    return os.path.join(os.path.dirname(os.path.abspath(path)), BACKUP_SUBDIR)


# ============================================================
#  备份挑选：同秒 / mtime 不可靠时必须保守，绝不静默挑旧的那份
# ============================================================
# 备份文件名 = <存档名>.<14 位备份时刻>[-<同秒序号>]
#
# 为什么名字里要带序号：时间戳只到秒，同一秒内连做两次备份会算出**同一个路径**，
# 后一次直接覆盖前一次 —— 那不是"挑错"，是"备份凭空少了一份"。
# 为什么 mtime 不能单独当判据：`shutil.copy2` 会把**源文件的 mtime** 一起搬过来，
# 于是备份上的 mtime 记的是"内容时间"而不是"备份时间"；再叠加系统时钟回拨、
# 跨盘/网络共享拷贝、FAT 只到 2 秒，按 mtime 挑"最新备份"完全可能挑到旧的那份 ——
# 而 newest_backup 的唯一用途就是**恢复存档**，挑错的代价是数据回退。
BACKUP_TS_FMT = "%Y%m%d%H%M%S"
_BACKUP_TAIL_RE = re.compile(r"^(\d{14})(?:-(\d+))?$")


class AmbiguousBackupError(Exception):
    """多份备份分不出谁更新（同秒 / mtime 与文件名打架 / mtime 读不到）。

    这个异常的意义就是**不许瞎猜**：调用方拿到它必须停下来告诉用户
    「有多份备份分不出新旧，请手动选择要恢复哪一份」。
    静默挑一个的代价是拿旧备份盖掉新进度（数据回退），比"这次没恢复成功"严重得多。
    """

    def __init__(self, path, candidates, reason):
        self.path = path
        self.candidates = list(candidates or [])     # [dict]：每份备份的元信息
        self.reason = reason
        Exception.__init__(self, "%s：%s" % (os.path.basename(path), reason))

    def describe(self, limit=8):
        """候选清单（一行一份，新的排前面），给人手动挑选用"""
        lines = []
        for c in self.candidates[:limit]:
            lines.append("· %s（文件名时刻 %s 序号 %s，mtime %s）"
                         % (os.path.basename(c["path"]),
                            c["name_ts"] if c["name_ts"] is not None else "无",
                            c["name_seq"], _fmt_mtime_ns(c["mtime_ns"])))
        if len(self.candidates) > limit:
            lines.append("· ……另有 %d 份" % (len(self.candidates) - limit))
        return "\n".join(lines)


def _fmt_mtime_ns(ns):
    """纳秒 mtime → 人能读的串（读不到就直说，别装成 1970）"""
    if ns is None:
        return "读不到"
    sec, frac = divmod(int(ns), 1000000000)
    return "%s.%06d" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sec)),
                        frac // 1000)


def _backup_meta(full_path, stem):
    """收集一份备份的两路"新旧证据"：文件名里的 (时刻, 序号) + 文件系统 mtime（纳秒）

    两路都可能不可靠：
      · 文件名：老版本 / 手工拷进来的备份没有时间戳段 → name_ts = None
      · mtime：copy2 留下的是内容时间；时钟回拨、拷贝、文件系统精度也都算坑
    所以这里只负责**取证**，判断交给 _rank_backups()。
    """
    meta = {"path": full_path, "name_ts": None, "name_seq": 0, "mtime_ns": None}
    name = os.path.basename(full_path)
    if name.startswith(stem + "."):
        m = _BACKUP_TAIL_RE.match(name[len(stem) + 1:])
        if m:
            meta["name_ts"] = int(m.group(1))
            meta["name_seq"] = int(m.group(2) or 0)
    try:
        meta["mtime_ns"] = os.stat(full_path).st_mtime_ns   # 纳秒：同秒也能分出先后
    except OSError:
        meta["mtime_ns"] = None
    return meta


def _backup_metas(path):
    """该存档在 backup/ 下的全部候选元信息（不排序、不判断）"""
    bdir = backup_dir_for(path)
    if not os.path.isdir(bdir):
        return []
    stem = os.path.basename(path)
    try:
        names = [f for f in os.listdir(bdir) if f.startswith(stem + ".")]
    except OSError:
        return []
    return [_backup_meta(os.path.join(bdir, f), stem) for f in sorted(names)]


def _rank_backups(path, metas):
    """按"新→旧"排好；分不出就抛 AmbiguousBackupError（绝不返回"猜的"那个）

    判据（两路证据互相印证）：
      ① 先比 mtime（st_mtime_ns，纳秒级）；
      ② mtime 并列 → 比文件名里的 时刻 + 同秒序号；
      ③ mtime 读不到、两路证据打架、或连②也并列 → 抛异常，交给人选。
    """
    if len(metas) <= 1:
        return list(metas)

    def mkey(m):
        return (m["mtime_ns"], m["name_ts"] if m["name_ts"] is not None else -1,
                m["name_seq"])

    unknown = [m for m in metas if m["mtime_ns"] is None]
    if unknown:
        raise AmbiguousBackupError(
            path, metas,
            "有 %d 份备份读不到修改时间（%s），判断不出新旧"
            % (len(unknown), "、".join(os.path.basename(m["path"]) for m in unknown)))

    by_mtime = sorted(metas, key=mkey, reverse=True)
    best = by_mtime[0]
    if len(by_mtime) > 1 and mkey(by_mtime[1]) == mkey(best):
        raise AmbiguousBackupError(
            path, by_mtime,
            "有 %d 份备份的 mtime 与文件名时间戳完全相同，分不出谁更新"
            % sum(1 for m in by_mtime if mkey(m) == mkey(best)))

    # 两路证据互相打架：mtime 说 A 新、文件名说 B 新 → 谁都不能信，报错让人选。
    # （copy2 保留内容时间、时钟回拨、手工拷备份都会造成这种局面。）
    named = [m for m in metas if m["name_ts"] is not None]
    if named:
        by_name = sorted(named, key=lambda m: (m["name_ts"], m["name_seq"],
                                               m["mtime_ns"]), reverse=True)
        nbest = by_name[0]
        if nbest["path"] != best["path"]:
            raise AmbiguousBackupError(
                path, by_mtime,
                "修改时间与文件名时刻指向不同的备份（mtime 说 %s 新，文件名说 %s 新），"
                "不敢替用户挑" % (os.path.basename(best["path"]),
                                  os.path.basename(nbest["path"])))
    return by_mtime


def list_backups(path):
    """该存档的全部备份元信息，按"新→旧"排好（无备份返回 []）。

    注意：分不出新旧时抛 AmbiguousBackupError —— 调用方必须显式处理，
    不允许"先当它没有备份"或者"随便拿第一个"。
    """
    return _rank_backups(path, _backup_metas(path))


def backup_file(path, keep=BACKUP_KEEP, throttle=BACKUP_THROTTLE_S):
    """把 path 当前内容备份到 <dir>/backup/<stem>.<ts>[-序号]，节流 + 清理旧备份。
    返回备份路径或 None（文件不存在 / 节流内跳过）。"""
    if not os.path.exists(path):
        return None
    bdir = backup_dir_for(path)
    os.makedirs(bdir, exist_ok=True)
    stem = os.path.basename(path)
    # 节流：同一 stem 的最近一次备份若在 throttle 秒内则跳过
    try:
        mtimes = [os.path.getmtime(os.path.join(bdir, f))
                  for f in os.listdir(bdir) if f.startswith(stem + ".")]
        if mtimes and time.time() - max(mtimes) < throttle:
            return None
    except Exception:
        pass
    ts = time.strftime(BACKUP_TS_FMT)
    dst = os.path.join(bdir, f"{stem}.{ts}")
    # 同秒重复备份：绝不覆盖上一份（覆盖 = 少一份备份），改用 -2/-3… 序号区分
    n = 1
    while os.path.exists(dst):
        n += 1
        dst = os.path.join(bdir, f"{stem}.{ts}-{n}")
    try:
        # 先取时间戳再拷：让备份的 mtime **不晚于**此刻。否则下面 throttle 的
        # "现在 - mtime" 会是负数，把自己刚做的备份当成"未来的备份"而不节流。
        now_ns = time.time_ns()
        shutil.copy2(path, dst)
        # copy2 连 mtime 一起搬 —— 那样备份上的 mtime 是"内容时间"而不是"备份时间"，
        # 按 mtime 挑最新备份就可能挑错（数据回退事故的根源之一）。
        # 这里显式改成"备份发生的时刻"：让 mtime 与文件名里的备份时刻说同一件事。
        try:
            os.utime(dst, ns=(now_ns, now_ns))
        except OSError:
            pass
    except Exception:
        return None
    # 清理：同名备份只留最近 keep 份（"新→旧"按 list_backups 的口径；
    # 分不出新旧时退化成保守排序：宁可多留，不可误删可能更新的那几份）
    try:
        metas = _backup_metas(path)
        try:
            ordered = _rank_backups(path, metas)
        except AmbiguousBackupError:
            ordered = sorted(metas, key=lambda m: ((m["name_ts"] or 0), m["name_seq"],
                                                   m["mtime_ns"] or 0), reverse=True)
        for meta in ordered[keep:]:
            try:
                os.remove(meta["path"])
            except Exception:
                pass
    except Exception:
        pass
    return dst


def newest_backup(path):
    """返回 path 最新的备份文件路径（无则 None）。

    **分不出新旧时抛 AmbiguousBackupError**（同秒 / mtime 与文件名打架 / mtime 读不到）：
    这个函数只服务于"恢复存档"，挑错等于拿旧数据盖掉新进度，
    所以宁可让上层提示用户手选，也不返回一个猜的。
    """
    cands = list_backups(path)
    return cands[0]["path"] if cands else None


def _read_json_file(path):
    """读 JSON；失败返回 (None, 错误信息)"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, str(e)


# ============================================================
#  历史树校验 / 修复
# ============================================================
def validate_history_tree(tree):
    """检查历史树结构，返回问题列表（空列表 = 健康）"""
    issues = []
    if not isinstance(tree, dict):
        return ["history_tree 不是对象"]
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict):
        return ["nodes 缺失或不是对象"]
    root = tree.get("root_id")
    for nid, node in nodes.items():
        if not isinstance(node, dict):
            issues.append(f"节点 {nid} 不是对象")
            continue
        if str(node.get("id", "")) != str(nid):
            issues.append(f"节点 {nid} 的 id 与键不一致")
        if node.get("role") not in VALID_ROLES:
            issues.append(f"节点 {nid} 的 role 非法: {node.get('role')!r}")
        if not isinstance(node.get("content"), str):
            issues.append(f"节点 {nid} 的 content 非字符串")
        if not isinstance(node.get("children_ids"), list):
            issues.append(f"节点 {nid} 的 children_ids 不是列表")
        for c in node.get("children_ids") or []:
            if c not in nodes:
                issues.append(f"节点 {nid} 引用了不存在的子节点 {c}")
        p = node.get("parent_id")
        if p is not None and p not in nodes:
            issues.append(f"节点 {nid} 的 parent_id {p} 不存在")
    if root is not None and root not in nodes:
        issues.append(f"root_id {root} 不存在")
    if tree.get("current_leaf_id") is not None and tree["current_leaf_id"] not in nodes:
        issues.append("current_leaf_id 指向不存在的节点")
    return issues


def repair_history_tree(tree):
    """尽力修复历史树（就地修改），返回 (树, 修复记录列表)。"""
    issues = []
    if not isinstance(tree, dict):
        tree = {}
    nodes = tree.get("nodes")
    if not isinstance(nodes, dict):
        nodes = {}
        tree["nodes"] = nodes
        issues.append("nodes 缺失，已重建为空树")
    # 1) 节点字段规整
    for nid, node in list(nodes.items()):
        if not isinstance(node, dict):
            del nodes[nid]
            issues.append(f"节点 {nid} 非对象，已删除")
            continue
        if str(node.get("id", "")) != str(nid):
            node["id"] = str(nid)
            issues.append(f"节点 {nid} 的 id 已修正")
        if node.get("role") not in VALID_ROLES:
            node["role"] = "user"
            issues.append(f"节点 {nid} 的 role 非法，已改为 user")
        if not isinstance(node.get("content"), str):
            node["content"] = str(node.get("content") or "")
        if not isinstance(node.get("children_ids"), list):
            node["children_ids"] = []
        if not isinstance(node.get("metadata"), dict):
            node["metadata"] = {}
        if "parent_id" not in node or (node["parent_id"] is not None and node["parent_id"] not in nodes):
            node["parent_id"] = None
    # 2) children 去重 + 去掉自引用和悬空引用
    for nid, node in nodes.items():
        kids = []
        for c in node.get("children_ids") or []:
            if c in nodes and c != nid and c not in kids:
                kids.append(c)
            elif c not in nodes:
                issues.append(f"节点 {nid} 的悬空子引用 {c} 已清除")
        node["children_ids"] = kids
    # 3) parent/children 一致性补齐
    for nid, node in nodes.items():
        p = node.get("parent_id")
        if p is not None:
            if nid not in (nodes[p].get("children_ids") or []):
                nodes[p].setdefault("children_ids", []).append(nid)
                issues.append(f"节点 {p} 的 children_ids 补上了 {nid}")
    # 4) root 修正：root 无效时选第一个无 parent 的节点
    root = tree.get("root_id")
    if root not in nodes:
        candidates = [nid for nid, n in nodes.items() if n.get("parent_id") is None]
        root = candidates[0] if candidates else None
        tree["root_id"] = root
        issues.append("root_id 无效，已重新指定")
    # 5) 从 root DFS 断环 + 剔除不可达孤儿
    if root in nodes:
        path = set()
        visited = set()

        def dfs(nid):
            if nid not in nodes or nid in path:
                return
            path.add(nid)
            visited.add(nid)
            kids = []
            for c in list(nodes[nid].get("children_ids") or []):
                if c in path:
                    issues.append(f"检测到环 {nid}->{c}，已断开")
                    continue
                dfs(c)
                kids.append(c)
            nodes[nid]["children_ids"] = kids
            path.remove(nid)

        dfs(root)
        for nid in list(nodes):
            if nid not in visited:
                del nodes[nid]
                issues.append(f"节点 {nid} 不可达（孤儿/环），已删除")
        # 5b) 按 children 图重建 parent_id（悬空/错位的 parent 修正为真实父节点）
        for nid, node in nodes.items():
            real_parent = next((pid for pid, pn in nodes.items()
                                if nid in (pn.get("children_ids") or [])), None)
            if node.get("parent_id") != real_parent:
                node["parent_id"] = real_parent
                issues.append(f"节点 {nid} 的 parent_id 已修正为 {real_parent}")
    else:
        # 空树：保证字段存在
        tree["root_id"] = None
        tree["current_leaf_id"] = None
        issues.append("树为空，已重置 root/leaf")
    # 6) current_leaf_id 修正：沿 root 最深链
    leaf = tree.get("current_leaf_id")
    if leaf not in nodes:
        cur = tree.get("root_id")
        guard = 0
        while cur in nodes and nodes[cur].get("children_ids") and guard < 100000:
            cur = nodes[cur]["children_ids"][-1]
            guard += 1
        tree["current_leaf_id"] = cur
        if cur is not None:
            issues.append("current_leaf_id 无效，已重算为最深叶子")
    return tree, issues


# ============================================================
#  存档文件级校验 / 修复 / 恢复
# ============================================================
def validate_save(data):
    """顶层字段 + 历史树校验，返回问题列表"""
    issues = []
    if not isinstance(data, dict):
        return ["存档不是 JSON 对象"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        issues.append("name 缺失或非法")
    if not isinstance(data.get("system_prompt"), str):
        issues.append("system_prompt 缺失或非字符串")
    ht = data.get("history_tree")
    if ht is not None:
        issues.extend(validate_history_tree(ht))
    if "unlocked" in data and not isinstance(data["unlocked"], bool):
        issues.append("unlocked 非布尔")
    return issues


def repair_save_data(data):
    """修复存档数据，返回 (新数据, 修复记录)。"""
    issues = []
    if not isinstance(data, dict):
        return {"name": "", "system_prompt": ""}, ["存档不是对象，已重建"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        issues.append("name 缺失，已补默认名")
        data["name"] = data.get("name") or "未命名"
    if not isinstance(data.get("system_prompt"), str):
        issues.append("system_prompt 缺失，已补空串")
        data["system_prompt"] = str(data.get("system_prompt") or "")
    if data.get("history_tree") is not None:
        data["history_tree"], tree_issues = repair_history_tree(data["history_tree"])
        issues.extend(tree_issues)
    return data, issues


def _recover_source(path):
    """挑一份可用于恢复的备份。返回 (备份路径或 None, 需要人介入的说明或 "")。

    分不出新旧（AmbiguousBackupError）时**一份都不恢复**，把候选列清楚交给用户 ——
    这就是"绝不静默回退数据"的落点：恢复失败只是麻烦，恢复错了是丢进度。
    """
    try:
        return newest_backup(path), ""
    except AmbiguousBackupError as e:
        msg = ("%s 有多份备份分不出新旧，已停止自动恢复：%s；%s；"
               "请在 %s 里手动挑一份（或把多余的备份挪走再试）"
               % (os.path.basename(path), e.reason,
                  e.describe().replace("\n", " "), backup_dir_for(path)))
        print("[存档守护] " + msg)
        return None, msg


def guard_loaded(path, kind="role"):
    """加载存档并守护：读不了 → 从备份恢复；结构坏了 → 留底 + 修复 + 原子写回。
    返回修复后的数据 dict；无法恢复时返回 None。应用加载存档时调用。"""
    data, err = _read_json_file(path)
    if data is None:
        bak, why = _recover_source(path)
        if bak:
            bdata, _ = _read_json_file(bak)
            if bdata is not None:
                atomic_write_json(path, bdata)
                print(f"[存档守护] {os.path.basename(path)} JSON 损坏，已从备份恢复: {os.path.basename(bak)}")
                data = bdata
            else:
                print(f"[存档守护] {os.path.basename(path)} JSON 损坏且备份也损坏，跳过")
                return None
        elif why:
            return None          # 备份分不出新旧：_recover_source 已把候选清单打出来了
        else:
            print(f"[存档守护] {os.path.basename(path)} JSON 损坏且无备份，跳过")
            return None
    if kind == "world":
        issues = validate_world(data)
        if not issues:
            return data
        backup_file(path, throttle=0)
        fixed, repairs = repair_world(data)
        atomic_write_json(path, fixed)
        print(f"[存档守护] 已修复世界卡 {os.path.basename(path)}: {'; '.join(repairs[:5])}")
        return fixed
    issues = validate_save(data)
    if not issues:
        return data
    backup_file(path, throttle=0)
    fixed, repairs = repair_save_data(data)
    atomic_write_json(path, fixed)
    print(f"[存档守护] 已修复存档 {os.path.basename(path)}: {'; '.join(repairs[:5])}")
    return fixed


def guard_file(path, do_repair=True, do_backup=True, kind="role"):
    """守护单个存档文件。kind: role(角色卡+记忆链) / world(世界卡)。
    返回 (状态, 说明)。"""
    if not os.path.exists(path):
        return "skipped", "文件不存在"
    data, err = _read_json_file(path)
    if data is None:
        # 读不了 → 尝试从备份恢复
        if do_repair:
            bak, why = _recover_source(path)
            if bak:
                bdata, _ = _read_json_file(bak)
                if bdata is not None:
                    atomic_write_json(path, bdata)
                    return "recovered", f"JSON 损坏（{err}），已从备份 {os.path.basename(bak)} 恢复"
            if why:                      # 备份分不出新旧：不恢复，让用户手选
                return "failed", f"JSON 损坏（{err}）；{why}"
            return "failed", f"JSON 损坏（{err}），且无可用备份"
        return "failed", f"JSON 损坏（{err}）"
    if kind == "world":
        issues = validate_world(data)
        if not issues:
            return "ok", "健康"
        if not do_repair:
            return "failed", "; ".join(issues[:5])
        if do_backup:
            backup_file(path, throttle=0)
        fixed, repairs = repair_world(data)
        atomic_write_json(path, fixed)
        return "repaired", "修复: " + "; ".join((issues + repairs)[:6])
    issues = validate_save(data)
    if not issues:
        return "ok", "健康"
    if not do_repair:
        return "failed", "; ".join(issues[:5])
    # 修复：先把坏的原件留底，再写回修好的
    if do_backup:
        backup_file(path, throttle=0)
    fixed, repairs = repair_save_data(data)
    atomic_write_json(path, fixed)
    return "repaired", "修复: " + "; ".join((issues + repairs)[:6])


# ---------- 世界卡轻量校验 ----------
def validate_world(data):
    issues = []
    if not isinstance(data, dict):
        return ["世界卡不是 JSON 对象"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        issues.append("name 缺失或非法")
    if not isinstance(data.get("rules"), list):
        issues.append("rules 不是列表")
    entries = data.get("entries")
    if entries is not None:
        if not isinstance(entries, list):
            issues.append("entries 不是列表")
        else:
            for i, e in enumerate(entries):
                if not isinstance(e, dict):
                    issues.append(f"entry[{i}] 不是对象")
                else:
                    if not isinstance(e.get("keywords"), list):
                        issues.append(f"entry[{i}] keywords 不是列表")
                    if not isinstance(e.get("content"), str):
                        issues.append(f"entry[{i}] content 非字符串")
    return issues


def repair_world(data):
    issues = []
    if not isinstance(data, dict):
        return {"name": ""}, ["世界卡不是对象，已重建"]
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        data["name"] = data.get("name") or "未命名"
        issues.append("name 已补默认值")
    if not isinstance(data.get("rules"), list):
        data["rules"] = [r for r in data.get("rules") or [] if isinstance(r, str)]
        issues.append("rules 已规整")
    entries = data.get("entries")
    if entries is not None and isinstance(entries, list):
        for i, e in enumerate(entries):
            if not isinstance(e, dict):
                entries[i] = {"keywords": [], "content": ""}
                issues.append(f"entry[{i}] 已重建")
                continue
            if not isinstance(e.get("keywords"), list):
                e["keywords"] = []
            if not isinstance(e.get("content"), str):
                e["content"] = str(e.get("content") or "")
    elif entries is not None:
        data["entries"] = []
        issues.append("entries 已重置为空列表")
    return data, issues


def sweep(data_dir, include_worlds=True, include_memory=True, do_repair=True, do_backup=True):
    """扫描并守护数据目录下的所有存档。返回汇总 dict。"""
    summary = {"ok": 0, "repaired": 0, "recovered": 0, "failed": 0, "skipped": 0, "logs": []}
    dirs = [(os.path.join(data_dir, "saves"), "role")]
    if include_worlds:
        dirs.append((os.path.join(data_dir, "worlds"), "world"))
    if include_memory:
        dirs.append((os.path.join(data_dir, "memory"), "role"))
    seen = set()
    for d, kind in dirs:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            # 跳过隐藏/元数据文件（如跑团会期锁 .trpg_lock.json）：
            # 它们不是角色卡/世界卡/记忆树，绝不能当作存档来校验、修复或备份。
            if fn.startswith("."):
                continue
            # 崩溃/并发残留的唯一临时文件（*.json.tmp.<pid>_<ms>_<tid>）：
            # 先于 .json 过滤处理（它们不以 .json 结尾）。
            #
            # ⚠ 只清**陈旧的**：这个 sweep 跑在后台线程（sweep_async），而写盘随时可能正在进行。
            # 一个正在写的 tmp 文件被删掉，紧接着的 os.replace 就会 ENOENT，那一次存档直接失败。
            # Windows 上恰好没事 —— 打开着的文件删不掉，所以这个竞态一直没暴露；
            # Linux/macOS 上 unlink 对打开的文件是允许的，于是 CI 上就红了（真事，2026-10）。
            # 判据用 mtime：正常写入的 tmp 只存在毫秒级，超过 10 分钟的铁定是崩溃残留。
            if ".tmp." in fn:
                p = os.path.join(d, fn)
                try:
                    if time.time() - os.path.getmtime(p) < TMP_STALE_S:
                        summary["skipped"] += 1
                        continue
                    os.remove(p)
                    summary["skipped"] += 1
                except Exception as e:
                    summary["failed"] += 1
                    summary["logs"].append(f"[failed] {os.path.relpath(p, data_dir)}: {e}")
                continue
            if not fn.endswith(".json"):
                continue
            if fn.endswith(".tmp"):
                continue  # 原子写入残留（旧命名，直接跳过不当作存档）
            p = os.path.join(d, fn)
            key = os.path.normcase(os.path.abspath(p))
            if key in seen:
                continue
            seen.add(key)
            try:
                status, msg = guard_file(p, do_repair=do_repair, do_backup=do_backup, kind=kind)
                summary[status] = summary.get(status, 0) + 1
                if status in ("repaired", "recovered", "failed"):
                    summary["logs"].append(f"[{status}] {os.path.relpath(p, data_dir)}: {msg}")
            except Exception as e:
                summary["failed"] += 1
                summary["logs"].append(f"[failed] {p}: {e}")
    return summary


def sweep_async(data_dir, on_done=None):
    """后台线程扫描（不阻塞启动）"""

    def run():
        try:
            s = sweep(data_dir)
            for log in s["logs"]:
                print(f"[存档守护] {log}")
            if s["repaired"] or s["recovered"]:
                print(f"[存档守护] 已自动修复 {s['repaired']} 个、从备份恢复 {s['recovered']} 个存档")
            if s["failed"]:
                print(f"[存档守护] ⚠️ {s['failed']} 个存档无法自动修复，请手动检查")
        except Exception:
            traceback.print_exc()
        finally:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


# ============================================================
#  命令行
# ============================================================
def main(argv=None):
    ap = argparse.ArgumentParser(prog="save_guard", description="DICK 存档守护：校验/修复/备份")
    ap.add_argument("action", choices=["check", "repair", "backup"],
                    help="check=只检查; repair=修复并写回; backup=强制备份")
    ap.add_argument("--dir", default=None, help="数据目录（默认取脚本同级目录）")
    ap.add_argument("--no-worlds", action="store_true", help="跳过 worlds/")
    ap.add_argument("--no-memory", action="store_true", help="跳过 memory/")
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.dir) if args.dir else os.path.dirname(os.path.abspath(__file__))
    do_repair = args.action in ("repair",)
    do_backup = args.action in ("repair", "backup")
    s = sweep(data_dir, include_worlds=not args.no_worlds, include_memory=not args.no_memory,
              do_repair=do_repair, do_backup=do_backup)
    print(f"存档守护（{args.action}）：健康 {s['ok']} / 修复 {s['repaired']} / "
          f"从备份恢复 {s['recovered']} / 失败 {s['failed']} / 跳过 {s['skipped']}")
    for log in s["logs"]:
        print("  " + log)
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
