"""Exercise the skill CLI with package clients stubbed to avoid network requests."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from umamusume_web_crawler.web import umamusu_wiki


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_category_download_json_progress_and_exit_status(tmp_path, monkeypatch, capsys, failure):
    script = Path(__file__).resolve().parents[1] / "skills/umamusume-wiki-crawler/scripts/crawl.py"
    spec = importlib.util.spec_from_file_location("skill_crawl", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "tqdm", None)

    existing = tmp_path / "existing.png"
    existing.write_bytes(b"saved")
    titles = ["File:existing.png", "File:new.png"]
    listing = AsyncMock(return_value=titles, side_effect=RuntimeError("HTTP 567") if failure else None)
    monkeypatch.setattr(umamusu_wiki, "list_umamusu_category_files", listing)

    async def image_info(title, **kwargs):
        assert kwargs["use_proxy"] is False
        return {"title": title, "url": "https://example.test/" + title.split(":")[1]}

    def image_bytes(url, **kwargs):
        assert url.endswith("/new.png")
        assert kwargs["use_proxy"] is False
        return b"new image"

    monkeypatch.setattr(umamusu_wiki, "fetch_umamusu_image_info", image_info)
    monkeypatch.setattr(umamusu_wiki, "_request_bytes", image_bytes)
    monkeypatch.setattr(sys, "argv", [
        str(script), "download_umamusu_category_images", "Category:Example",
        "--output-dir", str(tmp_path), "--max-files", "2", "--delay", "0", "--no-proxy",
    ])
    code = await cli._run(cli.parse_args())
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert existing.read_bytes() == b"saved"
    assert listing.call_args.kwargs["max_files"] == 2
    assert listing.call_args.kwargs["delay_s"] == 0
    assert listing.call_args.kwargs["use_proxy"] is False
    if failure:
        assert code == 1
        assert payload == {"status": "error", "message": "HTTP 567"}
        assert not (tmp_path / "new.png").exists()
    else:
        assert code == 0
        assert payload["status"] == "success"
        assert payload["count"] == 2
        assert [item["skipped"] for item in payload["downloaded"]] == [True, False]
        assert (tmp_path / "new.png").read_bytes() == b"new image"
        assert "[progress] 2/2" in captured.err
