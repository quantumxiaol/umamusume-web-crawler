import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page_visual_markitdown,
)


async def _run() -> None:
    target_url = os.getenv(
        "CRAWLER_BILIGAME_URL",
        "https://wiki.biligame.com/umamusume/东海帝皇",
    )
    use_proxy = os.getenv("CRAWLER_USE_PROXY", "0") not in ("0", "false", "False")
    try:
        content = await crawl_biligame_page_visual_markitdown(
            target_url, use_proxy=use_proxy
        )
        output_name = "biligame_visual.txt"
    except asyncio.TimeoutError:
        print("TEST_RESULT: FAILED (timeout)")
        raise
    assert isinstance(content, str)
    assert content.strip(), "Expected non-empty crawl content"
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
