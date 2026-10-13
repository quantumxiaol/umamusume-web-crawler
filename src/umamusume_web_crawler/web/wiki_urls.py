from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlparse

BASE_URLS = {
    "biligame": "https://wiki.biligame.com/umamusume/",
    "moegirl": "https://mzh.moegirl.org.cn/",
    "umamusu": "https://umamusu.wiki/",
    "wikiru": "https://umamusume.wikiru.jp/",
}


def detect_site(value: str) -> str:
    host = (urlparse(value).hostname or "").lower()
    if host == "wiki.biligame.com":
        return "biligame"
    if host in ("moegirl.org.cn", "mzh.moegirl.org.cn", "zh.moegirl.org.cn"):
        return "moegirl"
    if host == "umamusu.wiki":
        return "umamusu"
    if host == "umamusume.wikiru.jp":
        return "wikiru"
    raise ValueError("Unsupported wiki host.")


def normalize_title(value: str, site: str | None = None) -> str:
    if not value.startswith(("http://", "https://")):
        return value.strip()
    site = site or detect_site(value)
    parsed = urlparse(value)
    if detect_site(value) != site:
        raise ValueError(f"URL does not belong to {site}.")
    query = parse_qs(parsed.query)
    if site == "wikiru":
        if query.get("page"):
            if query.get("cmd", ["read"])[0] != "read":
                raise ValueError("Only wikiru reading URLs are supported.")
            return query["page"][0].strip()
        if parsed.query and "=" not in parsed.query and "&" not in parsed.query:
            return unquote(parsed.query).strip()
        raise ValueError("Missing wikiru page name in query string.")
    if parsed.path.endswith("/index.php"):
        title = query.get("title", [""])[0]
    else:
        path = parsed.path.lstrip("/")
        if site == "biligame":
            if not path.startswith("umamusume/"):
                raise ValueError("Expected the Bwiki umamusume wiki.")
            path = path[len("umamusume/"):]
        elif site == "moegirl" and path.startswith("wiki/"):
            path = path[len("wiki/"):]
        title = unquote(path)
    return title.strip()


def wiki_url(site: str, title: str) -> str:
    if not title.strip():
        raise ValueError("Missing wiki page title.")
    if site == "wikiru":
        return BASE_URLS[site] + "?" + quote(title, safe="")
    return BASE_URLS[site] + quote(title.replace(" ", "_"), safe="/:")
