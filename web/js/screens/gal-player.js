/* web/js/screens/gal-player.js —— GAL 的「播」：预览（先存盘再交给编年史播放器）+ 导出原生播放器。
 *
 * 归属：没有自己的 DOM；预览发 DICK.bus 'codex:play'，导出走后端 codex_export_player。
 * 为什么不直接调 codexPlay()：两块屏之间的调用只许走 DICK.state / DICK.bus（ARCHITECTURE 第十节）。
 */

function galPlay() {
  var n = codexCur; if (!n) return;
  if (galScript) galSave();     // 先保存，确保预览的是当前编辑
  codexCur = n;
  galCloseEditor();
  DICK.bus.emit('codex:play');
}
function galImport() {
  pywebview.api.codex_import_folder().then(function (r) {
    if (!r) return;
    if (r.ok) { galToast('[ic:check_circle] ' + (r.msg || '导入成功')); if (r.name) galOpenEditor(r.name); }
    else if (r.err && r.err !== 'cancelled') alert(r.err || '导入失败');
  });
}
function galPackExe() {
  if (!codexCur) return;
  if (!confirm('把「' + codexCur + '」打包成独立 EXE（双击即玩，首次约 1-2 分钟）？')) return;
  galToast('[ic:hourglass_empty] 正在启动打包…');
  pywebview.api.codex_pack_exe(codexCur).then(function (r) {
    if (!r || !r.ok) { galToast('[ic:error] ' + ((r && r.err) || '启动失败')); return; }
    var t = setInterval(function () {
      pywebview.api.codex_pack_exe_status(codexCur).then(function (s) {
        if (!s || !s.ok) return;
        if (s.state === 'building') galToast('[ic:hourglass_empty] ' + ((s.msg || '打包中…')).slice(0, 40));
        else if (s.state === 'done') { clearInterval(t); galToast('[ic:check_circle] 打包完成'); }
        else if (s.state === 'error') { clearInterval(t); galToast('[ic:error] ' + ((s.msg || '打包失败')).slice(0, 40)); }
      });
    }, 1500);
  }).catch(function (e) { galToast('[ic:error] ' + (e && e.message ? e.message : '启动失败')); });
}
function galCloseEditor() { document.getElementById('galEditor').style.display = 'none'; }
// ---- 导出到原生播放器（K<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌otlin 叙事引擎）----
// 和「 EXE」的区别：那个是 HTML 套壳，这个是真正的原生窗口程序，
// 同一份 codex.json 还能喂给安卓 APK 和 DICK 主程序。
function galPackPlayer() {
  if (!codexCur) return;
  if (!galScript) { alert('先打开一个剧本再导出。'); return; }
  // 先存盘：导出的一定是当前编辑的内容
  pywebview.api.codex_save(codexCur, JSON.stringify(galScript)).then(function (r) {
    if (!r || !r.ok) { alert('保存失败：' + ((r && r.err) || '')); return; }
    pywebview.api.codex_player_ready().then(function (rd) {
      if (!rd || !rd.ready) {
        alert('还没构建播放器。\n\n先在 DICK-Narrative 目录跑一次：\n' +
              '  powershell -ExecutionPolicy Bypass -File build.ps1 -Exe\n\n' +
              '构建好之后再回来点这个按钮。');
        return;
      }
      if (!confirm('把「' + codexCur + '」导出成原生播放器？\n\n' +
                   '会生成一个文件夹：里面是播放器 + 你的故事和素材，\n' +
                   '整个文件夹一起拷走就能给别人玩（约 130 MB）。\n\n' +
                   '下一步先让你选放在哪儿（默认桌面）。')) return;
      galToast('[ic:hourglass_empty] 正在导出…');
      pywebview.api.codex_export_player(codexCur).then(function (r2) {
        if (!r2 || !r2.ok) {
          if (r2 && r2.err === 'cancelled') { galToast('已取消'); return; }
          galToast('[ic:error] 导出失败');
          alert('导出失败：\n' + ((r2 && r2.err) || '未知错误'));
          return;
        }
        var t = setInterval(function () {
          pywebview.api.codex_player_status(codexCur).then(function (s) {
            if (!s || !s.ok) return;
            if (s.state === 'building') { galToast('[ic:hourglass_empty] ' + ((s.msg || '导出中…')).slice(0, 40)); }
            else if (s.state === 'done') {
              clearInterval(t);
              galToast('[ic:check_circle] 导出完成 · ' + (s.size || '?') + ' MB');
              var c = s.counts || {};
              alert('导出完成！\n\n位置：\n' + (s.dest || '') +
                    '\n\n' + (s.size || '?') + ' MB\n' +
                    '素材：立绘 ' + (c.sprites || 0) + ' · 背景 ' + (c.bg || 0) +
                    ' · 音乐 ' + (c.bgm || 0) + ' · 语音 ' + (c.voice || 0) +
                    '\n\n双击里面的 DICK-Narrative.exe 就能玩。');
            } else if (s.state === 'error') {
              clearInterval(t);
              galToast('[ic:error] ' + ((s.msg || '导出失败')).slice(0, 40));
              alert('导出失败：\n' + (s.msg || ''));
            }
          });
        }, 1200);
      }).catch(function (e) { galToast('[ic:error] ' + ((e && e.message) || '导出失败')); });
    });
  }).catch(function (e) { alert('保存失败：' + ((e && e.message) || '')); });
}
