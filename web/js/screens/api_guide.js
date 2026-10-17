/* api_guide.js —— 📖 API 教程面板 + 🧭 首启配置向导（一屏的行为）
 *
 * 两件事共用一份数据（服务商事实表）和三语文案：
 *   ① 教程面板：怎么选模型 / 服务商清单 / 三步配置 / 常见错误 / 免费链 / 省钱 / 官方搜索 / 免责小字；
 *   ② 首启向导：① 选服务商 → ② 填 Key → ③ 测试并保存（真实请求一次，通了才落盘）。
 *
 * 硬边界（见 web/UI_ARCHITECTURE.md）：
 *   · 不 getElementById 别的屏的 id；打开/关闭只走 `DICK.bus`（settings.js 发事件，这里订阅）；
 *   · 按钮一律来自 web/js/components/Button.js（不新造按钮外观）；
 *   · 文案一律 `T.<key>`（lang/strings.json 的键，三语齐全）；这里不写死一句用户看得见的中文
 *     —— 唯一例外是 `data-i18n` 漏翻时的兜底（那种情况初始 HTML 里已经有一份中文）。
 *   · 颜色只来自 web/styles/screens/api_guide.css 的类名，这里不写行内 color。
 */
window.ApiGuideScreen = (function (global) {
  'use strict';

  var mounted = false;
  var step = 0;                 // 向导当前步（0/1/2）
  var picked = null;            // 选中的服务商 id
  var keyDraft = '';            // 第②步的 Key（只在内存里，不写 localStorage）
  var testState = '';           // '' | 'testing' | 'ok' | 'err:<原因>|<下一步>'
  var freeMode = false;         // 用户点了「稍后再说」→ 进免费链模式

  /* ---------- 小工具：文案 / 元素 ---------- */
  /* 文案：一律写成 `pick(T.key)`，不写 `pick(动态键名)`。
     理由：tools/gen_i18n.py 的"谁在用这个键"只认**字面量** `T.xxx` / `T['xxx']` /
     `data-i18n`，写成 pick(T.xxx) 会让整套键被判成死键（tests/test_i18n_langs.py ⑤ 会红）。 */
  function pick(v, fallback) {
    return (v == null || v === '') ? (fallback || '') : String(v);
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = String(text); }
    return e;
  }
  function btn(props) {
    return global.DICK.components.Button(props);
  }

  /* ---------- 服务商事实表（教程用：6 家，含免 Key 那几家） ----------
     URL / Base / 模型名是语言无关的事实，所以三语同串；说明性文字才翻译。
     这张表与后端 PROVIDERS 是两回事：这里是"去哪注册、填什么"，那边是"程序真能连谁"。 */
  function providerFacts() {
    return [
      { name: pick(T.guide_p1_name), url: pick(T.guide_p1_url), base: pick(T.guide_p1_base),
        model: pick(T.guide_p1_model), buy: pick(T.guide_p1_buy), where: pick(T.guide_p1_where) },
      { name: pick(T.guide_p2_name), url: pick(T.guide_p2_url), base: pick(T.guide_p2_base),
        model: pick(T.guide_p2_model), buy: pick(T.guide_p2_buy), where: pick(T.guide_p2_where) },
      { name: pick(T.guide_p3_name), url: pick(T.guide_p3_url), base: pick(T.guide_p3_base),
        model: pick(T.guide_p3_model), buy: pick(T.guide_p3_buy), where: pick(T.guide_p3_where) },
      { name: pick(T.guide_p4_name), url: pick(T.guide_p4_url), base: pick(T.guide_p4_base),
        model: pick(T.guide_p4_model), buy: pick(T.guide_p4_buy), where: pick(T.guide_p4_where) },
      { name: pick(T.guide_p5_name), url: pick(T.guide_p5_url), base: pick(T.guide_p5_base),
        model: pick(T.guide_p5_model), buy: pick(T.guide_p5_buy), where: pick(T.guide_p5_where) },
      { name: pick(T.guide_p6_name), url: pick(T.guide_p6_url), base: pick(T.guide_p6_base),
        model: pick(T.guide_p6_model), buy: pick(T.guide_p6_buy), where: pick(T.guide_p6_where) }
    ];
  }

  /* 后端"程序真能连"的服务商（state().providers）；取不到时退回只含 DeepSeek 的一条。 */
  function appProviders() {
    var list = (global.PROVIDERS && global.PROVIDERS.length) ? global.PROVIDERS : [];
    return list.length ? list : [{ id: 'deepseek', name: 'DeepSeek', free: false,
      base_url: 'https://api.deepseek.com', models: ['deepseek-flash'],
      buy_url: 'https://platform.deepseek.com/' }];
  }

  /* 「去哪里拿 Key」：能对上教程哪一行就用那一行的注册地址，否则用后端给的 buy_url。 */
  function whereUrl(p) {
    var map = { deepseek: 'guide_p1_url', zhipu: 'guide_p2_url',
      siliconflow: 'guide_p3_url', ollama: 'guide_p6_url' };
    var k = map[p.id];
    return (map[p.id] && (map[p.id] === 'guide_p1_url' ? pick(T.guide_p1_url)
      : map[p.id] === 'guide_p2_url' ? pick(T.guide_p2_url)
      : map[p.id] === 'guide_p3_url' ? pick(T.guide_p3_url)
      : pick(T.guide_p6_url))) || p.buy_url || '';
  }

  /* ---------- ① 教程面板 ---------- */
  function section(title, bodyNode) {
    var sec = el('div', 'ag-sec');
    if (title) { sec.appendChild(el('div', 'ag-h', title)); }
    sec.appendChild(bodyNode);
    return sec;
  }

  function buildGuide() {
    var body = document.getElementById('apiGuideBody');
    if (!body) { return; }
    body.innerHTML = '';

    /* 怎么选模型 */
    var pick = el('div', 'ag-sub');
    [pick(T.guidePickChat), pick(T.guidePickReason), pick(T.guidePickFree)].forEach(function (line, i) {
      var row = el('div', 'ag-row');
      row.appendChild(el('span', 'ag-k', String(i + 1)));
      row.appendChild(el('span', null, line));
      pick.appendChild(row);
    });
    body.appendChild(section(pick(T.guidePickTitle), pick));

    /* 服务商清单 */
    var list = el('div');
    providerFacts().forEach(function (p) {
      var card = el('div', 'ag-prov');
      card.appendChild(el('div', 'ag-pname', p.name));
      var rows = [
        [pick(T.guideLabelUrl), p.url, true],
        [pick(T.guideLabelBuy), p.buy, false],
        [pick(T.apiWizWhere), p.where, false],
        [pick(T.st_base_url), p.base, false],
        [pick(T.st_model), p.model, false]
      ];
      rows.forEach(function (r) {
        var kv = el('div', 'ag-kv');
        kv.appendChild(el('b', null, r[0] + '：'));
        if (r[2]) {
          var a = el('span', 'ag-link', r[1]);
          a.setAttribute('role', 'link');
          a.onclick = function () {
            try { global.pywebview.api.open_url(r[1]); } catch (e) { /* 非网页壳里没有 pywebview */ }
          };
          kv.appendChild(a);
        } else {
          kv.appendChild(el('span', null, r[1]));
        }
        card.appendChild(kv);
      });
      list.appendChild(card);
    });
    body.appendChild(section(pick(T.apiGuideTitle), list));

    /* 三步配置 */
    var steps = el('div');
    [pick(T.guideStep1), pick(T.guideStep2), pick(T.guideStep3)].forEach(function (line, i) {
      var row = el('div', 'ag-row');
      row.appendChild(el('span', 'ag-k', String(i + 1)));
      row.appendChild(el('span', null, line));
      steps.appendChild(row);
    });
    body.appendChild(section(pick(T.apiWizTitle), steps));

    /* 常见错误对照表 */
    var errs = el('div', 'ag-err');
    [[T.guideErr1S, T.guideErr1F], [T.guideErr2S, T.guideErr2F],
      [T.guideErr3S, T.guideErr3F], [T.guideErr4S, T.guideErr4F],
      [T.guideErr5S, T.guideErr5F]].forEach(function (pr) {
      errs.appendChild(el('div', 'ag-es', pick(pr[0])));
      errs.appendChild(el('div', 'ag-ef', pick(pr[1])));
    });
    body.appendChild(section(pick(T.guideErrTitle), errs));

    /* 免费链 / 省钱 / 官方搜索 / 免责 */
    [[T.guideFreeTitle, T.guideFreeBody], [T.guideTipTitle, T.guideTipBody],
      [T.guideSearchTitle, T.guideSearchBody]].forEach(function (pr) {
      body.appendChild(section(pick(pr[0]), el('div', 'ag-sub', pick(pr[1]))));
    });
    body.appendChild(section(null, el('div', 'ag-sub', pick(T.guideFooter))));
  }

  function openGuide() {
    buildGuide();
    var m = document.getElementById('apiGuideModal');
    if (m) { m.classList.add('open'); }
  }
  function closeGuide() {
    var m = document.getElementById('apiGuideModal');
    if (m) { m.classList.remove('open'); }
  }

  /* ---------- ② 首启向导 ---------- */
  function renderSteps() {
    var box = document.getElementById('apiWizSteps');
    if (!box) { return; }
    box.innerHTML = '';
    [pick(T.apiWizStep1), pick(T.apiWizStep2), pick(T.apiWizStep3)].forEach(function (label, i) {
      box.appendChild(el('div', 'aw-pill' + (i === step ? ' on' : ''), label));
    });
  }

  function renderFoot() {
    var foot = document.getElementById('apiWizFoot');
    if (!foot) { return; }
    foot.innerHTML = '';
    var grow = el('div', 'aw-grow');
    foot.appendChild(grow);
    if (step > 0) {
      foot.appendChild(btn({ label: pick(T.apiWizPrev), variant: 'ghost', size: 'sm',
        onClick: function () { step -= 1; testState = ''; renderWizard(); } }));
    }
    if (step < 2) {
      foot.appendChild(btn({ label: pick(T.apiWizNext), variant: 'primary', size: 'sm',
        onClick: function () {
          if (step === 0 && !picked) { return; }
          step += 1; testState = ''; renderWizard();
        } }));
    } else {
      foot.appendChild(btn({ label: pick(T.apiWizStep3), variant: 'primary', size: 'sm',
        onClick: runTest }));
    }
    var later = el('span', 'aw-later', pick(T.apiWizLater));
    later.onclick = useFreeChain;
    foot.appendChild(later);
  }

  function renderWizard() {
    renderSteps();
    var body = document.getElementById('apiWizBody');
    if (!body) { return; }
    body.innerHTML = '';
    var cur = appProviders().filter(function (p) { return p.id === picked; })[0];

    if (step === 0) {
      var cards = el('div', 'aw-cards');
      appProviders().forEach(function (p) {
        var c = el('div', 'aw-card' + (p.id === picked ? ' on' : ''));
        c.appendChild(el('span', 'aw-cn', p.name));
        c.appendChild(el('span', 'aw-cb',
          (p.base_url || '') + (p.free ? ' · ' + pick(T.apiWizFree) : '')));
        c.onclick = function () {
          picked = p.id;
          var ms = p.models || [];
          keyDraft = (global.apiKeysMap && global.apiKeysMap[p.id]) || '';
          if (!p.free && ms.length) { /* 模型留给后端按默认填，这里不覆盖用户的设置 */ }
          renderWizard();
        };
        cards.appendChild(c);
      });
      body.appendChild(cards);
    } else if (step === 1) {
      var wrap = el('div');
      wrap.appendChild(el('div', 'ag-h', cur ? cur.name : ''));
      var inp = el('input', 'aw-key');
      inp.type = 'text';
      inp.setAttribute('autocomplete', 'off');
      inp.setAttribute('autocapitalize', 'off');
      inp.setAttribute('spellcheck', 'false');
      inp.placeholder = (cur && cur.free) ? pick(T.apiWizFree) : 'sk-...';
      inp.value = keyDraft;
      inp.disabled = !!(cur && cur.free);
      inp.oninput = function () { keyDraft = inp.value; };
      wrap.appendChild(inp);
      if (cur) {
        var meta = el('div', 'aw-meta');
        meta.appendChild(el('div', null, pick(T.st_base_url) + ': ' + (cur.base_url || '')));
        meta.appendChild(el('div', null, pick(T.st_model) + ': ' +
          ((cur.models && cur.models[0]) || '')));
        var w = whereUrl(cur);
        if (w && !cur.free) {
          var a = el('span', 'ag-link', pick(T.apiWizWhere) + ' → ' + w);
          a.onclick = function () {
            try { global.pywebview.api.open_url(w); } catch (e) { /* 忽略 */ }
          };
          meta.appendChild(a);
        }
        wrap.appendChild(meta);
      }
      body.appendChild(wrap);
    } else {
      var box = el('div');
      box.appendChild(el('div', 'ag-h', cur ? cur.name : ''));
      var meta2 = el('div', 'aw-meta');
      meta2.appendChild(el('div', null, pick(T.st_base_url) + ': ' + (cur ? cur.base_url : '')));
      meta2.appendChild(el('div', null, pick(T.st_model) + ': ' +
        (cur && cur.models ? cur.models[0] : '')));
      box.appendChild(meta2);
      var res = el('div', 'aw-res');
      if (testState === 'testing') {
        res.textContent = pick(T.apiWizTesting);
      } else if (testState === 'ok') {
        res.className = 'aw-res ok';
        res.textContent = pick(T.apiWizOk);
      } else if (testState.indexOf('err:') === 0) {
        var parts = testState.slice(4).split('|');
        res.className = 'aw-res err';
        res.textContent = pick(T.apiWizFail) + ' — ' + (parts[0] || '') +
          (parts[1] ? '  ·  ' + parts[1] : '');
      }
      box.appendChild(res);
      body.appendChild(box);
    }
    renderFoot();
  }

  /* 真连一次：成功才落盘。失败把人话原因 + 下一步建议一起显示出来。 */
  function runTest() {
    var cur = appProviders().filter(function (p) { return p.id === picked; })[0];
    if (!cur) { return; }
    testState = 'testing';
    renderWizard();
    var key = (cur.free ? '' : keyDraft);
    var base = cur.base_url || '';
    var model = (cur.models && cur.models[0]) || '';
    var done = function (r) {
      if (r && r.ok) {
        testState = 'ok';
        freeMode = false;
        try { global.localStorage.setItem('dick.apiWizard', 'done'); } catch (e) { /* 隐私模式 */ }
        renderWizard();
        setTimeout(closeWizard, 700);
      } else {
        testState = 'err:' + ((r && r.err) || '?') + '|' + ((r && r.hint) || '');
        renderWizard();
      }
    };
    try {
      global.pywebview.api.test_and_save_key(key, base, model, picked).then(done, function (e) {
        done({ ok: false, err: String(e), hint: pick(T.guideErr4F) });
      });
    } catch (e) {
      // 非 pywebview 环境（直接拿浏览器开 i<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ndex.html）：只做本地保存，别假装测通了
      done({ ok: false, err: String(e), hint: '' });
    }
  }

  /* 「稍后再说」= 进入免费链模式：挑第一家有 free 标记的服务商直接保存（不需要 Key）。 */
  function useFreeChain() {
    var free = appProviders().filter(function (p) { return p.free; })[0];
    if (!free) { closeWizard(); return; }
    picked = free.id;
    keyDraft = '';
    testState = 'testing';
    step = 2;
    renderWizard();
    try {
      global.pywebview.api.test_and_save_key('', free.base_url || '',
        (free.models && free.models[0]) || '', free.id).then(function (r) {
        testState = (r && r.ok) ? 'ok' : ('err:' + ((r && r.err) || '?') + '|' + ((r && r.hint) || ''));
        freeMode = !!(r && r.ok);
        if (freeMode) {
          try { global.localStorage.setItem('dick.apiWizard', 'free'); } catch (e) { /* 忽略 */ }
        }
        renderWizard();
        if (freeMode) { setTimeout(closeWizard, 600); }
      }, function () { closeWizard(); });
    } catch (e) {
      closeWizard();
    }
  }

  function openWizard(force) {
    // 已经配好 Key（且用户没强制重开）就别打扰
    if (!force) {
      try {
        if (global.localStorage.getItem('dick.apiWizard') === 'done') { return; }
      } catch (e) { /* 忽略 */ }
    }
    step = 0;
    testState = '';
    if (!picked) {
      var list = appProviders();
      var ds = list.filter(function (p) { return p.id === 'deepseek'; })[0];
      picked = (ds || list[0]).id;
    }
    renderWizard();
    var m = document.getElementById('apiWizModal');
    if (m) { m.classList.add('open'); }
  }
  function closeWizard() {
    var m = document.getElementById('apiWizModal');
    if (m) { m.classList.remove('open'); }
  }

  /* ---------- 挂载 ---------- */
  function mount() {
    if (mounted) { return; }
    if (!document.getElementById('apiGuideModal') || !document.getElementById('apiWizModal')) {
      console.error('[api_guide] 片段没注入，跳过挂载');
      return;
    }
    mounted = true;
    var cl = document.getElementById('apiGuideClose');
    if (cl) { cl.onclick = closeGuide; }
    // 点遮罩关闭（.modal 本身是遮罩，点它而不是 .modal-box 才算）
    ['apiGuideModal', 'apiWizModal'].forEach(function (id) {
      var m = document.getElementById(id);
      m.addEventListener('click', function (e) { if (e.target === m) { m.classList.remove('open'); } });
    });
    global.DICK.bus.on('api:guide', openGuide);
    global.DICK.bus.on('api:wizard', function () { openWizard(true); });
    global.DICK.bus.on('api:wizard:auto', function () { openWizard(false); });
  }
  function unmount() { mounted = false; }

  return {
    mount: mount, unmount: unmount,
    openGuide: openGuide, closeGuide: closeGuide,
    openWizard: openWizard, closeWizard: closeWizard
  };
})(window);

DICK.router.register('api_guide', { fragment: 'screens/api_guide.html', module: window.ApiGuideScreen });

/* 兼容入口：
   · apiGuideOpen()       —— 老代码/控制台直接开教程；
   · apiWizardAutoOpen()  —— index.html 在拿到 state() 之后调：没 Key 且没选免费链就弹向导。 */
function apiGuideOpen() { window.ApiGuideScreen.openGuide(); }
function apiWizardOpen() { window.ApiGuideScreen.openWizard(true); }
function apiWizardAutoOpen() { window.ApiGuideScreen.openWizard(false); }
