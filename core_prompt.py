# -*- coding: utf-8 -*-
"""PromptMixin —— 从 DICK_core.py 的 ChatCore 拆出（ast 精确切分）。

方法：_est_tokens、_queue_rolling_summary、_gen_rolling_summary、_with_rolling_summary、_fit_budget、_time_scale、_life_role、_life_world、_life_injection、_world_memory_injection、_inject_world_context、_build_role_prompt、_rebuild_system_node、_opening_prompt
"""
from __future__ import annotations

import time as _time
from typing import Dict, List
from core_tree import MessageNode
from card_modes import mode_block
from player_persona import persona_block
from sycophancy import guard_text as sycophancy_guard_text

import random
import re
import threading

class PromptMixin:
        # ---------- 上下文预算（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌防爆上下文） ----------
        @staticmethod
        def _est_tokens(text: str) -> int:
            """粗略估算 token 数：中日文约 1 字符 1 token，混合内容按 2 字符 1 token 保守估计"""
            if not text:
                return 0
            return max(1, len(text) // 2 + 8)

        def _queue_rolling_summary(self, dropped_messages):
            """后台线程：把被裁剪掉的历史压缩进滚动摘要（不阻塞当前请求）"""
            if not self.rolling_summary_enabled or self._summarizing:
                return
            text = "\n".join(
                f"{m.get('role', '?')}: {str(m.get('content', ''))[:300]}"
                for m in dropped_messages)
            if not text.strip():
                return
            self._summarizing = True
            threading.Thread(target=self._gen_rolling_summary, args=(text,), daemon=True).start()

        def _gen_rolling_summary(self, text):
            try:
                old = self.rolling_summary
                if self.client:
                    stop = self.stop_sequences or None
                    try:
                        resp = self.client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content":
                                 "把下面的对话历史压缩成 300 字以内的滚动摘要，保留人物关系、剧情进展、"
                                 "关键设定与未完成事项。若已有旧摘要，请合并去重后输出新摘要。只输出摘要本身。"},
                                {"role": "user", "content": f"旧摘要：{old or '无'}\n\n新历史：\n{text[:6000]}"},
                            ],
                            stream=False,
                            timeout=60,
                            stop=stop,
                        )
                    except (APIConnectionError, APITimeoutError):
                        # 直连失败 → 切内置中转后重试一次
                        if self._maybe_switch_relay():
                            resp = self.client.chat.completions.create(
                                model=self.model,
                                messages=[
                                    {"role": "system", "content":
                                     "把下面的对话历史压缩成 300 字以内的滚动摘要，保留人物关系、剧情进展、"
                                     "关键设定与未完成事项。若已有旧摘要，请合并去重后输出新摘要。只输出摘要本身。"},
                                    {"role": "user", "content": f"旧摘要：{old or '无'}\n\n新历史：\n{text[:6000]}"},
                                ],
                                stream=False,
                                timeout=60,
                                stop=stop,
                            )
                        else:
                            raise
                    summary = (resp.choices[0].message.content or "").strip()
                else:
                    # 无 LLM 时退化为"尾部截取"
                    summary = (old + "\n（续）" if old else "") + text[-400:]
                if summary:
                    with self._summary_lock:
                        self.rolling_summary = summary[:2000]
                    print(f"[滚动摘要] ✅ 已更新（{len(summary)} 字）")
            except Exception as e:
                print(f"[滚动摘要] 生成失败: {e}")
            finally:
                self._summarizing = False

        def _with_rolling_summary(self, system_msgs):
            """把滚动摘要作为 system 消息附加（裁剪与未裁剪路径共用）"""
            out = list(system_msgs)
            with self._summary_lock:
                if self.rolling_summary:
                    out.append({"role": "system",
                                "content": f"【历史滚动摘要】\n{self.rolling_summary}"})
            return out

        def _fit_budget(self, messages: List[Dict]) -> List[Dict]:
            """按预算裁剪消息：保留全部 system + 最近的历史消息（越旧越先丢弃）。
            当前最后一条用户消息永远保留。
            健壮性：reserve 按预算比例取，滚动摘要计入开销，最终硬性保证总 token ≤ 预算。"""
            budget = self.context_budget
            if not budget:
                return messages
            # 给回复留的余量：预算越大留越多，但保底 256、封顶 1024（避免小预算被 reserve 卡死）
            reserve = max(256, min(1024, int(budget * 0.12)))
            system_msgs = [m for m in messages if m.get('role') == 'system']
            rest = [m for m in messages if m.get('role') != 'system']
            if not rest:
                return messages

            # 滚动摘要本身也占 token（常被漏算，导致实际超预算）
            sum_tokens = 0
            with self._summary_lock:
                if self.rolling_summary:
                    sum_tokens = self._est_tokens(self.rolling_summary)

            used = sum(self._est_tokens(m.get('content', '')) for m in system_msgs)
            remaining = budget - used - reserve - sum_tokens
            if remaining <= 0:
                # 预算连 system+摘要 都不够：只保留最后一条用户消息，并把 system 也截断到可容纳
                last = rest[-1]
                # 给 system 留出的字符预算：塞满剩余预算后，用户消息至少 80 字
                user_cap = max(80, int(budget * 0.4))
                sys_slot = max(0, budget - self._est_tokens(last.get('content', '')) - reserve)
                sys_slot = max(80, sys_slot)  # 保底，防止 system 被压成 0
                kept_sys = []
                for idxm, m in enumerate(list(system_msgs[:1])):
                    mc = m.get('content', '')
                    if self._est_tokens(mc) > sys_slot:
                        m = dict(m)
                        m['content'] = mc[:sys_slot] + "…"
                    kept_sys.append(m)
                content = last.get('content', '')
                if self._est_tokens(content) > user_cap:
                    last = dict(last)
                    last['content'] = content[:user_cap] + "…"
                # 最后兜底：若仍超预算（极端），只剩一条 system+一条 user，最多 budget 字符
                print("[上下文预算] ⚠️ system 提示超出预算，仅保留最后一条用户消息")
                dropped = rest[:-1]
                self._queue_rolling_summary(dropped)
                return self._with_rolling_summary(kept_sys) + [last]

            kept = []
            # ---- 远窗：按清晰度抽，而不是"从新到旧填满就断" ----
            # 清晰度高的旧消息可以挤在低清晰度的新消息前面 —— 现实里就是会这样。
            # 清晰度太低的（低于阈值）当成【真的忘了】，不填也不进摘要：
            # 用摘要把它救回来，就等于"什么都不会忘"，那正是要避免的。
            try:
                import salience as _sal
            except Exception:
                _sal = None

            if _sal is None:
                # 退化到老行为：从新到旧填
                kept, used_rest = [], 0
                for m in reversed(rest):
                    t = self._est_tokens(m.get('content', ''))
                    if used_rest + t > remaining and m is not rest[-1]:
                        break
                    kept.append(m)
                    used_rest += t
                kept.reverse()
                trimmed = len(rest) - len(kept)
                if trimmed:
                    self._queue_rolling_summary(rest[:trimmed])
                return self._with_rolling_summary(system_msgs) + kept

            sel = _sal.select(rest, recent_window=self.recent_window,
                              budget_tokens=remaining, est_tokens=self._est_tokens,
                              now=_time.time(), scale=self._time_scale())
            kept = sel["kept"]
            used_rest = sum(self._est_tokens(m.get('content', '')) for m in kept)
            # 被想起来的节点记一次"提起"——越被提起越牢
            for item in sel["recalled"]:
                try:
                    _sal.mark_mentioned(rest[item["i"]].get("_node_id"))
                except Exception:
                    pass
            # 只有"清晰度够但预算塞不下"的才值得摘要；真忘掉的不摘要
            if sel["dropped"]:
                self._queue_rolling_summary(sel["dropped"])
            n_forget = len(sel["forgotten"])
            n_drop = len(sel["dropped"])
            if n_forget or n_drop:
                print(f"[记忆] 🧠 想起 {len(sel['recalled'])} 条旧事，"
                      f"忘了 {n_forget} 条（清晰度低于阈值），"
                      f"{n_drop} 条塞不下（已转摘要）；预算 {budget} tokens")
            return self._with_rolling_summary(system_msgs) + kept

        # ---------- 软件时间流速 ----------
        def _time_scale(self):
            """世界那边比现实快多少倍。读不到就当作 1（不加速）。"""
            try:
                import time_scale as _ts
                return _ts.load()
            except Exception:
                return 1.0

        # ---------- 生活层（吃饭）：世界时钟 + 厨具历史库 + 食材库 ----------
        def _life_role(self, speaker=None):
            """这一轮在演谁：单角色就是她；群聊按 @ 到的那个（认不出就用第一个）"""
            roles = self.active_roles or []
            if not roles:
                return None
            if speaker:
                for r in roles:
                    if isinstance(r, dict) and r.get("name") == speaker:
                        return r
            return roles[0] if len(roles) == 1 else ({"name": speaker} if speaker else roles[0])

        def _life_world(self):
            """当前世界卡；没初始化好就当没有 —— 少一张世界卡不该把整段生活层弄没"""
            try:
                return self.world_data
            except Exception:
                return None

        def _life_injection(self, chain, speaker=None):
            """生活层注入文本。关掉了 / 没有时间戳 / 出错，都返回 ""。

            出错只打印不抛：这里是每轮回复的必经之路，为一个"生活细节"把整条回复弄挂不值当；
            但**不静默**——日志里看得见（以前插件钩子那种 `except: pass` 就是坑）。
            """
            try:
                import life_core as _life
                if not _life.enabled():
                    return ""
                return _life.injection_text(chain, self._time_scale(),
                                            role=self._life_role(speaker),
                                            world=self._life_world())
            except Exception as e:
                print("[life] 生活层注入失败: %s" % e)
                return ""

        # ---------- 世界记忆（演化）：这个世界现在是什么样 ----------
        def _world_memory_injection(self, chain, speaker=None, user_input=""):
            """每轮注入的【世界·演化】。关掉 / 没有值得提醒的事实 / 出错，都返回 ""。

            与生活层/空间层同一套写法：出错只打印不抛（这是每轮回复的必经之路），
            但不静默 —— 日志里看得见。写入不在这里，而在一轮结束后的插件钩子里
            （注入必须只读，重试/重放不该把强度刷上去）。
            """
            try:
                import world_memory as _wm
                if not _wm.enabled():
                    return ""
                role = self._life_role(speaker)
                return _wm.injection_text(chain, scale=self._time_scale(),
                                          world=self._life_world(),
                                          name=str((role or {}).get("name") or "她"),
                                          focus=user_input)
            except Exception as e:
                print("[world_memory] 世界记忆注入失败: %s" % e)
                return ""

        def _inject_world_context(self, user_input: str) -> str:
            """世界书高级匹配：
            条目支持字段（均向后兼容，缺省即旧行为）：
              match:  "any"(默认，任一关键词子串命中) | "all"(全部命中) | "regex"(关键词作正则)
              weight: 排序权重（缺省取 priority）
              probability: 命中后随机包含的概率 0-100（缺省 100）
              depth:   递归链最大长度（1=仅扫用户输入；2=命中内容可再触发一层；3=两层，以此类推，上限 4）
            """
            if not self.worlds_data:
                return ""
            # 穿梭语义：只扫描当前所在世界的条目（未设置当前世界时回退为全部，兼容旧行为）
            if self.current_world_name:
                worlds_to_scan = [w for w in self.worlds_data if w.get('name') == self.current_world_name]
                if not worlds_to_scan:
                    worlds_to_scan = self.worlds_data
            else:
                worlds_to_scan = self.worlds_data
            text_lower = user_input.lower()
            chosen = []  # (weight, content, entry, world_name)

            def pick(entry, trigger_text, world_name):
                if not entry.get('enabled', True):
                    return None
                content = entry.get('content', '')
                if not content:
                    return None
                constant = bool(entry.get('constant', False))
                if not constant and not self._entry_matches(entry, trigger_text):
                    return None
                prob = entry.get('probability', 100)
                try:
                    prob = float(prob)
                except (TypeError, ValueError):
                    prob = 100
                if prob < 100 and random.random() * 100 > prob:
                    return None
                weight = entry.get('weight', entry.get('priority', 100))
                try:
                    weight = float(weight)
                except (TypeError, ValueError):
                    weight = 100
                # 检索算法：命中质量评分（多关键词命中 / 长词精确命中 → 加分）
                if not constant:
                    kws = entry.get('keywords', [])
                    if isinstance(kws, str):
                        kws = [kws]
                    hits = sum(1 for k in kws if k and self._kw_hit(str(k), trigger_text))
                    exact = sum(1 for k in kws if k and str(k).strip().lower() in trigger_text)
                    weight += hits * 10 + exact * 20
                return (weight, content, entry, world_name)

            for w in worlds_to_scan:
                wname = w.get('name', '未知世界')
                for entry in w.get('entries', []):
                    hit = pick(entry, text_lower, wname)
                    if hit:
                        chosen.append(hit)

            # 递归：命中条目的内容可触发其他世界条目（depth 控制递归轮数，上限 4）
            depth_max = 1
            for w in self.worlds_data:
                for entry in w.get('entries', []):
                    try:
                        depth_max = max(depth_max, int(entry.get('depth', 1) or 1))
                    except (TypeError, ValueError):
                        pass
            depth_max = min(max(depth_max, 1), 4)
            if chosen:
                triggered_text = " ".join(c for _, c, _, _ in chosen).lower()
                for _pass in range(1, depth_max):
                    new_hits = []
                    for w in worlds_to_scan:
                        wname = w.get('name', '未知世界')
                        for entry in w.get('entries', []):
                            if any(entry is e for _, _, e, _ in chosen):
                                continue
                            hit = pick(entry, triggered_text, wname)
                            if hit:
                                chosen.append(hit)
                                new_hits.append(hit)
                    if not new_hits:
                        break
                    triggered_text = " ".join(c for _, c, _, _ in chosen).lower()

            if not chosen:
                return ""
            # 常驻条目不受数量上限约束；关键词命中按权重排序截取
            consts = [x for x in chosen if x[2].get('constant')]
            matched = [x for x in chosen if not x[2].get('constant')]
            matched.sort(key=lambda x: x[0], reverse=True)  # 权重越高越靠前
            max_entries = int(getattr(self, 'world_max_entries', 3))
            lines = []
            for _, c, _, wname in consts + matched[:max_entries]:
                lines.append(f"- [{wname}] {c}")
            return "【当前场景相关信息】\n" + "\n".join(lines) + "\n"

        def _build_role_prompt(self, role):
            """真·多角色群聊：目标角色的专属 system prompt（物理隔离——只含该角色）。
            结构：身份锚 + 该角色提示词 + 该角色机制/战斗（若生效）+ 群聊规则。"""
            name = role.get('name', '未知角色')
            parts = []
            parts.append(f"你现在的身份是：{name}。\n{role.get('system_prompt', '')}")
            adv = role.get('advanced')
            if isinstance(adv, dict):
                game = adv.get('game')
                if isinstance(game, dict) and (game.get('rules') or '').strip():
                    parts.append(f"【内置游戏：{game.get('name') or name}】\n{str(game.get('rules')).strip()}\n"
                                 + (f"初始状态：{str(game.get('state')).strip()}\n"
                                    if (game.get('state') or '').strip() else "")
                                 + "你和玩家按上述规则进行游戏：你负责推进游戏、判定行动、维护并汇报状态；玩家输入即为游戏中的行动。")
                mech = adv.get('mechanics')
                if isinstance(mech, dict) and mech is self._mech_config:
                    block = self._mech_prompt_block(mech)
                    if block:
                        parts.append(block)
                bcfg = adv.get('battle')
                if isinstance(bcfg, dict) and bcfg.get("enabled") and bcfg is self._battle_config():
                    bblock = self._battle_prompt_block(bcfg)
                    if bblock:
                        parts.append(bblock)
                extra = adv.get('extra_prompt')
                if isinstance(extra, str) and extra.strip():
                    parts.append(extra.strip())
            roster = "、".join(r.get('name', f'角色{i+1}') for i, r in enumerate(self.active_roles))
            parts.append(
                "这是一场多人角色扮演群聊，群成员名单：" + roster + "。\n"
                "群聊规则（必守）：\n"
                "1. 你现在扮演【" + name + "】，只以 " + name + " 的人设和口吻发言，绝不模仿其他角色。\n"
                "2. 回复格式必须为：[" + name + "]: 内容。\n"
                "3. 用户消息以「@角色名 内容」指定发言对象；未指定时由与内容最相关的角色回应。\n"
                "4. 严禁替用户（玩家）发言，严禁让多个角色在同一轮同时说话。\n"
                "5. 若此刻没有想说的，只回复：[" + name + "]: 沉默。\n"
            )
            return "\n\n".join(p for p in parts if p and str(p).strip())

        def _rebuild_system_node(self):
            old_system_ids = [nid for nid, node in self.tree.nodes.items() if node.role == 'system']
            first_children = []
            for sid in old_system_ids:
                node = self.tree.nodes.get(sid)
                if node:
                    first_children.extend(node.children_ids)
                    del self.tree.nodes[sid]
                    if self.tree.root_id == sid:
                        self.tree.root_id = None

            combined = ""
            if self.prompt_preset and self.prompt_preset.get('system_prefix'):
                combined += self.prompt_preset['system_prefix'].strip() + "\n\n"
            combined += self.system_prompt_base + "\n"
            # 角色卡高级设置（开发者模式）：内置游戏 / 额外提示 → 注入系统提示
            for idx, role in enumerate(self.active_roles):
                adv = role.get('advanced')
                if not isinstance(adv, dict):
                    continue
                game = adv.get('game')
                if isinstance(game, dict) and (game.get('rules') or '').strip():
                    gname = (game.get('name') or role.get('name') or '内置游戏').strip()
                    combined += f"\n【内置游戏：{gname}】\n{str(game.get('rules')).strip()}\n"
                    if (game.get('state') or '').strip():
                        combined += f"初始状态：{str(game.get('state')).strip()}\n"
                    combined += ("你和玩家按上述规则进行游戏：你负责推进游戏、判定行动、维护并汇报状态；"
                                 "玩家输入即为游戏中的行动。\n")
                # 机制卡（好感度/状态/事件）→ 注入系统提示（只注入当前生效的那份配置）
                mech = adv.get('mechanics')
                if isinstance(mech, dict) and mech is self._mech_config:
                    block = self._mech_prompt_block(mech)
                    if block:
                        combined += block + "\n"
                # 战斗系统（招式/公式/buff）→ 注入系统提示
                bcfg = adv.get('battle')
                if isinstance(bcfg, dict) and bcfg.get("enabled") and bcfg is self._battle_config():
                    bblock = self._battle_prompt_block(bcfg)
                    if bblock:
                        combined += bblock + "\n"
                extra = adv.get('extra_prompt')
                if isinstance(extra, str) and extra.strip():
                    combined += f"\n{extra.strip()}\n"
            if len(self.active_roles) == 1:
                role = self.active_roles[0]
                # 角色卡的 system_prompt 里【自己就带】了「你现在的身份是：X。」
                # （实测 34/35 张卡都这样），这里再加一遍就会重复两行。
                # 重复的身份声明会让模型跟着复读，是「回复重复」的常见来源，
                # 所以先剥掉卡片自带的那行，再统一由程序加一次。
                sp = (role.get('system_prompt') or '').lstrip()
                sp = re.sub(r'^你现在的身份是\s*[：:][^\n]*\n+', '', sp, count=1)
                combined += f"你现在的身份是：{role.get('name', '未知角色')}。\n"
                combined += sp + "\n"
            elif len(self.active_roles) > 1:
                # 真·多角色群聊（每个角色独立调用模型）：system 节点只放「公共框架」，
                # 角色提示词由 _build_role_prompt 按目标角色单独注入（物理隔离，绝不串戏）。
                roster = "、".join(r.get('name', f'角色{i+1}') for i, r in enumerate(self.active_roles))
                combined += (
                    "这是一场多人角色扮演群聊，群成员名单：" + roster + "。\n"
                    "群聊规则（必守）：\n"
                    "1. 每条回复只扮演【一个】群成员，回复格式必须为：[角色名]: 内容（角色名与群成员名单完全一致）。\n"
                    "2. 用户消息以「@角色名 内容」指定发言对象；未指定时由与内容最相关的角色回应。\n"
                    "3. 严禁替用户（玩家）发言，严禁让多个角色在同一轮同时说话。\n"
                    "4. 被指定发言的角色以该角色的人设和口吻回应，其余角色保持沉默。\n"
                    "5. 若本群成员此刻没有想说的，只回复：[角色名]: 沉默。\n"
                )

            if self.worlds_data:
                combined += "\n【平行世界设定】\n"
                for w in self.worlds_data:
                    wname = w.get('name', '未知世界')
                    marker = " ★当前所在" if wname == self.current_world_name else ""
                    combined += f"===== {wname}{marker} =====\n"
                    combined += f"背景：{w.get('description', '')}\n"
                    rules = w.get('rules', [])
                    if rules:
                        combined += "基础规则：\n" + "\n".join([f"- {r}" for r in rules]) + "\n"
                combined += ("以上是多个平行世界，玩家角色可以在其间穿越。"
                             "当前所在世界以 ★ 标注，回复时以当前世界的设定为准，"
                             "玩家穿越后请自然衔接跨世界剧情。\n")

            # 玩家角色卡（乙女/梦女向：称呼、代词、视角、关系都写进去）
            _pb = persona_block(self.player_persona)
            if _pb:
                combined += _pb
            # 反讨好守卫：最近几轮如果一直在顺着说，这一轮就让她有点自己的立场
            _guard = sycophancy_guard_text(self.tree.get_current_chain()[-6:])
            if _guard:
                combined += _guard
            # 人物卡模式（GAL / 乙女·梦向 / 跑团 分开，各自带情感反馈强度）
            if isinstance(self.player_persona, dict):
                _mb = mode_block(self.player_persona.get('mode'), self.player_persona.get('emotional'))
                if _mb:
                    combined += _mb

            # 提示词预设：额外规则与结尾补充
            if self.prompt_preset:
                rules = self.prompt_preset.get('rules', '')
                if isinstance(rules, str) and rules.strip():
                    combined += f"\n【额外规则】\n{rules.strip()}\n"
                suffix = self.prompt_preset.get('system_suffix', '')
                if isinstance(suffix, str) and suffix.strip():
                    combined += f"\n{suffix.strip()}\n"

            # 指令模板扩展：预设可要求回复风格 / 单角色时要求以指定前缀开头（酒馆 instruct 模板的对等物）
            if self.prompt_preset:
                resp_style = self.prompt_preset.get('response_style') or ''
                if isinstance(resp_style, str) and resp_style.strip():
                    combined += f"\n【回复要求】\n{resp_style.strip()}\n"
                asst_prefix = self.prompt_preset.get('assistant_prefix') or ''
                if isinstance(asst_prefix, str) and asst_prefix.strip() and len(self.active_roles) == 1:
                    combined += f"\n回复时请以「{asst_prefix.strip()}」开头。\n"

            # 去 AI 味：默认注入人性化对话规则（设置可关）
            if self.humanize:
                combined += (
                    "\n【对话人性化（必守）】\n"
                    "1. 具体不抽象：说细节（颜色/气味/味道/感受），说「我煮了番茄鸡蛋面，有点咸但很满足」而不是「我吃过了」。\n"
                    "2. 日常生活每次都有变化：食物、天气、活动、心情不固定——不要每次都吃同样的东西、说同样的话。\n"
                    "3. 允许口语与不完美：停顿（……）、语气词（嗯/啊/唉）、抱怨、小失误。\n"
                    "4. 不要模板化：不用固定开场/结尾/句式，不要列表式回复，不用「作为AI」「抱歉我无法」这类词。\n"
                    "5. 聊过的事自然提起，像真的记得（吃过的饭、去过的地方、说过的话）。\n"
                )

            # 语言锚：没有这条，角色名或世界观带日文时模型会直接漂成日语。
            # 实测角色名是「にゃんにゃんファ」这类假名时，正文会整段变日文。
            combined += (
                "\n【语言（必守）】\n"
                "正文一律使用简体中文。不要因为角色名、世界观、参考设定是外文就改用外语；"
                "引用外文时保留原词即可，叙述与对白仍用中文。\n"
            )

            # 中字日配：允许隐藏的日文配音句（[ja]...[/ja] 不显示，仅用于语音合成）
            if self.humanize:
                combined += (
                    "\n【配音句（可选）】\n"
                    "如需配音，在回复【最末尾】附一句日文，并且必须完整包在 [ja] 与 [/ja] 之间，"
                    "例如：……那，我们走吧。[ja]そ、それじゃ、行きましょう。[/ja]\n"
                    "日文只允许出现在这对标签内部 —— 正文里出现任何没有包在标签里的日文都算错误，"
                    "会让用户看到「一段中文接一段日文」，看起来像回复了两遍。\n"
                    "标签本身不会显示给用户，仅用于语音合成；不需要配音时整段省略。\n"
                )

            sys_node = MessageNode('system', combined.strip(), parent_id=None)
            self.tree.nodes[sys_node.id] = sys_node
            self.tree.root_id = sys_node.id

            for cid in first_children:
                if cid in self.tree.nodes:
                    self.tree.nodes[cid].parent_id = sys_node.id
                    sys_node.children_ids.append(cid)

            self.tree.fix_leaf()

        # ---------- API 交互 ----------
        def _opening_prompt(self, cue):
            """把角色卡的开场白改写成「让模型演出第一幕」的指令。

            为什么不直接把开场白当消息贴出来：
                贴出来的是作者写死的文字，和当前选中的世界卡/玩家卡/好感度无关，
                读起来像一段设定文档，而不是「她在对你说话」。交给模型现场演，
                开场才会对上当前配置，用户才有沉浸感。

            两个必须写明的点：
              · 明确这是【场景】不是台词 —— 否则模型会把这段文字原样复述一遍；
              · 明确场景里的「你」指玩家角色 —— 否则「你」会被演成一个没有名字、
                没有外貌的陌生人，玩家角色卡等于白选。
            """
            who = "玩家"
            try:
                nm = (self.player_persona or {}).get("name")
                if nm:
                    who = str(nm)
            except Exception:
                pass
            return (
                "【本场开场 · 由你演出，不是台词】\n"
                "下面是这一场的起点。请以你所扮演角色的身份，把它【演出来】，"
                "作为这段对话的第一幕：\n"
                "1. 用角色的动作、神态、语气把它呈现出来；不要复述、不要解说这段设定文字本身。\n"
                "2. 场景里的「你」指的是玩家角色「%s」。请严格按玩家角色的设定来写他"
                "（名字、外貌、身份都对得上），不要把他写成一个无名无貌的陌生人。\n"
                "3. 篇幅就按平时说话来，像真的在开口，不要写成小说开篇。\n"
                "4. 演完之后，自然留一个让对方能接话的口子，不要自问自答。\n\n"
                "—— 场景如下 ——\n%s" % (who, cue)
            )
