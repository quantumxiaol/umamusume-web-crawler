from __future__ import annotations

import argparse
import contextlib
import sys
from collections.abc import AsyncIterator

import uvicorn
from mcp.server import Server
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page_visual_markitdown,
    crawl_moegirl_page_visual_markitdown,
    crawl_page,
    crawl_page_visual_markitdown,
)
from umamusume_web_crawler.web.search import google_search_urls

mcp = FastMCP("Umamusume Web MCP")


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
Crawl a page from a URL and return the page content as markdown.
Use this for general pages that do not require site-specific handling.
"""
)
async def crawl_web_page(url: str) -> dict:
    try:
        markdown = await crawl_page(url, use_proxy=False)
        return {"status": "success", "result": str(markdown)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool(
    description="""
Capture a webpage as PDF via browser rendering, convert the PDF to Markdown with MarkItDown,
and return the Markdown string.
Uses a proxy if use_proxy is true. If use_proxy is omitted, it follows proxy settings from .env.
"""
)
async def crawl_web_page_visual_markitdown(
    url: str, use_proxy: bool | None = None
) -> dict:
    try:
        markdown = await crawl_page_visual_markitdown(url, use_proxy=use_proxy)
        return {"status": "success", "result": str(markdown)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool(
    description="""
Capture a Bilibili Wiki page as PDF via browser rendering, convert the PDF to Markdown
with MarkItDown, and return the Markdown string.
Use this for wiki.biligame.com/umamusume pages.
If use_proxy is omitted, it follows proxy settings from .env.
"""
)
async def crawl_biligame_wiki(url: str, use_proxy: bool | None = None) -> dict:
    try:
        markdown = await crawl_biligame_page_visual_markitdown(url, use_proxy=use_proxy)
        return {"status": "success", "result": str(markdown)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool(
    description="""
Capture a Moegirl Wiki page as PDF via browser rendering, convert the PDF to Markdown
with MarkItDown, and return the Markdown string.
Use this for mzh.moegirl.org.cn pages. If use_proxy is omitted, it follows proxy settings
from .env. print_scale defaults to 0.65 when omitted.
"""
)
async def crawl_moegirl_wiki(
    url: str,
    use_proxy: bool | None = None,
    print_scale: float | None = None,
    headless: bool = False,
) -> dict:
    try:
        markdown = await crawl_moegirl_page_visual_markitdown(
            url,
            use_proxy=use_proxy,
            print_scale=print_scale,
            headless=headless,
        )
        return {"status": "success", "result": str(markdown)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


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
