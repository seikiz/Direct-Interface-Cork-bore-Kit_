/* tests/card_view_harness.js —— 工坊卡片外显（网页端渲染器）的行为探针
 *
 * 为什么要有它：`tests/test_card_view.py` 能静态查「有没有把 JSON 字符串化显示」，
 * 但查不出「渲染出来是不是真的像张卡」——那要真的跑一遍渲染器。这里用 Node 把
 * `web/card_fields.js`（字段表）+ `web/js/screens/ws.js`（渲染器）加载起来，
 * 喂几份真实形状的卡，把渲染结果以 JSON 吐给 Python 断言。
 *
 * 只 stub 三样东西（渲染器的 cardHtml 是纯函数，本来就不碰 DOM / 网络）：
 *   · window/DICK —— 模块顶部要注册路由与 state 绑定；
 *   · pywebview  —— 只在按钮回调里用，这里不会被调用；
 *   · document   —— 只有 wsCardPaint 用；cardHtml 不走它，给个空壳就够。
 *
 * 用法：node tests/card_view_harness.js   → 打印 JSON（Python 侧断言）
 *                                         出错退出码 1（Python 会把它当 FAIL 打出来）
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);

// ---- 最小 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌stub ----
global.window = global;
global.DICK = {
  state: { bindGlobal: function () { } },
  router: { register: function () { } },
};
global.pywebview = { api: {} };
global.document = {
  getElementById: function () { return null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return {}; },
};
// escapeHtml：与 web/index.html 里的实现同语义（先 & 再尖括号引号）
global.escapeHtml = function (s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};

// ---- 加载真实产物：文案表 → 字段表 → 渲染器 ----
require(path.join(ROOT, 'web', 'i18n.js'));
require(path.join(ROOT, 'web', 'card_fields.js'));
require(path.join(ROOT, 'web', 'js', 'screens', 'ws.js'));

const Ws = global.WsScreen;
if (!Ws || typeof Ws.cardHtml !== 'function') {
  console.error('渲染器没有导出 cardHtml（web/js/screens/ws.js 底部 return 块）');
  process.exit(1);
}

// ---- 用例：形状照真实的卡来（角色卡 / 世界卡包 / 坏 JSON / 数组 JSON）----
const ROLE = {
  name: '测试角色卡',
  system_prompt: '第一段：他是谁。\\n\\n第二段：他从哪来。\\n\\n第三段：他在做什么。',
  personality: '冷静，话少，先看再动。',
  appearance: '黑色短发，左手腕有一道旧伤。',
  first_mes: '「你来了。」\\n他抬起眼。',
  legacy: '来自旧版存档',
  unlocked: true,
  card_data: { spec: 'chara_card_v2', data: { name: '测试角色卡' } },
  history_tree: { nodes: [], root_id: 'n1' },
  unknown_block: { alpha: '甲', beta: '乙' },
  unknown_list: ['一', '二', '三'],
};

const WORLD = {
  name: '测试世界卡',
  description: '世界简介。',
  params: { era: '明末', space: '江南水乡', era_kind: '古代' },
  rules: ['规则一', '规则二', '规则三'],
  entries: [{ keywords: ['甲'], content: '内容一' }, { keywords: ['乙'], content: '内容二' }],
  author: '测试作者',
};

// 长正文：用来验证 8 行折叠（10 段 = 10 行 > 8）
const LONG = { name: '长正文卡' };
LONG.system_prompt = Array.from({ length: 10 }, (_, i) => '第' + (i + 1) + '行正文。').join('\\n\\n');

const CASES = [
  { key: 'role', text: JSON.stringify(ROLE), file: '测试角色卡.json' },
  { key: 'world', text: JSON.stringify(WORLD), file: '测试世界卡.json' },
  { key: 'long', text: JSON.stringify(LONG), file: '长正文卡.json' },
  { key: 'broken', text: '这不是 JSON，只是一段原文。\\n\\n第二段原文。', file: '坏文件.json' },
  { key: 'array', text: '[1,2,3]', file: '数组.json' },
  { key: 'empty', text: '', file: '空文件.json', err: '文件不存在' },
];

function renderAll(lang) {
  global.T = (global.DICK_I18N && (global.DICK_I18N[lang] || global.DICK_I18N.zh)) || {};
  const out = {};
  CASES.forEach(function (c) {
    out[c.key] = Ws.cardHtml(c.text, c.file, c.err || '');
  });
  return out;
}

const result = {
  langs: ['zh', 'ja'],
  zh: renderAll('zh'),
  ja: renderAll('ja'),
  sections: (global.DICK_CARD_FIELDS || {}).sections || [],
  collapseLines: (global.DICK_CARD_FIELDS || {}).collapseLines,
};
process.stdout.write(JSON.stringify(result, null, 1) + '\n');
