from __future__ import annotations

import pytest

from agent.config import load_config
from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.nodes.planner import create_execute_plan_node, create_step_observe_node
from agent.state import Plan

pytestmark = pytest.mark.anyio


def _runtime_config() -> dict[str, object]:
    return {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }


async def test_plan_agent_step_uses_production_worker_with_fake_llm() -> None:
    plan: Plan = {
        "steps": [
            {
                "id": "delegate",
                "title": "Delegate implementation to coder",
                "type": "agent",
                "dependencies": [],
                "acceptance_criteria": ["Worker output is recorded."],
                "status": "pending",
            }
        ],
        "status": "running",
    }
    execute = create_execute_plan_node(
        llm_client=FakeLLMClient(responses=["Production worker fake output."])
    )
    observe = create_step_observe_node()

    state = {
        "messages": [{"role": "user", "content": "Implement a focused change."}],
        "runtime_config": _runtime_config(),
        "plan": plan,
        "observations": [],
        "tool_calls": [],
        "mcp_sessions": [],
    }

    state = {**state, **await execute(state)}
    state = {**state, **await observe(state)}

    assert state["plan"]["steps"][0]["status"] == "completed"
    assert state["plan"]["steps"][0]["result"] == "Production worker fake output."
    assert state["observations"][0]["source"] == "plan_agent:delegate:coder_agent"


async def test_worker_path_uses_fake_llm_production_registry_in_graph() -> None:
    graph = build_graph(
        llm_client=FakeLLMClient(
            responses=[
                "Researcher output from fake production worker.",
                "Coder output from fake production worker.",
                "Reviewer output from fake production worker.",
            ]
        )
    )

    result = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Use researcher, coder, and reviewer agents in parallel.",
                }
            ]
        }
    )

    assert result["intent_decision"]["path"] == "multi_agent_orchestrator"
    assert "mock" not in result["final_answer"].lower()
    assert "Researcher output from fake production worker." in result["final_answer"]
    assert any(
        item["agent_name"] == "coder_agent"
        and item["output"] == "Coder output from fake production worker."
        for item in result["agent_results"]
    )


async def test_worker_path_real_llm_smoke_when_key_present() -> None:
    config = load_config()
    if not config.openai_api_key_present:
        pytest.skip("OPENAI_API_KEY is not configured in environment or .env.")

    graph = build_graph()
    result = await graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Use reviewer agent in parallel to review the claim: LangGraph coordinates agent state.",
                }
            ],
            "runtime_config": {
                **config.to_runtime_config(),
                "worker_timeout_seconds": 60,
                "reflection_enabled": False,
                "memory_enabled": False,
            },
        }
    )

    assert result["intent_decision"]["path"] == "multi_agent_orchestrator"
    assert result["agent_results"][0]["status"] in {"completed", "partial"}
    assert any(
        item["agent_name"] == "reviewer_agent"
        and item["status"] == "completed"
        and item["output"].strip()
        for item in result["agent_results"]
    )
