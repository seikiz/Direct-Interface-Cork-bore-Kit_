# -*- coding: utf-8 -*-
"""modules/image_gen/presets.py —— 生图预设表（内置 6 套 + 用户覆盖）

搬家来源：仓库根 `image_gen.py` 的 `PRESETS` / `presets_path` / `load_presets` /
`save_presets` / `user_presets_json` / `list_presets`，**行为一字未改**。

两条铁律（搬之前就有，一条都不能少）：
  ① 用户文件里的下划线键是注释，读的时候跳过、写回时必须原样留着；
  ② 本版不认识的字段（将来版本加的 / 用户手加的）写回时也必须留着 ——
     否则"用户回退一次就永久丢档"，与三层配置、世界记忆那几处是同一类问题。

数据文件路径由调用方给（壳层传自己的数据目录），块自己不去猜宿主目录。
"""

import json
import os
import types

PRESETS_FILE = "image_presets.json"

# 内置风格：名字 → prompt 前缀 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌+ 说明。用户选预设即自动拼提示词。
# 用只读视图包起来是刻意的（ARCHITECTURE.md 十一：块里不许有模块级可变全局）。
# 这张表是**格式常量**、不是状态：真状态（用户覆盖）在磁盘上那份 image_presets.json 里，
# `load_presets()` 每次读盘再合并。所以这里只读视图最贴近事实 —— 谁也别想就地改它。
PRESETS = types.MappingProxyType({
    "anime": {
        "label": "动漫风",
        "prompt": "anime style, clean line art, vibrant colors, detailed eyes, ",
        "desc": "日式动漫插画风，适合角色立绘",
    },
    "realistic": {
        "label": "写实风",
        "prompt": "photorealistic, 8k, detailed skin texture, natural lighting, ",
        "desc": "照片级写实，适合场景/人像",
    },
    "painterly": {
        "label": "厚涂油画",
        "prompt": "oil painting style, thick brush strokes, warm palette, ",
        "desc": "油画厚涂风，氛围感强",
    },
    "chibi": {
        "label": "Q版",
        "prompt": "chibi style, cute, big head small body, simple background, ",
        "desc": "Q版可爱风，适合头像/表情",
    },
    "cyberpunk": {
        "label": "赛博朋克",
        "prompt": "cyberpunk, neon lights, rain, futuristic city, high contrast, ",
        "desc": "赛博朋克霓虹风",
    },
    "watercolor": {
        "label": "水彩",
        "prompt": "watercolor painting, soft edges, pastel colors, paper texture, ",
        "desc": "水彩清新风",
    },
})


def presets_path(base_dir):
    return os.path.join(base_dir or ".", PRESETS_FILE)


def load_presets(base_dir=None):
    """内置预设 + 用户覆盖。返回 {id: {label, prompt, desc, custom?}}。

    用户文件 image_presets.json 支持两种写法：
      · 完整写法：{"guofeng": {"label": "国风线稿", "prompt": "chinese ink line art, ", "desc": "…"}}
      · 简写：    {"guofeng": "chinese ink line art, "}
    下划线开头的键（如 "_说明"）会跳过，方便在文件里写注释。
    """
    out = {k: dict(v) for k, v in PRESETS.items()}
    path = presets_path(base_dir)
    try:
        if not os.path.isfile(path):
            return out
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
    except Exception:
        return out
    if not isinstance(user, dict):
        return out
    for k, v in user.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, str) and v.strip():
            out[k] = {"label": k, "prompt": v, "desc": "（自定义）", "custom": True}
        elif isinstance(v, dict) and str(v.get("prompt") or "").strip():
            base = out.get(k, {})
            out[k] = {
                "label": v.get("label") or base.get("label") or k,
                "prompt": v["prompt"],
                "desc": v.get("desc") or base.get("desc") or "（自定义）",
                "custom": True,
            }
    return out


def save_presets(base_dir, obj):
    """写用户覆盖文件。返回 (ok, 消息)。传 {} 即恢复内置默认。

    兼容线内"老程序读新文件"是允许发生的（用户回退一次），所以写回时**保留不认识的键**：
      · 下划线开头的顶层键（用户手写的注释）原样留着；
      · 预设对象里本版不认识的字段（将来版本加的、或用户手加的）原样留着。
    否则回退一次就永久丢掉 —— 与三层配置、世界记忆那几处是同一类问题。
    """
    if not isinstance(obj, dict):
        return False, "预设必须是一个 JSON 对象"
    # 磁盘上那一份：用来把"本版不认识的东西"带回去。
    # 注意要点：调用方通常是 `load_presets()` 的**合并视图**（只有 label/prompt/desc/custom），
    # 所以不认识的键在到达这里之前就已经被它滤掉了 —— 只靠 obj 保留不住，
    # 必须从磁盘原件补回来（与三层配置、世界记忆那几处同一类问题）。
    disk = {}
    try:
        with open(presets_path(base_dir), encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            disk = got
    except Exception:
        disk = {}
    clean = {}
    for k, v in obj.items():
        if str(k).startswith("_"):
            clean[k] = v          # 注释键：不当预设，也不许丢
            continue
        if isinstance(v, str):
            if not v.strip():
                return False, "预设「%s」的提示词是空的" % k
            clean[k] = v
        elif isinstance(v, dict):
            if not str(v.get("prompt") or "").strip():
                return False, "预设「%s」缺少 prompt 字段" % k
            item = {"prompt": v["prompt"]}
            for f in ("label", "desc"):
                if v.get(f):
                    item[f] = v[f]
            old = disk.get(k)
            for f, fv in (old if isinstance(old, dict) else {}).items():
                if f not in item:              # 磁盘原件里本版不认识的字段
                    item[f] = fv
            for f, fv in v.items():            # 调用方多给的字段（也不许丢）
                if f not in item:
                    item[f] = fv
            clean[k] = item
        else:
            return False, "预设「%s」的格式不对（应为字符串或对象）" % k
    for k, v in disk.items():                  # 顶层注释键：磁盘上有就带走
        if str(k).startswith("_") and k not in clean:
            clean[k] = v
    try:
        with open(presets_path(base_dir), "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return False, "写入失败：" + str(e)[:120]
    return True, "已保存 %d 个自定义预设" % len(clean)


def user_presets_json(base_dir):
    """给设置面板的编辑器看：用户覆盖文件的原始内容（没有就返回空对象）。"""
    path = presets_path(base_dir)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def list_presets(presets=None):
    """预设列表（前端下拉用）。presets 传 load_presets() 的结果即可带上用户预设。"""
    src = presets or PRESETS
    return [{"id": k, "label": v.get("label", k), "desc": v.get("desc", ""),
             "custom": bool(v.get("custom"))} for k, v in src.items()]
