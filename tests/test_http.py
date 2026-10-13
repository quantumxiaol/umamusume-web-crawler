from email.message import Message
from io import BytesIO
from urllib.request import HTTPSHandler, ProxyHandler
from urllib.response import addinfourl

import pytest

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.http import build_http_opener
from umamusume_web_crawler.web.search import _fetch_google_search_html


def _proxies(opener):
    return next(
        (
            handler.proxies
            for handler in opener.handlers
            if isinstance(handler, ProxyHandler)
        ),
        {},
    )


def test_no_proxy_ignores_config_environment_and_system(monkeypatch):
    monkeypatch.setattr(config, "http_proxy", "http://configured.invalid:8080")
    monkeypatch.setattr(config, "https_proxy", "http://configured.invalid:8080")

    def unexpected_proxy_lookup():
        pytest.fail("Explicit no-proxy must not consult environment/system proxies")

    monkeypatch.setattr("urllib.request.getproxies", unexpected_proxy_lookup)
    assert _proxies(build_http_opener(False)) == {}


@pytest.mark.parametrize("use_proxy", [None, True])
def test_config_proxy_is_preferred_and_updates_are_observed(monkeypatch, use_proxy):
    monkeypatch.setattr(config, "http_proxy", "http://first.invalid:8080")
    monkeypatch.setattr(config, "https_proxy", None)
    monkeypatch.setattr(
        "urllib.request.getproxies", lambda: {"https": "http://system.invalid:8080"}
    )
    assert _proxies(build_http_opener(use_proxy)) == {
        "http": "http://first.invalid:8080",
        "https": "http://first.invalid:8080",
    }
    monkeypatch.setattr(config, "http_proxy", None)
    monkeypatch.setattr(config, "https_proxy", "http://second.invalid:8080")
    assert _proxies(build_http_opener(use_proxy)) == {
        "http": "http://second.invalid:8080",
        "https": "http://second.invalid:8080",
    }


@pytest.mark.parametrize("use_proxy", [None, True])
def test_without_config_urllib_proxy_discovery_is_preserved(monkeypatch, use_proxy):
    monkeypatch.setattr(config, "http_proxy", None)
    monkeypatch.setattr(config, "https_proxy", None)
    monkeypatch.setattr(
        "urllib.request.getproxies", lambda: {"https": "http://system.invalid:8080"}
    )
    assert _proxies(build_http_opener(use_proxy)) == {
        "https": "http://system.invalid:8080"
    }


def test_google_no_proxy_reaches_target_directly(monkeypatch):
    monkeypatch.setattr(config, "http_proxy", None)
    monkeypatch.setattr(config, "https_proxy", None)
    monkeypatch.setattr("urllib.request.proxy_bypass", lambda host: False)
    monkeypatch.setattr(
        "urllib.request.getproxies", lambda: {"https": "http://system.invalid:8080"}
    )
    hosts = []

    def fake_https_open(self, request):
        hosts.append(request.host)
        response = addinfourl(
            BytesIO(b"<html>result</html>"), Message(), request.full_url, 200
        )
        response.msg = "OK"
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", fake_https_open)
    html = _fetch_google_search_html("test", num=1, timeout_s=1, use_proxy=False)
    assert html == "<html>result</html>"
    assert hosts == ["www.google.com"]


@pytest.fixture
def transport(monkeypatch, tmp_path):
    from umamusume_web_crawler.web import http
    monkeypatch.setenv('CRAWLER_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(http, '_last_request', {})
    monkeypatch.setattr(http, '_blocked_until', {})
    return http


def test_cache_hit_and_project_user_agent(transport, monkeypatch):
    from unittest.mock import Mock
    opener = Mock()
    response = addinfourl(BytesIO(b'{"result":42}'), Message(), 'https://wiki.test/api', 200)
    opener.open.return_value = response
    monkeypatch.setattr(transport, 'build_http_opener', lambda use_proxy: opener)
    assert transport.request_json('https://wiki.test/api', min_interval_s=0,
                                  referer='https://wiki.test/') == {'result':42}
    assert transport.request_json('https://wiki.test/api', min_interval_s=0,
                                  referer='https://wiki.test/') == {'result':42}
    assert opener.open.call_count == 1
    assert opener.open.call_args.args[0].get_header('User-agent') == config.user_agent
    assert opener.open.call_args.args[0].get_header('Accept') == 'application/json'
    assert opener.open.call_args.args[0].get_header('Referer') == 'https://wiki.test/'


@pytest.mark.parametrize('status', [403,429,567])
def test_rate_limit_has_no_retry_and_cools_down(transport, monkeypatch, status):
    from urllib.error import HTTPError
    from unittest.mock import Mock
    headers=Message(); headers['Retry-After']='120'
    headers['Server']='TencentEdgeOne'; headers['EO-LOG-UUID']='diagnostic-id'
    headers['Set-Cookie']='session=do-not-log'
    opener=Mock(); opener.open.side_effect=HTTPError('https://wiki.test/api',status,'blocked',headers,None)
    monkeypatch.setattr(transport,'build_http_opener',lambda use_proxy: opener)
    with pytest.raises(transport.SourceError, match=str(status)) as caught:
        transport.request_text('https://wiki.test/api',min_interval_s=0)
    assert caught.value.response_headers == {
        'Server': 'TencentEdgeOne', 'EO-LOG-UUID': 'diagnostic-id', 'Retry-After': '120',
    }
    assert 'diagnostic-id' in str(caught.value) and 'do-not-log' not in str(caught.value)
    with pytest.raises(transport.SourceError, match='cooling down'):
        transport.request_text('https://wiki.test/another',min_interval_s=0)
    assert opener.open.call_count==1


def test_api_error_with_http_200_is_never_cached(transport, monkeypatch, tmp_path):
    from unittest.mock import Mock
    opener=Mock()
    opener.open.return_value=addinfourl(BytesIO(b'{"error":{"code":"action-notallowed"}}'),Message(),'https://wiki.test/api',200)
    monkeypatch.setattr(transport,'build_http_opener',lambda use_proxy: opener)
    with pytest.raises(transport.SourceError, match='action-notallowed'):
        transport.request_json('https://wiki.test/api',min_interval_s=0)
    assert not list(tmp_path.glob('*.json'))


def test_success_retry_after_header_does_not_trigger_retry(transport, monkeypatch):
    from unittest.mock import Mock
    headers=Message(); headers['Retry-After']='60'
    opener=Mock()
    opener.open.return_value=addinfourl(BytesIO(b'[]'),headers,'https://umapyoi.test/api',200)
    monkeypatch.setattr(transport,'build_http_opener',lambda use_proxy: opener)
    assert transport.request_json('https://umapyoi.test/api',min_interval_s=0)==[]
    assert opener.open.call_count==1


def test_binary_transport_bounds_body_and_sets_project_headers(transport, monkeypatch):
    from unittest.mock import Mock
    opener = Mock()
    opener.open.return_value = addinfourl(BytesIO(b'12345'), Message(), 'https://wiki.test/a.png', 200)
    monkeypatch.setattr(transport, 'build_http_opener', lambda use_proxy: opener)
    with pytest.raises(transport.SourceError, match='exceeds'):
        transport.request_bytes('https://wiki.test/a.png', max_bytes=4, min_interval_s=0,
                                referer='https://wiki.test/source')
    request = opener.open.call_args.args[0]
    assert request.get_header('User-agent') == config.user_agent
    assert request.get_header('Referer') == 'https://wiki.test/source'


def test_binary_and_text_share_host_cooldown(transport, monkeypatch):
    from urllib.error import HTTPError
    from unittest.mock import Mock
    opener = Mock()
    headers = Message(); headers['Retry-After'] = '120'
    opener.open.side_effect = HTTPError('https://wiki.test/image.png', 503, 'wait', headers, None)
    monkeypatch.setattr(transport, 'build_http_opener', lambda use_proxy: opener)
    with pytest.raises(transport.SourceError, match='503'):
        transport.request_bytes('https://wiki.test/image.png', min_interval_s=0)
    with pytest.raises(transport.SourceError, match='cooling down'):
        transport.request_text('https://wiki.test/api', min_interval_s=0)
    assert opener.open.call_count == 1


def test_incomplete_binary_transfer_retries_once(transport, monkeypatch):
    from http.client import IncompleteRead
    from unittest.mock import Mock
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.side_effect = [IncompleteRead(b'partial', 10), b'complete']
    opener = Mock(); opener.open.return_value = response
    monkeypatch.setattr(transport, 'build_http_opener', lambda use_proxy: opener)
    monkeypatch.setattr(transport.time, 'sleep', lambda seconds: None)
    assert transport.request_bytes('https://wiki.test/image.png', min_interval_s=0) == b'complete'
    assert opener.open.call_count == 2
