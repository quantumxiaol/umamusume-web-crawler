"""Public, read-only PukiWiki pages (not a MediaWiki API)."""
from __future__ import annotations

import asyncio
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .html_content import content_root
from .http import SourceError, request_text
from .wiki_urls import normalize_title, wiki_url


async def fetch_wikiru_html(title_or_url: str, *, use_proxy: bool | None = None) -> str:
    title = normalize_title(title_or_url, 'wikiru')
    html = await asyncio.to_thread(request_text, wiki_url('wikiru', title),
                                   timeout_s=60, use_proxy=use_proxy)
    soup = BeautifulSoup(html, 'lxml')
    heading = soup.select_one('#title') or soup.find('h1')
    # A misspelled URL can return the front page or edit form with HTTP 200.
    if heading is None or title not in heading.get_text(' ', strip=True):
        raise SourceError('wikiru returned a different or missing page.')
    content_root(html, 'wikiru')
    return html


async def search_wikiru_titles(keyword: str, *, limit: int = 5,
                                use_proxy: bool | None = None) -> list[str]:
    if not keyword.strip() or not 1 <= limit <= 50:
        raise ValueError('Provide a keyword and a limit between 1 and 50.')
    url = wiki_url('wikiru', 'キャラクター一覧')
    html = await asyncio.to_thread(request_text, url, timeout_s=60, cache_ttl_s=86400,
                                   use_proxy=use_proxy)
    root = content_root(html, 'wikiru')
    candidates = []
    for link in root.select('table a[href]'):
        try:
            title = normalize_title(urljoin(url, link['href']), 'wikiru')
        except ValueError:
            continue
        if keyword.casefold() in title.casefold() and title not in candidates:
            candidates.append(title)
    return sorted(candidates, key=lambda name: name.casefold() != keyword.casefold())[:limit]
