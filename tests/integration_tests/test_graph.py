import pytest

from agent import graph

pytestmark = pytest.mark.anyio


async def test_agent_simple_passthrough() -> None:
    inputs = {"messages": [{"role": "user", "content": "some request"}]}
    res = await graph.ainvoke(inputs)
    assert res["intent_decision"]["path"] == "direct_answer"
    assert res["memory_write_result"]["status"] == "skipped"
    assert res["final_answer"] == "SuperAgent runtime skeleton received: some request"
    assert "changeme" not in res


@pytest.mark.parametrize(
    ("message", "expected_path", "expected_answer"),
    [
        (
            "Read the README file and run the tests.",
            "react_agent",
            "ReAct agent path selected; tool execution is not implemented yet.",
        ),
        (
            "Design and implement a migration plan, then validate each step.",
            "planner",
            "Planner path selected; plan execution is not implemented yet.",
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
    res = await graph.ainvoke({"messages": [{"role": "user", "content": message}]})

    assert res["intent_decision"]["path"] == expected_path
    assert res["intent_decision"]["reason"]
    assert res["intent_decision"]["confidence"] >= 0.72
    assert res["intent_decision"]["signals"]
    assert res["intent_decision"]["requires_reflection"] is True
    assert res["final_answer"] == expected_answer
