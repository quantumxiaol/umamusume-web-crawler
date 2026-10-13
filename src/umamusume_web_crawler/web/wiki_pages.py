"""One complete-body path shared by CLI, MCP and the skill."""
from __future__ import annotations

import asyncio

from .biligame import fetch_biligame_html
from .html_content import parse_html_page
from .http import request_text
from .umamusu_wiki import fetch_umamusu_html
from .wikiru import fetch_wikiru_html
from .wiki_urls import detect_site, normalize_title, wiki_url


async def fetch_wiki_page(value: str, *, site: str | None = None,
                          use_proxy: bool | None = None) -> dict:
    site = site or detect_site(value)
    title = normalize_title(value, site)
    url = wiki_url(site, title)
    if site == 'biligame':
        html = await fetch_biligame_html(title, use_proxy=use_proxy)
        transport = 'mediawiki_parse'
    elif site == 'umamusu':
        html = await fetch_umamusu_html(title, use_proxy=use_proxy)
        transport = 'mediawiki_parse'
    elif site == 'moegirl':
        # extracts intentionally omit tables; parse/revisions require permission.
        # Read only the public article, with no access-control workaround.
        html = await asyncio.to_thread(request_text, url, use_proxy=use_proxy)
        transport = 'public_html'
    elif site == 'wikiru':
        html = await fetch_wikiru_html(title, use_proxy=use_proxy)
        transport = 'public_html'
    else:
        raise ValueError(f'Unsupported wiki: {site}')
    return {**parse_html_page(html, title=title, source_url=url, site=site),
            'site': site, 'transport': transport}
