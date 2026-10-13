"""Retained Google tool functions; neither MCP server nor skill imports these."""
from __future__ import annotations

import asyncio

from umamusume_web_crawler.web.search import google_search_page_urls, google_search_urls


async def web_search_google(query: str) -> dict:
    """Search Google through its API when called explicitly from Python."""
    try:
        results = await asyncio.to_thread(google_search_urls, query, num=5)
        return {
            "results": [
                {"url": item["url"], "priority": str(item["priority"])}
                for item in results
            ]
        }
    except Exception as exc:
        return {"results": [], "error": str(exc)}


async def crawl_google_page(
    query: str, num: int = 5, use_proxy: bool | None = None
) -> dict:
    """Parse a Google result page when called explicitly from Python."""
    try:
        results = await asyncio.to_thread(
            google_search_page_urls, query, num=num, use_proxy=use_proxy
        )
        return {
            "results": [
                {"url": item["url"], "priority": str(item["priority"])}
                for item in results
            ]
        }
    except Exception as exc:
        return {"results": [], "error": str(exc)}
