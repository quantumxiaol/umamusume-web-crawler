from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from httplib2 import Http, ProxyInfo

from umamusume_web_crawler.config import config

_DEFAULT_SEARCH_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def _build_http() -> Optional[Http]:
    proxy_url = config.http_proxy or config.https_proxy
    if not proxy_url:
        return None
    if not proxy_url.startswith("http://"):
        raise ValueError("Proxy must start with http:// for httplib2 ProxyInfo")
    _, rest = proxy_url.split("http://", 1)
    if ":" not in rest:
        raise ValueError("Proxy must be in the form http://host:port")
    host, port = rest.rsplit(":", 1)
    proxy_info = ProxyInfo(
        proxy_type=3,
        proxy_host=host,
        proxy_port=int(port),
    )
    return Http(proxy_info=proxy_info)


def _extract_formatted_urls(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"url": item["formattedUrl"], "priority": idx + 1}
        for idx, item in enumerate(results)
        if "formattedUrl" in item
    ]


def google_search(search_term: str, **kwargs: Any) -> List[Dict[str, Any]]:
    config.validate_web_tools()
    http = _build_http()
    service = build("customsearch", "v1", developerKey=config.google_api_key, http=http)
    res = service.cse().list(q=search_term, cx=config.google_cse_id, **kwargs).execute()
    return _extract_formatted_urls(res.get("items", []))


def google_search_urls(search_term: str, **kwargs: Any) -> List[Dict[str, Any]]:
    urls = google_search(search_term, **kwargs)
    if not urls:
        raise ValueError("No results found")
    return urls


def _google_user_agent() -> str:
    user_agent = config.user_agent or _DEFAULT_SEARCH_UA
    if user_agent == "UmamusumeWebCrawler/1.0":
        return _DEFAULT_SEARCH_UA
    return user_agent


def _build_proxy_handler(use_proxy: bool | None) -> ProxyHandler | None:
    if use_proxy is False:
        return None
    proxy_url = config.proxy_url()
    if not proxy_url:
        return None
    return ProxyHandler({"http": proxy_url, "https": proxy_url})


def _fetch_google_search_html(
    query: str,
    *,
    num: int,
    timeout_s: float,
    use_proxy: bool | None,
) -> str:
    params = {"q": query, "num": str(num), "hl": "zh-CN"}
    url = f"https://www.google.com/search?{urlencode(params)}"
    headers = {
        "User-Agent": _google_user_agent(),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = Request(url, headers=headers)
    proxy_handler = _build_proxy_handler(use_proxy)
    opener = build_opener(proxy_handler) if proxy_handler else build_opener()
    with opener.open(req, timeout=timeout_s) as resp:
        payload = resp.read()
    return payload.decode("utf-8", errors="replace")


def _normalize_google_href(href: str) -> str | None:
    if href.startswith("/url?"):
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        candidate = params.get("q", params.get("url", [""]))[0]
        if candidate:
            return unquote(candidate)
        return None
    if href.startswith("http://") or href.startswith("https://"):
        parsed = urlparse(href)
        if "google." in parsed.netloc or parsed.netloc.endswith("googleusercontent.com"):
            return None
        return href
    return None


def google_search_page_urls(
    query: str,
    *,
    num: int = 5,
    timeout_s: float = 10.0,
    use_proxy: bool | None = None,
) -> List[Dict[str, Any]]:
    if not query:
        raise ValueError("Missing google search query.")
    html = _fetch_google_search_html(
        query, num=num, timeout_s=timeout_s, use_proxy=use_proxy
    )
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    results: List[Dict[str, Any]] = []
    for link in soup.select("a[href]"):
        href = link.get("href")
        if not href:
            continue
        url = _normalize_google_href(href)
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({"url": url, "priority": len(results) + 1})
        if len(results) >= num:
            break
    if not results:
        raise ValueError("No results found")
    return results
