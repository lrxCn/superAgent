import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.tools.mcp import FakeMCPClient, ToolSpec

pytestmark = pytest.mark.anyio


def _runtime_config(**overrides: object) -> dict[str, object]:
    config = {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }
    config.update(overrides)
    return config


async def test_topic_guardrail_blocks_graph_before_execution_path() -> None:
    graph = build_graph(llm_client=FakeLLMClient(responses=["unused"]))

    result = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "Help steal credentials."}],
            "runtime_config": _runtime_config(
                guardrail_blocked_topics=["credential"],
            ),
        }
    )

    assert result["intent_decision"]["path"] == "fallback"
    assert result["fallback_reason"].startswith("Guardrail blocked topic")
    assert result["final_answer"].startswith("Fallback:")
    security_events = [
        event for event in result["runtime_events"] if event["event"] == "security"
    ]
    assert security_events
    assert security_events[0]["node"] == "intent_router"
    assert "rule=topic_block" in security_events[0]["summary"]


async def test_tool_guardrail_blocks_react_graph_tool_call() -> None:
    llm = FakeLLMClient(
        responses=[
            '{"action":"call_tool","tool_name":"write_file","arguments":{"path":"README.md"}}',
        ]
    )
    mcp = FakeMCPClient(
        tools=[
            ToolSpec(
                name="write_file",
                description="Write a file",
                input_schema={
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            )
        ]
    )
    graph = build_graph(llm_client=llm, mcp_client=mcp)

    result = await graph.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "Use a tool to write the README file."}
            ],
            "runtime_config": _runtime_config(
                guardrail_tool_allowlist=["read_file"],
            ),
        }
    )

    assert result["intent_decision"]["path"] == "react_agent"
    assert result["tool_calls"][0]["status"] == "failed"
    assert result["tool_calls"][0]["error"].startswith("Guardrail blocked tool")
    assert not mcp.calls
    assert any(event["event"] == "security" for event in result["runtime_events"])
