/* web/js/screens/ws-detail.js —— 创意工坊「卡片详情」弹窗（2026-12）
 * 用户：「给创意工坊加一个详细功能吧，点角色卡会有详细的东西。」
 * 窄条预览（#wsPreview）正文超 8 行就折叠、世界书 / 机制 / 文件都不显示，看不全一张卡；
 * 这里给一张卡开独立弹窗：抬头（头像 / 标题 / 作者·版本·类型 / #标签）+ 各分区全文
 * （**不折叠**）+ 世界书 / 机制 / 文件三块（点标题展开）+ 底部动作。
 * 三条硬规矩（tests/test_card_detail.py 盯着）
 * ① 字段清单只有一份真相：分区 / 键 / 标签 / 阈值全从 window.DICK_CARD_FIELDS 读（生成物，
 *    源头 design/card_fields.json）；本文件不写任何字段名 —— 键靠点号路径从表里取，标签走
 *    DICK_CARD_FIELD_LABEL，作者 / 版本 / 标签按标签文案反查，抄不出第二份字段表。
 * ② 界面不出现 JSON 原文：没有 JSON.stringify / <pre> / 大括号 / 引号；字符串里包着 JSON 的
 *    （世界卡包的 params.space）只报「对象 · N 项」。
 * ③ 屏间只经 DICK.bus：原文由 ws.js 发来（'ws:detail:open'），底部动作只发事件
 *    （'card:import' 归外壳、'ws:detail:action' 回本屏已有的按钮），不摸别屏的 id。
 * 归属：结构 web/screens/ws.html 的 #wsDetailModal；样式 web/styles/screens/ws-detail.css。 */
window.WsDetail = (function (global) {
  'use strict';

  var MAX_ENTRIES = 200;      // 世界书只画前 200 条，剩下的报「还有 N 条」
  var bound = false;          // 遮罩 / 关闭 / 四个动作 / Esc 只绑一次
  var cur = null;             // 当前模型（关窗即释放）
  var opened = {};            // 三块 extras 的展开态（默认全收起）

  /* ---------- 取值与展示的小工具（纯函数） ---------- */
  function cfg() { return global.DICK_CARD_FIELDS || {}; }
  function labelOf(id) { try { return global.DICK_CARD_LABEL(id) || ''; } catch (e) { return ''; } }
  function fieldLabel(key) { try { return global.DICK_CARD_FIELD_LABEL(key) || ''; } catch (e) { return ''; } }
  function esc(s) { return escapeHtml(s === null || s === undefined ? '' : s); }
  function norm(v) {          // 卡片把换行存成字面 \n 两个字符 → 还原真换行，再掐掉行尾空白
    var s = (v === null || v === undefined) ? '' : String(v);
    return s.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\t/g, '\t')
      .replace(/[ \t]+\n/g, '\n').replace(/\s+$/, '');
  }
  function paras(text) {      // 正文 → 段落（空行分段；段内单换行保留）
    var blocks = norm(text).split(/\n[ \t]*\n+/), out = [], i, b;
    for (i = 0; i < blocks.length; i++) { b = blocks[i].trim(); if (b) { out.push(b); } }
    return out;
  }
  function oneLine(s, max) {   // 压成一行 + 截断（两列视图用）
    var t = String(s).replace(/\s*\n\s*/g, ' ').replace(/\s+/g, ' ');
    return (max > 0 && t.length > max) ? (t.slice(0, max) + '…') : t;
  }
  /* 标量 → 文本（布尔走三语文案）；容器返回 null（交给 countText，绝不打花括号） */
  function scalar(v) {
    var t = typeof v, tt = global.T || {};
    if (t === 'string') { return norm(v); }
    if (t === 'number') { return String(v); }
    if (t === 'boolean') { return v ? (tt.card_yes || '') : (tt.card_no || ''); }
    return null;
  }
  function jsonOf(text) {     // 字符串里包着 JSON（世界卡包的 params.space 就是）→ 解出容器
    var t = String(text === null || text === undefined ? '' : text).trim();
    if (!t || (t.charAt(0) !== '{' && t.charAt(0) !== '[')) { return null; }
    try { var v = JSON.parse(t); return (v && typeof v === 'object') ? v : null; } catch (e) { return null; }
  }
  function countText(v) {     // 容器 → 计数文案（T.card_count_list / card_count_obj）
    var tt = global.T || {}, list = Array.isArray(v);
    var tpl = list ? (tt.card_count_list || '') : (tt.card_count_obj || '');
    var n = list ? v.length : Object.keys(v || {}).length;
    return tpl ? String(tpl).replace('%d', String(n)) : String(n);
  }
  function valueText(v, max) {
    var sc = scalar(v), inner;
    if (sc === null) { return countText(v); }
    inner = jsonOf(sc);
    return inner ? countText(inner) : oneLine(sc, max);
  }
  function pick(obj, path) {  // 点号路径：params.era 这类键要下钻一层（世界卡把年代 / 空间住在 params 里）
    var parts = String(path).split('.'), v = obj, i;
    for (i = 0; i < parts.length; i++) {
      if (!v || typeof v !== 'object' || Array.isArray(v)) { return undefined; }
      if (!Object.prototype.hasOwnProperty.call(v, parts[i])) { return undefined; }
      v = v[parts[i]];
    }
    return v;
  }
  function hiddenMap() {      // 隐藏槽（原样数据槽，不进界面）：键表 + 前缀，一次建好
    var c = cfg(), out = { keys: {}, prefixes: c.hiddenPrefixes || [] };
    (c.hiddenKeys || []).forEach(function (k) { out.keys[k] = 1; });
    return out;
  }
  function isHidden(h, key) {
    var i;
    if (h.keys[key]) { return true; }
    for (i = 0; i < h.prefixes.length; i++) { if (String(key).indexOf(h.prefixes[i]) === 0) { return true; } }
    return false;
  }
  /* 按「字段标签文案」反查值（作者 / 版本 / 标签）：标签只住生成物里，这里不写字段名 */
  function byLabel(obj, labelText) {
    var keys = Object.keys(obj || {}), i;
    if (!labelText) { return ''; }
    for (i = 0; i < keys.length; i++) { if (fieldLabel(keys[i]) === labelText) { return obj[keys[i]]; } }
    return '';
  }
  /* ---------- 模型（纯数据，不碰 DOM） ---------- */
  function titleOf(obj, file) {
    var tk = cfg().titleKeys || [], i, v;
    for (i = 0; i < tk.length; i++) {
      v = scalar(pick(obj, tk[i]));
      if (v && v.replace(/\s/g, '')) { return oneLine(v, 80); }
    }
    return String(file || '').replace(/\.json$/i, '');
  }
  /* 一个分区：按表里的 mode 走 body / kv / list 三种展示方式，**不折叠** */
  function sectionOf(obj, sec, seen) {
    var kvMax = cfg().kvValueChars || 120, i, j, v, txt, flat, arr, items, s, val, lbl;
    var out = { id: sec.id, mode: sec.mode, blocks: [], rows: [] }, seenLbl = {};
    var keys = sec.keys || [];
    for (i = 0; i < keys.length; i++) {
      v = pick(obj, keys[i]);
      if (v === undefined) { continue; }
      if (sec.mode === 'body') {
        txt = scalar(v); flat = txt ? txt.replace(/\s+/g, '') : '';
        if (!flat || seen[flat]) { continue; }   // 空值跳过；同文只留一份（system_prompt 常与 description 同文）
        seen[flat] = 1;
        out.blocks.push({ label: fieldLabel(keys[i]), paras: paras(txt) });
      } else if (sec.mode === 'list') {
        arr = Array.isArray(v) ? v : [v]; items = [];
        for (j = 0; j < arr.length; j++) { s = valueText(arr[j], 0); if (s) { items.push(s); } }
        if (items.length) { out.blocks.push({ label: fieldLabel(keys[i]), items: items }); }
      } else {
        val = valueText(v, kvMax); lbl = fieldLabel(keys[i]) || keys[i];
        if (!val || seenLbl[lbl]) { continue; }  // params.era 与 era 同时存在时不留两行
        seenLbl[lbl] = 1;
        out.rows.push({ label: lbl, value: val });
      }
    }
    return (out.blocks.length || out.rows.length) ? out : null;
  }
  /* 没被任何分区认领的键 → 「其它信息」两列；对象下钻一层，键名没登记就显示键名本身 */
  function otherOf(obj, claimed, seen, hid) {
    var kvMax = cfg().kvValueChars || 120, rows = [], i, c;
    var keys = Object.keys(obj || {});
    for (i = 0; i < keys.length; i++) {
      var k = keys[i], v = obj[k], val, kids, path, vt;
      if (isHidden(hid, k) || claimed[k]) { continue; }
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        kids = Object.keys(v);
        for (c = 0; c < kids.length; c++) {
          path = k + '.' + kids[c]; vt = valueText(v[kids[c]], kvMax);
          if (isHidden(hid, kids[c]) || claimed[path] || !vt || seen[vt.replace(/\s+/g, '')]) { continue; }
          rows.push({ label: fieldLabel(path) || path, value: vt });
        }
        continue;
      }
      val = valueText(v, kvMax);
      if (val && !seen[String(val).replace(/\s+/g, '')]) { rows.push({ label: fieldLabel(k) || k, value: val }); }
    }
    return rows;
  }
  function metaOf(obj, rtype) {   // 作者 · 版本 · 类型
    var tt = global.T || {}, parts = [];
    var au = valueText(byLabel(obj, tt.card_f_author || ''), 40);
    var ve = valueText(byLabel(obj, tt.card_f_version || ''), 20);
    if (au) { parts.push(au); } if (ve) { parts.push('v' + String(ve).replace(/^v/i, '')); }
    if (rtype) { parts.push(rtype); }
    return parts.join(' · ');
  }
  function tagsOf(obj) {
    var tt = global.T || {}, raw = byLabel(obj, tt.card_f_tags || '');
    var list = Array.isArray(raw) ? raw : String(raw || '').split(/[,，、;；\s]+/);
    var out = [], i, t;
    for (i = 0; i < list.length; i++) { t = String(list[i]).replace(/^#+/, '').trim(); if (t) { out.push(t); } }
    return out;
  }
  /* 世界书：角色卡的 world_entries / 世界卡的 entries（数组，逐条看） */
  function worldList(obj) {
    var c = [obj.world_entries, obj.entries], i;
    if (obj.world && typeof obj.world === 'object') { c.push(obj.world.entries || obj.world); }
    for (i = 0; i < c.length; i++) { if (Array.isArray(c[i]) && c[i].length) { return c[i]; } }
    return [];
  }
  function mechOf(obj) {      // 机制：advanced.mechanics（好感 / 状态 / 事件都在里面）
    var adv = obj.advanced, m = (adv && typeof adv === 'object') ? adv.mechanics : null;
    if (!m || typeof m !== 'object') { m = obj.mechanics; }
    return (m && typeof m === 'object' && Object.keys(m).length) ? m : null;
  }
  function bytesOf(text) {    // 文件大小 = 原文的 UTF-8 字节数（后端只回原文，不新增接口）
    var s = String(text || ''), n = 0, i, c;
    for (i = 0; i < s.length; i++) {
      c = s.charCodeAt(i);
      if (c < 0x80) { n += 1; } else if (c < 0x800) { n += 2; }
      else if (c < 0xd800 || c > 0xdbff) { n += 3; } else { n += 4; i++; }
    }
    return n;
  }
  function sizeText(n) {
    if (n < 1024) { return n + ' B'; }
    if (n < 1048576) { return (Math.round(n / 102.4) / 10) + ' KB'; }
    return (Math.round(n / 104857.6) / 10) + ' MB';
  }
  /* 三块 extras：世界书 / 机制 / 文件（数据结构，通用渲染，不新增标签表） */
  function extrasOf(obj, p, src) {
    var o = obj || {}, world = worldList(o), mech = mechOf(o), i;
    var wh = '', shown = Math.min(world.length, MAX_ENTRIES);
    for (i = 0; i < shown; i++) { wh += '<div class="ws-detail-entry">' + valueHtml(world[i], 0) + '</div>'; }
    if (world.length > shown) { wh += '<div class="ws-detail-more">还有 ' + (world.length - shown) + ' 条</div>'; }
    var mh = mech ? valueHtml(mech, 0) : '', name = String(p.file || ''), size = sizeText(bytesOf(src));
    var frows = [{ label: '文件名', value: name }, { label: '类型', value: String(p.rtype || '') },
                 { label: '大小', value: size }, { label: '字段', value: Object.keys(o).length + ' 项' }];
    return [
      { id: 'world', title: '世界书', body: wh || '<div class="ws-detail-more">暂无内容</div>',
        summary: world.length ? (world.length + ' 条') : '暂无' },
      { id: 'mech', title: '机制', body: mh || '<div class="ws-detail-more">暂无内容</div>',
        summary: mech ? (Object.keys(mech).length + ' 项') : '暂无' },
      { id: 'file', title: '文件', body: kvHtml(frows), summary: oneLine(name, 26) + ' · ' + size }
    ];
  }
  /* 原文 → 模型（纯函数：守护测试直接喂 JSON 字符串进来） */
  function build(p) {
    p = p || {};
    var src = (p.text === null || p.text === undefined) ? '' : String(p.text), obj = null, i, k;
    var m = { title: '', meta: '', tags: [], sections: [], other: [], extras: [] };
    try {
      var parsed = JSON.parse(src);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) { obj = parsed; }
    } catch (e) { obj = null; }
    if (!obj) {
      // 不是卡（坏文件 / 空文件 / 原始<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌文本）→ 原文按段落显示，别留一块空白
      m.title = String(p.file || '').replace(/\.json$/i, ''); m.meta = String(p.rtype || '');
      m.sections = [{ id: '', mode: 'body', blocks: [{ label: '', paras: paras(src || String(p.err || '')) }] }];
      m.extras = extrasOf(null, p, src);
      return m;
    }
    var c = cfg(), tk = c.titleKeys || [], secs = c.sections || [], claimed = {}, seen = {};
    var hid = hiddenMap(), got;
    for (i = 0; i < tk.length; i++) { claimed[tk[i]] = 1; }
    m.title = titleOf(obj, p.file);
    for (i = 0; i < secs.length; i++) {
      got = sectionOf(obj, secs[i], seen);
      if (!got) { continue; }
      for (k = 0; k < (secs[i].keys || []).length; k++) { claimed[secs[i].keys[k]] = 1; }
      m.sections.push(got);
    }
    m.other = otherOf(obj, claimed, seen, hid); m.meta = metaOf(obj, p.rtype);
    m.tags = tagsOf(obj); m.extras = extrasOf(obj, p, src);
    return m;
  }
  /* ---------- 渲染（body / kv / list 三种展示方式） ---------- */
  function kvHtml(rows) {
    var h = '<div class="ws-detail-kv">', i;
    for (i = 0; i < rows.length; i++) {
      h += '<div class="ws-detail-k">' + esc(rows[i].label) + '</div>' +
        '<div class="ws-detail-v">' + esc(rows[i].value) + '</div>';
    }
    return h + '</div>';
  }
  function paraHtml(blk) {
    var ps = blk.paras || [], i;
    var h = (blk.label ? '<div class="ws-detail-sub">' + esc(blk.label) + '</div>' : '') + '<div class="ws-detail-p">';
    for (i = 0; i < ps.length; i++) { h += '<p>' + esc(ps[i]) + '</p>'; }
    return h + '</div>';
  }
  function listHtml(blk) {
    var it = blk.items || [], i;
    var h = (blk.label ? '<div class="ws-detail-sub">' + esc(blk.label) + '</div>' : '') + '<ul class="ws-detail-ul">';
    for (i = 0; i < it.length; i++) { h += '<li>' + esc(it[i]) + '</li>'; }
    return h + '</ul>';
  }
  function sectionHtml(sec) {
    var h = '<section class="ws-detail-sec">', lb = labelOf(sec.id), i, bs = sec.blocks || [];
    if (lb) { h += '<div class="ws-detail-sec-label">' + esc(lb) + '</div>'; }
    if (sec.mode === 'kv') { h += kvHtml(sec.rows || []); }
    for (i = 0; i < bs.length; i++) { h += bs[i].items ? listHtml(bs[i]) : paraHtml(bs[i]); }
    return h + '</section>';
  }
  /* 通用渲染（三块 extras 专用）：对象 → 键值行，数组 → 逐条行，长文本 → 正文段落。
     这里**不认识任何字段名** —— 键名没在字段表里登记就原样显示键名本身。 */
  function valueHtml(v, depth) {
    var kvMax = cfg().kvValueChars || 120, h = '', items, subs, rows, deep, keys, i, k, t, lb, val;
    if (Array.isArray(v)) {
      items = []; subs = [];
      for (i = 0; i < v.length; i++) {
        if (v[i] && typeof v[i] === 'object') { subs.push(v[i]); }
        else { t = valueText(v[i], kvMax); if (t) { items.push(t); } }
      }
      if (items.length) { h += listHtml({ items: items }); }
      for (i = 0; i < subs.length && depth < 3; i++) {
        h += '<div class="ws-detail-entry">' + valueHtml(subs[i], depth + 1) + '</div>';
      }
      return h;
    }
    if (v && typeof v === 'object') {
      rows = []; deep = []; keys = Object.keys(v);
      for (i = 0; i < keys.length; i++) {
        val = v[keys[i]];
        if (val && typeof val === 'object') { deep.push({ label: fieldLabel(keys[i]) || keys[i], value: val }); continue; }
        t = scalar(val);
        if (t === null) { continue; }
        lb = fieldLabel(keys[i]) || keys[i];
        if (t.length > kvMax) { deep.push({ label: lb, paras: paras(t) }); }
        else if (t) { rows.push({ label: lb, value: oneLine(t, kvMax) }); }
      }
      if (rows.length) { h += kvHtml(rows); }
      for (k = 0; k < deep.length; k++) {
        h += '<div class="ws-detail-sub">' + esc(deep[k].label) + '</div>';
        h += deep[k].paras ? paraHtml({ paras: deep[k].paras })
          : (depth < 3 ? valueHtml(deep[k].value, depth + 1) : '');
      }
      return h;
    }
    t = scalar(v);
    return t ? '<div class="ws-detail-p"><p>' + esc(t) + '</p></div>' : '';
  }
  /* 一块 extras：标题可点（默认收起）+ 一行摘要；条目太多只画前 N 条 + 「还有 N 条」 */
  function extraHtml(x) {
    var open = !!opened[x.id];
    return '<section class="ws-detail-x"><button class="ws-detail-x-head" data-x="' + x.id + '">' +
      '<span class="ws-detail-x-title">' + esc(x.title) + '</span>' +
      '<span class="ws-detail-x-sum">' + esc(x.summary) + '</span>' +
      '<span class="ws-detail-x-arrow">' + (open ? '▾' : '▸') + '</span></button>' +
      '<div class="ws-detail-x-body"' + (open ? '' : ' hidden') + '>' + x.body + '</div></section>';
  }
  function headHtml(m) {      // 抬头：标题 / 作者 · 版本 · 类型 / #标签
    var h = '<div class="ws-detail-title">' + esc(m.title) + '</div>';
    if (m.meta) { h += '<div class="ws-detail-meta">' + esc(m.meta) + '</div>'; }
    if (m.tags && m.tags.length) {
      h += '<div class="ws-detail-tags">' + esc('#' + m.tags.join(' #')) + '</div>';
    }
    return h;
  }
  function contentHtml(m) {   // 正文：各分区全文 + 「其它信息」+ 三块 extras
    var h = '', i, oc = cfg().other || {}, ex = m.extras || [];
    for (i = 0; i < m.sections.length; i++) { h += sectionHtml(m.sections[i]); }
    if (m.other && m.other.length) { h += sectionHtml({ id: oc.id || '', mode: oc.mode || 'kv', rows: m.other }); }
    for (i = 0; i < ex.length; i++) { h += extraHtml(ex[i]); }
    return '<div class="ws-detail-wrap">' + h + '</div>';
  }

  /* ---------- DOM（只碰本文件自己的 id：wsDetail*） ---------- */
  function el(id) { return global.document ? global.document.getElementById(id) : null; }
  function emit(name, payload) {
    if (global.DICK && global.DICK.bus && global.DICK.bus.emit) { global.DICK.bus.emit(name, payload); }
  }
  function paint() {
    var head = el('wsDetailHead'), body = el('wsDetailBody'), av = el('wsDetailAvatar'), pic = '';
    if (!cur) { return; }
    try {   // 头像复用外壳的 avatarHtml（拿不到就留空，不影响详情）
      if (cur.title && typeof global.avatarHtml === 'function') { pic = global.avatarHtml(cur.title); }
    } catch (e) { pic = ''; }
    if (av) { av.innerHTML = pic; }
    if (head) { head.innerHTML = headHtml(cur); }
    if (body) { body.innerHTML = contentHtml(cur); body.scrollTop = 0; }
  }
  function open(p) {
    cur = build(p); opened = {}; paint();
    var modal = el('wsDetailModal');
    if (modal) { modal.classList.add('open'); }
    bind();
  }
  function close() {
    var modal = el('wsDetailModal');
    if (modal) { modal.classList.remove('open'); }
    cur = null; opened = {};
  }
  function toggle(id) { if (id) { opened[id] = !opened[id]; paint(); } }
  /* 绑定只做一次：遮罩 / 关闭 / 四个动作 / Esc（详情里没有输入框，Esc 不会抢别人的） */
  function bind() {
    var modal = el('wsDetailModal'), body = el('wsDetailBody'), btn, acts;
    if (bound || !modal || !body) { return; }   // 绑过 / 片段没注入（下次 open 再试）
    bound = true;
    body.onclick = function (e) {              // 点 extras 的标题 = 展开 / 收起
      var hit = (e.target && e.target.closest) ? e.target.closest('[data-x]') : null;
      if (hit) { toggle(hit.getAttribute('data-x')); }
    };
    modal.onclick = function (e) { if (e.target === modal) { close(); } };   // 点遮罩关
    btn = el('wsDetailClose');
    if (btn) { btn.onclick = close; }
    acts = { wsDetailImport: 'card:import', wsDetailExport: 'export',
             wsDetailDelete: 'delete', wsDetailUpload: 'upload' };
    Object.keys(acts).forEach(function (id) {
      var b = el(id);
      if (!b) { return; }
      b.onclick = function () {
        var a = acts[id];
        // 导入是外壳的动作（它有自己的按钮与去向），其余三个回本屏已有的按钮
        if (a === 'card:import') { emit(a, {}); } else { emit('ws:detail:action', { action: a }); }
      };
    });
    global.document.addEventListener('keydown', function (e) {
      var k = (e && (e.key || e.code)) || '';
      if (k !== 'Escape' && k !== 'Esc') { return; }
      if (modal.classList.contains('open')) { close(); }
    });
  }

  return {
    mount: bind, open: open, close: close, build: build,
    headHtml: headHtml, contentHtml: contentHtml,
    /* 给守护测试用：一份原文 → 两段 HTML（不碰 DOM，不要求弹窗存在） */
    render: function (p) { var m = build(p); return { head: headHtml(m), body: contentHtml(m) }; }
  };
})(window);

/* 事件入口（屏间只经 DICK.bus）：
 *   'ws:detail:open'  —— 工坊里点了卡片，payload = {text, file, rtype, err}
 *   'ws:detail:close' —— 这张卡被删掉了，详情自己收起来 */
if (window.DICK && window.DICK.bus && window.DICK.bus.on) {
  window.DICK.bus.on('ws:detail:open', function (p) { window.WsDetail.open(p); });
  window.DICK.bus.on('ws:detail:close', function () { window.WsDetail.close(); });
}
