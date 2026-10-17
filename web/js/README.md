# web/js —— 前端脚本分区（阶段 1 建骨架，阶段 2 开始往里搬）

现状（阶段 2 结束）：
- `web/js/state.js`：`DICK.state`（有名字的状态域）+ `DICK.bus`（一次性事件）—— **跨屏只走这里**；
- `web/js/router.js`：屏的注册 / 片段同步注入 / `mount()`·`unmount()` 分发；
- `web/js/screens/`：已经搬了 5 屏（go / gen / crop / dial / em）；
- 页尾那 6000 多行老脚本还在 `web/index.html` 里，是阶段 5 的活。

| 目录/文件 | 放什么 | 不许放什么 |
| --- | --- | --- |
| `bridge/` | `pywebview.api.*` 的适配层：参数整形、错误兜底、超时/重试 | 业务判断、DOM 操作 |
| `state.js` | 唯一可变状态 + 订阅（键名登记在它的 `SCHEMA` 里） | 任何 `getElementById` |
| `router.js` | 屏的注册、片段注入、mount/unmount 分发 | 具体屏的渲染细节、显隐逻辑 |
| `components/` | 无屏依赖的控件：按钮、输入框、模态壳、下拉 | 直接读全局状态 |
| `screens/` | 一屏一个文件，只依赖 `state` + `components` + `bridge` | 别的屏的内部符号 |

`state/` 与 `router/` 两个空目录保留：现在还没到需要拆包的量，
真拆的时候把 `js/state.js`、`js/router.js` 挪进去，README 一起搬。

规矩只有一条：**屏之间只通过 `state.js` 的订阅/事件通信**。
耦合现状用 `python -X utf8 tools/audit_ui_coupling.py` 量（基线 `tools/ui_coupling_baseline.json`），
搬运前后的结构守恒用 `python -X utf8 tools/ui_snapshot.py --check` 量。
