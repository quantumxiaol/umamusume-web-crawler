from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - fallback when tqdm is unavailable
    tqdm = None

# Keep script runnable from repository root without installation.
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent
src_path = project_root / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.tools import crawl_wiki, search_wiki, umapyoi_tool
from umamusume_web_crawler.web.umamusu_wiki import (
    download_umamusu_file, fetch_umamusu_image_info, list_umamusu_category_files,
)


def _resolve_proxy_arg(namespace: argparse.Namespace) -> bool | None:
    if namespace.proxy:
        return True
    if namespace.no_proxy:
        return False
    return None


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


class _NoopProgress:
    def __init__(self, total: int) -> None:
        self.total = total
        self.current = 0

    def update(self, value: int = 1) -> None:
        self.current += value
        print(f"[progress] {self.current}/{self.total}", file=sys.stderr)

    def close(self) -> None:
        return None

    def set_postfix(self, **kwargs) -> None:
        if not kwargs:
            return
        summary = " ".join(f"{key}={value}" for key, value in kwargs.items())
        print(f"[progress] {summary}", file=sys.stderr)


def _make_progress(total: int, *, desc: str):
    if tqdm is None:
        return _NoopProgress(total)
    return tqdm(total=total, desc=desc, unit="file")


async def tool_download_umamusu_category_images(
    category: str,
    *,
    output_dir: str,
    max_files: int | None,
    delay_s: float,
    use_proxy: bool | None,
) -> dict:
    try:
        titles = await list_umamusu_category_files(
            category,
            max_files=max_files,
            delay_s=delay_s,
            use_proxy=use_proxy,
        )
        print(
            f"[info] Found {len(titles)} files in {category}. "
            f"Downloading to {output_dir}", file=sys.stderr
        )
        downloads = []
        progress = _make_progress(len(titles), desc="umamusu images")
        downloaded_count = 0
        skipped_count = 0
        try:
            for index, title in enumerate(titles):
                info = await fetch_umamusu_image_info(title, use_proxy=use_proxy)
                raw_title = str(info["title"])
                filename = raw_title.split(":", 1)[-1].replace("/", "_")
                target_path = Path(output_dir) / filename
                if target_path.exists():
                    skipped_count += 1
                    downloads.append(
                        {
                            **info,
                            "filename": filename,
                            "path": str(target_path),
                            "bytes": target_path.stat().st_size,
                            "skipped": True,
                        }
                    )
                else:
                    downloaded = await download_umamusu_file(
                        title,
                        output_dir=output_dir,
                        use_proxy=use_proxy,
                    )
                    downloaded["skipped"] = False
                    downloads.append(downloaded)
                    downloaded_count += 1
                progress.update(1)
                progress.set_postfix(
                    downloaded=downloaded_count,
                    skipped=skipped_count,
                )
                if delay_s > 0 and index + 1 < len(titles):
                    await asyncio.sleep(delay_s)
        finally:
            progress.close()
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
            "Biligame, Moegirl, umamusu.wiki, wikiru, and Umapyoi"
        )
    )
    subparsers = parser.add_subparsers(dest="tool", required=True)

    for site in ("biligame", "moegirl", "umamusu", "wikiru"):
        search = subparsers.add_parser(f"{site}_wiki_search", help=f"Search {site} titles")
        search.add_argument("keyword")
        search.add_argument("--limit", type=int, default=5)
        _add_proxy_flags(search)
        crawl = subparsers.add_parser(f"crawl_{site}_wiki", help=f"Read {site} rendered article")
        crawl.add_argument("url", help="URL or exact page title")
        crawl.add_argument("--max-depth", type=int, default=1, help="Legacy compatibility argument; no effect")
        crawl.add_argument("--max-pages", type=int, default=5, help="Legacy compatibility argument; no effect")
        _add_proxy_flags(crawl)
    search = subparsers.add_parser("umapyoi_character_search", help="Search Japanese/English names or game_id")
    search.add_argument("keyword")
    search.add_argument("--limit", type=int, default=5)
    _add_proxy_flags(search)
    for action in ("character", "resources"):
        command = subparsers.add_parser(f"get_umapyoi_{action}")
        command.add_argument("game_id", type=int, help="Game ID, not the Umapyoi database id")
        _add_proxy_flags(command)

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

    if args.tool.endswith("_wiki_search"):
        payload = await search_wiki(args.tool.removesuffix("_wiki_search"), args.keyword,
                                    limit=args.limit, use_proxy=use_proxy)
    elif args.tool.startswith("crawl_"):
        site = args.tool.removeprefix("crawl_").removesuffix("_wiki")
        payload = await crawl_wiki(site, args.url, use_proxy=use_proxy,
                                   max_depth=args.max_depth, max_pages=args.max_pages)
    elif args.tool == "umapyoi_character_search":
        payload = await umapyoi_tool("search", keyword=args.keyword, limit=args.limit, use_proxy=use_proxy)
    elif args.tool.startswith("get_umapyoi_"):
        payload = await umapyoi_tool(args.tool.removeprefix("get_umapyoi_"), game_id=args.game_id, use_proxy=use_proxy)
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
