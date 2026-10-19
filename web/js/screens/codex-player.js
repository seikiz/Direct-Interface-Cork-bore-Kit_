/* web/js/screens/codex-player.js —— 编年史播放器（一）：开播/退出、存档读档回溯、素材与音频。
 *
 * 归属：结构在 web/screens/codex.html 的 codexPlayer 里（cx 前缀那一堆 id 全是本文件的）。
 * 为什么套 IIFE：这块屏的 DOM 只许本文件碰；对外只留 window.CodexPlayer + 文件末尾的旧名门面。
 *
 * 与编辑器（codex 前缀）的接触面 —— 只有 DICK.state，没有 DOM：
 * · 播放器把「该不该占屏」写成 DICK.store.codex.set('playerOpen', true/false)，
 *   编辑器订阅后去动播放器容器的 display（容器 id 是 codex 前缀，归编辑器所有）。
 * · 剧本/包名照旧读 codexCur / codexPlayer（store/codex.js 的兼容访问器）。
 *
 * 同块的另一半：codex-player-scene.js（场景推进/选项/条件/打字/结局），它挂到同一个对象上。
 *
 * // ---------- CODEX 播放器 ----------   ← 原 index.html 的分段注释，保留出处
 */

window.CodexPlayer = (function (global) {
  'use strict';
  var DICK = global.DICK;
  /* 场景推进在 codex-player-scene.js；这三个是「调用发生在点击之后」的转发壳 */
  function codexStartScene(id) { return global.CodexPlayer.startScene(id); }
  function codexNextLine() { return global.CodexPlayer.next(); }
  function codexStopAuto() { return global.CodexPlayer.stopAuto(); }

  function codexPlay() {
    if (!codexCur) return;
    pywebview.api.codex_get(codexCur).then(function (r) {
      if (!r || !r.ok) { alert((r && r.err) || '读取失败'); return; }
      if (!r.valid) {
        if (!confirm('剧本结构有问题：\n' + (r.issues || []).slice(0, 4).join('\n') + '\n\n仍要播放吗？')) return;
      }
      codexPlayer = {
        script: r.script,
        scenes: r.script.scenes || [],
        idx: -1, scene: null, lineIdx: 0, lines: [],
        curSceneId: null, lastChoicePoint: null,
        audioBgm: null, audioVoice: null,
        auto: false, autoTimer: null, typing: false, typingTimer: null,
        cache: {},
      };
      // 标<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌题页
      document.getElementById('cxTitleName').textContent = r.script.name || codexCur;
      document.getElementById('cxTitleIntro').textContent = r.script.intro || '';
      // 章节选择（GALGAME 手感）：列出场景，点击直达
      var cl = document.getElementById('cxChapterList');
      cl.innerHTML = '';
      (r.script.scenes || []).forEach(function (sc, idx) {
        var lbl = sc.title || sc.id || ('章节 ' + (idx + 1));
        var b = document.createElement('button');
        b.textContent = (idx === 0 ? '▶ ' : '[ic:menu_book] ') + lbl;
        b.style.cssText = 'display:block;width:100%;text-align:left;margin:3px 0;padding:5px 10px;font-size:13px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);color:var(--text);border-radius:6px;cursor:pointer';
        b.onclick = function (e) {
          e.stopPropagation();
          document.getElementById('cxTitle').style.display = 'none';
          codexStartScene(sc.id);
        };
        cl.appendChild(b);
      });
      document.getElementById('cxTitle').style.display = 'flex';
      document.getElementById('cxEnd').style.display = 'none';
      document.getElementById('cxText').textContent = '';
      document.getElementById('cxSpeaker').style.display = 'none';
      document.getElementById('cxChoice').style.display = 'none';
      document.getElementById('cxNote').textContent = '';
      document.getElementById('cxSprites').innerHTML = '';
      document.getElementById('cxBg').style.backgroundImage = 'none';
    DICK.store.codex.set('playerOpen', true);   // 容器显隐由编辑器订阅（见 codex-editor.js 的 codexMount）
    });
  }
  function codexPlayerExit() {
    if (codexPlayer) {
      if (codexPlayer.audioBgm) { codexPlayer.audioBgm.pause(); codexPlayer.audioBgm = null; }
      if (codexPlayer.audioVoice) { codexPlayer.audioVoice.pause(); codexPlayer.audioVoice = null; }
      if (codexPlayer.typingTimer) clearTimeout(codexPlayer.typingTimer);
      if (codexPlayer.autoTimer) clearTimeout(codexPlayer.autoTimer);
      codexPlayer = null;
    }
    DICK.store.codex.set('playerOpen', false);
  }
  // ---------- 存档 / 读档 / 回溯（localStorage，按包名隔离） ----------
  function codexSaveSlot() {
    if (!codexPlayer || !codexPlayer.curSceneId) return;
    var slot = {
      pkg: codexCur,
      sceneId: codexPlayer.curSceneId,
      lineIdx: Math.max(0, codexPlayer.lineIdx - 1),
    };
    try {
      localStorage.setItem('codex_save_' + codexCur, JSON.stringify(slot));
      var b = document.getElementById('cxSave');
      if (b) { b.textContent = '[ic:save] 已存档'; setTimeout(function () { if (b) b.textContent = '[ic:save] 存档'; }, 1200); }
    } catch (e) {}
  }
  function codexLoadSlot() {
    if (!codexPlayer) return;
    var raw = null;
    try { raw = localStorage.getItem('codex_save_' + codexCur); } catch (e) {}
    if (!raw) { alert('还没有存档（播放中按「存档」）'); return; }
    var slot = null;
    try { slot = JSON.parse(raw); } catch (e) {}
    if (!slot || !slot.sceneId) { alert('存档损坏'); return; }
    codexStopAuto();
    // 跳转到存档场景，并定位到该行
    var sc = null;
    for (var i = 0; i < codexPlayer.scenes.length; i++) {
      if (codexPlayer.scenes[i].id === slot.sceneId) { sc = codexPlayer.scenes[i]; break; }
    }
    if (!sc) { alert('存档指向的场景不存在'); return; }
    codexPlayer.scene = sc;
    codexPlayer.curSceneId = sc.id;
    codexPlayer.lines = sc.lines || [];
    codexSetBg(sc.bg);
    codexPlayBgm(sc.bgm);
    // 重置 UI 层
    document.getElementById('cxChoice').style.display = 'none';
    document.getElementById('cxNote').textContent = '';
    document.getElementById('cxText').textContent = '';
    document.getElementById('cxSpeaker').style.display = 'none';
    // 从存档行重新执行（跳过纯控制行直到遇到文本/选项）
    codexPlayer.lineIdx = Math.max(0, Math.min(slot.lineIdx || 0, (sc.lines || []).length - 1));
    codexNextLine();
  }
  function codexRewind() {
    // 回溯：优先回到上一个选项点（选错可重选）；否则回当前场景开头
    if (!codexPlayer) return;
    codexStopAuto();
    var targetScene = null;
    var targetLine = 0;
    if (codexPlayer.lastChoicePoint && codexPlayer.lastChoicePoint.sceneId) {
      for (var i = 0; i < codexPlayer.scenes.length; i++) {
        if (codexPlayer.scenes[i].id === codexPlayer.lastChoicePoint.sceneId) {
          targetScene = codexPlayer.scenes[i];
          targetLine = codexPlayer.lastChoicePoint.lineIdx || 0;
          break;
        }
      }
    }
    if (!targetScene && codexPlayer.scene) {
      targetScene = codexPlayer.scene;
      targetLine = 0;
    }
    if (!targetScene) return;
    codexPlayer.lastChoicePoint = null;
    var lb = document.getElementById('cxRewind');
    if (lb) lb.textContent = '[ic:fast_rewind] 回溯';
    codexPlayer.scene = targetScene;
    codexPlayer.curSceneId = targetScene.id;
    codexPlayer.lineIdx = targetLine;
    codexPlayer.lines = targetScene.lines || [];
    document.getElementById('cxChoice').style.display = 'none';
    document.getElementById('cxNote').textContent = '';
    document.getElementById('cxText').textContent = '';
    document.getElementById('cxSpeaker').style.display = 'none';
    codexSetBg(targetScene.bg);
    codexPlayBgm(targetScene.bgm);
    codexNextLine();
  }
  function codexLoadAsset(kind, file, cb) {
    if (!file) { cb(null); return; }
    var key = kind + '|' + file;
    if (codexPlayer && codexPlayer.cache[key]) { cb(codexPlayer.cache[key]); return; }
    pywebview.api.codex_asset(codexCur, kind, file).then(function (r) {
      if (r && r.ok && r.data) {
        if (codexPlayer) codexPlayer.cache[key] = r.data;
        cb(r.data);
      } else cb(null);
    }).catch(function () { cb(null); });
  }
  function codexSetBg(file) {
    if (!file) { document.getElementById('cxBg').style.backgroundImage = 'none'; return; }
    codexLoadAsset('bg', file, function (url) {
      if (url) document.getElementById('cxBg').style.backgroundImage = 'url("' + url + '")';
    });
  }
  // 立绘多位置：sprites 数组 [{file, pos}] 或多立绘同屏；兼容单立绘 sprite + pos
  function codexSetSprites(list) {
    var box = document.getElementById('cxSprites');
    box.innerHTML = '';
    if (!list || !list.length) return;
    // 按 pos 分组：center 后画（最前），left/right 并列
    var order = ['right', 'center', 'left'];
    var groups = {};
    list.forEach(function (it) {
      var pos = it.pos || 'center';
      if (['left', 'center', 'right'].indexOf(pos) < 0) pos = 'center';
      if (!groups[pos]) groups[pos] = [];
      groups[pos].push(it);
    });
    order.forEach(function (pos) {
      (groups[pos] || []).forEach(function (it) {
        var img = document.createElement('img');
        img.className = 'cx-sprite cx-sprite-' + pos;
        img.style.cssText = codexSpriteCss(pos) + ';opacity:0';
        img.onload = function () { img.style.transition = 'opacity .45s ease'; img.style.opacity = '1'; };
        box.appendChild(img);
        codexLoadAsset('sprites', it.file, function (url) {
          if (url && img.parentNode) img.src = url;
        });
      });
    });
  }
  function codexSpriteCss(pos) {
    var base = 'position:absolute;bottom:0;height:100%;max-height:560px;object-fit:contain;' +
      'filter:drop-shadow(0 0 24px rgba(0,0,0,.6));transition:all .35s ease;';
    if (pos === 'left') return base + 'left:2%;transform-origin:bottom left;';
    if (pos === 'right') return base + 'right:2%;transform-origin:bottom right;';
    return base + 'left:50%;transform:translateX(-50%);transform-origin:bottom center;';
  }
  // 点内多张图片：自动适配大小、居中摆放；传空/clear 则退出该层
  function codexSetImages(list) {
    var box = document.getElementById('cxImages');
    if (!box) return;
    box.innerHTML = '';
    if (!list || !list.length) { box.style.display = 'none'; return; }
    box.style.display = 'flex';
    list.forEach(function (f) {
      var img = document.createElement('img');
      img.style.cssText = 'max-width:42%;max-height:58%;object-fit:contain;border-radius:8px;box-shadow:0 8px 28px rgba(0,0,0,.55);opacity:0;transition:opacity .4s ease';
      img.onload = function () { img.style.opacity = '1'; };
      box.appendChild(img);
      codexLoadAsset('sprites', f, function (url) { if (url && img.parentNode) img.src = url; });
    });
  }
  function codexPlayBgm(file) {
    var old = codexPlayer.audioBgm;
    if (old) { old.pause(); old.src = ''; codexPlayer.audioBgm = null; }
    if (!file) return;
    codexLoadAsset('bgm', file, function (url) {
      if (!url || !codexPlayer) return;
      var a = new Audio(url);
      a.loop = true;
      a.volume = (codexVolume / 100) * 0.6;
      a.play().catch(function () {});
      codexPlayer.audioBgm = a;
    });
  }
  function codexPlayVoice(file) {
    if (!file) return;
    codexLoadAsset('voice', file, function (url) {
      if (!url || !codexPlayer) return;
      if (codexPlayer.audioVoice) { codexPlayer.audioVoice.pause(); }
      var a = new Audio(url);
      a.volume = (codexVolume / 100) * 0.9;
      a.play().catch(function () {});
      codexPlayer.audioVoice = a;
    });
  }

  return {
    play: codexPlay,
    exit: codexPlayerExit,
    saveSlot: codexSaveSlot,
    loadSlot: codexLoadSlot,
    rewind: codexRewind,
    loadAsset: codexLoadAsset,
    setBg: codexSetBg,
    setSprites: codexSetSprites,
    spriteCss: codexSpriteCss,
    setImages: codexSetImages,
    playBgm: codexPlayBgm,
    playVoice: codexPlayVoice
  };
})(window);

/* ---- 兼容门面（老全局名，内部只转调模块；index.html 的 loadState 还在叫 codexPlay）---- */
function codexPlay() { return window.CodexPlayer.play(); }
function codexPlayerExit() { return window.CodexPlayer.exit(); }
function codexSaveSlot() { return window.CodexPlayer.saveSlot(); }
function codexLoadSlot() { return window.CodexPlayer.loadSlot(); }
function codexRewind() { return window.CodexPlayer.rewind(); }

// 别的屏要开播（GAL 的「预览」、双击 .codex 自动打开）只发这个事件
DICK.bus.on('codex:play', function (p) {
  if (p && p.pkg) { codexCur = p.pkg; }
  window.CodexPlayer.play();
});

