import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)
from umamusume_web_crawler.web.umamusu_wiki import (
    fetch_umamusu_wikitext_expanded,
)


def _title_from_url(value: str) -> str:
    if not value.startswith("http://") and not value.startswith("https://"):
        return value
    parsed = urlparse(value)
    return unquote(parsed.path.strip("/").split("/")[-1])


async def _run() -> None:
    target_url = os.getenv(
        "CRAWLER_UMAMUSU_URL",
        "https://umamusu.wiki/Tokai_Teio",
    )
    try:
        content = await fetch_umamusu_wikitext_expanded(
            target_url, max_depth=0, max_pages=1
        )
        output_name = "umamusu_api.md"
    except asyncio.TimeoutError:
        print("TEST_RESULT: FAILED (timeout)")
        raise
    assert isinstance(content, str)
    assert content.strip(), "Expected non-empty crawl content"
    page = parse_wiki_page(content, site="umamusu")
    heading = _title_from_url(target_url)
    content = wiki_page_to_llm_markdown(heading, page, site="umamusu")
    output_dir = Path("results") / "test"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name
    output_path.write_text(content, encoding="utf-8")
    print(f"Wrote {len(content)} chars to {output_path}")
    print("TEST_RESULT: PASSED")


@pytest.mark.asyncio
async def test_umamusu_wiki_crawler() -> None:
    await _run()


if __name__ == "__main__":
    asyncio.run(_run())
