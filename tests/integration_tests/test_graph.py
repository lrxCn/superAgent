import pytest

from agent.config import load_config
from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.reflection import create_evaluator_node
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
            "Multi-agent orchestration",
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
        assert expected_answer in res["final_answer"]
        if expected_path == "multi_agent_orchestrator":
            assert res["agent_results"][0]["agent_name"] == "orchestrator"
            assert res["agent_results"][0]["status"] in {"completed", "partial"}


async def test_agent_routes_tool_request_through_react_loop() -> None:
    graph = _react_graph()
    res = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Read the README file and run the tests."}]}
    )

    assert res["intent_decision"]["path"] == "react_agent"
    assert res["mcp_sessions"][0]["status"] == "connected"
    assert res["tool_calls"][0]["status"] == "completed"
    assert res["final_answer"] == "Tool path completed."


async def test_reflection_integration_uses_llm_evaluator() -> None:
    client = FakeLLMClient(
        responses=[
            '{"action":"finish","answer":"Tool path completed with enough detail."}',
            '{"status":"PASS","issues":[],"suggestions":[]}',
        ]
    )
    graph = build_graph(
        llm_client=client,
        mcp_client=FakeMCPClient(
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
        ),
    )

    res = await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Read the README file and run the tests."}]}
    )

    assert res["intent_decision"]["path"] == "react_agent"
    assert res["evaluation"]["enabled"] is True
    assert res["evaluation"]["status"] == "pass"
    assert res["evaluation"]["source"] == "llm"
    assert len(client.calls) == 2
    assert "reflection evaluator" in client.calls[-1].messages[0]["content"]


async def test_reflection_real_llm_evaluator_integration() -> None:
    config = load_config()
    if not config.openai_api_key_present:
        pytest.skip("OPENAI_API_KEY is required for real LLM reflection integration.")

    node = create_evaluator_node()
    res = await node(
        {
            "messages": [
                {"role": "user", "content": "Please review this short answer."}
            ],
            "runtime_config": config.to_runtime_config(),
            "intent_decision": {
                "path": "fallback",
                "reason": "reflection integration fixture",
                "confidence": 0.9,
                "signals": ["reflection_fixture"],
                "requires_reflection": True,
            },
            "final_answer": "LangGraph coordinates stateful agent workflows.",
            "evaluation": {
                "enabled": True,
                "status": "not_required",
                "issues": [],
                "suggestions": [],
                "gate_reasons": ["path:fallback"],
                "skip_reason": None,
            },
        }
    )

    assert res["evaluation"]["enabled"] is True
    assert res["evaluation"]["source"] == "llm"
    assert res["evaluation"]["model"] == config.openai_model_name
    assert res["evaluation"]["status"] in {"pass", "fail"}
    assert isinstance(res["evaluation"]["issues"], list)
    assert isinstance(res["evaluation"]["suggestions"], list)
