/* web/js/screens/dial.js —— 时间流速表盘屏（阶段 2：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 归属
 * 结构：web/screens/dial.html（index.html 里原位只剩挂载点 <!--@screen:dial-->）
 * 样式：没有专属 css 块 —— 表盘是 dialRender() 现画的 SVG，颜色全走 CSS 变量。
 * 契约：router 注入片段后调 mount()；mount() 只做一件事：绑「保存这个流速」按钮
 * （表盘本身是打开时 dialRender() 现生成的，静态 DOM 里只有一个空 #dialWrap）。
 * 本屏依赖的外部符号（阶段 3/4/5 的收尾清单）
 * · pywebview.api.get_time_scale() / set_time_scale(x)：后端在 time_scale.py，
 * 口径（对数刻度、一轮 30 秒）必须和 Python 侧一致，见 tests/test_web_dom.py ⑤。
 * · treeStatus()：保存成功后往**树状回溯面板**里打一行提示 —— 又一处跨屏调用，
 * 应该是 DICK.bus.emit('toast', …) 由外壳统一点；留在阶段 3 收。
 * · alert()：保存失败还是原生弹窗（原有行为，本轮不改交互）。
 */
window.DialScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ---------- 时间流<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌速表盘 ----------
  // 为什么是对数刻度：10 ~ 1000万 跨 6 个数量级，线性表盘 98% 的行程都挤在
  // 最前几档上，指针一动就是几百万倍，没法用。对数下每转一格 = ×10。
  // 弧线用单条 path，进度用 stroke-dasharray 画 —— 比 angle() 取整稳，
  // 也不会在两端出现毛刺。
  var TIME_DIAL = { presets: [], min: 10, max: 10000000, cur: 720, draft: 720, len: 0 };

  var DEG = Math.PI / 180.0;
  var A0 = -210 * DEG;
  var A1 = 30 * DEG;

  function dialXY(t, r, cx, cy) {
    var a = A0 + (A1 - A0) * t;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  }

  function dialPath(r, cx, cy) {
    var p0 = dialXY(0, r, cx, cy), p1 = dialXY(1, r, cx, cy);
    var d = A1 - A0;
    return 'M ' + p0[0].toFixed(2) + ' ' + p0[1].toFixed(2) +
           ' A ' + r + ' ' + r + ' 0 ' + (d > Math.PI ? 1 : 0) + ' 1 ' +
           p1[0].toFixed(2) + ' ' + p1[1].toFixed(2);
  }

  function dialPosOf(scale) {
    var lo = Math.log10(TIME_DIAL.min), hi = Math.log10(TIME_DIAL.max);
    if (hi <= lo) return 0;
    var v = Math.log10(Math.max(TIME_DIAL.min, Math.min(TIME_DIAL.max, scale)));
    return Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
  }

  function dialScaleOf(t) {
    var lo = Math.log10(TIME_DIAL.min), hi = Math.log10(TIME_DIAL.max);
    return Math.pow(10, lo + (hi - lo) * t);
  }

  function fmtScale(s) {
    if (s >= 1e6) return (s / 1e6).toFixed(s >= 1e7 ? 0 : 1) + 'M';
    if (s >= 1e4) return Math.round(s / 1e3) + 'K';
    return String(Math.round(s));
  }

  // 和服务端同一套口径：一轮 ≈ 现实 30 秒
  function perRoundText(s) {
    var sec = s * 30;
    if (sec < 60) return '一轮约 ' + Math.round(sec) + ' 秒';
    if (sec < 3600) return '一轮约 ' + Math.round(sec / 60) + ' 分钟';
    if (sec < 86400) return '一轮约 ' + (sec / 3600).toFixed(1) + ' 小时';
    var days = sec / 86400;
    if (days < 30) return '一轮约 ' + days.toFixed(1) + ' 天';
    var months = days / 30;
    if (months < 24) return '一轮约 ' + months.toFixed(1) + ' 个月';
    return '一轮约 ' + (months / 12).toFixed(1) + ' 年';
  }

  function dialRender() {
    var wrap = document.getElementById('dialWrap');
    if (!wrap) return;
    var W = 300, H = 216, cx = W / 2, cy = 118, R = 100;
    var t = dialPosOf(TIME_DIAL.draft);
    var main = dialPath(R, cx, cy);
    var n = dialXY(t, R, cx, cy);
    var s = '';
    s += '<svg id="dialSvg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '"'
       + ' style="touch-action:none;cursor:grab;user-select:none">';
    // 底弧 + 进度弧
    s += '<path d="' + main + '" fill="none" stroke="var(--line)" stroke-width="10" stroke-linecap="round"/>';
    s += '<path d="' + main + '" fill="none" stroke="var(--accent)" stroke-width="10" stroke-linecap="round"'
       + ' stroke-dasharray="' + TIME_DIAL.len + '" stroke-dashoffset="' + (TIME_DIAL.len * (1 - t)).toFixed(1) + '"/>';
    // 刻度
    TIME_DIAL.presets.forEach(function (p) {
      var pt = dialPosOf(p.scale);
      var a = dialXY(pt, R - 16, cx, cy), b = dialXY(pt, R + 9, cx, cy);
      s += '<line x1="' + a[0].toFixed(1) + '" y1="' + a[1].toFixed(1) + '" x2="' + b[0].toFixed(1)
         + '" y2="' + b[1].toFixed(1) + '" stroke="var(--sub)" stroke-width="1.5" opacity="0.75"/>';
    });
    // 指针
    s += '<line x1="' + cx + '" y1="' + cy + '" x2="' + n[0].toFixed(1) + '" y2="' + n[1].toFixed(1)
       + '" stroke="var(--text)" stroke-width="2.5" stroke-linecap="round"/>';
    s += '<circle cx="' + n[0].toFixed(1) + '" cy="' + n[1].toFixed(1) + '" r="6.5" fill="var(--accent)"/>';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="7" fill="var(--text)"/>';
    // 中央读数
    s += '<text x="' + cx + '" y="' + (cy + 34) + '" text-anchor="middle" font-size="21" font-weight="700"'
       + ' fill="var(--text)">' + fmtScale(TIME_DIAL.draft) + '×</text>';
    s += '<text x="' + cx + '" y="' + (cy + 54) + '" text-anchor="middle" font-size="12"'
       + ' fill="var(--sub)">' + perRoundText(TIME_DIAL.draft) + '</text>';
    s += '</svg>';
    wrap.innerHTML = s;
    dialBind(cx, cy, R);
    dialWarn();
  }

  function dialSetFromXY(clientX, clientY) {
    var svg = document.getElementById('dialSvg');
    if (!svg) return;
    var box = svg.getBoundingClientRect();
    var x = (clientX - box.left) * (300 / box.width) - 150;
    var y = (clientY - box.top) * (216 / box.height) - 118;
    var ang = Math.atan2(y, x);
    if (ang < A0) ang += 2 * Math.PI;          // 弧度制：A0 是负的
    var t = (ang - A0) / (A1 - A0);
    TIME_DIAL.draft = dialScaleOf(Math.max(0, Math.min(1, t)));
    dialRender();
  }

  function dialBind(cx, cy, R) {
    var svg = document.getElementById('dialSvg');
    if (!svg) return;
    var dragging = false;
    svg.addEventListener('pointerdown', function (e) {
      dragging = true;
      try { svg.setPointerCapture(e.pointerId); } catch (err) {}
      svg.style.cursor = 'grabbing';
      dialSetFromXY(e.clientX, e.clientY);
      e.preventDefault();
    });
    svg.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      dialSetFromXY(e.clientX, e.clientY);
      e.preventDefault();
    });
    var stop = function () { dragging = false; if (svg) svg.style.cursor = 'grab'; };
    svg.addEventListener('pointerup', stop);
    svg.addEventListener('pointercancel', stop);
    svg.addEventListener('lostpointercapture', stop);
  }

  function dialWarn() {
    var el = document.getElementById('dialWarning');
    if (!el) return;
    var s = TIME_DIAL.draft;
    var readout = document.getElementById('dialReadout');
    var hit = null;
    TIME_DIAL.presets.forEach(function (p) {
      if (Math.abs(Math.log10(s) - Math.log10(p.scale)) < 0.02) hit = p;
    });
    if (readout) {
      readout.innerHTML = hit
        ? '<b>' + hit.name + '</b>'
        : '<span style="color:var(--sub)">' + perRoundText(s) + '（不在预设档上，也可用）</span>';
    }
    el.textContent = (s >= 3600)
      ? '[ic:warning] 高倍率下时间过得极快：现实几分钟就等于她那边好几天。适合"跳过一段时间"的玩法，'
        + '不适合慢慢聊。'
      : '低倍率更像实时聊天：现实里的间隔基本等于她那边的间隔。';
  }

  function timeDialOpen() {
    if (!window.pywebview || !pywebview.api || !pywebview.api.get_time_scale) return;
    pywebview.api.get_time_scale().then(function (r) {
      if (!r || !r.ok) {
        document.getElementById('dialWarning').textContent = (r && r.err) || '读不到时间设置。';
        document.getElementById('timeDialModal').classList.add('open');
        return;
      }
      TIME_DIAL.presets = r.presets || [];
      TIME_DIAL.min = r.min || 10;
      TIME_DIAL.max = r.max || 10000000;
      TIME_DIAL.cur = r.scale;
      TIME_DIAL.draft = r.scale;
      // 弧长：SVG 无路径测量时的可靠近似（半径 R 的圆弧）
      TIME_DIAL.len = Math.abs(A1 - A0) * 100;
      dialRender();
      document.getElementById('timeDialModal').classList.add('open');
    }).catch(function (e) {
      document.getElementById('dialWarning').textContent = '读时间设置出错：' + e;
      document.getElementById('timeDialModal').classList.add('open');
    });
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    mounted = true;
    if (!document.getElementById('timeDialModal')) {
      console.error('[dial] 片段没注入（找不到 #timeDialModal），这一屏跳过挂载');
      mounted = false;
      return;
    }
    document.getElementById('dialSave').onclick = function () {
      if (!window.pywebview || !pywebview.api || !pywebview.api.set_time_scale) return;
      pywebview.api.set_time_scale(TIME_DIAL.draft).then(function (r) {
        if (!r || !r.ok) { alert('保存失败：' + ((r && r.err) || '未知')); return; }
        TIME_DIAL.cur = r.scale;
        treeStatus('[ic:hourglass_empty] 时间流速已设为 ' + r.describe);
        document.getElementById('timeDialModal').classList.remove('open');
      });
    };
  }

  function unmount() {
    // 表盘没有定时器：拖动事件是挂在 dialRender() 现画的 #dialSvg 上的，重画时整块换掉即可。
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    open: timeDialOpen, render: dialRender, warn: dialWarn,
    state: function () { return TIME_DIAL; }
  };
})(window);

/* ===== 兼容入口（阶段 3/4/5 清理）=====
 * timeDialOpen 由聊天头部那个「 流速」小按钮（外壳侧栏生成的）直接调；
 * dialRender 是原来就有的全局名（tests/test_web_dom.py ③④ 也认它）。 */
function timeDialOpen() { return window.DialScreen.open(); }
function dialRender() { return window.DialScreen.render(); }

// 注册到路由：片段 = screens/dial.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('dial', { fragment: 'screens/dial.html', module: window.DialScreen });
