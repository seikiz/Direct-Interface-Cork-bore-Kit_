/* web/js/store/codex.js —— 编年史（codex）的数据层：一组有名字的状态域 + 一个薄壳 API。
 *
 * 为什么单独抽出来（阶段 5 的第一步）
 * ---------------------------------
 * 编年史是"编辑器（codex*） + 播放器（cx*）"两块 UI 长在同一份数据上：
 * 编辑器写 codexCur/codexScript，播放器读它并维护 codexPlayer；两边原来靠 85 处
 * "你去 getElementById 我的 id / 我读你的顶层 var"串在一起，谁也搬不走。
 * 所以先只动**数据**：把这 8 个顶层 var 收进 DICK.state['codex.*']，再用本文件当唯一入口。
 * UI 仍然是原来那些函数（读写同名全局，靠 state.js 的兼容访问器转发），行为一个字没变 ——
 * 这一步的价值是"数据有了明确的家"，下一步才敢把 UI 分开搬。
 *
 * 数据模型（谁写谁读）
 * codexCur '包名' | null 编辑器：当前选中的包（列表高亮 + 播放器拿它去载入）
 * codexScript 剧本对象 | null 编辑器：正在编辑的 codex.json（保存前都是它）
 * codexPlayer 播放器运行时 | null 播放器：{scenes, idx, auto, audioBgm…}，退出时置 null
 * codexVolume 0-100 播放器：音量（设置项，写进后端）
 * codexTypeSpeed '' | 'fast' | 'slow' 播放器：打字机速度
 * codexExeTimer 定时器 id | null 打包 exe 的轮询（打包结束/失败要清掉）
 * _gScript 剧本对象 | null 节点图编辑器（gal 的画布版）正在编辑的同一份剧本
 * _gSel '场景 id' | null 节点图编辑器当前选中的场景
 *
 * 用法：`DICK.store.codex.get('codexCur')` / `.set('codexCur', name)` / `.reset()`
 * 也可以直接 `DICK.state.get('codex.codexCur')`；老代码继续用裸名字 codexCur（兼容访问器）。
 */
(function (global) {
  'use strict';

  var DICK = global.DICK || (global.DICK = {});
  var NS = 'codex.';

  /* 这些 bindGlobal 就是"把老名字接到状态域上"的那一步。
 * 为什么放在 store 里而不是 index.html：数据层只有一处注册，排查时不用满页找。
 * 顺序无所谓（都是 setter/getter 注册），但键名必须和 state.js 的 SCHEMA 一致。 */
DICK.state.bindGlobal('codexCur', 'codex.codexCur', null);          // 当前选中的包名
DICK.state.bindGlobal('codexScript', 'codex.codexScript', null);       // 当前剧本对象（编辑用）
DICK.state.bindGlobal('codexPlayer', 'codex.codexPlayer', null);       // 播放器运行时状态
DICK.state.bindGlobal('codexVolume', 'codex.codexVolume', 100);        // 播放器音量 0-100（多媒体权限）
DICK.state.bindGlobal('codexTypeSpeed', 'codex.codexTypeSpeed', '');      // 打字机速度：'' 自适应 | 'fast' 快 | 'slow' 慢（设置项）
DICK.state.bindGlobal('_gScript', 'codex._gScript', null);   // 当前正在编辑的剧本对象
DICK.state.bindGlobal('_gSel', 'codex._gSel', null);      // 当前选中场景 id
DICK.state.bindGlobal('codexExeTimer', 'codex.codexExeTimer', null);

  /* ---------------- 薄壳 API（给"新代码<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌"用；老代码用裸名字也行） ---------------- */
  function get(name, dflt) {
    return DICK.state.get(NS + name, dflt);
  }

  function set(name, value) {
    return DICK.state.set(NS + name, value);
  }

  /* 退出播放器/关编辑器时把"也许该忘掉"的运行时清回默认值。
 * 只做浅重置：包名与剧本不清（那是用户正在编辑的东西），清的是播放器态与定时器。 */
  function clearPlayer() {
    set('codexPlayer', null);
    if (get('codexExeTimer')) {
      try { clearInterval(get('codexExeTimer')); } catch (e) {}
      set('codexExeTimer', null);
    }
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
  DICK.store.codex = { ns: NS, get: get, set: set, clearPlayer: clearPlayer, keys: keys };
})(window);
