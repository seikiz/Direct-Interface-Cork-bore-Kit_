// 黑白图标系统回归测试（node tests/test_icons.js）
// 覆盖：①文件内所有 emoji 已被 ICONS 覆盖（或是有意保留的符号）
//       ②iconifyText/iconifyUI 真实逻辑（最小 DOM 桩）：替换前导 emoji、
//         保留 #chat 内容、幂等、未收录符号不动
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
const head = src.slice(src.indexOf('var _SVG'), src.indexOf('function iconifyText'));
const sandbox0 = {};
vm.createContext(sandbox0);
vm.runInContext(head + '\n;globalThis.__ICONS = ICONS; globalThis.__RE = _EMOJI_RE;', sandbox0);
const ICONS = sandbox0.__ICONS;
const RE = sandbox0.__RE;

const ALLOW = new Set(['✕', '☰', '★', '▸', '▾', '◀', '▶', '↻', '＋', '📦', '😏']);
const emojiRe = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}\u{20E3}\u{1F1E6}-\u{1F1FF}]/gu;
const seen = new Set();
for (const ch of html.match(emojiRe) || []) {
  const clean = ch.replace(/\uFE0F/g, '');
  if (clean) seen.add(clean);
}
const missing = [...seen].filter(c => !ICONS[c] && !ALLOW.has(c));
check(missing.length === 0, '所有 emoji 已覆盖（缺失: ' + JSON.stringify(missing) + '）');
let badSvg = 0;
for (const k of Object.keys(ICONS)) {
  const v = ICONS[k];
  if (typeof v !== 'string' || !v.startsWith('<svg ') || !v.endsWith('</svg>')) badSvg++;
}
check(badSvg === 0, '全部 ' + Object.keys(ICONS).length + ' 个图标均为合法 svg 字符串');
const leading = (s) => {
  const mm = s.match(RE);
  if (!mm) return null;
  return { clean: mm[1].replace(/\uFE0F/g, ''), rest: s.slice(mm[0].length) };
};
check(leading('📂 存档列表').clean === '📂' && ICONS['📂'], '前导 emoji 提取（📂）');
check(leading('⚙️ 设置').clean === '⚙' && ICONS['⚙'], 'FE0F 变体归一（⚙️→⚙）');
check(leading('✕ 移除').clean === '✕' && !ICONS['✕'], '未收录符号 ✕ 不替换');
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
        n.childNodes.forEach(walk);
      })(root);
      let i = 0;
      return {
        get currentNode() { return i > 0 ? out[i - 1] : null; },
        nextNode() { return i < out.length ? out[i++] : null; }
      };
    }
  },
  NodeFilter: { SHOW_TEXT: 4, FILTER_REJECT: 2, FILTER_ACCEPT: 1 },
  console
};
vm.createContext(sandbox);
vm.runInContext(engine, sandbox);

const chatMsg = makeText('你好，这是聊天内容 😀 用户发的');
const chatEl = build('chat', ['#chat'], [chatMsg]);
build('sidebar', [], [makeText('📂 存档列表')]);
build('settingsModal', [], [makeText('🧮 上下文预算')]);
build('main', [], [chatEl]);

sandbox.iconifyUI();

const sib = ids['sidebar'].childNodes[0];
check(sib.nodeType === 1 && sib.className === 'ic' && /<svg /.test(sib.innerHTML), '侧栏 📂 → svg 图标');
check(ids['sidebar'].childNodes[1].nodeType === 3 && ids['sidebar'].childNodes[1].data === ' 存档列表', '图标后文本保留');
check(ids['settingsModal'].childNodes[0].className === 'ic', '设置模态 🧮 → svg 图标');
check(chatEl.childNodes[0].nodeType === 3 && chatEl.childNodes[0].data === '你好，这是聊天内容 😀 用户发的', '#chat 内容原样保留');
const before = ids['sidebar'].childNodes.length;
sandbox.iconifyUI();
check(ids['sidebar'].childNodes.length === before, '重复 iconifyUI 不叠加');

const plainEl = build('plain', [], []);
const plainText = makeText('普通文本');
plainEl.appendChild(plainText);
sandbox.iconifyText(plainText);
check(plainEl.childNodes[0] === plainText, '无 emoji 文本不动');

const xEl = build('xbox', [], []);
const xText = makeText('✕ 移除');
xEl.appendChild(xText);
sandbox.iconifyText(xText);
check(xEl.childNodes[0] === xText, '未收录符号 ✕ 保留');

console.log(fail === 0 ? 'ICON_TEST_OK' : 'ICON_TEST_FAIL: ' + fail);
process.exit(fail ? 1 : 0);
