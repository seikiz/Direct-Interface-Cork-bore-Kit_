# DICK 插件开发标准（Plugin 编写规范）

> DICK 的插件是 **Python 后端插件**（`plugins/*.py`）——与酒馆（SillyTavern）的前端 JS extension 不同：
> 酒馆插件操作界面，DICK 插件挂接**引擎能力**（模型通道 / 文件系统 / 网络 / 机制卡 / 战斗 / CODEX）。
> 本文档是编写插件必须遵守的标准。

---

## 一、快速上手（最小插件）

把任意 `.py` 文件放进 DICK 目录下的 `plugins/` 文件夹，重启即加载。文件不能以 `_` 开头。

```python
# plugins/hello_plugin.py
from plugin_base import PluginBase

class HelloPlugin(PluginBase):
    name = "打招呼"          # 唯一插件名（显示名）
    version = "1.0"
    description = "示例插件：注册一个 /hello 命令"
    author = "你的名字"

    def on_command(self, command, args):
        if command == "hello":
            return "👋 你好！这是 DICK 插件。", False
        return None
```

重启后输入 `/hello` 即可看到回复。

---

## 二、插件文件规范

| 项目 | 标准 |
|---|---|
| 位置 | `plugins/*.py`（exe 旁；多个插件目录时用户目录可覆盖内置同名） |
| 命名 | 小写下划线，如 `hello_plugin.py`；**不得以 `_` 开头**（被忽略） |
| 类 | 继承 `PluginBase`，每个文件可定义多个插件类 |
| 编码 | UTF-8（文件头加 `# -*- coding: utf-8 -*-`） |
| 导入 | 使用 `from plugin_base import PluginBase`；可 `import` 标准库与已打包依赖 |

---

## 三、类属性（必填/选填）

```python
class MyPlugin(PluginBase):
    name = "插件名"          # 必填：全局唯一
    version = "1.0"          # 建议
    description = "一句话说明" # 建议
    author = "作者"          # 建议
    enabled = True           # 默认启用（用户可在设置里切换）
```

---

## 四、生命周期钩子（按需实现）

```python
def on_load(self):
    """插件加载后调用：打印横幅、初始化资源"""
    pass

def on_unload(self):
    """插件卸载时调用：释放资源、清理临时文件"""
    pass
```

---

## 五、消息钩子

```python
def on_message_send(self, user_input):
    """用户发送消息前调用。
    返回修改后的文本（如注入前缀）；返回 None 或空串可阻止发送。"""
    return user_input

def on_message_received(self, user_input, ai_reply):
    """AI 回复后调用（可读取/分析回复，不能改回复内容）。"""
    pass
```

---

## 六、命令钩子（核心）

```python
def on_command(self, command, args):
    """处理自定义命令，如 /hello。
    返回约定：
      (response_text, should_send_to_ai)
        response_text      给用户看到的文本（也会进聊天记录）
        should_send_to_ai  True=把用户原文发给 AI；False=不发给 AI（纯工具回复）
    或 None（不处理该命令）。
    也可返回纯字符串（等价 (str, False)）。"""
    if command == "hello":
        return "👋 你好！", False
    if command == "askai":
        return "这句话会发给 AI", True
    return None
```

**命令约定**：
- 命令名不带头 `/`（`on_command` 收到的 `command` 已是去斜杠的）
- 大小写不敏感（管理器统一转小写）
- 参数在 `args`（字符串，已 strip）

---

## 七、声明式设置（settings_schema）

插件可声明设置项，管理器自动生成设置界面，**无需写任何 UI 代码**：

```python
settings_schema = [
    {"key": "count", "label": "数量", "type": "int",
     "default": 3, "min": 1, "max": 10},
    {"key": "auto", "label": "自动开启", "type": "bool", "default": True},
    {"key": "greeting", "label": "问候语", "type": "text", "default": "你好"},
    {"key": "api_key", "label": "密钥", "type": "secret", "default": ""},
    {"key": "mode", "label": "模式", "type": "choice", "default": "a",
     "options": [{"value": "a", "label": "模式A"}, {"value": "b", "label": "模式B"}]},
    {"key": "file", "label": "文件", "type": "file", "default": ""},
]
```

**读写设置**（自动持久化到 `plugin_settings/<插件名>.json`）：
```python
def on_command(self, command, args):
    if command == "count":
        n = self.get_setting("count", 3)   # 读（带默认值）
        self.set_setting("count", n + 1)   # 写（自动保存）
        return f"当前 {n}", False
```

`type` 支持：`text` / `secret`（密码框）/ `int` / `bool` / `choice` / `file`。

---

## 八、声明式 UI 按钮（ui_buttons）

插件可在主界面「🧩 插件坞」注册按钮：

```python
ui_buttons = [
    {"type": "method", "label": "🖼️ 图片", "method": "show_window"},  # 点击调插件方法
    {"type": "insert", "label": "🎲 d20", "text": "/r 1d20"},          # 点击插入命令到输入框
]
```

只有启用的插件才显示按钮。

---

## 九、访问核心（core）

插件构造时收到 `core`（ChatCore 实例），可访问：

| 成员 | 用途 |
|---|---|
| `self.core.client` | OpenAI 兼容客户端（发请求用，如 `client.chat.completions.create(...)`） |
| `self.core.model` | 当前模型名 |
| `self.core.tree` | 树状记忆（节点/历史） |
| `self.core.mechanism_state` | 机制状态（好感/状态/战斗） |
| `self.core._mech_config` | 机制卡配置 |
| `self.core.is_processing` | 是否正在生成 |

示例（读取当前好感度）：
```python
def on_command(self, command, args):
    if command == "好感":
        st = getattr(self.core, "mechanism_state", None) or {}
        aff = st.get("affection")
        return f"❤️ 当前好感：{aff}", False
```

---

## 十、插件边界

插件钩子已覆盖：加载/卸载、消息发送前/后、命令。这些钩子就是"插件标准"的边界——
**不要在插件里直接改前端 HTML**（那是酒馆 extension 的活）；DICK 插件只做后端能力。

---

## 十一、调试与发布

```python
print("[我的插件] 加载完成")   # 输出到 debug.log（exe 模式）或控制台
```

- 错误会打印 `[Plugin] Load failed <文件名>: <错误>`，改完重开 DICK 生效
- 分享插件：把 `.py` 文件发给别人，丢进对方 `plugins/` 即可（无商店、无审核）

---

## 十二、标准速查表

| 你想做什么 | 用哪个 |
|---|---|
| 自定义命令 | `on_command` + `name` |
| 用户发言前改文本 | `on_message_send` |
| AI 回复后做处理 | `on_message_received` |
| 可配置项 | `settings_schema` + `get_setting/set_setting` |
| 界面按钮 | `ui_buttons`（method/insert） |
| 初始化/清理 | `on_load` / `on_unload` |
| 访问模型/记忆/机制 | `self.core.*` |
| 插件间通信 | 通过 `core`（共享状态） |

---

*DICK 插件标准 v1.0 —— 后辈向酒馆老前辈致意：它管前端，我管引擎。*
