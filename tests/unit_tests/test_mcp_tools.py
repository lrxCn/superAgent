import asyncio

import pytest

from agent.tools.mcp import (
    FakeMCPClient,
    MCPConnectionError,
    MCPStdioConfig,
    MCPToolError,
    MCPUrlConfig,
    MultiMCPClient,
    ToolObservation,
    ToolSpec,
    build_example_mcp_config,
    build_mcp_configs,
    create_configured_mcp_client,
    sanitize_tool_content,
    split_tool_name,
    validate_tool_arguments,
)

pytestmark = pytest.mark.anyio


def test_sanitize_tool_content_redacts_sensitive_fields_and_truncates() -> None:
    payload = {
        "summary": "ok",
        "api_key": "secret-value",
        "nested": {"authorization": "Bearer abc"},
    }
    rendered = sanitize_tool_content(payload)
    assert "secret-value" not in rendered
    assert "Bearer abc" not in rendered
    assert "[redacted]" in rendered

    huge = "x" * 5000
    truncated = sanitize_tool_content(huge)
    assert len(truncated) <= 4000
    assert truncated.endswith("[truncated]")


def test_validate_tool_arguments_checks_required_and_types() -> None:
    spec = ToolSpec(
        name="read_file",
        description="Read a file",
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
    )

    assert validate_tool_arguments(spec, {}) == "Missing required arguments: path"
    assert validate_tool_arguments(spec, {"path": 1}) == "Argument 'path' must be of type string."
    assert validate_tool_arguments(spec, {"path": "./docs/README.md"}) is None


async def test_fake_mcp_client_success_and_records_calls() -> None:
    client = FakeMCPClient(
        tools=[ToolSpec("read_file", "Read a file", {"type": "object", "properties": {}})],
        responses={
            "read_file": ToolObservation(
                tool_name="read_file",
                content='{"text":"hello"}',
                success=True,
            )
        },
    )
    await client.connect()
    tools = await client.list_tools()
    result = await client.call_tool("read_file", {"path": "README.md"}, timeout_seconds=1.0)
    await client.close()

    assert [tool.name for tool in tools] == ["read_file"]
    assert result.success is True
    assert client.calls[0].arguments == {"path": "README.md"}


async def test_fake_mcp_client_failure_and_timeout() -> None:
    failing = FakeMCPClient(
        responses={"read_file": MCPToolError("tool crashed")},
    )
    await failing.connect()
    with pytest.raises(MCPToolError):
        await failing.call_tool("read_file", {}, timeout_seconds=1.0)

    slow = FakeMCPClient(delay_seconds=0.2)
    await slow.connect()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            slow.call_tool("read_file", {}, timeout_seconds=0.05),
            timeout=0.05,
        )


async def test_fake_mcp_client_connect_error() -> None:
    client = FakeMCPClient(connect_error=MCPConnectionError("server down"))
    with pytest.raises(MCPConnectionError):
        await client.connect()


def test_build_example_mcp_config_from_env() -> None:
    config = build_example_mcp_config()
    assert config.command == "npx"
    assert "@modelcontextprotocol/server-filesystem" in " ".join(config.args)


def test_build_mcp_configs_supports_stdio_and_url() -> None:
    from agent.config import load_config

    config = load_config(
        {
            "MCP_SERVERS": (
                "["
                '{"name":"fs","transport":"stdio","command":"npx","args":"-y server ./docs"},'
                '{"name":"catalog","transport":"streamable_http",'
                '"url":"https://crowcrowcrow.com/api/mcp/mcp"}'
                "]"
            )
        }
    )

    configs = build_mcp_configs(config)

    assert isinstance(configs[0], MCPStdioConfig)
    assert configs[0].args == ["-y", "server", "./docs"]
    assert isinstance(configs[1], MCPUrlConfig)
    assert configs[1].transport == "streamable_http"


def test_create_configured_mcp_client_returns_multi_client() -> None:
    from agent.config import load_config

    config = load_config(
        {
            "MCP_SERVERS": (
                "["
                '{"name":"one","transport":"stdio","command":"npx","args":[]},'
                '{"name":"two","transport":"streamable_http","url":"http://127.0.0.1/mcp"}'
                "]"
            )
        }
    )

    assert isinstance(create_configured_mcp_client(config), MultiMCPClient)


async def test_multi_mcp_client_qualifies_and_routes_tools() -> None:
    filesystem = FakeMCPClient(
        tools=[
            ToolSpec(
                name="read_file",
                description="Read a file",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            )
        ],
        responses={
            "read_file": ToolObservation(
                tool_name="read_file",
                content="README content",
                success=True,
            )
        },
    )
    filesystem.config = MCPStdioConfig(
        command="npx",
        args=["-y", "server", "./docs"],
        name="filesystem",
    )
    catalog = FakeMCPClient(
        tools=[
            ToolSpec(
                name="products.search",
                description="Search products",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {"query": {"type": "string"}},
                },
            )
        ],
        responses={
            "products.search": ToolObservation(
                tool_name="products.search",
                content="catalog content",
                success=True,
            )
        },
    )
    catalog.config = MCPUrlConfig(
        name="catalog",
        url="https://crowcrowcrow.com/api/mcp/mcp",
        transport="streamable_http",
    )
    client = MultiMCPClient(configs=[], clients=[filesystem, catalog])

    await client.connect()
    tools = await client.list_tools()
    filesystem_result = await client.call_tool(
        "filesystem.read_file",
        {"path": "README.md"},
        timeout_seconds=1,
    )
    catalog_result = await client.call_tool(
        "catalog.products.search",
        {"query": "protein"},
        timeout_seconds=1,
    )
    sessions = client.session_summaries()
    await client.close()

    assert {tool.name for tool in tools} == {
        "filesystem.read_file",
        "read_file",
        "catalog.products.search",
        "products.search",
    }
    assert filesystem_result.tool_name == "filesystem.read_file"
    assert filesystem.calls[0].tool_name == "read_file"
    assert catalog_result.tool_name == "catalog.products.search"
    assert catalog.calls[0].tool_name == "products.search"
    assert sessions[0]["name"] == "filesystem"
    assert sessions[1]["tools"] == ["catalog.products.search"]


async def test_multi_mcp_client_requires_qualified_name_for_ambiguous_tools() -> None:
    first = FakeMCPClient(
        tools=[ToolSpec("search", "Search A", {"type": "object", "properties": {}})]
    )
    first.config = MCPStdioConfig(command="a", args=[], name="a")
    second = FakeMCPClient(
        tools=[ToolSpec("search", "Search B", {"type": "object", "properties": {}})]
    )
    second.config = MCPStdioConfig(command="b", args=[], name="b")
    client = MultiMCPClient(configs=[], clients=[first, second])

    await client.connect()

    with pytest.raises(MCPToolError):
        await client.call_tool("search", {}, timeout_seconds=1)

    result = await client.call_tool("a.search", {}, timeout_seconds=1)
    await client.close()

    assert result.success is True


def test_split_tool_name_accepts_qualified_and_legacy_names() -> None:
    assert split_tool_name("filesystem.read_file") == ("filesystem", "read_file")
    assert split_tool_name("read_file") == (None, "read_file")
