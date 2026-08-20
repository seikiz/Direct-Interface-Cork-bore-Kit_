# ============================================================
#   web_search_plugin.py - 联网搜索 v2.0
#
#   免 Key 搜索：DuckDuckGo / Bing 抓取 → 标题+摘要+链接
#   → 注入文档上下文，AI 结合实时信息回答（财报模式必备）。
#
#   命令：
#     /搜索 <关键词>         搜索并把结果注入上下文（快）
#     /深搜 <关键词>         搜索 + 自动跟进抓取每条结果的网页正文（全）
# ============================================================

import html
import re
from urllib.parse import quote

import requests

import web_fetch
from plugin_base import PluginBase

NL = chr(10)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def parse_ddg(html_text, limit=5):
    """解析 DuckDuckGo html 版结果：标题 + 摘要 + 链接"""
    results = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S)
    for href, title, snippet in pattern.findall(html_text or ""):
        title = html.unescape(re.sub(r'<[^>]+>', '', title)).strip()
        snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet)).strip()
        if not title:
            continue
        url = href
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/l/?"):
            m = re.search(r'uddg=([^&]+)', url)
            if m:
                url = html.unescape(m.group(1))
        results.append({"title": title, "snippet": snippet, "url": url})
        if len(results) >= limit:
            break
    return results


def parse_bing(html_text, limit=5):
    """解析 Bing 结果：<li class="b_algo"><h2><a href>标题</a></h2><p>摘要</p>"""
    results = []
    pattern = re.compile(
        r'<li class="b_algo".*?<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>'
        r'.*?(?:<p[^>]*>(.*?)</p>)?', re.S)
    for href, title, snippet in pattern.findall(html_text or ""):
        title = html.unescape(re.sub(r'<[^>]+>', '', title)).strip()
        snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet or "")).strip()
        if not title:
            continue
        results.append({"title": title, "snippet": snippet, "url": href})
        if len(results) >= limit:
            break
    return results


class WebSearchPlugin(PluginBase):
    name = "联网搜索"
    version = "2.0"
    description = "免 Key 联网搜索（DuckDuckGo/Bing），支持深搜（自动跟进抓正文）"
    author = "seiki"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "🔍 搜索", "text": "/搜索 "},
        {"type": "insert", "label": "🔍 深搜", "text": "/深搜 "},
    ]

    settings_schema = [
        {"key": "engine", "label": "搜索引擎", "type": "choice",
         "options": ["自动（DuckDuckGo 优先）", "DuckDuckGo", "Bing"],
         "default": "自动（DuckDuckGo 优先）"},
        {"key": "count", "label": "结果条数", "type": "int",
         "default": 5, "min": 1, "max": 10},
        {"key": "deep_count", "label": "深搜跟进抓正文的条数", "type": "int",
         "default": 4, "min": 1, "max": 8},
        {"key": "timeout", "label": "超时（秒）", "type": "int",
         "default": 10, "min": 5, "max": 30},
    ]

    def on_load(self):
        print("[联网搜索] v2.0：/搜索 <关键词> 快速搜索；/深搜 <关键词> 搜索并跟进抓正文")

    def _search(self, query):
        count = int(self.get_setting("count", 5))
        timeout = int(self.get_setting("timeout", 10))
        engine = self.get_setting("engine", "自动（DuckDuckGo 优先）")
        attempts = []
        if engine in ("自动（DuckDuckGo 优先）", "DuckDuckGo"):
            attempts.append(("DuckDuckGo", "https://html.duckduckgo.com/html/?q=" + quote(query), parse_ddg))
        if engine in ("自动（DuckDuckGo 优先）", "Bing"):
            attempts.append(("Bing", "https://www.bing.com/search?q=" + quote(query), parse_bing))
        errors = []
        for name, url, parser in attempts:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=timeout)
                resp.encoding = resp.apparent_encoding or "utf-8"
                results = parser(resp.text, count)
                if results:
                    return name, results
                errors.append(f"{name}：无结果（可能被反爬拦截）")
            except Exception as e:
                errors.append(f"{name}：{e}")
        return None, "；".join(errors) if errors else "未知错误"

    def _deep_search(self, query):
        name, payload = self._search(query)
        if name is None:
            return f"⚠️ 搜索失败：{payload}", False
        results = payload
        depth = int(self.get_setting("deep_count", 4))
        timeout = int(self.get_setting("timeout", 10))
        parts = ["🔍 深搜结果（" + name + "，关键词：" + query + "）"]
        got = 0
        for i, r in enumerate(results[:depth], 1):
            parts.append(f"{i}. {r['title']}" + NL + "   " + r["snippet"] + NL + "   " + r["url"])
            try:
                body = web_fetch.fetch_text(r["url"], timeout=timeout, max_chars=2000)
                if body:
                    got += 1
                    snippet = body[:900]
                    parts.append("   【正文】" + snippet + ("…" if len(body) > 900 else ""))
                else:
                    parts.append("   【正文】提取为空")
            except Exception as e:
                parts.append("   【正文】抓取失败：" + str(e))
        digest = NL.join(parts)
        core = self.core
        if hasattr(core, "set_document_context"):
            core.set_document_context(digest)
        n = min(depth, len(results))
        return (digest + NL + NL + f"✅ 已跟进抓取 {got}/{n} 篇正文并注入上下文，现在可以直接提问（如：总结这些内容的要点）"), False

    def on_command(self, command, args):
        query = (args or "").strip()
        if command in ("深搜", "deepsearch", "deep"):
            if not query:
                return ("🔍 深搜用法：/深搜 <关键词>" + NL +
                        "  先搜索，再自动跟进抓取每条结果的网页正文，一并注入上下文。"), False
            return self._deep_search(query)
        if command not in ("搜索", "search", "web"):
            return None
        if not query:
            return ("🔍 联网搜索 用法：/搜索 <关键词>" + NL +
                    "  例：/搜索 宁德时代 最新新闻" + NL +
                    "  结果会注入文档上下文，随后直接提问即可。" + NL +
                    "  想要网页全文？用 /深搜 <关键词>。"), False
        name, payload = self._search(query)
        if name is None:
            return f"⚠️ 搜索失败：{payload}", False
        results = payload
        lines = [f"🔍 搜索结果（{name}，关键词：{query}）"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}" + NL + "   " + r["snippet"] + NL + "   " + r["url"])
        digest = NL.join(lines)
        core = self.core
        if hasattr(core, "set_document_context"):
            core.set_document_context(digest)
        return (digest + NL + NL + "✅ 已注入上下文，现在可以直接提问（如：根据搜索结果总结要点）"), False
