# Web 前端结构（解耦 阶段 0 / 1 / 2 / 3 / 4 已完成，5 做了数据层）

口径：**结构先就位，逻辑分批搬**。`index.html` 从 7969 行 → 7340（阶段2）→ **6240 行**（阶段4 收尾），
搬走了 11 屏（围棋/生图/裁剪/表盘/编辑消息 + 跑团/记忆调试/多存档/加密备份/世界书条目/创意工坊/设置），
把 7 个顶层 var 收进 `DICK.state`，把文案从「setT 里逐个 id 改名」改成 `data-i18n` 标注，
并把编年史 / GAL 制作器的**数据层**抽成 `web/js/store/`。

各阶段收尾时的 `index.html` 行数（audit 口径，含末尾空行）：

| 阶段 | 做了什么 | index.html | 解耦分 |
| --- | --- | --- | --- |
| 2 | 状态/路由骨架 + 5 个小屏 | 7340 | 29.6 |
| 3 | state 收口（7 个 var）+ 6 个面板屏 | 6531 | 32.0 |
| 4 | i18n 改 `data-i18n` + 设置屏 | 6256 | 34.0 |
| 5（数据层） | codex/gal 的 23 个顶层 var → `DICK.state`，抽 store | 6240 | 35.0 |

> 安卓侧同期由另一条线在拆（`Theme.kt` 退役、`App.kt`/`Dialogs.kt` 分流到 `ui/`、`nav/`），
> 所以 `audit_ui_coupling` 的总分里，①③⑤（安卓部分）的涨落不全来自网页端 —— 看网页端就看
> "⑤ 屏与屏的耦合" 括号里的 `网页 N` 和 ① 里 `web/index.html` 那一行。

每次搬完必须跑的三件事（少一件就等着出怪 bug）：

```
python -X utf8 tools/ui_snapshot.py --check      # 结构 / 样式规则 / 行内 style 有没有被无意改动
python -X utf8 tests/test_web_dom.py             # JS 引用的元素/函数是不是真的存在
node tests/test_icons.js                         # emoji → 图标名覆盖率
```

`tools/audit_ui_coupling.py` 量的是"有多耦合"（基线 `tools/ui_coupling_baseline.json`），
改完跑一遍，数字变差就非 0 退出。

## 目录职责
| 路径 | 职责 | 硬边界 |
| --- | --- | --- |
| `web/index.html` | 文档骨架 + **挂载点** + 页尾老脚本 | 不再长 `<style>`；不再新增顶层 `<script>`（屏的代码进 `js/screens/`） |
| `web/screens/<名字>.html` | 一屏的 DOM 片段（结构归这里） | 不写逻辑；片段里不出现 `<!--@screen:…-->` 嵌套（HTML 注释不能嵌套） |
| `web/js/state.js` | `DICK.state`（有名字的状态域）+ `DICK.bus`（一次性事件）+ `bindGlobal`（老名字→状态域） | 不碰 DOM、不读 localStorage |
| `web/js/store/<名字>.js` | 一个**数据层**：把某一大块功能的状态域登记好，再给一个薄壳 API（`get/set/reset…`） | 只碰 state，不碰 DOM、不 import 屏 |
| `web/js/router.js` | 屏的注册 / 片段**同步**注入 / mount·unmount 分发 | 不渲染屏内容、不管显隐 |
| `web/js/screens/<名字>.js` | 一屏的行为：`mount()` / `unmount()` + 兼容入口 | 不许 `getElementById` 另一个屏的 id |
| `web/styles/` | `tokens`（变量+reset）→ `screens` → `components` → `panels`，**顺序即层叠** | 不许按"语义"重排文件（见各文件头注释）；屏的专有样式写 `styles/screens/<名字>.css`，`<link>` 手写进 index.html 头部（顺序必须在人眼前） |
| `web/js/bridge/` `state/` `router/` `components/` | 阶段 1 定的分区，桥/组件还没搬 | 空目录保留，`state`/`router` 目前就是上面那两个单文件 |

## 阶段2：一屏怎么装进页面

1. `web/screens/go.html` 存这一屏的 DOM（从 index.html **逐字**搬出来的那段）。
2. `index.html` 原地只留一个注释挂载点：

   ```html
   <!--@screen:go-->  <!-- 这一屏的 DOM 在 web/screens/go.html，由 web/js/router.js 同步注入 -->
   ```

   挂载点必须是注释，不能是 `<div id="screen-go">`：多包一层 div 会改 DOM 层级，
   而模态的样式里有按祖先/兄弟算的规则（而且 `#inputbar` 是 flex 容器，多一个元素就是多一个 flex item）。
   注释节点不参与布局，插在它后面 = 和原来写在那个位置**一模一样**。

3. `web/js/screens/go.js` 只做两件事：定义模块（`window.GoScreen = (function(){…})()`）、
   注册自己（`DICK.router.register('go', {fragment:'screens/go.html', module: window.GoScreen})`）。
4. `index.html` 页尾、老脚本**之前**：

   ```html
   <script src="js/state.js"></script>
   <script src="js/router.js"></script>
   <script src="js/screens/go.js"></script>   <!-- 各屏只定义 + 注册 -->
   …
   <script>DICK.router.boot();</script>       <!-- 同步注入片段 + 逐屏 mount() -->
   <script>/* 页尾那 6000 多行老脚本原封不动 */</script>
   ```

### 为什么注入必须是同步的
页尾那段老脚本是**解析期**就执行顶层语句的（`document.getElementById('dialSave').onclick = …`）。
片段如果异步到位，这些 `getElementById` 会拿到 `null`，整段脚本当场抛异常 ——
后面所有的绑定、轮询、渲染全部不会发生，而页面看上去"还行"（只是点什么都没反应）。

所以 `router.js` 用**同步 XHR** 读片段（`index.html` 的 `file://` 页面能读同目录文件，
前提是 pywebview 默认给 WebView2 开了 `--allow-file-access-from-files`，
见 `webview/__init__.py` 的 `ALLOW_FILE_URLS = True`），拿到后 `innerHTML` 塞进 `<template>`，
再 `insertBefore(template.content, marker.nextSibling)`。代价是控制台一条
"Synchronous XMLHttpRequest 已弃用"的警告和一次本地文件读（十几 KB、几毫秒），
换来的是零时序风险 —— 值。

### state.js 的用法（跨屏只走这里）
```js
DICK.state.set('editMsg.target', { seq: 3, kind: 'ai' });  // 写（值没变不惊动订阅者）
DICK.state.get('editMsg.target', null);                    // 读
DICK.state.on('editMsg.target', fn);                       // 订阅，返回退订函数
DICK.bus.emit('msg:edit', { seq: 3, kind: 'ai', text: '…' });  // 一次性动作
DICK.bus.on('msg:edit', fn);
```
键名登记在 `state.js` 的 `SCHEMA` 里（阶段3/5 之后有 33 个域：`editMsg.*`、`router.*`、`ws.*`、`wm.*`、
`save.*`、`codex.*`、`gal.*` —— 每一条都写了"谁写谁读"）。
新加一个域要写清"谁写谁读"，否则它就是下一个裸全局。

### 一屏模块的模板
```js
window.XxScreen = (function (global) {
  'use strict';
  var mounted = false;

  /* … 本屏的状态与函数（原来是 index.html 的顶层代码，搬过来只多缩进两格）… */

  function mount() {                 // router 注入片段之后调；幂等
    if (mounted) { return; }
    if (!document.getElementById('xxModal')) {      // 片段没到位就别硬挂
      console.error('[xx] 片段没注入，跳过挂载');
      return;
    }
    mounted = true;
    /* …原来写在顶层的那些 onclick / addEventListener 绑定… */
  }
  function unmount() { /* 收定时器、退订、置空 —— 现在没人调，但契约先立好 */ }

  return { mount: mount, unmount: unmount, /* 给兼容入口转调用的动作 */ };
})(window);
DICK.router.register('xx', { fragment: 'screens/xx.html', module: window.XxScreen });
```

## 已搬出的屏
阶段 2（5 个低耦合小屏）：

| 屏 | 片段 | 模块 | 兼容入口（阶段 5 清理） | 还欠的跨屏依赖 |
| --- | --- | --- | --- | --- |
| 🎴 围棋 `go` | `screens/go.html`（30 行） | `js/screens/go.js`（212 行） | `goOpen` `goClose` `goNew` `goPlay` `goAct` `goPaint` `goBind` `goEl` | `galToast()`、外壳的 `#btnGo`（mount 里绑） |
| 🎨 生图 `gen` | `screens/gen.html`（40 行） | `js/screens/gen.js`（154 行） | `applyGenLast` `loadGenPresets` `genRun` `genHintByBackend` | 读设置屏的 `#stImgBackend`/`#stImgBase` |
| ✂️ 裁剪 `crop` | `screens/crop.html`（20 行） | `js/screens/crop.js`（150 行） | `cropOpen` `cropRender` | `avatarCache` / `reloadRoles()`（聊天屏） |
| ⏳ 表盘 `dial` | `screens/dial.html`（17 行） | `js/screens/dial.js`（229 行） | `timeDialOpen` `dialRender` | `treeStatus()`（树面板）、`alert()` |
| ✏️ 编辑消息 `em` | `screens/em.html`（14 行） | `js/screens/em.js`（98 行） | `openEditMsg`（原来没有函数名，入口是顶层 var `editTarget`） | `T.editMsg`、`alert()` |

阶段 3（6 个面板屏 + state 收口）与阶段 4（设置屏）：

| 屏 | 片段 | 模块 | 专属 CSS | 兼容入口（阶段 5 清理） | 还欠的跨屏依赖 |
| --- | --- | --- | --- | --- | --- |
| 🎭 跑团 `trpg` | `screens/trpg.html`（4 行） | `js/screens/trpg.js`（44 行） | 无（全行内） | `renderTrpgBar` | `loadState()` 退出后重刷、`escapeHtml()` |
| 🧠 记忆调试 `mem` | `screens/mem.html`（14 行） | `js/screens/mem.js`（60 行） | 无（全行内） | `memDebugDraw` | `evEsc()`、外壳机制条 `renderTreePanel` 反向摸 `#memDebugHead`/`#memDebugModal` |
| 💾 多存档 `save` | `screens/save.html`（17 行） | `js/screens/save.js`（137 行） | `styles/screens/save.css`（11 条规则） | `openSaves` `renderSaveList` `saveFmtTs` | `#chat` 清空、`streamingEl`/`lastSeq`/`loadState()`（外壳） |
| 🔐 加密备份 `bk` | `screens/bk.html`（41 行） | `js/screens/bk.js`（163 行） | 无（用组件层 .modal/.field/.row） | `bkStatus` `bkOpen` `bkClose` `bkGen` `bkPwStrength` `bkExport` `bkRestore` | `reloadRoles()`/`reloadWorlds()`、`escapeHtml()`；index.html 的 Esc 关窗仍调 `bkClose()` |
| 🌍 世界书条目 `wm` | `screens/wm.html`（25 行） | `js/screens/wm.js`（214 行） | `styles/screens/wm.css`（16 条规则：`.wentry` + `.p-grid`） | `renderWmParams` `collectWmParams` `renderWmEntries` `collectWmEntries` | `reloadWorlds()`、`lastUserText`、`escapeHtml()`；`#btnNewWorld` 在侧栏、`#worldList` 的点击分流留在 index.html（只调 `WmScreen.openEdit`） |
| 🧰 创意工坊 `ws` | `screens/ws.html`（58 行） | `js/screens/ws.js`（299 行） | `styles/screens/ws.css`（11 条规则：`.ws-*`） | `wsSetStatus` `wsRefreshAuto` `wsLoadLocal` `wsShowLocalPreview` `wsSwitchTab` `wsFillOnline` `wsSetPluginStatus` `wsRefreshPlugins` `wsRefreshOnline` | `reloadRoles()`/`reloadWorlds()`、`jobWait()`、`escapeHtml()`、`#btnWorkshop` |
| ⚙️ 设置 `settings` | `screens/settings.html`（142 行） | `js/screens/settings.js`（122 行，**只搬了预算/字体/插件管理那几段**） | 无（用组件层 .modal/.field/.prow） | `renderBudget` `applyFont` `renderPlugins` | 见下面「阶段 5 待办」：设置屏的其余 JS 与外壳缠得很深 |

### 为什么 `ws`/`wm`/`save` 有专属 CSS，别的屏没有
只有**真的以这一屏命名、且别处不用**的规则才搬：`.ws-*`、`.wentry`/`.p-grid`、`.save-row`/`.save-new`。
搬家只改存放位置、一行声明都没动（`ui_snapshot` 比的是全局规则集合，会核对）；
`<link>` 顺序是**层叠的一部分**，所以三处都是插在原来那一段的相对位置：
`save.css` 紧跟 `screens.css`（仍在 `components.css` **之前**），`wm.css`/`ws.css` 排在 `panels.css` 之后
（`components.css` **之后**）—— `.save-new input` 与 `.modal-box input`、`.ws-card .btn2` 与 `.modal-box .btn2`
各自特异性相同，靠的就是这个前后关系。改顺序 = 改观感，别动。

## 阶段 3：state 收口（7 个顶层 var → 状态域 + 兼容访问器）

为什么不是「直接改名」：这些名字在页面里被裸读写几十处（`wsCurLocal = …` / `if (!editingWorld)`），
搬一屏就全改一遍的收益远小于风险。所以让**名字继续能用**，值只存在 state 里：
`DICK.state.bindGlobal(名字, 状态域, 默认值)` 在 window 上挂一个访问器（getter/setter 直通 store）。

| 老名字 | 状态域 | 谁写谁读 | 注册在哪 |
| --- | --- | --- | --- |
| `wsCurLocal` | `ws.curLocal` | ws 屏：创意工坊「本地」页选中的文件 `{rtype, filename}` | `js/screens/ws.js` |
| `wsCurOnline` | `ws.curOnline` | ws 屏：在线列表选中的作品 | `js/screens/ws.js` |
| `wsOnlineCache` | `ws.onlineCache` | ws 屏：上次拉到的在线列表（渲染 + 选中都靠它） | `js/screens/ws.js` |
| `wmEntries` | `wm.entries` | wm 屏：编辑中的世界书条目数组（未落盘） | `js/screens/wm.js` |
| `wmParams` | `wm.params` | wm 屏：编辑中的 8 格世界参数（未落盘） | `js/screens/wm.js` |
| `editingWorld` | `wm.editingWorld` | wm 屏：正在编辑哪个世界（null = 新建） | `js/screens/wm.js` |
| `saveModalCur` | `save.current` | save 屏：多存档面板正在看哪个角色的存档 | `js/screens/save.js` |

两个坑（写在 `state.js` 的 `bindGlobal` 注释里了）：
① 先 `defineProperty` 后 `var` → TypeError（顶层 `var` 在 window 上占的是不可配置属性），所以**必须先把 `var` 删掉**；
② 默认值必须是同一份引用（`[]` / `{}` 只在注册时落一次），否则 `wmEntries.push(…)` 推进一个临时数组，下一秒就没了。

跨屏通知走 `DICK.bus`：`loadStateFill()` 不再直接点名 `renderTrpgBar()`，改成
`DICK.bus.emit('trpg:state', s.trpg)`，trpg 屏在 `mount()` 里订阅 —— 外壳不知道谁来画那条状态条。

## 阶段 4：文案改标注（`data-i18n`）

以前换语言 = `setT()` 里 68 行「按 id 摸元素、改 textContent」。它一个人就贡献了 43 处跨屏 id 引用。
现在文案写在元素上，`setT()` 只剩 5 件事：

```html
<span data-i18n="sidebar" data-i18n-prefix="🎭 " id="cardsTitle">🎭 角色与世界</span>
<textarea data-i18n-placeholder="placeholder" id="input" …></textarea>
```

| 标注 | 含义 |
| --- | --- |
| `data-i18n="<键名>"` | `textContent = T[键名]` |
| `data-i18n-prefix="🎭 "` | 前面再拼一个图标前缀（**前缀不进文案表**，emoji 由图标系统换掉） |
| `data-i18n-placeholder="<键名>"` | `placeholder = T[键名]` |

- 键名**就是** `lang/strings.json` 的键，一个都没新造；`tools/gen_i18n.py` 的 `desktop_web` 判定已扩展成
  「`T.键` / `T['键']` / `data-i18n="键"` / `data-i18n-placeholder="键"` 都算在用」，否则整页的键会被判成死键。
- 表里没有这个键时**不动元素**：初始 HTML 里那行中文就是兜底（漏翻也看得懂，不会变空白）。
- `tests/test_i18n_langs.py` ⑨ 会核对：标注的键必须都在 json 里、三语都有文案、`setT()` 不许再逐 id 改名。
- 仍是 JS 动态生成的（不属于标注）：8 格世界参数标签（`T['param_' + k]`）、预设按钮（要拼当前预设名）、
  语言下拉的选中项、`语言 / Language / 言語` 这行三语同形题头。

## 阶段 5（只做了数据层）：`web/js/store/`

| 文件 | 状态域 | 管什么 |
| --- | --- | --- |
| `js/store/codex.js` | `codex.*`（8 个） | 编年史：当前包 / 编辑中的剧本 / 播放器运行时 / 音量 / 打字速度 / 打包轮询定时器 / 节点图编辑器的剧本与选中场景 |
| `js/store/gal.js` | `gal.*`（15 个） | GAL 制作器：剧本 / 每条线的 body 容器 / 拖动中节点 / 连线中 / 平移与缩放 / 撤销重做栈 / 素材缓存 |

这 23 个顶层 var 全部改成 `bindGlobal`，**其余代码一行没动**（老名字照旧读写）；
`DICK.store.codex` / `DICK.store.gal` 提供 `get/set/clearPlayer/resetView/clearAssets/keys`。
这一步只是"数据有了明确的家"，**编年史与 GAL 的 UI 还没搬**（见下）。

## 阶段 5 待办（还没做的，按风险排序）
1. **编年史编辑器 + 播放器（85 处互引）**：`#codexModal` 那 160 行 DOM → `screens/codex.html`，
   `#codexPlayer` 那份全屏播放器也要一起；JS 约 1200 行（`codex*` 90 个函数 + `cx*` 播放器 20 个）。
   编辑器→播放器现在有 12 处直接摸 `#cx*` 的 DOM（`codexPlay`/`codexNextLine`/`codexShowChoice`…），
   搬的时候**只许经 `DICK.store.codex` + `DICK.bus`**，原全局函数名留兼容入口。
2. **GAL 制作器（约 1000 行 + SVG 连线/拖拽）**：`#galEditor` 全屏画布。坐标计算与事件绑定必须原样搬，
   搬完要跑一次交互 smoke（开编辑器 → 加节点 → 连线 → 保存 → 播放器读得到）。
3. **设置屏剩下的 JS**：`loadStateFill()`（94 行，一边填设置控件一边刷聊天状态）、
   `fillProvider`/`renderProviderSel`/`renderModelSel`/`closeOverlays`（下拉浮层组件，预设菜单也在用）、
   `applyTheme`/`applyChatWallpaper`（观感层，聊天屏也调）、预设编辑器、Live2D 段。
   这些不以"按屏切"为主要矛盾，先要把 `loadStateFill` 拆成"拉状态 / 分发给各屏"两半。
4. **新建角色 `nr` / 角色卡编辑 `pp` / 角色卡槽 `role` / 世界卡槽 `world`**：`nr` 与 `pp` 的表单代码互相
   复用（`fillRoleFields`/`collectRoleFields` 两边都在用），要连着搬。
5. **`ev` 事件编辑器（4 处摸 `nr*`）**、**`qc` 快捷面板**、**`fin` 财报折叠**、**`onb` 首启引导**、**`sg` 箭头教程**。

## 剩余跨屏依赖 Top（阶段 5 的施工顺序表）
| 处数 | 从 → 到 | 具体是什么 |
| --- | --- | --- |
| 85 | 编年史编辑器 `codex*` → 编年史播放器 `cx*` | 播放器没有"状态机"，一切由编辑器函数直接改 `#cxText`/`#cxChoice`/`#cxSprite` 等 DOM |
| 18 | 顶层绑定语句 → 播放器 `cx*` | `#cx*` 那堆 onclick/keydown 绑定还写在 index.html，和编辑器函数混在一个匿名块里 |
| 12 | `codexPlay` → 播放器 | 开播时一次性设 `#codexPlayer`/`#cxStage`/`#cxTextbox` 的显隐 |
| 11 | 新建角色 `nr*` → 设置 `st*` + 角色卡槽 `role*` | 角色卡编辑里读设置、列存档 |
| 11 | 事件编辑器 `ev*` → 新建角色 `nr*` | 事件进度面板读角色卡的机制字段 |
| 6 | 顶层绑定 → 快捷面板 `qc*` | 快捷面板按钮绑定还在 index.html |
| 5 | `wm.js` → `world*` | `#worldModal` 这个 id 的前缀是 `world`（审计按前缀归属，所以算成"世界卡槽"的）—— 是审计口径问题，不是真耦合 |
| 4 | `gal` → 编年史编辑器 `codex*` | `galSave`/`galJson` 复用编辑器的状态栏与 JSON 面板 |
| 3 | 外壳 → 财报折叠 `fin*` | 快捷面板里那个折叠区的显隐由外壳控制 |
| 2 | 外壳 → 角色卡槽/世界卡槽 | 侧栏列表的选择事件 |
| 1 | `save.js` → `#chat` | 读档后清空聊天区（该换成 `DICK.bus.emit('chat:reload')`） |
| 1 | `mem` 反向 | 外壳机制条直接摸 `#memDebugHead`/`#memDebugModal`（该换成 `DICK.bus.emit('mem:draw')`） |

## 快照工具能挡什么、不能挡什么
`tools/ui_snapshot.py` 把三样东西拍成 `tools/ui_snapshot.json`：DOM 结构树
（层级 + tag + id + class + 其余属性）、所有 CSS 的"选择器 → 声明"集合、
每个带 `style=` 的元素的规范化行内样式。它认 `<!--@screen:名字-->`，会先把片段展开再拍，
所以"把一屏搬出去"这一步本身不会让它变红 —— 只有搬错才会。

- **能挡**：DOM 层级/位置挪错、class 漏一个或改名、id 改了、CSS 声明被改/删/重复
  （含 `@media` 上下文）、行内 `style` 被顺手改掉。
- **挡不住**：浏览器层的层叠计算（继承、同优先级先后、`@supports`、`:hover`/`:focus`、
  `:nth-child`、字体度量与换行）、运行时 DOM（`goPaint()` 的棋盘、`dialRender()` 的 SVG、
  聊天消息）、文字内容（文案走 i18n，不在守恒范围）、真像素。
  它是"搬运守恒"的栅栏，不是渲染截图对比。

合法改动（设计变更）就 `--write` 重钉基线，并在 commit/PR 里说明为什么。

## DOM id 前缀规范
一屏一个前缀，id = `<前缀><驼峰>`，前缀即"这一屏的命名空间"：
`st`（设置）、`nr`（新建角色）、`pp`（角色卡编辑）、`codex`/`cx`（编年史编辑器/播放器）、
`ws`（世界书/世界卡）、`gal`（GAL 制作器）、`go`（围棋）、`gen`（生图）、`ev`（事件）、
`wm`（世界书条目）、`bk`（备份）、`mem`（记忆调试）、`trpg`（跑团）、`dial`（时间表盘）、
`onb`（首启引导）、`sg`（教程）、`save`（多存档）、`crop`（裁剪）、`em`（编辑消息）。
外壳（侧栏/主区/输入区）用无前缀短名（`chat`/`input`/`send`/`choices`…）。

## 新增一屏要动的文件
1. `web/screens/xx.html`：这一屏的 DOM（从 index.html 剪出来，逐字别改）；
2. `web/index.html`：原位留 `<!--@screen:xx-->` 挂载点 + 一行 `<script src="js/screens/xx.js">`；
3. `web/js/screens/xx.js`：`mount()`/`unmount()` + 自注册 + 兼容入口；
4. `web/js/state.js`：它需要的状态域（登记进 `SCHEMA`，写清谁写谁读）；
5. 需要后端就加 `web/js/bridge/` 的适配；
6. 跑 `python -X utf8 tools/ui_snapshot.py --check`、`tests/test_web_dom.py`、`node tests/test_icons.js`，
   再跑 `python -X utf8 tools/audit_ui_coupling.py --baseline tools/ui_coupling_baseline.json`。

## 组件契约
- **props 进、事件出**：组件不读全局状态，交互只通过 `onXxx` 回调往外抛。
- **样式边界**：只允许用 `web/styles/components.css` 的类名与 `theme.css` 的 CSS 变量；
  组件内不许写行内 `style="color:#…"`（那就等于把观感焊进 JS）。
- **无屏意识**：组件不知道自己在哪一屏；屏通过传参表达差异（尺寸/变体），不靠父选择器。
- **可测**：工厂函数是纯的 —— 同样 props → 同样 DOM，不发请求。

按钮组件（签名先定下来，还没落地）：

```js
// web/js/components/Button.js
Button({
  label,      // 文案（必填；可含 emoji，由 iconify 换成图标）
  icon,       // 可选：Material Symbols 名字，渲染在 label 前
  variant,    // 'primary' | 'ghost' | 'danger' | 'plain'，默认 'plain'
  size,       // 'sm' | 'md' | 'lg'，默认 'md'
  disabled,   // 布尔，默认 false
  onClick,    // (event) => void
}) -> HTMLElement            // 返回 <button class="btn btn--primary btn--md">，不自挂载
```

## 下一批的注意点
- **别在搬结构时顺手美化**：行内 `style=` 一律原样搬（本轮 6 屏 + 设置屏都是这么搬的）。
  真要抽成类名，抽完必须 `ui_snapshot --write` 重钉，并核对 diff 只有 `style` 那一栏在动。
- **一次只搬一屏**，每屏四件套：`ui_snapshot --check`、`test_web_dom`、`test_icons.js`、**逐行守恒**
  （把原块按行做有序子序列比对，允许注释/挂载点差异 —— 这条能挡住"搬的时候少抄了一行"）。
- 每加一个 `<script src="js/screens/xx.js">` 或 `<link href="styles/screens/xx.css">`，`ui_snapshot` 都会
  报 DOM 差异（它把 script/link 也算元素）。确认差异**只有**这一行，再 `--write` 重钉。
- `tests/test_web_dom.py` ⑥ 查"跨文件同名声明"：两个模块定义同名全局会静默覆盖。
  所以兼容入口只能写在**一个**模块文件里。
- 搬完一屏记得 `utau_env\Scripts\python.exe seiki_mark.py mark <改过的文件>`（水印插在注释里，幂等）。

## 安卓侧（阶段 1 / 2 已完成）

口径与网页同一条：**结构先就位，逻辑分批搬**，一次只搬一屏、搬完立刻编译。
本轮把 `App.kt`（2734 行）+ `Dialogs.kt`（2907 行）两个扁平巨文件拆成了
`App.kt`（**30 行**：入口 + 主题解析）+ `Dialogs.kt`（**238 行**：只剩兼容门面）
+ `ui/screens/<feature>/` 一屏一份。**没有改任何布局数值、文案与交互顺序**（唯一的观感改动
是用户点名要修的四个 UI bug，见文末）。

### 目录职责
| 路径 | 职责 | 硬边界 |
| --- | --- | --- |
| `App.kt` | 取 `ChatViewModel` + 解析主题（`resolveTheme`/`accentFor`）+ 转调 `ChatScreen` | 不加任何屏的代码；新屏去 `ui/screens/` |
| `ui/screens/chat/ChatScreen.kt` | 聊天主屏（顶栏 / 机制三栏 / 消息列表 / 输入栏 / 引擎接线） | 只认 `vm` / `theme` / `accent` / `OverlayHost`；下一步按"顶栏→机制栏→输入栏→消息列表→引擎动作"继续切 |
| `ui/screens/<feature>/` | **一屏一包**：`XxxScreen.kt`（渲染）+ `XxxState.kt`（屏内瞬态）+ `XxxActions.kt`（对外依赖） | 屏不许读别的屏的内部字段；跨屏只走 `vm` 的 `showXxx` 开关与回调 |
| `ui/components/` | 共用控件（按钮/图标按钮/标签/输入框/卡片/勾选行/弹窗壳/空状态/加载态） | **只吃参数**：不读 `ChatViewModel`、不读 App 闭包、不认屏；颜色只许来自 `LocalDickPalette` |
| `ui/theme/` | `Tokens.kt`（生成物，色值唯一真相）+ `Theme.kt`（`ThemeSpec`/`THEMES`/`ACCENTS`/身份色 + 三语显示名） | 颜色只在这里出现（`gen_tokens.py` 的输出路径已跟着改） |
| `nav/Routes.kt` | 屏的注册（`Routes` 常量 = `vm.showXxx` 开关名）+ `OverlayHost`（叠放顺序） | 不写业务，只转调；**顺序 = 叠放顺序**，别重排 |
| `nav/DialogDeps.kt` | App() 与屏之间的接线契约（启动器 / 回调 / 只读对象） | 每收窄一屏（`<Feature>Actions`）就少一个字段 |
| `Dialogs.kt` | **历史门面**：同名 Composable 转调新屏 | 门面里不许加逻辑；新屏不许再往这里写 |
| `Ui.kt` | 图标系统（`MsIcon`/`IconText`/`splitLeadingEmoji`）+ 聊天气泡/头像 | 「机器」层，下一步再搬进 `ui/components/`（`tests/test_android_icons.py` 钉着这个路径） |

### 状态怎么走（跨屏只认这一个出口）
- **唯一状态源 = `ChatViewModel`**。App 级偏好（主题/强调色/预设/世界/开发者模式/去 AI 味/
  风格闸/长句/自动接话/语言）2026-11 全部收进 `vm`，各屏 `var x by vm.x` 读写同一份；
  以前是 `App()` 里 `rememberSaveable` 一份 + 屏里一份副本 —— 两份迟早不同步。
- **屏内瞬态放 `XxxState.kt`**（例：`SettingsState.foldPlugins`）。判据：离开这一屏就没意义 → State；
  别的屏/引擎也要读 → `vm`。
- **屏与 App 的接触面 = `XxxActions`**（例：`SettingsActions` / `WorkshopActions`）。
  屏不再拿整个 `DialogDeps` 抽屉；兼容层用 `DialogDeps.settingsActions()` 投影。
- **屏与屏之间不许互相调用**：要么改 `vm` 的开关，要么用回调往上抛（`Lanes` 与 `vm` 的现有写法，
  没有新造事件总线）。

### 组件签名（`ui/components/`，全部"只吃参数、事件往外抛"）
```kotlin
// Buttons.kt —— 三档按钮，语义固定（Primary=当前值/主操作，Secondary=次级入口，Plain=行内轻动作）
enum class DickButtonVariant { Primary, Secondary, Plain }
@Composable fun DickActionButton(label: String, onClick: () -> Unit,
                                 variant: DickButtonVariant = DickButtonVariant.Plain,
                                 modifier: Modifier = Modifier, enabled: Boolean = true,
                                 fontSize: TextUnit = TextUnit.Unspecified,
                                 color: Color = Color.Unspecified)
@Composable fun DickButton(label, onClick, modifier, enabled, fontSize)          // Primary
@Composable fun DickTextButton(label, onClick, modifier, enabled, fontSize, color) // Plain
@Composable fun DickOutlinedButton(label, onClick, modifier, enabled, fontSize)   // Secondary
@Composable fun DickIconButton(icon: String, onClick: () -> Unit, modifier = Modifier,
                               enabled = true, fontSize = 12.sp, iconSize = 16.dp,
                               tint = Color.Unspecified)                          // 只有图标的 TextButton

// Fields.kt
@Composable fun DickField(value: String, onValueChange: (String) -> Unit, label: String,
                          modifier = Modifier, singleLine = false, minLines = 1, enabled = true)      // 浮动 label
@Composable fun DickLabeledField(value, onValueChange, label: String, modifier = Modifier,
                                 hint: String? = null, singleLine = false, minLines = 1, enabled = true) // label 在框上方，hint 在框下方灰字

// Cards.kt
enum class DickTone { Text, Muted, Dim, Accent, Danger, Ok, Warn }
enum class DickSurfaceTone { Surface, Surface2, Bubble }
@Composable fun DickCard(modifier = Modifier, radius: Dp = 12.dp,
                         tone: DickSurfaceTone = DickSurfaceTone.Surface, content: @Composable () -> Unit)
@Composable fun DickTag(text: String, modifier = Modifier, tone: DickTone = DickTone.Muted,
                        fontSize: TextUnit = TextUnit.Unspecified, iconSize: Dp = 16.dp,
                        maxLines: Int = Int.MAX_VALUE)                                   // 标签/徽章/状态串
@Composable fun DickCheckRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit,
                             modifier = Modifier, topPadding: Dp = 14.dp, iconSize: Dp = 14.dp)

// DialogShell.kt
@Composable fun DickDialog(onDismissRequest: () -> Unit, title: @Composable () -> Unit,
                           text: @Composable () -> Unit, confirmButton: @Composable () -> Unit,
                           dismissButton: @Composable (() -> Unit)? = null)

// States.kt
@Composable fun DickEmptyState(text: String, modifier = Modifier, fontSize = 12.sp, iconSize = 13.dp)
@Composable fun DickLoading(text: String, modifier = Modifier, fontSize = 12.sp, iconSize = 13.dp)
```
规矩：**同一控件在两个以上屏出现过 → 必须收进这里**，屏里不许再直接散调 Material3 的
`Button`/`TextButton`/`OutlinedButton`/`OutlinedTextField`。
仍然读全局的组件：**0 个**（`DickTag`/`DickCard` 读 `LocalDickPalette`，那是主题令牌，不是状态）。

### 一屏的目录长这样
```
ui/screens/settings/
├── SettingsScreen.kt   渲染（只认 vm + SettingsActions）
├── SettingsState.kt    屏内瞬态（foldPlugins）
├── SettingsActions.kt  对外依赖 + DialogDeps 投影
└── TimeDialScreen.kt   时间流速表盘（设置打开的子面板）
```

### 搬迁进度（`Dialogs.kt` 里已经"没人"的名字 = 门面）
| feature | 文件 | 兼容门面 |
| --- | --- | --- |
| settings | `SettingsScreen.kt`(327) `TimeDialScreen.kt` | `SettingsDialog` `TimeScalePanel` |
| workshop | `WorkshopScreen.kt`(319) + State/Actions | `WorkshopDialog` |
| lifeSpace | `LifeSpaceScreen.kt`(417) | `LifeSpaceSettingsPanel` |
| trpg | `TrpgScreen.kt`(165) | `TrpgDialog` |
| cardEdit | `CardEditScreen.kt`(610) `PersonaScreen.kt`(192) | `RoleEditDialog` `PersonaDialog` |
| backup | `BranchesScreen.kt`(266) `SaveSlotsScreen.kt`(65) | `BranchesDialog` `SaveSlotsDialog` |
| library | `RolesScreen.kt`(101) `WorldsScreen.kt`(43) `WorldEditScreen.kt`(142) | `RolesDialog` `WorldsDialog` `WorldEditDialog` |
| common | `DeleteConfirmScreen.kt` `CardFaceScreen.kt` `AvatarCropScreen.kt` `EditMsgScreen.kt` `FolderMenuScreen.kt` `Endings.kt` | 同名 |
| chat | `ChatScreen.kt`(2736) | —— |

### 还欠的（按顺序建议）
1. **`Ui.kt` 的图标机器搬进 `ui/components/`**：`MsIcon`/`IconText`/`splitLeadingEmoji`/
   `MaterialSymbols`。卡在 `tests/test_android_icons.py` ⑤ 钉了 `.../com/dick/app/Ui.kt` 这个路径
   —— 要连测试里的 `UI` 常量一起改（一条路径）。
2. **`ChatScreen.kt` 继续切**（2400 行）：顶栏 → 机制三栏 → 输入栏 → 消息列表 → 引擎动作
   （`sendMessage`/`landAssistantReply`/`saveTree` 那一坨）。切之前先把它们依赖的 40 多个
   `remember` 收进 `ChatState`/`ChatActions`，否则只能"整块平移"。
3. **`DickTheme` 的层级**：它现在只包住抽屉，14 个 overlay 弹窗画在主题外层（拿到的是
   Material3 默认配色）。要么给弹窗全部显式传色，要么提上来并接受一次观感变更 —— 二选一。
4. **`<Feature>Actions` 收窄**：trpg/cardEdit/backup/library/common 六组仍拿整个 `DialogDeps`。
5. **`Routes` 常量还没被逻辑用到**：现在是"注册表 + 文档"，等做真正的路由（返回栈/深链）时接管。

### 每次搬完必须过的四关
```
cd DICK-Android; gradle :app:compileDebugKotlin --offline     # 编译
gradle :app:assembleDebug --offline                          # 装得起来
python -X utf8 tests/test_android_icons.py                   # 图标名都在字体里
python -X utf8 tests/test_android_parity.py                  # 生活/空间注入接线没断
python -X utf8 tests/test_android_lanes.py                   # 重活还在线上，没回主线程
python -X utf8 tests/test_android_settings_i18n.py           # 设置屏没有裸中文（漏译）
python -X utf8 tools/gen_i18n.py --check                     # 三语文案表一致
```
`test_android_parity.py` / `test_android_lanes.py` 已经从"只读 `App.kt`"改成
"`App.kt` + `ui/screens/chat/ChatScreen.kt` 拼起来看" —— 断言没删，只是跟着代码走。

### 2026-11 修的四个 UI bug（用户截图报的，唯一允许的观感改动）
| # | 现象 | 改法 | 文件 |
| --- | --- | --- | --- |
| A | 输入框里塞着"温度（留空=默认）"这类说明，值没地方写 | label 画到框**上方**、说明变成框下**灰色小字**；正则那格的长示例删掉 | `Fields.kt`（新增 `DickLabeledField`）`SettingsScreen.kt` |
| B | 同一屏一半日文一半中文 | 设置屏 37 处文案全走 `I18n.t(key, 中文原串)`，新增 55 个键（zh/en/ja），主题/强调色/预设的**名字**也走键 | `SettingsScreen.kt` `Theme.kt` `Models.kt` `lang/strings.json` |
| C | 同类操作一个实心一个描边，看不出主次 | 按钮收成三档语义（Primary/Secondary/Plain），"当前值"用 Primary、"进另一个面板"用 Secondary、"取消/±"用 Plain | `Buttons.kt` `SettingsScreen.kt` |
| D | 自己的气泡和页面底色几乎一样、署名悬空、编辑图标错位 | 用户气泡加 `palette.border` 描边；署名行高压到 14sp + 2dp 间距；动作条按语音侧对齐（自己的在右） | `Ui.kt`（`Bubble`） |

翻译键的安全网：`tests/test_android_settings_i18n.py` —— 设置屏里**裸中文字面量**（注释除外）
直接失败，同时校验用到的 key 三语齐全且声明了 `used_by=android`。加新屏就往 `FILES` 里加一行。
