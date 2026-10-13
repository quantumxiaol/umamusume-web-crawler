import asyncio
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest
from filelock import FileLock, Timeout
from PIL import Image

from umamusume_web_crawler.web import biligame_chibi as chibi
from umamusume_web_crawler.web.http import SourceError


def png(color="red"):
    stream = io.BytesIO()
    Image.new("RGBA", (2, 2), color).save(stream, format="PNG")
    return stream.getvalue()


def widget(resource="100430", character="1004", poses=("0010", "0011")):
    images = "".join(
        f'<a href="/umamusume/文件:Petit_chr_{character}_{resource}_{pose}.png">'
        f'<img src="https://patchwiki.biligame.com/thumbnail.png"></a>'
        for pose in poses
    )
    return f'<div class="qchar-container"><div class="data-container"><pre>{images}</pre></div></div>'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"schema_version": 2, "characters": [{
        "id": "1004", "name_cn": "丸善斯基", "name_en": "Maruzensky", "implemented": True,
        "wiki_title": "丸善斯基", "variants": [
            {"costume_id": "100401", "wiki_title": "丸善斯基", "is_base": True},
            {"costume_id": "100402", "wiki_title": "【夏日】丸善斯基", "is_base": False},
        ],
    }]}), encoding="utf-8")
    state = {"data": png(), "sha1": "version1", "missing": set()}
    page = AsyncMock(side_effect=lambda title, **kw: widget("100401" if title == "丸善斯基" else "100430"))
    monkeypatch.setattr(chibi, "fetch_biligame_html", page)

    def info(url, **kwargs):
        assert kwargs["referer"] == "https://wiki.biligame.com/umamusume/"
        query = parse_qs(urlparse(url).query)
        assert query["prop"] == ["imageinfo"]
        pages = []
        for title in query["titles"][0].split("|"):
            pose = title.rsplit(" ", 1)[-1].removesuffix(".png")
            original = "https://patchwiki.biligame.com/original/" + title.replace(" ", "_")
            pages.append({"title": title.replace("File:", "文件:"), "imageinfo": [] if pose in state["missing"] else [{
                "url": original, "size": len(state["data"]), "width": 2, "height": 2,
                "mime": "image/png", "sha1": state["sha1"],
            }]})
        return {"query": {"pages": pages}}

    api = Mock(side_effect=info)
    binary = Mock(side_effect=lambda *args, **kw: state["data"])
    monkeypatch.setattr(chibi, "request_json", api)
    monkeypatch.setattr(chibi, "request_bytes", binary)
    root = tmp_path / "images"

    async def run(**kwargs):
        return await chibi.download_biligame_chibi(
            output_dir=root, characters_json=index, page_delay=0, **kwargs,
        )

    return run, root, index, page, api, binary, state


def test_only_qchar_and_actual_resource_mapping():
    html = '<img alt="Petit chr 9999 999901 0010.png">' + widget()
    files = chibi.extract_chibi_files(html, "1004")
    assert [item["resource_costume_id"] for item in files] == ["100430", "100430"]
    with pytest.raises(SourceError, match="expected 1004"):
        chibi.extract_chibi_files(widget(character="1003"), "1004")
    with pytest.raises(SourceError, match="Ambiguous"):
        chibi.extract_chibi_files(widget() + widget("100410"), "1004")


def test_index_selection_and_base_only(setup):
    _, _, index, *_ = setup
    assert len(chibi.load_chibi_targets(index, characters=["maruzensky"])) == 2
    base = chibi.load_chibi_targets(index, characters=["1004"], base_only=True)
    assert [t.costume_id for t in base] == ["100401"]
    with pytest.raises(ValueError, match="Unknown characters"):
        chibi.load_chibi_targets(index, characters=["typo"])


@pytest.mark.asyncio
async def test_costumes_original_pngs_and_offline_resume(setup):
    run, root, _, page, api, binary, _ = setup
    result = await run(characters=["丸善斯基"])
    assert result["pages_complete"] == 2 and result["images_downloaded"] == 4
    assert not result["errors"]
    manifest = json.loads((root / chibi.MANIFEST_NAME).read_text())
    variant = manifest["pages"]["1004:100402"]
    assert variant["costume_id"] == "100402"
    assert variant["resource_costume_id"] == "100430" and not variant["is_base"]
    item = variant["files"]["0010"]
    assert item["path"] == "1004_丸善斯基/100402_【夏日】/Petit_chr_1004_100430_0010.png"
    assert "original" in item["url"]
    assert not list(root.rglob("*.html")) and not list(root.rglob("*.part"))
    page.reset_mock(); api.reset_mock(); binary.reset_mock()
    result = await run()
    assert result["pages_skipped"] == 2
    page.assert_not_called(); api.assert_not_called(); binary.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["delete", "corrupt"])
async def test_resume_repairs_only_missing_or_corrupt_png(setup, damage):
    run, root, _, page, _, binary, _ = setup
    await run()
    path = next(root.glob("*/100402_*/*0011.png"))
    path.unlink() if damage == "delete" else path.write_bytes(b"bad data")
    page.reset_mock(); binary.reset_mock()
    result = await run()
    assert result["pages_skipped"] == 1
    assert result["images_downloaded"] == 1 and result["images_reused"] == 1
    assert binary.call_count == 1 and page.await_count == 1
    assert path.read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_refresh_checks_source_hash_and_preserves_old_png_on_bad_response(setup):
    run, root, _, page, api, binary, state = setup
    await run(base_only=True)
    original = {p: p.read_bytes() for p in root.rglob("*.png")}
    binary.reset_mock()
    result = await run(base_only=True, refresh_existing=True)
    assert result["images_reused"] == 2 and binary.call_count == 0
    assert page.call_args.kwargs["cache_ttl_s"] == api.call_args.kwargs["cache_ttl_s"] == 0
    state["sha1"] = "version2"
    state["data"] = b"<html>access challenge</html>"
    result = await run(base_only=True, refresh_existing=True)
    assert result["pages_pending"] == 1 and len(result["errors"]) == 1
    assert all(p.read_bytes() == data for p, data in original.items())
    state["data"] = png("blue")
    result = await run(base_only=True, refresh_existing=True)
    assert result["images_downloaded"] == 2 and result["pages_pending"] == 0


@pytest.mark.asyncio
async def test_missing_original_is_partial_then_retried(setup):
    run, root, _, _, _, binary, state = setup
    state["missing"] = {"0011"}
    result = await run(base_only=True)
    assert result["pages_pending"] == 1 and result["images_downloaded"] == 1
    entry = json.loads((root / chibi.MANIFEST_NAME).read_text())["pages"]["1004:100401"]
    assert entry["status"] == "partial" and "Missing original" in entry["errors"][0]
    state["missing"] = set()
    binary.reset_mock()
    result = await run(base_only=True)
    assert result["pages_complete"] == 1 and result["images_reused"] == 1
    assert binary.call_count == 1


@pytest.mark.asyncio
async def test_missing_widget_pose_does_not_count_as_complete(setup):
    run, _, _, page, *_ = setup
    page.side_effect = None
    page.return_value = widget("100401", poses=("0010",))
    result = await run(base_only=True)
    assert result["images_downloaded"] == 1 and result["pages_complete"] == 0
    assert "0011" in result["errors"][0]["errors"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429, 567, 503])
async def test_access_or_retry_after_stops_before_next_page(setup, status):
    run, root, _, page, _, binary, _ = setup
    binary.side_effect = [png(), SourceError("stop", status=status, retry_after="120")]
    result = await run()
    assert result["stopped"] and result["images_downloaded"] == 1
    assert result["errors"][0]["stage"] == "image_download:0011"
    assert result["errors"][0]["http_error"]["status"] == status
    assert page.await_count == 1 and binary.call_count == 2
    manifest = json.loads((root / chibi.MANIFEST_NAME).read_text())
    assert manifest["pages"]["1004:100401"]["status"] == "partial"


@pytest.mark.asyncio
async def test_cancelled_download_keeps_checkpoint_and_releases_lock(setup):
    run, root, _, _, _, binary, _ = setup
    binary.side_effect = [png(), asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError):
        await run(base_only=True)
    entry = json.loads((root / chibi.MANIFEST_NAME).read_text())["pages"]["1004:100401"]
    assert entry["status"] == "partial" and list(entry["files"]) == ["0010"]
    binary.side_effect = lambda *a, **kw: png()
    result = await run(base_only=True)
    assert result["images_reused"] == result["images_downloaded"] == 1


@pytest.mark.asyncio
async def test_lock_and_invalid_manifest_fail_without_fetching(setup):
    run, root, _, page, *_ = setup
    root.mkdir()
    with FileLock(str(root / ".chibi.lock")):
        with pytest.raises(Timeout):
            await run()
    path = root / chibi.MANIFEST_NAME
    path.write_text("broken JSON")
    with pytest.raises(ValueError):
        await run()
    assert path.read_text() == "broken JSON"
    page.assert_not_called()


@pytest.mark.asyncio
async def test_cli_forwards_selection_output_and_returns_failure(monkeypatch, tmp_path):
    import sys
    from umamusume_web_crawler import cli
    run = AsyncMock(return_value={"pages_pending": 1})
    monkeypatch.setattr(cli, "download_biligame_chibi", run)
    monkeypatch.setattr(sys, "argv", ["crawler", "--task", "biligame-chibi",
                                     "--character", "1004", "--character", "东海帝皇",
                                     "--chibi-output", str(tmp_path), "--base-only", "--no-proxy"])
    with pytest.raises(SystemExit) as exc:
        await cli._run(cli.parse_args())
    assert exc.value.code == 1
    assert run.call_args.kwargs["characters"] == ["1004", "东海帝皇"]
    assert run.call_args.kwargs["output_dir"] == str(tmp_path)
    assert run.call_args.kwargs["base_only"] and run.call_args.kwargs["use_proxy"] is False


def test_valid_png_with_wrong_source_hash_is_rejected():
    import hashlib
    data = png()
    info = {"size": len(data), "width": 2, "height": 2, "sha1": hashlib.sha1(data).hexdigest()}
    assert chibi._validate_png(data, info)["width"] == 2
    info["sha1"] = "0" * 40
    with pytest.raises(SourceError, match="hash does not match"):
        chibi._validate_png(data, info)


@pytest.mark.asyncio
async def test_biligame_page_api_sets_same_wiki_referer(monkeypatch):
    from umamusume_web_crawler.web import biligame
    request = Mock(return_value={"parse": {"text": widget()}})
    monkeypatch.setattr(biligame, "_request_json", request)
    await biligame.fetch_biligame_html("特别周", use_proxy=False)
    assert request.call_args.kwargs["referer"] == "https://wiki.biligame.com/umamusume/"
    assert request.call_args.kwargs["use_proxy"] is False


@pytest.mark.asyncio
async def test_page_block_records_phase_and_edge_request_id(setup):
    run, root, _, page, api, binary, _ = setup
    headers = {"Server": "TencentEdgeOne", "EO-LOG-UUID": "sample-id"}
    page.side_effect = SourceError("blocked", status=567, response_headers=headers)
    result = await run()
    assert result["stopped"] and result["errors"][0]["stage"] == "page_html"
    assert result["errors"][0]["http_error"]["response_headers"] == headers
    entry = json.loads((root / chibi.MANIFEST_NAME).read_text())["pages"]["1004:100401"]
    assert entry["http_error"]["response_headers"]["EO-LOG-UUID"] == "sample-id"
    api.assert_not_called(); binary.assert_not_called()
