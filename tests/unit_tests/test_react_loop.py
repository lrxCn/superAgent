import pytest

from agent.llm import FakeLLMClient
from agent.nodes.react import create_react_node, parse_react_decision
from agent.tools.mcp import (
    FakeMCPClient,
    MCPConnectionError,
    MCPStdioConfig,
    MCPUrlConfig,
    MultiMCPClient,
    ToolObservation,
    ToolSpec,
)

pytestmark = pytest.mark.anyio


def test_parse_react_decision_accepts_finish_and_call_tool() -> None:
    finish = parse_react_decision('{"action":"finish","answer":"done"}')
    assert finish is not None
    assert finish.action == "finish"
    assert finish.answer == "done"

    call = parse_react_decision(
        '{"action":"call_tool","tool_name":"read_file","arguments":{"path":"README.md"}}'
    )
    assert call is not None
    assert call.tool_name == "read_file"
    assert call.arguments == {"path": "README.md"}


async def test_react_node_writes_tool_calls_and_observations() -> None:
    llm = FakeLLMClient(
        responses=[
            '{"action":"call_tool","tool_name":"read_file","arguments":{"path":"README.md"}}',
            '{"action":"finish","answer":"README says hello."}',
        ]
    )
    mcp = FakeMCPClient(
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
                content='{"text":"hello"}',
                success=True,
            )
        },
    )
    node = create_react_node(llm_client=llm, mcp_client=mcp)

    result = await node(
        {
            "messages": [{"role": "user", "content": "Read README.md"}],
            "runtime_config": {
                "react_max_steps": 8,
                "plan_max_steps": 12,
                "worker_max_concurrency": 4,
                "worker_timeout_seconds": 120,
                "tool_timeout_seconds": 30,
                "reflection_max_rounds": 1,
                "memory_enabled": True,
                "reflection_enabled": True,
            },
        }
    )

    assert result["mcp_sessions"][0]["status"] == "connected"
    assert result["tool_calls"][0]["tool_name"] == "read_file"
    assert result["tool_calls"][0]["status"] == "completed"
    assert result["observations"]
    assert result["final_answer"] == "README says hello."


async def test_react_node_routes_server_qualified_tools() -> None:
    llm = FakeLLMClient(
        responses=[
            (
                '{"action":"call_tool","tool_name":"catalog.products.search",'
                '"arguments":{"query":"protein"}}'
            ),
            '{"action":"finish","answer":"Found products."}',
        ]
    )
    filesystem = FakeMCPClient(
        tools=[
            ToolSpec(
                name="read_file",
                description="Read a file",
                input_schema={"type": "object", "properties": {}},
            )
        ],
    )
    filesystem.config = MCPStdioConfig(command="npx", args=[], name="filesystem")
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
                content="catalog result",
                success=True,
            )
        },
    )
    catalog.config = MCPUrlConfig(
        url="http://127.0.0.1:8000/mcp",
        transport="streamable_http",
        name="catalog",
    )
    mcp = MultiMCPClient(configs=[], clients=[filesystem, catalog])
    node = create_react_node(llm_client=llm, mcp_client=mcp)

    result = await node({"messages": [{"role": "user", "content": "Search products"}]})

    assert result["mcp_sessions"][0]["name"] == "filesystem"
    assert result["mcp_sessions"][1]["name"] == "catalog"
    assert result["tool_calls"][0]["tool_name"] == "catalog.products.search"
    assert catalog.calls[0].tool_name == "products.search"
    assert not filesystem.calls


async def test_react_node_records_validation_failure() -> None:
    llm = FakeLLMClient(
        responses=[
            '{"action":"call_tool","tool_name":"read_file","arguments":{}}',
            '{"action":"finish","answer":"Could not read file."}',
        ]
    )
    mcp = FakeMCPClient(
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
        ]
    )
    node = create_react_node(llm_client=llm, mcp_client=mcp)

    result = await node({"messages": [{"role": "user", "content": "Read README.md"}]})

    assert result["tool_calls"][0]["status"] == "failed"
    assert "Missing required arguments" in str(result["tool_calls"][0]["error"])
    assert result["observations"][0]["error"]


async def test_react_node_stops_at_max_steps() -> None:
    llm = FakeLLMClient(
        responses=[
            '{"action":"call_tool","tool_name":"read_file","arguments":{"path":"a.md"}}'
        ]
        * 10
    )
    mcp = FakeMCPClient(
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
        ]
    )
    node = create_react_node(llm_client=llm, mcp_client=mcp)

    result = await node(
        {
            "messages": [{"role": "user", "content": "Keep reading files"}],
            "runtime_config": {
                "react_max_steps": 2,
                "plan_max_steps": 12,
                "worker_max_concurrency": 4,
                "worker_timeout_seconds": 120,
                "tool_timeout_seconds": 30,
                "reflection_max_rounds": 1,
                "memory_enabled": True,
                "reflection_enabled": True,
            },
        }
    )

    assert result["fallback_reason"] == "ReAct loop exceeded max steps (2)."
    assert len(result["tool_calls"]) == 2


async def test_react_node_mcp_connection_failure_does_not_raise() -> None:
    mcp = FakeMCPClient(connect_error=MCPConnectionError("server unavailable"))
    node = create_react_node(
        llm_client=FakeLLMClient(responses=['{"action":"finish","answer":"unused"}']),
        mcp_client=mcp,
    )

    result = await node({"messages": [{"role": "user", "content": "Read a file"}]})

    assert result["mcp_sessions"][0]["status"] == "failed"
    assert "server unavailable" in result["fallback_reason"]
    assert result["final_answer"].startswith("Fallback:")
