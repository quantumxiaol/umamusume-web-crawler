"""Live source smoke test; use the offline suite for deterministic verification."""
import asyncio
import os
from pathlib import Path
import pytest
from umamusume_web_crawler.web.wiki_pages import fetch_wiki_page

async def _run():
    url = os.getenv("CRAWLER_MOEGIRL_URL", "https://mzh.moegirl.org.cn/东海帝王")
    page = await fetch_wiki_page(url, site="moegirl")
    assert page["source_format"] == "rendered_html"
    assert len(page["markdown"]) > 1000
    if url == "https://mzh.moegirl.org.cn/东海帝王":
        assert page["infobox"]
        assert "150" in str(page["infobox"])
    output = Path("results/test/moegirl_complete.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page["markdown"], encoding="utf-8")

@pytest.mark.asyncio
async def test_moegirl_complete_body():
    await _run()

if __name__ == "__main__":
    asyncio.run(_run())
