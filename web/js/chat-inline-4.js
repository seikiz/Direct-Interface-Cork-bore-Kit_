/* 从 index.html 内联脚本拆出（第 4/4 段，顺序加载；全局作用域不变） */
// ---- 看板娘（核心·L<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ive2D）设置 ----
var l2dModels = [];
function renderL2DSettings(l2d) {
  l2dModels = (l2d && l2d.models) || [];
  document.getElementById('stL2dScale').value = (l2d && l2d.scale) || 100;
  document.getElementById('stL2dPos').value = (l2d && l2d.pos) || '右下';
  document.getElementById('stL2dOpacity').value = (l2d && l2d.opacity) || 95;
  document.getElementById('stL2dDrag').checked = (l2d && l2d.draggable) !== false;
  document.getElementById('stL2dBreath').checked = (l2d && l2d.breath) !== false;
  document.getElementById('stL2dModelName').textContent = (l2d && l2d.model) ? l2d.model : '（未选择）';
}
function setL2dSetting(key, value) {
  pywebview.api.set_l2d(key, value).then(function (r) {
    if (r && r.ok) {
      try { if (L2D && L2D.applySettings) L2D.applySettings(); } catch (e) {}
      loadState();
    }
  });
}
document.getElementById('stL2dModel').onclick = function () {
  // 2026-12 文案清理：原来这句把模型文件名与目录路径都念出来了（"请把 .model3.json 放入
  // web/live2d/models/"），用户只需要知道"还没有模型可选"。
  if (!l2dModels.length) { alert('还没有可用的看板娘模型：把模型放进程序目录后重启就能选到。'); return; }
  var cur = document.getElementById('stL2dModelName').textContent;
  var idx = l2dModels.indexOf(cur);
  var next = l2dModels[(idx + 1) % l2dModels.length];
  document.getElementById('stL2dModelName').textContent = next;
  setL2dSetting('model', next);
};
document.getElementById('stL2dScale').addEventListener('change', function () { setL2dSetting('scale', parseInt(this.value, 10) || 100); });
document.getElementById('stL2dPos').addEventListener('change', function () { setL2dSetting('pos', this.value); });
document.getElementById('stL2dOpacity').addEventListener('change', function () { setL2dSetting('opacity', parseInt(this.value, 10) || 95); });
document.getElementById('stL2dDrag').addEventListener('change', function () { setL2dSetting('draggable', this.checked); });
document.getElementById('stL2dBreath').addEventListener('change', function () { setL2dSetting('breath', this.checked); });
document.getElementById('stLangSel').onchange = function () {
  // 三选一：中文 / English / 日本語 —— 选完立刻落盘（后端写 config.json 的 language）
  var want = this.value;
  pywebview.api.set_language(want).then(function (r) {
    if (r && r.ok) setT(r.lang); else setT(want);
  }).catch(function () {});
};
// ---- 世界卡撰写 ----
document.getElementById('worldList').addEventListener('click', function (e) {
  var tv = hitAttr(e, ['data-travel']);
  if (tv) {
    pywebview.api.travel(tv).then(function (r) {
      if (r && !r.ok) { alert((r && r.err) || '穿越失败'); return; }
      reloadWorlds();
    });
    return;
  }
  var en = hitAttr(e, ['data-wedit']);
  if (en) {
    WmScreen.openEdit(en);   // 世界书条目屏自己取数据/填表/开窗（阶段3：跨屏只留这一个调用）
    return;
  }
  var d = hitAttr(e, ['data-wdel']);
  if (d && confirm('删除世界 ' + d + '？')) {
    pywebview.api.delete_world(d).then(function () { reloadWorlds(); });
  }
});
// 世界书条目的列表渲染/收集（entryHtml/renderWmEntries/collectWmEntries）
// 也搬到了 web/js/screens/wm.js。
function reloadWorlds() {
  pywebview.api.state().then(function (s) {
    if (s) renderWorlds(s.worlds || [], s.selected_worlds || [], s.current_world || '');
  });
}

// 玩家角色卡：精细化结构化表单
function openPersonaModal() {
  pywebview.api.get_persona().then(function (f) {
    f = f || {};
    document.getElementById('ppNameInput').value = f.name || '';
    document.getElementById('ppAddressInput').value = f.address || '';
    document.getElementById('ppModeInput').value = f.mode || '';
    document.getElementById('ppPronounInput').value = f.pronoun || '';
    document.getElementById('ppPerspectiveInput').value = f.perspective || 'second';
    document.getElementById('ppRelationInput').value = f.relationship || '';
    document.getElementById('ppTabooInput').value = Array.isArray(f.taboo) ? f.taboo.join('，') : (f.taboo || '');
    document.getElementById('ppLegacyInput').value = f.legacy || '';
    document.getElementById('ppAppearanceInput').value = f.appearance || '';
    document.getElementById('ppPersonalityInput').value = f.personality || '';
    document.getElementById('ppBackgroundInput').value = f.background || '';
    document.getElementById('ppSpeechInput').value = f.speech || '';
    document.getElementById('ppFirstMesInput').value = f.first_mes || '';
    document.getElementById('ppMesExampleInput').value = f.mes_example || '';
    document.getElementById('ppNotesInput').value = f.notes || '';
    // 玩家卡同规格：战斗属性 + 正则回填
    var padv = f.advanced || null;
    var pb = padv && padv.battle ? padv.battle : null;
    document.getElementById('ppBattleEnabled').checked = !!(pb && pb.enabled);
    if (pb) {
      var attrs = pb.attrs || {};
      document.getElementById('ppBattleAttrs').value = Object.keys(attrs).map(function (k) {
        var a = attrs[k];
        return [k, a.label || k, a.initial, a.max !== undefined ? a.max : ''].join('|');
      }).join('\n');
      document.getElementById('ppBattleMech').value = (pb.mech_attrs || []).map(function (a) {
        return [a.key, a.label || a.key, a.initial, a.max !== undefined ? a.max : ''].join('|');
      }).join('\n');
    } else {
      document.getElementById('ppBattleAttrs').value = 'hp|生命|100|100\natk|攻击|10\ndef|防御|5';
      document.getElementById('ppBattleMech').value = '';
    }
    document.getElementById('ppRegexInput').value = (padv && padv.regex_rules || []).map(function (x) {
      return [x.id, x.name || x.id, x.pattern, x.replace, x.scope || 'both'].join('|');
    }).join('\n');
    document.getElementById('personaModal').classList.add('open');
  });
}
document.getElementById('btnPersona').onclick = function () { openPersonaModal(); };
// 切模式顺手预填视角：乙女/梦向 = 第二人称，跑团 = 第三人称（她手动选过就不动）
document.getElementById('ppModeInput').onchange = function () {
  var def = { gal: 'second', otome: 'second', trpg: 'third' }[this.value];
  var pv = document.getElementById('ppPerspectiveInput');
  if (def && !pv.dataset.touched) pv.value = def;
};
document.getElementById('ppPerspectiveInput').onchange = function () {
  this.dataset.touched = '1';
};
document.getElementById('ppCancel').onclick = function () { document.getElementById('personaModal').classList.remove('open'); };
document.getElementById('ppSave').onclick = function () {
  var p = {
    name: document.getElementById('ppNameInput').value.trim(),
    mode: document.getElementById('ppModeInput').value,
    address: document.getElementById('ppAddressInput').value.trim(),
    pronoun: document.getElementById('ppPronounInput').value,
    perspective: document.getElementById('ppPerspectiveInput').value || 'second',
    relationship: document.getElementById('ppRelationInput').value.trim(),
    taboo: document.getElementById('ppTabooInput').value.trim(),
    legacy: document.getElementById('ppLegacyInput').value.trim(),
    appearance: document.getElementById('ppAppearanceInput').value.trim(),
    personality: document.getElementById('ppPersonalityInput').value.trim(),
    background: document.getElementById('ppBackgroundInput').value.trim(),
    speech: document.getElementById('ppSpeechInput').value.trim(),
    first_mes: document.getElementById('ppFirstMesInput').value.trim(),
    mes_example: document.getElementById('ppMesExampleInput').value.trim(),
    notes: document.getElementById('ppNotesInput').value.trim(),
  };
  // 玩家卡同规格：战斗属性 + 正则
  var padv = null;
  if (document.getElementById('ppBattleEnabled').checked) {
    var battrs = {};
    document.getElementById('ppBattleAttrs').value.split('\n').forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var q = line.split('|');
      if (q.length < 2) return;
      var key = q[0].trim();
      if (!key) return;
      var entry = { label: q[1] ? q[1].trim() : key };
      var init = parseInt(q[2], 10);
      entry.initial = isNaN(init) ? 10 : init;
      if (q[3] !== undefined && q[3].trim() !== '') {
        var mx = parseInt(q[3], 10);
        entry.max = isNaN(mx) ? (key === 'hp' ? 100 : 999999) : mx;
      } else if (key === 'hp') entry.max = 100;
      battrs[key] = entry;
    });
    var padvBattle = { enabled: true };
    if (Object.keys(battrs).length) padvBattle.attrs = battrs;
    var bmech = [];
    document.getElementById('ppBattleMech').value.split('\n').forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var q = line.split('|');
      if (q.length < 2) return;
      var key = q[0].trim();
      if (!key) return;
      var entry = { key: key, label: q[1] ? q[1].trim() : key };
      var init = parseInt(q[2], 10);
      entry.initial = isNaN(init) ? 10 : init;
      var mx = parseInt(q[3], 10);
      entry.max = isNaN(mx) ? 999999 : mx;
      bmech.push(entry);
    });
    if (bmech.length) padvBattle.mech_attrs = bmech;
    padv = { battle: padvBattle };
  }
  var prr = [];
  document.getElementById('ppRegexInput').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var q = line.split('|');
    if (q.length < 4) return;
    var scope = q[4] ? q[4].trim() : 'both';
    if (['ai', 'user', 'both'].indexOf(scope) < 0) scope = 'both';
    prr.push({ id: q[0].trim(), name: q[1] ? q[1].trim() : q[0].trim(), pattern: q[2], replace: q.slice(3).join('|'), scope: scope, enabled: true });
  });
  if (prr.length) { if (!padv) padv = {}; padv.regex_rules = prr; }
  if (padv) p.advanced = padv;
  pywebview.api.set_persona(JSON.stringify(p)).then(function () {
    document.getElementById('personaModal').classList.remove('open');
    loadState();
  });
};
document.getElementById('ppAvatar').onclick = function () {
  var nm = document.getElementById('ppNameInput').value.trim() || '你';
  document.getElementById('fileInput').setAttribute('data-avatar-target', nm);
  document.getElementById('fileInput').click();
};

// 创意工坊（世界卡库）：wsCurLocal/wsCurOnline/wsOnlineCache 改存 DICK.state['ws.*']，
// 兼容入口在 web/js/screens/ws.js 里注册；开关窗与三个 Tab 的绑定也搬过去了。






// 编年史（codex）编辑器/播放器与 GAL 制作器的代码全部搬到 web/js/screens/codex-*.js / gal-*.js（阶段 5）：
// 结构在 web/screens/codex.html、web/screens/gal.html；index.html 里只剩 <!--@screen:codex--> 与 <!--@screen:gal-->。
// 原来那 2338 行按「连续切片」整块搬走，逐行守恒与跨屏零引用由 tests/test_screen_blocks.py 守着。
// 创意工坊本地/在线两个 Tab 的按钮绑定搬到了 web/js/screens/ws.js（阶段3）。

// ---- 前版功能：预算 / 自动接话 / 字体 / 插件管理 / 文档 / 导出 ----
var BUDGETS = [0, 4096, 16384, 32768, 65536, 131072];
var currentBudget = 0;
var FONT_SIZES = ['13px', '14.5px', '16px'];
var FONT_LABELS = ['小', '中', '大'];
var currentFont = 1;

// 预算 / 字体 / 插件管理的渲染与动作搬到了 web/js/screens/settings.js（阶段4）。
// 兼容入口 renderBudget()/applyFont()/renderPlugins() 在那里注册，loadStateFill 照旧调用。

// 设置屏的那几个按钮/列表绑定也在 web/js/screens/settings.js（阶段4）。
document.getElementById('qcRead').onclick = function () {
  pywebview.api.read_document(null).then(function (r) {
    if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
  });
};
document.getElementById('qcClearDoc').onclick = function () {
  pywebview.api.clear_document().then(function () {});
};
document.getElementById('qcExport').onclick = function () {
  pywebview.api.export_chat().then(function (r) {
    if (r && r.ok) alert('已导出：' + r.file);
    else if (r && r.err !== 'cancelled') alert((r && r.err) || '导出失败');
  });
};
document.getElementById('qcNovel').onclick = function () {
  // 小说导出：走树上的实际路径，未选的分支变成脚注（普通「导出Word」导的是扁平列表）
  pywebview.api.export_novel('epub').then(function (r) {
    if (r && r.ok) alert('已导出《' + (r.title || '') + '》\n' + (r.msg || '') + '\n\n文件：' + r.file);
    else if (r && r.err !== 'cancelled') alert((r && r.err) || '导出失败');
  }).catch(function (e) { alert('导出失败：' + e); });
};
document.getElementById('qcTheme').onclick = function () {
  themeIdx = (themeIdx + 1) % THEMES.length;
  applyTheme();
  pywebview.api.set_theme(themeIdx, accentIdx);
};

window.addEventListener('pywebviewready', function () {
  var aliasOk = ensureApiAliases();
  if (!aliasOk || !(window.pywebview && window.pywebview.api && window.pywebview.api.state)) {
    var tries = 0;
    var t = setInterval(function () {
      tries++;
      if (ensureApiAliases() && window.pywebview.api && window.pywebview.api.state) {
        clearInterval(t);
        loadState();
      } else if (tries > 10) {
        clearInterval(t);
        loadState();
      }
    }, 300);
  } else {
    loadState();
  }
  setInterval(poll, 150);
});

/* ================= Live2D 看板娘（懒加载，插件启用才激活） ================= */
var L2D = {
  enabled: false,
  modelFile: '',
  scale: 100, pos: '右下', opacity: 95, draggable: true, breath: true,
  app: null, model: null, scriptsLoaded: false, loading: false,
  hintTimer: null,

  showHint: function (msg, ms) {
    var el = document.getElementById('l2d-hint');
    if (!el) return;
    el.textContent = msg;
    el.style.display = 'block';
    if (this.hintTimer) clearTimeout(this.hintTimer);
    var self = this;
    this.hintTimer = setTimeout(function () { el.style.display = 'none'; }, ms || 4000);
  },

  // 从核心态 state.l2d 读取看板娘设置（已并入底层，不再依赖插件开关）
  syncFromState: function (st) {
    var self = this;
    if (!st) return;
    var p = (st && st.l2d) || null;
    var was = self.enabled;
    // 核心化：恒启用，但无模型时不真正加载
    self.enabled = !!(p && p.enabled);
    if (p) {
      self.modelFile = p.model || '';
      self.scale = parseInt(p.scale, 10) || 100;
      self.pos = p.pos || '右下';
      self.opacity = parseInt(p.opacity, 10) || 95;
      self.draggable = p.draggable !== false;
      self.breath = p.breath !== false;
      self.models = p.models || [];
    }
    if (self.enabled && !was && self.modelFile) {
      this.activate();
    } else if (!self.enabled && was) {
      this.deactivate();
    }
  },

  activate: function () {
    if (this.loading || this.scriptsLoaded && this.model) return;
    var self = this;
    this.loading = true;
    // 1) 检查资源是否存在
    var probe = new Image();
    probe.onerror = function () {
      self.loading = false;
      self.showHint('[ic:warning] Live2D 资源缺失：请将渲染库放入 web/live2d/vendor/（pixi.min.js / live2dcubismcore.min.js / pixi-live2d-display.min.js），模型放入 web/live2d/models/');
    };
    probe.onload = function () {
      self.loading = false;
      self.loadScripts();
    };
    probe.src = 'live2d/vendor/pixi.min.js?' + Date.now();
  },

  loadScripts: function () {
    var self = this;
    var scripts = [
      'live2d/vendor/pixi.min.js',
      'live2d/vendor/live2dcubismcore.min.js',
      'live2d/vendor/pixi-live2d-display.min.js'
    ];
    var idx = 0;
    function next() {
      if (idx >= scripts.length) { self.initModel(); return; }
      var s = document.createElement('script');
      s.src = scripts[idx] + '?' + Date.now();
      s.onload = function () { idx++; next(); };
      s.onerror = function () {
        self.showHint('[ic:warning] 加载失败: ' + scripts[idx] + '（请检查 web/live2d/vendor/ 目录）');
        idx = scripts.length;
      };
      document.head.appendChild(s);
    }
    next();
  },

  initModel: function () {
    var self = this;
    if (!window.PIXI || !window.Live2DModel) {
      this.showHint('[ic:warning] Live2D 渲染库加载失败（pixi / live2d-display 未就绪）');
      return;
    }
    var stageEl = document.getElementById('l2d-stage');
    if (!stageEl) return;
    if (!this.modelFile) {
      this.showHint('[ic:warning] 未选择模型：请在 [ic:settings] 设置 → 插件 → Live2D 看板娘 的「模型」里选择（web/live2d/models/）');
      return;
    }
    var modelUrl = 'live2d/models/' + encodeURIComponent(this.modelFile);
    try {
      this.app = new PIXI.Application({ resizeTo: window, transparent: true, antialias: true });
      stageEl.appendChild(this.app.view);
      this.app.view.style.position = 'fixed';
      this.app.view.style.pointerEvents = 'none';
      this.app.view.style.zIndex = '9000';
      this.app.view.style.width = '100%';
      this.app.view.style.height = '100%';
      var container = new PIXI.Container();
      this.app.stage.addChild(container);
      Live2DModel.from(modelUrl).then(function (model) {
        self.model = model;
        container.addChild(model);
        self.applySettings();
        model.on('hit', function (hitAreas) {
          if (hitAreas && hitAreas.length) {
            self.showHint('[ic:target] 触发了：' + hitAreas.join(', '));
          }
        });
      }).catch(function (e) {
        self.showHint('[ic:warning] 模型加载失败: ' + (e && e.message ? e.message : e));
      });
    } catch (e) {
      this.showHint('[ic:warning] Live2D 初始化失败: ' + (e && e.message ? e.message : e));
    }
  },

  applySettings: function () {
    if (!this.model || !this.app) return;
    var m = this.model;
    var sc = this.scale / 100;
    m.scale.set(sc, sc);
    var vw = window.innerWidth, vh = window.innerHeight;
    var bw = m.width * m.scale.x, bh = m.height * m.scale.y;
    var margin = 20;
    var x, y;
    if (this.pos === '右下') { x = vw - bw - margin; y = vh - bh - margin; }
    else if (this.pos === '左下') { x = margin; y = vh - bh - margin; }
    else if (this.pos === '右上') { x = vw - bw - margin; y = margin; }
    else { x = margin; y = margin; }
    m.position.set(x, y);
    this.app.view.style.opacity = this.opacity / 100;
  },

  deactivate: function () {
    if (this.app) {
      try { this.app.destroy(true); } catch (e) {}
      this.app = null; this.model = null;
    }
    var stageEl = document.getElementById('l2d-stage');
    if (stageEl) stageEl.innerHTML = '';
  }
};

// L2D 状态已由 loadStateFill 内联同步（见 renderPlugins 后的调用）

/* ================= 架构级水印（隐蔽，反抄袭溯源） ================= */
(function () {
  // 1) 控制台标识（开发者可见，用户无感）。版号不写死：由 state() 带回
  // （唯一真相在仓库根目录 version.json），拿到后补一行带版号的。
  try { console.log("%cDICK %cCODEX engine — 本产品由 DICK 架构驱动", "color:#f59e0b;font-weight:bold", "color:#888"); } catch (e) {}
  // 2) DOM 属性标记（抄界面 DOM 即带走）
  try {
    var root = document.documentElement;
    if (root && !root.getAttribute('data-dick')) root.setAttribute('data-dick', 'cod3x-7f3a');
  } catch (e) {}
  // 3) 极淡角落水印（肉眼难察，截图/录屏仍可取证）
  try {
    var wm = document.createElement('div');
    wm.setAttribute('aria-hidden', 'true');
    wm.textContent = 'DICK';
    wm.style.cssText = 'position:fixed;right:2px;bottom:0;font-size:8px;color:rgba(255,255,255,0.05);pointer-events:none;z-index:1;user-select:none;';
    document.body.appendChild(wm);
  } catch (e) {}
})();

// 加密备份屏的动作搬到了 web/js/screens/bk.js（DOM 在 web/screens/bk.html）。

// 加密备份屏的按钮绑定也在 web/js/screens/bk.js（阶段3）。
// 事件进度弹窗：点背景 / Esc 关闭
document.getElementById('evProgressModal').addEventListener('click', function (e) {
  if (e.target === this) this.classList.remove('open');
});
document.addEventListener('keydown', function (e) {
  if (e.code !== 'Escape') return;
  var pm = document.getElementById('evProgressModal');
  if (pm && pm.classList.contains('open')) { pm.classList.remove('open'); return; }
  var m = document.getElementById('backupModal');
  if (m && m.classList.contains('open')) bkClose();
});
