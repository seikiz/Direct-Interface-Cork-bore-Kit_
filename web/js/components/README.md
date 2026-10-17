# web/js/components —— 控件层（占位）

职责：**连按钮都算组件**。每个控件一个工厂函数，返回 DOM 片段，
只认 props、只抛事件，不读全局状态、不认屏。

契约示例（详见 `web/UI_ARCHITECTURE.md`）：

```js
Button({ label, icon, variant, size, disabled, onClick }) -> HTMLElement
```

**边界**：样式只允许用 `web/styles/components.css` 里的类名或 CSS 变量；
不许在组件里写行内 `style="color:#..."`（那就等于把观感焊死在 JS 里）。

现状：还没搬 —— 现在 201 个 `<button>` 直接写在 HTML 里、样式靠类名散落，
`tools/audit_ui_coupling.py` 指标 ⑥ 在数"裸控件"。
