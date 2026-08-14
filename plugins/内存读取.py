# plugins/memory_probe.py
# 稳定版：使用 ctypes.string_at，无需管理员权限，永不报错码6

import ctypes
from plugin_base import PluginBase

class MemoryProbePlugin(PluginBase):
    name = "内存探针"
    version = "0.5"
    description = "使用 ctypes.string_at 读取本进程内存"
    author = "你"
    enabled = True

    def on_command(self, command, args):
        if command == "mem_help":
            return self._help(), False

        elif command == "mem_self":
            parts = args.split()
            if len(parts) < 2:
                return "用法：/mem_self <地址> <字节数>", False
            try:
                address = int(parts[0], 0)
                size = int(parts[1])
                data = self._read_own_memory(address, size)
                if data is None:
                    return "❌ 读取失败，地址可能无效", False
                hex_dump = " ".join(f"{b:02x}" for b in data)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else '.' for b in data[:32])
                return (
                    f"📍 地址 0x{address:x} 读取 {size} 字节：\n"
                    f"HEX: {hex_dump}\n"
                    f"ASCII: {ascii_part}"
                ), False
            except ValueError:
                return "❌ 地址格式错误，请使用十进制或 0x 开头", False
            except OSError as e:
                return f"❌ 系统错误：{e}", False

        return None

    def _read_own_memory(self, address, size):
        try:
            return ctypes.string_at(address, size)
        except (ValueError, OSError, TypeError):
            return None

    def _help(self):
        return (
            "🧪 内存探针 v0.5（使用 string_at）\n"
            "/mem_self <地址> <字节数>  – 读取本进程内存\n"
            "/mem_help                   – 本帮助\n"
            "示例：/mem_self 140735268915712 16"
        )