/* web/js/screens/wm.js —— 世界书条目（世界卡的编辑窗；阶段 3 从 index.html 整块搬出，零行为变化）
 *
 * 这一屏原来是"三个入口各摸一遍它的 DOM"：
 * · 侧栏「 新建世界」按钮 → 清表 + 开窗
 * · 世界卡列表里点 （data-wedit）→ 取后端数据 + 填表 + 开窗
 * · 弹窗自己的 保存/取消/AI起草/加条目/删条目
 * 搬家后前两个入口只叫一句 WmScreen.openNew() / WmScreen.openEdit(name)，
 * 弹窗内部的 DOM 不再被别处按 id 摸（index.html 里已经没有一行 wm* 的 getElementById）。
 *
 * 状态（阶段 3 收口）
 * editingWorld → DICK.state['wm.editingWorld']（null = 新建）
 * wmParams → DICK.state['wm.params']
 * wmEntries → DICK.state['wm.entries']
 * 三个同名全局是兼容访问器（state.js 的 bindGlobal），所以本文件里的读写一个字都没改。
 *
 * 归属
 * 结构：web/screens/wm.html（index.html 里原位只剩挂载点 <!--@screen:wm-->）
 * 样式：web/styles/screens/wm.css —— 原 styles/panels.css 的 .wentry（世界书条目卡片）
 * 与 .p-grid/.pcell（8 格世界参数网格）原样搬出去，<link> 排在 panels.css 之后。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 * · pywebview.api.get_world / create_world / update_world / ai_draft
 * · reloadWorlds() 保存成功后刷侧栏世界卡列表（外壳的函数，直接调用）
 * · lastUserText 取世界数据时带上"上次说的话"（外壳的），做上下文相关的世界记忆
 * · escapeHtml() 组件层转义
 * · #btnNewWorld 入口按钮在外壳侧栏（本屏 mount 时绑）
 * · #worldList 入口列表在外壳侧栏（点击分流仍写在 index.html，只调 openEdit）
 */
window.WmScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 世<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌界卡撰写 =================
  // 两个编辑态 + 世界参数的键表（键 = 后端 world.params 的字段名，别改）
  // 世界书条目数组的真身：DICK.state['wm.entries']（window.wmEntries 是兼容访问器）
  DICK.state.bindGlobal('wmEntries', 'wm.entries', []);
  DICK.state.bindGlobal('editingWorld', 'wm.editingWorld', null);
  DICK.state.bindGlobal('wmParams', 'wm.params', {});

  var PARAM_KEYS = ['tech_level', 'supernatural', 'physics', 'time_flow', 'climate', 'geography', 'politics', 'economy'];
  var PARAM_LABELS = {
    tech_level: '科技水平', supernatural: '超自然体系', physics: '物理法则', time_flow: '时间流速',
    climate: '气候环境', geography: '地理格局', politics: '政治格局', economy: '经济体系',
  };

  /* 8 格世界参数（科技水平/超自然体系/…）的渲染与收集 */
  function renderWmParams() {
    var box = document.getElementById('wmParamsList');
    if (!box) return;
    box.innerHTML = '';
    PARAM_KEYS.forEach(function (k) {
      var label = T['param_' + k] || PARAM_LABELS[k];
      var cell = document.createElement('div');
      cell.className = 'pcell';
      cell.innerHTML = '<span>' + escapeHtml(label) + '</span><input data-pk="' + k + '" value="' + escapeHtml((wmParams[k] || '').replace(/"/g, '&quot;')) + '">';
      box.appendChild(cell);
    });
  }

  function collectWmParams() {
    var out = {};
    PARAM_KEYS.forEach(function (k) {
      var inp = document.querySelector('#wmParamsList input[data-pk="' + k + '"]');
      var v = inp ? inp.value.trim() : '';
      if (v) out[k] = v;
    });
    return out;
  }

  /* ---------------- 入口：新建 / 编辑（都由外壳的侧栏按钮和列表点进来） ---------------- */
  function bindNewWorld() {
    document.getElementById('btnNewWorld').onclick = function () {
      editingWorld = null;
      document.getElementById('wmTitle').textContent = '新建世界';
      document.getElementById('wmNameInput').value = '';
      document.getElementById('wmDescInput').value = '';
      document.getElementById('wmRulesInput').value = '';
      wmEntries = [];
      renderWmEntries();
      wmParams = {};
      renderWmParams();
      document.getElementById('worldModal').classList.add('open');
    };
  }

  /* 世界卡列表里点 [ic:edit]：取后端数据 → 填表 → 开窗（原来写在世界卡列表的点击处理器里） */
  function openEdit(en) {
        editingWorld = en;
        pywebview.api.get_world(en, lastUserText).then(function (w) {
          document.getElementById('wmNameInput').value = en;
          document.getElementById('wmDescInput').value = w ? (w.description || '') : '';
          document.getElementById('wmRulesInput').value = w ? (w.rules || []).join('\n') : '';
          wmEntries = (w && w.entries) ? w.entries.map(function (e) {
            return { keywords: e.keywords || [], content: e.content || '', match: e.match || 'any',
                     weight: e.weight || 100, probability: e.probability === undefined ? 100 : e.probability,
                     depth: e.depth || 1, enabled: e.enabled !== false, constant: !!e.constant,
                     triggered: !!e.triggered };
          }) : [];
          renderWmEntries();
          wmParams = (w && w.params) ? w.params : {};
          renderWmParams();
          document.getElementById('wmTitle').textContent = '编辑世界：' + en;
          document.getElementById('worldModal').classList.add('open');
        });
  }

  /* ---------------- 世界书条目列表（关键词触发的小卡片） ---------------- */
  function attrEscape(s) {
    return escapeHtml(s).replace(/"/g, '&quot;');
  }
  function entryHtml(e, idx) {
    var dot = '<span class="we-dot' + (e.constant ? ' const' : (e.triggered ? ' on' : '')) + '"></span>';
    var kw = (e.keywords || []).join(', ');
    var mSel = '';
    ['any', 'all', 'regex'].forEach(function (m) {
      mSel += '<option value="' + m + '"' + ((e.match || 'any') === m ? ' selected' : '') + '>' + m + '</option>';
    });
    return '<div class="wentry" data-widx="' + idx + '">' +
      '<div class="we-row">' + dot +
      '<span class="we-chk"><input type="checkbox" data-f="enabled"' + (e.enabled !== false ? ' checked' : '') + '> ' + T.weEnabled + '</span>' +
      '<span class="we-chk"><input type="checkbox" data-f="constant"' + (e.constant ? ' checked' : '') + '> ' + T.weConst + '</span>' +
      '<span style="flex:1"></span>' +
      '<button class="we-del" data-delentry="' + idx + '">[ic:close]</button></div>' +
      '<div class="we-row"><input type="text" data-f="keywords" placeholder="' + T.weKeywords + '" value="' + attrEscape(kw) + '"></div>' +
      '<div class="we-row"><select data-f="match">' + mSel + '</select>' +
      '<input type="number" class="narrow" data-f="weight" min="0" max="999" value="' + (e.weight || 100) + '" title="' + T.weWeight + '">' +
      '<input type="number" class="narrow" data-f="probability" min="0" max="100" value="' + (e.probability === undefined ? 100 : e.probability) + '" title="' + T.weProb + '">' +
      '<input type="number" class="narrow" data-f="depth" min="1" max="4" value="' + (e.depth || 1) + '" title="' + T.weDepth + '"></div>' +
      '<textarea data-f="content" rows="2" placeholder="' + T.weContent + '">' + escapeHtml(e.content || '') + '</textarea></div>';
  }
  function renderWmEntries() {
    document.getElementById('wmEntriesList').innerHTML = wmEntries.map(function (e, i) { return entryHtml(e, i); }).join('');
  }
  function collectWmEntries() {
    var list = [];
    Array.prototype.slice.call(document.querySelectorAll('#wmEntriesList .wentry')).forEach(function (el) {
      var e = {};
      el.querySelectorAll('[data-f]').forEach(function (inp) {
        var f = inp.getAttribute('data-f');
        if (f === 'enabled' || f === 'constant') e[f] = inp.checked;
        else if (f === 'keywords') e[f] = inp.value.split(',').map(function (x) { return x.trim(); }).filter(Boolean);
        else if (f === 'weight' || f === 'probability' || f === 'depth') e[f] = parseFloat(inp.value) || 0;
        else e[f] = inp.value;
      });
      if ((e.content || '').trim()) list.push(e);
    });
    return list;
  }

  /* ---------------- 条目列表的两个交互：加一条 / 删一条 ---------------- */
  function bindEntryList() {
    document.getElementById('wmAddEntry').onclick = function () {
      wmEntries.push({ keywords: [], content: '', match: 'any', weight: 100, probability: 100, depth: 1, enabled: true, constant: false, triggered: false });
      renderWmEntries();
    };
    document.getElementById('wmEntriesList').addEventListener('click', function (e) {
      var el = e.target.closest ? e.target.closest('[data-delentry]') : null;
      var d = el ? el.getAttribute('data-delentry') : null;
      if (d !== null) { wmEntries.splice(parseInt(d, 10), 1); renderWmEntries(); }
    });
  }

  /* ---------------- 弹窗底部：取消 / 保存 / AI 起草 ---------------- */
  function bindModalButtons() {
    document.getElementById('wmCancel').onclick = function () {
      document.getElementById('worldModal').classList.remove('open');
      editingWorld = null;
    };
    document.getElementById('wmSave').onclick = function () {
      var n = document.getElementById('wmNameInput').value.trim();
      var d = document.getElementById('wmDescInput').value.trim();
      var r = document.getElementById('wmRulesInput').value.trim();
      if (!n || !d) return;
      var entriesJson = JSON.stringify(collectWmEntries());
      var paramsJson = JSON.stringify(collectWmParams());
      var fn = editingWorld ? pywebview.api.update_world(editingWorld, d, r, entriesJson, paramsJson) : pywebview.api.create_world(n, d, r, entriesJson, paramsJson);
      fn.then(function (res) {
        if (res && res.ok) {
          document.getElementById('worldModal').classList.remove('open');
          editingWorld = null;
          reloadWorlds();
        }
      });
    };
    document.getElementById('wmDraft').onclick = function () {
      var idea = document.getElementById('wmDescInput').value.trim() || document.getElementById('wmNameInput').value.trim();
      if (!idea) { document.getElementById('wmDescInput').focus(); return; }
      pywebview.api.ai_draft('world', idea).then(function (r) {
        if (r && r.ok && r.data) {
          document.getElementById('wmNameInput').value = r.data.name || '';
          document.getElementById('wmDescInput').value = r.data.description || '';
          document.getElementById('wmRulesInput').value = (r.data.rules || []).join('\n');
          if (r.data.params) {
            wmParams = r.data.params;
            renderWmParams();
          }
        } else {
          alert((r && r.err) || 'AI 起草失败');
        }
      });
    };
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('worldModal')) {
      console.error('[wm] 片段没注入（找不到 #worldModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    bindNewWorld();
    bindEntryList();
    bindModalButtons();
  }

  function unmount() {
    var b = document.getElementById('btnNewWorld');
    if (b) { b.onclick = null; }
    var el = document.getElementById('wmAddEntry');
    if (el) { el.onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    openEdit: openEdit,
    renderParams: renderWmParams, collectParams: collectWmParams,
    renderEntries: renderWmEntries, collectEntries: collectWmEntries,
    entryHtml: entryHtml
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前这 5 个都是 index.html 的顶层全局函数。外部还在叫的只有一个：
 * · renderWmParams() —— setT() 换语言时会重画参数标签（index.html 里还有调用点）
 * 其余 4 个只在模块内部用。同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function renderWmParams() { return window.WmScreen.renderParams(); }
function collectWmParams() { return window.WmScreen.collectParams(); }
function renderWmEntries() { return window.WmScreen.renderEntries(); }
function collectWmEntries() { return window.WmScreen.collectEntries(); }

// 注册到路由：片段 = screens/wm.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('wm', { fragment: 'screens/wm.html', module: window.WmScreen });
