"""Offline regressions for body loss, table associations and URL identity."""
import json
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from umamusume_web_crawler.web import wiki_pages, wikiru
from umamusume_web_crawler.web.html_content import parse_html_page
from umamusume_web_crawler.web.http import SourceError
from umamusume_web_crawler.web.wiki_urls import normalize_title, wiki_url, detect_site


def parse(html, site='biligame'):
    return parse_html_page(html, title='test', source_url=wiki_url(site, 'test'), site=site)


def test_moegirl_template_and_folded_body_are_preserved():
    page = parse('''<template id="MOE_SKIN_TEMPLATE_BODYCONTENT"><div class="mw-parser-output">
    <h2>资料</h2><table><tr><th>身高</th><td>150cm</td></tr></table>
    <div style="display:none"><h3>台词</h3><p>隐藏的完整台词</p></div>
    <div class="mw-editsection">编辑噪声</div></div></template>''', 'moegirl')
    assert page['infobox']['身高'] == '150cm'
    assert '隐藏的完整台词' in page['markdown']
    assert '编辑噪声' not in page['markdown']


def test_generated_voices_and_cv_column_header():
    page = parse('''<div class="mw-parser-output"><table>
    <tr><th>CV</th><th colspan="3">TAG</th></tr><tr><td>Machico</td><td colspan="3"></td></tr>
    </table><div>生日<div class="voice_text_jp">おめでとう！</div>
    <div class="voice_text_chs" style="display:none">生日快乐！</div></div>
    <table><tr><th>技能</th><th>效果</th></tr><tr><td>技能甲</td><td>速度上升</td></tr></table></div>''')
    assert page['infobox']['CV'] == 'Machico'
    assert '日文：おめでとう！' in page['markdown']
    assert '简中：生日快乐！' in page['markdown']
    assert '| 技能甲 | 速度上升 |' in page['markdown']


def test_wikiru_rowspan_conditions_and_comment_boundary():
    html = '''<div id="body"><h2>基本情報</h2><table>
    <tr><td rowspan="2">portrait</td><th>名前</th><td>テイオー</td></tr>
    <tr><th>CV</th><td>Machico</td></tr></table><div><h2>ボイス</h2>
    <div style="display:none"><table><tr><th>条件</th><th>台詞</th><th>備考</th></tr>
    <tr><td>ホーム</td><td>台詞一</td><td rowspan="2">親愛度3以上</td></tr>
    <tr><td>ホーム</td><td>台詞二</td></tr></table></div>
    <h2>コメントフォーム</h2><p>ユーザー投稿</p></div><p>later comments</p></div>'''
    page = parse(html, 'wikiru')
    assert page['infobox']['名前'] == 'テイオー'
    assert page['infobox']['CV'] == 'Machico'
    assert '| ホーム | 台詞二 | 親愛度3以上 |' in page['markdown']
    assert 'ユーザー投稿' not in page['markdown']
    assert 'later comments' not in page['markdown']


def test_nested_table_and_image_only_information():
    html = '''<div class="mw-parser-output"><table><tr><td>档案</td><td><table>
    <tr><th>身高</th><td>150cm</td></tr></table></td></tr></table>
    <img alt="芝适性A"><a href="/Tokai_Teio/Gallery">Gallery</a></div>'''
    page = parse(html, 'umamusu')
    assert '150cm' in page['markdown']
    assert '芝适性A' in page['markdown']
    assert '(https://umamusu.wiki/Tokai_Teio/Gallery)' in page['markdown']


@pytest.mark.parametrize('html', ['<html>Access denied</html>', '<div class="mw-parser-output"></div>',
                                  '<div class="mw-parser-output"><div class="noarticletext">missing</div></div>'])
def test_access_or_missing_pages_are_not_success(html):
    with pytest.raises(SourceError):
        parse(html)


@pytest.mark.parametrize('site,title', [('umamusu','Tokai Teio/Gallery'), ('biligame','角色/台词'),
                                        ('moegirl','赛马娘:东海帝王'), ('wikiru','トウカイテイオー')])
def test_page_url_roundtrip_preserves_subpages(site, title):
    assert normalize_title(wiki_url(site, title), site).replace('_',' ') == title
    assert detect_site(wiki_url(site, title)) == site


def test_wrong_host_and_wikiru_edit_query_rejected():
    with pytest.raises(ValueError):
        normalize_title('https://umamusume.wikiru.jp/?cmd=edit&page=test', 'wikiru')
    with pytest.raises(ValueError):
        detect_site('https://umamusu.wiki.example.org/test')
    with pytest.raises(ValueError):
        normalize_title('https://wiki.biligame.com/another/test', 'biligame')


@pytest.mark.asyncio
async def test_moegirl_complete_path_uses_public_html(monkeypatch):
    calls=[]
    def fetch(url, **kwargs):
        calls.append(url)
        return '<div class="mw-parser-output"><h2>台词</h2><table><tr><td>全文</td></tr></table></div>'
    monkeypatch.setattr(wiki_pages, 'request_text', fetch)
    page=await wiki_pages.fetch_wiki_page('东海帝王', site='moegirl')
    assert page['transport']=='public_html'
    assert len(calls)==1 and 'api.php' not in calls[0]
    assert '全文' in page['markdown']


@pytest.mark.asyncio
async def test_wikiru_search_and_wrong_page(monkeypatch):
    def fetch(url, **kwargs):
        return '''<h1>FrontPage</h1><div id="body"><h2>一覧</h2><table><tr><td>
        <a href="./?%E3%83%86%E3%82%A4%E3%82%AA%E3%83%BC">テイオー</a>
        <a href="./?cmd=edit&page=テイオー">edit</a>
        <a href="https://example.org/?テイオー">outside</a></td></tr></table></div>'''
    monkeypatch.setattr(wikiru, 'request_text', fetch)
    assert await wikiru.search_wikiru_titles('テイオー') == ['テイオー']
    with pytest.raises(SourceError, match='different'):
        await wikiru.fetch_wikiru_html('テイオー')


def test_mcp_default_never_loads_google_in_fresh_process():
    code = '''import asyncio, json, sys
from umamusume_web_crawler.mcp.server import mcp
names=[t.name for t in asyncio.run(mcp.list_tools())]
assert not any('google' in n for n in names)
assert 'umamusume_web_crawler.web.search' not in sys.modules
assert 'umamusume_web_crawler.mcp.google_tools' not in sys.modules
assert not any(n.startswith('googleapiclient') for n in sys.modules)
assert {'crawl_wikiru_wiki','get_umapyoi_character','get_umapyoi_resources'} <= set(names)
print(json.dumps(names))
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)


@pytest.mark.asyncio
async def test_mcp_structured_result_and_error(monkeypatch):
    from umamusume_web_crawler.web import tools
    from umamusume_web_crawler.mcp.server import mcp
    monkeypatch.setattr(tools, 'fetch_wiki_page', AsyncMock(return_value={
        'markdown':'# full body', 'infobox':{'身高':'150cm'}, 'source_format':'rendered_html'}))
    result = await mcp.call_tool('crawl_wikiru_wiki', {'url':'テイオー'})
    payload = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
    assert payload['result'] == '# full body'
    assert payload['infobox']['身高'] == '150cm'
    monkeypatch.setattr(tools, 'fetch_wiki_page', AsyncMock(side_effect=SourceError('HTTP 567')))
    result = await mcp.call_tool('crawl_biligame_wiki', {'url':'东海帝皇'})
    payload = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
    assert payload['status']=='error' and '567' in payload['message']


def test_wikiru_footnotes_outside_body_exclude_comment_notes():
    page = parse('''<div id="body"><h2>基本情報</h2><p>本文<a href="#notefoot_1">*1</a></p>
    <h2>コメントフォーム</h2><p>投稿<a href="#notefoot_2">*2</a></p></div>
    <div id="note"><a id="notefoot_1" href="#notetext_1">*1</a><span>本文の出典</span><br>
    <a id="notefoot_2" href="#notetext_2">*2</a><span>コメントの出典</span><br></div>''', 'wikiru')
    assert '本文の出典' in page['markdown']
    assert 'コメントの出典' not in page['markdown']
