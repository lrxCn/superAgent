import os

import pytest

from agent.tools.mcp import (
    MCPStdioConfig,
    create_mcp_client,
    validate_tool_arguments,
)

pytestmark = [pytest.mark.anyio, pytest.mark.mcp]


async def test_stdio_mcp_filesystem_lists_tools() -> None:
    if os.environ.get("RUN_MCP_TESTS") != "true":
        pytest.skip("Set RUN_MCP_TESTS=true after local Node.js is available.")

    client = create_mcp_client(
        MCPStdioConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "./docs"],
            name="filesystem_smoke",
        )
    )
    await client.connect()
    tools = await client.list_tools()
    await client.close()

    assert tools
    read_tool = next((tool for tool in tools if tool.name == "read_file"), None)
    assert read_tool is not None
    assert validate_tool_arguments(
        read_tool,
        {"path": "README.md"},
    ) is None
