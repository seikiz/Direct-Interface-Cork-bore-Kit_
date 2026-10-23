/* tests/screen_harness.js —— 最小 DOM/桥接替身 + codex/gal 交互 smoke。
 *
 * 为什么手写替身而不是 jsdom：仓库里没有 node_modules（也不该为一次 smoke 引进依赖），
 * 而且这里要验的是「按钮接线 / 节点图坐标 / 保存 → 播放器读到 / 逐行走」这条**逻辑链**，
 * 不需要真的排版。所以替身只做到"代码摸得到、赋值不炸、取得到刚写进去的值"。
 *
 * 跑法：node tests/screen_harness.js
 * 退出码 0 = 全过；非 0 = 有不通过的断言（会打印是哪一条）。
 * 由 tests/test_screen_smoke.py 包一层，接进 tools/run_local_suite.py。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.dirname(__dirname);
const WEB = path.join(ROOT, 'web');

let PASS = 0;
let FAIL = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { PASS++; return true; }
  FAIL++;
  failures.push(name + (detail ? '  ← ' + detail : ''));
  return false;
}

// ===================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌============================= 最小 DOM
function makeDom() {
  const byId = Object.create(null);

  function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.id = '';
    this.className = '';
    this.value = '';
    this.textContent = '';
    this.title = '';
    this.type = '';
    this.checked = false;
    this.disabled = false;
    this.draggable = false;
    this.placeholder = '';
    this.src = '';
    this.srcdoc = '';
    this.parentNode = null;
    this.childNodes = [];
    this.dataset = {};
    this.style = {};
    this._attrs = {};
    this._html = '';
    this._on = {};
    this.classList = {
      _set: {},
      add(c) { this._set[c] = 1; },
      remove(c) { delete this._set[c]; },
      contains(c) { return !!this._set[c]; },
      toggle(c) { if (this._set[c]) { delete this._set[c]; return false; } this._set[c] = 1; return true; }
    };
  }
  Object.defineProperty(El.prototype, 'innerHTML', {
    get() { return this._html; },
    set(v) {
      this._html = String(v == null ? '' : v);
      if (this._html === '') { this.childNodes.length = 0; }
    }
  });
  Object.defineProperty(El.prototype, 'cssText', {
    get() { return this._css || ''; }, set(v) { this._css = String(v); }
  });
  El.prototype.appendChild = function (c) {
    if (!c) { return c; }
    this.childNodes.push(c);
    c.parentNode = this;
    if (c.id && !byId[c.id]) { byId[c.id] = c; }
    return c;
  };
  El.prototype.removeChild = function (c) {
    const i = this.childNodes.indexOf(c);
    if (i >= 0) { this.childNodes.splice(i, 1); c.parentNode = null; }
    return c;
  };
  El.prototype.remove = function () {
    if (this.parentNode) { this.parentNode.removeChild(this); }
    if (this.id) { delete byId[this.id]; }
  };
  El.prototype.setAttribute = function (k, v) {
    this._attrs[k] = String(v);
    if (k === 'id') { this.id = String(v); byId[this.id] = this; }
    if (k === 'data-scene') { this.dataset.scene = String(v); }
  };
  El.prototype.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; };
  El.prototype.hasAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); };
  El.prototype.addEventListener = function (n, f) { (this._on[n] || (this._on[n] = [])).push(f); };
  El.prototype.removeEventListener = function (n, f) {
    const l = this._on[n]; if (!l) { return; }
    const i = l.indexOf(f); if (i >= 0) { l.splice(i, 1); }
  };
  El.prototype.fire = function (n, ev) {
    (this._on[n] || []).slice().forEach(function (f) { f(ev || {}); });
    const h = this['on' + n];
    if (typeof h === 'function') { h.call(this, ev || {}); }
  };
  El.prototype.querySelector = function () { return null; };
  El.prototype.querySelectorAll = function () { return []; };
  El.prototype.getBoundingClientRect = function () { return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; };
  El.prototype.contains = function () { return false; };
  El.prototype.scrollIntoView = function () {};
  El.prototype.focus = function () {};
  El.prototype.click = function () { this.fire('click', { target: this, currentTarget: this, stopPropagation() {} }); };
  Object.defineProperty(El.prototype, 'firstChild', { get() { return this.childNodes[0] || null; } });

  const doc = {
    _byId: byId,
    documentElement: new El('html'),
    body: new El('body'),
    _on: {},
    createElement: function (t) { return new El(t); },
    createElementNS: function (_ns, t) { return new El(t); },
    createTextNode: function (t) { const n = new El('#text'); n.textContent = String(t); n.nodeType = 3; return n; },
    getElementById: function (id) { return byId[id] || null; },
    querySelector: function (sel) {
      if (typeof sel === 'string' && sel.charAt(0) === '#') { return byId[sel.slice(1)] || null; }
      return null;
    },
    querySelectorAll: function () { return []; },
    addEventListener: function (n, f) { (doc._on[n] || (doc._on[n] = [])).push(f); },
    removeEventListener: function (n, f) {
      const l = doc._on[n]; if (!l) { return; }
      const i = l.indexOf(f); if (i >= 0) { l.splice(i, 1); }
    },
    fire: function (n, ev) { (doc._on[n] || []).slice().forEach(function (f) { f(ev || {}); }); },
    elementFromPoint: function () { return null; },
    createTreeWalker: function () { return { nextNode: function () { return false; }, currentNode: null }; }
  };

  /* 片段里的 id 全部登记成元素：本 smoke 只按 id 取元素，不建层级（逻辑链用不到） */
  function absorbFragment(rel, tagHint) {
    const html = fs.readFileSync(path.join(WEB, rel), 'utf8');
    const re = /id="([A-Za-z_][\w-]*)"/g;
    let m;
    while ((m = re.exec(html))) {
      if (!byId[m[1]]) { byId[m[1]] = new El(tagHint || 'div'); byId[m[1]].id = m[1]; }
    }
    return html;
  }
  return { doc, El, absorbFragment, byId };
}

// ================================================================ 沙箱
function makeSandbox(dom) {
  const answers = [];            // prompt 的答案队列
  const log = { alerts: [], confirms: 0, saved: null, api: [] };
  const store = {};

  function syncPromise(value) {
    const p = {
      then: function (fn) {
        const r = fn ? fn(value) : undefined;
        return r && r.then ? r : p;
      },
      catch: function () { return p; }
    };
    return p;
  }

  const api = {
    codex_list: function () { log.api.push('list'); return syncPromise({ ok: true, packages: [{ name: 'demo', sprites: 1, bg: 1, bgm: 0, voice: 0, scenes: 2, has_script: true }] }); },
    codex_get: function () { log.api.push('get'); return syncPromise({ ok: true, valid: true, script: log.saved || null }); },
    codex_save: function (name, json) { log.api.push('save'); log.saved = JSON.parse(json); return syncPromise({ ok: true, valid: true, issues: [] }); },
    codex_create: function (n) { return syncPromise({ ok: true, name: n }); },
    codex_analyze: function () { return syncPromise({ ok: true, stats: { scenes: 1, lines: 1 } }); },
    codex_script_files: function () { return syncPromise({ ok: true, files: { sprites: [], bg: [], bgm: [], voice: [] } }); },
    codex_run_action: function () { return syncPromise({ ok: true }); },
    codex_volume: function () { return syncPromise({ ok: true }); },
    codex_fullscreen: function () { return syncPromise({ ok: true }); },
    codex_pack: function () { return syncPromise({ ok: true, counts: {}, size: 0, rel: 'x.html', path: '' }); },
    codex_pack_exe: function () { return syncPromise({ ok: false, err: 'skip' }); },
    codex_export_player: function () { return syncPromise({ ok: false, err: 'cancelled' }); }
  };

  const win = {
    console: console,
    document: dom.doc,
    pywebview: { api: api },
    alert: function (m) { log.alerts.push(String(m)); },
    confirm: function () { log.confirms++; return true; },
    prompt: function () { return answers.length ? answers.shift() : null; },
    setTimeout: function (fn) { fn(); return 0; },          // 同步：打字机/等待一步到底，终止条件靠脚本本身
    clearTimeout: function () {},
    setInterval: function () { return 0; },
    clearInterval: function () {},
    requestAnimationFrame: function (fn) { fn(); return 1; },
    cancelAnimationFrame: function () {},
    localStorage: {
      _d: store,
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
      setItem: function (k, v) { store[k] = String(v); }
    },
    Audio: function () { return { play: function () { return syncPromise(); }, pause: function () {} }; },
    innerWidth: 1280, innerHeight: 800,
    navigator: { userAgent: 'node' },
    location: { href: 'file:///web/index.html' },
    JSON: JSON, Math: Math, Object: Object, Array: Array, String: String, Number: Number,
    Date: Date, RegExp: RegExp, Error: Error, isNaN: isNaN, parseInt: parseInt, parseFloat: parseFloat,
    encodeURIComponent: encodeURIComponent, decodeURIComponent: decodeURIComponent
  };
  win.window = win;
  win.globalThis = win;
  win.global = win;

  /* 外壳里的工具函数（不在搬走的块里，但被它调用）：直接从 index.html 抠出来，保证是同一份实现。
   * escapeHtml 依赖 stripInvisible + ZW_RE，一起抠 —— 少抠一个就会在 smoke 里当场 ReferenceError。 */
  // 前端已拆分：index.html + js/chat-inline-*.js（工具函数在同目录的分段脚本里）
  let indexHtml = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
  const jsDir = path.join(WEB, 'js');
  for (const f of fs.readdirSync(jsDir).sort()) {
    if (f.startsWith('chat-inline') && f.endsWith('.js')) {
      indexHtml += '\n' + fs.readFileSync(path.join(jsDir, f), 'utf8');
    }
  }
  const zw = /var ZW_RE = [\s\S]*?\n/.exec(indexHtml);
  const strip = /function stripInvisible\([\s\S]*?\n\}/.exec(indexHtml);
  const esc = /function escapeHtml\([\s\S]*?\n\}/.exec(indexHtml);
  if (!zw || !strip || !esc) { throw new Error('index.html 里找不到 ZW_RE / stripInvisible / escapeHtml'); }
  vm.runInNewContext(zw[0] + strip[0] + '\n' + esc[0] + '\nthis.__escapeHtml = escapeHtml;', win);

  const ctx = vm.createContext(win);
  return { ctx, win, log, answers, api };
}

function load(ctx, rel) {
  const p = path.join(WEB, rel);
  vm.runInContext(fs.readFileSync(p, 'utf8'), ctx, { filename: rel });
}

// ================================================================ 主流程
function main() {
  const dom = makeDom();
  const { doc, El } = dom;
  dom.absorbFragment('screens/codex.html');
  dom.absorbFragment('screens/gal.html');
  /* 外壳里被这一屏摸到的两个 id（侧栏按钮 + 别的屏的容器不在此列） */
  ['btnCodex', 'chat'].forEach(function (id) { if (!dom.byId[id]) { dom.byId[id] = new El('div'); dom.byId[id].id = id; } });

  const box = makeSandbox(dom);
  const ctx = box.ctx;

  /* 加载顺序**从 index.html 里读**：脚本标签漏一个/排错位置，这个 smoke 直接红
   * （只挑本屏需要的：状态/路由/数据层 + codex/gal 的屏模块）。 */
  const indexSrc = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
  const wanted = [];
  const tagRe = /<script\s+src="([^"]+)"><\/script>/g;
  let t;
  while ((t = tagRe.exec(indexSrc))) {
    const s = t[1];
    if (s === 'js/state.js' || s === 'js/router.js' || s.startsWith('js/store/')
      || /^js\/screens\/(codex|gal)-/.test(s)) {
      wanted.push(s);
    }
  }
  check('index.html 里的屏模块脚本都被找到（4 个基础 + 12 个屏模块 = 16）', wanted.length === 16,
    '实际 ' + wanted.length + '：' + wanted.join(' '));
  wanted.forEach(function (f) { load(ctx, f); });
  check('16 个脚本按 index.html 的顺序加载无异常', true);
  check('CodexPlayer 命名空间已建立', typeof box.win.CodexPlayer === 'object' && typeof box.win.CodexPlayer.play === 'function');
  check('CodexPlayer 两半都挂上了', typeof box.win.CodexPlayer.next === 'function' && typeof box.win.CodexPlayer.setBg === 'function');
  check('GalScreen 已注册', typeof box.win.GalScreen === 'object' && typeof box.win.GalScreen.mount === 'function');
  check('旧全局名仍是门面', typeof box.win.codexPlay === 'function' && typeof box.win.galSave === 'function' && typeof box.win.galToast === 'function');

  /* ---- 挂载：片段到位后按钮才接线 ---- */
  box.win.CodexScreen.mount();
  box.win.GalScreen.mount();
  check('codex 挂载后按钮已接线', typeof doc.getElementById('codexNewBtn').onclick === 'function');
  check('gal 挂载后按钮已接线', typeof doc.getElementById('galSaveBtn').onclick === 'function');
  check('播放器容器初始不显示', doc.getElementById('codexPlayer').style.display !== 'block');

  /* ---- 1. 编辑器：打开一个包 ---- */
  box.win.codexCur = 'demo';
  box.log.saved = {
    name: 'demo', intro: '测试剧本', scenes: [
      { id: 's1', title: '开场', lines: [{ kind: 'say', text: '第一行' }, { kind: 'say', text: '第二行' }, { kind: 'choice', choice: [{ text: '去 s2', goto: 's2' }] }] },
      { id: 's2', title: '结局', lines: [{ kind: 'say', text: '到了 s2' }] }
    ]
  };
  box.win.galOpenEditor('demo');
  check('galOpenEditor 真的读到了剧本', box.win.galScript && box.win.galScript.scenes.length === 2);
  check('galStats 写上了线/点数', /线 2/.test(doc.getElementById('galStats').textContent));

  /* ---- 2. 加一条线（节点） ---- */
  box.answers.push('第三条线');
  box.win.galAddLine();
  check('加线后场景数 = 3', box.win.galScript.scenes.length === 3);
  const newId = box.win.galScript.scenes[2].id;
  check('新线 id 是 s3', newId === 's3', newId);
  check('加线后统计刷新', /线 3/.test(doc.getElementById('galStats').textContent));

  /* ---- 3. 拖节点（坐标算法）+ 连线（分支） ---- */
  const sc3 = box.win.galScript.scenes[2];
  box.win.galNodeDown({ button: 0, stopPropagation: function () {}, clientX: 100, clientY: 100 }, sc3.id, 40, 30);
  box.win.galNodeMove({ clientX: 160, clientY: 130 });
  box.win.galNodeUp({});
  check('拖动把 dx/dy 记进 gx/gy', sc3.gx === 100 && sc3.gy === 60, sc3.gx + ',' + sc3.gy);
  box.win.galConnectScene('s1', 's3');
  const s1 = box.win.galScript.scenes[0];
  const hasChoice = (s1.lines || []).some(function (l) { return l && l.choice && l.choice.some(function (o) { return o.goto === 's3'; }); });
  check('连线后 s1 多了一条指向 s3 的选项', hasChoice);
  // 替身里的 setTimeout 是同步执行的，所以 galToast 的"1.6 秒后淡出"会立刻跑完；
  // 这里只验它确实被调过（文案），不验显示时长（那是真实浏览器的事）。
  check('连线后有 toast 反馈', /选项分支/.test(doc.getElementById('galToast').textContent),
    doc.getElementById('galToast').textContent);

  /* ---- 4. 保存：GAL → 编年史的 JSON 面板（跨屏只走 bus） ---- */
  box.win.galSave();
  check('保存真的写到了后端', box.log.saved && box.log.saved.scenes.length === 3);
  check('保存后 codex 的 JSON 面板已同步', JSON.parse(doc.getElementById('codexJsonInput').value).scenes.length === 3);
  check('保存有 toast', /已保存/.test(doc.getElementById('galToast').textContent));

  /* ---- 5. 播放器：开播 + 逐行走 ---- */
  box.win.codexCur = 'demo';
  box.win.galPlayerHidden = doc.getElementById('galEditor').style.display === 'none';
  box.win.galPlay();                    // 预览：先存盘 → 关编辑器 → bus 'codex:play'
  check('预览关掉了 GAL 编辑器', doc.getElementById('galEditor').style.display === 'none');
  check('播放器运行时已建立', box.win.codexPlayer && box.win.codexPlayer.scenes.length === 3);
  check('播放器容器由编辑器订阅点亮', doc.getElementById('codexPlayer').style.display === 'block');
  check('标题页写了剧本名', doc.getElementById('cxTitleName').textContent === 'demo');
  check('章节列表列出 3 条线', doc.getElementById('cxChapterList').childNodes.length === 3);

  doc.getElementById('cxTitle').onclick();          // 点标题页 → 从第一条线开始
  check('第一行的字打完了', doc.getElementById('cxText').textContent === '第一行', doc.getElementById('cxText').textContent);
  check('说话人为空时不显示名牌', doc.getElementById('cxSpeaker').style.display === 'none');
  box.win.codexNextLine();
  check('第二行', doc.getElementById('cxText').textContent === '第二行', doc.getElementById('cxText').textContent);
  box.win.codexNextLine();                           // 走到选项
  const cxChoice = doc.getElementById('cxChoice');
  check('选项面板显示', cxChoice.style.display === 'block');
  check('选项按钮数 = 2（去 s2 / 去 s3）', cxChoice.childNodes.length === 2, String(cxChoice.childNodes.length));
  check('出现选项时记住了回溯点', !!(box.win.codexPlayer.lastChoicePoint && box.win.codexPlayer.lastChoicePoint.sceneId === 's1'));

  /* ---- 6. 回溯：回到选项点 ---- */
  box.win.codexRewind();
  check('回溯后仍停在 s1 的选项前', box.win.codexPlayer.curSceneId === 's1');
  check('回溯又给出选项', doc.getElementById('cxChoice').childNodes.length === 2);

  /* ---- 7. 选项 → 跳转 ---- */
  doc.getElementById('cxChoice').childNodes[1].onclick();   // 第二项 = 去 s3
  check('点选项跳到 s3', box.win.codexPlayer.curSceneId === 's3', box.win.codexPlayer.curSceneId);
  box.win.codexNextLine();                                   // s3 只有一行 → 播完 → 结局
  check('走完线后出结局页', doc.getElementById('cxEnd').style.display === 'flex');
  check('结局页有标题', doc.getElementById('cxEndTitle').textContent === '完结', doc.getElementById('cxEndTitle').textContent);

  /* ---- 8. 存档 / 读档 ---- */
  box.win.codexSaveSlot();
  check('存档写进了 localStorage', !!box.win.localStorage.getItem('codex_save_demo'));
  box.win.codexLoadSlot();
  check('读档没有弹"损坏"', box.log.alerts.length === 0, box.log.alerts.join('|'));

  /* ---- 9. 退出：容器回到编辑器手里 ---- */
  box.win.codexPlayerExit();
  check('退出后播放器容器隐藏', doc.getElementById('codexPlayer').style.display === 'none');
  check('退出后运行时清空', box.win.codexPlayer === null);

  /* ---- 10. 反向：编辑器 → GAL 的入口只发事件 ---- */
  const before = doc.getElementById('galEditor').style.display;
  doc.getElementById('codexEditBtn').onclick();             // codexEdit → bus 'gal:open-editor'
  check('编辑器能通过事件打开 GAL（设置被改回 flex）', before === 'none' && doc.getElementById('galEditor').style.display === 'flex');
  check('侧栏按钮也走事件打开 GAL', (function () {
    doc.getElementById('btnCodex').onclick();
    return doc.getElementById('galEditor').style.display === 'flex';
  })());

  /* ---- 11. 关闭编辑器不再抛 ---- */
  doc.getElementById('galCloseBtn').onclick();
  check('GAL 关闭后 display=none', doc.getElementById('galEditor').style.display === 'none');

  console.log('');
  failures.forEach(function (f) { console.log('  [FAIL] ' + f); });
  console.log('通过 ' + PASS + ' / 失败 ' + FAIL);
  return FAIL ? 1 : 0;
}

process.exit(main());
