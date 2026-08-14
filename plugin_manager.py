# plugin_manager.py
import os
import sys
import importlib.util
import traceback
import json
from typing import Dict, List, Optional
from plugin_base import PluginBase


class PluginManager:
    def __init__(self, core, plugin_dir="plugins", config_file="config.json"):
        self.core = core
        self.plugin_dir = plugin_dir
        self.config_file = config_file
        self.plugins: Dict[str, PluginBase] = {}
        self.loaded_modules = []
        self._ensure_dir()

    def _ensure_dir(self):
        if not os.path.exists(self.plugin_dir):
            os.makedirs(self.plugin_dir)

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
        states = self._load_states()

        for filename in os.listdir(self.plugin_dir):
            full_path = os.path.join(self.plugin_dir, filename)
            if not os.path.isfile(full_path):
                continue  # 跳过目录
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = filename[:-3]
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
                    response, send_to_ai = result
                    if send_to_ai:
                        return response
                    else:
                        return f"[插件响应]\n{response}"
            except Exception as e:
                print(f"[插件] {plugin.name} 命令处理出错: {e}")
        return None