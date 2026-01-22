from __future__ import annotations

from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from httplib2 import Http, ProxyInfo

from umamusume_web_crawler.config import config


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
