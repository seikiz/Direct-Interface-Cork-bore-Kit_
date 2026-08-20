# plugin_manager.py
import os
import shutil
import sys
import importlib.util
import traceback
import json
from typing import Dict, List, Optional
from plugin_base import PluginBase
import app_paths


class PluginManager:
    def __init__(self, core, plugin_dir=None, config_file="config.json"):
        self.core = core
        # 插件目录列表：[0]=可写目录(用户安装新插件)，[1]=打包内置目录(只读)
        if plugin_dir:
            self.plugin_dirs = [plugin_dir]
        else:
            self.plugin_dirs = app_paths.get_plugin_dirs()
        self.plugin_dir = self.plugin_dirs[0]
        # 配置文件：相对路径时按应用数据根目录解析（exe 模式跟随 exe）
        if not os.path.isabs(config_file):
            config_file = os.path.join(app_paths.get_base_dir(), config_file)
        self.config_file = config_file
        self.plugins: Dict[str, PluginBase] = {}
        self.loaded_modules = []
        self.plugin_files: Dict[str, str] = {}  # 插件名 -> .py 文件路径（用于卸载）
        self._ensure_dir()

    def _ensure_dir(self):
        for d in self.plugin_dirs:
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass  # 打包内置目录可能不可写
        sys.path.insert(0, app_paths.get_base_dir())

    def _load_states(self) -> Dict[str, bool]:
        """从 config.json 加载插件状态"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    return cfg.get("plugin_states", {})
        except Exception as e:
            print(f"[PluginManager] 加载插件状态失败: {e}")
        return {}

    def _save_states(self):
        """保存插件状态到 config.json"""
        try:
            states = {name: p.enabled for name, p in self.plugins.items()}
            cfg = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg["plugin_states"] = states
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PluginManager] 保存插件状态失败: {e}")

    def load_plugins(self):
        self.unload_plugins()
        sys.path.insert(0, os.path.abspath("."))
        sys.path.insert(0, app_paths.get_base_dir())
        states = self._load_states()

        # 依次扫描所有插件目录：内置目录在前，用户目录在后（可覆盖内置同名插件）
        seen_modules = set()
        for d in self.plugin_dirs:
            if not os.path.isdir(d):
                continue
            for filename in sorted(os.listdir(d)):
                full_path = os.path.join(d, filename)
                if not os.path.isfile(full_path):
                    continue  # 跳过目录
                if not filename.endswith(".py") or filename.startswith("_"):
                    continue

                module_name = filename[:-3]
                if module_name in seen_modules:
                    continue
                seen_modules.add(module_name)
                try:
                    spec = importlib.util.spec_from_file_location(
                        module_name,
                        full_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.loaded_modules.append(module)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and
                            issubclass(attr, PluginBase) and
                            attr is not PluginBase):
                            plugin_instance = attr(self.core)
                            if plugin_instance.name in states:
                                plugin_instance.enabled = states[plugin_instance.name]
                            plugin_instance.on_load()
                            self.plugins[plugin_instance.name] = plugin_instance
                            self.plugin_files[plugin_instance.name] = full_path
                            # 使用纯 ASCII 状态标识，避免 GBK 编码错误
                            status = "Y" if plugin_instance.enabled else "N"
                            print(f"[Plugin] {status} {plugin_instance.name} v{plugin_instance.version}")
                except Exception as e:
                    print(f"[Plugin] Load failed {filename}: {e}")
                
    def unload_plugins(self):
        for plugin in self.plugins.values():
            try:
                plugin.on_unload()
            except:
                pass
        self.plugins.clear()
        for module in self.loaded_modules:
            if module.__name__ in sys.modules:
                del sys.modules[module.__name__]
        self.loaded_modules.clear()

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        return self.plugins.get(name)

    def get_all_plugins(self) -> List[PluginBase]:
        return list(self.plugins.values())

    def reload_plugins(self):
        self.unload_plugins()
        self.load_plugins()

    def toggle_plugin(self, name: str) -> bool:
        """切换插件启用状态，并保存到配置"""
        plugin = self.plugins.get(name)
        if not plugin:
            return False
        plugin.enabled = not plugin.enabled
        self._save_states()
        return plugin.enabled

    def handle_command(self, user_input: str):
        if not user_input.startswith("/"):
            return None
        parts = user_input[1:].strip().split(maxsplit=1)
        if not parts:
            return None
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            try:
                result = plugin.on_command(command, args)
                if result is not None:
                    if isinstance(result, str):
                        response, send_to_ai = result, False
                    else:
                        response, send_to_ai = result
                    if send_to_ai:
                        return response
                    else:
                        return f"[插件响应]\n{response}"
            except Exception as e:
                print(f"[插件] {plugin.name} 命令处理出错: {e}")
        return None

    # ---------- 插件安装 / 卸载 ----------
    def install_plugin(self, src_path: str):
        """安装插件：把 .py 文件复制到 plugins/ 目录。返回 (成功?, 消息)"""
        filename = os.path.basename(src_path)
        if not filename.endswith(".py"):
            return False, f"「{filename}」不是 .py 文件"
        dst = os.path.join(self.plugin_dir, filename)
        if os.path.exists(dst):
            return False, f"「{filename}」已安装（同名插件已存在）"
        try:
            shutil.copy2(src_path, dst)
            return True, f"已安装「{filename}」，点击「🔄 重载插件」生效"
        except Exception as e:
            return False, f"安装失败：{e}"

    def uninstall_plugin(self, name: str):
        """卸载插件：把文件改名为 .py.off（不再加载，保留原文件）。返回 (成功?, 消息)"""
        path = self.plugin_files.get(name)
        if not path or not os.path.exists(path):
            return False, f"找不到「{name}」的插件文件"
        try:
            off_path = path + ".off"
            if os.path.exists(off_path):
                os.remove(off_path)
            os.rename(path, off_path)
            return True, f"已卸载「{name}」（文件保留为 .off）"
        except Exception as e:
            return False, f"卸载失败：{e}"

    def installed_plugin_files(self):
        """列出所有插件目录中的 .py 文件（含尚未重载生效的）"""
        files = []
        for d in self.plugin_dirs:
            try:
                if os.path.isdir(d):
                    files += [f for f in os.listdir(d)
                              if f.endswith(".py") and not f.startswith("_")]
            except Exception:
                pass
        return sorted(set(files))