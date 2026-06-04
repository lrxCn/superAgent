"""Local FastMCP Streamable HTTP server for integration smoke tests."""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP


def main() -> None:
    port = int(sys.argv[1])
    server = FastMCP(
        "local-http-smoke",
        host="127.0.0.1",
        port=port,
        log_level="ERROR",
        streamable_http_path="/mcp",
    )

    @server.tool()
    def echo(text: str) -> str:
        """Echo text through the local HTTP MCP server."""
        return text

    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
