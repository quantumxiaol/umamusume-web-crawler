import os
import sys
import json
from argparse import Namespace
from unittest.mock import AsyncMock

import pytest
from bs4 import BeautifulSoup

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from umamusume_web_crawler import cli
from umamusume_web_crawler.web.biligame_assets import (
    CharacterAssetTarget,
    DEFAULT_AUDIO_OUTPUT_ROOT,
    DEFAULT_IMAGE_OUTPUT_ROOT,
    build_image_filename,
    crawl_biligame_character_assets,
    extract_character_images,
    extract_text_near_node,
    parse_image_srcset,
)


def test_parse_image_srcset_picks_highest_density() -> None:
    srcset = (
        "//example.com/a.png 1x, "
        "//example.com/b.png 2x, "
        "//example.com/c.png 640w"
    )
    assert parse_image_srcset(srcset) == "https://example.com/c.png"


def test_extract_character_images_prefers_original_media_filename() -> None:
    html = """
    <div class="support_card-bt">角色立绘</div>
    <div class="support_card-bg2">
      <a href="/umamusume/%E6%96%87%E4%BB%B6:Tokai_Teio.png">
        <img
          src="//patchwiki.biligame.com/images/umamusume/thumb/a/ab/Tokai_Teio.png/320px-Tokai_Teio.png"
          alt="ignored.png"
        />
      </a>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")

    images = extract_character_images(soup, "Tokai Teio")

    assert images == [
        (
            "https://patchwiki.biligame.com/images/umamusume/a/ab/Tokai_Teio.png",
            "Tokai_Teio.png",
        )
    ]


def test_extract_text_near_node_reads_jp_and_zh_voice_text() -> None:
    html = """
    <div class="voice_block">
      <div class="voice_text_jp">こんにちは</div>
      <div class="voice_text_chs">你好</div>
      <div class="bikit-audio" data-src="//cdn.example.com/voice.mp3"></div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(".bikit-audio")
    assert node is not None

    texts = extract_text_near_node(node)

    assert texts == {"jp": "こんにちは", "zh": "你好"}


def test_build_image_filename_falls_back_to_url_extension() -> None:
    html = '<img alt="Tokai Teio" src="//cdn.example.com/teio.webp" />'
    soup = BeautifulSoup(html, "html.parser")
    node = soup.img
    assert node is not None

    filename = build_image_filename(
        node,
        "https://cdn.example.com/teio.webp",
        "Tokai Teio",
        1,
    )

    assert filename == "teio.webp"


def test_biligame_asset_default_output_roots_are_under_results() -> None:
    assert DEFAULT_AUDIO_OUTPUT_ROOT == "results/voicedata"
    assert DEFAULT_IMAGE_OUTPUT_ROOT == "results/imagedata/characters"


@pytest.mark.asyncio
async def test_complete_manifest_skips_page_without_starting_crawler(
    tmp_path, monkeypatch
) -> None:
    image_root = tmp_path / "images"
    image_dir = image_root / "Special Week"
    image_dir.mkdir(parents=True)
    (image_dir / "special.png").write_bytes(b"image")
    manifest = image_root / ".biligame_asset_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pages": {
                    "特别周": {
                        "name_en": "Special Week",
                        "images": ["special.png"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fail_if_started(*args, **kwargs):
        raise AssertionError("crawler must not start for a complete manifest page")

    monkeypatch.setattr(
        "umamusume_web_crawler.web.biligame_assets.AsyncWebCrawler",
        fail_if_started,
    )
    summary = await crawl_biligame_character_assets(
        [
            CharacterAssetTarget(
                page_title="特别周",
                name_cn="特别周",
                name_en="Special Week",
                character_id="1001",
                costume_id="100101",
            )
        ],
        image_output_root=image_root,
        skip_audio=True,
        verbose=False,
    )

    assert summary["page_skipped"] == 1
    assert summary["success"] == 1


@pytest.mark.asyncio
async def test_image_manifest_does_not_skip_audio_crawl(tmp_path, monkeypatch) -> None:
    image_root = tmp_path / "images"
    image_dir = image_root / "Special Week"
    image_dir.mkdir(parents=True)
    (image_dir / "special.png").write_bytes(b"image")
    manifest = image_root / ".biligame_asset_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pages": {
                    "特别周": {
                        "name_en": "Special Week",
                        "images": ["special.png"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakeCrawler:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    mock_process = AsyncMock(
        return_value={
            "cn": "特别周",
            "en": "Special Week",
            "wiki_title": "特别周",
            "success": True,
            "audio_unique": 1,
            "audio_downloaded": 1,
            "audio_skipped": 0,
            "image_unique": 1,
            "image_downloaded": 0,
            "image_skipped": 1,
            "image_files": ["special.png"],
        }
    )
    monkeypatch.setattr(
        "umamusume_web_crawler.web.biligame_assets.AsyncWebCrawler", FakeCrawler
    )
    monkeypatch.setattr(
        "umamusume_web_crawler.web.biligame_assets.process_character_assets",
        mock_process,
    )

    summary = await crawl_biligame_character_assets(
        {"特别周": "Special Week"},
        image_output_root=image_root,
        skip_audio=False,
        verbose=False,
        page_delay=0,
    )

    assert summary["page_skipped"] == 0
    assert summary["audio_downloaded"] == 1
    mock_process.assert_awaited_once()


@pytest.mark.asyncio
async def test_trusted_existing_base_directory_bootstraps_manifest(
    tmp_path, monkeypatch
) -> None:
    image_root = tmp_path / "images"
    image_dir = image_root / "Tokai Teio"
    image_dir.mkdir(parents=True)
    (image_dir / "Jsf_100301.png").write_bytes(b"image")

    def fail_if_started(*args, **kwargs):
        raise AssertionError("crawler must not start for a trusted existing directory")

    monkeypatch.setattr(
        "umamusume_web_crawler.web.biligame_assets.AsyncWebCrawler",
        fail_if_started,
    )
    summary = await crawl_biligame_character_assets(
        [
            CharacterAssetTarget(
                page_title="东海帝皇",
                name_cn="东海帝皇",
                name_en="Tokai Teio",
                character_id="1003",
                costume_id="100301",
            )
        ],
        image_output_root=image_root,
        skip_audio=True,
        trust_existing_character_dirs=True,
        verbose=False,
    )

    manifest = json.loads(
        (image_root / ".biligame_asset_manifest.json").read_text(encoding="utf-8")
    )
    assert summary["page_skipped"] == 1
    assert manifest["pages"]["东海帝皇"]["images"] == ["Jsf_100301.png"]


@pytest.mark.asyncio
async def test_cli_routes_biligame_assets_task(monkeypatch) -> None:
    mock_crawl = AsyncMock(return_value={"total": 1, "success": 1})
    monkeypatch.setattr(cli, "crawl_biligame_character_assets", mock_crawl)

    args = Namespace(
        task="biligame-assets",
        url=None,
        mode="auto",
        visual=False,
        output="results/crawl.md",
        visual_dir="results/visual",
        use_proxy=False,
        no_proxy=True,
        print_scale=None,
        headless=False,
        capture_pdf=False,
        no_capture_pdf=False,
        google_api_key=None,
        google_cse_id=None,
        audio_output="results/voicedata",
        image_output="results/imagedata/characters",
        skip_images=False,
        skip_audio=False,
        character=["特别周"],
        name=["Special Week"],
        dump_html=None,
        characters_json="umamusume_characters.json",
        request_delay=0.2,
        page_delay=0.5,
        concurrency=4,
        asset_summary_output=None,
        asset_quiet=True,
    )

    await cli._run(args)

    mock_crawl.assert_awaited_once()
    called_targets = mock_crawl.await_args.args[0]
    assert called_targets == {"特别周": "Special Week"}
    assert mock_crawl.await_args.kwargs["use_proxy"] is False
