import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.tools.mcp import FakeMCPClient, ToolObservation, ToolSpec

pytestmark = pytest.mark.anyio


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


direct_graph = build_graph(llm_client=FakeLLMClient(responses=["direct fake answer"]))

plan_graph = build_graph(
    llm_client=FakeLLMClient(
        responses=[
            "analysis output",
            "execution output",
            "summary output",
        ]
    )
)


async def test_agent_simple_passthrough() -> None:
    inputs = {"messages": [{"role": "user", "content": "some request"}]}
    res = await direct_graph.ainvoke(inputs)
    assert res["intent_decision"]["path"] == "direct_answer"
    assert res["memory_write_result"]["status"] == "skipped"
    assert res["final_answer"] == "direct fake answer"
    assert "changeme" not in res


@pytest.mark.parametrize(
    ("message", "expected_path", "expected_answer"),
    [
        (
            "Design and implement a migration plan, then validate each step.",
            "planner",
            "Plan execution summary",
        ),
        (
            "Use researcher, coder, and reviewer agents in parallel.",
            "multi_agent_orchestrator",
            "Multi-agent path selected; worker orchestration is not implemented yet.",
        ),
        (
            "help",
            "fallback",
            "Fallback: Input is underspecified and needs clarification before execution.",
        ),
    ],
)
async def test_agent_routes_to_placeholder_paths(
    message: str,
    expected_path: str,
    expected_answer: str,
) -> None:
    graph = plan_graph if expected_path == "planner" else direct_graph
    res = await graph.ainvoke({"messages": [{"role": "user", "content": message}]})

    assert res["intent_decision"]["path"] == expected_path
    assert res["intent_decision"]["reason"]
    assert res["intent_decision"]["confidence"] >= 0.72
    assert res["intent_decision"]["signals"]
    assert res["intent_decision"]["requires_reflection"] is True
    if expected_path == "planner":
        assert res["plan"]["status"] == "completed"
        assert expected_answer in res["final_answer"]
    else:
        assert res["final_answer"] == expected_answer


async def test_agent_routes_tool_request_through_react_loop() -> None:
    graph = _react_graph()
    res = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Read the README file and run the tests."}]}
    )

    assert res["intent_decision"]["path"] == "react_agent"
    assert res["mcp_sessions"][0]["status"] == "connected"
    assert res["tool_calls"][0]["status"] == "completed"
    assert res["final_answer"] == "Tool path completed."
