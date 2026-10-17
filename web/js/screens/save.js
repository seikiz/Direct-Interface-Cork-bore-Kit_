/* web/js/screens/save.js —— 💾 角色卡·多存档（阶段 3：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * "正在看哪个角色的存档"原来是顶层 var saveModalCur（谁都能改、改坏了没痕迹）。
 * 现在真身是 DICK.state['save.current']，`window.saveModalCur` 只是兼容访问器 ——
 * 所以本文件里那 30 多处 `saveModalCur` 的读写**一个字都没改**（阶段 3 的收口口径）。
 *
 * 归属
 *   结构：web/screens/save.html（index.html 里原位只剩挂载点 <!--@screen:save-->）
 *   样式：web/styles/screens/save.css —— 原 screens.css 里的 .save-row/.save-label/
 *         .save-ops/.save-active/.save-new 这 5 组规则原样搬出去，<link> 仍排在
 *         styles/screens.css 之后、components.css 之前（层叠顺序一字未动）。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 *   · pywebview.api.card_save*   后端存档点读写
 *   · loadState()                读档后整页重刷（外壳的）
 *   · streamingEl / lastSeq      外壳的流式态与游标 —— 读档要"清空重来"，本屏直接置了
 *   · #chat                      读档后清空聊天区（**跨屏摸 DOM，阶段 5 该换成 bus 事件**）
 *   · prompt()/confirm()         改名/删除/覆盖仍是原生弹窗（原有行为，本轮不改交互）
 */
window.SaveScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 💾 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌多存档 =================
  // ===== 角色卡·多存档（新存档功能） =====
  // "正在看哪个角色的存档"真身是 DICK.state['save.current']，同名全局只是兼容访问器（阶段 3 收口）。
  DICK.state.bindGlobal('saveModalCur', 'save.current', null);

  function saveFmtTs(ts) {
    if (!ts) return '';
    try { var d = new Date(ts); if (!isNaN(d.getTime())) return d.toLocaleString(); } catch (e) {}
    return String(ts);
  }
  function openSaves(name) {
    saveModalCur = name;
    document.getElementById('saveTitle').textContent = '💾 存档 · ' + name;
    document.getElementById('saveLabel').value = '';
    document.getElementById('saveModal').classList.add('open');
    renderSaveList();
  }
  function renderSaveList() {
    var name = saveModalCur; if (!name) return;
    var box = document.getElementById('saveList');
    box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--sub)">加载中…</div>';
    pywebview.api.card_saves(name).then(function (r) {
      if (!r || !r.ok) {
        box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--sub)">' + ((r && r.err) || '加载失败') + '</div>';
        return;
      }
      var saves = r.saves || [];
      var active = r.active_save;
      if (!saves.length) {
        box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--sub)">还没有存档点。<br>继续聊天后点「📝 新存档」即把当前进度固化成一个存档点。</div>';
        return;
      }
      var html = '';
      saves.forEach(function (s) {
        var aid = s.id === active;
        html += '<div class="save-row' + (aid ? ' save-active' : '') + '">' +
          '<div class="save-meta" style="flex:1;min-width:0">' +
            '<span class="save-label">' + (aid ? '● ' : '') + escapeHtml(s.label || '未命名存档') + '</span>' +
            '<div style="font-size:11px;color:var(--sub)">' + (s.progress || 0) + ' 条对话 · ' + saveFmtTs(s.updated_ts) + '</div>' +
          '</div>' +
          '<div class="save-ops" style="flex:none">' +
            '<button class="iconbtn" title="读档（切换到该存档点）" data-sload="' + escapeHtml(s.id) + '">📂</button>' +
            '<button class="iconbtn" title="覆盖保存（把当前进度写到该存档点）" data-sovl="' + escapeHtml(s.id) + '">💾</button>' +
            '<button class="iconbtn" title="重命名" data-sren="' + escapeHtml(s.id) + '">✏️</button>' +
            '<button class="iconbtn act-del" title="删除" data-sdel="' + escapeHtml(s.id) + '">🗑️</button>' +
          '</div>' +
        '</div>';
      });
      box.innerHTML = html;
    }).catch(function () {
      box.innerHTML = '<div style="padding:20px;text-align:center;color:var(--sub)">加载失败</div>';
    });
  }

  /* ---------------- 按钮/列表绑定（片段注入之后才摸得到元素） ---------------- */
  function bindSaveButtons() {
    document.getElementById('saveNewBtn').onclick = function () {
      var name = saveModalCur; if (!name) return;
      var lbl = document.getElementById('saveLabel').value.trim();
      pywebview.api.card_save_new(name, lbl).then(function () { renderSaveList(); });
    };
    document.getElementById('saveCloseBtn').onclick = function () {
      document.getElementById('saveModal').classList.remove('open');
    };
    document.getElementById('saveList').addEventListener('click', function (e) {
      var name = saveModalCur; if (!name) return;
      var t = e.target, act = null, sid = null;
      while (t && t !== e.currentTarget && t.getAttribute) {
        var a = t.getAttribute('data-sload'); if (a) { act = 'sload'; sid = a; break; }
        a = t.getAttribute('data-sovl');   if (a) { act = 'sovl'; sid = a; break; }
        a = t.getAttribute('data-sren');   if (a) { act = 'sren'; sid = a; break; }
        a = t.getAttribute('data-sdel');   if (a) { act = 'sdel'; sid = a; break; }
        t = t.parentNode;
      }
      if (!act) return;
      if (act === 'sren') {
        var lbl = prompt('新的存档名：');
        if (lbl === null) return;
        pywebview.api.card_save_rename(name, sid, lbl).then(renderSaveList);
        return;
      }
      if (act === 'sdel') {
        if (!confirm('删除这个存档点？')) return;
        pywebview.api.card_save_delete(name, sid).then(renderSaveList);
        return;
      }
      if (act === 'sovl') {
        if (!confirm('用当前进度覆盖这个存档点？')) return;
        pywebview.api.card_save(name, '', sid).then(renderSaveList);
        return;
      }
      if (act === 'sload') {
        if (!confirm('读档：切换到该存档点？当前未保存的进度会被替换。')) return;
        pywebview.api.card_save_load(name, sid).then(function () {
          renderSaveList();
          // 整刷聊天与新角色历史
          document.getElementById('chat').innerHTML = '';
          streamingEl = null;
          lastSeq = 0;
          loadState();
        });
        return;
      }
    });
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('saveModal')) {
      console.error('[save] 片段没注入（找不到 #saveModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    bindSaveButtons();
  }

  function unmount() {
    var b = document.getElementById('saveNewBtn');
    if (b) { b.onclick = null; }
    var c = document.getElementById('saveCloseBtn');
    if (c) { c.onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    open: openSaves, render: renderSaveList, fmtTs: saveFmtTs
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前这三个都是 index.html 的顶层全局函数：
 *   · openSaves(name)   —— 角色列表里点「💾 存档」时叫它（index.html 里还有调用点）
 *   · renderSaveList()  —— 后端返回后重画列表
 *   · saveFmtTs(ts)     —— 时间戳格式化（本屏自己的渲染在用）
 * 同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function openSaves(name) { return window.SaveScreen.open(name); }
function renderSaveList() { return window.SaveScreen.render(); }
function saveFmtTs(ts) { return window.SaveScreen.fmtTs(ts); }

// 注册到路由：片段 = screens/save.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('save', { fragment: 'screens/save.html', module: window.SaveScreen });
