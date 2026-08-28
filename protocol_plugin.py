import json
import os
import subprocess

from plugin_base import PluginBase


class ProtocolPlugin(PluginBase):
    def __init__(self, core, name, command, args=None, base_dir=None):
        self.name = name or "协议插件"
        self.version = "?"
        self.description = "语言无关协议插件"
        self.author = "?"
        self._spawn_err = None
        self._p = None
        self._cmd = command
        self._args = list(args or [])
        if base_dir:
            self._args = [
                a if (os.path.isabs(a) or not os.path.exists(os.path.join(base_dir, a)))
                else os.path.join(base_dir, a)
                for a in self._args
            ]
        super().__init__(core)
        self._start()

    def _start(self):
        try:
            self._p = subprocess.Popen(
                [self._cmd] + self._args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            meta = self._call({"hook": "get_meta"})
            if meta and isinstance(meta.get("result"), dict):
                m = meta["result"]
                self.name = m.get("name") or self.name
                self.version = m.get("version") or self.version
                self.description = m.get("description") or self.description
                self.author = m.get("author") or self.author
            ui = self._call({"hook": "list_ui_buttons"})
            if ui and isinstance(ui.get("result"), list):
                self.ui_buttons = ui["result"]
            st = self._call({"hook": "get_settings"})
            if st and isinstance(st.get("result"), dict):
                self.settings = st["result"]
        except Exception as e:
            self._spawn_err = f"插件启动失败: {e}"

    def _call(self, req):
        try:
            self._p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            self._p.stdin.flush()
            resp = self._p.stdout.readline()
            if not resp:
                return None
            return json.loads(resp)
        except Exception:
            return None

    def on_load(self):
        self._call({"hook": "on_load"})

    def on_unload(self):
        try:
            self._call({"hook": "close"})
        finally:
            try:
                if self._p:
                    self._p.stdin.close()
                    self._p.stdout.close()
                    self._p.terminate()
            except Exception:
                pass

    def contextInjection(self):
        r = self._call({"hook": "context_injection"})
        if r and r.get("result"):
            return str(r["result"])
        return ""

    def on_message_send(self, user_input):
        r = self._call({"hook": "on_message_send", "user_input": user_input})
        res = r.get("result") if r else None
        if isinstance(res, dict):
            if res.get("block"):
                return None
            t = res.get("text")
            return t if t else user_input
        return user_input

    def on_message_received(self, user_input, ai_reply):
        try:
            self._call({"hook": "on_message_received", "user_input": user_input, "ai_reply": ai_reply})
        except Exception:
            pass

    def on_command(self, command, args):
        r = self._call({"hook": "on_command", "command": command, "args": args})
        res = r.get("result") if r else None
        if isinstance(res, dict):
            text = res.get("text")
            if text is not None:
                return (str(text), bool(res.get("send", False)))
        return None

    def get_setting(self, key, default=None):
        r = self._call({"hook": "get_setting", "key": key})
        if r and r.get("result") is not None:
            return r["result"]
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value
        self._call({"hook": "set_setting", "key": key, "value": value})
        self._save_settings()
