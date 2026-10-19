/* web/js/screens/gal-scene.js —— GAL 场景步骤行（一个「点」一行控件）+ 干净界面入口 + 新建包。
 *
 * 归属：结构在 web/screens/gal.html（galScenePanel 由本文件填，入口按钮在工具条上）。
 * 只碰 gal 前缀的 id；剧本数据走 galScript（store/gal.js 的兼容访问器）。
 */

function galScenePointRow(sc, ln, re) {
  var row = document.createElement('div');
  row.className = 'gal-editor';
  row.style.cssText = 'margin:0;flex-basis:auto;flex-wrap:wrap;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bubble,#161b22)';
  var sel = document.createElement('select');
  Object.keys(_gKindNames).forEach(function (k) { var o = document.createElement('option'); o.value = k; o.textContent = _gKindNames[k]; sel.appendChild(o); });
  sel.value = ln.kind || 'say';
  sel.onchange = function () { galPushUndo(); ln.kind = sel.value; if (ln.kind === 'choice') ln.choice = ln.choice || []; re(); };
  row.appendChild(sel);
  if (ln.kind === 'choice') {
    var optBox = document.createElement('div');
    var ro = function () {
      optBox.innerHTML = '';
      (ln.choice || []).forEach(function (o, k) {
        var r = document.createElement('div'); r.className = 'row';
        r.appendChild(galInput(o.text || '', '选项文字', function (v) { o.text = v; }));
        r.appendChild(galInput(o.goto || '', 'goto', function (v) { o.goto = v; }));
        var c = galInput(o.if ? JSON.stringify(o.if) : '', '[ic:lock] 条件', function (v) { try { o.if = v.trim() ? JSON.parse(v) : undefined; } catch (e) { o.if = undefined; } });
        c.style.cssText = 'flex:1;min-width:150px;background:var(--bubble,#161b22);border:1px solid rgba(245,158,11,.4);border-radius:6px;color:var(--warn);padding:5px 8px;font-size:12px';
        r.appendChild(c);
        var del = document.createElement('button'); del.className = 'btn2 ghost'; del.textContent = '[ic:close]'; del.style.cssText = 'color:var(--danger);font-size:11px;padding:2px 6px'; del.onclick = function () { galPushUndo(); ln.choice.splice(k, 1); ro(); }; r.appendChild(del);
        optBox.appendChild(r);
      });
      var add = document.createElement('button'); add.className = 'btn2 ghost'; add.textContent = '[ic:add] 选项'; add.style.cssText = 'font-size:11px;padding:3px 8px'; add.onclick = function () { galPushUndo(); ln.choice = ln.choice || []; ln.choice.push({ text: '', goto: '' }); ro(); }; optBox.appendChild(add);
    };
    ro(); row.appendChild(optBox);
  } else {
    // 元信息（说话人/立绘/语音/参数）一行，正文独<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌占一行 —— 免得 5 个控件平分一行挤成一条
    var meta = document.createElement('div');
    meta.style.cssText = 'display:flex;align-items:center;gap:12px;flex-wrap:wrap;flex:1 1 100%';
    if (ln.kind === 'say') { meta.appendChild(galRoleSelect(ln)); meta.appendChild(galAssetSelect('sprites', ln.sprite || '', '立绘', function (v) { ln.sprite = v; })); meta.appendChild(galAssetSelect('voice', ln.voice || '', '语音', function (v) { ln.voice = v; })); }
    if (ln.kind === 'bg') meta.appendChild(galAssetSelect('bg', ln.bg || '', '背景', function (v) { ln.bg = v; }));
    if (ln.kind === 'bgm') meta.appendChild(galAssetSelect('bgm', ln.bgm || '', '音乐', function (v) { ln.bgm = v; }));
    if (ln.kind === 'setflag') meta.appendChild(galInput((ln.flag && ln.flag.k) || '', 'flag', function (v) { ln.flag = { k: v, v: true }; }));
    if (ln.kind === 'effect') meta.appendChild(galInput(ln.effect || 'shake', 'shake/flash', function (v) { ln.effect = v; }));
    if (ln.kind === 'wait') meta.appendChild(galInput(ln.ms || 300, '毫秒', function (v) { ln.ms = Number(v) || 0; }));
    if (ln.kind === 'jump') meta.appendChild(galInput(ln.goto || '', '目标线', function (v) { ln.goto = v; }));
    if (ln.kind === 'end') meta.appendChild(galInput(ln.end || '', '结局', function (v) { ln.end = v; }));
    if (meta.childNodes.length) row.appendChild(meta);
    var content = galInput(ln.text || '', (ln.kind === 'note' ? '旁白内容' : '内容'), function (v) { ln.text = v; });
    content.style.cssText = content.style.cssText + ';flex:1 1 100%';
    row.appendChild(content);
  }
  // 点内图片（可多张，自动适配）+ 退出图片
  var imgWrap = document.createElement('div'); imgWrap.className = 'row'; imgWrap.style.cssText = 'flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px;flex-basis:100%';
  imgWrap.appendChild(document.createTextNode('[ic:image] 图片:'));
  var imgList = document.createElement('span'); imgList.style.cssText = 'display:inline-flex;flex-wrap:wrap;gap:8px';
  ln.images = ln.images || [];
  var renderImgs = function () {
    imgList.innerHTML = '';
    ln.images.forEach(function (f, i) {
      var inp = galInput(f, '图片文件', function (v) { ln.images[i] = v; }); inp.style.cssText = 'width:150px;background:var(--bubble,#161b22);border:1px solid var(--line);border-radius:6px;color:var(--text,#ddd);padding:6px 8px;font-size:12px';
      var rm = document.createElement('button'); rm.textContent = '[ic:close]'; rm.className = 'btn2 ghost'; rm.style.cssText = 'color:var(--danger);font-size:12px;padding:4px 8px'; rm.onclick = function () { galPushUndo(); ln.images.splice(i, 1); renderImgs(); };
      imgList.appendChild(inp); imgList.appendChild(rm);
    });
  };
  renderImgs();
  imgWrap.appendChild(imgList);
  var addImg = document.createElement('button'); addImg.className = 'btn2 ghost'; addImg.textContent = '[ic:add] 图'; addImg.style.cssText = 'font-size:11px;padding:3px 8px'; addImg.onclick = function () { galPushUndo(); ln.images.push(''); renderImgs(); }; imgWrap.appendChild(addImg);
  var clearImg = document.createElement('label'); clearImg.style.cssText = 'font-size:11px;color:var(--sub);display:inline-flex;align-items:center;gap:4px;margin-left:6px;cursor:pointer';
  var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!ln.clearImages; cb.onchange = function () { galPushUndo(); ln.clearImages = cb.checked; };
  clearImg.appendChild(cb); clearImg.appendChild(document.createTextNode('退出图片'));
  imgWrap.appendChild(clearImg);
  row.appendChild(imgWrap);
  var del = document.createElement('button'); del.className = 'btn2 ghost'; del.textContent = '[ic:delete]'; del.style.cssText = 'color:var(--danger);font-size:11px;padding:2px 6px'; del.onclick = function () { galPushUndo(); sc.lines = (sc.lines || []).filter(function (x) { return x !== ln; }); re(); }; row.appendChild(del);
  return row;
}
// 干净专用界面入口： GAL制作器 → 直接进入全屏编辑器 + 包选择
function galOpenInterface() {
  document.getElementById('galEditor').style.display = 'flex';
  document.getElementById('galTitle').textContent = '[ic:book] GAL制作器';
  document.getElementById('galStats').textContent = '';
  var sel = document.getElementById('galPkgSel');
  sel.innerHTML = '<option>加载中…</option>';
  pywebview.api.codex_list().then(function (r) {
    if (!r || !r.ok) { document.getElementById('galStats').textContent = '[ic:error] ' + ((r && r.err) || '加载失败'); return; }
    var pkgs = r.packages || [];
    sel.innerHTML = '';
    if (!pkgs.length) {
      sel.innerHTML = '<option value="">（无包）</option>';
      document.getElementById('galLines').innerHTML = '<div style="color:var(--sub);padding:30px;text-align:center">还没有剧本。<br>点「[ic:add] 新建」生成示例，再进来改成你的故事。</div>';
      return;
    }
    pkgs.forEach(function (p) { var o = document.createElement('option'); o.value = p.name; o.textContent = p.name + (p.scenes ? ' · ' + p.scenes + '线' : ''); sel.appendChild(o); });
    var pick = pkgs[0].name;
    if (codexCur && pkgs.some(function (p) { return p.name === codexCur; })) pick = codexCur;
    sel.value = pick;
    galOpenEditor(pick);
  }).catch(function (e) { document.getElementById('galStats').textContent = '[ic:error] ' + (e && e.message ? e.message : '加载失败'); });
}
function galNewPkg() {
  var n = prompt('新建 GAL 包名称（生成示例剧本，可立即编辑/播放）:', '我的故事');
  if (!n || !n.trim()) return;
  pywebview.api.codex_create(n.trim()).then(function (r) {
    if (r && r.ok) { codexCur = r.name || n.trim(); galOpenInterface(); }
    else alert((r && r.err) || '创建失败');
  });
}
