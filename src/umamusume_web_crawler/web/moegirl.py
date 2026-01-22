from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict
from urllib.parse import parse_qs, quote, unquote, urlparse, urlencode
from urllib.request import ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup

from umamusume_web_crawler.config import config


DEFAULT_API_ENDPOINT = "https://zh.moegirl.org.cn/api.php"
_TRANSCLUSION_PATTERN = re.compile(r"\{\{:\s*([^}|]+)")


def _normalize_title(value: str) -> str:
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.path.endswith("/index.php"):
            params = parse_qs(parsed.query)
            title = params.get("title", [""])[0]
        else:
            title = unquote(parsed.path.strip("/").split("/")[-1])
        return title.strip()
    return value.strip()


def _build_api_url(endpoint: str, params: Dict[str, str]) -> str:
    query = urlencode(params, quote_via=quote)
    return f"{endpoint}?{query}"


def _build_opener(use_proxy: bool | None) -> object:
    if use_proxy is False:
        return build_opener()
    proxy_url = config.proxy_url()
    if not proxy_url:
        return build_opener()
    proxy_handler = ProxyHandler({"http": proxy_url, "https": proxy_url})
    return build_opener(proxy_handler)


def _request_json(
    url: str, *, timeout_s: float, use_proxy: bool | None = None
) -> Dict[str, Any]:
    headers = {
        "User-Agent": config.user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = Request(url, headers=headers)
    opener = _build_opener(use_proxy)
    with opener.open(req, timeout=timeout_s) as resp:
        payload = resp.read()
    return json.loads(payload.decode("utf-8"))


def _extract_page(payload: Dict[str, Any]) -> Dict[str, Any]:
    query = payload.get("query", {})
    pages = query.get("pages")
    if isinstance(pages, list):
        return pages[0] if pages else {}
    if isinstance(pages, dict):
        return next(iter(pages.values()), {})
    return {}


def _extract_wikitext_from_page(page: Dict[str, Any]) -> str:
    revisions = page.get("revisions") or []
    if not revisions:
        return ""
    revision = revisions[0]
    if isinstance(revision, dict):
        if "slots" in revision:
            slots = revision.get("slots") or {}
            main = slots.get("main") or {}
            return str(main.get("*") or main.get("content") or "")
        return str(revision.get("*") or revision.get("content") or "")
    return ""


def _extract_parse_html(payload: Dict[str, Any]) -> str:
    parse = payload.get("parse") or {}
    text = parse.get("text")
    if isinstance(text, dict):
        return str(text.get("*") or "")
    if isinstance(text, str):
        return text
    return ""


def _extract_transclusions(wikitext: str) -> list[str]:
    titles: list[str] = []
    for match in _TRANSCLUSION_PATTERN.finditer(wikitext or ""):
        title = match.group(1).strip()
        if title and title not in titles:
            titles.append(title)
    return titles


async def fetch_moegirl_wikitext(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing moegirl page title.")
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
        "titles": title,
    }
    url = _build_api_url(endpoint, params)
    payload = await asyncio.to_thread(
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy
    )
    page = _extract_page(payload)
    content = _extract_wikitext_from_page(page)
    if not content:
        raise RuntimeError("Moegirl API returned empty wikitext.")
    return content


async def fetch_moegirl_wikitext_expanded(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    max_depth: int = 1,
    max_pages: int = 5,
    use_proxy: bool | None = None,
) -> str:
    visited: set[str] = set()

    async def _fetch(title: str, depth: int) -> str:
        if not title or title in visited or len(visited) >= max_pages:
            return ""
        visited.add(title)
        text = await fetch_moegirl_wikitext(
            title, endpoint=endpoint, timeout_s=timeout_s, use_proxy=use_proxy
        )
        if depth <= 0:
            return text
        transclusions = _extract_transclusions(text)
        if not transclusions:
            return text
        appended: list[str] = []
        for child_title in transclusions:
            if len(visited) >= max_pages:
                break
            child_text = await _fetch(child_title, depth - 1)
            if child_text:
                appended.append(f"\n\n== {child_title} ==\n{child_text}")
        if appended:
            return text + "".join(appended)
        return text

    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing moegirl page title.")
    return await _fetch(title, max_depth)


async def search_moegirl_titles(
    keyword: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    limit: int = 5,
    timeout_s: float = 10.0,
    use_proxy: bool | None = None,
) -> list[str]:
    if not keyword:
        raise ValueError("Missing moegirl search keyword.")
    params = {
        "action": "opensearch",
        "search": keyword,
        "limit": str(limit),
        "format": "json",
    }
    url = _build_api_url(endpoint, params)
    payload = await asyncio.to_thread(
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy
    )
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        return [str(title) for title in payload[1] if title]
    return []


async def fetch_moegirl_html(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing moegirl page title.")
    params = {
        "action": "parse",
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "page": title,
    }
    url = _build_api_url(endpoint, params)
    payload = await asyncio.to_thread(
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy
    )
    html = _extract_parse_html(payload)
    if not html:
        raise RuntimeError("Moegirl API returned empty HTML.")
    return html


async def fetch_moegirl_text(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    html = await fetch_moegirl_html(
        title_or_url, endpoint=endpoint, timeout_s=timeout_s, use_proxy=use_proxy
    )
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one(".mw-parser-output") or soup.body
    if not main:
        return ""
    return main.get_text("\n", strip=True)
