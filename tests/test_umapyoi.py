from unittest.mock import AsyncMock

import pytest

from umamusume_web_crawler.web import umapyoi
from umamusume_web_crawler.web.http import SourceError


@pytest.mark.asyncio
async def test_search_preserves_game_and_database_ids_and_nulls(monkeypatch):
    rows = [{'id':4550, 'game_id':1003, 'name_en':'Tokai Teio', 'name_jp':'トウカイテイオー'},
            {'id':1, 'game_id':None, 'name_en':'NPC', 'name_jp':'NPC'}]
    monkeypatch.setattr(umapyoi, '_get', AsyncMock(return_value=rows))
    result = await umapyoi.search_umapyoi_characters('1003')
    assert result['results']==[rows[0]]
    assert (await umapyoi.search_umapyoi_characters('npc'))['results'][0]['game_id'] is None
    assert (await umapyoi.search_umapyoi_characters('TOKAI'))['results']==[rows[0]]


@pytest.mark.asyncio
async def test_profile_keeps_missing_fields_and_rejects_wrong_id(monkeypatch):
    monkeypatch.setattr(umapyoi, '_get', AsyncMock(return_value={'game_id':1003,'id':4550,'family_fact':None}))
    result=await umapyoi.fetch_umapyoi_character(1003)
    assert result['profile']['family_fact'] is None
    assert result['missing_fields']==['family_fact']
    with pytest.raises(SourceError, match='mismatched'):
        await umapyoi.fetch_umapyoi_character(4550)
    with pytest.raises(ValueError):
        await umapyoi.fetch_umapyoi_character(0)


@pytest.mark.asyncio
async def test_resources_report_partial_failure_without_downloading_urls(monkeypatch):
    calls=[]
    async def get(path, use_proxy):
        calls.append(path)
        if path=='character/1003':
            return {'game_id':1003,'detail_img_pc':'https://example.org/expired.png'}
        if path.startswith('outfit'):
            return [{'chara_id':1003, 'id':100301}]
        if path.startswith('support'):
            raise SourceError('rate limited')
        return [{'label':'制服','images':[{'image':'https://example.org/a.png'}]}]
    monkeypatch.setattr(umapyoi, '_get', get)
    result=await umapyoi.fetch_umapyoi_resources(1003)
    assert result['partial'] and 'support_cards' in result['errors']
    assert result['url_status']=='unverified'
    assert result['outfits'][0]['id']==100301
    assert all(not path.startswith('https:') for path in calls)


@pytest.mark.asyncio
async def test_missing_profile_stops_resource_queries(monkeypatch):
    get=AsyncMock(side_effect=SourceError('404'))
    monkeypatch.setattr(umapyoi,'_get',get)
    with pytest.raises(SourceError):
        await umapyoi.fetch_umapyoi_resources(999999)
    assert get.await_count==1


@pytest.mark.asyncio
async def test_wrong_resource_identity_is_not_accepted(monkeypatch):
    async def get(path, use_proxy):
        if path=='character/1003': return {'game_id':1003}
        if path.startswith('character/images'): return []
        return [{'chara_id':1129}]
    monkeypatch.setattr(umapyoi,'_get',get)
    result=await umapyoi.fetch_umapyoi_resources(1003)
    assert result['partial'] and set(result['errors'])=={'outfits'}
    assert result['support_cards'][0]['chara_id']==1129
