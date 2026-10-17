/* web/js/screens/mem.js —— 记忆清晰度面板（阶段 3：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 这一屏是**纯读**的：拿到后端 memory_debug 的结果就画一张表，不改任何状态。
 * 谁打开它？外壳的机制条（renderTreePanel 里那个「 记忆」小按钮）在点击时调后端，
 * 拿到结果再调本屏。搬家前它是"用户点外壳的按钮 → 外壳的函数直接画另一个面板的 DOM"，
 * 现在两种叫法都能用：
 * · 老代码：memDebugDraw(res) —— 兼容入口，转调本模块（index.html 一行没改）
 * · 新代码：MemScreen.draw(res) —— 阶段 4 之后外壳改成 DICK.bus.emit('mem:draw', res)
 *
 * 归属
 * 结构：web/screens/mem.html（index.html 里原位只剩挂载点 <!--@screen:mem-->）
 * 样式：没有专属 css 块 —— 表格全是行内 style（本轮不做美化），所以不建 mem.css。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 * · evEsc() 事件编辑器那边的转义函数（名字起在 ev 上，其实是通用的）
 * · pywebview.api.memory_debug() 由调用方（外壳机制条）发，本屏只收结果
 */
window.MemScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 记<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌忆清晰度 =================
  // 遗忘被设计成不可建模的，所以不给你看内部数字的话，你判断不出它坏没坏。
  // 遗忘被设计成不可建模的，所以不给你看内部数字的话，你判断不出它坏没坏。
  function memDebugDraw(res) {
    var head = document.getElementById('memDebugHead');
    var list = document.getElementById('memDebugList');
    if (!res || !res.ok) {
      head.textContent = (res && res.err) || '读不到记忆状态。';
      list.innerHTML = '';
      document.getElementById('memDebugModal').classList.add('open');
      return;
    }
    var p = res.params || {};
    head.innerHTML = '历史共 <b>' + res.total + '</b> 条，还记得 <b>' + res.alive
      + '</b>，已忘 <b>' + res.forgotten + '</b>'
      + '<br>阈值 ' + res.threshold + '　近窗无条件保留 ' + (res.recent_window || 0) + ' 条'
      + '<br><span style="opacity:.75">衰减率范围 ' + (p.decay_min || 0) + '~' + (p.decay_max || 0)
      + '／天，其中 ' + Math.round((p.decay_portion || 0) * 100) + '% 的节点是"快忘"的'
      + ' —— 这就是"想不起来为什么忘了"的来源</span>';
    var h = '<table style="width:100%;border-collapse:collapse">'
      + '<tr style="color:var(--sub)"><th align="left">清晰度</th><th align="left">年龄</th>'
      + '<th align="left">衰减/天</th><th align="left">内容</th></tr>';
    (res.rows || []).forEach(function (r) {
      var dim = r.alive ? '' : 'opacity:.45;text-decoration:line-through;';
      h += '<tr style="' + dim + 'border-top:1px solid var(--line)">'
        + '<td style="padding:3px 6px">' + (r.alive ? '[ic:check_circle] ' : '[ic:bedtime] ') + r.salience + '</td>'
        + '<td style="padding:3px 6px;white-space:nowrap">'
        + (r.age_days < 1 ? (Math.round(r.age_days * 24) + '小时') : (r.age_days + '天')) + '</td>'
        + '<td style="padding:3px 6px">' + r.decay_per_day + '</td>'
        + '<td style="padding:3px 6px">' + evEsc(r.preview) + '</td></tr>';
    });
    h += '</table>';
    list.innerHTML = h;
    document.getElementById('memDebugModal').classList.add('open');
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('memDebugModal')) {
      console.error('[mem] 片段没注入（找不到 #memDebugModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    // 本屏没有按钮要绑：关闭按钮是行内 onclick，画表由调用方给数据
  }

  function unmount() {
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    draw: memDebugDraw
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前 memDebugDraw 是 index.html 的顶层全局函数，外壳的机制条直接把它当回调传给 .then()。
 * 同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function memDebugDraw(res) { return window.MemScreen.draw(res); }

// 注册到路由：片段 = screens/mem.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('mem', { fragment: 'screens/mem.html', module: window.MemScreen });
