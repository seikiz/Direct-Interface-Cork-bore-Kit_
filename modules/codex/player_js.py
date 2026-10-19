# -*- coding: utf-8 -*-
"""modules/codex/player_js.py —— 导出播放器的内联 JS（一份数据，两处引用）

搬家来源：`codex_core.py` 的 `STANDALONE_PLAYER_JS`，**一字未改**（326 行的 JS 字符串）。

单独成文件的原因只有一个：它太大（占原文件 1/6），和 HTML 模板挤在一起会顶到行数预算。
真正用到它的地方在 `player.py`（可编辑模板）与 `render_standalone`（嵌入打包产物）。
"""

STANDALONE_PLAYER_JS = r"""
// ============ CODEX 独立播放器（零后端依赖：资源内嵌、localStorage 存档） ============
// __CODEX_DATA__ 由打包器注入：{script, assets}
__DICK_MARK_JS__
var __cxScript = __CODEX_DATA__.script;
var __cxAssets = __CODEX_DATA__.assets;
var cxState = null; // 播放器运行时状态
var cxVars = { state: (typeof __CODEX_STATE__ === 'undefined' ? null : __CODEX_STATE__) };  // 运行时机制状态（宿主注入；null=预览不隐藏）
function cxCmp(op, a, b) {
  if (op === '>=') return a >= b;
  if (op === '>') return a > b;
  if (op === '<=') return a <= b;
  if (op === '<') return a < b;
  if (op === '!=') return a != b;
  return a == b;
}
function cxNum(v) {
  if (v === null || v === undefined) return null;
  var n = Number(v);
  return isNaN(n) ? null : n;
}
function cxCond(cond) {
  if (!cond || cond === true || typeof cond !== 'object' || Object.keys(cond).length === 0) return true;
  var st = cxVars.state;
  if (st === null || st === undefined) return true;  // 预览/作者模式：不隐藏
  if (cond.all && Array.isArray(cond.all)) return cond.all.every(cxCond);
  if (cond.any && Array.isArray(cond.any)) return cond.any.some(cxCond);
  var state = st.mechanism_state || st;
  if ('aff' in cond) {
    var t = cond.aff, op = '==', n = null;
    if (typeof t === 'string') {
      var m = /^\s*(>=|<=|>|<|!=|==|=)?\s*(-?\d+(?:\.\d+)?)\s*$/.exec(t);
      if (m) { op = m[1] || '=='; n = cxNum(m[2]); } else n = cxNum(t);
    } else n = cxNum(t);
    var aff = cxNum(state.affection);
    if (n === null || aff === null) return false;
    return cxCmp(op, aff, n);
  }
  if (cond.status && typeof cond.status === 'object') {
    var sts = state.status || {};
    return Object.keys(cond.status).every(function (k) {
      var v = sts[k], q = cond.status[k];
      if (cxNum(v) !== null && cxNum(q) !== null) return cxCmp('==', cxNum(v), cxNum(q));
      return String(v) == String(q);
    });
  }
  if (cond.flags && Array.isArray(cond.flags)) {
    var fl = state.flags || {};
    return cond.flags.every(function (f) {
      f = String(f);
      var neg = f.charAt(0) === '!';
      var k = neg ? f.slice(1) : f;
      var present = Array.isArray(fl) ? fl.indexOf(k) >= 0 : (fl[k] ? !!fl[k] : false);
      return present !== neg;
    });
  }
  return true;
}
function cxFilter(items) {
  if (!Array.isArray(items)) return items;
  return items.filter(function (o) {
    if (o && o.if !== undefined && o.if !== null && !cxCond(o.if)) return false;
    return true;
  });
}
function cxEffect(name) {
  var el = document.getElementById('cxBg');
  if (!el) return;
  if (name === 'shake') { el.style.animation = 'none'; void el.offsetWidth; el.style.animation = 'cxshake .4s'; }
  else if (name === 'flash') { el.style.filter = 'brightness(2.2)'; setTimeout(function(){ el.style.filter = ''; }, 180); }
}

function cxGetAsset(kind, file) {
  if (!file) return null;
  return (__cxAssets[kind] || {})[file] || null;
}
function cxSetBg(file) {
  var el = document.getElementById('cxBg');
  var url = cxGetAsset('bg', file);
  el.style.backgroundImage = url ? 'url("' + url + '")' : 'none';
}
function cxSpriteCss(pos) {
  var base = 'position:absolute;bottom:0;height:100%;max-height:560px;object-fit:contain;filter:drop-shadow(0 0 24px rgba(0,0,0,.6));transition:all .35s ease;';
  if (pos === 'left') return base + 'left:2%;transform-origin:bottom left;';
  if (pos === 'right') return base + 'right:2%;transform-origin:bottom right;';
  return base + 'left:50%;transform:translateX(-50%);transform-origin:bottom center;';
}
function cxSetSprites(list) {
  var box = document.getElementById('cxSprites');
  box.innerHTML = '';
  if (!list || !list.length) return;
  ['right', 'center', 'left'].forEach(function (pos) {
    list.filter(function (it) { return (it.pos || 'center') === pos; }).forEach(function (it) {
      var url = cxGetAsset('sprites', it.file);
      if (!url) return;
      var img = document.createElement('img');
      img.src = url;
      img.style.cssText = cxSpriteCss(it.pos || 'center');
      box.appendChild(img);
    });
  });
}
function cxPlayBgm(file) {
  if (cxState && cxState.audioBgm) { cxState.audioBgm.pause(); cxState.audioBgm = null; }
  var url = cxGetAsset('bgm', file);
  if (!url) return;
  var a = new Audio(url);
  a.loop = true; a.volume = 0.6;
  a.play().catch(function () {});
  cxState.audioBgm = a;
}
function cxPlayVoice(file) {
  var url = cxGetAsset('voice', file);
  if (!url) return;
  if (cxState && cxState.audioVoice) cxState.audioVoice.pause();
  var a = new Audio(url);
  a.volume = 0.9; a.play().catch(function () {});
  cxState.audioVoice = a;
}
function cxTypeText(text, speaker) {
  var el = document.getElementById('cxText');
  var sp = document.getElementById('cxSpeaker');
  document.getElementById('cxNote').textContent = '';
  el.textContent = '';
  if (speaker) { sp.style.display = 'block'; sp.textContent = speaker; }
  else sp.style.display = 'none';
  cxState.typing = true;
  var i = 0;
  var step = function () {
    if (!cxState) return;
    if (i < text.length) { el.textContent = text.slice(0, i + 1); i++; cxState.typingTimer = setTimeout(step, 30); }
    else { cxState.typing = false; cxScheduleAuto(); }
  };
  step();
}
function cxSkipTyping() {
  if (!cxState || !cxState.typing) return;
  if (cxState.typingTimer) clearTimeout(cxState.typingTimer);
  var ln = cxState.lines[cxState.lineIdx - 1];
  if (ln && 'text' in ln) document.getElementById('cxText').textContent = ln.text || '';
  cxState.typing = false;
  cxScheduleAuto();
}
function cxScheduleAuto() {
  if (!cxState || !cxState.auto) return;
  if (cxState.autoTimer) clearTimeout(cxState.autoTimer);
  cxState.autoTimer = setTimeout(function () { if (cxState && cxState.auto) cxNextLine(); }, 1600);
}
function cxStopAuto() {
  if (!cxState) return;
  cxState.auto = false;
  if (cxState.autoTimer) { clearTimeout(cxState.autoTimer); cxState.autoTimer = null; }
  var b = document.getElementById('cxAuto'); if (b) b.textContent = '⏩ 自动';
}
function cxShowChoice(opts) {
  opts = cxFilter(opts || []);
  var box = document.getElementById('cxChoice');
  box.style.display = 'block';
  box.innerHTML = '';
  cxState.lastChoicePoint = { sceneId: cxState.curSceneId, lineIdx: cxState.lineIdx };
  var lb = document.getElementById('cxRewind'); if (lb) lb.textContent = '⏪ 回到选项';
  opts.forEach(function (o) {
    var b = document.createElement('button');
    b.textContent = o.text || '';
    b.style.cssText = 'display:block;width:100%;margin:6px 0;text-align:left;font-size:15px;padding:10px 14px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.25);color:#eee;border-radius:8px;cursor:pointer';
    b.onclick = function () {
      box.style.display = 'none';
      cxStopAuto();
      var lb2 = document.getElementById('cxRewind'); if (lb2) lb2.textContent = '⏪ 回溯';
      cxGoto(o.goto || '');
    };
    box.appendChild(b);
  });
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
}
function cxShowEnd(title) {
  cxStopAuto();
  document.getElementById('cxEndTitle').textContent = title || '结局';
  document.getElementById('cxEnd').style.display = 'flex';
}
function cxStartScene(id) {
  var scenes = cxState.scenes;
  var found = false;
  for (var i = 0; i < scenes.length; i++) {
    if (scenes[i].id === id) { cxState.scene = scenes[i]; found = true; break; }
  }
  if (!found) { cxShowEnd('⚠️ 场景不存在: ' + id); return; }
  cxState.curSceneId = cxState.scene.id;
  cxState.lineIdx = 0;
  cxState.lines = cxState.scene.lines || [];
  cxSetBg(cxState.scene.bg);
  cxPlayBgm(cxState.scene.bgm);
  if (cxState.scene.sprites && cxState.scene.sprites.length) cxSetSprites(cxState.scene.sprites);
  else cxSetSprites([]);
  cxNextLine();
}
function cxGoto(id) {
  if (!id) { cxNextLine(); return; }
  cxStartScene(id);
}
function cxNextLine() {
  if (!cxState) return;
  if (cxState.waitTimer) { clearTimeout(cxState.waitTimer); cxState.waitTimer = null; }  // 点一下跳过等待
  if (cxState.typing) { cxSkipTyping(); return; }
  if (cxState.lineIdx >= cxState.lines.length) {
    var sc = cxState.scene;
    if (sc && sc.jump) { cxStartScene(sc.jump); return; }
    if (sc && sc.next) { cxStartScene(sc.next); return; }
    cxShowEnd('完结');
    return;
  }
  var ln = cxState.lines[cxState.lineIdx++];
  if (!ln || typeof ln !== 'object') { cxNextLine(); return; }
  if (ln.bg) cxSetBg(ln.bg);
  if (ln.bgm) cxPlayBgm(ln.bgm);
  if (ln.sprites && ln.sprites.length) cxSetSprites(ln.sprites);
  else if (ln.sprite) cxSetSprites([{ file: ln.sprite, pos: ln.pos || 'center' }]);
  if (ln.voice) cxPlayVoice(ln.voice);
  if ('text' in ln) cxTypeText(ln.text || '', ln.speaker || '');
  else if ('note' in ln) {
    document.getElementById('cxNote').textContent = ln.note || '';
    document.getElementById('cxText').textContent = '';
    document.getElementById('cxSpeaker').style.display = 'none';
    cxScheduleAuto();
  } else if ('choice' in ln) {
    document.getElementById('cxNote').textContent = '';
    cxShowChoice(ln.choice || []);
  } else if ('jump' in ln) cxGoto(ln.jump);
  else if ('end' in ln) cxShowEnd(ln.end);
  else if (ln.kind === 'hide') { cxSetSprites([]); cxNextLine(); }
  else if (ln.kind === 'effect') { cxEffect(ln.effect); cxNextLine(); }
  else if (ln.kind === 'wait') {
    // 真等待（与主程序内嵌预览同语义）：默认 300ms、上限 5s、点一下可跳过
    var ms = Number(ln.ms); if (isNaN(ms)) ms = 300;
    ms = Math.max(0, Math.min(ms, 5000));
    cxState.waitTimer = setTimeout(function () { cxState.waitTimer = null; cxNextLine(); }, ms);
  }
  else if (ln.kind === 'setflag') { if (cxVars.state && cxVars.state.flags) { var fk = ln.flag && ln.flag.k; if (fk) cxVars.state.flags[fk] = (ln.flag && ln.flag.v) || true; } cxNextLine(); }
  else if (ln.kind === 'roll') { if (cxVars.state && cxVars.state.flags) { var rk = ln.roll && ln.roll.k; if (rk) cxVars.state.flags[rk] = 1 + Math.floor(Math.random() * ((ln.roll && ln.roll.d || 100))); } cxNextLine(); }
  else if (ln.kind === 'bg' || ln.kind === 'bgm' || ln.kind === 'sfx' || ln.kind === 'show') { cxNextLine(); }
  else if ('action' in ln) cxNextLine(); // 独立版无后端：跳过行动钩子
  else cxNextLine();                      // 兜底：没识别出来的步骤也前进，别卡住
}
function cxSave() {
  if (!cxState || !cxState.curSceneId) return;
  var slot = { sceneId: cxState.curSceneId, lineIdx: Math.max(0, cxState.lineIdx - 1) };
  try { localStorage.setItem('codex_save', JSON.stringify(slot)); var b = document.getElementById('cxSave'); if (b) { b.textContent = '💾 已存档'; setTimeout(function () { if (b) b.textContent = '💾 存档'; }, 1200); } } catch (e) {}
}
function cxLoad() {
  if (!cxState) return;
  var raw = null; try { raw = localStorage.getItem('codex_save'); } catch (e) {}
  if (!raw) { alert('还没有存档'); return; }
  var slot = null; try { slot = JSON.parse(raw); } catch (e) {}
  if (!slot || !slot.sceneId) { alert('存档损坏'); return; }
  cxStopAuto();
  var sc = null;
  for (var i = 0; i < cxState.scenes.length; i++) if (cxState.scenes[i].id === slot.sceneId) { sc = cxState.scenes[i]; break; }
  if (!sc) { alert('存档指向的场景不存在'); return; }
  cxState.scene = sc; cxState.curSceneId = sc.id;
  cxState.lines = sc.lines || [];
  cxSetBg(sc.bg); cxPlayBgm(sc.bgm);
  document.getElementById('cxChoice').style.display = 'none';
  document.getElementById('cxNote').textContent = '';
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
  cxState.lineIdx = Math.max(0, Math.min(slot.lineIdx || 0, (sc.lines || []).length - 1));
  cxNextLine();
}
function cxRewind() {
  if (!cxState) return;
  cxStopAuto();
  var targetScene = null, targetLine = 0;
  if (cxState.lastChoicePoint && cxState.lastChoicePoint.sceneId) {
    for (var i = 0; i < cxState.scenes.length; i++) if (cxState.scenes[i].id === cxState.lastChoicePoint.sceneId) { targetScene = cxState.scenes[i]; targetLine = cxState.lastChoicePoint.lineIdx || 0; break; }
  }
  if (!targetScene && cxState.scene) { targetScene = cxState.scene; targetLine = 0; }
  if (!targetScene) return;
  cxState.lastChoicePoint = null;
  var lb = document.getElementById('cxRewind'); if (lb) lb.textContent = '⏪ 回溯';
  cxState.scene = targetScene; cxState.curSceneId = targetScene.id;
  cxState.lineIdx = targetLine; cxState.lines = targetScene.lines || [];
  document.getElementById('cxChoice').style.display = 'none';
  document.getElementById('cxNote').textContent = '';
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
  cxSetBg(targetScene.bg); cxPlayBgm(targetScene.bgm);
  cxNextLine();
}
function cxStart() {
  cxState = {
    script: __cxScript, scenes: __cxScript.scenes || [],
    scene: null, lineIdx: 0, lines: [], curSceneId: null, lastChoicePoint: null,
    audioBgm: null, audioVoice: null, auto: false, autoTimer: null, typing: false, typingTimer: null,
  };
  document.getElementById('cxTitleName').textContent = __cxScript.name || 'CODEX';
  document.getElementById('cxTitleIntro').textContent = __cxScript.intro || '';
  document.getElementById('cxTitle').style.display = 'flex';
  document.getElementById('cxEnd').style.display = 'none';
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
  document.getElementById('cxChoice').style.display = 'none';
  document.getElementById('cxNote').textContent = '';
  document.getElementById('cxSprites').innerHTML = '';
  document.getElementById('cxBg').style.backgroundImage = 'none';
}
document.addEventListener('DOMContentLoaded', cxStart);
document.getElementById('cxTitle').onclick = function () { document.getElementById('cxTitle').style.display = 'none'; cxStartScene((cxState.scenes[0] || {}).id || ''); };
document.getElementById('cxEnd').onclick = function () { document.getElementById('cxEnd').style.display = 'none'; cxState = null; document.getElementById('cxSprites').innerHTML = ''; cxStart(); };
document.getElementById('cxSave').onclick = cxSave;
document.getElementById('cxLoad').onclick = cxLoad;
document.getElementById('cxRewind').onclick = cxRewind;
document.getElementById('cxAuto').onclick = function () {
  if (!cxState) return;
  cxState.auto = !cxState.auto;
  this.textContent = cxState.auto ? '⏸ 停止自动' : '⏩ 自动';
  if (cxState.auto) cxScheduleAuto(); else cxStopAuto();
};
document.getElementById('cxTextbox').onclick = function () {
  if (!cxState) return;
  if (document.getElementById('cxChoice').style.display === 'block') return;
  if (document.getElementById('cxTitle').style.display === 'flex') return;
  if (document.getElementById('cxEnd').style.display === 'flex') return;
  cxNextLine();
};
"""
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌