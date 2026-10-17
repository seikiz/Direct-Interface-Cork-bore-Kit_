/* web/js/screens/settings.js —— ⚙️ 设置屏（阶段 4：DOM 全搬出来，JS 先搬"自成一体"的那几段）
 *
 * 阶段 4 对设置屏做了两件事：
 *   ① 文案从"setT() 里逐个 getElementById 改名"改成元素上的 `data-i18n` 标注
 *      （见 index.html 的 applyI18n + web/UI_ARCHITECTURE.md）。所以本屏 label 一个都不用 JS 管。
 *   ② DOM 整块搬到 web/screens/settings.html；JS 里**自成一体**的那几段搬到这里：
 *      预算 / 自动接话 / 字体 / 插件管理（原 index.html 的"前版功能"段）。
 *
 * 为什么只搬这几段（诚实说明）
 *   设置屏的 JS 跟外壳缠得很深，硬拆会连带重写外壳：
 *     · loadStateFill()（94 行）一边填设置控件、一边刷聊天状态 —— 它是外壳的状态泵；
 *     · fillProvider / renderProviderSel / renderModelSel / closeOverlays 是"下拉浮层"组件，
 *       预设菜单也在用（同 .dd-overlay 结构），属于组件层不属于设置屏；
 *     · applyTheme / applyChatWallpaper 是观感层，聊天屏也在调。
 *   所以本轮搬的是"只服务设置屏、且没有外部调用者"的部分，其余留在 index.html，
 *   靠下面这些兼容入口互通 —— 这也正是阶段 5 之后要继续收的活。
 *
 * 归属
 *   结构：web/screens/settings.html（index.html 里原位只剩挂载点 <!--@screen:settings-->）
 *   样式：没有专属 css 块 —— 设置屏用的是组件层的 .modal/.modal-box/.field/.prow/.chipgrid，
 *         规则都在 styles/components.css 与 styles/panels.css 里，按"一屏不要自造样式"的规矩
 *         本轮不新建 settings.css。
 * 本屏依赖的外部符号
 *   · pywebview.api.set_budget / set_auto_turn / set_font / set_dev_mode / set_plugin / set_plugin_setting
 *   · setFinEnabled()      财报模式开关 → 快捷面板的财报折叠区（快捷面板那屏的）
 *   · #nrAdv              开发者模式开关要顺带改「新建角色」里那块高级区（角色屏的 DOM，跨屏摸了一把）
 *   · currentBudget / currentFont / BUDGETS / FONT_SIZES / FONT_LABELS
 *                         仍是 index.html 的顶层 var（loadStateFill 会写 currentBudget），
 *                         本轮不动它们，只把它们的使用者搬进来。
 */
window.SettingsScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= ⚙️ 预算 / <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌字体 / 插件管理 =================
  function budgetLabel(t) {
    return t === 0 ? T.budgetUnlimited : Math.round(t / 1024) + 'K';
  }

  function renderBudget() {
    document.getElementById('stBudgetBtn').textContent = T.stBudget.replace('🧮 ', '🧮 ') + '：' + budgetLabel(currentBudget);
  }

  function applyFont(idx) {
    currentFont = idx;
    document.body.style.fontSize = FONT_SIZES[idx];
    document.getElementById('stFontBtn').textContent = T.stFont.replace('🔤 ', '🔤 ') + '：' + FONT_LABELS[idx];
  }

  function renderPlugins(plugins) {
    var box = document.getElementById('stPluginList');
    box.innerHTML = '';
    var fin = false;
    (plugins || []).forEach(function (p) {
      if (p.name === '财报助手') fin = !!p.enabled;
      var row = document.createElement('div');
      row.className = 'prow';
      var head = '<div class="phead">' +
        '<input type="checkbox" data-plug="' + escapeHtml(p.name) + '"' + (p.enabled ? ' checked' : '') + '>' +
        '<span class="pname pname-toggle" data-ptog="' + escapeHtml(p.name) + '">' + escapeHtml(p.name) + '</span>' +
        '<span style="color:var(--sub)">v' + escapeHtml(p.version || '') + '</span>' +
        '<span class="parrow" data-parrow="' + escapeHtml(p.name) + '" style="float:right;color:var(--sub)">▸</span></div>' +
        '<div class="pdesc">' + escapeHtml(p.description || '') + '</div>';
      var sets = '';
      (p.schema || []).forEach(function (s) {
        var key = s.key;
        var val = p.settings[key] !== undefined ? p.settings[key] : s.default;
        sets += '<div class="pset"><label>' + escapeHtml(s.label || key) + '</label>';
        if (s.type === 'bool') {
          sets += '<input type="checkbox" data-pset="' + escapeHtml(p.name) + '|' + escapeHtml(key) + '|bool"' + (val ? ' checked' : '') + '>';
        } else if (s.type === 'choice') {
          sets += '<select data-pset="' + escapeHtml(p.name) + '|' + escapeHtml(key) + '|choice">';
          (s.options || []).forEach(function (o) {
            var ov = typeof o === 'string' ? o : o.value;
            var ol = typeof o === 'string' ? o : (o.label || o.value);
            sets += '<option value="' + escapeHtml(ov) + '"' + (String(val) === String(ov) ? ' selected' : '') + '>' + escapeHtml(ol) + '</option>';
          });
          sets += '</select>';
        } else if (s.type === 'int') {
          sets += '<input type="number" data-pset="' + escapeHtml(p.name) + '|' + escapeHtml(key) + '|int" value="' + escapeHtml(String(val)) + '">';
        } else {
          sets += '<input type="' + (s.type === 'secret' ? 'password' : 'text') + '" data-pset="' + escapeHtml(p.name) + '|' + escapeHtml(key) + '|text" value="' + escapeHtml(String(val || '').replace(/"/g, '&quot;')) + '">';
        }
        sets += '</div>';
      });
      var psetsWrap = '<div class="psets" data-psets="' + escapeHtml(p.name) + '" style="display:none">' + sets + '</div>';
      row.innerHTML = head + psetsWrap;
      box.appendChild(row);
    });
    setFinEnabled(fin);   // 财报模式启用与否 → 控制快捷面板财报折叠区显隐
  }

  /* ---------------- 这几个控件的绑定（片段注入之后才摸得到元素） ---------------- */
  function bindTools() {
    document.getElementById('stBudgetBtn').onclick = function () {
      var i = BUDGETS.indexOf(currentBudget);
      i = (i + 1) % BUDGETS.length;
      currentBudget = BUDGETS[i];
      renderBudget();
      pywebview.api.set_budget(currentBudget);
    };
    document.getElementById('stAutoInput').onchange = function () {
      pywebview.api.set_auto_turn(this.checked);
    };
    document.getElementById('stFontBtn').onclick = function () {
      applyFont((currentFont + 1) % FONT_SIZES.length);
      pywebview.api.set_font(currentFont);
    };
    document.getElementById('stDevModeInput').onchange = function () {
      window.devMode = this.checked;
      pywebview.api.set_dev_mode(this.checked).then(function () {
        var advBox = document.getElementById('nrAdv');
        if (advBox) advBox.style.display = window.devMode ? '' : 'none';
      });
    };
    document.getElementById('stPluginList').addEventListener('change', function (e) {
      var t = e.target;
      var pn = t.getAttribute('data-plug');
      if (pn) {
        pywebview.api.set_plugin(pn, t.checked);
        return;
      }
      var ps = t.getAttribute('data-pset');
      if (ps) {
        var parts = ps.split('|');
        var name = parts[0], key = parts[1], type = parts[2];
        var val = type === 'bool' ? t.checked : t.value;
        pywebview.api.set_plugin_setting(name, key, val);
      }
    });
    // 点插件名/箭头 → 展开/收起该插件的设置（默认折叠）
    document.getElementById('stPluginList').addEventListener('click', function (e) {
      var t = e.target;
      var name = t.getAttribute('data-ptog') || t.getAttribute('data-parrow');
      if (!name) return;
      var prow = t.closest ? t.closest('.prow') : null;
      var psets = prow ? prow.querySelector('.psets') : null;
      var arrow = prow ? prow.querySelector('.parrow') : null;
      if (!psets) return;
      var open = psets.style.display !== 'none';
      psets.style.display = open ? 'none' : '';
      if (arrow) arrow.textContent = open ? '▸' : '▾';
    });
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('settingsModal')) {
      console.error('[settings] 片段没注入（找不到 #settingsModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    bindTools();
  }

  function unmount() {
    var b = document.getElementById('stBudgetBtn');
    if (b) { b.onclick = null; }
    var f = document.getElementById('stFontBtn');
    if (f) { f.onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    renderBudget: renderBudget, applyFont: applyFont, renderPlugins: renderPlugins,
    budgetLabel: budgetLabel
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前这四个都是 index.html 的顶层全局函数，外壳的 loadStateFill() 在状态刷新时直接叫它们：
 *   renderBudget()         刷新"预算：不限/32K"那个按钮
 *   applyFont(idx)         应用字号（顺带改 body 的 font-size）
 *   renderPlugins(list)    插件管理列表（含"财报助手"开关联动快捷面板）
 * 同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function renderBudget() { return window.SettingsScreen.renderBudget(); }
function applyFont(idx) { return window.SettingsScreen.applyFont(idx); }
function renderPlugins(plugins) { return window.SettingsScreen.renderPlugins(plugins); }

// 注册到路由：片段 = screens/settings.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('settings', { fragment: 'screens/settings.html', module: window.SettingsScreen });
