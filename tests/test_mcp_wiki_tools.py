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
    ("biligame", "crawl_biligame_wiki", "https://wiki.biligame.com/umamusume/东海帝皇"),
    ("moegirl", "crawl_moegirl_wiki", "https://mzh.moegirl.org.cn/东海帝王"),
    ("umamusu", "crawl_umamusu_wiki", "https://umamusu.wiki/Tokai_Teio"),
    ("wikiru", "crawl_wikiru_wiki", "https://umamusume.wikiru.jp/?トウカイテイオー"),
]


async def _call_tool(tool_name: str, arguments: dict) -> dict:
    server_url = os.getenv("MCP_URL", "http://127.0.0.1:7777/mcp/")
    async with streamable_http_client(server_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert not any("google" in name for name in tool_names)
            assert tool_name in tool_names, f"Missing MCP tool: {tool_name}"
            result = await session.call_tool(tool_name, arguments)

    assert not result.isError, f"{tool_name} MCP protocol error: {result}"
    payload = result.structuredContent
    if not isinstance(payload, dict):
        text_blocks = [item.text for item in result.content if hasattr(item, "text")]
        assert text_blocks, f"{tool_name} returned no JSON content"
        payload = json.loads(text_blocks[0])
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    ("site", "tool_name", "url"), MCP_WIKI_CASES,
    ids=[case[0] for case in MCP_WIKI_CASES],
)
async def test_mcp_wiki_crawler_tool(site: str, tool_name: str, url: str) -> None:
    payload = await _call_tool(tool_name, {
        "url": url, "max_depth": 0, "max_pages": 1, "use_proxy": False,
    })
    assert payload.get("status") == "success", f"{site} MCP tool failed: {payload}"
    assert payload.get("source_format") == "rendered_html"
    content = payload.get("result")
    assert isinstance(content, str) and len(content) > 1000
    assert "150" in str(payload.get("infobox")), f"{site} lost character fields"
    if site == "wikiru":
        assert "ボイス" in content and "親愛度" in content
        assert "コメントフォーム" not in content


@pytest.mark.parametrize("action", ["search", "character", "resources"])
async def test_mcp_umapyoi_tools(action: str) -> None:
    if action == "search":
        payload = await _call_tool("umapyoi_character_search", {
            "keyword": "Tokai Teio", "use_proxy": False,
        })
        assert "error" not in payload, payload
        assert any(item["game_id"] == 1003 for item in payload["results"])
        return
    payload = await _call_tool(f"get_umapyoi_{action}", {"game_id": 1003, "use_proxy": False})
    assert payload.get("status") == "success", payload
    assert payload["game_id"] == 1003
    if action == "character":
        assert payload["profile"]["name_jp"] == "トウカイテイオー"
    else:
        assert payload["partial"] is False, payload["errors"]
        assert payload["outfits"] and payload["support_cards"] and payload["images"]
        assert payload["url_status"] == "unverified"
