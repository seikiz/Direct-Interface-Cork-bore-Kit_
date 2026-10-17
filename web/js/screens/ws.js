/* web/js/screens/ws.js —— 🧰 创意工坊 / 世界卡库（阶段 3：从 index.html 整块搬出，零行为变化）
 *
 * 这一屏原来是 index.html 里**两段**离得很远的顶层代码：
 *   第 1 段（约 4230 行）：ws* 系列函数 + 插件 Tab 的两个按钮 + 开窗/关窗/Tab 切换
 *   第 2 段（约 6780 行）：本地列表的 onchange、导出/打开目录/删除、连接检测、搜索、
 *                          下载/点赞/上传/在线删除 —— 夹在 codex 播放器的绑定中间
 * 两段合成一个模块后，"点「🧰 创意工坊」→ 选 Tab → 选文件 → 下载"整条链路都在本文件里，
 * 不再和 codex 播放器的绑定混在一个匿名块里（审计里那 17 处"跨屏引用"就是这么来的）。
 *
 * 状态（阶段 3 收口）
 *   wsCurLocal    → DICK.state['ws.curLocal']     「本地」页选中的文件 {rtype, filename}
 *   wsCurOnline   → DICK.state['ws.curOnline']    在线列表选中的作品
 *   wsOnlineCache → DICK.state['ws.onlineCache']  上次拉到的在线列表
 * 三个同名全局是兼容访问器（state.js 的 bindGlobal），所以本文件里的读写一个字都没改。
 *
 * 归属
 *   结构：web/screens/ws.html（index.html 里原位只剩挂载点 <!--@screen:ws-->）
 *   样式：web/styles/screens/ws.css —— 原 styles/panels.css 的 .ws-cols/.ws-col、
 *         .ws-cards、.ws-card 一族、.ws-empty、.ws-tabbtn 原样搬出去，
 *         <link> 排在 panels.css（与 wm.css）之后。
 * 本屏依赖的外部符号（阶段 4/5 的收尾清单）
 *   · pywebview.api.workshop_*（state/preview/export/open_folder/delete_local/save_conn/
 *     detect_proxy/delete）
 *   · jobWait(kind, args)   后端分道任务（workshop.list/search/test/download/like/upload/plugins/
 *     install_plugin）—— 外壳的 jobs 通道，本屏只发不收
 *   · reloadRoles() / reloadWorlds()  下载/删除后刷新侧栏（外壳函数，直接调用）
 *   · escapeHtml()          组件层转义
 *   · #btnWorkshop          入口按钮在外壳侧栏（本屏 mount 时绑）
 *   · alert()/confirm()     删除确认仍是原生弹窗（原有行为，本轮不改交互）
 */
window.WsScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ================= 🧰 创<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌意工坊 =================
  // 三个选中态（真身都在 DICK.state['ws.*']，下面三行只注册同名兼容访问器）
  // ---- 创意工坊 ----
  // 「选中了哪个本地文件 / 哪个在线作品 / 在线列表缓存」真身都在 DICK.state['ws.*']，
  // 下面这三个同名全局只是兼容访问器（阶段 3 收口：老代码里的 `wsCurLocal = …` 一个字都不用改）。
  DICK.state.bindGlobal('wsCurLocal', 'ws.curLocal', null);
  DICK.state.bindGlobal('wsCurOnline', 'ws.curOnline', null);
  DICK.state.bindGlobal('wsOnlineCache', 'ws.onlineCache', []);

  function wsSetStatus(t) { document.getElementById('wsStatus').textContent = t || ''; }

  function wsRefreshAuto() {
    pywebview.api.workshop_state().then(function (s) {
      if (!s) return;
      var stEl = document.getElementById('wsAutoStatus');
      if (stEl) {
        stEl.innerHTML = s.active_server
          ? '🛰️ 自动连接：<span style="color:var(--accent)">' + escapeHtml(s.active_server) + '</span>'
          : '🛰️ 自动连接中...';
      }
    }).catch(function () {});
  }

  function wsLoadLocal() {
    pywebview.api.workshop_state().then(function (s) {
      if (!s) return;
      document.getElementById('wsProxyInput').value = s.proxy || '';
      document.getElementById('wsKeyInput').value = s.has_key ? '••••••••' : '';
      var stEl = document.getElementById('wsAutoStatus');
      if (stEl) {
        stEl.innerHTML = s.active_server
          ? '🛰️ 自动连接：<span style="color:var(--accent)">' + escapeHtml(s.active_server) + '</span>'
          : '🛰️ 自动连接中...';
      }
      var rl = document.getElementById('wsLocalRoles');
      var wl = document.getElementById('wsLocalWorlds');
      var pl = document.getElementById('wsLocalPacks');
      rl.innerHTML = '';
      (s.local_roles || []).forEach(function (f) {
        var o = document.createElement('option'); o.value = f; o.textContent = f.replace('.json', ''); rl.appendChild(o);
      });
      wl.innerHTML = '';
      (s.local_worlds || []).forEach(function (f) {
        var o = document.createElement('option'); o.value = f; o.textContent = f.replace('.json', ''); wl.appendChild(o);
      });
      if (pl) {
        pl.innerHTML = '';
        (s.local_packs || []).forEach(function (f) {
          var o = document.createElement('option'); o.value = f; o.textContent = f.replace('.json', ''); pl.appendChild(o);
        });
      }
    }).catch(function () {});
  }

  function wsShowLocalPreview(rtype, filename) {
    wsCurLocal = { rtype: rtype, filename: filename };
    pywebview.api.workshop_preview(rtype, filename).then(function (r) {
      document.getElementById('wsPreview').textContent = (r && r.ok) ? r.preview : ((r && r.err) || '');
    });
  }

  function wsSwitchTab(tab) {
    var isLocal = tab === 'local';
    var isOnline = tab === 'online';
    var isPlugin = tab === 'plugin';
    document.getElementById('wsLocalPane').style.display = isLocal ? '' : 'none';
    document.getElementById('wsOnlinePane').style.display = isOnline ? '' : 'none';
    document.getElementById('wsPluginPane').style.display = isPlugin ? '' : 'none';
    document.getElementById('wsTabLocal').className = 'btn2 ws-tabbtn' + (isLocal ? '' : ' ghost');
    document.getElementById('wsTabOnline').className = 'btn2 ws-tabbtn' + (isOnline ? '' : ' ghost');
    document.getElementById('wsTabPlugin').className = 'btn2 ws-tabbtn' + (isPlugin ? '' : ' ghost');
    if (isOnline) wsRefreshOnline();
    if (isPlugin) wsRefreshPlugins();
  }

  function wsFillOnline(list) {
    wsOnlineCache = list || [];
    var box = document.getElementById('wsOnlineList');
    box.innerHTML = '';
    if (!wsOnlineCache.length) {
      box.innerHTML = '<div class="ws-empty">暂无作品（服务器可能未启动）</div>';
      return;
    }
    wsOnlineCache.forEach(function (r, i) {
      var card = document.createElement('div');
      card.className = 'ws-card';
      card.style.cursor = 'pointer';
      card.innerHTML =
        '<div class="ws-card-top"><span class="ws-card-name">' + (r.type === '角色卡' ? '🎭 ' : (r.type === '世界卡包' ? '📦 ' : '🌍 ')) + escapeHtml(r.name || '') + '</span>' +
        '<span class="ws-card-meta">' + escapeHtml(r.author || '?') + ' · ↓' + (r.downloads || 0) + ' · ❤' + (r.likes || 0) + '</span></div>' +
        (r.description ? '<div class="ws-card-desc">' + escapeHtml(String(r.description).slice(0, 60)) + '</div>' : '');
      card.onclick = function () {
        document.querySelectorAll('#wsOnlineList .ws-card').forEach(function (c) { c.style.borderColor = ''; });
        card.style.borderColor = 'var(--accent)';
        wsCurOnline = r;
      };
      box.appendChild(card);
    });
    wsCurOnline = null;
  }

  // ---------- 创意工坊插件 Tab（插件市场） ----------
  function wsSetPluginStatus(t) { document.getElementById('wsPluginStatus').textContent = t || ''; }

  function wsRefreshPlugins() {
    wsSetPluginStatus('加载中...');
    jobWait('workshop.plugins', []).then(function (r) {
      if (!r || !r.ok) {
        wsSetPluginStatus('❌ ' + ((r && r.err) || '加载失败'));
        return;
      }
      var box = document.getElementById('wsPluginList');
      box.innerHTML = '';
      var plugins = r.plugins || [];
      var local = r.local || [];
      if (!plugins.length) {
        box.innerHTML = '<div class="ws-empty">插件市场暂无内容（工坊服务器未启动或未上传插件）</div>';
        wsSetPluginStatus('共 0 个插件');
        return;
      }
      plugins.forEach(function (p) {
        var installed = local.indexOf((p.original_name || '').replace(/\.py$/i, '')) >= 0 || local.indexOf(p.name) >= 0;
        var card = document.createElement('div');
        card.className = 'ws-card';
        card.innerHTML =
          '<div class="ws-card-top"><span class="ws-card-name">🔌 ' + escapeHtml(p.name || '') + '</span>' +
          '<span class="ws-card-meta">v' + escapeHtml(p.version || '1.0') + ' · ' + escapeHtml(p.author || '?') + ' · ↓' + (p.downloads || 0) + '</span></div>' +
          (p.description ? '<div class="ws-card-desc">' + escapeHtml(String(p.description).slice(0, 80)) + '</div>' : '') +
          '<div class="ws-card-btns">' +
          (installed
            ? '<span style="font-size:11px;color:var(--ok);padding:3px 4px">✅ 已安装</span>'
            : '<button class="btn2" data-pid="' + p.id + '">⬇️ 安装</button>') +
          '</div>';
        var btn = card.querySelector('[data-pid]');
        if (btn) {
          btn.onclick = function () {
            btn.disabled = true;
            btn.textContent = '⏳ 安装中...';
            jobWait('workshop.install_plugin', [p.id]).then(function (rr) {
              if (rr && rr.ok) {
                btn.outerHTML = '<span style="font-size:11px;color:var(--ok);padding:3px 4px">✅ 已安装 ' + escapeHtml(rr.name || '') + '</span>';
                wsSetPluginStatus('✅ 安装成功：' + (rr.name || ''));
              } else {
                btn.disabled = false;
                btn.textContent = '⬇️ 安装';
                wsSetPluginStatus('❌ ' + ((rr && rr.err) || '安装失败'));
              }
            }).catch(function (e) {
              btn.disabled = false;
              btn.textContent = '⬇️ 安装';
              wsSetPluginStatus('❌ ' + (e && e.message ? e.message : '网络错误'));
            });
          };
        }
        box.appendChild(card);
      });
      wsSetPluginStatus('共 ' + plugins.length + ' 个插件');
    }).catch(function (e) { wsSetPluginStatus('❌ ' + (e && e.message ? e.message : '网络错误')); });
  }

  /* ---------------- 插件 Tab 的两个按钮 ---------------- */
  function bindPluginTab() {
    document.getElementById('wsPluginRefresh').onclick = function () { wsRefreshPlugins(); };
    document.getElementById('wsPluginOpen').onclick = function () {
      pywebview.api.workshop_open_folder('plugins').then(function () {});
    };
  }

  function wsRefreshOnline() {
    wsSetStatus('加载中...');
    jobWait('workshop.list', []).then(function (r) {
      if (r && r.ok) {
        var mk = function (arr, type) {
          return (arr || []).map(function (x) { return { id: x.id, name: x.name, author: x.author, downloads: x.downloads, likes: x.likes, tags: x.tags, type: type, original_name: x.original_name }; });
        };
        var all = mk(r.cards, '角色卡').concat(mk(r.worlds, '世界卡')).concat(mk(r.packs, '世界卡包'));
        wsFillOnline(all);
        wsSetStatus('共 ' + all.length + ' 个作品'
          + (r.server_old ? '（服务器为旧版，无世界卡包）' : ''));
      } else {
        wsFillOnline([]);
        wsSetStatus('❌ ' + ((r && r.err) || '加载失败'));
      }
    }).catch(function (e) { wsSetStatus('❌ ' + (e && e.message ? e.message : '网络错误')); });
  }

  /* ---------------- 开窗 / 关窗 / 三个 Tab ---------------- */
  function bindOpenButtons() {
    document.getElementById('btnWorkshop').onclick = function () {
      document.getElementById('wsModal').classList.add('open');
      wsSwitchTab('local');
      wsLoadLocal();
      // 代理探测：只提示本机有哪些代理，**不自动填入**。
      // 系统/本机代理常把稍大的上传包体截断（实测传 1.3KB 请求体经 127.0.0.1:7890 得 502，
      // 同一份文件直连 201），所以默认直连，只有用户明确要代理时才走它。
      var px = document.getElementById('wsProxyInput');
      if (px && !px.value.trim() && pywebview.api.workshop_detect_proxy) {
        pywebview.api.workshop_detect_proxy().then(function (r) {
          if (r && r.ok && r.found && r.found.length) {
            wsSetStatus('🛰️ 直连优先；本机检测到 ' + r.found[0].url + '（要走代理再填进上面那栏）');
          }
        }).catch(function () {});
      }
    };
    document.getElementById('wsCloseBtn').onclick = function () { document.getElementById('wsModal').classList.remove('open'); };
    document.getElementById('wsTabLocal').onclick = function () { wsSwitchTab('local'); };
    document.getElementById('wsTabOnline').onclick = function () { wsSwitchTab('online'); };
    document.getElementById('wsTabPlugin').onclick = function () { wsSwitchTab('plugin'); };
  }

  /* ---------------- 本地 / 在线两个 Tab 的按钮与列表（原来夹在 codex 绑定中间那一段） ---------------- */
  function bindLocalOnline() {
    document.getElementById('wsLocalRoles').onchange = function () { if (this.value) wsShowLocalPreview('角色卡', this.value); };
    document.getElementById('wsLocalWorlds').onchange = function () { if (this.value) wsShowLocalPreview('世界卡', this.value); };
    document.getElementById('wsLocalPacks').onchange = function () { if (this.value) wsShowLocalPreview('世界卡包', this.value); };
    document.getElementById('wsExportBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在列表里选一个文件'); return; }
      pywebview.api.workshop_export(wsCurLocal.rtype, wsCurLocal.filename).then(function (r) {
        if (r && !r.ok && r.err !== 'cancelled') alert(r.err);
      });
    };
    document.getElementById('wsOpenBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在列表里选一个文件'); return; }
      var folder = wsCurLocal.rtype === '角色卡' ? 'roles' : (wsCurLocal.rtype === '世界卡包' ? 'packs' : 'worlds');
      pywebview.api.workshop_open_folder(folder).then(function () {});
    };
    document.getElementById('wsLocalDelBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在列表里选一个文件'); return; }
      if (!confirm('删除本地文件 ' + wsCurLocal.filename + ' ？')) return;
      pywebview.api.workshop_delete_local(wsCurLocal.rtype, wsCurLocal.filename).then(function (r) {
        if (r && r.ok) {
          wsCurLocal = null;
          document.getElementById('wsPreview').textContent = '';
          wsLoadLocal();
          reloadRoles();
          reloadWorlds();
        } else alert((r && r.err) || '删除失败');
      });
    };
    document.getElementById('wsTestBtn').onclick = function () {
      // 重新检测：保存代理设置 → 刷新自动连接状态 → 测试连接
      var key = document.getElementById('wsKeyInput').value.trim();
      if (key === '••••••••') key = '';
      var proxy = document.getElementById('wsProxyInput').value.trim();
      wsSetStatus('检测中...');
      pywebview.api.workshop_save_conn('', key, proxy).then(function () {
        wsRefreshAuto();
      });
      jobWait('workshop.test', []).then(function (r) {
        if (r && r.ok) {
          var st = r.stats || {};
          wsSetStatus('✅ 已连接（认证: ' + ((r.health && r.health.auth) || 'open') + ' · 下载 ' + (st.downloads || 0) + ' · 点赞 ' + (st.likes || 0) + '）');
        } else wsSetStatus('❌ ' + ((r && r.err) || '连接失败'));
      });
    };
    document.getElementById('wsAllBtn').onclick = function () { wsRefreshOnline(); };
    document.getElementById('wsSearchBtn').onclick = function () {
      var q = document.getElementById('wsSearchInput').value.trim();
      wsSetStatus('搜索中...');
      jobWait('workshop.search', [q, '']).then(function (r) {
        if (r && r.ok) {
          wsFillOnline((r.results || []).map(function (x) { return { id: x.id, name: x.name, author: x.author, downloads: x.downloads, likes: x.likes, tags: x.tags, type: x.type || '角色卡', original_name: x.original_name }; }));
          wsSetStatus('找到 ' + (r.results || []).length + ' 个');
        } else wsSetStatus('❌ ' + ((r && r.err) || '搜索失败'));
      });
    };
    document.getElementById('wsDownloadBtn').onclick = function () {
      if (!wsCurOnline) { alert('先在列表里选一个作品'); return; }
      wsSetStatus('下载中...');
      jobWait('workshop.download', [wsCurOnline.id, wsCurOnline.type, wsCurOnline.original_name || (wsCurOnline.name + '.json')]).then(function (r) {
        if (r && r.ok) {
          wsSetStatus('✅ 已下载：' + r.file);
          wsLoadLocal();
          reloadRoles();
          reloadWorlds();
        } else wsSetStatus('❌ ' + ((r && r.err) || '下载失败'));
      });
    };
    document.getElementById('wsLikeBtn').onclick = function () {
      if (!wsCurOnline) { alert('先选一个作品'); return; }
      jobWait('workshop.like', [wsCurOnline.id, wsCurOnline.type]).then(function (r) {
        wsSetStatus(r && r.ok ? '✅ 已点赞' : '❌ ' + ((r && r.err) || '失败'));
      });
    };
    document.getElementById('wsUploadBtn').onclick = function () {
      if (!wsCurLocal) { alert('先在「本地」页选一个要上传的文件'); return; }
      var name = wsCurLocal.filename.replace('.json', '');
      wsSetStatus('上传中...');
      jobWait('workshop.upload', [wsCurLocal.rtype, name]).then(function (r) {
        wsSetStatus(r && r.ok ? '✅ 上传成功' : '❌ ' + ((r && r.err) || '上传失败'));
      });
    };
    document.getElementById('wsOnlineDelBtn').onclick = function () {
      if (!wsCurOnline) { alert('先选一个作品'); return; }
      if (!confirm('从工坊删除「' + wsCurOnline.name + '」？此操作不可恢复。')) return;
      pywebview.api.workshop_delete(wsCurOnline.id, wsCurOnline.type).then(function (r) {
        if (r && r.ok) { wsSetStatus('✅ 已删除'); wsRefreshOnline(); }
        else wsSetStatus('❌ ' + ((r && r.err) || '删除失败'));
      });
    };
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('wsModal')) {
      console.error('[ws] 片段没注入（找不到 #wsModal），这一屏跳过挂载');
      return;
    }
    mounted = true;
    bindPluginTab();
    bindOpenButtons();
    bindLocalOnline();
  }

  function unmount() {
    var b = document.getElementById('btnWorkshop');
    if (b) { b.onclick = null; }
    var c = document.getElementById('wsCloseBtn');
    if (c) { c.onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    setStatus: wsSetStatus, refreshAuto: wsRefreshAuto, loadLocal: wsLoadLocal,
    showLocalPreview: wsShowLocalPreview, switchTab: wsSwitchTab, fillOnline: wsFillOnline,
    setPluginStatus: wsSetPluginStatus, refreshPlugins: wsRefreshPlugins,
    refreshOnline: wsRefreshOnline
  };
})(window);

/* ===== 兼容入口（阶段 4/5 清理）=====
 * 搬家前这 9 个都是 index.html 的顶层全局函数。本轮搬完，index.html 里**已经没有任何一处**
 * 调用它们（开窗/关窗/Tab 由本屏 mount() 绑，渲染由本屏自己按需调）。
 * 但插件作者/老脚本可能按名字叫，所以同名全局继续存在，内部只转调模块 —— 实现不再有第二份。 */
function wsSetStatus(t) { return window.WsScreen.setStatus(t); }
function wsRefreshAuto() { return window.WsScreen.refreshAuto(); }
function wsLoadLocal() { return window.WsScreen.loadLocal(); }
function wsShowLocalPreview(rtype, filename) { return window.WsScreen.showLocalPreview(rtype, filename); }
function wsSwitchTab(tab) { return window.WsScreen.switchTab(tab); }
function wsFillOnline(list) { return window.WsScreen.fillOnline(list); }
function wsSetPluginStatus(t) { return window.WsScreen.setPluginStatus(t); }
function wsRefreshPlugins() { return window.WsScreen.refreshPlugins(); }
function wsRefreshOnline() { return window.WsScreen.refreshOnline(); }

// 注册到路由：片段 = screens/ws.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('ws', { fragment: 'screens/ws.html', module: window.WsScreen });
