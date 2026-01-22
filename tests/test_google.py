import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web.search import google_search_urls


def test_google_search_urls() -> None:
    if not os.getenv("GOOGLE_API_KEY") or not os.getenv("GOOGLE_CSE_ID"):
        print("TEST_RESULT: SKIPPED (GOOGLE_API_KEY/GOOGLE_CSE_ID not set)")
        pytest.skip("GOOGLE_API_KEY or GOOGLE_CSE_ID not set")

    query_str = "爱慕织姬 site:wiki.biligame.com/umamusume"
    results = google_search_urls(search_term=query_str)
    assert isinstance(results, list)
    assert results, "Expected non-empty google search results"
    print(f"Google results: {len(results)} for query={query_str!r}")
    for item in results[:3]:
        print(f"- {item.get('url')} (priority={item.get('priority')})")
    print("TEST_RESULT: PASSED")


if __name__ == "__main__":
    test_google_search_urls()
