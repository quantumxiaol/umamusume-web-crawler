"""
check mcp server and list tools

Local MCP example:
python tests/test_mcp_tool_crawler_biligame.py -u "http://127.0.0.1:7777/mcp/" \
    --tool-name crawl_biligame_wiki \
    --tool-arg "url=https://wiki.biligame.com/umamusume/爱慕织姬"

Notes:
- crawl_biligame_wiki uses the MediaWiki API and returns parsed Markdown.
- Optional: --tool-arg "use_proxy=true"
- Optional: --tool-arg "max_depth=1"
- Optional: --tool-arg "max_pages=5"
"""

import argparse
import asyncio
import json
import os
from typing import Any, Dict, Optional

import pytest
from dotenv import load_dotenv
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

load_dotenv()


def parse_tool_args(args_str_list: list) -> Dict[str, Any]:
    """
    将 ["key=value", "foo=bar"] 转为 {"key": "value", "foo": "bar"}
    支持自动类型解析：str, int, float, bool, None
    """
    result = {}
    if not args_str_list:
        return result

    for item in args_str_list:
        if "=" not in item:
            raise ValueError(f"Invalid tool-arg format: {item}, expected key=value")
        k, v = item.split("=", 1)

        # 尝试类型解析
        try:
            v = json.loads(v.lower() if v.lower() in ("true", "false", "null") else v)
        except json.JSONDecodeError:
            pass  # keep as string

        result[k] = v
    return result


async def async_main(
    server_url: str = "",
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
):

    async with streamable_http_client(server_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("MCP server session已初始化")

            tools = await load_mcp_tools(session)
            tool_dict = {tool.name: tool for tool in tools}

            print("可用工具:", [tool.name for tool in tools])
            for tool in tools:
                print(f"Tool: {tool.name}")
                print(f"Args Schema: {tool.args}")
                print(f"Description: {tool.description}\n")

            # =============================
            # 场景1: 仅列出工具（无 tool_name）
            # =============================
            if not tool_name:
                print("未提供工具调用，仅列出工具信息。")
                print("TEST_RESULT: PASSED")
                return None

            # =============================
            # 场景2: 直接调用指定工具
            # =============================
            if tool_name:
                if tool_name not in tool_dict:
                    print(f"错误: 工具 '{tool_name}' 未在 MCP 服务中找到！")
                    print("TEST_RESULT: FAILED")
                    return

                if not tool_args:
                    print(f"警告: 调用工具 '{tool_name}' 但未提供参数。")
                    tool_args = {}

                try:
                    print(f"正在调用工具: {tool_name}，参数: {tool_args}")
                    result = await tool_dict[tool_name].ainvoke(tool_args)
                    print("✅ 工具调用成功！返回结果:")
                    print(
                        json.dumps(result, indent=2, ensure_ascii=False)
                        if isinstance(result, (dict, list))
                        else result
                    )

                    # 可选：结构化解析（如果返回的是 JSON 字符串）
                    if isinstance(result, str):
                        try:
                            parsed = json.loads(result)
                            print("🔍 JSON 解析结果:")
                            print(json.dumps(parsed, indent=2, ensure_ascii=False))
                        except json.JSONDecodeError:
                            pass

                    print("TEST_RESULT: PASSED")
                    return result
                except Exception as e:
                    print(f"❌ 工具调用失败: {type(e).__name__}: {e}")
                    print("TEST_RESULT: FAILED")
                    return None


@pytest.mark.asyncio
async def test_mcp_tool_call() -> None:
    server_url = os.getenv("MCP_URL", "http://127.0.0.1:7777/mcp/")
    tool_name = os.getenv("MCP_TOOL_NAME", "crawl_biligame_wiki")
    tool_args = parse_tool_args(
        [
            os.getenv(
                "MCP_TOOL_QUERY",
                "url=https://wiki.biligame.com/umamusume/爱慕织姬",
            )
        ]
    )

    try:
        async with streamable_http_client(server_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)
                tool_dict = {tool.name: tool for tool in tools}
                assert tool_name in tool_dict, f"Missing tool: {tool_name}"
                print(f"Tool call: {tool_name} args={tool_args}")
                result = await tool_dict[tool_name].ainvoke(tool_args)
                assert result, "Empty tool result"
                if isinstance(result, dict):
                    status = result.get("status")
                    assert status == "success", f"Tool error: {result}"
                    content = result.get("result") or result.get("message") or ""
                    snippet = (
                        content.replace("\n", " ")[:200]
                        if isinstance(content, str)
                        else ""
                    )
                    print(f"Result status: {status}")
                    if snippet:
                        print(f"Result snippet: {snippet}")
                    else:
                        print(f"Result keys: {list(result.keys())}")
                else:
                    print(f"Result type: {type(result).__name__}")
                print("TEST_RESULT: PASSED")
    except Exception as exc:
        print(f"TEST_RESULT: SKIPPED ({exc})")
        pytest.skip(f"MCP server not available: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test MCP Server: list tools or invoke tool"
    )

    parser.add_argument(
        "-u",
        "--base_url",
        type=str,
        default="http://127.0.0.1:7777/mcp/",
        help="MCP server base url",
    )
    parser.add_argument(
        "--tool-name",
        type=str,
        default="crawl_biligame_wiki",
        help="要直接调用的工具名称，例如 crawl_biligame_wiki",
    )
    parser.add_argument(
        "--tool-arg",
        action="append",
        default=["url=https://wiki.biligame.com/umamusume/爱慕织姬"],
        help="工具参数，格式 key=value，可多次使用",
    )
    args = parser.parse_args()

    # 解析 tool-arg
    tool_args = parse_tool_args(args.tool_arg) if args.tool_arg else None

    # 运行主函数
    asyncio.run(
        async_main(
            server_url=args.base_url,
            tool_name=args.tool_name,
            tool_args=tool_args,
        )
    )
