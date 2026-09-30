# -*- coding: utf-8 -*-
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   style_guard.py - 确定性"风格闸" v2
#
#   不跟 Transformer 的注意力权重较劲，把"怎么说"从模型手里抽出来、
#   用确定性规则兜住：只洗文学腔表达，绝不删内容、绝不压缩。
#
#   定位：模型输出 定稿后、写入上下文(tree)之前 调用。
#   这样文学腔进不了上下文 → 掐断"文学自增强"；具体细节/动作/情绪
#   原样保留 → 角色照旧"活着"（不被压成"万年萝莉"）。
#
#   v2 关键：词汇层偏生活 + 放任度。
#     - 文学词 → 日常词（把"凝视"翻成"看着"、把"仿佛"翻成"好像"…）。
#     - GRAMMAR_OFFSET=0.10 放任度：控制清洗力度，保留人类语法偏离
#       （倒装/省略/语气词/断句/语序）——绝不清洗成"标准工整 AI 腔"。
#
#   只做表达层，不碰语义；倒装/省略/语气词/叹词 永不触碰。
# ============================================================

import re

# ---- 放任度：越高越"留着"人类的不完美，越少清洗 ----
GRAMMAR_OFFSET = 0.10

# ---- 文学词 → 生活词（词汇层偏生活，用日常用语替代） ----
_LIT_TO_LIFE = [
    ("眼眸", "眼睛"), ("双眸", "眼睛"), ("眸子", "眼睛"), ("眼瞳", "眼睛"),
    ("朱唇", "嘴唇"), ("唇瓣", "嘴唇"), ("双唇", "嘴唇"),
    ("面庞", "脸"), ("脸颊", "脸"), ("俏脸", "脸"),
    ("掌心", "手心"), ("纤手", "手"), ("玉手", "手"),
    ("倩影", "身影"),
    ("凝视", "看"), ("注视", "看"),
    ("轻叹", "叹"), ("叹息", "叹气"),
    ("呢喃", "小声说"), ("低语", "小声说"), ("低喃", "小声念"),
    ("顿时", "一下子"), ("霎时", "一下子"),
    ("缓缓", "慢慢"), ("徐徐", "慢慢"), ("渐渐", "慢慢"),
    ("仿佛", "好像"), ("宛如", "好像"), ("如同", "好像"), ("犹如", "好像"),
    ("好似", "好像"), ("恍若", "好像"),
    # ---- 言情/本子重灾区：身体/动作 文学词 → 生活词（去修辞、留内容，不审查） ----
    ("娇躯", "身子"), ("玉体", "身体"), ("酮体", "身体"),
    ("酥胸", "胸口"), ("玉峰", "胸口"),
    ("香肩", "肩膀"), ("玉肩", "肩膀"),
    ("玉腿", "腿"), ("纤腿", "腿"), ("修长的腿", "腿"),
    ("香颈", "脖子"), ("玉颈", "脖子"),
    ("腰肢", "腰"), ("纤腰", "腰"),
    ("脊背", "后背"), ("背脊", "后背"),
    ("轻颤", "抖"), ("战栗", "发抖"), ("酥麻", "麻"),
    ("潮红", "脸红"), ("泛潮", "红了"), ("泛红", "红了"),
    ("娇喘", "喘"), ("低吟", "哼"), ("娇吟", "哼"), ("婉转", "哼"),
    ("耳鬓厮磨", "贴着耳朵蹭"), ("缠绵", "缠在一起"), ("缱绻", "纠缠"),
]

# ---- 语境化比喻 → 事实（提升事实权重、减少花哨修辞；内容/结果保留） ----
_METAPHOR_TO_FACT = [
    ("像电流穿过四肢", "发麻"), ("电流窜过四肢", "发麻"), ("像电流穿过", "发麻"),
    ("电流一般", "发麻"), ("酥麻的电流", "麻意"),
    ("软成了一滩水", "浑身发软"), ("软成一滩水", "浑身发软"),
    ("融成一滩水", "浑身发软"), ("化成一滩水", "浑身发软"), ("化为春水", "浑身发软"),
    ("眼神拉丝地看着", "直勾勾地看着"), ("眼神拉丝", "直勾勾地"), ("空气变得粘稠", "空气安静"),
    ("浑身像被抽空了力气", "浑身没力气"), ("像被抽空了力气", "没力气"),
    ("脑子一片空白", "脑子空白"), ("意乱情迷", "脑子发懵"),
    ("呼吸变得沉重", "呼吸变重"),
    ("脸颊绯红", "脸红了"), ("双颊绯红", "脸红了"), ("酥软", "发软"),
]


def _metaphor_to_fact(text):
    """把常见言情/本子比喻 翻成事实化表达（去比喻、增事实，保留结果）。"""
    for src, dst in _METAPHOR_TO_FACT:
        if src in text:
            text = text.replace(src, dst)
    return text

# ---- 堆叠文学性副词（AA地 / AB地 / 四字地），只保留第一个 ----
_LIT_ADV = (
    "缓缓地|轻轻地|悄悄地|默默地|静静地|淡淡地|微微地|柔柔地|"
    "渐渐地|慢慢地|幽幽地|悄然地|恍然地|怯怯地|"
    "若有所思地|似有若无地|不经意地|无意识地|下意识地|"
    "不动声色地|若无其事地"
)
_STACK_ADV_RE = re.compile(
    "((?:" + _LIT_ADV + ")(?:、\\s*(?:" + _LIT_ADV + "))+)"
)

# ---- 铺陈性开头词（比喻/小说旁白），去掉但保留其后的内容 ----
_LIT_OPENERS = (
    "仿佛身处于", "仿佛置身于", "仿佛置身", "仿佛看到", "仿佛听到", "仿佛感觉",
    "宛如置身", "宛如一个", "宛如一场", "宛如被", "如同置身", "如同一个",
    "似有若无地", "恍若", "好像置身", "好像看到",
    "像是被", "像是身处于", "似乎置身于",
)
_OPENER_RE = re.compile("(" + "|".join(_LIT_OPENERS) + ")")

# ---- 句子拆分（只在超长句内部、于原标点处断开；阈值随放任度提高） ----
_WEAK_PUNC = "，、；：——…"


def _colloquialize(text):
    """文学词 → 生活词。整词替换，不碰语义、不碰语法结构。"""
    for src, dst in _LIT_TO_LIFE:
        if src in text:
            text = text.replace(src, dst)
    return text


def _strip_literary_openers(text):
    opener = "|".join(_LIT_OPENERS)
    text = re.sub(r"([。！？!?，,；]\s*)(" + opener + ")", r"\1", text)
    text = re.sub(r"^(" + opener + ")", "", text)
    return text


def _collapse_stacked_adverbs(text):
    def _sub(m):
        seg = m.group(0)
        first = re.match(_LIT_ADV, seg)
        return first.group(0) if first else seg
    return _STACK_ADV_RE.sub(_sub, text)


def _split_overlong(sentence, max_len):
    if len(sentence) <= max_len:
        return sentence
    parts = []
    s = sentence
    while len(s) > max_len:
        sp = -1
        for i, ch in enumerate(s):
            if ch in _WEAK_PUNC and i <= max_len:
                sp = i
        if sp <= 0:
            break
        parts.append(s[:sp + 1].strip())
        s = s[sp + 1:].strip()
    parts.append(s)
    return " ".join(p for p in parts if p)


def _split_long_sentences(text, max_len):
    out = []
    for line in text.split("\n"):
        rebuilt = ""
        for sent in re.split(r"(?<=[。！？!?])", line):
            if not sent.strip():
                continue
            rebuilt += _split_overlong(sent, max_len)
        out.append(rebuilt)
    return "\n".join(out)


def _collapse_ellipsis(text):
    text = re.sub(r"(?:。){4,}", "……", text)
    text = re.sub(r"(?:…){3,}", "……", text)
    text = re.sub(r"(?:\.){4,}", "……", text)
    return text


def _collapse_ws(text):
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def style_guard(text, enabled=True, grammar_offset=None, long_sentence=False):
    """确定性风格闸：洗文学腔、词汇偏生活、保留人类语法偏离与一切内容。
    long_sentence=True 时不再拆长句（长句模式），允许更流畅/文学化的长句自然发挥。"""
    if not enabled or not isinstance(text, str) or not text.strip():
        return text
    offset = float(grammar_offset) if grammar_offset is not None else GRAMMAR_OFFSET
    # 放任度越大，长句拆分阈值越高（越少拆，越保留自然的语序/倒装/断句）
    max_len = 5000 if long_sentence else int(70 + offset * 300)
    t = _collapse_ellipsis(text)
    t = _metaphor_to_fact(t)
    t = _colloquialize(t)
    t = _strip_literary_openers(t)
    t = _collapse_stacked_adverbs(t)
    t = _split_long_sentences(t, max_len)
    t = _collapse_ws(t)
    return t

if __name__ == "__main__":
    samples = [
        "她凝视着我，眸子里仿佛藏着万千星辰，缓缓地、轻轻地、悄悄地，她轻叹一声，朱唇微启：\"没事的。\"",
        "嗯，我今天煮了番茄鸡蛋面，有点咸但很满足。你吃了吗？",
        "喂！你干嘛呢？快点过来帮忙。",
        "他就是有点怪，看我的眼神总是躲躲闪闪的，像是有啥心事。",
    ]
    for s in samples:
        print("原:", s)
        print("洗:", style_guard(s))
        print("-" * 60)
