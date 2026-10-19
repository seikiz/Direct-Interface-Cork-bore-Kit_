/* web/js/screens/codex-editor.js —— 编年史（codex）编辑器：包管理 + 剧本 JSON 编辑 + 保存/校验。
 *
 * 归属（阶段 5：index.html 里最后两块屏之一整块搬出，2026-11）
 * 结构 web/screens/codex.html（codexModal / codexPasteModal / codexAdvancedModal / codexPlayer 四块）
 * 样式 web/styles/screens/codex.css（本屏没有专属规则：全用 components 的 .modal/.btn2/.row + 行内 style）
 * 数据 web/js/store/codex.js（codex.cur / codex.script …；老名字 codexCur / codexScript 是兼容访问器）
 * 同块的其它文件（按 index.html 里的加载顺序）：
 *   codex-graph.js（节点图）→ gal-*.js（GAL 屏）→ codex-pack.js（打包/发布）
 *   → codex-player.js + codex-player-scene.js（播放器）→ codex-bind.js（按钮绑定）
 *
 * 契约
 * · 本文件是 codex 这一屏唯一的注册点：mount() 按片段到位后接线，unmount() 收摊。
 * · 编辑器不摸播放器的 DOM（cx 前缀那些 id）：开播只发 DICK.bus 'codex:play'。
 * · 播放器也不摸编辑器的 DOM：它把「该不该占屏」写成 DICK.state['codex.playerOpen']，
 *   由这里的订阅者去动播放器容器 —— 这是编辑器与播放器之间唯一的接触面。
 * · GAL 屏要借本屏的 JSON 面板看同一份剧本：走 DICK.bus 'codex:json-sync' / 'codex:json-open'，
 *   本屏自己写自己的 textarea（跨屏不摸 DOM）。
 *
 * 依赖的外部符号（运行时都已存在）：pywebview.api.codex_*、escapeHtml()、codexCur/codexScript 状态域
 */


// ================= CODEX 专属 GAL<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌GAME（PC 端独有） =================
// 编年史 codex 的数据层收进 DICK.state（5 个：codexCur、codexScript、codexPlayer、codexVolume、codexTypeSpeed）；注册在 web/js/store/codex.js

function codexSetStatus(s) {
  var el = document.getElementById('codexStatus');
  if (el) el.textContent = s || '';
}
function codexOpen() {
  document.getElementById('codexModal').classList.add('open');
  document.getElementById('codexDetail').style.display = 'none';
  document.getElementById('codexEditor').style.display = 'none';
  document.getElementById('codexFiles').style.display = 'none';
  codexCur = null;
  codexLoadList();
}
function codexLoadList() {
  codexSetStatus('加载中…');
  pywebview.api.codex_list().then(function (r) {
    if (!r || !r.ok) { codexSetStatus('[ic:error] ' + ((r && r.err) || '加载失败')); return; }
    codexSetStatus('共 ' + r.packages.length + ' 个 CODEX 包');
    renderCodexList(r.packages || []);
  }).catch(function (e) { codexSetStatus('[ic:error] ' + (e && e.message ? e.message : '加载失败')); });
}
function renderCodexList(pkgs) {
  var box = document.getElementById('codexList');
  box.innerHTML = '';
  if (!pkgs.length) {
    box.innerHTML = '<div style="color:var(--sub);padding:14px;text-align:center">还没有 CODEX 包 —— 点「[ic:folder] 导入文件夹」选一个含有立绘/音乐/背景/配音的文件夹，或「[ic:add] 新建」从模板开始</div>';
    return;
  }
  pkgs.forEach(function (p) {
    var card = document.createElement('div');
    card.className = 'role-card';
    var sel = p.name === codexCur ? 'style="border-color:var(--accent,#f59e0b)"' : '';
    var res = '[ic:sprite]' + p.sprites + ' [ic:image]' + p.bg + ' [ic:music_note]' + p.bgm + ' [ic:mic]' + p.voice;
    card.innerHTML =
      '<div class="rc-name" ' + sel + '>' +
        '<label for="">[ic:book] ' + escapeHtml(p.name) + (p.has_script ? '' : ' <span style="color:var(--danger)">(缺剧本)</span>') + '</label>' +
        '<span style="flex:1"></span>' +
        '<span style="font-size:11px;color:var(--sub)">' + res + '</span>' +
      '</div>' +
      '<div style="font-size:11px;color:var(--sub);padding:2px 0 0 24px">' + escapeHtml(p.intro || '') +
        (p.scenes ? ' · ' + p.scenes + ' 场景' : '') + '</div>';
    card.style.cursor = 'pointer';
    card.onclick = function () { codexSelect(p.name); };
    box.appendChild(card);
  });
}
function codexSelect(name) {
  codexCur = name;
  document.getElementById('codexDetail').style.display = 'block';
  document.getElementById('codexEditor').style.display = 'none';
  document.getElementById('codexFiles').style.display = 'none';
  document.getElementById('codexDetailName').textContent = '[ic:book] ' + name;
  codexLoadList(); // 刷新高亮 + 简介
  pywebview.api.codex_get(name).then(function (r) {
    if (!r || !r.ok) { codexSetStatus('[ic:error] ' + ((r && r.err) || '读取失败')); return; }
    var intro = (r.script && r.script.intro) || '';
    document.getElementById('codexIntro').textContent = intro || '（无简介）';
    if (!r.valid && r.issues && r.issues.length) {
      codexSetStatus('[ic:warning] 剧本问题: ' + r.issues.slice(0, 2).join('; '));
    }
  });
}
function codexNew() {
  var n = prompt('新建 CODEX 包名称（将生成示例剧本，可立即播放）:', '我的故事');
  if (!n || !n.trim()) return;
  pywebview.api.codex_create(n.trim()).then(function (r) {
    if (r && r.ok) { codexLoadList(); codexSelect(r.name); }
    else alert((r && r.err) || '新建失败');
  });
}
function codexSample() {
  var n = prompt('示例包名称（将生成带占位立绘/背景/音乐/配音的完整示例，可直接播放）:', '示例·夏日祭');
  if (!n || !n.trim()) return;
  codexSetStatus('[ic:hourglass_empty] 生成示例包…');
  pywebview.api.codex_sample(n.trim()).then(function (r) {
    if (r && r.ok) { codexSetStatus('[ic:check_circle] 示例包已生成'); codexLoadList(); codexSelect(r.name); }
    else { codexSetStatus(''); alert((r && r.err) || '生成失败'); }
  });
}
function codexDraft() {
  // 素材供应链：一句话主题 → AI 生成完整剧本 → 预览编辑 → 保存为新包
  var n = prompt('新包名称:', '我的故事');
  if (!n || !n.trim()) return;
  var idea = prompt('一句话主题（如：雨天的咖啡店，内向少女鼓起勇气搭话）:', '雨天的咖啡店，内向少女鼓起勇气搭话');
  if (!idea || !idea.trim()) return;
  codexSetStatus('[ic:hourglass_empty] AI 起草剧本中…（约 30-60 秒）');
  pywebview.api.codex_draft(n.trim(), idea.trim()).then(function (r) {
    if (!r || !r.ok) { codexSetStatus(''); alert((r && r.err) || '起草失败'); return; }
    // 生成包 + 把 AI 剧本写进去
    pywebview.api.codex_create(n.trim()).then(function (cr) {
      if (!cr || !cr.ok) { codexSetStatus(''); alert('建包失败'); return; }
      pywebview.api.codex_save(cr.name, JSON.stringify(r.script)).then(function (sr) {
        codexSetStatus('[ic:check_circle] AI 剧本已生成' + (sr && sr.valid ? '' : '（有结构提示，可编辑修正）'));
        codexLoadList();
        codexCur = cr.name;
        codexEdit();
      });
    });
  }).catch(function (e) { codexSetStatus(''); alert('起草失败: ' + (e && e.message ? e.message : '')); });
}
function codexImport() {
  pywebview.api.codex_import_folder().then(function (r) {
    if (!r) return;
    if (r.ok) { codexSetStatus('[ic:check_circle] ' + (r.msg || '导入成功')); codexLoadList(); if (r.name) codexSelect(r.name); }
    else if (r.err !== 'cancelled') alert(r.err || '导入失败');
  });
}
function codexImportZip() {
  pywebview.api.codex_import_zip().then(function (r) {
    if (!r) return;
    if (r.ok) { codexSetStatus('[ic:check_circle] ' + (r.msg || '导入成功')); codexLoadList(); if (r.name) codexSelect(r.name); }
    else if (r.err !== 'cancelled') alert(r.err || '导入失败');
  });
}
function codexImportCodex() {
  pywebview.api.codex_import_codex().then(function (r) {
    if (!r) return;
    if (r.ok) { codexSetStatus('[ic:check_circle] ' + (r.msg || '导入成功')); codexLoadList(); if (r.name) codexSelect(r.name); }
    else if (r.err !== 'cancelled') alert(r.err || '导入失败');
  });
}
function codexPasteOpen() {
  document.getElementById('codexPasteInput').value = '';
  codexPasteStatus('');
  document.getElementById('codexPasteModal').classList.add('open');
}
function codexPasteStatus(s) { var el = document.getElementById('codexPasteStatus'); if (el) el.textContent = s || ''; }
function codexPasteConvert() {
  var text = document.getElementById('codexPasteInput').value.trim();
  if (!text) { codexPasteStatus('请先粘贴剧本'); return; }
  codexPasteStatus('[ic:hourglass_empty] 转化中…');
  pywebview.api.codex_import_script(text).then(function (r) {
    if (!r || !r.ok) { codexPasteStatus('[ic:error] ' + ((r && r.err) || '转化失败')); return; }
    codexPasteStatus('[ic:check_circle] 已识别为 ' + (r.kind === 'json' ? 'JSON' : '纯文本') + ' 剧本' + (r.valid ? '' : '，有结构提示，可修正后保存'));
    var doSave = function (pkgName) {
      pywebview.api.codex_save(pkgName, JSON.stringify(r.script)).then(function (sr) {
        codexPasteStatus('[ic:check_circle] 已保存到「' + pkgName + '」' + (sr && sr.valid ? '' : '（有结构提示）'));
        document.getElementById('codexPasteModal').classList.remove('open');
        codexCur = pkgName;
        codexSelect(pkgName);
        codexEdit();
      });
    };
    if (codexCur) { doSave(codexCur); }
    else {
      pywebview.api.codex_create(r.autoName || '我的剧本').then(function (cr) {
        if (cr && cr.ok) doSave(cr.name);
        else codexPasteStatus('[ic:error] 建包失败：' + ((cr && cr.err) || ''));
      });
    }
  }).catch(function (e) { codexPasteStatus('[ic:error] ' + (e && e.message ? e.message : '转化失败')); });
}
function codexImportSprites() {
  if (!codexCur) return;
  codexSetStatus('[ic:hourglass_empty] 导入立绘…');
  pywebview.api.codex_import_sprites(codexCur).then(function (r) {
    codexSetStatus('');
    if (r && r.ok) {
      codexSetStatus('[ic:check_circle] ' + (r.msg || ('导入 ' + r.added.length + ' 张立绘')));
      codexLoadList();
    } else if (r && r.err !== 'cancelled') {
      alert(r.err || '导入失败');
      codexLoadList();
    }
  });
}
function codexTplStatus(s) { var el = document.getElementById('codexTplStatus'); if (el) el.textContent = s || ''; }
function codexAdvancedOpen() {
  if (!codexCur) return;
  codexTplStatus('');
  document.getElementById('codexAdvancedModal').classList.add('open');
  document.getElementById('codexTplPreview').srcdoc = '';
  codexTplStatus('[ic:hourglass_empty] 加载播放器模板…');
  pywebview.api.codex_get_player_template(codexCur).then(function (r) {
    if (!r || !r.ok) { codexTplStatus('[ic:error] ' + ((r && r.err) || '加载失败')); return; }
    document.getElementById('codexTplInput').value = r.html || '';
    codexTplStatus(r.is_custom ? '[ic:edit] 自定义模板（来自本包 player.html）' : '[ic:check_circle] 系统内置模板');
  });
}
function codexAdvancedPlay() {
  if (!codexCur) return;
  var tpl = document.getElementById('codexTplInput').value;
  codexTplStatus('[ic:hourglass_empty] 渲染中…');
  pywebview.api.codex_render(codexCur, tpl).then(function (r) {
    if (!r || !r.ok) { codexTplStatus('[ic:error] ' + ((r && r.err) || '渲染失败')); return; }
    document.getElementById('codexTplPreview').srcdoc = r.html || '';
    codexTplStatus('[ic:play] 已渲染（试玩预览）');
  });
}
function codexAdvancedSave() {
  if (!codexCur) return;
  var tpl = document.getElementById('codexTplInput').value;
  codexTplStatus('[ic:hourglass_empty] 保存中…');
  pywebview.api.codex_save_player_template(codexCur, tpl).then(function (r) {
    if (r && r.ok) codexTplStatus('[ic:check_circle] ' + (r.msg || '模板已保存'));
    else codexTplStatus('[ic:error] ' + ((r && r.err) || '保存失败'));
  });
}
function codexAdvancedReset() {
  if (!codexCur) return;
  codexTplStatus('[ic:hourglass_empty] 恢复默认…');
  pywebview.api.codex_get_player_template('').then(function (r) {
    if (!r || !r.ok) { codexTplStatus('[ic:error] ' + ((r && r.err) || '失败')); return; }
    document.getElementById('codexTplInput').value = r.html || '';
    codexTplStatus('[ic:settings_backup_restore] 已载入系统内置模板，点「[ic:save] 保存模板」才会写入本包');
  });
}
function codexExportCodex() {
  if (!codexCur) return;
  pywebview.api.codex_export_codex(codexCur).then(function (r) {
    if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
    else if (r && r.ok) {
      var info = document.getElementById('codexPackInfo');
      info.innerHTML = '[ic:check_circle] 已导出 .codex 包：' + escapeHtml(r.file) + ' —— 发给任何人，对方双击（注册关联后）即可在 DICK 打开播放。';
      info.style.display = 'block';
    }
  });
}
function codexAssoc() {
  pywebview.api.codex_register_assoc().then(function (r) {
    if (r && r.ok) codexSetStatus(r.msg || '[ic:check_circle] 已注册');
    else alert((r && r.err) || '注册失败');
  });
}
function codexVoice() {
  // 一键配音：UTAU 批量合成台词 → voice/ + 更新剧本引用
  if (!codexCur) return;
  if (!confirm('为「' + codexCur + '」的所有台词一键合成配音？（需启用 UTAU 语音插件 + 声库，逐句合成较慢）')) return;
  codexSetStatus('[ic:hourglass_empty] 逐句配音中…（每句约 3-10 秒）');
  pywebview.api.codex_auto_voice(codexCur).then(function (r) {
    codexSetStatus('');
    if (r && r.ok) {
      var info = document.getElementById('codexPackInfo');
      info.innerHTML = '[ic:check_circle] ' + escapeHtml(r.msg || '配音完成') + ' —— 播放时自动读出台词。';
      info.style.display = 'block';
      codexLoadList();
    } else alert((r && r.err) || '配音失败');
  });
}
function codexDelete() {
  if (!codexCur) return;
  if (!confirm('删除 CODEX 包「' + codexCur + '」？此操作不可恢复。')) return;
  pywebview.api.codex_delete(codexCur).then(function (r) {
    if (r && r.ok) { codexCur = null; document.getElementById('codexDetail').style.display = 'none'; codexLoadList(); }
    else alert((r && r.err) || '删除失败');
  });
}
function codexEdit() {
  if (!codexCur) return;
  DICK.bus.emit('gal:open-editor', codexCur);
}
function codexEditorStatus(s) { document.getElementById('codexEditorStatus').textContent = s || ''; }
function codexFormat() {
  var box = document.getElementById('codexJsonInput');
  try { box.value = JSON.stringify(JSON.parse(box.value), null, 2); codexEditorStatus('[ic:palette] 已格式化'); }
  catch (e) { codexEditorStatus('[ic:error] ' + e.message); }
}
function codexCheck() {
  var box = document.getElementById('codexJsonInput');
  try {
    var obj = JSON.parse(box.value);
    pywebview.api.codex_save(codexCur, JSON.stringify(obj)).then(function (r) {
      if (r && r.ok) codexEditorStatus(r.valid ? '[ic:check_circle] 结构正常' : '[ic:warning] ' + ((r.issues || []).slice(0, 3).join('; ')));
      else codexEditorStatus('[ic:error] ' + ((r && r.err) || '校验失败'));
    });
  } catch (e) { codexEditorStatus('[ic:error] JSON 解析失败: ' + e.message); }
}
function codexSave() {
  var box = document.getElementById('codexJsonInput');
  try { JSON.parse(box.value); } catch (e) { codexEditorStatus('[ic:error] JSON 解析失败: ' + e.message); return; }
  pywebview.api.codex_save(codexCur, box.value).then(function (r) {
    if (r && r.ok) { codexEditorStatus(r.valid ? '[ic:check_circle] 已保存，结构正常' : '[ic:warning] 已保存但: ' + ((r.issues || []).slice(0, 2).join('; '))); codexLoadList(); }
    else codexEditorStatus('[ic:error] ' + ((r && r.err) || '保存失败'));
  });
}

/* ================= 一屏的挂载 / 卸载（router 注入片段之后调用） =================
 * 这里只做「接线」，不搬逻辑：编辑器按钮在 codex-bind.js，节点图按钮在 codex-graph.js。
 * 两块屏（编辑器 ↔ 播放器）的接触面只有两条，见文件头「契约」：
 * ① DICK.state['codex.playerOpen']：播放器写、这里读（动播放器容器的 display）；
 * ② DICK.bus 'codex:json-sync' / 'codex:json-open'：GAL 屏借 JSON 面板。
 */
function codexMount() {
  var mod = window.CodexScreen;
  if (mod && mod.__ready) { return; }          // mount 幂等（router 也会挡一次）
  if (!document.getElementById('codexModal')) {
    console.error('[codex] 片段没注入（找不到 codexModal），这一屏跳过挂载');
    return;
  }
  codexBindEditor();
  codexBindPlayer();
  codexGraphBind();
  DICK.state.on('codex.playerOpen', function (v) {
    var box = document.getElementById('codexPlayer');
    if (box) { box.style.display = v ? 'block' : 'none'; }
  });
  DICK.bus.on('codex:json-sync', function (p) {
    var box = document.getElementById('codexJsonInput');
    if (!box || !p || !p.script) { return; }
    box.value = JSON.stringify(p.script, null, 2);
    if (p.save) { codexSave(); }
  });
  DICK.bus.on('codex:json-open', function (p) {
    var box = document.getElementById('codexJsonInput');
    if (!box || !p || !p.script) { return; }
    box.value = JSON.stringify(p.script, null, 2);
    document.getElementById('codexModal').classList.add('open');
    document.getElementById('codexGraphWrap').style.display = 'none';
    document.getElementById('codexEditor').style.display = 'block';
  });
  if (mod) { mod.__ready = true; }
}

function codexUnmount() {
  DICK.state.set('codex.playerOpen', false);
}

/* 本文件定义的全局函数（codexOpen/codexSelect/codexSave…）就是这一屏的门面，
   另有 codex-graph.js / codex-pack.js 里的同类；这里只把「屏」这个身份挂出来。 */
window.CodexScreen = { mount: codexMount, unmount: codexUnmount,
                       open: codexOpen, list: codexLoadList, select: codexSelect,
                       edit: codexEdit };

// 注册到路由：片段 = screens/codex.html，模块 = 上面这个
DICK.router.register('codex', { fragment: 'screens/codex.html', module: window.CodexScreen });

