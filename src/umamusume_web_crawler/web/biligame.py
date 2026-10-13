from __future__ import annotations

import asyncio
import re
from typing import Any, Dict
from urllib.parse import quote, urlencode, urljoin

from bs4 import BeautifulSoup

from umamusume_web_crawler.web.http import request_json as _request_json
from umamusume_web_crawler.web.wiki_urls import normalize_title


DEFAULT_API_ENDPOINT = "https://wiki.biligame.com/umamusume/api.php"
_TRANSCLUSION_PATTERN = re.compile(r"\{\{:\s*([^}|]+)")


def _normalize_title(value: str) -> str:
    return normalize_title(value, "biligame")


def _build_api_url(endpoint: str, params: Dict[str, str]) -> str:
    query = urlencode(params, quote_via=quote)
    return f"{endpoint}?{query}"



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


async def fetch_biligame_wikitext(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing biligame page title.")
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
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy,
        referer=urljoin(endpoint, "./"),
    )
    page = _extract_page(payload)
    content = _extract_wikitext_from_page(page)
    if not content:
        raise RuntimeError("Biligame API returned empty wikitext.")
    return content


async def fetch_biligame_wikitext_expanded(
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
        text = await fetch_biligame_wikitext(
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
        raise ValueError("Missing biligame page title.")
    return await _fetch(title, max_depth)


async def search_biligame_titles(
    keyword: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    limit: int = 5,
    timeout_s: float = 10.0,
    use_proxy: bool | None = None,
) -> list[str]:
    if not keyword:
        raise ValueError("Missing biligame search keyword.")
    params = {
        "action": "opensearch",
        "search": keyword,
        "limit": str(limit),
        "format": "json",
    }
    url = _build_api_url(endpoint, params)
    payload = await asyncio.to_thread(
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy,
        referer=urljoin(endpoint, "./"),
    )
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        return [str(title) for title in payload[1] if title]
    return []


async def fetch_biligame_html(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
    cache_ttl_s: float = 3600,
    min_interval_s: float = 2,
) -> str:
    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing biligame page title.")
    params = {
        "action": "parse",
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "page": title,
    }
    url = _build_api_url(endpoint, params)
    payload = await asyncio.to_thread(
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy,
        cache_ttl_s=cache_ttl_s, min_interval_s=min_interval_s,
        referer=urljoin(endpoint, "./"),
    )
    html = _extract_parse_html(payload)
    if not html:
        raise RuntimeError("Biligame API returned empty HTML.")
    return html


async def fetch_biligame_text(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    html = await fetch_biligame_html(
        title_or_url, endpoint=endpoint, timeout_s=timeout_s, use_proxy=use_proxy
    )
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one(".mw-parser-output") or soup.body
    if not main:
        return ""
    return main.get_text("\n", strip=True)
