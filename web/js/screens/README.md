# web/js/screens —— 屏的脚本，一屏一个文件

命名：`<名字>.js`，名字就是 DOM id 的前缀去掉前缀（`go`/`gen`/`crop`/`dial`/`em`…，
前缀表见 `web/UI_ARCHITECTURE.md`）。模块对象叫 `XxScreen`（`GoScreen`/`EditMsgScreen`…）。

每个文件固定三段：
1. 顶部一段中文注释：**归属**（片段在哪、有没有专属 css）、**契约**、**依赖的外部符号**；
2. `window.XxScreen = (function(){ … mount() / unmount() … })()`；
3. 兼容入口（原来的全局函数名，内部转调模块）+ `DICK.router.register(...)`。

每个文件只允许依赖：
  · `../state.js`（`DICK.state` 读状态、`DICK.bus` 收事件）
  · `../components/`（拼界面）
  · `../bridge/`（调后端）
**不许** `getElementById` 另一个屏的 id —— 那正是当前 185 处跨屏耦合的来源。

现状：已搬 go / gen / crop / dial / em。顺序与理由见 `web/UI_ARCHITECTURE.md` 的「下一批」。
