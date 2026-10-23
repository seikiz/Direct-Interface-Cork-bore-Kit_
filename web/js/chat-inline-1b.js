/* 从 index.html 内联脚本拆出（第 1b 段，紧接第 1 段） */
// ---- 首次启<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌动引导框 ----
var onboardStep = 0;
var ONB_TOTAL = 5;
function showOnboard(startStep) {
  document.getElementById('onboard').style.display = 'block';
  onboardStep = typeof startStep === 'number' ? Math.min(Math.max(startStep,0), ONB_TOTAL-1) : 0;
  renderOnboard();
}
function renderOnboard() {
  document.querySelectorAll('.onb-step').forEach(function (el, i) {
    el.classList.toggle('on', i === onboardStep);
  });
  document.getElementById('onbPrev').style.display = onboardStep > 0 ? '' : 'none';
  document.getElementById('onbNext').textContent = onboardStep >= ONB_TOTAL - 1 ? '开始使用 [ic:rocket_launch]' : '下一步';
  // 配置模型一步：显示当前是否有 Key 的实时状态，引导用户行动
  if (onboardStep === 1) {
    var has = window._hasKey;
    var el = document.getElementById('onbKeyStatus');
    if (el) el.textContent = has ? '[ic:check_circle] 已配置' : '[ic:warning] 尚未配置 —— 这是开始聊天前的第一步';
  }
}
function dismissOnboard() {
  document.getElementById('onboard').style.display = 'none';
  try { pywebview.api.dismiss_welcome().then(function () {}); } catch (e) {}
}
document.getElementById('onbNext').onclick = function () {
  if (onboardStep >= ONB_TOTAL - 1) { dismissOnboard(); return; }
  onboardStep++;
  renderOnboard();
};
document.getElementById('onbPrev').onclick = function () {
  if (onboardStep > 0) { onboardStep--; renderOnboard(); }
};
document.getElementById('onbSkip').onclick = dismissOnboard;

// 回档成就横幅：灰白 MC progress 风，边缘滑入后自动滑出
var _achTimer = null;
function showAchToast(icon, title, desc) {
  var t = document.getElementById('achToast');
  if (!t) return;
  document.getElementById('achToastIc').textContent = icon || '▣';
  document.getElementById('achToastTxt').innerHTML = '<b>' + (title || '已回到这段故事') + '</b><span>' + (desc || '回档') + '</span>';
  t.classList.add('show');
  if (_achTimer) clearTimeout(_achTimer);
  _achTimer = setTimeout(function () { t.classList.remove('show'); }, 2600);
}

// steps: [{ id, title, html, open?, select? }]. id=要高亮的元素id；open=引导前要打开的模态；
// select=点击该元素（选模型商/模型）时触发的函数名（用于展开下拉）。上一步可回溯。
var SG = null;
function startKeyGuide() {
  // KEY 配置箭头引导：自动打开设置，逐步指向 模型商/API Key/模型/保存
  SG = {
    idx: 0,
    steps: [
      { id: 'stProviderBtn', open: 'settingsModal', title: '第 1 步 · 选模型商',
        html: '先选你用哪家模型。这里是「[ic:settings] 设置 → 模型商」。<br>建议：<b>DeepSeek 官方</b>（质量最稳）或 <b>OVH 免费链</b>（免填 Key 练手）。' },
      { id: 'stBuyBtn', title: '第 2 步 · 去领 Key',
        html: '点「<b>[ic:key] 去官网注册 / 充值</b>」会打开模型商官网。<br>注册后到官网控制台创建 <b>API Key</b>（sk-… 开头）复制下来。' },
      { id: 'stKeyInput', title: '第 3 步 · 粘贴 API Key',
        html: '把刚复制的 <b>API Key</b> 粘到这里（就是 sk-… 那一长串）。<br>选免费链/本地模型可留空。Base URL 选商后会自动填好。' },
      { id: 'stModelInput', select: 'stModelBtn', title: '第 4 步 · 选模型',
        html: '选一个具体<b>模型</b>（每家提供的列表不同）。点这里展开，或直接输入模型 ID。' },
      { id: 'stSave', title: '第 5 步 · 保存',
        html: '一切填好，点「<b>保存设置</b>」。<br>保存后就能去左侧勾选角色卡开始聊天了。' },
    ],
  };
  SG.steps[0].open = 'settingsModal';
  runGuideStep();
  dismissOnboard();  // 关掉旧文字浮窗，避免重叠
}

function runGuideStep() {
  var st = SG.steps[SG.idx];
  // 先打开需要的模态（设置），并确保元素可见
  if (st.open) {
    var m = document.getElementById(st.open);
    if (m && !m.classList.contains('open')) m.classList.add('open');
  }
  var el = document.getElementById(st.id);
  var sgH = document.getElementById('sgHighlight');
  var sgB = document.getElementById('sgBubble');
  var sgM = document.getElementById('sgMask');
  if (!el) { nextGuideStep(); return; }  // 元素不存在则跳过
  // 若该步需要点击某个下拉选择器
  if (st.select) {
    try { document.getElementById(st.select).click(); } catch (e) {}
  }
  // 让目标元素滚动到可视区（设置模态内部可能滚动），滚动结束后再定位气泡
  try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) {}
  setTimeout(function () { repositionGuide(el, sgH, sgB); }, 60);
  sgM.style.display = 'block';
  sgH.style.display = 'block';
  sgB.style.display = 'block';
  document.getElementById('sgPrev').style.display = SG.idx > 0 ? '' : 'none';
  document.getElementById('sgNext').textContent = SG.idx >= SG.steps.length - 1 ? '完成 [ic:check_circle]' : '下一步 →';
  document.getElementById('sgStep').textContent = st.title || '';
  document.getElementById('sgBody').innerHTML = st.html || '';
  repositionGuide(el, sgH, sgB);
}

function repositionGuide(el, sgH, sgB) {
  var r = el.getBoundingClientRect();
  var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  sgH.style.left = (r.left - 6) + 'px';
  sgH.style.top = (r.top - 6) + 'px';
  sgH.style.width = (r.width + 12) + 'px';
  sgH.style.height = (r.height + 12) + 'px';
  // 气泡放在目标下方或上方（取决于空间）；箭头朝目标
  var bw = 300, bh = 120;
  var vw = window.innerWidth, vh = window.innerHeight;
  var bx = Math.max(10, Math.min(cx - bw / 2, vw - bw - 10));
  var by, arrowSide = 'top';
  if (r.bottom + bh + 16 < vh) { by = r.bottom + 16; }
  else { by = Math.max(10, r.top - bh - 16); arrowSide = 'bottom'; }
  sgB.style.left = bx + 'px';
  sgB.style.top = by + 'px';
  var ar = sgB.querySelector('.sg-arrow') || document.createElement('div');
  if (!ar.parentNode) { ar.className = 'sg-arrow'; sgB.appendChild(ar); }
  ar.style.border = '9px solid transparent';
  if (arrowSide === 'top') {
    ar.style.borderBottomColor = 'var(--accent)';
    ar.style.top = '-18px'; ar.style.left = Math.max(0, Math.min(cx - bx - 9, bw - 18)) + 'px';
  } else {
    ar.style.borderTopColor = 'var(--accent)';
    ar.style.bottom = '-18px'; ar.style.left = Math.max(0, Math.min(cx - bx - 9, bw - 18)) + 'px';
  }
}

function nextGuideStep() {
  SG.idx++;
  if (SG.idx >= SG.steps.length) { endGuide(); return; }
  runGuideStep();
}
function prevGuideStep() {
  if (SG.idx > 0) { SG.idx--; runGuideStep(); }
}
function endGuide() {
  var sgM = document.getElementById('sgMask'), sgH = document.getElementById('sgHighlight'), sgB = document.getElementById('sgBubble');
  sgM.style.display = 'none'; sgH.style.display = 'none'; sgB.style.display = 'none';
  SG = null;
}
document.getElementById('sgNext').onclick = nextGuideStep;
document.getElementById('sgPrev').onclick = prevGuideStep;
document.getElementById('sgSkip').onclick = endGuide;
// 首启"配置模型"步的箭头引导按钮
var _onbKeyGuideBtn = document.getElementById('onbKeyGuide');
if (_onbKeyGuideBtn) _onbKeyGuideBtn.onclick = function () { startKeyGuide(); };
// 设置面板里的"配置教程"按钮（老用户 / 已过首启也能随时重看）
var _stKeyGuideBtn = document.getElementById('stKeyGuideBtn');
if (_stKeyGuideBtn) _stKeyGuideBtn.onclick = function () { startKeyGuide(); };
// 窗口缩放时重定位当前高亮
window.addEventListener('resize', function () {
  if (!SG) return;
  var el = document.getElementById(SG.steps[SG.idx].id);
  if (el) repositionGuide(el, document.getElementById('sgHighlight'), document.getElementById('sgBubble'));
});

function loadState() {
  pywebview.api.state().then(function (s) {
    if (!s) return;
    // 版号从后端来（唯一真相 = version.json）：欢迎页显示一行，控制台补一行
    try {
      var vEl = document.getElementById('onbVersion');
      if (vEl && s.version) vEl.textContent = s.version_full || ('DICK ' + s.version);
      if (s.version && window.__dickVerLogged !== s.version) {
        window.__dickVerLogged = s.version;
        console.log("%c" + (s.version_full || ("DICK " + s.version)),
          "color:var(--warn);font-weight:bold");
      }
    } catch (e) {}
    try {
    loadStateFill(s);
    } catch (e) {}
  });
}
function loadStateFill(s) {
  if (!s) return;
    lang = s.lang;
    themeIdx = s.theme || 0;
    accentIdx = s.accent || 0;
    setT(lang);
    applyTheme();
    loadChatWallpaper();
    try { if (typeof renderL2DSettings === 'function') renderL2DSettings(s.l2d); } catch (e) {}
    // 跑团状态条归 trpg 屏自己画：外壳只发一条「跑团状态变了」，不问谁来画（阶段3）
    try { DICK.bus.emit('trpg:state', s.trpg); } catch (e) {}
    lastSeq = (s.messages || []).length ? s.messages[s.messages.length - 1].seq : 0;
    lastEpoch = s.epoch || 0;
    (s.messages || []).forEach(appendMessage);
    renderRoles(s.roles || [], s.selected_roles || [], s.role_unlocked || {});
    renderWorlds(s.worlds || [], s.selected_worlds || [], s.current_world || '');
    renderPresets(s.presets || [], s.preset || '');
    PROVIDERS = s.providers || [];
    apiKeysMap = s.api_keys || {};
    currentProviderId = s.provider || 'deepseek';
    renderProviderSel(currentProviderId);
    document.getElementById('stModelInput').value = s.model || 'deepseek-flash';
    // 生图配置回填
    document.getElementById('stImgKey').value = s.image_gen_key ? '••••••••' : '';
    document.getElementById('stImgBase').value = s.image_gen_base_url || 'https://api.siliconflow.cn/v1';
    document.getElementById('stImgModel').value = s.image_gen_model || 'black-forest-labs/FLUX.1-schnell';
    var stImgBe = document.getElementById('stImgBackend');
    if (stImgBe) stImgBe.value = s.image_gen_backend || 'auto';
    applyGenLast(s.image_gen_last);
    fillProvider(currentProviderId, true);
    // 首启向导（2026-11）：**没配到可用 Key、且当前不是免 Key 厂商** → 自动弹 3 步向导。
    // 「稍后再说」会切到免费链（免 Key 厂商不需要 Key，所以那种情况不打扰）；
    // 配通一次之后 localStorage 记 done，别每次启动都弹。
    try {
      var _p = providerById(currentProviderId);
      if (!s.has_key && !(_p && _p.free)) apiWizardAutoOpen();
    } catch (e) { console.warn('[api] 向导没能弹出：', e); }
    document.getElementById('stBaseInput').value = s.base_url || document.getElementById('stBaseInput').value;
    document.getElementById('stProxyInput').value = s.proxy || '';
    document.getElementById('stRelayInput').value = s.relay_url || '';
    var rs = document.getElementById('relayStatus');
    // 2026-12 文案清理：说明"备用线路"就够了，不再向用户解释中转/直连的实现（用户原话：
    // 「去掉应用内所有技术说明部分」）。
    if (rs) rs.textContent = s.relay_on ? '● 备用线路已启用' : '○ 直连优先';
    document.getElementById('stStopInput').value = (s.stop_input || []).join(', ');
    var ss = document.getElementById('stopStatus');
    if (ss) ss.textContent = '当前生效：' + ((s.stop_sequences || []).join(' | ') || '（默认）');
    // 正则规则预填（全局）
    try {
      pywebview.api.get_regex_rules().then(function (r) {
        var box = document.getElementById('stRegexInput');
        if (box && r && r.rules) {
          box.value = (r.rules || []).map(function (x) {
            return [x.id, x.name || x.id, x.pattern, x.replace, x.scope || 'both'].join('|');
          }).join('\n');
        }
      }).catch(function () {});
    } catch (e) {}
    document.getElementById('stTempInput').value = s.temperature === undefined || s.temperature === null ? '' : s.temperature;
    document.getElementById('stTopPInput').value = s.top_p === undefined || s.top_p === null ? '' : s.top_p;
    window.ollamaOnline = !!s.ollama_online;
    document.getElementById('stKeyInput').value = s.has_key ? '••••••••' : '';
    currentBudget = s.budget || 0;
    renderBudget();
    document.getElementById('stAutoInput').checked = !!s.auto_turn;
    window.devMode = !!s.dev_mode;
    document.getElementById('stDevModeInput').checked = window.devMode;
    document.getElementById('stHumanizeInput').checked = !!s.humanize;
    document.getElementById('stStyleGuardInput').checked = s.style_guard !== false;
    document.getElementById('stStyleGuardLongInput').checked = s.style_guard_long === true;
    if (!s.welcome_shown) {
      window._hasKey = !!s.has_key;
      showOnboard(s.has_key ? 0 : 1);
      // 首启且未配 Key：自动触发箭头引导，把新手直接带上配置之路（可跳过）
      if (!s.has_key) {
        setTimeout(function () {
          try { startKeyGuide(); } catch (e) {}
        }, 400);
      }
    }
    applyFont(s.font || 1);
    currentSpeaker = (s.selected_roles || []).length === 1 ? s.selected_roles[0] : 'AI';
    renderPlugins(s.plugins || []);
    renderQuickReplies();
    if (typeof L2D !== 'undefined' && L2D.syncFromState) { try { L2D.syncFromState(s); } catch (e) {} }
    setStreaming(s.streaming, s.opening_loading);
    renderChoices(s.choices);
    renderMechanism(s.mechanism);
    renderBattle(s.battle);
    // 离线推进：启动后问一次"你不在的时候世界走了多少"（只出方案，点了才应用）
    setTimeout(function () { try { offlineCheck(); } catch (e) {} }, 900);
    // 系统权限：双击 .codex 文件启动 → 自动打开 CODEX 播放器
    if (s.codex_auto_open && !window.__codexAutoPlayed) {
      window.__codexAutoPlayed = true;
      codexCur = s.codex_auto_open;
      try { pywebview.api.codex_clear_auto_open().then(function () {}); } catch (e) {}
      setTimeout(function () { codexPlay(); }, 300);
    }
    document.getElementById('send').disabled = !!s.busy;
    // 图标替换交给 iconifyWatch 的 DOM 监听（#chat 的流式输出不会触发整树扫描，
    // 否则每次轮询都全量走一遍 DOM）。只有不支持 MutationObserver 时才退化为全量扫。
    if (typeof MutationObserver !== 'function') iconifyUI();
}

function renderRoles(roles, selected, unlockedMap) {
  var box = document.getElementById('roleList');
  box.innerHTML = '';
  roles.forEach(function (n) {
    var sel = selected.indexOf(n) >= 0 ? 'checked' : '';
    var unl = unlockedMap && unlockedMap[n];
    // 角色卡：第一行名字 + 第二行功能按钮，固定间距
    var card = document.createElement('div');
    card.className = 'role-card';
    var nm = escapeHtml(n);
    card.innerHTML =
      '<div class="rc-name">' +
        '<input type="checkbox" ' + sel + ' data-role="' + nm + '" style="flex:none">' +
        avatarHtml(n, 'role') +
        '<label for="">' + nm + '</label>' +
        (unl ? '<span class="rc-unlock" title="破甲已开启">[ic:local_fire_department]</span>' : '') +
      '</div>' +
      '<div class="rc-actions">' +
        '<button class="iconbtn" title="解锁/破甲" data-unlock="' + nm + '" style="' + (unl ? 'color:var(--danger)' : '') + '">' + (unl ? '[ic:local_fire_department] 破甲' : '[ic:local_fire_department]') + '</button>' +
        '<button class="iconbtn" title="存档点" data-saves="' + nm + '">[ic:save] 档</button>' +
        '<button class="iconbtn" title="编辑" data-edit="' + nm + '">[ic:edit] 编辑</button>' +
        '<button class="iconbtn" title="头像" data-avatar="' + nm + '">[ic:person] 头像</button>' +
        '<button class="iconbtn" title="导出 JSON" data-xjson="' + nm + '">[ic:download] JSON</button>' +
        '<button class="iconbtn" title="导出 PNG" data-xpng="' + nm + '">[ic:image] PNG</button>' +
        '<button class="iconbtn act-del" title="删除" data-del="' + nm + '">[ic:delete]</button>' +
      '</div>';
    box.appendChild(card);
  });
}

function renderWorlds(worlds, selected, current) {
  var box = document.getElementById('worldList');
  box.innerHTML = '';
  worlds.forEach(function (n) {
    var row = document.createElement('div');
    row.className = 'role-row';
    var sel = selected.indexOf(n) >= 0 ? 'checked' : '';
    var mark = (current === n) ? ' <span style="color:var(--accent)" title="current">★</span>' : '';
    row.innerHTML = '<label><input type="checkbox" ' + sel + ' data-world="' + escapeHtml(n) + '"> ' + escapeHtml(n) + mark + '</label>' +
      '<button class="iconbtn" title="travel" data-travel="' + escapeHtml(n) + '">[ic:rocket_launch]</button>' +
      '<button class="iconbtn" title="edit" data-wedit="' + escapeHtml(n) + '">[ic:edit]</button>' +
      '<button class="iconbtn" title="delete" data-wdel="' + escapeHtml(n) + '">[ic:delete]</button>';
    box.appendChild(row);
  });
}

function selectedRoles() {
  return Array.prototype.slice.call(document.querySelectorAll('input[data-role]:checked')).map(function (i) { return i.getAttribute('data-role'); });
}
function selectedWorlds() {
  return Array.prototype.slice.call(document.querySelectorAll('input[data-world]:checked')).map(function (i) { return i.getAttribute('data-world'); });
}

// 当前是不是浅色（显式选浅色 → 是；跟随系统 → 问系统）
function isLightNow() {
  var t = THEMES[themeIdx] || 'dark';
  if (t === 'light') return true;
  if (t === 'auto') {
    try { return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches); } catch (e) { return false; }
  }
  return false;
}
function applyTheme() {
  document.body.className = THEMES[themeIdx] || 'dark';
  // 强调色写在 body 的内联样式上：内联优先于 body.light/.oled 那几条规则，也优先于 :root 的默认值，
  // 所以「换主题」和「换强调色」两个设置不会互相盖掉。--accent-text 一起换，
  // 否则浅色主题下白字压深蓝、或深字压亮蓝，会有一半不达标。
  var light = isLightNow();
  var a = ACCENTS[accentIdx] || ACCENTS[0];
  document.body.style.setProperty('--accent', light ? a.light : a.dark);
  document.body.style.setProperty('--accent-text', light ? '#ffffff' : '#0b1220');
  document.getElementById('stThemeBtn').textContent = T.theme + '：' + (THEMES[themeIdx] === 'dark' ? '深色' : (THEMES[themeIdx] === 'light' ? '浅色' : (THEMES[themeIdx] === 'auto' ? '跟随系统' : 'OLED')));
  document.getElementById('stAccentBtn').textContent = T.accent + (['蓝','绿','紫','粉'][accentIdx]);
}

// 跟随系统时，系统在浅/暗之间切换要跟着变（否则得手动再点一次主题）
try {
  if (window.matchMedia) {
    var _mql = window.matchMedia('(prefers-color-scheme: light)');
    var _onScheme = function () { if (THEMES[themeIdx] === 'auto') applyTheme(); };
    if (_mql.addEventListener) _mql.addEventListener('change', _onScheme);
    else if (_mql.addListener) _mql.addListener(_onScheme);
  }
} catch (e) {}

function applyChatWallpaper(dataUrl) {
  var chat = document.getElementById('chat');
  if (!chat) return;
  if (dataUrl && String(dataUrl).indexOf('data:') === 0) {
    chat.style.setProperty('--chat-wallpaper', 'url("' + dataUrl + '")');
    chat.classList.add('has-wallpaper');
  } else {
    chat.style.removeProperty('--chat-wallpaper');
    chat.classList.remove('has-wallpaper');
  }
  // 设置面板状态
  var st = document.getElementById('stWallpaperState');
  if (st) st.textContent = dataUrl && String(dataUrl).indexOf('data:') === 0 ? '已设置' : '未设置（默认主题背景）';
}
function loadChatWallpaper() {
  try {
    pywebview.api.get_chat_wallpaper().then(function (r) {
      if (r && r.ok) applyChatWallpaper(r.data || '');
    }).catch(function () {});
  } catch (e) {}
}

// 跑团状态条搬到了 web/js/screens/trpg.js（DOM 在 web/screens/trpg.html）。
// 这里只留兼容入口 renderTrpgBar()（转调 TrpgScreen.render），阶段 4/5 再清。

function updatePresetName() {
  var nm = window.currentPreset || '默认';
  document.getElementById('presetBtn').textContent = T.preset + nm + ' ▾';
}

function renderPresets(presets, current) {
  window.currentPreset = current || '默认';
  updatePresetName();
  var items = (presets || []).map(function (p) {
    return { value: p, label: p, sel: p === (current || '默认') };
  });
  window.__presetItems = items;
}

function send() {
  var text = document.getElementById('input').value.trim();
  var hasImg = !!pendingImage;
  if (!text && !hasImg) return;
  // 零宽字符防线：发出去之前先清干净，别让它白烧 token
  if (text) {
    var nz = invisibleCount(text);
    if (nz) {
      var wasBomb = nz > 24;
      text = stripInvisible(text);
      try { document.getElementById('input').value = text; } catch (e) {}
      if (wasBomb) {
        galToast('[ic:warning] 已剔除 ' + nz + ' 个零宽字符（看不见却会白烧 token、卡界面）');
      }
    }
  }
  var imgB64 = hasImg ? pendingImage.b64 : null;
  var imgMime = hasImg ? pendingImage.mime : null;
  if (text) lastUserText = text;
  pywebview.api.send(text, imgB64, imgMime).then(function (r) {
    if (r && r.ok) {
      document.getElementById('input').value = '';
      clearImage();
      closeQuick();
    }
  });
}

function clearImage() {
  pendingImage = null;
  document.getElementById('imgprev').style.display = 'none';
}

function closeQuick() {
  document.getElementById('quickpanel').classList.remove('open');
  document.getElementById('plusBtn').textContent = '[ic:add]';
}

// ---------- 事件 ----------
document.getElementById('sideToggle').onclick = function () {
  document.getElementById('sidebar').classList.add('collapsed');
};
document.getElementById('sideOpen').onclick = function () {
  document.getElementById('sidebar').classList.remove('collapsed');
};
document.getElementById('cardsHead').onclick = function () {
  var open = !this.classList.contains('open');
  this.classList.toggle('open', open);
  document.getElementById('cardsBody').classList.toggle('closed', !open);
};
document.getElementById('plusBtn').onclick = function () {
  var p = document.getElementById('quickpanel');
  p.classList.toggle('open');
  this.textContent = p.classList.contains('open') ? '[ic:close]' : '[ic:add]';
};
// 财报折叠：点头部展开/收起；未启用财报模式则整块隐藏
document.getElementById('finFoldHead').onclick = function () {
  var body = document.getElementById('finFoldBody');
  var arrow = document.getElementById('finFoldArrow');
  var open = body.style.display !== 'none';
  body.style.display = open ? 'none' : '';
  arrow.textContent = open ? '▸' : '▾';
};
function setFinEnabled(en) {
  window.finEnabled = !!(en);
  var f = document.getElementById('finFold');
  if (f) f.style.display = window.finEnabled ? '' : 'none';
}
document.querySelectorAll('.chip[data-cmd]').forEach(function (c) {
  c.onclick = function () {
    var cmd = this.getAttribute('data-cmd');
    var input = document.getElementById('input');
    input.value = input.value.trim() ? input.value + ' ' + cmd : cmd;
    input.focus();
  };
});
document.getElementById('qcImage').onclick = function () { document.getElementById('fileInput').click(); };
document.getElementById('fileInput').onchange = function () {
  var f = this.files[0];
  if (!f) return;
  var reader = new FileReader();
  reader.onload = function () {
    pendingImage = { b64: reader.result.split(',')[1], mime: f.type || 'image/png' };
    document.getElementById('imgprevImg').src = reader.result;
    document.getElementById('imgprev').style.display = 'flex';
    document.getElementById('imgprevText').textContent = T.imgAttached;
  };
  reader.readAsDataURL(f);
};
document.getElementById('imgprevRemove').onclick = clearImage;
document.getElementById('send').onclick = send;
// ---------- 离线推进（你不在的时候，世界自己走了一小步）----------
// 后端只出"方案"，点了「让它发生」才改状态，并且可以撤销 —— 见 api_offline_peek/apply/undo
var offlineProposal = null;
function offlineCheck() {
  pywebview.api.offline_peek().then(function (r) {
    if (!r || !r.ok || !r.proposal) return;
    offlineProposal = r.proposal;
    var p = r.proposal;
    var parts = [];
    parts.push('<b>' + (p.summary || '') + '</b>');
    var det = [];
    det.push('现实 ' + Math.round((p.elapsed_real_sec || 0) / 60) + ' 分钟 × 时间流速 ' +
             (p.scale || 1) + ' 倍 = 软件时间 ' + Math.round((p.elapsed_sw_sec || 0) / 3600) + ' 小时');
    if (p.capped) det.push('已按上限计（离开太久，不按更长时间结算）');
    det.push('应用后会有 ' + (p.turns || 0) + ' 个回合的推进（事件冷却据此前进）；不喜欢可以一键撤销');
    document.getElementById('offlineSummary').innerHTML = parts.join('<br>');
    document.getElementById('offlineDetail').innerHTML = det.join('<br>');
    document.getElementById('offlineUndoBtn').style.display = 'none';
    document.getElementById('offlineApplyBtn').style.display = '';
    document.getElementById('offlineModal').classList.add('open');
  }).catch(function () {});
}
document.getElementById('offlineApplyBtn').onclick = function () {
  var b = this; b.disabled = true;
  pywebview.api.offline_apply(true).then(function (r) {
    b.disabled = false;
    if (r && r.ok) {
      // 弹窗不关："撤销"按钮要留在眼前，否则玩家看完提示就找不到反悔入口了
      document.getElementById('offlineApplyBtn').style.display = 'none';
      document.getElementById('offlineIgnoreBtn').textContent = '关闭';
      document.getElementById('offlineUndoBtn').style.display = '';
      document.getElementById('offlineDetail').innerHTML =
        '已应用：' + (r.summary || '') + (r.undo_saved ? '<br>不满意可以点「[ic:settings_backup_restore] 撤销结算」把它退回去。' : '');
    } else {
      alert((r && r.err) || '应用失败');
    }
  }).catch(function () { b.disabled = false; });
};
document.getElementById('offlineIgnoreBtn').onclick = function () {
  var label = this.textContent || '';
  if (label === '关闭') {   // 已经应用过了：直接关，不要再调后端（否则会把它当"忽略"记账）
    document.getElementById('offlineModal').classList.remove('open');
    return;
  }
  pywebview.api.offline_apply(false).then(function () {
    document.getElementById('offlineModal').classList.remove('open');
  }).catch(function () {
    document.getElementById('offlineModal').classList.remove('open');
  });
};
document.getElementById('offlineUndoBtn').onclick = function () {
  pywebview.api.offline_undo().then(function (r) {
    if (r && r.ok) {
      alert('已撤销上一次离线结算');
      document.getElementById('offlineUndoBtn').style.display = 'none';
      document.getElementById('offlineModal').classList.remove('open');
    } else {
      alert((r && r.err) || '撤销失败');
    }
  });
};
