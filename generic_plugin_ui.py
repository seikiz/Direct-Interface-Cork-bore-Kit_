# ============================================================
#   generic_plugin_ui.py - 泛用插件设置界面（声明式渲染器）
#
#   插件只需在类上声明 settings_schema（见 plugin_base.py 注释），
#   调用 open_plugin_settings(master, plugin) 即自动生成设置窗口：
#   插件作者从此不需要写任何 Tkinter 代码。
#
#   支持类型: text / secret / int / bool / choice / file
# ============================================================

import tkinter as tk
from tkinter import filedialog, messagebox
from customtkinter import *

import ui_fonts as uf


def open_plugin_settings(master, plugin):
    """根据插件的 settings_schema 自动生成设置窗口"""
    schema = getattr(plugin, "settings_schema", None) or []
    if not schema:
        messagebox.showinfo("提示", f"「{plugin.name}」没有可配置项")
        return

    dialog = CTkToplevel(master)
    dialog.title(f"⚙️ {plugin.name} - 设置")
    dialog.geometry("500x520")
    dialog.transient(master)
    dialog.grab_set()

    CTkLabel(dialog, text=f"⚙️ {plugin.name} 设置", font=uf.f("header", bold=True)).pack(pady=(14, 2))
    CTkLabel(dialog, text=f"v{plugin.version} · {plugin.author}",
             font=uf.f("small"), text_color="gray").pack(pady=(0, 8))

    scroll = CTkScrollableFrame(dialog, width=460, height=380)
    scroll.pack(fill="both", expand=True, padx=12, pady=6)

    # key -> (widget_var, type, meta)
    widgets = {}

    def browse(var):
        path = filedialog.askopenfilename(title="选择文件")
        if path:
            var.set(path)

    for item in schema:
        key = item.get("key")
        if not key:
            continue
        label = item.get("label", key)
        typ = item.get("type", "text")
        default = item.get("default")
        current = plugin.get_setting(key, default)

        frame = CTkFrame(scroll)
        frame.pack(fill="x", pady=4, padx=4)
        CTkLabel(frame, text=label, font=uf.f("normal")).pack(anchor="w", padx=8, pady=(6, 0))

        if typ == "bool":
            var = tk.BooleanVar(value=bool(current))
            CTkSwitch(frame, text="", variable=var).pack(anchor="w", padx=8, pady=(0, 6))
            widgets[key] = (var, "bool", item)
        elif typ == "choice":
            options = item.get("options", [])
            if not isinstance(options, list) or not options:
                options = [""]
            value = str(current) if current in options else options[0]
            var = tk.StringVar(value=value)
            CTkOptionMenu(frame, values=options, variable=var, width=220).pack(anchor="w", padx=8, pady=(0, 6))
            widgets[key] = (var, "choice", item)
        elif typ == "int":
            var = tk.StringVar(value=str(current))
            CTkEntry(frame, textvariable=var, width=220).pack(anchor="w", padx=8, pady=(0, 6))
            widgets[key] = (var, "int", item)
        elif typ == "file":
            var = tk.StringVar(value=str(current))
            row = CTkFrame(frame)
            row.pack(fill="x", padx=8, pady=(0, 6))
            CTkEntry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            CTkButton(row, text="📂 浏览", width=70, command=lambda v=var: browse(v)).pack(side="left", padx=(6, 0))
            widgets[key] = (var, "file", item)
        else:  # text / secret
            var = tk.StringVar(value=str(current))
            CTkEntry(frame, textvariable=var, width=300,
                     show="*" if typ == "secret" else "").pack(anchor="w", padx=8, pady=(0, 6))
            widgets[key] = (var, "text", item)

    btn_frame = CTkFrame(dialog)
    btn_frame.pack(fill="x", pady=10)

    def save():
        for key, (var, typ, meta) in widgets.items():
            raw = var.get()
            if typ == "bool":
                plugin.set_setting(key, bool(raw))
            elif typ == "int":
                try:
                    val = int(str(raw).strip())
                except ValueError:
                    messagebox.showerror("错误", f"「{meta.get('label', key)}」必须是整数")
                    return
                if meta.get("min") is not None:
                    val = max(int(meta["min"]), val)
                if meta.get("max") is not None:
                    val = min(int(meta["max"]), val)
                plugin.set_setting(key, val)
            else:
                plugin.set_setting(key, raw)
        plugin._save_settings()
        messagebox.showinfo("成功", "设置已保存，立即生效")
        dialog.destroy()

    CTkButton(btn_frame, text="💾 保存", command=save, width=130).pack(side="left", padx=14)
    CTkButton(btn_frame, text="恢复默认", command=lambda: _reset_defaults(plugin, widgets), width=100).pack(side="left", padx=6)
    CTkButton(btn_frame, text="取消", command=dialog.destroy, width=80).pack(side="right", padx=14)


def _reset_defaults(plugin, widgets):
    if not messagebox.askyesno("确认", "恢复所有设置项为默认值？"):
        return
    for item in plugin.settings_schema:
        key = item.get("key")
        if key:
            plugin.set_setting(key, item.get("default"))
    # 刷新窗口中的控件值
    for key, (var, typ, meta) in widgets.items():
        default = next((i.get("default") for i in plugin.settings_schema if i.get("key") == key), None)
        if typ == "bool":
            var.set(bool(default))
        else:
            var.set("" if default is None else str(default))
    messagebox.showinfo("成功", "已恢复默认设置")
