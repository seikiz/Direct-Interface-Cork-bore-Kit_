/* Button.js —— 按钮工厂（组件层，第一件落地的组件）
 *
 * 契约（见 web/UI_ARCHITECTURE.md「组件契约」）：
 *   · props 进、事件出：不读全局状态，交互只经 onClick 往外抛；
 *   · 不自挂载：返回元素，由调用方决定插哪里；
 *   · 样式边界：**只用既有的 `.btn2` / `.btn2.ghost`** —— 本项目已经有一套按钮外观，
 *     这里再发明一套 `.btn--primary` 就等于把观感焊死在组件里（那是硬边界里明令禁止的）；
 *   · 组件内不写行内 `style="color:#…"`。
 *
 * 变体语义（与安卓侧 DickButtonVariant 对齐）：
 *   primary —— 当前值/主操作 → 实心（.btn2）
 *   ghost   —— 次级入口/取消 → 描边（.btn2.ghost）
 *   plain   —— 行内轻动作     → 描边（.btn2.ghost，默认）
 *
 * 用法：
 *   document.body.appendChild(DICK.components.Button({
 *     label: '测试并保存', variant: 'primary', onClick: function (e) { … }
 *   }));
 */
(function (global) {
  'use strict';

  var VARIANTS = { primary: '', ghost: ' ghost', plain: ' ghost' };
  var SIZES = { sm: ' ag-btn-sm', md: '', lg: ' ag-btn-lg' };

  function Button(props) {
    var p = props || {};
    var el = document.createElement('button');
    var variant = VARIANTS.hasOwnProperty(p.variant) ? p.variant : 'plain';
    el.type = p.type || 'button';
    el.className = 'btn2' + (VARIANTS[variant] || '') + (SIZES[p.size] || '') +
      (p.className ? ' ' + p.className : '');
    el.textContent = p.label == null ? '' : String(p.label);
    if (p.title) { el.title = String(p.title); }
    if (p.id) { el.id = String(p.id); }
    if (p.disabled) { el.disabled = true; }
    if (typeof p.onClick === 'function') {
      el.addEventListener('click', function (e) {
        if (el.disabled) { return; }
        p.onClick(e);
      });
    }
    return el;
  }

  global.DICK = global.DICK || {};
  global.DICK.components = global.DICK.components || {};
  global.DICK.components.Button = Button;
})(window);
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌