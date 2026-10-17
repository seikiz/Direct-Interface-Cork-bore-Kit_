/* web/js/screens/em.js —— 编辑消息屏（阶段 2：从 index.html 的顶层代码搬出，零行为变化）
 *
 * 这一屏比别的小，但它是"跨屏状态"最典型的一处：
 * 搬家前 —— 聊天屏的点击处理器把 `editTarget` 写进一个顶层 var，再直接去摸
 * `#emInput` / `#emTitle` / `#editMsgModal`；保存/取消也挂在顶层。
 * 于是"哪条消息在编辑"这件事，谁都能改、谁都不知道谁改了。
 * 搬家后 —— 聊天屏只发一条事件（`msg:edit`）就撒手；本屏自己开、自己存、自己关，
 * "正在编辑哪条"存在 DICK.state['editMsg.target']（键名登记在 state.js 的 SCHEMA）。
 *
 * 归属
 * 结构：web/screens/em.html（index.html 里原位只剩挂载点 <!--@screen:em-->）
 * 样式：没有专属 css 块（.modal/.modal-box/.field/.row 都是组件层的），所以不需要 em.css。
 * 契约：router 注入片段后调 mount()：绑保存/取消两个按钮 + 订阅 msg:edit。
 * 本屏依赖的外部符号（阶段 3/4/5 的收尾清单）
 * · pywebview.api.edit_message(seq, text)：后端改存档里的这一条
 * · T.editMsg：界面文案表（web/i18n.js 生成物）—— 标题跟着当前语言走
 * · alert()：失败提示还是原生弹窗（原有行为，本轮不改交互）
 */
window.EditMsgScreen = (function (global) {
  'use strict';

  var mounted = false;
  var offBus = null;

  /* ---------------- 状态：不放裸全局，放 state 容器 ---------------- */
  function target() {
    return DICK.state.get('editMsg.target', null);
  }

  function setTarget(v) {
    return DICK.state.set('editMsg.target', v);
  }

  /* ---------------- 动作 ---------------- */
  /* 打开编辑框。seq/kind 由聊天屏通过 msg:edit 事件带过来，text 是这条消息的正文。 */
  function open(seq, kind, text) {
    setTarget({ seq: seq, kind: kind });
    var input = document.getElementById('emInput');
    var title = document.getElementById('emTitle');
    if (input) { input.value = text || ''; }
    if (title) { title.textContent = T.editMsg; }
    var modal = document.getElementById('editMsgModal');
    if (modal) { modal.classList.add('open'); }
  }

  function save() {
    var t = target();
    if (!t) { return; }
    var v = document.getElementById('emInput').value.trim();
    if (!v) { return; }
    pywebview.api.edit_message(t.seq, v).then(function (r) {
      if (r && !r.ok) { alert((r && r.err) || 'failed'); return; }
      document.getElementById('editMsgModal').classList.remove('open');
      setTarget(null);
    });
  }

  function cancel() {
    document.getElementById('editMsgModal').classList.remove('open');
    setTarget(null);
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('editMsgModal')) {
      console.error('[em] 片段没注入（找不到 #editMsgModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    document.getElementById('emSave').onclick = save;
    document.getElementById('emCancel').onclick = cancel;
    offBus = DICK.bus.on('msg:edit', function (p) {
      if (p) { open(p.seq, p.kind, p.text); }
    });
  }

  function unmount() {
    if (offBus) { offBus(); offBus = null; }
    document.getElementById('emSave').onclick = null;
    document.getElementById('emCancel').onclick = null;
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    open: open, save: save, cancel: cancel, target: target
  };
})(window);

/* ===== 兼容入口（阶段 3/4/5 清理）=====
 * 搬家前这条流程没有独立的全局函数名 —— 它的"入口"就是顶层 var editTarget（谁写谁说了算）。
 * 那个 var 已经没了（改存 DICK.state），所以这里给愿意显式调用的老代码留一个稳定的名字。
 * 聊天屏自己用的是 DICK.bus.emit('msg:edit', …)，不走这个函数。 */
function openEditMsg(seq, kind, text) { return window.EditMsgScreen.open(seq, kind, text); }

// 注册到路由：片段 = screens/em.html（相对 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌web/index.html），模块 = 上面这个 IIFE
DICK.router.register('em', { fragment: 'screens/em.html', module: window.EditMsgScreen });
