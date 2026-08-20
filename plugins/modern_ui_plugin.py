# ============================================================
#   modern_ui_plugin.py - 现代界面（主题美化插件）v1.0
#
#   一键把整个应用换成现代化外观：
#   - 6 种现代强调色（电光蓝/霓虹紫/极光青/翡翠绿/活力橙/樱花粉）
#   - 3 套主题模式（深色 / 浅色 / OLED 纯黑）
#   - 圆角大小、紧凑模式
#   - 🎨 主题中心面板（卡片式设计，点击色块即时预览）
#
#   使用新插件体系：settings_schema 生成设置窗口 + ui_buttons 注册插件坞按钮
# ============================================================

import tkinter as tk

from customtkinter import (CTk, CTkButton, CTkCheckBox, CTkEntry, CTkFrame,
                           CTkLabel, CTkOptionMenu, CTkScrollableFrame, CTkSlider,
                           CTkSwitch, CTkTabview, CTkTextbox, CTkToplevel,
                           set_appearance_mode)

import ui_fonts as uf
from plugin_base import PluginBase


class ModernUIPlugin(PluginBase):
    name = "现代界面"
    version = "1.0"
    description = "现代化主题美化：强调色、深色/浅色/OLED、圆角与紧凑模式"
    author = "seiki"
    enabled = True

    # 插件坞按钮：打开主题中心
    ui_buttons = [
        {"type": "method", "label": "🎨 主题", "method": "open_panel"},
    ]

    # 声明式设置（⚙️ 自动生成设置窗口）
    settings_schema = [
        {"key": "accent", "label": "强调色", "type": "choice",
         "options": ["电光蓝", "霓虹紫", "极光青", "翡翠绿", "活力橙", "樱花粉"],
         "default": "电光蓝"},
        {"key": "mode", "label": "主题模式", "type": "choice",
         "options": ["深色", "浅色", "OLED"], "default": "深色"},
        {"key": "radius", "label": "圆角大小", "type": "int",
         "default": 8, "min": 0, "max": 24},
        {"key": "compact", "label": "紧凑模式（更小的控件高度）", "type": "bool",
         "default": False},
    ]

    # ---------- 调色板 ----------
    ACCENTS = {
        "电光蓝": "#3b82f6", "霓虹紫": "#8b5cf6", "极光青": "#06b6d4",
        "翡翠绿": "#10b981", "活力橙": "#f97316", "樱花粉": "#ec4899",
    }
    # 会被替换成强调色的"旧默认蓝"
    DEFAULT_BLUES = {"#1f6aa5", "#3a7ebf", "#2b5e8b", "#1e4566"}

    def on_load(self):
        # 插件在窗口构建前加载，延后到界面就绪后再应用主题
        try:
            root = tk._default_root
            if root:
                root.after(600, self.apply_theme)
        except Exception:
            pass
        print("[现代界面] 已加载：主题将自动应用（点击 🎨 主题 打开主题中心）")

    # ============================================================
    # 调色板与配色工具
    # ============================================================
    def accent_color(self):
        name = self.get_setting("accent", "电光蓝")
        return self.ACCENTS.get(name, "#3b82f6")

    def palette(self):
        mode = self.get_setting("mode", "深色")
        if mode == "OLED":
            return {"appearance": "dark", "bg": "#000000", "frame": "#0a0a0c",
                    "hover": "#18181c", "text": "#e5e7eb", "muted": "#9ca3af",
                    "chat_bg": "#000000", "chat_fg": "#e5e7eb"}
        if mode == "浅色":
            return {"appearance": "light", "bg": "#f5f6f8", "frame": "#ffffff",
                    "hover": "#e9edf2", "text": "#1f2937", "muted": "#6b7280",
                    "chat_bg": "#ffffff", "chat_fg": "#111827"}
        return {"appearance": "dark", "bg": "#0f1115", "frame": "#161a22",
                "hover": "#1f2430", "text": "#e5e7eb", "muted": "#9ca3af",
                "chat_bg": "#0d1016", "chat_fg": "#e5e7eb"}

    @staticmethod
    def _darken(hex_color, factor=0.78):
        """把十六进制颜色变暗，生成 hover 色"""
        try:
            h = hex_color.lstrip("#")
            r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
            return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"
        except Exception:
            return hex_color

    def _walk(self, widget):
        yield widget
        try:
            for child in widget.winfo_children():
                yield from self._walk(child)
        except Exception:
            return

    # ============================================================
    # 主题应用引擎
    # ============================================================
    def apply_theme(self):
        """把当前设置应用到整个界面（可重复调用，即时生效）"""
        try:
            root = tk._default_root
        except Exception:
            root = None
        if not root:
            return
        pal = self.palette()
        accent = self.accent_color()
        hover = self._darken(accent)
        radius = int(self.get_setting("radius", 8))
        compact = bool(self.get_setting("compact", False))
        set_appearance_mode(pal["appearance"])

        try:
            root.configure(fg_color=pal["bg"])
        except Exception:
            pass

        btn_h = 26 if compact else 30
        for w in self._walk(root):
            try:
                if isinstance(w, CTkButton):
                    cur = w.cget("fg_color")
                    if cur in self.DEFAULT_BLUES or cur == "transparent":
                        w.configure(fg_color=accent, hover_color=hover,
                                    corner_radius=radius, height=btn_h)
                    else:
                        w.configure(corner_radius=radius, height=btn_h)
                elif isinstance(w, CTkEntry):
                    w.configure(fg_color=pal["frame"], text_color=pal["text"],
                                corner_radius=radius, border_color=hover)
                elif isinstance(w, CTkTextbox):
                    w.configure(fg_color=pal["chat_bg"], text_color=pal["chat_fg"],
                                corner_radius=radius)
                elif isinstance(w, CTkFrame) or isinstance(w, CTkScrollableFrame):
                    if w.cget("fg_color") not in (None, "transparent"):
                        w.configure(corner_radius=radius)
                elif isinstance(w, CTkLabel):
                    cur = w.cget("text_color")
                    # None 或主题元组（未显式设色）→ 应用现代文字色；
                    # 显式颜色（gray/green/red...）保持不变
                    if cur is None or not isinstance(cur, str):
                        w.configure(text_color=pal["text"])
                elif isinstance(w, CTkOptionMenu):
                    w.configure(fg_color=pal["frame"], button_color=pal["frame"],
                                button_hover_color=pal["hover"], text_color=pal["text"],
                                corner_radius=radius)
                elif isinstance(w, CTkSlider):
                    w.configure(progress_color=accent, button_color=accent)
                elif isinstance(w, CTkSwitch):
                    w.configure(progress_color=accent, button_color=accent)
                elif isinstance(w, CTkCheckBox):
                    w.configure(fg_color=accent, border_color=hover,
                                hover_color=hover, checkmark_color=pal["bg"])
                elif isinstance(w, CTkTabview):
                    w.configure(fg_color=pal["bg"])
                elif isinstance(w, tk.Listbox):
                    w.configure(bg=pal["frame"], fg=pal["text"],
                                selectbackground=accent)
            except Exception:
                continue

        # 聊天区 tag 颜色（token 信息等）
        for w in self._walk(root):
            if isinstance(w, CTkTextbox):
                try:
                    w.tag_config("token_info", foreground=pal["muted"])
                except Exception:
                    pass
        return True

    # ============================================================
    # 🎨 主题中心面板（卡片式现代设计）
    # ============================================================
    def open_panel(self):
        root = tk._default_root
        panel = CTkToplevel(root)
        panel.title("🎨 主题中心")
        panel.geometry("460x560")
        panel.transient(root)

        pal = self.palette()
        accent = self.accent_color()
        radius = int(self.get_setting("radius", 8))

        def card(parent, title, subtitle=""):
            c = CTkFrame(parent, corner_radius=14, fg_color=pal["frame"])
            c.pack(fill="x", padx=12, pady=6)
            CTkLabel(c, text=title, font=uf.f("normal", bold=True)).pack(anchor="w", padx=14, pady=(10, 0))
            if subtitle:
                CTkLabel(c, text=subtitle, font=uf.f("small"),
                         text_color=pal["muted"]).pack(anchor="w", padx=14)
            return c

        scroll = CTkScrollableFrame(panel, fg_color=pal["bg"], corner_radius=0)
        scroll.pack(fill="both", expand=True)

        # ---- 卡片 1：强调色 ----
        c1 = card(scroll, "🎨 强调色", "点击色块即时预览并保存")
        row = CTkFrame(c1, fg_color="transparent")
        row.pack(anchor="w", padx=14, pady=(8, 12))
        for i, (name, color) in enumerate(self.ACCENTS.items()):
            sw = CTkButton(row, text="", width=36, height=36, corner_radius=18,
                           fg_color=color, hover_color=self._darken(color),
                           command=lambda n=name: self._pick_accent(n, panel, scroll, pal))
            sw.pack(side="left", padx=5)

        # ---- 卡片 2：模式 ----
        c2 = card(scroll, "🌗 主题模式")
        row2 = CTkFrame(c2, fg_color="transparent")
        row2.pack(anchor="w", padx=14, pady=(8, 12))
        for mode in ("深色", "浅色", "OLED"):
            CTkButton(row2, text=mode, width=76, corner_radius=radius,
                      fg_color=accent if self.get_setting("mode") == mode else pal["frame"],
                      hover_color=self._darken(accent),
                      text_color=pal["text"] if self.get_setting("mode") != mode else "#ffffff",
                      command=lambda m=mode: self._pick_mode(m, panel, scroll)).pack(side="left", padx=5)

        # ---- 卡片 3：圆角 ----
        c3 = card(scroll, "🔲 圆角大小", "0 = 直角（更硬朗），24 = 大圆角（更柔和）")
        radius_var = tk.IntVar(value=int(self.get_setting("radius", 8)))
        CTkSlider(c3, from_=0, to=24, number_of_steps=24, variable=radius_var,
                  command=lambda v: self._pick_radius(int(v), panel, scroll)).pack(fill="x", padx=14, pady=(6, 12))

        # ---- 卡片 4：紧凑模式 ----
        c4 = card(scroll, "📏 紧凑模式", "更小的控件高度，适合小屏幕")
        compact_var = tk.BooleanVar(value=bool(self.get_setting("compact", False)))
        CTkSwitch(c4, text="", variable=compact_var,
                  command=lambda: self._pick_compact(compact_var.get(), panel, scroll)).pack(anchor="w", padx=14, pady=(4, 12))

        # ---- 底部 ----
        btn = CTkFrame(panel, fg_color="transparent")
        btn.pack(fill="x", pady=10)
        CTkButton(btn, text="🔄 恢复默认", fg_color="#8b0000", hover_color="#5e0000",
                  command=lambda: self._reset(panel, scroll)).pack(side="left", padx=14)
        CTkButton(btn, text="关闭", command=panel.destroy).pack(side="right", padx=14)
        panel.grab_set()

    # ---- 面板交互（即时应用 + 保存） ----
    def _rebuild_panel(self, panel):
        """销毁旧面板并开新面板（旧面板引用随之失效）"""
        try:
            panel.destroy()
        except Exception:
            pass
        self.open_panel()

    def _pick_accent(self, name, panel, scroll, pal):
        self.set_setting("accent", name)
        self.apply_theme()
        self._rebuild_panel(panel)

    def _pick_mode(self, mode, panel, scroll):
        self.set_setting("mode", mode)
        self.apply_theme()
        self._rebuild_panel(panel)

    def _pick_radius(self, val, panel, scroll):
        self.set_setting("radius", int(val))
        self.apply_theme()

    def _pick_compact(self, on, panel, scroll):
        self.set_setting("compact", bool(on))
        self.apply_theme()

    def _reset(self, panel, scroll):
        for item in self.settings_schema:
            self.set_setting(item["key"], item["default"])
        self.apply_theme()
        self._rebuild_panel(panel)
