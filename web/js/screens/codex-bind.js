/* web/js/screens/codex-bind.js —— 编年史**编辑器**那一屏的按钮绑定（片段注入之后才摸得到元素）。
 *
 * 为什么单独一档：绑定语句必须在片段注入之后执行，所以只能是函数，由 codex-editor.js 的 codexMount() 调；
 * 顺手也让「这一屏有多少个触点」一眼能数完。
 * 只碰 codex 前缀的 id（播放器的 cx 那组在 codex-player-bind.js）；要跨屏的动作一律发 DICK.bus 事件。
 */

/* web/js/screens/codex-bind.js —— codex 屏的按钮绑定（编辑器和播放器各一组）。
 *
 * 为什么单独一档：绑定语句必须在**片段注入之后**执行，所以只能是函数，由 codex-editor.js 的
 * codexMount() 调；顺手也让「这一屏有多少个触点」一眼能数完。
 * 只碰 codex 前缀（编辑器那组）与 cx 前缀（播放器那组）的 id；跨屏动作一律发 DICK.bus 事件。
 *
 * // 播放器事件绑定   ← 原 index.html 的分段注释，保留出处（这一档现在两种绑定都有）
 */

function codexBindEditor() {
  document.getElementById('btnCodex').onclick = function () { DICK.bus.emit('gal:open-interface'); };
  document.getElementById('codexCloseBtn').onclick = function () { document.getElementById('codexModal').classList.remove('open'); };
  document.getElementById('codexNewBtn').onclick = codexNew;
  document.getElementById('codexSampleBtn').onclick = codexSample;
  document.getElementById('codexDraftBtn').onclick = codexDraft;
  document.getElementById('codexPasteBtn').onclick = codexPasteOpen;
  document.getElementById('codexPasteConvertBtn').onclick = codexPasteConvert;
  document.getElementById('codexImportBtn').onclick = codexImport;
  document.getElementById('codexImportZipBtn').onclick = codexImportZip;
  document.getElementById('codexImportCodexBtn').onclick = codexImportCodex;
  document.getElementById('codexAssocBtn').onclick = codexAssoc;
  document.getElementById('codexVoiceBtn').onclick = codexVoice;
  document.getElementById('codexSpriteBtn').onclick = codexImportSprites;
  document.getElementById('codexAdvancedBtn').onclick = codexAdvancedOpen;
  document.getElementById('codexTplPlayBtn').onclick = codexAdvancedPlay;
  document.getElementById('codexTplSaveBtn').onclick = codexAdvancedSave;
  document.getElementById('codexTplResetBtn').onclick = codexAdvancedReset;
  document.getElementById('codexExportCodexBtn').onclick = codexExportCodex;
  document.getElementById('codexDelBtn').onclick = codexDelete;
  document.getElementById('codexEditBtn').onclick = codexEdit;
  // 播放按钮不直接调 codexPlay()：开播是"播放器那一屏"的事，编辑器只发事件
  // （与 GAL 的预览、双击 .codex 自动打开走同一条 'codex:play'，入口只有一个）
  document.getElementById('codexPlayBtn').onclick = function () { DICK.bus.emit('codex:play'); };
  document.getElementById('codexReleaseBtn').onclick = codexRelease;
  document.getElementById('codexExportBtn').onclick = codexExport;
  document.getElementById('codexPackBtn').onclick = function () { codexPack(true); };
  document.getElementById('codexPackSaveBtn').onclick = codexPackSaveAs;
  document.getElementById('codexExeBtn').onclick = codexPackExe;
  document.getElementById('codexFilesBtn').onclick = codexShowFiles;
  document.getElementById('codexFmtBtn').onclick = codexFormat;
  document.getElementById('codexCheckBtn').onclick = codexCheck;
  document.getElementById('codexSaveBtn').onclick = codexSave;
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌