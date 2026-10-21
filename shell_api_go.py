# -*- coding: utf-8 -*-
"""shell_api_go —— 从 Kit.py 拆出的 mixin（^api_go|^api_offline|^api_tree|^api_select）。

包含方法：api_select_roles、api_select_worlds、api_tree_drift、api_tree_weights、api_tree_prune、api_tree、api_go_settings、api_go_new、api_go_state、api_go_play、api_go_pass、api_go_undo…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

import json
import offline_advance
import tree_weight

class ApiGoMixin:
    """shell_api_go"""

    def api_select_roles(self, names_json):
        try:
            names = json.loads(names_json)
            names = [n for n in names if any(r["name"] == n for r in self.roles)]
        except Exception:
            return {"ok": False}
        # 先把当前聊天树写回「旧」的<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌首个选中角色，再切换选择：
        # 否则取消勾选/切换角色时，旧角色的记录会残留在聊天窗口，
        # 甚至误写进新选角色的存档里。
        self._save_tree()
        self.selected_roles = names
        self.config["selected_roles"] = list(names)
        self.config["last_role"] = names[0] if names else ""
        self._save_config()
        # 切换角色 = 新会话：清空系统横幅（欢迎语/命令回显等），界面彻底初始化
        self.sys_msgs = []
        # 进度同步：拉取该角色最新树存档（若比本地新则用服务器版本，实现跨设备续聊）
        if self._ws_sync_enabled() and names:
            self._ws_pull_tree(names[0])
        self._activate_core(reload_tree=True)
        return {"ok": True}


    def api_select_worlds(self, names_json):
        try:
            names = json.loads(names_json)
            self.selected_worlds = [n for n in names if any(w.get("name") == n for w in self.worlds)]
        except Exception:
            pass
        self._sync_worlds()
        return {"ok": True}


    def api_tree_drift(self, dry_run=True):
        """核查当前主干有没有漂移。三态：cleared / suspected / drifted。

        默认只写状态、**不删任何东西** —— 判定这事儿先让用户看着跑一阵。
        确认漂移的节点可以通过 api_tree_prune 之外的路径手动处理，
        不在这里自动剪，因为"漂移"有时候正是用户想要的走向。
        """
        try:
            import tree_weight
        except Exception as e:
            return {"ok": False, "err": "缺少 tree_weight 模块：" + str(e)[:120]}
        keys = self._drift_keys()
        if not keys:
            return {"ok": False, "err": "还没设本场关键词。点「🔍 漂移核查」上面的输入框填几个词，"
                                        "例如：册子、扉页、铅笔字",
                    "need_keys": True}
        # 案卷 = 世界卡 + 角色卡 + 开局那几轮（"现实"的文本化）
        case_parts = []
        for r in (self.roles or []):
            if r.get("name") in (self.selected_roles or []):
                case_parts.append(str(r.get("prompt") or ""))
        for w in (self.worlds or []):
            if w.get("name") in (self.selected_worlds or []):
                case_parts.append(str(w.get("description") or ""))
        case_text = "\n".join(case_parts)
        try:
            r = tree_weight.audit_tree(self.core.tree, keys, case_text, write=True)
            self._save_tree()
            return r
        except Exception as e:
            return {"ok": False, "err": "核查失败：" + str(e)[:200]}

    # ---------- 前瞻展开（树壳 → 树状AI 的那一步） ----------

    def api_tree_weights(self):
        """给整棵树打分并写回节点元数据（主干 70% / 枝干 50%，有效权重 = 可实行性 × 合理性 × 位置）。

        只打分不删任何东西 —— 让用户先看清楚再决定要不要剪。
        """
        try:
            import tree_weight
        except Exception as e:
            return {"ok": False, "err": "缺少 tree_weight 模块：" + str(e)[:120]}
        try:
            st = tree_weight.annotate(self.core.tree)
            self._save_tree()
            return {"ok": True, "stats": st}
        except Exception as e:
            return {"ok": False, "err": "打分失败：" + str(e)[:200]}


    def api_tree_prune(self, dry_run=True):
        """按有效权重剪掉低分枝叶。

        硬规则（都在 tree_weight 里保证，这里不重复实现）：
          主干永不删 / system 永不删 / 主干上没有对话节点时一律不剪 / 不留断头孤儿。
        dry_run=True 时只报告不真删。
        """
        try:
            import tree_weight
        except Exception as e:
            return {"ok": False, "err": "缺少 tree_weight 模块：" + str(e)[:120]}
        try:
            before = len(self.core.tree.nodes)
            r = tree_weight.prune(self.core.tree, dry_run=bool(dry_run))
            if not dry_run and r.get("removed_count"):
                self._save_tree()
                self._rebuild_messages()
            r["before"] = before
            r["after"] = len(self.core.tree.nodes)
            return r
        except Exception as e:
            return {"ok": False, "err": "剪枝失败：" + str(e)[:200]}


    def api_tree(self, scope="all"):
        """树状回溯：返回完整历史树（主线平铺 + 分支收纳）。
        当前路径（主线）上的节点 on_path=True（不缩进、不右窜）；
        离线分支以 branch_root 标识：branch_root==自身 的行是「分支收纳行」，
        其 branch_size 为分支节点数，展开后成员按 branch_depth（分支内深度）显示。

        scope="all"：完整树（含选项间对话）。
        scope="choices"：选项骨架——只保留「选项节点」+ 当前叶子，隐藏选项间的对话，
        平铺展示（branch_root 置空，不做分支收纳行），用于分线剧情下快速聚焦选项。"""
        tree = self.core.tree
        nodes = tree.nodes
        # 当前路径（root → 当前叶子），主线 = 路径上的节点
        path = set()
        nid = tree.current_leaf_id
        while nid and nid in nodes:
            path.add(nid)
            nid = nodes[nid].parent_id

        def subtree_size(nid):
            node = nodes.get(nid)
            if not node:
                return 0
            return 1 + sum(subtree_size(c) for c in node.children_ids)

        out = []
        branch_sizes = {}

        def walk(nid, in_branch, branch_depth):
            node = nodes.get(nid)
            if not node:
                return
            on_path = nid in path
            if on_path:
                in_branch = None
                branch_depth = 0
            elif in_branch is None:
                in_branch = nid
                branch_depth = 0
                branch_sizes[nid] = subtree_size(nid)
            else:
                branch_depth += 1
            out.append({
                "id": nid,
                "role": node.role,
                "content": (node.content or "").replace("\n", " ")[:60],
                "on_path": on_path,
                "branch_root": in_branch,
                "branch_depth": branch_depth,
                "branch_size": branch_sizes.get(in_branch, 0),
                "is_current": nid == tree.current_leaf_id,
                "is_leaf": not node.children_ids,
                "is_choice": bool((node.metadata or {}).get("is_choice")),
            })
            for c in node.children_ids:
                walk(c, in_branch, branch_depth)

        if tree.root_id:
            walk(tree.root_id, None, 0)

        if scope == "choices":
            # 选项骨架：保留分支归属（branch_root/branch_depth），前端据此按支线分组，
            # 并把「非选项、非当前」的对话折叠成可展开的 ··· 段。仅视图层折叠，不改存储结构。
            pass
        return out


    def api_go_settings(self):
        """给界面显示「这盘棋她打算怎么跟你下」"""
        st = self._go_settings()
        b = self._go_game()
        st["ok"] = True
        st["human"] = getattr(self, "_go_human", "black")
        st["size"] = b.size if b else 19
        st["style"] = self._go_style()
        st["style_label"] = self.GO_STYLE_LABEL.get(st["style"], "")
        st["komi"] = b.komi if b else 7.5
        return st


    def api_go_new(self, size=19, human_color="black", komi=7.5):
        """开新局。human_color: 'black' 或 'white'"""
        try:
            import go_engine as ge
        except Exception as e:
            return {"ok": False, "err": "围棋引擎缺失：" + str(e)[:120]}
        try:
            size = int(size or 19)
        except Exception:
            size = 19
        if size not in (9, 13, 19):
            size = 19
        b = ge.new_game(size=size, komi=float(komi or 7.5))
        self._go = b
        human = "white" if str(human_color).lower().startswith("w") else "black"
        self._go_human = human
        self._go_log = []
        st = self._go_settings()
        if human == "black" and st["handicap"]:
            n = b.setup_handicap(st["handicap"])
            self._go_note("让子局：她让你 %d 子（好感度 %d，%s）" % (n, st["aff"], st["mood"]))
        elif human == "white" and st["komi_extra"]:
            b.komi += st["komi_extra"]
            self._go_note("她多贴 %.1f 目给你（好感度 %d，%s）" % (st["komi_extra"], st["aff"], st["mood"]))
        self._go_note("开新局：%d 路，你执%s，贴目 %.1f，她的棋风「%s」" %
                      (size, "黑" if human == "black" else "白", b.komi,
                       self.GO_STYLE_LABEL.get(self._go_style(), "均衡").split(" —— ")[0]))
        self._go_maybe_ai_first()
        return {"ok": True, "state": b.state(), "human": human,
                "settings": st, "log": self._go_log[-6:]}


    def api_go_state(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        try:
            cands = [c["display"] for c in b.candidates(limit=6)]
        except Exception:
            cands = []
        st = self._go_settings()
        st["style_label"] = self.GO_STYLE_LABEL.get(self._go_style(), "")
        return {"ok": True, "state": b.state(),
                "human": getattr(self, "_go_human", "black"),
                "candidates": cands,
                "settings": st,
                "log": getattr(self, "_go_log", [])[-10:]}


    def api_go_play(self, x, y):
        """玩家落子（x,y 为 0 起算的内部坐标）。落完自动触发 AI 回手。"""
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        r = b.play(int(x), int(y))
        if not r["ok"]:
            return {"ok": False, "err": r["reason"]}
        self._go_note("你落子 %s%s" % (r["display"],
                                    ("，提 %d 子" % len(r["captured"])) if r["captured"] else ""))
        if b.finished:
            return {"ok": True, "state": b.state(), "ended": True, "log": self._go_log[-6:]}
        self._go_ai_turn("我下在 %s。" % r["display"])
        return {"ok": True, "state": b.state(), "log": self._go_log[-6:]}


    def api_go_pass(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        r = b.pass_turn()
        self._go_note("你停一手")
        if r.get("ended") or b.finished:
            return {"ok": True, "state": b.state(), "ended": True, "log": self._go_log[-6:]}
        self._go_ai_turn("我停一手（pass）。")
        return {"ok": True, "state": b.state(), "log": self._go_log[-6:]}


    def api_go_undo(self):
        """悔棋：退回到自己上一次落子之前（退两手：AI 一手 + 自己一手）。"""
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        n = 0
        for _ in range(2):
            if b.undo()["ok"]:
                n += 1
        if n:
            self._go_note("悔棋 %d 手" % n)
        return {"ok": True, "state": b.state(), "undone": n, "log": self._go_log[-6:]}


    def api_go_resign(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        import go_engine as ge
        human = getattr(self, "_go_human", "black")
        color = ge.BLACK if human == "black" else ge.WHITE
        r = b.resign(color)
        self._go_note("你认输 —— " + b.result)
        return {"ok": True, "state": b.state(), "result": b.result}


    def api_go_score(self):
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        s = b.score()
        return {"ok": True, "score": s}


    def api_go_ai(self):
        """手动让 AI 走一手（调试/补救用）"""
        b = self._go_game()
        if b is None:
            return {"ok": False, "err": "还没开局"}
        self._go_retry = 0
        self._go_ai_turn("（继续）")
        return {"ok": True, "state": b.state()}


    def api_offline_peek(self):
        """看看"你不在的时候世界走了多少" —— 只出方案，什么都不改。"""
        p = self._offline_plan()
        return {"ok": bool(p.get("ok")), "proposal": p, "key": self._offline_key()}


    def api_offline_apply(self, accept=True):
        """应用（accept=True）或忽略（False）刚算出的离线推进。

        应用会改机制状态并往聊天里插一条系统消息（可读的时间说明）；
        忽略则只记下"这段时间处理过了"，避免下次启动又弹一遍。
        两条路都会更新记账点 —— 这是防重复提示的关键。
        """
        import offline_advance
        try:
            p = self._offline_plan()
        except Exception as e:
            return {"ok": False, "err": "计算失败：" + str(e)[:120]}
        if not p.get("ok"):
            return {"ok": False, "err": p.get("skipped") or "没有需要推进的时间"}
        key = self._offline_key()
        # 记账：无论应用还是忽略，都把这局的"已处理到"推进到这次的上次互动时间
        try:
            book = dict(self.config.get("offline_dismissed") or {})
            book[key] = p.get("last_active")
            self.config["offline_dismissed"] = book
        except Exception:
            pass
        if not accept:
            self._save_config()
            return {"ok": True, "applied": False, "summary": p["summary"]}
        undo = None
        try:
            undo = offline_advance.apply(p, self.core.mechanism_state)
        except Exception as e:
            return {"ok": False, "err": "应用失败：" + str(e)[:140]}
        if not undo:
            self._save_config()
            return {"ok": True, "applied": False, "summary": p["summary"],
                    "note": "这次没有数值变化，只推进了时间记账"}
        # 进聊天记录：一条可读的时间说明（沿用生图那种系统消息写法）
        try:
            self.sys_msgs.append({"kind": "ai", "speaker": "🕰 离线推进",
                                  "content": p["summary"], "node_id": None})
            self._rebuild_messages()
        except Exception:
            pass
        self._save_config()
        self._persist_offline_undo(undo)
        return {"ok": True, "applied": True, "summary": p["summary"],
                "turns": p.get("turns", 0), "affection": p.get("affection"),
                "status": p.get("status", []), "undo_saved": bool(undo)}


    def api_offline_undo(self):
        """撤销上一次离线推进（状态回到应用前；聊天里那条说明留着，但会标注已撤销）"""
        import offline_advance
        undo = getattr(self, "_offline_undo", None)
        if not undo:
            return {"ok": False, "err": "没有可撤销的离线推进"}
        ok = offline_advance.revert(undo, self.core.mechanism_state)
        self._offline_undo = None
        if ok:
            try:
                self.sys_msgs.append({"kind": "ai", "speaker": "🕰 离线推进",
                                      "content": "（已撤销上一次离线结算）", "node_id": None})
                self._rebuild_messages()
            except Exception:
                pass
        return {"ok": bool(ok), "err": "" if ok else "撤销失败"}

