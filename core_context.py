# -*- coding: utf-8 -*-
"""core_context —— 上下文注入策略（从 DICK_core.py 拆出）。

`ContextInjector` 只做一件事：决定"这一次请求往提示里塞什么"（世界卡、记忆、
时间、角色状态…），不负责发请求。把它单独放，是因为它是最常被改的一张策略表。
"""
from __future__ import annotations

class ContextInjector:
    """动态上下文注入器 - 从索引文件中按关键词检索"""
    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self.indices = {}  # {index_filename: index_data}
        self._load_all_indices()

    def _load_all_indices(self):
        """加载所有 .index.json 文件"""
        if not os.path.exists(self.index_dir):
            return
        for fname in os.listdir(self.index_dir):
            if fname.endswith('.index.json'):
                try:
                    with open(os.path.join(self.index_dir, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.indices[fname] = data
                except Exception as e:
                    print(f"[ContextInjector] 加载索引失败: {fname} - {e}")

    def get_context(self, user_input: str, max_entries: int = 3, priority_threshold: int = 200) -> str:
        """
        根据用户输入检索相关条目，返回拼接后的上下文
        :param user_input: 用户消息
        :param max_entries: 最多返回几条
        :param priority_threshold: 只返回 priority <= 此值的条目（越小越优先）
        """
        if not user_input or not self.indices:
            return ""

        # 提取关键词<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（简单分词）
        words = set()
        for w in re.split(r'[，,、。.！!？?；;：:\s\n]+', user_input):
            w = w.strip()
            if len(w) >= 2:
                words.add(w.lower())

        if not words:
            return ""

        # 匹配所有索引
        matched = []
        for idx_name, idx_data in self.indices.items():
            for entry in idx_data.get('entries', []):
                entry_priority = entry.get('priority', 100)
                if entry_priority > priority_threshold:
                    continue
                entry_keys = [k.lower() for k in entry.get('keywords', [])]
                # 检查是否有关键词匹配
                for word in words:
                    for key in entry_keys:
                        if word in key or key in word:
                            matched.append(entry)
                            break
                    else:
                        continue
                    break

        # 去重（按 content 去重）
        seen = set()
        unique = []
        for entry in matched:
            content = entry.get('content', '')
            if content not in seen:
                seen.add(content)
                unique.append(entry)

        # 按优先级排序
        unique.sort(key=lambda x: x.get('priority', 100))

        # 取前 max_entries 条
        selected = unique[:max_entries]
        if not selected:
            return ""

        # 拼接成上下文
        parts = []
        for entry in selected:
            comment = entry.get('comment', '')
            content = entry.get('content', '')
            if comment:
                parts.append(f"【{comment}】\n{content}")
            else:
                parts.append(content)

        return "\n\n".join(parts)


# ============================================================
#   ChatCore - 对话核心（整合 TreeManager + API + 动态注入）
# ============================================================
GAP_NOTICE_SECONDS = 30 * 60      # 小于这个间隔不吭声（"刚说的话"不值得标注）
GAP_MAX_MARKS = 3                 # 最多标几段间隔，防止长历史把提示撑大
DAY_NOTICE_HOURS = 20             # 超过这么久，报"天"而不是"小时"
