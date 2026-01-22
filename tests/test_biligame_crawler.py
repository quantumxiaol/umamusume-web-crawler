import asyncio
import os
import sys
from urllib.parse import unquote, urlparse
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web.biligame import (
    fetch_biligame_wikitext_expanded,
    search_biligame_titles,
)
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)


def _title_from_url(value: str) -> str:
    if not value.startswith("http://") and not value.startswith("https://"):
        return value
    parsed = urlparse(value)
    return unquote(parsed.path.strip("/").split("/")[-1])


async def _run() -> None:
    target_url = os.getenv(
        "CRAWLER_BILIGAME_URL",
        "https://wiki.biligame.com/umamusume/东海帝皇",
    )
    keyword = os.getenv("CRAWLER_BILIGAME_QUERY", "东海帝皇")
    try:
        titles = await search_biligame_titles(keyword)
        if titles:
            print(f"Search results for {keyword!r}: {titles}")
            target_title = titles[0]
        else:
            print(f"No search results for {keyword!r}, fallback to URL")
            target_title = target_url
        content = await fetch_biligame_wikitext_expanded(
            target_title, max_depth=1, max_pages=5
        )
        output_name = "biligame_api.md"
    except asyncio.TimeoutError:
        print("TEST_RESULT: FAILED (timeout)")
        raise
    assert isinstance(content, str)
    assert content.strip(), "Expected non-empty crawl content"
    page = parse_wiki_page(content, site="biligame")
    heading = target_title if titles else _title_from_url(target_title)
    content = wiki_page_to_llm_markdown(heading, page, site="biligame")
    output_dir = Path("results") / "test"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(content)} chars to {output_path}")
    print("TEST_RESULT: PASSED")


@pytest.mark.asyncio
async def test_biligame_crawler() -> None:
    await _run()


if __name__ == "__main__":
    asyncio.run(_run())
