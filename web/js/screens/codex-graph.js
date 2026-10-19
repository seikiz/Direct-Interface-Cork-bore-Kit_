/* web/js/screens/codex-graph.js —— 编年史的节点图编辑器（线-点-分支 剪辑）。
 *
 * 归属：结构在 web/screens/codex.html 的 codexGraphWrap 里；数据 _gScript / _gSel 在 store/codex.js。
 * 说明：这块 DOM 的 id 历史上写成了 cxGraph*（cx 前缀在审计口径里算「播放器」），其实它在
 *       codexGraphWrap 内部，是编辑器自己的画布。改 id = 改 DOM，违反「搬运零变化」，
 *       所以这一处跨前缀引用登记为**已知道的欠债**（见 UI_ARCHITECTURE.md 的例外表）。
 *       SVG 里的 onclick 是拼出来的字符串，必须能摸到全局函数，所以本文件保持顶层函数（不套 IIFE）。
 */
// ===== GAL 叙事引擎 · 节点图<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌编辑器（线-点-分支 剪辑） =====
// 编年史 codex 的数据层收进 DICK.state（2 个：_gScript、_gSel）；注册在 web/js/store/codex.js
// 注意：这张表同时被 SVG <text>（节点图）和 <option>（下拉）消费，两处都放不进 <span> 图标，
// 所以只放纯文字（节点图本来就按 kind 上色）；DOM 场景要用图标请取 _gKindIcon。
var _gKindNames = { say:'台词', note:'旁白', show:'显示立绘', hide:'隐藏立绘', bg:'背景', bgm:'音乐', sfx:'音效', effect:'特效', wait:'等待', setflag:'设标记', roll:'抽取', choice:'分支', jump:'跳转', end:'结局', action:'动作' };
// 每种节点一个图标。名字必须是 Material Symbols 里**真的有的连字**（tests/test_no_emoji_ui.py ①
// 按字体连字表把关）—— 原来的 memo/music/bell/burst/dice/flag_end 六个名字字体里没有，
// 界面上只会画成名字本身，这次一并换成 fonts 里有的：description / music_note /
// notifications / flare / casino / sports_score。
var _gKindIcon = { say:'[ic:chat]', note:'[ic:description]', show:'[ic:sprite]', hide:'[ic:sprite_off]', bg:'[ic:image]', bgm:'[ic:music_note]', sfx:'[ic:notifications]', effect:'[ic:flare]', wait:'[ic:hourglass]', setflag:'[ic:flag]', roll:'[ic:casino]', choice:'[ic:shuffle]', jump:'[ic:arrow_right]', end:'[ic:sports_score]', action:'[ic:settings]' };
function codexGraphStatus(s) { document.getElementById('cxGraphStatus').textContent = s || ''; }
function codexGraphOpen() {
  var box = document.getElementById('codexJsonInput');
  try { _gScript = JSON.parse(box.value || 'null'); } catch (e) { codexGraphStatus('[ic:error] JSON 解析失败: ' + e.message); return; }
  if (!_gScript || typeof _gScript !== 'object') _gScript = { name: codexCur || '我的故事', scenes: [] };
  if (!_gScript.scenes) _gScript.scenes = [];
  _gSel = null;
  document.getElementById('codexEditor').style.display = 'none';
  document.getElementById('codexGraphWrap').style.display = 'block';
  document.getElementById('cxSceneEdit').style.display = 'none';
  codexRenderGraph();
  codexGraphStatus('[ic:movie] 线-点-分支 · ' + (_gScript.scenes || []).length + ' 条线 · 点「线」编步骤，点分支边改条件');
}
function codexGraphJson() {
  document.getElementById('codexGraphWrap').style.display = 'none';
  document.getElementById('codexEditor').style.display = 'block';
  var box = document.getElementById('codexJsonInput');
  if (_gScript) box.value = JSON.stringify(_gScript, null, 2);
}
function codexGraphAddScene() {
  var t = prompt('新场景(线)标题：', '场景 ' + ((_gScript.scenes || []).length + 1));
  if (t === null) return;
  _gScript.scenes = _gScript.scenes || [];
  var base = _gScript.scenes.length + 1, nid = 's' + base;
  while (_gScript.scenes.some(function (s) { return s.id === nid; })) { base++; nid = 's' + base; }
  _gScript.scenes.push({ id: nid, title: (t || nid).trim(), lines: [] });
  _gSel = nid;
  codexRenderGraph();
  codexEditSceneGraph(nid);
}
// 图布局（线=过程条，点=节拍，分支=岔口）：每条「线」(场景) 独占一行；行内点是横向排列的节拍。
function _gLayout() {
  var scenes = _gScript.scenes || [];
  var byId = {}; scenes.forEach(function (s) { byId[s.id] = s; });
  var order = [], seen = {}, q = [scenes[0].id];
  while (q.length) {
    var id = q.shift(); if (seen[id]) continue; seen[id] = true;
    if (byId[id]) order.push(id);
    var sc = byId[id]; if (!sc) continue;
    (sc.lines || []).forEach(function (ln) {
      if (ln && ln.choice) ln.choice.forEach(function (o) { if (o && o.goto && byId[o.goto] && !seen[o.goto]) q.push(o.goto); });
      if (ln && ln.jump && byId[ln.jump] && !seen[ln.jump]) q.push(ln.jump);
    });
    var nxt = sc.next || sc.jump;
    if (nxt && byId[nxt] && !seen[nxt]) q.push(nxt);
  }
  scenes.forEach(function (s) { if (!seen[s.id]) order.push(s.id); });
  var pos = {};
  order.forEach(function (id, i) {
    var sc = byId[id];
    var beats = (sc && sc.lines) || [];
    pos[id] = { y: 60 + i * 128, beats: beats, w: Math.max(240, beats.length * 150) };
  });
  return { pos: pos, scenes: scenes, byId: byId, order: order };
}
function codexRenderGraph() {
  var wrap = document.getElementById('cxGraphCanvas');
  var L = _gLayout();
  var maxX = 600, maxY = 200;
  L.order.forEach(function (id) { var p = L.pos[id]; if (p) { if (60 + p.w > maxX) maxX = 60 + p.w; if (p.y > maxY) maxY = p.y; } });
  var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + (maxX + 200) + '" height="' + (maxY + 90) + '" style="display:block">' +
    '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#4a5462"/></marker></defs>';
  var edges = '';
  function edge(t, ty, label, fromX, fromY) {
    var q = L.pos[t]; if (!q) return;
    var x1 = fromX !== undefined ? fromX : (maxX - 60);
    var y1 = fromY !== undefined ? fromY : 0;
    var x2 = 60, y2 = q.y + 22;
    edges += '<path d="M' + x1 + ',' + y1 + ' C' + (x1 + 90) + ',' + y1 + ' ' + (x2 - 90) + ',' + y2 + ' ' + x2 + ',' + y2 + '" fill="none" stroke="' + (ty === 'cond' ? '#f59e0b' : '#4a5462') + '" stroke-width="2" marker-end="url(#arr)"/>' +
      (label ? '<text x="' + Math.round((x1 + x2) / 2) + '" y="' + Math.round((y1 + y2) / 2 - 5) + '" fill="' + (ty === 'cond' ? '#f59e0b' : '#8a93a3') + '" font-size="10" text-anchor="middle">' + escapeHtml(label) + '</text>' : '');
  }
  L.scenes.forEach(function (sc) {
    var p = L.pos[sc.id]; if (!p) return;
    (sc.lines || []).forEach(function (ln) {
      if (!ln || typeof ln !== 'object') return;
      var kind = ln.kind || 'say';
      if (kind === 'choice') (ln.choice || []).forEach(function (o, k) {
        if (o && o.goto && L.byId[o.goto]) edge(o.goto, o.if ? 'cond' : 'line', (o.if ? '[ic:lock]' : '[ic:shuffle]') + ' ' + (o.text || ''), 265 + k * 90, p.y + 22);
      });
      if (ln.jump && L.byId[ln.jump]) edge(ln.jump, 'line', '跳', 265, p.y + 22);
    });
    var nxt = sc.next || sc.jump;
    if (nxt && L.byId[nxt]) edge(nxt, 'line', '下一', 60 + p.w, p.y + 22);
  });
  svg += edges;
  L.scenes.forEach(function (sc) {
    var p = L.pos[sc.id]; if (!p) return;
    var sel = sc.id === _gSel;
    var lineW = Math.max(240, p.beats.length * 150);
    // 线 = 一条过程条：左端标题 + 点串
    var click = 'onclick="codexEditSceneGraph(\'' + escapeHtml(sc.id) + '\')" style="cursor:pointer"';
    svg += '<g ' + click + '>' +
      '<rect x="60" y="' + p.y + '" width="' + lineW + '" height="44" rx="10" fill="' + (sel ? 'rgba(245,158,11,.16)' : 'rgba(255,255,255,.04)') + '" stroke="' + (sel ? '#f59e0b' : '#3a4553') + '" stroke-width="' + (sel ? 2 : 1) + '"/>' +
      '<rect x="60" y="' + p.y + '" width="150" height="44" rx="10" fill="rgba(245,158,11,.10)" stroke="#3a4553" stroke-width="1"/>' +
      '<text x="70" y="' + (p.y + 20) + '" fill="#f5c06c" font-size="12" font-weight="bold">线 ' + escapeHtml(sc.id || '') + '</text>' +
      '<text x="70" y="' + (p.y + 35) + '" fill="#8a93a3" font-size="10">' + escapeHtml((sc.title || '').slice(0, 12)) + '</text>' +
      '</g>';
    for (var i = 0; i < p.beats.length; i++) {
      var ln = p.beats[i];
      if (!ln || typeof ln !== 'object') continue;
      var bx = 225 + i * 150;
      var kind = ln.kind || 'say';
      var icon = _gKindNames[kind] || '·';
      var isChoice = kind === 'choice';
      var snip = ((typeof ln.text === 'string' && ln.text) || (isChoice ? '分支' : kind)).slice(0, 12);
      svg += '<g ' + click + '>' +
        '<rect x="' + bx + '" y="' + p.y + '" width="140" height="44" rx="8" fill="' + (isChoice ? 'rgba(245,158,11,.12)' : 'rgba(120,160,220,.06)') + '" stroke="' + (isChoice ? '#f59e0b' : '#4a5462') + '" stroke-width="1"/>' +
        '<text x="' + (bx + 8) + '" y="' + (p.y + 18) + '" fill="' + (isChoice ? '#f59e0b' : '#c8d6e5') + '" font-size="10">' + escapeHtml(icon) + '</text>' +
        '<text x="' + (bx + 8) + '" y="' + (p.y + 34) + '" fill="#8a93a3" font-size="9">' + escapeHtml(snip) + '</text>' +
        '</g>';
    }
  });
  svg += '</svg>';
  wrap.innerHTML = svg;
}
function codexEditSceneGraph(sid) {
  _gSel = sid;
  var sc = (_gScript.scenes || []).find(function (s) { return s.id === sid; });
  var panel = document.getElementById('cxSceneEdit');
  panel.style.display = 'block';
  panel.innerHTML = '';
  if (!sc) { panel.innerHTML = '<div style="color:var(--text-sub)">场景不存在</div>'; return; }
  var h = document.createElement('div');
  h.className = 'row';
  h.style.cssText = 'justify-content:flex-start;align-items:center;margin-bottom:6px';
  h.innerHTML = '<b style="font-size:14px">场景 ' + escapeHtml(sc.id) + '</b> <input id="cxSceneTitle" style="flex:1;min-width:120px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:5px 8px;font-size:13px">';
  panel.appendChild(h);
  document.getElementById('cxSceneTitle').value = sc.title || '';
  document.getElementById('cxSceneTitle').oninput = function () { sc.title = this.value; };
  // 步骤列表
  var list = document.createElement('div');
  list.id = 'cxSceneSteps';
  panel.appendChild(list);
  function renderSteps() {
    list.innerHTML = '';
    var lines = sc.lines || []; sc.lines = lines;
    lines.forEach(function (ln, i) { renderStepRow(sc, ln, i); });
    var add = document.createElement('button');
    add.className = 'btn2 ghost';
    add.textContent = '[ic:add] 加一步';
    add.style.cssText = 'margin-top:6px';
    add.onclick = function () { sc.lines.push({ kind: 'say', text: '' }); renderSteps(); };
    list.appendChild(add);
    var delScene = document.createElement('button');
    delScene.className = 'btn2 ghost';
    delScene.textContent = '[ic:delete] 删除本场景';
    delScene.style.cssText = 'margin-top:6px;color:var(--danger);margin-left:8px';
    delScene.onclick = function () { _gScript.scenes = _gScript.scenes.filter(function (s) { return s.id !== sc.id; }); _gSel = null; codexRenderGraph(); document.getElementById('cxSceneEdit').style.display = 'none'; };
    list.appendChild(delScene);
  }
  function renderStepRow(sc, ln, i) {
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0;padding:6px;border:1px solid var(--line);border-radius:6px;background:var(--bubble)';
    var selKind = document.createElement('select');
    Object.keys(_gKindNames).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = _gKindNames[k]; selKind.appendChild(o); });
    selKind.value = ln.kind || 'say';
    selKind.onchange = function () { ln.kind = selKind.value; if (ln.kind === 'action') { delete ln.text; delete ln.sprite; delete ln.voice; } renderSteps(); };
    row.appendChild(selKind);
    var inp;
    if (ln.kind === 'choice') {
      var ci = document.createElement('span'); ci.textContent = '分支：'; row.appendChild(ci);
      (ln.choice || []).forEach(function (o) { renderChoiceItem(row, ln, o); });
      var addOpt = document.createElement('button'); addOpt.className = 'btn2 ghost'; addOpt.textContent = '[ic:add] 选项'; addOpt.style.cssText = 'font-size:11px;padding:3px 8px'; addOpt.onclick = function () { ln.choice = ln.choice || []; ln.choice.push({ text: '', goto: '' }); renderSteps(); }; row.appendChild(addOpt);
      row.appendChild(delBtn(ln, i));
      list.appendChild(row); return;
    }
    if (ln.kind === 'jump' || ln.kind === 'end') {
      inp = mkInput(ln.goto !== undefined ? ln.goto : (ln.end || ''), 's2', function (v) { if (ln.kind === 'jump') ln.goto = v; else ln.end = v; });
      inp.placeholder = ln.kind === 'jump' ? '目标场景 id' : '结局文本';
      row.appendChild(inp);
    } else {
      inp = mkInput(ln.text || '', '台词文本', function (v) { ln.text = v; });
      inp.style.cssText = 'flex:2;min-width:150px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:5px 8px;font-size:12px';
      row.appendChild(inp);
      if (ln.kind === 'say') {
        var sp = mkInput(ln.sprite || '', '立绘文件', function (v) { ln.sprite = v; });
        sp.style.cssText = 'flex:1;min-width:80px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:5px 8px;font-size:12px';
        row.appendChild(sp);
        var vo = mkInput(ln.voice || '', '语音', function (v) { ln.voice = v; });
        vo.style.cssText = 'flex:1;min-width:80px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:5px 8px;font-size:12px';
        row.appendChild(vo);
      }
      if (ln.kind === 'setflag') { var fk = mkInput((ln.flag && ln.flag.k) || '', 'flag 名', function (v) { ln.flag = { k: v, v: true }; }); row.appendChild(fk); }
      if (ln.kind === 'roll') { var rk = mkInput((ln.roll && ln.roll.d) || 100, '面数', function (v) { ln.roll = { d: Number(v) || 100 }; }); row.appendChild(rk); }
      if (ln.kind === 'effect') { var ef = mkInput(ln.effect || 'shake', 'shake/flash', function (v) { ln.effect = v; }); row.appendChild(ef); }
      if (ln.kind === 'wait') { var ms = mkInput(ln.ms || 300, '毫秒', function (v) { ln.ms = Number(v) || 0; }); row.appendChild(ms); }
    }
    row.appendChild(delBtn(ln, i));
    list.appendChild(row);
  }
  function renderChoiceItem(row, ln, o) {
    var box = document.createElement('span');
    box.style.cssText = 'display:inline-flex;gap:4px;align-items:center;margin:2px 4px';
    var ot = document.createElement('input'); ot.value = o.text || ''; ot.placeholder = '选项文字'; ot.style.cssText = 'background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:3px 6px;font-size:12px;width:110px'; ot.oninput = function () { o.text = ot.value; }; box.appendChild(ot);
    var og = document.createElement('input'); og.value = o.goto || ''; og.placeholder = 'goto'; og.style.cssText = 'background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:3px 6px;font-size:12px;width:70px'; og.oninput = function () { o.goto = og.value; }; box.appendChild(og);
    var oc = document.createElement('input'); oc.value = o.if ? JSON.stringify(o.if) : ''; oc.placeholder = '条件 {aff:>=85}'; oc.style.cssText = 'background:var(--bubble);border:1px solid rgba(245,158,11,.4);border-radius:6px;color:var(--warn);padding:3px 6px;font-size:12px;width:150px'; oc.oninput = function () { try { o.if = oc.value.trim() ? JSON.parse(oc.value) : undefined; } catch (e) { o.if = undefined; } }; box.appendChild(oc);
    var del = document.createElement('button'); del.textContent = '[ic:close]'; del.className = 'btn2 ghost'; del.style.cssText = 'color:var(--danger);font-size:11px;padding:2px 6px'; del.onclick = function () { ln.choice = ln.choice.filter(function (x) { return x !== o; }); renderSteps(); }; box.appendChild(del);
    row.appendChild(box);
  }
  function delBtn(ln, i) {
    var d = document.createElement('button'); d.textContent = '[ic:delete]'; d.className = 'btn2 ghost'; d.style.cssText = 'color:var(--danger);font-size:12px;padding:2px 6px'; d.onclick = function () { sc.lines.splice(i, 1); renderSteps(); }; return d;
  }
  function mkInput(val, ph, cb) {
    var x = document.createElement('input'); x.value = val; x.placeholder = ph; firstInput(x); return x;
  }
  function firstInput(x) { x.style.cssText = 'flex:1;min-width:90px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:5px 8px;font-size:12px'; x.oninput = function () { cb(x.value); }; }
  renderSteps();
  codexRenderGraph();
}
function codexSaveGraph() {
  try { var box = document.getElementById('codexJsonInput'); box.value = JSON.stringify(_gScript, null, 2); codexSave(); codexGraphStatus('[ic:check_circle] 已保存到剧本'); }
  catch (e) { codexGraphStatus('[ic:error] ' + e.message); }
}
function codexGraphBind() {
  document.getElementById('codexGraphBtn').onclick = codexGraphOpen;
  document.getElementById('cxGraphSaveBtn').onclick = codexSaveGraph;
  document.getElementById('cxGraphAddBtn').onclick = codexGraphAddScene;
  document.getElementById('cxGraphJsonBtn').onclick = codexGraphJson;
}
