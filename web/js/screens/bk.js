/* web/js/screens/bk.js —— 🔐 加密备份（阶段 3：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 这一屏没有状态：口令只在输入框里，不进 JS 变量、不进 localStorage（"口令不保存在任何地方"
 * 是这个功能的承诺，搬家时必须原样保住）。
 *
 * 归属
 *   结构：web/screens/bk.html（index.html 里原位只剩挂载点 <!--@screen:bk-->）
 *   样式：没有专属 css 块 —— 它用的是组件层的 .modal/.modal-box/.field/.row，
 *         所以不建 bk.css（多一个空文件比没有更糟）。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 *   · pywebview.api.backup_* / export_backup_encrypted / import_backup_encrypted
 *   · escapeHtml()     组件层转义
 *   · reloadRoles() / reloadWorlds()  还原成功后要重刷侧栏（外壳的函数，直接调用）
 *   · #btnBackup       入口按钮在外壳侧栏（本屏 mount 时绑它）
 *   · Esc 关窗         仍写在 index.html 的全局 keydown 里，它调兼容入口 bkClose()
 */
window.BkScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 🔐 加<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌密备份 =================
  // ================= 🔐 加密备份 =================
  function bkStatus(html, kind) {
    var el = document.getElementById('bkStatus');
    if (!el) return;
    var color = kind === 'bad' ? '#ff6b6b' : (kind === 'good' ? '#5fd39a' : 'var(--sub)');
    el.style.color = color;
    el.innerHTML = html;
  }

  function bkOpen() {
    var a = document.getElementById('bkPw'), b = document.getElementById('bkPw2');
    a.value = ''; b.value = '';
    a.type = 'password'; b.type = 'password';   // 复位：别把上次生成的明文口令留在屏幕上
    document.getElementById('bkPwMsg').textContent = '';
    document.getElementById('bkGenHint').textContent = '';
    var warn = document.getElementById('bkWarn');
    warn.innerHTML = '⚠️ 口令<b>不保存在任何地方</b>，忘了就打不开了。请单独记好（抄纸上 / 存密码管理器）。';
    warn.style.color = 'var(--sub)';
    bkStatus('');
    document.getElementById('backupModal').classList.add('open');
  }

  function bkClose() { document.getElementById('backupModal').classList.remove('open'); }

  // 生成随机强口令：自己想的口令普遍很弱，而且【忘了就永久打不开】。
  // 让程序给一个 32 字节随机码、切回明文显示并全选，用户直接抄走。
  function bkGen() {
    var hint = document.getElementById('bkGenHint');
    hint.textContent = '生成中…';
    pywebview.api.backup_make_password().then(function (r) {
      if (!r || !r.ok) { hint.textContent = '生成失败：' + ((r && r.err) || '未知错误'); return; }
      var pw = r.password;
      var a = document.getElementById('bkPw'), b = document.getElementById('bkPw2');
      a.type = 'text'; b.type = 'text';
      a.value = pw; b.value = pw;
      try { a.focus(); a.select(); } catch (e) {}
      var lvl = document.getElementById('bkPwMsg');
      lvl.textContent = '已生成强口令（' + pw.length + ' 位随机）';
      lvl.style.color = '#5fd39a';
      var warn = document.getElementById('bkWarn');
      warn.innerHTML = '⚠️ <b>现在就把下面这串抄下来</b>（纸上 / 密码管理器），' +
                       '然后关掉本窗口。这个口令只显示这一次，我们不保存，' +
                       '丢了这份备份就永久打不开了。';
      warn.style.color = '#ffb454';
      hint.textContent = '已填入两栏、已全选，可 Ctrl+C 复制';
    }).catch(function (e) { hint.textContent = '生成失败：' + e; });
  }

  function bkPwStrength() {
    var pw = document.getElementById('bkPw').value;
    var msg = document.getElementById('bkPwMsg');
    if (!pw) { msg.textContent = ''; return; }
    try {
      pywebview.api.backup_password_check(pw).then(function (r) {
        if (!r || !r.ok) { msg.textContent = ''; return; }
        msg.textContent = r.msg;
        msg.style.color = r.ok_to_use ? '#5fd39a' : '#ffb454';
      });
    } catch (e) { msg.textContent = ''; }
  }

  function bkExport() {
    var pw = document.getElementById('bkPw').value;
    var pw2 = document.getElementById('bkPw2').value;
    if (!pw) { bkStatus('请先输入口令。', 'bad'); return; }
    if (pw !== pw2) { bkStatus('两次输入的口令不一样，请重新确认。', 'bad'); return; }
    if (pw.length < 12) { bkStatus('口令太短（至少 12 位）。', 'bad'); return; }
    bkStatus('正在打包并加密，请稍候…');
    document.getElementById('bkExport').disabled = true;
    pywebview.api.export_backup_encrypted(pw).then(function (r) {
      document.getElementById('bkExport').disabled = false;
      if (!r || !r.ok) {
        if (r && r.err === 'cancelled') { bkStatus('已取消。'); return; }
        bkStatus('备份失败：' + ((r && r.err) || '未知错误'), 'bad');
        return;
      }
      var kb = (r.size / 1024).toFixed(1);
      bkStatus('✅ 备份完成<br>' +
               '文件：<b>' + escapeHtml(r.name) + '</b><br>' +
               '共 ' + r.entries + ' 项，加密后 ' + kb + ' KB<br>' +
               '<span style="color:var(--sub)">存到网盘/U盘都可以 —— 没有口令谁也打不开。</span>', 'good');
    }).catch(function (e) {
      document.getElementById('bkExport').disabled = false;
      bkStatus('备份失败：' + e, 'bad');
    });
  }

  function bkRestore() {
    var pw = document.getElementById('bkPw').value;
    if (!pw) { bkStatus('请先输入这份备份的口令，再点还原。', 'bad'); return; }
    bkStatus('选择备份文件…');
    pywebview.api.import_backup_encrypted(pw).then(function (r) {
      if (!r || !r.ok) {
        if (r && r.err === 'cancelled') { bkStatus('已取消。'); return; }
        var e = (r && r.err) || '未知错误';
        if (e.indexOf('口令错误') >= 0 || e.indexOf('篡改') >= 0) {
          bkStatus('❌ 口令错误，或这个文件被改动过。<br>' +
                   '<span style="color:var(--sub)">如果确定口令没错，换一份备份再试。</span>', 'bad');
        } else {
          bkStatus('还原失败：' + escapeHtml(e), 'bad');
        }
        return;
      }
      bkStatus('✅ ' + escapeHtml(r.msg), 'good');
      try { reloadRoles(); } catch (e) {}
      try { reloadWorlds(); } catch (e) {}
      try { pywebview.api.state().then(function () {}); } catch (e) {}
    }).catch(function (e) { bkStatus('还原失败：' + e, 'bad'); });
  }

  /* ---------------- 按钮绑定（片段注入之后才摸得到元素） ---------------- */
  function bindBkButtons() {
    document.getElementById('btnBackup').onclick = bkOpen;
    document.getElementById('bkCancel').onclick = bkClose;
    document.getElementById('bkExport').onclick = bkExport;
    document.getElementById('bkRestore').onclick = bkRestore;
    document.getElementById('bkPw').oninput = bkPwStrength;
    document.getElementById('bkGen').onclick = bkGen;
    document.getElementById('backupModal').addEventListener('click', function (e) {
      if (e.target === this) bkClose();
    });
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('backupModal')) {
      console.error('[bk] 片段没注入（找不到 #backupModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    bindBkButtons();
  }

  function unmount() {
    var m = document.getElementById('backupModal');
    if (m) { m.onclick = null; }
    var b = document.getElementById('btnBackup');
    if (b) { b.onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    status: bkStatus, open: bkOpen, close: bkClose, genPassword: bkGen,
    passwordStrength: bkPwStrength, exportBackup: bkExport, restore: bkRestore
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前这 7 个都是 index.html 的顶层全局函数。外部还在叫的有两个：
 *   · bkClose()  —— index.html 的 Esc keydown 处理器（那段本轮不动）
 *   · bkOpen()   —— 侧栏「🔐 加密备份」按钮（现在由本屏 mount() 绑）
 * 其余 5 个只在模块内部用。同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function bkStatus(html, kind) { return window.BkScreen.status(html, kind); }
function bkOpen() { return window.BkScreen.open(); }
function bkClose() { return window.BkScreen.close(); }
function bkGen() { return window.BkScreen.genPassword(); }
function bkPwStrength() { return window.BkScreen.passwordStrength(); }
function bkExport() { return window.BkScreen.exportBackup(); }
function bkRestore() { return window.BkScreen.restore(); }

// 注册到路由：片段 = screens/bk.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('bk', { fragment: 'screens/bk.html', module: window.BkScreen });
