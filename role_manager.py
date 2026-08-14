# ============================================================
#   role_manager.py - 多角色管理器
#   负责角色选择、@all 处理、消息前缀构建
# ============================================================

from typing import List, Optional, Callable
import re


class RoleManager:
    """管理多角色选择与消息前缀构建"""
    def __init__(self):
        self.active_roles: List[str] = []  # 角色名列表（不含 .json）
        self.speaker: Optional[str] = None  # 当前选中的角色，或 "@全部"

    def update_roles(self, role_names: List[str]):
        """更新激活的角色列表，并重置选择"""
        self.active_roles = role_names
        if not role_names:
            self.speaker = None
        elif len(role_names) == 1:
            self.speaker = role_names[0]
        else:
            # 多角色时，默认选中第一个，不选 @全部
            self.speaker = role_names[0]

    def set_speaker(self, speaker: str):
        """设置当前说话角色（可以是角色名或"@全部"）"""
        if speaker == "@全部" or speaker in self.active_roles:
            self.speaker = speaker
        else:
            raise ValueError(f"无效的说话角色：{speaker}")

    def get_speaker_options(self) -> List[str]:
        """获取下拉菜单选项"""
        if len(self.active_roles) <= 1:
            return []
        return ["@全部"] + self.active_roles

    def build_send_content(self, user_input: str) -> str:
        """
        根据当前说话角色构建实际发送的消息内容
        返回带 @ 前缀的字符串
        """
        if not self.speaker:
            return user_input

        # 如果用户已手动输入 @，则不再重复添加
        if user_input.startswith("@"):
            return user_input

        if self.speaker == "@全部":
            # 构建 @角色1 @角色2 ... 前缀
            prefix = " ".join([f"@{name}" for name in self.active_roles])
            return f"{prefix} {user_input}"
        else:
            # 单角色
            return f"@{self.speaker} {user_input}"

    def is_multi_role(self) -> bool:
        """是否激活了多个角色"""
        return len(self.active_roles) > 1

    def get_current_speaker_display(self) -> str:
        """获取当前说话角色的显示文本"""
        if not self.speaker:
            return "无"
        return self.speaker