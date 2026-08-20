# -*- coding: utf-8 -*-
# utau_speak.py —— UTAU 合成 helper，由 utau_env（Python 3.11，含 putao/pykakasi/pypinyin）运行。
# 用法: python utau_speak.py <voicebank_dir> <pitch> <duration_ms> <text> <out.wav>
# 文本 → 音素（日文假名优先 / 中文拼音 fallback）→ putao（纯 Python UTAU 合成器）→ WAV
# 音素按声库 oto.ini 实际条目匹配（罗马音/假名/片假名变体兜底）
import sys

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


def main():
    voicebank, pitch, duration, text, out = sys.argv[1:6]
    from putao.core import Config, Project, TrackError
    cfg = Config(name="dick", author="dick", voicebank=voicebank, resampler="world")
    proj = Project(cfg)
    tr = proj.new_track("voice")
    vb_keys = set(tr.resampler.voicebank.entries.keys())
    phonemes = _phoneme_candidates(text, vb_keys)
    used = 0
    missing = []
    for ph in phonemes:
        try:
            tr.note(ph, int(pitch), int(duration))
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
    print("OK:" + out + note)


if __name__ == "__main__":
    main()
