# -*- coding: utf-8 -*-
# ============================================================
#   financial_plugin.py - 财报助手 v2.0
#
#   命令：
#     /财报 爬取              全源深爬：10 官方政策源 + 分页 + 正文 + 关联文件递归
#     /财报 标题              全源标题速览（不抓正文，最快）
#     /财报 爬取 <网址>       抓取指定文件全文
#     /爬取 <网址>            通用网页爬取：任意网站正文（新闻/文章/公告）
#     /财报 入库              全源深爬存入本地政策库（增量去重）
#     /财报 更新              同上（别名）
#     /财报 检索 <关键词>     从政策库检索相关条目
#     /财报 定时 [开|关] [小时]  政策库自动刷新（默认 6 小时）
#     /财报 帮助              使用说明
#
#   政策库 policy_db.json 保存在 exe/工程根目录（便携设计）。
#   「财报模式」预设下发送消息，会自动引用与话题最相关的库内条目。
# ============================================================

import json
import os
import re
import sys
import threading
import time
from datetime import datetime

import app_paths
import stock_analysis
import web_fetch
from plugin_base import PluginBase

NL = chr(10)


class FinancialPlugin(PluginBase):
    name = "财报助手"
    version = "2.0"
    description = "政策深爬 + 通用网页爬取 + 本地政策库（增量更新、自动引用）"
    author = "seiki"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "📈 爬取政策", "text": "/财报 爬取"},
        {"type": "insert", "label": "🌐 爬网页", "text": "/爬取 "},
        {"type": "insert", "label": "📚 检索政策库", "text": "/财报 检索 "},
        {"type": "insert", "label": "📊 个股分析", "text": "/财报 股票 "},
        {"type": "insert", "label": "🔗 联动分析", "text": "/财报 联动 "},
        {"type": "insert", "label": "📈 涨跌幅榜", "text": "/股票列表 "},
        {"type": "insert", "label": "🔍 全市场筛选", "text": "/全市场 "},
    ]

    settings_schema = [
        {"key": "max_articles", "label": "每个来源爬取的文章数上限", "type": "int",
         "default": 4, "min": 1, "max": 20},
        {"key": "max_pages", "label": "每个来源翻页数", "type": "int",
         "default": 2, "min": 1, "max": 5},
        {"key": "max_total", "label": "单次爬取总量上限（条）", "type": "int",
         "default": 30, "min": 5, "max": 100},
        {"key": "fetch_bodies", "label": "深度爬取：跟进抓取每篇正文", "type": "bool",
         "default": True},
        {"key": "body_chars", "label": "每篇正文截断字符数", "type": "int",
         "default": 2000, "min": 300, "max": 8000},
        {"key": "timeout", "label": "单页超时（秒）", "type": "int",
         "default": 8, "min": 3, "max": 30},
        {"key": "auto_refresh_hours", "label": "政策库自动刷新间隔（小时，0=关闭）", "type": "int",
         "default": 0, "min": 0, "max": 168},
    ]

    # 官方公开政策源（红头文件发布渠道，失效时可用 /财报 爬取 <网址> 手动补充）
    SOURCES = [
        ("中国政府网·政策", "https://www.gov.cn/zhengce/"),
        ("央行·沟通交流", "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html"),
        ("证监会·要闻", "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml"),
        ("发改委·新闻发布", "https://www.ndrc.gov.cn/xwdt/xwfb/"),
        ("财政部·政策发布", "http://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/"),
        ("工信部·政策文件", "https://www.miit.gov.cn/zwgk/zcwj/index.html"),
        ("商务部·政策发布", "http://www.mofcom.gov.cn/article/zwgk/zcfb/"),
        ("金融监管总局·政策", "https://www.nfra.gov.cn/cn/view/pages/ItemList.html?itemPId=915&itemId=916"),
        ("国家统计局·发布", "https://www.stats.gov.cn/sj/zxfb/"),
        ("国家能源局·政策", "http://www.nea.gov.cn/zcfg/"),
    ]

    def __init__(self, core):
        super().__init__(core)
        self._refresh_lock = threading.Lock()
        self._refreshing = False

    def on_load(self):
        print("[财报助手] v2.0：/财报 爬取|入库|检索|定时 · /爬取 <网址> · 政策库自动引用 · 金融史年表1617-2026")
        self._seed_history()
        hours = int(self.get_setting("auto_refresh_hours", 0))
        if hours > 0 and self._db_stale(hours):
            threading.Thread(target=self._refresh_db_quiet, daemon=True).start()

    def _seed_history(self):
        """把金融史年表（1617-2026）播种进政策库：仅补缺失，不覆盖用户爬取内容。
        年表来源：工程目录或打包目录(_MEIPASS)下的 financial_history.json"""
        try:
            candidates = []
            base = app_paths.get_base_dir()
            candidates.append(os.path.join(base, "financial_history.json"))
            bundled = getattr(sys, "_MEIPASS", None)
            if bundled:
                candidates.append(os.path.join(bundled, "financial_history.json"))
            path = next((p for p in candidates if os.path.isfile(p)), None)
            if not path:
                return
            with open(path, "r", encoding="utf-8") as f:
                hist = json.load(f)
            entries = hist.get("entries", []) if isinstance(hist, dict) else []
            if not entries:
                return
            db = self._load_db()
            missing = [e for e in entries if isinstance(e, dict)
                       and e.get("url") and e.get("url") not in db["articles"]]
            if not missing:
                return
            for e in missing:
                db["articles"][e["url"]] = {"title": e.get("title", ""),
                                            "url": e["url"],
                                            "source": e.get("source", "金融史年表·1617-2026"),
                                            "text": e.get("text", "")}
            db["history_count"] = len(entries)
            self._save_db(db)
            print(f"[财报助手] 金融史年表播种 {len(missing)} 条（1617-2026）")
        except Exception as e:
            print(f"[财报助手] 年表播种失败: {e}")

    # ---------- 基础抓取 ----------
    def _fetch(self, url, timeout=None):
        return web_fetch.fetch_html(url, timeout=timeout or int(self.get_setting("timeout", 8)))

    # ---------- 深爬核心 ----------
    def _crawl_all(self, fetch_bodies=True, max_pages=None, max_total=None):
        """全源深爬：列表页分页 + 正文跟进 + 文内政策链接递归(深度1) + URL 去重。
        返回文章 dict 列表：[{"title","url","source","text"}]"""
        per_source = int(self.get_setting("max_articles", 4))
        pages = int(max_pages if max_pages is not None else self.get_setting("max_pages", 2))
        total_cap = int(max_total if max_total is not None else self.get_setting("max_total", 30))
        body_chars = int(self.get_setting("body_chars", 2000))
        timeout = int(self.get_setting("timeout", 8))
        seen = set()
        articles = []

        for name, url in self.SOURCES:
            if len(articles) >= total_cap:
                break
            # 1) 收集列表页（BFS 翻页，同域）
            page_urls = [url]
            i = 0
            while i < len(page_urls) and len(page_urls) < pages:
                pu = page_urls[i]
                i += 1
                try:
                    html_text = self._fetch(pu, timeout)
                    for nxt in web_fetch.find_pagination(html_text, pu, pu, 2):
                        if nxt not in page_urls and web_fetch.same_domain(nxt, url):
                            page_urls.append(nxt)
                except Exception:
                    continue
            # 2) 收集文章链接（跨页去重）
            links = []
            for pu in page_urls:
                try:
                    html_text = self._fetch(pu, timeout)
                    for t, u in web_fetch.find_article_links(html_text, pu, per_source):
                        if u not in seen:
                            links.append((t, u, name))
                except Exception:
                    continue
                if len(links) >= per_source * pages:
                    break
            # 3) 抓正文（含文内政策链接递归）
            for title, aurl, src in links:
                if len(articles) >= total_cap:
                    break
                seen.add(aurl)
                text = ""
                if fetch_bodies:
                    try:
                        time.sleep(0.15)  # 礼貌限速
                        html_text = self._fetch(aurl, timeout)
                        text = web_fetch.clean_text(html_text, max_chars=body_chars)
                        # 文内政策链接递归（深度 1，同域，限量 2）
                        if text:
                            for t2, u2 in web_fetch.find_article_links(html_text, aurl, 2, web_fetch.POLICY_KW):
                                if u2 in seen or not web_fetch.same_domain(u2, aurl) or not web_fetch.is_policy_url(u2):
                                    continue
                                seen.add(u2)
                                try:
                                    time.sleep(0.15)
                                    b2 = web_fetch.fetch_text(u2, timeout=timeout, max_chars=body_chars)
                                    if b2:
                                        articles.append({"title": t2, "url": u2, "source": src + "·关联文件", "text": b2})
                                except Exception:
                                    pass
                    except Exception:
                        text = ""
                articles.append({"title": title, "url": aurl, "source": src, "text": text})
        return articles

    def _crawl_sources(self, fetch_bodies=None):
        """全源爬取并注入文档上下文（不落库）"""
        if fetch_bodies is None:
            fetch_bodies = bool(self.get_setting("fetch_bodies", True))
        try:
            articles = self._crawl_all(fetch_bodies=fetch_bodies)
        except Exception as e:
            return f"⚠️ 爬取失败：{e}"
        if not articles:
            return ("⚠️ 全部来源爬取失败（网络受限或站点改版）。" + NL +
                    "可用 /财报 爬取 <网址> 手动补充指定文件。")
        parts = []
        cur_src = None
        for a in articles:
            if a["source"] != cur_src:
                cur_src = a["source"]
                parts.append("【" + cur_src + "】")
            if fetch_bodies and a["text"]:
                parts.append("■ " + a["title"] + NL + "  （来源：" + a["url"] + "）" + NL + "  " + a["text"] + NL)
            else:
                parts.append("- " + a["title"] + "（" + a["url"] + "）")
        digest = NL.join(parts)
        core = self.core
        if hasattr(core, "set_document_context"):
            core.set_document_context(digest)
        preview = digest[:1200]
        if len(digest) > 1200:
            preview += NL + "…（完整内容已注入上下文）"
        bodies = sum(1 for a in articles if a["text"])
        srcs = len(set(a["source"].split("·")[0] for a in articles))
        mode_text = "深度抓取 " + str(bodies) + " 篇正文" if fetch_bodies else "标题速览"
        return ("📈 已爬取 " + str(srcs) + " 个政策源（" + mode_text + "，共 " +
                str(len(articles)) + " 条）：" + NL + preview + NL + NL +
                "✅ 已注入文档上下文，现在可以直接提问分析（如：结合最新政策分析新能源板块走势）")

    def _crawl_single(self, url):
        url = (url or "").strip()
        if not url:
            return ("🌐 用法：/爬取 <网址> 抓取任意网页正文" + NL +
                    "  例：/爬取 https://www.gov.cn/zhengce/content/xxxx.htm")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            html_text = self._fetch(url)
            title = web_fetch.page_title(html_text)
            text = web_fetch.clean_text(html_text, max_chars=8000)
            if not text.strip():
                return "⚠️ 未能从该页面提取到文本（可能是纯图片、JS 渲染或需登录的页面）"
            head = ("📄 " + title + NL + "来源：" + url + NL + NL) if title else ("📄 已抓取 " + url + NL + NL)
            core = self.core
            if hasattr(core, "set_document_context"):
                core.set_document_context(head + text)
            preview = text[:600]
            if len(text) > 600:
                preview += NL + "…（全文 " + str(len(text)) + " 字符已注入上下文）"
            return head + preview + NL + NL + "✅ 已注入上下文，可直接提问分析"
        except Exception as e:
            return f"⚠️ 抓取失败：{e}"

    # ---------- 政策库 ----------
    def _db_path(self):
        return os.path.join(app_paths.get_base_dir(), "policy_db.json")

    def _load_db(self):
        path = self._db_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("articles"), dict):
                    return data
            except Exception:
                pass
        return {"updated_at": "", "articles": {}}

    def _save_db(self, db):
        with open(self._db_path(), "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=1)

    def _build_db(self):
        """全源深爬入库（按 URL 增量去重/更新），返回 (新增, 更新, 总量)"""
        articles = self._crawl_all(fetch_bodies=True)
        db = self._load_db()
        added = updated = 0
        for a in articles:
            old = db["articles"].get(a["url"])
            if old:
                if a["text"] and a["text"] != old.get("text"):
                    old.update(a)
                    updated += 1
            else:
                db["articles"][a["url"]] = a
                added += 1
        db["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_db(db)
        self._seed_history()
        return added, updated, len(db["articles"])

    def _db_stale(self, hours):
        db = self._load_db()
        if not db.get("updated_at"):
            return True
        try:
            ts = datetime.strptime(db["updated_at"], "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - ts).total_seconds() > hours * 3600
        except Exception:
            return True

    def _refresh_db_quiet(self):
        with self._refresh_lock:
            if self._refreshing:
                return
            self._refreshing = True
        try:
            added, updated, total = self._build_db()
            print(f"[财报助手] 政策库后台刷新：+{added} 更新{updated} 共{total} 条")
        except Exception as e:
            print(f"[财报助手] 政策库后台刷新失败：{e}")
        finally:
            self._refreshing = False

    def _search_db(self, query, top=8):
        """关键词打分检索：标题命中 x3 + 正文命中"""
        db = self._load_db()
        arts = db.get("articles", {})
        if not arts:
            return []
        tokens = []
        for m in re.finditer(r"[0-9A-Za-z]+", query or ""):
            tokens.append(m.group(0).lower())
        cjk = re.sub(r"[^\u4e00-\u9fff]", "", query or "")
        for i in range(len(cjk) - 1):
            tokens.append(cjk[i:i + 2])
        tokens = [t for t in tokens if len(t) >= 2]
        scored = []
        for url, a in arts.items():
            title = a.get("title", "")
            text = a.get("text", "")
            score = 0
            for tk in tokens:
                score += title.count(tk) * 3 + text.count(tk)
            if query and query in title:
                score += 5
            if score > 0:
                scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored[:top]]

    def _auto_inject(self, user_input):
        """财报模式 + 政策库：自动引用与话题最相关的条目（追加到文档上下文）"""
        core = self.core
        if not core:
            return
        preset = getattr(core, "prompt_preset", None) or {}
        if preset.get("name") != "财报模式":
            return
        hits = self._search_db(user_input, top=3)
        if not hits:
            return
        parts = ["【政策库自动引用（与当前话题相关）】"]
        for a in hits:
            body = (a.get("text") or "")[:400]
            parts.append("■ " + a.get("title", "") + NL + "  来源：" + a.get("url", "") + NL + "  " + body)
        digest = NL.join(parts)
        try:
            core.set_document_context(digest, append=True)
        except TypeError:
            core.set_document_context(digest)

    # ---------- 插件钩子 ----------
    def on_message_send(self, user_input):
        hours = int(self.get_setting("auto_refresh_hours", 0))
        if hours > 0 and self._db_stale(hours):
            threading.Thread(target=self._refresh_db_quiet, daemon=True).start()
        self._auto_inject(user_input)
        return user_input

    # ---------- 命令 ----------
    def on_command(self, command, args):
        arg = (args or "").strip()
        low = arg.lower()
        if command in ("爬取", "crawl"):
            if low:
                return self._crawl_single(low), False
            return self._crawl_sources(), False
        if command in ("股票", "stock"):
            if not arg:
                return ("📊 用法：/股票 <代码>，如 /股票 600519 或 /股票 sh600519"), False
            return self._analyze_stock(arg), False
        if command in ("联动", "linked"):
            if not arg:
                return ("🔗 用法：/联动 <代码1[,代码2...]> [关键词]，如 /联动 600519,300750 消费 新能源"), False
            return self._analyze_linked(arg), False
        if command in ("股票列表", "涨跌幅榜", "ranklist"):
            return self._market_list(arg), False
        if command in ("全市场", "screen"):
            return self._screen_market(arg), False
        if command != "财报":
            return None
        if low in ("help", "帮助", "h", ""):
            return self._help(), False
        if low.startswith("爬取"):
            url = arg[2:].strip()
            if url:
                return self._crawl_single(url), False
            return self._crawl_sources(), False
        if low in ("标题", "速览", "titles"):
            return self._crawl_sources(fetch_bodies=False), False
        if low in ("入库", "更新", "建库"):
            try:
                added, updated, total = self._build_db()
                return (f"📚 政策库已更新：新增 {added} 条，更新 {updated} 条，库内共 {total} 条" + NL +
                        "（policy_db.json 保存在程序旁，内置金融史年表1617-2026共49条；财报模式下自动引用相关条目，/财报 检索 <关键词> 可查询）"), False
            except Exception as e:
                return f"⚠️ 入库失败：{e}", False
        if low.startswith("检索") or low.startswith("查询"):
            q = arg[2:].strip()
            if not q:
                return "📚 用法：/财报 检索 <关键词>，如 /财报 检索 新能源", False
            hits = self._search_db(q, top=8)
            if not hits:
                return "📚 政策库中没有匹配的条目（可先 /财报 入库 建立政策库）", False
            parts = ["📚 政策库检索结果（" + q + "）"]
            for i, a in enumerate(hits, 1):
                parts.append(f"{i}. {a.get('title','')}（{a.get('source','')}）")
                parts.append("   " + a.get("url", ""))
            digest = NL.join(parts)
            core = self.core
            if hasattr(core, "set_document_context"):
                try:
                    core.set_document_context(digest, append=True)
                except TypeError:
                    core.set_document_context(digest)
            return (digest + NL + NL + "✅ 已注入上下文，可直接提问"), False
        if low.startswith("股票") or low.startswith("stock"):
            code = arg[2:].strip() if low.startswith("股票") else arg[5:].strip()
            if not code:
                return ("📊 用法：/财报 股票 <代码>，如 /财报 股票 600519"), False
            return self._analyze_stock(code), False
        if low.startswith("股票列表") or low.startswith("涨跌幅榜"):
            return self._market_list(arg[4:].strip() if low.startswith("股票列表") else arg[4:].strip()), False
        if low.startswith("全市场") or low.startswith("screen"):
            rest = arg[3:].strip() if low.startswith("全市场") else arg[6:].strip()
            return self._screen_market(rest), False
        if low.startswith("联动") or low.startswith("linked"):
            rest = arg[2:].strip() if low.startswith("联动") else arg[6:].strip()
            if not rest:
                return ("🔗 用法：/财报 联动 <代码1[,代码2...]> [关键词]"), False
            return self._analyze_linked(rest), False
        if low.startswith("定时"):
            rest = arg[2:].strip()
            if not rest:
                h = int(self.get_setting("auto_refresh_hours", 0))
                state = ("开启，每 " + str(h) + " 小时自动刷新") if h > 0 else "关闭"
                return ("⏰ 政策库定时刷新：" + state + NL +
                        "用法：/财报 定时 开 [小时] 或 /财报 定时 关"), False
            toks = rest.split()
            if toks[0] in ("开", "开启", "on"):
                hours = int(toks[1]) if len(toks) > 1 and toks[1].isdigit() else 6
                self.set_setting("auto_refresh_hours", hours)
                return f"⏰ 已开启政策库定时刷新（每 {hours} 小时，过期后下次发消息时后台自动刷新）", False
            if toks[0] in ("关", "关闭", "off"):
                self.set_setting("auto_refresh_hours", 0)
                return "⏰ 已关闭政策库定时刷新", False
            return "⏰ 用法：/财报 定时 开 [小时] 或 /财报 定时 关", False
        return self._help(), False

    def _analyze_linked(self, arg):
        """联动综合分析：多股技术面 + 政策库匹配 + 综合结论（结果注入上下文）"""
        nums = ["一", "二", "三", "四", "五", "六", "七"]
        parts = arg.split()
        codes = [c.strip() for c in parts[0].split(",") if c.strip()] if parts else []
        keywords = " ".join(parts[1:]) if len(parts) > 1 else ""
        if not codes:
            return "🔗 用法：/联动 <代码1[,代码2...]> [关键词]"
        codes = codes[:5]
        names = []
        sections = []
        sums = []
        for code in codes:
            try:
                q = stock_analysis.fetch_quote(code)
                names.append(str(q["name"]))
            except Exception:
                names.append(code)
            try:
                report = stock_analysis.analyze(code)
                sections.append(report)
                m = re.search(r"偏多 ([0-9]+)｜中性 ([0-9]+)｜偏空 ([0-9]+) → (.+)", report)
                sums.append((code, m.group(1), m.group(2), m.group(3), m.group(4)) if m else (code, "?", "?", "?", "?"))
            except Exception as e:
                sections.append("⚠️ " + code + " 分析失败：" + str(e))
                sums.append((code, "?", "?", "?", "?"))
        # 政策面：按 股票名 + 用户关键词 检索政策库
        policy_hits = []
        seen_urls = set()
        for name in names:
            for a in self._search_db((name + " " + keywords).strip(), top=4):
                url = a.get("url", "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                policy_hits.append(a)
        L = []
        L.append("🔗 联动综合分析报告（" + str(len(codes)) + " 只个股 × 政策库）")
        L.append("━━━━━━━━━━━━━━━━━━━━")
        idx = 0
        for code, report in zip(codes, sections):
            L.append("【" + nums[min(idx, 6)] + "、" + names[idx] + "（" + code + "）技术面】")
            L.append(report)
            L.append("")
            idx += 1
        L.append("【" + nums[min(idx, 6)] + "、政策面（匹配：" + ",".join(names) + ((" " + keywords) if keywords else "") + "）】")
        if not policy_hits:
            L.append("（政策库暂无匹配条目。先运行 /财报 入库 建立政策库（10 官方源自动深爬），或补充关键词重试）")
        else:
            for a in policy_hits[:8]:
                text = str(a.get("text", ""))
                L.append("■ " + str(a.get("title", "")) + "（" + str(a.get("source", "")) + "）")
                L.append("  " + text[:200] + ("…" if len(text) > 200 else ""))
        L.append("")
        L.append("【" + nums[min(idx + 1, 6)] + "、联动结论】")
        for code, b, n2, be, verdict in sums:
            L.append("  " + code + "：偏多 " + str(b) + "｜中性 " + str(n2) + "｜偏空 " + str(be) + " → " + str(verdict))
        total_bull = sum(int(s[1]) for s in sums if s[1].isdigit())
        total_bear = sum(int(s[3]) for s in sums if s[3].isdigit())
        if policy_hits:
            L.append("  政策面：" + str(len(policy_hits)) + " 条相关条目已纳入上下文，关注政策对相关行业的边际影响")
        else:
            L.append("  政策面：无匹配（可 /财报 入库 补库）")
        if total_bear > total_bull:
            L.append("  综合：技术面偏空信号占优，结合政策面谨慎对待")
        elif total_bull > total_bear:
            L.append("  综合：技术面偏多信号占优，可结合政策面寻找催化")
        else:
            L.append("  综合：技术面多空胶着，等待方向选择")
        L.append("  💡 报告已注入上下文，直接让 AI 深度解读（如：综合分析这两只票的联动机会）")
        L.append("⚠️ 仅供参考，不构成任何投资建议")
        digest = NL.join(L)
        core = self.core
        if hasattr(core, "set_document_context"):
            try:
                core.set_document_context(digest, append=True)
            except TypeError:
                core.set_document_context(digest)
        preview = digest[:1600]
        return preview + (NL + "…（完整报告已注入上下文）" if len(digest) > 1600 else "")

    def _market_list(self, arg):
        """/股票列表 [N] 涨幅榜；/股票列表 跌 [N] 跌幅榜"""
        losers = False
        text = (arg or "").strip()
        if text.startswith("跌") or text.startswith("down"):
            losers = True
            text = text[1:].strip()
        n = int(text) if text.isdigit() else 20
        n = max(1, min(n, 100))
        try:
            return stock_analysis.market_list_report(n, losers)
        except Exception as e:
            return "📈 行情列表获取失败：" + str(e)

    def _screen_market(self, arg):
        """/全市场 涨幅>5 换手>10 ..."""
        if not (arg or "").strip():
            return stock_analysis.screen_report("")
        try:
            report = stock_analysis.screen_report(arg)
        except Exception as e:
            return "🔍 全市场筛选失败：" + str(e)
        core = self.core
        if hasattr(core, "set_document_context"):
            try:
                core.set_document_context(report, append=True)
            except TypeError:
                core.set_document_context(report)
        return report

    def _analyze_stock(self, code):
        """个股炒股要素分析：实时行情 + 估值 + 全技术指标，结果注入上下文"""
        try:
            report = stock_analysis.analyze(code)
        except Exception as e:
            return f"📊 个股分析失败：{e}"
        core = self.core
        if hasattr(core, "set_document_context"):
            try:
                core.set_document_context(report, append=True)
            except TypeError:
                core.set_document_context(report)
        return report

    def _help(self):
        return NL.join([
            "📈 财报助手 v2.0 使用说明",
            "  /财报 爬取              全源深爬：10 官方政策源 + 翻页 + 正文 + 关联文件递归",
            "  /财报 标题              全源标题速览（不抓正文，最快）",
            "  /财报 爬取 <网址>       抓取指定文件全文",
            "  /爬取 <网址>            通用网页爬取：任意网站正文（新闻/文章/公告）",
            "  /财报 入库              全源深爬存入本地政策库（增量去重）",
            "  /财报 检索 <关键词>     从政策库检索相关条目",
            "  /财报 股票 <代码>       A股个股炒股要素分析（行情/估值/均线/MACD/KDJ/RSI/BOLL/ATR/支撑压力）",
            "  /股票 <代码>            个股分析快捷方式",
            "  /财报 联动 <代码,代码> [关键词]  联动综合分析：多股技术面 + 政策库匹配 + 综合结论",
            "  /联动 <代码,代码> [关键词]      联动分析快捷方式",
            "  /股票列表 [N] / 跌 [N]       A股涨跌幅榜（全市场 5900+ 只）",
            "  /全市场 涨幅>5 换手>10     全市场筛选（涨幅/换手/量比/市盈/市值/流入）",
            "  /财报 定时 开 [小时]    开启政策库定时刷新（默认 6 小时）",
            "  /财报 定时 关           关闭定时刷新",
            "  财报模式下发送消息会自动引用政策库中与话题最相关的条目。",
            "  爬取后直接提问，如：结合最新政策分析新能源板块走势",
        ])
