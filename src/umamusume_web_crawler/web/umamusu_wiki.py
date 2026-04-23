from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup

from umamusume_web_crawler.config import config


DEFAULT_API_ENDPOINT = "https://umamusu.wiki/w/api.php"
DEFAULT_BASE_URL = "https://umamusu.wiki/"
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


def _normalize_category_title(value: str) -> str:
    title = _normalize_title(value)
    if not title:
        return ""
    if title.startswith("Category:"):
        return title
    return f"Category:{title}"


def _normalize_file_title(value: str) -> str:
    title = _normalize_title(value)
    if not title:
        return ""
    if title.startswith("File:"):
        return title
    return f"File:{title}"


def _build_api_url(endpoint: str, params: Dict[str, str]) -> str:
    query = urlencode(params, quote_via=quote)
    return f"{endpoint}?{query}"


def _build_opener(use_proxy: bool | None) -> object:
    if use_proxy is False:
        return build_opener(ProxyHandler({}))
    proxy_url = config.proxy_url()
    if not proxy_url:
        return build_opener()
    proxy_handler = ProxyHandler({"http": proxy_url, "https": proxy_url})
    return build_opener(proxy_handler)


def _request_json(
    url: str, *, timeout_s: float, use_proxy: bool | None = None
) -> Dict[str, Any] | list[Any]:
    headers = {
        "User-Agent": config.user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = Request(url, headers=headers)
    opener = _build_opener(use_proxy)
    with opener.open(req, timeout=timeout_s) as resp:
        payload = resp.read()
    return json.loads(payload.decode("utf-8"))


def _request_bytes(
    url: str, *, timeout_s: float, use_proxy: bool | None = None
) -> bytes:
    headers = {
        "User-Agent": config.user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = Request(url, headers=headers)
    opener = _build_opener(use_proxy)
    with opener.open(req, timeout=timeout_s) as resp:
        return resp.read()


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


def _extract_category_member_titles(payload: Dict[str, Any]) -> list[str]:
    query = payload.get("query", {})
    members = query.get("categorymembers")
    if not isinstance(members, list):
        return []
    return [str(item.get("title")) for item in members if item.get("title")]


def _extract_continue(payload: Dict[str, Any], key: str) -> str | None:
    token = payload.get("continue", {}).get(key)
    if not token:
        return None
    return str(token)


def _extract_imageinfo(page: Dict[str, Any]) -> Dict[str, Any]:
    imageinfo = page.get("imageinfo")
    if not isinstance(imageinfo, list) or not imageinfo:
        return {}
    item = imageinfo[0]
    if not isinstance(item, dict):
        return {}
    return item


def _filename_from_file_title(file_title: str) -> str:
    title = _normalize_file_title(file_title)
    if not title:
        return "download.bin"
    _, _, suffix = title.partition(":")
    filename = suffix or title
    return filename.replace("/", "_")


async def search_umamusu_titles(
    keyword: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    limit: int = 5,
    timeout_s: float = 10.0,
    use_proxy: bool | None = None,
) -> list[str]:
    if not keyword:
        raise ValueError("Missing umamusu.wiki search keyword.")
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


async def fetch_umamusu_wikitext(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing umamusu.wiki page title.")
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
    if not isinstance(payload, dict):
        raise RuntimeError("umamusu.wiki API returned unexpected payload.")
    page = _extract_page(payload)
    content = _extract_wikitext_from_page(page)
    if not content:
        raise RuntimeError("umamusu.wiki API returned empty wikitext.")
    return content


async def fetch_umamusu_wikitext_expanded(
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
        text = await fetch_umamusu_wikitext(
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
        raise ValueError("Missing umamusu.wiki page title.")
    return await _fetch(title, max_depth)


async def fetch_umamusu_html(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    title = _normalize_title(title_or_url)
    if not title:
        raise ValueError("Missing umamusu.wiki page title.")
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
    if not isinstance(payload, dict):
        raise RuntimeError("umamusu.wiki API returned unexpected payload.")
    html = _extract_parse_html(payload)
    if not html:
        raise RuntimeError("umamusu.wiki API returned empty HTML.")
    return html


async def fetch_umamusu_text(
    title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> str:
    html = await fetch_umamusu_html(
        title_or_url, endpoint=endpoint, timeout_s=timeout_s, use_proxy=use_proxy
    )
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one(".mw-parser-output") or soup.body
    if not main:
        return ""
    return main.get_text("\n", strip=True)


async def list_umamusu_category_files(
    category_title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    page_limit: int = 500,
    max_files: int | None = None,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
    delay_s: float = 0.0,
) -> list[str]:
    category_title = _normalize_category_title(category_title_or_url)
    if not category_title:
        raise ValueError("Missing umamusu.wiki category title.")

    if page_limit <= 0:
        raise ValueError("page_limit must be greater than 0.")

    titles: list[str] = []
    seen: set[str] = set()
    cmcontinue: str | None = None

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_title,
            "cmtype": "file",
            "cmlimit": str(min(page_limit, 500)),
            "format": "json",
            "formatversion": "2",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        url = _build_api_url(endpoint, params)
        payload = await asyncio.to_thread(
            _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy
        )
        if not isinstance(payload, dict):
            raise RuntimeError("umamusu.wiki category API returned unexpected payload.")

        for title in _extract_category_member_titles(payload):
            if title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if max_files is not None and len(titles) >= max_files:
                return titles

        next_token = _extract_continue(payload, "cmcontinue")
        if not next_token:
            return titles

        cmcontinue = next_token
        if delay_s > 0:
            await asyncio.sleep(delay_s)


async def fetch_umamusu_image_info(
    file_title_or_url: str,
    *,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> dict[str, Any]:
    file_title = _normalize_file_title(file_title_or_url)
    if not file_title:
        raise ValueError("Missing umamusu.wiki file title.")
    params = {
        "action": "query",
        "prop": "imageinfo",
        "titles": file_title,
        "iiprop": "url|mime|size",
        "format": "json",
        "formatversion": "2",
    }
    url = _build_api_url(endpoint, params)
    payload = await asyncio.to_thread(
        _request_json, url, timeout_s=timeout_s, use_proxy=use_proxy
    )
    if not isinstance(payload, dict):
        raise RuntimeError("umamusu.wiki image API returned unexpected payload.")
    page = _extract_page(payload)
    imageinfo = _extract_imageinfo(page)
    raw_url = imageinfo.get("url")
    if not raw_url:
        raise RuntimeError(f"umamusu.wiki API returned no image URL for {file_title}.")
    return {
        "title": str(page.get("title") or file_title),
        "url": str(raw_url),
        "mime": str(imageinfo.get("mime") or ""),
        "size": int(imageinfo.get("size") or 0),
    }


async def download_umamusu_file(
    file_title_or_url: str,
    *,
    output_dir: str | Path,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
) -> dict[str, Any]:
    info = await fetch_umamusu_image_info(
        file_title_or_url, endpoint=endpoint, timeout_s=timeout_s, use_proxy=use_proxy
    )
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = _filename_from_file_title(str(info["title"]))
    output_path = directory / filename
    payload = await asyncio.to_thread(
        _request_bytes, str(info["url"]), timeout_s=timeout_s, use_proxy=use_proxy
    )
    await asyncio.to_thread(output_path.write_bytes, payload)
    return {
        **info,
        "filename": filename,
        "path": str(output_path),
        "bytes": len(payload),
    }


async def download_umamusu_category_images(
    category_title_or_url: str,
    *,
    output_dir: str | Path,
    endpoint: str = DEFAULT_API_ENDPOINT,
    page_limit: int = 500,
    max_files: int | None = None,
    timeout_s: float = 30.0,
    use_proxy: bool | None = None,
    delay_s: float = 0.5,
) -> list[dict[str, Any]]:
    titles = await list_umamusu_category_files(
        category_title_or_url,
        endpoint=endpoint,
        page_limit=page_limit,
        max_files=max_files,
        timeout_s=timeout_s,
        use_proxy=use_proxy,
        delay_s=delay_s,
    )
    downloads: list[dict[str, Any]] = []
    for index, title in enumerate(titles):
        downloads.append(
            await download_umamusu_file(
                title,
                output_dir=output_dir,
                endpoint=endpoint,
                timeout_s=timeout_s,
                use_proxy=use_proxy,
            )
        )
        if delay_s > 0 and index + 1 < len(titles):
            await asyncio.sleep(delay_s)
    return downloads
