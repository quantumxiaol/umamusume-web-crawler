"""Umapyoi supplemental profiles and resource indices; preserve source values."""
from __future__ import annotations

import asyncio

from .http import SourceError, request_json

BASE_URL = 'https://umapyoi.net/api/v1/'


async def _get(path: str, use_proxy: bool | None):
    return await asyncio.to_thread(request_json, BASE_URL + path,
                                   use_proxy=use_proxy, cache_ttl_s=86400)


def _game_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('game_id must be a positive game ID, not the Umapyoi database id.')
    return value


def _records(value, endpoint: str) -> list[dict]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SourceError(f'Umapyoi {endpoint} returned an invalid record list.')
    return value


async def search_umapyoi_characters(keyword: str, *, limit: int = 5,
                                     use_proxy: bool | None = None) -> dict:
    if not keyword.strip() or not 1 <= limit <= 50:
        raise ValueError('Provide a keyword and a limit between 1 and 50.')
    rows = _records(await _get('character/list', use_proxy), 'character/list')
    key = keyword.strip().casefold()
    results = [row for row in rows if any(
        key in str(row.get(field) or '').casefold()
        for field in ('name_jp', 'name_en')) or str(row.get('game_id')) == key]
    results.sort(key=lambda row: not any(
        str(row.get(field) or '').casefold() == key
        for field in ('name_jp', 'name_en', 'game_id')))
    return {'source_url': BASE_URL + 'character/list', 'results': results[:limit]}


async def fetch_umapyoi_character(game_id: int, *, use_proxy: bool | None = None) -> dict:
    game_id = _game_id(game_id)
    path = f'character/{game_id}'
    profile = await _get(path, use_proxy)
    if not isinstance(profile, dict) or profile.get('game_id') != game_id:
        raise SourceError('Umapyoi returned an invalid or mismatched character profile.')
    return {'source_url': BASE_URL + path, 'game_id': game_id, 'profile': profile,
            'missing_fields': [key for key, value in profile.items() if value is None or value == ''],
            'usage': 'Supplemental source values; not automatically merged into wiki profiles.'}


async def fetch_umapyoi_resources(game_id: int, *, use_proxy: bool | None = None) -> dict:
    game_id = _game_id(game_id)
    # Validate identity before querying resource collections; a nonexistent character
    # must not look like a valid character with empty collections.
    profile = await fetch_umapyoi_character(game_id, use_proxy=use_proxy)
    groups, errors, sources = {}, {}, {'profile': profile['source_url']}
    for kind, path in (
        ('outfits', f'outfit/character/{game_id}'),
        ('support_cards', f'support/character/{game_id}'),
        ('images', f'character/images/{game_id}'),
    ):
        sources[kind] = BASE_URL + path
        try:
            rows = _records(await _get(path, use_proxy), path)
            # Support results also contain group cards whose primary chara_id
            # belongs to another member. Keep that source relationship intact.
            if kind == 'outfits' and any(row.get('chara_id') != game_id for row in rows):
                raise SourceError(f'Umapyoi {kind} contains a mismatched character ID.')
            if kind == 'images' and any(not isinstance(row.get('images'), list) for row in rows):
                raise SourceError('Umapyoi returned invalid image groups.')
            groups[kind] = rows
        except SourceError as exc:
            errors[kind] = str(exc)
    if not groups:
        raise SourceError(f'All Umapyoi resource collections failed: {errors}')
    return {'game_id': game_id, 'sources': sources, **groups, 'errors': errors,
            'partial': bool(errors), 'url_status': 'unverified',
            'profile_resources': {key: value for key, value in profile['profile'].items()
                                  if isinstance(value, str) and value.startswith(('https://', 'http://'))},
            'usage': 'Resource index only. URLs may expire; no files have been downloaded. Support results may include group cards with another primary chara_id.'}
