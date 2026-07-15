from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup, Tag
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, ProxyConfig

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.crawler import SingleProxyRotationStrategy


BASE_URL = "https://wiki.biligame.com/umamusume/"
DEFAULT_AUDIO_OUTPUT_ROOT = "results/voicedata"
DEFAULT_IMAGE_OUTPUT_ROOT = "results/imagedata/characters"
DEFAULT_CHARACTERS_JSON = "umamusume_characters.json"
DEFAULT_ASSET_MANIFEST = ".biligame_asset_manifest.json"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_REAL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class CharacterAssetTarget:
    page_title: str
    name_cn: str
    name_en: str
    character_id: str | None = None
    costume_id: str | None = None
    is_base: bool = True


def _build_opener(use_proxy: bool | None) -> object:
    if use_proxy is False:
        return build_opener(ProxyHandler({}))
    proxy_url = config.proxy_url()
    if not proxy_url:
        return build_opener()
    proxy_handler = ProxyHandler({"http": proxy_url, "https": proxy_url})
    return build_opener(proxy_handler)


def _download_bytes(
    url: str,
    *,
    referer: str,
    timeout_s: float,
    use_proxy: bool | None,
) -> bytes:
    headers = {
        "User-Agent": config.user_agent or _REAL_USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": referer,
    }
    req = Request(url, headers=headers)
    opener = _build_opener(use_proxy)
    with opener.open(req, timeout=timeout_s) as resp:
        return resp.read()


async def download_file(
    url: str,
    filepath: str | Path,
    *,
    use_proxy: bool | None,
    referer: str = "https://wiki.biligame.com/",
    timeout_s: float = 30.0,
) -> None:
    payload = await asyncio.to_thread(
        _download_bytes,
        url,
        referer=referer,
        timeout_s=timeout_s,
        use_proxy=use_proxy,
    )
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, payload)


async def save_text(text: str, filepath: str | Path) -> None:
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, text, encoding="utf-8")


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    return url


def is_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(IMAGE_EXTENSIONS)


def to_original_image_url(url: str) -> str:
    if "/images/umamusume/thumb/" not in url:
        return url
    direct_url = url.replace("/images/umamusume/thumb/", "/images/umamusume/", 1)
    return direct_url.rsplit("/", 1)[0]


def parse_image_srcset(srcset: str) -> str | None:
    best_url = ""
    best_score = -1.0
    for part in srcset.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        fields = chunk.split()
        candidate = normalize_url(fields[0])
        if not candidate:
            continue
        score = 1.0
        if len(fields) > 1:
            descriptor = fields[-1].lower()
            if descriptor.endswith("x"):
                try:
                    score = float(descriptor[:-1])
                except ValueError:
                    score = 1.0
            elif descriptor.endswith("w"):
                try:
                    score = float(descriptor[:-1]) / 100.0
                except ValueError:
                    score = 1.0
        if score >= best_score:
            best_score = score
            best_url = candidate
    return best_url or None


def sanitize_filename(name: str, fallback: str) -> str:
    cleaned = name.strip().replace(" ", "_")
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned or fallback


def extract_media_filename(text: str) -> str | None:
    decoded = unquote(text)
    match = re.search(r"文件:([^#?]+)", decoded)
    if match:
        return match.group(1).strip()
    return None


def choose_image_url(img_node: Tag) -> str | None:
    srcset = img_node.get("srcset")
    if srcset:
        srcset_url = parse_image_srcset(srcset)
        if srcset_url and is_image_url(srcset_url):
            return to_original_image_url(srcset_url)
    for key in ("data-src", "data-original", "src"):
        value = img_node.get(key)
        if not value:
            continue
        candidate = normalize_url(value)
        if is_image_url(candidate):
            return to_original_image_url(candidate)
    return None


def image_size_at_least(img_node: Tag, min_size: int) -> bool:
    width = img_node.get("data-file-width") or img_node.get("width") or "0"
    height = img_node.get("data-file-height") or img_node.get("height") or "0"
    try:
        width_num = int(width)
    except ValueError:
        width_num = 0
    try:
        height_num = int(height)
    except ValueError:
        height_num = 0
    return max(width_num, height_num) >= min_size


def ensure_unique_filename(filename: str, used: set[str]) -> str:
    if filename not in used:
        return filename
    stem, ext = Path(filename).stem, Path(filename).suffix
    suffix = 2
    while True:
        candidate = f"{stem}_{suffix}{ext}"
        if candidate not in used:
            return candidate
        suffix += 1


def build_image_filename(
    img_node: Tag,
    image_url: str,
    fallback_prefix: str,
    index: int,
) -> str:
    name: str | None = None
    parent_link = img_node.find_parent("a")
    if parent_link:
        href = parent_link.get("href") or ""
        name = extract_media_filename(href)
    if not name:
        alt_text = (img_node.get("alt") or "").strip()
        if "." in alt_text:
            name = alt_text
    if not name:
        name = Path(urlparse(image_url).path).name
    if not name:
        name = f"{fallback_prefix}_{index}.png"

    fallback = f"{fallback_prefix}_{index}"
    cleaned = sanitize_filename(name, fallback)
    stem = Path(cleaned).stem
    ext = Path(cleaned).suffix
    if not ext:
        url_ext = Path(urlparse(image_url).path).suffix.lower()
        ext = url_ext if url_ext in IMAGE_EXTENSIONS else ".png"
    return f"{stem}{ext}"


def extract_character_images(soup: BeautifulSoup, char_en_name: str) -> list[tuple[str, str]]:
    image_nodes: list[Tag] = []
    for title_node in soup.select("div.support_card-bt"):
        title = title_node.get_text(strip=True)
        if "立绘" not in title:
            continue
        image_container = title_node.find_next_sibling("div", class_="support_card-bg2")
        if image_container:
            image_nodes.extend(
                [node for node in image_container.select("img") if isinstance(node, Tag)]
            )

    if not image_nodes:
        fallback_nodes = soup.select("a.image[href*='文件:'] img")
        image_nodes.extend(
            [
                node
                for node in fallback_nodes
                if isinstance(node, Tag) and image_size_at_least(node, 240)
            ]
        )

    seen_urls: set[str] = set()
    used_names: set[str] = set()
    image_items: list[tuple[str, str]] = []
    for idx, img_node in enumerate(image_nodes, start=1):
        image_url = choose_image_url(img_node)
        if not image_url or image_url in seen_urls:
            continue
        seen_urls.add(image_url)
        filename = build_image_filename(img_node, image_url, char_en_name, idx)
        filename = ensure_unique_filename(filename, used_names)
        used_names.add(filename)
        image_items.append((image_url, filename))
    return image_items


def extract_text_from_row(row: Tag) -> str:
    cells = row.find_all("td")
    candidates: list[str] = []
    for cell in cells:
        if cell.find("div", class_="bikited-audio") or cell.find(
            "div", class_="bikit-audio"
        ):
            continue
        text = cell.get_text(strip=True)
        if text:
            candidates.append(text)
    if not candidates:
        return "no_text"
    return max(candidates, key=len)


def extract_texts_from_container(container: Tag) -> dict[str, str]:
    texts: dict[str, str] = {}
    jp_node = container.find(class_="voice_text_jp")
    if jp_node:
        text = jp_node.get_text(strip=True)
        if text:
            texts["jp"] = text
    chs_node = container.find(class_="voice_text_chs")
    if chs_node:
        text = chs_node.get_text(strip=True)
        if text:
            texts["zh"] = text
    if "zh" not in texts:
        cht_node = container.find(class_="voice_text_cht")
        if cht_node:
            text = cht_node.get_text(strip=True)
            if text:
                texts["zh"] = text
    if texts:
        return texts
    candidates: list[str] = []
    for child in container.find_all(["td", "div"], recursive=False):
        if child.find("div", class_="bikited-audio") or child.find(
            "div", class_="bikit-audio"
        ):
            continue
        text = child.get_text(strip=True)
        if text:
            candidates.append(text)
    if candidates:
        texts["jp"] = max(candidates, key=len)
    return texts


def extract_audio_url(node: Tag) -> str | None:
    for key in ("data-src", "data-url", "data-file", "data-audio", "src"):
        value = node.get(key)
        if value and ".mp3" in value:
            return value
    for value in node.attrs.values():
        if isinstance(value, str) and ".mp3" in value:
            return value
    return None


def extract_text_near_node(node: Tag) -> dict[str, str]:
    for parent in node.parents:
        if not isinstance(parent, Tag):
            continue
        texts = extract_texts_from_container(parent)
        if texts:
            return texts
    row = node.find_parent("tr")
    if isinstance(row, Tag):
        text = extract_text_from_row(row)
        return {"jp": text} if text != "no_text" else {}
    table_like = node.find_parent(
        lambda tag: isinstance(tag, Tag)
        and tag.name == "div"
        and "display: table" in (tag.get("style") or "")
    )
    if isinstance(table_like, Tag):
        return extract_texts_from_container(table_like)
    container = node.find_parent(["li", "div", "td"])
    if isinstance(container, Tag):
        text = container.get_text(strip=True)
        if text:
            return {"jp": text}
    return {}


def load_asset_targets_from_json(
    json_path: str | Path, *, include_variants: bool = False
) -> list[CharacterAssetTarget]:
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("characters"), list):
        targets: list[CharacterAssetTarget] = []
        for item in data["characters"]:
            if not isinstance(item, dict) or not item.get("implemented"):
                continue
            name_cn = str(item.get("name_cn") or "").strip()
            name_en = str(item.get("name_en") or "").strip()
            page_title = str(item.get("wiki_title") or name_cn).strip()
            character_id = str(item.get("id") or "").strip() or None
            variants = item.get("variants")
            if include_variants and isinstance(variants, list):
                for variant in variants:
                    if not isinstance(variant, dict):
                        continue
                    variant_title = str(variant.get("wiki_title") or "").strip()
                    if not variant_title:
                        continue
                    targets.append(
                        CharacterAssetTarget(
                            page_title=variant_title,
                            name_cn=name_cn,
                            name_en=name_en,
                            character_id=character_id,
                            costume_id=str(variant.get("costume_id") or "").strip()
                            or None,
                            is_base=bool(variant.get("is_base")),
                        )
                    )
            elif page_title and name_cn and name_en:
                targets.append(
                    CharacterAssetTarget(
                        page_title=page_title,
                        name_cn=name_cn,
                        name_en=name_en,
                        character_id=character_id,
                    )
                )
        return targets
    if not isinstance(data, dict):
        raise ValueError("characters json must be a mapping or a schema-v2 index")
    return [
        CharacterAssetTarget(
            page_title=str(name_cn),
            name_cn=str(name_cn),
            name_en=str(name_en),
        )
        for name_cn, name_en in data.items()
        if name_cn and name_en
    ]


def load_characters_from_json(json_path: str | Path) -> dict[str, str]:
    return {
        target.page_title: target.name_en
        for target in load_asset_targets_from_json(json_path)
    }


def _coerce_asset_targets(
    targets: Mapping[str, str] | Sequence[CharacterAssetTarget],
) -> list[CharacterAssetTarget]:
    if isinstance(targets, Mapping):
        return [
            CharacterAssetTarget(
                page_title=str(name_cn),
                name_cn=str(name_cn),
                name_en=str(name_en),
            )
            for name_cn, name_en in targets.items()
        ]
    return list(targets)


def load_asset_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        return {"schema_version": 1, "pages": {}}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "pages": {}}
    if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
        return {"schema_version": 1, "pages": {}}
    return data


def manifest_page_is_complete(
    manifest: dict[str, Any],
    target: CharacterAssetTarget,
    image_output_root: str | Path,
) -> bool:
    entry = manifest.get("pages", {}).get(target.page_title)
    if not isinstance(entry, dict) or entry.get("name_en") != target.name_en:
        return False
    filenames = entry.get("images")
    if not isinstance(filenames, list) or not filenames:
        return False
    image_dir = Path(image_output_root) / target.name_en
    return all((image_dir / str(filename)).is_file() for filename in filenames)


def local_character_dir_has_images(
    target: CharacterAssetTarget, image_output_root: str | Path
) -> bool:
    if not target.is_base:
        return False
    image_dir = Path(image_output_root) / target.name_en
    if not image_dir.is_dir():
        return False
    return any(
        path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        for path in image_dir.iterdir()
    )


async def save_asset_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    await asyncio.to_thread(manifest_path.write_text, text, encoding="utf-8")


def _build_browser_config() -> BrowserConfig:
    headers = {
        "User-Agent": _REAL_USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    return BrowserConfig(
        headless=True,
        user_agent=_REAL_USER_AGENT,
        viewport_width=1600,
        viewport_height=900,
        headers=headers,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
        ],
    )


def _build_run_config(use_proxy: bool | None) -> CrawlerRunConfig:
    proxy_url = config.proxy_url()
    proxy = (
        SingleProxyRotationStrategy(ProxyConfig(server=proxy_url))
        if proxy_url and use_proxy is not False
        else None
    )
    return CrawlerRunConfig(
        proxy_rotation_strategy=proxy,
        wait_until="domcontentloaded",
        wait_for="body",
        delay_before_return_html=1.5,
        remove_overlay_elements=True,
        magic=True,
        scan_full_page=True,
        word_count_threshold=1,
        excluded_selector=".ads, .comments, #sidebar, #footer",
    )


async def _crawl_character_html(
    crawler: AsyncWebCrawler,
    *,
    character_name: str,
    use_proxy: bool | None,
) -> str:
    url = f"{BASE_URL}{character_name}"
    result = await crawler.arun(url=url, config=_build_run_config(use_proxy))
    if not result.success or not result.html:
        raise RuntimeError(f"failed to load {character_name}: {url}")
    return str(result.html)


async def process_character_assets(
    crawler: AsyncWebCrawler,
    *,
    char_cn_name: str,
    char_en_name: str,
    page_title: str | None = None,
    audio_output_root: str | Path,
    image_output_root: str | Path,
    dump_html_dir: str | Path | None,
    request_delay: float,
    semaphore: asyncio.Semaphore,
    skip_audio: bool,
    skip_images: bool,
    use_proxy: bool | None,
    verbose: bool,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "cn": char_cn_name,
        "en": char_en_name,
        "wiki_title": page_title or char_cn_name,
        "success": False,
        "audio_candidates": 0,
        "audio_unique": 0,
        "audio_downloaded": 0,
        "audio_skipped": 0,
        "image_candidates": 0,
        "image_unique": 0,
        "image_downloaded": 0,
        "image_skipped": 0,
        "image_files": [],
    }
    html = await _crawl_character_html(
        crawler, character_name=page_title or char_cn_name, use_proxy=use_proxy
    )
    stats["success"] = True

    soup = BeautifulSoup(html, "html.parser")
    if dump_html_dir:
        dump_path = Path(dump_html_dir) / f"{char_en_name}.html"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(dump_path.write_text, html, encoding="utf-8")

    audio_items: list[tuple[str, dict[str, str], str]] = []
    if not skip_audio:
        audio_nodes = soup.select(
            "div.bikit-audio, div.bikited-audio, audio, source, "
            "[data-src], [data-url], [data-file], [data-audio]"
        )
        stats["audio_candidates"] = len(audio_nodes)
        seen_urls: set[str] = set()
        index = 0
        for raw_node in audio_nodes:
            if not isinstance(raw_node, Tag):
                continue
            audio_url = extract_audio_url(raw_node)
            if not audio_url:
                continue
            if audio_url.startswith("//"):
                audio_url = f"https:{audio_url}"
            if audio_url in seen_urls:
                continue
            seen_urls.add(audio_url)
            index += 1
            audio_items.append(
                (
                    audio_url,
                    extract_text_near_node(raw_node),
                    f"{char_en_name}_{index}",
                )
            )
        stats["audio_unique"] = len(audio_items)
        if verbose:
            print(f"[info] {char_cn_name}: found {len(audio_items)} unique audio items")

    image_items: list[tuple[str, str]] = []
    if not skip_images:
        image_items = extract_character_images(soup, char_en_name)
        stats["image_candidates"] = len(image_items)
        stats["image_unique"] = len(image_items)
        stats["image_files"] = [filename for _, filename in image_items]
        if verbose:
            print(f"[info] {char_cn_name}: found {len(image_items)} unique image items")

    async def handle_audio(audio_url: str, texts: dict[str, str], file_basename: str) -> None:
        audio_dir = Path(audio_output_root) / char_en_name
        mp3_path = audio_dir / f"{file_basename}.mp3"
        jp_path = audio_dir / f"{file_basename}_jp.txt"
        zh_path = audio_dir / f"{file_basename}_zh.txt"

        if mp3_path.exists():
            stats["audio_skipped"] += 1
        else:
            async with semaphore:
                if request_delay > 0:
                    await asyncio.sleep(request_delay)
                await download_file(audio_url, mp3_path, use_proxy=use_proxy)
            stats["audio_downloaded"] += 1
        if texts.get("jp") and not jp_path.exists():
            await save_text(texts["jp"], jp_path)
        if texts.get("zh") and not zh_path.exists():
            await save_text(texts["zh"], zh_path)

    async def handle_image(image_url: str, filename: str) -> None:
        image_dir = Path(image_output_root) / char_en_name
        image_path = image_dir / filename
        if image_path.exists():
            stats["image_skipped"] += 1
            return
        async with semaphore:
            if request_delay > 0:
                await asyncio.sleep(request_delay)
            await download_file(image_url, image_path, use_proxy=use_proxy)
        stats["image_downloaded"] += 1

    if audio_items:
        await asyncio.gather(
            *(handle_audio(url, texts, name) for url, texts, name in audio_items)
        )
    if image_items:
        await asyncio.gather(*(handle_image(url, name) for url, name in image_items))
    return stats


async def crawl_biligame_character_assets(
    targets: Mapping[str, str] | Sequence[CharacterAssetTarget],
    *,
    audio_output_root: str | Path = DEFAULT_AUDIO_OUTPUT_ROOT,
    image_output_root: str | Path = DEFAULT_IMAGE_OUTPUT_ROOT,
    dump_html_dir: str | Path | None = None,
    request_delay: float = 0.2,
    page_delay: float = 0.5,
    concurrency: int = 4,
    skip_audio: bool = False,
    skip_images: bool = False,
    use_proxy: bool | None = None,
    verbose: bool = True,
    asset_manifest_path: str | Path | None = None,
    refresh_existing: bool = False,
    trust_existing_character_dirs: bool = False,
) -> dict[str, Any]:
    asset_targets = _coerce_asset_targets(targets)
    if not asset_targets:
        raise ValueError("No biligame characters provided.")
    if concurrency <= 0:
        raise ValueError("concurrency must be greater than 0.")

    semaphore = asyncio.Semaphore(concurrency)
    summary: dict[str, Any] = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "no_audio": 0,
        "no_image": 0,
        "audio_downloaded": 0,
        "audio_skipped": 0,
        "image_downloaded": 0,
        "image_skipped": 0,
        "page_skipped": 0,
        "characters": [],
    }

    manifest_path = (
        Path(asset_manifest_path)
        if asset_manifest_path is not None
        else Path(image_output_root) / DEFAULT_ASSET_MANIFEST
    )
    manifest = load_asset_manifest(manifest_path)
    pending_targets: list[CharacterAssetTarget] = []
    for target in asset_targets:
        summary["total"] += 1
        skip_reason: str | None = None
        if not skip_images and not refresh_existing:
            if manifest_page_is_complete(manifest, target, image_output_root):
                skip_reason = "manifest"
            elif trust_existing_character_dirs and local_character_dir_has_images(
                target, image_output_root
            ):
                skip_reason = "trusted-existing-directory"
                image_dir = Path(image_output_root) / target.name_en
                manifest["pages"][target.page_title] = {
                    "name_cn": target.name_cn,
                    "name_en": target.name_en,
                    "character_id": target.character_id,
                    "costume_id": target.costume_id,
                    "images": sorted(
                        path.name
                        for path in image_dir.iterdir()
                        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                    ),
                }
        if skip_reason:
            summary["success"] += 1
            summary["page_skipped"] += 1
            stats = {
                "cn": target.name_cn,
                "en": target.name_en,
                "wiki_title": target.page_title,
                "success": True,
                "page_skipped": True,
                "skip_reason": skip_reason,
            }
            summary["characters"].append(stats)
            if verbose:
                print(
                    f"[skip-page] {target.page_title} -> {target.name_en} "
                    f"({skip_reason})"
                )
        else:
            pending_targets.append(target)

    if trust_existing_character_dirs:
        await save_asset_manifest(manifest_path, manifest)

    if not pending_targets:
        if verbose:
            print(
                "[summary] total={total} success={success} failed={failed} "
                "page_skipped={page_skipped} image_downloaded={image_downloaded} "
                "image_skipped={image_skipped}".format(**summary)
            )
        return summary

    async with AsyncWebCrawler(config=_build_browser_config(), verbose=False) as crawler:
        for target in pending_targets:
            if verbose:
                print(
                    f"[info] crawling {target.page_title} -> {target.name_en}"
                )
            try:
                stats = await process_character_assets(
                    crawler,
                    char_cn_name=target.name_cn,
                    char_en_name=target.name_en,
                    page_title=target.page_title,
                    audio_output_root=audio_output_root,
                    image_output_root=image_output_root,
                    dump_html_dir=dump_html_dir,
                    request_delay=request_delay,
                    semaphore=semaphore,
                    skip_audio=skip_audio,
                    skip_images=skip_images,
                    use_proxy=use_proxy,
                    verbose=verbose,
                )
            except Exception as exc:
                summary["failed"] += 1
                stats = {
                    "cn": target.name_cn,
                    "en": target.name_en,
                    "wiki_title": target.page_title,
                    "success": False,
                    "error": str(exc),
                }
                if verbose:
                    print(f"[error] {target.page_title}: {exc}")
            else:
                summary["success"] += 1
                if not skip_audio and stats["audio_unique"] == 0:
                    summary["no_audio"] += 1
                if not skip_images and stats["image_unique"] == 0:
                    summary["no_image"] += 1
                summary["audio_downloaded"] += stats["audio_downloaded"]
                summary["audio_skipped"] += stats["audio_skipped"]
                summary["image_downloaded"] += stats["image_downloaded"]
                summary["image_skipped"] += stats["image_skipped"]
                if not skip_images and stats["image_files"]:
                    manifest["pages"][target.page_title] = {
                        "name_cn": target.name_cn,
                        "name_en": target.name_en,
                        "character_id": target.character_id,
                        "costume_id": target.costume_id,
                        "images": stats["image_files"],
                    }
                    await save_asset_manifest(manifest_path, manifest)
            summary["characters"].append(stats)
            if page_delay > 0:
                await asyncio.sleep(page_delay)

    if verbose:
        print(
            "[summary] total={total} success={success} failed={failed} "
            "no_audio={no_audio} no_image={no_image} "
            "page_skipped={page_skipped} "
            "audio_downloaded={audio_downloaded} audio_skipped={audio_skipped} "
            "image_downloaded={image_downloaded} image_skipped={image_skipped}".format(
                **summary
            )
        )
    return summary
