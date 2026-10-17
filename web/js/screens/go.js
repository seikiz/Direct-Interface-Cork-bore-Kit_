/* web/js/screens/go.js —— 🎴 围棋屏（阶段 2：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 归属
 *   结构：web/screens/go.html（index.html 里原位只剩挂载点 <!--@screen:go-->）
 *   样式：这屏没有专属 css 块 —— 布局全是行内 style，棋盘是 SVG 属性 + goPaint() 画出来的，
 *         所以 web/styles/screens/go.css 不存在，也不需要（新增一条规则时再建）。
 * 契约（见 web/UI_ARCHITECTURE.md）：router 注入片段后调 mount()；unmount() 收掉轮询定时器。
 * 本屏依赖的外部符号（搬的时候刻意原样留着，属于阶段 3/4/5 的收尾清单）
 *   · pywebview.api.go_*   规则引擎在 go_engine.py，这里只画棋盘/转坐标/轮询
 *   · galToast()           提示条（它其实是外壳级 toast，只是名字挂在 GAL 那边）
 *   · escapeHtml()         组件层的转义
 *   · #btnGo               入口按钮在外壳侧栏里 —— 本屏唯一一处碰别人 DOM 的地方，
 *                          阶段 3 应该换成 DICK.bus.emit('go:open') 由外壳转发。
 */
window.GoScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 🎴 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌围棋 =================
  // 规则全在 go_engine.py；这里只负责画棋盘、把点击转成坐标、轮询等角色落子。
  var goState = null, goTimer = null, goSize = 19, goHuman = 'black';

  function goEl(id) { return document.getElementById(id); }

  function goOpen() {
    goEl('goPanel').style.display = 'flex';
    pywebview.api.go_state().then(function (r) {
      if (!r || !r.ok) { goNew(goSize, goHuman); return; }
      goState = r.state; goSize = r.state.size; goHuman = r.human || 'black';
      goPaint(r);
    }).catch(function () { goNew(goSize, goHuman); });
    if (goTimer) clearInterval(goTimer);
    goTimer = setInterval(function () {
      if (goEl('goPanel').style.display === 'none') return;
      pywebview.api.go_state().then(function (r) {
        if (r && r.ok) { goState = r.state; goPaint(r); }
      }).catch(function () {});
    }, 1500);
  }
  function goClose() {
    goEl('goPanel').style.display = 'none';
    if (goTimer) { clearInterval(goTimer); goTimer = null; }
  }
  function goNew(size, human) {
    pywebview.api.go_new(size, human).then(function (r) {
      if (r && r.ok) { goState = r.state; goSize = r.state.size; goHuman = r.human || 'black'; goPaint(r); }
      else galToast('❌ ' + ((r && r.err) || '开不了局'));
    }).catch(function (e) { galToast('❌ ' + ((e && e.message) || '开不了局')); });
  }
  function goPlay(x, y) {
    if (!goState || goState.finished) return;
    var mine = (goHuman === 'black' ? 1 : 2);
    if ((goState.to_move === 'black' ? 1 : 2) !== mine) { galToast('等对方落子…'); return; }
    if (goState.grid[y][x]) { galToast('这里有子了'); return; }
    pywebview.api.go_play(x, y).then(function (r) {
      if (!r || !r.ok) { galToast('❌ ' + ((r && r.err) || '下不了')); return; }
      goState = r.state; goPaint({ state: r.state, log: r.log });
    }).catch(function (e) { galToast('❌ ' + ((e && e.message) || '下不了')); });
  }
  function goAct(api, label) {
    pywebview.api[api]().then(function (r) {
      if (!r || !r.ok) { galToast('❌ ' + ((r && r.err) || (label + '失败'))); return; }
      if (r.state) { goState = r.state; goPaint(r); }
      if (r.score) {
        var s = r.score;
        alert('黑 ' + s.black + ' 目　白 ' + s.white + ' + 贴目 ' + s.komi +
              ' = ' + s.white_total.toFixed(1) + '\n\n' + s.winner +
              '\n（提子：黑 ' + s.captured.black + ' / 白 ' + s.captured.white + '）');
      }
    }).catch(function (e) { galToast('❌ ' + ((e && e.message) || (label + '失败'))); });
  }
  function goPaint(r) {
    var st = (r && r.state) || goState;
    if (!st) return;
    var svg = goEl('goSvg');
    var n = st.size, pad = 30, span = 600 - pad * 2, step = span / (n - 1);
    var COLS = 'ABCDEFGHJKLMNOPQRST';
    var p = ['<rect x="0" y="0" width="600" height="600" rx="6" fill="#241d15"/>'];
    for (var i = 0; i < n; i++) {
      var q = pad + i * step;
      p.push('<line x1="' + pad + '" y1="' + q + '" x2="' + (600 - pad) + '" y2="' + q + '" stroke="rgba(214,182,130,.45)" stroke-width="1"/>');
      p.push('<line x1="' + q + '" y1="' + pad + '" x2="' + q + '" y2="' + (600 - pad) + '" stroke="rgba(214,182,130,.45)" stroke-width="1"/>');
    }
    var stars = n === 19 ? [3, 9, 15] : (n === 13 ? [3, 6, 9] : [2, 4, 6]);
    stars.forEach(function (a) {
      stars.forEach(function (b) {
        p.push('<circle cx="' + (pad + a * step) + '" cy="' + (pad + b * step) + '" r="3.4" fill="rgba(214,182,130,.8)"/>');
      });
    });
    for (var k = 0; k < n; k++) {
      p.push('<text x="' + (pad + k * step) + '" y="15" fill="rgba(214,182,130,.55)" font-size="12" text-anchor="middle">' + COLS[k] + '</text>');
      p.push('<text x="13" y="' + (pad + k * step + 4) + '" fill="rgba(214,182,130,.55)" font-size="12" text-anchor="middle">' + (n - k) + '</text>');
    }
    for (var y = 0; y < n; y++) {
      for (var x = 0; x < n; x++) {
        var v = st.grid[y][x];
        if (!v) continue;
        var cx = pad + x * step, cy = pad + y * step, black = (v === 1);
        p.push('<circle cx="' + cx + '" cy="' + cy + '" r="' + (step * 0.46).toFixed(2) + '" fill="' +
               (black ? '#111114' : '#ecebe8') + '" stroke="' + (black ? '#000' : '#8f8b84') + '" stroke-width="1.2"/>');
      }
    }
    if (st.last_move) {
      p.push('<circle cx="' + (pad + st.last_move[0] * step) + '" cy="' + (pad + st.last_move[1] * step) +
             '" r="' + (step * 0.17).toFixed(2) + '" fill="#e5484d"/>');
    }
    p.push('<g id="goHit"></g>');
    svg.innerHTML = p.join('');

    var mine = (goHuman === 'black' ? 1 : 2);
    var myTurn = !st.finished && ((st.to_move === 'black' ? 1 : 2) === mine);
    var hit = [];
    if (myTurn) {
      for (var y2 = 0; y2 < n; y2++) {
        for (var x2 = 0; x2 < n; x2++) {
          if (st.grid[y2][x2]) continue;
          hit.push('<circle cx="' + (pad + x2 * step) + '" cy="' + (pad + y2 * step) + '" r="' +
                   (step * 0.48).toFixed(2) + '" fill="transparent" style="cursor:pointer" data-gx="' + x2 + '" data-gy="' + y2 + '"/>');
        }
      }
    }
    var hg = goEl('goHit');
    if (hg) {
      hg.innerHTML = hit.join('');
      Array.prototype.forEach.call(hg.querySelectorAll('[data-gx]'), function (el) {
        el.addEventListener('click', function () {
          goPlay(parseInt(el.getAttribute('data-gx'), 10), parseInt(el.getAttribute('data-gy'), 10));
        });
      });
    }
    var txt;
    if (st.finished) {
      txt = '🏁 ' + (st.result || '终局');
    } else {
      var who = (st.to_move === 'black' ? '⚫ 黑方' : '⚪ 白方');
      txt = who + '走' + (myTurn ? '（你）' : '（对方思考中…）') +
            ' · 第 ' + (st.moves + 1) + ' 手 · 提子 黑' + st.captured.black + ' / 白' + st.captured.white;
    }
    goEl('goStatus').textContent = txt;
    // 「她打算怎么跟你下」——好感度决定的让子/放水 + 棋风
    var gs = (r && r.settings) || null;
    var infoEl = goEl('goInfo');
    if (infoEl) {
      if (gs) {
        var deal = gs.handicap ? ('让你 ' + gs.handicap + ' 子')
                 : (gs.komi_extra ? ('多贴 ' + (gs.komi_extra).toFixed(1) + ' 目') : '分先');
        infoEl.textContent = '💗 好感度 ' + gs.aff + '　·　' + deal +
          '　·　棋风：' + String(gs.style_label || '均衡').split(' —— ')[0] +
          '　·　' + (gs.mood || '');
      } else {
        infoEl.textContent = '';
      }
    }
    var logs = (r && r.log) || [];
    goEl('goLog').innerHTML = logs.length
      ? logs.map(function (s) { return '<div>· ' + escapeHtml(String(s)) + '</div>'; }).join('')
      : '<div style="color:var(--sub,#8a93a3)">还没开始</div>';
  }
  function goBind() {
    goEl('btnGo').onclick = goOpen;
    goEl('goClose').onclick = goClose;
    goEl('goNew19').onclick = function () { goNew(19, goHuman); };
    goEl('goNew9').onclick = function () { goNew(9, goHuman); };
    goEl('goSwap').onclick = function () { goNew(goSize, goHuman === 'black' ? 'white' : 'black'); };
    goEl('goUndo').onclick = function () { goAct('go_undo', '悔棋'); };
    goEl('goPass').onclick = function () { goAct('go_pass', '停一手'); };
    goEl('goResume').onclick = function () { goAct('go_ai', '催一手'); };
    goEl('goScore').onclick = function () { goAct('go_score', '数目'); };
    goEl('goResign').onclick = function () { goAct('go_resign', '认输'); };
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    mounted = true;
    if (!document.getElementById('goPanel')) {
      console.error('[go] 片段没注入（找不到 #goPanel），这一屏跳过挂载');
      mounted = false;
      return;
    }
    goBind();
  }

  function unmount() {
    if (goTimer) { clearInterval(goTimer); goTimer = null; }
    goClose();
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    open: goOpen, close: goClose, newGame: goNew, play: goPlay, act: goAct,
    paint: goPaint, bind: goBind, el: goEl,
    state: function () { return goState; }
  };
})(window);

/* ===== 兼容入口（阶段 3/4/5 清理）=====
 * 搬家之前这些都是 index.html 里的顶层全局函数，别处（插件注入的 onclick、老脚本）可能还在叫。
 * 所以同名全局继续存在，内部只是转调模块 —— 函数本身不再有第二份实现。 */
function goEl(id) { return window.GoScreen.el(id); }
function goOpen() { return window.GoScreen.open(); }
function goClose() { return window.GoScreen.close(); }
function goNew(size, human) { return window.GoScreen.newGame(size, human); }
function goPlay(x, y) { return window.GoScreen.play(x, y); }
function goAct(api, label) { return window.GoScreen.act(api, label); }
function goPaint(r) { return window.GoScreen.paint(r); }
function goBind() { return window.GoScreen.bind(); }

// 注册到路由：片段 = screens/go.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('go', { fragment: 'screens/go.html', module: window.GoScreen });
