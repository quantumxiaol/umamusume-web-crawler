
import asyncio
import argparse
import sys
import os
from urllib.parse import urlparse
from pathlib import Path

# Add project root to sys.path if needed, or assume package is installed.
# For robustness in development environment, we add the src directory.
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent.parent
src_path = project_root / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from umamusume_web_crawler.web.biligame import fetch_biligame_wikitext_expanded
from umamusume_web_crawler.web.moegirl import fetch_moegirl_wikitext_expanded
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)
from umamusume_web_crawler.config import config
from dotenv import load_dotenv

def _detect_mode(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "wiki.biligame.com" in host:
        return "biligame"
    if "moegirl.org.cn" in host:
        return "moegirl"
    return "generic"

def _title_from_url(value: str) -> str:
    if not value.startswith("http://") and not value.startswith("https://"):
        return value
    parsed = urlparse(value)
    if parsed.path.endswith("/index.php"):
        params = urlparse(value).query
        if "title=" in params:
            import urllib.parse
            q = urllib.parse.parse_qs(params)
            return q.get("title", [""])[0] or "page"
    return Path(parsed.path).name or "page"

async def crawl(url: str, site: str, use_proxy: bool | None = None):
    # Load env for consistent behavior with CLI
    load_dotenv()
    config.update_from_env()
    
    if site == "auto":
        site = _detect_mode(url)

    if site == "generic":
        print(f"Error: URL {url} is not a supported MediaWiki site (Bilibili/Moegirl). Use --visual for generic sites.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching {url} (site: {site})...", file=sys.stderr)
    
    try:
        if site == "biligame":
            wikitext = await fetch_biligame_wikitext_expanded(
                url, max_depth=1, max_pages=5, use_proxy=use_proxy
            )
        elif site == "moegirl":
            wikitext = await fetch_moegirl_wikitext_expanded(
                url, max_depth=1, max_pages=5, use_proxy=use_proxy
            )
        else:
             print(f"Error: Unknown site {site}", file=sys.stderr)
             sys.exit(1)

        page = parse_wiki_page(wikitext, site=site)
        heading = _title_from_url(url)
        markdown = wiki_page_to_llm_markdown(heading, page, site=site)
        print(markdown)

    except Exception as e:
        print(f"Error crawling {url}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Crawl a wiki page using MediaWiki API")
    parser.add_argument("url", help="URL to crawl")
    parser.add_argument("--site", choices=["auto", "biligame", "moegirl"], default="auto", help="Target site type")
    parser.add_argument("--proxy", action="store_true", help="Enable proxy")
    parser.add_argument("--no-proxy", action="store_true", help="Disable proxy")
    
    args = parser.parse_args()
    
    use_proxy = None
    if args.proxy:
        use_proxy = True
    elif args.no_proxy:
        use_proxy = False
        
    asyncio.run(crawl(args.url, args.site, use_proxy))

if __name__ == "__main__":
    main()
