// 黑白图标系统回归测试（node te<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌sts/test_icons.js）
// 覆盖：①index.html 里出现的 UI emoji 全部被 ICONS 收录（注释里的举例不算）
//       ②iconifyText/iconifyUI 真实逻辑（最小 DOM 桩）：行首与句中替换、#chat 保留、
//         SVG/script/textarea 不触碰、幂等、[ic:名字] 具名标记、未收录符号不动
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log('NO_SCRIPT'); process.exit(1); }
const src = m[1];

let fail = 0;
const check = (c, msg) => { if (!c) { fail++; console.log('  FAIL ' + msg); } else console.log('  OK   ' + msg); };

// ============ ① 覆盖率 ============
// 注释里的 emoji（例如 ZWJ 组合的举例）不是界面元素，扫描前先去掉行注释
const ui = html.replace(/^[ \t]*\/\/.*$/gm, '');
const head = src.slice(src.indexOf('var _SVG'), src.indexOf('function iconifyText'));
const sandbox0 = {};
vm.createContext(sandbox0);
vm.runInContext(head + '\n;globalThis.__ICONS = ICONS; globalThis.__NAMED = NAMED_ICONS; globalThis.__RE = _EMOJI_RE; globalThis.__CLS = _EMOJI_CLS;', sandbox0);
const ICONS = sandbox0.__ICONS;
const NAMED = sandbox0.__NAMED;
const RE = sandbox0.__RE;
const CLS = sandbox0.__CLS;

// 纯排版符号（不是"图标"，用字体渲染更稳），以及文档里出现的箭头
const ALLOW = new Set(['▸', '▾', '◀', '▶', '＋', '▣', '↻', '⏎',
  '→', '←', '↑', '↓', '↔', '⇒', '⇐', '⇔']);
const emojiRe = new RegExp(CLS.slice(1, -1), 'gu');
const seen = new Set();
for (const ch of ui.match(emojiRe) || []) {
  const clean = ch.replace(/\uFE0F/g, '');
  if (clean) seen.add(clean);
}
const missing = [...seen].filter(c => !ICONS[c] && !ALLOW.has(c));
check(missing.length === 0, '所有 UI emoji 已覆盖（缺失: ' + JSON.stringify(missing) + '）');
let badSvg = 0;
for (const k of Object.keys(ICONS)) {
  const v = ICONS[k];
  if (typeof v !== 'string' || !v.startsWith('<svg ') || !v.endsWith('</svg>')) badSvg++;
}
check(badSvg === 0, '全部 ' + Object.keys(ICONS).length + ' 个图标均为合法 svg 字符串');
check(Object.keys(NAMED).length >= 3, '具名图标表就绪（' + Object.keys(NAMED).join('/') + '）');
const leading = (s) => {
  const mm = s.match(RE);
  if (!mm) return null;
  return { clean: mm[1].replace(/\uFE0F/g, ''), rest: s.slice(mm[0].length) };
};
check(leading('📂 存档列表').clean === '📂' && ICONS['📂'], '前导 emoji 提取（📂）');
check(leading('⚙️ 设置').clean === '⚙' && ICONS['⚙'], 'FE0F 变体归一（⚙️→⚙）');
check(leading('⏳ 生成中').clean === '⏳' && ICONS['⏳'], '新增范围 2300-23FF 命中（⏳）');
check(leading('普通文本') === null, '无 emoji 不动');

// ============ ② DOM 逻辑（最小桩） ============
function makeEl(sel) {
  const el = {
    nodeType: 1, _sel: sel || [], childNodes: [], parentNode: null,
    innerHTML: '', className: '',
    appendChild(c) { c.parentNode = el; el.childNodes.push(c); return c; },
    insertBefore(n, ref) {
      const i = el.childNodes.indexOf(ref);
      if (i < 0) el.childNodes.push(n); else el.childNodes.splice(i, 0, n);
      n.parentNode = el;
      return n;
    },
    removeChild(n) {
      const i = el.childNodes.indexOf(n);
      if (i >= 0) el.childNodes.splice(i, 1);
      n.parentNode = null;
      return n;
    },
    closest(selList) {
      const list = selList.split(',').map(s => s.trim());
      let cur = el;
      while (cur) {
        if (cur._sel.some(s => list.includes(s))) return cur;
        cur = cur.parentNode;
      }
      return null;
    }
  };
  return el;
}
function makeText(data) { return { nodeType: 3, data, parentNode: null }; }
// icons/<name>.png 覆盖机制用到的 Image：src 一赋值就触发 onerror（等于"没放图片"），图标应保持 SVG
let imgProbes = 0;
function ImageStub() {
  imgProbes++;
  this.alt = ''; this.className = ''; this.onload = null; this.onerror = null; this._src = '';
}
Object.defineProperty(ImageStub.prototype, 'src', {
  get() { return this._src; },
  set(v) { this._src = v; if (this.onerror) this.onerror(); }
});

const ids = {};
function build(id, sel, children) {
  const el = makeEl(sel || []);
  ids[id] = el;
  (children || []).forEach(c => el.appendChild(c));
  return el;
}

const segStart = src.indexOf('var _SVG');
const uiStart = src.indexOf('function iconifyUI', segStart);
const segEnd = src.indexOf('\nfunction ', uiStart + 10);
const engine = src.slice(segStart, segEnd > segStart ? segEnd : src.length);

const sandbox = {
  document: {
    body: null,
    createElement() { return makeEl([]); },
    createTextNode(d) { return makeText(d); },
    getElementById(id) { return ids[id] || null; },
    createTreeWalker(root, what, filter) {
      const out = [];
      (function walk(n) {
        if (n.nodeType === 3) {
          if (filter.acceptNode(n) !== 2) out.push(n);
          return;
        }
        (n.childNodes || []).forEach(walk);
      })(root);
      let i = 0;
      return {
        get currentNode() { return i > 0 ? out[i - 1] : null; },
        nextNode() { return i < out.length ? out[i++] : null; }
      };
    }
  },
  NodeFilter: { SHOW_TEXT: 4, FILTER_REJECT: 2, FILTER_ACCEPT: 1 },
  Image: ImageStub,
  console
};
vm.createContext(sandbox);
vm.runInContext(engine, sandbox);

const textOf = (el) => el.childNodes.map(n => (n.nodeType === 3 ? n.data : '[ic]')).join('');
const countIcons = (el) => el.childNodes.filter(n => n.nodeType === 1 && n.className === 'ic').length;

// 侧栏：行首 emoji
const sidebar = build('sidebar', [], [makeText('📂 存档列表')]);
// 设置模态：句中 emoji（旧实现漏掉的情形）
const settingsModal = build('settingsModal', [], [makeText('点「📁 导入文件夹」选一个目录')]);
// 聊天内容：必须原样保留
const chatMsg = makeText('你好，这是聊天内容 😀 用户发的');
const chatEl = build('chat', ['#chat'], [chatMsg]);
// 节点图：SVG <text> 里塞 span 会渲染不出来，必须不碰
const svgText = makeText('🔀 分支');
const svgEl = build('galGraph', ['svg'], [svgText]);
// 代码/脚本区同理
const scriptText = makeText('// emoji 组合 👨‍👩‍👧 举例');
const scriptEl = build('sc', ['script'], [scriptText]);
// 具名标记 + 未知名 + 未收录符号
const namedEl = build('named', [], [makeText('[ic:go] 围棋 · [ic:nope] 保留 · ☂ 不动')]);
const main = build('main', [], [chatEl, svgEl, scriptEl, namedEl]);
const body = build('body', [], [sidebar, settingsModal, main]);
sandbox.document.body = body;

sandbox.iconifyUI();

check(countIcons(sidebar) === 1 && sidebar.childNodes[1].nodeType === 3 && sidebar.childNodes[1].data === ' 存档列表',
  '侧栏行首 📂 → svg 图标，后续文本保留');
check(countIcons(settingsModal) === 1 && textOf(settingsModal) === '点「[ic] 导入文件夹」选一个目录',
  '句中 emoji 也被替换（📁 → 图标）');
check(chatEl.childNodes[0] === chatMsg && chatMsg.data === '你好，这是聊天内容 😀 用户发的',
  '#chat 内容原样保留');
check(svgEl.childNodes[0] === svgText, 'SVG <text> 内不替换（🔀 留给节点图自己上色）');
check(scriptEl.childNodes[0] === scriptText, 'script 内不替换');
check(countIcons(namedEl) === 1 && textOf(namedEl) === '[ic] 围棋 · [ic:nope] 保留 · ☂ 不动',
  '[ic:go] 具名标记生效；未知名与未收录符号原样保留');

const before = sidebar.childNodes.length;
const probesAfterFirst = imgProbes;
sandbox.iconifyUI();
check(sidebar.childNodes.length === before, '重复 iconifyUI 不叠加（幂等）');
check(imgProbes === probesAfterFirst, 'PNG 槽位负缓存生效（第二遍不再重复探测，' + imgProbes + ' 个槽位）');
check(imgProbes > 0, 'PNG 覆盖机制仍在探测（' + imgProbes + ' 个槽位）');

const plainEl = build('plain', [], []);
const plainText = makeText('普通文本');
plainEl.appendChild(plainText);
sandbox.iconifyText(plainText);
check(plainEl.childNodes[0] === plainText, '无 emoji 文本不动');

const multi = build('multi', [], []);
const multiText = makeText('✅❌ 连续两个');
multi.appendChild(multiText);
sandbox.iconifyText(multiText);
check(countIcons(multi) === 2 && textOf(multi) === '[ic][ic] 连续两个', '连续多个 emoji 逐个拆开替换');

console.log(fail === 0 ? 'ICON_TEST_OK' : 'ICON_TEST_FAIL: ' + fail);
process.exit(fail ? 1 : 0);
