/* 从 index.html 内联脚本拆出（第 3/4 段，顺序加载；全局作用域不变） */
// ---- 角色<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌卡导入 ----
document.getElementById('btnImportCard').onclick = function () {
  pywebview.api.import_card().then(function (r) {
    if (r && r.ok) {
      avatarCache[r.name] = undefined;
      reloadRoles();
      if (r.note) {
        try { pywebview.api.state().then(function () { alert('已导入「' + r.name + '」' + r.note); }); } catch (e) { alert(r.note); }
      }
    } else if (r && r.err !== 'cancelled') {
      alert(r.err);
    }
  });
};
// 卡片详情弹窗的「导入」也走这里（2026-12）：详情屏只发事件，按钮与去向归外壳自己，
// 免得它隔着屏去摸 #btnImportCard（屏间只经 DICK.bus）。
DICK.bus.on('card:import', function () { document.getElementById('btnImportCard').click(); });
// ---- 消息操作：编辑 / 重新生成 / 滑条 ----
document.getElementById('chat').addEventListener('click', function (e) {
  var btn = e.target.closest ? e.target.closest('button[data-act]') : null;
  if (!btn) return;
  var msgEl = btn.closest('.msg');
  if (!msgEl) return;
  var seq = parseInt(msgEl.getAttribute('data-seq'), 10);
  var act = btn.getAttribute('data-act');
  if (act === 'edit') {
    var bub = msgEl.querySelector('.bubble');
    // 编辑消息屏自己管输入框/标题/开关：这里只发一条「要编辑这条」，屏之间不再互相摸 DOM
    if (!DICK.bus.emit('msg:edit', {
      seq: seq,
      kind: msgEl.classList.contains('user') ? 'user' : 'ai',
      text: bub ? bub.textContent : ''
    })) { console.warn('[chat] 编辑消息屏没挂上（msg:edit 无人订阅）'); }
  } else if (act === 'speak') {
    var nid = msgEl.getAttribute('data-node');
    var sbtn = btn;
    sbtn.disabled = true;
    pywebview.api.speak_node(nid).then(function (r) {
      sbtn.disabled = false;
      if (r && !r.ok && r.err) alert(r.err);
    }).catch(function () { sbtn.disabled = false; });
  } else if (act === 'regen') {
    pywebview.api.regenerate(seq).then(function (r) {
      if (r && !r.ok) alert((r && r.err) || 'failed');
    });
  } else if (act === 'sprev' || act === 'snext') {
    var idx = 0, total = 0;
    var n = msgEl.querySelector('.swipe-n');
    if (n) {
      var parts = n.textContent.split('/');
      idx = parseInt(parts[0], 10) - 1;
      total = parseInt(parts[1], 10);
    }
    var ni = act === 'snext' ? Math.min(idx + 1, total - 1) : Math.max(idx - 1, 0);
    if (ni === idx) return;
    pywebview.api.switch_swipe(seq, ni).then(function (r) {
      if (r && !r.ok) alert((r && r.err) || 'failed');
    });
  }
});
// ---- 树状回溯（主线平铺 + 分支收纳，点击任意节点跳回） ----
var expandedBranches = {};
function treeStatus(msg) {
  // 树面板里的一次性提示条：打完分/剪完枝给个明确回执，
  // 否则用户点完不知道发生了什么（这类操作看不见结果就等于没做）。
  var p = document.getElementById('branchPanel');
  if (!p) return;
  var old = p.querySelector('.b-status');
  if (old) old.parentNode.removeChild(old);
  var d = document.createElement('div');
  d.className = 'b-item b-status';
  d.style.cssText = 'color:var(--sub);font-style:italic;white-space:normal;';
  d.textContent = msg;
  p.insertBefore(d, p.firstChild ? p.firstChild.nextSibling : null);
  setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); }, 8000);
}
function loadTree(smart) {
  pywebview.api.tree(treeScope).then(function (list) {
    treeList = list || [];
    // 首次打开且未手动切过：若存在选项节点，自动切到「只看选项」骨架（分线剧情默认清爽）
    if (smart && !manualScope) {
      var hasChoice = (list || []).some(function (n) { return n.is_choice; });
      if (hasChoice && treeScope !== 'choices') {
        treeScope = 'choices';
        loadTree(false);
        return;
      }
    }
    var p = document.getElementById('branchPanel');
    renderTreePanel(p);
  }).catch(function () {});
}
function renderTreePanel(p) {
  p.innerHTML = '';
  var head = document.createElement('div');
  head.className = 'b-head';
  head.style.cssText = 'display:flex;align-items:center;gap:8px;';
  var title = document.createElement('span');
  title.style.cssText = 'flex:1;';
  title.textContent = (T.treeTitle || '回溯');
  head.appendChild(title);
  var cap = document.createElement('span');
  cap.textContent = '⊟ 收纳';
  cap.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  cap.title = '全部收起（折叠选项间的对话）';
  cap.onclick = function (ev) {
    ev.stopPropagation();
    collapseAll();
  };
  head.appendChild(cap);
  // 树权重：主干 70% / 枝干 50%，有效权重 = 可实行性 × 合理性 × 位置
  var wBtn = document.createElement('span');
  wBtn.textContent = '[ic:balance] 打分';
  wBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  wBtn.title = '给整棵树打分（主干 70% / 枝干 50%），不删任何东西';
  wBtn.onclick = function (ev) {
    ev.stopPropagation();
    wBtn.textContent = '[ic:balance] …';
    pywebview.api.tree_weights().then(function (r) {
      wBtn.textContent = '[ic:balance] 打分';
      if (!r || !r.ok) { alert('打分失败：' + ((r && r.err) || '未知')); return; }
      var s = r.stats || {};
      treeStatus('[ic:balance] 已打分 ' + s.scored + ' 个节点（主干 ' + s.trunk
        + ' / 枝干 ' + s.branch + '）。权重：主干 ' + Math.round(s.trunk_weight * 100)
        + '% / 枝干 ' + Math.round(s.branch_weight * 100) + '%，阈值 '
        + Math.round(s.threshold * 100) + '%');
      loadTree(false);
    }).catch(function (e) { wBtn.textContent = '[ic:balance] 打分'; });
  };
  head.appendChild(wBtn);
  var pBtn = document.createElement('span');
  pBtn.textContent = '[ic:content_cut] 剪枝';
  pBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  pBtn.title = '剪掉低分枝叶（先预览，确认后才真删；主干永不删）';
  pBtn.onclick = function (ev) {
    ev.stopPropagation();
    // 先 dry-run 预览 —— 直接删是不可逆的，必须先让用户看到要删什么
    pBtn.textContent = '[ic:content_cut] …';
    pywebview.api.tree_prune(true).then(function (r) {
      pBtn.textContent = '[ic:content_cut] 剪枝';
      if (!r || !r.ok) { alert('剪枝检查失败：' + ((r && r.err) || '未知')); return; }
      if (!r.removed_count) {
        treeStatus('[ic:content_cut] 没有需要剪的枝叶（阈值 ' + Math.round(r.threshold * 100)
          + '%，主干与最新候选都受保护）');
        return;
      }
      var lines = (r.removed || []).slice(0, 6).map(function (x) {
        return '· 有效权重 ' + x.effective + '：' + (x.reasons || []).join('，');
      }).join('\n');
      if (!confirm('将要剪掉 ' + r.removed_count + ' 个低分节点：\n' + lines
        + '\n\n主干（你正在读的这条）不会被删。确定吗？')) return;
      pywebview.api.tree_prune(false).then(function (r2) {
        if (!r2 || !r2.ok) { alert('剪枝失败：' + ((r2 && r2.err) || '未知')); return; }
        treeStatus('[ic:content_cut] 已剪掉 ' + r2.removed_count + ' 个节点（'
          + r2.before + ' → ' + r2.after + '）');
        loadTree(false);
      });
    }).catch(function () { pBtn.textContent = '[ic:content_cut] 剪枝'; });
  };
  head.appendChild(pBtn);
  // 漂移核查：三态（正常 / 有嫌疑 / 定案漂移）+ 延迟定案
  // 为什么不自动剪：漂移有时候正是用户想要的走向，判定先给人看
  var dBtn = document.createElement('span');
  dBtn.textContent = '[ic:search] 漂移';
  dBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  dBtn.title = '核查有没有偏离本场目标（先在上面输入框填本场关键词）';
  dBtn.onclick = function (ev) {
    ev.stopPropagation();
    var cur = (window.__driftKeys || []).join('、');
    var inp = prompt('本场关键词（这场戏在讲什么？逗号分隔）\n'
      + '只有明确的目标词才可靠——泛泛的重叠分不出「跑题」和「措辞巧合」。', cur);
    if (inp === null) return;
    var keys = inp.split(/[,，、\s]+/).filter(function (x) { return x; });
    if (!keys.length) { treeStatus('没填关键词，不做判定（不填就不会乱定罪）'); return; }
    window.__driftKeys = keys;
    pywebview.api.set_drift_keys(JSON.stringify(keys)).then(function () {
      dBtn.textContent = '[ic:search] …';
      pywebview.api.tree_drift(true).then(function (r) {
        dBtn.textContent = '[ic:search] 漂移';
        if (!r || !r.ok) { treeStatus('核查失败：' + ((r && r.err) || '未知')); return; }
        var c = r.counts || {};
        treeStatus('[ic:search] 核查 ' + r.audited + ' 轮 → 正常 ' + (c.cleared || 0)
          + ' / 有嫌疑 ' + (c.suspected || 0) + ' / 定案漂移 ' + (c.drifted || 0)
          + '（只记状态，没有删任何东西）');
        var bad = (r.verdicts || []).filter(function (v) { return v.state === 'drifted'; });
        if (bad.length) {
          console.warn('漂移节点：', bad.map(function (v) {
            return { node: v.node, coverage: v.coverage, why: v.reasons };
          }));
        }
      }).catch(function () { dBtn.textContent = '[ic:search] 漂移'; });
    });
  };
  head.appendChild(dBtn);
  // 前瞻展开：把树从"生成后的仓库"挪到"生成之中"
  // 代价是每轮多 K×D 次调用，所以默认关，且必须显式确认
  var lBtn = document.createElement('span');
  lBtn.textContent = '[ic:explore] 前瞻';
  lBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  lBtn.title = '先生成几条路、往前探几轮，挑端点最正的给你（会多花 token）';
  lBtn.onclick = function (ev) {
    ev.stopPropagation();
    var b = parseInt(prompt('前瞻几条分支？（1~5）', '2') || '0', 10);
    if (!b) return;
    var d = parseInt(prompt('每条往前探几轮？（1~5）', '2') || '0', 10);
    if (!d) return;
    var calls = b * d;
    if (!confirm('每轮最多多花 ' + calls + ' 次模型调用（' + b + ' 条 × ' + d + ' 轮）。\n\n'
      + '· 没设本场关键词时不会前瞻（不会瞎挑）\n'
      + '· 判据还是启发式：搜得越深，判错的代价越大\n\n确定开启吗？')) return;
    pywebview.api.set_lookahead(true, b, d).then(function (r) {
      if (!r || !r.ok) { alert('开启失败：' + ((r && r.err) || '未知')); return; }
      lBtn.textContent = '[ic:explore] 前瞻开';
      lBtn.style.color = '#5fd39a';
      treeStatus('[ic:explore] 前瞻已开：' + r.note);
    });
  };
  head.appendChild(lBtn);
  // 偏好导出：把树里已经在产生、但不导出就永远拿不到的偏好信号接住
  var xBtn = document.createElement('span');
  xBtn.textContent = '[ic:upload] 偏好';
  xBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  xBtn.title = '把「同一问下你选了哪条、放弃了哪条」导出成 JSONL（只读，不改任何东西）';
  xBtn.onclick = function (ev) {
    ev.stopPropagation();
    xBtn.textContent = '[ic:upload] …';
    pywebview.api.export_preferences().then(function (r) {
      xBtn.textContent = '[ic:upload] 偏好';
      if (!r || !r.ok) { treeStatus('导出失败：' + ((r && r.err) || '未知')); return; }
      if (!r.samples && !r.written) { treeStatus('[ic:upload] ' + (r.msg || '还没有样本')); return; }
      var s = r.stats || {};
      var agree = (s.agreement === null || s.agreement === undefined)
        ? '一致率未知（先跑一次 [ic:balance] 打分）' : ('启发式与你的一致率 ' + Math.round(s.agreement * 100) + '%');
      treeStatus('[ic:upload] ' + r.msg + '；' + agree
        + '；正样本 ' + (s.samples || 0) + ' 条 / 负样本 ' + (s.rejected_total || 0) + ' 条');
    }).catch(function () { xBtn.textContent = '[ic:upload] 偏好'; });
  };
  head.appendChild(xBtn);
  // 价值声明（rubric）：第 2 步。声明错了比不声明更糟 —— 搜索会忠实放大它
  var rBtn = document.createElement('span');
  rBtn.textContent = '[ic:content_paste] 标准';
  rBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  rBtn.title = '声明本场的评分标准（每行一条）。有这个，前瞻才会按你的标准挑，而不只是避开硬故障';
  rBtn.onclick = function (ev) {
    ev.stopPropagation();
    var cur = (window.__rubric || []).join('\n');
    var inp = prompt('本场评分标准（每行一条，最多 8 条）\n'
      + '例：\n每轮必须推进一点，不能原地抒情\n不解释来历，悬念要留住\n不写成说明文，不回答案卷\n\n'
      + '[ic:warning] 写不好比不写更糟 —— 声明错了，搜索会忠实地放大它。', cur);
    if (inp === null) return;
    var items = inp.split('\n').map(function (x) { return x.trim(); })
      .filter(function (x) { return x; });
    window.__rubric = items;
    pywebview.api.set_rubric(items.join('\n')).then(function (r) {
      if (!r || !r.ok) { alert('保存失败：' + ((r && r.err) || '未知')); return; }
      if (!items.length) { treeStatus('[ic:content_paste] 已清空标准（前瞻退回只用启发式）'); return; }
      treeStatus('[ic:content_paste] 已存 ' + items.length + ' 条标准（' + r.role + '）。'
        + '开着前瞻时，每条分支的端点会按这些标准判一次分');
    });
  };
  head.appendChild(rBtn);
  /** 记忆调试：看每条历史的清晰度、年龄、隐藏衰减率。
 * 遗忘被设计成不可建模的，所以不给你看内部数字的话，你判断不出它坏没坏。 */
  var memBtn = document.createElement('span');
  memBtn.textContent = '[ic:memory] 记忆';
  memBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  memBtn.title = '看当前历史的记忆清晰度：还记得哪些、忘了哪些、每条各自多久忘一次'
    + '（和快捷栏那个「[ic:memory] 记忆」回溯命令不同：那个是把旧消息捞回来，这个是看记忆状态）';
  memBtn.onclick = function (ev) {
    ev.stopPropagation();
    if (!window.pywebview || !pywebview.api || !pywebview.api.memory_debug) return;
    pywebview.api.memory_debug().then(memDebugDraw).catch(function (e) {
      document.getElementById('memDebugHead').textContent = '读记忆失败：' + e;
      document.getElementById('memDebugModal').classList.add('open');
    });
  };
  head.appendChild(memBtn);
  /** 时间流速表盘：世界那边比现实快多少倍。
 * 对数刻度（每转一格 ×10）—— 线性的话 98% 行程都挤在最前几档上，没法用。 */
  var dialBtn = document.createElement('span');
  dialBtn.textContent = '[ic:hourglass_empty] 流速';
  dialBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  dialBtn.title = '世界那边过得比现实快多少倍（10 ~ 1000万）。拖表盘调，不用输数字';
  dialBtn.onclick = function (ev) { ev.stopPropagation(); timeDialOpen(); };
  head.appendChild(dialBtn);
  /** 调试面板（非开发者向）：把"训练"这件事变成看数、点一下、看结果。
 * 它不该出现在开发者入口里 —— 训练排序器不需要懂编程，只需要有偏好数据。 */
  var dbgBtn = document.createElement('span');
  dbgBtn.textContent = '[ic:terminal] 调试';
  dbgBtn.style.cssText = 'cursor:pointer;color:var(--sub);font-weight:600;user-select:none;';
  dbgBtn.title = '数据够不够 / 本地训练排序器 / 它学到了什么（不需要服务器）';
  dbgBtn.onclick = function (ev) {
    ev.stopPropagation();
    pywebview.api.ranker_status().then(function (r) {
      if (!r || !r.ok) { treeStatus('调试面板打不开：' + ((r && r.err) || '未知')); return; }
      var d = r.readiness || {};
      var msg = '[ic:bar_chart] 偏好数据：' + (d.samples || 0) + ' 条（正样本），需 ' + (d.need_more ? (d.samples + d.need_more) : d.samples) + ' 条才够训。\n';
      if (d.warnings && d.warnings.length) msg += '\n[ic:warning] ' + d.warnings.join('\n[ic:warning] ') + '\n';
      if (r.heuristic_agreement !== null && r.heuristic_agreement !== undefined) {
        msg += '\n启发式与你的一致率：' + Math.round(r.heuristic_agreement * 100) + '%\n';
      }
      msg += '\n模型：' + (r.model
        ? ('已训练（训练准确率 ' + r.model.train_acc + '，留出 ' + r.model.holdout_acc + '）')
        : '还没有') + '\n';
      if (r.model && r.model.top) {
        msg += '它在用的特征：' + r.model.top.map(function (x) {
          return x[0] + ' ' + (x[1] > 0 ? '+' : '') + x[1].toFixed(2);
        }).join('、') + '\n';
      }
      msg += '\n现在训一次吗？' + (d.ready ? '（纯本地，几秒钟，不联网、不用 API Key）'
                                        : '（数据还不够，训出来是噪声 —— 建议先多滑几次）');
      if (!confirm(msg)) return;
      if (!d.ready && !confirm('数据确实不够，还是要训吗？')) return;
      treeStatus('[ic:terminal] 训练中…');
      pywebview.api.train_ranker().then(function (t) {
        if (!t || !t.ok) { treeStatus('[ic:terminal] 训练没成：' + ((t && t.err) || '未知')); return; }
        var top = (t.top || []).map(function (x) {
          return x[0] + ' ' + (x[1] > 0 ? '+' : '') + x[1].toFixed(2);
        }).join('、');
        treeStatus('[ic:terminal] ' + t.msg + '；训练准确率 ' + t.train_acc
          + '，留出 ' + t.holdout_acc + '；权重最大：' + top);
        if (confirm('要启用它来给前瞻打分吗？\n\n会用你训出来的权重替代我手搓的那套判据。')) {
          pywebview.api.set_ranker(true).then(function () {
            treeStatus('[ic:terminal] 排序器已启用（前瞻时按你训出来的权重挑分支）');
          });
        }
      });
    });
  };
  head.appendChild(dbgBtn);
  var tg = document.createElement('span');
  tg.textContent = (treeScope === 'choices') ? '[ic:bookmark] 只看选项' : '[ic:description] 全部节点';
  tg.style.cssText = 'cursor:pointer;color:var(--accent);font-weight:600;user-select:none;';
  tg.onclick = function (ev) {
    ev.stopPropagation();
    manualScope = true;
    treeScope = (treeScope === 'choices') ? 'all' : 'choices';
    saveTreeView();
    loadTree(false);
  };
  head.appendChild(tg);
  p.appendChild(head);
  if (!treeList.length) {
    var hint = document.createElement('div');
    hint.className = 'b-hint';
    hint.textContent = '暂无对话历史';
    p.appendChild(hint);
    return;
  }
  function addRow(n, indent, branchHeader) {
    if (n.role === 'system') return;  // 系统节点不占行（收纳）
    var it = document.createElement('div');
    it.className = 'b-item' + (n.on_path ? ' on-path' : '') + (n.is_current ? ' cur' : '') + (branchHeader ? ' brh' : '');
    it.style.paddingLeft = (10 + indent * 14) + 'px';
    // 成就图标（灰白系）：角色/分支/选项 各配一个灰度图标
    var icon = n.role === 'user' ? '〔你〕' : (n.role === 'system' ? '[ic:settings]' : '〔AI〕');
    if (n.is_choice) icon = '▣';
    var badge = n.is_current ? '<span class="b-cur">当前</span>' : '';
    var who = '<span class="b-who">' + icon + '</span>';
    if (branchHeader) {
      var open = !!expandedBranches[n.id];
      // 分支 = 灰白成就"变体"：标题「分支 ×n」+ 灰描述
      it.innerHTML = who + '<span class="b-main"><span class="b-prev">' + (open ? '▾ ' : '▸ ') +
        '分支 ×' + n.branch_size + '</span><span class="b-desc">' + escapeHtml(n.content || '') + '</span></span>' + badge;
      it.onclick = function () {
        if (expandedBranches[n.id]) delete expandedBranches[n.id];
        else expandedBranches[n.id] = true;
        saveTreeView();
        renderTreePanel(p);
      };
    } else {
      it.innerHTML = who + '<span class="b-main"><span class="b-prev">' +
        escapeHtml(n.content || '') + '</span><span class="b-desc">' +
        (n.is_choice ? '选项节点' : (n.role === 'user' ? '你' : 'AI') + ' · ' +
         (n.on_path ? '当前剧情线' : '分支剧情')) + '</span></span>' + badge;
      it.onclick = function () {
        pywebview.api.backtrack(n.id).then(function (r) {
          if (r && r.ok) {
            p.classList.remove('open');
            try { showAchToast(n.is_choice ? '▣' : (n.role === 'user' ? '〔你〕' : '〔AI〕'), '已回到这段故事', '回档 · ' + (n.content || '').slice(0, 24)); } catch (e) {}
            lastSeq = 0;
            lastEpoch = -1;
            document.getElementById('chat').innerHTML = '';
            streamingEl = null;
            loadState();
          } else if (r && r.err) alert(r.err);
        });
      };
    }
    p.appendChild(it);
  }
  if (treeScope === 'choices') {
    renderTreeChoices(p, addRow);
    return;
  }
  var i = 0;
  while (i < treeList.length) {
    var n = treeList[i];
    if (n.on_path) {
      addRow(n, 0, false);
      i++;
    } else {
      var open = !!expandedBranches[n.branch_root];
      addRow(n, 0, true);
      i++;
      if (open) {
        while (i < treeList.length && treeList[i].branch_root === n.branch_root) {
          addRow(treeList[i], treeList[i].branch_depth, false);
          i++;
        }
      } else {
        while (i < treeList.length && treeList[i].branch_root === n.branch_root) i++;
      }
    }
  }
}
// ---- 选项骨架（只看选项）：按支线分组 + 折叠选项间对话为可展开 ··· 段 ----
// 注意：函数名不能叫 renderChoices —— 那是 Galgame 选项面板的渲染器（本文件靠前处已定义），
// 同名声明会被这一份覆盖，选项面板就再也不刷新了（test_web_dom.py 有同名冲突审计）。
function renderTreeChoices(p, addRow) {
  var hasChoice = treeList.some(function (n) { return n.is_choice; });
  if (!hasChoice) {
    // 无选项：直接平铺全部（保留定位与回溯，避免空视图）
    treeList.forEach(function (n) { addRow(n, 0, false); });
    return;
  }
  var i = 0;
  while (i < treeList.length) {
    var n = treeList[i];
    if (n.role === 'system') { i++; continue; }        // 系统节点不占位
    if (n.on_path) {
      // 主线：连续一段 on_path 节点，折叠其中非选项/非当前的对白
      var run = [];
      while (i < treeList.length && treeList[i].role !== 'system' && treeList[i].on_path) { run.push(treeList[i]); i++; }
      renderCollapsedRun(p, run, addRow, 0);
    } else {
      // 支线：按 branch_root 收纳成「分支」行，展开后同样折叠对白
      var open = !!expandedBranches[n.branch_root];
      addRow(n, 0, true);
      i++;
      if (open) {
        var members = [];
        while (i < treeList.length && treeList[i].branch_root === n.branch_root) { members.push(treeList[i]); i++; }
        renderCollapsedRun(p, members, addRow, 1);
      } else {
        while (i < treeList.length && treeList[i].branch_root === n.branch_root) i++;
      }
    }
  }
}
function renderCollapsedRun(p, nodes, addRow, indent) {
  var i = 0, prevId = null;
  while (i < nodes.length) {
    var n = nodes[i];
    if (n.role === 'system') { i++; continue; }
    if (n.is_choice || n.is_current) {
      addRow(n, indent, false);
      prevId = n.id;
      i++;
      continue;
    }
    var start = i;
    while (i < nodes.length && !(nodes[i].is_choice || nodes[i].is_current)) { i++; }
    var seg = nodes.slice(start, i);
    var nextId = null;
    for (var j = i; j < nodes.length; j++) {
      if (nodes[j].is_choice || nodes[j].is_current) { nextId = nodes[j].id; break; }
    }
    addSegmentRow(p, seg, addRow, prevId, nextId, indent);
  }
}
function addSegmentRow(p, seg, addRow, prevId, nextId, indent) {
  indent = indent || 0;
  var key = (prevId || '') + '>' + (nextId || '');
  var open = !!expandSeg[key];
  var it = document.createElement('div');
  it.className = 'b-item seg' + (open ? ' seg-open' : '');
  it.style.paddingLeft = (10 + indent * 14) + 'px';
  it.innerHTML = '<span class="b-who">' + (open ? '▾' : '▸') + '</span>' +
    '<span class="b-prev seg-label">⋯ ' + seg.length + ' 条对话</span>';
  it.onclick = function (e) {
    e.stopPropagation();
    if (expandSeg[key]) delete expandSeg[key];
    else expandSeg[key] = true;
    saveTreeView();
    renderTreePanel(document.getElementById('branchPanel'));
  };
  p.appendChild(it);
  if (open) {
    seg.forEach(function (sn) { addRow(sn, indent, false); });
  }
}
// ---- 树视图状态持久化（localStorage）+ 全部收纳 ----
function saveTreeView() {
  try {
    localStorage.setItem('dick_tree_view', JSON.stringify({
      treeScope: treeScope, manualScope: manualScope,
      expandSeg: expandSeg, expandedBranches: expandedBranches
    }));
  } catch (e) {}
}
function loadTreeView() {
  try {
    var raw = localStorage.getItem('dick_tree_view');
    if (!raw) return;
    var d = JSON.parse(raw);
    if (d.treeScope) treeScope = d.treeScope;
    if (typeof d.manualScope === 'boolean') manualScope = d.manualScope;
    if (d.expandSeg) expandSeg = d.expandSeg;
    if (d.expandedBranches) expandedBranches = d.expandedBranches;
  } catch (e) {}
}
function collapseAll() {
  expandSeg = {};
  expandedBranches = {};
  saveTreeView();
  renderTreePanel(document.getElementById('branchPanel'));
}
loadTreeView();
document.getElementById('btnBranches').onclick = function (e) {
  e.stopPropagation();
  var p = document.getElementById('branchPanel');
  if (p.classList.contains('open')) { p.classList.remove('open'); return; }
  loadTree(true);
  p.classList.add('open');
};
document.addEventListener('click', function (e) {
  var p = document.getElementById('branchPanel');
  if (p.classList.contains('open') && e.target !== document.getElementById('btnBranches') && !p.contains(e.target)) {
    p.classList.remove('open');
  }
});
// 预设选择：点顶部预设名循环
function openPresetMenu() {
  showOverlay('presetBtn', 'presetMenu', window.__presetItems || [], function (name) {
    closeOverlays();
    window.currentPreset = name;
    updatePresetName();
    pywebview.api.set_preset(name).then(function () {});
  });
}

document.getElementById('presetBtn').onclick = function (e) {
  e.stopPropagation();
  if (!window.__presetItems || !window.__presetItems.length) {
    pywebview.api.state().then(function (s) {
      if (s) renderPresets(s.presets || [], s.preset || '');
      openPresetMenu();
    });
    return;
  }
  openPresetMenu();
};
document.getElementById('btnNewRole').onclick = function () {
  document.getElementById('nrNameInput').disabled = false;
  document.getElementById('nrNameInput').value = '';
  fillRoleFields({});
  editingRole = null;
  document.getElementById('roleModal').classList.add('open');
};
document.getElementById('nrCancel').onclick = function () { document.getElementById('roleModal').classList.remove('open'); };
document.getElementById('nrCancel').onclick = function () {
  document.getElementById('roleModal').classList.remove('open');
  document.getElementById('nrNameInput').disabled = false;
  editingRole = null;
};
document.getElementById('nrSave').onclick = function () {
  var n = document.getElementById('nrNameInput').value.trim();
  var f = collectRoleFields();
  if (!n || !(f.legacy || f.appearance || f.personality || f.background || f.speech || f.first_mes || f.notes)) return;
  var payload = JSON.stringify(f);
  var fn = editingRole ? pywebview.api.update_role(editingRole, payload) : pywebview.api.create_role(n, payload);
  fn.then(function (r) {
    if (r && r.ok) {
      document.getElementById('roleModal').classList.remove('open');
      document.getElementById('nrNameInput').disabled = false;
      document.getElementById('nrNameInput').value = '';
      fillRoleFields({});
      editingRole = null;
      reloadRoles();
    }
  });
};
document.getElementById('nrDraft').onclick = function () {
  var idea = document.getElementById('nrLegacyInput').value.trim() ||
             document.getElementById('nrBackgroundInput').value.trim() ||
             document.getElementById('nrPersonalityInput').value.trim() ||
             '写一位有趣的角色';
  pywebview.api.ai_draft('role', idea).then(function (r) {
    if (r && r.ok && r.data) {
      var d = r.data;
      document.getElementById('nrNameInput').disabled = false;
      document.getElementById('nrNameInput').value = d.name || '';
      if (d.system_prompt && !d.appearance && !d.personality) {
        document.getElementById('nrLegacyInput').value = d.system_prompt;
      } else {
        fillRoleFields(d);
        if (d.legacy) document.getElementById('nrLegacyInput').value = d.legacy;
      }
    } else {
      alert((r && r.err) || 'AI 起草失败');
    }
  });
};
document.getElementById('btnSettings').onclick = function () {
  document.getElementById('settingsModal').classList.add('open');
};
// 侧边栏「 插件」：直接打开设置（插件管理所在），作为插件抽屉的便捷入口
document.getElementById('btnPlugins').onclick = function () {
  document.getElementById('settingsModal').classList.add('open');
};
document.getElementById('stCancel').onclick = function () { document.getElementById('settingsModal').classList.remove('open'); };
document.getElementById('stImgSave').onclick = function () {
  var key = document.getElementById('stImgKey').value.trim();
  if (key === '••••••••') key = '';
  var be = (document.getElementById('stImgBackend') || {}).value || 'auto';
  pywebview.api.save_image_gen(key, document.getElementById('stImgBase').value.trim(), document.getElementById('stImgModel').value.trim(), be).then(function (r) {
    if (r && r.ok) {
      document.getElementById('stImgState').textContent =
        '当前后端：' + (r.backend || 'openai') + (r.needs_key ? '（需要 Key）' : '（不需要 Key）');
      genHintByBackend();
      alert('生图设置已保存（后端：' + (r.backend || '') + '）');
    } else {
      alert((r && r.err) || '保存失败');
    }
  });
};
// ---------- 生图预设编辑器 ----------
function loadPresetEditor() {
  pywebview.api.get_image_presets_file().then(function (r) {
    if (!r || !r.ok) return;
    var txt = JSON.stringify(r.presets || {}, null, 2);
    document.getElementById('stPresetText').value = txt === '{}' ? '' : txt;
    var n = Object.keys(r.presets || {}).length;
    document.getElementById('stPresetState').textContent =
      (n ? '已有 ' + n + ' 个自定义预设。' : '还没有自定义预设。') +
      '内置：' + (r.builtin || []).map(function (b) { return b.label; }).join('、') +
      '　文件：' + (r.path || '');
    window.__presetExample = r.example || {};
  });
}
document.getElementById('stPresetSave').onclick = function () {
  var text = document.getElementById('stPresetText').value.trim() || '{}';
  pywebview.api.save_image_presets_file(text).then(function (r) {
    if (r && r.ok) {
      loadPresetEditor();
      loadGenPresets();
      alert((r.msg || '预设已保存') + '（生图面板的风格下拉已刷新）');
    } else {
      alert((r && r.err) || '保存失败');
    }
  });
};
document.getElementById('stPresetExample').onclick = function () {
  document.getElementById('stPresetText').value =
    JSON.stringify(window.__presetExample || {}, null, 2);
};
document.getElementById('stPresetReset').onclick = function () {
  document.getElementById('stPresetText').value = '';
  document.getElementById('stPresetSave').click();
};
document.getElementById('stProviderBtn').onclick = function (e) {
  e.stopPropagation();
  showOverlay('stProviderBtn', 'stProviderMenu', PROVIDERS.map(function (x) {
    var tag = x.free ? '免 Key' : '';
    if (x.id === 'ollama') tag = window.ollamaOnline ? '● 本地已连接' : '○ 本地未检测到';
    return { value: x.id, label: x.name, tag: tag, sel: x.id === currentProviderId };
  }), function (pid) {
    closeOverlays();
    fillProvider(pid, false);
  });
};
document.getElementById('stModelBtn').onclick = function (e) {
  e.stopPropagation();
  var p = providerById(currentProviderId);
  if (!p) return;
  var cur = document.getElementById('stModelInput').value.trim();
  var items = p.models.map(function (m) {
    return { value: m, label: m, sel: m === cur };
  });
  if (cur && p.models.indexOf(cur) < 0) {
    items.push({ value: cur, label: cur + '（自定义）', sel: true });
  }
  showOverlay('stModelBtn', 'stModelMenu', items, function (m) {
    closeOverlays();
    document.getElementById('stModelInput').value = m;
    renderModelSel(p);
  });
};
document.addEventListener('click', function (e) {
  var pm = document.getElementById('stProviderMenu');
  var mm = document.getElementById('stModelMenu');
  if (pm.style.display !== 'none' && !pm.contains(e.target) && e.target !== document.getElementById('stProviderBtn')) {
    pm.style.display = 'none';
  }
  if (mm.style.display !== 'none' && !mm.contains(e.target) && e.target !== document.getElementById('stModelBtn')) {
    mm.style.display = 'none';
  }
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') closeOverlays();
});
document.getElementById('stModelInput').addEventListener('input', function () {
  var p = providerById(currentProviderId);
  if (p) renderModelSel(p);
});
document.getElementById('stBuyBtn').onclick = function () {
  var p = providerById(currentProviderId);
  if (p) {
    pywebview.api.open_url(p.buy_url).then(function (r) {
      if (r && !r.ok) alert((r && r.err) || '打开失败');
    });
  }
};
document.getElementById('stSave').onclick = function () {
  var keyInput = document.getElementById('stKeyInput');
  var key = keyInput.value.trim();
  if (key === '••••••••') key = apiKeysMap[currentProviderId] || '';
  if (key) apiKeysMap[currentProviderId] = key;
  pywebview.api.save_key(key, document.getElementById('stBaseInput').value, document.getElementById('stModelInput').value, currentProviderId).then(function () {
    pywebview.api.set_proxy(document.getElementById('stProxyInput').value.trim()).then(function () {});
    pywebview.api.set_relay(document.getElementById('stRelayInput').value.trim()).then(function () {});
    pywebview.api.set_stop(document.getElementById('stStopInput').value).then(function () {});
    // 正则规则：文本行 → JSON 数组
    var rrList = [];
    document.getElementById('stRegexInput').value.split('\n').forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var p = line.split('|');
      if (p.length < 4) return;
      var scope = p[4] ? p[4].trim() : 'both';
      if (['ai', 'user', 'both'].indexOf(scope) < 0) scope = 'both';
      rrList.push({ id: p[0].trim(), name: p[1] ? p[1].trim() : p[0].trim(), pattern: p[2], replace: p.slice(3).join('|'), scope: scope, enabled: true });
    });
    pywebview.api.set_regex_rules(JSON.stringify(rrList)).then(function () {});
    pywebview.api.set_humanize(document.getElementById('stHumanizeInput').checked).then(function () {});
    pywebview.api.set_style_guard(document.getElementById('stStyleGuardInput').checked, document.getElementById('stStyleGuardLongInput').checked).then(function () {});
    pywebview.api.set_sampling(document.getElementById('stTempInput').value, document.getElementById('stTopPInput').value).then(function () {
      document.getElementById('settingsModal').classList.remove('open');
    });
  });
};
document.getElementById('stThemeBtn').onclick = function () {
  themeIdx = (themeIdx + 1) % THEMES.length;
  applyTheme();
  pywebview.api.set_theme(themeIdx, accentIdx);
};
document.getElementById('stAccentBtn').onclick = function () {
  accentIdx = (accentIdx + 1) % ACCENTS.length;
  applyTheme();
  pywebview.api.set_theme(themeIdx, accentIdx);
};
// ---- 聊天壁纸（核心） ----
document.getElementById('stWallpaperSet').onclick = function () {
  pywebview.api.set_chat_wallpaper().then(function (r) {
    if (r && r.ok) applyChatWallpaper(r.data || '');
    else if (r && r.err !== 'cancelled') alert(r.err || '设置失败');
  });
};
document.getElementById('stWallpaperClear').onclick = function () {
  pywebview.api.clear_chat_wallpaper().then(function (r) {
    if (r && r.ok) applyChatWallpaper('');
  });
};
