/* web/js/screens/gal-canvas.js —— GAL 画布：角色面板 + 节点图渲染 + 缩放平移 + 右键菜单 + 场景面板。
 *
 * 归属：结构在 web/screens/gal.html（galLines / galCtx / galScenePanel …）。
 * 搬迁口径：坐标计算、SVG 连线、拖拽/缩放/右键的算法**逐字保留**（这是最容易改坏观感的一段）。
 * 只碰 gal 前缀的 id；不读别的屏的 DOM。
 */


// ===== 角色管理（独立的角色实<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌体，供台词点下拉选择） =====
function galEnsureRoles() { if (!galScript.roles) galScript.roles = []; }
function galToggleRoles() {
  var p = document.getElementById('galRolePanel'); if (!p) return;
  var sceneP = document.getElementById('galScenePanel'); if (sceneP) sceneP.style.display = 'none';
  p.style.display = (p.style.display === 'block') ? 'none' : 'block';
  if (p.style.display === 'block') galRenderRoles();
}
function galRenderRoles() {
  galEnsureRoles();
  var p = document.getElementById('galRolePanel'); if (!p) return;
  p.innerHTML = '';
  var h = document.createElement('div');
  h.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line)';
  h.innerHTML = '<b style="font-size:13px;color:var(--text)">[ic:group] 角色（独立实体）</b>';
  var close = document.createElement('button'); close.className = 'btn2 ghost'; close.textContent = '[ic:close]'; close.onclick = function () { p.style.display = 'none'; };
  h.appendChild(close);
  p.appendChild(h);
  var wrap = document.createElement('div'); wrap.style.cssText = 'padding:8px 12px';
  var hint = document.createElement('div'); hint.style.cssText = 'font-size:11px;color:var(--sub);margin-bottom:6px';
  hint.textContent = '角色名 = 说话时显示的名字；立绘/语音 = 该角色默认值（台词点留空自动套用）。';
  wrap.appendChild(hint);
  galScript.roles.forEach(function (r, i) {
    var row = document.createElement('div'); row.style.cssText = 'display:flex;align-items:center;gap:6px;margin:6px 0';
    row.appendChild(galInput(r.name || '', '角色名', function (v) { r.name = v; }));
    row.appendChild(galInput(r.sprite || '', '立绘', function (v) { r.sprite = v; }));
    row.appendChild(galInput(r.voice || '', '语音', function (v) { r.voice = v; }));
    var del = document.createElement('button'); del.className = 'btn2 ghost'; del.textContent = '[ic:close]'; del.style.cssText = 'color:var(--danger);font-size:12px;padding:2px 6px'; del.onclick = function () { galPushUndo(); galScript.roles.splice(i, 1); galRenderRoles(); }; row.appendChild(del);
    wrap.appendChild(row);
  });
  var add = document.createElement('button'); add.className = 'btn2'; add.textContent = '[ic:add] 加角色'; add.onclick = function () { galPushUndo(); galScript.roles.push({ name: '', sprite: '', voice: '' }); galRenderRoles(); };
  wrap.appendChild(add);
  p.appendChild(wrap);
}
function galRoleSelect(ln) {
  galEnsureRoles();
  var sel = document.createElement('select');
  var opt0 = document.createElement('option'); opt0.value = ''; opt0.textContent = '（未指定）'; sel.appendChild(opt0);
  (galScript.roles || []).forEach(function (r) { var o = document.createElement('option'); o.value = r.name || ''; o.textContent = r.name || '(未命名角色)'; sel.appendChild(o); });
  sel.value = ln.speaker || '';
  sel.onchange = function () { ln.speaker = sel.value; };
  sel.style.cssText = 'flex:1;min-width:80px;background:var(--panel);border:1px solid var(--line);border-radius:6px;color:var(--text);padding:5px 8px;font-size:12px';
  return sel;
}
// ===== 回档式节点图：场景=节点 · 顺序/分支=连线 · 点节点就地编它的点 =====
function galGraphLayout() {
  var scenes = galScript.scenes || [];
  var byId = {}; scenes.forEach(function (s) { byId[s.id] = s; });
  var level = {}, order = [], seen = {}, q = [[scenes.length ? scenes[0].id : '', 0]];
  while (q.length) {
    var e = q.shift(), id = e[0], lv = e[1];
    if (!id || seen[id]) continue; seen[id] = true; level[id] = lv; order.push(id);
    var sc = byId[id]; if (!sc) continue;
    (sc.lines || []).forEach(function (ln) {
      if (ln && ln.choice) ln.choice.forEach(function (o) { if (o && o.goto && byId[o.goto] && !seen[o.goto]) q.push([o.goto, lv + 1]); });
      if (ln && ln.jump && byId[ln.jump] && !seen[ln.jump]) q.push([ln.jump, lv + 1]);
    });
    var nxt = sc.next || sc.jump;
    if (nxt && byId[nxt] && !seen[nxt]) q.push([nxt, lv + 1]);
  }
  scenes.forEach(function (s) { if (!seen[s.id]) order.push(s.id); });
  var rowIn = {};
  order.forEach(function (id) { var lv = level[id] || 0; if (rowIn[lv] === undefined) rowIn[lv] = 0; rowIn[id] = rowIn[lv]++; });
  return { byId: byId, order: order, cols: function (id) { return level[id] || 0; }, rows: function (id) { return rowIn[id] || 0; } };
}
function galRenderGraph() {
  var box = document.getElementById('galLines');
  var panel = document.getElementById('galScenePanel'); if (panel) panel.style.display = 'none';
  if (!galScript || !galScript.scenes || !galScript.scenes.length) { box.innerHTML = '<div style="color:var(--sub);padding:30px;text-align:center">还没有线(场景)。点「[ic:add] 加线」开始。</div>'; return; }
  var L = galGraphLayout();
  var nodeW = 180, nodeH = 84, gx = 260, gy = 150;
  var pos = {};
  L.order.forEach(function (id) { var sc = L.byId[id]; var px = 40 + L.cols(id) * gx, py = 30 + L.rows(id) * gy; if (sc && sc.gx !== undefined) px = sc.gx; if (sc && sc.gy !== undefined) py = sc.gy; pos[id] = { x: px, y: py }; });
  var maxX = 600, maxY = 200;
  L.order.forEach(function (id) { var p = pos[id]; if (p) { if (p.x + nodeW > maxX) maxX = p.x + nodeW; if (p.y + nodeH > maxY) maxY = p.y + nodeH; } });
  var S = galScale || 1;
  var svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + Math.ceil((maxX + 40) * S) + '" height="' + Math.ceil((maxY + 40) * S) + '" style="display:block;overflow:visible;user-select:none;-webkit-user-select:none"><defs><marker id="garr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#4a5462"/></marker></defs><g transform="scale(' + S + ')">';
  function edge(x1, y1, x2, y2, label, cond, dim, openId, focusIdx, etype, eo) {
    var op = dim === undefined ? 1 : dim;
    var dx = x2 - x1;
    var stroke = (etype === 'choice') ? (cond ? '#f59e0b' : '#e8a33d') : '#7aa2b8';
    var clickFn;
    if (etype === 'choice') clickFn = "galEditOption('" + escapeHtml(openId) + "'," + (focusIdx === undefined ? -1 : focusIdx) + "," + (eo === undefined ? -1 : eo) + ",event)";
    else clickFn = "galOpenScenePanel('" + escapeHtml(openId) + "'," + (focusIdx === undefined ? -1 : focusIdx) + ")";
    var d;
    if (dx > 4) {
      // 前向：经源右侧空隙竖道的平滑弯线（不穿节点、无死角）
      var lane = x1 + 40;
      d = 'M' + x1 + ',' + y1 + ' C' + lane + ',' + y1 + ' ' + lane + ',' + y2 + ' ' + (x2 - 2) + ',' + y2;
    } else {
      // 反向/同层：从上方绕行的弧形
      var lift = Math.min(y1, y2) - 56;
      d = 'M' + x1 + ',' + y1 + ' C' + x1 + ',' + lift + ' ' + x2 + ',' + lift + ' ' + (x2 - 2) + ',' + y2;
    }
    svg += '<path d="' + d + '" fill="none" stroke="' + stroke + '" stroke-width="1.5" stroke-opacity="' + op + '" marker-end="url(#garr)"/>';
    // 透明命中区：点整条线即可选中/编辑（不挡节点，节点在后绘制于上层）
    if (openId) svg += '<path d="' + d + '" fill="none" stroke="rgba(255,255,255,0)" stroke-width="14" style="pointer-events:stroke;cursor:pointer" data-edge="1" data-erole="' + (etype || '') + '" data-esrc="' + escapeHtml(openId) + '" data-eidx="' + (focusIdx === undefined ? -1 : focusIdx) + '" data-eo="' + (eo === undefined ? -1 : eo) + '" onclick="event.stopPropagation();' + clickFn + '"/>';
    // 标签放在竖道/折线旁，避让节点
    var laneX = (dx > 4) ? (x1 + 40) : Math.round((x1 + x2) / 2);
    var lx = laneX + 4, ly = Math.round((y1 + y2) / 2 - 6);
    if (label) svg += '<text x="' + lx + '" y="' + ly + '" fill="' + stroke + '" font-size="9" opacity="' + op + '" text-anchor="start" style="cursor:pointer" onclick="event.stopPropagation();' + clickFn + '">' + escapeHtml(label) + '</text>';
  }
  L.order.forEach(function (id) {
    var sc = L.byId[id], p = pos[id]; if (!sc || !p) return;
    var srcKey = galIsKey(sc);
    var lines = sc.lines || [];
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i]; if (!ln || typeof ln !== 'object') continue;
      if (ln.choice) ln.choice.forEach(function (o, k) {
        var gt = L.byId[o.goto];
        if (o && o.goto && gt && pos[o.goto]) edge(p.x + nodeW, p.y + nodeH / 2 + (k - (ln.choice.length - 1) / 2) * 10, pos[o.goto].x, pos[o.goto].y + nodeH / 2, ((o.if ? '[ic:lock] ' : '[ic:shuffle] ') + (o.text || '')), o.if ? 1 : 0, galKeyOnly ? (srcKey && galIsKey(gt) ? 1 : 0.25) : 1, sc.id, i, 'choice', k);
      });
      if (ln.jump && L.byId[ln.jump] && pos[ln.jump]) edge(p.x + nodeW, p.y + nodeH / 2, pos[ln.jump].x, pos[ln.jump].y + nodeH / 2, '▸ 跳', 0, galKeyOnly ? (srcKey && galIsKey(L.byId[ln.jump]) ? 1 : 0.25) : 1, sc.id, i, 'jump', 0);
    }
    var nxt = sc.next || sc.jump;
    if (nxt && L.byId[nxt] && pos[nxt]) edge(p.x + nodeW, p.y + nodeH / 2, pos[nxt].x, pos[nxt].y + nodeH / 2, '▸ 进行', 0, galKeyOnly ? (srcKey && galIsKey(L.byId[nxt]) ? 1 : 0.25) : 1, sc.id, -1, 'next', 0);
  });
  L.order.forEach(function (id) {
    var sc = L.byId[id], p = pos[id]; if (!sc || !p) return;
    var isKey = galIsKey(sc);
    var dim = galKeyOnly && !isKey ? 0.16 : 1;
    var pts = sc.lines || [];
    var body = '';
    for (var i = 0; i < Math.min(3, pts.length); i++) {
      var ln = pts[i] || {}, kind = ln.kind || 'say';
      var icon = _gKindNames[kind] || '·';
      var snip = (typeof ln.text === 'string' && ln.text) || kind;
      body += '<text x="' + (p.x + 10) + '" y="' + (p.y + 28 + i * 16) + '" fill="var(--sub)" font-size="9">' + escapeHtml(icon + ' ' + String(snip).slice(0, 18)) + '</text>';
    }
    if (pts.length > 3) body += '<text x="' + (p.x + 10) + '" y="' + (p.y + 28 + 3 * 16) + '" fill="var(--sub)" font-size="9">…</text>';
    svg += '<g data-scene="' + escapeHtml(sc.id) + '" onclick="if(!galDragged)galOpenScenePanel(\'' + escapeHtml(sc.id) + '\')" onmousedown="galNodeDown(event,\'' + escapeHtml(sc.id) + '\',' + p.x + ',' + p.y + ')" style="cursor:grab" opacity="' + dim + '">' +
      '<rect x="' + p.x + '" y="' + p.y + '" width="' + nodeW + '" height="' + nodeH + '" rx="10" fill="' + (isKey ? 'rgba(245,158,11,.14)' : 'var(--bubble)') + '" stroke="' + (isKey ? '#f59e0b' : 'var(--line)') + '" stroke-width="' + (isKey ? 2 : 1) + '"/>' +
      '<text x="' + (p.x + 10) + '" y="' + (p.y + 20) + '" fill="' + (isKey ? '#f5c06c' : 'var(--text)') + '" font-size="13" font-weight="bold">' + (isKey ? '★ ' : '') + escapeHtml(sc.title || sc.id || '') + '</text>' +
      body +
      '<text x="' + (p.x + 10) + '" y="' + (p.y + nodeH - 8) + '" fill="#f5c06c" font-size="9">' + pts.length + ' 点</text>' +
      '<text x="' + (p.x + nodeW - 14) + '" y="' + (p.y + 20) + '" fill="' + (isKey ? '#f5c06c' : 'var(--sub)') + '" font-size="12" onclick="event.stopPropagation();galToggleKey(\'' + escapeHtml(sc.id) + '\')" onmousedown="event.stopPropagation()" style="cursor:pointer">' + (isKey ? '★' : '☆') + '</text>' +
      '<circle cx="' + (p.x + nodeW) + '" cy="' + (p.y + nodeH / 2) + '" r="5" fill="#f59e0b" stroke="var(--bg)" stroke-width="1.5" onmousedown="event.stopPropagation();galConnStart(event,\'' + escapeHtml(sc.id) + '\',' + (p.x + nodeW) + ',' + (p.y + nodeH / 2) + ')" style="cursor:crosshair"></circle>' +
      '</g>';
  });
  svg += '</g></svg>';
  var _sl = box.scrollLeft, _st = box.scrollTop;
  box.innerHTML = svg;
  box.scrollLeft = _sl; box.scrollTop = _st;
}
// 画布平移 + 缩放（滚轮缩放 / 拖空白平移 / 节点仍可单独拖）
function galSetupViewport() {
  var ct = document.getElementById('galLines');
  if (!ct || ct._gv) return; ct._gv = true;
  ct.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;
    if (e.target === ct || e.target.tagName === 'svg') {
      galPan = { sx: e.clientX, sy: e.clientY, sl: ct.scrollLeft, st: ct.scrollTop };
      e.preventDefault();
      function mv(ev) { if (!galPan) return; ct.scrollLeft = galPan.sl - (ev.clientX - galPan.sx); ct.scrollTop = galPan.st - (ev.clientY - galPan.sy); }
      function up() { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); galPan = null; }
      document.addEventListener('mousemove', mv);
      document.addEventListener('mouseup', up);
    }
  });
  ct.addEventListener('wheel', function (e) {
    e.preventDefault();
    galZoomTo((galScale || 1) * (e.deltaY < 0 ? 1.12 : 0.88));
  }, { passive: false });
}
function galZoomTo(s) {
  var ct = document.getElementById('galLines');
  var sl = ct ? ct.scrollLeft : 0, st = ct ? ct.scrollTop : 0;
  galScale = Math.max(0.4, Math.min(2.5, s));
  var d = document.getElementById('galZoomVal'); if (d) d.textContent = Math.round(galScale * 100) + '%';
  galRenderGraph();
  if (ct) { ct.scrollLeft = sl; ct.scrollTop = st; }
}
function galFit() {
  var ct = document.getElementById('galLines'); if (!ct || !galScript) return;
  var L = galGraphLayout();
  var baseW = 600, baseH = 200;
  L.order.forEach(function (id) {
    var sc = L.byId[id];
    var x = (sc && sc.gx !== undefined) ? sc.gx : 40 + L.cols(id) * 260;
    var y = (sc && sc.gy !== undefined) ? sc.gy : 30 + L.rows(id) * 150;
    if (x + 180 + 40 > baseW) baseW = x + 180 + 40;
    if (y + 84 + 40 > baseH) baseH = y + 84 + 40;
  });
  var s = Math.min(ct.clientWidth / baseW, ct.clientHeight / baseH, 1.0);
  galZoomTo(Math.max(0.4, Math.min(1.5, s)));
}
// 右键菜单（节点 / 连线 / 空白）
function galMenuHide() { var m = document.getElementById('galCtx'); if (m) m.style.display = 'none'; }
function galMenuShow(items, x, y) {
  var m = document.getElementById('galCtx'); if (!m) return;
  m.innerHTML = '';
  items.forEach(function (it) {
    if (it === '-') { var s = document.createElement('div'); s.style.cssText = 'border-top:1px solid var(--line);margin:3px 0'; m.appendChild(s); return; }
    var b = document.createElement('button');
    b.textContent = it.label;
    b.style.cssText = 'display:block;width:100%;text-align:left;font-size:12px;padding:6px 10px;color:var(--text);background:transparent;border:none;cursor:pointer;border-radius:6px;transition:background .12s';
    b.onmouseenter = function () { b.style.background = 'var(--line)'; };
    b.onmouseleave = function () { b.style.background = 'transparent'; };
    b.onclick = function () { galMenuHide(); it.fn(); };
    m.appendChild(b);
  });
  m.style.display = 'block';
  m.style.left = Math.min(x, (window.innerWidth || 1200) - 220) + 'px';
  m.style.top = Math.min(y, (window.innerHeight || 800) - items.length * 34 - 20) + 'px';
}
// 就地编辑「选项」：点选项弹出小编辑框（文本/goto/条件），无需跳面板
function galOptPopClose() { var p = document.getElementById('galOptPop'); if (p) p.style.display = 'none'; }
function galEditOption(srcId, idx, eo, ev) {
  if (ev && ev.stopPropagation) ev.stopPropagation();
  var sc = (galScript.scenes || []).find(function (s) { return s.id === srcId; });
  var ln = sc && sc.lines && sc.lines[idx];
  var opts = ln && ln.choice;
  var o = opts && opts[eo];
  var p = document.getElementById('galOptPop');
  if (!p || !sc || !o) return;
  p.innerHTML = '<b style="font-size:13px;color:var(--warn)">[ic:edit] 编辑选项</b>';
  var t = galInput(o.text || '', '选项文字', function (v) { o.text = v; }); t.style.cssText = 'display:block;width:100%;margin-top:6px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:6px 8px;font-size:12px'; p.appendChild(t);
  var g = galInput(o.goto || '', '目标场景 id (goto)', function (v) { o.goto = v; }); g.style.cssText = 'display:block;width:100%;margin-top:6px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:6px 8px;font-size:12px'; p.appendChild(g);
  var c = galInput(o.if ? JSON.stringify(o.if) : '', '[ic:lock] 条件 {"aff":">=85"}（可留空）', function (v) { try { o.if = v.trim() ? JSON.parse(v) : undefined; } catch (e) { o.if = undefined; } }); c.style.cssText = 'display:block;width:100%;margin-top:6px;background:var(--bubble);border:1px solid rgba(245,158,11,.4);border-radius:6px;color:var(--warn);padding:6px 8px;font-size:12px'; p.appendChild(c);
  var btns = document.createElement('div'); btns.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-top:8px';
  var del = document.createElement('button'); del.className = 'btn2 ghost'; del.textContent = '[ic:delete] 删选项'; del.style.cssText = 'color:var(--danger);padding:5px 12px'; del.onclick = function () { galPushUndo(); opts.splice(eo, 1); galOptPopClose(); galRenderGraph(); }; btns.appendChild(del);
  var right = document.createElement('div');
  var add1 = document.createElement('button'); add1.className = 'btn2'; add1.textContent = '[ic:add] 加选项'; add1.style.cssText = 'padding:5px 12px'; add1.onclick = function () { galPushUndo(); opts.push({ text: '选项', goto: '' }); galOptPopClose(); galRenderGraph(); }; right.appendChild(add1);
  var done = document.createElement('button'); done.className = 'btn2'; done.textContent = '[ic:check_circle] 完成'; done.style.cssText = 'padding:5px 12px;margin-left:6px'; done.onclick = function () { galOptPopClose(); galRenderGraph(); }; right.appendChild(done);
  btns.appendChild(right);
  p.appendChild(btns);
  p.style.display = 'block';
  p.style.left = Math.min((ev && ev.clientX) || 40, (window.innerWidth || 1200) - 320) + 'px';
  p.style.top = Math.min((ev && ev.clientY) || 40, (window.innerHeight || 800) - 240) + 'px';
  document.addEventListener('click', function h(e) { var mp = document.getElementById('galOptPop'); if (mp && mp.style.display === 'block' && !mp.contains(e.target)) { mp.style.display = 'none'; document.removeEventListener('click', h); } });
}

function galDeleteEdge(srcId, role, idx, eo) {
  var sc = (galScript.scenes || []).find(function (s) { return s.id === srcId; });
  if (!sc) return;
  galPushUndo();
  if (role === 'next') { delete sc.next; }
  else if (role === 'jump') { var l = sc.lines && sc.lines[idx]; if (l) delete l.jump; }
  else if (role === 'choice') { var cp = sc.lines && sc.lines[idx]; if (cp && cp.choice) { cp.choice.splice(eo, 1); if (cp.choice.length === 0) sc.lines.splice(idx, 1); } }
  galRenderGraph();
}
function galSetupCtx() {
  var ct = document.getElementById('galLines');
  if (!ct || ct._gctx) return; ct._gctx = true;
  ct.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    var t = e.target, edge = null, node = null;
    while (t && t.getAttribute) {
      if (t.getAttribute('data-edge')) { edge = t; break; }
      if (t.getAttribute('data-scene')) { node = t.getAttribute('data-scene'); break; }
      t = t.parentNode;
    }
    if (edge) {
      var src = edge.getAttribute('data-esrc'), role = edge.getAttribute('data-erole'), idx = parseInt(edge.getAttribute('data-eidx'), 10), eo = parseInt(edge.getAttribute('data-eo'), 10);
      galMenuShow([
        { label: '[ic:edit] 编辑此分支', fn: function () { galOpenScenePanel(src, idx); } },
        { label: '[ic:delete] 删除此连接', fn: function () { galDeleteEdge(src, role, idx, eo); } },
      ], e.clientX, e.clientY);
    } else if (node) {
      var sc = (galScript.scenes || []).find(function (s) { return s.id === node; });
      galMenuShow([
        { label: '[ic:edit] 编辑点', fn: function () { galOpenScenePanel(node); } },
        { label: galIsKey(sc) ? '☆ 标为叙事线' : '[ic:star] 标为关键节点', fn: function () { galToggleKey(node); } },
        { label: '[ic:edit] 重命名线', fn: function () { var n = prompt('线标题：', (sc && sc.title) || ''); if (n !== null && sc) { sc.title = n; galRenderGraph(); } } },
        { label: '[ic:delete] 删除线(场景)', fn: function () { if (confirm('删除线「' + ((sc && sc.title) || node) + '」？')) { galScript.scenes = galScript.scenes.filter(function (s) { return s.id !== node; }); galRenderGraph(); } } },
      ], e.clientX, e.clientY);
    } else {
      galMenuShow([
        { label: '[ic:add] 加线(场景)', fn: galAddLine },
        { label: galKeyOnly ? '[ic:star] 全部' : '[ic:star] 仅看关键', fn: function () { galKeyOnly = !galKeyOnly; var b = document.getElementById('galKeyBtn'); if (b) b.textContent = galKeyOnly ? '[ic:star] 全部' : '[ic:star] 仅看关键'; galRenderGraph(); } },
        { label: '[ic:search] 缩放 100%', fn: function () { galScale = 1; galRenderGraph(); } },
      ], e.clientX, e.clientY);
    }
  });
  document.addEventListener('click', function (e) { var m = document.getElementById('galCtx'); if (m && m.style.display === 'block' && !m.contains(e.target)) galMenuHide(); });
}
// 全局兜底：松开鼠标清除可能残留的拖拽高亮（避免节点"变白"卡住）
document.addEventListener('mouseup', function () {
  if (galConnTarget) { var g = document.querySelector('[data-scene="' + galConnTarget + '"]'); if (g) g.style.filter = ''; galConnTarget = null; }
});
function galOpenScenePanel(sid, focusIdx) {
  var sc = (galScript.scenes || []).find(function (s) { return s.id === sid; });
  var panel = document.getElementById('galScenePanel');
  if (!sc || !panel) return;
  panel.style.display = 'block';
  panel.innerHTML = '';
  var h = document.createElement('div');
  h.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)';
  h.innerHTML = '<b style="font-size:14px;color:var(--warn)">线 ' + escapeHtml(sc.id) + ' 「' + escapeHtml(sc.title || '') + '」 · 编辑点</b>';
  var keyBtn = document.createElement('button'); keyBtn.className = 'btn2'; keyBtn.textContent = galIsKey(sc) ? '[ic:star] 关键节点' : '☆ 叙事线'; keyBtn.onclick = function () { galToggleKey(sc.id); galOpenScenePanel(sc.id, focusIdx); };
  h.appendChild(keyBtn);
  var close = document.createElement('button'); close.className = 'btn2 ghost'; close.textContent = '[ic:close] 收起'; close.onclick = function () { panel.style.display = 'none'; galRenderGraph(); };
  h.appendChild(close);
  panel.appendChild(h);
  // 场景级图片（进入该线即显示，可被点内图片覆盖/退出）
  var sImg = document.createElement('div'); sImg.style.cssText = 'padding:12px 16px;border-bottom:1px dashed var(--line);font-size:12px;color:var(--sub,#8a93a3)';
  sImg.appendChild(document.createTextNode('场景图片(进入即显示): '));
  var sList = document.createElement('span'); sList.style.cssText = 'display:inline-flex;flex-wrap:wrap;gap:8px;margin-top:6px';
  sc.images = sc.images || [];
  var renderS = function () {
    sList.innerHTML = '';
    sc.images.forEach(function (f, i) {
      var inp = galInput(f, '图片文件', function (v) { sc.images[i] = v; }); inp.style.cssText = 'width:150px;background:var(--bubble);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:6px 8px;font-size:12px';
      var rm = document.createElement('button'); rm.textContent = '[ic:close]'; rm.className = 'btn2 ghost'; rm.style.cssText = 'color:var(--danger);font-size:12px;padding:4px 8px'; rm.onclick = function () { galPushUndo(); sc.images.splice(i, 1); renderS(); };
      sList.appendChild(inp); sList.appendChild(rm);
    });
  };
  renderS();
  sImg.appendChild(sList);
  var addS = document.createElement('button'); addS.className = 'btn2 ghost'; addS.textContent = '[ic:add] 加场景图'; addS.style.cssText = 'font-size:12px;padding:5px 10px;margin-left:8px'; addS.onclick = function () { galPushUndo(); sc.images.push(''); renderS(); }; sImg.appendChild(addS);
  panel.appendChild(sImg);
  // 快速插入调色板：点一下插一个对应类型的点（尽量简化）
  var pal = document.createElement('div'); pal.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px;border-bottom:1px solid var(--line);font-size:12px;color:var(--sub)';
  pal.appendChild(document.createTextNode('快速加点: '));
  [['[ic:chat_bubble] 台词', {kind:'say', text:''}], ['[ic:note] 旁白', {kind:'note', note:''}], ['[ic:image] 换景', {kind:'bg', bg:''}],
   ['[ic:music_note] 换BGM', {kind:'bgm', bgm:''}], ['[ic:mic] 配音', {kind:'say', voice:''}], ['[ic:flare] 特效', {kind:'effect', effect:'shake'}],
   ['[ic:hourglass_empty] 等待', {kind:'wait', ms:500}], ['[ic:shuffle] 分支', {kind:'choice', choice:[{text:'', goto:''}]}],
   ['[ic:arrow_right] 跳转', {kind:'jump', goto:''}], ['[ic:sports_score] 结局', {kind:'end', end:''}], ['[ic:settings] 动作', {kind:'action', action:''}]
  ].forEach(function (p) {
    var b = document.createElement('button'); b.className = 'btn2 ghost'; b.textContent = p[0];
    b.style.cssText = 'font-size:12px;padding:5px 12px';
    b.onclick = function () { galPushUndo(); (sc.lines = sc.lines || []).push(JSON.parse(JSON.stringify(p[1]))); render(); };
    pal.appendChild(b);
  });
  panel.appendChild(pal);
  var body = document.createElement('div'); body.style.cssText = 'padding:12px 16px;display:flex;flex-direction:column;gap:10px';
  panel.appendChild(body);
  var focused = null;
  function render() {
    body.innerHTML = '';
    var lines = sc.lines || []; sc.lines = lines;
    for (var i = 0; i < lines.length; i++) {
      var r = galScenePointRow(sc, lines[i], render);
      // 2026-11 容器令牌化：选中框原来写死 #f59e0b（＝暗色 --warn）；浅色主题下 --warn 是 #b45309
      // （#f59e0b 压白只有 2.13:1，作为焦点框不达标），换令牌后暗色取值逐字节相同。
      if (i === focusIdx) { r.style.outline = '2px solid var(--warn)'; r.style.outlineOffset = '2px'; focused = r; }
      body.appendChild(r);
    }
    var add = document.createElement('button'); add.className = 'btn2'; add.textContent = '[ic:add] 加一点'; add.onclick = function () { galPushUndo(); lines.push({ kind: 'say', text: '' }); render(); };
    body.appendChild(add);
  }
  render();
  galLoadAssets(function () { try { render(); } catch (e) {} });   // 素材清单到了再刷一次下拉
  if (focused && focused.scrollIntoView) focused.scrollIntoView({ block: 'center' });
}
