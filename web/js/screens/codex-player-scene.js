/* web/js/screens/codex-player-scene.js —— 编年史播放器（二）：场景推进/选项/条件/打字机/结局。
 *
 * 归属：结构在 web/screens/codex.html（cx 前缀的 id）。挂在 window.CodexPlayer 上，
 *       和 codex-player.js 是同一个屏的两半（它先加载，素材/音频那半在那边）。
 * 说明：条件分支 codexCond 与导出播放器里的 cxCond 同语义，是「预览和成品一致」的关键，
 *       这一段的判断顺序一个字没改。
 */

(function (global) {
  'use strict';
  var DICK = global.DICK;
  var P = global.CodexPlayer;              // codex-player.js 先加载
  /* 素材/背景/立绘/音频在 codex-player.js：老名字继续用，函数体一行没改 */
  var codexSetBg = P.setBg, codexPlayBgm = P.playBgm, codexSetSprites = P.setSprites,
      codexSetImages = P.setImages, codexPlayVoice = P.playVoice;

  function codexRole(name) {
    if (!name || !codexPlayer || !codexPlayer.script || !codexPlayer.script.roles) return null;
    return (codexPlayer.script.roles || []).find(function (r) { return r && r.name === name; }) || null;
  }
  function codexStartScene(id) {
    var scenes = codexPlayer.scenes;
    var found = false;
    for (var i = 0; i < scenes.length; i++) {
      if (scenes[i].id === id) { codexPlayer.scene = scenes[i]; codexPlayer.idx = i; found = true; break; }
    }
    if (!found) {
      // 场景不存在（剧本被改坏/跳转<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌失效）→ 显示结束页，避免卡死
      codexShowEnd('[ic:warning] 场景不存在: ' + id);
      return;
    }
    codexPlayer.curSceneId = codexPlayer.scene.id;
    codexPlayer.lineIdx = 0;
    codexPlayer.lines = codexPlayer.scene.lines || [];
    codexSetBg(codexPlayer.scene.bg);
    codexPlayBgm(codexPlayer.scene.bgm);
    // 场景级立绘布局（可选）：sc.sprites = [{file, pos}]
    if (codexPlayer.scene.sprites && codexPlayer.scene.sprites.length) {
      codexSetSprites(codexPlayer.scene.sprites);
    } else {
      codexSetSprites([]);
    }
    // 场景级图片（可被点内图片覆盖/退出）
    codexSetImages(codexPlayer.scene.images || null);
    codexNextLine();
  }
  function codexShowChoice(opts, hiddenCount, totalCount) {
    var box = document.getElementById('cxChoice');
    box.style.display = 'block';
    box.innerHTML = '';
    // 记录回溯点：选项出现时自动存档（GALGAME 经典"选错可回退"）
    if (codexPlayer) {
      codexPlayer.lastChoicePoint = { sceneId: codexPlayer.curSceneId, lineIdx: codexPlayer.lineIdx };
      var lb = document.getElementById('cxRewind');
      if (lb) lb.textContent = '[ic:fast_rewind] 回到选项';
    }
    if (hiddenCount) {
      // 让作者一眼看出"这里有条件分支被门住了"，而不是以为剧本漏写了选项
      var hint = document.createElement('div');
      hint.style.cssText = 'font-size:12px;color:var(--warn);margin:2px 0 6px';
      hint.textContent = '[ic:lock] ' + hiddenCount + '/' + (totalCount || 0) +
        ' 个选项因条件不满足被隐藏　' + codexVarsHint();
      box.appendChild(hint);
    } else if (codexPlayer && codexPlayer.vars && codexPlayer.vars.available) {
      var h2 = document.createElement('div');
      h2.style.cssText = 'font-size:11px;color:var(--sub,#8a93a3);margin:2px 0 6px';
      h2.textContent = codexVarsHint();
      box.appendChild(h2);
    }
    opts.forEach(function (o) {
      var b = document.createElement('button');
      b.className = 'btn2';
      b.textContent = o.text || '';
      // contrast-skip:fixed-dark —— 这一条画在 #codexPlayer 的纯黑幕里（同名围栏见 web/screens/codex.html）：
      // 白色 8% 覆层盖在黑幕上，浅色主题下播放器仍是黑的，所以底色不跟主题换。
      b.style.cssText = 'display:block;width:100%;margin:6px 0;text-align:left;font-size:15px;padding:10px 14px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.25);color:var(--text);border-radius:8px;cursor:pointer';
      // /contrast-skip
      b.onclick = function () {
        box.style.display = 'none';
        codexStopAuto();
        var lb2 = document.getElementById('cxRewind');
        if (lb2) lb2.textContent = '[ic:fast_rewind] 回溯';
        codexGoto(o.goto || '');
      };
      box.appendChild(b);
    });
    document.getElementById('cxText').textContent = '';
    document.getElementById('cxSpeaker').style.display = 'none';
  }
  function codexGoto(id) {
    if (!id) { codexNextLine(); return; }
    codexStartScene(id);
  }
  // ---------- 内嵌预览的条件分支（与导出播放器的 cxCond / cxFilter 同语义）----------
  // 2026-10 之前：内嵌预览既不评估条件、也不执行 setflag/roll ——
  // 条件选项在编辑器里永远全部显示、标志位永远不置位，作者只能导出以后才知道写得对不对。
  // 现在两边同语义，且预览读的是【本局机制状态的快照】。
  /* 这一行原来是顶层 var（全局）。搬进 IIFE 后如果还是 var，就会变成"两个变量"：
   * 外壳的 renderMechanism 写全局的那个、这里读自己那个（恒为 null），预览的条件分支静默失效。
   * 所以显式写到 global 上 —— 名字不变、写读还是同一份，实现在严格的块作用域里。 */
  global.mechSnapshot = null;   // renderMechanism 每次收到 state 都会更新它

  function codexSnapshotVars() {
    // 为什么用快照而不是实时状态：
    // ① 试玩时 setflag/roll 只改快照 —— 绝不能污染玩家真实存档的好感/标志；
    // ② 快照保留当前好感度 →“好感 85 才出现的隐藏选项”在预览里当场就能验证。
    var m = mechSnapshot || {};
    var st = m.state || null;
    if (!st) return { available: false, affection: null, status: {}, flags: {} };
    return {
      available: true,
      affection: (st.affection === undefined ? null : st.affection),
      status: st.status || {},
      flags: st.flags || {},
    };
  }
  function codexVars() {
    if (!codexPlayer) return null;
    if (!codexPlayer.vars) codexPlayer.vars = codexSnapshotVars();
    return codexPlayer.vars;
  }
  function codexNum(v) {
    if (v === null || v === undefined) return null;
    var n = Number(v);
    return isNaN(n) ? null : n;
  }
  function codexCmp(op, a, b) {
    if (op === '>=') return a >= b;
    if (op === '>') return a > b;
    if (op === '<=') return a <= b;
    if (op === '<') return a < b;
    if (op === '!=') return a != b;
    return a == b;
  }
  function codexCond(cond) {
    if (!cond || cond === true || typeof cond !== 'object' || !Object.keys(cond).length) return true;
    var v = codexVars();
    if (!v || !v.available) return true;   // 没有机制状态（作者模式）→ 不隐藏，与导出播放器一致
    if (cond.all && Array.isArray(cond.all)) return cond.all.every(codexCond);
    if (cond.any && Array.isArray(cond.any)) return cond.any.some(codexCond);
    if ('aff' in cond) {
      var t = cond.aff, op = '==', n = null;
      if (typeof t === 'string') {
        var m = /^\s*(>=|<=|>|<|!=|==|=)?\s*(-?\d+(?:\.\d+)?)\s*$/.exec(t);
        if (m) { op = m[1] || '=='; n = codexNum(m[2]); } else n = codexNum(t);
      } else n = codexNum(t);
      var aff = codexNum(v.affection);
      if (n === null || aff === null) return false;
      return codexCmp(op, aff, n);
    }
    if (cond.status && typeof cond.status === 'object') {
      var sts = v.status || {};
      return Object.keys(cond.status).every(function (k) {
        var a = sts[k], b = cond.status[k];
        if (codexNum(a) !== null && codexNum(b) !== null) return codexCmp('==', codexNum(a), codexNum(b));
        return String(a) == String(b);
      });
    }
    if (cond.flags && Array.isArray(cond.flags)) {
      var fl = v.flags || {};
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
  function codexFilterOpts(opts) {
    var shown = [], hidden = 0;
    (opts || []).forEach(function (o) {
      if (o && o.if !== undefined && o.if !== null && !codexCond(o.if)) { hidden++; return; }
      shown.push(o);
    });
    return { shown: shown, hidden: hidden, total: (opts || []).length };
  }
  function codexEffect(name) {
    var el = document.getElementById('cxBg');
    if (!el) return;
    if (name === 'shake') {
      el.style.transition = 'none';
      el.style.transform = 'translateX(-9px)';
      setTimeout(function () {
        el.style.transform = 'translateX(9px)';
        setTimeout(function () { el.style.transform = ''; el.style.transition = ''; }, 70);
      }, 70);
    } else if (name === 'flash') {
      el.style.filter = 'brightness(2.2)';
      setTimeout(function () { el.style.filter = ''; }, 180);
    }
  }
  function codexVarsHint() {
    var v = codexVars();
    if (!v || !v.available) return '';
    var parts = [];
    if (v.affection !== null && v.affection !== undefined) parts.push('好感 ' + v.affection);
    var fk = Object.keys(v.flags || {});
    if (fk.length) parts.push('标志 ' + fk.join('/'));
    var sk = Object.keys(v.status || {});
    if (sk.length) parts.push('状态 ' + sk.map(function (k) { return k + '=' + v.status[k]; }).join(' '));
    return parts.length ? ('预览状态：' + parts.join('　')) : '';
  }

  function codexNextLine() {
    if (!codexPlayer) return;
    if (codexPlayer.waitTimer) { clearTimeout(codexPlayer.waitTimer); codexPlayer.waitTimer = null; }  // 点一下就跳过等待
    if (codexPlayer.typing) { codexSkipTyping(); return; }
    if (codexPlayer.lineIdx >= codexPlayer.lines.length) {
      // 场景播完：jump → next → 完结
      // （旧注释写的是"默认回场景列表第一个（避免卡死）"，与实现不符，已改正）
      var sc = codexPlayer.scene;
      if (sc && sc.jump) { codexStartScene(sc.jump); return; }
      if (sc && sc.next) { codexStartScene(sc.next); return; }
      // 无后续 → 结束
      codexShowEnd('完结');
      return;
    }
    var ln = codexPlayer.lines[codexPlayer.lineIdx++];
    if (!ln || typeof ln !== 'object') { codexNextLine(); return; }
    // 行内资源切换（台词行可同时切背景/音乐/立绘/配音）
    if (ln.bg) codexSetBg(ln.bg);
    if (ln.bgm) codexPlayBgm(ln.bgm);
    // 若台词指定了角色，且没单独写立绘/语音 → 自动套用该角色的默认立绘/音色
    var __role = codexRole(ln.speaker);
    var __sprite = ln.sprite || (__role && __role.sprite);
    var __voice = ln.voice || (__role && __role.voice);
    // 立绘多位置：sprites 数组优先；单立绘 sprite + pos 兼容
    if (ln.sprites && ln.sprites.length) {
      codexSetSprites(ln.sprites);
    } else if (__sprite) {
      codexSetSprites([{ file: __sprite, pos: ln.pos || 'center' }]);
    }
    if (__voice) codexPlayVoice(__voice);
    // 点内多张图片：进入/退出
    if (ln.images && ln.images.length) codexSetImages(ln.images);
    else if (ln.clearImages || ln.hideImages) codexSetImages(null);
    if ('text' in ln) {
      codexTypeText(ln.text || '', ln.speaker || '');
    } else if ('note' in ln) {
      var noteEl = document.getElementById('cxNote');
      noteEl.textContent = ln.note || '';
      document.getElementById('cxText').textContent = '';
      document.getElementById('cxSpeaker').style.display = 'none';
      codexScheduleAuto();
    } else if ('choice' in ln) {
      document.getElementById('cxNote').textContent = '';
      var __f = codexFilterOpts(ln.choice || []);
      codexShowChoice(__f.shown, __f.hidden, __f.total);
    } else if ('jump' in ln) {
      codexGoto(ln.jump);
    } else if ('end' in ln) {
      codexShowEnd(ln.end);
    } else if ('action' in ln) {
      // 插件钩子：调用现有插件命令（如 /speak 语音合成、/tts 等）
      // 注意：导出成独立 HTML 后没有后端，这一句会被跳过（导出播放器里的行为）
      pywebview.api.codex_run_action(String(ln.action)).then(function () {}).catch(function () {});
      codexNextLine();
    } else if (ln.kind === 'hide') {
      codexSetSprites([]); codexNextLine();
    } else if (ln.kind === 'effect') {
      codexEffect(ln.effect); codexNextLine();
    } else if (ln.kind === 'wait') {
      // 真等待（导出播放器同步为同一语义）：默认 300ms，上限 5s，点一下可跳过
      var __ms = codexNum(ln.ms);
      __ms = (__ms === null ? 300 : Math.max(0, Math.min(__ms, 5000)));
      codexPlayer.waitTimer = setTimeout(function () {
        codexPlayer.waitTimer = null;
        codexNextLine();
      }, __ms);
    } else if (ln.kind === 'setflag') {
      var __v = codexVars();
      var __k = (ln.flag && ln.flag.k) || '';
      if (__v && __k) __v.flags[__k] = (ln.flag && ln.flag.v !== undefined) ? ln.flag.v : true;
      codexNextLine();
    } else if (ln.kind === 'roll') {
      var __v2 = codexVars();
      var __rk = (ln.roll && ln.roll.k) || '';
      var __d = codexNum(ln.roll && ln.roll.d);
      if (__v2 && __rk) __v2.flags[__rk] = 1 + Math.floor(Math.random() * (__d && __d > 0 ? __d : 100));
      codexNextLine();
    } else if (ln.kind === 'bg' || ln.kind === 'bgm' || ln.kind === 'sfx' || ln.kind === 'show') {
      codexNextLine();          // 资源类步骤：上面已经切过资源，这里只负责前进
    } else {
      // 兜底：任何没识别出来的步骤也要前进 —— 旧版会"什么都不做"，表现为
      // 预览里莫名多一次点击、甚至看起来卡住。
      codexNextLine();
    }
  }
  function codexTypeText(text, speaker) {
    var el = document.getElementById('cxText');
    var sp = document.getElementById('cxSpeaker');
    document.getElementById('cxNote').textContent = '';
    el.textContent = '';
    if (speaker) { sp.style.display = 'block'; sp.textContent = speaker; }
    else sp.style.display = 'none';
    codexPlayer.typing = true;
    // 打字机速度：按行长度自适应（短句慢速有味道，长句提速不拖沓）
    var len = text.length;
    var interval = len > 120 ? 14 : len > 50 ? 22 : 32;
    if (codexTypeSpeed === 'fast') interval = 4;
    else if (codexTypeSpeed === 'slow') interval = 45;
    var i = 0;
    var step = function () {
      if (!codexPlayer) return;
      if (i < text.length) {
        el.textContent = text.slice(0, i + 1);
        i++;
        codexPlayer.typingTimer = setTimeout(step, interval);
      } else {
        codexPlayer.typing = false;
        codexScheduleAuto();
      }
    };
    step();
  }
  function codexSkipTyping() {
    if (!codexPlayer || !codexPlayer.typing) return;
    if (codexPlayer.typingTimer) clearTimeout(codexPlayer.typingTimer);
    var el = document.getElementById('cxText');
    var ln = codexPlayer.lines[codexPlayer.lineIdx - 1];
    if (ln && 'text' in ln) el.textContent = ln.text || '';
    codexPlayer.typing = false;
    codexScheduleAuto();
  }
  function codexScheduleAuto() {
    if (!codexPlayer || !codexPlayer.auto) return;
    if (codexPlayer.autoTimer) clearTimeout(codexPlayer.autoTimer);
    codexPlayer.autoTimer = setTimeout(function () {
      if (codexPlayer && codexPlayer.auto) codexNextLine();
    }, 1600);
  }
  function codexStopAuto() {
    if (!codexPlayer) return;
    codexPlayer.auto = false;
    if (codexPlayer.autoTimer) { clearTimeout(codexPlayer.autoTimer); codexPlayer.autoTimer = null; }
    var b = document.getElementById('cxAuto');
    if (b) b.textContent = '[ic:fast_forward] 自动';
  }
  function codexShowEnd(title) {
    codexStopAuto();
    document.getElementById('cxEndTitle').textContent = title || '结局';
    document.getElementById('cxEnd').style.display = 'flex';
  }

  /* 挂到同一个对象上（codex-player.js 先加载，P 一定在） */
  P.startScene = codexStartScene;
  P.next = codexNextLine;
  P.showChoice = codexShowChoice;
  P.goto = codexGoto;
  P.role = codexRole;
  P.vars = codexVars;
  P.snapshotVars = codexSnapshotVars;
  P.cond = codexCond;
  P.filterOpts = codexFilterOpts;
  P.effect = codexEffect;
  P.varsHint = codexVarsHint;
  P.typeText = codexTypeText;
  P.skipTyping = codexSkipTyping;
  P.scheduleAuto = codexScheduleAuto;
  P.stopAuto = codexStopAuto;
  P.showEnd = codexShowEnd;
  P.num = codexNum;
  P.cmp = codexCmp;
})(window);

/* ---- 兼容门面（老全局名；codex-bind.js 的播放器按钮与外壳的自动播放还在叫）---- */
function codexNextLine() { return window.CodexPlayer.next(); }
function codexStartScene(id) { return window.CodexPlayer.startScene(id); }
function codexScheduleAuto() { return window.CodexPlayer.scheduleAuto(); }
function codexStopAuto() { return window.CodexPlayer.stopAuto(); }
function codexCond(c) { return window.CodexPlayer.cond(c); }

