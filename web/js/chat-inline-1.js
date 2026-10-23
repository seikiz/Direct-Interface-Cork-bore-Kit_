/* 从 index.html 内联脚本拆出（第 1/4 段，顺序加载；全局作用域不变） */
/* 主聊天壳的内联脚本（从 index.html 拆出；同步加载，执行顺序与全局作用域不变） */
// pywebview 桥接别名：api_xxx -> <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌xxx（兼容不同 pywebview 版本的方法命名）
function ensureApiAliases() {
  try {
    var a = window.pywebview && window.pywebview.api;
    if (!a) return false;
    var done = false;
    Object.keys(a).forEach(function (k) {
      if (k.indexOf('api_') === 0 && typeof a[k] === 'function' && !a[k.slice(4)]) {
        a[k.slice(4)] = a[k];
        done = true;
      }
    });
    return done;
  } catch (e) { return false; }
}
ensureApiAliases();
var pywebview = window.pywebview;
var lastSeq = 0;
var lastEpoch = -1;
var lastUserText = '';

// ---------- 黑白线性图标（替代 emoji；currentColor 随主题） ----------
// ---- 图标：Material Symbols（唯一真相 icons/icons.json → web/icons.js，见 tools/gen_icons.py）----
// 这里只负责把"文本里的 emoji / [ic:名字]"换成 <span class="ms">图标名</span>，字形与大小
// 由上面的 @font-face / .ms 给。以前那四张手写的内联 SVG 字典（emoji→svg、png 槽位表、
// 具名表、按槽位索引表）连同 _ic / _SVG 两个小工具全部删掉了 —— 以后换图标只改 icons/icons.json。
function _iconEntry(emoji) {
  var m = window.DICK_ICONS || {};
  return m[emoji] || m[String(emoji).replace(/\uFE0F/g, '')] || null;
}
function _iconEntryByName(name) {
  var m = window.DICK_ICON_NAMES || {};
  return m[String(name || '').toLowerCase().replace(/^ic_/, '')] || null;
}
// 拼进 innerHTML 用（按钮那类）：图标名缺失时原样回退 emoji，绝不显示空白/豆腐块
function _iconHtml(emoji) {
  var e = _iconEntry(emoji);
  return e ? '<span class="ms">' + e.n + '</span>' : emoji;
}
// emoji 匹配范围：补上 2300-23FF（）与 2190-21FF（）——旧版漏了这两段，
// 结果「生成中/打包中」这类状态提示里的沙漏一直没被替换掉。
var _EMOJI_CLS = '[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{2300}-\u{23FF}\u{2190}-\u{21FF}\u{FE0F}\u{200D}\u{20E3}\u{1F1E6}-\u{1F1FF}]';
var _EMOJI_RE = new RegExp('^(' + _EMOJI_CLS + '+)', 'u');
var _ICON_SCAN = new RegExp('\\[ic:([a-z0-9_]+)\\]|(' + _EMOJI_CLS + '+)', 'giu');
// 这些区域里的文字一律不动：聊天正文（用户/AI 自己打的 emoji 要保留）、已替换的图标、
// SVG 文本（里面塞 <span> 会直接渲染不出来）、表单控件与代码。
// 另外两类地方**画不了字体图标**，所以那里的文案不放 emoji（状态由文字表达）：
// · 浏览器原生 alert()/confirm()/prompt()：弹窗不在 DOM 里，TreeWalker 碰不到
// · <input placeholder> / title 等属性：属性值是纯文本，塞不进 <span class="ms">
// [data-icon-scope]：作用域区（例如 gothic_frame.html 的预览按钮）由 web/icon_scope.js 按
// 它自己那份映射替换。全局扫描必须**让开** —— 否则全局先把它换成全局图标，作用域就没机会生效了。
var _ICON_SKIP = '#chat, .ic, svg, script, style, textarea, input, select, option, code, pre, [data-noicon], [data-icon-scope]';
function _iconSkip(node) {
  var p = node.parentNode;
  if (!p) return true;
  return !p.closest || !!p.closest(_ICON_SKIP);
}
// icons/<ic_name>.png 覆盖：没放图片时不能让每个图标都去撞一次 404 —— 按槽位缓存结果，
// 并且连续多次未命中就认定这个文件夹是空的、本次会话不再试探（命中一次即清零）。
var _iconPngHave = {}, _iconPngMiss = 0, _iconPngOff = false;
function _applyPng(span, slug) {
  if (!slug || _iconPngOff || typeof Image !== 'function') return;
  if (_iconPngHave[slug] === false) return;
  var img = new Image();
  img.alt = '';
  img.className = 'ic-img';
  img.onload = function () {
    _iconPngHave[slug] = true;
    _iconPngMiss = 0;
    span.innerHTML = '';
    span.appendChild(img);
  };
  img.onerror = function () {
    _iconPngHave[slug] = false;
    if (++_iconPngMiss >= 20) _iconPngOff = true;
  };
  img.src = 'icons/' + slug + '.png';
}
function _makeIcon(name, png, fallback) {
  var span = document.createElement('span');
  span.className = 'ic';
  if (name) span.innerHTML = '<span class="ms">' + name + '</span>';
  else if (fallback) span.textContent = fallback;   // 没映射就原样显示 emoji
  _applyPng(span, png);
  return span;
}
function _iconLookup(name) {
  var key = String(name).toLowerCase().replace(/^ic_/, '');
  var e = _iconEntryByName(key);
  if (e) return { name: e.n, png: e.p || ('ic_' + key) };
  // [ic:名字] 的语义就是「这里直接写 Material Symbols 的连字名」：
  // 表里没有（具名表只有 go/play/sprite… 六个）也照样画成 <span class="ms">名字</span>，
  // 不再把 "[ic:folder]" 这种字面量露给用户。字体缺这个连字时显示的是名字本身，
  // 一眼就能看出是名字写错了（tests/test_no_emoji_ui.py ① 会先按字体连字表把它拦住）。
  if (!/^[a-z0-9_]+$/.test(key)) return null;
  return { name: key, png: '' };
}
function iconifyText(textNode) {
  var s = textNode.data;
  if (!s) return;
  _ICON_SCAN.lastIndex = 0;
  var hits = [], m;
  while ((m = _ICON_SCAN.exec(s))) {
    if (m[1]) {                                     // [ic:名字] 具名标记
      var hit = _iconLookup(m[1]);
      if (hit) hits.push([m.index, m.index + m[0].length, hit.name, hit.png, '']);
      continue;
    }
    var run = m[2], whole = run.replace(/\uFE0F/g, '');
    var ent = _iconEntry(whole);
    if (ent) {                                      // 整段命中（单个 emoji 或 ZWJ 组合）
      hits.push([m.index, m.index + run.length, ent.n, ent.p || '', '']);
      continue;
    }
    var cps = run.match(/./gu) || [], off = 0;      // 连续多个不同 emoji：逐个拆开
    for (var i = 0; i < cps.length; i++) {
      var cp = cps[i], clean = cp.replace(/\uFE0F/g, '');
      var at = m.index + off;
      off += cp.length;
      var one = clean ? _iconEntry(clean) : null;
      if (!one) continue;                           // 没映射 → 原样留着这个 emoji
      hits.push([at, m.index + off, one.n, one.p || '', '']);
    }
  }
  if (!hits.length) return;
  var parent = textNode.parentNode;
  if (!parent) return;
  var at = 0;
  for (var h = 0; h < hits.length; h++) {
    if (hits[h][0] > at) parent.insertBefore(document.createTextNode(s.slice(at, hits[h][0])), textNode);
    parent.insertBefore(_makeIcon(hits[h][2], hits[h][3], hits[h][4]), textNode);
    at = hits[h][1];
  }
  if (at < s.length) parent.insertBefore(document.createTextNode(s.slice(at)), textNode);
  parent.removeChild(textNode);
}
function iconifyUI(root) {
  root = root || document.body || document.documentElement;
  if (!root || typeof document.createTreeWalker !== 'function') return;
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: function (n) {
      return _iconSkip(n) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
    }
  });
  var nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (var j = 0; j < nodes.length; j++) iconifyText(nodes[j]);
}
var _iconBusy = false, _iconQueued = false;
function _iconSchedule() {
  if (_iconQueued) return;
  _iconQueued = true;
  var go = function () {
    _iconQueued = false;
    _iconBusy = true;
    try { iconifyUI(); } finally { _iconBusy = false; }
  };
  if (typeof requestAnimationFrame === 'function') requestAnimationFrame(go);
  else if (typeof setTimeout === 'function') setTimeout(go, 16);
  else go();
}
// 模态/面板都是 innerHTML 现拼的，改完就过期了 —— 监听 DOM 变更自动补上。
// #chat 里的流式输出是最高频的变更源，直接跳过不触发整树扫描。
function iconifyWatch() {
  if (typeof MutationObserver !== 'function' || !document.body) return;
  new MutationObserver(function (recs) {
    if (_iconBusy) return;
    for (var i = 0; i < recs.length; i++) {
      var t = recs[i].target;
      if (t && t.closest && t.closest(_ICON_SKIP)) continue;
      _iconSchedule();
      return;
    }
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
}
// 立刻先跑一遍：静态标记里的 [ic:名字] 不能等到第一次 loadState 才换掉
// （后端没响应/没配 Key 时也得是图标，不能把 [ic:go] 当字面量露给用户）
iconifyUI();
iconifyWatch();
var streamingEl = null;
var currentSpeaker = 'AI'; // 当前激活角色（单角色时流式回复显示角色名）
var pendingImage = null;   // {b64, mime}
var avatarCache = {};      // name -> dataURL | 'LETTER'
var branchList = [];
var treeList = [];
var treeScope = 'all';
var manualScope = false;   // 用户手动切过树范围后，不再自动默认
var expandSeg = {};        // 选项骨架：段展开状态（key = prevId>nextId）
// 「正在编辑哪条消息」不再是顶层 var：搬到了 web/js/screens/em.js，
// 存在 DICK.state['editMsg.target']（见 web/js/state.js 的 SCHEMA）。
// 世界书条目（wmEntries）也搬走了：真身 DICK.state['wm.entries']，兼容访问器在 web/js/screens/wm.js。
var lang = 'zh';
// 主题：dark / light / oled / auto（auto = 跟随系统，body 上不加类，交给 theme.css 里的
// @media (prefers-color-scheme:light) 决定）。配色令牌见 web/theme.css（生成物），别在这写色值。
var THEMES = ['dark','light','oled','auto'];
var themeIdx = 0;
// 强调色同样是令牌的一部分：暗/浅各一版。浅色底上 #60a5fa/#4ade80 当文字色不达标（2.5:1 / 2.35:1），
// 所以浅色主题用同色相的深色版（见 design/tokens.json 的 accents）。
var ACCENTS = [
  { dark:'#60a5fa', light:'#2563eb' },
  { dark:'#4ade80', light:'#15803d' },
  { dark:'#a78bfa', light:'#6d28d9' },
  { dark:'#f472b6', light:'#be185d' }
];
var accentIdx = 0;
var T = {};

/* ---------------- 文案套用：只认标注，不再逐 id 点名（阶段 4） ----------------
 *
 * 为什么改：原来 setT() 里是 60 多行「按 id 摸到元素、再把 textContent 换成 T 表里的文案」，
 * 一屏一个 id 地"隔空改名" —— 换文案要同时懂 DOM 结构和 i18n 表，而且 setT 一个人就
 * 贡献了 43 处跨屏 id 引用（"屏与屏的耦合"里最大的一块）。
 * 现在文案写在元素上：`data-i18n="<key>"`（key 就是 lang/strings.json 的键，不新造），
 * 这里只做一遍 querySelectorAll，谁被标注谁就跟着语言走。
 *
 * data-i18n="<键名>" → textContent = T[键名]
 * data-i18n-prefix=" " → textContent = 前缀 + T[键名]（图标前缀不进文案表）
 * data-i18n-placeholder="<键名>" → placeholder = T[键名]（输入框占位符）
 *
 * 表里没有这个键时**不动元素**：初始 HTML 里那行中文就是兜底（漏翻也看得懂，不会变空白）。
 */
function applyI18n(root) {
  var box = root || document;
  var nodes = box.querySelectorAll('[data-i18n]');
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    var txt = T[el.getAttribute('data-i18n')];
    if (txt === undefined || txt === null) { continue; }
    var pre = el.getAttribute('data-i18n-prefix');
    el.textContent = (pre ? pre : '') + txt;
  }
  var phs = box.querySelectorAll('[data-i18n-placeholder]');
  for (var j = 0; j < phs.length; j++) {
    var pk = phs[j].getAttribute('data-i18n-placeholder');
    if (T[pk] !== undefined && T[pk] !== null) { phs[j].placeholder = T[pk]; }
  }
}

function setT(l) {
  // 三档：zh / en / ja。认不出的值退回中文（与后端 i18n.set_lang 同一条规矩）。
  // 文案表来自 web/i18n.js（由 lang/strings.json 生成，见 tools/gen_i18n.py）——
  // 这里原来内联了三段 T = {...}，跟 i18n.py / 安卓 I18n.kt 各写一份，迟早对不上。
  if (l !== 'en' && l !== 'ja') l = 'zh';
  lang = l;
  var table = (window.DICK_I18N || {});
  T = table[l] || table.zh || {};
  applyI18n();                    // ① 标注过的文案（绝大多数都走这里）
  var langSel = document.getElementById('stLangSel');
  if (langSel) langSel.value = lang;              // ② 语言下拉自己的选中项（不是文案）
  var langLbl = document.getElementById('stLang');
  if (langLbl) langLbl.textContent = '语言 / Language / 言語';  // ③ 三语同形，本来就不跟表走
  renderWmParams();               // ④ 8 格世界参数的标签是 T['param_' + k]，动态键
  updatePresetName();             // ⑤ 预设按钮要拼上当前预设名，不是固定文案
  iconifyUI();
  iconifyWatch();
}

function speakerColor(name) {
  var palette = ['#60a5fa','#34d399','#fbbf24','#a78bfa','#f472b6','#22d3ee','#fb923c','#f87171'];
  if (name === '你') return '#4ade80';
  if (name === 'AI' || !name) return '#94a3b8';
  var h = 0;
  for (var i = 0; i < name.length; i++) h += name.charCodeAt(i);
  return palette[h % palette.length];
}

function avatarHtml(name, cls) {
  var url = avatarCache[name];
  if (url === undefined) {
    try { url = pywebview.api.get_avatar(name); } catch (e) { url = null; }
    if (url === undefined || url === null) {
      avatarCache[name] = 'LETTER';
      var c = speakerColor(name);
      return '<span class="avatar letter" style="background:' + c + '">' + escapeHtml((name || 'A').charAt(0)) + '</span>';
    }
    avatarCache[name] = url;
  }
  if (url === 'LETTER') {
    var c2 = speakerColor(name);
    return '<span class="avatar letter" style="background:' + c2 + '">' + escapeHtml((name || 'A').charAt(0)) + '</span>';
  }
  return '<img class="avatar" src="' + url + '">';
}

// ---- 零宽字符防线 ----
// 零宽/不可见字符：白烧 token、卡住渲染、藏提示词注入、绕过关键词过滤。
// 少量 ZWJ(U+200D)/ZWNJ(U+200C) 是合法的（emoji 组合 要靠它），所以少量保留、超标全删。
var ZW_RE = /[\u200b\u200c\u200d\u2060\ufeff\u00ad\u034f\u180e\u061c\u200e\u200f\u202a-\u202e\u2061-\u2064\u2066-\u2069]|[\u{E0000}-\u{E007F}]/gu;
function stripInvisible(s) {
  if (typeof s !== 'string' || !s) return s;
  var hits = s.match(ZW_RE);
  if (!hits) return s;
  var allCond = hits.every(function (c) { return c === '\u200d' || c === '\u200c'; });
  if (allCond && hits.length <= 4) return s;      // 正常 emoji 组合，别误伤
  return s.replace(ZW_RE, '');
}
function invisibleCount(s) {
  if (typeof s !== 'string' || !s) return 0;
  var hits = s.match(ZW_RE);
  return hits ? hits.length : 0;
}

function escapeHtml(s) {
  return String(stripInvisible(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function displayName(speaker, kind) {
  // 用户消息：显示玩家卡名字（与头像文件名一致），无名字时显示「你」
  if (kind === 'user') return speaker || (lang === 'en' ? 'You' : (lang === 'ja' ? 'あなた' : '你'));
  if (kind === 'sys') return lang === 'en' ? 'System' : (lang === 'ja' ? 'システム' : '系统');
  return speaker || 'AI';
}

function whoClass(kind) {
  return kind === 'user' ? 'me' : 'ai';
}

var PROVIDERS = [];
var currentProviderId = 'deepseek';
var apiKeysMap = {};

function providerById(pid) {
  for (var i = 0; i < PROVIDERS.length; i++) if (PROVIDERS[i].id === pid) return PROVIDERS[i];
  return null;
}

function showOverlay(btnId, menuId, items, onPick) {
  var btn = document.getElementById(btnId);
  var menu = document.getElementById(menuId);
  menu.innerHTML = '';
  items.forEach(function (it) {
    var d = document.createElement('div');
    d.className = 'o-item' + (it.sel ? ' sel' : '');
    var main = document.createElement('span');
    main.textContent = it.label;
    d.appendChild(main);
    if (it.tag) {
      var t = document.createElement('span');
      t.className = 'tag';
      t.textContent = it.tag;
      d.appendChild(t);
    }
    d.onclick = function () { onPick(it.value); };
    menu.appendChild(d);
  });
  var r = btn.getBoundingClientRect();
  menu.style.top = Math.round(r.bottom + 4) + 'px';
  menu.style.left = Math.round(r.left) + 'px';
  menu.style.width = Math.max(260, Math.round(r.width)) + 'px';
  menu.style.display = '';
}

function closeOverlays() {
  document.getElementById('stProviderMenu').style.display = 'none';
  document.getElementById('stModelMenu').style.display = 'none';
  var pm = document.getElementById('presetMenu');
  if (pm) pm.style.display = 'none';
}

function renderProviderSel(selId) {
  var p = providerById(selId);
  document.getElementById('stProviderBtn').textContent = '模型商：' + (p ? p.name : selId) + ' ▾';
}

function renderModelSel(p) {
  var cur = document.getElementById('stModelInput').value.trim();
  document.getElementById('stModelBtn').textContent = '模型：' + (cur || '—') + ' ▾';
}

function fillProvider(pid, keepKeyInput) {
  currentProviderId = pid;
  var p = providerById(pid);
  if (!p) return;
  renderProviderSel(pid);
  document.getElementById('stBaseInput').value = p.base_url;
  var dl = document.getElementById('stModelList');
  dl.innerHTML = '';
  p.models.forEach(function (m) {
    var o = document.createElement('option');
    o.value = m;
    dl.appendChild(o);
  });
  var mi = document.getElementById('stModelInput').value.trim();
  if (!mi || p.models.indexOf(mi) < 0) {
    document.getElementById('stModelInput').value = p.models[0];
  }
  renderModelSel(p);
  var ki = document.getElementById('stKeyInput');
  ki.disabled = !!p.free;
  ki.placeholder = p.free ? '免 Key，留空即可' : 'sk-...';
  if (!keepKeyInput) {
    var saved = apiKeysMap[pid] || '';
    ki.value = saved ? '••••••••' : '';
  }
  document.getElementById('stBuyHint').textContent = p.free ? '无需付费，直接可用（高峰期会慢一点）' : '';
}

function appendMessage(m) {
  var chat = document.getElementById('chat');
  var div = document.createElement('div');
  var cls = 'msg';
  if (m.kind === 'user') cls += ' user';
  if (m.kind === 'sys') cls += ' sys';
  div.className = cls;
  div.setAttribute('data-seq', m.seq);
  if (m.node_id) div.setAttribute('data-node', m.node_id);
  var name = displayName(m.speaker, m.kind);
  var imgPart = m.image ? '<img class="img" src="' + m.image + '">' : '';
  var av = m.kind === 'sys' ? '' : avatarHtml(m.kind === 'user' ? (m.speaker || '你') : (m.speaker || 'AI'), cls);
  var ctl = '';
  if ((m.kind === 'user' || m.kind === 'ai') && m.node_id) {
    ctl += '<button data-act="edit">' + _iconHtml('[ic:edit]') + '</button>';
  }
  if (m.kind === 'ai') {
    ctl += '<button data-act="speak" title="朗读">' + (_iconHtml('[ic:volume_up]')) + '</button>';
    if (m.swipes && m.swipes.total > 1) {
      ctl += '<button data-act="sprev">◀</button><span class="swipe-n">' + (m.swipes.index + 1) + '/' + m.swipes.total + '</span><button data-act="snext">▶</button>';
    }
    ctl += '<button data-act="regen">↻</button>';
  }
  if (ctl) ctl = '<div class="mctl">' + ctl + '</div>';
  div.innerHTML = av + '<div class="body"><span class="who ' + whoClass(m.kind) + '">' + escapeHtml(name) +
    '</span><div class="bubble">' + imgPart + escapeHtml(m.content) + '</div>' + ctl + '</div>';
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function ensureStreaming() {
  if (!streamingEl || !streamingEl.parentNode) {
    var chat = document.getElementById('chat');
    streamingEl = document.createElement('div');
    streamingEl.className = 'msg';
    var spk = currentSpeaker || 'AI';
    streamingEl.innerHTML = avatarHtml(spk, 'msg') +
      '<div class="body"><span class="who ai">' + escapeHtml(spk) + '</span><div class="bubble"><span class="scontent"></span><span class="cursor">▌</span></div></div>';
    chat.appendChild(streamingEl);
  }
  return streamingEl;
}

function setStreaming(text, loading) {
  // 开局（开场白由模型演出）时流式文本还是空的，但必须让用户看到「正在生成」——
  // 否则开局那段等待期界面一片空白，用户分不清是在生成还是坏了。
  // 普通发消息时用户自己那句话说出来了、知道在等，所以只有开局需要这个兜底。
  if (!text && !loading) { removeStreaming(); return; }
  var el = ensureStreaming();
  el.querySelector('.scontent').textContent = text || '…';
  var chat = document.getElementById('chat');
  chat.scrollTop = chat.scrollHeight;
}

function removeStreaming() {
  if (streamingEl && streamingEl.parentNode) streamingEl.parentNode.removeChild(streamingEl);
  streamingEl = null;
}

// ---------- Galgame 选项（选择肢） ----------
function renderChoices(c) {
  var box = document.getElementById('choices');
  if (!c || ((!c.items || !c.items.length) && !c.loading)) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  box.style.display = 'flex';
  box.innerHTML = '';
  if (c.loading) {
    var hint = document.createElement('span');
    hint.className = 'ch-hint';
    hint.textContent = T.chLoading || '[ic:hourglass_empty] 正在生成选项…';
    box.appendChild(hint);
  }
  (c.items || []).forEach(function (t) {
    var b = document.createElement('button');
    b.className = 'choice-btn';
    var isObj = t && typeof t === 'object';
    var text = isObj ? (t.text || '') : t;
    var effParts = [];
    if (isObj && t.result) effParts.push(t.result);
    if (isObj && t.aff !== undefined && t.aff !== null) effParts.push('[ic:favorite]' + (t.aff > 0 ? '+' : '') + t.aff + '%');
    if (isObj && t.st && typeof t.st === 'object') {
      Object.keys(t.st).forEach(function (k) { effParts.push(k + ':' + t.st[k]); });
    }
    if (effParts.length) {
      b.innerHTML = escapeHtml(text) + '<span class="ch-eff">' + escapeHtml(effParts.join(' · ')) + '</span>';
    } else {
      b.textContent = text;
    }
    b.onclick = function () { pickChoice(text); };
    box.appendChild(b);
  });
  if (c.items && c.items.length) {
    var rg = document.createElement('button');
    rg.className = 'choice-btn ghost';
    rg.textContent = '↻';
    rg.title = '重新生成选项';
    rg.onclick = function () {
      try { pywebview.api.cyoa().then(function () {}); } catch (e) {}
    };
    box.appendChild(rg);
  }
}

function pickChoice(text) {
  try {
    pywebview.api.pick_choice(text).then(function (r) {
      if (r && r.ok) renderChoices({ items: [], loading: false, error: '' });
    });
  } catch (e) {}
}

// ---------- 战斗面板（属性 / 招式按钮 / buff） ----------
function renderBattle(b) {
  var bar = document.getElementById('battlebar');
  if (!bar) return;
  var attrs = (b && b.attrs) || [];
  var moves = (b && b.moves) || [];
  if (!b || (!attrs.length && !moves.length)) {
    bar.style.display = 'none';
    bar.innerHTML = '';
    return;
  }
  bar.style.display = 'flex';
  bar.innerHTML = '';
  var parts = [];
  // 玩家侧状态（同规格：玩家卡配的战斗属性）
  var pl = (b && b.player) || [];
  if (pl.length) {
    var plHp = 0;
    pl.forEach(function (a) { if (a.key === 'hp') plHp = a.value || 0; });
    parts.push('<span class="mb-item">[ic:person] 玩家 <b>' + plHp + '</b>HP</span>');
  }
  // ① 有合理上限（≤1000）的属性 → 进度条（hp 红 / 其他蓝）；无上限 → 数值
  var bars = [], nums = [];
  attrs.forEach(function (a) {
    var mx = a.max || 0;
    if (mx > 0 && mx <= 1000) bars.push(a); else nums.push(a);
  });
  bars.forEach(function (a) {
    var frac = Math.max(0, Math.min(1, (a.value || 0) / Math.max(1, a.max || 1)));
    var cls = a.key === 'hp' ? 'fight' : 'mp';
    parts.push('<span class="mb-item">[ic:swords] ' + escapeHtml(a.label || a.key) + ' <b>' + (a.value || 0) + '</b>/' + a.max +
      ' <span class="mb-bar ' + cls + '"><i style="width:' + Math.round(frac * 100) + '%"></i></span></span>');
  });
  if (nums.length) {
    parts.push('<span class="mb-item">' + nums.map(function (a) {
      return escapeHtml(a.label || a.key) + ' <b>' + (a.value || 0) + '</b>';
    }).join(' · ') + '</span>');
  }
  // ② 招式按钮
  if (moves.length) {
    parts.push('<span class="mb-moves">' + moves.map(function (m) {
      return '<button class="battle-btn" data-mid="' + escapeHtml(m.id) + '" title="' + escapeHtml(m.desc || '') + '">[ic:swords] ' + escapeHtml(m.name) + '</button>';
    }).join('') + '</span>');
  }
  // ③ buff 徽章
  (b.buffs || []).forEach(function (bf) {
    parts.push('<span class="mb-item buff">[ic:auto_awesome] ' + escapeHtml(bf.id) + ' ×' + bf.turns + '</span>');
  });
  bar.innerHTML = parts.join('');
  bar.querySelectorAll('[data-mid]').forEach(function (btn) {
    btn.onclick = function () {
      try { pywebview.api.battle_move(btn.getAttribute('data-mid')).then(function () {}); } catch (e) {}
    };
  });
}

// ---------- 机制卡状态栏（好感度 / 人物状态，不含战斗） ----------
function renderMechanism(m) {
  var bar = document.getElementById('mechbar');
  if (!bar) return;
  mechSnapshot = m;   // 给剧本预览的条件分支用（见 codexCond）：这里存最近一次机制状态
  var cfg = m && m.config, st = m && m.state;
  var fields = (cfg && cfg.status && cfg.status.fields || []).slice();
  if (!cfg || !st || (!cfg.affection && !fields.length)) {
    bar.style.display = 'none';
    bar.innerHTML = '';
    return;
  }
  bar.style.display = 'flex';
  bar.innerHTML = '';
  var parts = [];
  // ① 好感度栏：进度条
  if (cfg.affection) {
    var hi = cfg.affection.max || 100, lo = cfg.affection.min || 0;
    var cur = st.affection !== undefined ? st.affection : cfg.affection.initial;
    var frac = Math.max(0, Math.min(1, (cur - lo) / Math.max(1, hi - lo)));
    parts.push('<span class="mb-item">[ic:favorite] 好感 <b>' + cur + '</b>/' + hi +
      ' <span class="mb-bar"><i style="width:' + Math.round(frac * 100) + '%"></i></span></span>');
  }
  var stv = st.status || {};
  fields.forEach(function (f) {
    var v = stv[f.key] !== undefined ? stv[f.key] : f.initial;
    if (f.type === 'int') {
      var mn = f.min || 0, mx = f.max || 100;
      var curI = parseInt(v, 10) || 0;
      if (mx > 1000) {
        // 大上限属性（atk/def/spd 等）：数值显示
        parts.push('<span class="mb-item">[ic:swords] ' + escapeHtml(f.name || f.key) + ' <b>' + curI + '</b></span>');
      } else {
        var frac2 = Math.max(0, Math.min(1, (curI - mn) / Math.max(1, mx - mn)));
        parts.push('<span class="mb-item">[ic:swords] ' + escapeHtml(f.name || f.key) + ' <b>' + curI + '</b>/' + mx +
          ' <span class="mb-bar fight"><i style="width:' + Math.round(frac2 * 100) + '%"></i></span></span>');
      }
    } else {
      // ② 人物状态栏：文字
      parts.push('<span class="mb-item">' + escapeHtml(f.name || f.key) + '：<b>' + escapeHtml(String(v)) + '</b></span>');
    }
  });
  bar.innerHTML = parts.join('');
}

function poll() {
  try {
    pywebview.api.poll(lastSeq).then(function (res) {
      if (!res) return;
      if (res.epoch !== undefined && res.epoch !== lastEpoch) {
        lastEpoch = res.epoch;
        document.getElementById('chat').innerHTML = '';
        streamingEl = null;
        lastSeq = 0;
      }
      (res.items || []).forEach(function (m) {
        appendMessage(m);
        if (m.seq > lastSeq) lastSeq = m.seq;
      });
      setStreaming(res.streaming, res.opening_loading);
      document.getElementById('send').disabled = !!res.busy;
      renderChoices(res.choices);
      renderMechanism(res.mechanism);
      renderBattle(res.battle);
      // 分道执行的异步结果从这里回来（jobWait 的 Promise 在这一刻 resolve）
      jobResolveEvents(res.jobs);
    }).catch(function () {});
  } catch (e) {}
}

// Quick Reply：quick_replies.json 里的宏按钮（{player}/{char}/{world}/{random:...} 发送时展开）
function renderQuickReplies() {
  var row = document.getElementById('qrRow');
  if (!row) return;
  row.innerHTML = '';
  try {
    pywebview.api.quick_replies().then(function (list) {
      (list || []).forEach(function (q) {
        var b = document.createElement('button');
        b.className = 'chip';
        b.textContent = q.label || '？';
        b.title = q.text || '';
        b.onclick = function () {
          var input = document.getElementById('input');
          input.value = q.text || '';
          input.focus();
        };
        row.appendChild(b);
      });
    });
  } catch (e) {}
}
