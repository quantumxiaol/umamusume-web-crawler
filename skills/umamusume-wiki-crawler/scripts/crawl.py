from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from dotenv import load_dotenv

# Keep script runnable from repository root without installation.
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent
src_path = project_root / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.biligame import (
    fetch_biligame_wikitext_expanded,
    search_biligame_titles,
)
from umamusume_web_crawler.web.moegirl import (
    fetch_moegirl_wikitext_expanded,
    search_moegirl_titles,
)
from umamusume_web_crawler.web.umamusu_wiki import (
    DEFAULT_BASE_URL as _UMAMUSU_BASE_URL,
    download_umamusu_category_images,
    fetch_umamusu_wikitext_expanded,
    search_umamusu_titles,
)
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)

_BILIGAME_BASE_URL = "https://wiki.biligame.com/umamusume/"
_MOEGIRL_BASE_URL = "https://mzh.moegirl.org.cn/"


def _title_from_url(value: str) -> str:
    if not value.startswith("http://") and not value.startswith("https://"):
        return value
    parsed = urlparse(value)
    if parsed.path.endswith("/index.php"):
        params = parse_qs(parsed.query)
        title = params.get("title", [""])[0]
        if title:
            return title
    return unquote(parsed.path.strip("/").split("/")[-1])


def _build_wiki_url(base_url: str, title: str) -> str:
    return f"{base_url}{quote(title)}"


def _resolve_proxy_arg(namespace: argparse.Namespace) -> bool | None:
    if namespace.proxy:
        return True
    if namespace.no_proxy:
        return False
    return None


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def tool_biligame_wiki_search(
    keyword: str,
    *,
    limit: int,
    use_proxy: bool | None,
) -> dict:
    try:
        titles = await search_biligame_titles(keyword, limit=limit, use_proxy=use_proxy)
        results = [
            {
                "title": title,
                "url": _build_wiki_url(_BILIGAME_BASE_URL, title),
                "priority": str(idx + 1),
            }
            for idx, title in enumerate(titles)
        ]
        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


async def tool_moegirl_wiki_search(
    keyword: str,
    *,
    limit: int,
    use_proxy: bool | None,
) -> dict:
    try:
        titles = await search_moegirl_titles(keyword, limit=limit, use_proxy=use_proxy)
        results = [
            {
                "title": title,
                "url": _build_wiki_url(_MOEGIRL_BASE_URL, title),
                "priority": str(idx + 1),
            }
            for idx, title in enumerate(titles)
        ]
        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


async def tool_crawl_biligame_wiki(
    url: str,
    *,
    max_depth: int,
    max_pages: int,
    use_proxy: bool | None,
) -> dict:
    try:
        wikitext = await fetch_biligame_wikitext_expanded(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            use_proxy=use_proxy,
        )
        page = parse_wiki_page(wikitext, site="biligame")
        heading = _title_from_url(url)
        markdown = wiki_page_to_llm_markdown(heading, page, site="biligame")
        return {"status": "success", "result": markdown}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def tool_crawl_moegirl_wiki(
    url: str,
    *,
    max_depth: int,
    max_pages: int,
    use_proxy: bool | None,
) -> dict:
    try:
        wikitext = await fetch_moegirl_wikitext_expanded(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            use_proxy=use_proxy,
        )
        page = parse_wiki_page(wikitext, site="moegirl")
        heading = _title_from_url(url)
        markdown = wiki_page_to_llm_markdown(heading, page, site="moegirl")
        return {"status": "success", "result": markdown}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def tool_umamusu_wiki_search(
    keyword: str,
    *,
    limit: int,
    use_proxy: bool | None,
) -> dict:
    try:
        titles = await search_umamusu_titles(keyword, limit=limit, use_proxy=use_proxy)
        results = [
            {
                "title": title,
                "url": _build_wiki_url(_UMAMUSU_BASE_URL, title),
                "priority": str(idx + 1),
            }
            for idx, title in enumerate(titles)
        ]
        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


async def tool_crawl_umamusu_wiki(
    url: str,
    *,
    max_depth: int,
    max_pages: int,
    use_proxy: bool | None,
) -> dict:
    try:
        wikitext = await fetch_umamusu_wikitext_expanded(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            use_proxy=use_proxy,
        )
        page = parse_wiki_page(wikitext, site="umamusu")
        heading = _title_from_url(url)
        markdown = wiki_page_to_llm_markdown(heading, page, site="umamusu")
        return {"status": "success", "result": markdown}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def tool_download_umamusu_category_images(
    category: str,
    *,
    output_dir: str,
    max_files: int | None,
    delay_s: float,
    use_proxy: bool | None,
) -> dict:
    try:
        downloads = await download_umamusu_category_images(
            category,
            output_dir=output_dir,
            max_files=max_files,
            delay_s=delay_s,
            use_proxy=use_proxy,
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


def _add_proxy_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--proxy", action="store_true", help="Enable proxy")
    group.add_argument("--no-proxy", action="store_true", help="Disable proxy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "CLI wrapper for Umamusume wiki tools across "
            "Biligame, Moegirl, and umamusu.wiki"
        )
    )
    subparsers = parser.add_subparsers(dest="tool", required=True)

    p_bili_search = subparsers.add_parser(
        "biligame_wiki_search",
        help="Search titles on Bilibili Wiki",
    )
    p_bili_search.add_argument("keyword", help="Search keyword")
    p_bili_search.add_argument("--limit", type=int, default=5, help="Result limit")
    _add_proxy_flags(p_bili_search)

    p_moe_search = subparsers.add_parser(
        "moegirl_wiki_search",
        help="Search titles on Moegirl Wiki",
    )
    p_moe_search.add_argument("keyword", help="Search keyword")
    p_moe_search.add_argument("--limit", type=int, default=5, help="Result limit")
    _add_proxy_flags(p_moe_search)

    p_bili_crawl = subparsers.add_parser(
        "crawl_biligame_wiki",
        help="Fetch and parse a Bilibili Wiki page",
    )
    p_bili_crawl.add_argument("url", help="Biligame Wiki URL or page title")
    p_bili_crawl.add_argument("--max-depth", type=int, default=1, help="Transclusion depth")
    p_bili_crawl.add_argument("--max-pages", type=int, default=5, help="Max fetched pages")
    _add_proxy_flags(p_bili_crawl)

    p_moe_crawl = subparsers.add_parser(
        "crawl_moegirl_wiki",
        help="Fetch and parse a Moegirl Wiki page",
    )
    p_moe_crawl.add_argument("url", help="Moegirl URL or page title")
    p_moe_crawl.add_argument("--max-depth", type=int, default=1, help="Transclusion depth")
    p_moe_crawl.add_argument("--max-pages", type=int, default=5, help="Max fetched pages")
    _add_proxy_flags(p_moe_crawl)

    p_umamusu_search = subparsers.add_parser(
        "umamusu_wiki_search",
        help="Search titles on umamusu.wiki",
    )
    p_umamusu_search.add_argument("keyword", help="Search keyword")
    p_umamusu_search.add_argument("--limit", type=int, default=5, help="Result limit")
    _add_proxy_flags(p_umamusu_search)

    p_umamusu_crawl = subparsers.add_parser(
        "crawl_umamusu_wiki",
        help="Fetch and parse a umamusu.wiki page",
    )
    p_umamusu_crawl.add_argument("url", help="umamusu.wiki URL or page title")
    p_umamusu_crawl.add_argument(
        "--max-depth", type=int, default=1, help="Transclusion depth"
    )
    p_umamusu_crawl.add_argument(
        "--max-pages", type=int, default=5, help="Max fetched pages"
    )
    _add_proxy_flags(p_umamusu_crawl)

    p_umamusu_download = subparsers.add_parser(
        "download_umamusu_category_images",
        help="Download all images from a umamusu.wiki file category",
    )
    p_umamusu_download.add_argument(
        "category",
        help="Category title or URL, e.g. Category:Game_Backgrounds",
    )
    p_umamusu_download.add_argument(
        "--output-dir",
        default="results/umamusu_wiki_images",
        help="Directory to save downloaded files",
    )
    p_umamusu_download.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional limit on downloaded files",
    )
    p_umamusu_download.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between paged API/download requests",
    )
    _add_proxy_flags(p_umamusu_download)

    return parser.parse_args()


def _has_error(payload: dict) -> bool:
    if payload.get("status") == "error":
        return True
    return "error" in payload


async def _run(args: argparse.Namespace) -> int:
    use_proxy = _resolve_proxy_arg(args)

    if args.tool == "biligame_wiki_search":
        payload = await tool_biligame_wiki_search(
            args.keyword,
            limit=args.limit,
            use_proxy=use_proxy,
        )
    elif args.tool == "moegirl_wiki_search":
        payload = await tool_moegirl_wiki_search(
            args.keyword,
            limit=args.limit,
            use_proxy=use_proxy,
        )
    elif args.tool == "crawl_biligame_wiki":
        payload = await tool_crawl_biligame_wiki(
            args.url,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            use_proxy=use_proxy,
        )
    elif args.tool == "crawl_moegirl_wiki":
        payload = await tool_crawl_moegirl_wiki(
            args.url,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            use_proxy=use_proxy,
        )
    elif args.tool == "umamusu_wiki_search":
        payload = await tool_umamusu_wiki_search(
            args.keyword,
            limit=args.limit,
            use_proxy=use_proxy,
        )
    elif args.tool == "crawl_umamusu_wiki":
        payload = await tool_crawl_umamusu_wiki(
            args.url,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            use_proxy=use_proxy,
        )
    else:
        payload = await tool_download_umamusu_category_images(
            args.category,
            output_dir=args.output_dir,
            max_files=args.max_files,
            delay_s=args.delay,
            use_proxy=use_proxy,
        )

    _print_json(payload)
    return 1 if _has_error(payload) else 0


def main() -> None:
    load_dotenv()
    config.update_from_env()
    args = parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
