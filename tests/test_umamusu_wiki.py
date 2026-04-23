import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler.web import umamusu_wiki


@pytest.mark.asyncio
async def test_list_umamusu_category_files_handles_continue(monkeypatch) -> None:
    responses = [
        {
            "query": {
                "categorymembers": [
                    {"title": "File:Bg_0001.png"},
                    {"title": "File:Bg_0002.png"},
                ]
            },
            "continue": {"cmcontinue": "page|123", "continue": "-||"},
        },
        {
            "query": {
                "categorymembers": [
                    {"title": "File:Bg_0003.png"},
                    {"title": "File:Bg_0002.png"},
                ]
            }
        },
    ]
    calls: list[str] = []

    def fake_request_json(url: str, *, timeout_s: float, use_proxy: bool | None = None):
        calls.append(url)
        return responses[len(calls) - 1]

    monkeypatch.setattr(umamusu_wiki, "_request_json", fake_request_json)

    titles = await umamusu_wiki.list_umamusu_category_files("Game_Backgrounds")

    assert titles == [
        "File:Bg_0001.png",
        "File:Bg_0002.png",
        "File:Bg_0003.png",
    ]
    assert len(calls) == 2
    assert "cmtitle=Category%3AGame_Backgrounds" in calls[0]
    assert "cmcontinue=page%7C123" in calls[1]


@pytest.mark.asyncio
async def test_download_umamusu_category_images_uses_file_titles(tmp_path, monkeypatch) -> None:
    async def fake_list(
        category_title_or_url: str,
        *,
        endpoint: str = umamusu_wiki.DEFAULT_API_ENDPOINT,
        page_limit: int = 500,
        max_files: int | None = None,
        timeout_s: float = 30.0,
        use_proxy: bool | None = None,
        delay_s: float = 0.0,
    ) -> list[str]:
        assert category_title_or_url == "Category:Game_Backgrounds"
        return ["File:Bg_0001.png", "File:Bg_0002.webp"]

    async def fake_image_info(
        file_title_or_url: str,
        *,
        endpoint: str = umamusu_wiki.DEFAULT_API_ENDPOINT,
        timeout_s: float = 30.0,
        use_proxy: bool | None = None,
    ) -> dict[str, object]:
        filename = file_title_or_url.split(":", 1)[1]
        return {
            "title": file_title_or_url,
            "url": f"https://img.example/{filename}",
            "mime": "image/png",
            "size": 3,
        }

    def fake_request_bytes(
        url: str, *, timeout_s: float, use_proxy: bool | None = None
    ) -> bytes:
        return url.encode("utf-8")

    monkeypatch.setattr(umamusu_wiki, "list_umamusu_category_files", fake_list)
    monkeypatch.setattr(umamusu_wiki, "fetch_umamusu_image_info", fake_image_info)
    monkeypatch.setattr(umamusu_wiki, "_request_bytes", fake_request_bytes)

    downloads = await umamusu_wiki.download_umamusu_category_images(
        "Category:Game_Backgrounds",
        output_dir=tmp_path,
        delay_s=0.0,
    )

    assert [item["filename"] for item in downloads] == ["Bg_0001.png", "Bg_0002.webp"]
    assert (tmp_path / "Bg_0001.png").read_bytes() == b"https://img.example/Bg_0001.png"
    assert (tmp_path / "Bg_0002.webp").read_bytes() == b"https://img.example/Bg_0002.webp"


@pytest.mark.asyncio
async def test_fetch_umamusu_wikitext_expanded_appends_transclusions(monkeypatch) -> None:
    pages = {
        "List_of_Characters": "{{:Template:Characters}}\nIntro",
        "Template:Characters": "Expanded body",
    }

    async def fake_fetch(
        title_or_url: str,
        *,
        endpoint: str = umamusu_wiki.DEFAULT_API_ENDPOINT,
        timeout_s: float = 30.0,
        use_proxy: bool | None = None,
    ) -> str:
        return pages[title_or_url]

    monkeypatch.setattr(umamusu_wiki, "fetch_umamusu_wikitext", fake_fetch)

    content = await umamusu_wiki.fetch_umamusu_wikitext_expanded(
        "List_of_Characters",
        max_depth=1,
        max_pages=5,
    )

    assert "Intro" in content
    assert "== Template:Characters ==" in content
    assert "Expanded body" in content
