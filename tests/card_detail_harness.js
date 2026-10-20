/* tests/card_detail_harness.js —— 工坊「卡片详情」渲染器的行为探针
 *
 * 为什么要有它：`tests/test_card_detail.py` 能静态查「字段表是不是只有一份」「有没有把 JSON
 * 原文摊出来」，但查不出「每个分区是不是真的画出来了」「详情是不是真的不折叠」——那要真的跑
 * 一遍渲染器。这里用 Node 把 `web/i18n.js`（文案）+ `web/card_fields.js`（字段表）+
 * `web/js/screens/ws-detail.js`（渲染器）加载起来，喂几份真实形状的卡，把渲染结果以 JSON
 * 吐给 Python 断言。
 *
 * 只 stub 四样东西（渲染器纯函数不碰 DOM / 网络）：
 *   · window / DICK（state / router / bus）—— 模块加载时会挂 bus 订阅；
 *   · document —— 只有 paint() 用，render() 不走它；
 *   · escapeHtml —— 与 web/index.html 的同名函数同语义；
 *   · T —— 取 web/i18n.js 的 zh 表（换语言只影响标签文案，不影响结构）。
 *
 * 反向验证入口：环境变量 `DETAIL_MUTATE="旧串=>新串"` 会先在内存里改一份模块源码再执行
 * （不落盘、不留临时文件）。`test_card_detail.py` 用它做「删一个 section 渲染 → 必须判红」。
 *
 * 用法：node tests/card_detail_harness.js   → 打印 JSON（Python 侧断言）
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.dirname(__dirname);

// ---- 最小 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌stub ----
global.window = global;
global.DICK = {
  state: { bindGlobal: function () {}, get: function () {}, set: function () {} },
  router: { register: function () {} },
  bus: { on: function () {}, emit: function () { return 0; } },
};
global.pywebview = { api: {} };
global.document = {
  getElementById: function () { return null; },
  addEventListener: function () {},
  createElement: function () { return {}; },
};
// escapeHtml：与 web/index.html 同语义（先 & 再尖括号；属性位不用它）
global.escapeHtml = function (s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
};

// ---- 加载真实产物：文案表 → 字段表 ----
require(path.join(ROOT, 'web', 'i18n.js'));
require(path.join(ROOT, 'web', 'card_fields.js'));
global.T = global.DICK_I18N.zh;

// ---- 加载渲染器（可选做一次内存变异） ----
const DJS = path.join(ROOT, 'web', 'js', 'screens', 'ws-detail.js');
let code = fs.readFileSync(DJS, 'utf8');
const mut = process.env.DETAIL_MUTATE || '';
if (mut) {
  const parts = mut.split('=>');
  const from = parts[0], to = parts[1] === undefined ? '' : parts[1];
  if (code.indexOf(from) < 0) {
    console.error('MUTATE_ANCHOR_NOT_FOUND: ' + from);
    process.exit(2);
  }
  code = code.replace(from, to);
}
vm.runInThisContext(code, { filename: 'ws-detail.js' });
const D = global.WsDetail;
if (!D || typeof D.render !== 'function') {
  console.error('渲染器没有导出 render（web/js/screens/ws-detail.js 底部 return 块）');
  process.exit(1);
}

const F = global.DICK_CARD_FIELDS || {};

// ---- 造卡：**每个分区**都填上（键名全部从字段表里取，探针自己也不写字段名）----
function setPath(obj, p, v) {
  const parts = String(p).split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') { cur[parts[i]] = {}; }
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = v;
}

const FULL = { name: '测试角色卡' };
(F.sections || []).forEach(function (sec) {
  (sec.keys || []).forEach(function (k) {
    let v;
    if (sec.mode === 'body') { v = '【' + sec.id + '·' + k + '】第一段。\\n\\n第二段。'; }
    else if (sec.mode === 'list') { v = ['条目甲-' + sec.id, '条目乙-' + sec.id]; }
    else { v = '值-' + sec.id + '-' + k; }
    setPath(FULL, k, v);
  });
});
// 抬头用的三个"按语义取"的字段（标签表里登记过的键，值随便换一份更像真的）
FULL.author = 'seiki';
FULL.version = '1.0';
FULL.tags = ['病娇', '腹黑'];
// 三块 extras 的数据
FULL.world_entries = [
  { name: '咖啡馆', keys: ['咖啡'], content: '这家咖啡馆叫「蓝猫」，是主角的秘密基地。', enabled: true },
  { name: '老板娘', keys: ['老板娘'], content: '老板娘叫玲子，喜欢猫。' },
  { name: '学校', keys: ['学校'], content: '学校在河边，放学后很安静。' },
];
FULL.advanced = { mechanics: {
  affection: { enabled: true, initial: 51, min: 0, max: 100 },
  status: { enabled: true, fields: [{ key: 'mood', initial: '平静' }, { key: 'hp', initial: 100 }] },
  events: [{ id: 'confess', aff_ge: 80 }],
} };
// 隐藏槽 + 未知键（前者不许出现，后者进「其它信息」）
FULL.card_data = { spec: 'chara_card_v2', data: { name: '测试角色卡' } };
FULL.history_tree = { nodes: [], root_id: 'n1' };
FULL._meta = { v: 1 };
FULL.legacy = '来自旧版存档';
FULL.unknown_list = ['一', '二', '三'];

// 长正文：30 段（详情必须全画出来，不折叠）
function longText(n) {
  const out = [];
  for (let i = 1; i <= n; i++) { out.push('第' + i + '段正文。'); }
  return out.join('\\n\\n');
}
const LONG = { name: '长正文卡', system_prompt: longText(30) };

// 世界书 250 条：只画前 200 条 + 「还有 50 条」
const MANY = { name: '多条目卡' };
MANY.world_entries = [];
for (let i = 1; i <= 250; i++) {
  MANY.world_entries.push({ name: '条目' + i, keys: ['词' + i], content: '第' + i + '条内容。' });
}

// 字符串里包着 JSON（世界卡包的 params.space 就这么存）
const JSONSTR = { name: '字符串卡', params: { space: '{"places":[{"name":"宿舍","minutes":0}]}' } };

const CASES = {
  full: { text: JSON.stringify(FULL), file: '咲.json', rtype: '角色卡' },
  long: { text: JSON.stringify(LONG), file: '长正文卡.json', rtype: '角色卡' },
  many: { text: JSON.stringify(MANY), file: '多条目.json', rtype: '世界卡' },
  jsonstr: { text: JSON.stringify(JSONSTR), file: '字符串卡.json', rtype: '世界卡包' },
  broken: { text: '这不是 JSON，只是一段原文。\\n\\n第二段原文。', file: '坏卡.json', rtype: '角色卡' },
  empty: { text: '', file: '空卡.json', rtype: '角色卡', err: '文件不存在' },
};

const out = { mutated: mut || null, cases: {}, sections: [], fieldsVersion: F.version };
Object.keys(CASES).forEach(function (k) { out.cases[k] = D.render(CASES[k]); });
(F.sections || []).forEach(function (s) { out.sections.push(s.id); });

// ---- DOM 冒烟：真的点一下（最小 fake DOM，不连浏览器）----
// 探针要证明的不是"代码里有 onclick 这几个字"，而是 open() 之后 DOM 真的变了、
// Esc / 遮罩 / 关闭三种方式真的能关、点 extras 标题真的会展开、底部按钮真的发事件。
const els = {};
['wsDetailModal', 'wsDetailHead', 'wsDetailBody', 'wsDetailAvatar', 'wsDetailClose',
 'wsDetailImport', 'wsDetailExport', 'wsDetailDelete', 'wsDetailUpload'].forEach(function (id) {
  els[id] = {
    id: id, innerHTML: '', scrollTop: 0, onclick: null, _cls: {},
    classList: {
      add: function (c) { els[id]._cls[c] = 1; },
      remove: function (c) { delete els[id]._cls[c]; },
      contains: function (c) { return !!els[id]._cls[c]; }
    }
  };
});
const events = [];
const keyFns = [];
global.DICK.bus.emit = function (name, payload) { events.push([name, payload || null]); return 1; };
global.document = {
  getElementById: function (id) { return els[id] || null; },
  addEventListener: function (type, fn) { if (type === 'keydown') { keyFns.push(fn); } },
};
function isOpen() { return els.wsDetailModal.classList.contains('open'); }
function clickExtras(id) {
  els.wsDetailBody.onclick({
    target: { closest: function () { return { getAttribute: function () { return id; } }; } }
  });
}
const smoke = { painted: false, escClosed: false, maskClosed: false, btnClosed: false,
                expanded: false, collapsed: false, events: [] };
D.open(CASES.full);
smoke.painted = isOpen() && els.wsDetailBody.innerHTML.indexOf('ws-detail-sec') >= 0
  && els.wsDetailHead.innerHTML.indexOf('测试角色卡') >= 0;
keyFns.forEach(function (fn) { fn({ key: 'Escape' }); });
smoke.escClosed = !isOpen();
D.open(CASES.full);
els.wsDetailModal.onclick({ target: els.wsDetailModal });
smoke.maskClosed = !isOpen();
D.open(CASES.full);
els.wsDetailClose.onclick();
smoke.btnClosed = !isOpen();
D.open(CASES.full);
smoke.expanded0 = els.wsDetailBody.innerHTML.indexOf('class="ws-detail-x-body">') < 0;
clickExtras('world');
smoke.expanded = els.wsDetailBody.innerHTML.indexOf('class="ws-detail-x-body">') >= 0;
clickExtras('world');
smoke.collapsed = els.wsDetailBody.innerHTML.indexOf('class="ws-detail-x-body">') < 0;
els.wsDetailExport.onclick();
els.wsDetailDelete.onclick();
els.wsDetailUpload.onclick();
els.wsDetailImport.onclick();
smoke.events = events.map(function (e) { return [e[0], e[1] && e[1].action ? e[1].action : null]; });
out.smoke = smoke;

process.stdout.write(JSON.stringify(out, null, 1) + '\n');
