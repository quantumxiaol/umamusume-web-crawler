from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup, Tag

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.biligame import fetch_biligame_html


BILIGAME_INDEX_TITLE = "赛马娘一览"
BILIGAME_INDEX_URL = (
    "https://wiki.biligame.com/umamusume/"
    "%E8%B5%9B%E9%A9%AC%E5%A8%98%E4%B8%80%E8%A7%88"
)
OFFICIAL_CHARACTER_URL = "https://umamusume.jp/character/"
DEFAULT_NAME_OVERRIDES = "character_name_overrides.json"
INDEX_SCHEMA_VERSION = 2

_ICON_PATTERN = re.compile(r"^Chr icon (\d+) (\d+) 01\.png$")
_COSTUME_PREFIX_PATTERN = re.compile(r"^[【〖][^】〗]+[】〗]\s*")
_KANA_PATTERN = re.compile(r"[\u3040-\u30ff]")
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_REAL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def strip_costume_prefix(value: str) -> str:
    return _COSTUME_PREFIX_PATTERN.sub("", value).strip()


def _looks_like_chinese_name(value: str) -> bool:
    return bool(_CJK_PATTERN.search(value)) and not _KANA_PATTERN.search(value)


def _link_title(link: Tag) -> str:
    title = str(link.get("title") or "").strip()
    if title:
        return title
    href = str(link.get("href") or "")
    return unquote(urlparse(href).path.rstrip("/").rsplit("/", 1)[-1]).strip()


def parse_biligame_index(html: str) -> list[dict[str, Any]]:
    """Parse character/costume identifiers and page titles from the Bwiki index."""
    soup = BeautifulSoup(html, "html.parser")
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for image in soup.find_all("img"):
        alt = str(image.get("alt") or "")
        match = _ICON_PATTERN.match(alt)
        if not match:
            continue
        character_id, costume_id = match.groups()
        link = image.find_parent("a")
        if not isinstance(link, Tag):
            continue
        page_title = _link_title(link)
        if not page_title:
            continue

        if character_id not in grouped:
            grouped[character_id] = {
                "character_id": character_id,
                "variants": [],
            }
            order.append(character_id)
        variants = grouped[character_id]["variants"]
        if any(item["costume_id"] == costume_id for item in variants):
            continue
        variants.append(
            {
                "costume_id": costume_id,
                "wiki_title": page_title,
                "label": (
                    page_title[: page_title.find("】") + 1]
                    if page_title.startswith("【") and "】" in page_title
                    else page_title[: page_title.find("〗") + 1]
                    if page_title.startswith("〖") and "〗" in page_title
                    else None
                ),
                "is_base": int(costume_id) == int(character_id) * 100 + 1,
            }
        )

    records: list[dict[str, Any]] = []
    for character_id in order:
        record = grouped[character_id]
        variants = record["variants"]
        base = next((item for item in variants if item["is_base"]), variants[0])
        record["wiki_title"] = base["wiki_title"]
        records.append(record)
    return records


def parse_official_characters(html: str) -> list[dict[str, str]]:
    """Parse only the official Uma Musume roster, excluding staff/NPC article groups."""
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select(".character-index article")
    primary = articles[0] if articles else soup
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in primary.select('a[href^="/character/"]'):
        href = str(link.get("href") or "")
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        en_node = link.select_one(".dt-bg p")
        ja_node = link.select_one("dd p.name")
        if not slug or slug in seen or not en_node or not ja_node:
            continue
        seen.add(slug)
        records.append(
            {
                "official_slug": slug,
                "name_en": en_node.get_text(" ", strip=True),
                "name_ja": ja_node.get_text(" ", strip=True),
            }
        )
    return records


def parse_biligame_names(html: str) -> tuple[str | None, str | None]:
    """Read the canonical Chinese/Japanese names from a Bwiki character table."""
    soup = BeautifulSoup(html, "html.parser")
    for header_row in soup.find_all("tr"):
        headers = [cell.get_text(" ", strip=True) for cell in header_row.find_all(["th", "td"])]
        if "中文名" not in headers or "日文名" not in headers:
            continue
        value_row = header_row.find_next_sibling("tr")
        if not isinstance(value_row, Tag):
            continue
        values = [cell.get_text(" ", strip=True) for cell in value_row.find_all(["th", "td"])]
        if len(values) < len(headers):
            continue
        by_header = dict(zip(headers, values, strict=False))
        return by_header.get("中文名") or None, by_header.get("日文名") or None
    return None, None


def _load_name_records(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("characters"), list):
        return [item for item in data["characters"] if isinstance(item, dict)]
    if isinstance(data, dict):
        return [
            {"name_cn": str(name_cn), "name_en": str(name_en)}
            for name_cn, name_en in data.items()
            if name_cn and name_en
        ]
    raise ValueError("characters json must be a mapping or a schema-v2 index")


def load_name_overrides(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.exists():
        return {}
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("name overrides must be an object mapping cn to en")
    return {str(cn): str(en) for cn, en in data.items() if cn and en}


def _build_opener(use_proxy: bool | None) -> object:
    if use_proxy is False:
        return build_opener(ProxyHandler({}))
    proxy_url = config.proxy_url()
    if not proxy_url:
        return build_opener()
    return build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))


def _request_text(url: str, *, timeout_s: float, use_proxy: bool | None) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": config.user_agent or _REAL_USER_AGENT,
            "Accept-Language": "ja,en;q=0.9,zh-CN;q=0.8",
        },
    )
    opener = _build_opener(use_proxy)
    with opener.open(request, timeout=timeout_s) as response:
        return response.read().decode("utf-8")


async def fetch_official_character_html(
    *, timeout_s: float = 30.0, use_proxy: bool | None = None
) -> str:
    return await asyncio.to_thread(
        _request_text,
        OFFICIAL_CHARACTER_URL,
        timeout_s=timeout_s,
        use_proxy=use_proxy,
    )


def _existing_maps(
    records: list[dict[str, Any]], overrides: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    combined = list(records)
    combined.extend(
        {"name_cn": name_cn, "name_en": name_en}
        for name_cn, name_en in overrides.items()
    )
    by_id: dict[str, dict[str, Any]] = {}
    by_cn: dict[str, dict[str, Any]] = {}
    by_en: dict[str, dict[str, Any]] = {}
    for item in combined:
        name_cn = str(item.get("name_cn") or "").strip()
        name_en = str(item.get("name_en") or "").strip()
        character_id = str(item.get("id") or item.get("character_id") or "").strip()
        if character_id:
            by_id.setdefault(character_id, item)
        if name_cn:
            by_cn.setdefault(name_cn, item)
        if name_en:
            by_en.setdefault(normalize_name(name_en), item)
    return by_id, by_cn, by_en


async def build_character_index(
    *,
    existing_path: str | Path,
    overrides_path: str | Path | None = DEFAULT_NAME_OVERRIDES,
    use_proxy: bool | None = None,
    detail_delay: float = 0.2,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Merge the Bwiki implementation/costume index with the official roster."""
    existing = _load_name_records(existing_path)
    overrides = load_name_overrides(overrides_path)
    by_id, by_cn, by_en = _existing_maps(existing, overrides)

    biligame_html, official_html = await asyncio.gather(
        fetch_biligame_html(BILIGAME_INDEX_TITLE, use_proxy=use_proxy),
        fetch_official_character_html(use_proxy=use_proxy),
    )
    biligame_records = parse_biligame_index(biligame_html)
    official_records = parse_official_characters(official_html)
    official_by_en = {
        normalize_name(item["name_en"]): item for item in official_records
    }
    official_by_ja = {item["name_ja"]: item for item in official_records}

    implemented_by_slug: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, str]] = []

    for raw in biligame_records:
        character_id = raw["character_id"]
        base_title = raw["wiki_title"]
        clean_title = strip_costume_prefix(base_title)
        known = by_id.get(character_id) or by_cn.get(base_title) or by_cn.get(clean_title)
        name_cn = str((known or {}).get("name_cn") or "").strip()
        name_ja = str((known or {}).get("name_ja") or "").strip()
        official = (
            official_by_en.get(normalize_name(str((known or {}).get("name_en") or "")))
            if known
            else None
        )

        if not name_cn and _looks_like_chinese_name(clean_title):
            name_cn = clean_title
            known = by_cn.get(name_cn)
            if known:
                official = official_by_en.get(
                    normalize_name(str(known.get("name_en") or ""))
                )

        if official is None:
            official = official_by_ja.get(clean_title)

        if official is None:
            detail_error: str | None = None
            try:
                detail_html = await fetch_biligame_html(base_title, use_proxy=use_proxy)
                detail_cn, detail_ja = parse_biligame_names(detail_html)
                name_cn = detail_cn or name_cn
                name_ja = detail_ja or name_ja
                if name_ja:
                    official = official_by_ja.get(name_ja)
                if official is None and name_cn in by_cn:
                    known = by_cn[name_cn]
                    official = official_by_en.get(
                        normalize_name(str(known.get("name_en") or ""))
                    )
            except Exception as exc:
                detail_error = str(exc)
            if detail_delay > 0:
                await asyncio.sleep(detail_delay)

        if official is None:
            item = {"source": "biligame", "value": base_title}
            if detail_error:
                item["error"] = detail_error
            unresolved.append(item)
            continue

        stable = by_en.get(normalize_name(official["name_en"])) or known or {}
        name_cn = name_cn or str(stable.get("name_cn") or "").strip()
        if not name_cn:
            unresolved.append({"source": "biligame", "value": base_title})
            continue
        record = {
            "id": character_id,
            "name_cn": name_cn,
            "name_en": str(stable.get("name_en") or official["name_en"]),
            "name_ja": official["name_ja"],
            "official_slug": official["official_slug"],
            "implemented": True,
            "wiki_title": base_title,
            "variants": raw["variants"],
        }
        implemented_by_slug[official["official_slug"]] = record

    characters: list[dict[str, Any]] = []
    for official in official_records:
        implemented = implemented_by_slug.get(official["official_slug"])
        if implemented:
            characters.append(implemented)
            continue
        stable = by_en.get(normalize_name(official["name_en"]))
        if not stable:
            unresolved.append(
                {"source": "official", "value": official["name_en"]}
            )
            continue
        characters.append(
            {
                "id": stable.get("id") or stable.get("character_id"),
                "name_cn": stable["name_cn"],
                "name_en": stable["name_en"],
                "name_ja": official["name_ja"],
                "official_slug": official["official_slug"],
                "implemented": False,
                "wiki_title": None,
                "variants": [],
            }
        )

    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "biligame": BILIGAME_INDEX_URL,
            "official": OFFICIAL_CHARACTER_URL,
        },
        "counts": {
            "characters": len(characters),
            "implemented": sum(bool(item["implemented"]) for item in characters),
            "variants": sum(len(item["variants"]) for item in characters),
            "unresolved": len(unresolved),
        },
        "characters": characters,
    }
    return payload, unresolved


async def update_character_index(
    output_path: str | Path,
    *,
    overrides_path: str | Path | None = DEFAULT_NAME_OVERRIDES,
    use_proxy: bool | None = None,
    detail_delay: float = 0.2,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    payload, unresolved = await build_character_index(
        existing_path=output_path,
        overrides_path=overrides_path,
        use_proxy=use_proxy,
        detail_delay=detail_delay,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    await asyncio.to_thread(path.write_text, text, encoding="utf-8")
    return payload, unresolved
