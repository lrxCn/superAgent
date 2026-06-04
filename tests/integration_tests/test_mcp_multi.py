import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from agent.tools.mcp import (
    MCPStdioConfig,
    MCPUrlConfig,
    create_multi_mcp_client,
)

pytestmark = [pytest.mark.anyio, pytest.mark.mcp]


async def test_multi_mcp_stdio_and_local_http_smoke() -> None:
    if os.environ.get("RUN_MCP_TESTS") != "true":
        pytest.skip("Set RUN_MCP_TESTS=true after local Node.js is available.")

    port = _free_port()
    process = _start_fastmcp_server(port)
    try:
        _wait_for_http(f"http://127.0.0.1:{port}/mcp")
        client = create_multi_mcp_client(
            [
                MCPStdioConfig(
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "./docs"],
                    name="filesystem",
                ),
                MCPUrlConfig(
                    name="local_http",
                    transport="streamable_http",
                    url=f"http://127.0.0.1:{port}/mcp",
                    timeout_seconds=10,
                    sse_read_timeout_seconds=10,
                ),
            ]
        )

        await client.connect()
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        filesystem_result = await client.call_tool(
            "filesystem.read_file",
            {"path": "docs/progress.md"},
            timeout_seconds=30,
        )
        http_result = await client.call_tool(
            "local_http.echo",
            {"text": "hello multi mcp"},
            timeout_seconds=10,
        )
        await client.close()

        assert "filesystem.read_file" in names
        assert "local_http.echo" in names
        assert filesystem_result.success is True
        assert "# SuperAgent Progress" in filesystem_result.content
        assert http_result.success is True
        assert "hello multi mcp" in http_result.content
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


async def test_public_streamable_http_mcp_smoke() -> None:
    if os.environ.get("RUN_PUBLIC_MCP_TESTS") != "true":
        pytest.skip("Set RUN_PUBLIC_MCP_TESTS=true to hit the public stand-in MCP.")

    client = create_multi_mcp_client(
        [
            MCPUrlConfig(
                name="crow_catalog",
                transport="streamable_http",
                url="https://crowcrowcrow.com/api/mcp/mcp",
                timeout_seconds=15,
                sse_read_timeout_seconds=15,
            )
        ]
    )
    await client.connect()
    tools = await client.list_tools()
    result = await client.call_tool(
        "crow_catalog.products.search",
        {"query": "protein", "limit": 1},
        timeout_seconds=15,
    )
    await client.close()

    assert any(tool.name == "crow_catalog.products.search" for tool in tools)
    assert result.success is True
    assert "protein" in result.content.lower()


def _start_fastmcp_server(port: int) -> subprocess.Popen[str]:
    script = Path(__file__).with_name("mcp_http_server.py")
    return subprocess.Popen(
        [
            sys.executable,
            str(script),
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_http(url: str, timeout_seconds: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=1.0) as client:
                response = client.get(url)
            if response.status_code in {200, 307, 404, 405, 406}:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"MCP HTTP server did not start at {url}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
