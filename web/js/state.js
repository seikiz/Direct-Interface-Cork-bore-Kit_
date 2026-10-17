/* web/js/state.js —— 屏与屏之间唯一的通道：一堆"明确的状态域" + 一根极小的事件总线。
 *
 * 为什么要有它（而不是继续用裸全局）
 * ----------------------------------
 * 以前一屏要影响另一屏，只有两条路：拿对方的 DOM id 去 getElementById，或者改一个谁都能写的
 * 顶层 var。两种都没有"谁改的、什么时候改的"记录 —— 改坏了只能靠肉眼找。
 * 这里把这两条路收成一条：
 *   · DICK.state  只存**有名字的状态域**（键名登记在下面 SCHEMA 里，不许临时起名）；
 *                 set() 之后订阅者才知道值变了，屏自己决定要不要重画。
 *   · DICK.bus    只传"发生了一件事"（不存值），用于一次性的动作请求（比如"编辑这条消息"）。
 * 规矩：屏之间**不许**互相 getElementById，也不许互相调内部函数；要嘛 set 状态要嘛 emit 事件。
 *
 * 用法
 * ----
 *   DICK.state.set('editMsg.target', { seq: 3, kind: 'ai' });   // 写（值没变就不惊动任何人）
 *   var t = DICK.state.get('editMsg.target', null);             // 读（可以带默认值）
 *   var off = DICK.state.on('editMsg.target', fn);              // 订阅，返回退订函数
 *   DICK.state.bindGlobal('wsCurLocal', 'ws.curLocal', null);   // 阶段3：老名字 → 状态域（兼容入口）
 *   DICK.bus.emit('msg:edit', { seq: 3, kind: 'ai', text: '…' });   // 一次性动作
 *   DICK.bus.on('msg:edit', fn);
 *
 * 设计上的克制
 * ------------
 * · 只做浅比较：深比较会把"一次点击引发几万次属性遍历"这种坑带进来，而这里的值都很小；
 * · 订阅者抛异常不会连累别人（每个回调都 try 住，错误打到 console）；
 * · 不碰 DOM、不读 localStorage：这是状态层，渲染归屏。
 */
(function (global) {
  'use strict';

  var DICK = global.DICK || (global.DICK = {});
  if (DICK.state && DICK.bus) {
    return;                       // 重复加载（热重载/被引两次）不重建，免得丢订阅
  }

  /* 已登记的状态域（新加一条要写清"谁写谁读"，否则它就是下一个裸全局）
   *   editMsg.target  {seq, kind} | null   em 屏写/读（原来那个顶层 var editTarget）
   *   router.ready    true                  router 注入完片段后写（屏可以据此判断"能挂了吗"）
   *   router.open     'go' | …              router 记最后挂上的是哪一屏（排查用，不参与渲染）
   *
   * 阶段 3 收口的四个面板屏（键名 = 屏前缀.字段；都还是"本屏独占"的编辑态，
   * 跨屏只经 bus 通知，所以这里的域暂时只有各自的写在用）：
   *   ws.curLocal       {rtype, filename} | null   ws 写/读：「本地」页选中的那个文件
   *   ws.curOnline      作品对象 | null            ws 写/读：在线列表里选中的那个作品
   *   ws.onlineCache    [作品]                     ws 写/读：上次拉到的在线列表（渲染+选中都靠它）
   *   wm.entries        [条目]                     wm 写/读：编辑中的世界书条目（未落盘）
   *   wm.params         {key: 值}                  wm 写/读：编辑中的世界参数（未落盘）
   *   wm.editingWorld   '世界名' | null            wm 写/读：正在编辑哪个世界（null = 新建）
   *   save.current      '角色名' | null            save 写/读：多存档面板正在看哪个角色的存档
   *
   * 阶段 5 抽出的两个数据层（注册在 web/js/store/codex.js 与 store/gal.js，
   * 键名 codex.* / gal.*，语义见那两个文件头部 —— 这里只保证"有个明确的域"）：
   *   codex.cur / script / player / volume / typeSpeed / exeTimer / gScript / gSel
   *   gal.script / bodies / drag / keyOnly / dragNode / dragged / pan / scale / u / r /
   *   connecting / connTarget / raf / allOpen / assets */
  var SCHEMA = {
    'editMsg.target': null,
    'router.ready': false,
    'router.open': null,
    'ws.curLocal': null,
    'ws.curOnline': null,
    'ws.onlineCache': [],
    'wm.entries': [],
    'wm.params': {},
    'wm.editingWorld': null,
    'save.current': null,
    // ---- 阶段 5：编年史（codex）数据层 ----
    'codex.codexCur': null,
    'codex.codexScript': null,
    'codex.codexPlayer': null,
    'codex.codexVolume': 100,
    'codex.codexTypeSpeed': '',
    'codex.codexExeTimer': null,
    'codex._gScript': null,
    'codex._gSel': null,
    // ---- 阶段 5：GAL 制作器（gal）数据层 ----
    'gal.galScript': null,
    'gal.galBodies': {},
    'gal.galDrag': null,
    'gal.galKeyOnly': false,
    'gal.galDragNode': null,
    'gal.galDragged': false,
    'gal.galPan': null,
    'gal.galScale': 1,
    'gal.galU': [],
    'gal.galR': [],
    'gal.galConnecting': null,
    'gal.galConnTarget': null,
    'gal.galRAF': null,
    'gal.galAllOpen': {},
    'gal._galAssets': null
  };

  var store = {};
  for (var k in SCHEMA) {
    if (Object.prototype.hasOwnProperty.call(SCHEMA, k)) {
      store[k] = SCHEMA[k];
    }
  }
  var subs = {};                  // 键 → [回调]（'*' 是全量订阅）

  function _shallowSame(a, b) {
    if (a === b) { return true; }
    if (!a || !b || typeof a !== 'object' || typeof b !== 'object') { return false; }
    var ka = Object.keys(a);
    var kb = Object.keys(b);
    if (ka.length !== kb.length) { return false; }
    for (var i = 0; i < ka.length; i++) {
      if (a[ka[i]] !== b[ka[i]]) { return false; }
    }
    return true;
  }

  function _fire(key, value, old) {
    var lists = [subs[key], subs['*']];
    for (var n = 0; n < lists.length; n++) {
      var list = lists[n];
      if (!list) { continue; }
      for (var i = 0; i < list.length; i++) {
        try {
          list[i](value, old, key);
        } catch (e) {
          // 一个订阅者炸了不该让"改状态"这<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌个动作失败：打日志，继续通知别人
          if (global.console && console.error) {
            console.error('[state] 订阅者出错（' + key + '）：', e);
          }
        }
      }
    }
  }

  function get(key, dflt) {
    return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : dflt;
  }

  function set(key, value) {
    var old = store[key];
    if (_shallowSame(old, value)) {
      return value;               // 值没变：不写、不通知（否则订阅者会被无意义地刷）
    }
    store[key] = value;
    _fire(key, value, old);
    return value;
  }

  function on(key, fn) {
    if (typeof fn !== 'function') { return function () {}; }
    (subs[key] || (subs[key] = [])).push(fn);
    return function off() {
      var list = subs[key];
      if (!list) { return; }
      var i = list.indexOf(fn);
      if (i >= 0) { list.splice(i, 1); }
    };
  }

  function keys() {
    return Object.keys(store);
  }

  /* ---- 阶段 3 兼容入口：把老的顶层变量名接到状态域上 ----
   *
   * 为什么要这么绕：搬家前那些名字是 `var wsCurLocal = null;` 这样的顶层 var，全仓库
   * 有几十处 `wsCurLocal = …` / `if (!wsCurLocal)` 的裸名字读写。搬一屏就把这些调用点
   * 全改一遍，风险和收益不成比例 —— 所以让**名字继续能用**，但值只存在 state 里：
   * 唯一的真身是 store[key]，window 上的同名属性只是通往它的一个访问器。
   *
   * 两个坑（都是真踩过的）：
   *   ① 先 defineProperty、后 `var` 声明 → TypeError：顶层 `var` 会在 window 上占一个
   *      **不可配置**的属性，访问器定义不上去。所以调用方必须先把 `var x = …` 删掉
   *      （本阶段就是删掉换成这一句）。
   *   ② 默认值必须是**同一份引用**：`[]` / `{}` 要在这里落进 store 一次，不能每次
   *      get 时现造一个新的 —— 否则 `wmEntries.push(...)` 推进一个临时数组，下一秒就没了。
   *
   * 阶段 4/5 把旧引用清完之后，这些 alias 连同这个函数一起删。
   */
  function bindGlobal(name, key, dflt) {
    if (!Object.prototype.hasOwnProperty.call(store, key)) {
      store[key] = dflt;
    }
    try {
      Object.defineProperty(global, name, {
        configurable: true,
        enumerable: false,      // 别把 for (k in window) 的结果搞脏
        get: function () { return store[key]; },
        set: function (v) { set(key, v); }
      });
      return true;
    } catch (e) {
      // 注册不了就说清楚（多半是还有个 `var name` 没删），但别让整页起不来
      if (global.console && console.error) {
        console.error('[state] 兼容入口 ' + name + ' 注册失败（还留着 var 声明？）：', e);
      }
      return false;
    }
  }

  /* ---- 事件总线：只传"发生了什么事"，不存值 ---- */
  var handlers = {};

  function busOn(name, fn) {
    if (typeof fn !== 'function') { return function () {}; }
    (handlers[name] || (handlers[name] = [])).push(fn);
    return function off() {
      var list = handlers[name];
      if (!list) { return; }
      var i = list.indexOf(fn);
      if (i >= 0) { list.splice(i, 1); }
    };
  }

  function busEmit(name, payload) {
    var list = handlers[name];
    if (!list || !list.length) { return 0; }
    var copy = list.slice();      // 回调里退订不能影响这一轮派发
    for (var i = 0; i < copy.length; i++) {
      try {
        copy[i](payload);
      } catch (e) {
        if (global.console && console.error) {
          console.error('[bus] 订阅者出错（' + name + '）：', e);
        }
      }
    }
    return copy.length;
  }

  DICK.state = { get: get, set: set, on: on, keys: keys, schema: SCHEMA,
                 bindGlobal: bindGlobal };
  DICK.bus = { on: busOn, emit: busEmit };
})(window);
