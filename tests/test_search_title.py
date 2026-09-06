import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web.biligame import search_biligame_titles
from umamusume_web_crawler.web.moegirl import search_moegirl_titles
from umamusume_web_crawler.web.umamusu_wiki import search_umamusu_titles


@pytest.mark.asyncio
async def test_search_moegirl_title() -> None:
    keyword = os.getenv("CRAWLER_MOEGIRL_QUERY", "东海帝王")
    titles = await search_moegirl_titles(keyword)
    assert titles, "Expected moegirl search results"
    print(f"Moegirl search results for {keyword!r}: {titles}")
    assert any(title == keyword for title in titles), (
        f"Expected exact title {keyword!r} in moegirl results"
    )
    print("TEST_RESULT: PASSED")


@pytest.mark.asyncio
async def test_search_biligame_title() -> None:
    keyword = os.getenv("CRAWLER_BILIGAME_QUERY", "东海帝皇")
    titles = await search_biligame_titles(keyword)
    assert titles, "Expected biligame search results"
    print(f"Biligame search results for {keyword!r}: {titles}")
    assert any(title == keyword for title in titles), (
        f"Expected exact title {keyword!r} in biligame results"
    )
    print("TEST_RESULT: PASSED")


@pytest.mark.asyncio
async def test_search_umamusu_title() -> None:
    keyword = os.getenv("CRAWLER_UMAMUSU_QUERY", "Tokai Teio")
    titles = await search_umamusu_titles(keyword)
    assert titles, "Expected umamusu.wiki search results"
    print(f"umamusu.wiki search results for {keyword!r}: {titles}")
    assert any(title == keyword for title in titles), (
        f"Expected exact title {keyword!r} in umamusu.wiki results"
    )
    print("TEST_RESULT: PASSED")
