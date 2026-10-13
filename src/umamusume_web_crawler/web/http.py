"""Shared urllib proxy handling and the browser user agent for HTML workflows."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import OpenerDirector, ProxyHandler, Request, build_opener

from umamusume_web_crawler.config import config


# MediaWiki API requests use config.user_agent, not this browser identity.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


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
                 retry_after: str | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


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


def request_text(
    url: str, *, timeout_s: float = 45, use_proxy: bool | None = None,
    cache_ttl_s: float = 3600, min_interval_s: float = 2,
    json_response: bool = False,
) -> str:
    """GET public content with a disk cache and serialized requests per host.

    Cache only successful responses. Retry transient gateway/connection errors
    once; stop on access/rate-limit responses and impose a per-process cooldown.
    No stale-cache fallback is performed.
    """
    host = urlparse(url).netloc
    cache_dir = Path(os.getenv("CRAWLER_CACHE_DIR", "results/.http-cache"))
    key = hashlib.sha256(f"{url}\n{config.user_agent}".encode()).hexdigest()
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
        remaining = _blocked_until.get(host, 0) - time.monotonic()
        if remaining > 0:
            raise SourceError(f"{host} is cooling down; retry in {remaining:.0f}s.")
        for attempt in range(2):
            wait = min_interval_s - (time.monotonic() - _last_request.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                request = Request(url, headers={
                    "User-Agent": config.user_agent,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                })
                with build_http_opener(use_proxy).open(request, timeout=timeout_s) as response:
                    data = response.read(16_000_001)
                    if len(data) > 16_000_000:
                        raise SourceError("Source response exceeds 16 MB.")
                    text = data.decode("utf-8")
                _validate_payload(text, json_response)
                break
            except HTTPError as exc:
                retry_after = exc.headers.get("Retry-After")
                if exc.code in (403, 429, 567):
                    cooldown = max(60, int(retry_after)) if retry_after and retry_after.isdigit() else 60
                    _blocked_until[host] = time.monotonic() + cooldown
                if attempt == 0 and exc.code in (502, 503, 504) and not retry_after:
                    time.sleep(2)
                    continue
                raise SourceError(
                    f"{host} returned HTTP {exc.code}; retry later"
                    + (f" (Retry-After: {retry_after})" if retry_after else "") + ".",
                    status=exc.code, retry_after=retry_after,
                ) from exc
            except (URLError, TimeoutError) as exc:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise SourceError(f"Request to {host} failed: {exc}") from exc
            finally:
                _last_request[host] = time.monotonic()
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
