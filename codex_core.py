# -*- coding: utf-8 -*-
# ============================================================
#   codex_core.py - CODEX 专属 GALGAME 引擎核心
#
#   CODEX（COriX Engine for iDX? / COMmon eXperience format）
#   版本：CODEX v1.0（格式版本 codex/1.0）
#   授权：MIT —— 格式与参考实现均开放，任何前端/工具都可实现与嵌入。
#   定位：一个开源的视觉小说（GALGAME）包格式 + 播放器，由 DICK 发起，
#         但不对任何平台专有——酒馆（SillyTavern）等前端可直接内置。
#
#   傻瓜化资源导入（立绘/音乐/声音/背面/剧情）→ 剧本 codex.json
#   → 全屏播放器（背景 + 立绘 + 打字机文本 + 选项分支 + BGM/配音）
#   → 一键打包独立 HTML / EXE（零依赖，可分发）。
#
#   剧本格式（codex.json，JSON 功能友好——可视化编辑/校验/导入导出）：
#   {
#     "codex": "1.0",              # 格式版本（赋权：开放格式的版本声明）
#     "name": "我的故事",
#     "author": "",
#     "intro": "简介",
#     "scenes": [
#       {
#         "id": "s1",
#         "bg": "bg/教室.png",          # 进入场景时切换的背景（相对包根目录）
#         "bgm": "bgm/主题曲.mp3",      # 进入场景时播放的音乐（可选）
#         "lines": [
#           {"speaker": "咲", "sprite": "sprites/咲_立绘.png", "voice": "voice/01.wav",
#            "text": "早上好！"},
#           {"choice": [                      # 选项分支：玩家选择后跳转
#             {"text": "打招呼", "goto": "s2"},
#             {"text": "无视",   "goto": "s3"}
#           ]},
#           {"action": "/speak こんにちは"},  # 行动钩子：调用宿主平台命令（如插件）
#           {"jump": "s4"},                   # 无条件跳转
#           {"end": "结局：日常的一天"}        # 结局
#         ]
#       }
#     ]
#   }
#
#   行类型（lines 数组元素，按序播放）：
#     {"text": "...", "speaker": "名字", "sprite": "立绘相对路径",
#      "voice": "配音相对路径", "bg": "背景相对路径", "bgm": "音乐相对路径"}  台词行
#     {"choice": [{"text": "...", "goto": "场景id"}, ...]}                 选项分支
#     {"jump": "场景id"}                                                   跳转
#     {"action": "插件命令字符串"}                                          行动钩子（不改文案，执行命令）
#     {"end": "结局标题"}                                                   结局（停止播放，展示结算）
#     {"note": "舞台说明"}                                                  旁白（无 speaker 的小字）
#
#   立绘多位置：行级 sprites 数组 [{file, pos}]（pos: left/center/right），
#   兼容单立绘 sprite + pos 字段；场景级 sprites 设默认布局。
# ============================================================

CODEX_VERSION = "1.0"
CODEX_FORMAT = "codex/1.0"

import json
import os
import re
import struct
import zipfile

# ---------- 目录约定 ----------
SUBDIRS = ("sprites", "bg", "bgm", "voice")

# ---------- 资源自动归类：按扩展名 ----------
_EXT_KIND = {
    ".png": "sprites", ".jpg": "sprites", ".jpeg": "sprites", ".webp": "sprites", ".gif": "sprites",
    ".mp3": "bgm", ".wav": "bgm", ".ogg": "bgm", ".flac": "bgm",
    ".mp4": "voice", ".m4a": "voice",
}
# 明显按名归类（中文/英文关键词）→ 覆盖扩展名默认
_NAME_KIND = [
    (re.compile(r"(voice|配音|声|セリフ|せりふ|音声)", re.I), "voice"),
    (re.compile(r"(bgm|music|音乐|音楽|曲|theme)", re.I), "bgm"),
    (re.compile(r"(bg|背景|back|room|school|夜景|教室|海岸|駅|駅前)", re.I), "bg"),
    (re.compile(r"(sprite|立绘|立絵|表情|face|表情差分)", re.I), "sprites"),
]


def classify_file(name):
    """按文件名猜资源类别（sprites/bg/bgm/voice）；无法识别返回 None"""
    base = os.path.basename(name or "").lower()
    stem = os.path.splitext(base)[0]
    for pat, kind in _NAME_KIND:
        if pat.search(stem):
            return kind
    ext = os.path.splitext(base)[1]
    return _EXT_KIND.get(ext)


# ---------- 剧本校验 ----------
def validate_codex(data):
    """校验剧本 dict。返回 (ok, issues)"""
    issues = []
    if not isinstance(data, dict):
        return False, ["剧本必须是 JSON 对象"]
    name = str(data.get("name") or "").strip()
    if not name:
        issues.append("缺少 name（剧本名）")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        issues.append("缺少 scenes（至少一个场景）")
        return bool(not issues), issues
    ids = set()
    seen_dup = set()
    for i, sc in enumerate(scenes):
        if isinstance(sc, dict) and str(sc.get("id") or "").strip():
            sid = str(sc["id"]).strip()
            if sid in ids:
                seen_dup.add(sid)
            ids.add(sid)
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            issues.append(f"scenes[{i}] 不是对象")
            continue
        sid = str(sc.get("id") or "").strip()
        if not sid:
            issues.append(f"scenes[{i}] 缺少 id")
        elif sid in seen_dup:
            issues.append(f"场景 id 重复: {sid}")
        lines = sc.get("lines")
        if not isinstance(lines, list) or not lines:
            issues.append(f"场景 {sid or i} 缺少 lines")
            continue
        for j, ln in enumerate(lines):
            if not isinstance(ln, dict):
                issues.append(f"场景 {sid or i} lines[{j}] 不是对象")
                continue
            # 立绘多位置：sprites 数组 [{file, pos}]（pos: left/center/right）
            if "sprites" in ln:
                sl = ln["sprites"]
                if not isinstance(sl, list) or not sl:
                    issues.append(f"场景 {sid or i} lines[{j}] sprites 必须是非空数组")
                else:
                    for k, s in enumerate(sl):
                        if not isinstance(s, dict) or not str(s.get("file") or "").strip():
                            issues.append(f"场景 {sid or i} lines[{j}] sprites[{k}] 缺 file")
                        p = str(s.get("pos") or "center")
                        if p not in ("left", "center", "right"):
                            issues.append(f"场景 {sid or i} lines[{j}] sprites[{k}] pos 必须是 left/center/right: {p}")
            if "choice" in ln:
                opts = ln["choice"]
                if not isinstance(opts, list) or not opts:
                    issues.append(f"场景 {sid or i} lines[{j}] choice 为空")
                else:
                    for k, o in enumerate(opts):
                        if not isinstance(o, dict) or not str(o.get("text") or "").strip():
                            issues.append(f"场景 {sid or i} lines[{j}] choice[{k}] 缺 text")
                        g = str(o.get("goto") or "").strip()
                        if g and g not in ids:
                            issues.append(f"场景 {sid or i} lines[{j}] choice[{k}] goto 指向不存在的场景: {g}")
            if "jump" in ln:
                g = str(ln["jump"] or "").strip()
                if g and g not in ids:
                    issues.append(f"场景 {sid or i} lines[{j}] jump 指向不存在的场景: {g}")
            if not any(k in ln for k in ("text", "choice", "jump", "action", "end", "note")):
                issues.append(f"场景 {sid or i} lines[{j}] 缺少有效行类型")
    return bool(not issues), issues


def make_template(name="我的故事"):
    """生成一个开箱即用的示例剧本（可直接播放，验证播放器）"""
    return {
        "name": name,
        "author": "",
        "intro": "这是一个 CODEX 示例剧本：改改 codex.json 就能做出你的专属 GALGAME。\n"
                 "把立绘放 sprites/、背景放 bg/、音乐放 bgm/、配音放 voice/，"
                 "然后在 scenes 里引用即可（相对路径）。",
        "scenes": [
            {
                "id": "s1",
                "bg": "bg/教室.png",
                "bgm": "bgm/主题曲.mp3",
                "lines": [
                    {"note": "（清晨的教室里，阳光透过窗户洒进来。）"},
                    {"speaker": "咲", "sprite": "sprites/咲_立绘.png",
                     "voice": "voice/01.wav", "text": "早上好！今天也一起走吧。"},
                    {"choice": [
                        {"text": "牵起她的手", "goto": "s2"},
                        {"text": "假装没听见", "goto": "s3"},
                    ]},
                    {"end": "结局：日常的一天"},
                ],
            },
            {
                "id": "s2",
                "bg": "bg/走廊.png",
                "lines": [
                    {"speaker": "咲", "sprite": "sprites/咲_笑.png", "text": "（脸微微一红）嗯……走吧。"},
                    {"jump": "s1"},
                ],
            },
            {
                "id": "s3",
                "bg": "bg/走廊.png",
                "lines": [
                    {"speaker": "咲", "sprite": "sprites/咲_怒.png", "text": "喂！我在跟你说话呢！"},
                    {"end": "结局：惹她生气了"},
                ],
            },
        ],
    }


# ---------- 导入：把任意文件夹自动归类为 CODEX 包 ----------
def import_folder(src_dir, dest_root, name):
    """扫描 src_dir（或其子目录）里的资源，按类别复制到
    dest_root/<name>/{sprites,bg,bgm,voice}/；若已有 codex.json 则一并复制。
    返回 {"ok": bool, "moved": {kind: count}, "msg": str}"""
    import shutil
    src_dir = os.path.abspath(src_dir)
    if not os.path.isdir(src_dir):
        return {"ok": False, "msg": "源文件夹不存在"}
    dst = os.path.join(dest_root, name)
    os.makedirs(dst, exist_ok=True)
    counts = {k: 0 for k in SUBDIRS}
    copied_json = False
    for root, _dirs, files in os.walk(src_dir):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, src_dir)
            rel_norm = rel.replace("\\", "/")
            # codex.json 原样保留
            if fn == "codex.json" and not copied_json:
                try:
                    shutil.copy2(full, os.path.join(dst, "codex.json"))
                    copied_json = True
                except Exception:
                    pass
                continue
            kind = classify_file(fn)
            # 已在类别子目录里的文件优先按所在目录归类
            parts = rel_norm.split("/")
            if len(parts) > 1 and parts[0].lower() in SUBDIRS:
                kind = parts[0].lower()
            if not kind:
                continue
            out_dir = os.path.join(dst, kind)
            os.makedirs(out_dir, exist_ok=True)
            out_name = os.path.basename(fn)
            i = 1
            while os.path.exists(os.path.join(out_dir, out_name)):
                stem, ext = os.path.splitext(out_name)
                out_name = f"{stem}_{i}{ext}"
                i += 1
            try:
                shutil.copy2(full, os.path.join(out_dir, out_name))
                counts[kind] += 1
            except Exception:
                pass
    if not copied_json:
        # 没有现成剧本 → 自动生成：以文件名映射到示例引用
        tpl = make_template(name)
        # 把实际存在的资源名写进场景引用，保证播放器开箱能显示
        tpl = _wire_resources(tpl, dst)
        try:
            with open(os.path.join(dst, "codex.json"), "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    total = sum(counts.values())
    return {"ok": True, "moved": counts, "msg": f"导入 {total} 个资源文件"}


def _wire_resources(tpl, dst):
    """把导入的实际文件名回填到模板场景里（立绘/背景/音乐/配音各取第一个）"""
    def first(kind):
        d = os.path.join(dst, kind)
        try:
            for fn in sorted(os.listdir(d)):
                return f"{kind}/{fn}"
        except Exception:
            return None
    sprite = first("sprites")
    bg = first("bg")
    bgm = first("bgm")
    voice = first("voice")
    scenes = tpl.get("scenes") or []
    for sc in scenes:
        if bg:
            sc["bg"] = bg
        if bgm:
            sc["bgm"] = bgm
        for ln in sc.get("lines") or []:
            if isinstance(ln, dict) and "speaker" in ln:
                if sprite:
                    ln.setdefault("sprite", sprite)
                if voice:
                    ln.setdefault("voice", voice)
    return tpl


# ---------- 一键示例包（傻瓜化：含真实可播占位资源） ----------
def make_sample_package(dest_root, name="示例·夏日祭"):
    """生成一个带占位资源的示例 CODEX 包：1x1 渐变立绘/背景（PNG）、
    静音 BGM/配音（WAV），剧本引用真实文件 → 一键即可播放。
    返回 (ok, 包目录)"""
    import shutil
    import struct
    dst = os.path.join(dest_root, _safe_name(name))
    try:
        shutil.rmtree(dst, ignore_errors=True)
        for k in SUBDIRS:
            os.makedirs(os.path.join(dst, k), exist_ok=True)
        # --- 占位立绘（渐变圆角少女剪影，纯代码 PNG） ---
        sprites = {
            "咲_立绘.png": (255, 210, 130),
            "咲_笑.png": (255, 220, 150),
            "咲_怒.png": (255, 150, 120),
        }
        for fn, color in sprites.items():
            _write_placeholder_png(os.path.join(dst, "sprites", fn), color, w=420, h=720)
        bgs = {"教室.png": (120, 160, 200), "走廊.png": (90, 110, 140)}
        for fn, color in bgs.items():
            _write_placeholder_png(os.path.join(dst, "bg", fn), color, w=960, h=540)
        # --- 静音音频（WAV 静音 1 秒） ---
        _write_silent_wav(os.path.join(dst, "bgm", "主题曲.wav"))
        _write_silent_wav(os.path.join(dst, "voice", "01.wav"))
        # --- 剧本 ---
        tpl = make_template(name)
        tpl["intro"] = "这是 DICK 自带的一键示例包：直接点 ▶️ 播放就能看到立绘/背景/选项/结局。\n" \
                       "去 sprites/、bg/、bgm/、voice/ 替换成你自己的素材，再改 codex.json 就是你的专属 GALGAME。"
        tpl["scenes"][0]["bg"] = "bg/教室.png"
        tpl["scenes"][0]["bgm"] = "bgm/主题曲.wav"
        tpl["scenes"][0]["lines"][1]["sprite"] = "sprites/咲_立绘.png"
        tpl["scenes"][0]["lines"][1]["voice"] = "voice/01.wav"
        tpl["scenes"][1]["lines"][0]["sprite"] = "sprites/咲_笑.png"
        tpl["scenes"][2]["lines"][0]["sprite"] = "sprites/咲_怒.png"
        with open(os.path.join(dst, "codex.json"), "w", encoding="utf-8") as f:
            json.dump(tpl, f, ensure_ascii=False, indent=2)
        return True, dst
    except Exception as e:
        return False, str(e)


def _write_placeholder_png(path, rgb, w=420, h=720):
    """纯代码生成一张垂直渐变 PNG（无 PIL 依赖）"""
    import zlib
    r0, g0, b0 = rgb
    rows = []
    for y in range(h):
        t = y / max(1, h - 1)
        # 顶部亮、底部暗的渐变；中间一个简单的"头部/肩部"色块
        r = int(r0 * (1 - t * 0.45))
        g = int(g0 * (1 - t * 0.45))
        b = int(b0 * (1 - t * 0.45))
        row = bytearray([0])  # filter: None
        for x in range(w):
            # 简单剪影：头部圆 + 肩部梯形（深色）
            cx, cy = w // 2, h // 3
            if (x - cx) ** 2 + (y - cy) ** 2 < (h // 9) ** 2:
                row += bytes([r // 2, g // 2, b // 2])
            elif y > h // 3 and y < h * 0.8 and abs(x - cx) < (w // 5) * (1 - (y - h // 3) / (h * 0.5) * 0.5):
                row += bytes([r // 2, g // 2, b // 2])
            else:
                row += bytes([r, g, b])
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def _write_silent_wav(path, seconds=1, rate=22050):
    """生成静音 WAV（可播放、无爆音）"""
    import struct
    n = int(rate * seconds)
    data = b"\x00\x00" * n
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + \
          b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + \
          b"data" + struct.pack("<I", len(data))
    with open(path, "wb") as f:
        f.write(hdr + data)


# ---------- 打包：自包含单文件 HTML（独立 GALGAME，零后端依赖） ----------
def _inject_signature(script):
    """架构级水印：给剧本注入 _signature（抄格式/抄剧本都带走来源标识）"""
    try:
        import dick_mark
        if isinstance(script, dict) and not script.get("_signature"):
            script["_signature"] = dick_mark.mark_dict()
    except Exception:
        pass
    return script


def build_standalone_html(pkg_dir, embed_script=True):
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
    script = _inject_signature(script)
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


STANDALONE_PLAYER_JS = r"""
// ============ CODEX 独立播放器（零后端依赖：资源内嵌、localStorage 存档） ============
// __CODEX_DATA__ 由打包器注入：{script, assets}
__DICK_MARK_JS__
var __cxScript = __CODEX_DATA__.script;
var __cxAssets = __CODEX_DATA__.assets;
var cxState = null; // 播放器运行时状态

function cxGetAsset(kind, file) {
  if (!file) return null;
  return (__cxAssets[kind] || {})[file] || null;
}
function cxSetBg(file) {
  var el = document.getElementById('cxBg');
  var url = cxGetAsset('bg', file);
  el.style.backgroundImage = url ? 'url("' + url + '")' : 'none';
}
function cxSpriteCss(pos) {
  var base = 'position:absolute;bottom:0;height:100%;max-height:560px;object-fit:contain;filter:drop-shadow(0 0 24px rgba(0,0,0,.6));transition:all .35s ease;';
  if (pos === 'left') return base + 'left:2%;transform-origin:bottom left;';
  if (pos === 'right') return base + 'right:2%;transform-origin:bottom right;';
  return base + 'left:50%;transform:translateX(-50%);transform-origin:bottom center;';
}
function cxSetSprites(list) {
  var box = document.getElementById('cxSprites');
  box.innerHTML = '';
  if (!list || !list.length) return;
  ['right', 'center', 'left'].forEach(function (pos) {
    list.filter(function (it) { return (it.pos || 'center') === pos; }).forEach(function (it) {
      var url = cxGetAsset('sprites', it.file);
      if (!url) return;
      var img = document.createElement('img');
      img.src = url;
      img.style.cssText = cxSpriteCss(it.pos || 'center');
      box.appendChild(img);
    });
  });
}
function cxPlayBgm(file) {
  if (cxState && cxState.audioBgm) { cxState.audioBgm.pause(); cxState.audioBgm = null; }
  var url = cxGetAsset('bgm', file);
  if (!url) return;
  var a = new Audio(url);
  a.loop = true; a.volume = 0.6;
  a.play().catch(function () {});
  cxState.audioBgm = a;
}
function cxPlayVoice(file) {
  var url = cxGetAsset('voice', file);
  if (!url) return;
  if (cxState && cxState.audioVoice) cxState.audioVoice.pause();
  var a = new Audio(url);
  a.volume = 0.9; a.play().catch(function () {});
  cxState.audioVoice = a;
}
function cxTypeText(text, speaker) {
  var el = document.getElementById('cxText');
  var sp = document.getElementById('cxSpeaker');
  document.getElementById('cxNote').textContent = '';
  el.textContent = '';
  if (speaker) { sp.style.display = 'block'; sp.textContent = speaker; }
  else sp.style.display = 'none';
  cxState.typing = true;
  var i = 0;
  var step = function () {
    if (!cxState) return;
    if (i < text.length) { el.textContent = text.slice(0, i + 1); i++; cxState.typingTimer = setTimeout(step, 30); }
    else { cxState.typing = false; cxScheduleAuto(); }
  };
  step();
}
function cxSkipTyping() {
  if (!cxState || !cxState.typing) return;
  if (cxState.typingTimer) clearTimeout(cxState.typingTimer);
  var ln = cxState.lines[cxState.lineIdx - 1];
  if (ln && 'text' in ln) document.getElementById('cxText').textContent = ln.text || '';
  cxState.typing = false;
  cxScheduleAuto();
}
function cxScheduleAuto() {
  if (!cxState || !cxState.auto) return;
  if (cxState.autoTimer) clearTimeout(cxState.autoTimer);
  cxState.autoTimer = setTimeout(function () { if (cxState && cxState.auto) cxNextLine(); }, 1600);
}
function cxStopAuto() {
  if (!cxState) return;
  cxState.auto = false;
  if (cxState.autoTimer) { clearTimeout(cxState.autoTimer); cxState.autoTimer = null; }
  var b = document.getElementById('cxAuto'); if (b) b.textContent = '⏩ 自动';
}
function cxShowChoice(opts) {
  var box = document.getElementById('cxChoice');
  box.style.display = 'block';
  box.innerHTML = '';
  cxState.lastChoicePoint = { sceneId: cxState.curSceneId, lineIdx: cxState.lineIdx };
  var lb = document.getElementById('cxRewind'); if (lb) lb.textContent = '⏪ 回到选项';
  opts.forEach(function (o) {
    var b = document.createElement('button');
    b.textContent = o.text || '';
    b.style.cssText = 'display:block;width:100%;margin:6px 0;text-align:left;font-size:15px;padding:10px 14px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.25);color:#eee;border-radius:8px;cursor:pointer';
    b.onclick = function () {
      box.style.display = 'none';
      cxStopAuto();
      var lb2 = document.getElementById('cxRewind'); if (lb2) lb2.textContent = '⏪ 回溯';
      cxGoto(o.goto || '');
    };
    box.appendChild(b);
  });
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
}
function cxShowEnd(title) {
  cxStopAuto();
  document.getElementById('cxEndTitle').textContent = title || '结局';
  document.getElementById('cxEnd').style.display = 'flex';
}
function cxStartScene(id) {
  var scenes = cxState.scenes;
  var found = false;
  for (var i = 0; i < scenes.length; i++) {
    if (scenes[i].id === id) { cxState.scene = scenes[i]; found = true; break; }
  }
  if (!found) { cxShowEnd('⚠️ 场景不存在: ' + id); return; }
  cxState.curSceneId = cxState.scene.id;
  cxState.lineIdx = 0;
  cxState.lines = cxState.scene.lines || [];
  cxSetBg(cxState.scene.bg);
  cxPlayBgm(cxState.scene.bgm);
  if (cxState.scene.sprites && cxState.scene.sprites.length) cxSetSprites(cxState.scene.sprites);
  else cxSetSprites([]);
  cxNextLine();
}
function cxGoto(id) {
  if (!id) { cxNextLine(); return; }
  cxStartScene(id);
}
function cxNextLine() {
  if (!cxState) return;
  if (cxState.typing) { cxSkipTyping(); return; }
  if (cxState.lineIdx >= cxState.lines.length) {
    var sc = cxState.scene;
    if (sc && sc.jump) { cxStartScene(sc.jump); return; }
    if (sc && sc.next) { cxStartScene(sc.next); return; }
    cxShowEnd('完结');
    return;
  }
  var ln = cxState.lines[cxState.lineIdx++];
  if (!ln || typeof ln !== 'object') { cxNextLine(); return; }
  if (ln.bg) cxSetBg(ln.bg);
  if (ln.bgm) cxPlayBgm(ln.bgm);
  if (ln.sprites && ln.sprites.length) cxSetSprites(ln.sprites);
  else if (ln.sprite) cxSetSprites([{ file: ln.sprite, pos: ln.pos || 'center' }]);
  if (ln.voice) cxPlayVoice(ln.voice);
  if ('text' in ln) cxTypeText(ln.text || '', ln.speaker || '');
  else if ('note' in ln) {
    document.getElementById('cxNote').textContent = ln.note || '';
    document.getElementById('cxText').textContent = '';
    document.getElementById('cxSpeaker').style.display = 'none';
    cxScheduleAuto();
  } else if ('choice' in ln) {
    document.getElementById('cxNote').textContent = '';
    cxShowChoice(ln.choice || []);
  } else if ('jump' in ln) cxGoto(ln.jump);
  else if ('end' in ln) cxShowEnd(ln.end);
  else if ('action' in ln) cxNextLine(); // 独立版无后端：跳过行动钩子
}
function cxSave() {
  if (!cxState || !cxState.curSceneId) return;
  var slot = { sceneId: cxState.curSceneId, lineIdx: Math.max(0, cxState.lineIdx - 1) };
  try { localStorage.setItem('codex_save', JSON.stringify(slot)); var b = document.getElementById('cxSave'); if (b) { b.textContent = '💾 已存档'; setTimeout(function () { if (b) b.textContent = '💾 存档'; }, 1200); } } catch (e) {}
}
function cxLoad() {
  if (!cxState) return;
  var raw = null; try { raw = localStorage.getItem('codex_save'); } catch (e) {}
  if (!raw) { alert('还没有存档'); return; }
  var slot = null; try { slot = JSON.parse(raw); } catch (e) {}
  if (!slot || !slot.sceneId) { alert('存档损坏'); return; }
  cxStopAuto();
  var sc = null;
  for (var i = 0; i < cxState.scenes.length; i++) if (cxState.scenes[i].id === slot.sceneId) { sc = cxState.scenes[i]; break; }
  if (!sc) { alert('存档指向的场景不存在'); return; }
  cxState.scene = sc; cxState.curSceneId = sc.id;
  cxState.lines = sc.lines || [];
  cxSetBg(sc.bg); cxPlayBgm(sc.bgm);
  document.getElementById('cxChoice').style.display = 'none';
  document.getElementById('cxNote').textContent = '';
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
  cxState.lineIdx = Math.max(0, Math.min(slot.lineIdx || 0, (sc.lines || []).length - 1));
  cxNextLine();
}
function cxRewind() {
  if (!cxState) return;
  cxStopAuto();
  var targetScene = null, targetLine = 0;
  if (cxState.lastChoicePoint && cxState.lastChoicePoint.sceneId) {
    for (var i = 0; i < cxState.scenes.length; i++) if (cxState.scenes[i].id === cxState.lastChoicePoint.sceneId) { targetScene = cxState.scenes[i]; targetLine = cxState.lastChoicePoint.lineIdx || 0; break; }
  }
  if (!targetScene && cxState.scene) { targetScene = cxState.scene; targetLine = 0; }
  if (!targetScene) return;
  cxState.lastChoicePoint = null;
  var lb = document.getElementById('cxRewind'); if (lb) lb.textContent = '⏪ 回溯';
  cxState.scene = targetScene; cxState.curSceneId = targetScene.id;
  cxState.lineIdx = targetLine; cxState.lines = targetScene.lines || [];
  document.getElementById('cxChoice').style.display = 'none';
  document.getElementById('cxNote').textContent = '';
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
  cxSetBg(targetScene.bg); cxPlayBgm(targetScene.bgm);
  cxNextLine();
}
function cxStart() {
  cxState = {
    script: __cxScript, scenes: __cxScript.scenes || [],
    scene: null, lineIdx: 0, lines: [], curSceneId: null, lastChoicePoint: null,
    audioBgm: null, audioVoice: null, auto: false, autoTimer: null, typing: false, typingTimer: null,
  };
  document.getElementById('cxTitleName').textContent = __cxScript.name || 'CODEX';
  document.getElementById('cxTitleIntro').textContent = __cxScript.intro || '';
  document.getElementById('cxTitle').style.display = 'flex';
  document.getElementById('cxEnd').style.display = 'none';
  document.getElementById('cxText').textContent = '';
  document.getElementById('cxSpeaker').style.display = 'none';
  document.getElementById('cxChoice').style.display = 'none';
  document.getElementById('cxNote').textContent = '';
  document.getElementById('cxSprites').innerHTML = '';
  document.getElementById('cxBg').style.backgroundImage = 'none';
}
document.addEventListener('DOMContentLoaded', cxStart);
document.getElementById('cxTitle').onclick = function () { document.getElementById('cxTitle').style.display = 'none'; cxStartScene((cxState.scenes[0] || {}).id || ''); };
document.getElementById('cxEnd').onclick = function () { document.getElementById('cxEnd').style.display = 'none'; cxState = null; document.getElementById('cxSprites').innerHTML = ''; cxStart(); };
document.getElementById('cxSave').onclick = cxSave;
document.getElementById('cxLoad').onclick = cxLoad;
document.getElementById('cxRewind').onclick = cxRewind;
document.getElementById('cxAuto').onclick = function () {
  if (!cxState) return;
  cxState.auto = !cxState.auto;
  this.textContent = cxState.auto ? '⏸ 停止自动' : '⏩ 自动';
  if (cxState.auto) cxScheduleAuto(); else cxStopAuto();
};
document.getElementById('cxTextbox').onclick = function () {
  if (!cxState) return;
  if (document.getElementById('cxChoice').style.display === 'block') return;
  if (document.getElementById('cxTitle').style.display === 'flex') return;
  if (document.getElementById('cxEnd').style.display === 'flex') return;
  cxNextLine();
};
"""


def build_standalone_file(pkg_dir, out_path=None):
    """生成独立单文件 HTML（打包 GALGAME）。返回 (成功?, 输出路径或错误)"""
    embed, counts = build_standalone_html(pkg_dir)
    # 防 script 截断 + XSS：JSON 里的 < 转义为 \u003c（JS 解析自动还原）
    embed_safe = embed.replace("<", "\\u003c")
    # 播放器 JS：先放数据（JSON 序列化），再放播放器逻辑
    script_body = "var __CODEX_DATA__ = " + embed_safe + ";\n" + STANDALONE_PLAYER_JS
    html = STANDALONE_PLAYER_HTML.replace("__CODEX_EMBED__", script_body)
    # 架构级水印（隐蔽，抄产物即带走）
    try:
        import dick_mark
        html = html.replace("<!-- DICK-MARK -->",
                            "<!-- " + dick_mark.SIGNATURE + " -->", 1)
        html = html.replace("__DICK_MARK_JS__",
                            "window.__DICK_MARK='" + dick_mark.MARK_JS + "';", 1)
    except Exception:
        pass
    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(pkg_dir)),
                                _safe_name(os.path.basename(pkg_dir)) + ".html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return True, out_path, counts


STANDALONE_PLAYER_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<!-- DICK-MARK -->
<title>CODEX GALGAME</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:100%; height:100%; overflow:hidden; background:#000; font-family:"Microsoft YaHei",sans-serif; }
  #cxBg { position:absolute; inset:0; background-size:cover; background-position:center; background-color:#0a0a12; }
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


# ---------- 打包 EXE：pywebview 播放器壳 ----------
# 壳脚本：内嵌打包好的单文件 HTML（base64），pywebview 窗口加载。
# PyInstaller --onefile --noconsole 打成独立 EXE（无需浏览器，双击即玩）。
EXE_SHELL_TEMPLATE = r'''# -*- coding: utf-8 -*-
"""CODEX 独立播放器壳：加载内嵌的打包 HTML（零后端依赖）"""
import base64
import os
import sys

# PyInstaller windowed 模式无控制台：stdout/stderr 重定向到 exe 旁日志
if sys.stdout is None or sys.stderr is None:
    try:
        _log = open(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "codex_debug.log"),
                    "w", encoding="utf-8", errors="replace")
        if sys.stdout is None:
            sys.stdout = _log
        if sys.stderr is None:
            sys.stderr = _log
    except Exception:
        pass

_HTML_B64 = "__HTML_B64__"
_HTML = base64.b64decode(_HTML_B64).decode("utf-8")
_TITLE = "__TITLE__"

import webview


class _Api:
    def exit(self):
        try:
            for w in webview.windows:
                w.destroy()
        except Exception:
            pass
        return True


def main():
    api = _Api()
    window = webview.create_window(
        _TITLE, html=_HTML, js_api=api,
        width=1000, height=720, min_size=(720, 540),
        background_color="#0f1115")
    webview.start()


if __name__ == "__main__":
    main()
'''


def build_exe_shell(html, title="CODEX GALGAME"):
    """生成播放器壳脚本内容（HTML base64 内嵌）。"""
    import base64 as _b64
    b64 = _b64.b64encode(html.encode("utf-8")).decode("ascii")
    return EXE_SHELL_TEMPLATE.replace("__HTML_B64__", b64).replace("__TITLE__", title or "CODEX GALGAME")


def pyinstaller_cmd(shell_path, out_dir, name):
    """构造 PyInstaller 命令：单文件无控制台 EXE，输出到 out_dir/<name>.exe。
    返回 (cmd 列表, 说明)。"""
    hidden = [
        "webview", "webview.platforms.edgechromium", "webview.platforms.winforms",
        "clr_loader", "pythonnet", "urllib.parse",
    ]
    cmd = [
        "python", "-m", "PyInstaller",
        "--noconfirm", "--onefile", "--windowed",
        "--name", name,
        "--distpath", out_dir,
        "--workpath", os.path.join(out_dir, "_build"),
        "--specpath", os.path.join(out_dir, "_build"),
    ]
    for h in hidden:
        cmd += ["--hidden-import", h]
    cmd.append(shell_path)
    return cmd


def build_standalone_exe(pkg_dir, out_dir, name=None, py_cmd=None, log_cb=None):
    """完整打包 EXE 流程：生成 HTML → 写壳脚本 → 调 PyInstaller → 返回 EXE 路径。
    py_cmd: 覆盖 python 解释器（默认 sys.executable）；log_cb: 进度回调(str)。"""
    import subprocess
    import sys as _sys
    import shutil
    pkg_dir = os.path.abspath(pkg_dir)
    # 1) 生成单文件 HTML
    embed, counts = build_standalone_html(pkg_dir)
    html = STANDALONE_PLAYER_HTML.replace("__CODEX_EMBED__",
                                          "var __CODEX_DATA__ = " + embed.replace("<", "\\u003c") + ";\n" + STANDALONE_PLAYER_JS)
    with open(os.path.join(pkg_dir, "codex.json"), "r", encoding="utf-8") as f:
        script = json.load(f)
    title = str(script.get("name") or (name or "CODEX GALGAME"))
    safe = _safe_name(name or title or "CODEX-GALGAME")
    # 2) 写壳脚本到 out_dir/_build
    os.makedirs(out_dir, exist_ok=True)
    build_dir = os.path.join(out_dir, "_build")
    os.makedirs(build_dir, exist_ok=True)
    shell_path = os.path.join(build_dir, "codex_shell.py")
    with open(shell_path, "w", encoding="utf-8") as f:
        f.write(build_exe_shell(html, title))
    if log_cb:
        log_cb("壳脚本已生成，正在调用 PyInstaller…")
    # 3) PyInstaller
    if py_cmd is None:
        py_cmd = _sys.executable
    base_cmd = [py_cmd, "-m", "PyInstaller"] if py_cmd else ["python", "-m", "PyInstaller"]
    hidden = [
        "webview", "webview.platforms.edgechromium", "webview.platforms.winforms",
        "clr_loader", "pythonnet", "urllib.parse",
    ]
    cmd = base_cmd + [
        "--noconfirm", "--onefile", "--windowed",
        "--name", safe,
        "--distpath", out_dir,
        "--workpath", build_dir,
        "--specpath", build_dir,
    ]
    for h in hidden:
        cmd += ["--hidden-import", h]
    cmd.append(shell_path)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        tail = (r.stderr or "")[-1200:]
        raise RuntimeError("PyInstaller 失败:\n" + tail)
    exe = os.path.join(out_dir, safe + ".exe")
    if not os.path.isfile(exe):
        raise RuntimeError("打包完成但未找到 EXE: " + exe)
    return exe, counts


# ---------- 导出 / 导入 zip ----------
def export_zip(pkg_dir, zip_path):
    """把 CODEX 包打成 zip（含 codex.json 与全部资源）"""
    pkg_dir = os.path.abspath(pkg_dir)
    if not os.path.isdir(pkg_dir):
        return False
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(pkg_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, pkg_dir).replace("\\", "/")
                z.write(full, rel)
    return True


def import_zip(zip_path, dest_root):
    """解压 zip 到 dest_root/<包名>/（包名 = zip 内 codex.json 的 name 或压缩包名）。
    返回 (ok, name, msg)"""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            # 找 codex.json 的顶层目录
            top = None
            for n in names:
                if n.endswith("codex.json") and n.count("/") <= 1:
                    top = os.path.dirname(n)
                    break
            name = os.path.basename(zip_path)
            low_name = name.lower()
            if low_name.endswith(".zip"):
                name = name[:-4]
            elif low_name.endswith(".codex"):
                name = name[:-6]
            if top:
                try:
                    raw = z.read(os.path.join(top, "codex.json")).decode("utf-8")
                    data = json.loads(raw)
                    if str(data.get("name") or "").strip():
                        name = str(data["name"]).strip()
                except Exception:
                    pass
            dst = os.path.join(dest_root, _safe_name(name))
            os.makedirs(dst, exist_ok=True)
            for n in names:
                if n.endswith("/"):
                    continue
                if top:
                    rel = os.path.relpath(n, top).replace("\\", "/")
                else:
                    rel = n
                if not rel or rel.startswith(".."):
                    continue
                out = os.path.join(dst, rel)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with z.open(n) as src, open(out, "wb") as f:
                    f.write(src.read())
            return True, _safe_name(name), "导入成功"
    except Exception as e:
        return False, "", f"导入失败：{e}"


def _safe_name(name):
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00']:
        name = name.replace(ch, "_")
    return (name or "未命名").strip()[:60]
