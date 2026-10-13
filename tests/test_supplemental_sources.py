"""Low-volume live smoke tests for the two supplemental sources."""
import os

import pytest

from umamusume_web_crawler.web.tools import search_wiki
from umamusume_web_crawler.web.umapyoi import (
    fetch_umapyoi_character,
    fetch_umapyoi_resources,
    search_umapyoi_characters,
)
from umamusume_web_crawler.web.wiki_pages import fetch_wiki_page

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("RUN_SOURCE_INTEGRATION") != "1",
        reason="set RUN_SOURCE_INTEGRATION=1 to query public supplemental sources",
    ),
]


async def test_wikiru_character_search_and_complete_body():
    results = await search_wiki("wikiru", "トウカイテイオー", use_proxy=False)
    assert "error" not in results, results
    match = next(item for item in results["results"] if item["title"] == "トウカイテイオー")
    page = await fetch_wiki_page(match["url"], use_proxy=False)
    assert page["site"] == "wikiru"
    assert page["infobox"]["名前"] == "トウカイテイオー"
    assert "150" in page["infobox"]["身長"]
    assert "ボイス" in page["markdown"] and "親愛度" in page["markdown"]
    assert "コメントフォーム" not in page["markdown"]


async def test_umapyoi_search_profile_and_resources():
    results = await search_umapyoi_characters("Tokai Teio", use_proxy=False)
    assert any(item["game_id"] == 1003 for item in results["results"])
    profile = await fetch_umapyoi_character(1003, use_proxy=False)
    assert profile["profile"]["name_jp"] == "トウカイテイオー"
    assert profile["profile"]["game_id"] == 1003
    resources = await fetch_umapyoi_resources(1003, use_proxy=False)
    assert resources["partial"] is False, resources["errors"]
    assert resources["url_status"] == "unverified"
    # Counts can grow; verify structure and identity rather than a fixed snapshot.
    assert resources["outfits"] and resources["support_cards"] and resources["images"]
    assert all(item["chara_id"] == 1003 for item in resources["outfits"])
    assert any(group["images"] for group in resources["images"])
