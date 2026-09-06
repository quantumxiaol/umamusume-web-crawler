import json
import os

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.mcp_integration,
    pytest.mark.skipif(
        os.getenv("RUN_MCP_INTEGRATION") != "1",
        reason="set RUN_MCP_INTEGRATION=1 and start the MCP HTTP server",
    ),
]

MCP_WIKI_CASES = [
    (
        "biligame",
        "crawl_biligame_wiki",
        "https://wiki.biligame.com/umamusume/东海帝皇",
    ),
    (
        "moegirl",
        "crawl_moegirl_wiki",
        "https://mzh.moegirl.org.cn/东海帝王",
    ),
    (
        "umamusu",
        "crawl_umamusu_wiki",
        "https://umamusu.wiki/Tokai_Teio",
    ),
]


@pytest.mark.parametrize(
    ("site", "tool_name", "url"),
    MCP_WIKI_CASES,
    ids=[case[0] for case in MCP_WIKI_CASES],
)
async def test_mcp_wiki_crawler_tool(
    site: str, tool_name: str, url: str
) -> None:
    server_url = os.getenv("MCP_URL", "http://127.0.0.1:7777/mcp/")

    async with streamable_http_client(server_url) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert tool_name in tool_names, f"Missing MCP tool: {tool_name}"
            result = await session.call_tool(
                tool_name,
                {
                    "url": url,
                    "max_depth": 0,
                    "max_pages": 1,
                    "use_proxy": False,
                },
            )

    assert not result.isError, f"{site} MCP protocol error: {result}"
    payload = result.structuredContent
    if not isinstance(payload, dict):
        text_blocks = [
            item.text for item in result.content if hasattr(item, "text")
        ]
        assert text_blocks, f"{site} MCP tool returned no JSON content"
        payload = json.loads(text_blocks[0])

    assert payload.get("status") == "success", (
        f"{site} MCP tool failed: {payload}"
    )
    content = payload.get("result")
    assert isinstance(content, str) and content.strip(), (
        f"{site} MCP tool returned empty content"
    )
