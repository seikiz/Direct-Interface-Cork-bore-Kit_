# web/js/state —— 唯一状态源（实现暂时是单个文件 `../state.js`）

职责：持有可变状态，暴露 `get()` / `set()` / `on()`，**跨屏通信只走这里**。
屏写状态，屏订阅状态，谁都不去戳别人的 DOM。

**边界**：不许出现 `document.getElementById`；不许引用任何 `screens/` 里的东西。

现状：实现已经在 `web/js/state.js`（阶段 2）。键名登记在那里的 `SCHEMA`：
`editMsg.target`（编辑消息屏在用）、`router.ready` / `router.open`（router 自己用）。
`web/index.html` 顶层还有 55 个"会被重新赋值"的全局
（`tools/audit_ui_coupling.py` 指标 ④ 在数），继续一次搬一个域（主题/语言 → 角色卡 → 编年史 → GAL），
别一把梭。
