# plugins/image_upload_plugin.py - 图片导入插件 v1.1
# 功能：选择本地图片 → 预览/压缩 → 生成文字描述（Hugging Face BLIP）→ 发送消息时自动附加
from plugin_base import PluginBase
import tkinter as tk
from tkinter import filedialog
from customtkinter import *
import base64
import requests
import json
from PIL import Image, ImageTk
import io
import os

import ui_fonts as uf

# 独立配置文件（放在项目根目录，避免与主程序 config.json 互相覆盖）
def _get_config_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "image_plugin_config.json")


class ImageUploadPlugin(PluginBase):
    name = "ImageUpload"
    version = "1.1"
    description = "导入本地图片，自动生成描述并附加到消息"
    author = "seiki"
    enabled = True

    def __init__(self, core):
        super().__init__(core)
        self.image_data = None     # 压缩后的 base64
        self.image_name = ""       # 文件名
        self.api_token = self._load_token()
        self.window = None

    # ---------- Token 持久化 ----------
    def _load_token(self):
        try:
            with open(_get_config_path(), "r", encoding="utf-8") as f:
                return json.load(f).get("hf_token", "") or ""
        except Exception:
            return ""

    def _save_token(self):
        try:
            with open(_get_config_path(), "w", encoding="utf-8") as f:
                json.dump({"hf_token": self.api_token}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ImageUpload] Token 保存失败: {e}")

    # ---------- 窗口 ----------
    def on_load(self):
        self.window = CTkToplevel()
        self.window.title("🖼️ 导入图片")
        self.window.geometry("460x520")
        self.window.protocol("WM_DELETE_WINDOW", self.hide_window)

        CTkLabel(self.window, text="🖼️ 导入图片", font=uf.f("header", bold=True)).pack(pady=(12, 4))
        CTkLabel(self.window, text="选择一张图片，发送消息时自动附加 AI 生成的图片描述",
                 font=uf.f("small"), text_color="gray").pack(pady=(0, 8))

        self.btn_select = CTkButton(self.window, text="📂 选择图片", command=self.select_image)
        self.btn_select.pack(pady=5)
        self.btn_clear = CTkButton(self.window, text="🗑️ 清除图片", command=self.clear_image, fg_color="gray")
        self.btn_clear.pack(pady=5)

        self.preview_label = CTkLabel(self.window, text="未选择图片", font=uf.f("small"))
        self.preview_label.pack(pady=10)

        self.status_label = CTkLabel(self.window, text="就绪", font=uf.f("small"), text_color="gray")
        self.status_label.pack(pady=5)

        # Token 设置
        token_frame = CTkFrame(self.window)
        token_frame.pack(fill="x", padx=15, pady=(12, 0))
        CTkLabel(token_frame, text="🔑 HuggingFace Token（可选）:", font=uf.f("small")).pack(anchor="w", padx=8, pady=(8, 2))
        self.token_entry = CTkEntry(token_frame, show="*", placeholder_text="hf_xxx...")
        self.token_entry.pack(fill="x", padx=8, pady=(0, 4))
        if self.api_token:
            self.token_entry.insert(0, self.api_token)
        self.token_btn = CTkButton(token_frame, text="💾 保存 Token", command=self.save_token, width=120)
        self.token_btn.pack(anchor="w", padx=8, pady=(0, 8))
        CTkLabel(token_frame, text="没有 Token 也能选图，但消息中不会附加图片描述。",
                 font=uf.f("small"), text_color="gray", wraplength=380, justify="left").pack(anchor="w", padx=8, pady=(0, 8))

        self.window.withdraw()  # 默认隐藏，通过主界面「🖼️ 图片」按钮打开
        print("[ImageUpload] 已加载（在主界面点击 🖼️ 图片 打开）")

    def hide_window(self):
        self.window.withdraw()

    def show_window(self):
        if self.window:
            self.window.deiconify()
            self.window.lift()

    def save_token(self):
        token = self.token_entry.get().strip()
        self.api_token = token
        self._save_token()
        if token:
            self.status_label.configure(text="✅ Token 已保存", text_color="green")
        else:
            self.status_label.configure(text="已清除 Token", text_color="gray")

    # ---------- 图片处理 ----------
    def select_image(self):
        file_path = filedialog.askopenfilename(
            title="选择要导入的图片",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        self._load_image(file_path)

    def _load_image(self, file_path):
        """读取并压缩图片为 base64（最长边 1024，JPEG 转码降低体积）"""
        with open(file_path, "rb") as f:
            img_bytes = f.read()

        # 预览（无窗口环境时跳过，不影响加载）
        try:
            img = Image.open(io.BytesIO(img_bytes))
            img.thumbnail((240, 240))
            photo = ImageTk.PhotoImage(img)
            self.preview_label.configure(image=photo, text="")
            self.preview_label.image = photo
        except Exception:
            pass

        # 压缩转码
        img_full = Image.open(io.BytesIO(img_bytes))
        if img_full.mode in ("RGBA", "P", "LA"):
            img_full = img_full.convert("RGB")
        img_full.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img_full.save(buf, format="JPEG", quality=85)
        compressed = buf.getvalue()

        self.image_data = base64.b64encode(compressed).decode("utf-8")
        self.image_name = os.path.basename(file_path)
        size_kb = len(compressed) / 1024
        self.status_label.configure(
            text=f"✅ 已导入: {self.image_name}（压缩后 {size_kb:.0f} KB）", text_color="green")

    def clear_image(self):
        self.image_data = None
        self.image_name = ""
        self.preview_label.configure(image=None, text="未选择图片")
        self.status_label.configure(text="已清除", text_color="gray")

    # ---------- 描述生成 ----------
    def generate_description(self, image_base64):
        """调用 Hugging Face BLIP 模型生成图像描述"""
        if not self.api_token:
            return "⚠️ 未设置 HuggingFace Token，跳过图片描述"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        payload = {"inputs": image_base64, "parameters": {"max_length": 50}}
        try:
            resp = requests.post(
                "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base",
                headers=headers,
                json=payload,
                timeout=20
            )
            if resp.status_code == 200:
                result = resp.json()
                if result and isinstance(result, list):
                    return result[0].get("generated_text", "无法生成描述")
                return "无法生成描述"
            return f"API 错误: {resp.status_code}"
        except Exception as e:
            return f"请求失败: {e}"

    # ---------- 消息钩子 ----------
    def on_message_send(self, user_input):
        if not self.image_data:
            return user_input
        desc = self.generate_description(self.image_data)
        if desc and not desc.startswith("⚠️") and not desc.startswith("API") and not desc.startswith("请求"):
            modified = f"{user_input}\n[图片: {self.image_name}]\n[图片描述: {desc}]"
            print(f"[ImageUpload] 📝 已附加描述: {desc[:60]}...")
            return modified
        else:
            print(f"[ImageUpload] ⚠️ {desc}")
            # 没有可用描述时至少附上文件名，方便对方知道发过图
            return f"{user_input}\n[图片: {self.image_name}]"
