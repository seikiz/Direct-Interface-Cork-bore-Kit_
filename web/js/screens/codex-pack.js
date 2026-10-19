/* web/js/screens/codex-pack.js —— 打包 / 发布 / 导出 / 资源清单（codex 屏的「出货」那一段）。
 *
 * 归属：结构在 web/screens/codex.html（codexPackInfo / codexFiles 在 codexModal 里）。
 * 只碰 codex 前缀的 id；打包/发布是后端 pywebview.api.codex_* 的活，本文件只管按钮反馈与轮询。
 */

function codexExport() {
  if (!codexCur) return;
  pywebview.api.codex_export(codexCur).then(function (r) {
    if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
  });
}
function codexPack(showInfo) {
  // 打包：生成独立单文件 GALGA<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ME（HTML，双击即玩，可分发）
  if (!codexCur) return;
  document.getElementById('codexPackInfo').style.display = 'none';
  codexSetStatus('[ic:hourglass_empty] 打包中…');
  pywebview.api.codex_pack(codexCur).then(function (r) {
    codexSetStatus('');
    if (!r || !r.ok) { alert((r && r.err) || '打包失败'); return; }
    var info = document.getElementById('codexPackInfo');
    var parts = [];
    if (r.counts) {
      parts.push('[ic:style]立绘 ' + (r.counts.sprites || 0) + ' · [ic:image]背景 ' + (r.counts.bg || 0) +
                 ' · [ic:music_note]音乐 ' + (r.counts.bgm || 0) + ' · [ic:mic]配音 ' + (r.counts.voice || 0));
    }
    parts.push('单文件 ' + (r.size ? (r.size / 1024 / 1024).toFixed(1) : '?') + ' MB');
    info.innerHTML = '[ic:check_circle] 打包成功：' + parts.join(' · ') +
      '<br>[ic:description] 已保存到包内 <b>' + escapeHtml(r.rel || '') + '</b> —— 双击该 HTML 即可独立游玩（无需 DICK，可发给任何人）。';
    info.style.display = 'block';
    if (showInfo !== false && window.pywebview.api.open_path) {
      try { pywebview.api.open_path(r.path).then(function () {}); } catch (e) {}
    }
  }).catch(function (e) { codexSetStatus(''); alert('打包失败: ' + (e && e.message ? e.message : '')); });
}
function codexPackSaveAs() {
  if (!codexCur) return;
  pywebview.api.codex_pack_save_as(codexCur).then(function (r) {
    if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
    else if (r && r.ok) {
      var info = document.getElementById('codexPackInfo');
      info.innerHTML = '[ic:check_circle] 已另存为：' + escapeHtml(r.path) + '（' + (r.size / 1024 / 1024).toFixed(1) + ' MB）—— 独立 GALGAME，双击即玩。';
      info.style.display = 'block';
    }
  });
}
// 编年史 codex 的数据层收进 DICK.state（1 个：codexExeTimer）；注册在 web/js/store/codex.js
function codexRelease() {
  // 两步发布：一键打包 EXE + HTML + .codex 三件套（决战兵器·分发闭环）
  if (!codexCur) return;
  var info = document.getElementById('codexPackInfo');
  info.style.display = 'block';
  info.innerHTML = '[ic:rocket_launch] 正在发布（打包 EXE 首次约 1-2 分钟）…';
  document.getElementById('codexReleaseBtn').disabled = true;
  pywebview.api.codex_release(codexCur).then(function (r) {
    if (!r || !r.ok) {
      info.innerHTML = '[ic:error] ' + ((r && r.err) || '发布启动失败');
      document.getElementById('codexReleaseBtn').disabled = false;
      return;
    }
    if (codexExeTimer) clearInterval(codexExeTimer);
    codexExeTimer = setInterval(function () { codexReleasePoll(); }, 1500);
  }).catch(function (e) {
    info.innerHTML = '[ic:error] ' + (e && e.message ? e.message : '发布失败');
    document.getElementById('codexReleaseBtn').disabled = false;
  });
}
function codexReleasePoll() {
  if (!codexCur) { if (codexExeTimer) clearInterval(codexExeTimer); return; }
  pywebview.api.codex_pack_exe_status(codexCur).then(function (r) {
    if (!r || !r.ok) return;
    var info = document.getElementById('codexPackInfo');
    if (r.state === 'building') {
      info.innerHTML = '[ic:rocket_launch] ' + escapeHtml(r.msg || '发布中…');
    } else if (r.state === 'done') {
      if (codexExeTimer) { clearInterval(codexExeTimer); codexExeTimer = null; }
      document.getElementById('codexReleaseBtn').disabled = false;
      var mb = function (b) { return b ? (b / 1024 / 1024).toFixed(1) : '?'; };
      info.innerHTML =
        '[ic:check_circle] 发布完成 —— 三件套已生成到包内 <b>dist/</b>：<br>' +
        '[ic:desktop_windows] EXE：' + escapeHtml(r.exe || '') + '（' + mb(r.size_exe) + ' MB）—— 零依赖，双击即玩，可发给任何人<br>' +
        '[ic:language] HTML：' + escapeHtml(r.html || '') + '（' + mb(r.size_html) + ' MB）—— 浏览器即玩<br>' +
        '[ic:inventory] .codex：' + escapeHtml(r.codex || '') + '（' + mb(r.size_codex) + ' MB）—— 双击（注册关联后）用 DICK 打开';
      codexLoadList();
    } else if (r.state === 'error') {
      if (codexExeTimer) { clearInterval(codexExeTimer); codexExeTimer = null; }
      document.getElementById('codexReleaseBtn').disabled = false;
      info.innerHTML = '[ic:error] 发布失败：' + escapeHtml((r.msg || r.err || '未知错误').slice(0, 300)) +
        '<br><span style="font-size:11px">EXE 需要本机 Python + pyinstaller；HTML/.codex 不依赖。</span>';
    }
  }).catch(function () {});
}
function codexPackExe() {
  // 打包独立 EXE（无需浏览器，双击即玩）：后台线程 + 轮询状态
  if (!codexCur) return;
  var info = document.getElementById('codexPackInfo');
  info.style.display = 'block';
  info.innerHTML = '[ic:hourglass_empty] 正在启动打包…（需要本机 Python 含 PyInstaller，首次约 1-2 分钟，请稍候）';
  codexExeBtn.disabled = true;
  pywebview.api.codex_pack_exe(codexCur).then(function (r) {
    if (!r || !r.ok) {
      info.innerHTML = '[ic:error] ' + ((r && r.err) || '启动失败');
      codexExeBtn.disabled = false;
      return;
    }
    if (codexExeTimer) clearInterval(codexExeTimer);
    codexExeTimer = setInterval(function () { codexExePoll(); }, 1500);
  }).catch(function (e) {
    info.innerHTML = '[ic:error] ' + (e && e.message ? e.message : '启动失败');
    codexExeBtn.disabled = false;
  });
}
function codexExePoll() {
  if (!codexCur) { if (codexExeTimer) clearInterval(codexExeTimer); return; }
  pywebview.api.codex_pack_exe_status(codexCur).then(function (r) {
    if (!r || !r.ok) return;
    var info = document.getElementById('codexPackInfo');
    if (r.state === 'building') {
      info.innerHTML = '[ic:hourglass_empty] ' + escapeHtml(r.msg || '打包中…');
    } else if (r.state === 'done') {
      if (codexExeTimer) { clearInterval(codexExeTimer); codexExeTimer = null; }
      document.getElementById('codexExeBtn').disabled = false;
      var parts = ['[ic:desktop_windows] EXE 打包完成'];
      if (r.counts) parts.push('[ic:style]' + (r.counts.sprites || 0) + ' [ic:image]' + (r.counts.bg || 0) +
        ' [ic:music_note]' + (r.counts.bgm || 0) + ' [ic:mic]' + (r.counts.voice || 0));
      if (r.size) parts.push((r.size / 1024 / 1024).toFixed(1) + ' MB');
      info.innerHTML = '[ic:check_circle] ' + parts.join(' · ') +
        '<br>[ic:description] 已保存到 <b>' + escapeHtml(r.rel || r.exe || '') + '</b> —— 双击该 EXE 即可独立游玩（无需 DICK、无需浏览器，可发给任何人）。';
      codexLoadList();
    } else if (r.state === 'error') {
      if (codexExeTimer) { clearInterval(codexExeTimer); codexExeTimer = null; }
      document.getElementById('codexExeBtn').disabled = false;
      info.innerHTML = '[ic:error] 打包失败：' + escapeHtml((r.msg || r.err || '未知错误').slice(0, 300)) +
        '<br><span style="font-size:11px">需要本机安装 Python 且 <code>pip install pyinstaller</code>。'
    }
  }).catch(function () {});
}
function codexShowFiles() {
  if (!codexCur) return;
  document.getElementById('codexEditor').style.display = 'none';
  document.getElementById('codexFiles').style.display = 'block';
  pywebview.api.codex_script_files(codexCur).then(function (r) {
    var box = document.getElementById('codexFiles');
    if (!r || !r.ok) { box.innerHTML = '<div style="color:var(--danger)">加载失败</div>'; return; }
    var html = '';
    var labels = { sprites: '[ic:style] 立绘', bg: '[ic:image] 背景', bgm: '[ic:music_note] 音乐', voice: '[ic:mic] 配音' };
    for (var k in labels) {
      var files = (r.files && r.files[k]) || [];
      html += '<div class="section-label">' + labels[k] + '（' + files.length + '）</div>';
      if (!files.length) { html += '<div style="font-size:11px;color:var(--sub);padding:2px 0 6px">空</div>'; continue; }
      html += '<div style="display:flex;flex-wrap:wrap;gap:6px;padding:2px 0 8px">' +
        files.map(function (f) { return '<span style="font-size:11px;background:var(--bg,#111);border:1px solid var(--line);border-radius:4px;padding:2px 6px">' + escapeHtml(f) + '</span>'; }).join('') +
        '</div>';
    }
    box.innerHTML = html;
  });
}
