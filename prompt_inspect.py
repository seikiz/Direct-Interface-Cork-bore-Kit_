# -*- coding: utf-8 -*-
"""
prompt_inspect.py —— 把「应用真正发给模型的东西」原样打出来（不调用 API）

为什么需要它：
    角色漂成日语、回复重复、热注入失效 —— 这些问题的根因都在【发出去的载荷】里，
    但界面只显示模型的回复，看不到我们到底喂了什么。
    没有这个视图，调「热注入策略」只能靠猜。

它做的是：
    用真实的 ChatCore + 真实的角色卡/世界卡/设置组装一次请求，
    把 messages 拦下来打印，一个 token 都不花。

用法：
    python prompt_inspect.py                      # 用 config.json 里的最近角色
    python prompt_inspect.py 角色名                # 指定角色
    python prompt_inspect.py 角色名 --user "你好"   # 指定这句用户输入
    python prompt_inspect.py --raw                # 只打原始 JSON（方便 diff）
"""

import collections
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


# ------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------
#  拦住请求：拿到 messages 就中断，绝不发网络请求
# ------------------------------------------------------------
class _Capture(Exception):
    pass


class _Completions:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kw):
        self._sink.append(kw)
        raise _Capture()


class _Chat:
    def __init__(self, sink):
        self.completions = _Completions(sink)


class _Client:
    def __init__(self, sink):
        self.chat = _Chat(sink)


CAPTURE = []


def load_json(p, default=None):
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def find_role(name=None):
    """从 saves/ 里挑一张角色卡"""
    saves = os.path.join(ROOT, "saves")
    if not os.path.isdir(saves):
        return None, None
    cands = [f for f in sorted(os.listdir(saves))
             if f.endswith(".json") and not f.startswith(".")]
    if name:
        for f in cands:
            if os.path.splitext(f)[0] == name:
                return f, load_json(os.path.join(saves, f))
        for f in cands:
            if name in f:
                return f, load_json(os.path.join(saves, f))
        return None, None
    cfg = load_json(os.path.join(ROOT, "config.json"), {}) or {}
    last = cfg.get("last_role")
    if last:
        for f in cands:
            if os.path.splitext(f)[0] == last:
                return f, load_json(os.path.join(saves, f))
    for f in cands:
        d = load_json(os.path.join(saves, f))
        if isinstance(d, dict) and d.get("system_prompt"):
            return f, d
    return None, None


def build_core(role_data, cfg):
    from DICK_core import ChatCore
    c = ChatCore()
    c.client = _Client(CAPTURE)            # 假 client：能进流程，但不发请求
    c.set_model(cfg.get("model") or "deepseek-v4-flash")
    c.set_system_base(cfg.get("system_prompt_base") or "")
    c.humanize = bool(cfg.get("humanize", True))
    for attr in ("style_guard", "rolling_summary"):
        if attr in cfg:
            try:
                setattr(c, attr, bool(cfg[attr]))
            except Exception:
                pass
    if cfg.get("prompt_preset"):
        c.set_prompt_preset(cfg["prompt_preset"])
    c.set_sampling(cfg.get("temperature"), cfg.get("top_p"))
    if cfg.get("stop_sequences"):
        c.set_stop_sequences(cfg["stop_sequences"])
    if cfg.get("persona"):
        c.set_player_persona(cfg["persona"])

    # 只注入【选中的】世界 —— 应用里 _worlds_for_core() 就是这么做的。
    # 早先这里把所有世界都塞进去，结果把「不相关的世界书淹没人格」
    # 报成了应用的 bug，其实是我这个工具自己造的。工具必须忠实于应用行为。
    selected = cfg.get("selected_worlds") or []
    worlds = []
    wdir = os.path.join(ROOT, "worlds")
    if selected and os.path.isdir(wdir):
        for f in sorted(os.listdir(wdir)):
            if not f.endswith(".json"):
                continue
            w = load_json(os.path.join(wdir, f))
            if isinstance(w, dict):
                w.setdefault("name", os.path.splitext(f)[0])
                if w["name"] in selected:
                    worlds.append(w)
    if worlds:
        c.set_worlds(worlds)
        if cfg.get("current_world"):
            c.set_current_world(cfg["current_world"])

    # 去掉 history_tree：要看的是「全新一轮会发什么」
    rd = dict(role_data or {})
    rd.pop("history_tree", None)

    # 忠实复现 _load_roles：直接用应用自己的 role_prompt_from_card，
    # 不要在这里自己拼一遍渲染规则 —— 那样迟早和应用走偏。
    # （这个坑踩过两次了：世界卡一次、开场白一次。工具不忠实 = 假发现。）
    try:
        import html_app as _ha
        prompt, fields, _legacy = _ha.role_prompt_from_card(rd.get("name") or "", rd)
        rd["system_prompt"] = prompt
        rd["_fields"] = fields
    except Exception:
        pass

    c.set_active_roles([rd])

    # 开场白现在不是「贴一条消息」，而是当【场景】交给模型演出第一幕。
    # 所以这里不再插入任何消息，只把场景挂上去，让转储能看到开局的真实载荷。
    try:
        mes = ""
        for k in ("first_mes",):
            v = rd.get(k)
            if isinstance(v, str) and v.strip():
                mes = v.strip()
                break
        if not mes:
            f0 = rd.get("_fields") or {}
            mes = str(f0.get("first_mes") or "").strip()
        if mes:
            c.opening_cue = mes
            c._opening_text = mes
    except Exception:
        pass
    return c


def diagnose(msgs):
    """针对需求端反馈的问题，逐条体检载荷"""
    joined = "\n".join(m.get("content", "") for m in msgs)
    out = []

    def add(ok, label, detail=""):
        out.append((ok, label, detail))

    roles = [m.get("role") for m in msgs]
    add(True, "消息条数 %d（system %d / user %d）"
        % (len(msgs), roles.count("system"), roles.count("user")))

    sys_idx = [i for i, m in enumerate(msgs) if m.get("role") == "system"]
    last_sys = sys_idx[-1] if sys_idx else -1
    last_user = max([i for i, m in enumerate(msgs) if m.get("role") == "user"] or [-1])

    # ① 形态检查：与「创作前提是否存在」无关，任何载荷都该干净。
    #    （早先这几个检查写在 prem_idx>=0 分支里，结果没有创作前提的载荷
    #      就完全跳过了检查，等于体检漏项。）
    add(not re.search(r"\n\s{8,}\S", joined), "无整行缩进垃圾",
        "三引号字符串的缩进会原样进载荷" if re.search(r"\n\s{8,}\S", joined) else "")
    add("<think>" not in joined, "无假 <think> 标签",
        "真带推理的模型会把它当成自己没写过的思维链" if "<think>" in joined else "")
    add(not re.search(r'回答\s*["\']true["\']', joined), "无「回答 true」指令",
        "会让模型多吐一行无关内容" if re.search(r'回答\s*["\']true["\']', joined) else "")

    # ② 创作前提的位置（只有存在时才判位置）
    prem_idx = next((i for i, m in enumerate(msgs)
                     if "创作前提" in m.get("content", "")), -1)
    if prem_idx >= 0:
        _pos_ok = (prem_idx == last_sys and prem_idx < last_user)
        add(_pos_ok, "创作前提是最后一条 system（位置正确）",
            "第 %d 条 / 最后一条 system 第 %d 条 / 本轮用户第 %d 条"
            % (prem_idx, last_sys, last_user)
            + ("" if _pos_ok else " —— 放前面会被后面的设定稀释"))
    else:
        add(True, "本轮未启用创作前提（角色未 unlocked）")

    # ② 语言锚
    anchors = ["简体中文", "用中文", "中文回复", "输出语言"]
    hit = [a for a in anchors if a in joined]
    add(bool(hit), "载荷里有语言锚",
        ("命中：" + "、".join(hit)) if hit
        else "角色名/世界观是日文时必然漂语言")

    # ③ [ja] 日配：不禁用（那是功能），但要确认它把日文约束在标签内
    if "[ja]" in joined:
        confined = ("只允许出现在" in joined or "只能出现在" in joined
                    or "都算错误" in joined)
        add(confined, "[ja] 把日文约束在标签内",
            "" if confined else "模型可能把日文写到标签外 → 看起来像「回复了两遍」")
    else:
        add(True, "本轮不涉及 [ja] 日配")

    # ④ 中英混写的规则行
    mixed = [ln.strip() for ln in joined.split("\n")
             if ("忽略" in ln and ("all" in ln or "any" in ln))]
    add(not mixed, "规则行无中英混写",
        str(mixed[:3]) if mixed else "")

    # ⑤ 重复长句：重复的身份声明会让模型跟着复读
    lines = [ln.strip() for ln in joined.split("\n") if len(ln.strip()) > 8]
    dup = [ln for ln, n in collections.Counter(lines).items() if n > 1]
    add(not dup, "无完全重复的长句",
        ("重复了：%s" % dup[:3]) if dup else "")

    # ⑥ 体积
    add(len(joined) < 40000, "载荷体积在预算内",
        "%d 字符（约 %d token）" % (len(joined), len(joined) // 2)
        + ("" if len(joined) < 40000 else " —— 已接近上下文预算"))
    return out


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass

    argv = sys.argv[1:]
    raw = "--raw" in argv
    opening = "--opening" in argv
    argv = [a for a in argv if a not in ("--raw", "--opening")]
    user = "（测试输入）你好"
    if "--user" in argv:
        i = argv.index("--user")
        if i + 1 < len(argv):
            user = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
    name = argv[0] if argv else None

    cfg = load_json(os.path.join(ROOT, "config.json"), {}) or {}
    fn, role = find_role(name)
    if not role:
        print("找不到角色卡。先跑一次应用，或用 `python prompt_inspect.py 角色名`。")
        return 1

    print("=" * 66)
    print("请求载荷转储（不调用 API）")
    print("=" * 66)
    print("角色卡      : %s" % fn)
    print("角色        : %s" % role.get("name"))
    print("unlocked    : %s" % role.get("unlocked"))
    print("模型        : %s / %s" % (cfg.get("provider"), cfg.get("model")))
    print("humanize    : %s   style_guard: %s"
          % (cfg.get("humanize"), cfg.get("style_guard")))
    print("选中世界    : %s" % (cfg.get("selected_worlds") or "（无）"))
    print()

    core = build_core(role, cfg)
    # 开局是「没有用户消息」的一轮：模型直接对着场景演出第一幕。
    # 加用户消息会改变载荷形状，调开场时看的东西就不对了。
    if not opening:
        core.add_user_message(user)
    else:
        if not core.opening_cue:
            print("这张卡没有开场白（first_mes），开局载荷无从生成。")
            return 1
    CAPTURE.clear()
    try:
        core._fetch_response(core.opening_cue if opening else user,
                             role.get("name"), None, None,
                             core.tree.current_leaf_id)
    except _Capture:
        pass
    except Exception as e:
        print("组装失败：%r" % e)
        return 1

    if not CAPTURE:
        print("没有捕获到请求 —— 组装路径可能变了，检查 _mk_stream。")
        return 1

    msgs = CAPTURE[0].get("messages", [])
    if raw:
        print(json.dumps(msgs, ensure_ascii=False, indent=2))
        return 0

    for i, m in enumerate(msgs):
        body = m.get("content", "")
        print("-" * 66)
        print("[%d] role=%s   %d 字符" % (i, m.get("role"), len(body)))
        print("-" * 66)
        print(body)
        print()

    print("=" * 66)
    print("针对需求端反馈的体检")
    print("=" * 66)
    bad = 0
    for ok, label, detail in diagnose(msgs):
        print("  %s %s" % ("OK  " if ok else "!!  ", label))
        if detail:
            print("        %s" % detail)
        if not ok:
            bad += 1
    print()
    print("问题项 %d 个" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
