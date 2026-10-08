# DICK 插件开发标准（Plugin 编写规范）

> DICK 的插件是 **Python 后端插件**（`plugins/*.py`）——与酒馆（SillyTavern）的前端 JS extension 不同：
> 酒馆插件操作界面，DICK 插件挂接**引擎能力**（模型通道 / 文件系统 / 网络 / 机制卡 / 战斗 / CODEX）。
> 本文档是编写插件必须遵守的标准。
>
> ⚠️ **插件不许自带 GUI 库**（`tkinter` / `customtkinter` / PyQt…）。要文件对话框、提示、确认，一律调
> **`host_ui`**（见 §五之二）：它是宿主的界面通道，跨平台、不引入额外依赖。历史教训：以前插件图方便
> `from tkinter import filedialog`，结果整个应用被迫背着 Tcl/Tk（每次发布 3.5 MB），还得在启动时建一个
> 隐藏 Tk 根窗口 —— 而那个窗口被关掉会**连带整个程序退出**。`tests/test_no_tk.py` 现在会拦住这种事。

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

## 五之二、上下文注入钩子（contextInjection）

```python
def contextInjection(self):
    """返回一段要追加进系统提示词的文本；不需要就返回空串或 None。

    管理器会把【所有已启用插件】的返回值聚合起来注入系统提示词 ——
    适合"这一轮必须遵守的规则""当前剧情状态""本插件能用的命令清单"这类
    每轮都要在场的内容。跑团模式插件就是用它把 GM 规则注进去的。

    ⚠️ 每轮都会注入，而且计入上下文预算：别在这里放会无限增长的东西。
    """
    return "【我的插件】当前状态：……"
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

## 九之二、要界面就调 host_ui（别自带 GUI 库）

插件需要"选个文件""提示一句"时，调宿主通道 `host_ui`（`host_ui.py`，随包分发）：

```python
import host_ui

path = host_ui.ask_file("选择酒馆卡 (PNG/JSON)",
                        types=("卡片文件 (*.png;*.json)", "所有文件 (*.*)"))
if not path:
    return "已取消（或当前环境没有对话框）", False      # 无界面环境返回 None，插件要能降级

save_to = host_ui.ask_save("导出到", default_name="角色卡.json", types=("JSON (*.json)",))
folder  = host_ui.ask_folder("选择模型目录")            # 选目录
host_ui.notify("导入完成：3 张角色卡、1 张世界卡", speaker="酒馆卡片导入")
host_ui.notify("这个文件解析不了", level="warn")        # level: info / warn / error
```

规则与语义：

| 事项 | 说明 |
|---|---|
| **不要** | `import tkinter` / `customtkinter` / PyQt…（`tests/test_no_tk.py` 会红，打包也会被迫背上 Tcl/Tk） |
| 返回 None | 表示"用户取消"**或**"当前环境没有界面"（手机端/服务端/测试）——插件必须把它当正常分支处理 |
| `notify` 去哪 | 作为一条系统消息进聊天记录（前端本来就会渲染系统消息） |
| 可选能力 | `host_ui.capabilities()` 返回 `{"ask_file":bool,"ask_save":bool,"notify":bool}`，可据此决定要不要给按钮 |
| 参数形式 | `types` 用 pywebview 的写法：`"说明 (*.png;*.jpg)"`；不传就 `All files (*.*)` |
| 宿主没接上 | 不会抛异常：`ask_*` 返 None、`notify` 打到 `debug.log` |

> 一句话：**插件只挂引擎能力，界面一律向宿主要** —— 这样插件在电脑版/手机版都能用，也不用为了一个文件框
> 让整个应用背一整套 GUI 库。

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
| 每轮往系统提示词加内容 | `contextInjection` |
| 可配置项 | `settings_schema` + `get_setting/set_setting` |
| 界面按钮 | `ui_buttons`（method/insert） |
| 初始化/清理 | `on_load` / `on_unload` |
| 访问模型/记忆/机制 | `self.core.*` |
| 插件间通信 | 通过 `core`（共享状态） |

---

*DICK 插件标准 v1.0 —— 后辈向酒馆老前辈致意：它管前端，我管引擎。*
