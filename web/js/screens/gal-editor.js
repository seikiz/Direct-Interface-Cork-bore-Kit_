/* web/js/screens/gal-editor.js —— GAL 制作器：撤销/重做、节点拖动、连线、素材下拉、开编辑器。
 *
 * 归属（阶段 5：index.html 里最后两块屏之一整块搬出，2026-11）
 * 结构 web/screens/gal.html（galEditor 全屏画布）
 * 样式 web/styles/screens/gal.css —— 原 screens.css 里 .gal-* 那 18 条规则原样搬出，
 *      <link> 仍紧跟 styles/screens.css（层叠顺序一字未动）
 * 数据 web/js/store/gal.js（gal.* 共 15 个域；老名字 galScript/galPan/galScale … 是兼容访问器）
 * 同块其它文件（按加载顺序）：
 *   gal-canvas.js（角色面板/节点图渲染/缩放平移/右键菜单/场景面板）
 *   → gal-scene.js（场景步骤行/干净界面入口/新建包）
 *   → gal-player.js（预览/导出原生播放器）
 *   → gal-lines.js（线内渲染/连线/保存/JSON/体检 + 全部按钮绑定）
 *
 * 契约
 * · 本文件是 gal 这一屏唯一的注册点（mount/unmount/register 在文件末尾）。
 * · 本屏只碰 gal 前缀的 id；要开编年史的东西（播放器、JSON 面板）一律发 DICK.bus 事件。
 * · 坐标/连线/缩放算法一行没改 —— 搬迁口径是「逐字」，不是「重写」。
 *
 * 依赖的外部符号：pywebview.api.codex_*（后端按包名取剧本）、escapeHtml()、codexCur（当前包）
 */


// ===== GAL 制作器 · 全屏「线-点-<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌分支」编辑器（单独界面，在线内编辑） =====
// GAL 制作器 gal 的数据层收进 DICK.state（10 个：galScript、galBodies、galDrag、galKeyOnly、galDragNode、galDragged、galPan、galScale、galU、galR）；注册在 web/js/store/gal.js

function galSnap() { try { return JSON.stringify(galScript); } catch (e) { return null; } }
function galPushUndo() { var s = galSnap(); if (s) { galU.push(s); if (galU.length > 100) galU.shift(); galR = []; } }
function galUndo() {
  if (!galU.length || !galScript) return;
  galR.push(galSnap());
  galScript = JSON.parse(galU.pop());
  if (!galScript.scenes) galScript.scenes = [];
  galRenderGraph(); galStatsSet();
}
function galRedo() {
  if (!galR.length || !galScript) return;
  galU.push(galSnap());
  galScript = JSON.parse(galR.pop());
  if (!galScript.scenes) galScript.scenes = [];
  galRenderGraph(); galStatsSet();
}
function galToast(msg) {
  var t = document.getElementById('galToast'); if (!t) return;
  t.textContent = msg; t.style.display = 'block'; t.style.opacity = '1';
  clearTimeout(t._tm);
  t._tm = setTimeout(function () { t.style.opacity = '0'; setTimeout(function () { t.style.display = 'none'; }, 300); }, 1600);
}
// GAL 制作器 gal 的数据层收进 DICK.state（3 个：galConnecting、galConnTarget、galRAF）；注册在 web/js/store/gal.js
function galNodeDown(ev, id, baseX, baseY) {
  if (ev.button !== 0) return;   // 右/中键不触发拖节点（给右键菜单用）
  ev.stopPropagation();
  galDragged = false;
  galDragNode = { id: id, sx: ev.clientX, sy: ev.clientY, bx: baseX, by: baseY };
  document.addEventListener('mousemove', galNodeMove);
  document.addEventListener('mouseup', galNodeUp);
}
function galNodeMove(ev) {
  if (!galDragNode) return;
  var dx = ev.clientX - galDragNode.sx, dy = ev.clientY - galDragNode.sy;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
    if (!galDragged) { galDragged = true; galPushUndo(); }
    var sc = (galScript.scenes || []).find(function (s) { return s.id === galDragNode.id; });
    if (sc) {
      sc.gx = galDragNode.bx + dx; sc.gy = galDragNode.by + dy;
      if (!galRAF) galRAF = requestAnimationFrame(function () { galRAF = null; galRenderGraph(); });  // 实时重画(平滑)，线跟着走
    }
  }
}
function galNodeUp(ev) {
  if (!galDragNode) return;
  document.removeEventListener('mousemove', galNodeMove);
  document.removeEventListener('mouseup', galNodeUp);
  if (galRAF) { cancelAnimationFrame(galRAF); galRAF = null; galRenderGraph(); }
  galDragNode = null;   // galDragged 保持 true 直到下次 mousedown（抑制拖动后点击开面板）
}
// 连接节点：从端口拖到目标节点 → 建立 next / choice 分支
function galConnStart(ev, srcId, x0, y0) {
  if (ev.button !== 0) return;
  ev.stopPropagation();
  galConnecting = { srcId: srcId, x0: x0, y0: y0, svg: document.querySelector('#galLines svg') };
  var svg = galConnecting.svg;
  if (svg) {
    // 追加到缩放组内，保证与节点/线同一坐标系（缩放时对齐）
    var host = svg.querySelector('g[transform]') || svg;
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('stroke', '#f59e0b'); p.setAttribute('stroke-width', '2'); p.setAttribute('fill', 'none'); p.setAttribute('stroke-dasharray', '5 3'); p.setAttribute('d', 'M' + x0 + ',' + y0 + ' L' + x0 + ',' + y0);
    host.appendChild(p);
    galConnecting.line = p;
  }
  document.addEventListener('mousemove', galConnMove);
  document.addEventListener('mouseup', galConnUp);
}
function galConnMove(ev) {
  if (!galConnecting) return;
  var svg = galConnecting.svg; if (!svg) return;
  var r = svg.getBoundingClientRect(), S = galScale || 1;
  var x = (ev.clientX - r.left) / S, y = (ev.clientY - r.top) / S;
  if (galConnecting.line) galConnecting.line.setAttribute('d', 'M' + galConnecting.x0 + ',' + galConnecting.y0 + ' C' + galConnecting.x0 + ',' + y + ' ' + x + ',' + galConnecting.y0 + ' ' + x + ',' + y);
  // 高亮悬停目标节点，提供实时反馈
  var el = document.elementFromPoint(ev.clientX, ev.clientY), tgtId = null;
  while (el && el.getAttribute) { if (el.getAttribute('data-scene')) { tgtId = el.getAttribute('data-scene'); break; } el = el.parentNode; }
  if (tgtId === galConnecting.srcId) tgtId = null;
  if (galConnTarget !== tgtId) {
    if (galConnTarget) { var g0 = document.querySelector('[data-scene="' + galConnTarget + '"]'); if (g0) g0.style.filter = ''; }
    if (tgtId) { var g1 = document.querySelector('[data-scene="' + tgtId + '"]'); if (g1) g1.style.filter = 'brightness(1.35)'; }
    galConnTarget = tgtId;
  }
}
function galConnUp(ev) {
  if (!galConnecting) return;
  document.removeEventListener('mousemove', galConnMove);
  document.removeEventListener('mouseup', galConnUp);
  var srcId = galConnecting.srcId, line = galConnecting.line;
  galConnecting = null;
  try { if (line && line.parentNode) line.parentNode.removeChild(line); } catch (e) {}
  if (galConnTarget) { var g0 = document.querySelector('[data-scene="' + galConnTarget + '"]'); if (g0) g0.style.filter = ''; galConnTarget = null; }
  var el = document.elementFromPoint(ev.clientX, ev.clientY);
  var node = null;
  while (el && el.getAttribute) {
    if (el.getAttribute && el.getAttribute('data-scene')) { node = el.getAttribute('data-scene'); break; }
    el = el.parentNode;
  }
  if (!node || node === srcId) return;
  galConnectScene(srcId, node);   // 自动判断类型 + toast 反馈
}
function galConnectScene(srcId, tgtId, mode) {
  var sc = (galScript.scenes || []).find(function (s) { return s.id === srcId; });
  if (!sc) return;
  galPushUndo();
  var assertChoice = function () {
    var cp = (sc.lines || []).find(function (l) { return l && l.choice; });
    if (cp) { cp.choice = cp.choice || []; cp.choice.push({ text: '选项', goto: tgtId }); }
    else { sc.lines = sc.lines || []; sc.lines.push({ kind: 'choice', choice: [{ text: '选项', goto: tgtId }] }); }
    galToast('[ic:shuffle] 已添加选项分支');
  };
  if (mode === 'choice') { assertChoice(); }
  else if (mode === 'next') { sc.next = tgtId; galToast('▸ 已设为进行(下一步)'); }
  else {
    // 自动判断：无输出 → 进行(next)；已有输出 → 选项(choice)
    var hasOut = sc.next != null || sc.jump != null || (sc.lines || []).some(function (l) { return l && l.choice; });
    if (hasOut) { assertChoice(); }
    else { sc.next = tgtId; galToast('▸ 已设为进行(下一步)'); }
  }
  galRenderGraph();
}
function galIsKey(sc) {
  if (!sc) return false;
  if (sc.key === true) return true;
  if (sc.key === false) return false;
  return (sc.lines || []).some(function (ln) { return ln && ln.choice; });
}
function galToggleKey(id) {
  var sc = (galScript.scenes || []).find(function (s) { return s.id === id; });
  if (!sc) return;
  galPushUndo();
  sc.key = !galIsKey(sc);
  galRenderGraph();
}
// GAL 制作器 gal 的数据层收进 DICK.state（1 个：galAllOpen）；注册在 web/js/store/gal.js
function galInput(val, ph, cb) {
  var x = document.createElement('input');
  x.value = val; x.placeholder = ph;
  x.style.cssText = 'flex:1;min-width:110px;background:var(--panel);border:1px solid var(--line);border-radius:6px;color:var(--text);padding:7px 10px;font-size:12px';
  x.oninput = function () { cb(x.value); };
  return x;
}
// 素材下拉：从包里已有的文件里挑，旁边带「 导入」直接从电脑导进包
// GAL 制作器 gal 的数据层收进 DICK.state（1 个：_galAssets）；注册在 web/js/store/gal.js
function galLoadAssets(cb) {
  if (!codexCur) { cb && cb(); return; }
  pywebview.api.codex_script_files(codexCur).then(function (r) {
    _galAssets = (r && r.ok) ? (r.files || {}) : {};
    cb && cb();
  }).catch(function () { _galAssets = {}; cb && cb(); });
}
function galAssetSelect(kind, val, ph, cb) {
  var wrap = document.createElement('span');
  wrap.style.cssText = 'display:inline-flex;align-items:center;gap:6px;flex:1 1 200px;min-width:170px';
  var sel = document.createElement('select');
  sel.style.cssText = 'flex:1;min-width:110px;background:var(--panel);border:1px solid var(--line);border-radius:6px;color:var(--text);padding:7px 10px;font-size:12px';
  var files = (_galAssets && _galAssets[kind]) || [];
  var list = files.map(function (f) { return kind + '/' + f; });
  if (val && list.indexOf(val) < 0) list.push(val);   // 包外/旧引用保留，不丢数据
  var o0 = document.createElement('option'); o0.value = ''; o0.textContent = '（不用' + ph + '）';
  sel.appendChild(o0);
  list.forEach(function (p) {
    var o = document.createElement('option'); o.value = p;
    o.textContent = p.indexOf(kind + '/') === 0 ? p.slice(kind.length + 1) : p;
    sel.appendChild(o);
  });
  sel.value = val || '';
  sel.onchange = function () { cb(sel.value); };
  var imp = document.createElement('button');
  imp.className = 'btn2 ghost'; imp.textContent = '[ic:inbox] 导入'; imp.title = '从电脑里选' + ph + '，导进这个包';
  imp.style.cssText = 'font-size:12px;padding:6px 10px;white-space:nowrap;flex:0 0 auto';
  imp.onclick = function () {
    imp.disabled = true; imp.textContent = '导入中…';
    pywebview.api.codex_import_asset(codexCur, kind).then(function (r) {
      imp.disabled = false; imp.textContent = '[ic:inbox] 导入';
      if (!r || !r.ok) {
        if (r && r.err !== 'cancelled') galToast('[ic:error] ' + ((r && r.err) || '导入失败'));
        return;
      }
      _galAssets = r.files || {};
      var add = (r.added || [])[0] || '';
      cb(add ? (kind + '/' + add) : sel.value);
      galToast('[ic:check_circle] 已导入 ' + (r.added || []).length + ' 个文件');
    }).catch(function (e) {
      imp.disabled = false; imp.textContent = '[ic:inbox] 导入';
      galToast('[ic:error] ' + ((e && e.message) || '导入失败'));
    });
  };
  wrap.appendChild(sel); wrap.appendChild(imp);
  return wrap;
}
function galOpenEditor(name) {
  codexCur = name;
  galScript = null;
  document.getElementById('galEditor').style.display = 'flex';
  document.getElementById('galTitle').textContent = '[ic:book] GAL 制作器 · ' + name;
  document.getElementById('galStats').textContent = '加载中…';
  pywebview.api.codex_get(name).then(function (r) {
    if (!r || !r.ok) { document.getElementById('galStats').textContent = '[ic:error] ' + ((r && r.err) || '加载失败'); return; }
    galScript = r.script;
    if (!galScript.scenes) galScript.scenes = [];
    galEnsureRoles();
    galRenderGraph();
    galStatsSet();
  });
}
function galStatsSet() {
  var n = (galScript.scenes || []).length, pts = 0;
  (galScript.scenes || []).forEach(function (s) { pts += (s.lines || []).length; });
  document.getElementById('galStats').textContent = '线 ' + n + ' · 点 ' + pts;
}

/* ================= 一屏的挂载 / 卸载（router 注入片段之后调用） ================= */
function galMount() {
  var mod = window.GalScreen;
  if (mod && mod.__ready) { return; }          // mount 幂等（router 也会挡一次）
  if (!document.getElementById('galEditor')) {
    console.error('[gal] 片段没注入（找不到 galEditor），这一屏跳过挂载');
    return;
  }
  galBindBar();        // 保存 / 角色 / 体检 三个按钮（gal-lines.js）
  galBindEditor();     // 画布视口 + 撤销/缩放/键盘/包选择（gal-lines.js）
  // 别的屏要开这一屏，只发这两个事件（不直接调函数）
  DICK.bus.on('gal:open-interface', function () { galOpenInterface(); });
  DICK.bus.on('gal:open-editor', function (name) { if (name) { galOpenEditor(name); } });
  if (mod) { mod.__ready = true; }
}

function galUnmount() { /* 本屏没有常驻定时器：RAF 由 galNodeUp 自己收尾 */ }

/* 本文件定义的全局函数（galOpenEditor/galSave/galToast…）就是这一屏的门面。
 * 注意：openInterface 的实现 galOpenInterface 在 gal-scene.js 里，本文件加载时它还不存在，
 * 所以这里包一层"调用时才解析"的转调 —— 直接写 galOpenInterface 会在载入这一行时 ReferenceError。 */
window.GalScreen = { mount: galMount, unmount: galUnmount,
                     open: function (name) { return galOpenEditor(name); },
                     openInterface: function () { return galOpenInterface(); } };

// 注册到路由：片段 = screens/gal.html，模块 = 上面这个
DICK.router.register('gal', { fragment: 'screens/gal.html', module: window.GalScreen });

