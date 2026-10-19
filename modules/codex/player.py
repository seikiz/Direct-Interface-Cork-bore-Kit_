# -*- coding: utf-8 -*-
"""modules/codex/player.py —— 独立播放器：单文件 HTML 的渲染与导出

搬家来源：`codex_core.py` 的 `_inject_signature` / `build_standalone_html` /
`STANDALONE_PLAYER_HTML` / `_EDITABLE_JS` / `DEFAULT_EDITABLE_TEMPLATE` /
`render_standalone` / `build_standalone_file` / `_load_custom_template`，
**模板与注入点一字未改**。

两处刻意的边界：
  ① **水印由宿主注入**：原来这里 `import dick_mark`（仓库根的宿主模块）—— 块搬去别的
     项目当场 ModuleNotFoundError。现在 `mark=None` 参数由 `service.bind(host)` 送进来；
     没给就跳过（与原 `try/except` 的降级行为一致）。
  ② **模板路径由调用方给**：`_load_custom_template(pkg_dir)` 只读包内 `player.html`，
     不碰任何全局目录，所以这一层照样能脱离宿主被测试。
"""

import json
import os

from .constants import SUBDIRS
from .player_js import STANDALONE_PLAYER_JS


def _inject_signature(script, mark=None):
    """架构级水印：给剧本注入 _signature（抄格式/抄剧本都带走来源标识）"""
    try:
        if mark is not None and isinstance(script, dict) \
                and not script.get("_signature"):
            script["_signature"] = mark.mark_dict()
    except Exception:
        pass
    return script


def build_standalone_html(pkg_dir, embed_script=True, mark=None):
    """把 CODEX 包打包成单文件 HTML：资源全部 base64 内嵌 + 独立播放器 JS。
    embed_script=True 时把播放器脚本内嵌；否则引用同目录 codex_player.js（供外部播放器复用）。
    返回 (html 字符串, 资源统计)"""
    import base64 as _b64
    pkg_dir = os.path.abspath(pkg_dir)
    jp = os.path.join(pkg_dir, "codex.json")
    if not os.path.isfile(jp):
        raise FileNotFoundError("codex.json 不存在")
    with open(jp, "r", encoding="utf-8") as f:
        script = json.load(f)
    script = _inject_signature(script, mark)
    assets = {}   # kind -> {relname: dataURL}
    counts = {}
    for kind in SUBDIRS:
        kd = os.path.join(pkg_dir, kind)
        assets[kind] = {}
        if not os.path.isdir(kd):
            continue
        for fn in sorted(os.listdir(kd)):
            p = os.path.join(kd, fn)
            if not os.path.isfile(p):
                continue
            with open(p, "rb") as f:
                raw = f.read()
            ext = os.path.splitext(fn)[1].lower()
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif",
                    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
                    ".flac": "audio/flac", ".mp4": "audio/mp4", ".m4a": "audio/mp4"}.get(ext, "application/octet-stream")
            assets[kind][fn] = "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")
            counts[kind] = counts.get(kind, 0) + 1
    payload = {
        "script": script,
        "assets": assets,
    }
    embed = json.dumps(payload, ensure_ascii=False)
    return embed, counts


def build_standalone_file(pkg_dir, out_path=None, mark=None):
    """生成独立单文件 HTML（打包 GALGAME）。返回 (成功?, 输出路径或错误)。
    若包内有 player.html 自定义模板则用之，否则用系统内置模板。"""
    pkg = os.path.abspath(pkg_dir)
    tpl = _load_custom_template(pkg)
    html, counts = render_standalone(pkg, tpl, mark=mark)
    if out_path is None:
        out_path = os.path.join(os.path.dirname(pkg),
                                _safe_name(os.path.basename(pkg)) + ".html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return True, out_path, counts


def _load_custom_template(pkg_dir):
    """读包内 player.html（高级自定义模板）；无则返回 None（用系统默认）。"""
    pt = os.path.join(os.path.abspath(pkg_dir), "player.html")
    if os.path.isfile(pt):
        try:
            with open(pt, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


STANDALONE_PLAYER_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<!-- DICK-MARK -->
<title>CODEX GALGAME</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:100%; height:100%; overflow:hidden; background:#000; font-family:"Microsoft YaHei",sans-serif; }
  #cxBg { position:absolute; inset:0; background-size:cover<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌; background-position:center; background-color:#0a0a12; }
  @keyframes cxshake { 0%{transform:translate(0,0)} 25%{transform:translate(6px,-4px)} 50%{transform:translate(-5px,5px)} 75%{transform:translate(4px,2px)} 100%{transform:translate(0,0)} }
  #cxSprites { position:absolute; left:0; right:0; bottom:120px; top:40px; pointer-events:none; z-index:2; }
  #cxTextbox { position:absolute; left:0; right:0; bottom:0; padding:18px 24px 26px;
    background:linear-gradient(transparent,rgba(0,0,0,.92) 35%); min-height:150px; cursor:pointer; }
  #cxSpeaker { font-size:17px; font-weight:bold; color:#ffd76e; margin-bottom:6px; display:none; }
  #cxText { font-size:18px; line-height:1.7; color:#eee; min-height:58px; white-space:pre-wrap; }
  #cxChoice { margin-top:12px; display:none; }
  #cxNote { font-size:14px; color:#9aa; font-style:italic; min-height:20px; }
  .topbtns { position:absolute; top:10px; right:12px; display:flex; gap:6px; z-index:10; }
  .topbtns button { background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.25); color:#ddd;
    border-radius:6px; padding:5px 10px; font-size:12px; cursor:pointer; }
  .topbtns button:hover { background:rgba(255,255,255,.2); }
  #cxTitle { position:absolute; inset:0; display:none; background:rgba(0,0,0,.94); z-index:5;
    flex-direction:column; align-items:center; justify-content:center; text-align:center; cursor:pointer; }
  #cxTitleName { font-size:34px; font-weight:bold; color:#ffd76e; margin-bottom:10px; }
  #cxTitleIntro { font-size:15px; color:#bbb; max-width:560px; line-height:1.8; white-space:pre-wrap; }
  #cxEnd { position:absolute; inset:0; display:none; z-index:5; flex-direction:column; align-items:center;
    justify-content:center; text-align:center; cursor:pointer;
    background:radial-gradient(circle at 50% 40%,rgba(255,215,110,.12),#000 70%); }
  #cxEndTitle { font-size:28px; font-weight:bold; color:#ffd76e; margin-bottom:8px; }
</style>
</head>
<body>
<div id="cxBg"></div>
<div id="cxSprites"></div>
<div id="cxTextbox">
  <div id="cxSpeaker"></div>
  <div id="cxText"></div>
  <div id="cxChoice"></div>
  <div id="cxNote"></div>
</div>
<div class="topbtns">
  <button id="cxSave">💾 存档</button>
  <button id="cxLoad">📂 读档</button>
  <button id="cxRewind">⏪ 回溯</button>
  <button id="cxAuto">⏩ 自动</button>
</div>
<div id="cxTitle">
  <div id="cxTitleName"></div>
  <div id="cxTitleIntro"></div>
  <div style="margin-top:26px;font-size:13px;color:#777">点击开始 ▸</div>
</div>
<div id="cxEnd">
  <div id="cxEndTitle"></div>
  <div style="font-size:13px;color:#888">— END —</div>
  <div style="margin-top:22px;font-size:13px;color:#777">点击重新开始</div>
</div>
<script>
__CODEX_EMBED__
</script>
</body>
</html>
"""


# ---------- 高级：可编辑播放器模板（现场改 GALGAME 代码） ----------
# DEFAULT_EDITABLE_TEMPLATE = 系统内置的完整播放器源（HTML + 内联播放器 JS），
# 其中数据注入点为 __CODEX_PAYLOAD__。高级用户可直接改这份模板，换掉任何 HTML/CSS/JS，
# 只需保留 __CODEX_PAYLOAD__（打包/试玩时替换为真实剧本资源数据）。
_EDITABLE_JS = "var __CODEX_DATA__ = __CODEX_PAYLOAD__;\n" + STANDALONE_PLAYER_JS
DEFAULT_EDITABLE_TEMPLATE = STANDALONE_PLAYER_HTML.replace("__CODEX_EMBED__", _EDITABLE_JS)


def render_standalone(pkg_dir, template_html=None, state=None, mark=None):
    """根据播放器模板渲染包为独立 HTML 字符串（现场试玩 / 打包共用）。
    template_html 为空则用系统内置模板；模板内保留 __CODEX_PAYLOAD__（或 __CODEX_EMBED__）注入点。
    state: 可选的运行时机制状态（dict），用于条件分支求值；None=预览（全部选项可见）。
    返回 (html, counts)。"""
    embed, counts = build_standalone_html(pkg_dir)
    # 防 script 截断 + XSS：JSON 里的 < 转义为 \u003c（JS 解析自动还原）
    embed_safe = embed.replace("<", "\\u003c")
    tpl = template_html if (template_html and template_html.strip()) else DEFAULT_EDITABLE_TEMPLATE
    if "__CODEX_PAYLOAD__" in tpl:
        tpl = tpl.replace("__CODEX_PAYLOAD__", embed_safe)
    elif "__CODEX_EMBED__" in tpl:
        tpl = tpl.replace("__CODEX_EMBED__",
                          "var __CODEX_DATA__ = " + embed_safe + ";\n" + STANDALONE_PLAYER_JS)
    else:
        raise ValueError("模板中需保留 __CODEX_PAYLOAD__（或 __CODEX_EMBED__）数据注入点")
    # 运行时机制状态注入（条件分支求值用）
    state_json = json.dumps(state, ensure_ascii=False) if isinstance(state, dict) else "null"
    tpl = tpl.replace("__CODEX_STATE__", state_json)
    # 架构级水印（隐蔽，抄产物即带走）
    try:
        if mark is not None:
            tpl = tpl.replace("<!-- DICK-MARK -->",
                              "<!-- " + mark.SIGNATURE + " -->", 1)
            tpl = tpl.replace("__DICK_MARK_JS__",
                              "window.__DICK_MARK='" + mark.MARK_JS + "';", 1)
    except Exception:
        pass
    return tpl, counts
