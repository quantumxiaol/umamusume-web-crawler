from __future__ import annotations

import asyncio
import re
from typing import Any, Dict
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup

from umamusume_web_crawler.web.http import request_json as _request_json
from umamusume_web_crawler.web.wiki_urls import normalize_title


DEFAULT_API_ENDPOINT = "https://mzh.moegirl.org.cn/api.php"
_TRANSCLUSION_PATTERN = re.compile(r"\{\{:\s*([^}|]+)")


def _normalize_title(value: str) -> str:
    return normalize_title(value, "moegirl")


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


def _extract_api_error(payload: Dict[str, Any]) -> tuple[str, str] | None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = str(error.get("code") or "")
    info = str(error.get("info") or error.get("*") or "")
    if not code and not info:
        return None
    return code, info


def _extract_plaintext_from_page(page: Dict[str, Any]) -> str:
    extract = page.get("extract")
    return str(extract or "").strip()


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
    extract_params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
        "formatversion": "2",
        "titles": title,
    }
    extract_url = _build_api_url(endpoint, extract_params)
    extract_payload = await asyncio.to_thread(
        _request_json, extract_url, timeout_s=timeout_s, use_proxy=use_proxy
    )
    extract_page = _extract_page(extract_payload)
    extract_text = _extract_plaintext_from_page(extract_page)
    if extract_text:
        return extract_text

    extract_error = _extract_api_error(extract_payload)
    if extract_error:
        code, info = extract_error
        raise RuntimeError(f"Moegirl API returned no content (extracts={code}:{info}).")
    raise RuntimeError("Moegirl API returned empty content.")


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
