/* 从 index.html 内联脚本拆出（第 2/4 段，顺序加载；全局作用域不变） */
// ---------- 分道执行：把后端异步任<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌务包成 Promise ----------
// 后端现在按"一个模块一条运行线"干活（见 jobs.py）：慢活儿（工坊网络/看图/插件钩子）
// 不再占着一次 js_api 调用干等。这里让调用方**几乎不用改**——
// 把「api 名字加括号」那套换成 jobWait('kind', [参数])，拿到的还是 Promise。
// 注意：注释里别写出真实的「pywebview.api.方法名(」形式 —— tests/test_js_api_binding.py
// 是按原文扫"前端调了哪些接口"的，注释里的例子会被当成一次调用（这次就踩了）。
var _jobWaiters = {};       // jobId -> {resolve, reject, timer}
function jobWait(kind, args, timeoutMs) {
  return new Promise(function (resolve, reject) {
    pywebview.api.job_submit(kind, args || []).then(function (r) {
      if (!r || !r.ok) { reject(new Error((r && r.err) || '任务提交失败')); return; }
      var jid = r.job;
      var timer = setTimeout(function () {
        if (_jobWaiters[jid]) {
          delete _jobWaiters[jid];
          reject(new Error('任务超时（' + kind + '）'));
        }
      }, timeoutMs || 60000);
      _jobWaiters[jid] = { resolve: resolve, reject: reject, timer: timer };
    }).catch(reject);
  });
}
function jobResolveEvents(events) {
  (events || []).forEach(function (e) {
    if (!e || e.type !== 'job') return;
    var w = _jobWaiters[e.id];
    if (!w) return;
    delete _jobWaiters[e.id];
    clearTimeout(w.timer);
    if (e.ok) w.resolve(e.result);
    else w.reject(new Error(e.err || '任务失败'));
  });
}

document.getElementById('input').addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
document.getElementById('roleList').addEventListener('change', function (e) {
  if (e.target.getAttribute('data-role')) {
    // 切换角色 = 保存当前会话并初始化界面（类似微信切换会话）
    // 后端 _activate_core 会触发 epoch+1，前端 poll 自动整刷为新角色的历史
    pywebview.api.select_roles(JSON.stringify(selectedRoles())).then(function () {
      // 立即整刷（不等下一次 poll 150ms）
      document.getElementById('chat').innerHTML = '';
      streamingEl = null;
      lastSeq = 0;
      loadState();
    });
  }
});
document.getElementById('worldList').addEventListener('change', function (e) {
  if (e.target.getAttribute('data-world')) {
    pywebview.api.select_worlds(JSON.stringify(selectedWorlds()));
  }
});
var editingRole = null;
// 世界书条目屏整体搬到了 web/screens/wm.html + web/js/screens/wm.js（阶段3）：
// editingWorld / wmParams 真身是 DICK.state['wm.*']，PARAM_KEYS / PARAM_LABELS 也跟着走了，
// 兼容入口（editingWorld / wmParams / renderWmParams / …）在 wm.js 里注册，这里一个字都不用改。

function collectRoleFields() {
  var advanced = null;
  // 机制卡：核心玩法，无论是否开发者模式都收集
  var mech = collectMechanics();
  // 战斗系统：角色卡一部分，同样直接收集
  var battle = collectBattle();
  if (window.devMode) {
    var gameName = document.getElementById('nrGameNameInput').value.trim();
    var gameRules = document.getElementById('nrGameRulesInput').value.trim();
    var gameState = document.getElementById('nrGameStateInput').value.trim();
    var extra = document.getElementById('nrExtraPromptInput').value.trim();
    var devNotes = document.getElementById('nrDevNotesInput').value.trim();
    var regexList = [];
    document.getElementById('nrRegexInput').value.split('\n').forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var p = line.split('|');
      if (p.length < 4) return;
      var scope = p[4] ? p[4].trim() : 'both';
      if (['ai', 'user', 'both'].indexOf(scope) < 0) scope = 'both';
      regexList.push({ id: p[0].trim(), name: p[1] ? p[1].trim() : p[0].trim(), pattern: p[2], replace: p.slice(3).join('|'), scope: scope, enabled: true });
    });
    var qrList = [];
    document.getElementById('nrCardQrInput').value.split('\n').forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var i = line.indexOf('|');
      if (i > 0) qrList.push({ label: line.slice(0, i).trim(), text: line.slice(i + 1).trim() });
    });
    advanced = {
      game: (gameRules || gameName) ? { name: gameName, rules: gameRules, state: gameState } : null,
      extra_prompt: extra,
      dev_notes: devNotes,
      card_quick_replies: qrList,
      card_face: document.getElementById('nrCardFaceInput').value.trim(),
    };
    if (regexList.length) advanced.regex_rules = regexList;
    if (mech) advanced.mechanics = mech;
    if (battle) advanced.battle = battle;
  } else if (mech || battle || regexList.length) {
    advanced = {};
    if (mech) advanced.mechanics = mech;
    if (battle) advanced.battle = battle;
    if (regexList.length) advanced.regex_rules = regexList;
  }
  return {
    legacy: document.getElementById('nrLegacyInput').value.trim(),
    appearance: document.getElementById('nrAppearanceInput').value.trim(),
    personality: document.getElementById('nrPersonalityInput').value.trim(),
    background: document.getElementById('nrBackgroundInput').value.trim(),
    speech: document.getElementById('nrSpeechInput').value.trim(),
    first_mes: document.getElementById('nrFirstMesInput').value.trim(),
    mes_example: document.getElementById('nrMesExampleInput').value.trim(),
    notes: document.getElementById('nrNotesInput').value.trim(),
    unlocked: document.getElementById('nrUnlockInput').checked,
    advanced: advanced,
  };
}

function cardFaceImport() {
  var inp = document.createElement('input');
  inp.type = 'file';
  inp.accept = '.html,.htm,text/html,.txt';
  inp.onchange = function () {
    var f = inp.files[0];
    if (!f) return;
    var r = new FileReader();
    r.onload = function () { document.getElementById('nrCardFaceInput').value = r.result; };
    r.readAsText(f);
  };
  inp.click();
}

function openCardFace(html) {
  var m = document.getElementById('cardFaceModal');
  if (!m) return;
  var fr = m.querySelector('iframe');
  if (fr) fr.srcdoc = html || '<div style="color:var(--text-sub);padding:30px">（暂无卡面。在角色→编辑→开发者模式→卡面 导入或编写 HTML。）</div>';
  m.classList.add('open');
}
function cardFacePreview() {
  openCardFace(document.getElementById('nrCardFaceInput').value || '');
}
function cardFaceClose() { var m = document.getElementById('cardFaceModal'); if (m) m.classList.remove('open'); }
function cardFaceShow() {
  var rs = selectedRoles();
  var name = rs[0];
  if (!name) { openCardFace(''); return; }
  try {
    pywebview.api.get_role(name).then(function (r) {
      var o = (typeof r === 'string') ? JSON.parse(r) : r;
      openCardFace((o && o.advanced && (o.advanced.card_face || '')) || '');
    }).catch(function () { openCardFace(''); });
  } catch (e) { openCardFace(''); }
}

// ---------- 机制/状态/战斗折叠区 ----------
function toggleFold(id) {
  var el = document.getElementById(id);
  if (el) el.classList.toggle('folded');
}
function setFold(id, open) {
  var el = document.getElementById(id);
  if (el) el.classList.toggle('folded', !open);
}

// 快速模板：一键填充机制/状态/战斗（工程冗余：让不会填格式的用户也能用）
// ---------- 事件可视化编辑器 ----------
// 数组 mechEvents 是真实来源；#nrEvents 只是序列化产物，供既有读写路径使用。
var mechEvents = [];
var evRawMode = false;

function evNewId() {
  var n = 1, used = {};
  mechEvents.forEach(function (e) { used[e.id] = true; });
  while (used['ev' + n]) n++;
  return 'ev' + n;
}

function evAdd() {
  mechEvents.push({ id: evNewId(), name: '', aff_ge: '', keywords: [],
                    prompt: '', once: true, cooldown: 0 });
  evRender();
}

function evDel(i) { mechEvents.splice(i, 1); evRender(); }

function evMove(i, d) {
  var j = i + d;
  if (j < 0 || j >= mechEvents.length) return;
  var t = mechEvents[i]; mechEvents[i] = mechEvents[j]; mechEvents[j] = t;
  evRender();
}

function evSet(i, f, v) { if (mechEvents[i]) { mechEvents[i][f] = v; evSyncTextarea(); } }

function evToggleRaw() {
  evRawMode = !evRawMode;
  document.getElementById('evEditor').style.display = evRawMode ? 'none' : '';
  document.getElementById('nrEvents').style.display = evRawMode ? '' : 'none';
  document.getElementById('evRawHint').style.display = evRawMode ? '' : 'none';
  var lbl = document.getElementById('evRawBtnLabel');
  if (lbl) lbl.textContent = evRawMode ? '回到可视化' : '显示原始格式';
  if (evRawMode) evSyncTextarea();
  else evParseTextarea();   // 从原始格式切回来时，重新解析用户手改的内容
  evRender();
}

// 序列化：写回隐藏 textarea
function evSyncTextarea() {
  var lines = mechEvents.map(function (e) {
    return [e.id, e.name || '', (e.aff_ge === '' || e.aff_ge === undefined) ? '' : e.aff_ge,
            (e.keywords || []).join(','), e.prompt || ''].join('|');
  });
  document.getElementById('nrEvents').value = lines.join('\n');
}

// 反序列化：从隐藏 textarea 读（兼容手改 + 旧卡）
function evParseTextarea() {
  var txt = document.getElementById('nrEvents').value || '';
  var out = [];
  txt.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 5) return;
    if (!p[0].trim()) return;
    var e = { id: p[0].trim(), name: p[1].trim(), prompt: p.slice(4).join('|').trim(),
              keywords: [], once: true, cooldown: 0 };
    var ag = p[2].trim();
    if (ag !== '') { var n = parseInt(ag, 10); if (!isNaN(n)) e.aff_ge = n; }
    else e.aff_ge = '';
    e.keywords = p[3].split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    out.push(e);
  });
  mechEvents = out;
}

// 从一行行文本装载（模板用）；同时刷新编辑器
function evLoadText(txt) {
  document.getElementById('nrEvents').value = txt || '';
  evParseTextarea();
  evRender();
}




// 记忆调试面板搬到了 web/js/screens/mem.js（DOM 在 web/screens/mem.html）。
// 这里只留兼容入口 memDebugDraw()（转调 MemScreen.draw），阶段 4/5 再清。


// 玩家看不到进度就会觉得事件坏了。这个面板纯读，不改任何状态。
var EV_STATE_LABEL = { fired: '[ic:check_circle] 已触发', cooling: '[ic:hourglass_empty] 冷却中', ready: '▶ 可触发', blocked: '[ic:lock] 未达成' };

function evOpenProgress(res) {
  var head = document.getElementById('evProgHead');
  var list = document.getElementById('evProgList');
  if (!res || !res.ok) {
    head.textContent = (res && res.err) || '读不到事件进度。';
    list.innerHTML = '';
    document.getElementById('evProgressModal').classList.add('open');
    return;
  }
  if (!res.total) {
    head.textContent = '还没有事件。在「[ic:tune] 机制卡」里加一个。';
    list.innerHTML = '';
    document.getElementById('evProgressModal').classList.add('open');
    return;
  }
  head.innerHTML = '共 <b>' + res.total + '</b> 个，已触发 <b>' + res.fired + '</b> 个'
    + (res.affection !== null && res.affection !== undefined
        ? '　当前好感 <b>' + res.affection + (res.aff_max ? ('/' + res.aff_max) : '') + '</b>' : '')
    + (res.turn ? '　已进行 ' + res.turn + ' 轮' : '');
  var h = '';
  (res.items || []).forEach(function (x) {
    var dim = (x.state === 'blocked' || x.state === 'cooling');
    h += '<div style="padding:7px 9px;border-radius:7px;margin-bottom:6px;border:1px solid var(--line);'
       + (dim ? 'opacity:.72;' : '') + '">'
       + '<div style="display:flex;justify-content:space-between;gap:8px">'
       +   '<b style="font-size:13px">' + evEsc(x.name) + '</b>'
       +   '<span style="font-size:11px;white-space:nowrap">'
       +     (EV_STATE_LABEL[x.state] || x.state) + '</span>'
       + '</div>'
       + '<div style="font-size:11px;color:var(--sub);margin-top:3px">' + evEsc(x.why || '') + '</div>'
       + '<div style="font-size:11px;color:var(--sub);margin-top:2px">'
       +   (x.aff_ge !== null && x.aff_ge !== undefined ? ('好感≥' + x.aff_ge + '　') : '')
       +   ((x.keywords && x.keywords.length) ? ('关键词：' + evEsc(x.keywords.join('/')))
                                              : '无关键词闸门')
       +   (x.times > 1 ? ('　已发生 ' + x.times + ' 次') : '')
       + '</div></div>';
  });
  list.innerHTML = h;
  document.getElementById('evProgressModal').classList.add('open');
}

// 编辑器里那一行摘要（不打开弹窗也能看到下一步是什么）
function evRenderProgress(res) {
  var bar = document.getElementById('evProgressText');
  if (!bar) return;
  if (!res || !res.ok || !res.total) {
    bar.textContent = (res && res.err) ? ('事件进度：' + res.err)
      : '事件进度：还没有事件。加一个就会在这里显示进度。';
    return;
  }
  var nxt = null;
  (res.items || []).forEach(function (x) {
    if (!nxt && x.state !== 'fired') nxt = x;
  });
  var txt = '事件进度 ' + res.fired + '/' + res.total
          + (res.affection !== null && res.affection !== undefined ? ('　好感 ' + res.affection) : '');
  if (nxt) txt += '　下一个：' + nxt.name + '（' + (nxt.why || '') + '）';
  bar.textContent = txt;
}

function evRefreshProgress() {
  if (!window.pywebview || !pywebview.api || !pywebview.api.event_progress) return;
  try {
    pywebview.api.event_progress().then(evRenderProgress).catch(function () {});
  } catch (e) { /* 没后端时静默 */ }
}

function evShowProgress() {
  if (!window.pywebview || !pywebview.api || !pywebview.api.event_progress) return;
  try {
    pywebview.api.event_progress().then(evOpenProgress).catch(function (e) {
      document.getElementById('evProgHead').textContent = '读事件进度出错：' + e;
      document.getElementById('evProgressModal').classList.add('open');
    });
  } catch (e) { /* 忽略 */ }
}

function evEsc(s) {
  return String(s === undefined || s === null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function evRender() {
  var box = document.getElementById('evEditor');
  if (!box) return;
  if (!mechEvents.length) {
    box.innerHTML = '<div style="font-size:11px;color:var(--sub);padding:6px 0">还没有事件。点下面「＋ 加一个事件」。</div>';
    evSyncTextarea();
    return;
  }
  var h = '';
  mechEvents.forEach(function (e, i) {
    h += '<div class="ev-card" style="border:1px solid var(--line);border-radius:8px;padding:8px;margin-bottom:8px">';
    h += '<div class="row" style="justify-content:space-between;margin-bottom:6px">'
       +   '<span style="font-size:11px;color:var(--sub)">事件 ' + (i + 1) + ' / ' + mechEvents.length + '</span>'
       +   '<span>'
       +     '<button class="btn2 ghost" style="width:auto;margin:0;padding:1px 7px" onclick="evMove(' + i + ',-1)" title="上移">↑</button> '
       +     '<button class="btn2 ghost" style="width:auto;margin:0;padding:1px 7px" onclick="evMove(' + i + ',1)" title="下移">↓</button> '
       +     '<button class="btn2 ghost" style="width:auto;margin:0;padding:1px 7px;color:var(--danger)" onclick="evDel(' + i + ')" title="删除">[ic:close]</button>'
       +   '</span>'
       + '</div>';
    h += '<div class="row" style="justify-content:flex-start;gap:6px;margin-bottom:6px">'
       +   '<input type="text" value="' + evEsc(e.name) + '" placeholder="事件名（如 告白）" '
       +     'oninput="evSet(' + i + ',\'name\',this.value)" style="flex:1;min-width:120px">'
       +   '<input type="text" value="' + evEsc(e.id) + '" placeholder="ID（结局要用）" '
       +     'oninput="evSet(' + i + ',\'id\',this.value)" style="width:110px">'
       + '</div>';
    h += '<div class="row" style="justify-content:flex-start;gap:6px;margin-bottom:6px">'
       +   '<span style="font-size:11px;color:var(--sub);line-height:30px">好感 ≥</span>'
       +   '<input type="number" min="0" max="99999" value="' + evEsc(e.aff_ge) + '" placeholder="留空=不限" '
       +     'oninput="evSet(' + i + ',\'aff_ge\',this.value===\'\'?\'\':(parseInt(this.value,10)||0))" style="width:90px">'
       +   '<input type="text" value="' + evEsc((e.keywords || []).join(',')) + '" placeholder="关键词（逗号分隔，可留空）" '
       +     'oninput="evSet(' + i + ',\'keywords\',this.value.split(\',\').map(function(x){return x.trim()}).filter(Boolean))" '
       +     'style="flex:1;min-width:140px">'
       + '</div>';
    h += '<div class="row" style="justify-content:flex-start;gap:10px;margin-bottom:6px">'
       +   '<label class="chkline" style="cursor:pointer;font-size:11px">'
       +     '<input type="checkbox" ' + (e.once === false ? 'checked' : '') + ' '
       +       'onchange="evSet(' + i + ',\'once\',!this.checked)"> 可重复触发</label>'
       +   '<span style="font-size:11px;color:var(--sub)">冷却（轮）</span>'
       +   '<input type="number" min="0" max="999" value="' + (e.cooldown || 0) + '" '
       +     'oninput="evSet(' + i + ',\'cooldown\',parseInt(this.value,10)||0)" style="width:70px">'
       +   '<span style="font-size:11px;color:var(--sub)">好感加成</span>'
       +   '<input type="number" min="-100" max="100" value="' + (e.aff !== undefined && e.aff !== '' ? e.aff : '') + '" '
       +     'placeholder="如 5" oninput="evSet(' + i + ',\'aff\',this.value===\'\'?\'\':(parseInt(this.value,10)||0))" style="width:70px">'
       + '</div>';
    h += '<textarea rows="2" placeholder="触发提示：事件发生时给 AI 的演出指令" '
       +   'oninput="evSet(' + i + ',\'prompt\',this.value)" style="width:100%">' + evEsc(e.prompt) + '</textarea>';
    h += '</div>';
  });
  box.innerHTML = h;
  evSyncTextarea();
}


function applyMechTemplate(t) {
  if (t === 'love') {
    document.getElementById('nrAffEnabled').checked = true;
    document.getElementById('nrAffInitial').value = 50;
    document.getElementById('nrAffMax').value = 100;
    document.getElementById('nrAffCrit').value = 0.001;
    document.getElementById('nrStFields').value = 'mood|心情|enum|平静|平静,开心,害羞,生气,委屈\nenergy|精力|int|100|0-100';
    evLoadText('confess|告白|80|告白,喜欢|她鼓起勇气向你告白，请演出这一重要时刻');
    setFold('foldMech', true); setFold('foldSt', true);
  } else if (t === 'battle') {
    document.getElementById('nrBattleEnabled').checked = true;
    document.getElementById('nrBattleAttrs').value = 'hp|生命|100|100\natk|攻击|10\ndef|防御|5';
    // 元素名是 nrBattleMechAttrs（不是 nrBattleMech）—— 写错会让整套「战斗冒险」
    // 模板在填机制属性时抛错，属性一栏永远是空的。
    document.getElementById('nrBattleMechAttrs').value = 'spd|速度|8|100\nmp|灵力|20|50';
    document.getElementById('nrBattleFormulas').value = 'damage=max(1, player_atk*2-def)\ncrit_chance=0.1\ncrit_mult=2';
    document.getElementById('nrBattleMoves').value = 'fire|火球术|player_atk*3-def|mp:5||投掷火球\nstrike|平砍|player_atk-def|\nheal|治愈|20||regen:2|恢复体力';
    document.getElementById('nrBattleBuffs').value = 'regen|再生|2|hp:5|每回合恢复5生命\npoison|中毒|3|hp:-5|每回合损失5生命';
    setFold('foldBattle', true);
  } else if (t === 'event') {
    evLoadText('meet|初遇|0|你好,初次见面|第一次相遇，自然演出\nstorm|风暴夜|30|暴风雨,打雷|暴风雨夜，她害怕地靠近你\nconfess|告白|80|告白,喜欢|她鼓起勇气向你告白');
    setFold('foldMech', true);
  } else if (t === 'clear') {
    document.getElementById('nrAffEnabled').checked = false;
    document.getElementById('nrStFields').value = '';
    evLoadText('');
    document.getElementById('nrBattleEnabled').checked = false;
    document.getElementById('nrBattleAttrs').value = '';
    document.getElementById('nrBattleMechAttrs').value = '';
    document.getElementById('nrBattleFormulas').value = '';
    document.getElementById('nrBattleMoves').value = '';
    document.getElementById('nrBattleBuffs').value = '';
  } else if (t === 'endings_love') {
    document.getElementById('nrEndings').value = 'good|告白成功|初见,约会,告白|90||她终于说出了那句喜欢\nbad|形同陌路|争吵,决裂|20||你们最终还是走散了\nhidden|雨夜告白|初见,雨夜,告白|1|藏|只有走完整条线才会亮起的结局……';
    setFold('foldEndings', true);
  } else if (t === 'endings_hidden') {
    document.getElementById('nrEndings').value = 'hidden|雨夜告白|初见,雨夜,告白|1|藏|只有走完整条线才会亮起…\nhidden|真相大白|秘密,线索,摊牌|1|藏|你终于问出了那句藏在心底很久的话。\nhidden|时间线|重来,循环,抉择|1|藏|这一次，你没有选择离开。\nhidden|幻梦|沉睡,迷梦,醒来|1|藏|你睁开眼，分不清刚才是不是一场梦。\nhidden|失控|占有,出格,失控|1|藏|她笑着看着你，眼里却没了光。';
    setFold('foldEndings', true);
  } else if (t === 'endings_clear') {
    document.getElementById('nrEndings').value = '';
  }
}

function collectMechanics() {
  var mech = {};
  if (document.getElementById('nrAffEnabled').checked) {
    var initial = parseInt(document.getElementById('nrAffInitial').value, 10);
    if (isNaN(initial)) initial = 50;
    var mx = parseInt(document.getElementById('nrAffMax').value, 10);
    if (isNaN(mx) || mx < 1) mx = 100;
    var crit = parseFloat(document.getElementById('nrAffCrit').value);
    if (isNaN(crit) || crit < 0) crit = 0.001;
    if (crit > 1) crit = 1;
    if (initial > mx) initial = mx;
    mech.affection = { enabled: true, initial: initial, min: 0, max: mx, crit: crit };
  }
  // 抽取概率（百分比）：天选=千分之一(0.1)，坍缩=十万分之一(0.001)
  var rollCrit = parseFloat(document.getElementById('nrRollCrit').value);
  var rollRare = parseFloat(document.getElementById('nrRollRare').value);
  var rollFail = parseFloat(document.getElementById('nrRollFail').value);
  var rollChosen = parseFloat(document.getElementById('nrRollChosen').value);
  var rollCollapse = parseFloat(document.getElementById('nrRollCollapse').value);
  if (!isNaN(rollCrit) || !isNaN(rollRare) || !isNaN(rollFail) || !isNaN(rollChosen) || !isNaN(rollCollapse)) {
    mech.roll = {
      crit: isNaN(rollCrit) ? 10 : Math.max(0, Math.min(100, rollCrit)),
      rare: isNaN(rollRare) ? 4 : Math.max(0, Math.min(100, rollRare)),
      fail: isNaN(rollFail) ? 2 : Math.max(0, Math.min(100, rollFail)),
      chosen: isNaN(rollChosen) ? 0.1 : Math.max(0, Math.min(100, rollChosen)),
      collapse: isNaN(rollCollapse) ? 0.001 : Math.max(0, Math.min(100, rollCollapse)),
    };
  }
  var stLines = [];
  document.getElementById('nrStFields').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 3) return;
    var key = p[0].trim(), name = p[1].trim();
    var type = p[2].trim() === 'int' ? 'int' : 'enum';
    var initial = p[3] ? p[3].trim() : (type === 'int' ? '0' : '');
    var extra = p[4] ? p[4].trim() : '';
    var f = { key: key, name: name || key, type: type };
    if (type === 'int') {
      var mm = extra.match(/^(\d+)\s*-\s*(\d+)$/);
      f.min = mm ? parseInt(mm[1], 10) : 0;
      f.max = mm ? parseInt(mm[2], 10) : 100;
      var iv = parseInt(initial, 10);
      f.initial = isNaN(iv) ? f.min : iv;
    } else {
      f.options = extra ? extra.split(',').map(function (x) { return x.trim(); }).filter(Boolean) : [];
      f.initial = initial || f.options[0] || '';
    }
    stLines.push(f);
  });
  if (stLines.length) mech.status = { enabled: true, fields: stLines };
  var evs = [];
  document.getElementById('nrEvents').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 5) return;
    var e = { id: p[0].trim(), name: p[1].trim(), prompt: p.slice(4).join('|').trim() };
    var ag = p[2].trim();
    if (ag !== '') { var n = parseInt(ag, 10); if (!isNaN(n)) e.aff_ge = n; }
    var kws = p[3].split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    if (kws.length) e.keywords = kws;
    // 只要求 id —— 原来还要求 prompt 非空，于是"只填了名字和好感"的事件
    // 会被静默丢掉（可视化编辑器里看着有，一存就没了）。提示留空时
    // 引擎有兜底演出语，所以不该在这里拦。
    if (!e.id) return;
    e.once = true;
    evs.push(e);
  });
  if (evs.length) mech.events = evs;
  // once/cooldown 不在管道格式里 —— 从编辑器数组按 id 合并回去，
  // 否则「可重复触发」勾了也存不进卡。
  if (mech.events && mech.events.length) {
    var byId = {};
    mechEvents.forEach(function (x) { byId[x.id] = x; });
    mech.events.forEach(function (e) {
      var src = byId[e.id];
      if (!src) return;
      e.once = (src.once === false) ? false : true;
      var cd = parseInt(src.cooldown, 10);
      e.cooldown = (isNaN(cd) || cd < 0) ? 0 : cd;
      var af = parseInt(src.aff, 10);
      if (!isNaN(af) && af !== 0) e.aff = af;
    });
  }
  // 管道格式放不下的属性（once/cooldown/aff）另存一份 sidecar，
  // 否则下一次回填就丢了。老卡没有这个字段，读的时候按默认值处理。
  if (mech.events && mech.events.length) {
    mech.ev_ext = {};
    mech.events.forEach(function (e) {
      var ext = {};
      if (e.once === false) ext.once = false;
      if (e.cooldown) ext.cooldown = e.cooldown;
      if (e.aff) ext.aff = e.aff;
      if (Object.keys(ext).length) mech.ev_ext[e.id] = ext;
    });
    if (!Object.keys(mech.ev_ext).length) delete mech.ev_ext;
  }
  var ends = [];
  document.getElementById('nrEndings').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 2) return;
    var e = { id: p[0].trim(), name: (p[1] || '').trim() || p[0].trim() };
    var w = {};
    var chain = (p[2] || '').trim();
    if (chain) w.events_chain = chain.split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    var ag = (p[3] || '').trim();
    if (ag !== '') { var n = parseInt(ag, 10); if (!isNaN(n)) w.aff_ge = n; }
    var hid = (p[4] || '').trim();
    if (['1', 'yes', 'hidden', '隐藏', '藏', 'true'].indexOf(hid) >= 0) e.hidden = true;
    if (Object.keys(w).length) e.when = w;
    var desc = p.slice(5).join('|').trim();
    if (desc) e.desc = desc;
    if (!e.id) return;
    ends.push(e);
  });
  if (ends.length) mech.endings = ends;
  return Object.keys(mech).length ? mech : null;
}

function collectBattle() {
  if (!document.getElementById('nrBattleEnabled').checked) return null;
  var battle = { enabled: true };
  var attrs = {};
  document.getElementById('nrBattleAttrs').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 2) return;
    var key = p[0].trim();
    if (!key) return;
    var entry = { label: p[1] ? p[1].trim() : key };
    var init = parseInt(p[2], 10);
    entry.initial = isNaN(init) ? 10 : init;
    if (p[3] !== undefined && p[3].trim() !== '') {
      var mx = parseInt(p[3], 10);
      entry.max = isNaN(mx) ? (key === 'hp' ? 100 : 999999) : mx;
    } else if (key === 'hp') {
      entry.max = 100;
    }
    attrs[key] = entry;
  });
  if (Object.keys(attrs).length) battle.attrs = attrs;
  var mechAttrs = [];
  document.getElementById('nrBattleMechAttrs').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 2) return;
    var key = p[0].trim();
    if (!key) return;
    var entry = { key: key, label: p[1] ? p[1].trim() : key };
    var init = parseInt(p[2], 10);
    entry.initial = isNaN(init) ? 10 : init;
    var mx = parseInt(p[3], 10);
    entry.max = isNaN(mx) ? 999999 : mx;
    mechAttrs.push(entry);
  });
  if (mechAttrs.length) battle.mech_attrs = mechAttrs;
  var formulas = {};
  document.getElementById('nrBattleFormulas').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var i = line.indexOf('=');
    if (i <= 0) return;
    var name = line.slice(0, i).trim();
    var expr = line.slice(i + 1).trim();
    if (name && expr) formulas[name] = expr;
  });
  if (Object.keys(formulas).length) battle.formulas = formulas;
  var moves = [];
  document.getElementById('nrBattleMoves').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 2) return;
    var id = p[0].trim();
    if (!id) return;
    var m = { id: id, name: p[1] ? p[1].trim() : id };
    if (p[2] && p[2].trim()) m.formula = p[2].trim();
    if (p[3] && p[3].trim()) {
      var cost = {};
      p[3].split(',').forEach(function (kv) {
        var sp = kv.split(':');
        if (sp.length === 2 && sp[0].trim() && !isNaN(parseInt(sp[1], 10))) cost[sp[0].trim()] = parseInt(sp[1], 10);
      });
      if (Object.keys(cost).length) m.cost = cost;
    }
    if (p[4] && p[4].trim()) {
      var bp = p[4].split(':');
      if (bp.length === 2 && bp[0].trim() && !isNaN(parseInt(bp[1], 10)))
        m.buffs = [{ id: bp[0].trim(), turns: parseInt(bp[1], 10) }];
    }
    if (p[5] && p[5].trim()) m.desc = p[5].trim();
    moves.push(m);
  });
  if (moves.length) battle.moves = moves;
  var buffs = [];
  document.getElementById('nrBattleBuffs').value.split('\n').forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var p = line.split('|');
    if (p.length < 2) return;
    var id = p[0].trim();
    if (!id) return;
    var b = { id: id, name: p[1] ? p[1].trim() : id };
    var turns = parseInt(p[2], 10);
    b.turns = isNaN(turns) ? 3 : turns;
    if (p[3] && p[3].trim()) {
      var at = {};
      p[3].split(',').forEach(function (kv) {
        var sp = kv.split(':');
        if (sp.length === 2 && sp[0].trim() && !isNaN(parseInt(sp[1], 10))) at[sp[0].trim()] = parseInt(sp[1], 10);
      });
      if (Object.keys(at).length) b.attrs = at;
    }
    if (p[4] && p[4].trim()) b.desc = p[4].trim();
    buffs.push(b);
  });
  if (buffs.length) battle.buffs = buffs;
  return battle;
}

function fillBattle(adv) {
  var battle = adv && adv.battle ? adv.battle : null;
  document.getElementById('nrBattleEnabled').checked = !!(battle && battle.enabled);
  if (!battle) {
    document.getElementById('nrBattleAttrs').value = 'hp|生命|100|100\natk|攻击|10\ndef|防御|5';
    document.getElementById('nrBattleMechAttrs').value = '';
    document.getElementById('nrBattleFormulas').value = 'damage=max(1, player_atk*2-def)\ncrit_chance=0.1\ncrit_mult=2';
    document.getElementById('nrBattleMoves').value = '';
    document.getElementById('nrBattleBuffs').value = '';
    return;
  }
  var attrs = battle.attrs || {};
  document.getElementById('nrBattleAttrs').value = Object.keys(attrs).map(function (k) {
    var a = attrs[k];
    return [k, a.label || k, a.initial, a.max !== undefined ? a.max : ''].join('|');
  }).join('\n');
  document.getElementById('nrBattleMechAttrs').value = (battle.mech_attrs || []).map(function (a) {
    return [a.key, a.label || a.key, a.initial, a.max !== undefined ? a.max : ''].join('|');
  }).join('\n');
  document.getElementById('nrBattleFormulas').value = Object.keys(battle.formulas || {}).map(function (k) {
    return k + '=' + battle.formulas[k];
  }).join('\n');
  document.getElementById('nrBattleMoves').value = (battle.moves || []).map(function (m) {
    var cost = m.cost ? Object.keys(m.cost).map(function (k) { return k + ':' + m.cost[k]; }).join(',') : '';
    var bf = m.buffs && m.buffs[0] ? (m.buffs[0].id + ':' + m.buffs[0].turns) : '';
    return [m.id, m.name || m.id, m.formula || '', cost, bf, m.desc || ''].join('|');
  }).join('\n');
  document.getElementById('nrBattleBuffs').value = (battle.buffs || []).map(function (b) {
    var at = b.attrs ? Object.keys(b.attrs).map(function (k) { return k + ':' + b.attrs[k]; }).join(',') : '';
    return [b.id, b.name || b.id, b.turns, at, b.desc || ''].join('|');
  }).join('\n');
}

function fillRoleFields(f) {
  f = f || {};
  document.getElementById('nrLegacyInput').value = f.legacy || '';
  document.getElementById('nrAppearanceInput').value = f.appearance || '';
  document.getElementById('nrPersonalityInput').value = f.personality || '';
  document.getElementById('nrBackgroundInput').value = f.background || '';
  document.getElementById('nrSpeechInput').value = f.speech || '';
  document.getElementById('nrFirstMesInput').value = f.first_mes || '';
  document.getElementById('nrMesExampleInput').value = f.mes_example || '';
  document.getElementById('nrNotesInput').value = f.notes || '';
  document.getElementById('nrUnlockInput').checked = !!f.unlocked;
  // 高级设置（开发者模式）
  var adv = f.advanced || null;
  var advBox = document.getElementById('nrAdv');
  if (advBox) advBox.style.display = window.devMode ? '' : 'none';
  var game = adv && adv.game ? adv.game : {};
  document.getElementById('nrGameNameInput').value = (game.name || '');
  document.getElementById('nrGameRulesInput').value = (game.rules || '');
  document.getElementById('nrGameStateInput').value = (game.state || '');
  document.getElementById('nrExtraPromptInput').value = (adv && adv.extra_prompt) || '';
  document.getElementById('nrCardFaceInput').value = (adv && adv.card_face) || '';
  document.getElementById('nrDevNotesInput').value = (adv && adv.dev_notes) || '';
  var qrLines = (adv && adv.card_quick_replies || []).map(function (q) {
    return (q.label || '') + '|' + (q.text || '');
  }).join('\n');
  document.getElementById('nrCardQrInput').value = qrLines;
  var rrLines = (adv && adv.regex_rules || []).map(function (x) {
    return [x.id, x.name || x.id, x.pattern, x.replace, x.scope || 'both'].join('|');
  }).join('\n');
  document.getElementById('nrRegexInput').value = rrLines;
  // 机制卡回填
  var mech = adv && adv.mechanics ? adv.mechanics : null;
  var aff = mech && mech.affection;
  document.getElementById('nrAffEnabled').checked = !!aff;
  document.getElementById('nrAffInitial').value = aff && aff.initial !== undefined ? aff.initial : 50;
  document.getElementById('nrAffMax').value = aff && aff.max !== undefined ? aff.max : 100;
  document.getElementById('nrAffCrit').value = aff && aff.crit !== undefined ? aff.crit : 0.001;
  var roll = mech && mech.roll ? mech.roll : {};
  document.getElementById('nrRollCrit').value = roll.crit !== undefined ? roll.crit : 10;
  document.getElementById('nrRollRare').value = roll.rare !== undefined ? roll.rare : 4;
  document.getElementById('nrRollFail').value = roll.fail !== undefined ? roll.fail : 2;
  document.getElementById('nrRollChosen').value = roll.chosen !== undefined ? roll.chosen : 0.1;
  document.getElementById('nrRollCollapse').value = roll.collapse !== undefined ? roll.collapse : 0.001;
  var stLines = (mech && mech.status && mech.status.fields || []).map(function (f) {
    var extra = f.type === 'int' ? (f.min + '-' + f.max) : ((f.options || []).join(','));
    return [f.key, f.name || f.key, f.type, f.initial, extra].join('|');
  }).join('\n');
  document.getElementById('nrStFields').value = stLines;
  var evLines = (mech && mech.events || []).map(function (e) {
    return [e.id, e.name || '', e.aff_ge !== undefined && e.aff_ge !== null ? e.aff_ge : '',
            (e.keywords || []).join(','), e.prompt || ''].join('|');
  }).join('\n');
  // 回填走可视化编辑器：先落文本，再解析成数组，再渲染
  evLoadText(evLines);
  // once/cooldown/aff 不在管道格式里，回填时单独接上（否则读旧卡会丢这几个字段）
  var ext = (mech && mech.ev_ext) || {};
  (mech && mech.events || []).forEach(function (e, i) {
    if (!mechEvents[i]) return;
    var x = ext[e.id] || {};
    mechEvents[i].once = (x.once === false || e.once === false) ? false : true;
    mechEvents[i].cooldown = parseInt(x.cooldown !== undefined ? x.cooldown : e.cooldown, 10) || 0;
    var af = parseInt(x.aff !== undefined ? x.aff : e.aff, 10);
    mechEvents[i].aff = isNaN(af) ? '' : af;
  });
  evRender();
  var endLines = (mech && mech.endings || []).map(function (e) {
    var w = e.when || {};
    var chain = (w.events_chain || []).join(',');
    var ag = w.aff_ge !== undefined ? w.aff_ge : '';
    return [e.id, e.name || '', chain, ag, e.hidden ? '藏' : '', e.desc || ''].join('|');
  }).join('\n');
  document.getElementById('nrEndings').value = endLines;
  // 战斗系统回填
  fillBattle(adv);
  // 折叠区按内容自动展开（恋爱卡默认全收起）
  var mech2 = adv && adv.mechanics;
  setFold('foldMech', !!(mech2 && (mech2.affection || (mech2.events && mech2.events.length))));
  setFold('foldSt', !!(mech2 && mech2.status && mech2.status.fields && mech2.status.fields.length));
  setFold('foldBattle', !!(adv && adv.battle && adv.battle.enabled));
  setFold('foldEndings', !!(mech2 && mech2.endings && mech2.endings.length));
  // 进度摘要：换角色/载入卡之后立刻反映当前状态
  evRefreshProgress();
}

// 世界参数（8 格网格）的渲染/收集搬到了 web/js/screens/wm.js。
// 从 e.target 向上找带指定 data-* 属性的元素（按钮内是 SVG 图标时 e.target 落在 path/svg 上）
function hitAttr(e, names) {
  var t = e.target;
  while (t && t !== e.currentTarget && t.getAttribute) {
    for (var i = 0; i < names.length; i++) {
      var v = t.getAttribute(names[i]);
      if (v !== null && v !== '') return v;
    }
    t = t.parentNode;
  }
  return null;
}
document.getElementById('roleList').addEventListener('click', function (e) {
  var en = hitAttr(e, ['data-edit']);
  if (en) {
    editingRole = en;
    pywebview.api.get_role(en).then(function (role) {
      document.getElementById('nrNameInput').value = en;
      document.getElementById('nrNameInput').disabled = true;
      var flds = role ? role.fields : {};
      flds.unlocked = role ? !!role.unlocked : false;
      fillRoleFields(flds);
      if (role && role.legacy) document.getElementById('nrLegacyInput').value = role.legacy;
      document.getElementById('nrTitle').textContent = '编辑角色：' + en;
      document.getElementById('roleModal').classList.add('open');
    });
    return;
  }
  var sv = hitAttr(e, ['data-saves']);
  if (sv) {
    openSaves(sv);
    return;
  }
  var n = hitAttr(e, ['data-avatar']);
  if (n) {
    document.getElementById('fileInput').setAttribute('data-avatar-target', n);
    document.getElementById('fileInput').click();
    return;
  }
  var ul = hitAttr(e, ['data-unlock']);
  if (ul) {
    pywebview.api.toggle_unlock(ul).then(function () { reloadRoles(); });
    return;
  }
  var xj = hitAttr(e, ['data-xjson']);
  if (xj) {
    pywebview.api.export_card(xj, 'json').then(function (r) {
      if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
    });
    return;
  }
  var xp = hitAttr(e, ['data-xpng']);
  if (xp) {
    pywebview.api.export_card(xp, 'png').then(function (r) {
      if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
    });
    return;
  }
  var d = hitAttr(e, ['data-del']);
  if (d && confirm('删除角色 ' + d + '？')) {
    pywebview.api.delete_role(d).then(function () { reloadRoles(); });
  }
});



document.getElementById('fileInput').addEventListener('change', function () {
  var target = this.getAttribute('data-avatar-target');
  if (target && this.files[0]) {
    var f = this.files[0];
    var reader = new FileReader();
    reader.onload = function () {
      var ext = (f.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
      // 打开裁剪模态，确认后上传
      cropOpen(target, reader.result, ext);
    };
    reader.readAsDataURL(f);
    this.removeAttribute('data-avatar-target');
  } else if (this.getAttribute('data-avatar-target')) {
    this.removeAttribute('data-avatar-target');
  }
});
function reloadRoles() {
  pywebview.api.state().then(function (s) {
    if (s) renderRoles(s.roles || [], s.selected_roles || [], s.role_unlocked || {});
  });
}

// 多存档："正在看哪个角色的存档"不再是顶层 var，改存 DICK.state['save.current']
// （兼容入口 window.saveModalCur 在 web/js/screens/save.js 里注册）。
// 多存档屏的渲染与动作搬到了 web/js/screens/save.js（DOM 在 web/screens/save.html）。
// 多存档屏的按钮/列表绑定也在 web/js/screens/save.js（阶段3）。
// 角色列表点「存档」仍然叫兼容入口 openSaves(name)。
