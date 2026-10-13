"""Download only Bwiki's interactive chibi PNGs, including costume variants.

Resolve rendered page references instead of guessing resource costume IDs.
The manifest checkpoints each verified image so an interrupted run can resume.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from filelock import FileLock
from PIL import Image

from umamusume_web_crawler.web.biligame import DEFAULT_API_ENDPOINT, fetch_biligame_html
from umamusume_web_crawler.web.character_targets import (
    DEFAULT_CHARACTERS_JSON, CharacterAssetTarget, load_asset_targets_from_json,
)
from umamusume_web_crawler.web.http import SourceError, request_bytes, request_json
from umamusume_web_crawler.web.wiki_urls import wiki_url

DEFAULT_CHIBI_OUTPUT = "results/biligame_chibi"
DEFAULT_CHIBI_REQUEST_DELAY = 5.0
DEFAULT_CHIBI_PAGE_DELAY = 10.0
MANIFEST_NAME = ".chibi_manifest.json"
_FILE_PATTERN = re.compile(r"Petit[ _]chr[ _](\d+)[ _](\d+)[ _](\d{4})\.png", re.I)
_REQUIRED_POSES = {"0010", "0011"}
_MAX_IMAGE_BYTES = 8_000_000


def load_chibi_targets(
    characters_json: str | Path = DEFAULT_CHARACTERS_JSON,
    *, characters: Sequence[str] | None = None, base_only: bool = False,
) -> list[CharacterAssetTarget]:
    """Select indexed roles by exact Chinese/English name or character ID."""
    targets = load_asset_targets_from_json(characters_json, include_variants=True)
    if not targets or any(
        not re.fullmatch(r"\d+", t.character_id or "")
        or not re.fullmatch(r"\d+", t.costume_id or "") for t in targets
    ):
        raise ValueError("Chibi downloads require a schema-v2 index with character/costume IDs.")
    if characters:
        selected = {value.strip().casefold() for value in characters}
        aliases = {alias.casefold() for t in targets for alias in (
            t.name_cn, t.name_en, t.character_id or "",
        )}
        unknown = selected - aliases
        if unknown:
            raise ValueError(f"Unknown characters in index: {', '.join(sorted(unknown))}")
        targets = [t for t in targets if selected.intersection({
            t.name_cn.casefold(), t.name_en.casefold(), (t.character_id or "").casefold(),
        })]
    if base_only:
        targets = [t for t in targets if t.is_base]
    keys = [(t.character_id, t.costume_id) for t in targets]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate character/costume IDs in index.")
    if not targets:
        raise ValueError("No matching costume pages in index.")
    return targets


def _file_parts(value: str) -> tuple[str, str, str] | None:
    name = unquote(value).rsplit(":", 1)[-1]
    match = _FILE_PATTERN.fullmatch(name.strip())
    return match.groups() if match else None


def extract_chibi_files(html: str, character_id: str) -> list[dict]:
    """Extract actual original-file identities only inside the Qchar widget."""
    soup = BeautifulSoup(html, "lxml")
    found = {}
    for img in soup.select(".qchar-container .data-container img"):
        link = img.find_parent("a")
        href = str(link.get("href", "")) if link else ""
        parsed = urlparse(href)
        title = parse_qs(parsed.query).get("title", [unquote(parsed.path.rsplit("/", 1)[-1])])[0]
        parts = _file_parts(title) or _file_parts(str(img.get("alt", "")))
        if not parts:
            continue
        role, resource, pose = parts
        if role != character_id:
            raise SourceError(f"Chibi belongs to character {role}, expected {character_id}.")
        item = {"resource_costume_id": resource, "pose": pose,
                "file_title": f"File:Petit chr {role} {resource} {pose}.png"}
        if pose in found and found[pose] != item:
            raise SourceError(f"Ambiguous chibi resource for pose {pose}.")
        found[pose] = item
    if not found:
        raise SourceError("Page has no usable Qchar image references.")
    if len({item["resource_costume_id"] for item in found.values()}) != 1:
        raise SourceError("Qchar poses refer to different resource costumes.")
    return [found[pose] for pose in sorted(found)]


async def _image_info(files: list[dict], **request_options) -> dict[tuple, dict]:
    url = DEFAULT_API_ENDPOINT + "?" + urlencode({
        "action": "query", "prop": "imageinfo", "iiprop": "url|size|mime|sha1",
        "format": "json", "formatversion": "2",
        "titles": "|".join(item["file_title"] for item in files),
    })
    payload = await asyncio.to_thread(
        request_json, url, referer=urljoin(DEFAULT_API_ENDPOINT, "./"), **request_options,
    )
    pages = payload.get("query", {}).get("pages", [])
    if isinstance(pages, dict):
        pages = pages.values()
    return {
        parts: page["imageinfo"][0]
        for page in pages
        if (parts := _file_parts(page.get("title", ""))) and page.get("imageinfo")
    }


def _safe_component(value: str) -> str:
    return re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", value).strip(" .")[:60] or "unnamed"


def _target_dir(target: CharacterAssetTarget) -> Path:
    label = "原皮" if target.is_base else target.page_title.removesuffix(target.name_cn).strip()
    return Path(f"{target.character_id}_{_safe_component(target.name_cn)}") / (
        f"{target.costume_id}_{_safe_component(label)}"
    )


def _relative_image_path(target: CharacterAssetTarget, resource: str, pose: str) -> Path:
    return _target_dir(target) / f"Petit_chr_{target.character_id}_{resource}_{pose}.png"


def _safe_path(root: Path, relative: Path) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Output path escapes output directory: {relative}")
    return path


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _save_manifest(path: Path, manifest: dict) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(path, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))


def _valid_local_file(root: Path, target: CharacterAssetTarget, item: dict) -> bool:
    parts = _file_parts(str(item.get("file_title", "")))
    if not parts or parts[0] != target.character_id:
        return False
    expected = _relative_image_path(target, parts[1], parts[2])
    if item.get("path") != expected.as_posix():
        return False
    path = _safe_path(root, expected)
    try:
        if not 0 < path.stat().st_size <= _MAX_IMAGE_BYTES:
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == item.get("sha256")
    except OSError:
        return False


def _complete_local_page(root: Path, target: CharacterAssetTarget, entry: dict) -> bool:
    files = entry.get("files", {})
    return (
        entry.get("status") == "complete" and entry.get("page_title") == target.page_title
        and _REQUIRED_POSES <= files.keys()
        and all(_valid_local_file(root, target, item) for item in files.values())
    )


def _validate_png(data: bytes, info: dict) -> dict:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SourceError("Image response is not PNG (possibly an access page).")
    if info.get("size") and len(data) != info["size"]:
        raise SourceError("PNG size does not match MediaWiki imageinfo.")
    source_sha1 = str(info.get("sha1") or "")
    if re.fullmatch(r"[0-9a-fA-F]{40}", source_sha1) and hashlib.sha1(data).hexdigest() != source_sha1.lower():
        raise SourceError("PNG hash does not match MediaWiki imageinfo; retry with refresh_existing.")
    with Image.open(io.BytesIO(data)) as img:
        if img.format != "PNG" or img.width > 4096 or img.height > 4096:
            raise SourceError("Unexpected chibi image format/dimensions.")
        img.verify()
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if (info.get("width"), info.get("height")) != img.size:
            raise SourceError("PNG dimensions do not match MediaWiki imageinfo.")
        return {"width": img.width, "height": img.height, "mode": img.mode,
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _should_stop(exc: Exception) -> bool:
    return isinstance(exc, SourceError) and (
        exc.status in (403, 429, 567) or bool(exc.retry_after)
    )


async def download_biligame_chibi(
    *, characters: Sequence[str] | None = None,
    output_dir: str | Path = DEFAULT_CHIBI_OUTPUT,
    characters_json: str | Path = DEFAULT_CHARACTERS_JSON,
    base_only: bool = False, refresh_existing: bool = False,
    use_proxy: bool | None = None, timeout_s: float = 30,
    request_delay: float = DEFAULT_CHIBI_REQUEST_DELAY,
    page_delay: float = DEFAULT_CHIBI_PAGE_DELAY,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Download indexed base/variant chibis, returning counts and per-page errors.

    No browser is launched. Requests are serial, 5 seconds apart per host by
    default (minimum 2); costume pages wait 10 seconds by default. Completed
    verified pages are skipped unless refresh_existing is set.
    Access/rate-limit errors stop the batch; rerun later to resume.
    """
    if isinstance(characters, str):
        characters = [characters]
    if any(not math.isfinite(v) or v < 0 for v in (request_delay, page_delay)) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("Delays must be finite/nonnegative and timeout must be positive.")
    targets = load_chibi_targets(characters_json, characters=characters, base_only=base_only)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = _safe_path(root, Path(MANIFEST_NAME))
    options = {"use_proxy": use_proxy, "timeout_s": timeout_s,
               "min_interval_s": max(2, request_delay)}
    api_options = {**options, "cache_ttl_s": 0 if refresh_existing else 3600}
    summary = {"output_dir": str(root), "manifest": str(manifest_path),
               "pages_total": len(targets), "pages_complete": 0, "pages_skipped": 0,
               "images_downloaded": 0, "images_reused": 0, "errors": [], "stopped": False}
    # FileLock is released by the OS even after interruption; never overwrite
    # another running downloader's checkpoint for the same output directory.
    with FileLock(str(_safe_path(root, Path(".chibi.lock"))), timeout=0):
        manifest = {"schema_version": 1, "pages": {}}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("pages"), dict):
                raise ValueError(f"Invalid chibi manifest: {manifest_path}")
        visited_page = False
        for target in targets:
            key = f"{target.character_id}:{target.costume_id}"
            old = manifest["pages"].get(key, {})
            if not refresh_existing and _complete_local_page(root, target, old):
                summary["pages_skipped"] += 1
                summary["pages_complete"] += 1
                if progress:
                    progress(f"[skip] {target.page_title}")
                continue
            if visited_page and page_delay:
                await asyncio.sleep(page_delay)
            visited_page = True
            if progress:
                progress(f"[fetch] {target.page_title}")
            entry = {**asdict(target), "source_page": wiki_url("biligame", target.page_title),
                     "status": "partial", "stage": "page_html",
                     "files": dict(old.get("files", {})), "errors": []}
            manifest["pages"][key] = entry
            # Persist in-progress before any await/download; cancellation never
            # leaves an old 'complete' checkpoint for a partly refreshed page.
            _save_manifest(manifest_path, manifest)
            try:
                html = await fetch_biligame_html(target.page_title, **api_options)
                files = extract_chibi_files(html, target.character_id)
                entry["resource_costume_id"] = files[0]["resource_costume_id"]
                entry["stage"] = "image_info"
                infos = await _image_info(files, **api_options)
                active_poses = {item["pose"] for item in files}
                entry["files"] = {pose: item for pose, item in entry["files"].items() if pose in active_poses}
                for file in files:
                    pose = file["pose"]
                    entry["stage"] = f"image_download:{pose}"
                    parts = _file_parts(file["file_title"])
                    info = infos.get(parts)
                    try:
                        if not info:
                            raise SourceError(f"Missing original file: {file['file_title']}")
                        url = info.get("url", "")
                        parsed = urlparse(url)
                        if parsed.scheme != "https" or parsed.hostname != "patchwiki.biligame.com" or info.get("mime") != "image/png":
                            raise SourceError(f"Unexpected image source/type: {url}")
                        previous = entry["files"].get(pose, {})
                        same_source = (
                            previous.get("file_title") == file["file_title"]
                            and previous.get("url") == url
                            and previous.get("source_sha1") == info.get("sha1")
                            and (not refresh_existing or bool(info.get("sha1")))
                        )
                        if same_source and _valid_local_file(root, target, previous):
                            summary["images_reused"] += 1
                            continue
                        data = await asyncio.to_thread(
                            request_bytes, url, **options, referer=entry["source_page"],
                            max_bytes=_MAX_IMAGE_BYTES,
                        )
                        metadata = _validate_png(data, info)
                        relative = _relative_image_path(target, file["resource_costume_id"], pose)
                        _atomic_write(_safe_path(root, relative), data)
                        entry["files"][pose] = {**file, **metadata, "path": relative.as_posix(),
                                                 "url": url, "source_sha1": info.get("sha1")}
                        summary["images_downloaded"] += 1
                        _save_manifest(manifest_path, manifest)
                    except (OSError, ValueError, RuntimeError) as exc:
                        if _should_stop(exc):
                            raise
                        entry["errors"].append(f"{pose}: {exc}")
                missing = _REQUIRED_POSES - active_poses
                if missing:
                    entry["errors"].append(f"Page is missing required poses: {', '.join(sorted(missing))}")
                if not entry["errors"]:
                    entry["status"] = "complete"
                    entry["stage"] = "complete"
                    summary["pages_complete"] += 1
            except (OSError, ValueError, RuntimeError) as exc:
                entry["errors"].append(str(exc))
                summary["stopped"] = _should_stop(exc)
                if isinstance(exc, SourceError):
                    entry["http_error"] = {"status": exc.status, "retry_after": exc.retry_after,
                                           "response_headers": exc.response_headers}
            _save_manifest(manifest_path, manifest)
            if entry["errors"]:
                summary["errors"].append({
                    "page_title": target.page_title, "stage": entry["stage"],
                    "errors": entry["errors"],
                    **({"http_error": entry["http_error"]} if "http_error" in entry else {}),
                })
                if progress:
                    progress(f"[partial] {target.page_title}: {'; '.join(entry['errors'])}")
            if summary["stopped"]:
                break
    summary["pages_pending"] = len(targets) - summary["pages_complete"]
    return summary
