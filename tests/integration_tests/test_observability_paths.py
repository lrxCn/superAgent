"""Smoke coverage for runtime events across execution paths."""

from __future__ import annotations

import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.memory.graphiti import MockLongTermMemoryClient
from agent.tools.mcp import FakeMCPClient, ToolObservation, ToolSpec

pytestmark = pytest.mark.anyio

CONTROL_PREFIX = ("intake", "load_memory", "context_budget", "intent_router")
COMMON_SUFFIX = ("reflection_gate", "memory_write", "final_answer")


def _event_nodes(result: dict[str, object]) -> list[str]:
    events = result.get("runtime_events", [])
    return [str(event["node"]) for event in events]  # type: ignore[index]


def _assert_subsequence(expected: tuple[str, ...], actual: list[str]) -> None:
    index = 0
    for node in actual:
        if index < len(expected) and node == expected[index]:
            index += 1
    assert index == len(expected), f"expected {expected}, got {actual}"


def _react_graph():
    llm = FakeLLMClient(
        responses=[
            '{"action":"call_tool","tool_name":"read_file","arguments":{"path":"README.md"}}',
            '{"action":"finish","answer":"Tool path completed."}',
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
    return build_graph(llm_client=llm, mcp_client=mcp)


@pytest.mark.parametrize(
    ("message", "path", "middle"),
    [
        (
            "What is LangGraph in one sentence?",
            "direct_answer",
            ("direct_answer",),
        ),
        (
            "Read the README file and run the tests.",
            "react_agent",
            ("react_agent",),
        ),
        (
            "Design and implement a migration plan, then validate each step.",
            "planner",
            ("plan_generate", "plan_validate", "execute_plan", "step_observe"),
        ),
        (
            "Use researcher, coder, and reviewer agents in parallel.",
            "multi_agent_orchestrator",
            ("multi_agent_orchestrator",),
        ),
        (
            "help",
            "fallback",
            ("fallback",),
        ),
    ],
)
async def test_path_emits_minimal_runtime_event_sequence(
    message: str,
    path: str,
    middle: tuple[str, ...],
) -> None:
    if path == "react_agent":
        graph = _react_graph()
    elif path == "planner":
        graph = build_graph(
            llm_client=FakeLLMClient(
                responses=["analysis output", "execution output", "summary output"]
            )
        )
    else:
        graph = build_graph(
            llm_client=FakeLLMClient(responses=["observability smoke answer"]),
            memory_client=MockLongTermMemoryClient(),
        )

    result = await graph.ainvoke({"messages": [{"role": "user", "content": message}]})

    assert result["intent_decision"]["path"] == path
    nodes = _event_nodes(result)
    expected = (*CONTROL_PREFIX, *middle, *COMMON_SUFFIX)
    _assert_subsequence(expected, nodes)
    assert result["path_metrics"]["path"] in {path, "control", middle[-1]}
    summaries = [str(event["summary"]) for event in result.get("runtime_events", [])]
    assert not any("sk-live" in item for item in summaries)
    assert not any("api_key=secret" in item for item in summaries)


async def test_fallback_reason_is_observed() -> None:
    graph = build_graph(llm_client=FakeLLMClient(responses=["fallback answer"]))
    result = await graph.ainvoke({"messages": [{"role": "user", "content": "help"}]})

    fallback_events = [
        event
        for event in result.get("runtime_events", [])
        if event.get("node") == "fallback"
    ]
    assert fallback_events
    assert "fallback_reason=" in fallback_events[-1]["summary"]
