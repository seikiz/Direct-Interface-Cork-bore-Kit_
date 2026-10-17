/* web/js/screens/trpg.js —— 🎭 跑团状态条（阶段 3：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 这一屏只有一条横条 + 一个「退出跑团」按钮，但它是"跨屏通知"的最小样例：
 *   搬家前 —— loadStateFill() 每次拿到新状态就 `renderTrpgBar(s.trpg)` 直接点名另一屏的函数。
 *   搬家后 —— loadStateFill() 只 `DICK.bus.emit('trpg:state', s.trpg)`；本屏在 mount() 里订阅。
 *            外壳不知道谁会画这条状态条，本屏也不知道外壳什么时候刷新 —— 两边只认事件名。
 * （兼容入口 renderTrpgBar() 仍然在，老代码/插件叫它一样能画。）
 *
 * 归属
 *   结构：web/screens/trpg.html（index.html 里原位只剩挂载点 <!--@screen:trpg-->）
 *   样式：没有专属 css 块 —— 这条横条的样式全写在自己的行内 style 里，所以不建 trpg.css。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 *   · pywebview.api.trpg_end()   后端结束跑团会话
 *   · loadState()                退出之后整页状态重刷（外壳的）
 *   · escapeHtml()               组件层的转义
 */
window.TrpgScreen = (function (global) {
  'use strict';

  var mounted = false;
  var offBus = null;

  // ================= 🎭 跑<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌团状态条 =================
  // 数据全来自后端 state.trpg；这里只画，不存。
  // ---------- 跑团会话条（主动提示 + 一键退出） ----------
  function renderTrpgBar(trpg) {
    var bar = document.getElementById('trpgBar');
    if (!bar) return;
    if (!trpg) { bar.style.display = 'none'; bar.innerHTML = ''; return; }
    var head = '';
    if (trpg.active) {
      var pc = trpg.turn || (trpg.pcs && trpg.pcs[0]) || '';
      head = '🎭 跑团中 · GM「' + (trpg.gm || '?') + '」 · PC ' + (trpg.pcs || []).length + ' · 第' + (trpg.round || 0) + '轮' +
             (pc ? ' · 行动者：' + pc : '') +
             (trpg.locked && trpg.locked.length ? ' · 🔒已锁定 ' + trpg.locked.length + ' 卡' : '');
    } else if (trpg.locked && trpg.locked.length) {
      head = '⚠️ 有未结束的跑团锁定：' + trpg.locked.join('、') + '（会期未正常退出）';
    } else {
      bar.style.display = 'none'; bar.innerHTML = ''; return;
    }
    bar.style.display = 'flex';
    bar.innerHTML = '<span style="flex:1;min-width:0">' + escapeHtml(head) + '</span>' +
      '<button class="btn" style="width:auto;margin:0;padding:2px 10px;font-size:12px" id="trpgExitBtn">🏁 退出跑团</button>';
    var b = document.getElementById('trpgExitBtn');
    if (b) b.onclick = function () {
      pywebview.api.trpg_end().then(function (r) {
        loadState();
      }).catch(function (e) {});
    };
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('trpgBar')) {
      console.error('[trpg] 片段没注入（找不到 #trpgBar），这一屏跳过挂载');
      return;
    }
    mounted = true;
    // 外壳只发事件，不问"谁来画"
    offBus = DICK.bus.on('trpg:state', function (trpg) { renderTrpgBar(trpg); });
  }

  function unmount() {
    if (offBus) { offBus(); offBus = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    render: renderTrpgBar
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前 renderTrpgBar 是 index.html 的顶层全局函数，插件注入的脚本/老代码可能还在叫。
 * 同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function renderTrpgBar(trpg) { return window.TrpgScreen.render(trpg); }

// 注册到路由：片段 = screens/trpg.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('trpg', { fragment: 'screens/trpg.html', module: window.TrpgScreen });
