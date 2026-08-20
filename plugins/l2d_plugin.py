# -*- coding: utf-8 -*-
# l2d_plugin.py - Live2D 看板娘插件（默认关闭）
#
# 提供 Live2D 立绘看板娘：需要将模型文件放入 web/live2d/models/ 目录
# （支持 .model3.json 的 Cubism 3/4 模型）。
# 默认关闭（enabled=False），在 ⚙️ 设置 → 插件 中勾选启用，
# 启用后前端会自动加载 web/live2d/vendor/ 下的渲染库并显示立绘。
#
# 依赖（需自行放置，打包时不包含）：
#   web/live2d/vendor/pixi.min.js
#   web/live2d/vendor/live2dcubismcore.min.js
#   web/live2d/vendor/pixi-live2d-display.min.js
import os

from plugin_base import PluginBase


class L2DPlugin(PluginBase):
    name = "Live2D 看板娘"
    version = "1.0"
    description = "Live2D 立绘看板娘（默认关闭）：模型放 web/live2d/models/，启用后显示在聊天界面角落"
    author = "seiki"
    enabled = False  # 默认关闭

    # 插件坞按钮：切换看板娘显隐（Tk 端提示）
    ui_buttons = [
        {"type": "method", "label": "🎎 Live2D", "method": "toggle_display"},
    ]

    settings_schema = [
        {"key": "model", "label": "模型（web/live2d/models/ 下）", "type": "choice",
         "options": [], "default": ""},
        {"key": "scale", "label": "缩放（%）", "type": "int", "default": 100, "min": 30, "max": 300},
        {"key": "pos", "label": "位置", "type": "choice",
         "options": ["右下", "左下", "右上", "左上"], "default": "右下"},
        {"key": "opacity", "label": "不透明度（%）", "type": "int", "default": 95, "min": 20, "max": 100},
        {"key": "draggable", "label": "可拖拽", "type": "bool", "default": True},
        {"key": "breath", "label": "呼吸动画", "type": "bool", "default": True},
    ]

    def __init__(self, core):
        super().__init__(core)
        # 动态填充模型选项（models 目录下的 .model3.json 文件名）
        try:
            models_dir = self._models_dir()
            opts = []
            if os.path.isdir(models_dir):
                for fn in sorted(os.listdir(models_dir)):
                    if fn.endswith(".model3.json"):
                        opts.append(fn)
            schema = list(self.settings_schema)
            for item in schema:
                if item.get("key") == "model":
                    item["options"] = opts
                    if not item.get("default") and opts:
                        item["default"] = opts[0]
            self.settings_schema = schema
        except Exception:
            pass

    def _models_dir(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cand = [
            os.path.join(base_dir, "..", "web", "live2d", "models"),
        ]
        for c in cand:
            if os.path.isdir(c):
                return c
        return cand[0]

    # ---------- 插件坞按钮动作（Tk 端） ----------
    def toggle_display(self):
        """Tk 端没有前端渲染，给出提示"""
        try:
            from tkinter import messagebox
            messagebox.showinfo(
                "Live2D 看板娘",
                "请在 HTML 界面启用：⚙️ 设置 → 插件 → 勾选「Live2D 看板娘」\n\n"
                "模型目录：web/live2d/models/（放置 .model3.json 文件）")
        except Exception:
            pass
