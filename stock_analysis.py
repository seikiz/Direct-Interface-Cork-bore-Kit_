# -*- coding: utf-8 -*-
# ============================================================
#   stock_analysis.py - A股炒股要素计算（免费数据源，免 Key）
#
#   数据源：
#     实时行情  https://qt.gtimg.cn/q=sh600519  （GBK，波浪号分隔）
#     前复权日K https://web.ifzq.gtimg.cn/appstock/app/fqkline/get
#
#   要素：实时行情 / 估值(PE/PB/市值) / 均线(5/10/20/60) / MACD / KDJ /
#         RSI(6/12/24) / BOLL / WR / ATR / 年化波动率 / 量能 / 支撑压力
# ============================================================

import json
import math
import re

import requests

NL = chr(10)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0"}


def _fnum(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def normalize_code(code):
    """600519 -> sh600519；0/3 开头 -> sz；4/8 -> bj；6 -> sh"""
    code = (code or "").strip().lower().replace(" ", "")
    if not code:
        return ""
    m = re.match(r"^(sh|sz|bj)([0-9]{6})$", code)
    if m:
        return m.group(1) + m.group(2)
    if re.match(r"^[0-9]{6}$", code):
        if code[0] == "6":
            prefix = "sh"
        elif code[0] in ("0", "3"):
            prefix = "sz"
        else:
            prefix = "bj"
        return prefix + code
    return code


def fetch_quote(code):
    code = normalize_code(code)
    resp = requests.get("https://qt.gtimg.cn/q=" + code, headers=HEADERS, timeout=10)
    text = resp.content.decode("gbk", errors="replace")
    fields = text.split("~")
    if len(fields) < 50:
        raise ValueError("未找到该股票（代码无效或停牌异常），请用 600519 或 sh600519 格式")

    def f(i):
        return fields[i].strip() if i < len(fields) else ""

    return {
        "name": f(1), "code": f(2), "price": _fnum(f(3)), "prev_close": _fnum(f(4)),
        "open": _fnum(f(5)), "volume_hand": _fnum(f(6)), "time": f(30),
        "change": _fnum(f(31)), "pct": _fnum(f(32)), "high": _fnum(f(33)), "low": _fnum(f(34)),
        "amount_wan": _fnum(f(37)), "turnover": _fnum(f(38)), "pe_ttm": _fnum(f(39)),
        "amplitude": _fnum(f(43)), "float_cap_yi": _fnum(f(44)), "total_cap_yi": _fnum(f(45)),
        "pb": _fnum(f(46)), "vol_ratio": _fnum(f(49)), "pe_dyn": _fnum(f(52)),
        "pe_static": _fnum(f(53)),
    }


def fetch_kline(code, count=160):
    code = normalize_code(code)
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" +
           code + ",day,,," + str(count) + ",qfq")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    data = json.loads(resp.text)
    node = (data.get("data") or {}).get(code) or {}
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for r in rows:
        if len(r) < 6:
            continue
        try:
            out.append({"date": r[0], "open": float(r[1]), "close": float(r[2]),
                        "high": float(r[3]), "low": float(r[4]), "volume": float(r[5])})
        except Exception:
            continue
    return out


# ---------- 指标 ----------
def sma(values, n):
    out = [None] * len(values)
    if len(values) >= n:
        s = sum(values[:n])
        out[n - 1] = s / n
        for i in range(n, len(values)):
            s += values[i] - values[i - n]
            out[i] = s / n
    return out


def ema(values, n):
    out = [None] * len(values)
    if not values:
        return out
    k = 2.0 / (n + 1)
    prev = values[0]
    out[0] = prev
    for i in range(1, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def macd(values):
    e12 = ema(values, 12)
    e26 = ema(values, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    hist = [(a - b) * 2 for a, b in zip(dif, dea)]
    return dif, dea, hist


def kdj(klines, n=9):
    ks, ds, js = [], [], []
    k_prev, d_prev = 50.0, 50.0
    for i, bar in enumerate(klines):
        lo = min(b["low"] for b in klines[max(0, i - n + 1):i + 1])
        hi = max(b["high"] for b in klines[max(0, i - n + 1):i + 1])
        rsv = 50.0 if hi == lo else (bar["close"] - lo) / (hi - lo) * 100
        k_prev = k_prev * 2 / 3 + rsv / 3
        d_prev = d_prev * 2 / 3 + k_prev / 3
        j = 3 * k_prev - 2 * d_prev
        ks.append(k_prev)
        ds.append(d_prev)
        js.append(j)
    return ks, ds, js


def rsi(values, n):
    out = [None] * len(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    if len(gains) < n:
        return out
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(values)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def boll(values, n=20):
    mid = sma(values, n)
    up, lo = [None] * len(values), [None] * len(values)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1:i + 1]
        m = mid[i]
        var = sum((v - m) ** 2 for v in window) / n
        sd = math.sqrt(var)
        up[i] = m + 2 * sd
        lo[i] = m - 2 * sd
    return up, mid, lo


def atr(klines, n=14):
    trs = [0.0]
    for i in range(1, len(klines)):
        h, l, pc = klines[i]["high"], klines[i]["low"], klines[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    out = [None] * len(trs)
    if len(trs) >= n:
        prev = sum(trs[1:n + 1]) / n
        out[n] = prev
        for i in range(n + 1, len(trs)):
            prev = (prev * (n - 1) + trs[i]) / n
            out[i] = prev
    return out


def wr(klines, n=14):
    out = [None] * len(klines)
    for i in range(n - 1, len(klines)):
        window = klines[i - n + 1:i + 1]
        hi = max(b["high"] for b in window)
        lo = min(b["low"] for b in window)
        out[i] = 100.0 if hi == lo else (hi - klines[i]["close"]) / (hi - lo) * 100
    return out


def volatility(values, n=20):
    if len(values) < n + 1:
        return 0.0
    rets = []
    for i in range(len(values) - n, len(values)):
        prev = values[i - 1]
        if prev > 0:
            rets.append(math.log(values[i] / prev))
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    return sd * math.sqrt(252) * 100


def _last(vals, back=0):
    for v in reversed(vals):
        if v is not None:
            if back == 0:
                return v
            back -= 1
    return None


def _cross_up(a, b, lookback=3):
    for i in range(1, min(lookback, len(a)) + 1):
        j = len(a) - i
        if a[j] is None or b[j] is None or a[j - 1] is None or b[j - 1] is None:
            continue
        if a[j - 1] <= b[j - 1] and a[j] > b[j]:
            return i
    return 0


def _cross_down(a, b, lookback=3):
    for i in range(1, min(lookback, len(a)) + 1):
        j = len(a) - i
        if a[j] is None or b[j] is None or a[j - 1] is None or b[j - 1] is None:
            continue
        if a[j - 1] >= b[j - 1] and a[j] < b[j]:
            return i
    return 0


def fmt(v, nd=2):
    if v is None:
        return "--"
    return ("{0:." + str(nd) + "f}").format(v)


_LAST_SOURCE = "eastmoney"


def _fetch_eastmoney_list(sort_field="f3", ascend=False, limit=6000):
    """东财全市场列表（约 5900 只，200/页分页 + 多节点轮换）"""
    rows = []
    seen = set()
    hosts = ["https://push2.eastmoney.com", "https://82.push2.eastmoney.com", "https://17.push2.eastmoney.com"]
    for pn in range(1, 40):
        pz = 200 if limit > 200 else limit
        url = (hosts[(pn - 1) % len(hosts)] + "/api/qt/clist/get?pn=" + str(pn) + "&pz=" + str(pz) +
               "&po=" + ("0" if ascend else "1") + "&np=1&fltt=2&invt=2&fid=" + sort_field +
               "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048" +
               "&fields=f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f62")
        diff = None
        for attempt in range(2):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=20)
                data = json.loads(resp.text)
                diff = (data.get("data") or {}).get("diff") or []
                break
            except Exception:
                if attempt == 1:
                    raise
        if not diff:
            break
        for r in diff:
            code = str(r.get("f12", ""))
            if code in seen:
                continue
            seen.add(code)
            rows.append({
                "code": code,
                "name": str(r.get("f14", "")),
                "price": _fnum(r.get("f2")),
                "pct": _fnum(r.get("f3")),
                "change": _fnum(r.get("f4")),
                "volume_hand": _fnum(r.get("f5")),
                "amount": _fnum(r.get("f6")),
                "amplitude": _fnum(r.get("f7")),
                "turnover": _fnum(r.get("f8")),
                "pe": _fnum(r.get("f9")),
                "vol_ratio": _fnum(r.get("f10")),
                "high": _fnum(r.get("f15")),
                "low": _fnum(r.get("f16")),
                "open": _fnum(r.get("f17")),
                "prev_close": _fnum(r.get("f18")),
                "total_cap_yi": _fnum(r.get("f20")) / 1e8,
                "float_cap_yi": _fnum(r.get("f21")) / 1e8,
                "pb": _fnum(r.get("f23")),
                "main_inflow_wan": _fnum(r.get("f62")) / 1e4,
            })
        if len(rows) >= limit or len(diff) < pz:
            break
    if not rows:
        raise ValueError("东财列表为空")
    return rows


def _quote_sina_keys(text):
    return re.sub(r'([{,][ ]*)([A-Za-z_][A-Za-z0-9_]*)([ ]*:)',
                  lambda m: m.group(1) + '"' + m.group(2) + '"' + m.group(3), text)


def _fetch_sina_list(sort_field="f3", ascend=False, limit=6000):
    """新浪行情中心备胎（hs_a 沪深北全 A，缺 量比/主力净流入 字段）"""
    sort_map = {"f3": "changepercent", "f6": "amount", "f8": "turnoverratio",
                "f10": "changepercent", "f62": "changepercent"}
    sort = sort_map.get(sort_field, "changepercent")
    headers = dict(HEADERS)
    headers["Referer"] = "https://finance.sina.com.cn/"
    rows = []
    seen = set()
    page = 1
    while len(rows) < limit and page <= 80:
        num = 80 if (limit - len(rows)) > 80 else (limit - len(rows))
        url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               "Market_Center.getHQNodeData?page=" + str(page) + "&num=" + str(num) +
               "&sort=" + sort + "&asc=" + ("1" if ascend else "0") +
               "&node=hs_a&symbol=&_s_r_a=page")
        data = None
        for attempt in range(2):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                data = json.loads(_quote_sina_keys(resp.text))
                break
            except Exception:
                if attempt == 1:
                    raise
        if not data:
            break
        for r in data:
            code = str(r.get("code", ""))
            if code in seen:
                continue
            seen.add(code)
            prev = _fnum(r.get("settlement"))
            rows.append({
                "code": code,
                "name": str(r.get("name", "")),
                "price": _fnum(r.get("trade")),
                "pct": _fnum(r.get("changepercent")),
                "change": _fnum(r.get("pricechange")),
                "volume_hand": _fnum(r.get("volume")) / 100,
                "amount": _fnum(r.get("amount")),
                "amplitude": ((_fnum(r.get("high")) - _fnum(r.get("low"))) / prev * 100) if prev else 0.0,
                "turnover": _fnum(r.get("turnoverratio")),
                "pe": _fnum(r.get("per")),
                "vol_ratio": 0.0,
                "high": _fnum(r.get("high")),
                "low": _fnum(r.get("low")),
                "open": _fnum(r.get("open")),
                "prev_close": prev,
                "total_cap_yi": _fnum(r.get("mktcap")) / 10000,
                "float_cap_yi": _fnum(r.get("nmc")) / 10000,
                "pb": _fnum(r.get("pb")),
                "main_inflow_wan": 0.0,
            })
        page += 1
        if len(data) < num:
            break
    if not rows:
        raise ValueError("新浪列表为空")
    return rows


def fetch_market_list(sort_field="f3", ascend=False, limit=6000):
    """全市场列表：东财优先（字段全），失败自动回退新浪。
    sort_field: f3涨幅 f6成交额 f8换手 f10量比 f62主力净流入"""
    global _LAST_SOURCE
    try:
        rows = _fetch_eastmoney_list(sort_field, ascend, limit)
        _LAST_SOURCE = "eastmoney"
        return rows
    except Exception:
        rows = _fetch_sina_list(sort_field, ascend, limit)
        _LAST_SOURCE = "sina"
        return rows


_SCREEN_KEYS = {"涨幅": "pct", "换手": "turnover", "量比": "vol_ratio",
                "市盈": "pe", "市值": "total_cap_yi", "流入": "main_inflow_wan"}


def parse_conditions(text):
    """"涨幅>5 换手>10 市值<200" -> [(涨幅, >, 5.0), ...]"""
    out = []
    for m in re.findall(r"([一-龥]+)(>=|<=|>|<)(-?[0-9.]+)", text or ""):
        key, op, val = m[0], m[1], float(m[2])
        if key in _SCREEN_KEYS:
            out.append((key, op, val))
    return out


def screen_market(conditions, limit=50):
    """全市场筛选：条件列表 [("涨幅", ">", 5.0), ...]，返回匹配前 limit 只"""
    rows = fetch_market_list("f3", False, 6000)
    pct_floor = None
    for key, op, val in conditions:
        if key == "涨幅" and op in (">", ">="):
            pct_floor = val
    out = []
    for r in rows:
        if pct_floor is not None and r["pct"] < pct_floor - 0.01:
            break  # 按涨幅降序，后面不可能再命中
        ok = True
        for key, op, val in conditions:
            v = r.get(_SCREEN_KEYS[key], 0.0)
            if op == ">":
                ok = v > val
            elif op == "<":
                ok = v < val
            elif op == ">=":
                ok = v >= val
            elif op == "<=":
                ok = v <= val
            else:
                ok = False
            if not ok:
                break
        if ok:
            out.append(r)
        if len(out) >= limit:
            break
    return out


def format_row(i, r):
    return (str(i) + ". " + r["name"] + "（" + r["code"] + "）现价 " + fmt(r["price"]) +
            "｜涨幅 " + fmt(r["pct"]) + "%｜换手 " + fmt(r["turnover"]) + "%｜量比 " +
            fmt(r["vol_ratio"]) + "｜市盈 " + fmt(r["pe"]) + "｜市值 " + fmt(r["total_cap_yi"]) +
            "亿｜主力净流入 " + fmt(r["main_inflow_wan"]) + "万")


def market_list_report(n=20, losers=False):
    rows = fetch_market_list("f3", losers, max(n, 1))
    head = "📉 A股跌幅榜 Top" if losers else "📈 A股涨幅榜 Top"
    lines = [head + str(len(rows)) + "（沪深北全市场，按涨跌幅排序）"]
    for i, r in enumerate(rows, 1):
        lines.append(format_row(i, r))
    return NL.join(lines)


def screen_report(text, limit=50):
    conditions = parse_conditions(text)
    if not conditions:
        return ("🔍 全市场筛选用法：/全市场 涨幅>5 换手>10 量比>2 市盈<50 市值<500 流入>1000" + NL +
                "  指标：涨幅% / 换手% / 量比 / 市盈 / 市值(亿) / 流入(主力净流入,万)")
    rows = screen_market(conditions, limit)
    cond_text = " ".join(k + op + ("%.2f" % v) for k, op, v in conditions)
    lines = ["🔍 全市场筛选（条件：" + cond_text + "）命中 " + str(len(rows)) + " 只（显示前 " + str(min(limit, len(rows))) + "）"]
    for i, r in enumerate(rows, 1):
        lines.append(format_row(i, r))
    if not rows:
        lines.append("（无匹配，放宽条件试试）")
    if _LAST_SOURCE == "sina" and any(k in ("量比", "流入") for k, _, _ in conditions):
        lines.append("⚠️ 当前使用新浪备用源（东财被限流），量比/主力净流入字段不可用")
    return NL.join(lines)


def analyze(code):
    quote = fetch_quote(code)
    bars = fetch_kline(code, 160)
    if len(bars) < 30:
        raise ValueError("K线数据不足（仅 " + str(len(bars)) + " 根），无法计算指标")
    closes = [b["close"] for b in bars]
    vols = [b["volume"] for b in bars]
    price = quote["price"]

    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    dif, dea, hist = macd(closes)
    ks, ds, js = kdj(bars)
    r6 = rsi(closes, 6)
    r12 = rsi(closes, 12)
    r24 = rsi(closes, 24)
    b_up, b_mid, b_lo = boll(closes)
    a = atr(bars)
    w = wr(bars)
    vola = volatility(closes)

    # 信号判定
    signs = []
    ma5v, ma10v, ma20v, ma60v = _last(ma5), _last(ma10), _last(ma20), _last(ma60)
    if ma5v is not None and ma20v is not None:
        if price > ma5v > ma10v > ma20v:
            signs.append(("均线", "多头排列", 1))
        elif price < ma5v < ma10v < ma20v:
            signs.append(("均线", "空头排列", -1))
        else:
            signs.append(("均线", "缠绕", 0))
    if _cross_up(dif, dea):
        signs.append(("MACD", "金叉", 1))
    elif _cross_down(dif, dea):
        signs.append(("MACD", "死叉", -1))
    else:
        signs.append(("MACD", "延续", 1 if _last(dif, 0) is not None and _last(dea, 0) is not None and _last(dif, 0) > _last(dea, 0) else -1))
    if _cross_up(ks, ds):
        signs.append(("KDJ", "金叉", 1))
    elif _cross_down(ks, ds):
        signs.append(("KDJ", "死叉", -1))
    else:
        jv = _last(js)
        signs.append(("KDJ", "超买" if jv is not None and jv > 100 else ("超卖" if jv is not None and jv < 0 else "中性"), -1 if jv is not None and jv > 100 else (1 if jv is not None and jv < 0 else 0)))
    r6v = _last(r6)
    signs.append(("RSI", "超买" if r6v is not None and r6v > 70 else ("超卖" if r6v is not None and r6v < 30 else "中性"),
                  -1 if r6v is not None and r6v > 70 else (1 if r6v is not None and r6v < 30 else 0)))
    bup, blo = _last(b_up), _last(b_lo)
    if bup is not None and blo is not None and bup > blo:
        pos = (price - blo) / (bup - blo) * 100
        signs.append(("BOLL", "强势区" if pos > 80 else ("弱势区" if pos < 20 else "中轨区"), 1 if pos > 80 else (-1 if pos < 20 else 0)))
    vola_avg5 = sum(vols[-5:]) / 5 if len(vols) >= 5 else 0
    vola_avg10 = sum(vols[-10:]) / 10 if len(vols) >= 10 else 0
    if vola_avg5 > vola_avg10 * 1.3:
        signs.append(("量能", "放量", 1))
    elif vola_avg5 < vola_avg10 * 0.7:
        signs.append(("量能", "缩量", -1))
    else:
        signs.append(("量能", "平量", 0))

    lo20 = min(b["low"] for b in bars[-20:])
    hi20 = max(b["high"] for b in bars[-20:])
    lo60 = min(b["low"] for b in bars[-60:]) if len(bars) >= 60 else lo20
    hi60 = max(b["high"] for b in bars[-60:]) if len(bars) >= 60 else hi20
    lo_all = min(b["low"] for b in bars)
    hi_all = max(b["high"] for b in bars)

    bullish = sum(1 for s in signs if s[2] > 0)
    bearish = sum(1 for s in signs if s[2] < 0)
    neutral = len(signs) - bullish - bearish
    if bearish >= 4 or (bearish > bullish and bearish >= 3):
        verdict = "偏空，注意风险"
    elif bullish >= 4 or (bullish > bearish and bullish >= 3):
        verdict = "偏多，可关注"
    else:
        verdict = "多空胶着，观望为主"

    L = []
    L.append("📊 " + quote["name"] + "（" + quote["code"] + "）炒股要素分析")
    L.append("⏱ 行情时间 " + quote["time"])
    L.append("【实时行情】现价 " + fmt(price) + "｜涨跌 " + fmt(quote["change"]) +
             "（" + fmt(quote["pct"]) + "%）｜今开 " + fmt(quote["open"]) +
             "｜最高 " + fmt(quote["high"]) + "｜最低 " + fmt(quote["low"]))
    L.append("  成交量 " + fmt(quote["volume_hand"] / 10000, 2) + " 万手｜成交额 " +
             fmt(quote["amount_wan"] / 10000, 2) + " 亿｜换手 " + fmt(quote["turnover"]) +
             "%｜量比 " + fmt(quote["vol_ratio"]) + "｜振幅 " + fmt(quote["amplitude"]) + "%")
    L.append("【估值】市盈(动) " + fmt(quote["pe_dyn"]) + "｜市盈(静) " + fmt(quote["pe_static"]) +
             "｜市净率 " + fmt(quote["pb"]) + "｜总市值 " + fmt(quote["total_cap_yi"]) +
             " 亿｜流通市值 " + fmt(quote["float_cap_yi"]) + " 亿")
    L.append("【均线】MA5 " + fmt(ma5v) + "｜MA10 " + fmt(ma10v) + "｜MA20 " + fmt(ma20v) +
             "｜MA60 " + fmt(ma60v) + "｜现价相对 MA20：" + fmt((price / ma20v - 1) * 100 if ma20v else 0) + "%")
    L.append("【MACD】DIF " + fmt(_last(dif)) + "｜DEA " + fmt(_last(dea)) + "｜柱 " + fmt(_last(hist)))
    L.append("【KDJ】K " + fmt(_last(ks)) + "｜D " + fmt(_last(ds)) + "｜J " + fmt(_last(js)))
    L.append("【RSI】RSI6 " + fmt(_last(r6)) + "｜RSI12 " + fmt(_last(r12)) + "｜RSI24 " + fmt(_last(r24)))
    L.append("【BOLL】上轨 " + fmt(bup) + "｜中轨 " + fmt(_last(b_mid)) + "｜下轨 " + fmt(blo))
    L.append("【WR/ATR/波动率】WR14 " + fmt(_last(w)) + "｜ATR14 " + fmt(_last(a)) +
             "（占现价 " + fmt(_last(a) / price * 100 if price else 0) + "%）｜20日年化波动率 " + fmt(vola) + "%")
    L.append("【支撑/压力】20日 支撑 " + fmt(lo20) + " / 压力 " + fmt(hi20) +
             "｜60日 支撑 " + fmt(lo60) + " / 压力 " + fmt(hi60) +
             "｜区间内 " + fmt(lo_all) + " - " + fmt(hi_all))
    L.append("【信号】" + "；".join(s[0] + "：" + s[1] + ("↑" if s[2] > 0 else ("↓" if s[2] < 0 else "")) for s in signs))
    L.append("【汇总】偏多 " + str(bullish) + "｜中性 " + str(neutral) + "｜偏空 " + str(bearish) +
             " → " + verdict)
    L.append("⚠️ 以上为技术指标计算，仅供参考，不构成任何投资建议")
    return NL.join(L)
