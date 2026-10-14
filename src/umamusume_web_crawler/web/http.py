"""Shared urllib proxy handling and the browser user agent for HTML workflows."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import suppress
from http.client import HTTPException, IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import OpenerDirector, ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup, SoupStrainer

from umamusume_web_crawler.config import config


# MediaWiki API requests use config.user_agent, not this browser identity.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
_ERROR_BODY_LIMIT = 8192
_ERROR_TITLE_LIMIT = 200


def build_http_opener(use_proxy: bool | None = None) -> OpenerDirector:
    """False disables all proxies; otherwise prefer config, then urllib defaults.

    Construct a fresh opener so later config updates take effect. In particular,
    an explicit False must not fall back to environment or system proxies.
    """
    if use_proxy is False:
        return build_opener(ProxyHandler({}))
    proxy_url = config.proxy_url()
    if proxy_url:
        return build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
    return build_opener()


class SourceError(RuntimeError):
    """A source failed; never present an error/challenge page as article content."""

    def __init__(self, message: str, *, status: int | None = None,
                 retry_after: str | None = None,
                 response_headers: dict[str, str] | None = None,
                 error_page_title: str | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.response_headers = response_headers or {}
        self.error_page_title = error_page_title


def _http_error_title(response: HTTPError) -> str | None:
    """Read a bounded HTML prefix for diagnostics, without retaining its body."""
    try:
        if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
            return None
        body = response.read(_ERROR_BODY_LIMIT)
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            text = body.decode(charset, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        title = BeautifulSoup(text, "html.parser", parse_only=SoupStrainer("title")).find("title")
        if title is None:
            return None
        text = title.get_text(" ", strip=True)
        text = "".join(char for char in text if char.isprintable() or char.isspace())
        return " ".join(text.split())[:_ERROR_TITLE_LIMIT] or None
    except (OSError, HTTPException, ValueError):
        # A failed diagnostic read must not replace the original HTTP status.
        return None
    finally:
        with suppress(OSError, HTTPException):
            response.close()


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_last_request: dict[str, float] = {}
_blocked_until: dict[str, float] = {}


def _host_lock(host: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(host, threading.Lock())


def _validate_payload(text: str, json_response: bool):
    if not json_response:
        return text
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise SourceError("Source returned invalid JSON (possibly an access page).") from exc
    if isinstance(value, dict) and value.get("error"):
        error = value["error"]
        raise SourceError(f"Source API error: {error}")
    return value


def _request_bytes_locked(
    url: str, *, host: str, timeout_s: float, use_proxy: bool | None,
    min_interval_s: float, max_bytes: int, referer: str | None = None,
    accept: str = "*/*",
) -> bytes:
    remaining = _blocked_until.get(host, 0) - time.monotonic()
    if remaining > 0:
        raise SourceError(f"{host} is cooling down; retry in {remaining:.0f}s.",
                          retry_after=str(int(remaining) + 1))
    for attempt in range(2):
        wait = min_interval_s - (time.monotonic() - _last_request.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        try:
            headers = {
                "User-Agent": config.user_agent,
                "Accept": accept,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
            }
            if referer:
                headers["Referer"] = referer
            request = Request(url, headers=headers)
            with build_http_opener(use_proxy).open(request, timeout=timeout_s) as response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise SourceError(f"Source response exceeds {max_bytes} bytes.")
            return data
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            # Keep only public diagnostic headers; never retain Set-Cookie or
            # other session/authentication material in logs or manifests.
            response_headers = {
                name: exc.headers[name]
                for name in ("Server", "Content-Type", "Retry-After", "EO-LOG-UUID",
                             "CF-Ray", "cf-mitigated")
                if exc.headers.get(name)
            }
            if exc.code in (403, 429, 567) or retry_after:
                cooldown = max(60, int(retry_after)) if retry_after and retry_after.isdigit() else 60
                _blocked_until[host] = time.monotonic() + cooldown
            if attempt == 0 and exc.code in (502, 503, 504) and not retry_after:
                with suppress(OSError, HTTPException):
                    exc.close()
                time.sleep(2)
                continue
            error_page_title = _http_error_title(exc)
            diagnostics = [f"{key}: {value}" for key, value in response_headers.items()]
            if error_page_title:
                diagnostics.append(f"Error page title: {error_page_title}")
            raise SourceError(
                f"{host} returned HTTP {exc.code}; retry later"
                + (f" (Retry-After: {retry_after})" if retry_after else "")
                + (" [" + "; ".join(diagnostics) + "]" if diagnostics else "") + ".",
                status=exc.code, retry_after=retry_after,
                response_headers=response_headers,
                error_page_title=error_page_title,
            ) from exc
        except (URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
            if attempt == 0:
                time.sleep(2)
                continue
            raise SourceError(f"Request to {host} failed: {exc}") from exc
        finally:
            _last_request[host] = time.monotonic()


def request_bytes(
    url: str, *, timeout_s: float = 45, use_proxy: bool | None = None,
    min_interval_s: float = 2, max_bytes: int = 16_000_000,
    referer: str | None = None,
) -> bytes:
    """Bounded binary GET using the same host limits/retries as text requests."""
    host = urlparse(url).netloc
    with _host_lock(host):
        return _request_bytes_locked(
            url, host=host, timeout_s=timeout_s, use_proxy=use_proxy,
            min_interval_s=min_interval_s, max_bytes=max_bytes, referer=referer,
        )


def request_text(
    url: str, *, timeout_s: float = 45, use_proxy: bool | None = None,
    cache_ttl_s: float = 3600, min_interval_s: float = 2,
    json_response: bool = False,
    referer: str | None = None,
) -> str:
    """GET public content with a disk cache and serialized requests per host.

    Cache only successful responses. Retry transient gateway/connection errors
    once; stop on access/rate-limit responses and impose a per-process cooldown.
    No stale-cache fallback is performed.
    """
    host = urlparse(url).netloc
    cache_dir = Path(os.getenv("CRAWLER_CACHE_DIR", "results/.http-cache"))
    cache_identity = f"{url}\n{config.user_agent}"
    if referer:
        cache_identity += f"\n{referer}"
    key = hashlib.sha256(cache_identity.encode()).hexdigest()
    cache_path = cache_dir / f"{key}.json"
    with _host_lock(host):
        if cache_ttl_s > 0:
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if 0 <= time.time() - cached["time"] < cache_ttl_s:
                    _validate_payload(cached["text"], json_response)
                    return cached["text"]
            except (OSError, ValueError, KeyError, TypeError, SourceError):
                pass
        data = _request_bytes_locked(
            url, host=host, timeout_s=timeout_s, use_proxy=use_proxy,
            min_interval_s=min_interval_s, max_bytes=16_000_000,
            referer=referer,
            accept="application/json" if json_response else "text/html, text/plain;q=0.9, */*;q=0.8",
        )
        text = data.decode("utf-8")
        _validate_payload(text, json_response)
        if cache_ttl_s > 0:
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                temp = cache_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
                temp.write_text(json.dumps({"time": time.time(), "text": text}), encoding="utf-8")
                temp.replace(cache_path)
            except OSError:
                pass  # A read-only cache must not make a successful GET fail.
        return text


def request_json(url: str, **kwargs):
    return json.loads(request_text(url, json_response=True, **kwargs))
