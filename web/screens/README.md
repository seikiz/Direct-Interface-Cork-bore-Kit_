# web/screens —— 屏的 HTML 片段

这里放**从 index.html 拆出来的屏级 DOM**，一屏一个文件（平的，不进子目录）：

    web/screens/go.html      围棋（🎴 全屏棋盘）
    web/screens/gen.html     生图模态
    web/screens/crop.html    头像裁剪模态
    web/screens/dial.html    时间流速表盘
    web/screens/em.html      编辑消息模态

为什么和 `web/js/screens/` 分开：**结构归这里，行为归 JS**。
这样换皮/改布局时只动 HTML 与 `web/styles/`，不用碰逻辑；反之换逻辑也不动结构。

## 硬规矩（都是踩过的坑）
1. **片段里不许再写 `<!--@screen:…-->`**：HTML 注释不能嵌套，外层注释会被内层的 `-->` 提前截断，
   后半截变成页面上的可见文字。
2. 片段可以有多根节点，按顺序插进挂载点后面；**挂载点必须是注释**
   （`<!--@screen:go-->`），不能是 `<div id="screen-go">` —— 多一层元素会改 DOM 层级与 flex 布局。
3. 搬家时**逐字**复制：class、行内 `style`、属性顺序、缩进都可以原样。
   `python -X utf8 tools/ui_snapshot.py --check` 会核对结构和每一处行内样式。
4. 专属样式写 `web/styles/screens/<名字>.css`，`<link>` 手写进 `index.html` 头部
   （样式表的先后就是层叠顺序，别让 router 运行时插）。

现状：阶段 2 搬完 5 屏。下一批的判据同前：DOM 在 index.html 里是连续的一段、
且 `tools/audit_ui_coupling.py` 指标 ⑤ 里它跟别的屏只剩个位数交叉引用。
