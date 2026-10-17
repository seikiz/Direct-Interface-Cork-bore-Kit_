/* web/js/router.js —— 极薄：屏的注册 / 片段的**同步**注入 / 挂载分发。
 *
 * 为什么是同步 XHR（而不是 fetch / import / innerHTML 拼字符串）
 * --------------------------------------------------------------
 * 这页是 pywebview 用 file:// 打开的（Direct-Interface Cork-bore Kit.py 里 create_window 传的是
 * 本地路径），而 pywebview 默认给 WebView2 开了 `--allow-file-access-from-files`
 * （webview/__init__.py 的 ALLOW_FILE_URLS=True）—— 所以 file:// 页面能同步读到同目录的
 * `screens/*.html`；这跟 `<link rel="stylesheet">` 能读到 styles/*.css 是同一个前提。
 *
 * 同步的意义：页尾那段 7000 行的老脚本是在**解析时**就执行顶层语句的（`dialSave.onclick = …`
 * 之类），片段如果异步到位，那些 getElementById 会拿到 null、整段脚本直接崩。
 * 所以注入必须发生在老脚本之前 —— 用同步 XHR 拿到片段、innerHTML 进 <template>、再插进
 * 挂载点。观感上等价于"原本就写在 index.html 里"。
 *
 * 代价：一次本地文件同步读（这几屏合计十几 KB，几毫秒），以及控制台一条
 * "Synchronous XMLHttpRequest" 弃用警告。换来的是零时序风险，值得。
 *
 * 挂载点写法（index.html 里，原位保留）：
 * <!--@screen:go-->
 * 片段文件：web/screens/go.html（可以多根，按顺序插进挂载点后面）
 * 屏模块：web/js/screens/go.js，必须导出 mount()/unmount()
 *
 * 为什么样式表**不**由 router 动态插
 * ----------------------------------
 * `<link>` 的先后就是层叠顺序，`.modal-box .btn2` 和 `.ws-card .btn2` 特异性相同，谁在后面谁赢。
 * 少写一处动态插入、多写一行显式 `<link>` —— 顺序留在 index.html 的头部一眼能看完，比"运行时
 * 按注册顺序拼出来"可靠得多。所以屏的 css 该在 styles/ 里，`<link>` 由人写在 index.html。
 */
(function (global) {
  'use strict';

  var DICK = global.DICK || (global.DICK = {});
  if (DICK.router) {
    return;                       // 重复加载不重建注册表
  }

  var reg = {};                   // 名字 → { fragment, module }（注册顺序 = 注入/挂载顺序）
  var order = [];
  var injected = {};

  function register(name, def) {
    if (!name || !def || !def.fragment) {
      throw new Error('[router] register 需要 {fragment: "screens/xx.html"}');
    }
    if (!reg[name]) { order.push(name); }
    reg[name] = { fragment: def.fragment, module: def.module || null };
    return reg[name];
  }

  function _readFragment(url) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, false);          // 见文件头：必须同步
    xhr.send(null);
    // file:// 下成功时 status 是 200（WebView2 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌带 --allow-file-access-from-files），
    // 某些实现会给 0 —— 两个都当成功，真正的判据是拿没拿到内容。
    if ((xhr.status !== 200 && xhr.status !== 0) || !xhr.responseText) {
      throw new Error('读不到片段：' + url + '（status ' + xhr.status + '）');
    }
    return xhr.responseText;
  }

  function _findMarker(name) {
    var root = document.body || document.documentElement;
    if (!root || !document.createTreeWalker) { return null; }
    var want = '@screen:' + name;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_COMMENT, null, false);
    while (walker.nextNode()) {
      if (String(walker.currentNode.nodeValue).trim() === want) {
        return walker.currentNode;
      }
    }
    return null;
  }

  /* 把一个屏的片段插到它的挂载点后面。返回 true = 这次真的插了，false = 之前插过/没有挂载点。 */
  function inject(name) {
    var d = reg[name];
    if (!d) { throw new Error('[router] 没注册过的屏：' + name); }
    if (injected[name]) { return false; }
    var marker = _findMarker(name);
    if (!marker) {
      // 没有挂载点有两种情况：① 片段还内联在页面里（搬家过程中的过渡态，能跑就行）；
      // ② 名字写错了。两种都只警告不抛 —— 一屏坏了不该让整页打不开。
      if (global.console && console.warn) {
        console.warn('[router] 找不到挂载点 <!--@screen:' + name + '-->，跳过片段注入');
      }
      return false;
    }
    var tpl = document.createElement('template');
    tpl.innerHTML = _readFragment(d.fragment);   // <template> 解析无副作用：不执行脚本/不加载图片
    marker.parentNode.insertBefore(tpl.content, marker.nextSibling);
    injected[name] = true;
    return true;
  }

  function mount(name) {
    var d = reg[name];
    if (!d || !d.module) { return false; }
    var mod = d.module;
    if (mod.__mounted) { return false; }
    try {
      mod.mount();
      mod.__mounted = true;
      DICK.state && DICK.state.set('router.open', name);
      DICK.bus && DICK.bus.emit('screen:mounted', { name: name });
      return true;
    } catch (e) {
      if (global.console && console.error) {
        console.error('[router] 屏 ' + name + ' 挂载失败：', e);
      }
      return false;
    }
  }

  /* 逐个屏：先注入片段，再挂载模块。整批做完才算 boot 完。 */
  function boot(names) {
    var list = names && names.length ? names : order;
    var ok = 0;
    for (var i = 0; i < list.length; i++) {
      var name = list[i];
      try {
        inject(name);
      } catch (e) {
        if (global.console && console.error) {
          console.error('[router] 屏 ' + name + ' 片段注入失败：', e);
        }
      }
      if (mount(name)) { ok++; }
    }
    DICK.state && DICK.state.set('router.ready', true);
    return ok;
  }

  function unmount(name) {
    var d = reg[name];
    if (!d || !d.module || !d.module.__mounted) { return false; }
    try {
      if (d.module.unmount) { d.module.unmount(); }
    } finally {
      d.module.__mounted = false;
    }
    return true;
  }

  function names() {
    return order.slice();
  }

  DICK.router = {
    register: register,
    inject: inject,
    mount: mount,
    unmount: unmount,
    boot: boot,
    names: names
  };
})(window);
