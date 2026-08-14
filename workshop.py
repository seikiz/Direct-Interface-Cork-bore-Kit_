# ============================================================
#   workshop.py - 创意工坊（联网版）
#   支持浏览、搜索、下载、点赞、上传、删除在线资源
#   服务器端见 net.py（python net.py 启动）
# ============================================================

import tkinter as tk
from tkinter import messagebox, filedialog
from customtkinter import *
import json
import os
import queue
import shutil
import sys
import subprocess
import threading
import requests
from datetime import datetime
from typing import Dict, Optional, List

import ui_fonts as uf

set_appearance_mode("dark")
set_default_color_theme("blue")

CONFIG_FILENAME = "workshop_config.json"
DEFAULT_SERVER_URL = "http://localhost:5000"


def get_base_dir():
    """应用根目录（兼容源码运行与打包运行）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class Workshop(CTkToplevel):
    def __init__(self, master=None, save_dir=None, world_dir=None, server_url=None):
        super().__init__(master)
        self.title("创意工坊 - 角色/世界管理")
        self.geometry("900x650")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        # 目录
        base = get_base_dir()
        if save_dir is None or world_dir is None:
            self.save_dir = os.path.join(base, "saves")
            self.world_dir = os.path.join(base, "worlds")
        else:
            self.save_dir = save_dir
            self.world_dir = world_dir

        for d in [self.save_dir, self.world_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

        # 连接配置（服务器地址 + 可选 API Key）
        self.config_file = os.path.join(base, CONFIG_FILENAME)
        cfg = self._load_workshop_config()
        self.server_url = (server_url or cfg.get("server_url") or DEFAULT_SERVER_URL).rstrip("/")
        self.api_key = cfg.get("api_key", "")
        self.server_online = False

        self.selected_file = None
        self.online_resources = []   # 服务器返回的全部资源
        self.online_display = []     # 当前列表中显示的资源（含筛选，与 Listbox 一一对应）
        self.tab_frames = {}

        # ---------- 主布局 ----------
        self.main_frame = CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ---------- 标签页 ----------
        self.tab_view = CTkTabview(self.main_frame)
        self.tab_view.pack(fill="both", expand=True)

        local_tab = self.tab_view.add("📁 本地管理")
        online_tab = self.tab_view.add("🌐 在线资源")

        self.tab_frames["本地管理"] = local_tab
        self.tab_frames["在线资源"] = online_tab

        # 构建本地管理标签（原有功能）
        self._build_local_tab(local_tab)

        # 构建在线资源标签
        self._build_online_tab(online_tab)

        # 底部按钮
        btn_frame = CTkFrame(self.main_frame)
        btn_frame.pack(fill="x", pady=10)

        CTkButton(btn_frame, text="📤 导出选中", command=self.export_selected).pack(side="left", padx=5)
        CTkButton(btn_frame, text="📥 导入文件", command=self.import_file).pack(side="left", padx=5)
        CTkButton(btn_frame, text="🔄 刷新", command=self.refresh_all).pack(side="left", padx=5)
        CTkButton(btn_frame, text="📤 上传到工坊", command=self.upload_selected).pack(side="left", padx=5)
        CTkButton(btn_frame, text="🗑️ 删除", fg_color="red", hover_color="#8b0000", command=self.delete_selected).pack(side="left", padx=5)
        CTkButton(btn_frame, text="📂 打开文件夹", command=self.open_folder).pack(side="left", padx=5)
        CTkButton(btn_frame, text="❌ 关闭", command=self.destroy).pack(side="right", padx=5)

        # 状态栏
        self.status_var = StringVar(value="就绪")
        status_bar = CTkLabel(self.main_frame, textvariable=self.status_var, font=uf.f("small"), text_color="gray")
        status_bar.pack(fill="x", pady=(5, 0))

        # 网络线程结果队列 + 主线程轮询（Tk 不允许在工作线程直接调用 after）
        self._result_queue = queue.Queue()
        self._pending_callbacks = []
        self.after(100, self._poll_results)

        self.refresh_all()

    # ==================== 连接配置 ====================
    def _load_workshop_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_workshop_config(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"server_url": self.server_url, "api_key": self.api_key},
                          f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("错误", f"保存连接配置失败：{e}")

    def _headers(self):
        """构造带可选 API Key 的请求头"""
        if self.api_key:
            return {"X-API-Key": self.api_key}
        return {}

    # ==================== 网络工具（线程化，不阻塞界面） ====================
    def _run_async(self, worker, on_success=None, on_error=None):
        """在后台线程执行 worker()，结果放入队列，
        由主线程的 _poll_results 轮询取出并回调（线程安全）。
        worker 返回的数据交给 on_success(data)；抛出的异常交给 on_error(exc)。
        """
        self._pending_callbacks.append((on_success, on_error))

        def target():
            try:
                result = ("ok", worker())
            except Exception as e:  # noqa: BLE001
                result = ("error", e)
            self._result_queue.put(result)

        threading.Thread(target=target, daemon=True).start()

    def _poll_results(self):
        """主线程定时轮询结果队列，执行对应回调（始终在 Tk 主线程运行）"""
        try:
            while True:
                kind, payload = self._result_queue.get_nowait()
                on_success, on_error = (self._pending_callbacks.pop(0)
                                        if self._pending_callbacks else (None, None))
                try:
                    if kind == "ok":
                        if on_success:
                            on_success(payload)
                    else:
                        if on_error:
                            on_error(payload)
                        else:
                            self.status_var.set(f"❌ 操作失败：{payload}")
                except Exception:
                    pass  # 单个回调出错不影响轮询
        except queue.Empty:
            pass
        try:
            self.after(100, self._poll_results)
        except Exception:
            pass  # 窗口已销毁时停止轮询

    # ---------- 本地管理标签 ----------
    def _build_local_tab(self, tab):
        """构建本地管理标签页（角色卡+世界卡分列）"""
        # 角色卡区域
        role_frame = CTkFrame(tab)
        role_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        CTkLabel(role_frame, text="📂 角色卡", font=uf.f("normal", bold=True)).pack(anchor="w")
        self.local_role_listbox = tk.Listbox(role_frame, bg="#2b2b2b", fg="white", selectbackground="#1f6aa5", font=uf.f("small"))
        self.local_role_listbox.pack(fill="both", expand=True, pady=5)
        self.local_role_listbox.bind("<<ListboxSelect>>", lambda e: self.on_local_select(e, self.save_dir, self.local_role_listbox))

        # 世界卡区域
        world_frame = CTkFrame(tab)
        world_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        CTkLabel(world_frame, text="🌍 世界卡", font=uf.f("normal", bold=True)).pack(anchor="w")
        self.local_world_listbox = tk.Listbox(world_frame, bg="#2b2b2b", fg="white", selectbackground="#1f6aa5", font=uf.f("small"))
        self.local_world_listbox.pack(fill="both", expand=True, pady=5)
        self.local_world_listbox.bind("<<ListboxSelect>>", lambda e: self.on_local_select(e, self.world_dir, self.local_world_listbox))

        # 预览区（底部）
        preview_frame = CTkFrame(tab, height=100)
        preview_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        CTkLabel(preview_frame, text="预览", font=uf.f("list", bold=True)).pack(anchor="w")
        self.local_preview = CTkTextbox(preview_frame, height=60, wrap="word", font=uf.f("small"))
        self.local_preview.pack(fill="both", expand=True)
        self.local_preview.configure(state="disabled")

        self.local_role_listbox.files = []
        self.local_world_listbox.files = []

    def on_local_select(self, event, dir_path, listbox):
        """本地列表选择事件"""
        selection = listbox.curselection()
        if not selection:
            return
        filename = listbox.get(selection[0])
        filepath = os.path.join(dir_path, filename)
        self.selected_file = filepath

        self.local_preview.configure(state="normal")
        self.local_preview.delete("1.0", "end")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            preview_text = self._format_preview(data)
            self.local_preview.insert("1.0", preview_text)
        except Exception as e:
            self.local_preview.insert("1.0", f"无法加载预览：{e}")
        self.local_preview.configure(state="disabled")
        self.status_var.set(f"选中: {filename}")

    def _format_preview(self, data):
        if isinstance(data, list):
            return f"旧格式对话列表，共 {len(data)} 条消息"
        if isinstance(data, dict):
            lines = []
            if 'name' in data:
                lines.append(f"名称: {data['name']}")
            if 'system_prompt' in data:
                lines.append(f"系统提示: {data['system_prompt'][:80]}...")
            if 'background' in data:
                lines.append(f"背景: {data['background'][:80]}...")
            if 'history_tree' in data:
                nodes = data['history_tree'].get('nodes', {})
                lines.append(f"对话节点数: {len(nodes)}")
            if 'rules' in data:
                lines.append(f"规则数: {len(data['rules'])}")
            if 'entries' in data:
                lines.append(f"关键词条目: {len(data['entries'])}")
            return "\n".join(lines) if lines else json.dumps(data, ensure_ascii=False, indent=2)[:200]
        return str(data)[:200]

    def refresh_local(self):
        """刷新本地列表"""
        self.local_role_listbox.delete(0, tk.END)
        self.local_world_listbox.delete(0, tk.END)
        try:
            files = [f for f in os.listdir(self.save_dir) if f.endswith('.json')]
            for f in sorted(files):
                self.local_role_listbox.insert(tk.END, f)
        except Exception:
            pass
        try:
            files = [f for f in os.listdir(self.world_dir) if f.endswith('.json')]
            for f in sorted(files):
                self.local_world_listbox.insert(tk.END, f)
        except Exception:
            pass

    # ---------- 在线资源标签 ----------
    def _build_online_tab(self, tab):
        """构建在线资源标签页"""
        # 连接设置栏
        conn_frame = CTkFrame(tab)
        conn_frame.pack(fill="x", padx=5, pady=5)
        CTkLabel(conn_frame, text="🔗 服务器:", font=uf.f("list")).pack(side="left", padx=5)
        self.server_entry = CTkEntry(conn_frame, width=240, placeholder_text="http://localhost:5000")
        self.server_entry.insert(0, self.server_url)
        self.server_entry.pack(side="left", padx=5)
        CTkLabel(conn_frame, text="🔑 Key(可选):", font=uf.f("list")).pack(side="left", padx=(10, 5))
        self.key_entry = CTkEntry(conn_frame, width=140, placeholder_text="服务器 API Key", show="*")
        if self.api_key:
            self.key_entry.insert(0, self.api_key)
        self.key_entry.pack(side="left", padx=5)
        CTkButton(conn_frame, text="💾 保存", command=self.save_connection, width=70).pack(side="left", padx=5)
        CTkButton(conn_frame, text="🔌 测试连接", command=self.test_connection, width=90).pack(side="left", padx=5)
        self.conn_status_var = StringVar(value="● 未连接")
        CTkLabel(conn_frame, textvariable=self.conn_status_var, font=uf.f("small"),
                 text_color="gray").pack(side="left", padx=10)

        # 搜索栏
        search_frame = CTkFrame(tab)
        search_frame.pack(fill="x", padx=5, pady=5)
        CTkLabel(search_frame, text="🔍 搜索:", font=uf.f("normal")).pack(side="left", padx=5)
        self.search_entry = CTkEntry(search_frame, width=250, placeholder_text="输入关键词搜索...")
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<Return>", lambda e: self.search_online())
        CTkButton(search_frame, text="搜索", command=self.search_online, width=80).pack(side="left", padx=5)

        # 类型筛选
        self.filter_var = StringVar(value="全部")
        CTkOptionMenu(search_frame, values=["全部", "角色卡", "世界卡"], variable=self.filter_var,
                      width=100, command=lambda _: self._apply_filter()).pack(side="left", padx=10)

        CTkButton(search_frame, text="🔄 刷新列表", command=self.refresh_online, width=100).pack(side="right", padx=5)

        # 资源列表（带滚动）
        list_frame = CTkFrame(tab)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.online_tree = tk.Listbox(list_frame, bg="#2b2b2b", fg="white", selectbackground="#1f6aa5", font=uf.f("small"))
        self.online_tree.pack(fill="both", expand=True, side="left")
        self.online_tree.bind("<<ListboxSelect>>", self.on_online_select)
        self.online_tree.bind("<Double-Button-1>", lambda e: self.download_selected())

        # 右侧详情/下载
        detail_frame = CTkFrame(tab, width=300)
        detail_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        CTkLabel(detail_frame, text="资源详情", font=uf.f("normal", bold=True)).pack(anchor="w")
        self.online_detail = CTkTextbox(detail_frame, wrap="word", font=uf.f("small"))
        self.online_detail.pack(fill="both", expand=True, pady=5)
        self.online_detail.configure(state="disabled")

        btn_frame = CTkFrame(detail_frame)
        btn_frame.pack(fill="x", pady=5)
        CTkButton(btn_frame, text="⬇️ 下载到本地", command=self.download_selected, width=110).pack(side="left", padx=5)
        CTkButton(btn_frame, text="❤️ 点赞", command=self.like_selected, width=70).pack(side="left", padx=5)
        CTkButton(btn_frame, text="🗑️ 删除", fg_color="#8b0000", hover_color="#5e0000",
                  command=self.delete_online_selected, width=70).pack(side="left", padx=5)

        self.online_resources = []
        self.online_display = []

    # ---------- 在线资源：网络操作 ----------
    def _merge_with_type(self, cards, worlds):
        resources = []
        for c in cards or []:
            c = dict(c)
            c['type'] = '角色卡'
            resources.append(c)
        for w in worlds or []:
            w = dict(w)
            w['type'] = '世界卡'
            resources.append(w)
        return resources

    def refresh_online(self):
        """从服务器获取资源列表（后台线程）"""
        self.status_var.set("正在获取在线资源...")
        self.conn_status_var.set("● 连接中...")

        def worker():
            health = requests.get(f"{self.server_url}/api/health", timeout=5,
                                  headers=self._headers())
            health.raise_for_status()
            cards_resp = requests.get(f"{self.server_url}/api/cards/list", timeout=5,
                                      headers=self._headers())
            worlds_resp = requests.get(f"{self.server_url}/api/worlds/list", timeout=5,
                                       headers=self._headers())
            cards = cards_resp.json() if cards_resp.status_code == 200 else []
            worlds = worlds_resp.json() if worlds_resp.status_code == 200 else []
            return self._merge_with_type(cards, worlds)

        def on_success(resources):
            self.server_online = True
            self.online_resources = resources
            self._apply_filter()
            self.conn_status_var.set(f"● 已连接 ({len(resources)} 个资源)")
            self.status_var.set(f"获取到 {len(resources)} 个在线资源")

        def on_error(exc):
            self.server_online = False
            self.online_resources = []
            self.online_display = []
            self.online_tree.delete(0, tk.END)
            self.online_tree.insert(tk.END, f"⚠️ 无法连接服务器 {self.server_url}")
            self.online_tree.insert(tk.END, "   请先运行: python net.py  (或检查上方服务器地址)")
            self.conn_status_var.set("● 离线")
            self.status_var.set("⚠️ 无法连接服务器，请确认 net.py 已启动")

        self._run_async(worker, on_success, on_error)

    def search_online(self):
        """搜索在线资源（统一搜索接口，覆盖角色卡+世界卡）"""
        query = self.search_entry.get().strip()
        if not query:
            self.refresh_online()
            return
        self.status_var.set(f"搜索: {query}...")
        # 注意：filter_var 是 Tk 变量，必须在主线程读取，不能在工作线程调用
        filter_type = self.filter_var.get()

        def worker():
            params = {"q": query}
            if filter_type == "角色卡":
                params["type"] = "cards"
            elif filter_type == "世界卡":
                params["type"] = "worlds"
            resp = requests.get(f"{self.server_url}/api/search", params=params,
                                timeout=8, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

        def on_success(results):
            self.online_resources = results
            self._apply_filter()
            self.status_var.set(f"找到 {len(results)} 个结果")

        def on_error(exc):
            self.status_var.set(f"❌ 搜索失败：{exc}")
            messagebox.showerror("错误", f"搜索失败：{exc}")

        self._run_async(worker, on_success, on_error)

    def _apply_filter(self):
        """按当前筛选条件重建显示列表（保证显示项与数据一一对应）"""
        self.online_tree.delete(0, tk.END)
        filter_type = self.filter_var.get()
        self.online_display = []
        for r in self.online_resources:
            rtype = r.get('type', '未知')
            if filter_type != "全部" and rtype != filter_type:
                continue
            self.online_display.append(r)
            name = r.get('name', '未知')
            author = r.get('author', '匿名')
            downloads = r.get('downloads', 0)
            likes = r.get('likes', 0)
            tags = ','.join(r.get('tags', [])[:3])
            display = f"{name[:20]} | {author[:10]} | ↓{downloads} ❤{likes} | {tags[:15]} | {rtype}"
            self.online_tree.insert(tk.END, display)
        if not self.online_display and self.server_online:
            self.online_tree.insert(tk.END, "（暂无符合条件的资源）")

    def _selected_resource(self):
        """返回当前选中的在线资源（按显示列表索引）"""
        selection = self.online_tree.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选中一个在线资源")
            return None
        idx = selection[0]
        if idx >= len(self.online_display):
            return None
        return self.online_display[idx]

    def on_online_select(self, event):
        """在线资源选择事件"""
        selection = self.online_tree.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.online_display):
            return
        resource = self.online_display[idx]
        self.online_detail.configure(state="normal")
        self.online_detail.delete("1.0", "end")
        detail = f"""名称: {resource.get('name', '未知')}
作者: {resource.get('author', '匿名')}
类型: {resource.get('type', '未知')}
标签: {', '.join(resource.get('tags', []))}
下载次数: {resource.get('downloads', 0)}
点赞数: {resource.get('likes', 0)}
上传时间: {resource.get('created_at', '未知')}
描述: {resource.get('description', '无')}
系统提示预览: {resource.get('system_prompt_preview', '无')[:200]}..."""
        self.online_detail.insert("1.0", detail)
        self.online_detail.configure(state="disabled")
        self.status_var.set(f"查看: {resource.get('name')}")

    def download_selected(self):
        """下载选中的在线资源（后台线程）"""
        resource = self._selected_resource()
        if not resource:
            return
        res_id = resource.get('id')
        res_type = resource.get('type', '角色卡')
        filename = resource.get('original_name', f"{resource.get('name', 'unknown')}.json")
        # 目标目录
        target_dir = self.save_dir if res_type == '角色卡' else self.world_dir

        self.status_var.set(f"正在下载: {resource.get('name')}...")

        def worker():
            url = f"{self.server_url}/api/cards/{res_id}" if res_type == '角色卡' else f"{self.server_url}/api/worlds/{res_id}"
            resp = requests.get(url, timeout=30, headers=self._headers())
            resp.raise_for_status()
            # 保存文件（重名自动加序号）
            dst = os.path.join(target_dir, filename)
            if os.path.exists(dst):
                base_name, ext = os.path.splitext(dst)
                i = 1
                while os.path.exists(f"{base_name}_{i}{ext}"):
                    i += 1
                dst = f"{base_name}_{i}{ext}"
            with open(dst, 'wb') as f:
                f.write(resp.content)
            return dst

        def on_success(dst):
            self.status_var.set(f"✅ 下载完成: {os.path.basename(dst)}")
            messagebox.showinfo("下载完成", f"文件已保存到:\n{dst}")
            self.refresh_local()
            self.refresh_online()

        def on_error(exc):
            self.status_var.set(f"❌ 下载失败：{exc}")
            messagebox.showerror("错误", f"下载失败：{exc}")

        self._run_async(worker, on_success, on_error)

    def like_selected(self):
        """点赞选中的在线资源（按类型选择接口）"""
        resource = self._selected_resource()
        if not resource:
            return
        res_id = resource.get('id')
        res_type = resource.get('type', '角色卡')

        def worker():
            url = (f"{self.server_url}/api/cards/{res_id}/like" if res_type == '角色卡'
                   else f"{self.server_url}/api/worlds/{res_id}/like")
            resp = requests.post(url, timeout=8, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

        def on_success(data):
            self.status_var.set(f"❤️ 点赞成功！当前 {data.get('likes', 0)} 个赞")
            self.refresh_online()

        def on_error(exc):
            self.status_var.set(f"❌ 点赞失败：{exc}")
            messagebox.showerror("错误", f"点赞失败：{exc}")

        self._run_async(worker, on_success, on_error)

    def delete_online_selected(self):
        """删除选中的在线资源（需要服务器开放模式或正确 API Key）"""
        resource = self._selected_resource()
        if not resource:
            return
        if not messagebox.askyesno("确认删除",
                                   f"确定要从创意工坊删除资源:\n「{resource.get('name')}」 吗？\n此操作不可恢复。"):
            return
        res_id = resource.get('id')
        res_type = resource.get('type', '角色卡')

        def worker():
            url = (f"{self.server_url}/api/cards/{res_id}" if res_type == '角色卡'
                   else f"{self.server_url}/api/worlds/{res_id}")
            resp = requests.delete(url, timeout=8, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

        def on_success(data):
            self.status_var.set(f"🗑️ {data.get('message', '已删除')}")
            self.online_detail.configure(state="normal")
            self.online_detail.delete("1.0", "end")
            self.online_detail.configure(state="disabled")
            self.refresh_online()

        def on_error(exc):
            self.status_var.set(f"❌ 删除失败：{exc}")
            messagebox.showerror("错误", f"删除失败：{exc}\n(若服务器开启了 API Key，请在上方填写)")

        self._run_async(worker, on_success, on_error)

    def upload_selected(self):
        """上传本地选中的文件到工坊"""
        if not self.selected_file:
            messagebox.showwarning("警告", "请先在本地选择一个文件")
            return
        # 判断类型
        res_type = "角色卡" if os.path.normpath(self.save_dir) in os.path.normpath(self.selected_file) else "世界卡"

        # 弹出信息输入框
        dialog = CTkToplevel(self)
        dialog.title("上传到创意工坊")
        dialog.geometry("400x350")
        dialog.transient(self)
        dialog.grab_set()

        CTkLabel(dialog, text="作者名称:", font=uf.f("normal")).pack(pady=(10, 0), anchor="w", padx=20)
        author_entry = CTkEntry(dialog, width=300)
        author_entry.pack(pady=5, padx=20)

        CTkLabel(dialog, text="标签（逗号分隔）:", font=uf.f("normal")).pack(pady=(10, 0), anchor="w", padx=20)
        tags_entry = CTkEntry(dialog, width=300)
        tags_entry.pack(pady=5, padx=20)

        CTkLabel(dialog, text="描述:", font=uf.f("normal")).pack(pady=(10, 0), anchor="w", padx=20)
        desc_entry = CTkEntry(dialog, width=300)
        desc_entry.pack(pady=5, padx=20)

        def do_upload():
            author = author_entry.get().strip() or "anonymous"
            tags = tags_entry.get().strip() or ""
            desc = desc_entry.get().strip() or ""
            selected = self.selected_file

            self.status_var.set(f"正在上传: {os.path.basename(selected)}...")

            def worker():
                with open(selected, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                files = {'file': (os.path.basename(selected),
                                 json.dumps(content, ensure_ascii=False),
                                 'application/json')}
                data = {'author': author, 'tags': tags, 'description': desc}
                url = (f"{self.server_url}/api/cards/upload" if res_type == "角色卡"
                       else f"{self.server_url}/api/worlds/upload")
                resp = requests.post(url, files=files, data=data, timeout=30,
                                     headers=self._headers())
                resp.raise_for_status()
                return resp.json()

            def on_success(data):
                self.status_var.set("✅ 上传成功！")
                messagebox.showinfo("上传成功", data.get("message", "已上传到创意工坊"))
                dialog.destroy()
                self.refresh_online()

            def on_error(exc):
                self.status_var.set(f"❌ 上传失败：{exc}")
                messagebox.showerror("错误", f"上传失败：{exc}\n(若服务器开启了 API Key，请先在上方保存 Key)")

            self._run_async(worker, on_success, on_error)

        CTkButton(dialog, text="上传", command=do_upload, width=150).pack(pady=20)

    # ---------- 连接设置操作 ----------
    def save_connection(self):
        """保存服务器地址与 API Key 配置"""
        url = self.server_entry.get().strip().rstrip("/")
        if not url:
            messagebox.showwarning("警告", "服务器地址不能为空")
            return
        self.server_url = url
        self.api_key = self.key_entry.get().strip()
        self._save_workshop_config()
        self.status_var.set(f"已保存连接设置: {self.server_url}")
        self.refresh_online()

    def test_connection(self):
        """测试服务器连通性并显示统计信息"""
        url = self.server_entry.get().strip().rstrip("/")
        if not url:
            messagebox.showwarning("警告", "服务器地址不能为空")
            return
        self.server_url = url
        self.api_key = self.key_entry.get().strip()
        self.status_var.set("正在测试连接...")

        def worker():
            health = requests.get(f"{self.server_url}/api/health", timeout=5,
                                  headers=self._headers())
            health.raise_for_status()
            stats = requests.get(f"{self.server_url}/api/stats", timeout=5,
                                 headers=self._headers())
            stats.raise_for_status()
            return health.json(), stats.json()

        def on_success(data):
            health, stats = data
            self.server_online = True
            self.conn_status_var.set("● 已连接")
            self.status_var.set(
                f"✅ 服务器在线 | 角色卡 {stats.get('cards', 0)} · 世界卡 {stats.get('worlds', 0)}"
                f" · 下载 {stats.get('downloads', 0)} · 点赞 {stats.get('likes', 0)}"
            )
            messagebox.showinfo("连接成功",
                                f"已连接到创意工坊服务器\n认证模式: {health.get('auth', 'open')}\n"
                                f"角色卡: {stats.get('cards', 0)} 张\n世界卡: {stats.get('worlds', 0)} 张")

        def on_error(exc):
            self.server_online = False
            self.conn_status_var.set("● 离线")
            self.status_var.set(f"❌ 连接失败：{exc}")
            messagebox.showerror("连接失败", f"无法连接到服务器:\n{self.server_url}\n\n请确认 net.py 已启动。\n({exc})")

        self._run_async(worker, on_success, on_error)

    # ---------- 通用操作 ----------
    def refresh_all(self):
        self.refresh_local()
        self.refresh_online()

    def export_selected(self):
        if not self.selected_file:
            messagebox.showwarning("警告", "请先选中一个文件")
            return
        target_dir = filedialog.askdirectory(title="选择导出目标文件夹")
        if not target_dir:
            return
        try:
            filename = os.path.basename(self.selected_file)
            dst = os.path.join(target_dir, filename)
            shutil.copy2(self.selected_file, dst)
            self.status_var.set(f"已导出到: {dst}")
            messagebox.showinfo("成功", f"文件已导出到:\n{dst}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败：{e}")

    def import_file(self):
        file_paths = filedialog.askopenfilenames(
            title="选择要导入的角色卡/世界卡",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not file_paths:
            return
        # 简单判断：如果文件包含 'world' 关键词或世界卡结构，导入到 world_dir
        target_dir = self.save_dir
        imported = 0
        for src in file_paths:
            try:
                with open(src, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 判断类型：包含 'rules' 或 'entries' 视为世界卡
                if isinstance(data, dict) and ('rules' in data or 'entries' in data):
                    target_dir = self.world_dir
                else:
                    target_dir = self.save_dir
                dst = os.path.join(target_dir, os.path.basename(src))
                if os.path.exists(dst):
                    base_name, ext = os.path.splitext(dst)
                    i = 1
                    while os.path.exists(f"{base_name}_{i}{ext}"):
                        i += 1
                    dst = f"{base_name}_{i}{ext}"
                shutil.copy2(src, dst)
                imported += 1
            except Exception as e:
                messagebox.showerror("错误", f"导入 {src} 失败：{e}")
        self.refresh_local()
        self.status_var.set(f"成功导入 {imported} 个文件")
        messagebox.showinfo("完成", f"已导入 {imported} 个文件")

    def delete_selected(self):
        if not self.selected_file:
            messagebox.showwarning("警告", "请先选中一个文件")
            return
        if not messagebox.askyesno("确认删除", f"确定要删除文件:\n{os.path.basename(self.selected_file)} 吗？"):
            return
        try:
            os.remove(self.selected_file)
            self.selected_file = None
            self.refresh_local()
            self.status_var.set("文件已删除")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败：{e}")

    def open_folder(self):
        # 简单打开 save_dir
        if os.path.exists(self.save_dir):
            try:
                os.startfile(self.save_dir)
            except AttributeError:
                try:
                    subprocess.Popen(['open', self.save_dir])
                except Exception:
                    subprocess.Popen(['xdg-open', self.save_dir])
        else:
            messagebox.showerror("错误", "文件夹不存在")


if __name__ == "__main__":
    root = CTk()
    root.withdraw()
    app = Workshop(root)
    app.mainloop()
