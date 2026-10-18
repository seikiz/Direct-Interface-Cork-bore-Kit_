/* web/js/screens/ws.js —— 创意工坊 / 世界卡库（阶段 3：从 index.html 整块搬出，零行为变化）
 *
 * 这一屏原来是 index.html 里**两段**离得很远的顶层代码：
 * 第 1 段（约 4230 行）：ws* 系列函数 + 插件 Tab 的两个按钮 + 开窗/关窗/Tab 切换
 * 第 2 段（约 6780 行）：本地列表的 onchange、导出/打开目录/删除、连接检测、搜索、
 * 下载/点赞/上传/在线删除 —— 夹在 codex 播放器的绑定中间
 * 两段合成一个模块后，"点「 创意工坊」→ 选 Tab → 选文件 → 下载"整条链路都在本文件里，
 * 不再和 codex 播放器的绑定混在一个匿名块里（审计里那 17 处"跨屏引用"就是这么来的）。
 *
 * 状态（阶段 3 收口）
 * wsCurLocal → DICK.state['ws.curLocal'] 「本地」页选中的文件 {rtype, filename}
 * wsCurOnline → DICK.state['ws.curOnline'] 在线列表选中的作品
 * wsOnlineCache → DICK.state['ws.onlineCache'] 上次拉到的在线列表
 * 三个同名全局是兼容访问器（state.js 的 bindGlobal），所以本文件里的读写一个字都没改。
 *
 * 归属
 * 结构：web/screens/ws.html（index.html 里原位只剩挂载点 <!--@screen:ws-->）
 * 样式：web/styles/screens/ws.css —— 原 styles/panels.css 的 .ws-cols/.ws-col、
 * .ws-cards、.ws-card 一族、.ws-empty、.ws-tabbtn 原样搬出去，
 * <link> 排在 panels.css（与 wm.css）之后。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 * · pywebview.api.workshop_*（state/preview/export/open_folder/delete_local/save_conn/
 * detect_proxy/delete）
 * · jobWait(kind, args) 后端分道任务（workshop.list/search/test/download/like/upload/plugins/
 * install_plugin）—— 外壳的 jobs 通道，本屏只发不收
 * · reloadRoles() / reloadWorlds() 下载/删除后刷新侧栏（外壳函数，直接调用）
 * · escapeHtml() 组件层转义
 * · #btnWorkshop 入口按钮在外壳侧栏（本屏 mount 时绑）
 * · alert()/confirm() 删除确认仍是原生弹窗（原有行为，本轮不改交互）
 */
window.WsScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 创<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌意工坊 =================
  // 三个选中态（真身都在 DICK.state['ws.*']，下面三行只注册同名兼容访问器）
  // ---- 创意工坊 ----
  // 「选中了哪个本地文件 / 哪个在线作品 / 在线列表缓存」真身都在 DICK.state['ws.*']，
  // 下面这三个同名全局只是兼容访问器（阶段 3 收口：老代码里的 `wsCurLocal = …` 一个字都不用改）。
  DICK.state.bindGlobal('wsCurLocal', 'ws.curLocal', null);
  DICK.state.bindGlobal('wsCurOnline', 'ws.curOnline', null);
  DICK.state.bindGlobal('wsOnlineCache', 'ws.onlineCache', []);

  function wsSetStatus(t) { document.getElementById('wsStatus').textContent = t || ''; }

  function wsRefreshAuto() {
    pywebview.api.workshop_state().then(function (s) {
      if (!s) return;
      var stEl = document.getElementById('wsAutoStatus');
      if (stEl) {
        // 2026-12 文案清理：这里原来把 active_server 的地址整个摊在界面上（用户不需要看
        // 端点），现在只说"已连接 / 连接中"。
        stEl.innerHTML = s.active_server
          ? '[ic:satellite_alt] 已连接'
          : '[ic:satellite_alt] 连接中...';
      }
    }).catch(function () {});
  }

  function wsLoadLocal() {
    pywebview.api.workshop_state().then(function (s) {
      if (!s) return;
      document.getElementById('wsProxyInput').value = s.proxy || '';
      document.getElementById('wsKeyInput').value = s.has_key ? '••••••••' : '';
      var stEl = document.getElementById('wsAutoStatus');
      if (stEl) {
        stEl.innerHTML = s.active_server
          ? '[ic:satellite_alt] 已连接'
          : '[ic:satellite_alt] 连接中...';
      }
      var rl = document.getElementById('wsLocalRoles');
      var wl = document.getElementById('wsLocalWorlds');
      var pl = document.getElementById('wsLocalPacks');
      rl.innerHTML = '';
      (s.local_roles || []).forEach(function (f) {
        var o = document.createElement('option'); o.value = f; o.textContent = f.replace('.json', ''); rl.appendChild(o);
      });
      wl.innerHTML = '';
      (s.local_worlds || []).forEach(function (f) {
        var o = document.createElement('option'); o.value = f; o.textContent = f.replace('.json', ''); wl.appendChild(o);
      });
      if (pl) {
        pl.innerHTML = '';
        (s.local_packs || []).forEach(function (f) {
          var o = document.createElement('option'); o.value = f; o.textContent = f.replace('.json', ''); pl.appendChild(o);
        });
      }
    }).catch(function () {});
  }

  function wsShowLocalPreview(rtype, filename) {
    wsCurLocal = { rtype: rtype, filename: filename };
    pywebview.api.workshop_preview(rtype, filename).then(function (r) {
      wsCardShow(r ? (r.ok ? r.preview : '') : '', filename,
                 r && !r.ok ? (r.err || '') : '');
    });
  }

  // ================= 卡片外显：结构化预览 =================
  /* 用户的反馈：「角色卡外显应该是结构化，而不是像现在一样像个代码，穿帮了」。
 *
 * 所以这里**不再把整份 JSON 塞进 <pre>**，而是按 design/card_fields.json 的分区表把它
 * 摆成一张卡：标题 / 角色设定 / 性格·外貌 / 开场白 / 基本信息 / 年代·空间 / 规则 /
 * 其它信息（两列）。字段清单与折叠阈值来自生成物 web/card_fields.js
 * （window.DICK_CARD_FIELDS，由 tools/gen_card_fields.py 从同一份 json 生成，
 * 安卓端 CardFields.kt 是它的镜像）——本文件只做渲染，**不硬编码字段名**。
 *
 * 三条硬规矩（tests/test_card_view.py 盯着）：
 * ① 不把 JSON 字符串化显示（没有 JSON.stringify / 没有 <pre>）；
 * ② 解析失败或不是 JSON → 显示原文，但用**正文样式**（不是等宽代码块）；
 * ③ 未知键一律进「其它信息」两列；数组/对象只报「列表 · N 项 / 对象 · N 项」，不打花括号。 */

  var wsCardCur = null;          // 当前卡片模型（展开/收起只重画这个）
  var wsCardOpen = {};           // 分区 id → 是否展开

  function wsCardCfg() { return window.DICK_CARD_FIELDS || {}; }

  /** 分区标签（生成物里展开成 T.<键> 字面量，文案只住 lang/strings.json） */
  function wsCardLabel(id) {
    try { return window.DICK_CARD_LABEL(id) || ''; } catch (e) { return ''; }
  }

  /** 字段标签；没登记的键返回空串（渲染器退回显示键名本身） */
  function wsCardFieldLabel(key) {
    try { return window.DICK_CARD_FIELD_LABEL(key) || ''; } catch (e) { return ''; }
  }

  /** 去掉字面 `\n` / `\t` 转义（卡片把换行存成两个字符），再掐掉行尾空白。 */
  function wsCardNorm(v) {
    var s = (v === null || v === undefined) ? '' : String(v);
    s = s.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n').replace(/\\t/g, '\t');
    return s.replace(/[ \t]+\n/g, '\n').replace(/\s+$/, '');
  }

  /** 正文 → 段落数组（空行分段；段内单换行保留）。 */
  function wsCardParas(text) {
    var t = wsCardNorm(text);
    var blocks = t.split(/\n[ \t]*\n+/);
    var out = [];
    for (var i = 0; i < blocks.length; i++) {
      var b = blocks[i].replace(/^\s+|\s+$/g, '');
      if (b) out.push(b);
    }
    return out;
  }

  function wsCardLineCount(paras) {
    var n = 0;
    for (var i = 0; i < paras.length; i++) n += paras[i].split('\n').length;
    return n;
  }

  /** 折叠：超过 collapseLines 行 → 只留攒够阈值的头几段。安卓端是同一套算法（逐行对齐）。 */
  function wsCardVisible(paras) {
    var limit = wsCardCfg().collapseLines || 8;
    var total = wsCardLineCount(paras);
    if (total <= limit) return { list: paras, more: false };
    var out = [], n = 0;
    for (var i = 0; i < paras.length; i++) {
      if (n >= limit) break;
      out.push(paras[i]);
      n += paras[i].split('\n').length;
    }
    return { list: out, more: true };
  }

  /** 标量 → 文本；容器（数组/对象）返回 null（交给 wsCardSummary，绝不打花括号）。 */
  function wsCardScalar(v) {
    if (v === null || v === undefined) return null;
    var t = typeof v;
    if (t === 'string') return wsCardNorm(v);
    if (t === 'number') return String(v);
    if (t === 'boolean') return v ? (T.card_yes || 'Yes') : (T.card_no || 'No');
    return null;
  }

  function wsCardSummary(v) {
    if (Array.isArray(v)) return String(T.card_count_list || '%d').replace('%d', String(v.length));
    if (v && typeof v === 'object') {
      return String(T.card_count_obj || '%d').replace('%d', String(Object.keys(v).length));
    }
    return '';
  }

  function wsCardOneLine(s, max) {
    var t = String(s).replace(/\s*\n\s*/g, ' ').replace(/\s+/g, ' ');
    return t.length > (max || 0) ? (max ? t.slice(0, max) + '…' : t) : t;
  }

  /** 字符串里包着 JSON 的情况（世界卡包的 params.space 就是这么存的）→ 解出容器。
 * 不这么做就得把 {"places":[{…}]} 原样摊在界面上 —— 那正是用户说的「像个代码，穿帮了」。 */
  function wsCardJsonOf(text) {
    var t = String(text === null || text === undefined ? '' : text).trim();
    if (!t || (t.charAt(0) !== '{' && t.charAt(0) !== '[')) return null;
    try {
      var v = JSON.parse(t);
      return (v && typeof v === 'object') ? v : null;
    } catch (e) { return null; }
  }

  /** 界面值：标量照抄（压成一行）；容器报计数；字符串里包的 JSON 也按容器报计数。 */
  function wsCardValueText(v, max) {
    var sc = wsCardScalar(v);
    if (sc === null) return wsCardSummary(v);
    var inner = wsCardJsonOf(sc);
    if (inner) return wsCardSummary(inner);
    return wsCardOneLine(sc, max);
  }

  /** 点号路径取值：params.era → obj.params.era（世界卡的年代/空间住在 params 里）。 */
  function wsCardGet(obj, path) {
    var parts = String(path).split('.');
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (!cur || typeof cur !== 'object' || Array.isArray(cur)) return undefined;
      if (!Object.prototype.hasOwnProperty.call(cur, parts[i])) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }

  function wsCardKV(path) { return wsCardFieldLabel(path) || path; }

  /** 空白压平（只用来判重：同一段话在别的分区已经显示过，就不要再显示一遍）。 */
  function wsCardFlat(s) { return String(s).replace(/\s+/g, ''); }

  function wsCardSeen(seen, text) {
    var flat = wsCardFlat(text);
    for (var i = 0; i < seen.length; i++) {
      if (seen[i].indexOf(flat) >= 0) return true;   // 这段是已显示内容的子串 → 重复
    }
    return false;
  }

  /** 一个分区：把同义键收进同一个块（body 按段、kv 两列、list 逐条）。 */
  function wsCardCollect(obj, sec, seenBody) {
    var cfg = wsCardCfg();
    var kvMax = cfg.kvValueChars || 120;
    var out = { id: sec.id, mode: sec.mode, blocks: [], rows: [] };
    var seenLabel = {}, seenText = {};
    var keys = sec.keys || [];
    for (var i = 0; i < keys.length; i++) {
      var path = keys[i];
      var v = wsCardGet(obj, path);
      if (v === undefined) continue;
      if (sec.mode === 'body') {
        var text = wsCardScalar(v);
        if (!text || !text.replace(/\s/g, '')) continue;
        if (seenText[text]) continue;       // system_prompt 与 description 同文时只留一份
        if (wsCardFlat(text).length >= 12 && wsCardSeen(seenBody, text)) continue;
        seenText[text] = 1;
        seenBody.push(wsCardFlat(text));
        out.blocks.push({ label: wsCardFieldLabel(path), paras: wsCardParas(text) });
      } else if (sec.mode === 'list') {
        var arr = Array.isArray(v) ? v : [v];
        var items = [];
        for (var j = 0; j < arr.length; j++) {
          var s = wsCardValueText(arr[j], 0);
          if (s) items.push(s);
        }
        if (items.length) out.blocks.push({ label: wsCardFieldLabel(path), items: items });
      } else {
        var val = wsCardValueText(v, kvMax);
        if (!val) continue;
        var lbl = wsCardKV(path);
        if (seenLabel[lbl]) continue;       // params.era 与 era 同时存在时不留两行
        seenLabel[lbl] = 1;
        out.rows.push({ label: lbl, value: val });
      }
    }
    return (out.blocks.length || out.rows.length) ? out : null;
  }

  /** 把一份卡 JSON 变成模型（纯数据，不碰 DOM）。 */
  function wsCardModel(obj, fileName) {
    var cfg = wsCardCfg();
    var title = '';
    var tk = cfg.titleKeys || [];
    for (var i = 0; i < tk.length; i++) {
      var tv = wsCardScalar(wsCardGet(obj, tk[i]));
      if (tv && tv.replace(/\s/g, '')) { title = wsCardOneLine(tv, 80); break; }
    }
    if (!title) title = String(fileName || '').replace(/\.json$/i, '');

    // 标题候选键算「已认领」：标题已经画在最上面了，再在「其它信息」里列一遍「name: xxx」是噪声
    var claimed = {};
    for (var t0 = 0; t0 < tk.length; t0++) claimed[tk[t0]] = 1;
    var sections = [];
    var seenBody = [];        // 已显示的正文（空白压平）：DICK 卡把同一段话既存进 system_prompt
    var secs = cfg.sections || [];
    for (var s = 0; s < secs.length; s++) {
      var got = wsCardCollect(obj, secs[s], seenBody);
      if (!got) continue;
      for (var k = 0; k < (secs[s].keys || []).length; k++) claimed[secs[s].keys[k]] = 1;
      sections.push(got);
    }

    var hidden = {};
    (cfg.hiddenKeys || []).forEach(function (h) { hidden[h] = 1; });
    var prefixes = cfg.hiddenPrefixes || [];
    function isHidden(key) {
      if (hidden[key]) return true;
      for (var p = 0; p < prefixes.length; p++) {
        if (String(key).indexOf(prefixes[p]) === 0) return true;
      }
      return false;
    }

    var kvMax = cfg.kvValueChars || 120;
    var other = [];
    // 长值重复正文时不再列一遍（旧版卡把旧的 system_prompt 存在 legacy 里，跟前文一模一样）
    function repeatedInBody(val) {
      var flat = wsCardFlat(val);
      if (flat.length < 20) return false;
      for (var i = 0; i < seenBody.length; i++) {
        if (seenBody[i].indexOf(flat) >= 0) return true;
      }
      return false;
    }
    var top = Object.keys(obj || {});
    for (var t = 0; t < top.length; t++) {
      var k = top[t];
      if (isHidden(k) || claimed[k]) continue;
      var v = obj[k];
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        // 对象下钻一层：世界卡的 params.tech_level 这类要看得见，不能压成「对象 · 8 项」。
        // 子项全被上面的分区认领了（或全是隐藏槽）→ 这一行整个不要，别留一行纯计数。
        var kids = Object.keys(v);
        for (var c = 0; c < kids.length; c++) {
          var path = k + '.' + kids[c];
          if (isHidden(kids[c]) || claimed[path]) continue;
          var val2 = wsCardValueText(v[kids[c]], kvMax);
          if (!val2 || repeatedInBody(val2)) continue;
          other.push({ label: wsCardKV(path), value: val2 });
        }
        continue;
      }
      var val = wsCardValueText(v, kvMax);
      if (!val || repeatedInBody(val)) continue;
      other.push({ label: wsCardKV(k), value: val });
    }
    return { title: title, sections: sections, other: other };
  }

  /** 兜底模型：不是 JSON / 解析失败 → 原文按正文排版（不是等宽代码块）。 */
  function wsCardRawModel(text, fileName) {
    var cfg = wsCardCfg();
    var t = String(text || '');
    var max = cfg.maxTextChars || 4000;
    if (t.length > max) t = t.slice(0, max) + '…';
    return {
      title: String(fileName || '').replace(/\.json$/i, ''),
      sections: [{ id: 'raw', mode: 'body', blocks: [{ label: '', paras: wsCardParas(t) }] }],
      other: []
    };
  }

  function wsCardEsc(s) { return escapeHtml(s === null || s === undefined ? '' : String(s)); }

  function wsCardBodyHtml(blk, secId) {
    var vis = wsCardVisible(blk.paras);
    var h = '';
    if (blk.label) h += '<div class="cv-sub">' + wsCardEsc(blk.label) + '</div>';
    h += '<div class="cv-body">';
    for (var i = 0; i < vis.list.length; i++) {
      h += '<p>' + wsCardEsc(vis.list[i]) + '</p>';
    }
    h += '</div>';
    if (vis.more) {
      var open = !!wsCardOpen[secId];
      h += '<button class="btn2 ghost cv-more" data-cv="' + wsCardEsc(secId) + '">' +
        wsCardEsc(open ? (T.card_collapse || 'Collapse') : (T.card_expand || 'Expand')) + '</button>';
    }
    return h;
  }

  function wsCardListHtml(blk) {
    var h = '';
    if (blk.label) h += '<div class="cv-sub">' + wsCardEsc(blk.label) + '</div>';
    h += '<ul class="cv-list">';
    for (var i = 0; i < blk.items.length; i++) h += '<li>' + wsCardEsc(blk.items[i]) + '</li>';
    h += '</ul>';
    return h;
  }

  function wsCardKvHtml(label, rows) {
    var h = '<section class="cv-sec">';
    if (label) h += '<div class="cv-sec-label">' + wsCardEsc(label) + '</div>';
    h += '<div class="cv-kv">';
    for (var i = 0; i < rows.length; i++) {
      h += '<div class="cv-k">' + wsCardEsc(rows[i].label) + '</div>' +
        '<div class="cv-v">' + wsCardEsc(rows[i].value) + '</div>';
    }
    h += '</div></section>';
    return h;
  }

  function wsCardSectionHtml(sec) {
    if (sec.mode === 'kv') return wsCardKvHtml(wsCardLabel(sec.id), sec.rows || []);
    var label = wsCardLabel(sec.id);
    var h = '<section class="cv-sec">' +
      (label ? '<div class="cv-sec-label">' + wsCardEsc(label) + '</div>' : '');
    for (var i = 0; i < sec.blocks.length; i++) {
      var blk = sec.blocks[i];
      h += blk.items ? wsCardListHtml(blk) : wsCardBodyHtml(blk, sec.id);
    }
    return h + '</section>';
  }

  /** 模型 → HTML（纯函数，不碰 DOM：守护测试直接调它）。 */
  function wsCardRender(m) {
    if (!m) return '';
    var h = '<div class="ws-cardview"><div class="cv-title">' + wsCardEsc(m.title) + '</div>';
    for (var i = 0; i < m.sections.length; i++) h += wsCardSectionHtml(m.sections[i]);
    if (m.other && m.other.length) h += wsCardKvHtml(wsCardLabel('other'), m.other);
    return h + '</div>';
  }

  /** 画到 #wsPreview（唯一改动 DOM 的地方）。 */
  function wsCardPaint() {
    var box = document.getElementById('wsPreview');
    if (!box) return;
    var m = wsCardCur;
    if (!m) { box.innerHTML = ''; return; }
    box.innerHTML = wsCardRender(m);
    var btns = box.querySelectorAll('.cv-more');
    for (var b = 0; b < btns.length; b++) {
      btns[b].onclick = function () {
        var id = this.getAttribute('data-cv');
        wsCardOpen[id] = !wsCardOpen[id];
        wsCardPaint();
      };
    }
  }

  /** 原文 + 文件名 → 模型（解析失败就退成原文模型）。 */
  function wsCardBuild(text, fileName, err) {
    var src = (text === null || text === undefined) ? '' : String(text);
    if (!src.trim()) {
      // 空文件 / 读不到：把原因当原文显示（正文样式），别留一块空白让人以为没点中
      return wsCardRawModel(err || '', fileName);
    }
    var obj = null;
    try {
      var parsed = JSON.parse(src);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) obj = parsed;
    } catch (e) { obj = null; }
    var cfg = wsCardCfg();
    if (obj && (cfg.sections || []).length) return wsCardModel(obj, fileName);
    return wsCardRawModel(src, fileName);
  }

  /** 入口：原文 + 文件名 → 结构化卡片（解析失败就按原文显示）。 */
  function wsCardShow(text, fileName, err) {
    wsCardOpen = {};
    wsCardCur = wsCardBuild(text, fileName, err);
    wsCardPaint();
  }

  /** 供守护测试用：一份卡原文 → HTML 字符串（不碰 DOM，不要求预览框存在）。 */
  function wsCardHtmlFor(text, fileName, err) {
    wsCardOpen = {};
    return wsCardRender(wsCardBuild(text, fileName, err));
  }

  function wsCardClear() {
    wsCardCur = null;
    wsCardOpen = {};
    wsCardPaint();
  }

  function wsSwitchTab(tab) {
    var isLocal = tab === 'local';
    var isOnline = tab === 'online';
    var isPlugin = tab === 'plugin';
    document.getElementById('wsLocalPane').style.display = isLocal ? '' : 'none';
    document.getElementById('wsOnlinePane').style.display = isOnline ? '' : 'none';
    document.getElementById('wsPluginPane').style.display = isPlugin ? '' : 'none';
    document.getElementById('wsTabLocal').className = 'btn2 ws-tabbtn' + (isLocal ? '' : ' ghost');
    document.getElementById('wsTabOnline').className = 'btn2 ws-tabbtn' + (isOnline ? '' : ' ghost');
    document.getElementById('wsTabPlugin').className = 'btn2 ws-tabbtn' + (isPlugin ? '' : ' ghost');
    if (isOnline) wsRefreshOnline();
    if (isPlugin) wsRefreshPlugins();
  }

  function wsFillOnline(list) {
    wsOnlineCache = list || [];
    var box = document.getElementById('wsOnlineList');
    box.innerHTML = '';
    if (!wsOnlineCache.length) {
      box.innerHTML = '<div class="ws-empty">暂无作品</div>';
      return;
    }
    wsOnlineCache.forEach(function (r, i) {
      var card = document.createElement('div');
      card.className = 'ws-card';
      card.style.cursor = 'pointer';
      card.innerHTML =
        '<div class="ws-card-top"><span class="ws-card-name">' + (r.type === '角色卡' ? '[ic:theater_comedy] ' : (r.type === '世界卡包' ? '[ic:inventory] ' : '[ic:public] ')) + escapeHtml(r.name || '') + '</span>' +
        '<span class="ws-card-meta">' + escapeHtml(r.author || '?') + ' · ↓' + (r.downloads || 0) + ' · [ic:favorite]' + (r.likes || 0) + '</span></div>' +
        (r.description ? '<div class="ws-card-desc">' + escapeHtml(String(r.description).slice(0, 60)) + '</div>' : '');
      card.onclick = function () {
        document.querySelectorAll('#wsOnlineList .ws-card').forEach(function (c) { c.style.borderColor = ''; });
        card.style.borderColor = 'var(--accent)';
        wsCurOnline = r;
      };
      box.appendChild(card);
    });
    wsCurOnline = null;
  }

  // ---------- 创意工坊插件 Tab（插件市场） ----------
  function wsSetPluginStatus(t) { document.getElementById('wsPluginStatus').textContent = t || ''; }

  function wsRefreshPlugins() {
    wsSetPluginStatus('加载中...');
    jobWait('workshop.plugins', []).then(function (r) {
      if (!r || !r.ok) {
        wsSetPluginStatus('[ic:error] ' + ((r && r.err) || '加载失败'));
        return;
      }
      var box = document.getElementById('wsPluginList');
      box.innerHTML = '';
      var plugins = r.plugins || [];
      var local = r.local || [];
      if (!plugins.length) {
        box.innerHTML = '<div class="ws-empty">插件市场暂无内容</div>';
        wsSetPluginStatus('共 0 个插件');
        return;
      }
      plugins.forEach(function (p) {
        var installed = local.indexOf((p.original_name || '').replace(/\.py$/i, '')) >= 0 || local.indexOf(p.name) >= 0;
        var card = document.createElement('div');
        card.className = 'ws-card';
        card.innerHTML =
          '<div class="ws-card-top"><span class="ws-card-name">[ic:extension] ' + escapeHtml(p.name || '') + '</span>' +
          '<span class="ws-card-meta">v' + escapeHtml(p.version || '1.0') + ' · ' + escapeHtml(p.author || '?') + ' · ↓' + (p.downloads || 0) + '</span></div>' +
          (p.description ? '<div class="ws-card-desc">' + escapeHtml(String(p.description).slice(0, 80)) + '</div>' : '') +
          '<div class="ws-card-btns">' +
          (installed
            ? '<span style="font-size:11px;color:var(--ok);padding:3px 4px">[ic:check_circle] 已安装</span>'
            : '<button class="btn2" data-pid="' + p.id + '">[ic:download] 安装</button>') +
          '</div>';
        var btn = card.querySelector('[data-pid]');
        if (btn) {
          btn.onclick = function () {
            btn.disabled = true;
            btn.textContent = '[ic:hourglass_empty] 安装中...';
            jobWait('workshop.install_plugin', [p.id]).then(function (rr) {
              if (rr && rr.ok) {
                btn.outerHTML = '<span style="font-size:11px;color:var(--ok);padding:3px 4px">[ic:check_circle] 已安装 ' + escapeHtml(rr.name || '') + '</span>';
                wsSetPluginStatus('[ic:check_circle] 安装成功：' + (rr.name || ''));
              } else {
                btn.disabled = false;
                btn.textContent = '[ic:download] 安装';
                wsSetPluginStatus('[ic:error] ' + ((rr && rr.err) || '安装失败'));
              }
            }).catch(function (e) {
              btn.disabled = false;
              btn.textContent = '[ic:download] 安装';
              wsSetPluginStatus('[ic:error] ' + (e && e.message ? e.message : '网络错误'));
            });
          };
        }
        box.appendChild(card);
      });
      wsSetPluginStatus('共 ' + plugins.length + ' 个插件');
    }).catch(function (e) { wsSetPluginStatus('[ic:error] ' + (e && e.message ? e.message : '网络错误')); });
  }

  /* ---------------- 插件 Tab 的两个按钮 ---------------- */
  function bindPluginTab() {
    document.getElementById('wsPluginRefresh').onclick = function () { wsRefreshPlugins(); };
    document.getElementById('wsPluginOpen').onclick = function () {
      pywebview.api.workshop_open_folder('plugins').then(function () {});
    };
  }

  function wsRefreshOnline() {
    wsSetStatus('加载中...');
    jobWait('workshop.list', []).then(function (r) {
      if (r && r.ok) {
        var mk = function (arr, type) {
          return (arr || []).map(function (x) { return { id: x.id, name: x.name, author: x.author, downloads: x.downloads, likes: x.likes, tags: x.tags, type: type, original_name: x.original_name }; });
        };
        var all = mk(r.cards, '角色卡').concat(mk(r.worlds, '世界卡')).concat(mk(r.packs, '世界卡包'));
        wsFillOnline(all);
        // 2026-12 文案清理：原来 server_old 会补一句"（服务器为旧版，无世界卡包）"——
        // 那是服务端的实现状态，用户看不到也不需要知道，直接不显示。
        wsSetStatus('共 ' + all.length + ' 个作品');
      } else {
        wsFillOnline([]);
        wsSetStatus('[ic:error] ' + ((r && r.err) || '加载失败'));
      }
    }).catch(function (e) { wsSetStatus('[ic:error] ' + (e && e.message ? e.message : '网络错误')); });
  }

  /* ---------------- 开窗 / 关窗 / 三个 Tab ---------------- */
  function bindOpenButtons() {
    document.getElementById('btnWorkshop').onclick = function () {
      document.getElementById('wsModal').classList.add('open');
      wsSwitchTab('local');
      wsLoadLocal();
      // 代理探测：只提示"本机有代理可用"，**不显示地址、不自动填入**。
      // 系统/本机代理常把稍大的上传包体截断（实测传 1.3KB 请求体经本机代理得 502，
      // 同一份文件直连 201），所以默认直连，只有用户明确要代理时才走它。
      var px = document.getElementById('wsProxyInput');
      if (px && !px.value.trim() && pywebview.api.workshop_detect_proxy) {
        pywebview.api.workshop_detect_proxy().then(function (r) {
          if (r && r.ok && r.found && r.found.length) {
            // 2026-12 文案清理：原来把 r.found[0].url 直接拼进状态行（用户看到的是
            // "http://127.0.0.1:7890" 这种地址），现在只说有这么个东西，地址留在输入框里。
            wsSetStatus('[ic:satellite_alt] 优先直连；本机有可用的代理通道，需要时填在上面的框里');
          }
        }).catch(function () {});
      }
    };
    document.getElementById('wsCloseBtn').onclick = function () { document.getElementById('wsModal').classList.remove('open'); };
    document.getElementById('wsTabLocal').onclick = function () { wsSwitchTab('local'); };
    document.getElementById('wsTabOnline').onclick = function () { wsSwitchTab('online'); };
    document.getElementById('wsTabPlugin').onclick = function () { wsSwitchTab('plugin'); };
  }

  /* ---------------- 本地 / 在线两个 Tab 的按钮与列表（原来夹在 codex 绑定中间那一段） ---------------- */
  function bindLocalOnline() {
    document.getElementById('wsLocalRoles').onchange = function () { if (this.value) wsShowLocalPreview('角色卡', this.value); };
    document.getElementById('wsLocalWorlds').onchange = function () { if (this.value) wsShowLocalPreview('世界卡', this.value); };
    document.getElementById('wsLocalPacks').onchange = function () { if (this.value) wsShowLocalPreview('世界卡包', this.value); };
    document.getElementById('wsExportBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在列表里选一个文件'); return; }
      pywebview.api.workshop_export(wsCurLocal.rtype, wsCurLocal.filename).then(function (r) {
        if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
      });
    };
    document.getElementById('wsOpenBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在列表里选一个文件'); return; }
      var folder = wsCurLocal.rtype === '角色卡' ? 'roles' : (wsCurLocal.rtype === '世界卡包' ? 'packs' : 'worlds');
      pywebview.api.workshop_open_folder(folder).then(function () {});
    };
    document.getElementById('wsLocalDelBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在列表里选一个文件'); return; }
      if (!confirm('删除本地文件 ' + wsCurLocal.filename + ' ？')) return;
      pywebview.api.workshop_delete_local(wsCurLocal.rtype, wsCurLocal.filename).then(function (r) {
        if (r && r.ok) {
          wsCurLocal = null;
          wsCardClear();
          wsLoadLocal();
          reloadRoles();
          reloadWorlds();
        } else alert((r && r.err) || '删除失败');
      });
    };
    document.getElementById('wsTestBtn').onclick = function () {
      // 重新检测：保存代理设置 → 刷新自动连接状态 → 测试连接
      var key = document.getElementById('wsKeyInput').value.trim();
      if (key === '••••••••') key = '';
      var proxy = document.getElementById('wsProxyInput').value.trim();
      wsSetStatus('检测中...');
      pywebview.api.workshop_save_conn('', key, proxy).then(function () {
        wsRefreshAuto();
      });
      jobWait('workshop.test', []).then(function (r) {
        if (r && r.ok) {
          var st = r.stats || {};
          // 2026-12 文案清理：原来这里拼的是 `认证: key`（服务端的鉴权模式），
          // 用户只需要知道"连上了"和几个统计数字。
          wsSetStatus('[ic:check_circle] 已连接（下载 ' + (st.downloads || 0) + ' · 点赞 ' + (st.likes || 0) + '）');
        } else wsSetStatus('[ic:error] ' + ((r && r.err) || '连接失败'));
      });
    };
    document.getElementById('wsAllBtn').onclick = function () { wsRefreshOnline(); };
    document.getElementById('wsSearchBtn').onclick = function () {
      var q = document.getElementById('wsSearchInput').value.trim();
      wsSetStatus('搜索中...');
      jobWait('workshop.search', [q, '']).then(function (r) {
        if (r && r.ok) {
          wsFillOnline((r.results || []).map(function (x) { return { id: x.id, name: x.name, author: x.author, downloads: x.downloads, likes: x.likes, tags: x.tags, type: x.type || '角色卡', original_name: x.original_name }; }));
          wsSetStatus('找到 ' + (r.results || []).length + ' 个');
        } else wsSetStatus('[ic:error] ' + ((r && r.err) || '搜索失败'));
      });
    };
    document.getElementById('wsDownloadBtn').onclick = function () {
      if (!wsCurOnline) { alert('先在列表里选一个作品'); return; }
      wsSetStatus('下载中...');
      jobWait('workshop.download', [wsCurOnline.id, wsCurOnline.type, wsCurOnline.original_name || (wsCurOnline.name + '.json')]).then(function (r) {
        if (r && r.ok) {
          wsSetStatus('[ic:check_circle] 已下载：' + r.file);
          wsLoadLocal();
          reloadRoles();
          reloadWorlds();
        } else wsSetStatus('[ic:error] ' + ((r && r.err) || '下载失败'));
      });
    };
    document.getElementById('wsLikeBtn').onclick = function () {
      if (!wsCurOnline) { alert('先选一个作品'); return; }
      jobWait('workshop.like', [wsCurOnline.id, wsCurOnline.type]).then(function (r) {
        wsSetStatus(r && r.ok ? '[ic:check_circle] 已点赞' : '[ic:error] ' + ((r && r.err) || '失败'));
      });
    };
    document.getElementById('wsUploadBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在「本地」页选一个要上传的文件'); return; }
      var name = wsCurLocal.filename.replace('.json', '');
      wsSetStatus('上传中...');
      jobWait('workshop.upload', [wsCurLocal.rtype, name]).then(function (r) {
        wsSetStatus(r && r.ok ? '[ic:check_circle] 上传成功' : '[ic:error] ' + ((r && r.err) || '上传失败'));
      });
    };
    document.getElementById('wsOnlineDelBtn').onclick = function () {
      if (!wsCurOnline) { alert('先选一个作品'); return; }
      if (!confirm('从工坊删除「' + wsCurOnline.name + '」？此操作不可恢复。')) return;
      pywebview.api.workshop_delete(wsCurOnline.id, wsCurOnline.type).then(function (r) {
        if (r && r.ok) { wsSetStatus('[ic:check_circle] 已删除'); wsRefreshOnline(); }
        else wsSetStatus('[ic:error] ' + ((r && r.err) || '删除失败'));
      });
    };
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('wsModal')) {
      console.error('[ws] 片段没注入（找不到 #wsModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    bindPluginTab();
    bindOpenButtons();
    bindLocalOnline();
  }

  function unmount() {
    var b = document.getElementById('btnWorkshop');
    if (b) { b.onclick = null; }
    var c = document.getElementById('wsCloseBtn');
    if (c) { c.onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    setStatus: wsSetStatus, refreshAuto: wsRefreshAuto, loadLocal: wsLoadLocal,
    showLocalPreview: wsShowLocalPreview, switchTab: wsSwitchTab, fillOnline: wsFillOnline,
    setPluginStatus: wsSetPluginStatus, refreshPlugins: wsRefreshPlugins,
    refreshOnline: wsRefreshOnline,
    // 卡片外显（结构化预览）：cardHtml 给守护测试用（纯函数），cardShow/cardClear 是运行时入口
    cardHtml: wsCardHtmlFor, cardShow: wsCardShow, cardClear: wsCardClear
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前这 9 个都是 index.html 的顶层全局函数。本轮搬完，index.html 里**已经没有任何一处**
 * 调用它们（开窗/关窗/Tab 由本屏 mount() 绑，渲染由本屏自己按需调）。
 * 但插件作者/老脚本可能按名字叫，所以同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function wsSetStatus(t) { return window.WsScreen.setStatus(t); }
function wsRefreshAuto() { return window.WsScreen.refreshAuto(); }
function wsLoadLocal() { return window.WsScreen.loadLocal(); }
function wsShowLocalPreview(rtype, filename) { return window.WsScreen.showLocalPreview(rtype, filename); }
function wsSwitchTab(tab) { return window.WsScreen.switchTab(tab); }
function wsFillOnline(list) { return window.WsScreen.fillOnline(list); }
function wsSetPluginStatus(t) { return window.WsScreen.setPluginStatus(t); }
function wsRefreshPlugins() { return window.WsScreen.refreshPlugins(); }
function wsRefreshOnline() { return window.WsScreen.refreshOnline(); }

// 注册到路由：片段 = screens/ws.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('ws', { fragment: 'screens/ws.html', module: window.WsScreen });
