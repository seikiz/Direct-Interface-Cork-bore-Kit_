// 作用域图标替换（scoped icons）—— 数据是 web/ic<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ons.js 里的 window.DICK_ICONS_SCOPED，
// 唯一真相仍是 icons/icons.json 的 scoped 段（由 tools/gen_icons.py 生成，别手改产物）。
//
// 为什么要有这一层
// ----------------
// 全局表（DICK_ICONS）是「整个界面 + 正文」共用的：往里面加一个 emoji，卡片/世界卡正文里
// 同样的 emoji 也会被一起换成图标 —— 预览页那五个按钮想用字体图标，但绝不该动正文。
// 所以作用域映射单独一段，只在**标了 data-icon-scope 的根元素内部**生效：
//
//   <div class="bar" data-icon-scope="gothic"> … 这里的 emoji 按 gothic 那份映射换 … </div>
//
// 三条铁律（改这个文件前先读）：
//   1. 只在根内替换。根外一个文本节点都不碰 —— 聊天区、卡片正文、世界卡正文都在根外。
//   2. 只认作用域自己那份映射，**不回落**到全局表；作用域里没有的 emoji 原样留着。
//      否则「局部」就名不副实了（全局表里有的 emoji 还是会漏进来）。
//   3. .ic / svg / script / textarea / input / select / option / code / pre / [data-noicon]
//      一律不碰（与 index.html 的 _ICON_SKIP 同一口径）：往 svg <text> 里塞 <span> 直接渲染不出来。
(function () {
  'use strict';

  // 与 index.html 的 _EMOJI_CLS 同一口径：漏掉 2300-23FF（⏳⏸）与 2190-21FF（↪）时踩过坑。
  var EMOJI_CLS = '[\\u{1F000}-\\u{1FAFF}\\u{2600}-\\u{27BF}\\u{2B00}-\\u{2BFF}' +
                  '\\u{2300}-\\u{23FF}\\u{2190}-\\u{21FF}\\u{FE0F}\\u{200D}\\u{20E3}' +
                  '\\u{1F1E6}-\\u{1F1FF}]';
  var RUN = new RegExp('(' + EMOJI_CLS + '+)', 'gu');
  var ZIP = /\uFE0F/g;                      // emoji 变体选择符：键里不带它，替换时要吃掉
  var SKIP = '.ic, svg, script, style, textarea, input, select, option, code, pre, [data-noicon]';
  var SCOPE_ATTR = '[data-icon-scope]';

  // 允许两种调用姿势：给作用域名（去 DICK_ICONS_SCOPED 里取），或直接给一份映射表。
  function resolve(mapOrName) {
    if (!mapOrName) return null;
    if (typeof mapOrName === 'string') return (window.DICK_ICONS_SCOPED || {})[mapOrName] || null;
    return mapOrName;
  }

  function skippable(node, root) {
    var p = node.parentNode;
    if (!p || !p.closest) return true;
    if (p.closest(SKIP)) return true;
    // 嵌套作用域：内层的那块交给内层自己（按内层的映射），外层不许抢
    var owner = p.closest(SCOPE_ATTR);
    return !!owner && owner !== root;
  }

  function makeIcon(name) {
    var span = document.createElement('span');
    span.className = 'ms';
    span.textContent = name;                // 连字：文本就是图标名（字体 liga 生效）
    return span;
  }

  // 映射的值有两种写法：生成的产物是 { n: 名字, p: "" }（与全局表同形），手写可以只给字符串。
  function nameOf(v) {
    if (!v) return '';
    return typeof v === 'object' ? String(v.n || '') : String(v);
  }

  // 把一个文本节点里的 emoji 换成 <span class="ms">名字</span>；返回换了几个
  function replaceNode(textNode, map) {
    var s = textNode.data;
    if (!s) return 0;
    var hits = [], m;
    RUN.lastIndex = 0;
    while ((m = RUN.exec(s))) {
      var run = m[1], whole = run.replace(ZIP, ''), hit0 = nameOf(map[whole]);
      if (hit0) {                           // 整段命中（单个 emoji 或 ZWJ 组合）
        hits.push([m.index, m.index + run.length, hit0]);
        continue;
      }
      var cps = run.match(/./gu) || [], off = 0;   // 连续多个不同 emoji：逐个拆
      for (var i = 0; i < cps.length; i++) {
        var cp = cps[i], clean = cp.replace(ZIP, ''), at = m.index + off;
        off += cp.length;
        var one = clean ? nameOf(map[clean]) : '';
        if (one) hits.push([at, m.index + off, one]);
      }
    }
    if (!hits.length) return 0;
    var parent = textNode.parentNode;
    if (!parent) return 0;
    var at = 0;
    for (var h = 0; h < hits.length; h++) {
      if (hits[h][0] > at) parent.insertBefore(document.createTextNode(s.slice(at, hits[h][0])), textNode);
      parent.insertBefore(makeIcon(hits[h][2]), textNode);
      at = hits[h][1];
    }
    if (at < s.length) parent.insertBefore(document.createTextNode(s.slice(at)), textNode);
    parent.removeChild(textNode);
    return hits.length;
  }

  // 在一个根元素**内部**按作用域映射替换。root 不传就不动（宁可什么都不换，也不许全页扫）。
  function iconifyScoped(root, mapOrName) {
    var map = resolve(mapOrName);
    if (!root || !map || typeof document.createTreeWalker !== 'function') return 0;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return skippable(n, root) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    var count = 0;
    for (var i = 0; i < nodes.length; i++) count += replaceNode(nodes[i], map);
    return count;
  }

  // 扫 root 里所有 [data-icon-scope="名字"]，各按自己的映射替换一遍；返回总替换数
  function iconifyScopedAll(root) {
    root = root || document.body || document.documentElement;
    if (!root || !root.querySelectorAll) return 0;
    var owners = [], list = root.querySelectorAll(SCOPE_ATTR), i;
    if (root.matches && root.matches(SCOPE_ATTR)) owners.push(root);
    for (i = 0; i < list.length; i++) owners.push(list[i]);
    var total = 0;
    for (i = 0; i < owners.length; i++) {
      total += iconifyScoped(owners[i], owners[i].getAttribute('data-icon-scope'));
    }
    return total;
  }

  window.iconifyScoped = iconifyScoped;
  window.iconifyScopedAll = iconifyScopedAll;

  // 静态标记不用页面自己调：脚本在 </body> 前就直接跑，在 <head> 里就等 DOM 就绪。
  // （body 里静态写着 data-icon-scope 的页面，一行 JS 都不用加。）
  function boot() { iconifyScopedAll(document.body || document.documentElement); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
