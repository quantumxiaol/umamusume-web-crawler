"""Transport-neutral tool results for MCP and skill commands."""
from __future__ import annotations

from collections.abc import Callable

from .biligame import search_biligame_titles
from .moegirl import search_moegirl_titles
from .umamusu_wiki import download_umamusu_category_images, search_umamusu_titles
from .wikiru import search_wikiru_titles
from .wiki_pages import fetch_wiki_page
from .wiki_urls import wiki_url
from .umapyoi import search_umapyoi_characters, fetch_umapyoi_character, fetch_umapyoi_resources

_SEARCHERS = {'biligame': search_biligame_titles, 'moegirl': search_moegirl_titles,
              'umamusu': search_umamusu_titles, 'wikiru': search_wikiru_titles}


async def search_wiki(site: str, keyword: str, *, limit: int = 5,
                      use_proxy: bool | None = None) -> dict:
    try:
        if not keyword.strip() or not 1 <= limit <= 50:
            raise ValueError('Provide a keyword and a limit between 1 and 50.')
        titles = await _SEARCHERS[site](keyword, limit=limit, use_proxy=use_proxy)
        return {'results': [{'title': title, 'url': wiki_url(site, title), 'priority': str(i + 1)}
                            for i, title in enumerate(titles)]}
    except Exception as exc:
        return {'results': [], 'error': str(exc)}


async def crawl_wiki(site: str, url: str, *, use_proxy: bool | None = None,
                     max_depth: int = 1, max_pages: int = 5) -> dict:
    # Legacy expansion arguments are accepted for compatibility. Server-rendered
    # HTML already expands templates; this path makes no recursive page requests.
    try:
        page = await fetch_wiki_page(url, site=site, use_proxy=use_proxy)
        return {'status': 'success', 'result': page.pop('markdown'), **page}
    except Exception as exc:
        return {'status': 'error', 'message': str(exc)}


async def umapyoi_tool(action: str, *, keyword: str = '', game_id: int = 0,
                       limit: int = 5, use_proxy: bool | None = None) -> dict:
    try:
        if action == 'search':
            return await search_umapyoi_characters(keyword, limit=limit, use_proxy=use_proxy)
        if action not in {'character', 'resources'}:
            raise ValueError('Unknown Umapyoi action.')
        fetch = fetch_umapyoi_character if action == 'character' else fetch_umapyoi_resources
        return {'status': 'success', **await fetch(game_id, use_proxy=use_proxy)}
    except Exception as exc:
        if action == 'search':
            return {'results': [], 'error': str(exc)}
        return {'status': 'error', 'message': str(exc)}


async def umamusu_category_images_tool(
    category: str,
    *,
    output_dir: str = "results/umamusu_wiki_images",
    max_files: int | None = None,
    delay_s: float = 0.5,
    use_proxy: bool | None = None,
    skip_existing: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    try:
        downloads = await download_umamusu_category_images(
            category,
            output_dir=output_dir,
            max_files=max_files,
            delay_s=delay_s,
            use_proxy=use_proxy,
            skip_existing=skip_existing,
            progress=progress,
        )
        return {
            "status": "success",
            "category": category,
            "output_dir": output_dir,
            "count": len(downloads),
            "downloaded": downloads,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
