/* web/js/screens/codex-player-bind.js —— 编年史**播放器**那一屏的按钮/键盘绑定。
 *
 * 为什么和编辑器的绑定分开：两块屏各自的 DOM 各自绑（这一档只碰 cx 前缀的 id），
 * 谁要加一个按钮，改动面就只有自己那一屏 —— 这也是「编辑器与播放器零互摸」的最后一段。
 * 由 codex-editor.js 的 codexMount() 在片段注入之后调（mount 里两行，一眼能看到谁负责什么）。
 */

function codexBindPlayer() {
  document.getElementById('cxBack').onclick = codexPlayerExit;
  // 多媒体权限：<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌全屏 + 音量
  document.getElementById('cxFull').onclick = function () {
    try { pywebview.api.codex_fullscreen().then(function () {}); } catch (e) {}
  };
  document.getElementById('cxVol').addEventListener('input', function () {
    codexVolume = parseInt(this.value, 10) || 100;
    try {
      pywebview.api.codex_volume(codexVolume).then(function () {});
      if (codexPlayer && codexPlayer.audioBgm) codexPlayer.audioBgm.volume = (codexVolume / 100) * 0.6;
      if (codexPlayer && codexPlayer.audioVoice) codexPlayer.audioVoice.volume = (codexVolume / 100) * 0.9;
    } catch (e) {}
  });
  document.getElementById('cxSave').onclick = codexSaveSlot;
  document.getElementById('cxLoad').onclick = codexLoadSlot;
  document.getElementById('cxRewind').onclick = codexRewind;
  document.getElementById('cxTitle').onclick = function () {
    document.getElementById('cxTitle').style.display = 'none';
    codexStartScene((codexPlayer.scenes[0] || {}).id || '');
  };
  document.getElementById('cxEnd').onclick = function () {
    document.getElementById('cxEnd').style.display = 'none';
    codexPlayerExit();
  };
  document.getElementById('cxAuto').onclick = function () {
    if (!codexPlayer) return;
    codexPlayer.auto = !codexPlayer.auto;
    this.textContent = codexPlayer.auto ? '[ic:pause] 停止自动' : '[ic:fast_forward] 自动';
    if (codexPlayer.auto) codexScheduleAuto();
    else codexStopAuto();
  };
  document.getElementById('cxTextbox').onclick = function () {
    if (!codexPlayer) return;
    if (document.getElementById('cxChoice').style.display === 'block') return;
    if (document.getElementById('cxTitle').style.display === 'flex') return;
    if (document.getElementById('cxEnd').style.display === 'flex') return;
    codexNextLine();
  };
  // 键位（GALGAME 手感）：空格/回车=下一行，Esc=退出
  document.addEventListener('keydown', function (e) {
    if (!codexPlayer) return;
    if (!DICK.state.get('codex.playerOpen', false)) return;
    if (document.getElementById('cxTitle').style.display === 'flex') return;
    if (document.getElementById('cxEnd').style.display === 'flex') return;
    if (e.code === 'Space' || e.code === 'Enter') {
      e.preventDefault();
      if (document.getElementById('cxChoice').style.display === 'block') return; // 选项时按键无效
      codexNextLine();
    } else if (e.code === 'Escape') {
      codexPlayerExit();
    }
  });
}
