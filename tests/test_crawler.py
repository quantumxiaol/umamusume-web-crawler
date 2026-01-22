import asyncio
import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web.crawler import crawl_page


@pytest.mark.asyncio
async def test_crawl_page_returns_content() -> None:
    target_url = os.getenv(
        "CRAWLER_TEST_URL",
        "https://example.com",
    )

    try:
        content = await crawl_page(target_url, use_proxy=False)
    except asyncio.TimeoutError:
        print("TEST_RESULT: FAILED (timeout)")
        raise
    assert isinstance(content, str)
    assert content.strip(), "Expected non-empty crawl content"
    print(content[:2000])
    print("TEST_RESULT: PASSED")


if __name__ == "__main__":
    args = sys.argv[1:] or [__file__]
    pytest.main(args)
