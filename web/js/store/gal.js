/* web/js/store/gal.js —— 🎬 GAL 制作器（gal）的数据层：画布/拖拽/撤销栈的家。
 *
 * 为什么单独抽出来（阶段 5 的第一步）
 * ---------------------------------
 * GAL 制作器是全项目最"有状态"的一屏：一份剧本 + 一堆**只在拖动期间有意义**的临时态
 * （正在拖哪个节点、临时连线、平移量、缩放、撤销/重做栈）。这些原来都是顶层 var，
 * 画布上的每个 mousemove 都在写它们 —— 谁都能改，出问题只能靠肉眼。
 * 本文件把它们收进 DICK.state['gal.*']：数据有了明确的家，UI 才谈得上搬走。
 * 注意：**坐标计算与事件绑定本轮一行没动**（阶段 5 只抽数据层，见 web/UI_ARCHITECTURE.md）。
 *
 * 数据模型（谁写谁读）
 *   galScript      剧本对象 | null      制作器：正在编辑的剧本（保存前都在内存里）
 *   galBodies      {sceneId: el}       制作器：每条线的 body 容器（拖点重排用，DOM 引用）
 *   galDrag        {scene, idx} | null  正在拖的"点"
 *   galKeyOnly     false               仅看关键节点（骨架视图）
 *   galDragNode    {id,sx,sy,bx,by,g} | null  正在拖的节点（画布版）
 *   galDragged     false               刚拖过 → 抑制拖动结束后的点击开面板
 *   galPan         {sx,sy,sl,st} | null 画布平移
 *   galScale       1                   画布缩放（0.2 ~ 3）
 *   galU / galR    [json]              撤销 / 重做栈（最多 100 步）
 *   galConnecting  {srcId,x0,y0,line,svg} | null  正在连线
 *   galConnTarget  '场景 id' | null    拖拽时悬停的目标
 *   galRAF         定时器 id | null    requestAnimationFrame 句柄
 *   galAllOpen     {sceneId: bool}     每条线是否整条展开
 *   _galAssets     {bgm,bg,sfx…} | null  素材清单缓存
 *
 * 用法：`DICK.store.gal.get('galScale')` / `.set('galScale', 1.2)` / `.resetView()`
 * 老代码继续用裸名字 galScale / galPan / …（state.js 的兼容访问器转发）。
 */
(function (global) {
  'use strict';

  var DICK = global.DICK || (global.DICK = {});
  var NS = 'gal.';

DICK.state.bindGlobal('galScript', 'gal.galScript', null);          // 当前编辑剧本
DICK.state.bindGlobal('galBodies', 'gal.galBodies', {});            // sceneId -> body 容器（拖点重排用）
DICK.state.bindGlobal('galDrag', 'gal.galDrag', null);            // 拖拽中的 {scene, idx}
DICK.state.bindGlobal('galKeyOnly', 'gal.galKeyOnly', false);        // 仅看关键节点(骨架)
DICK.state.bindGlobal('galDragNode', 'gal.galDragNode', null);        // 拖动节点 {id, sx, sy, bx, by, g}
DICK.state.bindGlobal('galDragged', 'gal.galDragged', false);        // 刚拖过(抑制拖动后的点击开面板)
DICK.state.bindGlobal('galPan', 'gal.galPan', null);             // 平移 {sx, sy, sl, st}
DICK.state.bindGlobal('galScale', 'gal.galScale', 1);              // 画布缩放
DICK.state.bindGlobal('galU', 'gal.galU', []);      // 撤销栈
DICK.state.bindGlobal('galR', 'gal.galR', []);      // 重做栈
DICK.state.bindGlobal('galConnecting', 'gal.galConnecting', null);      // 连线中 {srcId, x0, y0, line, svg}
DICK.state.bindGlobal('galConnTarget', 'gal.galConnTarget', null);      // 拖拽时悬停的目标场景 id
DICK.state.bindGlobal('galRAF', 'gal.galRAF', null);
DICK.state.bindGlobal('galAllOpen', 'gal.galAllOpen', {});           // sceneId -> 是否整条展开
DICK.state.bindGlobal('_galAssets', 'gal._galAssets', null);

  /* ---------------- 薄壳 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌API ---------------- */
  function get(name, dflt) {
    return DICK.state.get(NS + name, dflt);
  }

  function set(name, value) {
    return DICK.state.set(NS + name, value);
  }

  /* 关掉编辑器/换包时把"视图态"复位（不动剧本本身：那是用户的数据）。 */
  function resetView() {
    set('galScale', 1);
    set('galPan', null);
    set('galDrag', null);
    set('galDragNode', null);
    set('galConnecting', null);
    set('galConnTarget', null);
    set('galKeyOnly', false);
    set('galU', []);
    set('galR', []);
    set('galBodies', {});
  }

  /* 素材缓存：只有"重新读目录"时才该失效 */
  function clearAssets() {
    set('_galAssets', null);
  }

  function keys() {
    var out = [];
    var all = DICK.state.keys();
    for (var i = 0; i < all.length; i++) {
      if (all[i].indexOf(NS) === 0) { out.push(all[i].slice(NS.length)); }
    }
    return out;
  }

  DICK.store = DICK.store || {};
  DICK.store.gal = { ns: NS, get: get, set: set, resetView: resetView,
                     clearAssets: clearAssets, keys: keys };
})(window);
