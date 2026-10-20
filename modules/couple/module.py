# -*- coding: utf-8 -*-
"""耦合卡块（coupled pack）：把「主卡 + 世界 + 机制 + 设定表」当成一个不可拆的整体。

契约（kernel 加载用）
    register(kernel)  → 注册服务 "couple"
    service.build(pack, turn, recent_text) → 本轮上下文（分次设定）
接口刻意保持极窄：块不认识宿主，也不碰文件系统。

和"其它模式不兼容"的关系：模式互斥的判定也在本块里（selector.can_enable），
但**谁去关别人的模式是宿主的事**——块只回答"能不能开"。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from . import selector


def register(kernel) -> None:
    kernel.registry.register("couple", CoupleService(), owner="couple")


class CoupleService(object):
    """耦合包服务：校验 + 分次调度。无状态（全部入参传入）。"""

    def validate(self, pack: Dict[str, Any]) -> None:
        selector.validate_pack(pack)

    def can_enable(self, mode: str, active) -> Dict[str, Any]:
        ok, why = selector.can_enable(mode, active)
        return {"ok": ok, "reason": why,
                "modes": selector.modes_after_enable(mode, active) if ok else list(active)}

    def switch_to(self, mode: str, active) -> Dict[str, Any]:
        """强制切到 mode：互斥组里的其它模式自动关掉，返回切换后的集合。

        和 can_enable 的区别：can_enable 只回答"能不能"（不改变任何东西），
        switch_to 才真的给出"切换后的世界"。UI 上先问再切，两件事别混。
        """
        modes = selector.modes_after_enable(mode, active)
        return {"ok": True, "mode": mode, "modes": modes}

    def build(self, pack: Dict[str, Any], turn: int = 0, recent_text: str = "",
              used_recently: Optional[set] = None,
              budget_chars: Optional[int] = None) -> Dict[str, Any]:
        return selector.select_settings(pack, turn=turn, recent_text=recent_text,
                                        used_recently=used_recently,
                                        budget_chars=budget_chars)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌