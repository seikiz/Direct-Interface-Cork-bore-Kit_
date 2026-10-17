/* web/js/screens/crop.js —— ✂️ 图片裁剪屏（阶段 2：从 index.html 的顶层代码整块搬出，零行为变化）
 *
 * 归属
 *   结构：web/screens/crop.html（index.html 里原位只剩挂载点 <!--@screen:crop-->；
 *         它原来也嵌在 #inputbar 里，挂载点就在同一位置）
 *   样式：没有专属 css 块（舞台/遮罩/缩放条都是行内 style），所以不需要 screens/crop.css。
 * 契约：router 注入片段后调 mount()。
 * 本屏依赖的外部符号（阶段 3/4/5 的收尾清单）
 *   · pywebview.api.set_avatar(target, b64, 'png')：后端落头像文件
 *   · avatarCache / reloadRoles()：**角色列表所在的聊天屏的东西**。裁剪完要让角色列表
 *     重画头像，现在是直接写对方的缓存、调对方的函数 —— 应该改成
 *     DICK.bus.emit('avatar:changed', {target})，由聊天屏自己订阅重画。留在阶段 3 收。
 *   · 入口是 #fileInput 的 change（聊天屏的隐藏文件框）：cropOpen(target, dataUrl, ext)。
 */
window.CropScreen = (function (global) {
  'use strict';

  var mounted = false;

  // ===== 头像<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌裁剪 =====
  var cropState = { img: null, target: '', ext: 'png', zoom: 100, dx: 0, dy: 0, box: 200, dragging: false, sx: 0, sy: 0, ox: 0, oy: 0 };

  function cropOpen(target, dataUrl, ext) {
    cropState.target = target; cropState.ext = ext;
    cropState.zoom = 100; cropState.dx = 0; cropState.dy = 0;
    var img = document.getElementById('cropImg');
    img.src = dataUrl;
    img.onload = function () {
      cropState.img = img;
      document.getElementById('cropZoom').value = 100;
      document.getElementById('cropModal').classList.add('open');
      cropRender();
    };
  }

  function cropRender() {
    var img = cropState.img;
    if (!img) return;
    var stage = document.getElementById('cropStage');
    var sw = stage.clientWidth, sh = stage.clientHeight;
    var box = 200;
    var z = cropState.zoom / 100;
    var iw = img.naturalWidth, ih = img.naturalHeight;
    var scale = Math.max(sw / iw, sh / ih) * z;
    var w = iw * scale, h = ih * scale;
    // 以舞台中心为锚点：缩放时保持中心点不动
    var anchorX = sw / 2, anchorY = sh / 2;
    // 图片中心当前指向的位置
    var imgCx = cropState.dx + (cropState.lastW || w) / 2;
    var imgCy = cropState.dy + (cropState.lastH || h) / 2;
    // 新位置：让图片中心保持相对锚点偏移
    cropState.dx = anchorX + (imgCx - anchorX) - w / 2;
    cropState.dy = anchorY + (imgCy - anchorY) - h / 2;
    cropState.lastW = w; cropState.lastH = h;
    img.style.width = w + 'px';
    img.style.height = h + 'px';
    img.style.left = cropState.dx + 'px';
    img.style.top = cropState.dy + 'px';
  }

  /* ---------------- 挂载 / 卸载（router 注入片段之后调用） ---------------- */
  function mount() {
    if (mounted) { return; }
    mounted = true;
    if (!document.getElementById('cropModal')) {
      console.error('[crop] 片段没注入（找不到 #cropModal），这一屏跳过挂载');
      mounted = false;
      return;
    }
    document.getElementById('cropZoom').addEventListener('input', function () {
      cropState.zoom = parseInt(this.value, 10);
      cropRender();
    });
    document.getElementById('cropImg').addEventListener('mousedown', function (e) {
      cropState.dragging = true;
      cropState.sx = e.clientX; cropState.sy = e.clientY;
      cropState.ox = cropState.dx; cropState.oy = cropState.dy;
      e.preventDefault();
    });
    document.addEventListener('mousemove', function (e) {
      if (!cropState.dragging || !cropState.img) return;
      cropState.dx = cropState.ox + (e.clientX - cropState.sx);
      cropState.dy = cropState.oy + (e.clientY - cropState.sy);
      cropState.img.style.left = cropState.dx + 'px';
      cropState.img.style.top = cropState.dy + 'px';
    });
    document.addEventListener('mouseup', function () { cropState.dragging = false; });
    document.getElementById('cropCancelBtn').onclick = function () {
      document.getElementById('cropModal').classList.remove('open');
      cropState.img = null;
    };
    document.getElementById('cropOkBtn').onclick = function () {
      var img = cropState.img;
      if (!img) { document.getElementById('cropModal').classList.remove('open'); return; }
      var stage = document.getElementById('cropStage');
      var sw = stage.clientWidth, sh = stage.clientHeight;
      var box = 200;
      var z = cropState.zoom / 100;
      var scale = Math.max(sw / img.naturalWidth, sh / img.naturalHeight) * z;
      var iw = img.naturalWidth * scale, ih = img.naturalHeight * scale;
      // 裁剪框中心 = 舞台中心
      var cx = sw / 2, cy = sh / 2;
      // 图片上对应的源坐标
      var srcX = (cx - box / 2 - cropState.dx) / scale;
      var srcY = (cy - box / 2 - cropState.dy) / scale;
      var srcSize = box / scale;
      // 限制在图片范围内
      srcX = Math.max(0, Math.min(img.naturalWidth - srcSize, srcX));
      srcY = Math.max(0, Math.min(img.naturalHeight - srcSize, srcY));
      // 输出 256x256
      var out = document.createElement('canvas');
      out.width = 256; out.height = 256;
      var ctx = out.getContext('2d');
      ctx.drawImage(img, srcX, srcY, srcSize, srcSize, 0, 0, 256, 256);
      var dataUrl = out.toDataURL('image/png');
      pywebview.api.set_avatar(cropState.target, dataUrl.split(',')[1], 'png').then(function (r) {
        if (r && r.ok) {
          avatarCache[cropState.target] = undefined;
          reloadRoles();
        }
      });
      document.getElementById('cropModal').classList.remove('open');
      cropState.img = null;
    };
  }

  function unmount() {
    // 拖动/缩放那几个监听里有两个挂在 document 上（mousemove/mouseup）。它们的回调是匿名函数，
    // 搬的时候要一字不改，所以没有留引用可摘 —— 但两个回调都以 cropState.dragging 为闸门，
    // 没在拖动就什么都不做；mount() 有 mounted 幂等闸，不会重复注册。
    cropState.dragging = false;
    cropState.img = null;
    mounted = false;
  }

  return {
    mount: mount, unmount: unmount,
    open: cropOpen, render: cropRender,
    state: function () { return cropState; }
  };
})(window);

/* ===== 兼容入口（阶段 3/4/5 清理）=====
 * cropOpen 原来由 #fileInput 的 change 处理器直接调，现在改名到模块里，
 * 但保留同名全局，免得别处（插件/老脚本）找不到。 */
function cropOpen(target, dataUrl, ext) { return window.CropScreen.open(target, dataUrl, ext); }
function cropRender() { return window.CropScreen.render(); }

// 注册到路由：片段 = screens/crop.html（相对 web/index.html），模块 = 上面这个 IIFE
DICK.router.register('crop', { fragment: 'screens/crop.html', module: window.CropScreen });
