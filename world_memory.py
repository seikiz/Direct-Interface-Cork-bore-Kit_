# -*- coding: utf-8 -*-
"""world_memory.py —— 世界记忆的演化：把剧情里发生过的**世界级事实**沉淀成
「这个世界现在是什么样」。

为什么要有它
------------
`memory/_world/` 一直是个空容器：世界设定是**死的** —— 世界卡写一遍就永远那样。
剧情里发生过的事（城南的桥塌了、宗门换了掌门、她和你在码头吵过架）不会沉淀，
于是模型下一轮既可以拿旧设定接着演，也可以自己编一个跟前面矛盾的新说法。

生活层（life_core）管"她今天吃了什么"，空间层（space_core）管"她此刻在哪"，
这个模块管**这个世界现在是什么样**。

四条约束（沿用 life_core / space_core 定下的规矩）
--------------------------------------------------
  ① **约束优先**：它得能拦住自相矛盾，不是给模型加一段抒情提示词。同一地点说塌了
     又说没塌，归并成**一条**、按时间取最新，而不是并存两条互相打脸。
  ② **每轮只注入一小段**（默认 <=240 字，与另外两层一致），按优先级吃预算，
     截断不是从尾巴硬截。
  ③ **注入是只读的**：写入只发生在一轮结束后的抽取里（插件钩子 `on_message_received`）。
     所以同一轮重试/重放不会把强度刷上去 —— 空间层的"穿帮提醒计数"是反例，
     它必须在注入里 +1；世界记忆不需要那样做。
  ④ **确定性优先**：抽取是规则（可测、可解释），不调模型。想用模型辅助就显式接钩子
     （`set_model_extractor`），默认没有。

强度与衰减：为什么按**世界时间**算，以及 720 倍意味着什么
--------------------------------------------------------
`strength` 是「这条事实**此刻有多值得提醒模型**」，不是「它是否还成立」——
成立与否由内容本身决定，而且**永不自动删除**（只有一个例外：一个世界最多 max_facts 条，
超了丢最弱的，防止文件无限长）。

衰减口径与 `life_core.world_clock` / `space_core.world_minutes_since` 一致
（现实间隔 × 倍率），只是单位换成"世界天"：

    世界天数 = 现实秒数 × 倍率 / 86400
    strength(t) = strength × 0.5 ** (世界天数 / 半衰期)

为什么不用 `salience.py` 的 `AGE_MODE="real"`：那是**角色记忆**的口径，那边刻意按现实
时间衰老（注释里写了：乘上倍率会让 720 倍下的记忆只活 23 分钟、角色变金鱼）。
世界事实不是"角色的注意力"，它是**世界的现状**：那边过了多少日子，这件事就该显得多旧。

代价要写清楚：**同一个门槛在不同倍率下对应的现实时长差很多**。默认门槛 0.35、
地点半衰期 30 世界天，从满强度掉到门槛下要 45.4 世界天 ——
    · 1 倍：45 天
    · 720 倍：现实 91 分钟（因为 720 倍时现实 1 分钟 = 那边 12 小时）
这是**故意的**：那边一天过三遍的时候，一个半小时前的旧事本来就不该还在每轮提醒里。
而且它只是**淡出注入**，不清除；被剧情重新提起立刻回到满强度；也可以用
`/世界记忆 钉 <关键词>` 钉住（钉住的不淡出）。

半衰期按类别分（越"硬"的越慢）：

| 类别 | 半衰期（世界天） | 为什么 |
|---|---|---|
| rule 规则 | 不衰减 | 世界的物理定律/禁忌；写错了要改世界卡，不是等它淡出 |
| place 地点 | 30 | 桥塌了、店关门了这类"现状" |
| item 物品 | 30 | 同上 |
| org 组织 | 7 | 掌门换人这类剧情推进最容易被新剧情覆盖 |
| relation 关系 | 7 | 同上 |

归并与冲突
----------
一条事实的键是 `kind:subject`（subject 归一化：去标点空格、去尾部的"的/了"）。
**同一个主体只留一条** —— 这是刻意的：同一件事的两种说法（「云梦宗换了掌门」与
「云梦宗的掌门是陆沉」）如果各存一条，注入里就会被同一件事刷屏，而且很容易互相打脸。

  · 同一键再次出现 → **合并**：seen+1、强度回到满值附近、text 用最新说法、sources 留最近几条；
  · 同一键但 state 变了 → 也是合并，但记下 `prev_state` / `prev_at`：**最新一次说法算数**。

冲突**不留双份**（"桥先塌了后修好"在档案里只能有一条：修好了，旧的进 prev_state）。

字段（人在 `memory/_world/<世界名>.json` 里能直接读懂，也能手改）：

    world        世界名（没有世界卡时是 _default）
    updated      最后一次写盘时间
    facts[]      id / kind / subject / state / text / strength / seen /
                 first_seen / last_seen / prev_state / prev_at / pinned / sources[]

用法（命令入口在 plugins/world_memory_plugin.py：/世界记忆）：
    import world_memory as wm
    wm.note_turn(user_input, ai_reply, world=world, speaker="薇拉", scale=720)
    text = wm.injection_text(chain, scale=720, world=world, name="薇拉")
"""
import io
import json
import os
import re
import threading
from datetime import datetime

try:
    import app_paths
except Exception:                                     # pragma: no cover
    app_paths = None

try:
    import save_guard                                # 原子写 + 备份（别自己造）
except Exception:                                     # pragma: no cover
    save_guard = None

DIRNAME = os.path.join("memory", "_world")
DEFAULT_WORLD = "_default"

# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  一、配置（跟 time_scale.json / life_config.json 一个规矩：自己的文件、自己的缓存）
# ============================================================
DEFAULTS = {
    "enabled": True,
    "max_chars": 240,             # 注入上限（与另外两层一致）
    "half_life_days": 30.0,       # 地点/物品的半衰期（世界天）
    "org_half_life_days": 7.0,    # 组织/关系
    "fade_threshold": 0.35,       # 低于它就不进注入（与 salience.KEEP_THRESHOLD 同值，口径一致）
    "strength_max": 3.0,
    "reinforce": 0.9,             # 每次被重新提起加多少
    "max_facts": 400,             # 一个世界最多记这么多条（唯一的自动删除路径）
    "max_sources": 3,             # 每条事实留几条原始说法（给人核对用）
    "focus_messages": 2,          # 用最近几条消息做"场景相关度"
    "state_dir": DIRNAME,
}

_lock = threading.Lock()
_cache = None

GUIDE = ("（上面是这个世界已经发生过的事，别和它们矛盾；要改就直接用新剧情改，"
         "别当没发生。）")

# 这些主语不是"世界里的东西"（出现频率高、且没有指代，记下来只会污染注入）
_STOP_SUBJECTS = frozenset((
    u"这", u"那", u"这里", u"那里", u"这个", u"那个", u"什么", u"怎么", u"为什么",
    u"事情", u"时候", u"地方", u"东西", u"问题", u"大家", u"有人", u"别人",
))

# 否定/未然的前缀：命中就**不记**（「差点塌了」不是「塌了」）
_NEG_PREFIX = (u"没", u"没有", u"差点", u"险些", u"快要", u"就要", u"将要", u"要",
               u"万一", u"别", u"不再", u"不会", u"是否", u"难道")
# 假设句整句跳过：「如果桥塌了」不是「桥塌了」
_HYPOTHETICAL_START = (u"如果", u"要是", u"假如", u"万一", u"除非", u"若是",
                       u"要不是", u"倘若")

# 转述/框套词：主语前面挂着这些词时，真正的主语在它后面
# （「她告诉我城南的桥塌了」的主语是"城南的桥"，不是"她告诉我城南的桥"）
_FRAME_WORDS = (u"听说", u"据说", u"告诉我", u"告诉", u"大家都说", u"都说", u"说",
                u"看见", u"看到", u"知道", u"觉得", u"以为", u"发现", u"记得",
                u"原来", u"已经", u"刚刚", u"刚才", u"突然", u"忽然", u"结果",
                u"所以", u"可是", u"但是", u"不过", u"然后", u"后来", u"现在")
# 关系里的地点尾巴：「她和你在码头吵过架」的关系主体是「她和你」
_LOC_TAIL = re.compile(u"在[^和跟与]{1,10}$")

_PUNCT_CHARS = u" \t\r\n，。、；：！？!?.,;:~·…-—「」『』（）()[]【】\"'“”‘’"
_PUNCT = re.compile(u"[" + re.escape(_PUNCT_CHARS) + u"]")
# 切句：连句末标点一起留（问句与假设句要靠它判断）
_SENT_WITH_END = re.compile(u"([^。！？!?；;\\n]+)([。！？!?；;]?)")
_TAIL_JUNK = re.compile(u"(的|了|着|过|呢|吧|啊|呀)+$")
# 主语和动词之间的状语会被贪婪匹配粘进主语（「城南的桥又塌了」→"城南的桥又"），要切掉
_ADV_TAIL = re.compile(u"(又|也|还|再|就|才|已经|刚刚|刚才|突然|忽然|马上|立刻|"
                       u"终于|果然|竟然|居然|还是|一直|正在|马上)+$")


def config_path():
    try:
        base = app_paths.get_base_dir() if app_paths else None
    except Exception:
        base = None
    base = base or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "world_memory_config.json")


def load_config():
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
    data = dict(DEFAULTS)
    try:
        with io.open(config_path(), "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            for k in DEFAULTS:
                if k in got:
                    data[k] = got[k]
    except Exception:
        pass
    with _lock:
        _cache = dict(data)
    return data


def save_config(cfg):
    global _cache
    data = dict(DEFAULTS)
    data.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    with _lock:
        _cache = dict(data)
    try:
        p = config_path()
        tmp = p + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception as e:
        print("[world_memory] 配置保存失败: %s" % e)
    return data


def enabled():
    try:
        return bool(load_config().get("enabled"))
    except Exception:
        return False


# ============================================================
#  二、持久化：一个世界一份（memory/_world/<世界名>.json）
# ============================================================
def _safe_name(name):
    s = re.sub(r'[\\/:*?"<>|]', "_", str(name or "").strip())
    return s or DEFAULT_WORLD


def world_key(world):
    """世界名 → 文件键。没有世界卡就落到 _default（不建"无主"的第三条路）。"""
    if isinstance(world, dict):
        nm = str(world.get("name") or "").strip()
        if nm:
            return nm
    return DEFAULT_WORLD


def state_path(world, cfg=None):
    cfg = cfg or load_config()
    try:
        base = app_paths.get_base_dir() if app_paths else None
    except Exception:
        base = None
    base = base or os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, str(cfg.get("state_dir") or DIRNAME))
    return os.path.join(d, _safe_name(world_key(world)) + ".json")


def _parse_ts(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def _iso(dt):
    d = dt if isinstance(dt, datetime) else datetime.now()
    return d.replace(microsecond=0).isoformat()


def _scale(scale=None):
    """倍率：None = 读应用设置（time_scale）；显式给了但非法 → 当 1 倍（不偷偷用全局设置）。

    与 space_core._scale 同一条规矩：调用方明确传了坏值，退回"不加速"比"用另一个来源的
    倍率"更容易解释（否则测试与调用点都会意外受到全局设置影响）。
    """
    if scale is None:
        try:
            import time_scale as _ts
            return float(_ts.load())
        except Exception:
            return 1.0
    try:
        v = float(scale)
        return v if v > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def empty_state(world):
    return {"world": world_key(world), "updated": "", "facts": []}


def load_state(world, cfg=None):
    """读一个世界的记忆。文件不存在/坏了都返回空状态（不抛）。"""
    p = state_path(world, cfg)
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict):
            return empty_state(world)
        if not isinstance(st.get("facts"), list):
            st["facts"] = []
        st.setdefault("world", world_key(world))
        st.setdefault("updated", "")
        return st
    except Exception:
        return empty_state(world)


def save_state(world, st, cfg=None):
    """原子写 + 备份（用 save_guard，别自己造）。"""
    p = state_path(world, cfg)
    try:
        d = os.path.dirname(p)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        st["world"] = world_key(world)
        st["updated"] = _iso(None)
        if save_guard is not None:
            save_guard.atomic_write_json(p, st)
        else:                                        # pragma: no cover
            tmp = p + ".tmp"
            with io.open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
    except Exception as e:
        print("[world_memory] 世界记忆保存失败: %s" % e)
    return p


# ============================================================
#  三、抽取：从一轮里认出"世界状态变了"的候选（规则，可测、可解释）
# ============================================================
# 每条规则：(kind, 正则, subject 组名, state 生成器)
# 精度优先：宁可漏（模型自己还记着），不可错（错的事实会污染注入，而且会被当"定局"）。
_PLACE_VERBS = (u"塌了|垮了|着火了|被淹了|被烧了|被拆了|拆了|炸了|沉了|封了|"
                u"修好了|重建了|重新开张|关张了|关门了|开业了")
_ORG_VERBS = (u"换了掌门|换掌门|换了老板|换了首领|换了宗主|易主了|合并了|解散了|"
              u"成立了|被灭了|投降了|搬走了|扩张了")
_ITEM_VERBS = (u"丢了|碎了|被偷了|被抢了|弄坏了|找到了|不见了|被毁")
_REL_VERBS = (u"吵过架|吵架了|和好了|闹翻了|翻脸了|结婚了|订婚了|分手了|决裂了|"
              u"结盟了|认识了|成了朋友|反目了|合作了")

_NP = u"[^，。、；：！？!?\\s]{1,12}"          # 一个"名字"（不含标点/空白）

_RULES = (
    # 地点状态：城南的桥塌了 / 客栈着火了 / 老码头修好了（允许中间一个逗号：「城南的桥，塌了」）
    {"kind": "place",
     "re": re.compile(u"(?P<s>" + _NP + u")[，,]?(?P<v>" + _PLACE_VERBS + u")"),
     "state": lambda m: m.group("v")},
    # 组织变化：云梦宗换了掌门 / 商会易主了
    {"kind": "org",
     "re": re.compile(u"(?P<s>" + _NP + u")[，,]?(?P<v>" + _ORG_VERBS + u")"),
     "state": lambda m: m.group("v")},
    # 组织里具体是谁：云梦宗的掌门是陆沉 / 城主换成了老张
    {"kind": "org",
     "re": re.compile(u"(?P<s>" + _NP + u")(?:的)?(?P<what>掌门|城主|老板|首领|队长|宗主|掌柜)"
                      u"(?:换成|换成了|变成了|现在是|换作|是)(?P<who>" + _NP + u")"),
     "state": lambda m: u"%s是%s" % (m.group("what"), m.group("who"))},
    # 物品：玉佩碎了 / 那本书丢了
    {"kind": "item",
     "re": re.compile(u"(?P<s>" + _NP + u")[，,]?(?P<v>" + _ITEM_VERBS + u")"),
     "state": lambda m: m.group("v")},
    # 关系：阿绫和你吵过架 / 老约翰跟首领闹翻了（我/你 会按说话人归一化）
    {"kind": "relation",
     "re": re.compile(u"(?P<a>我|你|您|" + _NP + u")(?:和|跟|与)(?P<b>我|你|您|" + _NP + u")"
                      u"[，,]?(?P<v>" + _REL_VERBS + u")"),
     "state": lambda m: m.group("v")},
    # 规则：规矩是…… / 这里的禁忌：夜里不许出城（只认显式名词，避免把「你不能这样」记成规则）
    {"kind": "rule",
     "re": re.compile(u"(?:规矩|规则|法则|禁忌|铁律|禁令)[:：]?\\s*(?P<v>[^。！？!?\\n]{4,40})"),
     "state": lambda m: re.sub(u"^(是|为|就是|：)", u"", m.group("v").strip())},
)

# 可选：模型辅助抽取（默认没有；接了就用，两边结果走同一条归并路径）
_model_extractor = None


def set_model_extractor(fn):
    """接一个"模型辅助抽取"钩子：fn(user_input, ai_reply) -> [{"kind","subject","state"}, ...] 或 None。

    为什么留钩子而不是直接内置：规则抽取**可测可解释**，而调模型有成本、有不确定性、
    还要网络 —— 这两条路应该能分开开关。默认 None（关着）；命令面板会显示有没有接。
    """
    global _model_extractor
    _model_extractor = fn if callable(fn) else None
    return _model_extractor


def has_model_extractor():
    return callable(_model_extractor)


def normalize_subject(s):
    """主语归一化：去标点空白、去尾部的"的/了/着/过/呢/吧/啊/呀"，截到 24 字。"""
    t = _PUNCT.sub(u"", str(s or ""))
    t = _TAIL_JUNK.sub(u"", t)
    return t[:24]


def _cut_frame(s):
    """把主语前面挂着的转述/框套词切掉。

    「她告诉我城南的桥塌了」里贪婪匹配拿到的主语是"她告诉我城南的桥"，
    真正的主语在"告诉我"之后。切完为空就返回空串（宁可不记）。
    """
    t = str(s or u"")
    best = 0
    for w in _FRAME_WORDS:
        i = t.rfind(w)
        if i >= 0:
            best = max(best, i + len(w))
    return t[best:]


def _clean_subject(s, relation=False):
    t = _cut_frame(s)
    if relation:
        t = _LOC_TAIL.sub(u"", t)      # 「你在码头」→「你」
    t = _ADV_TAIL.sub(u"", t)          # 「城南的桥又」→「城南的桥」
    return normalize_subject(t)


def _clean_state(s):
    """状态归一化：只去标点空白，**保留尾部的"了"**。

    主语要去掉"了/的"（「城南的桥塌了」的主语是"城南的桥"），状态正好相反：
    「塌了」「修好了」「换了掌门」里的"了"是内容的一部分，去掉就变成「城南的桥塌」。
    """
    return _PUNCT.sub(u"", str(s or u""))[:24]


def _negated(fragment, pos):
    """动词/变化词前面几个字里有否定、未然、假设词 → 这不是一条"已经发生的事"。"""
    head = fragment[max(0, pos - 4):pos]
    return any(w in head for w in _NEG_PREFIX)


def _fragments(text):
    """切成句子（连标点一起切，好判断是不是问句）。

    问句不抽取：「桥塌了吗？」不是断言。假设句整句跳过：「如果桥塌了」同上。
    """
    out = []
    for m in _SENT_WITH_END.finditer(u"" if text is None else u"%s" % text):
        frag = m.group(1).strip()
        end = m.group(2)
        if not frag:
            continue
        if end in (u"？", u"?"):
            continue
        if frag.startswith(_HYPOTHETICAL_START):
            continue
        out.append(frag)
    return out


def _pick_subject(m, kind):
    gd = m.groupdict()
    if kind == "rule":
        return u""                     # 规则没有"主体"，用状态当键（见下）
    if u"s" in gd:
        return m.group("s")
    return u"%s和%s" % (m.group("a"), m.group("b"))


def _map_pronoun(name, speaker, player_name):
    t = str(name or "").strip()
    if t in (u"我",):
        return speaker or u"她"
    if t in (u"你", u"您"):
        return player_name or u"你"
    return t


def extract_facts(user_input, ai_reply, speaker=None, player_name=u"你", cfg=None):
    """规则抽取：返回 [{"id","kind","subject","state","text","source"}, ...]（同一轮内已去重）。

    抽两边的文本：AI 的叙述是"世界在发生什么"，玩家的输入也可能是设定声明
    （「城南的桥塌了」由玩家说出同样算）。问句跳过，否定/未然跳过。
    """
    found = {}
    pair_seen = set()                  # 同一条"主语+状态"只记一次（别让 place/item 各记一份）
    for text in (ai_reply, user_input):
        for frag in _fragments(text):
            for rule in _RULES:
                for m in rule["re"].finditer(frag):
                    gd = m.groupdict()
                    # 否定/未然要看**动词**前面几个字（「城南的桥差点塌了」的"差点"
                    # 夹在主语和动词之间，看匹配起点是看不出来的）
                    vpos = m.start("v") if "v" in gd else m.start()
                    if _negated(frag, vpos):
                        continue
                    state = _clean_state(rule["state"](m)) or u"发生了变化"
                    if rule["kind"] == "rule":
                        # 规则没有"主体"：用内容本身当键（再出现同样的规矩就归并）
                        subject = state
                        if len(subject) < 4:
                            continue
                    else:
                        subject = _pick_subject(m, rule["kind"])
                        if rule["kind"] == "relation":
                            a = _map_pronoun(gd.get("a"), speaker, player_name)
                            b = _map_pronoun(gd.get("b"), speaker, player_name)
                            subject = u"%s和%s" % (_clean_subject(a, relation=True),
                                                  _clean_subject(b, relation=True))
                        else:
                            subject = _clean_subject(subject)
                    if not subject or subject in _STOP_SUBJECTS:
                        continue
                    pair = u"%s|%s" % (subject, state)
                    if pair in pair_seen:
                        continue
                    pair_seen.add(pair)
                    fid = u"%s:%s" % (rule["kind"], subject)
                    # 同一个主体同理只留一条：后面的说法覆盖前面的
                    # （「云梦宗换了掌门。云梦宗的掌门是陆沉」→ 一条，状态是后者）
                    if rule["kind"] == "rule":
                        text_out = u"规矩：%s" % state
                    else:
                        text_out = u"%s%s" % (subject, state)
                    found[fid] = {"id": fid, "kind": rule["kind"], "subject": subject,
                                  "state": state, "text": text_out, "source": frag[:40]}
    if has_model_extractor():
        try:
            extra = _model_extractor(user_input, ai_reply) or []
        except Exception as e:
            print("[world_memory] 模型抽取失败（忽略）: %s" % e)
            extra = []
        for it in extra:
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind") or "place").strip() or "place"
            subject = normalize_subject(it.get("subject"))
            state = normalize_subject(it.get("state"))
            if not subject or not state or subject in _STOP_SUBJECTS:
                continue
            fid = u"%s:%s" % (kind, subject)
            found.setdefault(fid, {"id": fid, "kind": kind, "subject": subject, "state": state,
                                   "text": u"%s%s" % (subject, state),
                                   "source": str(it.get("source") or u"模型抽取")[:40]})
    return list(found.values())


# ============================================================
#  四、强度与衰减（按**世界时间**）
# ============================================================
def half_life_of(kind, cfg=None):
    """该类别的半衰期（世界天）。None = 不衰减（规则）。"""
    cfg = cfg or load_config()
    k = str(kind or "")
    if k == "rule":
        return None
    if k in ("org", "relation"):
        try:
            v = float(cfg.get("org_half_life_days"))
            return v if v > 0 else DEFAULTS["org_half_life_days"]
        except (TypeError, ValueError):
            return DEFAULTS["org_half_life_days"]
    try:
        v = float(cfg.get("half_life_days"))
        return v if v > 0 else DEFAULTS["half_life_days"]
    except (TypeError, ValueError):
        return DEFAULTS["half_life_days"]


def world_days_since(ts, scale=None, now=None):
    """现实时刻 → 那边过了多少**天**（系统时间 = 1 倍起源，乘倍率）。

    与 space_core.world_minutes_since 同一个换算，只是单位换成天：
    720 倍时现实 1 分钟 = 那边 12 小时 = 0.5 世界天。
    """
    d = _parse_ts(ts)
    if d is None:
        return None
    end = now if isinstance(now, datetime) else datetime.now()
    real = max(0.0, (end - d).total_seconds())
    return real * _scale(scale) / 86400.0


def current_strength(fact, scale=None, now=None, cfg=None):
    """这条事实此刻的强度（按世界时间衰减到 now）。"""
    if not isinstance(fact, dict):
        return 0.0
    try:
        base = float(fact.get("strength") or 0.0)
    except (TypeError, ValueError):
        base = 0.0
    hl = half_life_of(fact.get("kind"), cfg)
    if hl is None:
        return base
    days = world_days_since(fact.get("last_seen"), scale, now)
    if days is None or days <= 0:
        return base
    return base * (0.5 ** (days / hl))


def _trim_facts(st, cfg):
    """条数上限：超了丢最弱的（这是**唯一**的自动删除路径）。"""
    try:
        cap = int(cfg.get("max_facts") or DEFAULTS["max_facts"])
    except (TypeError, ValueError):
        cap = DEFAULTS["max_facts"]
    facts = st.get("facts") or []
    if cap <= 0 or len(facts) <= cap:
        return 0
    facts.sort(key=lambda f: (float(f.get("strength") or 0.0), str(f.get("last_seen") or "")))
    dropped = len(facts) - cap
    st["facts"] = facts[dropped:]
    return dropped


def merge_fact(st, fact, scale=None, now=None, cfg=None):
    """把一条抽取结果并进状态。返回 "added" / "merged" / "conflict"。

    · 没见过的键 → added（强度从 1.0 起）
    · 见过、state 一样 → merged（seen+1、强度回升）
    · 见过、state 变了 → conflict（仍是合并，只记 prev_state/prev_at：最新说法算数，
      绝不并存两条互相打脸的）
    """
    cfg = cfg or load_config()
    now = now if isinstance(now, datetime) else datetime.now()
    now_iso = _iso(now)
    facts = st.setdefault("facts", [])
    fid = str(fact.get("id") or u"")
    cur = None
    for f in facts:
        if str(f.get("id") or u"") == fid:
            cur = f
            break
    try:
        cap = float(cfg.get("strength_max") or DEFAULTS["strength_max"])
    except (TypeError, ValueError):
        cap = DEFAULTS["strength_max"]
    try:
        gain = float(cfg.get("reinforce") or DEFAULTS["reinforce"])
    except (TypeError, ValueError):
        gain = DEFAULTS["reinforce"]
    try:
        keep_src = int(cfg.get("max_sources") or DEFAULTS["max_sources"])
    except (TypeError, ValueError):
        keep_src = DEFAULTS["max_sources"]

    if cur is None:
        facts.append({
            "id": fid,
            "kind": str(fact.get("kind") or "place"),
            "subject": str(fact.get("subject") or u""),
            "state": str(fact.get("state") or u""),
            "text": str(fact.get("text") or u""),
            "strength": min(cap, 1.0),
            "seen": 1,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "prev_state": "",
            "prev_at": "",
            "pinned": bool(str(fact.get("kind") or "") == "rule"),
            "sources": [str(fact.get("source") or u"")[:40]],
        })
        _trim_facts(st, cfg)
        return "added"

    old_state = str(cur.get("state") or u"")
    new_state = str(fact.get("state") or u"")
    changed = bool(old_state and new_state and old_state != new_state)
    base = current_strength(cur, scale, now, cfg)
    cur["strength"] = min(cap, base + (gain * 1.5 if changed else gain))
    cur["seen"] = int(cur.get("seen") or 1) + 1
    if changed:
        cur["prev_state"] = old_state
        cur["prev_at"] = str(cur.get("last_seen") or "")
    cur["subject"] = str(fact.get("subject") or cur.get("subject") or u"")
    cur["state"] = new_state or old_state
    cur["text"] = str(fact.get("text") or cur.get("text") or u"")
    cur["last_seen"] = now_iso
    src = str(fact.get("source") or u"")[:40]
    if src:
        arr = [s for s in (cur.get("sources") or []) if s]
        if src not in arr:
            arr.insert(0, src)
        cur["sources"] = arr[:max(0, keep_src)]
    return "conflict" if changed else "merged"


def note_turn(user_input, ai_reply, world=None, speaker=None, scale=None, now=None, cfg=None,
              player_name=u"你"):
    """一轮结束后调用：抽取 → 归并 → 落盘。返回计数（给日志/测试看）。"""
    cfg = cfg or load_config()
    out = {"added": 0, "merged": 0, "conflict": 0, "total": 0, "enabled": bool(cfg.get("enabled"))}
    if not cfg.get("enabled"):
        return out
    facts = extract_facts(user_input, ai_reply, speaker=speaker, player_name=player_name, cfg=cfg)
    if not facts:
        return out
    st = load_state(world, cfg)
    for f in facts:
        kind = merge_fact(st, f, scale=scale, now=now, cfg=cfg)
        out[kind] = out.get(kind, 0) + 1
    save_state(world, st, cfg)
    out["total"] = len(st.get("facts") or [])
    return out


# ============================================================
#  五、检索：按当前场景挑哪几条（只读）
# ============================================================
def _focus_text(chain, cfg, extra=u""):
    """场景文本：最近几条消息 + 本轮输入（给"相关度"用）。"""
    try:
        n = int(cfg.get("focus_messages") or DEFAULTS["focus_messages"])
    except (TypeError, ValueError):
        n = DEFAULTS["focus_messages"]
    parts = [u"%s" % (extra or u"")]
    msgs = [m for m in (chain or []) if isinstance(m, dict) and m.get("role") != "system"]
    for m in msgs[-max(0, n):] if n > 0 else []:
        parts.append(str(m.get("content") or ""))
    return u" ".join(parts)


def _current_place(name):
    """她此刻在哪（给"这条事实跟眼前这一幕有关吗"加分）。空间层没开就返回空串。"""
    if not name:
        return u""
    try:
        import space_core as _sp
        st = _sp.load_state(name)
        return str(st.get("place") or u"")
    except Exception:
        return u""


def _head_noun(subject):
    """主语的中心词：「城南的桥」→「桥」。场景相关度按它匹配（原话里常说"那座桥"）。"""
    return str(subject or u"").split(u"的")[-1]


def rank_facts(st, scale=None, now=None, focus=u"", place=u"", cfg=None):
    """挑出"此刻值得提醒"的事实，按分数降序。返回 [(fact, score, strength), ...]。

    分数 = 衰减后的强度
         + 0.6 场景里刚提到过（主语或状态出现在最近的消息/本轮输入里）
         + 0.4 跟"她此刻在哪"有关
         + 0.3 规则（硬约束，宁可先说）
         + 0.5 钉住的
    门槛：钉住的与规则不参与淡出判定，其余强度低于 fade_threshold 就不进注入（但留档）。
    """
    cfg = cfg or load_config()
    now = now if isinstance(now, datetime) else datetime.now()
    try:
        thr = float(cfg.get("fade_threshold") or DEFAULTS["fade_threshold"])
    except (TypeError, ValueError):
        thr = DEFAULTS["fade_threshold"]
    focus = focus or u""
    place = place or u""
    out = []
    for f in (st.get("facts") or []):
        if not isinstance(f, dict):
            continue
        s = current_strength(f, scale, now, cfg)
        pinned = bool(f.get("pinned"))
        kind = str(f.get("kind") or u"")
        if not pinned and kind != "rule" and s < thr:
            continue
        score = s
        subj = str(f.get("subject") or u"")
        state = str(f.get("state") or u"")
        # 场景相关度：全名对得上，或者中心词对得上（「城南的桥」↔「那座桥」）
        head = _head_noun(subj)
        if focus:
            if (subj and subj in focus) or (state and state in focus) or (head and head in focus):
                score += 0.6
        if subj and place and (subj in place or place in subj):
            score += 0.4
        if kind == "rule":
            score += 0.3
        if pinned:
            score += 0.5
        out.append((f, score, s))
    # 稳定排序三段式：先 id（同分同时间的确定性），再时间倒序（最近提过的先），最后分数
    out.sort(key=lambda x: str(x[0].get("id") or u""))
    out.sort(key=lambda x: str(x[0].get("last_seen") or u""), reverse=True)
    out.sort(key=lambda x: -x[1])
    return out


def _age_note(fact, scale=None, now=None, cfg=None):
    """（N 次，那边 M 天前）—— 次数只在 >1 时出现，时间只在超过 1 世界天时出现。"""
    bits = []
    try:
        seen = int(fact.get("seen") or 1)
    except (TypeError, ValueError):
        seen = 1
    if seen > 1:
        bits.append(u"%d 次" % seen)
    days = world_days_since(fact.get("last_seen"), scale, now)
    if days is not None and days >= 1.0:
        if days >= 30:
            bits.append(u"那边 %.0f 个月前" % (days / 30.0))
        else:
            bits.append(u"那边 %.0f 天前" % days)
    if bool(fact.get("pinned")):
        bits.append(u"钉住")
    return (u"（" + u"，".join(bits) + u"）") if bits else u""


def injection_text(chain=None, scale=None, world=None, cfg=None, now=None, focus=u"",
                   name=None):
    """每轮注入的【世界·演化】。关掉 / 没有值得提醒的事实 / 算不出，都返回 ""。

    只读：不写盘、不改强度（写入只在一轮结束后的 note_turn 里）。
    长度按优先级吃预算：分数最高的两条是"必须"（否则整段没用），其余能塞多少塞多少。
    """
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    if not cfg.get("enabled"):
        return ""
    st = load_state(world, cfg)
    facts = st.get("facts") or []
    if not facts:
        return ""
    focus_txt = _focus_text(chain, cfg, extra=focus)
    ranked = rank_facts(st, scale=scale, now=now, focus=focus_txt,
                        place=_current_place(name), cfg=cfg)
    if not ranked:
        return ""                       # 都淡出了：这轮不提，但档案还在

    head = u"【世界·演化】这些是定局："
    items = []
    for i, (f, _score, _s) in enumerate(ranked):
        line = u"· %s%s" % (str(f.get("text") or f.get("subject") or u""),
                            _age_note(f, scale, now, cfg))
        items.append((line, i < 2))     # 前两条必须留
    try:
        room_total = int(cfg.get("max_chars") or DEFAULTS["max_chars"])
    except (TypeError, ValueError):
        room_total = DEFAULTS["max_chars"]
    room = max(60, room_total - len(head) - len(GUIDE) - 2)
    kept = []
    for line, must in items:
        piece = line + (u"\n" if kept or must else u"")
        if kept and len(u"".join(kept)) + len(piece) > room and not must:
            continue
        kept.append(piece)
    body = u"".join(kept).rstrip(u"\n")
    out = head + (u"\n" + body if body else u"")
    # 截断的算术要连"换行 + 省略号"一起算进去（空间层那边因为漏了这个差过一个字）
    if len(out) + 1 + len(GUIDE) > room_total:
        keep = max(0, room_total - len(GUIDE) - 2)
        out = out[:keep].rstrip(u"、，。· ") + u"…"
    return out + u"\n" + GUIDE


# ============================================================
#  六、命令面板要的那些操作
# ============================================================
def describe(world=None, scale=None, cfg=None, now=None, name=None):
    """给 /世界记忆 看的完整状态（比注入详细，含已淡出的）。"""
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    st = load_state(world, cfg)
    facts = st.get("facts") or []
    now = now if isinstance(now, datetime) else datetime.now()
    out = [u"世界记忆：%s（%s）" % (u"开" if cfg.get("enabled") else u"关",
                                 world_key(world))]
    out.append(u"文件：%s" % state_path(world, cfg))
    out.append(u"外部模型抽取：%s" % (u"已接" if has_model_extractor() else u"未接（规则抽取）"))
    if not facts:
        out.append(u"还没有记下任何事 —— 剧情里出现「桥塌了」「掌门换人了」这类"
                   u"世界级变化时才会记。")
        return u"\n".join(out)
    try:
        thr = float(cfg.get("fade_threshold") or DEFAULTS["fade_threshold"])
    except (TypeError, ValueError):
        thr = DEFAULTS["fade_threshold"]
    ranked = rank_facts(st, scale=scale, now=now, cfg=cfg)
    live = len(ranked)
    out.append(u"事实 %d 条（还在注入里的 %d 条，其余已淡出但在档）" % (len(facts), live))
    shown = 0
    for f, _sc, s in ranked:
        shown += 1
        out.append(u"  · %s%s" % (str(f.get("text") or u""), _age_note(f, scale, now, cfg)))
    for f in facts:
        if any(f is g for g, _s, _x in ranked):
            continue
        out.append(u"  ·（淡出 %.2f）%s" % (current_strength(f, scale, now, cfg),
                                          str(f.get("text") or u"")))
    if shown == 0:
        out.append(u"（现在没有一条够格进注入：都淡出了。提一次就回来，或 /世界记忆 钉 <关键词>）")
    out.append(u"用法：/世界记忆 清 ｜ /世界记忆 忘 <关键词> ｜ /世界记忆 钉|松 <关键词> ｜ "
               u"/世界记忆 开|关 ｜ /世界记忆 长 <80-1200>")
    return u"\n".join(out)


def _match(fact, keyword):
    k = str(keyword or u"").strip()
    if not k:
        return False
    blob = u"%s %s %s %s" % (fact.get("subject") or u"", fact.get("state") or u"",
                             fact.get("text") or u"", u" ".join(fact.get("sources") or []))
    return k in blob


def forget(world, keyword, cfg=None):
    """删掉匹配关键词的事实，返回删了几条。"""
    cfg = cfg or load_config()
    st = load_state(world, cfg)
    before = st.get("facts") or []
    kept = [f for f in before if not _match(f, keyword)]
    st["facts"] = kept
    if len(kept) != len(before):
        save_state(world, st, cfg)
    return len(before) - len(kept)


def clear(world, cfg=None):
    """清空**当前世界**的全部事实（文件保留，字段仍可读）。返回清掉几条。"""
    cfg = cfg or load_config()
    st = load_state(world, cfg)
    n = len(st.get("facts") or [])
    st["facts"] = []
    save_state(world, st, cfg)
    return n


def pin(world, keyword, pinned=True, cfg=None):
    """钉住/松开匹配的事实（钉住的永远不淡出）。返回改了几条。"""
    cfg = cfg or load_config()
    st = load_state(world, cfg)
    n = 0
    for f in (st.get("facts") or []):
        if _match(f, keyword):
            f["pinned"] = bool(pinned)
            n += 1
    if n:
        save_state(world, st, cfg)
    return n


def stats(world=None, cfg=None, now=None, scale=None):
    """一行摘要（给别的面板/测试用）：(总数, 还在注入里的条数)"""
    cfg = cfg or load_config()
    st = load_state(world, cfg)
    return len(st.get("facts") or []), len(rank_facts(st, scale=scale, now=now, cfg=cfg))
