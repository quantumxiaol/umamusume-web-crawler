from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from urllib.parse import urlparse

from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page,
    crawl_biligame_page_visual_markitdown,
    crawl_moegirl_page,
    crawl_moegirl_page_visual_markitdown,
    crawl_page,
    crawl_page_visual_markitdown,
)


def _detect_mode(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "wiki.biligame.com" in host:
        return "biligame"
    if "moegirl.org.cn" in host:
        return "moegirl"
    return "generic"


def _proxy_flag(value: bool | None, *, default: bool) -> bool:
    return default if value is None else value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl a web page and output markdown")
    parser.add_argument("--url", required=True, help="Target URL to crawl")
    parser.add_argument(
        "--mode",
        choices=("auto", "biligame", "moegirl", "generic"),
        default="auto",
        help="Crawl mode (default: auto)",
    )
    parser.add_argument(
        "--visual",
        action="store_true",
        help="Use visual capture (PDF -> MarkItDown)",
    )
    parser.add_argument(
        "--output",
        default="results/crawl.md",
        help="Output markdown path (use '-' for stdout)",
    )
    parser.add_argument(
        "--visual-dir",
        default="results/visual",
        help="Directory for captured PDF/PNG assets",
    )
    proxy_group = parser.add_mutually_exclusive_group()
    proxy_group.add_argument("--use-proxy", action="store_true", help="Enable proxy")
    proxy_group.add_argument("--no-proxy", action="store_true", help="Disable proxy")
    parser.add_argument(
        "--print-scale",
        type=float,
        default=None,
        help="Override print scale for Moegirl visual capture",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use headless mode for visual capture",
    )
    parser.add_argument(
        "--capture-pdf",
        action="store_true",
        help="Capture PDF during visual crawl (default: true)",
    )
    parser.add_argument(
        "--no-capture-pdf",
        action="store_true",
        help="Disable PDF capture (fall back to PNG)",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    mode = _detect_mode(args.url) if args.mode == "auto" else args.mode
    use_proxy = True if args.use_proxy else False if args.no_proxy else None
    capture_pdf = True
    if args.no_capture_pdf:
        capture_pdf = False
    if args.capture_pdf:
        capture_pdf = True

    if args.visual:
        output_dir = Path(args.visual_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if mode == "biligame":
            content = await crawl_biligame_page_visual_markitdown(
                args.url,
                use_proxy=use_proxy,
                output_dir=output_dir,
                capture_pdf=capture_pdf,
            )
        elif mode == "moegirl":
            content = await crawl_moegirl_page_visual_markitdown(
                args.url,
                use_proxy=use_proxy,
                output_dir=output_dir,
                capture_pdf=capture_pdf,
                print_scale=args.print_scale,
                headless=args.headless,
            )
        else:
            content = await crawl_page_visual_markitdown(
                args.url,
                use_proxy=use_proxy,
                output_dir=output_dir,
                capture_pdf=capture_pdf,
            )
    else:
        if mode == "biligame":
            content = await crawl_biligame_page(
                args.url, use_proxy=_proxy_flag(use_proxy, default=False)
            )
        elif mode == "moegirl":
            content = await crawl_moegirl_page(
                args.url, use_proxy=_proxy_flag(use_proxy, default=True)
            )
        else:
            content = await crawl_page(
                args.url, use_proxy=_proxy_flag(use_proxy, default=False)
            )

    if args.output == "-":
        print(content)
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(content)} chars to {output_path}")


def main() -> None:
    args = parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
