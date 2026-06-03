"""Memory write policy and node tests."""

from __future__ import annotations

import pytest

from agent.graph import build_graph
from agent.llm import FakeLLMClient
from agent.memory.graphiti import MockLongTermMemoryClient
from agent.memory.policy import (
    evaluate_write_policies,
    is_stable_candidate,
    memory_write_skip_reason,
    sensitive_skip_reason,
)
from agent.nodes.memory_write import execute_memory_write
from agent.state import AgentState

pytestmark = pytest.mark.anyio


def _runtime_config(**overrides: object) -> dict[str, object]:
    base = {
        "react_max_steps": 8,
        "plan_max_steps": 12,
        "worker_max_concurrency": 4,
        "worker_timeout_seconds": 120,
        "tool_timeout_seconds": 30,
        "reflection_max_rounds": 1,
        "memory_enabled": True,
        "reflection_enabled": True,
    }
    base.update(overrides)
    return base


def _state(**overrides: object) -> AgentState:
    state: AgentState = {
        "messages": [{"role": "user", "content": "preference: concise Chinese answers"}],
        "runtime_config": _runtime_config(),
        "intent_decision": {
            "path": "direct_answer",
            "reason": "simple",
            "confidence": 0.82,
            "signals": ["simple_question"],
            "requires_reflection": False,
        },
        "evaluation": {
            "enabled": False,
            "status": "not_required",
            "issues": [],
            "suggestions": [],
        },
        "final_answer": "LangGraph is a stateful graph runtime for agents.",
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_sensitive_content_is_filtered() -> None:
    assert sensitive_skip_reason("password: hunter2") in {
        "sensitive_assignment",
        "sensitive_content",
    }
    assert sensitive_skip_reason("My api_key is sk-abcdefghijklmnopqrst") == "sensitive_content"

    policy = evaluate_write_policies(
        _state(
            messages=[
                {
                    "role": "user",
                    "content": "preference: use token sk-abcdefghijklmnopqrst for auth",
                }
            ]
        )
    )

    assert policy.candidates == []
    assert any("sensitive" in item for item in policy.skipped)


def test_evaluation_failure_skips_memory_write() -> None:
    assert (
        memory_write_skip_reason(
            _state(
                evaluation={
                    "enabled": True,
                    "status": "fail",
                    "issues": ["empty_answer"],
                    "suggestions": [],
                }
            )
        )
        == "evaluation_failed"
    )


def test_preference_candidate_is_stable_and_stored() -> None:
    policy = evaluate_write_policies(_state())

    assert len(policy.candidates) == 1
    assert policy.candidates[0].category == "preference"
    assert is_stable_candidate(policy.candidates[0], _state()) is True


@pytest.mark.anyio
async def test_execute_memory_write_stores_eligible_candidate() -> None:
    client = MockLongTermMemoryClient()
    result = await execute_memory_write(_state(), client=client)

    assert result["status"] == "stored"
    assert result["target"] == "graphiti"
    assert result["stored_count"] == 1
    assert len(client.records) == 1
    assert client.records[0].metadata["confidence"] == 0.9


@pytest.mark.anyio
async def test_execute_memory_write_skips_when_memory_disabled() -> None:
    client = MockLongTermMemoryClient()
    result = await execute_memory_write(
        _state(runtime_config=_runtime_config(memory_enabled=False)),
        client=client,
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "memory_disabled"
    assert client.records == []


@pytest.mark.anyio
async def test_graphiti_failure_records_error_without_blocking_answer() -> None:
    client = MockLongTermMemoryClient(write_error="graphiti unavailable")
    graph = build_graph(
        llm_client=FakeLLMClient(responses=["direct fake answer"]),
        memory_client=client,
    )
    res = await graph.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "preference: concise Chinese answers"}
            ]
        }
    )

    assert res["memory_write_result"]["status"] == "error"
    assert res["memory_write_result"]["error"] == "graphiti unavailable"
    assert res["final_answer"] == "direct fake answer"


@pytest.mark.anyio
async def test_graph_stores_memory_for_explicit_preference() -> None:
    client = MockLongTermMemoryClient()
    graph = build_graph(
        llm_client=FakeLLMClient(responses=["Stored preference acknowledged."]),
        memory_client=client,
    )
    res = await graph.ainvoke(
        {
            "messages": [
                {"role": "user", "content": "preference: concise Chinese answers"}
            ]
        }
    )

    assert res["memory_write_result"]["status"] == "stored"
    assert res["memory_write_result"]["stored_count"] == 1
    assert any("concise Chinese" in record.content for record in client.records)
