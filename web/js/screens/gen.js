/* web/js/screens/gen.js —— 🎨 生图屏（阶段 2：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 归属
 *   结构：web/screens/gen.html（index.html 里原位只剩挂载点 <!--@screen:gen-->；
 *         注意它原来就嵌在 #inputbar 里，挂载点也在同一位置，DOM 层级一点没动）
 *   样式：没有专属 css 块（都是行内 style），所以不需要 web/styles/screens/gen.css。
 * 契约：router 注入片段后调 mount()。
 * 本屏依赖的外部符号（阶段 3/4/5 的收尾清单）
 *   · pywebview.api.gen_presets() / gen_image(…)：后端在 image_gen.py
 *   · alert()：错误提示还是原生弹窗（深色主题下会闪白框）——这是原有的行为，
 *     本轮只搬结构不改交互，所以原样留着；阶段 5 应该换成外壳的 toast。
 *   · #stImgBackend / #stImgBase：**设置屏的两个输入框**。genHintByBackend() 靠读它们
 *     判断「当前后端吃不吃负面提示词」—— 这是本屏唯一一处跨屏读 DOM，应该由设置屏
 *     set 到 DICK.state（例如 'img.backend'）后本屏订阅；留在阶段 3 收。
 */
window.GenScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ---------- 生<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌图 ----------
  var genPresets = [];
  var genLast = {};            // 上次生图的输入（由 state 回填，后端也记着）
  function applyGenLast(last) {
    if (!last || typeof last !== 'object') return;
    genLast = last;
    var set = function (id, v) { var el = document.getElementById(id); if (el && v !== undefined && v !== null) el.value = v; };
    set('genPrompt', last.prompt);
    set('genExtra', last.extra);
    set('genNegative', last.negative_prompt);
    set('genSize', last.size);
    set('genSeed', last.seed === undefined || last.seed === null ? '' : last.seed);
    if (last.preset) {
      var sel = document.getElementById('genPreset');
      if (sel) sel.value = last.preset;
    }
  }
  function loadGenPresets() {
    pywebview.api.gen_presets().then(function (r) {
      if (r && r.ok && r.presets) {
        genPresets = r.presets;
        var sel = document.getElementById('genPreset');
        var keep = sel.value || (genLast && genLast.preset) || '';
        sel.innerHTML = '';
        r.presets.forEach(function (p) {
          var o = document.createElement('option');
          o.value = p.id; o.textContent = p.label + (p.custom ? ' ★' : '');
          sel.appendChild(o);
        });
        if (keep) sel.value = keep;
        if (!sel.value && r.presets.length) sel.value = r.presets[0].id;
        sel.onchange = function () {
          var p = genPresets.find(function (x) { return x.id === sel.value; });
          document.getElementById('genPresetDesc').textContent = p ? p.desc : '';
        };
        sel.onchange();
      }
    });
  }
  function genRun() {
    var prompt = document.getElementById('genPrompt').value.trim();
    if (!prompt) { alert('请输入画面内容'); return; }
    var go = document.getElementById('genGo');
    go.disabled = true; go.textContent = '⏳ 生成中...';
    var preset = document.getElementById('genPreset').value;
    var size = document.getElementById('genSize').value;
    var neg = document.getElementById('genNegative').value.trim();
    var extra = document.getElementById('genExtra').value.trim();
    var seed = document.getElementById('genSeed').value.trim();
    document.getElementById('genNote').textContent = '生成中，本地模型可能要几十秒…';
    pywebview.api.gen_image(prompt, preset, size, neg, extra, seed).then(function (r) {
      go.disabled = false; go.textContent = '✨ 生成';
      if (r && r.ok && r.image) {
        document.getElementById('genResultImg').src = r.image;
        document.getElementById('genResult').style.display = 'block';
        if (r.seed !== undefined && r.seed !== null) document.getElementById('genSeed').value = r.seed;
        document.getElementById('genNote').textContent =
          (r.backend ? '后端：' + r.backend + '　' : '') + (r.note || '');
        genLast = { prompt: prompt, preset: preset, size: size,
                    negative_prompt: neg, extra: extra, seed: r.seed };
      } else {
        document.getElementById('genNote').textContent = (r && r.err) || '生成失败';
        alert((r && r.err) || '生成失败');
      }
    }).catch(function () {
      go.disabled = false; go.textContent = '✨ 生成';
      document.getElementById('genNote').textContent = '生成异常，看控制台/日志';
    });
  }
  // 后端不同，能用的参数也不同：负面提示词只有兼容端点/本地 SD 吃
  function genHintByBackend() {
    var be = (document.getElementById('stImgBackend') || {}).value || 'auto';
    var base = (document.getElementById('stImgBase') || {}).value || '';
    if (be === 'auto') {
      if (/pollinations/i.test(base)) be = 'pollinations';
      else if (/:8188|comfyui/i.test(base)) be = 'comfyui';
      else if (/:7860|sdwebui|a1111|forge|fooocus/i.test(base)) be = 'sdwebui';
      else be = 'openai';
    }
    var hint = document.getElementById('genNegativeHint');
    if (!hint) return;
    hint.textContent = (be === 'pollinations')
      ? '免 Key 后端不支持负面提示词（填了会被忽略）；风格词建议写进「补充风格词」。'
      : (be === 'comfyui' ? '本地 ComfyUI：负面提示词会进 7 号节点；尺寸以 512 的倍数为佳。' : '');
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    mounted = true;
    if (!document.getElementById('genImgModal')) {
      console.error('[gen] 片段没注入（找不到 #genImgModal），这一屏跳过挂载');
      mounted = false;
      return;
    }
    document.getElementById('genImgBtn').onclick = function () {
      loadGenPresets();
      genHintByBackend();
      document.getElementById('genResult').style.display = 'none';
      document.getElementById('genNote').textContent = '';
      document.getElementById('genImgModal').classList.add('open');
    };
    document.getElementById('genGo').onclick = function () { genRun(); };
    document.getElementById('genReroll').onclick = function () {
      // 重抽 = 换个随机种子再生成（同一个种子能复现同一张，挑到满意的就把种子留下）
      document.getElementById('genSeed').value = Math.floor(Math.random() * 1000000000);
      genRun();
    };
  }

  function unmount() {
    // 本屏没有定时器/全局监听：面板一关就是结束，off 掉按钮避免闭包留着
    if (document.getElementById('genImgBtn')) { document.getElementById('genImgBtn').onclick = null; }
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    run: genRun, applyLast: applyGenLast, loadPresets: loadGenPresets,
    hintByBackend: genHintByBackend,
    last: function () { return genLast; }
  };
})(window);

/* ===== 兼容入口（阶段 3/4/5 清理）=====
 * 搬家之前这四个是 index.html 里的顶层全局函数，设置屏（stRender / 保存生图设置 / 保存预设）
 * 还在直接叫它们。同名全局保留，内部转调模块。 */
function applyGenLast(last) { return window.GenScreen.applyLast(last); }
function loadGenPresets() { return window.GenScreen.loadPresets(); }
function genRun() { return window.GenScreen.run(); }
function genHintByBackend() { return window.GenScreen.hintByBackend(); }

// 注册到路由：片段 = screens/gen.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('gen', { fragment: 'screens/gen.html', module: window.GenScreen });
