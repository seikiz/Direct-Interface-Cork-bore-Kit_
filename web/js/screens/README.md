<!-- <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ 水印（seiki_mark 不支持 .md，这里手工同格式；渲染时不可见） -->
# web/js/screens —— 屏的脚本

命名：`<名字>.js`，名字就是 DOM id 的前缀（`go`/`gen`/`crop`/`dial`/`em`…，
前缀表见 `web/UI_ARCHITECTURE.md`）。模块对象叫 `XxScreen`（`GoScreen`/`EditMsgScreen`…）。

## 一屏一个文件，还是一屏几个文件？

- **默认一屏一个文件**（下面「单文件」那套）。
- 一屏超过 **400 行**就必须再切：`<屏>-<职责>.js`（例：`codex-editor.js` / `codex-graph.js` /
  `codex-player.js` / `codex-player-scene.js` / `codex-bind.js`）。切完仍然**只有第一个文件**
  负责 `mount()` + `DICK.router.register()`；其余文件只定义函数，并把要共享的部分挂到同一个
  全局命名空间上（例：`window.CodexPlayer`，供同屏的另一个文件调用）。
- 一屏多文件的规矩写在 `web/UI_ARCHITECTURE.md` 的「网页屏幕块清单」里，`tests/test_screen_blocks.py`
  会和磁盘对账：**文件没登记、行数超预算、id 前缀跨屏**，三种都会红。

每个文件固定三段：
1. 顶部一段中文注释：**归属**（片段在哪、有没有专属 css）、**契约**、**依赖的外部符号**；
2. `window.XxScreen = (function(){ … mount() / unmount() … })()`（一屏多文件时只有主文件这么做）；
3. 兼容入口（原来的全局函数名，内部转调模块）+ `DICK.router.register(...)`。

每个文件只允许依赖：
  · `../state.js`（`DICK.state` 读状态、`DICK.bus` 收事件）
  · `../components/`（拼界面）
  · `../bridge/`（调后端）
**不许** `getElementById` 另一个屏前缀的 id —— 那正是当年 185 处跨屏耦合的来源。
一屏多文件时，同屏的不同文件之间也要尽量只经"同屏命名空间"说话，不要互摸对方的私有变量。

现状：已搬 go / gen / crop / dial / em / trpg / mem / save / bk / wm / ws / settings / api_guide
/ **codex（6 个文件）** / **gal（5 个文件）**。顺序与理由见 `web/UI_ARCHITECTURE.md`。
