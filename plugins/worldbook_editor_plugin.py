# ============================================================
#   worldbook_editor_plugin.py - 世界书傻瓜式编辑器 v1.0
#
#   可视化编辑世界卡：世界信息（名称/描述/规则）+ 条目
#   （关键词/内容/匹配方式/权重/概率），全程不用手写 JSON。
#   保存后若编辑的是当前载入的世界卡，自动热更新。
# ============================================================

import json
import os
import re

import tkinter as tk
from tkinter import messagebox
from customtkinter import *

import app_paths
import ui_fonts as uf
from plugin_base import PluginBase

MATCH_OPTIONS = {
    "任一关键词命中（默认）": "any",
    "全部关键词都命中": "all",
    "正则表达式匹配": "regex",
}


class WorldbookEditorPlugin(PluginBase):
    name = "世界书编辑器"
    version = "1.0"
    description = "傻瓜式编辑世界卡条目：关键词/内容/匹配/权重/概率，不用手写 JSON"
    author = "seiki"
    enabled = True

    ui_buttons = [
        {"type": "method", "label": "📖 世界书", "method": "open_editor"},
    ]

    def __init__(self, core):
        super().__init__(core)
        self.world_dir = os.path.join(app_paths.get_base_dir(), "worlds")
        os.makedirs(self.world_dir, exist_ok=True)
        self.window = None
        self.current_file = None
        self.current_data = None

    # ==================== 纯逻辑（可测试） ====================
    def list_world_files(self):
        try:
            return sorted(f for f in os.listdir(self.world_dir) if f.endswith(".json"))
        except Exception:
            return []

    def read_world(self, filename):
        with open(os.path.join(self.world_dir, filename), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("不是有效的世界卡文件")
        data.setdefault("name", filename[:-5])
        data.setdefault("description", "")
        data.setdefault("rules", [])
        data.setdefault("entries", [])
        return data

    def write_world(self, filename, data):
        with open(os.path.join(self.world_dir, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._reload_if_active(data)

    def _reload_if_active(self, data):
        """若编辑的是当前载入的世界卡，热更新到核心"""
        core = self.core
        worlds = getattr(core, "worlds_data", None) or []
        name = data.get("name")
        if name and any(w.get("name") == name for w in worlds):
            core.set_worlds([data if w.get("name") == name else w for w in worlds])

    def normalize_entry(self, e):
        """把条目规范化为标准字段（兼容 keys 旧字段）"""
        e = dict(e)
        kws = e.get("keywords") or e.get("keys") or []
        if isinstance(kws, str):
            kws = [kws]
        flat = []
        for k in kws:
            for part in str(k).replace("，", ",").split(","):
                part = part.strip()
                if part:
                    flat.append(part)
        e["keywords"] = flat
        e["content"] = str(e.get("content", "")).strip()
        e["match"] = e.get("match", "any")
        e["weight"] = int(e.get("weight", 100))
        e["probability"] = int(e.get("probability", 100))
        if e.get("comment"):
            e["comment"] = str(e["comment"]).strip()
        return e

    # ==================== 窗口 ====================
    def open_editor(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        w = CTkToplevel()
        w.title("📖 世界书编辑器")
        w.geometry("720x600")
        self.window = w

        # ---- 顶部：选择世界卡 ----
        top = CTkFrame(w)
        top.pack(fill="x", padx=10, pady=(10, 4))
        CTkLabel(top, text="世界卡：", font=uf.f("normal")).pack(side="left", padx=5)
        self.file_var = tk.StringVar(value="")
        self.file_menu = CTkOptionMenu(top, values=["（请选择）"] + self.list_world_files(),
                                       variable=self.file_var, width=240,
                                       command=lambda _: self._open_selected())
        self.file_menu.pack(side="left", padx=5)
        CTkButton(top, text="🔄 刷新", command=self._refresh_files, width=70).pack(side="left", padx=5)
        CTkButton(top, text="➕ 新建世界卡", command=self._new_world, width=110).pack(side="left", padx=5)

        # ---- 世界信息 ----
        info = CTkFrame(w)
        info.pack(fill="x", padx=10, pady=4)
        CTkLabel(info, text="名称：", font=uf.f("small")).pack(side="left", padx=5)
        self.name_entry = CTkEntry(info, width=150, font=uf.f("small"))
        self.name_entry.pack(side="left", padx=(0, 8))
        CTkLabel(info, text="描述：", font=uf.f("small")).pack(side="left", padx=5)
        self.desc_entry = CTkEntry(info, width=330, font=uf.f("small"))
        self.desc_entry.pack(side="left", padx=(0, 8))
        CTkLabel(info, text="规则（每行一条）：", font=uf.f("small")).pack(anchor="w", padx=5)
        self.rules_box = CTkTextbox(info, height=54, font=uf.f("small"))
        self.rules_box.pack(fill="x", padx=5, pady=(0, 5))

        # ---- 条目列表 ----
        mid = CTkFrame(w)
        mid.pack(fill="both", expand=True, padx=10, pady=4)
        self.entry_listbox = tk.Listbox(mid, bg="#2b2b2b", fg="white",
                                        selectbackground="#1f6aa5", font=("微软雅黑", 10))
        self.entry_listbox.pack(side="left", fill="both", expand=True, padx=(0, 6))
        btns = CTkFrame(mid, width=150)
        btns.pack(side="right", fill="y")
        CTkButton(btns, text="➕ 添加条目", command=self._add_entry, width=130).pack(pady=3)
        CTkButton(btns, text="✏️ 编辑条目", command=self._edit_entry, width=130).pack(pady=3)
        CTkButton(btns, text="🗑️ 删除条目", fg_color="#8b0000", hover_color="#5e0000",
                  command=self._del_entry, width=130).pack(pady=3)
        CTkButton(btns, text="⬆ 上移", command=lambda: self._move_entry(-1), width=130).pack(pady=3)
        CTkButton(btns, text="⬇ 下移", command=lambda: self._move_entry(1), width=130).pack(pady=3)

        # ---- 底部 ----
        bottom = CTkFrame(w)
        bottom.pack(fill="x", padx=10, pady=(4, 10))
        self.status_label = CTkLabel(bottom, text="请选择或新建世界卡", font=uf.f("small"),
                                     text_color="gray")
        self.status_label.pack(side="left", padx=8)
        CTkButton(bottom, text="💾 保存", command=self._save, width=100).pack(side="right", padx=5)
        CTkButton(bottom, text="❌ 关闭", command=w.destroy, width=80).pack(side="right", padx=5)

    # ---- 交互 ----
    def _refresh_files(self):
        self.file_menu.configure(values=["（请选择）"] + self.list_world_files())
        self.file_var.set("（请选择）")

    def _open_selected(self):
        name = self.file_var.get()
        if not name or name == "（请选择）":
            return
        try:
            self.current_file = name
            self.current_data = self.read_world(name)
            self._load_into_ui()
            self.status_label.configure(text=f"已载入：{name}（{len(self.current_data['entries'])} 个条目）",
                                        text_color="green")
        except Exception as e:
            messagebox.showerror("错误", f"读取失败：{e}")

    def _load_into_ui(self):
        d = self.current_data
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, d.get("name", ""))
        self.desc_entry.delete(0, tk.END)
        self.desc_entry.insert(0, d.get("description", ""))
        self.rules_box.delete("1.0", "end")
        self.rules_box.insert("1.0", "\n".join(d.get("rules", [])))
        self._refresh_entry_list()

    def _refresh_entry_list(self):
        self.entry_listbox.delete(0, tk.END)
        for e in self.current_data.get("entries", []):
            kws = ",".join((e.get("keywords") or [])[:4])
            content = (e.get("content") or "")[:30]
            self.entry_listbox.insert(tk.END, f"[{kws}] {content}")

    def _new_world(self):
        name = self._ask_text("新建世界卡", "世界卡名称（保存时会生成 .json 文件）：")
        if not name:
            return
        safe = re.sub(r'[\\/:*?"<>|]', '_', name).strip('_.') or "新世界"
        filename = f"{safe}.json"
        if filename in self.list_world_files():
            messagebox.showwarning("提示", "同名世界卡已存在，请直接选择它")
            return
        self.current_file = filename
        self.current_data = {"name": name, "description": "", "rules": [], "entries": []}
        self._load_into_ui()
        self._refresh_files()
        self.file_var.set(filename)
        self.status_label.configure(text=f"新世界卡已就绪：{filename}（记得点 💾 保存）", text_color="green")

    def _ask_text(self, title, prompt):
        from tkinter import simpledialog
        return simpledialog.askstring(title, prompt, parent=self.window)

    def _save(self):
        if not self.current_data:
            messagebox.showwarning("提示", "还没有可保存的世界卡")
            return
        d = self.current_data
        d["name"] = self.name_entry.get().strip() or "未命名世界"
        d["description"] = self.desc_entry.get().strip()
        d["rules"] = [r.strip() for r in self.rules_box.get("1.0", "end").split("\n") if r.strip()]
        try:
            self.write_world(self.current_file, d)
            self.status_label.configure(text=f"✅ 已保存：{self.current_file}", text_color="green")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    def _add_entry(self):
        if not self.current_data:
            messagebox.showwarning("提示", "请先选择或新建世界卡")
            return
        entry = self._entry_dialog(None)
        if entry:
            self.current_data.setdefault("entries", []).append(entry)
            self._refresh_entry_list()

    def _edit_entry(self):
        idx = self._selected_index()
        if idx is None:
            return
        entry = self._entry_dialog(self.current_data["entries"][idx])
        if entry:
            self.current_data["entries"][idx] = entry
            self._refresh_entry_list()

    def _del_entry(self):
        idx = self._selected_index()
        if idx is None:
            return
        if not messagebox.askyesno("确认", "删除这条世界书条目？"):
            return
        self.current_data["entries"].pop(idx)
        self._refresh_entry_list()

    def _move_entry(self, direction):
        idx = self._selected_index()
        if idx is None:
            return
        entries = self.current_data["entries"]
        nxt = idx + direction
        if 0 <= nxt < len(entries):
            entries[idx], entries[nxt] = entries[nxt], entries[idx]
            self._refresh_entry_list()
            self.entry_listbox.selection_set(nxt)

    def _selected_index(self):
        sel = self.entry_listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选择一个条目")
            return None
        return sel[0]

    def _entry_dialog(self, entry):
        """条目编辑对话框（傻瓜式：每个字段带说明）"""
        entry = entry or {}
        dlg = CTkToplevel(self.window)
        dlg.title("编辑条目" if entry.get("content") else "添加条目")
        dlg.geometry("560x560")
        dlg.transient(self.window)
        dlg.grab_set()

        scroll = CTkScrollableFrame(dlg, width=520, height=470)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        CTkLabel(scroll, text="🔑 关键词（逗号分隔）", font=uf.f("normal")).pack(anchor="w", padx=8, pady=(8, 0))
        CTkLabel(scroll, text="AI 看到这些词出现，就会想起下面这条内容", font=uf.f("small"),
                 text_color="gray").pack(anchor="w", padx=8)
        kws_entry = CTkEntry(scroll, height=34)
        kws_entry.insert(0, ",".join(entry.get("keywords") or []))
        kws_entry.pack(fill="x", padx=8, pady=(2, 6))

        CTkLabel(scroll, text="📝 内容", font=uf.f("normal")).pack(anchor="w", padx=8, pady=(6, 0))
        CTkLabel(scroll, text="命中关键词时注入给 AI 的知识", font=uf.f("small"),
                 text_color="gray").pack(anchor="w", padx=8)
        content_box = CTkTextbox(scroll, height=130, font=uf.f("small"))
        content_box.insert("1.0", entry.get("content", ""))
        content_box.pack(fill="x", padx=8, pady=(2, 6))

        CTkLabel(scroll, text="🎯 匹配方式", font=uf.f("normal")).pack(anchor="w", padx=8, pady=(6, 0))
        match_var = tk.StringVar(value="任一关键词命中（默认）")
        for label, value in MATCH_OPTIONS.items():
            if value == entry.get("match", "any"):
                match_var.set(label)
        CTkOptionMenu(scroll, values=list(MATCH_OPTIONS.keys()), variable=match_var,
                      width=260).pack(anchor="w", padx=8, pady=(2, 6))

        row = CTkFrame(scroll)
        row.pack(fill="x", padx=8, pady=4)
        CTkLabel(row, text="⚖️ 权重（越大越先注入）", font=uf.f("normal")).pack(side="left", padx=(0, 4))
        weight_entry = CTkEntry(row, width=70)
        weight_entry.insert(0, str(entry.get("weight", 100)))
        weight_entry.pack(side="left", padx=(0, 14))
        CTkLabel(row, text="🎲 概率（100=必中）", font=uf.f("normal")).pack(side="left", padx=(0, 4))
        prob_entry = CTkEntry(row, width=70)
        prob_entry.insert(0, str(entry.get("probability", 100)))
        prob_entry.pack(side="left")

        CTkLabel(scroll, text="💬 备注（可选，不影响匹配）", font=uf.f("normal")).pack(anchor="w", padx=8, pady=(6, 0))
        comment_entry = CTkEntry(scroll)
        comment_entry.insert(0, entry.get("comment", ""))
        comment_entry.pack(fill="x", padx=8, pady=(2, 6))

        result = {"ok": False, "entry": None}

        def do_ok():
            kws = [k.strip() for k in kws_entry.get().split(",") if k.strip()]
            content = content_box.get("1.0", "end").strip()
            if not kws or not content:
                messagebox.showwarning("提示", "关键词和内容都不能为空")
                return
            try:
                weight = int(weight_entry.get().strip())
                prob = int(prob_entry.get().strip())
            except ValueError:
                messagebox.showwarning("提示", "权重和概率必须是数字")
                return
            result["entry"] = self.normalize_entry({
                "keywords": kws, "content": content,
                "match": MATCH_OPTIONS[match_var.get()],
                "weight": max(0, min(100, weight)),
                "probability": max(0, min(100, prob)),
                "comment": comment_entry.get().strip(),
            })
            result["ok"] = True
            dlg.destroy()

        btn = CTkFrame(dlg)
        btn.pack(fill="x", pady=8)
        CTkButton(btn, text="✅ 确定", command=do_ok, width=100).pack(side="left", padx=14)
        CTkButton(btn, text="取消", command=dlg.destroy, width=80).pack(side="right", padx=14)

        self.window.wait_window(dlg)
        return result["entry"]
