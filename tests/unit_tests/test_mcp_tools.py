import asyncio

import pytest

from agent.tools.mcp import (
    FakeMCPClient,
    MCPConnectionError,
    MCPToolError,
    ToolObservation,
    ToolSpec,
    build_example_mcp_config,
    sanitize_tool_content,
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
