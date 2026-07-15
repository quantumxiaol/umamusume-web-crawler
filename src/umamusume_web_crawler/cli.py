from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from umamusume_web_crawler.config import config

from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page,
    crawl_biligame_page_visual_markitdown,
    crawl_moegirl_page,
    crawl_moegirl_page_visual_markitdown,
    crawl_page,
    crawl_page_visual_markitdown,
)
from umamusume_web_crawler.web.biligame import fetch_biligame_wikitext_expanded
from umamusume_web_crawler.web.biligame_assets import (
    CharacterAssetTarget,
    DEFAULT_AUDIO_OUTPUT_ROOT,
    DEFAULT_CHARACTERS_JSON,
    DEFAULT_IMAGE_OUTPUT_ROOT,
    crawl_biligame_character_assets,
    load_asset_targets_from_json,
)
from umamusume_web_crawler.web.character_index import (
    DEFAULT_NAME_OVERRIDES,
    update_character_index,
)
from umamusume_web_crawler.web.moegirl import fetch_moegirl_wikitext_expanded
from umamusume_web_crawler.web.umamusu_wiki import fetch_umamusu_wikitext_expanded
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)


def _detect_mode(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "wiki.biligame.com" in host:
        return "biligame"
    if "moegirl.org.cn" in host:
        return "moegirl"
    if "umamusu.wiki" in host:
        return "umamusu"
    return "generic"


def _title_from_url(value: str) -> str:
    if not value.startswith("http://") and not value.startswith("https://"):
        return value
    parsed = urlparse(value)
    if parsed.path.endswith("/index.php"):
        params = urlparse(value).query
        # simple parse
        if "title=" in params:
            import urllib.parse
            q = urllib.parse.parse_qs(params)
            return q.get("title", [""])[0] or "page"
    return Path(parsed.path).name or "page"


async def _run_api_crawl(url: str, site: str, use_proxy: bool | None) -> str:
    print(f"[API-CRAWL] Fetching {url} via MediaWiki API...")
    if site == "biligame":
        wikitext = await fetch_biligame_wikitext_expanded(
            url, max_depth=1, max_pages=5, use_proxy=use_proxy
        )
    elif site == "moegirl":
        wikitext = await fetch_moegirl_wikitext_expanded(
            url, max_depth=1, max_pages=5, use_proxy=use_proxy
        )
    elif site == "umamusu":
        wikitext = await fetch_umamusu_wikitext_expanded(
            url, max_depth=1, max_pages=5, use_proxy=use_proxy
        )
    else:
        raise ValueError(f"Unsupported API site: {site}")

    page = parse_wiki_page(wikitext, site=site)
    heading = _title_from_url(url)
    return wiki_page_to_llm_markdown(heading, page, site=site)


def _proxy_flag(value: bool | None, *, default: bool) -> bool:
    return default if value is None else value


def _resolve_asset_targets(
    args: argparse.Namespace,
) -> dict[str, str] | list[CharacterAssetTarget]:
    if args.character:
        if not args.name or len(args.character) != len(args.name):
            raise SystemExit("--character and --name must be provided with the same count.")
        return dict(zip(args.character, args.name, strict=True))
    return load_asset_targets_from_json(
        args.characters_json,
        include_variants=getattr(args, "include_variants", False),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Umamusume crawler CLI")
    parser.add_argument(
        "--task",
        choices=("page", "biligame-assets", "update-character-index"),
        default="page",
        help="Task to run (default: page)",
    )
    parser.add_argument("--url", help="Target URL to crawl")
    parser.add_argument(
        "--mode",
        choices=("auto", "biligame", "moegirl", "umamusu", "generic"),
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
    parser.add_argument(
        "--google-api-key",
        default=None,
        help="Google API Key for search",
    )
    parser.add_argument(
        "--google-cse-id",
        default=None,
        help="Google Custom Search Engine ID",
    )
    parser.add_argument(
        "--audio-output",
        default=DEFAULT_AUDIO_OUTPUT_ROOT,
        help=f"Audio output root directory (default: {DEFAULT_AUDIO_OUTPUT_ROOT})",
    )
    parser.add_argument(
        "--image-output",
        default=DEFAULT_IMAGE_OUTPUT_ROOT,
        help=f"Image output root directory (default: {DEFAULT_IMAGE_OUTPUT_ROOT})",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip crawling character images.",
    )
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="Skip crawling audio files.",
    )
    parser.add_argument(
        "--character",
        action="append",
        help="Biligame wiki page suffix to crawl (can be repeated).",
    )
    parser.add_argument(
        "--name",
        action="append",
        help="English name for each --character, same order as provided.",
    )
    parser.add_argument(
        "--dump-html",
        default=None,
        help="Optional directory to dump raw HTML for debugging.",
    )
    parser.add_argument(
        "--characters-json",
        default=DEFAULT_CHARACTERS_JSON,
        help=f"Characters mapping json file (default: {DEFAULT_CHARACTERS_JSON})",
    )
    parser.add_argument(
        "--name-overrides",
        default=DEFAULT_NAME_OVERRIDES,
        help=(
            "Manual cn-to-en names used for official characters without a Bwiki page "
            f"(default: {DEFAULT_NAME_OVERRIDES})"
        ),
    )
    parser.add_argument(
        "--include-variants",
        action="store_true",
        help="Download every costume page from the schema-v2 character index.",
    )
    parser.add_argument(
        "--asset-manifest",
        default=None,
        help="Asset manifest path (default: <image-output>/.biligame_asset_manifest.json).",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Revisit pages recorded as complete in the local asset manifest.",
    )
    parser.add_argument(
        "--trust-existing-character-dirs",
        action="store_true",
        help=(
            "Treat non-empty existing base-character image directories as complete "
            "without visiting their Bwiki pages."
        ),
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.2,
        help="Delay in seconds before each asset download (default: 0.2)",
    )
    parser.add_argument(
        "--page-delay",
        type=float,
        default=0.5,
        help="Delay in seconds between character pages (default: 0.5)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Max concurrent asset downloads (default: 4)",
    )
    parser.add_argument(
        "--asset-summary-output",
        default=None,
        help="Optional JSON file to store biligame asset crawl summary.",
    )
    parser.add_argument(
        "--asset-quiet",
        action="store_true",
        help="Reduce biligame asset crawl logging.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    use_proxy = True if args.use_proxy else False if args.no_proxy else None
    if args.task == "update-character-index":
        payload, unresolved = await update_character_index(
            args.characters_json,
            overrides_path=args.name_overrides,
            use_proxy=use_proxy,
            detail_delay=args.request_delay,
        )
        counts = payload["counts"]
        print(
            f"Updated {args.characters_json}: characters={counts['characters']} "
            f"implemented={counts['implemented']} variants={counts['variants']} "
            f"unresolved={counts['unresolved']}"
        )
        for item in unresolved:
            print(f"[unresolved] {item['source']}: {item['value']}")
        return

    if args.task == "biligame-assets":
        if args.skip_audio and args.skip_images:
            raise SystemExit("--skip-audio and --skip-images cannot both be set.")
        include_variants = getattr(args, "include_variants", False)
        if include_variants and not args.skip_audio:
            raise SystemExit("--include-variants requires --skip-audio.")
        if include_variants and args.character:
            raise SystemExit(
                "--include-variants uses the schema-v2 --characters-json; "
                "do not combine it with --character."
            )
        targets = _resolve_asset_targets(args)
        summary = await crawl_biligame_character_assets(
            targets,
            audio_output_root=args.audio_output,
            image_output_root=args.image_output,
            dump_html_dir=args.dump_html,
            request_delay=args.request_delay,
            page_delay=args.page_delay,
            concurrency=args.concurrency,
            skip_audio=args.skip_audio,
            skip_images=args.skip_images,
            use_proxy=use_proxy,
            verbose=not args.asset_quiet,
            asset_manifest_path=getattr(args, "asset_manifest", None),
            refresh_existing=getattr(args, "refresh_existing", False),
            trust_existing_character_dirs=getattr(
                args, "trust_existing_character_dirs", False
            ),
        )
        if args.asset_summary_output:
            output_path = Path(args.asset_summary_output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Wrote asset summary to {output_path}")
        return

    if not args.url:
        raise SystemExit("--url is required when --task page.")

    mode = _detect_mode(args.url) if args.mode == "auto" else args.mode
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
        # Default to API for supported sites if not in visual mode
        if mode == "biligame":
             content = await _run_api_crawl(args.url, "biligame", use_proxy)
        elif mode == "moegirl":
             content = await _run_api_crawl(args.url, "moegirl", use_proxy)
        elif mode == "umamusu":
             content = await _run_api_crawl(args.url, "umamusu", use_proxy)
        else:
             # Fallback to headless browser for generic pages
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
    load_dotenv()
    args = parse_args()

    overrides = {}
    if args.google_api_key:
        overrides["google_api_key"] = args.google_api_key
    if args.google_cse_id:
        overrides["google_cse_id"] = args.google_cse_id

    if overrides:
        config.apply_overrides(**overrides)

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
