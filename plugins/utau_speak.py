# -*- coding: utf-8 -*-
# utau_speak.py —— UTAU 合成 helper，由 utau_env（Python 3.11，含 putao/pykakasi/pypinyin）运行。
# 用法: python utau_speak.py <voicebank_dir> <pitch> <duration_ms> <text> <out.wav> [pitch_mode]
#   pitch_mode: flat(默认,全平) / happy(上扬轻快) / sad(降调缓慢) / angry(句尾强降) / question(句尾上扬)
#   语气分析：按标点/语气词自动生成音高曲线，避免"死气沉沉"
# 文本 → 音素（日文假名优先 / 中文拼音 fallback）→ putao（纯 Python UTAU 合成器）→ WAV
# 音素按声库 oto.ini 实际条目匹配（罗马音/假名/片假名变体兜底）
import sys

# 日语系统冲突防护：cp932 控制台输出日文会崩 → 强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

KANA_ROMAN = {  # 50音 + 浊/半浊/拗音（小写罗马音，与多数 CV 声库一致）
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo',
    'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'を': 'wo', 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo',
    'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
    'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho',
    'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo',
    'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo',
    'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'じゃ': 'ja', 'じゅ': 'ju', 'じょ': 'jo',
    'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo',
    'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
    'ヴ': 'vu', 'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o',
    'ゃ': 'ya', 'ゅ': 'yu', 'ょ': 'yo', 'っ': '-', 'ー': '-',
}


def _kana_to_phonemes(kana_str):
    """假名串 → 音素列表（片假名先转平假名；拗音二连、促音/长音为 -）"""
    # 片假名(0x30A1-0x30F6) → 平假名(0x3041-0x3096)
    kana_str = ''.join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in kana_str)
    out = []
    chars = list(kana_str)
    i = 0
    while i < len(chars):
        c = chars[i]
        if c in ('っ', 'ー'):
            out.append('-')
            i += 1
            continue
        two = c + chars[i + 1] if i + 1 < len(chars) else ''
        if two in KANA_ROMAN:
            out.append(KANA_ROMAN[two])
            i += 2
            continue
        out.append(KANA_ROMAN.get(c, c))
        i += 1
    return out


def _phoneme_candidates(text, vb_keys):
    """为文本生成音素（优先声库命中；日文假名 → 罗马音，中文 fallback 拼音）"""
    cands = []
    try:
        from pykakasi import kakasi
        k = kakasi()
        kana = ''.join(item['kana'] for item in k.convert(text))
        cands = _kana_to_phonemes(kana)
    except Exception:
        cands = []
    if not cands:
        try:
            from pypinyin import lazy_pinyin
            cands = [p for p in lazy_pinyin(text) if p.strip()]
        except Exception:
            cands = []
    out = []
    for c in cands:
        if c == '-' or c in vb_keys:
            out.append(c)
            continue
        found = False
        for variant in (c, c.upper(), c.lower()):
            if variant in vb_keys:
                out.append(variant)
                found = True
                break
        if not found:
            out.append(c)  # 保留，note 时 TrackError 跳过
    return out


def _analyze_tone(text):
    """语气分析：按文本特征返回 (模式, 参数)。
    模式: flat / happy / sad / angry / question
    参数: {start, end, dur_scale} —— start/end 为音高偏移（相对基准），dur_scale 为语速倍率
    """
    t = text.strip()
    if not t:
        return "flat", {}
    # 情绪词（中文为主，兼顾日文）
    happy_kw = ("哈哈", "嘿嘿", "好耶", "太好了", "开心", "嘻嘻", "笑", "♪", "~", "～", "うれ", "嬉", "楽し")
    sad_kw = ("哭", "呜呜", "难过", "伤心", "寂寞", "不要走", "泣", "悲", "さみ", "寂")
    angry_kw = ("哼", "才不", "讨厌", "混蛋", "可恶", "生气", "怒", "む", "ふん")
    if any(k in t for k in happy_kw):
        return "happy", {"start": +2, "end": +5, "dur_scale": 0.85}
    if any(k in t for k in sad_kw):
        return "sad", {"start": -2, "end": -6, "dur_scale": 1.25}
    if any(k in t for k in angry_kw):
        return "angry", {"start": +4, "end": -8, "dur_scale": 0.8}
    # 标点判断
    if t.endswith("？") or t.endswith("?") or t.endswith("吗"):
        return "question", {"start": 0, "end": +7, "dur_scale": 1.0}
    if t.endswith("！") or t.endswith("!"):
        return "angry", {"start": +3, "end": -5, "dur_scale": 0.9}
    if "……" in t or "..." in t or "。。" in t:
        return "sad", {"start": -1, "end": -4, "dur_scale": 1.15}
    return "flat", {}


def _pitch_for(i, total, mode, base_pitch, params):
    """第 i 个音素（共 total 个）的音高：按模式插值，制造起伏而非全平"""
    if total <= 1:
        return base_pitch
    start = params.get("start", 0)
    end = params.get("end", 0)
    # 线性渐变 + 轻微波浪（±1 让听感自然，不机械）
    frac = i / max(1, total - 1)
    p = base_pitch + start + (end - start) * frac
    import math
    p += math.sin(i * 1.7) * 1.0  # 微起伏
    return int(round(p))


def main():
    args = sys.argv[1:]
    voicebank, pitch, duration, text, out = args[0], args[1], args[2], args[3], args[4]
    pitch_mode = args[5] if len(args) > 5 else "flat"
    from putao.core import Config, Project, TrackError
    cfg = Config(name="dick", author="dick", voicebank=voicebank, resampler="world")
    proj = Project(cfg)
    tr = proj.new_track("voice")
    vb_keys = set(tr.resampler.voicebank.entries.keys())
    phonemes = _phoneme_candidates(text, vb_keys)
    if pitch_mode == "auto":
        pitch_mode, params = _analyze_tone(text)
    else:
        params = {"start": 0, "end": 0, "dur_scale": 1.0}
        if pitch_mode == "happy":
            params = {"start": +2, "end": +5, "dur_scale": 0.85}
        elif pitch_mode == "sad":
            params = {"start": -2, "end": -6, "dur_scale": 1.25}
        elif pitch_mode == "angry":
            params = {"start": +4, "end": -8, "dur_scale": 0.8}
        elif pitch_mode == "question":
            params = {"start": 0, "end": +7, "dur_scale": 1.0}
    used = 0
    missing = []
    dur_scale = params.get("dur_scale", 1.0)
    d = max(60, int(int(duration) * dur_scale))
    total = len(phonemes)
    base_pitch = int(pitch)
    for i, ph in enumerate(phonemes):
        try:
            tr.note(ph, _pitch_for(i, total, pitch_mode, base_pitch, params), d)
            used += 1
        except TrackError:
            missing.append(ph)
        except Exception:
            pass
    if used == 0:
        print("ERR: 声库中找不到任何音素：" + " ".join(phonemes))
        sys.exit(2)
    proj.render(out)
    note = ""
    if missing:
        note = "（跳过音素：" + " ".join(missing) + "）"
    print("OK:" + out + note + " mode=" + pitch_mode)


if __name__ == "__main__":
    main()
