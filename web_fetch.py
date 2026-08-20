# -*- coding: utf-8 -*-
# ============================================================
#   web_fetch.py - 通用网页抓取（仅依赖 requests，无第三方解析库）
#
#   供 财报助手 / 联网搜索 等插件复用：
#     fetch_html(url)              抓 HTML 源码
#     fetch_text(url)              抓网页正文纯文本
#     clean_text(html)             HTML → 正文文本（去脚本/导航噪音）
#     page_title(html)             提取 <title>
#     find_article_links(...)      列表页 → 文章链接（标题+URL）
#     find_pagination(...)         列表页 → 下一页链接
#     same_domain(u1, u2)          是否同域名
#     is_policy_url(url)           是否像政策文件链接
# ============================================================

import html as _html
import html.parser
import re
from urllib.parse import urljoin, urlparse

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

NL = chr(10)

_NAV_NOISE = ("首页", "无障碍", "网站地图", "English", "联系我们",
              "版权", "ICP备", "政府网站", "客户端", "微博", "微信", "手机版",
              "政务新媒体", "网站标识码", "分享到", "打印本页", "关闭窗口")

POLICY_KW = ("通知", "办法", "规定", "意见", "公告", "细则", "条例", "政策",
             "批复", "答复", "解读", "zhengce", "zcfg", "content", "xxgk", "gongbao")

_ARTICLE_HREF_KW = ("content", "article", "zhengce", "htm", "shtml", "xxgk",
                    "zwgk", "zcfg", "t202", "detail", "news")

_PAGE_ANCHOR_KW = ("下一页", "下页", "next", ">", "»")


class _TextExtractor(html.parser.HTMLParser):
    """极简正文提取：跳过 script/style/noscript，收集可见文本"""
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        t = (data or "").strip()
        if t:
            self.parts.append(t)


def clean_text(html_text, max_chars=8000):
    """HTML → 正文：跳过脚本、去重、短行导航噪音过滤、压缩空白、截断"""
    p = _TextExtractor()
    try:
        p.feed(html_text or "")
    except Exception:
        pass
    lines, seen = [], set()
    total = 0
    for raw in p.parts:
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line in seen:
            continue
        if len(line) < 40 and any(k in line for k in _NAV_NOISE):
            continue
        seen.add(line)
        lines.append(line)
        total += len(line)
        if total >= max_chars:
            break
    return NL.join(lines)


def page_title(html_text):
    """提取 <title>（失败返回空串）"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text or "", re.S | re.I)
    if not m:
        return ""
    return _html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()


def fetch_html(url, timeout=10):
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def fetch_text(url, timeout=10, max_chars=8000):
    return clean_text(fetch_html(url, timeout), max_chars=max_chars)


def _abs(href, base_url):
    href = (href or "").strip()
    if not href or href.startswith(("javascript:", "#", "mailto:")):
        return ""
    return href if href.startswith("http") else urljoin(base_url, href)


def find_article_links(html_text, base_url, limit=10, href_keywords=None):
    """从列表页挑文章链接：标题 8~90 字 + href 含文章关键词"""
    kws = href_keywords or _ARTICLE_HREF_KW
    pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
    results, seen = [], set()
    for href, raw_title in pattern.findall(html_text or ""):
        title = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", raw_title))).strip()
        if not (8 <= len(title) <= 90):
            continue
        if not any(k in href for k in kws):
            continue
        abs_url = _abs(href, base_url)
        if not abs_url or abs_url in seen:
            continue
        seen.add(abs_url)
        results.append((title, abs_url))
        if len(results) >= limit:
            break
    return results


def find_pagination(html_text, base_url, current_url="", limit=5):
    """列表页 → 下一页链接（锚文本含 下一页/next，或 href 形如 index_N）"""
    pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
    out, seen = [], set()
    cur = (current_url or "").strip()
    for href, raw_anchor in pattern.findall(html_text or ""):
        anchor = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", raw_anchor))).strip()
        abs_url = _abs(href, base_url)
        if not abs_url or abs_url == cur or abs_url in seen:
            continue
        is_next = (anchor and any(k in anchor.lower() for k in _PAGE_ANCHOR_KW)) or re.search(r"index[_-]{BS}d+", href, re.I)
        if not is_next:
            continue
        seen.add(abs_url)
        out.append(abs_url)
        if len(out) >= limit:
            break
    return out


def same_domain(u1, u2):
    try:
        return urlparse(u1).netloc == urlparse(u2).netloc
    except Exception:
        return False


def is_policy_url(url):
    return any(k in (url or "") for k in POLICY_KW)
