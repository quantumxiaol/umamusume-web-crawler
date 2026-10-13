from __future__ import annotations

import argparse
import contextlib
import sys
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

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.tools import crawl_wiki, search_wiki, umapyoi_tool
from umamusume_web_crawler.web.umamusu_wiki import download_umamusu_category_images as _download_umamusu_category_images

mcp = FastMCP("Umamusume Web MCP")

@mcp.tool(description="Search biligame wiki titles.")
async def biligame_wiki_search(keyword: str, limit: int = 5, use_proxy: bool | None = None) -> dict:
    return await search_wiki("biligame", keyword, limit=limit, use_proxy=use_proxy)


@mcp.tool(description="Read biligame rendered article body, preserving tables and folded dialogue. max_depth/max_pages are legacy no-ops.")
async def crawl_biligame_wiki(url: str, max_depth: int = 1, max_pages: int = 5, use_proxy: bool | None = None) -> dict:
    return await crawl_wiki("biligame", url, use_proxy=use_proxy, max_depth=max_depth, max_pages=max_pages)


@mcp.tool(description="Search moegirl wiki titles.")
async def moegirl_wiki_search(keyword: str, limit: int = 5, use_proxy: bool | None = None) -> dict:
    return await search_wiki("moegirl", keyword, limit=limit, use_proxy=use_proxy)


@mcp.tool(description="Read moegirl rendered article body, preserving tables and folded dialogue. max_depth/max_pages are legacy no-ops.")
async def crawl_moegirl_wiki(url: str, max_depth: int = 1, max_pages: int = 5, use_proxy: bool | None = None) -> dict:
    return await crawl_wiki("moegirl", url, use_proxy=use_proxy, max_depth=max_depth, max_pages=max_pages)


@mcp.tool(description="Search umamusu wiki titles.")
async def umamusu_wiki_search(keyword: str, limit: int = 5, use_proxy: bool | None = None) -> dict:
    return await search_wiki("umamusu", keyword, limit=limit, use_proxy=use_proxy)


@mcp.tool(description="Read umamusu rendered article body, preserving tables and folded dialogue. max_depth/max_pages are legacy no-ops.")
async def crawl_umamusu_wiki(url: str, max_depth: int = 1, max_pages: int = 5, use_proxy: bool | None = None) -> dict:
    return await crawl_wiki("umamusu", url, use_proxy=use_proxy, max_depth=max_depth, max_pages=max_pages)


@mcp.tool(description="Search wikiru character index by Japanese page name.")
async def wikiru_wiki_search(keyword: str, limit: int = 5, use_proxy: bool | None = None) -> dict:
    return await search_wiki("wikiru", keyword, limit=limit, use_proxy=use_proxy)


@mcp.tool(description="Read wikiru rendered article body, preserving tables and folded dialogue. max_depth/max_pages are legacy no-ops.")
async def crawl_wikiru_wiki(url: str, max_depth: int = 1, max_pages: int = 5, use_proxy: bool | None = None) -> dict:
    return await crawl_wiki("wikiru", url, use_proxy=use_proxy, max_depth=max_depth, max_pages=max_pages)


@mcp.tool(description="Compatibility alias for biligame_wiki_search.")
async def biligame_wiki_seaech(keyword: str, limit: int = 5, use_proxy: bool | None = None) -> dict:
    return await biligame_wiki_search(keyword, limit, use_proxy)


@mcp.tool(description="Search Umapyoi structured profiles by Japanese/English name or game_id. Chinese aliases are not supported.")
async def umapyoi_character_search(keyword: str, limit: int = 5, use_proxy: bool | None = None) -> dict:
    return await umapyoi_tool("search", keyword=keyword, limit=limit, use_proxy=use_proxy)


@mcp.tool(description="Read a supplemental structured character profile. Use game_id, not database id; null fields are preserved.")
async def get_umapyoi_character(game_id: int, use_proxy: bool | None = None) -> dict:
    return await umapyoi_tool("character", game_id=game_id, use_proxy=use_proxy)


@mcp.tool(description="Read outfit, support card and image indices. URLs are unverified; no media are downloaded.")
async def get_umapyoi_resources(game_id: int, use_proxy: bool | None = None) -> dict:
    return await umapyoi_tool("resources", game_id=game_id, use_proxy=use_proxy)


@mcp.tool(
    description="""
Download image files from a umamusu.wiki category such as Category:Game_Backgrounds.
Uses MediaWiki categorymembers pagination and then imageinfo URLs for each file.
"""
)
async def download_umamusu_category_images(
    category: str,
    output_dir: str = "results/umamusu_wiki_images",
    max_files: int | None = None,
    delay_s: float = 0.5,
    use_proxy: bool | None = None,
) -> dict:
    try:
        downloads = await _download_umamusu_category_images(
            category,
            output_dir=output_dir,
            max_files=max_files,
            delay_s=delay_s,
            use_proxy=use_proxy,
        )
        return {
            "status": "success",
            "category": category,
            "output_dir": output_dir,
            "count": len(downloads),
            "downloaded": downloads,
        }
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
    load_dotenv()
    config.update_from_env()
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
