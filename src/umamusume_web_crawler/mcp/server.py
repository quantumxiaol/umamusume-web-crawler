from __future__ import annotations

import argparse
import contextlib
import sys
from urllib.parse import parse_qs, quote, unquote, urlparse
from collections.abc import AsyncIterator

from dotenv import load_dotenv

import uvicorn
from mcp.server import Server
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from umamusume_web_crawler.web.biligame import (
    fetch_biligame_wikitext_expanded,
    search_biligame_titles,
)
from umamusume_web_crawler.web.moegirl import (
    fetch_moegirl_wikitext_expanded,
    search_moegirl_titles,
)
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)
from umamusume_web_crawler.web.search import (
    google_search_page_urls,
    google_search_urls,
)

mcp = FastMCP("Umamusume Web MCP")

_BILIGAME_BASE_URL = "https://wiki.biligame.com/umamusume/"
_MOEGIRL_BASE_URL = "https://mzh.moegirl.org.cn/"


def _title_from_url(value: str) -> str:
    if not value.startswith("http://") and not value.startswith("https://"):
        return value
    parsed = urlparse(value)
    if parsed.path.endswith("/index.php"):
        params = parse_qs(parsed.query)
        title = params.get("title", [""])[0]
        if title:
            return title
    return unquote(parsed.path.strip("/").split("/")[-1])


def _build_wiki_url(base_url: str, title: str) -> str:
    return f"{base_url}{quote(title)}"


@mcp.tool(
    description="""
Performs a web search with Google for the given query and returns a list of URLs.
Use this tool first to find pages about a character or topic.
Returns up to 5 results ranked by relevance.

Example queries:
- "爱慕织姬 site:wiki.biligame.com/umamusume"
- "爱慕织姬 site:mzh.moegirl.org.cn"
"""
)
async def web_search_google(query: str) -> dict:
    try:
        results = google_search_urls(query, num=5)
        return {
            "results": [
                {"url": item["url"], "priority": str(item["priority"])}
                for item in results
            ]
        }
    except Exception as exc:
        return {"results": [], "error": str(exc)}


@mcp.tool(
    description="""
Search Biligame Wiki for a character name and return candidate wiki links.
"""
)
async def biligame_wiki_seaech(
    keyword: str, limit: int = 5, use_proxy: bool | None = None
) -> dict:
    try:
        titles = await search_biligame_titles(
            keyword, limit=limit, use_proxy=use_proxy
        )
        results = [
            {
                "title": title,
                "url": _build_wiki_url(_BILIGAME_BASE_URL, title),
                "priority": str(idx + 1),
            }
            for idx, title in enumerate(titles)
        ]
        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


@mcp.tool(
    description="""
Search Moegirl Wiki for a character name and return candidate wiki links.
"""
)
async def moegirl_wiki_search(
    keyword: str, limit: int = 5, use_proxy: bool | None = None
) -> dict:
    try:
        titles = await search_moegirl_titles(
            keyword, limit=limit, use_proxy=use_proxy
        )
        results = [
            {
                "title": title,
                "url": _build_wiki_url(_MOEGIRL_BASE_URL, title),
                "priority": str(idx + 1),
            }
            for idx, title in enumerate(titles)
        ]
        return {"results": results}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


@mcp.tool(
    description="""
Crawl a Bilibili Wiki page via API and return the parsed Markdown output.
Use this for wiki.biligame.com/umamusume pages. Supports optional transclusion expansion.
"""
)
async def crawl_biligame_wiki(
    url: str,
    max_depth: int = 1,
    max_pages: int = 5,
    use_proxy: bool | None = None,
) -> dict:
    try:
        wikitext = await fetch_biligame_wikitext_expanded(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            use_proxy=use_proxy,
        )
        page = parse_wiki_page(wikitext, site="biligame")
        heading = _title_from_url(url)
        markdown = wiki_page_to_llm_markdown(heading, page, site="biligame")
        return {"status": "success", "result": markdown}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool(
    description="""
Crawl a Moegirl Wiki page via API and return the parsed Markdown output.
Use this for mzh.moegirl.org.cn pages. Supports optional transclusion expansion.
"""
)
async def crawl_moegirl_wiki(
    url: str,
    max_depth: int = 1,
    max_pages: int = 5,
    use_proxy: bool | None = None,
) -> dict:
    try:
        wikitext = await fetch_moegirl_wikitext_expanded(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            use_proxy=use_proxy,
        )
        page = parse_wiki_page(wikitext, site="moegirl")
        heading = _title_from_url(url)
        markdown = wiki_page_to_llm_markdown(heading, page, site="moegirl")
        return {"status": "success", "result": markdown}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool(
    description="""
Fetch Google search result page HTML and extract result links.
Use this when Google API is unavailable and you need simple link extraction.
"""
)
async def crawl_google_page(
    query: str, num: int = 5, use_proxy: bool | None = None
) -> dict:
    try:
        results = google_search_page_urls(query, num=num, use_proxy=use_proxy)
        return {
            "results": [
                {"url": item["url"], "priority": str(item["priority"])}
                for item in results
            ]
        }
    except Exception as exc:
        return {"results": [], "error": str(exc)}


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    sse = SseServerTransport("/messages/")
    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=None,
        json_response=True,
        stateless=True,
    )

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    async def handle_streamable_http(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            print("MCP Web server started (StreamableHTTP).")
            try:
                yield
            finally:
                print("MCP Web server shutting down.")

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/mcp", app=handle_streamable_http),
            Mount("/messages/", app=sse.handle_post_message),
        ],
        lifespan=lifespan,
    )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run Umamusume Web MCP server")
    parser.add_argument("--http", action="store_true", help="Use StreamableHTTP + SSE")
    parser.add_argument("--sse", action="store_true", help="Alias for --http")
    parser.add_argument("--host", default=None, help="Host to bind to")
    parser.add_argument("--port", "-p", type=int, default=None, help="Port to listen on")
    args = parser.parse_args()

    use_http = args.http or args.sse
    if not use_http and (args.host or args.port):
        parser.error(
            "Host and port are only valid when using Streamable HTTP (see: --http)."
        )
        sys.exit(1)

    if use_http:
        starlette_app = create_starlette_app(mcp._mcp_server, debug=True)
        uvicorn.run(
            starlette_app,
            host=args.host if args.host else "127.0.0.1",
            port=args.port if args.port else 7777,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
