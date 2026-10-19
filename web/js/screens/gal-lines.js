/* web/js/screens/gal-lines.js —— GAL 线内渲染（旧版「展开一条线看所有点」）+ 连线 + 保存/JSON/体检，
 * 以及本屏全部按钮绑定（片段注入后由 galMount 调）。
 *
 * 归属：结构在 web/screens/gal.html；按钮就是工具条上那一排（galSaveBtn/galUndoBtn/…）。
 * 说明：galSave/galJson 以前直接写编年史的 JSON 面板（跨屏摸 DOM），现在改成
 *       DICK.bus('codex:json-sync' / 'codex:json-open')，由 codex 屏自己写自己的 textarea —— 界面表现不变。
 */

function galRenderLines() {
  var box = document.getElementById('galLines');
  box.innerHTML = '';
  galBodies = {};
  if (!galScript || !galScript.scenes || !galScript.scenes.length) {
    box.innerHTML = '<div style="color:var(--sub,#8a93a3);padding:30px;text-align:center">还没有线(场景)。点右上角「[ic:add] 加线(场景)」开始。</div>';
    return;
  }
  galScript.scenes.forEach(function (sc) { box.appendChild(galLineEl(sc)); });
}
function galLineEl(sc) {
  var line = document.createElement('div'); line.className = 'gal-line';
  var head = document.createElement('div'); head.className = 'gal-line-head';
  head.innerHTML = '<b>线 ' + escapeHtml(sc.id || '') + '</b><span class="gal-count">「' + escapeHtml((sc.title || '').slice(0, 20)) + '」</span>' +
    '<span class="gal-count"> ' + ((sc.lines || []).length) + ' 点</span>' +
    '<span class="gal-count">' + (galAllOpen[sc.id] ? ' [ic:keyboard_arrow_up] 收起' : ' [ic:keyboard_arrow_down] 展开') + '</span><span style="flex:1"></span>';
  head.title = '点击整条展开/收起';
  head.setAttribute('data-head', sc.id);
  line.appendChild(head);
  var body = document.createElement('div'); body.className = 'gal-body';
  line.appendChild(body);
  galBodies[sc.id] = body;
  head.onclick = function () { galToggleLine(sc, body, head); };
  galRenderBody(sc, body, galAllOpen[sc.id] ? -2 : -1);
  return line;
}
function galToggleLine(sc, body, head) {
  galAllOpen[sc.id] = !galAllOpen[sc.id];
  galRenderBody(sc, body, galAllOpen[sc.id] ? -2 : -1);
  if (head) {
    var sp = head.querySelector ? head.querySelector('.gal-count:last-of-type') : null;
    if (sp) sp.textContent = galAllOpen[sc.id] ? ' [ic:keyboard_arrow_up] 收起' : ' [ic:keyboard_arrow_down] 展开';
  }
}
function galRenderBody(sc, body, openIdx) {
  body.innerHTML = '';
  var lines = sc.lines || []; sc.lines = lines;
  for (var i = 0; i < lines.length; i++) {
    var ins = document.createElement('button'); ins.className = 'gal-insert'; ins.textContent = '+';
    ins.onclick = function (ev) { galInsertAt(sc, parseInt(ev.currentTarget.getAttribute('data-at'), 10), body); };
    ins.setAttribute('data-at', i);
    body.appendChild(ins);
    if (openIdx === i || openIdx === -2) {
      body.appendChild(galEditorEl(sc, i, body));
    } else {
      body.appendChild(galChipEl(sc, i));
      if ((sc.lines[i].kind || 'say') === 'choice') (sc.lines[i].choice || []).forEach(function (o) {
        var f = document.createElement('span'); f.className = 'gal-fork';
        f.setAttribute('data-goto', o.goto || '');
        f.setAttribute('data-cond', o.if ? '1' : '');
        f.textContent = ((o.if ? '[ic:lock] ' : '[ic:shuffle] ') + (o.text || '') + ' → ' + (o.goto || ''));
        body.appendChild(f);
      });
    }
  }
  var last = document.createElement('button'); last.className = 'gal-insert'; last.textContent = '+';
  last.setAttribute('data-at', lines.length);
  last.onclick = function (ev) { galInsertAt(sc, parseInt(ev.currentTarget.getAttribute('data-at'), 10), body); };
  body.appendChild(last);
  galDrawConnectors();
}
function galChipEl(sc, i) {
  var ln = sc.lines[i];
  var kind = ln.kind || 'say';
  var c = document.createElement('div');
  c.className = 'gal-chip' + (kind === 'choice' ? ' choice' : '');
  var icon = _gKindIcon[kind] || '·';
  var snip = (typeof ln.text === 'string' && ln.text) || (kind === 'choice' ? '分支' : kind);
  c.innerHTML = '<span class="gal-k">' + escapeHtml(icon) + '</span><span>' + escapeHtml(String(snip).slice(0, 16)) + '</span>';
  c.onclick = function () { galRenderBody(sc, galBodies[sc.id], i); };
  c.draggable = true;
  c.dataset.idx = i;
  c.addEventListener('dragstart', function () { galDrag = { scene: sc.id, idx: i }; });
  c.addEventListener('dragover', function (e) { e.preventDefault(); c.classList.add('drag-over'); });
  c.addEventListener('dragleave', function () { c.classList.remove('drag-over'); });
  c.addEventListener('drop', function (e) { e.preventDefault(); c.classList.remove('drag-over'); galReorder(sc, i); });
  return c;
}
function galReorder(sc, targetIdx) {
  if (!galDrag || galDrag.scene !== sc.id) return;
  var src = galDrag.idx; galDrag = null;
  if (src === targetIdx) return;
  var mv = sc.lines.splice(src, 1)[0];
  sc.lines.splice(targetIdx, 0, mv);
  galRenderBody(sc, galBodies[sc.id], -1);
}
// 可视化分支连接线：从 choice 选项点<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌画箭头指向目标「线头」，并带选项/条件标签
function galDrawConnectors() {
  if (!document.createElementNS || !galScript || !galScript.scenes) return;
  var ct = document.getElementById('galLines');
  var old = document.getElementById('galConn'); if (old && old.remove) old.remove();
  if (!ct) return;
  var ctr = ct.getBoundingClientRect();
  var W = ct.scrollWidth || ct.clientWidth, H = ct.scrollHeight || ct.clientHeight;
  var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('id', 'galConn');
  svg.style.cssText = 'position:absolute;left:0;top:0;width:' + W + 'px;height:' + H + 'px;pointer-events:none;z-index:5';
  var heads = {};
  var hs = ct.querySelectorAll('[data-head]');
  for (var i = 0; i < hs.length; i++) heads[hs[i].getAttribute('data-head')] = hs[i];
  function draw(x1, y1, x2, y2, label, isCond) {
    var xm = x2 - 12, ym = y2;
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', 'M' + x1 + ',' + y1 + ' C' + (x1 + 40) + ',' + y1 + ' ' + (xm - 40) + ',' + ym + ' ' + xm + ',' + ym);
    p.setAttribute('fill', 'none'); p.setAttribute('stroke', isCond ? '#f59e0b' : '#4a5462'); p.setAttribute('stroke-width', '1.5');
    svg.appendChild(p);
    var a = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    a.setAttribute('d', 'M' + xm + ',' + (ym - 4) + ' L' + (x2 - 2) + ',' + ym + ' L' + xm + ',' + (ym + 4) + ' Z');
    a.setAttribute('fill', isCond ? '#f59e0b' : '#4a5462');
    svg.appendChild(a);
    if (label) {
      var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('x', Math.round((x1 + x2) / 2));
      t.setAttribute('y', Math.round((y1 + y2) / 2 - 5));
      t.setAttribute('fill', isCond ? '#f5c06c' : '#8a93a3');
      t.setAttribute('font-size', '10'); t.setAttribute('text-anchor', 'middle');
      t.textContent = label;
      svg.appendChild(t);
    }
  }
  var forks = ct.querySelectorAll('[data-goto]');
  for (var j = 0; j < forks.length; j++) {
    var f = forks[j], g = f.getAttribute('data-goto'), tgt = heads[g];
    if (!tgt) continue;
    var fr = f.getBoundingClientRect(), tr = tgt.getBoundingClientRect();
    var x1 = fr.left - ctr.left + ct.scrollLeft, y1 = (fr.top + fr.height / 2) - ctr.top + ct.scrollTop;
    var x2 = tr.left - ctr.left + ct.scrollLeft, y2 = (tr.top + tr.height / 2) - ctr.top + ct.scrollTop;
    draw(x1, y1, x2, y2, (f.getAttribute('data-cond') ? '[ic:lock] ' : '[ic:shuffle] ') + (f.textContent || ''), !!f.getAttribute('data-cond'));
  }
  ct.appendChild(svg);
}
function galDeleteAt(sc, i, body) {
  sc.lines.splice(i, 1);
  galRenderBody(sc, body, -1);
}
function galInsertAt(sc, i, body) {
  sc.lines.splice(i, 0, { kind: 'say', text: '' });
  galRenderBody(sc, body, i);
}
function galEditorEl(sc, i, body) {
  var ln = sc.lines[i] || {};
  var box = document.createElement('div'); box.className = 'gal-editor'; box.style.cssText = 'flex-basis:100%';
  var row = document.createElement('div'); row.className = 'row';
  var sel = document.createElement('select');
  Object.keys(_gKindNames).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = _gKindNames[k]; sel.appendChild(o); });
  sel.value = ln.kind || 'say';
  sel.onchange = function () { ln.kind = sel.value; if (ln.kind === 'choice') ln.choice = ln.choice || []; if (ln.kind !== 'say') { delete ln.sprite; delete ln.voice; } galRenderBody(sc, body, i); };
  var kindL = document.createElement('label'); kindL.textContent = '类型：'; row.appendChild(kindL); row.appendChild(sel);
  box.appendChild(row);
  if (ln.kind === 'choice') {
    var optBox = document.createElement('div');
    var opts = ln.choice || []; ln.choice = opts;
    var renderOpts = function () {
      optBox.innerHTML = '';
      opts.forEach(function (o, k) {
        var r = document.createElement('div'); r.className = 'row';
        r.appendChild(galInput(o.text || '', '选项文字', function (v) { o.text = v; }));
        r.appendChild(galInput(o.goto || '', 'goto', function (v) { o.goto = v; }));
        var c = galInput(o.if ? JSON.stringify(o.if) : '', '[ic:lock] 条件 {"aff":">=85"}', function (v) { try { o.if = v.trim() ? JSON.parse(v) : undefined; } catch (e) { o.if = undefined; } });
        c.style.cssText = 'flex:1;min-width:150px;background:var(--bubble,#161b22);border:1px solid rgba(245,158,11,.4);border-radius:6px;color:var(--warn);padding:5px 8px;font-size:12px';
        r.appendChild(c);
        var del = document.createElement('button'); del.className = 'btn2 ghost'; del.textContent = '[ic:close]'; del.style.cssText = 'font-size:11px;padding:2px 6px;color:var(--danger)'; del.onclick = function () { opts.splice(k, 1); renderOpts(); };
        r.appendChild(del);
        optBox.appendChild(r);
      });
      var add = document.createElement('button'); add.className = 'btn2 ghost'; add.textContent = '[ic:add] 选项'; add.style.cssText = 'font-size:11px;padding:3px 8px';
      add.onclick = function () { opts.push({ text: '', goto: '' }); renderOpts(); };
      optBox.appendChild(add);
    };
    renderOpts();
    box.appendChild(optBox);
  } else {
    if (ln.kind === 'say') {
      box.appendChild(galInput(ln.sprite || '', '立绘文件', function (v) { ln.sprite = v; }));
      box.appendChild(galInput(ln.voice || '', '语音', function (v) { ln.voice = v; }));
    }
    if (ln.kind === 'setflag') box.appendChild(galInput((ln.flag && ln.flag.k) || '', 'flag 名', function (v) { ln.flag = { k: v, v: true }; }));
    if (ln.kind === 'roll') box.appendChild(galInput((ln.roll && ln.roll.d) || 100, '面数', function (v) { ln.roll = { d: Number(v) || 100 }; }));
    if (ln.kind === 'effect') box.appendChild(galInput(ln.effect || 'shake', 'shake/flash', function (v) { ln.effect = v; }));
    if (ln.kind === 'wait') box.appendChild(galInput(ln.ms || 300, '毫秒', function (v) { ln.ms = Number(v) || 0; }));
    if (ln.kind === 'jump') box.appendChild(galInput(ln.goto || '', '目标线 id', function (v) { ln.goto = v; }));
    if (ln.kind === 'end') box.appendChild(galInput(ln.end || '', '结局文本', function (v) { ln.end = v; }));
    box.appendChild(galInput(ln.text || '', '台词/内容', function (v) { ln.text = v; }));
  }
  var ops = document.createElement('div'); ops.className = 'row';
  var done = document.createElement('button'); done.className = 'btn2'; done.textContent = '[ic:check_circle] 完成'; done.onclick = function () { galRenderBody(sc, body, -1); };
  var del = document.createElement('button'); del.className = 'btn2 ghost'; del.textContent = '[ic:delete] 删本点'; del.style.cssText = 'color:var(--danger)'; del.onclick = function () { galDeleteAt(sc, i, body); };
  var after = document.createElement('button'); after.className = 'btn2 ghost'; after.textContent = '[ic:add] 其后插入'; after.onclick = function () { galInsertAt(sc, i + 1, body); };
  ops.appendChild(done); ops.appendChild(del); ops.appendChild(after);
  box.appendChild(ops);
  return box;
}
function galAddLine() {
  var t = prompt('新场景(线)标题：', '场景 ' + ((galScript.scenes || []).length + 1));
  if (t === null) return;
  galPushUndo();
  galScript.scenes = galScript.scenes || [];
  var base = galScript.scenes.length + 1, nid = 's' + base;
  while (galScript.scenes.some(function (s) { return s.id === nid; })) { base++; nid = 's' + base; }
  galScript.scenes.push({ id: nid, title: (t || nid).trim(), lines: [] });
  galRenderGraph(); galStatsSet();
}
function galSave() {
  if (!galScript) { return; }
  try {
    DICK.bus.emit('codex:json-sync', { script: galScript, save: true });
    galStatsSet();
    galPushUndo();
    galToast('[ic:check_circle] 已保存');
  } catch (e) { alert('保存失败: ' + e.message); }
}
function galJson() {
  if (!galScript) return;
  _gScript = galScript;
  DICK.bus.emit('codex:json-open', { script: galScript });
  galCloseEditor();
}
function galBindBar() {
  document.getElementById('galSaveBtn').onclick = galSave;
  document.getElementById('galRoleBtn').onclick = galToggleRoles;
  document.getElementById('galCheckBtn').onclick = galCheckRun;
}
// ---------- 剧本体检（结构 / 预览一致性 / 素材 / 统计）----------
function galCheckRender(r) {
  var box = document.getElementById('galCheckPanel');
  if (!r || r.err) {
    box.innerHTML = '<div style="color:var(--danger)">体检失败：' + ((r && r.err) || '未知错误') + '</div>';
    box.style.display = 'block';
    return;
  }
  var st = r.stats || {};
  var h = [];
  h.push('<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">' +
    '<b>[ic:search] 剧本体检</b>' +
    '<span style="color:var(--sub);font-size:12px">线 ' + (st.scenes || 0) + ' · 点 ' + (st.lines || 0) +
    ' · 选项 ' + (st.choices || 0) + ' · 结局 ' + (st.endings || 0) +
    ' · 约 ' + (st.est_minutes || 0) + ' 分钟' + (r.checked_pkg ? ' · 已查素材' : ' · 未查素材（先保存）') + '</span>' +
    '<span style="flex:1"></span>' +
    '<button class="btn2 ghost" style="width:auto;margin:0;padding:3px 10px" onclick="galCheckHide()">收起</button></div>');
  var issues = r.issues || [], warns = r.warnings || [];
  if (!issues.length && !warns.length) {
    h.push('<div style="color:var(--ok)">[ic:check_circle] 没查出问题：场景都可达、没有死行、能走到结局、素材引用完整。</div>');
  }
  if (issues.length) {
    h.push('<div style="color:var(--danger);margin:6px 0 4px"><b>结构问题 ' + issues.length + ' 条（会真的坏）</b></div>');
    issues.forEach(function (t) {
      h.push('<div style="padding:3px 0 3px 14px;border-left:2px solid #f87171;margin-bottom:3px">' + galCheckEsc(t) + '</div>');
    });
  }
  if (warns.length) {
    h.push('<div style="color:var(--warn);margin:10px 0 4px"><b>提示 ' + warns.length + ' 条（不坏，但会咬人）</b></div>');
    warns.forEach(function (t) {
      h.push('<div style="padding:3px 0 3px 14px;border-left:2px solid #fbbf24;margin-bottom:3px">' + galCheckEsc(t) + '</div>');
    });
  }
  box.innerHTML = h.join('');
  box.style.display = 'block';
}
function galCheckEsc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function galCheckHide() { document.getElementById('galCheckPanel').style.display = 'none'; }
function galCheckRun() {
  var box = document.getElementById('galCheckPanel');
  box.innerHTML = '<div style="color:var(--sub)">体检中…</div>';
  box.style.display = 'block';
  var pkg = (document.getElementById('galPkgSel') || {}).value || '';
  pywebview.api.codex_analyze(JSON.stringify(galScript || {}), pkg).then(galCheckRender)
    .catch(function (e) {
      box.innerHTML = '<div style="color:var(--danger)">体检调用失败：' + galCheckEsc(e) + '</div>';
    });
}
function galBindEditor() {
  galSetupViewport();
  galSetupCtx();
  document.getElementById('galUndoBtn').onclick = galUndo;
  document.getElementById('galRedoBtn').onclick = galRedo;
  document.getElementById('galAddLineBtn').onclick = galAddLine;
  document.getElementById('galZoomIn').onclick = function () { galZoomTo((galScale || 1) * 1.15); };
  document.getElementById('galZoomOut').onclick = function () { galZoomTo((galScale || 1) / 1.15); };
  document.getElementById('galZoomFit').onclick = galFit;
  // 缩放栏可拖动（避免挡住画布）
  (function () {
    var z = document.getElementById('galZoom'); if (!z) return;
    var zd = null;
    z.addEventListener('mousedown', function (ev) {
      if (ev.button !== 0) return;
      var b = z.getBoundingClientRect();
      zd = { sx: ev.clientX, sy: ev.clientY, ox: b.left, oy: b.top };
      ev.preventDefault();
      function mv(e) { if (!zd) return; z.style.left = (zd.ox + (e.clientX - zd.sx)) + 'px'; z.style.top = (zd.oy + (e.clientY - zd.sy)) + 'px'; z.style.bottom = 'auto'; }
      function up() { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); zd = null; }
      document.addEventListener('mousemove', mv);
      document.addEventListener('mouseup', up);
    });
  })();
  document.addEventListener('keydown', function (e) {
    if (!galScript || document.getElementById('galEditor').style.display !== 'flex') return;
    var mod = e.ctrlKey || e.metaKey;
    if (mod && e.key === 'z') { e.preventDefault(); if (e.shiftKey) galRedo(); else galUndo(); }
    else if (mod && e.key === 'y') { e.preventDefault(); galRedo(); }
  });
  document.getElementById('galAddLineBtn').onclick = galAddLine;
  document.getElementById('galJsonBtn').onclick = galJson;
  document.getElementById('galCloseBtn').onclick = galCloseEditor;
  document.getElementById('galPlayBtn').onclick = galPlay;
  document.getElementById('galImportBtn').onclick = galImport;
  document.getElementById('galExeBtn').onclick = galPackExe;
  document.getElementById('galPlayerBtn').onclick = galPackPlayer;
  document.getElementById('galNewBtn').onclick = galNewPkg;
  document.getElementById('galKeyBtn').onclick = function () { galKeyOnly = !galKeyOnly; this.textContent = galKeyOnly ? '[ic:star] 全部' : '[ic:star] 仅看关键'; galRenderGraph(); };
  document.getElementById('galPkgSel').onchange = function () { var n = this.value; if (n) galOpenEditor(n); };
}
